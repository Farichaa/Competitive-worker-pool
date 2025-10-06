"""
Исполнитель задач для пула воркеров.
"""

import time
import threading
from typing import Callable, Any, Optional, Dict
from dataclasses import dataclass
from datetime import datetime

from ..models.task import Task, TaskResult, TaskStatus
from ..models.worker import Worker, WorkerStatus
from ..utils.logger import get_logger
from ..exceptions import TaskExecutionError


logger = get_logger(__name__)


@dataclass
class ExecutionConfig:
    """Конфигурация выполнения задач."""
    timeout: Optional[float] = None
    enable_metrics: bool = True
    capture_exceptions: bool = True
    log_execution_details: bool = True


class TaskExecutor:
    """Исполнитель задач с поддержкой таймаутов и метрик."""
    
    def __init__(self, config: Optional[ExecutionConfig] = None):
        self.config = config or ExecutionConfig()
        self._execution_lock = threading.Lock()
        
        # Метрики выполнения
        self._metrics = {
            'total_executions': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'timeout_executions': 0,
            'total_execution_time': 0.0,
            'average_execution_time': 0.0,
            'max_execution_time': 0.0,
            'min_execution_time': float('inf')
        }
        
        logger.info(f"TaskExecutor initialized with config: {self.config}")
    
    def execute_task(self, task: Task, worker: Worker) -> TaskResult:
        """
        Выполнение задачи.
        
        Args:
            task: Задача для выполнения
            worker: Воркер, выполняющий задачу
            
        Returns:
            Результат выполнения задачи
        """
        start_time = time.time()
        execution_time = 0.0
        
        # Обновление статусов
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        worker.set_busy()
        
        try:
            if self.config.log_execution_details:
                logger.info(f"Executing task {task.id} on worker {worker.id}")
            
            # Выполнение задачи
            if self.config.timeout:
                result = self._execute_with_timeout(task, worker)
            else:
                result = self._execute_sync(task, worker)
            
            execution_time = time.time() - start_time
            
            # Обновление результата
            task.result = result
            task.completed_at = datetime.now()
            task.status = TaskStatus.COMPLETED
            
            # Создание TaskResult
            task_result = TaskResult(
                task_id=task.id,
                status=TaskStatus.COMPLETED,
                result=result,
                execution_time=execution_time,
                retry_count=task.retry_count,
                metadata=task.metadata
            )
            
            self._update_metrics(execution_time, True)
            
            if self.config.log_execution_details:
                logger.info(f"Task {task.id} completed successfully in {execution_time:.3f}s")
            
            return task_result
            
        except TimeoutError as e:
            execution_time = time.time() - start_time
            task.status = TaskStatus.FAILED
            task.error = e
            
            self._update_metrics(execution_time, False, is_timeout=True)
            
            logger.error(f"Task {task.id} timed out after {execution_time:.3f}s")
            
            return TaskResult(
                task_id=task.id,
                status=TaskStatus.FAILED,
                error=e,
                execution_time=execution_time,
                retry_count=task.retry_count
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            task.status = TaskStatus.FAILED
            task.error = e
            
            self._update_metrics(execution_time, False)
            
            logger.error(f"Task {task.id} failed with error: {e}")
            
            return TaskResult(
                task_id=task.id,
                status=TaskStatus.FAILED,
                error=e,
                execution_time=execution_time,
                retry_count=task.retry_count
            )
            
        finally:
            # Возвращение воркера в состояние idle
            worker.set_idle()
            worker.update_metrics(execution_time, task.status == TaskStatus.COMPLETED)
    
    def _execute_sync(self, task: Task, worker: Worker) -> Any:
        """Синхронное выполнение задачи."""
        try:
            return task.func(*task.args, **task.kwargs)
        except Exception as e:
            if self.config.capture_exceptions:
                raise TaskExecutionError(f"Task execution failed: {e}") from e
            raise
    
    def _execute_with_timeout(self, task: Task, worker: Worker) -> Any:
        """Выполнение задачи с таймаутом."""
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(task.func, *task.args, **task.kwargs)
            
            try:
                result = future.result(timeout=self.config.timeout)
                return result
            except concurrent.futures.TimeoutError:
                # Отмена выполнения
                future.cancel()
                raise TimeoutError(f"Task {task.id} timed out after {self.config.timeout}s")
            except Exception as e:
                if self.config.capture_exceptions:
                    raise TaskExecutionError(f"Task execution failed: {e}") from e
                raise
    
    def _update_metrics(self, execution_time: float, success: bool, is_timeout: bool = False):
        """Обновление метрик выполнения."""
        with self._execution_lock:
            self._metrics['total_executions'] += 1
            self._metrics['total_execution_time'] += execution_time
            
            # Обновление времени выполнения
            self._metrics['max_execution_time'] = max(
                self._metrics['max_execution_time'], 
                execution_time
            )
            self._metrics['min_execution_time'] = min(
                self._metrics['min_execution_time'], 
                execution_time
            )
            self._metrics['average_execution_time'] = (
                self._metrics['total_execution_time'] / self._metrics['total_executions']
            )
            
            if success:
                self._metrics['successful_executions'] += 1
            else:
                self._metrics['failed_executions'] += 1
                if is_timeout:
                    self._metrics['timeout_executions'] += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """Получение метрик выполнения."""
        with self._execution_lock:
            metrics = self._metrics.copy()
            
            # Расчет процентов
            total = metrics['total_executions']
            if total > 0:
                metrics['success_rate'] = (metrics['successful_executions'] / total) * 100
                metrics['failure_rate'] = (metrics['failed_executions'] / total) * 100
                metrics['timeout_rate'] = (metrics['timeout_executions'] / total) * 100
            else:
                metrics['success_rate'] = 0.0
                metrics['failure_rate'] = 0.0
                metrics['timeout_rate'] = 0.0
            
            # Исправление min_execution_time если не было выполнений
            if metrics['min_execution_time'] == float('inf'):
                metrics['min_execution_time'] = 0.0
            
            return metrics
    
    def reset_metrics(self):
        """Сброс метрик."""
        with self._execution_lock:
            self._metrics = {
                'total_executions': 0,
                'successful_executions': 0,
                'failed_executions': 0,
                'timeout_executions': 0,
                'total_execution_time': 0.0,
                'average_execution_time': 0.0,
                'max_execution_time': 0.0,
                'min_execution_time': float('inf')
            }
        
        logger.info("TaskExecutor metrics reset")
    
    def __repr__(self) -> str:
        metrics = self.get_metrics()
        return f"TaskExecutor(executions={metrics['total_executions']}, success_rate={metrics['success_rate']:.1f}%)"
