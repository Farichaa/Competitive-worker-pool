"""
Декораторы для пула воркеров.
"""

import time
import functools
import threading
from typing import Callable, Any, Optional, Union, List
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..utils.logger import get_logger


logger = get_logger(__name__)


@dataclass
class RateLimitConfig:
    """Конфигурация ограничения скорости."""
    max_calls: int = 100
    time_window: float = 60.0  # секунды
    burst_limit: int = 10  # максимальное количество вызовов подряд


class RateLimiter:
    """Ограничитель скорости выполнения."""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._calls = []
        self._lock = threading.Lock()
    
    def is_allowed(self) -> bool:
        """Проверка разрешения выполнения."""
        with self._lock:
            now = time.time()
            
            # Удаление старых вызовов
            cutoff_time = now - self.config.time_window
            self._calls = [call_time for call_time in self._calls if call_time > cutoff_time]
            
            # Проверка лимитов
            if len(self._calls) >= self.config.max_calls:
                return False
            
            # Добавление текущего вызова
            self._calls.append(now)
            return True
    
    def wait_time(self) -> float:
        """Время ожидания до следующего разрешенного вызова."""
        with self._lock:
            if len(self._calls) < self.config.max_calls:
                return 0.0
            
            oldest_call = min(self._calls)
            return (oldest_call + self.config.time_window) - time.time()


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
    on_failure: Optional[Callable] = None
):
    """
    Декоратор для повторных попыток выполнения функции.
    
    Args:
        max_attempts: Максимальное количество попыток
        delay: Начальная задержка между попытками
        backoff_factor: Коэффициент увеличения задержки
        exceptions: Типы исключений для ретрая
        on_failure: Callback при неудаче
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        if on_failure:
                            on_failure(e, attempt + 1)
                        logger.error(f"Function {func.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    
                    logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {current_delay}s")
                    time.sleep(current_delay)
                    current_delay *= backoff_factor
            
        return wrapper
    return decorator


def timeout(seconds: float):
    """
    Декоратор для ограничения времени выполнения функции.
    
    Args:
        seconds: Максимальное время выполнения в секундах
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Function {func.__name__} timed out after {seconds} seconds")
            
            # Установка обработчика таймаута
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(seconds))
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                # Восстановление старого обработчика
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        
        return wrapper
    return decorator


def rate_limit(config: Union[RateLimitConfig, dict]):
    """
    Декоратор для ограничения скорости выполнения функции.
    
    Args:
        config: Конфигурация ограничения скорости
    """
    if isinstance(config, dict):
        config = RateLimitConfig(**config)
    
    limiter = RateLimiter(config)
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not limiter.is_allowed():
                wait_time = limiter.wait_time()
                if wait_time > 0:
                    logger.warning(f"Rate limit exceeded for {func.__name__}. Waiting {wait_time:.2f}s")
                    time.sleep(wait_time)
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def measure_time(func: Callable) -> Callable:
    """
    Декоратор для измерения времени выполнения функции.
    
    Returns:
        Функция с дополнительной информацией о времени выполнения
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(f"{func.__name__} executed in {execution_time:.3f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"{func.__name__} failed after {execution_time:.3f}s: {e}")
            raise
    
    # Добавление атрибута для доступа к времени выполнения
    wrapper._measure_time = True
    return wrapper


def cache_result(ttl_seconds: Optional[float] = None, max_size: int = 128):
    """
    Декоратор для кэширования результатов функции.
    
    Args:
        ttl_seconds: Время жизни кэша в секундах (None = без истечения)
        max_size: Максимальный размер кэша
    """
    def decorator(func: Callable) -> Callable:
        cache = {}
        cache_timestamps = {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Создание ключа кэша
            cache_key = (args, tuple(sorted(kwargs.items())))
            
            # Проверка кэша
            if cache_key in cache:
                if ttl_seconds is None:
                    return cache[cache_key]
                
                # Проверка времени жизни
                if time.time() - cache_timestamps[cache_key] < ttl_seconds:
                    return cache[cache_key]
                else:
                    # Удаление устаревшего элемента
                    del cache[cache_key]
                    del cache_timestamps[cache_key]
            
            # Выполнение функции
            result = func(*args, **kwargs)
            
            # Сохранение в кэш
            cache[cache_key] = result
            cache_timestamps[cache_key] = time.time()
            
            # Ограничение размера кэша
            if len(cache) > max_size:
                # Удаление самого старого элемента
                oldest_key = min(cache_timestamps.keys(), key=lambda k: cache_timestamps[k])
                del cache[oldest_key]
                del cache_timestamps[oldest_key]
            
            return result
        
        # Методы для управления кэшем
        wrapper.cache_clear = lambda: (cache.clear(), cache_timestamps.clear())
        wrapper.cache_info = lambda: {
            'size': len(cache),
            'max_size': max_size,
            'ttl': ttl_seconds
        }
        
        return wrapper
    return decorator


def thread_safe(func: Callable) -> Callable:
    """
    Декоратор для обеспечения потокобезопасности функции.
    
    Args:
        func: Функция для защиты
    """
    lock = threading.Lock()
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with lock:
            return func(*args, **kwargs)
    
    return wrapper


def validate_input(validator: Callable) -> Callable:
    """
    Декоратор для валидации входных параметров функции.
    
    Args:
        validator: Функция валидации, принимающая (args, kwargs)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                validator(args, kwargs)
            except Exception as e:
                logger.error(f"Input validation failed for {func.__name__}: {e}")
                raise ValueError(f"Invalid input for {func.__name__}: {e}")
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def log_calls(level: str = "DEBUG", include_args: bool = False) -> Callable:
    """
    Декоратор для логирования вызовов функции.
    
    Args:
        level: Уровень логирования
        include_args: Включать ли аргументы в лог
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            log_message = f"Calling {func.__name__}"
            if include_args:
                log_message += f" with args={args}, kwargs={kwargs}"
            
            getattr(logger, level.lower())(log_message)
            
            try:
                result = func(*args, **kwargs)
                getattr(logger, level.lower())(f"{func.__name__} completed successfully")
                return result
            except Exception as e:
                getattr(logger, level.lower())(f"{func.__name__} failed: {e}")
                raise
        
        return wrapper
    return decorator


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    expected_exception: type = Exception
):
    """
    Декоратор Circuit Breaker для предотвращения каскадных сбоев.
    
    Args:
        failure_threshold: Порог количества сбоев
        recovery_timeout: Время ожидания перед попыткой восстановления
        expected_exception: Тип исключения для отслеживания
    """
    def decorator(func: Callable) -> Callable:
        state = {
            'failures': 0,
            'last_failure_time': None,
            'state': 'closed'  # closed, open, half-open
        }
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            
            # Проверка состояния Circuit Breaker
            if state['state'] == 'open':
                if state['last_failure_time'] and (now - state['last_failure_time']) > recovery_timeout:
                    state['state'] = 'half-open'
                    logger.info(f"Circuit breaker for {func.__name__} moved to half-open state")
                else:
                    raise RuntimeError(f"Circuit breaker for {func.__name__} is open")
            
            try:
                result = func(*args, **kwargs)
                
                # Успешное выполнение - сброс состояния
                if state['state'] == 'half-open':
                    state['state'] = 'closed'
                    state['failures'] = 0
                    logger.info(f"Circuit breaker for {func.__name__} moved to closed state")
                
                return result
                
            except expected_exception as e:
                state['failures'] += 1
                state['last_failure_time'] = now
                
                if state['failures'] >= failure_threshold:
                    state['state'] = 'open'
                    logger.error(f"Circuit breaker for {func.__name__} moved to open state")
                
                raise
        
        # Методы для управления Circuit Breaker
        wrapper.circuit_reset = lambda: (state.update({
            'failures': 0,
            'last_failure_time': None,
            'state': 'closed'
        }))
        
        wrapper.circuit_state = lambda: state['state']
        
        return wrapper
    return decorator
