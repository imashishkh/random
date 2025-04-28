"""
Order models and enumerations.

This module defines the data structures and types used for order management.
"""

from enum import Enum, auto
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
import json


class OrderType(Enum):
    """Available order types."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TWAP = "TWAP"  # Time-Weighted Average Price
    ICEBERG = "ICEBERG"  # Iceberg/Hidden orders


class OrderSide(Enum):
    """Order side: buy or sell."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Possible order statuses."""
    NEW = "NEW"  # Order accepted but not yet processed
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Order partially filled
    FILLED = "FILLED"  # Order fully filled
    CANCELED = "CANCELED"  # Order canceled
    REJECTED = "REJECTED"  # Order rejected by exchange
    EXPIRED = "EXPIRED"  # Order expired according to TIF
    PENDING = "PENDING"  # Order pending submission to exchange
    SUBMITTED = "SUBMITTED"  # Order submitted to exchange but not yet confirmed


class TimeInForce(Enum):
    """Time-in-force options."""
    GTC = "GTC"  # Good Till Canceled
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill
    GTD = "GTD"  # Good Till Date


class Order:
    """
    Represents a trading order.
    
    Attributes:
        order_id: Unique ID for the order
        client_order_id: Optional client-side order ID
        symbol: Trading pair/symbol
        side: Buy or sell
        order_type: Type of order (market, limit, etc.)
        quantity: Order quantity
        price: Limit price (for limit orders)
        stop_price: Stop price (for stop orders)
        time_in_force: How long the order will remain active
        status: Current status of the order
        account_id: Account identifier
        strategy_id: Strategy that generated this order
        created_at: When the order was created
        updated_at: When the order was last updated
        submitted_at: When the order was submitted to the exchange
        filled_at: When the order was filled (if applicable)
        exchange_order_id: ID assigned by the exchange (after submission)
        average_fill_price: Average fill price (for partial/full fills)
        filled_quantity: How much of the order has been filled
        remaining_quantity: How much of the order remains to be filled
        fee: Fee charged for the order
        fee_asset: Asset in which the fee was charged
        parent_order_id: ID of parent order (if applicable)
        venue: Exchange/venue where order was placed
        source: Source of the order (strategy, manual, etc.)
        metadata: Additional order metadata
    """
    
    def __init__(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        status: OrderStatus = OrderStatus.NEW,
        account_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        submitted_at: Optional[datetime] = None,
        filled_at: Optional[datetime] = None,
        exchange_order_id: Optional[str] = None,
        average_fill_price: Optional[float] = None,
        filled_quantity: float = 0.0,
        fee: Optional[float] = None,
        fee_asset: Optional[str] = None,
        parent_order_id: Optional[str] = None,
        venue: Optional[str] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize an order.
        
        Args:
            symbol: Trading pair/symbol
            side: Buy or sell
            quantity: Order quantity
            order_type: Type of order (market, limit, etc.)
            order_id: Unique ID for the order
            client_order_id: Optional client-side order ID
            price: Limit price (for limit orders)
            stop_price: Stop price (for stop orders)
            time_in_force: How long the order will remain active
            status: Current status of the order
            account_id: Account identifier
            strategy_id: Strategy that generated this order
            created_at: When the order was created
            updated_at: When the order was last updated
            submitted_at: When the order was submitted to the exchange
            filled_at: When the order was filled (if applicable)
            exchange_order_id: ID assigned by the exchange (after submission)
            average_fill_price: Average fill price (for partial/full fills)
            filled_quantity: How much of the order has been filled
            fee: Fee charged for the order
            fee_asset: Asset in which the fee was charged
            parent_order_id: ID of parent order (if applicable)
            venue: Exchange/venue where order was placed
            source: Source of the order (strategy, manual, etc.)
            metadata: Additional order metadata
        """
        # Required fields
        self.symbol = symbol
        self.side = side if isinstance(side, OrderSide) else OrderSide(side)
        self.quantity = quantity
        self.order_type = order_type if isinstance(order_type, OrderType) else OrderType(order_type)
        
        # Optional fields with defaults
        self.order_id = order_id if order_id else str(uuid.uuid4())
        self.client_order_id = client_order_id
        self.price = price
        self.stop_price = stop_price
        self.time_in_force = time_in_force if isinstance(time_in_force, TimeInForce) else TimeInForce(time_in_force)
        self.status = status if isinstance(status, OrderStatus) else OrderStatus(status)
        self.account_id = account_id
        self.strategy_id = strategy_id
        
        # Timestamps
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or self.created_at
        self.submitted_at = submitted_at
        self.filled_at = filled_at
        
        # Exchange info
        self.exchange_order_id = exchange_order_id
        self.average_fill_price = average_fill_price
        self.filled_quantity = filled_quantity
        self.remaining_quantity = quantity - filled_quantity
        self.fee = fee
        self.fee_asset = fee_asset
        
        # Relational info
        self.parent_order_id = parent_order_id
        self.venue = venue
        self.source = source
        
        # Additional data
        self.metadata = metadata or {}
        
        # Validation
        self._validate()
        
    def _validate(self) -> None:
        """Validate order parameters."""
        # Ensure required fields are present
        if not self.symbol:
            raise ValueError("Symbol is required")
        
        if not self.quantity or self.quantity <= 0:
            raise ValueError("Quantity must be positive")
        
        # Type-specific validation
        if self.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] and self.price is None:
            raise ValueError(f"{self.order_type.value} orders require a price")
        
        if self.order_type in [OrderType.STOP, OrderType.STOP_LIMIT] and self.stop_price is None:
            raise ValueError(f"{self.order_type.value} orders require a stop price")
    
    def update_status(self, status: OrderStatus) -> None:
        """
        Update order status.
        
        Args:
            status: New order status
        """
        if isinstance(status, str):
            status = OrderStatus(status)
        
        self.status = status
        self.updated_at = datetime.now()
        
        # Set additional timestamps based on status
        if status == OrderStatus.SUBMITTED:
            self.submitted_at = datetime.now()
        
        if status == OrderStatus.FILLED:
            self.filled_at = datetime.now()
            self.filled_quantity = self.quantity
            self.remaining_quantity = 0
    
    def update_fill(self, fill_quantity: float, fill_price: float, fee: Optional[float] = None, fee_asset: Optional[str] = None) -> None:
        """
        Update order with fill information.
        
        Args:
            fill_quantity: Quantity filled in this update
            fill_price: Price at which the fill occurred
            fee: Fee charged for this fill
            fee_asset: Asset in which the fee was charged
        """
        # Update fill info
        prev_filled = self.filled_quantity
        self.filled_quantity += fill_quantity
        self.remaining_quantity = max(0, self.quantity - self.filled_quantity)
        
        # Calculate volume-weighted average price
        if prev_filled > 0 and self.average_fill_price is not None:
            total_value = prev_filled * self.average_fill_price + fill_quantity * fill_price
            self.average_fill_price = total_value / self.filled_quantity
        else:
            self.average_fill_price = fill_price
        
        # Update fee
        if fee is not None:
            if self.fee is not None:
                self.fee += fee
            else:
                self.fee = fee
            self.fee_asset = fee_asset
        
        # Update timestamps
        self.updated_at = datetime.now()
        
        # Update status based on fill
        if self.filled_quantity >= self.quantity:
            self.update_status(OrderStatus.FILLED)
            self.filled_at = datetime.now()
        elif self.filled_quantity > 0:
            self.update_status(OrderStatus.PARTIALLY_FILLED)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert order to dictionary.
        
        Returns:
            Dictionary representation of the order
        """
        return {
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "price": self.price,
            "stop_price": self.stop_price,
            "time_in_force": self.time_in_force.value,
            "status": self.status.value,
            "account_id": self.account_id,
            "strategy_id": self.strategy_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "exchange_order_id": self.exchange_order_id,
            "average_fill_price": self.average_fill_price,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "fee": self.fee,
            "fee_asset": self.fee_asset,
            "parent_order_id": self.parent_order_id,
            "venue": self.venue,
            "source": self.source,
            "metadata": self.metadata,
        }
    
    def to_json(self) -> str:
        """
        Convert order to JSON string.
        
        Returns:
            JSON string representation of the order
        """
        return json.dumps(self.to_dict(), default=str)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Order':
        """
        Create order from dictionary.
        
        Args:
            data: Dictionary representation of the order
            
        Returns:
            Order object
        """
        # Parse datetime fields
        for field in ['created_at', 'updated_at', 'submitted_at', 'filled_at']:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])
        
        # Parse enum fields
        if 'side' in data and not isinstance(data['side'], OrderSide):
            data['side'] = OrderSide(data['side'])
        
        if 'order_type' in data and not isinstance(data['order_type'], OrderType):
            data['order_type'] = OrderType(data['order_type'])
        
        if 'time_in_force' in data and not isinstance(data['time_in_force'], TimeInForce):
            data['time_in_force'] = TimeInForce(data['time_in_force'])
        
        if 'status' in data and not isinstance(data['status'], OrderStatus):
            data['status'] = OrderStatus(data['status'])
        
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Order':
        """
        Create order from JSON string.
        
        Args:
            json_str: JSON string representation of the order
            
        Returns:
            Order object
        """
        return cls.from_dict(json.loads(json_str))
    
    def is_active(self) -> bool:
        """
        Check if the order is active.
        
        Returns:
            True if the order is active, False otherwise
        """
        return self.status in [
            OrderStatus.NEW, 
            OrderStatus.PARTIALLY_FILLED, 
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED
        ]
    
    def can_cancel(self) -> bool:
        """
        Check if the order can be canceled.
        
        Returns:
            True if the order can be canceled, False otherwise
        """
        return self.is_active()
    
    def can_modify(self) -> bool:
        """
        Check if the order can be modified.
        
        Returns:
            True if the order can be modified, False otherwise
        """
        return self.is_active()
    
    def __str__(self) -> str:
        """String representation of the order."""
        return (
            f"Order(id={self.order_id}, "
            f"symbol={self.symbol}, "
            f"side={self.side.value}, "
            f"type={self.order_type.value}, "
            f"quantity={self.quantity}, "
            f"price={self.price}, "
            f"status={self.status.value})"
        )
    
    def __repr__(self) -> str:
        """Detailed string representation of the order."""
        return str(self)


class OrderBook:
    """
    Maintains a collection of orders with indexing and querying capabilities.
    
    This class allows efficient lookup of orders by various attributes.
    """
    
    def __init__(self):
        """Initialize an empty order book."""
        self.orders: Dict[str, Order] = {}
        self.by_client_id: Dict[str, str] = {}
        self.by_exchange_id: Dict[str, str] = {}
        self.by_strategy: Dict[str, List[str]] = {}
        self.by_symbol: Dict[str, List[str]] = {}
        self.by_status: Dict[OrderStatus, List[str]] = {status: [] for status in OrderStatus}
    
    def add(self, order: Order) -> None:
        """
        Add an order to the order book.
        
        Args:
            order: Order to add
        """
        order_id = order.order_id
        
        # Store the order
        self.orders[order_id] = order
        
        # Update indexes
        if order.client_order_id:
            self.by_client_id[order.client_order_id] = order_id
        
        if order.exchange_order_id:
            self.by_exchange_id[order.exchange_order_id] = order_id
        
        if order.strategy_id:
            if order.strategy_id not in self.by_strategy:
                self.by_strategy[order.strategy_id] = []
            self.by_strategy[order.strategy_id].append(order_id)
        
        if order.symbol:
            if order.symbol not in self.by_symbol:
                self.by_symbol[order.symbol] = []
            self.by_symbol[order.symbol].append(order_id)
        
        if order.status not in self.by_status:
            self.by_status[order.status] = []
        self.by_status[order.status].append(order_id)
    
    def update(self, order: Order) -> None:
        """
        Update an existing order.
        
        Args:
            order: Updated order
        """
        # Get the current order
        existing_order = self.orders.get(order.order_id)
        
        if not existing_order:
            # If order doesn't exist, just add it
            self.add(order)
            return
        
        # Update indexes if status changed
        if existing_order.status != order.status:
            # Remove from old status index
            if existing_order.status in self.by_status:
                self.by_status[existing_order.status].remove(order.order_id)
            
            # Add to new status index
            if order.status not in self.by_status:
                self.by_status[order.status] = []
            self.by_status[order.status].append(order.order_id)
        
        # Update indexes if exchange_order_id changed
        if existing_order.exchange_order_id != order.exchange_order_id:
            if existing_order.exchange_order_id in self.by_exchange_id:
                del self.by_exchange_id[existing_order.exchange_order_id]
            
            if order.exchange_order_id:
                self.by_exchange_id[order.exchange_order_id] = order.order_id
        
        # Update the order
        self.orders[order.order_id] = order
    
    def get(self, order_id: str) -> Optional[Order]:
        """
        Get an order by ID.
        
        Args:
            order_id: Order ID
            
        Returns:
            Order or None if not found
        """
        return self.orders.get(order_id)
    
    def get_by_client_id(self, client_order_id: str) -> Optional[Order]:
        """
        Get an order by client order ID.
        
        Args:
            client_order_id: Client order ID
            
        Returns:
            Order or None if not found
        """
        order_id = self.by_client_id.get(client_order_id)
        return self.orders.get(order_id) if order_id else None
    
    def get_by_exchange_id(self, exchange_order_id: str) -> Optional[Order]:
        """
        Get an order by exchange order ID.
        
        Args:
            exchange_order_id: Exchange order ID
            
        Returns:
            Order or None if not found
        """
        order_id = self.by_exchange_id.get(exchange_order_id)
        return self.orders.get(order_id) if order_id else None
    
    def get_by_strategy(self, strategy_id: str) -> List[Order]:
        """
        Get all orders for a strategy.
        
        Args:
            strategy_id: Strategy ID
            
        Returns:
            List of orders
        """
        order_ids = self.by_strategy.get(strategy_id, [])
        return [self.orders[order_id] for order_id in order_ids if order_id in self.orders]
    
    def get_by_symbol(self, symbol: str) -> List[Order]:
        """
        Get all orders for a symbol.
        
        Args:
            symbol: Symbol
            
        Returns:
            List of orders
        """
        order_ids = self.by_symbol.get(symbol, [])
        return [self.orders[order_id] for order_id in order_ids if order_id in self.orders]
    
    def get_by_status(self, status: OrderStatus) -> List[Order]:
        """
        Get all orders with a particular status.
        
        Args:
            status: Order status
            
        Returns:
            List of orders
        """
        if isinstance(status, str):
            status = OrderStatus(status)
        
        order_ids = self.by_status.get(status, [])
        return [self.orders[order_id] for order_id in order_ids if order_id in self.orders]
    
    def get_active_orders(self) -> List[Order]:
        """
        Get all active orders.
        
        Returns:
            List of active orders
        """
        active_statuses = [
            OrderStatus.NEW,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED
        ]
        
        active_orders = []
        for status in active_statuses:
            active_orders.extend(self.get_by_status(status))
        
        return active_orders
    
    def remove(self, order_id: str) -> None:
        """
        Remove an order from the order book.
        
        Args:
            order_id: Order ID
        """
        order = self.orders.get(order_id)
        
        if not order:
            return
        
        # Remove from indexes
        if order.client_order_id and order.client_order_id in self.by_client_id:
            del self.by_client_id[order.client_order_id]
        
        if order.exchange_order_id and order.exchange_order_id in self.by_exchange_id:
            del self.by_exchange_id[order.exchange_order_id]
        
        if order.strategy_id and order.strategy_id in self.by_strategy:
            if order_id in self.by_strategy[order.strategy_id]:
                self.by_strategy[order.strategy_id].remove(order_id)
        
        if order.symbol and order.symbol in self.by_symbol:
            if order_id in self.by_symbol[order.symbol]:
                self.by_symbol[order.symbol].remove(order_id)
        
        if order.status in self.by_status and order_id in self.by_status[order.status]:
            self.by_status[order.status].remove(order_id)
        
        # Remove the order
        del self.orders[order_id]
    
    def clear(self) -> None:
        """Clear all orders from the order book."""
        self.orders.clear()
        self.by_client_id.clear()
        self.by_exchange_id.clear()
        self.by_strategy.clear()
        self.by_symbol.clear()
        self.by_status = {status: [] for status in OrderStatus}
    
    def __len__(self) -> int:
        """Get number of orders in the order book."""
        return len(self.orders)
    
    def __contains__(self, order_id: str) -> bool:
        """Check if an order is in the order book."""
        return order_id in self.orders
    
    def __iter__(self):
        """Iterate over orders in the order book."""
        return iter(self.orders.values()) 