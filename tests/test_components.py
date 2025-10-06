"""
Тесты для отдельных компонентов пула воркеров.
"""

import time
import pytest
import threading
from unittest.mock import Mock

from src.worker_pool.core.task_channel import TaskChannel, ChannelConfig
from src.worker_pool.core.retry_manager import RetryManager, RetryConfig, BackoffStrategy
from src.worker_pool.core.graceful_shutdown import GracefulShutdown, ShutdownConfig
from src.worker_pool.core.task_executor import TaskExecutor, ExecutionConfig
from src.worker_pool.core.worker_manager import WorkerManager, WorkerManagerConfig

from src.worker_pool.models.task import Task, TaskPriority, TaskStatus
from src.worker_pool.models.worker import Worker, WorkerStatus
from src.worker_pool.exceptions import TaskChannelError, RetryExhaustedError


class TestTaskChannel:
    """Тесты для канала задач."""
    
    def test_channel_initialization(self):
        """Тест инициализации канала."""
        channel = TaskChannel()
        assert len(channel) == 0
        assert not channel.is_shutdown()
    
    def test_submit_and_get_task(self):
        """Тест отправки и получения задачи."""
        channel = TaskChannel()
        
        task = Task(
            name="test_task",
            func=lambda x: x * 2,
            args=(5,)
        )
        
        # Отправка задачи
        success = channel.submit_task(task)
        assert success
        assert len(channel) == 1
        
        # Получение задачи
        retrieved_task = channel.get_task()
        assert retrieved_task is not None
        assert retrieved_task.id == task.id
        assert len(channel) == 0
    
    def test_priority_queues(self):
        """Тест приоритетных очередей."""
        config = ChannelConfig(priority_queues=True)
        channel = TaskChannel(config)
        
        # Создание задач с разными приоритетами
        low_task = Task(name="low", func=lambda: "low", priority=TaskPriority.LOW)
        high_task = Task(name="high", func=lambda: "high", priority=TaskPriority.HIGH)
        critical_task = Task(name="critical", func=lambda: "critical", priority=TaskPriority.CRITICAL)
        
        # Отправка в порядке low -> high -> critical
        channel.submit_task(low_task)
        channel.submit_task(high_task)
        channel.submit_task(critical_task)
        
        # Получение должно быть в порядке приоритета
        first = channel.get_task()
        second = channel.get_task()
        third = channel.get_task()
        
        assert first.name == "critical"
        assert second.name == "high"
        assert third.name == "low"
    
    def test_channel_overflow(self):
        """Тест переполнения канала."""
        config = ChannelConfig(max_size=2)
        channel = TaskChannel(config)
        
        # Заполнение канала
        task1 = Task(name="task1", func=lambda: "1")
        task2 = Task(name="task2", func=lambda: "2")
        task3 = Task(name="task3", func=lambda: "3")
        
        assert channel.submit_task(task1)
        assert channel.submit_task(task2)
        assert not channel.submit_task(task3)  # Должно не поместиться
    
    def test_channel_shutdown(self):
        """Тест завершения работы канала."""
        channel = TaskChannel()
        
        # Shutdown
        channel.shutdown()
        assert channel.is_shutdown()
        
        # Попытка отправки после shutdown должна вызвать исключение
        task = Task(name="test", func=lambda: "test")
        with pytest.raises(TaskChannelError):
            channel.submit_task(task)
    
    def test_channel_metrics(self):
        """Тест метрик канала."""
        channel = TaskChannel()
        
        task = Task(name="test", func=lambda: "test")
        channel.submit_task(task)
        channel.get_task()
        
        metrics = channel.get_metrics()
        assert metrics['tasks_submitted'] >= 1
        assert metrics['tasks_retrieved'] >= 1


class TestRetryManager:
    """Тесты для менеджера ретраев."""
    
    def test_retry_manager_initialization(self):
        """Тест инициализации менеджера ретраев."""
        manager = RetryManager()
        assert manager.config.max_retries == 3
    
    def test_exponential_backoff(self):
        """Тест экспоненциального backoff."""
        config = RetryConfig(strategy=BackoffStrategy.EXPONENTIAL, base_delay=1.0)
        manager = RetryManager(config)
        
        delay1 = manager.calculate_delay(1)
        delay2 = manager.calculate_delay(2)
        delay3 = manager.calculate_delay(3)
        
        assert delay1 == 1.0
        assert delay2 == 2.0
        assert delay3 == 4.0
    
    def test_linear_backoff(self):
        """Тест линейного backoff."""
        config = RetryConfig(strategy=BackoffStrategy.LINEAR, base_delay=1.0)
        manager = RetryManager(config)
        
        delay1 = manager.calculate_delay(1)
        delay2 = manager.calculate_delay(2)
        delay3 = manager.calculate_delay(3)
        
        assert delay1 == 1.0
        assert delay2 == 2.0
        assert delay3 == 3.0
    
    def test_fixed_backoff(self):
        """Тест фиксированного backoff."""
        config = RetryConfig(strategy=BackoffStrategy.FIXED, base_delay=2.0)
        manager = RetryManager(config)
        
        delay1 = manager.calculate_delay(1)
        delay2 = manager.calculate_delay(2)
        delay3 = manager.calculate_delay(3)
        
        assert delay1 == 2.0
        assert delay2 == 2.0
        assert delay3 == 2.0
    
    def test_retry_with_success(self):
        """Тест успешного ретрая."""
        manager = RetryManager()
        attempt_count = 0
        
        def executor_func(task):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ValueError("Временная ошибка")
            return "success"
        
        task = Task(name="test", func=lambda: "test", max_retries=3)
        
        result = manager.execute_with_retry(task, executor_func)
        
        assert result.is_success()
        assert attempt_count == 2
    
    def test_retry_exhausted(self):
        """Тест исчерпания ретраев."""
        manager = RetryManager()
        
        def executor_func(task):
            raise ValueError("Постоянная ошибка")
        
        task = Task(name="test", func=lambda: "test", max_retries=2)
        
        with pytest.raises(RetryExhaustedError):
            manager.execute_with_retry(task, executor_func)
    
    def test_should_retry_logic(self):
        """Тест логики определения необходимости ретрая."""
        manager = RetryManager()
        
        task = Task(name="test", func=lambda: "test", max_retries=3)
        
        # Должен ретраить при обычной ошибке
        assert manager.should_retry(task, ValueError("test"))
        
        # Не должен ретраить при исчерпании попыток
        task.retry_count = 3
        assert not manager.should_retry(task, ValueError("test"))


class TestGracefulShutdown:
    """Тесты для graceful shutdown."""
    
    def test_shutdown_initialization(self):
        """Тест инициализации shutdown."""
        shutdown = GracefulShutdown()
        assert not shutdown.is_shutdown_initiated()
        assert not shutdown.is_shutdown_completed()
    
    def test_shutdown_phases(self):
        """Тест фаз shutdown."""
        shutdown = GracefulShutdown()
        
        # Инициация
        status = shutdown.initiate_shutdown()
        assert status.phase.value == "initiated"
        assert shutdown.is_shutdown_initiated()
        
        # Выполнение с пустыми callback'ами
        final_status = shutdown.execute_shutdown()
        assert final_status.completed
        assert final_status.phase.value == "completed"
    
    def test_shutdown_callbacks(self):
        """Тест callback'ов shutdown."""
        shutdown = GracefulShutdown()
        callback_called = False
        
        def test_callback():
            nonlocal callback_called
            callback_called = True
        
        shutdown.add_cleanup_callback(test_callback)
        
        shutdown.initiate_shutdown()
        shutdown.execute_shutdown()
        
        assert callback_called
    
    def test_shutdown_timeout(self):
        """Тест таймаута shutdown."""
        config = ShutdownConfig(timeout=1.0)
        shutdown = GracefulShutdown(config)
        
        def slow_callback():
            time.sleep(2.0)  # Дольше таймаута
        
        shutdown.add_cleanup_callback(slow_callback)
        
        shutdown.initiate_shutdown()
        status = shutdown.execute_shutdown()
        
        # Shutdown должен завершиться по таймауту
        assert status.completed or status.error_count > 0


class TestTaskExecutor:
    """Тесты для исполнителя задач."""
    
    def test_executor_initialization(self):
        """Тест инициализации исполнителя."""
        executor = TaskExecutor()
        assert executor.config.timeout is None
    
    def test_successful_task_execution(self):
        """Тест успешного выполнения задачи."""
        executor = TaskExecutor()
        
        def test_func(x):
            return x * 2
        
        task = Task(name="test", func=test_func, args=(5,))
        worker = Worker()
        worker.start()
        
        result = executor.execute_task(task, worker)
        
        assert result.is_success()
        assert result.result == 10
        assert result.execution_time > 0
    
    def test_failed_task_execution(self):
        """Тест неудачного выполнения задачи."""
        executor = TaskExecutor()
        
        def failing_func():
            raise ValueError("Тестовая ошибка")
        
        task = Task(name="test", func=failing_func)
        worker = Worker()
        worker.start()
        
        result = executor.execute_task(task, worker)
        
        assert result.is_failure()
        assert result.error is not None
        assert "Тестовая ошибка" in str(result.error)
    
    def test_task_timeout(self):
        """Тест таймаута задачи."""
        config = ExecutionConfig(timeout=1.0)
        executor = TaskExecutor(config)
        
        def long_func():
            time.sleep(2.0)
            return "done"
        
        task = Task(name="test", func=long_func)
        worker = Worker()
        worker.start()
        
        result = executor.execute_task(task, worker)
        
        assert result.is_failure()
        assert isinstance(result.error, TimeoutError)
    
    def test_executor_metrics(self):
        """Тест метрик исполнителя."""
        executor = TaskExecutor()
        
        def test_func():
            return "test"
        
        task = Task(name="test", func=test_func)
        worker = Worker()
        worker.start()
        
        executor.execute_task(task, worker)
        
        metrics = executor.get_metrics()
        assert metrics['total_executions'] >= 1
        assert metrics['successful_executions'] >= 1
        assert metrics['success_rate'] > 0


class TestWorkerManager:
    """Тесты для менеджера воркеров."""
    
    def test_worker_manager_initialization(self):
        """Тест инициализации менеджера воркеров."""
        config = WorkerManagerConfig(min_workers=2, max_workers=5)
        manager = WorkerManager(config)
        
        assert len(manager.get_workers()) == 0
    
    def test_worker_creation_and_removal(self):
        """Тест создания и удаления воркеров."""
        config = WorkerManagerConfig(min_workers=1, max_workers=3)
        manager = WorkerManager(config)
        
        # Mock callback'ов
        manager._get_task_callback = lambda timeout: None
        manager._task_executor = lambda task, worker: None
        manager._on_worker_error = lambda worker, error: None
        
        manager.start()
        
        # Проверка создания минимального количества воркеров
        assert len(manager.get_workers()) >= 1
        
        # Принудительное масштабирование
        manager.force_scale_up(2)
        assert len(manager.get_workers()) >= 3
        
        manager.stop()
    
    def test_worker_stats(self):
        """Тест статистики воркеров."""
        config = WorkerManagerConfig(min_workers=1, max_workers=2)
        manager = WorkerManager(config)
        
        # Mock callback'ов
        manager._get_task_callback = lambda timeout: None
        manager._task_executor = lambda task, worker: None
        manager._on_worker_error = lambda worker, error: None
        
        manager.start()
        
        stats = manager.get_worker_stats()
        assert stats['total_workers'] >= 1
        assert stats['idle_workers'] >= 1
        assert stats['busy_workers'] == 0
        
        manager.stop()


if __name__ == "__main__":
    pytest.main([__file__])
