#!/usr/bin/env python3
"""
Скрипт для запуска примеров использования пула воркеров.
"""

import sys
import argparse
import importlib
from pathlib import Path


def main():
    """Основная функция скрипта."""
    parser = argparse.ArgumentParser(description="Запуск примеров пула воркеров")
    parser.add_argument(
        "example",
        choices=["basic", "advanced"],
        help="Тип примера для запуска"
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Путь к файлу конфигурации"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Уровень логирования"
    )
    
    args = parser.parse_args()
    
    # Добавление пути к модулям
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    try:
        if args.example == "basic":
            print("Запуск базового примера...")
            import examples.basic_usage
            examples.basic_usage.main()
        elif args.example == "advanced":
            print("Запуск продвинутого примера...")
            import examples.advanced_usage
            examples.advanced_usage.main()
        
        print("Пример завершен успешно!")
        
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка при выполнении примера: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
