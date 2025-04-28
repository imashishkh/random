"""
Usage examples for execution strategies.

This module provides examples of how to use the execution strategies
to optimize trade execution and minimize market impact.
"""

import logging
from typing import Dict, Any

from .execution.strategies import (
    ExecutionStrategyFactory,
    ExecutionStrategyType,
    ExecutionStatus
)

# Configure logger
logger = logging.getLogger(__name__)


def twap_example(exchange_client, order_manager):
    """
    Example of using TWAP strategy for order execution.
    
    Args:
        exchange_client: Exchange client
        order_manager: Order manager
    """
    # Create TWAP strategy with custom parameters
    twap_params = {
        "time_window_minutes": 60,    # Execute over 60 minutes
        "num_slices": 20,             # Split into 20 slices
        "slice_randomization_percent": 10,  # 10% randomization
        "adaptive_intervals": True,   # Adapt to market conditions
        "catch_up_enabled": True,     # Enable catch-up logic for missed slices
        "price_band_percent": 0.5,    # 0.5% price tolerance band
    }
    
    # Create callback functions
    callbacks = {
        "on_status_change": on_status_change_callback,
        "on_complete": on_completion_callback,
    }
    
    # Create strategy using factory
    strategy = ExecutionStrategyFactory.create_strategy(
        strategy_type=ExecutionStrategyType.TWAP,
        exchange_client=exchange_client,
        order_manager=order_manager,
        params=twap_params,
        callbacks=callbacks
    )
    
    # Execute a large order
    execution_id = strategy.execute_order(
        symbol="BTCUSDT",
        side="BUY",
        quantity=2.5,  # 2.5 BTC
        price=None     # Market order
    )
    
    logger.info(f"Started TWAP execution with ID: {execution_id}")
    
    # In a real application, you would now wait for callbacks
    # or periodically check the status and metrics
    
    # Example of getting execution metrics
    metrics = strategy.get_metrics()
    logger.info(f"Current metrics: {metrics}")
    
    # Example of updating parameters mid-execution
    new_params = {
        "num_slices": 15,  # Reduce number of slices
        "slice_randomization_percent": 15,  # Increase randomization
    }
    strategy.update_parameters(new_params)
    
    # Example of checking status
    status = strategy.get_status()
    logger.info(f"Current status: {status.value}")
    
    # Example of cancelling execution
    if status != ExecutionStatus.COMPLETED:
        result = strategy.cancel()
        logger.info(f"Cancelled execution: {result}")


def on_status_change_callback(execution_id, old_status, new_status):
    """
    Callback for status changes.
    
    Args:
        execution_id: Execution ID
        old_status: Old status
        new_status: New status
    """
    logger.info(f"Execution {execution_id} status changed: {old_status.value} -> {new_status.value}")


def on_completion_callback(execution_id, metrics):
    """
    Callback for execution completion.
    
    Args:
        execution_id: Execution ID
        metrics: Execution metrics
    """
    logger.info(f"Execution {execution_id} completed!")
    logger.info(f"Metrics: {metrics}")
    
    # Example of analyzing execution performance
    if metrics["slippage"] is not None:
        if metrics["slippage"] > 0.1:
            logger.warning(f"High slippage: {metrics['slippage']:.2f}%")
        else:
            logger.info(f"Good execution: {metrics['slippage']:.2f}% slippage")
            
    # Example of logging execution time
    execution_time_seconds = metrics["execution_time_ms"] / 1000
    logger.info(f"Execution took {execution_time_seconds:.2f} seconds")


def vwap_example(exchange_client, order_manager):
    """
    Example of using VWAP strategy for order execution.
    
    Args:
        exchange_client: Exchange client
        order_manager: Order manager
    """
    # Create VWAP strategy with custom parameters
    vwap_params = {
        "time_window_minutes": 120,    # Execute over 2 hours
        "participation_rate": 15,      # 15% of market volume
        "volume_prediction_method": "historical",
        "anomaly_detection_enabled": True,
    }
    
    # Not yet implemented
    logger.info("VWAP strategy example - not yet implemented")


def iceberg_example(exchange_client, order_manager):
    """
    Example of using Iceberg strategy for order execution.
    
    Args:
        exchange_client: Exchange client
        order_manager: Order manager
    """
    # Create Iceberg strategy with custom parameters
    iceberg_params = {
        "initial_tip_percent": 8,     # 8% initial tip size
        "tip_randomization": True,    # Randomize tip size
        "randomization_range": 25,    # 25% randomization range
        "dynamic_tip_sizing": True,   # Dynamically adjust tip size
    }
    
    # Not yet implemented
    logger.info("Iceberg strategy example - not yet implemented") 