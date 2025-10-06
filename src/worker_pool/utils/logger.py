"""
Система логирования для пула воркеров.
"""

import logging
import sys
import threading
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path


class WorkerPoolFormatter(logging.Formatter):
    """Кастомный форматтер для логов пула воркеров."""
    
    def __init__(self):
        super().__init__(
            fmt='%(asctime)s | %(levelname)-8s | %(name)-20s | %(threadName)-15s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    def format(self, record):
        # Добавляем информацию о потоке
        if not hasattr(record, 'threadName'):
            record.threadName = threading.current_thread().name
        
        return super().format(record)


class MetricsHandler(logging.Handler):
    """Обработчик логов для сбора метрик."""
    
    def __init__(self):
        super().__init__()
        self._metrics = {
            'total_logs': 0,
            'error_count': 0,
            'warning_count': 0,
            'info_count': 0,
            'debug_count': 0
        }
        self._lock = threading.Lock()
    
    def emit(self, record):
        with self._lock:
            self._metrics['total_logs'] += 1
            
            if record.levelno >= logging.ERROR:
                self._metrics['error_count'] += 1
            elif record.levelno >= logging.WARNING:
                self._metrics['warning_count'] += 1
            elif record.levelno >= logging.INFO:
                self._metrics['info_count'] += 1
            elif record.levelno >= logging.DEBUG:
                self._metrics['debug_count'] += 1
    
    def get_metrics(self) -> Dict[str, int]:
        """Получение метрик логов."""
        with self._lock:
            return self._metrics.copy()
    
    def reset_metrics(self):
        """Сброс метрик."""
        with self._lock:
            self._metrics = {
                'total_logs': 0,
                'error_count': 0,
                'warning_count': 0,
                'info_count': 0,
                'debug_count': 0
            }


# Глобальный обработчик метрик
_metrics_handler = MetricsHandler()


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    enable_console: bool = True,
    enable_metrics: bool = True,
    log_format: Optional[str] = None
):
    """
    Настройка системы логирования.
    
    Args:
        level: Уровень логирования
        log_file: Путь к файлу логов
        enable_console: Включить вывод в консоль
        enable_metrics: Включить сбор метрик
        log_format: Кастомный формат логов
    """
    # Получение уровня логирования
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Создание корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Очистка существующих обработчиков
    root_logger.handlers.clear()
    
    # Создание форматтера
    if log_format:
        formatter = logging.Formatter(log_format)
    else:
        formatter = WorkerPoolFormatter()
    
    # Консольный обработчик
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # Файловый обработчик
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Обработчик метрик
    if enable_metrics:
        _metrics_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(_metrics_handler)
    
    # Настройка логгеров для библиотек
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Получение логгера для модуля.
    
    Args:
        name: Имя модуля
        
    Returns:
        Объект логгера
    """
    return logging.getLogger(name)


def get_log_metrics() -> Dict[str, int]:
    """Получение метрик логов."""
    return _metrics_handler.get_metrics()


def reset_log_metrics():
    """Сброс метрик логов."""
    _metrics_handler.reset_metrics()


class LoggerMixin:
    """Миксин для добавления логирования в классы."""
    
    @property
    def logger(self) -> logging.Logger:
        """Получение логгера для класса."""
        return get_logger(self.__class__.__name__)


def log_execution_time(func):
    """Декоратор для логирования времени выполнения функции."""
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        start_time = datetime.now()
        
        try:
            result = func(*args, **kwargs)
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.debug(f"{func.__name__} executed in {execution_time:.3f}s")
            return result
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"{func.__name__} failed after {execution_time:.3f}s: {e}")
            raise
    
    return wrapper


def log_task_execution(task_id: str, worker_id: str):
    """Декоратор для логирования выполнения задач."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = get_logger("task_execution")
            logger.info(f"Starting task {task_id} on worker {worker_id}")
            
            start_time = datetime.now()
            try:
                result = func(*args, **kwargs)
                execution_time = (datetime.now() - start_time).total_seconds()
                logger.info(f"Task {task_id} completed on worker {worker_id} in {execution_time:.3f}s")
                return result
            except Exception as e:
                execution_time = (datetime.now() - start_time).total_seconds()
                logger.error(f"Task {task_id} failed on worker {worker_id} after {execution_time:.3f}s: {e}")
                raise
        
        return wrapper
    return decorator


class StructuredLogger:
    """Структурированный логгер для метрик и событий."""
    
    def __init__(self, name: str):
        self.logger = get_logger(name)
        self._context = {}
    
    def set_context(self, **kwargs):
        """Установка контекста для логов."""
        self._context.update(kwargs)
    
    def clear_context(self):
        """Очистка контекста."""
        self._context.clear()
    
    def log_event(self, event: str, level: str = "INFO", **data):
        """Логирование события с данными."""
        log_data = {
            'event': event,
            'timestamp': datetime.now().isoformat(),
            'context': self._context.copy(),
            'data': data
        }
        
        message = f"EVENT: {event}"
        if data:
            message += f" | DATA: {data}"
        
        getattr(self.logger, level.lower())(message, extra={'structured_data': log_data})
    
    def log_metric(self, metric_name: str, value: float, unit: str = "", **tags):
        """Логирование метрики."""
        metric_data = {
            'metric': metric_name,
            'value': value,
            'unit': unit,
            'timestamp': datetime.now().isoformat(),
            'context': self._context.copy(),
            'tags': tags
        }
        
        message = f"METRIC: {metric_name}={value}"
        if unit:
            message += f" {unit}"
        if tags:
            message += f" | TAGS: {tags}"
        
        self.logger.info(message, extra={'structured_data': metric_data})
    
    def log_error(self, error: Exception, **context):
        """Логирование ошибки с контекстом."""
        error_data = {
            'error': str(error),
            'error_type': type(error).__name__,
            'timestamp': datetime.now().isoformat(),
            'context': {**self._context, **context}
        }
        
        self.logger.error(f"ERROR: {error}", extra={'structured_data': error_data}, exc_info=True)
