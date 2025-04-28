"""
Generator Base Classes

This module defines the base interfaces for different types of generators,
including market data generators and order generators.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, AsyncIterator, Callable, Union
from datetime import datetime
import logging
import time
import uuid
from dataclasses import dataclass

from ..config import MarketDataType, OrderType, PatternType


@dataclass
class MarketDataTick:
    """Market data tick representation."""
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    tick_id: str = None
    
    def __post_init__(self):
        if self.tick_id is None:
            self.tick_id = str(uuid.uuid4())


@dataclass
class MarketDataTrade:
    """Market trade execution representation."""
    symbol: str
    timestamp: datetime
    price: float
    volume: float
    direction: str  # "buy" or "sell"
    trade_id: str = None
    
    def __post_init__(self):
        if self.trade_id is None:
            self.trade_id = str(uuid.uuid4())


@dataclass
class OrderBookLevel:
    """Single level in an order book."""
    price: float
    volume: float


@dataclass
class OrderBookSnapshot:
    """Order book snapshot representation."""
    symbol: str
    timestamp: datetime
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    snapshot_id: str = None
    
    def __post_init__(self):
        if self.snapshot_id is None:
            self.snapshot_id = str(uuid.uuid4())


@dataclass
class CandleData:
    """OHLCV candle data representation."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    candle_id: str = None
    
    def __post_init__(self):
        if self.candle_id is None:
            self.candle_id = str(uuid.uuid4())


@dataclass
class OrderData:
    """Order data representation."""
    symbol: str
    timestamp: datetime
    order_type: OrderType
    direction: str  # "buy" or "sell"
    price: Optional[float]  # None for market orders
    volume: float
    stop_price: Optional[float] = None  # For stop and stop-limit orders
    order_id: str = None
    
    def __post_init__(self):
        if self.order_id is None:
            self.order_id = str(uuid.uuid4())


# Define a generic type for all market data types
MarketData = Union[MarketDataTick, MarketDataTrade, OrderBookSnapshot, CandleData]


class BaseGenerator(ABC):
    """Base class for all data generators."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the generator.
        
        Args:
            config: Configuration dictionary
            logger: Optional logger instance
        """
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._running = False
        self._stop_event = asyncio.Event()
        self._data_listeners: List[Callable[[Any], None]] = []
        
    @abstractmethod
    async def start(self) -> None:
        """Start the generator."""
        self._running = True
        self._stop_event.clear()
        
    @abstractmethod
    async def stop(self) -> None:
        """Stop the generator."""
        self._running = False
        self._stop_event.set()
        
    def add_listener(self, listener: Callable[[Any], None]) -> None:
        """
        Add a listener function to receive generated data.
        
        Args:
            listener: Callback function that accepts generated data
        """
        self._data_listeners.append(listener)
        
    def remove_listener(self, listener: Callable[[Any], None]) -> None:
        """
        Remove a listener function.
        
        Args:
            listener: Listener function to remove
        """
        if listener in self._data_listeners:
            self._data_listeners.remove(listener)
    
    def _notify_listeners(self, data: Any) -> None:
        """
        Notify all listeners with generated data.
        
        Args:
            data: Generated data to send to listeners
        """
        for listener in self._data_listeners:
            try:
                listener(data)
            except Exception as e:
                self.logger.error(f"Error in listener callback: {e}")
    
    async def _sleep_adjusted(self, delay: float) -> None:
        """
        Sleep for the specified delay, but can be interrupted by stop_event.
        
        Args:
            delay: Sleep time in seconds
        """
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            # This is expected when the timeout occurs before the event is set
            pass


class MarketDataGenerator(BaseGenerator):
    """Base class for market data generators."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the market data generator.
        
        Args:
            config: Configuration dictionary
            logger: Optional logger instance
        """
        super().__init__(config, logger)
        self.data_type = config.get('data_type', MarketDataType.TICK)
        self.symbols = config.get('symbols', ['EURUSD'])
        self.rate = config.get('rate', 1000)  # Ticks per second
        self.burst_rate = config.get('burst_rate')  # Optional burst rate
        self.pattern = config.get('pattern', PatternType.NORMAL)
        self.volatility = config.get('volatility', 0.0002)  # Base volatility level
    
    @abstractmethod
    async def generate_data(self) -> AsyncIterator[MarketData]:
        """
        Generate market data.
        
        Returns:
            AsyncIterator yielding market data
        """
        pass

    async def _generate_burst(self, duration: float = 1.0, rate_multiplier: float = 10.0) -> None:
        """
        Generate a burst of data at a higher rate.
        
        Args:
            duration: Burst duration in seconds
            rate_multiplier: Multiplier for the base rate during burst
        """
        burst_rate = self.burst_rate or int(self.rate * rate_multiplier)
        self.logger.info(f"Starting data burst at {burst_rate} ticks/sec for {duration} seconds")
        
        # Store original rate to restore after burst
        original_rate = self.rate
        
        try:
            # Set burst rate
            self.rate = burst_rate
            
            # Sleep for burst duration
            start_time = time.time()
            await self._sleep_adjusted(duration)
            
            elapsed = time.time() - start_time
            self.logger.info(f"Data burst completed after {elapsed:.2f} seconds")
        finally:
            # Restore original rate
            self.rate = original_rate


class OrderGenerator(BaseGenerator):
    """Base class for order generators."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the order generator.
        
        Args:
            config: Configuration dictionary
            logger: Optional logger instance
        """
        super().__init__(config, logger)
        self.enabled = config.get('enabled', False)
        self.order_types = config.get('order_types', [OrderType.MARKET, OrderType.LIMIT])
        self.rate = config.get('rate', 10)  # Orders per second
        self.burst_rate = config.get('burst_rate')  # Optional burst rate
        self.burst_duration = config.get('burst_duration', 1.0)  # Burst duration in seconds
        self.size_min = config.get('size_min', 0.1)
        self.size_max = config.get('size_max', 10.0)
        self.correlated_to_market = config.get('correlated_to_market', True)
        self.symbols = config.get('symbols', ['EURUSD'])
        
        # Optional reference to a market data generator to correlate with
        self.market_data_generator = None
    
    @abstractmethod
    async def generate_orders(self) -> AsyncIterator[OrderData]:
        """
        Generate order data.
        
        Returns:
            AsyncIterator yielding order data
        """
        pass
    
    def set_market_data_generator(self, generator: MarketDataGenerator) -> None:
        """
        Set the market data generator to correlate with.
        
        Args:
            generator: Market data generator instance
        """
        self.market_data_generator = generator
    
    async def _generate_burst(self, duration: Optional[float] = None, rate_multiplier: float = 10.0) -> None:
        """
        Generate a burst of orders at a higher rate.
        
        Args:
            duration: Burst duration in seconds (defaults to self.burst_duration)
            rate_multiplier: Multiplier for the base rate during burst
        """
        if not self.enabled:
            return
            
        burst_duration = duration or self.burst_duration
        burst_rate = self.burst_rate or (self.rate * rate_multiplier)
        
        self.logger.info(f"Starting order burst at {burst_rate} orders/sec for {burst_duration} seconds")
        
        # Store original rate to restore after burst
        original_rate = self.rate
        
        try:
            # Set burst rate
            self.rate = burst_rate
            
            # Sleep for burst duration
            start_time = time.time()
            await self._sleep_adjusted(burst_duration)
            
            elapsed = time.time() - start_time
            self.logger.info(f"Order burst completed after {elapsed:.2f} seconds")
        finally:
            # Restore original rate
            self.rate = original_rate 