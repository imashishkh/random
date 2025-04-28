"""
Binance data collector.

This module implements a collector for fetching data from Binance API.
It supports both REST API and WebSocket streams for different data types.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Callable

import pandas as pd
import aiohttp

from .base import BaseCollector, DataSink
from .binance.constants import (
    REST_API_URL, WS_API_URL, PUBLIC_ENDPOINTS, AUTH_ENDPOINTS, 
    TIMEFRAMES, WEBSOCKET_STREAMS, 
    RETRY_CODES, RETRY_HTTP_STATUSES
)
from .binance.monitoring import BinanceMonitor
from .binance.websocket import BinanceWebSocketClient

logger = logging.getLogger(__name__)


class BinanceCollector(BaseCollector):
    """
    Collector for Binance exchange data.
    
    Provides methods to fetch data from Binance using both REST API and WebSockets.
    Supports various data types including OHLCV, trade, ticker, and order book data.
    """
    
    def __init__(
        self, 
        symbols: List[str],
        timeframes: Optional[List[str]] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        data_sink: Optional[DataSink] = None,
        use_testnet: bool = False,
        request_timeout: int = 10,
        rate_limit_waiting: bool = True,
        enable_monitoring: bool = True,
        monitor_check_interval: int = 60
    ):
        """
        Initialize the Binance collector.
        
        Args:
            symbols: List of trading pair symbols to collect data for
            timeframes: List of timeframes for candlestick data
            api_key: Binance API key for authenticated endpoints
            api_secret: Binance API secret for authenticated endpoints
            data_sink: Data sink to store collected data
            use_testnet: Whether to use the Binance testnet
            request_timeout: Timeout for HTTP requests in seconds
            rate_limit_waiting: Whether to wait on rate limit errors
            enable_monitoring: Whether to enable health monitoring
            monitor_check_interval: Interval for health checks in seconds
        """
        super().__init__(name="Binance", config={
            "symbols": symbols,
            "timeframes": timeframes or ["1m"],
            "use_testnet": use_testnet,
            "request_timeout": request_timeout,
            "rate_limit_waiting": rate_limit_waiting,
            "enable_monitoring": enable_monitoring,
            "monitor_check_interval": monitor_check_interval
        })
        
        # Set up Binance-specific configuration
        self.symbols = [s.upper() for s in symbols]
        self.timeframes = timeframes or ["1m"]
        self.api_key = api_key
        self.api_secret = api_secret
        self.data_sink = data_sink
        
        # Base URLs based on testnet setting
        if use_testnet:
            self.rest_api_url = "https://testnet.binance.vision/api"
            self.ws_api_url = "wss://testnet.binance.vision/ws"
        else:
            self.rest_api_url = REST_API_URL
            self.ws_api_url = WS_API_URL
            
        # HTTP session for REST API requests
        self.session = None
        
        # WebSocket client
        self.ws_client = None
        
        # Track rate limits
        self.rate_limit_reset = 0
        self.rate_limit_remaining = 0
        
        # Setup monitoring if enabled
        self.enable_monitoring = enable_monitoring
        if enable_monitoring:
            self.monitor = BinanceMonitor(
                collector_name=f"BinanceCollector-{'-'.join(symbols[:2])}" + 
                              (f"+{len(symbols)-2}more" if len(symbols) > 2 else ""),
                check_interval=monitor_check_interval
            )
        else:
            self.monitor = None
    
    async def start(self):
        """
        Start the Binance collector.
        
        Initializes HTTP session and WebSocket client.
        """
        if self.running:
            return
            
        await super().start()
        
        # Initialize HTTP session
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config['request_timeout'])
        )
        
        # Initialize WebSocket client
        self.ws_client = BinanceWebSocketClient(
            on_message=self._on_ws_message,
            base_url=self.ws_api_url
        )
        
        # Start WebSocket connection
        await self.ws_client.connect()
        
        # Start monitoring if enabled
        if self.enable_monitoring and self.monitor:
            await self.monitor.start_monitoring()
            
            # Update WebSocket connection status in monitor
            if self.ws_client:
                self.monitor.record_ws_connection(connected=True)
        
    async def stop(self):
        """
        Stop the Binance collector.
        
        Closes HTTP session and WebSocket client.
        """
        if not self.running:
            return
            
        # Stop monitoring first
        if self.enable_monitoring and self.monitor:
            await self.monitor.stop_monitoring()
            
        # Close WebSocket client
        if self.ws_client:
            if self.enable_monitoring and self.monitor:
                self.monitor.record_ws_connection(connected=False)
            await self.ws_client.disconnect()
            self.ws_client = None
            
        # Close HTTP session
        if self.session:
            await self.session.close()
            self.session = None
            
        await super().stop()
        
    async def collect(self, data_type: str, symbol: str, timeframe: Optional[str] = None, **kwargs) -> Any:
        """
        Collect data from Binance.
        
        Args:
            data_type: Type of data to collect (kline, trade, ticker, etc.)
            symbol: Trading pair symbol
            timeframe: Timeframe for kline data
            **kwargs: Additional parameters for the request
            
        Returns:
            Collected data
        """
        result = None
        success = False
        error = None
        data_points = 0
        
        try:
            if data_type == "kline":
                assert timeframe, "Timeframe must be specified for kline data"
                result = await self.fetch_klines(symbol, timeframe, **kwargs)
            elif data_type == "trade":
                result = await self.fetch_trades(symbol, **kwargs)
            elif data_type == "ticker":
                result = await self.fetch_ticker(symbol)
            elif data_type == "orderbook":
                result = await self.fetch_orderbook(symbol, **kwargs)
            elif data_type == "exchange_info":
                result = await self.fetch_exchange_info(**kwargs)
            else:
                raise ValueError(f"Unsupported data type: {data_type}")
                
            success = True
            # Count data points if possible
            if hasattr(result, '__len__'):
                data_points = len(result)
            elif isinstance(result, dict) and result.get('bids') and hasattr(result['bids'], '__len__'):
                data_points = len(result['bids']) + len(result.get('asks', []))
            elif isinstance(result, dict):
                data_points = 1
                
        except Exception as e:
            error = str(e)
            logger.error(f"Error collecting {data_type} data for {symbol}: {error}")
            raise
            
        finally:
            # Record metrics if monitoring is enabled
            if self.enable_monitoring and self.monitor:
                self.monitor.record_request(success=success, error=error, data_points=data_points)
                
        return result
        
    async def subscribe_ws(self, data_type: str, symbol: str, timeframe: Optional[str] = None, callback: Optional[Callable] = None):
        """
        Subscribe to WebSocket stream.
        
        Args:
            data_type: Type of data to subscribe to
            symbol: Trading pair symbol
            timeframe: Timeframe for kline data
            callback: Callback function for processing messages
            
        Returns:
            Stream name that was subscribed to
        """
        if not self.ws_client:
            raise RuntimeError("WebSocket client not initialized. Call start() first.")
            
        symbol = symbol.lower()
        
        if data_type == "kline":
            assert timeframe, "Timeframe must be specified for kline stream"
            stream = f"{symbol}@kline_{timeframe}"
        elif data_type == "trade":
            stream = f"{symbol}@trade"
        elif data_type == "ticker":
            stream = f"{symbol}@ticker"
        elif data_type == "bookTicker":
            stream = f"{symbol}@bookTicker"
        elif data_type == "depth":
            stream = f"{symbol}@depth"
        else:
            raise ValueError(f"Unsupported WebSocket stream type: {data_type}")
            
        if callback:
            self.ws_client.add_callback(stream, callback)
            
        await self.ws_client.add_stream(stream)
        
        # Record subscription in monitoring
        if self.enable_monitoring and self.monitor:
            self.monitor.record_ws_subscription(stream, subscribed=True)
            
        return stream
        
    async def unsubscribe_ws(self, stream: str):
        """
        Unsubscribe from WebSocket stream.
        
        Args:
            stream: Stream name to unsubscribe from
        """
        if not self.ws_client:
            return
            
        await self.ws_client.remove_stream(stream)
        
        # Record unsubscription in monitoring
        if self.enable_monitoring and self.monitor:
            self.monitor.record_ws_subscription(stream, subscribed=False)
        
    async def _on_ws_message(self, msg: Dict[str, Any]):
        """
        Process WebSocket message.
        
        Args:
            msg: Message from WebSocket
        """
        # Record message receipt in monitoring
        if self.enable_monitoring and self.monitor:
            self.monitor.record_ws_message(msg)
            
        # Store data if a data sink is configured
        if self.data_sink:
            await self.data_sink.store(msg)
            
    async def _make_request(
        self, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None, 
        method: str = "GET",
        auth: bool = False
    ) -> Any:
        """
        Make a request to the Binance API.
        
        Handles rate limiting, authentication, and error handling.
        
        Args:
            endpoint: API endpoint
            params: Request parameters
            method: HTTP method
            auth: Whether to use authentication
            
        Returns:
            Response data
        """
        if not self.session:
            raise RuntimeError("HTTP session not initialized. Call start() first.")
            
        # Check rate limit
        if self.rate_limit_remaining == 0 and time.time() < self.rate_limit_reset:
            wait_time = max(0, self.rate_limit_reset - time.time())
            if self.config["rate_limit_waiting"]:
                logger.warning(f"Rate limit exceeded, waiting {wait_time:.2f} seconds")
                await asyncio.sleep(wait_time)
            else:
                raise Exception(f"Rate limit exceeded, reset in {wait_time:.2f} seconds")
                
        # Build URL
        url = f"{self.rest_api_url}{endpoint}"
        
        # Add authentication if needed
        headers = {}
        if auth:
            if not self.api_key or not self.api_secret:
                raise ValueError("API key and secret required for authenticated endpoints")
                
            # TODO: Implement Binance authentication signature
            timestamp = int(time.time() * 1000)
            if params is None:
                params = {}
                
            params["timestamp"] = timestamp
            
            # Add signature (implement according to Binance API docs)
            
            headers["X-MBX-APIKEY"] = self.api_key
        
        # Make request with retry logic
        max_retries = 3
        retry_delay = 1
        
        for retry in range(max_retries):
            try:
                if method == "GET":
                    response = await self.session.get(url, params=params, headers=headers)
                elif method == "POST":
                    response = await self.session.post(url, json=params, headers=headers)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                    
                # Update rate limit info
                if "X-MBX-USED-WEIGHT" in response.headers:
                    weight = int(response.headers["X-MBX-USED-WEIGHT"])
                    self.rate_limit_remaining = 1200 - weight  # Binance default weight limit
                    
                if "Retry-After" in response.headers:
                    self.rate_limit_reset = time.time() + int(response.headers["Retry-After"])
                    
                # Handle HTTP errors
                if response.status in RETRY_HTTP_STATUSES:
                    if retry < max_retries - 1:
                        await asyncio.sleep(retry_delay * (2 ** retry))
                        continue
                    else:
                        response.raise_for_status()
                        
                # Parse JSON response
                data = await response.json()
                
                # Check for Binance error
                if isinstance(data, dict) and "code" in data and "msg" in data:
                    error_code = data["code"]
                    error_msg = data["msg"]
                    
                    if error_code in RETRY_CODES and retry < max_retries - 1:
                        logger.warning(f"Binance API error {error_code}: {error_msg}, retrying...")
                        await asyncio.sleep(retry_delay * (2 ** retry))
                        continue
                    else:
                        raise Exception(f"Binance API error {error_code}: {error_msg}")
                        
                return data
                
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if retry < max_retries - 1:
                    logger.warning(f"Request error: {str(e)}, retrying...")
                    await asyncio.sleep(retry_delay * (2 ** retry))
                else:
                    raise Exception(f"Request failed after {max_retries} retries: {str(e)}")
    
    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[Union[int, datetime, str]] = None,
        end_time: Optional[Union[int, datetime, str]] = None,
        limit: int = 500
    ) -> pd.DataFrame:
        """
        Fetch kline (candlestick) data.
        
        Args:
            symbol: Trading pair symbol
            interval: Kline interval
            start_time: Start time
            end_time: End time
            limit: Maximum number of records to return
            
        Returns:
            DataFrame with kline data
        """
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit
        }
        
        # Convert datetime objects to timestamp
        if start_time:
            if isinstance(start_time, datetime):
                start_time = int(start_time.timestamp() * 1000)
            params["startTime"] = start_time
            
        if end_time:
            if isinstance(end_time, datetime):
                end_time = int(end_time.timestamp() * 1000)
            params["endTime"] = end_time
            
        data = await self._make_request(PUBLIC_ENDPOINTS["klines"], params)
        
        # Convert to DataFrame
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_volume",
            "taker_buy_quote_volume", "ignored"
        ])
        
        # Convert types
        numeric_columns = ["open", "high", "low", "close", "volume", "quote_volume", 
                          "taker_buy_volume", "taker_buy_quote_volume"]
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col])
            
        # Convert timestamp to datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
        
        # Set timestamp as index
        df.set_index("timestamp", inplace=True)
        
        # Drop unnecessary columns
        df.drop("ignored", axis=1, inplace=True)
        
        # Check data completeness if monitoring is enabled
        if self.enable_monitoring and self.monitor and start_time and end_time:
            # Convert timestamps to datetime if they're not already
            if isinstance(start_time, int):
                start_dt = datetime.fromtimestamp(start_time / 1000)
            elif isinstance(start_time, datetime):
                start_dt = start_time
                
            if isinstance(end_time, int):
                end_dt = datetime.fromtimestamp(end_time / 1000)
            elif isinstance(end_time, datetime):
                end_dt = end_time
                
            completeness = self.monitor.check_data_completeness(
                data=df,
                expected_interval=interval,
                start_time=start_dt,
                end_time=end_dt
            )
            
            # Log completeness info
            if completeness["completeness_pct"] < 100:
                logger.warning(
                    f"Data completeness for {symbol} {interval}: {completeness['completeness_pct']:.1f}% "
                    f"({completeness['missing_points']} missing points out of {completeness['expected_points']})"
                )
                
        return df
    
    async def fetch_trades(
        self,
        symbol: str,
        limit: int = 500
    ) -> pd.DataFrame:
        """
        Fetch recent trades.
        
        Args:
            symbol: Trading pair symbol
            limit: Maximum number of trades to return
            
        Returns:
            DataFrame with trade data
        """
        params = {
            "symbol": symbol.upper(),
            "limit": limit
        }
        
        data = await self._make_request(PUBLIC_ENDPOINTS["trades"], params)
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Convert types
        numeric_columns = ["price", "qty", "quoteQty"]
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col])
            
        # Convert timestamp to datetime
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        
        # Set timestamp as index
        df.set_index("time", inplace=True)
        
        return df
    
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch 24hr ticker.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Ticker data
        """
        params = {
            "symbol": symbol.upper()
        }
        
        return await self._make_request(PUBLIC_ENDPOINTS["ticker"], params)
    
    async def fetch_orderbook(
        self,
        symbol: str,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Fetch order book.
        
        Args:
            symbol: Trading pair symbol
            limit: Depth of the order book
            
        Returns:
            Order book data
        """
        params = {
            "symbol": symbol.upper(),
            "limit": limit
        }
        
        return await self._make_request(PUBLIC_ENDPOINTS["depth"], params)
    
    async def fetch_exchange_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch exchange information.
        
        Args:
            symbol: Optional specific symbol to get info for
            
        Returns:
            Exchange info
        """
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
            
        return await self._make_request(PUBLIC_ENDPOINTS["exchange_info"], params)
        
    def get_monitor_status(self) -> Optional[Dict[str, Any]]:
        """
        Get monitoring status report.
        
        Returns:
            Status report or None if monitoring is disabled
        """
        if self.enable_monitoring and self.monitor:
            return self.monitor.get_status_report()
        return None


# Example usage
async def example_usage():
    """Example of using the BinanceCollector."""
    # Create collector
    collector = BinanceCollector(symbols=["BTCUSDT", "ETHUSDT"])
    
    try:
        # Start collector
        await collector.start()
        
        # Fetch OHLCV data
        btc_klines = await collector.fetch_klines("BTCUSDT", "1h", limit=10)
        print(f"BTCUSDT 1h klines:\n{btc_klines}")
        
        # Subscribe to WebSocket streams
        await collector.subscribe_ws("trade", "btcusdt", callback=lambda msg: print(f"Trade: {msg}"))
        await collector.subscribe_ws("kline", "ethusdt", timeframe="1m", 
                                    callback=lambda msg: print(f"Kline: {msg}"))
        
        # Wait for some WebSocket messages
        await asyncio.sleep(10)
        
        # Get monitoring status
        status = collector.get_monitor_status()
        if status:
            print(f"Monitoring status: {status}")
        
    finally:
        # Clean up
        await collector.stop()
        

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_usage()) 