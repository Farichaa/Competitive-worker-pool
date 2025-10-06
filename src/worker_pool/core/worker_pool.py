"""
Основной класс конкурентного пула воркеров.
"""

import threading
import time
from typing import Callable, Any, Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime

from .task_channel import TaskChannel, ChannelConfig
from .retry_manager import RetryManager, RetryConfig
from .graceful_shutdown import GracefulShutdown, ShutdownConfig
from .task_executor import TaskExecutor, ExecutionConfig
from .worker_manager import WorkerManager, WorkerManagerConfig

from ..models.task import Task, TaskResult, TaskStatus, TaskPriority
from ..models.worker import Worker, WorkerStatus
from ..models.pool_metrics import PoolMetrics, PoolStatus

from ..utils.logger import get_logger
from ..exceptions import WorkerPoolError, TaskExecutionError


logger = get_logger(__name__)


@dataclass
class WorkerPoolConfig:
    """Конфигурация пула воркеров."""
    
    # Основные параметры
    min_workers: int = 2
    max_workers: int = 10
    
    # Конфигурации компонентов
    channel_config: ChannelConfig = field(default_factory=ChannelConfig)
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    shutdown_config: ShutdownConfig = field(default_factory=ShutdownConfig)
    execution_config: ExecutionConfig = field(default_factory=ExecutionConfig)
    worker_config: WorkerManagerConfig = field(default_factory=WorkerManagerConfig)
    
    # Дополнительные параметры
    enable_metrics: bool = True
    enable_monitoring: bool = True
    log_level: str = "INFO"


class WorkerPool:
    """Конкурентный пул воркеров с каналом задач, graceful shutdown и ретраями."""
    
    def __init__(self, config: Optional[WorkerPoolConfig] = None):
        self.config = config or WorkerPoolConfig()
        self._lock = threading.Lock()
        self._status = PoolStatus.STOPPED
        
        # Инициализация компонентов
        self._task_channel = TaskChannel(self.config.channel_config)
        self._retry_manager = RetryManager(self.config.retry_config)
        self._graceful_shutdown = GracefulShutdown(self.config.shutdown_config)
        self._task_executor = TaskExecutor(self.config.execution_config)
        
        # Настройка менеджера воркеров
        worker_config = self.config.worker_config
        worker_config.min_workers = self.config.min_workers
        worker_config.max_workers = self.config.max_workers
        self._worker_manager = WorkerManager(worker_config)
        
        # Метрики пула
        self._pool_metrics = PoolMetrics()
        
        # Настройка callback'ов
        self._setup_callbacks()
        
        logger.info(f"WorkerPool initialized with config: {self.config}")
    
    def _setup_callbacks(self):
        """Настройка callback'ов между компонентами."""
        # Callback для менеджера воркеров
        self._worker_manager.set_task_executor(self._execute_task_with_retry)
        self._worker_manager.set_get_task_callback(self._task_channel.get_task)
        self._worker_manager.set_on_worker_error(self._on_worker_error)
        
        # Callback для graceful shutdown
        self._graceful_shutdown.add_cleanup_callback(self._cleanup_resources)
    
    def start(self):
        """Запуск пула воркеров."""
        with self._lock:
            if self._status != PoolStatus.STOPPED:
                raise WorkerPoolError(f"Pool is not stopped (current status: {self._status.value})")
            
            logger.info("Starting WorkerPool...")
            self._status = PoolStatus.STARTING
            
            try:
                # Запуск менеджера воркеров
                self._worker_manager.start()
                
                # Инициализация метрик
                self._pool_metrics.start_pool()
                
                self._status = PoolStatus.RUNNING
                logger.info("WorkerPool started successfully")
                
            except Exception as e:
                self._status = PoolStatus.ERROR
                logger.error(f"Failed to start WorkerPool: {e}")
                raise WorkerPoolError(f"Failed to start pool: {e}") from e
    
    def stop(self, timeout: Optional[float] = None):
        """Остановка пула воркеров с graceful shutdown."""
        logger.info("Stopping WorkerPool...")
        
        # Инициация graceful shutdown
        self._graceful_shutdown.initiate_shutdown()
        
        # Выполнение shutdown
        shutdown_status = self._graceful_shutdown.execute_shutdown(
            stop_new_tasks_callback=self._stop_accepting_tasks,
            get_pending_tasks_callback=lambda: len(self._task_channel),
            terminate_workers_callback=self._worker_manager.stop
        )
        
        with self._lock:
            if shutdown_status.completed:
                self._status = PoolStatus.STOPPED
                self._pool_metrics.stop_pool()
                logger.info("WorkerPool stopped successfully")
            else:
                self._status = PoolStatus.ERROR
                logger.error("WorkerPool shutdown failed")
    
    def submit_task(
        self, 
        func: Callable, 
        *args, 
        name: str = "",
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> str:
        """
        Отправка задачи в пул.
        
        Args:
            func: Функция для выполнения
            *args: Аргументы функции
            name: Имя задачи
            priority: Приоритет задачи
            max_retries: Максимальное количество ретраев
            timeout: Таймаут выполнения
            **kwargs: Именованные аргументы функции
            
        Returns:
            ID задачи
        """
        if self._status != PoolStatus.RUNNING:
            raise WorkerPoolError(f"Pool is not running (current status: {self._status.value})")
        
        if self._graceful_shutdown.is_shutdown_initiated():
            raise WorkerPoolError("Pool is shutting down")
        
        # Создание задачи
        task = Task(
            name=name or func.__name__,
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority,
            max_retries=max_retries or self.config.retry_config.max_retries,
            timeout=timeout or self.config.execution_config.timeout
        )
        
        # Отправка в канал
        success = self._task_channel.submit_task(task)
        if not success:
            raise WorkerPoolError("Failed to submit task to channel")
        
        # Обновление метрик
        self._pool_metrics.total_tasks_submitted += 1
        self._pool_metrics.update_queue_size(len(self._task_channel))
        
        logger.debug(f"Task {task.id} submitted to pool")
        return task.id
    
    def _execute_task_with_retry(self, task: Task, worker: Worker) -> TaskResult:
        """Выполнение задачи с ретраями."""
        def executor_func(t: Task) -> TaskResult:
            return self._task_executor.execute_task(t, worker)
        
        return self._retry_manager.execute_with_retry(task, executor_func)
    
    def _stop_accepting_tasks(self):
        """Остановка приема новых задач."""
        logger.info("Stopping new task acceptance")
        # Канал автоматически перестанет принимать задачи при shutdown
    
    def _on_worker_error(self, worker: Worker, error: Exception):
        """Обработка ошибки воркера."""
        logger.error(f"Worker {worker.id} error: {error}")
        worker.set_error()
        
        # Обновление метрик
        self._pool_metrics.total_tasks_failed += 1
    
    def _cleanup_resources(self):
        """Очистка ресурсов при завершении."""
        logger.info("Cleaning up pool resources")
        
        # Очистка канала
        self._task_channel.clear()
        
        # Сброс метрик
        if self.config.enable_metrics:
            self._retry_manager.clear_history()
            self._task_executor.reset_metrics()
    
    def get_status(self) -> PoolStatus:
        """Получение статуса пула."""
        return self._status
    
    def get_metrics(self) -> Dict[str, Any]:
        """Получение метрик пула."""
        with self._lock:
            pool_metrics = self._pool_metrics.to_dict()
            
            # Добавление метрик компонентов
            pool_metrics.update({
                'channel_metrics': self._task_channel.get_metrics(),
                'retry_metrics': self._retry_manager.get_stats(),
                'execution_metrics': self._task_executor.get_metrics(),
                'worker_metrics': self._worker_manager.get_worker_stats()
            })
            
            return pool_metrics
    
    def get_worker_count(self) -> int:
        """Получение количества воркеров."""
        return len(self._worker_manager.get_workers())
    
    def get_queue_size(self) -> int:
        """Получение размера очереди задач."""
        return len(self._task_channel)
    
    def scale_workers(self, count: int):
        """
        Масштабирование количества воркеров.
        
        Args:
            count: Новое количество воркеров (положительное - увеличение, отрицательное - уменьшение)
        """
        if count > 0:
            self._worker_manager.force_scale_up(count)
        elif count < 0:
            self._worker_manager.force_scale_down(abs(count))
        
        logger.info(f"Scaled workers by {count}, current count: {self.get_worker_count()}")
    
    def get_workers(self) -> List[Worker]:
        """Получение списка воркеров."""
        return self._worker_manager.get_workers()
    
    def get_worker_by_id(self, worker_id: str) -> Optional[Worker]:
        """Получение воркера по ID."""
        return self._worker_manager.get_worker_by_id(worker_id)
    
    def is_running(self) -> bool:
        """Проверка работы пула."""
        return self._status == PoolStatus.RUNNING
    
    def is_shutting_down(self) -> bool:
        """Проверка процесса завершения работы."""
        return self._graceful_shutdown.is_shutdown_initiated()
    
    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Ожидание завершения всех задач.
        
        Args:
            timeout: Таймаут ожидания
            
        Returns:
            True если все задачи завершены, False если таймаут
        """
        if timeout is None:
            timeout = 30.0
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if len(self._task_channel) == 0:
                # Проверяем, что все воркеры свободны
                busy_workers = sum(1 for w in self.get_workers() if w.status == WorkerStatus.BUSY)
                if busy_workers == 0:
                    return True
            
            time.sleep(0.1)
        
        return False
    
    def __enter__(self):
        """Контекстный менеджер - вход."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер - выход."""
        self.stop()
    
    def __repr__(self) -> str:
        return (f"WorkerPool(status={self._status.value}, "
                f"workers={self.get_worker_count()}, "
                f"queue_size={self.get_queue_size()})")
