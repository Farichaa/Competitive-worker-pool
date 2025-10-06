# Makefile для пула воркеров

.PHONY: help install install-dev test test-cov lint format clean docs examples

# Переменные
PYTHON := python
PIP := pip
PYTEST := pytest
BLACK := black
FLAKE8 := flake8
MYPY := mypy
ISORT := isort

# Цвета для вывода
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help: ## Показать справку
	@echo "Доступные команды:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'

install: ## Установить основные зависимости
	@echo "$(YELLOW)Установка основных зависимостей...$(NC)"
	$(PIP) install -r requirements.txt

install-dev: ## Установить зависимости для разработки
	@echo "$(YELLOW)Установка зависимостей для разработки...$(NC)"
	$(PIP) install -e .
	$(PIP) install -r requirements.txt

test: ## Запустить тесты
	@echo "$(YELLOW)Запуск тестов...$(NC)"
	$(PYTHON) scripts/run_tests.py --verbose

test-cov: ## Запустить тесты с покрытием
	@echo "$(YELLOW)Запуск тестов с покрытием...$(NC)"
	$(PYTHON) scripts/run_tests.py --coverage --verbose

test-fast: ## Быстрые тесты
	@echo "$(YELLOW)Запуск быстрых тестов...$(NC)"
	$(PYTEST) tests/ -v -x

lint: ## Проверка кода линтерами
	@echo "$(YELLOW)Проверка кода...$(NC)"
	$(FLAKE8) src/ tests/ examples/ --max-line-length=100
	$(MYPY) src/ --ignore-missing-imports

format: ## Форматирование кода
	@echo "$(YELLOW)Форматирование кода...$(NC)"
	$(BLACK) src/ tests/ examples/ --line-length=100
	$(ISORT) src/ tests/ examples/ --profile=black

format-check: ## Проверка форматирования
	@echo "$(YELLOW)Проверка форматирования...$(NC)"
	$(BLACK) --check src/ tests/ examples/ --line-length=100
	$(ISORT) --check-only src/ tests/ examples/ --profile=black

clean: ## Очистка временных файлов
	@echo "$(YELLOW)Очистка временных файлов...$(NC)"
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/
	rm -rf dist/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/

docs: ## Генерация документации
	@echo "$(YELLOW)Генерация документации...$(NC)"
	cd docs && make html

examples: ## Запуск примеров
	@echo "$(YELLOW)Запуск примеров...$(NC)"
	$(PYTHON) scripts/run_examples.py basic
	$(PYTHON) scripts/run_examples.py advanced

examples-basic: ## Запуск базового примера
	@echo "$(YELLOW)Запуск базового примера...$(NC)"
	$(PYTHON) scripts/run_examples.py basic

examples-advanced: ## Запуск продвинутого примера
	@echo "$(YELLOW)Запуск продвинутого примера...$(NC)"
	$(PYTHON) scripts/run_examples.py advanced

build: ## Сборка пакета
	@echo "$(YELLOW)Сборка пакета...$(NC)"
	$(PYTHON) setup.py sdist bdist_wheel

install-local: ## Локальная установка пакета
	@echo "$(YELLOW)Локальная установка пакета...$(NC)"
	$(PIP) install -e .

check: format-check lint test ## Полная проверка (форматирование + линтинг + тесты)

ci: install-dev check test-cov ## Команды для CI/CD

all: clean install-dev check test-cov examples ## Полная проверка проекта

# Развертывание
deploy-test: ## Развертывание в тестовую среду
	@echo "$(YELLOW)Развертывание в тестовую среду...$(NC)"
	# Здесь будут команды для развертывания

deploy-prod: ## Развертывание в продакшн
	@echo "$(YELLOW)Развертывание в продакшн...$(NC)"
	# Здесь будут команды для развертывания

# Мониторинг
monitor: ## Запуск мониторинга
	@echo "$(YELLOW)Запуск мониторинга...$(NC)"
	$(PYTHON) -c "from src.worker_pool.utils.monitoring import MetricsCollector; import time; c = MetricsCollector(); c.start(); time.sleep(10); c.stop()"

# Бенчмарки
benchmark: ## Запуск бенчмарков
	@echo "$(YELLOW)Запуск бенчмарков...$(NC)"
	$(PYTHON) -c "import time; from src.worker_pool import WorkerPool; pool = WorkerPool(); pool.start(); start = time.time(); [pool.submit_task(lambda x: x*2, i) for i in range(1000)]; pool.wait_for_completion(); print(f'1000 задач за {time.time()-start:.2f}s'); pool.stop()"
