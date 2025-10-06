"""
Модели данных для пула воркеров.
"""

from .task import Task, TaskResult, TaskStatus, TaskPriority
from .worker import Worker, WorkerStatus, WorkerMetrics
from .pool_metrics import PoolMetrics, PoolStatus

__all__ = [
    "Task",
    "TaskResult", 
    "TaskStatus",
    "TaskPriority",
    "Worker",
    "WorkerStatus",
    "WorkerMetrics",
    "PoolMetrics",
    "PoolStatus"
]
