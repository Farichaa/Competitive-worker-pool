"""
Модели задач для пула воркеров.
"""

import uuid
import time
from enum import Enum
from typing import Any, Callable, Optional, Dict
from dataclasses import dataclass, field
from datetime import datetime


class TaskStatus(Enum):
    """Статусы задач."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Приоритеты задач."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Task:
    """Представление задачи."""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    func: Callable = None
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    max_retries: int = 3
    timeout: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[Exception] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Валидация после инициализации."""
        if not self.func:
            raise ValueError("Task function is required")
        if not isinstance(self.func, Callable):
            raise ValueError("Task function must be callable")


@dataclass
class TaskResult:
    """Результат выполнения задачи."""
    
    task_id: str
    status: TaskStatus
    result: Optional[Any] = None
    error: Optional[Exception] = None
    execution_time: Optional[float] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    completed_at: datetime = field(default_factory=datetime.now)
    
    def is_success(self) -> bool:
        """Проверка успешности выполнения."""
        return self.status == TaskStatus.COMPLETED
    
    def is_failure(self) -> bool:
        """Проверка неудачного выполнения."""
        return self.status in [TaskStatus.FAILED, TaskStatus.CANCELLED]
