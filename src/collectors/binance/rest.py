"""
Binance REST API client.

This module implements a client for the Binance REST API with rate limiting,
error handling, and request retry functionality.
"""

import asyncio
import hashlib
import hmac
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode

import aiohttp
import pandas as pd
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential
)

from .binance.constants import (
    BASE_URL,
    HTTP_STATUS_RETRY,
    RATE_LIMITS,
    REST_API,
    RETRY_ERRORS,
    TIMEFRAMES,
)


logger = logging.getLogger(__name__)


class BinanceAPIError(Exception):
    """Exception raised for Binance API errors."""
    
    def __init__(self, status_code: int, response: Dict[str, Any]):
        """
        Initialize the exception.
        
        Args:
            status_code: HTTP status code
            response: Response body
        """
        self.status_code = status_code
        self.code = response.get("code", 0)
        self.msg = response.get("msg", "Unknown error")
        super().__init__(f"Binance API error {status_code} ({self.code}): {self.msg}")


class BinanceRateLimiter:
    """
    Rate limiter for Binance API requests.
    
    Implements a token bucket algorithm for each limit type.
    """
    
    def __init__(self):
        """Initialize the rate limiter."""
        self._buckets = {}
        self._init_buckets()
        
    def _init_buckets(self):
        """Initialize token buckets for each limit type."""
        for limit_type, config in RATE_LIMITS.items():
            # Each bucket is a tuple of (tokens, last_refill_time)
            self._buckets[limit_type] = (config["limit"], time.time())
            
    async def acquire(self, limit_type: str = "REQUEST_WEIGHT", weight: int = 1):
        """
        Acquire tokens from a bucket.
        
        Args:
            limit_type: Type of rate limit
            weight: Weight of the request
            
        Raises:
            asyncio.TimeoutError: If unable to acquire within timeout
        """
        if limit_type not in self._buckets:
            logger.warning(f"Unknown limit type: {limit_type}")
            return
            
        while True:
            # Refill the bucket
            tokens, last_refill = self._buckets[limit_type]
            now = time.time()
            
            # Calculate tokens to add based on time elapsed
            config = RATE_LIMITS[limit_type]
            elapsed = now - last_refill
            new_tokens = elapsed * (config["limit"] / config["interval"])
            
            # Update bucket
            tokens = min(tokens + new_tokens, config["limit"])
            last_refill = now
            
            if tokens >= weight:
                # We have enough tokens, consume them
                tokens -= weight
                self._buckets[limit_type] = (tokens, last_refill)
                return
                
            # Calculate wait time until we have enough tokens
            wait_time = (weight - tokens) * (config["interval"] / config["limit"])
            logger.debug(f"Rate limit reached for {limit_type}, waiting {wait_time:.2f}s")
            
            # Wait until we have enough tokens
            await asyncio.sleep(wait_time)


class BinanceRESTClient:
    """
    Binance REST API client.
    
    Handles API requests with rate limiting, authentication, error handling, and retries.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: str = BASE_URL,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        """
        Initialize the client.
        
        Args:
            api_key: Binance API key for authenticated requests
            api_secret: Binance API secret for authenticated requests
            base_url: Base URL for API requests
            session: aiohttp session to use for requests
        """
        self.api_key = api_key
        self.api_secret = api_secret.encode() if api_secret else None
        self.base_url = base_url
        
        self._session = session
        self._own_session = False
        self._limiter = BinanceRateLimiter()
        
    async def __aenter__(self):
        """Set up the client when used as an async context manager."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._own_session = True
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up the client when exiting the async context manager."""
        if self._own_session and self._session is not None:
            await self._session.close()
            self._session = None
            
    def _get_headers(self) -> Dict[str, str]:
        """
        Get request headers.
        
        Returns:
            Headers dictionary
        """
        headers = {
            "Accept": "application/json",
            "User-Agent": "binance-collector/1.0"
        }
        
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key
            
        return headers
        
    def _get_signature(self, params: Dict[str, Any]) -> str:
        """
        Generate signature for authenticated requests.
        
        Args:
            params: Request parameters
            
        Returns:
            HMAC SHA256 signature
        """
        if not self.api_secret:
            raise ValueError("API secret is required for authenticated requests")
            
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret,
            query_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return signature
        
    @retry(
        retry=retry_if_exception_type(
            (aiohttp.ClientError, asyncio.TimeoutError, BinanceAPIError)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        authenticated: bool = False,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        weight: int = 1,
    ) -> Any:
        """
        Make an API request.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            authenticated: Whether the request requires authentication
            params: Query parameters
            data: Request body data
            headers: Additional headers
            weight: Request weight for rate limiting
            
        Returns:
            Response data
            
        Raises:
            BinanceAPIError: If the API returns an error
            aiohttp.ClientError: If there's a network error
        """
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._own_session = True
            
        url = f"{self.base_url}{endpoint}"
        
        # Prepare headers
        request_headers = self._get_headers()
        if headers:
            request_headers.update(headers)
            
        # Prepare parameters
        request_params = params or {}
        
        if authenticated:
            # Add timestamp
            request_params["timestamp"] = int(time.time() * 1000)
            
            # Generate signature
            signature = self._get_signature(request_params)
            request_params["signature"] = signature
            
        # Acquire rate limit token
        await self._limiter.acquire(weight=weight)
        
        try:
            async with self._session.request(
                method=method,
                url=url,
                params=request_params,
                json=data,
                headers=request_headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response_data = await response.json()
                
                if response.status != 200:
                    error = BinanceAPIError(response.status, response_data)
                    
                    # Check if we should retry
                    if response.status in HTTP_STATUS_RETRY or (
                        isinstance(response_data, dict) and 
                        response_data.get("code") in RETRY_ERRORS
                    ):
                        logger.warning(f"Retryable error: {error}")
                        raise error
                    else:
                        logger.error(f"API error: {error}")
                        raise error
                        
                return response_data
                
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(f"Request error: {e}")
            raise
            
    async def get_server_time(self) -> int:
        """
        Get server time.
        
        Returns:
            Server time in milliseconds
        """
        data = await self._request(
            method="GET",
            endpoint=REST_API["server_time"],
            weight=1
        )
        return data["serverTime"]
        
    async def get_exchange_info(self) -> Dict[str, Any]:
        """
        Get exchange information.
        
        Returns:
            Exchange information
        """
        return await self._request(
            method="GET",
            endpoint=REST_API["exchange_info"],
            weight=10
        )
        
    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get information for a specific symbol.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Symbol information
        """
        exchange_info = await self.get_exchange_info()
        
        for symbol_info in exchange_info["symbols"]:
            if symbol_info["symbol"] == symbol:
                return symbol_info
                
        return None
        
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500
    ) -> List[List[Any]]:
        """
        Get klines (candlestick data).
        
        Args:
            symbol: Trading pair symbol
            interval: Kline interval
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            limit: Maximum number of klines to return (max 1000)
            
        Returns:
            List of klines
        """
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1000)
        }
        
        if start_time:
            params["startTime"] = start_time
            
        if end_time:
            params["endTime"] = end_time
            
        # Weight depends on the limit
        weight = 1
        if limit > 100:
            weight = 2
        if limit > 500:
            weight = 5
            
        return await self._request(
            method="GET",
            endpoint=REST_API["klines"],
            params=params,
            weight=weight
        )
        
    def format_klines(self, klines: List[List[Any]]) -> pd.DataFrame:
        """
        Format klines data into a DataFrame.
        
        Args:
            klines: List of klines
            
        Returns:
            DataFrame with klines data
        """
        if not klines:
            return pd.DataFrame(
                columns=[
                    "timestamp", "open", "high", "low", "close", 
                    "volume", "close_time", "quote_volume", "trades",
                    "taker_buy_base_volume", "taker_buy_quote_volume", "ignored"
                ]
            )
            
        df = pd.DataFrame(
            klines,
            columns=[
                "timestamp", "open", "high", "low", "close", 
                "volume", "close_time", "quote_volume", "trades",
                "taker_buy_base_volume", "taker_buy_quote_volume", "ignored"
            ]
        )
        
        # Convert to appropriate types
        for col in ["open", "high", "low", "close", "volume", "quote_volume", 
                   "taker_buy_base_volume", "taker_buy_quote_volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            
        for col in ["timestamp", "close_time"]:
            df[col] = pd.to_datetime(df[col], unit="ms")
            
        df["trades"] = df["trades"].astype(int)
        
        # Drop the ignored column
        df = df.drop(columns=["ignored"])
        
        return df
        
    async def get_ohlcv(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500
    ) -> pd.DataFrame:
        """
        Get OHLCV data.
        
        Args:
            symbol: Trading pair symbol
            interval: Kline interval
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            limit: Maximum number of klines to return (max 1000)
            
        Returns:
            DataFrame with OHLCV data
        """
        klines = await self.get_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        return self.format_klines(klines)
        
    async def get_all_ohlcv(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000
    ) -> pd.DataFrame:
        """
        Get all OHLCV data in the specified time range.
        
        This method iteratively fetches klines to cover the entire time range.
        
        Args:
            symbol: Trading pair symbol
            interval: Kline interval
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            limit: Maximum number of klines to return per request
            
        Returns:
            DataFrame with OHLCV data
        """
        # If neither start_time nor end_time is provided, just fetch latest klines
        if start_time is None and end_time is None:
            return await self.get_ohlcv(
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
        end_time = end_time or int(time.time() * 1000)
        
        if start_time is None:
            # Calculate a start time based on the end time and interval
            duration = limit * TIMEFRAMES[interval] * 1000
            start_time = end_time - duration
            
        all_klines = []
        current_start = start_time
        
        # Fetch klines until we've covered the entire time range
        while current_start < end_time:
            klines = await self.get_klines(
                symbol=symbol,
                interval=interval,
                start_time=current_start,
                end_time=end_time,
                limit=limit
            )
            
            if not klines:
                break
                
            all_klines.extend(klines)
            
            # Update the start time for the next request
            # Add 1ms to avoid duplicates
            current_start = klines[-1][0] + 1
            
            # If we got fewer klines than the limit, we've reached the end
            if len(klines) < limit:
                break
                
            # Avoid rate limiting
            await asyncio.sleep(0.1)
            
        return self.format_klines(all_klines)
        
    async def get_trades(
        self,
        symbol: str,
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """
        Get recent trades.
        
        Args:
            symbol: Trading pair symbol
            limit: Maximum number of trades to return (max 1000)
            
        Returns:
            List of trades
        """
        params = {
            "symbol": symbol,
            "limit": min(limit, 1000)
        }
        
        # Weight depends on the limit
        weight = 1
        if limit > 100:
            weight = 2
        if limit > 500:
            weight = 5
            
        return await self._request(
            method="GET",
            endpoint=REST_API["trades"],
            params=params,
            weight=weight
        )
        
    async def get_historical_trades(
        self,
        symbol: str,
        limit: int = 500,
        from_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get historical trades.
        
        Args:
            symbol: Trading pair symbol
            limit: Maximum number of trades to return (max 1000)
            from_id: Trade ID to fetch from
            
        Returns:
            List of trades
            
        Note:
            This endpoint requires API key.
        """
        if not self.api_key:
            raise ValueError("API key is required for historical trades")
            
        params = {
            "symbol": symbol,
            "limit": min(limit, 1000)
        }
        
        if from_id:
            params["fromId"] = from_id
            
        return await self._request(
            method="GET",
            endpoint=REST_API["historical_trades"],
            params=params,
            weight=5
        )
        
    def format_trades(self, trades: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Format trades data into a DataFrame.
        
        Args:
            trades: List of trades
            
        Returns:
            DataFrame with trades data
        """
        if not trades:
            return pd.DataFrame(
                columns=[
                    "id", "price", "qty", "quoteQty", "time", 
                    "isBuyerMaker", "isBestMatch"
                ]
            )
            
        df = pd.DataFrame(trades)
        
        # Convert to appropriate types
        for col in ["price", "qty", "quoteQty"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], unit="ms")
            
        for col in ["isBuyerMaker", "isBestMatch"]:
            if col in df.columns:
                df[col] = df[col].astype(bool)
                
        return df
        
    async def get_all_trades(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000
    ) -> pd.DataFrame:
        """
        Get all trades in the specified time range.
        
        This method iteratively fetches trades to cover the entire time range.
        
        Args:
            symbol: Trading pair symbol
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            limit: Maximum number of trades to return per request
            
        Returns:
            DataFrame with trades data
            
        Note:
            This method uses the aggTrades endpoint which requires different handling.
        """
        params = {
            "symbol": symbol,
            "limit": min(limit, 1000)
        }
        
        if start_time:
            params["startTime"] = start_time
            
        if end_time:
            params["endTime"] = end_time
            
        all_trades = []
        current_start = start_time
        
        while True:
            # Update params with the current start time
            if current_start:
                params["startTime"] = current_start
                
            trades = await self._request(
                method="GET",
                endpoint=REST_API["agg_trades"],
                params=params,
                weight=1
            )
            
            if not trades:
                break
                
            all_trades.extend(trades)
            
            # Update the start time for the next request
            # Add 1ms to avoid duplicates
            current_start = trades[-1]["T"] + 1
            
            # If we got fewer trades than the limit, we've reached the end
            if len(trades) < limit:
                break
                
            # If we've reached the end time, we're done
            if end_time and current_start >= end_time:
                break
                
            # Avoid rate limiting
            await asyncio.sleep(0.1)
            
        # Format the trades
        if not all_trades:
            return pd.DataFrame(
                columns=[
                    "a", "p", "q", "f", "l", "T", "m", "M"
                ]
            )
            
        df = pd.DataFrame(all_trades)
        
        # Rename columns for clarity
        df.rename(
            columns={
                "a": "aggregated_trade_id",
                "p": "price",
                "q": "quantity",
                "f": "first_trade_id",
                "l": "last_trade_id",
                "T": "timestamp",
                "m": "is_buyer_maker",
                "M": "is_best_price_match"
            },
            inplace=True
        )
        
        # Convert to appropriate types
        for col in ["price", "quantity"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        
        for col in ["is_buyer_maker", "is_best_price_match"]:
            df[col] = df[col].astype(bool)
            
        return df
        
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get ticker for a symbol.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Ticker data
        """
        params = {"symbol": symbol}
        
        return await self._request(
            method="GET",
            endpoint=REST_API["ticker"],
            params=params,
            weight=1
        )
        
    async def get_all_tickers(self) -> List[Dict[str, Any]]:
        """
        Get tickers for all symbols.
        
        Returns:
            List of ticker data
        """
        return await self._request(
            method="GET",
            endpoint=REST_API["ticker"],
            weight=2
        )
        
    async def get_order_book(
        self,
        symbol: str,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get order book for a symbol.
        
        Args:
            symbol: Trading pair symbol
            limit: Number of price levels to include (5, 10, 20, 50, 100, 500, 1000, 5000)
            
        Returns:
            Order book data
        """
        valid_limits = [5, 10, 20, 50, 100, 500, 1000, 5000]
        if limit not in valid_limits:
            limit = min(valid_limits, key=lambda x: abs(x - limit))
            logger.warning(f"Invalid limit, using {limit} instead")
            
        params = {
            "symbol": symbol,
            "limit": limit
        }
        
        # Weight depends on the limit
        weight = 1
        if limit > 100:
            weight = 5
        if limit > 1000:
            weight = 10
            
        return await self._request(
            method="GET",
            endpoint=REST_API["depth"],
            params=params,
            weight=weight
        )
        
    def format_order_book(self, order_book: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format order book data.
        
        Args:
            order_book: Order book data
            
        Returns:
            Formatted order book data
        """
        result = {
            "lastUpdateId": order_book["lastUpdateId"],
            "bids": [],
            "asks": []
        }
        
        # Format bids
        for price, qty in order_book["bids"]:
            result["bids"].append({
                "price": float(price),
                "quantity": float(qty)
            })
            
        # Format asks
        for price, qty in order_book["asks"]:
            result["asks"].append({
                "price": float(price),
                "quantity": float(qty)
            })
            
        return result
        
    async def get_account(self) -> Dict[str, Any]:
        """
        Get account information.
        
        Returns:
            Account information
            
        Note:
            This endpoint requires API key and secret.
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret are required for account info")
            
        return await self._request(
            method="GET",
            endpoint=REST_API["account"],
            authenticated=True,
            weight=10
        )
        
    async def get_exchange_status(self) -> Dict[str, Any]:
        """
        Get exchange system status.
        
        Returns:
            System status
        """
        return await self._request(
            method="GET",
            endpoint=REST_API["system_status"],
            weight=1
        ) 