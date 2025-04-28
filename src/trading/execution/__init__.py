"""
Execution module for trading system.

This module handles the execution of orders using various strategies
and algorithms to optimize trading performance.
"""

from .execution.strategies import (
    ExecutionStrategy,
    ExecutionStatus,
    ExecutionMetrics,
    TWAPStrategy,
    VWAPStrategy,
    IcebergStrategy,
    ExecutionStrategyFactory,
    ExecutionStrategyType
)

__all__ = [
    'ExecutionStrategy',
    'ExecutionStatus',
    'ExecutionMetrics',
    'TWAPStrategy',
    'VWAPStrategy',
    'IcebergStrategy',
    'ExecutionStrategyFactory',
    'ExecutionStrategyType',
] 