"""
Тесты для основного класса WorkerPool.
"""

import time
import pytest
import threading
from unittest.mock import Mock, patch

from src.worker_pool import WorkerPool, TaskPriority
from src.worker_pool.models.task import Task, TaskStatus
from src.worker_pool.models.worker import Worker, WorkerStatus
from src.worker_pool.exceptions import WorkerPoolError, TaskExecutionError


class TestWorkerPool:
    """Тесты для класса WorkerPool."""
    
    def test_worker_pool_initialization(self):
        """Тест инициализации пула воркеров."""
        pool = WorkerPool()
        
        assert pool.get_status().value == "stopped"
        assert pool.get_worker_count() == 0
        assert pool.get_queue_size() == 0
        assert not pool.is_running()
    
    def test_worker_pool_start_stop(self):
        """Тест запуска и остановки пула."""
        pool = WorkerPool()
        
        # Запуск
        pool.start()
        assert pool.is_running()
        assert pool.get_worker_count() >= 2  # Минимум воркеров
        
        # Остановка
        pool.stop()
        assert not pool.is_running()
    
    def test_context_manager(self):
        """Тест использования как контекстный менеджер."""
        with WorkerPool() as pool:
            assert pool.is_running()
            assert pool.get_worker_count() > 0
        
        # После выхода из контекста пул должен быть остановлен
        pool = WorkerPool()
        with pool:
            pass
        assert not pool.is_running()
    
    def test_submit_simple_task(self):
        """Тест отправки простой задачи."""
        def simple_task(x):
            return x * 2
        
        with WorkerPool() as pool:
            task_id = pool.submit_task(simple_task, 5, name="test_task")
            assert isinstance(task_id, str)
            assert len(task_id) > 0
            
            # Ожидание завершения
            pool.wait_for_completion(timeout=5.0)
            
            # Проверка метрик
            metrics = pool.get_metrics()
            assert metrics['total_tasks_submitted'] >= 1
    
    def test_task_priorities(self):
        """Тест приоритетов задач."""
        results = []
        
        def priority_task(name):
            results.append(name)
            time.sleep(0.1)
            return name
        
        with WorkerPool() as pool:
            # Отправка задач с разными приоритетами
            pool.submit_task(priority_task, "low", priority=TaskPriority.LOW)
            pool.submit_task(priority_task, "high", priority=TaskPriority.HIGH)
            pool.submit_task(priority_task, "normal", priority=TaskPriority.NORMAL)
            pool.submit_task(priority_task, "critical", priority=TaskPriority.CRITICAL)
            
            pool.wait_for_completion(timeout=10.0)
        
        # Критическая задача должна выполниться первой
        assert results[0] == "critical"
        assert "high" in results[:2]  # Высокий приоритет в первых двух
    
    def test_task_retries(self):
        """Тест автоматических ретраев."""
        attempt_count = 0
        
        def failing_task():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("Временная ошибка")
            return "success"
        
        with WorkerPool() as pool:
            task_id = pool.submit_task(
                failing_task,
                name="retry_task",
                max_retries=5
            )
            
            pool.wait_for_completion(timeout=10.0)
            
            # Задача должна выполниться успешно после ретраев
            assert attempt_count == 3
            
            # Проверка метрик ретраев
            metrics = pool.get_metrics()
            retry_metrics = metrics['retry_metrics']
            assert retry_metrics['total_retries'] >= 2
    
    def test_task_timeout(self):
        """Тест таймаута задач."""
        def long_task():
            time.sleep(5)  # Долгая задача
            return "done"
        
        with WorkerPool() as pool:
            task_id = pool.submit_task(
                long_task,
                name="timeout_task",
                timeout=1.0  # Таймаут 1 секунда
            )
            
            pool.wait_for_completion(timeout=10.0)
            
            # Проверка метрик таймаутов
            metrics = pool.get_metrics()
            execution_metrics = metrics['execution_metrics']
            assert execution_metrics['timeout_executions'] >= 1
    
    def test_worker_scaling(self):
        """Тест масштабирования воркеров."""
        with WorkerPool() as pool:
            initial_workers = pool.get_worker_count()
            
            # Принудительное масштабирование
            pool.scale_workers(3)
            assert pool.get_worker_count() >= initial_workers + 3
            
            pool.scale_workers(-1)
            assert pool.get_worker_count() >= initial_workers + 2
    
    def test_metrics_collection(self):
        """Тест сбора метрик."""
        def metric_task(x):
            time.sleep(0.1)
            return x * 2
        
        with WorkerPool() as pool:
            # Отправка нескольких задач
            for i in range(5):
                pool.submit_task(metric_task, i)
            
            pool.wait_for_completion(timeout=10.0)
            
            metrics = pool.get_metrics()
            
            # Проверка основных метрик
            assert metrics['total_tasks_submitted'] >= 5
            assert metrics['total_tasks_completed'] >= 5
            assert metrics['average_execution_time'] > 0
            
            # Проверка метрик воркеров
            worker_metrics = metrics['worker_metrics']
            assert worker_metrics['total_workers'] > 0
            assert worker_metrics['total_tasks_completed'] >= 5
    
    def test_graceful_shutdown(self):
        """Тест graceful shutdown."""
        def long_task():
            time.sleep(2)
            return "completed"
        
        pool = WorkerPool()
        pool.start()
        
        try:
            # Отправка долгой задачи
            pool.submit_task(long_task, name="long_task")
            
            # Немедленная остановка
            start_time = time.time()
            pool.stop(timeout=5.0)
            shutdown_time = time.time() - start_time
            
            # Shutdown должен завершиться быстро
            assert shutdown_time < 5.0
            assert not pool.is_running()
            
        finally:
            if pool.is_running():
                pool.stop()
    
    def test_concurrent_task_submission(self):
        """Тест конкурентной отправки задач."""
        def concurrent_task(task_id):
            time.sleep(0.1)
            return task_id
        
        with WorkerPool() as pool:
            # Отправка задач из разных потоков
            task_ids = []
            threads = []
            
            def submit_tasks():
                for i in range(10):
                    task_id = pool.submit_task(concurrent_task, i)
                    task_ids.append(task_id)
            
            # Создание нескольких потоков для отправки
            for _ in range(3):
                thread = threading.Thread(target=submit_tasks)
                threads.append(thread)
                thread.start()
            
            # Ожидание завершения отправки
            for thread in threads:
                thread.join()
            
            # Ожидание завершения выполнения
            pool.wait_for_completion(timeout=10.0)
            
            # Проверка результатов
            assert len(task_ids) == 30
            metrics = pool.get_metrics()
            assert metrics['total_tasks_submitted'] >= 30
            assert metrics['total_tasks_completed'] >= 30
    
    def test_error_handling(self):
        """Тест обработки ошибок."""
        def error_task():
            raise RuntimeError("Тестовая ошибка")
        
        with WorkerPool() as pool:
            task_id = pool.submit_task(error_task, name="error_task")
            
            pool.wait_for_completion(timeout=5.0)
            
            # Проверка метрик ошибок
            metrics = pool.get_metrics()
            assert metrics['total_tasks_failed'] >= 1
            assert metrics['error_rate'] > 0
    
    def test_submit_task_without_running_pool(self):
        """Тест отправки задачи в остановленный пул."""
        def simple_task():
            return "test"
        
        pool = WorkerPool()
        
        with pytest.raises(WorkerPoolError):
            pool.submit_task(simple_task)
    
    def test_worker_pool_with_custom_config(self):
        """Тест пула с пользовательской конфигурацией."""
        from src.worker_pool.core import WorkerPoolConfig
        
        config = WorkerPoolConfig(
            min_workers=3,
            max_workers=6,
            enable_metrics=True
        )
        
        with WorkerPool(config) as pool:
            assert pool.get_worker_count() >= 3
            
            # Отправка задачи
            task_id = pool.submit_task(lambda x: x * 2, 10)
            pool.wait_for_completion()
            
            # Проверка метрик
            metrics = pool.get_metrics()
            assert metrics['total_tasks_completed'] >= 1


if __name__ == "__main__":
    pytest.main([__file__])
