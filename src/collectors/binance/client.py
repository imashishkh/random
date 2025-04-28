"""
Binance REST API client.

This module contains the client implementation for interacting with
the Binance REST API for spot trading and market data.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

import aiohttp

from .constants import (
    BASE_URL,
    ENDPOINTS,
    RETRY_CODES,
    RETRY_ERRORS,
    RETRY_HTTP_CODES
)


logger = logging.getLogger(__name__)


class BinanceClientError(Exception):
    """
    Exception raised for Binance API errors.
    
    Attributes:
        code: Error code
        message: Error message
    """
    
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Binance API error {code}: {message}")


class BinanceClient:
    """
    Client for the Binance REST API.
    
    Handles API requests, authentication, rate limiting, and error handling.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: str = BASE_URL,
        request_timeout: float = 10.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        session: Optional[aiohttp.ClientSession] = None
    ):
        """
        Initialize the Binance client.
        
        Args:
            api_key: Binance API key for authenticated endpoints
            api_secret: Binance API secret for authenticated endpoints
            base_url: Base URL for the Binance API
            request_timeout: Timeout for API requests in seconds
            max_retries: Maximum number of retries for failed requests
            retry_delay: Initial delay between retries in seconds
            session: Optional aiohttp ClientSession to use for requests
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Use provided session or create a new one
        self._session = session
        self._own_session = session is None
        
        # Track API call statistics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.retried_requests = 0
    
    async def __aenter__(self):
        """
        Set up the client when used as an async context manager.
        """
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Clean up the client when exiting the async context manager.
        """
        await self.close()
    
    async def close(self):
        """
        Close the aiohttp session if we created it.
        """
        if self._own_session and self._session is not None:
            await self._session.close()
            self._session = None
    
    def _get_session(self) -> aiohttp.ClientSession:
        """
        Get the aiohttp session, creating one if needed.
        
        Returns:
            aiohttp.ClientSession: The session to use for requests
        """
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._own_session = True
        return self._session
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """
        Generate the HMAC-SHA256 signature for authenticated requests.
        
        Args:
            params: Request parameters to sign
            
        Returns:
            Signature string
        """
        if not self.api_secret:
            raise ValueError("API secret is required for authenticated endpoints")
        
        # Convert to query string
        query_string = urlencode(params)
        
        # Create signature
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def _add_auth_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        Add authentication headers to the request.
        
        Args:
            headers: Existing headers
            
        Returns:
            Headers with authentication added
        """
        if not self.api_key:
            raise ValueError("API key is required for authenticated endpoints")
        
        headers['X-MBX-APIKEY'] = self.api_key
        return headers
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        authenticated: bool = False,
        api_version: str = 'v3'
    ) -> Any:
        """
        Make an HTTP request to the Binance API.
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint
            params: URL parameters
            data: Request body data
            headers: HTTP headers
            authenticated: Whether this is an authenticated request
            api_version: API version to use
            
        Returns:
            API response data
            
        Raises:
            BinanceClientError: If the API returns an error
            aiohttp.ClientError: For network-related errors
        """
        params = params or {}
        headers = headers or {}
        
        # Full URL
        url = f"{self.base_url}/{api_version}/{endpoint}"
        
        # Add timestamp for authenticated requests
        if authenticated:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._generate_signature(params)
            headers = self._add_auth_headers(headers)
        
        session = self._get_session()
        
        # Track total requests
        self.total_requests += 1
        
        # Implement retry logic
        retries = 0
        while True:
            try:
                async with session.request(
                    method,
                    url,
                    params=params,
                    json=data,
                    headers=headers,
                    timeout=self.request_timeout
                ) as response:
                    # Handle error responses
                    if response.status >= 400:
                        # Get error details if possible
                        try:
                            error_data = await response.json()
                            if 'code' in error_data and 'msg' in error_data:
                                error_code = error_data['code']
                                error_msg = error_data['msg']
                                
                                # Check if this error is retryable
                                if (error_code in RETRY_ERRORS and 
                                    retries < self.max_retries):
                                    retries += 1
                                    self.retried_requests += 1
                                    wait_time = self.retry_delay * (2 ** (retries - 1))
                                    logger.warning(
                                        f"Retryable error {error_code}: {error_msg}. "
                                        f"Retrying in {wait_time:.2f}s ({retries}/{self.max_retries})"
                                    )
                                    await asyncio.sleep(wait_time)
                                    continue
                                
                                # Not retryable or max retries reached
                                self.failed_requests += 1
                                raise BinanceClientError(error_code, error_msg)
                        except (json.JSONDecodeError, KeyError):
                            pass
                        
                        # Check if HTTP status is retryable
                        if (response.status in RETRY_HTTP_CODES and 
                            retries < self.max_retries):
                            retries += 1
                            self.retried_requests += 1
                            wait_time = self.retry_delay * (2 ** (retries - 1))
                            logger.warning(
                                f"Retryable HTTP status {response.status}. "
                                f"Retrying in {wait_time:.2f}s ({retries}/{self.max_retries})"
                            )
                            await asyncio.sleep(wait_time)
                            continue
                        
                        # Not retryable or max retries reached
                        self.failed_requests += 1
                        response.raise_for_status()
                    
                    # Parse JSON response
                    response_data = await response.json()
                    self.successful_requests += 1
                    return response_data
                    
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                # Retry on network errors
                if retries < self.max_retries:
                    retries += 1
                    self.retried_requests += 1
                    wait_time = self.retry_delay * (2 ** (retries - 1))
                    logger.warning(
                        f"Network error: {str(e)}. "
                        f"Retrying in {wait_time:.2f}s ({retries}/{self.max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                
                # Max retries reached
                self.failed_requests += 1
                raise
    
    # Public API endpoints
    
    async def get_server_time(self) -> int:
        """
        Get the current server time from Binance.
        
        Returns:
            Server timestamp in milliseconds
        """
        response = await self._make_request('GET', ENDPOINTS['server_time'])
        return response['serverTime']
    
    async def get_exchange_info(self) -> Dict[str, Any]:
        """
        Get exchange information including rate limits and symbol information.
        
        Returns:
            Exchange information
        """
        return await self._make_request('GET', ENDPOINTS['exchange_info'])
    
    async def get_symbols(self) -> List[str]:
        """
        Get a list of all available trading symbols.
        
        Returns:
            List of symbol strings
        """
        exchange_info = await self.get_exchange_info()
        return [symbol['symbol'] for symbol in exchange_info['symbols']]
    
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        startTime: Optional[int] = None,
        endTime: Optional[int] = None
    ) -> List[List[Any]]:
        """
        Get candlestick data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            interval: Candlestick interval (e.g. 1m, 5m, 1h)
            limit: Number of candles to return (max 1000)
            startTime: Start time in milliseconds
            endTime: End time in milliseconds
            
        Returns:
            List of candles where each candle is a list of values
        """
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': min(limit, 1000)  # Max 1000 candles per request
        }
        
        if startTime:
            params['startTime'] = startTime
        
        if endTime:
            params['endTime'] = endTime
        
        return await self._make_request('GET', ENDPOINTS['klines'], params=params)
    
    async def get_ticker_24hr(self, symbol: Optional[str] = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Get 24hr ticker statistics.
        
        Args:
            symbol: Trading pair symbol or None for all symbols
            
        Returns:
            Ticker statistics for one symbol or a list for all symbols
        """
        params = {}
        if symbol:
            params['symbol'] = symbol
        
        return await self._make_request('GET', ENDPOINTS['ticker_24hr'], params=params)
    
    async def get_ticker_price(self, symbol: Optional[str] = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Get latest price for a symbol or all symbols.
        
        Args:
            symbol: Trading pair symbol or None for all symbols
            
        Returns:
            Latest price data
        """
        params = {}
        if symbol:
            params['symbol'] = symbol
        
        return await self._make_request('GET', ENDPOINTS['ticker_price'], params=params)
    
    async def get_order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """
        Get order book for a symbol.
        
        Args:
            symbol: Trading pair symbol
            limit: Depth of the order book (max 5000)
            
        Returns:
            Order book data
        """
        valid_limits = [5, 10, 20, 50, 100, 500, 1000, 5000]
        # Find the closest valid limit
        actual_limit = min(valid_limits, key=lambda x: abs(x - limit))
        
        params = {
            'symbol': symbol,
            'limit': actual_limit
        }
        
        return await self._make_request('GET', ENDPOINTS['order_book'], params=params)
    
    # Authenticated API endpoints
    
    async def get_account(self) -> Dict[str, Any]:
        """
        Get account information.
        
        Returns:
            Account information
            
        Requires:
            API key and secret
        """
        return await self._make_request('GET', ENDPOINTS['account'], authenticated=True)
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all open orders for a symbol or all symbols.
        
        Args:
            symbol: Trading pair symbol or None for all symbols
            
        Returns:
            List of open orders
            
        Requires:
            API key and secret
        """
        params = {}
        if symbol:
            params['symbol'] = symbol
        
        return await self._make_request('GET', ENDPOINTS['open_orders'], params=params, authenticated=True)
    
    async def get_order(
        self,
        symbol: str,
        orderId: Optional[int] = None,
        origClientOrderId: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get order status.
        
        Args:
            symbol: Trading pair symbol
            orderId: Order ID
            origClientOrderId: Original client order ID
            
        Returns:
            Order information
            
        Requires:
            API key and secret
        """
        params = {'symbol': symbol}
        
        if orderId:
            params['orderId'] = orderId
        elif origClientOrderId:
            params['origClientOrderId'] = origClientOrderId
        else:
            raise ValueError("Either orderId or origClientOrderId must be provided")
        
        return await self._make_request('GET', ENDPOINTS['order'], params=params, authenticated=True)
    
    async def create_order(
        self,
        symbol: str,
        side: str,
        type: str,
        timeInForce: Optional[str] = None,
        quantity: Optional[float] = None,
        quoteOrderQty: Optional[float] = None,
        price: Optional[float] = None,
        newClientOrderId: Optional[str] = None,
        stopPrice: Optional[float] = None,
        icebergQty: Optional[float] = None,
        newOrderRespType: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new order.
        
        Args:
            symbol: Trading pair symbol
            side: Order side (BUY or SELL)
            type: Order type (LIMIT, MARKET, STOP_LOSS, etc.)
            timeInForce: Time in force (GTC, IOC, FOK)
            quantity: Order quantity
            quoteOrderQty: Quote order quantity (for MARKET orders)
            price: Order price
            newClientOrderId: Client order ID
            stopPrice: Stop price
            icebergQty: Iceberg quantity
            newOrderRespType: Response type (ACK, RESULT, FULL)
            
        Returns:
            Order creation response
            
        Requires:
            API key and secret
        """
        params = {
            'symbol': symbol,
            'side': side,
            'type': type
        }
        
        # Add optional parameters if provided
        if timeInForce:
            params['timeInForce'] = timeInForce
        
        if quantity:
            params['quantity'] = quantity
        
        if quoteOrderQty:
            params['quoteOrderQty'] = quoteOrderQty
        
        if price:
            params['price'] = price
        
        if newClientOrderId:
            params['newClientOrderId'] = newClientOrderId
        
        if stopPrice:
            params['stopPrice'] = stopPrice
        
        if icebergQty:
            params['icebergQty'] = icebergQty
        
        if newOrderRespType:
            params['newOrderRespType'] = newOrderRespType
        
        return await self._make_request('POST', ENDPOINTS['order'], params=params, authenticated=True)
    
    async def cancel_order(
        self,
        symbol: str,
        orderId: Optional[int] = None,
        origClientOrderId: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel an active order.
        
        Args:
            symbol: Trading pair symbol
            orderId: Order ID
            origClientOrderId: Original client order ID
            
        Returns:
            Cancellation confirmation
            
        Requires:
            API key and secret
        """
        params = {'symbol': symbol}
        
        if orderId:
            params['orderId'] = orderId
        elif origClientOrderId:
            params['origClientOrderId'] = origClientOrderId
        else:
            raise ValueError("Either orderId or origClientOrderId must be provided")
        
        return await self._make_request('DELETE', ENDPOINTS['order'], params=params, authenticated=True) 