"""
Канал задач для конкурентного пула воркеров.
"""

import asyncio
import queue
import threading
import time
from typing import Optional, List, Callable, Any
from collections import defaultdict, deque
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

from ..models.task import Task, TaskPriority
from ..utils.logger import get_logger
from ..exceptions import TaskChannelError


logger = get_logger(__name__)


@dataclass
class ChannelConfig:
    """Конфигурация канала задач."""
    max_size: int = 1000
    priority_queues: bool = True
    timeout: Optional[float] = None
    enable_metrics: bool = True


class TaskChannel:
    """Канал для передачи задач между компонентами пула воркеров."""
    
    def __init__(self, config: Optional[ChannelConfig] = None):
        self.config = config or ChannelConfig()
        self._shutdown_event = threading.Event()
        self._metrics_lock = threading.Lock()
        
        # Основные очереди задач
        if self.config.priority_queues:
            self._priority_queues = {
                TaskPriority.CRITICAL: queue.PriorityQueue(maxsize=self.config.max_size),
                TaskPriority.HIGH: queue.PriorityQueue(maxsize=self.config.max_size),
                TaskPriority.NORMAL: queue.PriorityQueue(maxsize=self.config.max_size),
                TaskPriority.LOW: queue.PriorityQueue(maxsize=self.config.max_size),
            }
        else:
            self._main_queue = queue.Queue(maxsize=self.config.max_size)
        
        # Метрики
        self._metrics = {
            'tasks_submitted': 0,
            'tasks_retrieved': 0,
            'tasks_dropped': 0,
            'queue_overflows': 0,
            'average_wait_time': 0.0,
            'max_wait_time': 0.0,
            'current_size': 0,
            'max_size_reached': 0
        }
        
        # Статистика по приоритетам
        self._priority_stats = defaultdict(int)
        
        logger.info(f"TaskChannel initialized with config: {self.config}")
    
    def submit_task(self, task: Task, timeout: Optional[float] = None) -> bool:
        """
        Отправка задачи в канал.
        
        Args:
            task: Задача для выполнения
            timeout: Таймаут для отправки
            
        Returns:
            True если задача успешно добавлена, False иначе
        """
        if self._shutdown_event.is_set():
            raise TaskChannelError("Channel is shutting down")
        
        start_time = time.time()
        
        try:
            if self.config.priority_queues:
                success = self._submit_to_priority_queue(task, timeout)
            else:
                success = self._submit_to_main_queue(task, timeout)
            
            if success:
                with self._metrics_lock:
                    self._metrics['tasks_submitted'] += 1
                    self._priority_stats[task.priority] += 1
                    self._metrics['current_size'] += 1
                    self._metrics['max_size_reached'] = max(
                        self._metrics['max_size_reached'], 
                        self._metrics['current_size']
                    )
                
                wait_time = time.time() - start_time
                self._update_wait_metrics(wait_time)
                
                logger.debug(f"Task {task.id} submitted to channel with priority {task.priority}")
                return True
            else:
                with self._metrics_lock:
                    self._metrics['tasks_dropped'] += 1
                    self._metrics['queue_overflows'] += 1
                
                logger.warning(f"Task {task.id} dropped due to queue overflow")
                return False
                
        except Exception as e:
            logger.error(f"Error submitting task {task.id}: {e}")
            with self._metrics_lock:
                self._metrics['tasks_dropped'] += 1
            return False
    
    def get_task(self, timeout: Optional[float] = None) -> Optional[Task]:
        """
        Получение задачи из канала.
        
        Args:
            timeout: Таймаут для получения задачи
            
        Returns:
            Задача или None если таймаут
        """
        if self._shutdown_event.is_set():
            return None
        
        start_time = time.time()
        
        try:
            if self.config.priority_queues:
                task = self._get_from_priority_queues(timeout)
            else:
                task = self._get_from_main_queue(timeout)
            
            if task:
                with self._metrics_lock:
                    self._metrics['tasks_retrieved'] += 1
                    self._metrics['current_size'] -= 1
                
                wait_time = time.time() - start_time
                self._update_wait_metrics(wait_time)
                
                logger.debug(f"Task {task.id} retrieved from channel")
                return task
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error retrieving task: {e}")
            return None
    
    def _submit_to_priority_queue(self, task: Task, timeout: Optional[float] = None) -> bool:
        """Отправка в приоритетную очередь."""
        priority_queue = self._priority_queues[task.priority]
        
        try:
            # Используем время создания как tie-breaker для FIFO в рамках приоритета
            priority_item = (task.created_at.timestamp(), task)
            priority_queue.put(priority_item, timeout=timeout)
            return True
        except queue.Full:
            return False
    
    def _submit_to_main_queue(self, task: Task, timeout: Optional[float] = None) -> bool:
        """Отправка в основную очередь."""
        try:
            self._main_queue.put(task, timeout=timeout)
            return True
        except queue.Full:
            return False
    
    def _get_from_priority_queues(self, timeout: Optional[float] = None) -> Optional[Task]:
        """Получение из приоритетных очередей."""
        # Проверяем очереди в порядке приоритета
        for priority in [TaskPriority.CRITICAL, TaskPriority.HIGH, TaskPriority.NORMAL, TaskPriority.LOW]:
            queue_obj = self._priority_queues[priority]
            try:
                priority_item = queue_obj.get(timeout=0.1)  # Короткий таймаут для проверки
                queue_obj.task_done()
                _, task = priority_item
                return task
            except queue.Empty:
                continue
        
        # Если ничего не найдено, ждем в очереди HIGHEST приоритета
        try:
            priority_item = self._priority_queues[TaskPriority.CRITICAL].get(timeout=timeout)
            self._priority_queues[TaskPriority.CRITICAL].task_done()
            _, task = priority_item
            return task
        except queue.Empty:
            return None
    
    def _get_from_main_queue(self, timeout: Optional[float] = None) -> Optional[Task]:
        """Получение из основной очереди."""
        try:
            return self._main_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def _update_wait_metrics(self, wait_time: float):
        """Обновление метрик времени ожидания."""
        with self._metrics_lock:
            self._metrics['max_wait_time'] = max(self._metrics['max_wait_time'], wait_time)
            
            # Простое скользящее среднее
            if self._metrics['average_wait_time'] == 0:
                self._metrics['average_wait_time'] = wait_time
            else:
                self._metrics['average_wait_time'] = (self._metrics['average_wait_time'] + wait_time) / 2
    
    def get_metrics(self) -> dict:
        """Получение метрик канала."""
        with self._metrics_lock:
            metrics = self._metrics.copy()
            metrics['priority_stats'] = dict(self._priority_stats)
            return metrics
    
    def get_queue_sizes(self) -> dict:
        """Получение размеров очередей."""
        if self.config.priority_queues:
            sizes = {}
            for priority, queue_obj in self._priority_queues.items():
                sizes[priority.value] = queue_obj.qsize()
            return sizes
        else:
            return {'main_queue': self._main_queue.qsize()}
    
    def clear(self):
        """Очистка всех очередей."""
        if self.config.priority_queues:
            for queue_obj in self._priority_queues.values():
                while not queue_obj.empty():
                    try:
                        queue_obj.get_nowait()
                        queue_obj.task_done()
                    except queue.Empty:
                        break
        else:
            while not self._main_queue.empty():
                try:
                    self._main_queue.get_nowait()
                except queue.Empty:
                    break
        
        with self._metrics_lock:
            self._metrics['current_size'] = 0
        
        logger.info("Task channel cleared")
    
    def shutdown(self, timeout: Optional[float] = None):
        """Корректное завершение работы канала."""
        logger.info("Shutting down task channel...")
        self._shutdown_event.set()
        
        # Ждем завершения всех операций
        if timeout:
            time.sleep(timeout)
        
        logger.info("Task channel shutdown complete")
    
    def is_shutdown(self) -> bool:
        """Проверка завершения работы."""
        return self._shutdown_event.is_set()
    
    def __len__(self) -> int:
        """Размер канала."""
        return self._metrics['current_size']
    
    def __repr__(self) -> str:
        return f"TaskChannel(size={len(self)}, config={self.config})"
