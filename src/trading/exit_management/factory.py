from typing import Dict, Any

from .config import ExitStrategyConfig
from .models import ExitStrategyType
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


class ExitStrategyFactory:
    """Factory for creating exit strategy instances"""
    
    @staticmethod
    def create_strategy(config: ExitStrategyConfig) -> ExitStrategy:
        """
        Create and return a specific exit strategy based on configuration
        
        Args:
            config: Configuration for the exit strategy
            
        Returns:
            An instance of a concrete ExitStrategy implementation
            
        Raises:
            ValueError: If the strategy type is unknown
        """
        strategy_type = config.strategy_type
        params = config.parameters
        
        # Stop-loss strategies
        if strategy_type == ExitStrategyType.FIXED_STOP_LOSS:
            return FixedStopLoss(**params)
        elif strategy_type == ExitStrategyType.TRAILING_STOP_LOSS:
            return TrailingStopLoss(**params)
        elif strategy_type == ExitStrategyType.ATR_STOP_LOSS:
            return AtrStopLoss(**params)
        elif strategy_type == ExitStrategyType.TIME_BASED_STOP_LOSS:
            return TimeBasedStopLoss(**params)
            
        # Take-profit strategies
        elif strategy_type == ExitStrategyType.FIXED_TAKE_PROFIT:
            return FixedTakeProfit(**params)
        elif strategy_type == ExitStrategyType.TRAILING_TAKE_PROFIT:
            return TrailingTakeProfit(**params)
        elif strategy_type == ExitStrategyType.PARTIAL_EXIT:
            return PartialExitStrategy(**params)
        elif strategy_type == ExitStrategyType.SCALED_EXIT:
            return ScaledExitStrategy(**params)
        
        raise ValueError(f"Unknown exit strategy type: {strategy_type}")
    
    @staticmethod
    def create_default_stop_loss(risk_percentage: float = 0.02) -> ExitStrategy:
        """
        Create a default stop-loss strategy
        
        Args:
            risk_percentage: Percentage risk for the stop-loss
            
        Returns:
            A fixed stop-loss strategy
        """
        return FixedStopLoss(percentage=risk_percentage)
    
    @staticmethod
    def create_default_take_profit(reward_percentage: float = 0.04) -> ExitStrategy:
        """
        Create a default take-profit strategy
        
        Args:
            reward_percentage: Percentage reward for the take-profit
            
        Returns:
            A fixed take-profit strategy
        """
        return FixedTakeProfit(percentage=reward_percentage) 