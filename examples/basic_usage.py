"""
Базовый пример использования конкурентного пула воркеров.
"""

import time
import random
from src.worker_pool import WorkerPool, TaskPriority


def simple_task(x: int) -> int:
    """Простая задача для демонстрации."""
    print(f"Выполняется задача с аргументом {x}")
    time.sleep(random.uniform(0.1, 0.5))  # Имитация работы
    return x * 2


def failing_task(x: int) -> int:
    """Задача, которая может завершиться с ошибкой."""
    if random.random() < 0.3:  # 30% вероятность ошибки
        raise ValueError(f"Ошибка в задаче {x}")
    
    time.sleep(random.uniform(0.1, 0.3))
    return x * 3


def cpu_intensive_task(n: int) -> int:
    """CPU-интенсивная задача."""
    result = 0
    for i in range(n):
        result += i ** 2
    return result


def main():
    """Основная функция с примерами использования."""
    print("=== Базовый пример использования пула воркеров ===\n")
    
    # Создание и запуск пула
    with WorkerPool() as pool:
        print(f"Пул запущен с {pool.get_worker_count()} воркерами")
        
        # Пример 1: Простые задачи
        print("\n1. Отправка простых задач:")
        task_ids = []
        for i in range(5):
            task_id = pool.submit_task(
                simple_task, 
                i, 
                name=f"simple_task_{i}",
                priority=TaskPriority.NORMAL
            )
            task_ids.append(task_id)
            print(f"   Отправлена задача {task_id}")
        
        # Ожидание завершения
        print("   Ожидание завершения задач...")
        pool.wait_for_completion(timeout=10.0)
        
        # Пример 2: Задачи с приоритетами
        print("\n2. Задачи с разными приоритетами:")
        
        # Низкий приоритет
        pool.submit_task(
            simple_task, 100, 
            name="low_priority", 
            priority=TaskPriority.LOW
        )
        
        # Высокий приоритет
        pool.submit_task(
            simple_task, 200, 
            name="high_priority", 
            priority=TaskPriority.HIGH
        )
        
        # Критический приоритет
        pool.submit_task(
            simple_task, 300, 
            name="critical_priority", 
            priority=TaskPriority.CRITICAL
        )
        
        print("   Отправлены задачи с разными приоритетами")
        
        # Пример 3: Задачи с ретраями
        print("\n3. Задачи с автоматическими ретраями:")
        for i in range(3):
            pool.submit_task(
                failing_task, i, 
                name=f"retry_task_{i}",
                max_retries=3
            )
        
        print("   Отправлены задачи с возможными ошибками (с ретраями)")
        
        # Пример 4: CPU-интенсивные задачи
        print("\n4. CPU-интенсивные задачи:")
        for i in range(3):
            pool.submit_task(
                cpu_intensive_task, 10000 + i * 1000,
                name=f"cpu_task_{i}",
                priority=TaskPriority.NORMAL
            )
        
        print("   Отправлены CPU-интенсивные задачи")
        
        # Ожидание завершения всех задач
        print("\nОжидание завершения всех задач...")
        if pool.wait_for_completion(timeout=30.0):
            print("Все задачи завершены успешно!")
        else:
            print("Таймаут ожидания завершения задач")
        
        # Вывод метрик
        print("\n=== Метрики пула ===")
        metrics = pool.get_metrics()
        print(f"Всего задач отправлено: {metrics['total_tasks_submitted']}")
        print(f"Задач завершено: {metrics['total_tasks_completed']}")
        print(f"Задач с ошибками: {metrics['total_tasks_failed']}")
        print(f"Процент успеха: {metrics['success_rate']:.1f}%")
        print(f"Среднее время выполнения: {metrics['average_execution_time']:.3f}s")
        
        # Метрики воркеров
        worker_metrics = metrics['worker_metrics']
        print(f"\nВоркеры:")
        print(f"  Всего: {worker_metrics['total_workers']}")
        print(f"  Свободных: {worker_metrics['idle_workers']}")
        print(f"  Занятых: {worker_metrics['busy_workers']}")
        print(f"  Утилизация: {worker_metrics['worker_utilization']:.1f}%")
        
        # Метрики ретраев
        retry_metrics = metrics['retry_metrics']
        print(f"\nРетраи:")
        print(f"  Всего ретраев: {retry_metrics['total_retries']}")
        print(f"  Успешных ретраев: {retry_metrics['successful_retries']}")
        print(f"  Неудачных ретраев: {retry_metrics['failed_retries']}")
    
    print("\nПул воркеров остановлен")


if __name__ == "__main__":
    main()
