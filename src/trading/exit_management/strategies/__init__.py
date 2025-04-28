"""
Exit strategies for trading positions.

This module contains strategies for stop-loss and take-profit management.
"""

from .base import ExitStrategy
from .stop_loss import (
    FixedStopLoss,
    TrailingStopLoss,
    AtrStopLoss,
    TimeBasedStopLoss
)
from .take_profit import (
    FixedTakeProfit,
    TrailingTakeProfit,
    PartialExitStrategy,
    ScaledExitStrategy
)

__all__ = [
    'ExitStrategy',
    'FixedStopLoss',
    'TrailingStopLoss',
    'AtrStopLoss',
    'TimeBasedStopLoss',
    'FixedTakeProfit',
    'TrailingTakeProfit',
    'PartialExitStrategy',
    'ScaledExitStrategy',
] 