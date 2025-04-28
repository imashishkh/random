"""
Data Source Module

This module contains the abstract base class for data sources and a factory
for creating data source adapters for different providers.
"""

import abc
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Tuple

import pandas as pd
import numpy as np
from dotenv import load_dotenv

from ..cache.redis_client import get_cache, set_cache
from ..utils.retry import retry_with_backoff

# Load environment variables
load_dotenv()

# Configure logger
logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit Breaker implementation to prevent cascading failures when API services are down."""
    
    def __init__(self, failure_threshold: int = 5, reset_timeout: int = 60):
        """
        Initialize the circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening the circuit
            reset_timeout: Seconds to wait before attempting to close the circuit
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
    
    def record_failure(self):
        """Record a failure and update circuit state."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
    
    def record_success(self):
        """Record a success and reset the circuit if in HALF-OPEN state."""
        if self.state == "HALF-OPEN":
            self.state = "CLOSED"
            self.failure_count = 0
            self.last_failure_time = None
            logger.info("Circuit breaker closed after successful operation")
    
    def is_open(self) -> bool:
        """
        Check if the circuit is open.
        
        Returns:
            True if the circuit is open and should prevent operations
        """
        if self.state == "OPEN":
            # Check if it's time to try again
            if self.last_failure_time and (time.time() - self.last_failure_time) > self.reset_timeout:
                self.state = "HALF-OPEN"
                logger.info("Circuit breaker transitioned to HALF-OPEN state")
                return False
            return True
        return False
    
    def reset(self):
        """Reset the circuit breaker to its initial state."""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"


class DataSourceAdapter(abc.ABC):
    """
    Abstract base class for data source adapters.
    
    Provides a common interface for different data sources.
    """
    
    def __init__(
        self,
        cache_ttl: int = 3600,
        rate_limit: int = 60,
        circuit_breaker: Optional[CircuitBreaker] = None
    ):
        """
        Initialize the data source adapter.
        
        Args:
            cache_ttl: Default cache time-to-live in seconds
            rate_limit: Maximum requests per minute
            circuit_breaker: Optional circuit breaker instance
        """
        self.cache_ttl = cache_ttl
        self.rate_limit = rate_limit
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.last_request_time = 0
        self.requests_this_minute = 0
        self.minute_start_time = time.time()
    
    def _respect_rate_limit(self):
        """
        Ensure rate limiting is respected by adding delays if necessary.
        """
        current_time = time.time()
        
        # Reset counter if a minute has passed
        if current_time - self.minute_start_time >= 60:
            self.requests_this_minute = 0
            self.minute_start_time = current_time
        
        # Check if we've hit the rate limit
        if self.requests_this_minute >= self.rate_limit:
            # Calculate how long we need to wait until the next minute
            wait_time = 60 - (current_time - self.minute_start_time)
            if wait_time > 0:
                logger.info(f"Rate limit reached, waiting {wait_time:.2f} seconds")
                time.sleep(wait_time)
                # Reset after waiting
                self.requests_this_minute = 0
                self.minute_start_time = time.time()
        
        # Update request count
        self.requests_this_minute += 1
        self.last_request_time = time.time()
    
    def _get_cache_key(self, method: str, params: Dict[str, Any]) -> str:
        """
        Generate a standardized cache key for the request.
        
        Args:
            method: The method or endpoint being called
            params: Request parameters
            
        Returns:
            Formatted cache key string
        """
        # Sort params for consistent keys regardless of dict order
        sorted_params = sorted(params.items())
        param_str = "_".join(f"{k}:{v}" for k, v in sorted_params)
        return f"{self.__class__.__name__}:{method}:{param_str}"
    
    def _get_cached_or_fetch(
        self, 
        method: str,
        params: Dict[str, Any],
        fetch_func,
        ttl: Optional[int] = None
    ) -> Any:
        """
        Try to get data from cache, otherwise fetch it and cache the result.
        
        Args:
            method: The method or endpoint being called
            params: Request parameters
            fetch_func: Function to call if cache miss
            ttl: Optional cache TTL override
            
        Returns:
            The requested data
        """
        cache_key = self._get_cache_key(method, params)
        cached_data = get_cache(cache_key)
        
        if cached_data is not None:
            logger.debug(f"Cache hit for {cache_key}")
            return cached_data
        
        # Check circuit breaker before making the request
        if self.circuit_breaker.is_open():
            logger.warning(f"Circuit breaker is open, skipping request to {method}")
            raise RuntimeError(f"Circuit breaker is open for {method}")
        
        # Respect rate limits
        self._respect_rate_limit()
        
        try:
            # Fetch the data
            data = fetch_func()
            
            # Cache the result
            ttl = ttl or self.cache_ttl
            set_cache(cache_key, data, ttl)
            
            # Record success for circuit breaker
            self.circuit_breaker.record_success()
            
            return data
            
        except Exception as e:
            # Record failure for circuit breaker
            self.circuit_breaker.record_failure()
            logger.error(f"Error fetching data from {method}: {str(e)}")
            raise
    
    @abc.abstractmethod
    async def fetch_ohlcv(
        self, 
        symbol: str, 
        timeframe: str,
        limit: int = 1000,
        since: Optional[Union[datetime, int]] = None,
        to: Optional[Union[datetime, int]] = None
    ) -> pd.DataFrame:
        """
        Fetch OHLCV (candlestick) data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            timeframe: Data timeframe (e.g., '1h', '1d')
            limit: Maximum number of candles to fetch
            since: Start time
            to: End time
            
        Returns:
            DataFrame with OHLCV data
        """
        pass
    
    @abc.abstractmethod
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch current ticker data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Dictionary with ticker data
        """
        pass
    
    @abc.abstractmethod
    async def fetch_fundamental_data(
        self, 
        symbol: str,
        data_type: str
    ) -> Dict[str, Any]:
        """
        Fetch fundamental data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            data_type: Type of fundamental data
            
        Returns:
            Dictionary with fundamental data
        """
        pass
    
    @abc.abstractmethod
    async def fetch_news(
        self,
        keywords: List[str],
        limit: int = 10,
        days: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Fetch news articles related to keywords.
        
        Args:
            keywords: List of keywords to search for
            limit: Maximum number of articles to fetch
            days: How many days of news to fetch
            
        Returns:
            List of news articles
        """
        pass
    
    @abc.abstractmethod
    async def fetch_economic_indicator(
        self,
        indicator: str,
        country: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Fetch economic indicator data.
        
        Args:
            indicator: Economic indicator code
            country: Country code
            start_date: Start date
            end_date: End date
            
        Returns:
            DataFrame with economic indicator data
        """
        pass


class CCXTAdapter(DataSourceAdapter):
    """
    Data source adapter for CCXT library.
    
    Provides access to cryptocurrency exchange data.
    """
    
    def __init__(
        self,
        exchange_id: str = 'binance',
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize the CCXT adapter.
        
        Args:
            exchange_id: CCXT exchange ID
            api_key: API key for authentication
            api_secret: API secret for authentication
            **kwargs: Additional arguments for the base class
        """
        super().__init__(**kwargs)
        self.exchange_id = exchange_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.exchange = None
        
        # This import is here to avoid loading CCXT if not needed
        import ccxt.async_support as ccxt
        
        # Initialize exchange
        if exchange_id not in ccxt.exchanges:
            raise ValueError(f"Exchange {exchange_id} not supported by CCXT")
        
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
            }
        })
    
    async def __aenter__(self):
        """Support for async with statement."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the exchange connection when exiting context."""
        if self.exchange:
            await self.exchange.close()
    
    @retry_with_backoff(max_retries=3, backoff_factor=2)
    async def fetch_ohlcv(
        self, 
        symbol: str, 
        timeframe: str,
        limit: int = 1000,
        since: Optional[Union[datetime, int]] = None,
        to: Optional[Union[datetime, int]] = None
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data using CCXT.
        
        Args:
            symbol: Trading pair symbol
            timeframe: Data timeframe (e.g., '1h', '1d')
            limit: Maximum number of candles to fetch
            since: Start time
            to: End time
            
        Returns:
            DataFrame with OHLCV data
        """
        # Convert datetime to timestamp if needed
        if since and isinstance(since, datetime):
            since = int(since.timestamp() * 1000)
        
        # Create params for caching
        params = {
            'symbol': symbol,
            'timeframe': timeframe,
            'limit': limit,
            'since': since
        }
        
        # Define fetch function for caching wrapper
        async def fetch_func():
            # Ensure the exchange is loaded
            if self.exchange is None:
                raise RuntimeError("Exchange not initialized")
            
            # Fetch the OHLCV data
            ohlcv = await self.exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                since=since
            )
            
            # Convert to DataFrame
            df = pd.DataFrame(ohlcv, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume'
            ])
            
            # Process timestamps
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Convert types
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            return df.to_dict(orient='split')
        
        # Get data with caching
        result = self._get_cached_or_fetch('fetch_ohlcv', params, fetch_func)
        
        # Convert back to DataFrame if it came from cache
        if isinstance(result, dict):
            df = pd.DataFrame(
                data=result.get('data', []),
                index=pd.to_datetime(result.get('index', [])),
                columns=result.get('columns', [])
            )
            return df
        
        return result
    
    @retry_with_backoff(max_retries=3, backoff_factor=2)
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch current ticker data using CCXT.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Dictionary with ticker data
        """
        params = {'symbol': symbol}
        
        async def fetch_func():
            if self.exchange is None:
                raise RuntimeError("Exchange not initialized")
                
            ticker = await self.exchange.fetch_ticker(symbol)
            return ticker
        
        # Use a shorter cache TTL for ticker data (10 seconds)
        return self._get_cached_or_fetch('fetch_ticker', params, fetch_func, ttl=10)
    
    async def fetch_fundamental_data(
        self, 
        symbol: str,
        data_type: str
    ) -> Dict[str, Any]:
        """
        CCXT doesn't directly support fundamental data.
        This method returns placeholder data.
        
        Args:
            symbol: Trading pair symbol
            data_type: Type of fundamental data
            
        Returns:
            Dictionary with placeholder data
        """
        logger.warning("CCXT does not support fundamental data")
        return {'error': 'Fundamental data not available via CCXT'}
    
    async def fetch_news(
        self,
        keywords: List[str],
        limit: int = 10,
        days: int = 1
    ) -> List[Dict[str, Any]]:
        """
        CCXT doesn't support news fetching.
        This method returns placeholder data.
        
        Args:
            keywords: List of keywords to search for
            limit: Maximum number of articles to fetch
            days: How many days of news to fetch
            
        Returns:
            Empty list
        """
        logger.warning("CCXT does not support news fetching")
        return []
    
    async def fetch_economic_indicator(
        self,
        indicator: str,
        country: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        CCXT doesn't support economic indicators.
        This method returns an empty DataFrame.
        
        Args:
            indicator: Economic indicator code
            country: Country code
            start_date: Start date
            end_date: End date
            
        Returns:
            Empty DataFrame
        """
        logger.warning("CCXT does not support economic indicators")
        return pd.DataFrame()


class YFinanceAdapter(DataSourceAdapter):
    """
    Data source adapter for Yahoo Finance.
    
    Provides access to stock and forex market data.
    """
    
    def __init__(self, **kwargs):
        """
        Initialize the Yahoo Finance adapter.
        
        Args:
            **kwargs: Additional arguments for the base class
        """
        super().__init__(**kwargs)
    
    @retry_with_backoff(max_retries=3, backoff_factor=2)
    async def fetch_ohlcv(
        self, 
        symbol: str, 
        timeframe: str,
        limit: int = 1000,
        since: Optional[Union[datetime, int]] = None,
        to: Optional[Union[datetime, int]] = None
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data from Yahoo Finance.
        
        Args:
            symbol: Trading pair symbol
            timeframe: Data timeframe (e.g., '1h', '1d')
            limit: Maximum number of candles to fetch
            since: Start time
            to: End time
            
        Returns:
            DataFrame with OHLCV data
        """
        # Convert timeframe to yfinance format
        interval_map = {
            '1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m',
            '1h': '1h', '2h': '2h', '4h': '4h',
            '1d': '1d', '1w': '1wk', '1M': '1mo'
        }
        
        yf_interval = interval_map.get(timeframe, '1d')
        
        # Handle start and end times
        if since and isinstance(since, int):
            since = datetime.fromtimestamp(since / 1000)
        
        if to and isinstance(to, int):
            to = datetime.fromtimestamp(to / 1000)
        
        # Default start time if not provided
        if not since:
            # Calculate start time based on limit and timeframe
            days_map = {
                '1m': 7, '5m': 30, '15m': 30, '30m': 60,
                '1h': 730, '2h': 730, '4h': 730,
                '1d': 1825, '1wk': 1825, '1mo': 1825
            }
            days = days_map.get(yf_interval, 30)
            since = datetime.now() - timedelta(days=days)
        
        # Default end time if not provided
        if not to:
            to = datetime.now()
        
        # Create params for caching
        params = {
            'symbol': symbol,
            'interval': yf_interval,
            'start': since.strftime('%Y-%m-%d') if since else None,
            'end': to.strftime('%Y-%m-%d') if to else None
        }
        
        # Define fetch function for caching wrapper
        def fetch_func():
            # This import is here to avoid loading yfinance if not needed
            import yfinance as yf
            
            # Get data from Yahoo Finance
            ticker = yf.Ticker(symbol)
            df = ticker.history(
                period=None,
                interval=yf_interval,
                start=since,
                end=to
            )
            
            # Rename columns to match our standard format
            df = df.rename(columns={
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })
            
            # Keep only the columns we need
            df = df[['open', 'high', 'low', 'close', 'volume']]
            
            # Limit the number of rows if specified
            if limit and len(df) > limit:
                df = df.iloc[-limit:]
            
            return df.to_dict(orient='split')
        
        # Execute in a separate thread since yfinance is synchronous
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        # Get data with caching
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(
                pool, 
                lambda: self._get_cached_or_fetch('fetch_ohlcv', params, fetch_func)
            )
        
        # Convert back to DataFrame if it came from cache
        if isinstance(result, dict):
            df = pd.DataFrame(
                data=result.get('data', []),
                index=pd.to_datetime(result.get('index', [])),
                columns=result.get('columns', [])
            )
            return df
        
        return result
    
    @retry_with_backoff(max_retries=3, backoff_factor=2)
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch current ticker data from Yahoo Finance.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Dictionary with ticker data
        """
        params = {'symbol': symbol}
        
        def fetch_func():
            import yfinance as yf
            
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Create a standardized ticker format
            return {
                'symbol': symbol,
                'timestamp': int(time.time() * 1000),
                'datetime': datetime.now().isoformat(),
                'high': info.get('dayHigh'),
                'low': info.get('dayLow'),
                'bid': info.get('bid'),
                'ask': info.get('ask'),
                'last': info.get('regularMarketPrice'),
                'close': info.get('previousClose'),
                'open': info.get('open'),
                'baseVolume': info.get('volume'),
                'info': info
            }
        
        # Execute in a separate thread since yfinance is synchronous
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            # Use a shorter cache TTL for ticker data (30 seconds)
            return await loop.run_in_executor(
                pool,
                lambda: self._get_cached_or_fetch('fetch_ticker', params, fetch_func, ttl=30)
            )
    
    @retry_with_backoff(max_retries=3, backoff_factor=2)
    async def fetch_fundamental_data(
        self, 
        symbol: str,
        data_type: str
    ) -> Dict[str, Any]:
        """
        Fetch fundamental data from Yahoo Finance.
        
        Args:
            symbol: Trading pair symbol
            data_type: Type of fundamental data ('financials', 'balance_sheet', 'cashflow', etc.)
            
        Returns:
            Dictionary with fundamental data
        """
        params = {'symbol': symbol, 'data_type': data_type}
        
        def fetch_func():
            import yfinance as yf
            
            ticker = yf.Ticker(symbol)
            
            # Handle different types of fundamental data
            if data_type == 'financials':
                return ticker.financials.to_dict()
            elif data_type == 'balance_sheet':
                return ticker.balance_sheet.to_dict()
            elif data_type == 'cashflow':
                return ticker.cashflow.to_dict()
            elif data_type == 'earnings':
                return ticker.earnings.to_dict()
            elif data_type == 'sustainability':
                return ticker.sustainability.to_dict() if ticker.sustainability is not None else {}
            elif data_type == 'recommendations':
                return ticker.recommendations.to_dict() if ticker.recommendations is not None else {}
            elif data_type == 'info':
                return ticker.info
            else:
                raise ValueError(f"Unsupported data type: {data_type}")
        
        # Execute in a separate thread since yfinance is synchronous
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            # Use a longer cache TTL for fundamental data (1 day)
            return await loop.run_in_executor(
                pool,
                lambda: self._get_cached_or_fetch('fetch_fundamental', params, fetch_func, ttl=86400)
            )
    
    async def fetch_news(
        self,
        keywords: List[str],
        limit: int = 10,
        days: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Yahoo Finance adapter doesn't directly support news fetching.
        This method returns placeholder data.
        
        Args:
            keywords: List of keywords to search for
            limit: Maximum number of articles to fetch
            days: How many days of news to fetch
            
        Returns:
            Empty list
        """
        logger.warning("YFinance adapter does not support news fetching")
        return []
    
    async def fetch_economic_indicator(
        self,
        indicator: str,
        country: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Yahoo Finance adapter doesn't support economic indicators.
        This method returns an empty DataFrame.
        
        Args:
            indicator: Economic indicator code
            country: Country code
            start_date: Start date
            end_date: End date
            
        Returns:
            Empty DataFrame
        """
        logger.warning("YFinance adapter does not support economic indicators")
        return pd.DataFrame()


class DataSourceFactory:
    """
    Factory for creating data source adapters.
    
    Provides a centralized way to create and manage data source instances.
    """
    
    def __init__(self):
        """Initialize the factory."""
        self.adapter_classes = {
            'ccxt': CCXTAdapter,
            'yfinance': YFinanceAdapter,
            # Add more adapter classes as they are implemented
        }
        self.instances = {}
    
    def get_adapter(
        self, 
        source_type: str,
        **kwargs
    ) -> DataSourceAdapter:
        """
        Get a data source adapter instance.
        
        Args:
            source_type: Type of data source
            **kwargs: Additional arguments for the adapter
            
        Returns:
            Data source adapter instance
            
        Raises:
            ValueError: If the source type is not supported
        """
        if source_type not in self.adapter_classes:
            raise ValueError(f"Unsupported data source type: {source_type}")
        
        # Create a cache key for this adapter configuration
        config_str = "_".join(f"{k}:{v}" for k, v in sorted(kwargs.items()))
        instance_key = f"{source_type}_{config_str}"
        
        # Return existing instance if available
        if instance_key in self.instances:
            return self.instances[instance_key]
        
        # Create new instance
        adapter_class = self.adapter_classes[source_type]
        adapter = adapter_class(**kwargs)
        
        # Store for reuse
        self.instances[instance_key] = adapter
        
        return adapter 