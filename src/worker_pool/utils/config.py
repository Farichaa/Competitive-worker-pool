"""
Система конфигурации для пула воркеров.
"""

import json
import yaml
import os
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass, asdict
from pathlib import Path

from ..core.task_channel import ChannelConfig
from ..core.retry_manager import RetryConfig
from ..core.graceful_shutdown import ShutdownConfig
from ..core.task_executor import ExecutionConfig
from ..core.worker_manager import WorkerManagerConfig


@dataclass
class Config:
    """Основная конфигурация пула воркеров."""
    
    # Основные параметры пула
    min_workers: int = 2
    max_workers: int = 10
    enable_metrics: bool = True
    enable_monitoring: bool = True
    log_level: str = "INFO"
    
    # Конфигурации компонентов
    channel: ChannelConfig = None
    retry: RetryConfig = None
    shutdown: ShutdownConfig = None
    execution: ExecutionConfig = None
    worker_manager: WorkerManagerConfig = None
    
    def __post_init__(self):
        """Инициализация конфигураций по умолчанию."""
        if self.channel is None:
            self.channel = ChannelConfig()
        if self.retry is None:
            self.retry = RetryConfig()
        if self.shutdown is None:
            self.shutdown = ShutdownConfig()
        if self.execution is None:
            self.execution = ExecutionConfig()
        if self.worker_manager is None:
            self.worker_manager = WorkerManagerConfig()
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь."""
        config_dict = asdict(self)
        
        # Рекурсивно преобразуем вложенные конфигурации
        for key, value in config_dict.items():
            if hasattr(value, '__dict__'):
                config_dict[key] = asdict(value)
        
        return config_dict
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """Создание из словаря."""
        # Извлекаем конфигурации компонентов
        channel_data = data.pop('channel', {})
        retry_data = data.pop('retry', {})
        shutdown_data = data.pop('shutdown', {})
        execution_data = data.pop('execution', {})
        worker_manager_data = data.pop('worker_manager', {})
        
        # Создаем основной объект
        config = cls(**data)
        
        # Устанавливаем конфигурации компонентов
        if channel_data:
            config.channel = ChannelConfig(**channel_data)
        if retry_data:
            config.retry = RetryConfig(**retry_data)
        if shutdown_data:
            config.shutdown = ShutdownConfig(**shutdown_data)
        if execution_data:
            config.execution = ExecutionConfig(**execution_data)
        if worker_manager_data:
            config.worker_manager = WorkerManagerConfig(**worker_manager_data)
        
        return config
    
    def validate(self) -> bool:
        """Валидация конфигурации."""
        errors = []
        
        # Проверка основных параметров
        if self.min_workers < 1:
            errors.append("min_workers must be >= 1")
        
        if self.max_workers < self.min_workers:
            errors.append("max_workers must be >= min_workers")
        
        if self.max_workers > 100:
            errors.append("max_workers should not exceed 100")
        
        # Проверка конфигурации канала
        if self.channel.max_size < 1:
            errors.append("channel.max_size must be >= 1")
        
        # Проверка конфигурации ретраев
        if self.retry.max_retries < 0:
            errors.append("retry.max_retries must be >= 0")
        
        if self.retry.base_delay < 0:
            errors.append("retry.base_delay must be >= 0")
        
        # Проверка конфигурации shutdown
        if self.shutdown.timeout < 0:
            errors.append("shutdown.timeout must be >= 0")
        
        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")
        
        return True
    
    def update(self, **kwargs) -> 'Config':
        """Обновление конфигурации с новыми значениями."""
        new_config = self.to_dict()
        new_config.update(kwargs)
        return Config.from_dict(new_config)


def load_config(file_path: Union[str, Path]) -> Config:
    """
    Загрузка конфигурации из файла.
    
    Args:
        file_path: Путь к файлу конфигурации
        
    Returns:
        Объект конфигурации
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        if file_path.suffix.lower() in ['.yaml', '.yml']:
            data = yaml.safe_load(f)
        elif file_path.suffix.lower() == '.json':
            data = json.load(f)
        else:
            raise ValueError(f"Unsupported configuration file format: {file_path.suffix}")
    
    config = Config.from_dict(data)
    config.validate()
    
    return config


def save_config(config: Config, file_path: Union[str, Path], format: str = 'yaml'):
    """
    Сохранение конфигурации в файл.
    
    Args:
        config: Объект конфигурации
        file_path: Путь к файлу
        format: Формат файла ('yaml' или 'json')
    """
    file_path = Path(file_path)
    data = config.to_dict()
    
    # Создаем директорию если не существует
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        if format.lower() == 'yaml':
            yaml.dump(data, f, default_flow_style=False, indent=2)
        elif format.lower() == 'json':
            json.dump(data, f, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"Unsupported format: {format}")


def load_config_from_env() -> Config:
    """
    Загрузка конфигурации из переменных окружения.
    
    Returns:
        Объект конфигурации
    """
    config_data = {}
    
    # Основные параметры
    if os.getenv('WORKER_POOL_MIN_WORKERS'):
        config_data['min_workers'] = int(os.getenv('WORKER_POOL_MIN_WORKERS'))
    
    if os.getenv('WORKER_POOL_MAX_WORKERS'):
        config_data['max_workers'] = int(os.getenv('WORKER_POOL_MAX_WORKERS'))
    
    if os.getenv('WORKER_POOL_LOG_LEVEL'):
        config_data['log_level'] = os.getenv('WORKER_POOL_LOG_LEVEL')
    
    if os.getenv('WORKER_POOL_ENABLE_METRICS'):
        config_data['enable_metrics'] = os.getenv('WORKER_POOL_ENABLE_METRICS').lower() == 'true'
    
    # Конфигурация канала
    channel_data = {}
    if os.getenv('CHANNEL_MAX_SIZE'):
        channel_data['max_size'] = int(os.getenv('CHANNEL_MAX_SIZE'))
    
    if os.getenv('CHANNEL_PRIORITY_QUEUES'):
        channel_data['priority_queues'] = os.getenv('CHANNEL_PRIORITY_QUEUES').lower() == 'true'
    
    if channel_data:
        config_data['channel'] = channel_data
    
    # Конфигурация ретраев
    retry_data = {}
    if os.getenv('RETRY_MAX_RETRIES'):
        retry_data['max_retries'] = int(os.getenv('RETRY_MAX_RETRIES'))
    
    if os.getenv('RETRY_BASE_DELAY'):
        retry_data['base_delay'] = float(os.getenv('RETRY_BASE_DELAY'))
    
    if os.getenv('RETRY_MAX_DELAY'):
        retry_data['max_delay'] = float(os.getenv('RETRY_MAX_DELAY'))
    
    if retry_data:
        config_data['retry'] = retry_data
    
    # Конфигурация shutdown
    shutdown_data = {}
    if os.getenv('SHUTDOWN_TIMEOUT'):
        shutdown_data['timeout'] = float(os.getenv('SHUTDOWN_TIMEOUT'))
    
    if shutdown_data:
        config_data['shutdown'] = shutdown_data
    
    return Config.from_dict(config_data)


def create_default_config() -> Config:
    """Создание конфигурации по умолчанию."""
    return Config()


def merge_configs(base_config: Config, override_config: Config) -> Config:
    """
    Объединение двух конфигураций.
    
    Args:
        base_config: Базовая конфигурация
        override_config: Конфигурация для переопределения
        
    Returns:
        Объединенная конфигурация
    """
    base_dict = base_config.to_dict()
    override_dict = override_config.to_dict()
    
    # Рекурсивное объединение словарей
    def merge_dicts(base: dict, override: dict) -> dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = merge_dicts(result[key], value)
            else:
                result[key] = value
        return result
    
    merged_dict = merge_dicts(base_dict, override_dict)
    return Config.from_dict(merged_dict)
