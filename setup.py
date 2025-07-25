"""
Setup script for SyntropyLog Python

This script configures the SyntropyLog Python package for distribution
and installation.
"""

from setuptools import setup, find_packages
import os

# Read the README file
def read_readme():
    """Read the README.md file for long description."""
    readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "SyntropyLog Python - From Chaos to Clarity"

# Read version from __init__.py
def get_version():
    """Extract version from __init__.py file."""
    init_path = os.path.join(os.path.dirname(__file__), 'syntropylog', '__init__.py')
    with open(init_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('__version__'):
                return line.split('=')[1].strip().strip('"\'')
    return '0.1.0'

setup(
    name="syntropylog",
    version=get_version(),
    author="Syntropysoft",
    author_email="info@syntropysoft.com",
    description="From Chaos to Clarity - The Observability Framework for High-Performance Teams",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/Syntropysoft/SyntropyLog",
    project_urls={
        "Bug Tracker": "https://github.com/Syntropysoft/SyntropyLog/issues",
        "Documentation": "https://syntropysoft.github.io/syntropylog-doc/",
        "Source Code": "https://github.com/Syntropysoft/SyntropyLog",
    },
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Logging",
        "Topic :: System :: Monitoring",
        "Topic :: System :: Distributed Computing",
    ],
    python_requires=">=3.8",
    install_requires=[
        "pydantic>=1.10.0",
        "asyncio-mqtt>=0.11.0",  # For MQTT support
        "redis>=4.0.0",  # For Redis integration
        "aiohttp>=3.8.0",  # For HTTP client instrumentation
        "structlog>=22.0.0",  # For structured logging
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "black>=22.0.0",
            "isort>=5.0.0",
            "mypy>=1.0.0",
            "flake8>=5.0.0",
        ],
        "kafka": [
            "aiokafka>=0.8.0",
        ],
        "rabbitmq": [
            "aio-pika>=8.0.0",
        ],
        "nats": [
            "nats-py>=2.0.0",
        ],
        "fastapi": [
            "fastapi>=0.100.0",
            "uvicorn>=0.20.0",
        ],
        "django": [
            "django>=4.0.0",
        ],
        "flask": [
            "flask>=2.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "syntropylog=syntropylog.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "syntropylog": ["py.typed"],
    },
    zip_safe=False,
    keywords=[
        "logging",
        "observability",
        "monitoring",
        "tracing",
        "correlation",
        "distributed",
        "async",
        "python",
    ],
    license="Apache License 2.0",
    platforms=["any"],
) 