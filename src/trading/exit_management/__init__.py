"""
Exit Management System for Trading Strategies

This module provides a comprehensive system for managing stop-loss and 
take-profit levels for trading positions. It supports various types of 
exit strategies including fixed, trailing, volatility-based, and 
time-based.
"""

from .models import (
    Position,
    ExitOrder,
    MarketData,
    OrderType,
    OrderStatus,
    ExitStrategyType
)

from .config import (
    ExitStrategyConfig,
    GlobalRiskParameters,
    StrategyExitConfig,
    ExitManagerConfig
)

from .factory import ExitStrategyFactory
from .manager import ExitManager

# Strategies
from .strategies.base import ExitStrategy
from .strategies.stop_loss import (
    FixedStopLoss,
    TrailingStopLoss,
    AtrStopLoss,
    TimeBasedStopLoss
)
from .strategies.take_profit import (
    FixedTakeProfit,
    TrailingTakeProfit,
    PartialExitStrategy,
    ScaledExitStrategy
)

from .exit_management.exit_manager import ExitManager
from .exit_management.stop_loss_strategies import (
    StopLossStrategy,
    FixedStopLoss,
    TrailingStopLoss,
    ATRStopLoss,
    BreakEvenStopLoss,
    IndicatorBasedStopLoss,
    CombinedStopLoss
)
from .exit_management.take_profit_strategies import (
    TakeProfitStrategy,
    FixedTakeProfit,
    MultiLevelTakeProfit,
    TrailingTakeProfit,
    RiskRewardTakeProfit,
    CombinedTakeProfit
)

__all__ = [
    # Models
    'Position',
    'ExitOrder',
    'MarketData',
    'OrderType',
    'OrderStatus',
    'ExitStrategyType',
    
    # Config
    'ExitStrategyConfig',
    'GlobalRiskParameters',
    'StrategyExitConfig',
    'ExitManagerConfig',
    
    # Factory
    'ExitStrategyFactory',
    
    # Manager
    'ExitManager',
    
    # Strategies
    'ExitStrategy',
    'FixedStopLoss',
    'TrailingStopLoss',
    'AtrStopLoss',
    'TimeBasedStopLoss',
    'FixedTakeProfit',
    'TrailingTakeProfit',
    'PartialExitStrategy',
    'ScaledExitStrategy',
    'StopLossStrategy',
    'ATRStopLoss',
    'BreakEvenStopLoss',
    'IndicatorBasedStopLoss',
    'CombinedStopLoss',
    'TakeProfitStrategy',
    'MultiLevelTakeProfit',
    'RiskRewardTakeProfit',
    'CombinedTakeProfit'
] 