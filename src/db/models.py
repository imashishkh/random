"""
Entity model classes for the trade analytics application.
These models represent the database structure and provide data validation.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from decimal import Decimal

@dataclass
class TradeBase:
    """Base class for trade-related entities with common fields."""
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class Symbol(TradeBase):
    """Symbol entity representing a tradable financial instrument."""
    name: str
    type: str  # 'forex', 'stock', 'crypto', etc.
    description: Optional[str] = None
    active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Trade(TradeBase):
    """Trade entity representing a single trade transaction."""
    symbol_id: int
    open_time: datetime
    open_price: Decimal
    close_time: Optional[datetime] = None
    close_price: Optional[Decimal] = None
    volume: Decimal = Decimal('0.01')
    direction: str = 'buy'  # 'buy' or 'sell'
    pnl: Optional[Decimal] = None
    pips: Optional[Decimal] = None
    status: str = 'open'  # 'open', 'closed', 'cancelled'
    take_profit: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    commission: Optional[Decimal] = None
    swap: Optional[Decimal] = None
    tags: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def calculate_pnl(self) -> Decimal:
        """Calculate the profit or loss for this trade."""
        if self.close_price is None or self.status != 'closed':
            return Decimal('0')
            
        price_diff = self.close_price - self.open_price
        if self.direction == 'sell':
            price_diff = -price_diff
            
        pnl = price_diff * self.volume
        
        # Subtract costs if available
        if self.commission:
            pnl -= self.commission
        if self.swap:
            pnl -= self.swap
            
        return pnl
        
    def calculate_pips(self) -> Decimal:
        """Calculate the number of pips for this trade."""
        if self.close_price is None or self.status != 'closed':
            return Decimal('0')
            
        price_diff = abs(self.close_price - self.open_price)
        # For Forex, typically multiply by 10000 to get pips
        # This is a simplified calculation - actual pip calculation depends on the currency pair
        pips = price_diff * Decimal('10000')
        
        if (self.direction == 'buy' and self.close_price < self.open_price) or \
           (self.direction == 'sell' and self.close_price > self.open_price):
            pips = -pips
            
        return pips

@dataclass
class TradeMetric(TradeBase):
    """Trade metric entity for tracking performance statistics."""
    symbol_id: Optional[int] = None
    metric_type: str = ''  # 'daily', 'weekly', 'monthly', etc.
    date: datetime = field(default_factory=datetime.now)
    win_count: int = 0
    loss_count: int = 0
    total_trades: int = 0
    profit_amount: Decimal = Decimal('0')
    loss_amount: Decimal = Decimal('0')
    net_pnl: Decimal = Decimal('0')
    largest_win: Decimal = Decimal('0')
    largest_loss: Decimal = Decimal('0')
    average_win: Decimal = Decimal('0')
    average_loss: Decimal = Decimal('0')
    win_rate: Decimal = Decimal('0')
    profit_factor: Decimal = Decimal('0')
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def calculate_derived_metrics(self) -> None:
        """Calculate derived metrics based on raw trade data."""
        self.total_trades = self.win_count + self.loss_count
        
        if self.total_trades > 0:
            self.win_rate = Decimal(self.win_count) / Decimal(self.total_trades)
            
        if self.loss_amount != 0:
            self.profit_factor = abs(self.profit_amount / self.loss_amount) if self.loss_amount else Decimal('0')
            
        if self.win_count > 0:
            self.average_win = self.profit_amount / Decimal(self.win_count)
            
        if self.loss_count > 0:
            self.average_loss = abs(self.loss_amount / Decimal(self.loss_count))

@dataclass
class TradingSession(TradeBase):
    """Trading session entity representing a group of related trades."""
    name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str = 'active'  # 'active', 'completed', 'cancelled'
    description: Optional[str] = None
    tag: Optional[str] = None
    trades_count: int = 0
    net_pnl: Decimal = Decimal('0')
    win_count: int = 0
    loss_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TradeTag(TradeBase):
    """Trade tag entity for categorizing trades."""
    name: str
    description: Optional[str] = None
    color: Optional[str] = None  # Hex color code
    is_system: bool = False

@dataclass
class PriceData(TradeBase):
    """Price data entity for storing historical price information."""
    symbol_id: int
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Optional[Decimal] = None
    timeframe: str = '1m'  # '1m', '5m', '15m', '1h', '4h', '1d', etc.
    
@dataclass
class TradingStrategy(TradeBase):
    """Trading strategy entity for tracking performance by strategy."""
    name: str
    description: Optional[str] = None
    is_active: bool = True
    win_count: int = 0
    loss_count: int = 0
    total_trades: int = 0
    net_pnl: Decimal = Decimal('0')
    win_rate: Decimal = Decimal('0')
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update_stats(self, is_win: bool, pnl: Decimal) -> None:
        """Update strategy statistics with a new trade result."""
        self.total_trades += 1
        
        if is_win:
            self.win_count += 1
        else:
            self.loss_count += 1
            
        self.net_pnl += pnl
        
        if self.total_trades > 0:
            self.win_rate = Decimal(self.win_count) / Decimal(self.total_trades) 