from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum


class TradeDirection(str, Enum):
    """Enum for trade direction"""
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Trade:
    """Data structure for individual trades"""
    id: str
    symbol: str
    open_time: datetime
    close_time: datetime
    direction: TradeDirection
    open_price: float
    close_price: float
    size: float
    pnl: float
    fees: float = 0.0
    strategy: str = "default"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration(self) -> timedelta:
        """Calculate the duration of the trade"""
        return self.close_time - self.open_time
    
    @property
    def net_pnl(self) -> float:
        """Calculate net P&L after fees"""
        return self.pnl - self.fees
    
    @property
    def is_winning(self) -> bool:
        """Determine if the trade was profitable"""
        return self.net_pnl > 0
    
    @property
    def return_pct(self) -> float:
        """Calculate percentage return for the trade"""
        # For long positions: (close_price - open_price) / open_price
        # For short positions: (open_price - close_price) / open_price
        if self.direction == TradeDirection.BUY:
            return ((self.close_price - self.open_price) / self.open_price) * 100
        else:
            return ((self.open_price - self.close_price) / self.open_price) * 100


@dataclass
class PerformanceTimePeriod:
    """Data structure for time period selections"""
    start_date: datetime
    end_date: datetime
    label: str
    
    @classmethod
    def last_day(cls) -> 'PerformanceTimePeriod':
        """Create a time period for the last day"""
        end = datetime.now()
        start = end - timedelta(days=1)
        return cls(start, end, "Last Day")
    
    @classmethod
    def last_week(cls) -> 'PerformanceTimePeriod':
        """Create a time period for the last week"""
        end = datetime.now()
        start = end - timedelta(days=7)
        return cls(start, end, "Last Week")
    
    @classmethod
    def last_month(cls) -> 'PerformanceTimePeriod':
        """Create a time period for the last month"""
        end = datetime.now()
        start = end - timedelta(days=30)
        return cls(start, end, "Last Month")
    
    @classmethod
    def last_year(cls) -> 'PerformanceTimePeriod':
        """Create a time period for the last year"""
        end = datetime.now()
        start = end - timedelta(days=365)
        return cls(start, end, "Last Year")
    
    @classmethod
    def year_to_date(cls) -> 'PerformanceTimePeriod':
        """Create a time period for year to date"""
        end = datetime.now()
        start = datetime(end.year, 1, 1)
        return cls(start, end, "Year to Date")
    
    @classmethod
    def custom(cls, start: datetime, end: datetime, label: str = "Custom") -> 'PerformanceTimePeriod':
        """Create a custom time period"""
        return cls(start, end, label)


@dataclass
class TradeFilter:
    """Data structure for filtering trades"""
    time_period: Optional[PerformanceTimePeriod] = None
    symbols: Optional[List[str]] = None
    strategies: Optional[List[str]] = None
    min_pnl: Optional[float] = None
    max_pnl: Optional[float] = None
    directions: Optional[List[TradeDirection]] = None
    tags: Optional[List[str]] = None 