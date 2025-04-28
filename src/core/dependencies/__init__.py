"""
Dependency checking system for the trading environment.

This package provides a robust system for checking dependencies before
starting the trading environment. It ensures all required services,
APIs, and resources are available before the system starts.

Basic usage:
    from core.dependencies import DependencyChecker, RedisCheck, ApiCheck
    
    checker = DependencyChecker()
    checker.register_check(RedisCheck())
    checker.register_check(ApiCheck("https://api.example.com/health"))
    
    summary = checker.run_checks()
    if summary.failures > 0:
        print("Not all dependencies are available!")
    else:
        print("All dependencies are available!")
"""

from .base import CheckStatus, CheckResult, DependencyCheck
from .checker import DependencyChecker, CheckSummary
from .services import (
    ServiceCheck,
    RedisCheck,
    PostgresCheck,
    ApiCheck,
    BinanceApiCheck,
    FileSystemCheck,
    PortCheck
)

__all__ = [
    'CheckStatus',
    'CheckResult',
    'DependencyCheck',
    'DependencyChecker',
    'CheckSummary',
    'ServiceCheck',
    'RedisCheck',
    'PostgresCheck',
    'ApiCheck',
    'BinanceApiCheck',
    'FileSystemCheck',
    'PortCheck',
] 