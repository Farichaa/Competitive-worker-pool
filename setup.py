"""
Установочный скрипт для пула воркеров.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Чтение README
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding='utf-8')

# Чтение requirements
requirements = []
requirements_file = this_directory / "requirements.txt"
if requirements_file.exists():
    with open(requirements_file, 'r', encoding='utf-8') as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name="concurrent-worker-pool",
    version="1.0.0",
    author="Worker Pool Team",
    author_email="team@workerpool.example.com",
    description="Высокопроизводительный конкурентный пул воркеров с поддержкой каналов задач, graceful shutdown и ретраев с backoff",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/example/concurrent-worker-pool",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Distributed Computing",
        "Topic :: System :: Networking",
    ],
    python_requires=">=3.8",
    install_requires=[
        "psutil>=5.9.0",
        "pyyaml>=6.0",
        "requests>=2.28.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "pytest-mock>=3.10.0",
            "pytest-asyncio>=0.21.0",
            "black>=22.0.0",
            "flake8>=5.0.0",
            "mypy>=1.0.0",
            "isort>=5.12.0",
        ],
        "docs": [
            "sphinx>=5.0.0",
            "sphinx-rtd-theme>=1.2.0",
        ],
        "monitoring": [
            "prometheus-client>=0.15.0",
        ],
        "cli": [
            "click>=8.1.0",
            "rich>=13.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "worker-pool-examples=scripts.run_examples:main",
            "worker-pool-tests=scripts.run_tests:main",
        ],
    },
    include_package_data=True,
    package_data={
        "worker_pool": ["config/*.yaml", "config/*.json"],
    },
    keywords="concurrent worker pool thread pool task queue retry backoff graceful shutdown",
    project_urls={
        "Bug Reports": "https://github.com/example/concurrent-worker-pool/issues",
        "Source": "https://github.com/example/concurrent-worker-pool",
        "Documentation": "https://concurrent-worker-pool.readthedocs.io/",
    },
)
