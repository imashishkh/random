"""
Forex Trading Bot - Setup Script

This file configures the installation of the Forex Trading Bot package,
including CLI entry points and dependencies.
"""

from setuptools import setup, find_packages

# Fallback setup script for compatibility with pip, build tools,
# and development environments that don't support pyproject.toml
# For modern packaging, refer to pyproject.toml instead.

setup(
    name="forex-trading-bot",
    version="0.1.0",
    description="USDT-Based Forex AI Trading Agent Swarm",
    author="Forex Trading Team",
    author_email="team@forextrading.example.com",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    include_package_data=True,
    install_requires=[
        "click>=8.0.0",
        "rich>=10.0.0",
        "fastapi>=0.68.0",
        "uvicorn>=0.15.0",
        "pydantic>=1.8.0",
        "python-dotenv>=0.19.0",
        "structlog",
        "langchain",
        "langgraph",
        "pandas",
        "numpy",
        "requests",
        "aiohttp",
        "websockets", 
        "redis",
        "pymongo",
        "cryptography",
        "keyring",
        "pytest",
        "tenacity",
        "ccxt",
    ],
    entry_points={
        "console_scripts": [
            "botctl=src.cli.bot_cli:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Financial and Insurance Industry",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
) 