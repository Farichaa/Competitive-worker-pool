"""
Система мониторинга для пула воркеров.
"""

import time
import threading
import psutil
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque

from ..utils.logger import get_logger


logger = get_logger(__name__)


@dataclass
class SystemMetrics:
    """Метрики системы."""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_available_mb: float = 0.0
    disk_usage_percent: float = 0.0
    network_io_bytes: int = 0
    load_average: tuple = (0.0, 0.0, 0.0)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class HealthStatus:
    """Статус здоровья системы."""
    is_healthy: bool = True
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


class MetricsCollector:
    """Сборщик метрик системы и приложения."""
    
    def __init__(self, collection_interval: float = 5.0, history_size: int = 100):
        self.collection_interval = collection_interval
        self.history_size = history_size
        
        self._metrics_history: deque = deque(maxlen=history_size)
        self._custom_metrics: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._collection_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Callback'и для пользовательских метрик
        self._custom_collectors: List[Callable[[], Dict[str, Any]]] = []
        
        logger.info(f"MetricsCollector initialized with interval {collection_interval}s")
    
    def start(self):
        """Запуск сбора метрик."""
        if self._collection_thread and self._collection_thread.is_alive():
            logger.warning("Metrics collection already running")
            return
        
        self._stop_event.clear()
        self._collection_thread = threading.Thread(
            target=self._collection_loop,
            name="metrics-collector",
            daemon=True
        )
        self._collection_thread.start()
        logger.info("Metrics collection started")
    
    def stop(self):
        """Остановка сбора метрик."""
        if self._collection_thread and self._collection_thread.is_alive():
            self._stop_event.set()
            self._collection_thread.join(timeout=5.0)
            logger.info("Metrics collection stopped")
    
    def _collection_loop(self):
        """Основной цикл сбора метрик."""
        while not self._stop_event.is_set():
            try:
                # Сбор системных метрик
                system_metrics = self._collect_system_metrics()
                
                # Сбор пользовательских метрик
                custom_metrics = self._collect_custom_metrics()
                
                # Объединение метрик
                all_metrics = {
                    'timestamp': datetime.now(),
                    'system': system_metrics,
                    'custom': custom_metrics
                }
                
                # Сохранение в историю
                with self._lock:
                    self._metrics_history.append(all_metrics)
                
                time.sleep(self.collection_interval)
                
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")
                time.sleep(1.0)
    
    def _collect_system_metrics(self) -> SystemMetrics:
        """Сбор системных метрик."""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Память
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_mb = memory.used / (1024 * 1024)
            memory_available_mb = memory.available / (1024 * 1024)
            
            # Диск
            disk = psutil.disk_usage('/')
            disk_usage_percent = (disk.used / disk.total) * 100
            
            # Сеть
            network = psutil.net_io_counters()
            network_io_bytes = network.bytes_sent + network.bytes_recv
            
            # Load average (Linux/Unix)
            try:
                load_average = psutil.getloadavg()
            except AttributeError:
                load_average = (0.0, 0.0, 0.0)
            
            return SystemMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_used_mb=memory_used_mb,
                memory_available_mb=memory_available_mb,
                disk_usage_percent=disk_usage_percent,
                network_io_bytes=network_io_bytes,
                load_average=load_average
            )
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            return SystemMetrics()
    
    def _collect_custom_metrics(self) -> Dict[str, Any]:
        """Сбор пользовательских метрик."""
        custom_metrics = {}
        
        for collector in self._custom_collectors:
            try:
                metrics = collector()
                custom_metrics.update(metrics)
            except Exception as e:
                logger.error(f"Error in custom metric collector {collector}: {e}")
        
        return custom_metrics
    
    def add_custom_collector(self, collector: Callable[[], Dict[str, Any]]):
        """Добавление пользовательского сборщика метрик."""
        self._custom_collectors.append(collector)
        logger.debug(f"Added custom metric collector: {collector}")
    
    def get_current_metrics(self) -> Optional[Dict[str, Any]]:
        """Получение текущих метрик."""
        with self._lock:
            if self._metrics_history:
                return self._metrics_history[-1]
            return None
    
    def get_metrics_history(self, duration_minutes: Optional[int] = None) -> List[Dict[str, Any]]:
        """Получение истории метрик."""
        with self._lock:
            history = list(self._metrics_history)
        
        if duration_minutes:
            cutoff_time = datetime.now() - timedelta(minutes=duration_minutes)
            history = [m for m in history if m['timestamp'] >= cutoff_time]
        
        return history
    
    def get_metrics_summary(self, duration_minutes: int = 5) -> Dict[str, Any]:
        """Получение сводки метрик за период."""
        history = self.get_metrics_history(duration_minutes)
        
        if not history:
            return {}
        
        # Агрегация системных метрик
        cpu_values = [m['system'].cpu_percent for m in history]
        memory_values = [m['system'].memory_percent for m in history]
        
        summary = {
            'duration_minutes': duration_minutes,
            'data_points': len(history),
            'system': {
                'cpu': {
                    'avg': sum(cpu_values) / len(cpu_values),
                    'max': max(cpu_values),
                    'min': min(cpu_values)
                },
                'memory': {
                    'avg': sum(memory_values) / len(memory_values),
                    'max': max(memory_values),
                    'min': min(memory_values)
                }
            }
        }
        
        return summary


class HealthChecker:
    """Проверка здоровья системы."""
    
    def __init__(self, metrics_collector: Optional[MetricsCollector] = None):
        self.metrics_collector = metrics_collector
        self._health_checks: List[Callable[[], HealthStatus]] = []
        
        # Пороги для автоматических проверок
        self.cpu_threshold = 90.0
        self.memory_threshold = 90.0
        self.disk_threshold = 95.0
        
        logger.info("HealthChecker initialized")
    
    def add_health_check(self, check_func: Callable[[], HealthStatus]):
        """Добавление проверки здоровья."""
        self._health_checks.append(check_func)
        logger.debug(f"Added health check: {check_func}")
    
    def check_health(self) -> HealthStatus:
        """Выполнение всех проверок здоровья."""
        issues = []
        warnings = []
        
        # Автоматические проверки на основе метрик
        if self.metrics_collector:
            current_metrics = self.metrics_collector.get_current_metrics()
            if current_metrics:
                system_metrics = current_metrics.get('system')
                if system_metrics:
                    # Проверка CPU
                    if system_metrics.cpu_percent > self.cpu_threshold:
                        issues.append(f"High CPU usage: {system_metrics.cpu_percent:.1f}%")
                    elif system_metrics.cpu_percent > self.cpu_threshold * 0.8:
                        warnings.append(f"Elevated CPU usage: {system_metrics.cpu_percent:.1f}%")
                    
                    # Проверка памяти
                    if system_metrics.memory_percent > self.memory_threshold:
                        issues.append(f"High memory usage: {system_metrics.memory_percent:.1f}%")
                    elif system_metrics.memory_percent > self.memory_threshold * 0.8:
                        warnings.append(f"Elevated memory usage: {system_metrics.memory_percent:.1f}%")
                    
                    # Проверка диска
                    if system_metrics.disk_usage_percent > self.disk_threshold:
                        issues.append(f"High disk usage: {system_metrics.disk_usage_percent:.1f}%")
                    elif system_metrics.disk_usage_percent > self.disk_threshold * 0.8:
                        warnings.append(f"Elevated disk usage: {system_metrics.disk_usage_percent:.1f}%")
        
        # Пользовательские проверки
        for check_func in self._health_checks:
            try:
                health_status = check_func()
                issues.extend(health_status.issues)
                warnings.extend(health_status.warnings)
            except Exception as e:
                logger.error(f"Error in health check {check_func}: {e}")
                issues.append(f"Health check error: {e}")
        
        is_healthy = len(issues) == 0
        
        return HealthStatus(
            is_healthy=is_healthy,
            issues=issues,
            warnings=warnings
        )
    
    def is_system_healthy(self) -> bool:
        """Быстрая проверка здоровья системы."""
        return self.check_health().is_healthy


class PerformanceMonitor:
    """Мониторинг производительности пула воркеров."""
    
    def __init__(self, pool_instance=None):
        self.pool_instance = pool_instance
        self._monitoring_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Пороги для алертов
        self.queue_size_threshold = 100
        self.worker_utilization_threshold = 95.0
        self.error_rate_threshold = 10.0
        
        logger.info("PerformanceMonitor initialized")
    
    def start_monitoring(self, interval: float = 10.0):
        """Запуск мониторинга производительности."""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            logger.warning("Performance monitoring already running")
            return
        
        self._stop_event.clear()
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(interval,),
            name="performance-monitor",
            daemon=True
        )
        self._monitoring_thread.start()
        logger.info("Performance monitoring started")
    
    def stop_monitoring(self):
        """Остановка мониторинга."""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._stop_event.set()
            self._monitoring_thread.join(timeout=5.0)
            logger.info("Performance monitoring stopped")
    
    def _monitoring_loop(self, interval: float):
        """Основной цикл мониторинга."""
        while not self._stop_event.is_set():
            try:
                if self.pool_instance:
                    self._check_pool_health()
                
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Error in performance monitoring: {e}")
                time.sleep(1.0)
    
    def _check_pool_health(self):
        """Проверка здоровья пула."""
        try:
            metrics = self.pool_instance.get_metrics()
            
            # Проверка размера очереди
            queue_size = metrics.get('current_queue_size', 0)
            if queue_size > self.queue_size_threshold:
                logger.warning(f"High queue size: {queue_size}")
            
            # Проверка загрузки воркеров
            worker_metrics = metrics.get('worker_metrics', {})
            utilization = worker_metrics.get('worker_utilization', 0)
            if utilization > self.worker_utilization_threshold:
                logger.warning(f"High worker utilization: {utilization:.1f}%")
            
            # Проверка процента ошибок
            error_rate = metrics.get('error_rate', 0)
            if error_rate > self.error_rate_threshold:
                logger.warning(f"High error rate: {error_rate:.1f}%")
                
        except Exception as e:
            logger.error(f"Error checking pool health: {e}")
