"""
Исключения для пула воркеров.
"""


class WorkerPoolError(Exception):
    """Базовое исключение для пула воркеров."""
    pass


class TaskExecutionError(WorkerPoolError):
    """Ошибка выполнения задачи."""
    pass


class RetryExhaustedError(WorkerPoolError):
    """Исчерпаны все попытки ретрая."""
    pass


class ShutdownError(WorkerPoolError):
    """Ошибка при завершении работы."""
    pass


class TaskChannelError(WorkerPoolError):
    """Ошибка канала задач."""
    pass


class WorkerError(WorkerPoolError):
    """Ошибка воркера."""
    pass


class ConfigurationError(WorkerPoolError):
    """Ошибка конфигурации."""
    pass


class TimeoutError(WorkerPoolError):
    """Ошибка таймаута."""
    pass


class ResourceError(WorkerPoolError):
    """Ошибка ресурсов (память, файлы и т.д.)."""
    pass


class ValidationError(WorkerPoolError):
    """Ошибка валидации."""
    pass
