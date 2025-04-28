"""
Data models for WebSocket message handling.

This module defines Pydantic models for parsing and validating
WebSocket messages from various cryptocurrency exchanges.
"""
import time
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, validator, field_validator, ValidationInfo, ConfigDict

class WebSocketMessageType(str, Enum):
    """Types of WebSocket messages."""
    TRADE = "trade"
    KLINE = "kline"
    TICKER = "ticker"
    DEPTH = "depth"
    BOOK_TICKER = "bookTicker"
    AGG_TRADE = "aggTrade"
    USER_DATA = "userData"
    EXECUTION_REPORT = "executionReport"
    OUTBOUND_ACCOUNT_INFO = "outboundAccountInfo"
    ACCOUNT_UPDATE = "accountUpdate"
    ORDER_UPDATE = "orderUpdate"
    LISTEN_KEY_EXPIRED = "listenKeyExpired"
    STREAM_EXPIRED = "streamExpired"
    ERROR = "error"
    UNKNOWN = "unknown"

class WebSocketConnectionStatus(str, Enum):
    """Connection status for WebSocket clients."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"

class TradeModel(BaseModel):
    """Model for trade data."""
    symbol: str
    id: int
    price: float
    quantity: float
    timestamp: int
    buyer_order_id: Optional[int] = None
    seller_order_id: Optional[int] = None
    is_buyer_maker: bool
    is_best_match: Optional[bool] = None
    trade_time: Optional[datetime] = None
    
    @field_validator('trade_time', mode='before')
    @classmethod
    def set_trade_time(cls, v, info: ValidationInfo):
        """Set trade_time from timestamp if not provided."""
        if v is None and 'timestamp' in info.data:
            return datetime.fromtimestamp(info.data['timestamp'] / 1000.0)
        return v

class KlineModel(BaseModel):
    """Model for candlestick/kline data."""
    symbol: str
    interval: str
    start_time: int
    close_time: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    trades: int
    is_closed: bool
    quote_volume: float
    taker_buy_volume: float
    taker_buy_quote_volume: float
    start_datetime: Optional[datetime] = None
    close_datetime: Optional[datetime] = None
    
    @validator('start_datetime', pre=True, always=True)
    def set_start_datetime(cls, v, values):
        """Set start_datetime from start_time if not provided."""
        if v is None and 'start_time' in values:
            return datetime.fromtimestamp(values['start_time'] / 1000.0)
        return v
    
    @validator('close_datetime', pre=True, always=True)
    def set_close_datetime(cls, v, values):
        """Set close_datetime from close_time if not provided."""
        if v is None and 'close_time' in values:
            return datetime.fromtimestamp(values['close_time'] / 1000.0)
        return v

class TickerModel(BaseModel):
    """Model for ticker data."""
    symbol: str
    price_change: float
    price_change_percent: float
    weighted_avg_price: float
    prev_close_price: float
    last_price: float
    last_qty: float
    bid_price: float
    bid_qty: float
    ask_price: float
    ask_qty: float
    open_price: float
    high_price: float
    low_price: float
    volume: float
    quote_volume: float
    open_time: int
    close_time: int
    first_id: int
    last_id: int
    count: int
    timestamp: Optional[int] = None
    datetime: Optional[datetime] = None
    
    @validator('timestamp', pre=True, always=True)
    def set_timestamp(cls, v, values):
        """Set timestamp to close_time if not provided."""
        if v is None and 'close_time' in values:
            return values['close_time']
        return v
    
    @validator('datetime', pre=True, always=True)
    def set_datetime(cls, v, values):
        """Set datetime from timestamp if not provided."""
        if v is None and 'timestamp' in values:
            return datetime.fromtimestamp(values['timestamp'] / 1000.0)
        return v

class DepthLevel(BaseModel):
    """Model for a single depth level (price and quantity)."""
    price: float
    quantity: float

class DepthModel(BaseModel):
    """Model for order book depth data."""
    symbol: str
    update_id: int
    timestamp: Optional[int] = None
    bids: List[DepthLevel]
    asks: List[DepthLevel]
    datetime: Optional[datetime] = None
    
    @validator('timestamp', pre=True, always=True)
    def set_timestamp(cls, v):
        """Set timestamp to current time if not provided."""
        if v is None:
            return int(time.time() * 1000)
        return v
    
    @validator('datetime', pre=True, always=True)
    def set_datetime(cls, v, values):
        """Set datetime from timestamp if not provided."""
        if v is None and 'timestamp' in values:
            return datetime.fromtimestamp(values['timestamp'] / 1000.0)
        return v

class BookTickerModel(BaseModel):
    """Model for best bid/ask price and quantity."""
    symbol: str
    bid_price: float
    bid_qty: float
    ask_price: float
    ask_qty: float
    timestamp: Optional[int] = None
    datetime: Optional[datetime] = None
    
    @validator('timestamp', pre=True, always=True)
    def set_timestamp(cls, v):
        """Set timestamp to current time if not provided."""
        if v is None:
            return int(time.time() * 1000)
        return v
    
    @validator('datetime', pre=True, always=True)
    def set_datetime(cls, v, values):
        """Set datetime from timestamp if not provided."""
        if v is None and 'timestamp' in values:
            return datetime.fromtimestamp(values['timestamp'] / 1000.0)
        return v

class BalanceModel(BaseModel):
    """Model for account balance information."""
    asset: str
    free: float
    locked: float
    
    @validator('free', 'locked', pre=True)
    def convert_to_float(cls, v):
        """Convert string values to float."""
        if isinstance(v, str):
            return float(v)
        return v

class OrderModel(BaseModel):
    """Model for order information."""
    symbol: str
    order_id: int
    client_order_id: str
    price: float
    orig_qty: float
    executed_qty: float
    status: str
    time_in_force: str
    type: str
    side: str
    stop_price: Optional[float] = 0.0
    iceberg_qty: Optional[float] = 0.0
    time: int
    update_time: Optional[int] = None
    is_working: Optional[bool] = None
    orig_quote_order_qty: Optional[float] = 0.0
    datetime: Optional[datetime] = None
    
    @validator('datetime', pre=True, always=True)
    def set_datetime(cls, v, values):
        """Set datetime from time if not provided."""
        if v is None and 'time' in values:
            return datetime.fromtimestamp(values['time'] / 1000.0)
        return v

class AccountUpdateModel(BaseModel):
    """Model for account update events."""
    event_type: str = "account"
    event_time: int
    transaction_time: Optional[int] = None
    balances: List[BalanceModel]
    
    @validator('transaction_time', pre=True, always=True)
    def set_transaction_time(cls, v, values):
        """Set transaction_time to event_time if not provided."""
        if v is None and 'event_time' in values:
            return values['event_time']
        return v

class OrderUpdateModel(BaseModel):
    """Model for order update events."""
    event_type: str = "executionReport"
    event_time: int
    symbol: str
    client_order_id: str
    side: str
    order_type: str
    time_in_force: str
    order_quantity: float
    price: float
    stop_price: Optional[float] = None
    iceberg_quantity: Optional[float] = None
    order_list_id: Optional[int] = -1
    original_client_order_id: Optional[str] = None
    current_execution_type: str
    current_order_status: str
    order_reject_reason: Optional[str] = None
    order_id: int
    last_executed_quantity: float
    cumulative_filled_quantity: float
    last_executed_price: Optional[float] = None
    commission_amount: Optional[float] = None
    commission_asset: Optional[str] = None
    transaction_time: int
    trade_id: Optional[int] = None
    is_order_working: bool
    is_trade_maker_side: Optional[bool] = None
    
    @validator('last_executed_price', pre=True, always=True)
    def set_last_price(cls, v, values):
        """Set last_executed_price to price if not provided and last_executed_quantity > 0."""
        if v is None and 'last_executed_quantity' in values and values['last_executed_quantity'] > 0:
            return values.get('price', 0.0)
        return v

class WebSocketMessage(BaseModel):
    """Base model for all WebSocket messages."""
    stream: Optional[str] = None
    message_data: Dict[str, Any]
    msg_type: WebSocketMessageType = WebSocketMessageType.UNKNOWN
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
    event_datetime: datetime = Field(default_factory=datetime.now)
    raw_data: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

class WebSocketError(BaseModel):
    """Model for WebSocket error messages."""
    code: int
    message: str
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
    event_datetime: datetime = Field(default_factory=datetime.now)
    
    model_config = ConfigDict(arbitrary_types_allowed=True) 