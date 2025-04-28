"""
Trading agent system for forex trading.

This package provides a framework for implementing and managing
various trading agents for forex trading.
"""

# Expose key components at the agents level
from .risk import MultiLevelExitStrategy

__all__ = [
    'MultiLevelExitStrategy',
]
