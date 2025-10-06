"""
Конкурентный пул воркеров с каналом задач, graceful shutdown и ретраями с backoff.

Основные компоненты:
- WorkerPool: основной класс для управления пулом воркеров
- TaskChannel: канал для передачи задач
- RetryManager: менеджер для ретраев с экспоненциальным backoff
- GracefulShutdown: механизм корректного завершения работы
"""

from .core.worker_pool import WorkerPool
from .core.task_channel import TaskChannel
from .core.retry_manager import RetryManager, RetryConfig
from .core.graceful_shutdown import GracefulShutdown
from .models.task import Task, TaskResult, TaskStatus
from .models.worker import Worker, WorkerStatus
from .utils.config import Config, load_config
from .utils.logger import get_logger
from .exceptions import (
    WorkerPoolError,
    TaskExecutionError,
    RetryExhaustedError,
    ShutdownError
)

__version__ = "1.0.0"
__author__ = "Worker Pool Team"

__all__ = [
    "WorkerPool",
    "TaskChannel", 
    "RetryManager",
    "RetryConfig",
    "GracefulShutdown",
    "Task",
    "TaskResult",
    "TaskStatus",
    "Worker",
    "WorkerStatus",
    "Config",
    "load_config",
    "get_logger",
    "WorkerPoolError",
    "TaskExecutionError", 
    "RetryExhaustedError",
    "ShutdownError"
]
