"""
Base module for the high-performance order execution system.
Defines the core interfaces and abstract classes for the execution system components.
"""
import abc
import enum
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, Union

# Configure logger
logger = logging.getLogger(__name__)

class OrderStatus(enum.Enum):
    """Enum representing possible order statuses."""
    CREATED = "created"
    VALIDATED = "validated"
    ROUTING = "routing"
    REJECTED = "rejected"
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    ERROR = "error"

class OrderType(enum.Enum):
    """Enum representing order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TWAP = "twap"
    VWAP = "vwap"
    ICEBERG = "iceberg"

class OrderSide(enum.Enum):
    """Enum representing order sides."""
    BUY = "buy"
    SELL = "sell"

class Order:
    """Class representing an order in the system."""
    
    def __init__(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        client_order_id: Optional[str] = None,
        exchange: Optional[str] = None,
        strategy_id: Optional[str] = None,
        algo_params: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize a new order.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            order_type: Type of order
            side: Order side (buy/sell)
            quantity: Order quantity
            price: Order price (for limit orders)
            stop_price: Stop price (for stop orders)
            client_order_id: Client-assigned order ID
            exchange: Target exchange
            strategy_id: ID of the strategy that generated this order
            algo_params: Additional parameters for algorithmic orders
        """
        self.symbol = symbol
        self.order_type = order_type
        self.side = side
        self.quantity = quantity
        self.price = price
        self.stop_price = stop_price
        self.client_order_id = client_order_id or str(uuid.uuid4())
        self.exchange = exchange
        self.strategy_id = strategy_id
        self.algo_params = algo_params or {}
        
        # Automatically populated fields
        self.exchange_order_id = None
        self.status = OrderStatus.CREATED
        self.created_at = datetime.utcnow()
        self.updated_at = self.created_at
        self.executed_quantity = 0.0
        self.average_price = 0.0
        self.fills = []
        self.error = None
        self.metadata = {}
        
    def update_status(self, status: OrderStatus) -> None:
        """
        Update the order status.
        
        Args:
            status: New order status
        """
        self.status = status
        self.updated_at = datetime.utcnow()
        logger.info(f"Order {self.client_order_id} status updated to {status.value}")
    
    def add_fill(self, quantity: float, price: float, timestamp: datetime) -> None:
        """
        Add a fill to the order.
        
        Args:
            quantity: Filled quantity
            price: Fill price
            timestamp: Fill timestamp
        """
        self.fills.append({
            "quantity": quantity,
            "price": price,
            "timestamp": timestamp
        })
        
        self.executed_quantity += quantity
        
        # Recalculate average price
        total_value = sum(fill["quantity"] * fill["price"] for fill in self.fills)
        self.average_price = total_value / self.executed_quantity if self.executed_quantity > 0 else 0
        
        # Update status
        if abs(self.executed_quantity - self.quantity) < 1e-8:
            self.update_status(OrderStatus.FILLED)
        elif self.executed_quantity > 0:
            self.update_status(OrderStatus.PARTIALLY_FILLED)
            
        logger.info(f"Order {self.client_order_id} fill added: {quantity} @ {price}")
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the order to a dictionary.
        
        Returns:
            Dictionary representation of the order
        """
        return {
            "client_order_id": self.client_order_id,
            "exchange_order_id": self.exchange_order_id,
            "symbol": self.symbol,
            "order_type": self.order_type.value,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "stop_price": self.stop_price,
            "exchange": self.exchange,
            "strategy_id": self.strategy_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "executed_quantity": self.executed_quantity,
            "average_price": self.average_price,
            "fills": self.fills,
            "error": self.error,
            "algo_params": self.algo_params,
            "metadata": self.metadata
        }

class BaseOrderExecutionSystem(abc.ABC):
    """Abstract base class for the order execution system."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the base order execution system.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        logger.info("Initializing order execution system")
        
    @abc.abstractmethod
    async def submit_order(self, order: Order) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Submit an order to the execution system.
        
        Args:
            order: Order to submit
            
        Returns:
            Tuple of (success, error_message, order_details)
        """
        pass
    
    @abc.abstractmethod
    async def cancel_order(self, client_order_id: str) -> Tuple[bool, Optional[str]]:
        """
        Cancel an order.
        
        Args:
            client_order_id: Client order ID to cancel
            
        Returns:
            Tuple of (success, error_message)
        """
        pass
    
    @abc.abstractmethod
    async def get_order_status(self, client_order_id: str) -> Tuple[bool, Optional[OrderStatus], Optional[Dict[str, Any]]]:
        """
        Get the status of an order.
        
        Args:
            client_order_id: Client order ID to check
            
        Returns:
            Tuple of (success, status, order_details)
        """
        pass
    
    @abc.abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all open orders.
        
        Args:
            symbol: Optional symbol to filter by
            
        Returns:
            List of open orders
        """
        pass 