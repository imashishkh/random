"""
Implementations of common order validators.
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, time

from .execution.core.base import Order, OrderType, OrderSide
from .execution.validation.base import BaseValidator, ValidationResult

# Configure logger
logger = logging.getLogger(__name__)

class SymbolValidator(BaseValidator):
    """Validates that the order symbol is valid."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the validator.
        
        Args:
            config: Optional configuration with valid_symbols list
        """
        super().__init__("SymbolValidator", config)
        self.valid_symbols = self.config.get("valid_symbols", [])
        
    def validate(self, order: Order, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Validate that the order's symbol is in the list of valid symbols.
        
        Args:
            order: Order to validate
            context: Optional context with available_symbols
            
        Returns:
            ValidationResult
        """
        context = context or {}
        available_symbols = context.get("available_symbols", self.valid_symbols)
        
        if not available_symbols:
            # If no symbols are available, we can't validate
            return self._create_result(True)
        
        if order.symbol not in available_symbols:
            return self._create_result(
                False,
                f"Invalid symbol: {order.symbol}",
                {"valid_symbols": available_symbols}
            )
        
        return self._create_result(True)

class PriceValidator(BaseValidator):
    """Validates order price is appropriate for the order type."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the validator.
        
        Args:
            config: Optional configuration
        """
        super().__init__("PriceValidator", config)
        
    def validate(self, order: Order, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Validate that the order has appropriate price values for its type.
        
        Args:
            order: Order to validate
            context: Optional context
            
        Returns:
            ValidationResult
        """
        # Market orders don't require a price
        if order.order_type == OrderType.MARKET:
            return self._create_result(True)
        
        # Limit orders require a price
        if order.order_type == OrderType.LIMIT and order.price is None:
            return self._create_result(
                False,
                "Limit orders require a price",
                {"order_type": order.order_type.value}
            )
        
        # Stop orders require a stop price
        if order.order_type == OrderType.STOP and order.stop_price is None:
            return self._create_result(
                False,
                "Stop orders require a stop price",
                {"order_type": order.order_type.value}
            )
        
        # Stop-limit orders require both a price and a stop price
        if order.order_type == OrderType.STOP_LIMIT and (order.price is None or order.stop_price is None):
            return self._create_result(
                False,
                "Stop-limit orders require both a price and a stop price",
                {"order_type": order.order_type.value}
            )
        
        # TWAP and VWAP orders require a price or use the market price
        if order.order_type in [OrderType.TWAP, OrderType.VWAP] and not order.algo_params:
            return self._create_result(
                False,
                f"{order.order_type.value.upper()} orders require algorithm parameters",
                {"order_type": order.order_type.value}
            )
        
        # Iceberg orders require a price and display quantity
        if order.order_type == OrderType.ICEBERG:
            if order.price is None:
                return self._create_result(
                    False,
                    "Iceberg orders require a price",
                    {"order_type": order.order_type.value}
                )
            
            if "display_quantity" not in order.algo_params:
                return self._create_result(
                    False,
                    "Iceberg orders require a display quantity",
                    {"order_type": order.order_type.value}
                )
        
        # Price must be positive
        if order.price is not None and order.price <= 0:
            return self._create_result(
                False,
                "Price must be positive",
                {"price": order.price}
            )
        
        # Stop price must be positive
        if order.stop_price is not None and order.stop_price <= 0:
            return self._create_result(
                False,
                "Stop price must be positive",
                {"stop_price": order.stop_price}
            )
        
        return self._create_result(True)

class QuantityValidator(BaseValidator):
    """Validates that the order quantity is valid."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the validator.
        
        Args:
            config: Optional configuration with min_quantity and max_quantity
        """
        super().__init__("QuantityValidator", config)
        self.min_quantity = self.config.get("min_quantity", 0.0001)
        self.max_quantity = self.config.get("max_quantity", 1000000)
        
    def validate(self, order: Order, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Validate that the order's quantity is within acceptable limits.
        
        Args:
            order: Order to validate
            context: Optional context with symbol_limits
            
        Returns:
            ValidationResult
        """
        context = context or {}
        
        # Get symbol-specific limits if available
        symbol_limits = context.get("symbol_limits", {}).get(order.symbol, {})
        min_quantity = symbol_limits.get("min_quantity", self.min_quantity)
        max_quantity = symbol_limits.get("max_quantity", self.max_quantity)
        
        # Quantity must be positive
        if order.quantity <= 0:
            return self._create_result(
                False,
                "Quantity must be positive",
                {"quantity": order.quantity}
            )
        
        # Check minimum quantity
        if order.quantity < min_quantity:
            return self._create_result(
                False,
                f"Quantity {order.quantity} is below minimum {min_quantity}",
                {"quantity": order.quantity, "min_quantity": min_quantity}
            )
        
        # Check maximum quantity
        if order.quantity > max_quantity:
            return self._create_result(
                False,
                f"Quantity {order.quantity} exceeds maximum {max_quantity}",
                {"quantity": order.quantity, "max_quantity": max_quantity}
            )
        
        # For iceberg orders, check that display quantity is less than total quantity
        if order.order_type == OrderType.ICEBERG:
            display_quantity = order.algo_params.get("display_quantity", 0)
            
            if display_quantity <= 0:
                return self._create_result(
                    False,
                    "Display quantity must be positive",
                    {"display_quantity": display_quantity}
                )
            
            if display_quantity > order.quantity:
                return self._create_result(
                    False,
                    "Display quantity cannot exceed total quantity",
                    {"display_quantity": display_quantity, "total_quantity": order.quantity}
                )
        
        return self._create_result(True)

class MarketHoursValidator(BaseValidator):
    """Validates that the order is being placed during market hours."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the validator.
        
        Args:
            config: Optional configuration with market_hours
        """
        super().__init__("MarketHoursValidator", config)
        
        # Default market hours (UTC): 24/7 for crypto markets
        self.market_hours = self.config.get("market_hours", {})
        
        # Default is to allow 24/7 trading if not specified
        if not self.market_hours:
            self.market_hours = {
                day: {"start": time(0, 0), "end": time(23, 59, 59)}
                for day in range(7)  # 0 = Monday, 6 = Sunday
            }
        
    def validate(self, order: Order, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Validate that the order is being placed during market hours.
        
        Args:
            order: Order to validate
            context: Optional context with current_time
            
        Returns:
            ValidationResult
        """
        context = context or {}
        
        # Get the current time, or use the provided time
        current_time = context.get("current_time", datetime.utcnow())
        
        # Get symbol-specific market hours if available
        symbol_market_hours = context.get("symbol_market_hours", {}).get(
            order.symbol, self.market_hours
        )
        
        # If no market hours are defined for this symbol, assume 24/7 trading
        if not symbol_market_hours:
            return self._create_result(True)
        
        # Get the current day of the week (0 = Monday, 6 = Sunday)
        current_day = current_time.weekday()
        
        # Get the market hours for the current day
        day_hours = symbol_market_hours.get(current_day)
        
        # If no hours are defined for this day, the market is closed
        if not day_hours:
            return self._create_result(
                False,
                f"Market is closed for {order.symbol} on {current_time.strftime('%A')}",
                {"current_day": current_day, "current_time": current_time.isoformat()}
            )
        
        # Get the start and end times
        start_time = day_hours.get("start")
        end_time = day_hours.get("end")
        
        # If start or end time is not defined, assume market is open
        if not start_time or not end_time:
            return self._create_result(True)
        
        # Convert current_time to time object for comparison
        current_time_obj = current_time.time()
        
        # Check if current time is within market hours
        if start_time <= end_time:
            # Simple case: start time is before end time
            if current_time_obj < start_time or current_time_obj > end_time:
                return self._create_result(
                    False,
                    f"Market for {order.symbol} is closed at {current_time.strftime('%H:%M:%S')}",
                    {
                        "current_time": current_time.isoformat(),
                        "market_hours": {
                            "start": start_time.strftime("%H:%M:%S"),
                            "end": end_time.strftime("%H:%M:%S")
                        }
                    }
                )
        else:
            # Complex case: market spans midnight (e.g., 22:00 - 04:00)
            if current_time_obj < start_time and current_time_obj > end_time:
                return self._create_result(
                    False,
                    f"Market for {order.symbol} is closed at {current_time.strftime('%H:%M:%S')}",
                    {
                        "current_time": current_time.isoformat(),
                        "market_hours": {
                            "start": start_time.strftime("%H:%M:%S"),
                            "end": end_time.strftime("%H:%M:%S")
                        }
                    }
                )
        
        return self._create_result(True)

# Export the validators
__all__ = [
    "SymbolValidator",
    "PriceValidator",
    "QuantityValidator",
    "MarketHoursValidator"
] 