from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Union
import time


class OrderType(Enum):
    """Types of orders that can be placed on the exchange"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"


class OrderStatus(Enum):
    """Status values for exchange orders"""
    PENDING = "PENDING"      # Order is being processed locally
    NEW = "NEW"              # Order accepted by exchange
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ExitStrategyType(Enum):
    """Types of exit strategies for stop-loss and take-profit"""
    # Stop-loss types
    FIXED_STOP_LOSS = "FIXED_STOP_LOSS"
    TRAILING_STOP_LOSS = "TRAILING_STOP_LOSS"
    ATR_STOP_LOSS = "ATR_STOP_LOSS"
    TIME_BASED_STOP_LOSS = "TIME_BASED_STOP_LOSS"
    
    # Take-profit types
    FIXED_TAKE_PROFIT = "FIXED_TAKE_PROFIT"
    TRAILING_TAKE_PROFIT = "TRAILING_TAKE_PROFIT"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    SCALED_EXIT = "SCALED_EXIT"


@dataclass
class ExitOrder:
    """Represents an exit order (stop-loss or take-profit)"""
    order_id: str  # Exchange order ID, empty if not yet placed
    position_id: str  # Associated position ID
    price: float  # Order price
    quantity: float  # Order quantity
    type: OrderType  # Order type
    status: str  # Order status
    created_time: int  # Timestamp when order was created
    updated_time: int = field(default_factory=lambda: int(time.time()))
    exchange_info: Dict = field(default_factory=dict)  # Additional exchange-specific info


@dataclass
class Position:
    """Represents a trading position"""
    symbol: str  # Trading pair/symbol
    position_id: str  # Unique position identifier
    entry_price: float  # Average entry price
    quantity: float  # Position size
    side: str  # "BUY" or "SELL"
    open_time: int  # Timestamp when position was opened
    stop_loss_orders: List[ExitOrder] = field(default_factory=list)  # Stop-loss orders
    take_profit_orders: List[ExitOrder] = field(default_factory=list)  # Take-profit orders
    is_active: bool = True  # Whether position is still active


@dataclass
class MarketData:
    """Container for market data needed for exit calculations"""
    symbol: str
    last_price: float  # Current price
    timestamp: int  # Data timestamp
    
    # Technical indicators
    atr: Optional[float] = None  # Average True Range
    bollinger_upper: Optional[float] = None
    bollinger_lower: Optional[float] = None
    rsi: Optional[float] = None
    
    # Market state information
    is_volatile: bool = False
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)
    
    # Additional data
    extra: Dict = field(default_factory=dict) 