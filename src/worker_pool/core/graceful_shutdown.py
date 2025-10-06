"""
Механизм graceful shutdown для пула воркеров.
"""

import signal
import threading
import time
from typing import Callable, List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from ..utils.logger import get_logger
from ..exceptions import ShutdownError


logger = get_logger(__name__)


class ShutdownPhase(Enum):
    """Фазы завершения работы."""
    INITIATED = "initiated"
    STOPPING_NEW_TASKS = "stopping_new_tasks"
    WAITING_FOR_COMPLETION = "waiting_for_completion"
    TERMINATING_WORKERS = "terminating_workers"
    COMPLETED = "completed"


@dataclass
class ShutdownConfig:
    """Конфигурация graceful shutdown."""
    timeout: float = 30.0  # Общий таймаут в секундах
    worker_termination_timeout: float = 5.0  # Таймаут для завершения воркеров
    task_completion_timeout: float = 20.0  # Таймаут для завершения задач
    force_terminate: bool = True  # Принудительное завершение по таймауту
    wait_for_pending_tasks: bool = True  # Ждать завершения задач в очереди
    signal_handling: bool = True  # Обработка системных сигналов
    cleanup_callbacks: List[Callable] = field(default_factory=list)  # Callback'и для очистки


@dataclass
class ShutdownStatus:
    """Статус завершения работы."""
    phase: ShutdownPhase
    start_time: datetime
    timeout: float
    tasks_completed: int = 0
    workers_terminated: int = 0
    cleanup_callbacks_executed: int = 0
    error_count: int = 0
    completed: bool = False
    error: Optional[Exception] = None


class GracefulShutdown:
    """Менеджер graceful shutdown для пула воркеров."""
    
    def __init__(self, config: Optional[ShutdownConfig] = None):
        self.config = config or ShutdownConfig()
        self._shutdown_event = threading.Event()
        self._status: Optional[ShutdownStatus] = None
        self._lock = threading.Lock()
        self._callbacks: List[Callable] = []
        
        # Регистрация обработчиков сигналов
        if self.config.signal_handling:
            self._register_signal_handlers()
        
        logger.info(f"GracefulShutdown initialized with config: {self.config}")
    
    def _register_signal_handlers(self):
        """Регистрация обработчиков системных сигналов."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown")
            self.initiate_shutdown()
        
        try:
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
        except (OSError, ValueError) as e:
            logger.warning(f"Could not register signal handlers: {e}")
    
    def initiate_shutdown(self) -> ShutdownStatus:
        """
        Инициация graceful shutdown.
        
        Returns:
            Статус завершения работы
        """
        with self._lock:
            if self._status and self._status.phase != ShutdownPhase.COMPLETED:
                logger.warning("Shutdown already in progress")
                return self._status
            
            self._shutdown_event.set()
            self._status = ShutdownStatus(
                phase=ShutdownPhase.INITIATED,
                start_time=datetime.now(),
                timeout=self.config.timeout
            )
            
            logger.info("Graceful shutdown initiated")
            return self._status
    
    def execute_shutdown(
        self,
        stop_new_tasks_callback: Optional[Callable] = None,
        get_pending_tasks_callback: Optional[Callable] = None,
        terminate_workers_callback: Optional[Callable] = None,
        cleanup_callbacks: Optional[List[Callable]] = None
    ) -> ShutdownStatus:
        """
        Выполнение graceful shutdown.
        
        Args:
            stop_new_tasks_callback: Callback для остановки приема новых задач
            get_pending_tasks_callback: Callback для получения количества ожидающих задач
            terminate_workers_callback: Callback для завершения воркеров
            cleanup_callbacks: Дополнительные callback'и для очистки
            
        Returns:
            Финальный статус завершения работы
        """
        if not self._status:
            raise ShutdownError("Shutdown not initiated")
        
        try:
            # Фаза 1: Остановка приема новых задач
            self._status.phase = ShutdownPhase.STOPPING_NEW_TASKS
            logger.info("Phase 1: Stopping new task acceptance")
            
            if stop_new_tasks_callback:
                try:
                    stop_new_tasks_callback()
                except Exception as e:
                    logger.error(f"Error in stop_new_tasks_callback: {e}")
                    self._status.error_count += 1
            
            # Фаза 2: Ожидание завершения текущих задач
            if self.config.wait_for_pending_tasks:
                self._status.phase = ShutdownPhase.WAITING_FOR_COMPLETION
                logger.info("Phase 2: Waiting for task completion")
                
                self._wait_for_task_completion(get_pending_tasks_callback)
            
            # Фаза 3: Завершение воркеров
            self._status.phase = ShutdownPhase.TERMINATING_WORKERS
            logger.info("Phase 3: Terminating workers")
            
            if terminate_workers_callback:
                try:
                    terminate_workers_callback()
                except Exception as e:
                    logger.error(f"Error in terminate_workers_callback: {e}")
                    self._status.error_count += 1
            
            # Фаза 4: Выполнение cleanup callback'ов
            all_cleanup_callbacks = (cleanup_callbacks or []) + self.config.cleanup_callbacks + self._callbacks
            self._execute_cleanup_callbacks(all_cleanup_callbacks)
            
            # Завершение
            self._status.phase = ShutdownPhase.COMPLETED
            self._status.completed = True
            
            elapsed_time = (datetime.now() - self._status.start_time).total_seconds()
            logger.info(f"Graceful shutdown completed in {elapsed_time:.2f} seconds")
            
        except Exception as e:
            self._status.error = e
            self._status.error_count += 1
            logger.error(f"Error during graceful shutdown: {e}")
            
            if self.config.force_terminate:
                logger.warning("Force terminating due to error")
                self._force_terminate()
        
        return self._status
    
    def _wait_for_task_completion(self, get_pending_tasks_callback: Optional[Callable] = None):
        """Ожидание завершения задач."""
        start_time = time.time()
        timeout = self.config.task_completion_timeout
        
        while time.time() - start_time < timeout:
            try:
                if get_pending_tasks_callback:
                    pending_count = get_pending_tasks_callback()
                    if pending_count == 0:
                        logger.info("All pending tasks completed")
                        return
                    
                    logger.debug(f"Waiting for {pending_count} pending tasks to complete")
                
                # Проверка каждые 100ms
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error checking pending tasks: {e}")
                self._status.error_count += 1
                break
        
        # Таймаут
        logger.warning(f"Task completion timeout ({timeout}s) exceeded")
    
    def _execute_cleanup_callbacks(self, callbacks: List[Callable]):
        """Выполнение cleanup callback'ов."""
        for callback in callbacks:
            try:
                logger.debug(f"Executing cleanup callback: {callback}")
                callback()
                self._status.cleanup_callbacks_executed += 1
            except Exception as e:
                logger.error(f"Error in cleanup callback {callback}: {e}")
                self._status.error_count += 1
    
    def _force_terminate(self):
        """Принудительное завершение."""
        logger.warning("Force terminating all components")
        # Здесь можно добавить принудительное завершение воркеров
        # через threading.Thread или multiprocessing.Process
    
    def add_cleanup_callback(self, callback: Callable):
        """Добавление cleanup callback'а."""
        self._callbacks.append(callback)
        logger.debug(f"Added cleanup callback: {callback}")
    
    def remove_cleanup_callback(self, callback: Callable):
        """Удаление cleanup callback'а."""
        try:
            self._callbacks.remove(callback)
            logger.debug(f"Removed cleanup callback: {callback}")
        except ValueError:
            pass
    
    def is_shutdown_initiated(self) -> bool:
        """Проверка инициации shutdown."""
        return self._shutdown_event.is_set()
    
    def is_shutdown_completed(self) -> bool:
        """Проверка завершения shutdown."""
        return self._status and self._status.completed
    
    def get_status(self) -> Optional[ShutdownStatus]:
        """Получение текущего статуса."""
        return self._status
    
    def get_elapsed_time(self) -> float:
        """Получение времени с начала shutdown."""
        if self._status:
            return (datetime.now() - self._status.start_time).total_seconds()
        return 0.0
    
    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Ожидание завершения shutdown.
        
        Args:
            timeout: Таймаут ожидания
            
        Returns:
            True если завершен, False если таймаут
        """
        if not self._status:
            return True
        
        if timeout is None:
            timeout = self.config.timeout
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._status.completed:
                return True
            time.sleep(0.1)
        
        return False
    
    def reset(self):
        """Сброс состояния для повторного использования."""
        with self._lock:
            self._shutdown_event.clear()
            self._status = None
            logger.info("GracefulShutdown reset")
    
    def __repr__(self) -> str:
        if self._status:
            return f"GracefulShutdown(phase={self._status.phase.value}, elapsed={self.get_elapsed_time():.1f}s)"
        return "GracefulShutdown(not_initiated)"
