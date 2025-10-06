"""
Метрики пула воркеров.
"""

from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from .worker import WorkerMetrics


class PoolStatus(Enum):
    """Статусы пула."""
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class PoolMetrics:
    """Метрики пула воркеров."""
    
    # Основные метрики
    total_tasks_submitted: int = 0
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    total_tasks_retried: int = 0
    
    # Метрики времени
    total_execution_time: float = 0.0
    average_execution_time: float = 0.0
    max_execution_time: float = 0.0
    min_execution_time: float = float('inf')
    
    # Метрики очереди
    current_queue_size: int = 0
    max_queue_size: int = 0
    average_queue_size: float = 0.0
    
    # Метрики воркеров
    total_workers: int = 0
    active_workers: int = 0
    idle_workers: int = 0
    busy_workers: int = 0
    
    # Метрики производительности
    throughput_per_second: float = 0.0
    success_rate: float = 0.0
    error_rate: float = 0.0
    
    # Временные метрики
    pool_start_time: Optional[datetime] = None
    pool_stop_time: Optional[datetime] = None
    uptime: float = 0.0
    
    # Дополнительные метрики
    retry_rate: float = 0.0
    timeout_rate: float = 0.0
    graceful_shutdown_count: int = 0
    
    def start_pool(self):
        """Запуск пула."""
        self.pool_start_time = datetime.now()
    
    def stop_pool(self):
        """Остановка пула."""
        self.pool_stop_time = datetime.now()
        if self.pool_start_time:
            self.uptime = (self.pool_stop_time - self.pool_start_time).total_seconds()
    
    def update_task_completion(self, execution_time: float, success: bool = True):
        """Обновление завершения задачи."""
        self.total_tasks_completed += 1
        self.total_execution_time += execution_time
        
        # Обновление времени выполнения
        self.max_execution_time = max(self.max_execution_time, execution_time)
        self.min_execution_time = min(self.min_execution_time, execution_time)
        self.average_execution_time = self.total_execution_time / self.total_tasks_completed
        
        if not success:
            self.total_tasks_failed += 1
        
        self._update_rates()
    
    def update_task_retry(self):
        """Обновление ретрая задачи."""
        self.total_tasks_retried += 1
        self._update_rates()
    
    def update_queue_size(self, size: int):
        """Обновление размера очереди."""
        self.current_queue_size = size
        self.max_queue_size = max(self.max_queue_size, size)
        # Простое скользящее среднее
        if self.average_queue_size == 0:
            self.average_queue_size = size
        else:
            self.average_queue_size = (self.average_queue_size + size) / 2
    
    def update_worker_stats(self, total: int, active: int, idle: int, busy: int):
        """Обновление статистики воркеров."""
        self.total_workers = total
        self.active_workers = active
        self.idle_workers = idle
        self.busy_workers = busy
    
    def _update_rates(self):
        """Обновление процентных соотношений."""
        total_processed = self.total_tasks_completed + self.total_tasks_failed
        if total_processed > 0:
            self.success_rate = (self.total_tasks_completed / total_processed) * 100
            self.error_rate = (self.total_tasks_failed / total_processed) * 100
        
        if self.total_tasks_submitted > 0:
            self.retry_rate = (self.total_tasks_retried / self.total_tasks_submitted) * 100
        
        # Расчет throughput
        if self.pool_start_time and not self.pool_stop_time:
            uptime = (datetime.now() - self.pool_start_time).total_seconds()
            if uptime > 0:
                self.throughput_per_second = total_processed / uptime
    
    def get_uptime(self) -> float:
        """Получение времени работы пула."""
        if self.pool_start_time and not self.pool_stop_time:
            return (datetime.now() - self.pool_start_time).total_seconds()
        return self.uptime
    
    def to_dict(self) -> Dict:
        """Преобразование в словарь."""
        return {
            'total_tasks_submitted': self.total_tasks_submitted,
            'total_tasks_completed': self.total_tasks_completed,
            'total_tasks_failed': self.total_tasks_failed,
            'total_tasks_retried': self.total_tasks_retried,
            'total_execution_time': self.total_execution_time,
            'average_execution_time': self.average_execution_time,
            'max_execution_time': self.max_execution_time,
            'min_execution_time': self.min_execution_time if self.min_execution_time != float('inf') else 0,
            'current_queue_size': self.current_queue_size,
            'max_queue_size': self.max_queue_size,
            'average_queue_size': self.average_queue_size,
            'total_workers': self.total_workers,
            'active_workers': self.active_workers,
            'idle_workers': self.idle_workers,
            'busy_workers': self.busy_workers,
            'throughput_per_second': self.throughput_per_second,
            'success_rate': self.success_rate,
            'error_rate': self.error_rate,
            'retry_rate': self.retry_rate,
            'uptime': self.get_uptime()
        }
