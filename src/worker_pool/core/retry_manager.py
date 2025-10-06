"""
Менеджер ретраев с экспоненциальным backoff.
"""

import time
import random
import threading
from typing import Callable, Any, Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from ..models.task import Task, TaskStatus, TaskResult
from ..utils.logger import get_logger
from ..exceptions import RetryExhaustedError, TaskExecutionError


logger = get_logger(__name__)


class BackoffStrategy(Enum):
    """Стратегии backoff."""
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"
    RANDOM = "random"


@dataclass
class RetryConfig:
    """Конфигурация ретраев."""
    max_retries: int = 3
    base_delay: float = 1.0  # Базовая задержка в секундах
    max_delay: float = 60.0  # Максимальная задержка в секундах
    exponential_base: float = 2.0  # База для экспоненциального роста
    jitter: bool = True  # Добавлять случайность к задержке
    jitter_factor: float = 0.1  # Фактор джиттера (10%)
    strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    retry_on_exceptions: Optional[List[type]] = None  # Типы исключений для ретрая
    stop_on_exceptions: Optional[List[type]] = None  # Типы исключений для остановки


@dataclass
class RetryAttempt:
    """Информация о попытке ретрая."""
    attempt_number: int
    delay: float
    timestamp: datetime
    exception: Optional[Exception] = None
    task_id: str = ""


class RetryManager:
    """Менеджер ретраев с различными стратегиями backoff."""
    
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self._retry_history: Dict[str, List[RetryAttempt]] = {}
        self._lock = threading.Lock()
        
        # Статистика
        self._stats = {
            'total_retries': 0,
            'successful_retries': 0,
            'failed_retries': 0,
            'average_delay': 0.0,
            'max_delay_used': 0.0
        }
        
        logger.info(f"RetryManager initialized with config: {self.config}")
    
    def should_retry(self, task: Task, exception: Exception) -> bool:
        """
        Определение необходимости ретрая.
        
        Args:
            task: Задача
            exception: Исключение
            
        Returns:
            True если нужен ретрай, False иначе
        """
        # Проверка количества попыток
        if task.retry_count >= task.max_retries:
            return False
        
        # Проверка типов исключений для остановки
        if self.config.stop_on_exceptions:
            if any(isinstance(exception, exc_type) for exc_type in self.config.stop_on_exceptions):
                return False
        
        # Проверка типов исключений для ретрая
        if self.config.retry_on_exceptions:
            return any(isinstance(exception, exc_type) for exc_type in self.config.retry_on_exceptions)
        
        # По умолчанию ретраим все исключения
        return True
    
    def calculate_delay(self, attempt_number: int, task_id: str = "") -> float:
        """
        Расчет задержки для следующей попытки.
        
        Args:
            attempt_number: Номер попытки (начиная с 1)
            task_id: ID задачи для истории
            
        Returns:
            Задержка в секундах
        """
        if attempt_number <= 0:
            return self.config.base_delay
        
        if self.config.strategy == BackoffStrategy.FIXED:
            delay = self.config.base_delay
        elif self.config.strategy == BackoffStrategy.LINEAR:
            delay = self.config.base_delay * attempt_number
        elif self.config.strategy == BackoffStrategy.EXPONENTIAL:
            delay = self.config.base_delay * (self.config.exponential_base ** (attempt_number - 1))
        elif self.config.strategy == BackoffStrategy.RANDOM:
            delay = random.uniform(self.config.base_delay, self.config.max_delay)
        else:
            delay = self.config.base_delay
        
        # Ограничение максимальной задержки
        delay = min(delay, self.config.max_delay)
        
        # Добавление джиттера
        if self.config.jitter:
            jitter_amount = delay * self.config.jitter_factor
            delay += random.uniform(-jitter_amount, jitter_amount)
            delay = max(0, delay)  # Не может быть отрицательной
        
        # Сохранение в историю
        if task_id:
            self._record_attempt(task_id, attempt_number, delay)
        
        return delay
    
    def execute_with_retry(
        self, 
        task: Task, 
        executor_func: Callable[[Task], TaskResult]
    ) -> TaskResult:
        """
        Выполнение задачи с ретраями.
        
        Args:
            task: Задача для выполнения
            executor_func: Функция выполнения задачи
            
        Returns:
            Результат выполнения
            
        Raises:
            RetryExhaustedError: Если исчерпаны все попытки
        """
        last_exception = None
        start_time = time.time()
        
        for attempt in range(task.max_retries + 1):  # +1 для первой попытки
            try:
                logger.debug(f"Executing task {task.id}, attempt {attempt + 1}")
                
                # Обновление статуса задачи
                if attempt > 0:
                    task.status = TaskStatus.RETRYING
                    task.retry_count = attempt
                
                result = executor_func(task)
                
                # Успешное выполнение
                if result.is_success():
                    execution_time = time.time() - start_time
                    result.execution_time = execution_time
                    result.retry_count = attempt
                    
                    self._update_stats(True, attempt, execution_time)
                    logger.info(f"Task {task.id} completed successfully after {attempt + 1} attempts")
                    return result
                
                # Неудачное выполнение
                last_exception = result.error
                
            except Exception as e:
                last_exception = e
                logger.warning(f"Task {task.id} failed on attempt {attempt + 1}: {e}")
            
            # Проверка необходимости ретрая
            if attempt < task.max_retries and self.should_retry(task, last_exception):
                delay = self.calculate_delay(attempt + 1, task.id)
                
                logger.info(f"Retrying task {task.id} in {delay:.2f} seconds (attempt {attempt + 2})")
                
                # Ожидание перед следующей попыткой
                time.sleep(delay)
            else:
                break
        
        # Все попытки исчерпаны
        execution_time = time.time() - start_time
        self._update_stats(False, task.retry_count, execution_time)
        
        error_msg = f"Task {task.id} failed after {task.retry_count + 1} attempts"
        logger.error(error_msg)
        
        if last_exception:
            raise RetryExhaustedError(error_msg) from last_exception
        else:
            raise RetryExhaustedError(error_msg)
    
    def _record_attempt(self, task_id: str, attempt_number: int, delay: float):
        """Запись попытки ретрая в историю."""
        with self._lock:
            if task_id not in self._retry_history:
                self._retry_history[task_id] = []
            
            attempt = RetryAttempt(
                attempt_number=attempt_number,
                delay=delay,
                timestamp=datetime.now(),
                task_id=task_id
            )
            self._retry_history[task_id].append(attempt)
    
    def _update_stats(self, success: bool, retry_count: int, execution_time: float):
        """Обновление статистики."""
        with self._lock:
            self._stats['total_retries'] += retry_count
            
            if success:
                self._stats['successful_retries'] += 1
            else:
                self._stats['failed_retries'] += 1
    
    def get_retry_history(self, task_id: str) -> List[RetryAttempt]:
        """Получение истории ретраев для задачи."""
        with self._lock:
            return self._retry_history.get(task_id, []).copy()
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики ретраев."""
        with self._lock:
            stats = self._stats.copy()
            
            # Расчет средней задержки
            total_delays = sum(
                sum(attempt.delay for attempt in attempts)
                for attempts in self._retry_history.values()
            )
            total_attempts = sum(len(attempts) for attempts in self._retry_history.values())
            
            if total_attempts > 0:
                stats['average_delay'] = total_delays / total_attempts
                stats['max_delay_used'] = max(
                    max(attempt.delay for attempt in attempts)
                    for attempts in self._retry_history.values()
                    if attempts
                )
            
            stats['total_tasks_with_retries'] = len(self._retry_history)
            return stats
    
    def clear_history(self):
        """Очистка истории ретраев."""
        with self._lock:
            self._retry_history.clear()
            self._stats = {
                'total_retries': 0,
                'successful_retries': 0,
                'failed_retries': 0,
                'average_delay': 0.0,
                'max_delay_used': 0.0
            }
        
        logger.info("Retry history cleared")
    
    def __repr__(self) -> str:
        stats = self.get_stats()
        return f"RetryManager(retries={stats['total_retries']}, success_rate={stats.get('success_rate', 0):.1f}%)"
