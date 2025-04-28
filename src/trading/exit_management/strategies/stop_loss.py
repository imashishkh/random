from typing import Dict, List, Optional
import time

from .base import ExitStrategy
from ..models import ExitOrder, Position, MarketData, OrderType


class FixedStopLoss(ExitStrategy):
    """Simple fixed percentage or price stop-loss"""
    
    def __init__(self, percentage: Optional[float] = None, price: Optional[float] = None):
        """
        Initialize with either a fixed percentage or absolute price
        
        Args:
            percentage: Stop loss percentage (0.05 = 5%), applied to entry price
            price: Absolute stop loss price
        """
        if percentage is None and price is None:
            raise ValueError("Either percentage or price must be provided")
            
        self.percentage = percentage
        self.fixed_price = price
        
    def calculate_exit_levels(self, position: Position, market_data: MarketData) -> List[float]:
        if self.fixed_price is not None:
            return [self.fixed_price]
            
        if position.side == "BUY":
            stop_price = position.entry_price * (1 - self.percentage)
        else:  # SELL position
            stop_price = position.entry_price * (1 + self.percentage)
            
        return [stop_price]
        
    def generate_exit_orders(self, position: Position, market_data: MarketData) -> List[ExitOrder]:
        stop_prices = self.calculate_exit_levels(position, market_data)
        
        orders = []
        for price in stop_prices:
            # Create a stop loss order
            order = self._create_exit_order(
                position=position,
                price=price,
                quantity=position.quantity,  # Full position
                order_type=OrderType.STOP
            )
            orders.append(order)
            
        return orders
        
    def update_exit_orders(self, position: Position, current_orders: List[ExitOrder], 
                          market_data: MarketData) -> List[ExitOrder]:
        # For fixed stop-loss, no updates needed unless the fixed price changed
        if not current_orders or (self.fixed_price is not None and 
                                 self.fixed_price != current_orders[0].price):
            return self.generate_exit_orders(position, market_data)
        return current_orders


class TrailingStopLoss(ExitStrategy):
    """Stop-loss that trails price movements at a defined distance"""
    
    def __init__(self, trail_percentage: float, activation_percentage: Optional[float] = None):
        """
        Initialize trailing stop loss
        
        Args:
            trail_percentage: Distance to maintain behind price (0.05 = 5%)
            activation_percentage: Price movement needed to activate trailing (optional)
        """
        self.trail_percentage = trail_percentage
        self.activation_percentage = activation_percentage
        self.highest_price = 0.0  # For long positions
        self.lowest_price = float('inf')  # For short positions
        self.is_activated = activation_percentage is None  # Activate immediately if no activation % given
        
    def calculate_exit_levels(self, position: Position, market_data: MarketData) -> List[float]:
        current_price = market_data.last_price
        
        if not self.is_activated:
            # Check if trailing stop should be activated
            if position.side == "BUY":
                activation_price = position.entry_price * (1 + self.activation_percentage)
                if current_price >= activation_price:
                    self.is_activated = True
                    self.highest_price = current_price
            else:  # SELL position
                activation_price = position.entry_price * (1 - self.activation_percentage)
                if current_price <= activation_price:
                    self.is_activated = True
                    self.lowest_price = current_price
        
        if not self.is_activated:
            # Return initial stop based on entry price if not activated
            if position.side == "BUY":
                return [position.entry_price * (1 - self.trail_percentage)]
            else:
                return [position.entry_price * (1 + self.trail_percentage)]
        
        # Update highest/lowest seen prices
        if position.side == "BUY":
            self.highest_price = max(self.highest_price, current_price)
            stop_price = self.highest_price * (1 - self.trail_percentage)
        else:  # SELL position
            self.lowest_price = min(self.lowest_price, current_price)
            stop_price = self.lowest_price * (1 + self.trail_percentage)
            
        return [stop_price]
        
    def generate_exit_orders(self, position: Position, market_data: MarketData) -> List[ExitOrder]:
        stop_prices = self.calculate_exit_levels(position, market_data)
        
        orders = []
        for price in stop_prices:
            order = self._create_exit_order(
                position=position,
                price=price,
                quantity=position.quantity,
                order_type=OrderType.STOP
            )
            orders.append(order)
            
        return orders
        
    def update_exit_orders(self, position: Position, current_orders: List[ExitOrder], 
                          market_data: MarketData) -> List[ExitOrder]:
        # Calculate new stop price
        new_stop_prices = self.calculate_exit_levels(position, market_data)
        
        if not current_orders:
            return self.generate_exit_orders(position, market_data)
            
        current_stop_price = current_orders[0].price
        new_stop_price = new_stop_prices[0]
        
        # Only update if the new stop price is more favorable
        if position.side == "BUY" and new_stop_price > current_stop_price:
            return self.generate_exit_orders(position, market_data)
        elif position.side == "SELL" and new_stop_price < current_stop_price:
            return self.generate_exit_orders(position, market_data)
            
        return current_orders


class AtrStopLoss(ExitStrategy):
    """Volatility-based stop-loss using Average True Range (ATR)"""
    
    def __init__(self, atr_multiplier: float = 2.0, period: int = 14):
        """
        Initialize ATR-based stop loss
        
        Args:
            atr_multiplier: Multiplier applied to ATR value (default: 2.0)
            period: ATR calculation period (default: 14)
        """
        self.atr_multiplier = atr_multiplier
        self.period = period
        
    def calculate_exit_levels(self, position: Position, market_data: MarketData) -> List[float]:
        # Get ATR value from market data
        atr = market_data.atr
        
        if atr is None:
            # Fallback to a fixed percentage if ATR is not available
            if position.side == "BUY":
                return [position.entry_price * 0.95]  # 5% stop loss
            else:
                return [position.entry_price * 1.05]  # 5% stop loss
        
        current_price = market_data.last_price
        
        # Calculate stop distance based on ATR
        stop_distance = atr * self.atr_multiplier
        
        if position.side == "BUY":
            stop_price = current_price - stop_distance
        else:  # SELL position
            stop_price = current_price + stop_distance
            
        return [stop_price]
        
    def generate_exit_orders(self, position: Position, market_data: MarketData) -> List[ExitOrder]:
        stop_prices = self.calculate_exit_levels(position, market_data)
        
        orders = []
        for price in stop_prices:
            order = self._create_exit_order(
                position=position,
                price=price,
                quantity=position.quantity,
                order_type=OrderType.STOP
            )
            orders.append(order)
            
        return orders
        
    def update_exit_orders(self, position: Position, current_orders: List[ExitOrder], 
                          market_data: MarketData) -> List[ExitOrder]:
        # Always recalculate ATR-based stops as volatility changes
        return self.generate_exit_orders(position, market_data)


class TimeBasedStopLoss(ExitStrategy):
    """Time-based stop-loss that exits a position after a specified duration"""
    
    def __init__(self, max_duration_seconds: int, price_buffer_percentage: float = 0.005):
        """
        Initialize time-based stop loss
        
        Args:
            max_duration_seconds: Maximum time to hold position in seconds
            price_buffer_percentage: Buffer for market order execution (0.5% default)
        """
        self.max_duration_seconds = max_duration_seconds
        self.price_buffer_percentage = price_buffer_percentage
        
    def calculate_exit_levels(self, position: Position, market_data: MarketData) -> List[float]:
        # Check if maximum duration is exceeded
        current_time = int(time.time())
        time_elapsed = current_time - position.open_time
        
        if time_elapsed >= self.max_duration_seconds:
            # Time to exit - use current price with a buffer
            current_price = market_data.last_price
            if position.side == "BUY":
                # For long positions, set slightly below market to ensure execution
                return [current_price * (1 - self.price_buffer_percentage)]
            else:
                # For short positions, set slightly above market
                return [current_price * (1 + self.price_buffer_percentage)]
        
        # No exit yet, return empty list
        return []
        
    def generate_exit_orders(self, position: Position, market_data: MarketData) -> List[ExitOrder]:
        exit_prices = self.calculate_exit_levels(position, market_data)
        
        if not exit_prices:
            # No exit needed yet
            return []
            
        orders = []
        for price in exit_prices:
            # Use market order for time-based exits
            order = self._create_exit_order(
                position=position,
                price=price,
                quantity=position.quantity,
                order_type=OrderType.MARKET  # Use market order for immediate execution
            )
            orders.append(order)
            
        return orders
        
    def update_exit_orders(self, position: Position, current_orders: List[ExitOrder], 
                          market_data: MarketData) -> List[ExitOrder]:
        # For time-based, just check if it's time to exit
        exit_orders = self.generate_exit_orders(position, market_data)
        
        if exit_orders:
            # Time to exit, return new orders
            return exit_orders
            
        # No time-based exit needed yet
        return current_orders 