"""
Продвинутые примеры использования пула воркеров.
"""

import time
import asyncio
import requests
from typing import List, Dict, Any
from src.worker_pool import WorkerPool, TaskPriority
from src.worker_pool.core import WorkerPoolConfig
from src.worker_pool.utils import setup_logging, MetricsCollector


def http_request_task(url: str, timeout: int = 5) -> Dict[str, Any]:
    """Задача для выполнения HTTP запросов."""
    try:
        response = requests.get(url, timeout=timeout)
        return {
            'url': url,
            'status_code': response.status_code,
            'content_length': len(response.content),
            'success': True
        }
    except Exception as e:
        return {
            'url': url,
            'error': str(e),
            'success': False
        }


def data_processing_task(data: List[int]) -> Dict[str, Any]:
    """Задача для обработки данных."""
    if not data:
        return {'error': 'Empty data', 'success': False}
    
    # Имитация обработки данных
    time.sleep(0.1)
    
    result = {
        'sum': sum(data),
        'average': sum(data) / len(data),
        'max': max(data),
        'min': min(data),
        'count': len(data),
        'success': True
    }
    
    return result


def batch_processing_task(batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Задача для пакетной обработки."""
    results = []
    
    for item in batch:
        # Имитация обработки элемента
        time.sleep(0.05)
        
        processed_item = {
            'id': item.get('id'),
            'processed': True,
            'timestamp': time.time(),
            'data': item.get('data', {})
        }
        
        results.append(processed_item)
    
    return results


def monitoring_task() -> Dict[str, Any]:
    """Задача для мониторинга системы."""
    import psutil
    
    return {
        'cpu_percent': psutil.cpu_percent(),
        'memory_percent': psutil.virtual_memory().percent,
        'disk_percent': psutil.disk_usage('/').percent,
        'timestamp': time.time()
    }


def example_custom_config():
    """Пример настройки пользовательской конфигурации."""
    print("=== Пример с пользовательской конфигурацией ===\n")
    
    # Создание конфигурации
    config = WorkerPoolConfig(
        min_workers=3,
        max_workers=8,
        enable_metrics=True,
        enable_monitoring=True
    )
    
    # Настройка компонентов
    config.channel_config.max_size = 500
    config.channel_config.priority_queues = True
    
    config.retry_config.max_retries = 5
    config.retry_config.base_delay = 0.5
    config.retry_config.exponential_base = 2.0
    
    config.shutdown_config.timeout = 60.0
    config.shutdown_config.wait_for_pending_tasks = True
    
    config.execution_config.timeout = 30.0
    config.execution_config.enable_metrics = True
    
    # Создание пула с конфигурацией
    with WorkerPool(config) as pool:
        print(f"Пул создан с конфигурацией: {config.min_workers}-{config.max_workers} воркеров")
        
        # Отправка задач
        for i in range(10):
            pool.submit_task(
                data_processing_task,
                list(range(i * 10, (i + 1) * 10)),
                name=f"data_task_{i}",
                priority=TaskPriority.NORMAL
            )
        
        pool.wait_for_completion()
        print("Все задачи завершены")


def example_http_requests():
    """Пример выполнения HTTP запросов."""
    print("\n=== Пример HTTP запросов ===\n")
    
    urls = [
        "https://httpbin.org/get",
        "https://httpbin.org/delay/1",
        "https://httpbin.org/status/200",
        "https://httpbin.org/status/404",
        "https://httpbin.org/json"
    ]
    
    with WorkerPool() as pool:
        task_ids = []
        
        for i, url in enumerate(urls):
            task_id = pool.submit_task(
                http_request_task,
                url,
                timeout=10,
                name=f"http_request_{i}",
                priority=TaskPriority.NORMAL
            )
            task_ids.append(task_id)
        
        print(f"Отправлено {len(urls)} HTTP запросов")
        
        # Ожидание завершения
        pool.wait_for_completion(timeout=30.0)
        
        # Вывод результатов
        metrics = pool.get_metrics()
        print(f"Завершено запросов: {metrics['total_tasks_completed']}")
        print(f"Ошибок: {metrics['total_tasks_failed']}")


def example_batch_processing():
    """Пример пакетной обработки данных."""
    print("\n=== Пример пакетной обработки ===\n")
    
    # Создание тестовых данных
    batches = []
    for i in range(5):
        batch = []
        for j in range(20):
            batch.append({
                'id': f"item_{i}_{j}",
                'data': {'value': i * 20 + j, 'category': f'cat_{i % 3}'}
            })
        batches.append(batch)
    
    with WorkerPool() as pool:
        print(f"Обработка {len(batches)} пакетов данных")
        
        for i, batch in enumerate(batches):
            pool.submit_task(
                batch_processing_task,
                batch,
                name=f"batch_{i}",
                priority=TaskPriority.NORMAL
            )
        
        pool.wait_for_completion()
        print("Пакетная обработка завершена")


def example_monitoring():
    """Пример мониторинга с метриками."""
    print("\n=== Пример мониторинга ===\n")
    
    # Настройка логирования
    setup_logging(level="INFO", enable_metrics=True)
    
    with WorkerPool() as pool:
        # Создание сборщика метрик
        metrics_collector = MetricsCollector(collection_interval=2.0)
        metrics_collector.start()
        
        # Отправка задач мониторинга
        for i in range(10):
            pool.submit_task(
                monitoring_task,
                name=f"monitoring_{i}",
                priority=TaskPriority.LOW
            )
        
        # Ожидание выполнения
        time.sleep(5)
        
        # Получение метрик
        pool_metrics = pool.get_metrics()
        system_metrics = metrics_collector.get_current_metrics()
        
        print("Метрики пула:")
        print(f"  Задач выполнено: {pool_metrics['total_tasks_completed']}")
        print(f"  Среднее время выполнения: {pool_metrics['average_execution_time']:.3f}s")
        print(f"  Размер очереди: {pool_metrics['current_queue_size']}")
        
        if system_metrics:
            sys_metrics = system_metrics.get('system', {})
            print("\nСистемные метрики:")
            print(f"  CPU: {sys_metrics.get('cpu_percent', 0):.1f}%")
            print(f"  Память: {sys_metrics.get('memory_percent', 0):.1f}%")
            print(f"  Диск: {sys_metrics.get('disk_usage_percent', 0):.1f}%")
        
        metrics_collector.stop()


def example_priority_queues():
    """Пример использования приоритетных очередей."""
    print("\n=== Пример приоритетных очередей ===\n")
    
    def priority_task(name: str, priority: TaskPriority):
        """Задача с указанием приоритета."""
        print(f"Выполняется задача {name} с приоритетом {priority.value}")
        time.sleep(0.1)
        return f"Результат {name}"
    
    with WorkerPool() as pool:
        # Отправка задач с разными приоритетами
        tasks = [
            ("low_1", TaskPriority.LOW),
            ("normal_1", TaskPriority.NORMAL),
            ("high_1", TaskPriority.HIGH),
            ("critical_1", TaskPriority.CRITICAL),
            ("low_2", TaskPriority.LOW),
            ("normal_2", TaskPriority.NORMAL),
            ("high_2", TaskPriority.HIGH),
            ("critical_2", TaskPriority.CRITICAL),
        ]
        
        for name, priority in tasks:
            pool.submit_task(
                priority_task,
                name,
                priority,
                name=f"priority_{name}",
                priority=priority
            )
        
        print("Задачи отправлены в порядке: low -> normal -> high -> critical")
        print("Ожидаемый порядок выполнения: critical -> high -> normal -> low")
        
        pool.wait_for_completion()
        print("Все задачи завершены")


def example_graceful_shutdown():
    """Пример graceful shutdown."""
    print("\n=== Пример graceful shutdown ===\n")
    
    def long_running_task(duration: float):
        """Долго выполняющаяся задача."""
        print(f"Запущена долгая задача на {duration}s")
        time.sleep(duration)
        print(f"Завершена долгая задача")
        return f"Результат за {duration}s"
    
    pool = WorkerPool()
    
    try:
        pool.start()
        
        # Отправка долгих задач
        for i in range(3):
            pool.submit_task(
                long_running_task,
                2.0 + i,
                name=f"long_task_{i}",
                priority=TaskPriority.NORMAL
            )
        
        print("Отправлены долгие задачи")
        print("Ожидание 3 секунды перед shutdown...")
        time.sleep(3)
        
    finally:
        print("Инициация graceful shutdown...")
        pool.stop(timeout=10.0)
        print("Shutdown завершен")


def main():
    """Основная функция с продвинутыми примерами."""
    print("=== Продвинутые примеры использования пула воркеров ===\n")
    
    try:
        # Запуск примеров
        example_custom_config()
        example_http_requests()
        example_batch_processing()
        example_monitoring()
        example_priority_queues()
        example_graceful_shutdown()
        
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
    except Exception as e:
        print(f"\nОшибка: {e}")
    
    print("\nВсе примеры завершены")


if __name__ == "__main__":
    main()
