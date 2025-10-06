"""
Модели воркеров для пула.
"""

import uuid
import time
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock


class WorkerStatus(Enum):
    """Статусы воркеров."""
    IDLE = "idle"
    BUSY = "busy"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class WorkerMetrics:
    """Метрики воркера."""
    
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_execution_time: float = 0.0
    average_execution_time: float = 0.0
    last_task_at: Optional[datetime] = None
    uptime: float = 0.0
    error_count: int = 0
    
    def update_execution_time(self, execution_time: float):
        """Обновление времени выполнения."""
        self.tasks_completed += 1
        self.total_execution_time += execution_time
        self.average_execution_time = self.total_execution_time / self.tasks_completed
        self.last_task_at = datetime.now()
    
    def update_failure(self):
        """Обновление статистики ошибок."""
        self.tasks_failed += 1
        self.error_count += 1
    
    def get_success_rate(self) -> float:
        """Получение процента успешных задач."""
        total = self.tasks_completed + self.tasks_failed
        if total == 0:
            return 0.0
        return (self.tasks_completed / total) * 100


@dataclass
class Worker:
    """Представление воркера."""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    status: WorkerStatus = WorkerStatus.IDLE
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    metrics: WorkerMetrics = field(default_factory=WorkerMetrics)
    metadata: Dict[str, Any] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)
    
    def start(self):
        """Запуск воркера."""
        with self._lock:
            self.status = WorkerStatus.IDLE
            self.started_at = datetime.now()
    
    def stop(self):
        """Остановка воркера."""
        with self._lock:
            self.status = WorkerStatus.STOPPED
            self.stopped_at = datetime.now()
            if self.started_at:
                self.metrics.uptime = (self.stopped_at - self.started_at).total_seconds()
    
    def set_busy(self):
        """Установка статуса занят."""
        with self._lock:
            if self.status == WorkerStatus.IDLE:
                self.status = WorkerStatus.BUSY
    
    def set_idle(self):
        """Установка статуса свободен."""
        with self._lock:
            if self.status == WorkerStatus.BUSY:
                self.status = WorkerStatus.IDLE
    
    def set_shutting_down(self):
        """Установка статуса завершения работы."""
        with self._lock:
            self.status = WorkerStatus.SHUTTING_DOWN
    
    def set_error(self):
        """Установка статуса ошибки."""
        with self._lock:
            self.status = WorkerStatus.ERROR
            self.metrics.update_failure()
    
    def update_metrics(self, execution_time: float, success: bool = True):
        """Обновление метрик."""
        with self._lock:
            if success:
                self.metrics.update_execution_time(execution_time)
            else:
                self.metrics.update_failure()
    
    def is_available(self) -> bool:
        """Проверка доступности воркера."""
        return self.status == WorkerStatus.IDLE
    
    def get_uptime(self) -> float:
        """Получение времени работы."""
        if self.started_at and not self.stopped_at:
            return (datetime.now() - self.started_at).total_seconds()
        return self.metrics.uptime
