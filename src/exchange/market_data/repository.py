"""
Market Data Repository module.

This module provides a central repository for storing and retrieving
the latest market data with configurable time-to-live (TTL).
"""
import time
import logging
from typing import Dict, Any, Optional
from threading import Lock

logger = logging.getLogger(__name__)

class MarketDataRepository:
    """
    Central repository for latest market data.
    
    Provides thread-safe storage and retrieval of latest market data
    with configurable time-to-live (TTL) for different data types.
    """
    
    _instance = None  # Singleton instance
    
    @classmethod
    def get_instance(cls, *args, **kwargs):
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls(*args, **kwargs)
        return cls._instance
    
    def __init__(self):
        """Initialize the market data repository."""
        # Data storage
        self.trades = {}        # symbol -> latest trade
        self.tickers = {}       # symbol -> latest ticker
        self.book_tickers = {}  # symbol -> latest book ticker
        
        # Data timestamps
        self.trade_times = {}   # symbol -> last trade time
        self.ticker_times = {}  # symbol -> last ticker time
        self.book_ticker_times = {} # symbol -> last book ticker time
        
        # TTL in seconds for different data types
        self.ttl_trades = 60        # 1 minute
        self.ttl_tickers = 60       # 1 minute
        self.ttl_book_tickers = 10  # 10 seconds
        
        # Thread safety
        self.lock = Lock()
        
        logger.info("Market data repository initialized")
    
    def update_trade(self, trade_data: Dict[str, Any]) -> None:
        """
        Update the latest trade data for a symbol.
        
        Args:
            trade_data: Trade data to store
        """
        symbol = trade_data.get("symbol", "").upper()
        if not symbol:
            return
        
        with self.lock:
            self.trades[symbol] = trade_data
            self.trade_times[symbol] = time.time()
    
    def update_ticker(self, ticker_data: Dict[str, Any]) -> None:
        """
        Update the latest ticker data for a symbol.
        
        Args:
            ticker_data: Ticker data to store
        """
        symbol = ticker_data.get("symbol", "").upper()
        if not symbol:
            return
        
        with self.lock:
            self.tickers[symbol] = ticker_data
            self.ticker_times[symbol] = time.time()
    
    def update_book_ticker(self, book_ticker_data: Dict[str, Any]) -> None:
        """
        Update the latest book ticker data for a symbol.
        
        Args:
            book_ticker_data: Book ticker data to store
        """
        symbol = book_ticker_data.get("symbol", "").upper()
        if not symbol:
            return
        
        with self.lock:
            self.book_tickers[symbol] = book_ticker_data
            self.book_ticker_times[symbol] = time.time()
    
    def get_latest_trade(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest trade data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Latest trade data or None if not available or expired
        """
        symbol = symbol.upper()
        
        with self.lock:
            # Check if we have trade data for this symbol
            if symbol not in self.trades:
                return None
            
            # Check if the data is expired
            now = time.time()
            if now - self.trade_times.get(symbol, 0) > self.ttl_trades:
                return None
            
            return self.trades[symbol]
    
    def get_latest_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest ticker data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Latest ticker data or None if not available or expired
        """
        symbol = symbol.upper()
        
        with self.lock:
            # Check if we have ticker data for this symbol
            if symbol not in self.tickers:
                return None
            
            # Check if the data is expired
            now = time.time()
            if now - self.ticker_times.get(symbol, 0) > self.ttl_tickers:
                return None
            
            return self.tickers[symbol]
    
    def get_latest_book_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest book ticker data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Latest book ticker data or None if not available or expired
        """
        symbol = symbol.upper()
        
        with self.lock:
            # Check if we have book ticker data for this symbol
            if symbol not in self.book_tickers:
                return None
            
            # Check if the data is expired
            now = time.time()
            if now - self.book_ticker_times.get(symbol, 0) > self.ttl_book_tickers:
                return None
            
            return self.book_tickers[symbol]
    
    def clean_expired_data(self) -> None:
        """Remove expired data from the repository."""
        now = time.time()
        
        with self.lock:
            # Clean trades
            for symbol in list(self.trades.keys()):
                if now - self.trade_times.get(symbol, 0) > self.ttl_trades:
                    del self.trades[symbol]
                    del self.trade_times[symbol]
            
            # Clean tickers
            for symbol in list(self.tickers.keys()):
                if now - self.ticker_times.get(symbol, 0) > self.ttl_tickers:
                    del self.tickers[symbol]
                    del self.ticker_times[symbol]
            
            # Clean book tickers
            for symbol in list(self.book_tickers.keys()):
                if now - self.book_ticker_times.get(symbol, 0) > self.ttl_book_tickers:
                    del self.book_tickers[symbol]
                    del self.book_ticker_times[symbol]
    
    def set_ttl(self, data_type: str, ttl_seconds: int) -> None:
        """
        Set the TTL for a data type.
        
        Args:
            data_type: Data type ('trades', 'tickers', 'book_tickers')
            ttl_seconds: Time-to-live in seconds
        """
        if data_type == 'trades':
            self.ttl_trades = ttl_seconds
        elif data_type == 'tickers':
            self.ttl_tickers = ttl_seconds
        elif data_type == 'book_tickers':
            self.ttl_book_tickers = ttl_seconds
        else:
            logger.warning(f"Unknown data type: {data_type}") 