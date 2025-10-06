"""
Менеджер воркеров для пула.
"""

import threading
import time
from typing import List, Optional, Dict, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime

from ..models.worker import Worker, WorkerStatus
from ..models.task import Task, TaskResult
from ..utils.logger import get_logger
from ..exceptions import WorkerPoolError


logger = get_logger(__name__)


@dataclass
class WorkerManagerConfig:
    """Конфигурация менеджера воркеров."""
    min_workers: int = 1
    max_workers: int = 10
    worker_idle_timeout: float = 60.0  # Время простоя перед завершением воркера
    worker_startup_delay: float = 0.1  # Задержка при запуске воркера
    auto_scaling: bool = True  # Автоматическое масштабирование
    scaling_check_interval: float = 5.0  # Интервал проверки масштабирования


class WorkerManager:
    """Менеджер воркеров с автоматическим масштабированием."""
    
    def __init__(self, config: Optional[WorkerManagerConfig] = None):
        self.config = config or WorkerManagerConfig()
        self._workers: List[Worker] = []
        self._worker_threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._scaling_thread: Optional[threading.Thread] = None
        
        # Callback'и для взаимодействия с пулом
        self._task_executor: Optional[Callable[[Task], TaskResult]] = None
        self._get_task_callback: Optional[Callable] = None
        self._on_worker_error: Optional[Callable[[Worker, Exception]]] = None
        
        logger.info(f"WorkerManager initialized with config: {self.config}")
    
    def set_task_executor(self, executor: Callable[[Task], TaskResult]):
        """Установка исполнителя задач."""
        self._task_executor = executor
    
    def set_get_task_callback(self, callback: Callable):
        """Установка callback'а для получения задач."""
        self._get_task_callback = callback
    
    def set_on_worker_error(self, callback: Callable[[Worker, Exception], None]):
        """Установка callback'а для обработки ошибок воркеров."""
        self._on_worker_error = callback
    
    def start(self):
        """Запуск менеджера воркеров."""
        logger.info("Starting WorkerManager...")
        
        # Создание минимального количества воркеров
        for _ in range(self.config.min_workers):
            self._create_worker()
        
        # Запуск потока масштабирования
        if self.config.auto_scaling:
            self._start_scaling_thread()
        
        logger.info(f"WorkerManager started with {len(self._workers)} workers")
    
    def stop(self):
        """Остановка менеджера воркеров."""
        logger.info("Stopping WorkerManager...")
        
        self._shutdown_event.set()
        
        # Остановка потока масштабирования
        if self._scaling_thread and self._scaling_thread.is_alive():
            self._scaling_thread.join(timeout=5.0)
        
        # Остановка всех воркеров
        with self._lock:
            for worker in self._workers:
                self._stop_worker(worker)
            
            # Ожидание завершения потоков
            for thread in self._worker_threads.values():
                if thread.is_alive():
                    thread.join(timeout=5.0)
        
        logger.info("WorkerManager stopped")
    
    def _create_worker(self) -> Worker:
        """Создание нового воркера."""
        with self._lock:
            if len(self._workers) >= self.config.max_workers:
                raise WorkerPoolError(f"Maximum workers limit ({self.config.max_workers}) reached")
            
            worker = Worker(name=f"worker-{len(self._workers) + 1}")
            worker.start()
            self._workers.append(worker)
            
            # Создание потока для воркера
            thread = threading.Thread(
                target=self._worker_loop,
                args=(worker,),
                name=f"worker-thread-{worker.id}",
                daemon=True
            )
            thread.start()
            self._worker_threads[worker.id] = thread
            
            logger.info(f"Created worker {worker.id}")
            return worker
    
    def _stop_worker(self, worker: Worker):
        """Остановка воркера."""
        worker.set_shutting_down()
        logger.info(f"Stopping worker {worker.id}")
    
    def _worker_loop(self, worker: Worker):
        """Основной цикл воркера."""
        logger.info(f"Worker {worker.id} started")
        
        try:
            while not self._shutdown_event.is_set() and worker.status != WorkerStatus.STOPPED:
                try:
                    # Получение задачи
                    if self._get_task_callback:
                        task = self._get_task_callback(timeout=1.0)
                        if task:
                            self._execute_task_on_worker(task, worker)
                        else:
                            # Проверка таймаута простоя
                            if self._should_terminate_idle_worker(worker):
                                logger.info(f"Terminating idle worker {worker.id}")
                                break
                    else:
                        time.sleep(0.1)
                        
                except Exception as e:
                    logger.error(f"Error in worker {worker.id} loop: {e}")
                    if self._on_worker_error:
                        self._on_worker_error(worker, e)
                    
                    worker.set_error()
                    time.sleep(1.0)  # Пауза перед повтором
                    
        except Exception as e:
            logger.error(f"Fatal error in worker {worker.id}: {e}")
        finally:
            worker.stop()
            logger.info(f"Worker {worker.id} stopped")
    
    def _execute_task_on_worker(self, task: Task, worker: Worker):
        """Выполнение задачи на воркере."""
        if not self._task_executor:
            logger.error("No task executor set")
            return
        
        try:
            self._task_executor(task, worker)
        except Exception as e:
            logger.error(f"Task execution error on worker {worker.id}: {e}")
            if self._on_worker_error:
                self._on_worker_error(worker, e)
    
    def _should_terminate_idle_worker(self, worker: Worker) -> bool:
        """Проверка необходимости завершения простаивающего воркера."""
        if len(self._workers) <= self.config.min_workers:
            return False
        
        if worker.metrics.last_task_at:
            idle_time = (datetime.now() - worker.metrics.last_task_at).total_seconds()
            return idle_time > self.config.worker_idle_timeout
        
        return False
    
    def _start_scaling_thread(self):
        """Запуск потока масштабирования."""
        self._scaling_thread = threading.Thread(
            target=self._scaling_loop,
            name="worker-scaling-thread",
            daemon=True
        )
        self._scaling_thread.start()
        logger.info("Worker scaling thread started")
    
    def _scaling_loop(self):
        """Цикл автоматического масштабирования."""
        while not self._shutdown_event.is_set():
            try:
                self._check_scaling_needs()
                time.sleep(self.config.scaling_check_interval)
            except Exception as e:
                logger.error(f"Error in scaling loop: {e}")
                time.sleep(1.0)
    
    def _check_scaling_needs(self):
        """Проверка необходимости масштабирования."""
        with self._lock:
            current_workers = len(self._workers)
            idle_workers = sum(1 for w in self._workers if w.is_available())
            busy_workers = current_workers - idle_workers
            
            # Логика масштабирования (упрощенная)
            queue_size = 0
            if self._get_task_callback:
                # Получаем размер очереди (это нужно будет реализовать в TaskChannel)
                pass
            
            # Масштабирование вверх
            if (queue_size > busy_workers * 2 and 
                current_workers < self.config.max_workers):
                logger.info(f"Scaling up: creating new worker (queue: {queue_size}, workers: {current_workers})")
                try:
                    self._create_worker()
                except WorkerPoolError:
                    pass  # Достигнут лимит
            
            # Масштабирование вниз (удаление простаивающих воркеров)
            elif (idle_workers > 1 and 
                  current_workers > self.config.min_workers):
                idle_worker = next((w for w in self._workers if w.is_available()), None)
                if idle_worker and self._should_terminate_idle_worker(idle_worker):
                    logger.info(f"Scaling down: removing idle worker {idle_worker.id}")
                    self._remove_worker(idle_worker)
    
    def _remove_worker(self, worker: Worker):
        """Удаление воркера."""
        try:
            self._stop_worker(worker)
            self._workers.remove(worker)
            
            # Ожидание завершения потока
            thread = self._worker_threads.pop(worker.id, None)
            if thread and thread.is_alive():
                thread.join(timeout=2.0)
            
            logger.info(f"Removed worker {worker.id}")
        except Exception as e:
            logger.error(f"Error removing worker {worker.id}: {e}")
    
    def get_workers(self) -> List[Worker]:
        """Получение списка воркеров."""
        with self._lock:
            return self._workers.copy()
    
    def get_worker_by_id(self, worker_id: str) -> Optional[Worker]:
        """Получение воркера по ID."""
        with self._lock:
            return next((w for w in self._workers if w.id == worker_id), None)
    
    def get_worker_stats(self) -> Dict[str, Any]:
        """Получение статистики воркеров."""
        with self._lock:
            total_workers = len(self._workers)
            idle_workers = sum(1 for w in self._workers if w.is_available())
            busy_workers = sum(1 for w in self._workers if w.status == WorkerStatus.BUSY)
            
            total_tasks = sum(w.metrics.tasks_completed for w in self._workers)
            total_failed = sum(w.metrics.tasks_failed for w in self._workers)
            
            return {
                'total_workers': total_workers,
                'idle_workers': idle_workers,
                'busy_workers': busy_workers,
                'total_tasks_completed': total_tasks,
                'total_tasks_failed': total_failed,
                'average_tasks_per_worker': total_tasks / total_workers if total_workers > 0 else 0,
                'worker_utilization': (busy_workers / total_workers * 100) if total_workers > 0 else 0
            }
    
    def force_scale_up(self, count: int = 1):
        """Принудительное масштабирование вверх."""
        with self._lock:
            for _ in range(min(count, self.config.max_workers - len(self._workers))):
                try:
                    self._create_worker()
                except WorkerPoolError:
                    break
    
    def force_scale_down(self, count: int = 1):
        """Принудительное масштабирование вниз."""
        with self._lock:
            available_workers = [w for w in self._workers if w.is_available()]
            for _ in range(min(count, len(available_workers))):
                if len(self._workers) > self.config.min_workers:
                    self._remove_worker(available_workers.pop())
    
    def __repr__(self) -> str:
        stats = self.get_worker_stats()
        return f"WorkerManager(workers={stats['total_workers']}, idle={stats['idle_workers']}, busy={stats['busy_workers']})"
