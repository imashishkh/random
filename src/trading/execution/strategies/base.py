"""
Base class for algorithmic execution strategies.

This module defines the abstract base class for all execution strategies,
providing a common interface and shared functionality.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple, Callable
import time
import logging
import uuid
import threading
from datetime import datetime

# Configure logger
logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """Execution status enum for tracking strategy state."""
    INITIALIZED = "initialized"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"
    PAUSED = "paused"


class ExecutionMetrics:
    """Class for tracking execution quality metrics."""
    
    def __init__(self):
        """Initialize execution metrics."""
        self.start_time = None
        self.end_time = None
        self.expected_price = None
        self.avg_execution_price = None
        self.slippage = None
        self.market_impact = None
        self.fill_rate = 0.0
        self.total_quantity = 0.0
        self.executed_quantity = 0.0
        self.execution_time_ms = 0
        self.num_orders = 0
        self.num_fills = 0
        self.order_ids = []
        
    def calculate_fill_rate(self):
        """Calculate the current fill rate."""
        if self.total_quantity > 0:
            self.fill_rate = (self.executed_quantity / self.total_quantity) * 100
        return self.fill_rate
    
    def calculate_slippage(self, benchmark_price: float):
        """Calculate slippage against a benchmark price."""
        if not self.avg_execution_price or not benchmark_price:
            return None
        
        self.expected_price = benchmark_price
        self.slippage = (self.avg_execution_price - benchmark_price) / benchmark_price * 100
        return self.slippage
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "expected_price": self.expected_price,
            "avg_execution_price": self.avg_execution_price,
            "slippage": self.slippage,
            "market_impact": self.market_impact,
            "fill_rate": self.fill_rate,
            "total_quantity": self.total_quantity,
            "executed_quantity": self.executed_quantity,
            "execution_time_ms": self.execution_time_ms,
            "num_orders": self.num_orders,
            "num_fills": self.num_fills
        }


class ExecutionStrategy(ABC):
    """
    Abstract base class for all execution strategies.
    
    This class defines the interface that all execution strategies must implement,
    and provides common functionality for execution tracking and management.
    """
    
    def __init__(
        self,
        exchange_client: Any,
        order_manager: Any,
        params: Dict[str, Any] = None,
        callbacks: Dict[str, Callable] = None
    ):
        """
        Initialize the execution strategy.
        
        Args:
            exchange_client: The exchange client for market data and order execution
            order_manager: The order manager for tracking orders
            params: Strategy-specific parameters
            callbacks: Callback functions for various events
        """
        self.exchange_client = exchange_client
        self.order_manager = order_manager
        self.params = params or {}
        self.callbacks = callbacks or {}
        
        # Execution tracking
        self.execution_id = str(uuid.uuid4())
        self.status = ExecutionStatus.INITIALIZED
        self.metrics = ExecutionMetrics()
        self.active_orders = {}
        self.error = None
        
        # Locks for thread safety
        self._lock = threading.RLock()
        
        # Execution control
        self._stop_event = threading.Event()
        self._execution_thread = None
        
        logger.info(f"Initialized {self.__class__.__name__} strategy with ID {self.execution_id}")
    
    @abstractmethod
    def execute_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        **kwargs
    ) -> str:
        """
        Execute an order using this strategy.
        
        Args:
            symbol: Trading pair symbol
            side: Order side (BUY or SELL)
            quantity: Order quantity
            price: Limit price (if applicable)
            **kwargs: Additional parameters
            
        Returns:
            Execution ID
        """
        pass
    
    @abstractmethod
    def cancel(self) -> bool:
        """
        Cancel all active orders and stop the strategy.
        
        Returns:
            True if cancelled successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def update_parameters(self, new_params: Dict[str, Any]) -> None:
        """
        Update strategy parameters.
        
        Args:
            new_params: New parameters to update
        """
        pass
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current execution metrics.
        
        Returns:
            Dictionary of metrics
        """
        with self._lock:
            return self.metrics.to_dict()
    
    def get_status(self) -> ExecutionStatus:
        """
        Get current execution status.
        
        Returns:
            Current status enum
        """
        with self._lock:
            return self.status
    
    def _update_status(self, new_status: ExecutionStatus) -> None:
        """
        Update execution status and trigger callbacks.
        
        Args:
            new_status: New status to set
        """
        with self._lock:
            old_status = self.status
            self.status = new_status
            
            # Log status change
            logger.info(f"Execution {self.execution_id} status changed: {old_status.value} -> {new_status.value}")
            
            # Call status change callback if registered
            if "on_status_change" in self.callbacks:
                try:
                    self.callbacks["on_status_change"](self.execution_id, old_status, new_status)
                except Exception as e:
                    logger.error(f"Error in status change callback: {str(e)}")
    
    def _handle_order_update(self, order_update: Dict[str, Any]) -> None:
        """
        Handle order update from the exchange.
        
        Args:
            order_update: Order update data
        """
        with self._lock:
            # Update metrics based on order update
            self._update_metrics(order_update)
            
            # Check if execution is complete
            if self._is_execution_complete():
                self._update_status(ExecutionStatus.COMPLETED)
                
                # Call completion callback if registered
                if "on_complete" in self.callbacks:
                    try:
                        self.callbacks["on_complete"](self.execution_id, self.get_metrics())
                    except Exception as e:
                        logger.error(f"Error in completion callback: {str(e)}")
    
    def _update_metrics(self, order_update: Dict[str, Any]) -> None:
        """
        Update execution metrics based on order update.
        
        Args:
            order_update: Order update data
        """
        # This is a base implementation that should be extended by subclasses
        with self._lock:
            if "status" in order_update and order_update["status"] == "FILLED":
                self.metrics.num_fills += 1
                
                # Update executed quantity
                fill_qty = float(order_update.get("executedQty", 0))
                self.metrics.executed_quantity += fill_qty
                
                # Update average execution price
                if self.metrics.avg_execution_price is None:
                    self.metrics.avg_execution_price = float(order_update.get("price", 0))
                else:
                    # Weighted average
                    prev_qty = self.metrics.executed_quantity - fill_qty
                    prev_avg = self.metrics.avg_execution_price
                    fill_price = float(order_update.get("price", 0))
                    
                    if prev_qty + fill_qty > 0:
                        self.metrics.avg_execution_price = (
                            (prev_avg * prev_qty) + (fill_price * fill_qty)
                        ) / (prev_qty + fill_qty)
                
                # Update fill rate
                self.metrics.calculate_fill_rate()
    
    def _is_execution_complete(self) -> bool:
        """
        Check if execution is complete.
        
        Returns:
            True if complete, False otherwise
        """
        # Base implementation - override in subclasses for strategy-specific logic
        with self._lock:
            # Simple completion check - executed quantity matches total quantity
            return (self.metrics.executed_quantity >= self.metrics.total_quantity * 0.99 and 
                    self.metrics.total_quantity > 0)
    
    def _validate_market_conditions(self, symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Validate market conditions for safe execution.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Base implementation - override in subclasses for strategy-specific checks
        try:
            # Check if market is open/active
            # Check for extreme volatility
            # Check for sufficient liquidity
            return True, None
        except Exception as e:
            logger.error(f"Error validating market conditions: {str(e)}")
            return False, str(e)
    
    def _check_circuit_breakers(self, market_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Check if circuit breakers should activate.
        
        Args:
            market_data: Current market data
            
        Returns:
            Tuple of (should_break, reason)
        """
        # Base implementation - override in subclasses for strategy-specific circuit breakers
        return False, None
    
    def _log_execution_start(self, symbol: str, side: str, quantity: float, price: Optional[float] = None) -> None:
        """
        Log execution start with relevant details.
        
        Args:
            symbol: Trading pair symbol
            side: Order side
            quantity: Order quantity
            price: Order price (if applicable)
        """
        logger.info(
            f"Starting {self.__class__.__name__} execution {self.execution_id}: "
            f"{side} {quantity} {symbol}" + (f" @ {price}" if price else "")
        )
        
        # Set metrics start time
        self.metrics.start_time = datetime.now()
        self.metrics.total_quantity = quantity 