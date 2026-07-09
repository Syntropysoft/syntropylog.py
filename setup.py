"""
Setup script for slpy.
"""

from setuptools import setup, find_packages
import os


def read_readme():
    path = os.path.join(os.path.dirname(__file__), "README.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "slpy — The Declarative Observability Framework for Python"


def get_version():
    init = os.path.join(os.path.dirname(__file__), "slpy", "__init__.py")
    with open(init, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip("\"'")
    return "0.1.0"


setup(
    name="slpy",
    version=get_version(),
    author="Syntropysoft",
    author_email="info@syntropysoft.com",
    description="The Declarative Observability Framework for Python",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/Syntropysoft/syntropylog.py",
    packages=find_packages(include=["slpy", "slpy.*"]),
    python_requires=">=3.7",
    install_requires=[],  # zero runtime dependencies
    extras_require={
        "fastapi": [
            "fastapi>=0.100.0",
        ],
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Logging",
        "Topic :: System :: Monitoring",
    ],
    keywords=["logging", "observability", "masking", "context", "fastapi", "async"],
    license="Apache-2.0",
    include_package_data=True,
    package_data={"slpy": ["py.typed"]},
    zip_safe=False,
)
