from typing import Dict, List, Optional
import time

from .base import ExitStrategy
from ..models import ExitOrder, Position, MarketData, OrderType


class FixedTakeProfit(ExitStrategy):
    """Simple fixed percentage or price take-profit"""
    
    def __init__(self, percentage: Optional[float] = None, price: Optional[float] = None):
        """
        Initialize with either a fixed percentage or absolute price
        
        Args:
            percentage: Take profit percentage (0.05 = 5%), applied to entry price
            price: Absolute take profit price
        """
        if percentage is None and price is None:
            raise ValueError("Either percentage or price must be provided")
            
        self.percentage = percentage
        self.fixed_price = price
        
    def calculate_exit_levels(self, position: Position, market_data: MarketData) -> List[float]:
        if self.fixed_price is not None:
            return [self.fixed_price]
            
        if position.side == "BUY":
            profit_price = position.entry_price * (1 + self.percentage)
        else:  # SELL position
            profit_price = position.entry_price * (1 - self.percentage)
            
        return [profit_price]
        
    def generate_exit_orders(self, position: Position, market_data: MarketData) -> List[ExitOrder]:
        profit_prices = self.calculate_exit_levels(position, market_data)
        
        orders = []
        for price in profit_prices:
            order = self._create_exit_order(
                position=position,
                price=price,
                quantity=position.quantity,  # Full position
                order_type=OrderType.TAKE_PROFIT
            )
            orders.append(order)
            
        return orders
        
    def update_exit_orders(self, position: Position, current_orders: List[ExitOrder], 
                          market_data: MarketData) -> List[ExitOrder]:
        # For fixed take-profit, no updates needed unless the fixed price changed
        if not current_orders or (self.fixed_price is not None and 
                                 self.fixed_price != current_orders[0].price):
            return self.generate_exit_orders(position, market_data)
        return current_orders


class TrailingTakeProfit(ExitStrategy):
    """Take-profit that trails price movements to lock in more profit"""
    
    def __init__(self, activation_percentage: float, trail_percentage: float):
        """
        Initialize trailing take-profit
        
        Args:
            activation_percentage: Price movement needed to activate (e.g., 0.05 = 5%)
            trail_percentage: Distance to maintain behind price (e.g., 0.02 = 2%)
        """
        self.activation_percentage = activation_percentage
        self.trail_percentage = trail_percentage
        self.highest_price = 0.0  # For long positions
        self.lowest_price = float('inf')  # For short positions
        self.is_activated = False
        
    def calculate_exit_levels(self, position: Position, market_data: MarketData) -> List[float]:
        current_price = market_data.last_price
        
        # Check if take-profit should be activated
        if not self.is_activated:
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
            # Initial take-profit level before activation
            if position.side == "BUY":
                return [position.entry_price * (1 + self.activation_percentage)]
            else:
                return [position.entry_price * (1 - self.activation_percentage)]
        
        # Update trailing levels
        if position.side == "BUY":
            self.highest_price = max(self.highest_price, current_price)
            take_profit_price = self.highest_price * (1 - self.trail_percentage)
        else:  # SELL position
            self.lowest_price = min(self.lowest_price, current_price)
            take_profit_price = self.lowest_price * (1 + self.trail_percentage)
            
        return [take_profit_price]
        
    def generate_exit_orders(self, position: Position, market_data: MarketData) -> List[ExitOrder]:
        profit_prices = self.calculate_exit_levels(position, market_data)
        
        orders = []
        for price in profit_prices:
            order = self._create_exit_order(
                position=position,
                price=price,
                quantity=position.quantity,
                order_type=OrderType.TAKE_PROFIT
            )
            orders.append(order)
            
        return orders
        
    def update_exit_orders(self, position: Position, current_orders: List[ExitOrder], 
                          market_data: MarketData) -> List[ExitOrder]:
        # Calculate new take-profit price
        new_profit_prices = self.calculate_exit_levels(position, market_data)
        
        if not current_orders:
            return self.generate_exit_orders(position, market_data)
            
        current_profit_price = current_orders[0].price
        new_profit_price = new_profit_prices[0]
        
        # Only update if the new take-profit price has moved significantly
        if position.side == "BUY" and abs(new_profit_price - current_profit_price) > 0.0001:
            return self.generate_exit_orders(position, market_data)
        elif position.side == "SELL" and abs(new_profit_price - current_profit_price) > 0.0001:
            return self.generate_exit_orders(position, market_data)
            
        return current_orders


class PartialExitStrategy(ExitStrategy):
    """Take profit strategy that exits position in stages at different price levels"""
    
    def __init__(self, levels: List[Dict[str, float]]):
        """
        Initialize with exit levels
        
        Args:
            levels: List of dicts with 'percentage' and 'quantity_percentage' 
                   Example: [{'percentage': 0.05, 'quantity_percentage': 0.3}, 
                             {'percentage': 0.1, 'quantity_percentage': 0.5}]
        """
        self.levels = sorted(levels, key=lambda x: x['percentage'])
        
        # Validate that quantity percentages sum to no more than 1.0
        total_qty = sum(level['quantity_percentage'] for level in self.levels)
        if total_qty > 1.0:
            raise ValueError(f"Sum of quantity percentages ({total_qty}) exceeds 1.0")
        
    def calculate_exit_levels(self, position: Position, market_data: MarketData) -> List[float]:
        prices = []
        
        for level in self.levels:
            percentage = level['percentage']
            
            if position.side == "BUY":
                price = position.entry_price * (1 + percentage)
            else:  # SELL position
                price = position.entry_price * (1 - percentage)
                
            prices.append(price)
            
        return prices
        
    def generate_exit_orders(self, position: Position, market_data: MarketData) -> List[ExitOrder]:
        prices = self.calculate_exit_levels(position, market_data)
        
        orders = []
        for i, price in enumerate(prices):
            # Calculate quantity for this level
            level_quantity = position.quantity * self.levels[i]['quantity_percentage']
            
            order = self._create_exit_order(
                position=position,
                price=price,
                quantity=level_quantity,
                order_type=OrderType.TAKE_PROFIT
            )
            orders.append(order)
            
        return orders
    
    def update_exit_orders(self, position: Position, current_orders: List[ExitOrder], 
                          market_data: MarketData) -> List[ExitOrder]:
        # For fixed take-profit levels, typically no updates needed
        if not current_orders or len(current_orders) != len(self.levels):
            return self.generate_exit_orders(position, market_data)
            
        # Check if any order quantities need updates due to partial fills
        needs_update = False
        for i, order in enumerate(current_orders):
            expected_qty = position.quantity * self.levels[i]['quantity_percentage']
            if abs(order.quantity - expected_qty) > 0.0001:
                needs_update = True
                break
                
        if needs_update:
            return self.generate_exit_orders(position, market_data)
            
        return current_orders


class ScaledExitStrategy(ExitStrategy):
    """Take profit strategy that scales out of position based on market conditions"""
    
    def __init__(self, base_percentage: float, scale_factor: float, 
                 levels: int = 3, max_percentage: Optional[float] = None):
        """
        Initialize with scaling parameters
        
        Args:
            base_percentage: Initial target percentage (e.g., 0.03 = 3%)
            scale_factor: Factor to multiply for each level (e.g., 2.0)
            levels: Number of exit levels (default: 3)
            max_percentage: Maximum target percentage (optional cap)
        """
        self.base_percentage = base_percentage
        self.scale_factor = scale_factor
        self.levels = levels
        self.max_percentage = max_percentage
        
    def calculate_exit_levels(self, position: Position, market_data: MarketData) -> List[float]:
        prices = []
        
        for i in range(self.levels):
            # Calculate percentage for this level with scaling
            percentage = self.base_percentage * (self.scale_factor ** i)
            
            # Cap at max_percentage if specified
            if self.max_percentage is not None:
                percentage = min(percentage, self.max_percentage)
                
            if position.side == "BUY":
                price = position.entry_price * (1 + percentage)
            else:  # SELL position
                price = position.entry_price * (1 - percentage)
                
            prices.append(price)
            
        return prices
        
    def generate_exit_orders(self, position: Position, market_data: MarketData) -> List[ExitOrder]:
        prices = self.calculate_exit_levels(position, market_data)
        
        # Calculate quantity per level (equal distribution)
        level_quantity = position.quantity / self.levels
        
        orders = []
        for price in prices:
            order = self._create_exit_order(
                position=position,
                price=price,
                quantity=level_quantity,
                order_type=OrderType.TAKE_PROFIT
            )
            orders.append(order)
            
        return orders
    
    def update_exit_orders(self, position: Position, current_orders: List[ExitOrder], 
                          market_data: MarketData) -> List[ExitOrder]:
        # For scaled exit, only need updates if level count changes
        if not current_orders or len(current_orders) != self.levels:
            return self.generate_exit_orders(position, market_data)
            
        # Check if any order quantities need updates due to partial fills
        needs_update = False
        level_quantity = position.quantity / self.levels
        
        for order in current_orders:
            if abs(order.quantity - level_quantity) > 0.0001:
                needs_update = True
                break
                
        if needs_update:
            return self.generate_exit_orders(position, market_data)
            
        return current_orders 