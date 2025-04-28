"""
Factory for creating execution strategy instances.

This module provides a factory for creating and configuring execution
strategy instances based on strategy type and parameters.
"""

import logging
from enum import Enum
from typing import Dict, Any, Optional, Type

from .execution.strategies.base import ExecutionStrategy
from .execution.strategies.twap import TWAPStrategy
from .execution.strategies.vwap import VWAPStrategy
from .execution.strategies.iceberg import IcebergStrategy

# Configure logger
logger = logging.getLogger(__name__)


class ExecutionStrategyType(Enum):
    """Enumeration of available execution strategy types."""
    TWAP = "twap"  # Time-Weighted Average Price
    VWAP = "vwap"  # Volume-Weighted Average Price
    ICEBERG = "iceberg"  # Iceberg Orders
    SIMPLE = "simple"  # Simple market/limit execution


class ExecutionStrategyFactory:
    """
    Factory for creating execution strategy instances.
    
    Provides a centralized way to create and configure different types of
    execution strategies with appropriate parameters and dependencies.
    """
    
    # Registry of strategy classes
    _strategy_classes: Dict[ExecutionStrategyType, Type[ExecutionStrategy]] = {
        ExecutionStrategyType.TWAP: TWAPStrategy,
        ExecutionStrategyType.VWAP: VWAPStrategy,
        ExecutionStrategyType.ICEBERG: IcebergStrategy,
        # Add more strategies as they are implemented
    }
    
    @classmethod
    def create_strategy(
        cls,
        strategy_type: ExecutionStrategyType,
        exchange_client: Any,
        order_manager: Any,
        params: Optional[Dict[str, Any]] = None,
        callbacks: Optional[Dict[str, Any]] = None
    ) -> ExecutionStrategy:
        """
        Create an execution strategy instance.
        
        Args:
            strategy_type: Type of execution strategy to create
            exchange_client: Exchange client for market data and order execution
            order_manager: Order manager for tracking orders
            params: Strategy-specific parameters
            callbacks: Callback functions for various events
            
        Returns:
            Configured execution strategy instance
            
        Raises:
            ValueError: If strategy type is not available
            NotImplementedError: If strategy is not fully implemented yet
        """
        if strategy_type not in cls._strategy_classes:
            raise ValueError(f"Unsupported execution strategy type: {strategy_type}")
        
        strategy_class = cls._strategy_classes[strategy_type]
        
        logger.info(f"Creating {strategy_type.value} execution strategy")
        
        # Create and return the strategy instance
        return strategy_class(
            exchange_client=exchange_client,
            order_manager=order_manager,
            params=params,
            callbacks=callbacks
        )
    
    @classmethod
    def register_strategy(
        cls,
        strategy_type: ExecutionStrategyType,
        strategy_class: Type[ExecutionStrategy]
    ) -> None:
        """
        Register a new strategy class.
        
        Args:
            strategy_type: Type of execution strategy
            strategy_class: Strategy class to register
            
        Raises:
            TypeError: If strategy_class is not a subclass of ExecutionStrategy
        """
        if not issubclass(strategy_class, ExecutionStrategy):
            raise TypeError(f"Strategy class must be a subclass of ExecutionStrategy")
        
        cls._strategy_classes[strategy_type] = strategy_class
        logger.info(f"Registered {strategy_type.value} execution strategy")
    
    @classmethod
    def get_available_strategies(cls) -> Dict[ExecutionStrategyType, str]:
        """
        Get dictionary of available strategies and their descriptions.
        
        Returns:
            Dictionary mapping strategy types to descriptions
        """
        return {
            ExecutionStrategyType.TWAP: "Time-Weighted Average Price",
            ExecutionStrategyType.VWAP: "Volume-Weighted Average Price",
            ExecutionStrategyType.ICEBERG: "Iceberg Orders",
            ExecutionStrategyType.SIMPLE: "Simple Execution"
        } 