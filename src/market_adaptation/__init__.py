"""
Market Adaptation Package

This package provides functionality to adapt trading strategy parameters
based on current market conditions.

Classes:
    AdaptationStrategy: Adapts trading parameters based on market regimes,
                        volatility, trends, and time-based factors.
"""

from .adaptation_strategy import AdaptationStrategy

__all__ = ["AdaptationStrategy"]
