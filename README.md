# Конкурентный пул воркеров

Высокопроизводительный конкурентный пул воркеров для Python с поддержкой каналов задач, graceful shutdown и автоматических ретраев с экспоненциальным backoff.

## 🚀 Особенности

- **Канал задач** - эффективная передача задач между компонентами с поддержкой приоритетных очередей
- **Graceful Shutdown** - корректное завершение работы с ожиданием завершения текущих задач
- **Ретраи с Backoff** - автоматические повторные попытки с экспоненциальным, линейным или фиксированным backoff
- **Автоматическое масштабирование** - динамическое управление количеством воркеров
- **Мониторинг и метрики** - подробная статистика работы пула и системы
- **Конфигурируемость** - гибкая настройка всех компонентов
- **Потокобезопасность** - полная поддержка многопоточности

## 📁 Структура проекта

```
src/worker_pool/
├── core/                    # Основные компоненты
│   ├── worker_pool.py      # Главный класс WorkerPool
│   ├── task_channel.py     # Канал задач с приоритетными очередями
│   ├── retry_manager.py    # Менеджер ретраев с backoff
│   ├── graceful_shutdown.py # Механизм graceful shutdown
│   ├── task_executor.py    # Исполнитель задач
│   └── worker_manager.py   # Менеджер воркеров
├── models/                 # Модели данных
│   ├── task.py            # Модели задач
│   ├── worker.py          # Модели воркеров
│   └── pool_metrics.py    # Метрики пула
├── utils/                  # Утилиты
│   ├── config.py          # Система конфигурации
│   ├── logger.py          # Логирование
│   ├── monitoring.py      # Мониторинг и метрики
│   └── decorators.py      # Декораторы
└── exceptions.py          # Исключения

examples/                   # Примеры использования
├── basic_usage.py         # Базовые примеры
└── advanced_usage.py      # Продвинутые примеры

tests/                      # Тесты
├── test_worker_pool.py    # Тесты основного класса
└── test_components.py     # Тесты компонентов
```

## 🛠 Установка

```bash
# Клонирование репозитория
git clone <repository-url>
cd worker-pool

# Установка зависимостей
pip install -r requirements.txt

# Установка в режиме разработки
pip install -e .
```

## 📖 Быстрый старт

### Базовое использование

```python
from src.worker_pool import WorkerPool, TaskPriority

# Создание и запуск пула
with WorkerPool() as pool:
    # Отправка простой задачи
    task_id = pool.submit_task(
        lambda x: x * 2,
        10,
        name="multiply_task",
        priority=TaskPriority.NORMAL
    )
    
    # Ожидание завершения
    pool.wait_for_completion()
    
    # Получение метрик
    metrics = pool.get_metrics()
    print(f"Выполнено задач: {metrics['total_tasks_completed']}")
```

### Задачи с ретраями

```python
def unreliable_task():
    import random
    if random.random() < 0.3:  # 30% вероятность ошибки
        raise ValueError("Временная ошибка")
    return "Успех"

with WorkerPool() as pool:
    task_id = pool.submit_task(
        unreliable_task,
        name="retry_task",
        max_retries=5  # Максимум 5 попыток
    )
```

### Приоритетные задачи

```python
with WorkerPool() as pool:
    # Низкий приоритет
    pool.submit_task(task_func, priority=TaskPriority.LOW)
    
    # Высокий приоритет
    pool.submit_task(task_func, priority=TaskPriority.HIGH)
    
    # Критический приоритет
    pool.submit_task(task_func, priority=TaskPriority.CRITICAL)
```

## ⚙️ Конфигурация

### Пользовательская конфигурация

```python
from src.worker_pool.core import WorkerPoolConfig
from src.worker_pool.core.task_channel import ChannelConfig
from src.worker_pool.core.retry_manager import RetryConfig

# Создание конфигурации
config = WorkerPoolConfig(
    min_workers=3,
    max_workers=10,
    enable_metrics=True
)

# Настройка канала задач
config.channel_config = ChannelConfig(
    max_size=1000,
    priority_queues=True
)

# Настройка ретраев
config.retry_config = RetryConfig(
    max_retries=5,
    base_delay=1.0,
    exponential_base=2.0
)

# Создание пула с конфигурацией
with WorkerPool(config) as pool:
    # Использование пула
    pass
```

### Конфигурация из файла

```python
from src.worker_pool.utils.config import load_config

# Загрузка из YAML файла
config = load_config("config.yaml")

# Загрузка из JSON файла
config = load_config("config.json")

# Загрузка из переменных окружения
config = load_config_from_env()
```

Пример `config.yaml`:
```yaml
min_workers: 3
max_workers: 10
enable_metrics: true
channel:
  max_size: 1000
  priority_queues: true
retry:
  max_retries: 5
  base_delay: 1.0
  exponential_base: 2.0
```

## 🔄 Стратегии Backoff

Поддерживаются различные стратегии backoff для ретраев:

```python
from src.worker_pool.core.retry_manager import RetryConfig, BackoffStrategy

# Экспоненциальный backoff (по умолчанию)
config = RetryConfig(
    strategy=BackoffStrategy.EXPONENTIAL,
    base_delay=1.0,
    exponential_base=2.0
)

# Линейный backoff
config = RetryConfig(
    strategy=BackoffStrategy.LINEAR,
    base_delay=1.0
)

# Фиксированный backoff
config = RetryConfig(
    strategy=BackoffStrategy.FIXED,
    base_delay=2.0
)

# Случайный backoff
config = RetryConfig(
    strategy=BackoffStrategy.RANDOM,
    base_delay=1.0,
    max_delay=10.0
)
```

## 📊 Мониторинг и метрики

### Базовые метрики

```python
with WorkerPool() as pool:
    # Выполнение задач...
    
    metrics = pool.get_metrics()
    
    # Метрики пула
    print(f"Всего задач: {metrics['total_tasks_submitted']}")
    print(f"Завершено: {metrics['total_tasks_completed']}")
    print(f"Ошибок: {metrics['total_tasks_failed']}")
    print(f"Процент успеха: {metrics['success_rate']:.1f}%")
    
    # Метрики воркеров
    worker_metrics = metrics['worker_metrics']
    print(f"Воркеров: {worker_metrics['total_workers']}")
    print(f"Утилизация: {worker_metrics['worker_utilization']:.1f}%")
    
    # Метрики ретраев
    retry_metrics = metrics['retry_metrics']
    print(f"Всего ретраев: {retry_metrics['total_retries']}")
```

### Системный мониторинг

```python
from src.worker_pool.utils.monitoring import MetricsCollector

# Создание сборщика метрик
collector = MetricsCollector(collection_interval=5.0)
collector.start()

# Получение текущих метрик
current_metrics = collector.get_current_metrics()
if current_metrics:
    system = current_metrics['system']
    print(f"CPU: {system.cpu_percent:.1f}%")
    print(f"Память: {system.memory_percent:.1f}%")

collector.stop()
```

## 🔧 Продвинутые возможности

### Graceful Shutdown

```python
pool = WorkerPool()
pool.start()

try:
    # Выполнение задач...
    pass
finally:
    # Корректное завершение с ожиданием текущих задач
    pool.stop(timeout=30.0)
```

### Масштабирование воркеров

```python
with WorkerPool() as pool:
    # Увеличение количества воркеров
    pool.scale_workers(3)
    
    # Уменьшение количества воркеров
    pool.scale_workers(-2)
    
    print(f"Текущее количество воркеров: {pool.get_worker_count()}")
```

### Декораторы

```python
from src.worker_pool.utils.decorators import retry, timeout, rate_limit

@retry(max_attempts=3, delay=1.0)
@timeout(seconds=10.0)
@rate_limit(max_calls=100, time_window=60.0)
def my_task():
    # Ваша задача
    pass
```

## 🧪 Тестирование

```bash
# Запуск всех тестов
pytest

# Запуск с покрытием
pytest --cov=src/worker_pool

# Запуск конкретного теста
pytest tests/test_worker_pool.py::TestWorkerPool::test_submit_simple_task

# Запуск с подробным выводом
pytest -v
```

## 📝 Примеры

Запуск примеров:

```bash
# Базовый пример
python examples/basic_usage.py

# Продвинутый пример
python examples/advanced_usage.py
```

## 🏗 Архитектура

### Основные компоненты

1. **WorkerPool** - главный класс, координирующий работу всех компонентов
2. **TaskChannel** - канал для передачи задач с поддержкой приоритетных очередей
3. **WorkerManager** - управление воркерами с автоматическим масштабированием
4. **RetryManager** - система ретраев с различными стратегиями backoff
5. **GracefulShutdown** - механизм корректного завершения работы
6. **TaskExecutor** - выполнение задач с поддержкой таймаутов

### Поток данных

```
Задача -> TaskChannel -> WorkerManager -> TaskExecutor -> Результат
                ↓
        RetryManager (при ошибках)
                ↓
        GracefulShutdown (при завершении)
```

## 🚀 Производительность

- **Высокая пропускная способность** - эффективная обработка тысяч задач в секунду
- **Низкая задержка** - минимальное время от отправки до выполнения задачи
- **Масштабируемость** - автоматическое управление ресурсами
- **Отказоустойчивость** - автоматические ретраи и восстановление

## 🤝 Вклад в проект

1. Форкните репозиторий
2. Создайте ветку для новой функции (`git checkout -b feature/amazing-feature`)
3. Зафиксируйте изменения (`git commit -m 'Add amazing feature'`)
4. Отправьте в ветку (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

## 📄 Лицензия

Этот проект распространяется под лицензией MIT. См. файл `LICENSE` для подробностей.

## 🆘 Поддержка

Если у вас есть вопросы или проблемы:

1. Проверьте [документацию](docs/)
2. Посмотрите [примеры](examples/)
3. Создайте [Issue](issues/) в репозитории

## 🔄 История версий

### v1.0.0
- Первый релиз
- Базовая функциональность пула воркеров
- Поддержка каналов задач
- Graceful shutdown
- Ретраи с backoff
- Мониторинг и метрики

---

**Создано с ❤️ для высокопроизводительных Python приложений**