#!/usr/bin/env python3
"""
Скрипт для запуска тестов пула воркеров.
"""

import sys
import subprocess
import argparse
from pathlib import Path


def main():
    """Основная функция скрипта."""
    parser = argparse.ArgumentParser(description="Запуск тестов пула воркеров")
    parser.add_argument(
        "--test-path",
        type=str,
        default="tests/",
        help="Путь к тестам"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Запуск с измерением покрытия"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Подробный вывод"
    )
    parser.add_argument(
        "--test-pattern",
        type=str,
        help="Паттерн для фильтрации тестов"
    )
    
    args = parser.parse_args()
    
    # Команда pytest
    cmd = ["python", "-m", "pytest"]
    
    if args.coverage:
        cmd.extend(["--cov=src/worker_pool", "--cov-report=html", "--cov-report=term"])
    
    if args.verbose:
        cmd.append("-v")
    
    if args.test_pattern:
        cmd.extend(["-k", args.test_pattern])
    
    cmd.append(args.test_path)
    
    # Запуск тестов
    try:
        print(f"Запуск команды: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True)
        print("Все тесты прошли успешно!")
        return result.returncode
        
    except subprocess.CalledProcessError as e:
        print(f"Тесты завершились с ошибкой: {e}")
        return e.returncode
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
        return 1


if __name__ == "__main__":
    sys.exit(main())
