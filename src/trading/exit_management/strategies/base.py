from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import time
import uuid

from ..models import ExitOrder, Position, MarketData, OrderType, OrderStatus


class ExitStrategy(ABC):
    """
    Abstract base class for all exit strategies (stop-loss and take-profit).
    """
    
    @abstractmethod
    def calculate_exit_levels(self, position: Position, market_data: MarketData) -> List[float]:
        """
        Calculate exit price levels based on position and market data.
        
        Args:
            position: The trading position
            market_data: Current market data including price and indicators
            
        Returns:
            List of price levels where exits should be triggered
        """
        pass
        
    @abstractmethod
    def generate_exit_orders(self, position: Position, market_data: MarketData) -> List[ExitOrder]:
        """
        Generate exit orders based on the strategy.
        
        Args:
            position: The trading position
            market_data: Current market data
            
        Returns:
            List of exit orders to be placed
        """
        pass
        
    @abstractmethod
    def update_exit_orders(self, position: Position, current_orders: List[ExitOrder], 
                          market_data: MarketData) -> List[ExitOrder]:
        """
        Update existing exit orders based on new market data.
        
        Args:
            position: The trading position
            current_orders: Currently active exit orders for this position
            market_data: Current market data
            
        Returns:
            Updated list of exit orders (may be the same if no changes needed)
        """
        pass
    
    def _create_exit_order(self, position: Position, price: float, quantity: float, 
                          order_type: OrderType) -> ExitOrder:
        """
        Helper method to create an exit order.
        
        Args:
            position: The trading position
            price: Order price
            quantity: Order quantity
            order_type: Type of order
            
        Returns:
            A new ExitOrder instance
        """
        current_time = int(time.time())
        
        return ExitOrder(
            order_id="",  # Will be filled by exchange
            position_id=position.position_id,
            price=price,
            quantity=quantity,
            type=order_type,
            status=OrderStatus.PENDING.value,
            created_time=current_time,
            updated_time=current_time
        ) 