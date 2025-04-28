"""
REST Transport Implementation for Exchange Communications

This module provides a REST-based transport implementation using CCXT
for communicating with cryptocurrency exchanges.
"""
import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Union, Callable, Tuple, TypeVar, Generic, cast
import ccxt.async_support as ccxt

from .transport.base import (
    TransportType,
    AuthType,
    ConnectionStatus,
    RequestMetadata,
    ResponseMetadata,
    Request,
    Response,
    RetryPolicy,
    BaseTransport,
    DefaultRetryPolicy
)

# Configure logger
logger = logging.getLogger(__name__)

class RESTTransport(BaseTransport):
    """
    REST transport implementation using CCXT.
    
    This class provides REST API transport functionality for cryptocurrency
    exchanges supported by the CCXT library.
    """
    
    def __init__(
        self,
        exchange: str,
        base_url: str,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        extra_auth: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_policy: Optional[RetryPolicy] = None,
        enable_rate_limit: bool = True,
        testnet: bool = False,
        exchange_options: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the REST transport.
        
        Args:
            exchange: Name of the exchange (must be supported by CCXT)
            base_url: Base URL for the exchange API (can be None to use CCXT default)
            api_key: API key for authentication
            api_secret: API secret for authentication
            extra_auth: Extra authentication parameters required by some exchanges
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            retry_policy: Policy for determining when to retry requests
            enable_rate_limit: Whether to enable rate limiting
            testnet: Whether to use the testnet
            exchange_options: Additional options to pass to the CCXT exchange constructor
        """
        # Initialize base class with the determined auth type
        auth_type = AuthType.API_KEY if api_key and api_secret else AuthType.NONE
        super().__init__(
            exchange=exchange,
            base_url=base_url,
            auth_type=auth_type,
            timeout=timeout,
            max_retries=max_retries,
            retry_policy=retry_policy or DefaultRetryPolicy(max_retries),
            enable_rate_limit=enable_rate_limit
        )
        
        # Store authentication credentials
        self.api_key = api_key
        self.api_secret = api_secret
        self.extra_auth = extra_auth or {}
        self.testnet = testnet
        
        # Exchange options
        self.exchange_options = exchange_options or {}
        
        # Store the CCXT client
        self.client = None
        self.exchange_id = self._normalize_exchange_id(exchange)
        
        # Active subscription callbacks (REST polling subscriptions)
        self.subscriptions = {}
        self.subscription_tasks = {}
    
    @property
    def transport_type(self) -> TransportType:
        """Get the transport type."""
        return TransportType.REST
    
    def _normalize_exchange_id(self, exchange: str) -> str:
        """
        Normalize the exchange ID to match CCXT's expected format.
        
        Args:
            exchange: Exchange name or ID
            
        Returns:
            Normalized exchange ID for CCXT
        """
        # Convert to lowercase and remove spaces
        exchange_id = exchange.lower().replace(' ', '')
        
        # Handle common aliases
        exchange_aliases = {
            'binance': 'binance',
            'binanceus': 'binanceus',
            'binancefutures': 'binanceusdm',
            'binancecoinm': 'binancecoinm',
            'kucoin': 'kucoin',
            'ftx': 'ftx',
            'bybit': 'bybit',
            'deribit': 'deribit'
        }
        
        return exchange_aliases.get(exchange_id, exchange_id)
    
    async def connect(self) -> bool:
        """
        Initialize the CCXT client and test the connection.
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
        try:
            self._update_status(ConnectionStatus.CONNECTING)
            
            # Prepare CCXT constructor options
            options = {
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'timeout': self.timeout * 1000,  # CCXT uses milliseconds
                'enableRateLimit': self.enable_rate_limit,
                'options': {
                    'adjustForTimeDifference': True
                }
            }
            
            # Add extra authentication parameters if provided
            if self.extra_auth:
                for key, value in self.extra_auth.items():
                    options[key] = value
            
            # Add custom URLs for testnet if needed
            if self.testnet:
                if self.exchange_id == 'binance':
                    options['urls'] = {
                        'api': {
                            'public': 'https://testnet.binance.vision/api/v3',
                            'private': 'https://testnet.binance.vision/api/v3',
                        }
                    }
                elif self.exchange_id == 'binanceusdm':
                    options['urls'] = {
                        'api': {
                            'public': 'https://testnet.binancefuture.com/fapi/v1',
                            'private': 'https://testnet.binancefuture.com/fapi/v1',
                        }
                    }
                # Add more exchange-specific testnet URLs as needed
            
            # Add custom base URL if provided
            if self.base_url:
                options['urls'] = options.get('urls', {})
                options['urls']['api'] = self.base_url
            
            # Add any additional exchange options
            options.update(self.exchange_options)
            
            # Get the CCXT exchange class
            exchange_class = getattr(ccxt, self.exchange_id)
            
            # Create the CCXT client
            self.client = exchange_class(options)
            
            # Load markets to validate connection
            await self.client.load_markets()
            
            # Test the connection
            await self.client.fetch_time()
            
            # Update connection status
            self._update_status(ConnectionStatus.CONNECTED)
            self.connected_since = time.time()
            
            logger.info(f"Connected to {self.exchange} REST API")
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to {self.exchange} REST API: {str(e)}")
            self._update_status(ConnectionStatus.ERROR, str(e))
            return False
    
    async def disconnect(self) -> bool:
        """
        Disconnect from the exchange API.
        
        Returns:
            bool: True if disconnection was successful, False otherwise
        """
        try:
            # Cancel any active subscription tasks
            for channel, task in self.subscription_tasks.items():
                if not task.done():
                    task.cancel()
            
            # Clear subscriptions
            self.subscriptions = {}
            self.subscription_tasks = {}
            
            # Close CCXT client
            if self.client:
                await self.client.close()
                self.client = None
            
            # Update status
            self._update_status(ConnectionStatus.DISCONNECTED)
            
            logger.info(f"Disconnected from {self.exchange} REST API")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from {self.exchange} REST API: {str(e)}")
            return False
    
    async def is_connected(self) -> bool:
        """
        Check if the transport is connected.
        
        Returns:
            bool: True if connected, False otherwise
        """
        if self.status != ConnectionStatus.CONNECTED or not self.client:
            return False
        
        try:
            # Perform a lightweight API call to verify connection
            await self.client.fetch_time()
            return True
        except Exception:
            return False
    
    async def send(self, request: Request) -> Response:
        """
        Send a request to the exchange API.
        
        Args:
            request: Request to send
            
        Returns:
            Response: Response from the exchange
        """
        if not self.client:
            await self.connect()
            if not self.client:
                return Response(
                    data=None,
                    metadata=ResponseMetadata(
                        status_code=500,
                        error="Not connected to the exchange API"
                    )
                )
        
        method = request.metadata.method.lower()
        endpoint = request.path.lstrip('/')
        params = request.params.copy()
        
        # Prepare the response metadata
        response_metadata = ResponseMetadata()
        response_metadata.timestamp = time.time()
        
        start_time = time.time()
        retry_count = 0
        last_exception = None
        
        while retry_count <= self.max_retries:
            try:
                # Build the method name dynamically based on CCXT patterns
                # Example: POST /api/v3/order becomes create_order or fetch_balance
                method_name = self._get_ccxt_method_name(method, endpoint)
                
                if not hasattr(self.client, method_name):
                    raise AttributeError(f"Method {method_name} not found in CCXT client")
                
                # Execute the CCXT method
                method_func = getattr(self.client, method_name)
                result = await method_func(**params)
                
                # Successful response
                response_metadata.status_code = 200
                response_metadata.latency = time.time() - start_time
                
                # Extract rate limit info from client if available
                if hasattr(self.client, 'last_response_headers'):
                    headers = getattr(self.client, 'last_response_headers', {})
                    response_metadata.rate_limit_info = self._extract_rate_limit_headers(headers)
                
                # Update metrics
                self.update_metrics(
                    latency=response_metadata.latency,
                    is_retry=(retry_count > 0)
                )
                
                return Response(
                    data=result,
                    metadata=response_metadata,
                    raw=result
                )
                
            except Exception as e:
                last_exception = e
                retry_count += 1
                
                # Prepare error response
                response_metadata.status_code = self._get_status_code_from_exception(e)
                response_metadata.error = str(e)
                response_metadata.latency = time.time() - start_time
                
                # Create response object
                response = Response(
                    data=None,
                    metadata=response_metadata
                )
                
                # Check if we should retry
                if not self.retry_policy or not self.retry_policy.should_retry(response, retry_count):
                    break
                
                # Get delay before retry
                delay = self.retry_policy.get_delay(response, retry_count)
                logger.warning(f"Retrying {method} {endpoint} in {delay:.2f}s (attempt {retry_count}/{self.max_retries})")
                
                # Wait before retrying
                await asyncio.sleep(delay)
        
        # Failed after retries or non-retryable error
        response_metadata.latency = time.time() - start_time
        self.update_metrics(
            latency=response_metadata.latency,
            is_error=True,
            is_retry=(retry_count > 1)
        )
        
        return Response(
            data=None,
            metadata=response_metadata,
            raw=last_exception
        )
    
    async def subscribe(self, channel: str, callback: Callable[[Response], None]) -> bool:
        """
        Subscribe to a REST-based data channel using polling.
        
        Args:
            channel: Channel to subscribe to (format: "method:endpoint:interval")
            callback: Function to call with received data
            
        Returns:
            bool: True if subscription was successful, False otherwise
        """
        # Parse subscription string
        try:
            method, endpoint, interval = channel.split(':')
            interval = float(interval)
        except ValueError:
            logger.error(f"Invalid subscription format: {channel}")
            return False
        
        # Store the subscription
        self.subscriptions[channel] = callback
        
        # Cancel existing subscription task if exists
        if channel in self.subscription_tasks and not self.subscription_tasks[channel].done():
            self.subscription_tasks[channel].cancel()
        
        # Create a new polling task
        self.subscription_tasks[channel] = asyncio.create_task(
            self._poll_subscription(method, endpoint, interval, callback)
        )
        
        logger.info(f"Subscribed to {channel}")
        return True
    
    async def unsubscribe(self, channel: str) -> bool:
        """
        Unsubscribe from a REST-based data channel.
        
        Args:
            channel: Channel to unsubscribe from
            
        Returns:
            bool: True if unsubscription was successful, False otherwise
        """
        if channel not in self.subscriptions:
            logger.warning(f"Not subscribed to {channel}")
            return False
        
        # Cancel the polling task
        if channel in self.subscription_tasks and not self.subscription_tasks[channel].done():
            self.subscription_tasks[channel].cancel()
            del self.subscription_tasks[channel]
        
        # Remove the subscription
        del self.subscriptions[channel]
        
        logger.info(f"Unsubscribed from {channel}")
        return True
    
    async def _poll_subscription(
        self, 
        method: str, 
        endpoint: str, 
        interval: float, 
        callback: Callable[[Response], None]
    ) -> None:
        """
        Poll an endpoint at regular intervals and call the callback with the results.
        
        Args:
            method: HTTP method to use
            endpoint: API endpoint to poll
            interval: Polling interval in seconds
            callback: Function to call with received data
        """
        channel = f"{method}:{endpoint}:{interval}"
        logger.debug(f"Starting polling for {channel}")
        
        while True:
            try:
                # Create request
                request = Request(
                    path=endpoint,
                    metadata=RequestMetadata(
                        method=method.upper(),
                        endpoint=endpoint
                    )
                )
                
                # Send request
                response = await self.send(request)
                
                # Call callback with response
                callback(response)
                
            except asyncio.CancelledError:
                logger.debug(f"Polling for {channel} cancelled")
                break
                
            except Exception as e:
                logger.error(f"Error polling {channel}: {str(e)}")
            
            # Wait for next poll
            await asyncio.sleep(interval)
    
    def _update_status(self, status: ConnectionStatus, reason: Optional[str] = None) -> None:
        """
        Update the connection status.
        
        Args:
            status: New status
            reason: Reason for status change
        """
        self.status = status
        self.disconnect_reason = reason
        
        if status == ConnectionStatus.CONNECTED:
            self.connected_since = time.time()
        elif status == ConnectionStatus.DISCONNECTED or status == ConnectionStatus.ERROR:
            self.connected_since = None
    
    def _get_ccxt_method_name(self, http_method: str, endpoint: str) -> str:
        """
        Map HTTP method and endpoint to CCXT method name.
        
        Args:
            http_method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint
            
        Returns:
            CCXT method name
        """
        # Check for known endpoints and map to CCXT methods
        
        # Markets and tickers
        if endpoint.endswith('/ticker') or 'ticker' in endpoint:
            return 'fetch_ticker'
        if endpoint.endswith('/tickers') or 'tickers' in endpoint:
            return 'fetch_tickers'
        if endpoint.endswith('/orderbook') or 'orderbook' in endpoint or 'depth' in endpoint:
            return 'fetch_order_book'
        if endpoint.endswith('/trades') or 'trades' in endpoint:
            return 'fetch_trades'
        if endpoint.endswith('/ohlcv') or 'klines' in endpoint:
            return 'fetch_ohlcv'
        if endpoint.endswith('/markets') or 'exchange-info' in endpoint:
            return 'fetch_markets'
        
        # Trading methods
        if http_method == 'post' and ('order' in endpoint):
            return 'create_order'
        if http_method == 'delete' and ('order' in endpoint):
            return 'cancel_order'
        if http_method == 'get' and ('order' in endpoint) and 'orders' not in endpoint:
            return 'fetch_order'
        if 'open' in endpoint and 'orders' in endpoint:
            return 'fetch_open_orders'
        if endpoint.endswith('/orders') or 'allorders' in endpoint:
            return 'fetch_orders'
        if 'myTrades' in endpoint or 'my-trades' in endpoint:
            return 'fetch_my_trades'
        
        # Account methods
        if 'balance' in endpoint or 'account' in endpoint:
            return 'fetch_balance'
        
        # Fallback to HTTP method prefix
        method_prefixes = {
            'get': 'fetch',
            'post': 'create',
            'put': 'update',
            'delete': 'cancel'
        }
        
        # Default to endpoint-based name
        prefix = method_prefixes.get(http_method, 'fetch')
        endpoint_parts = endpoint.strip('/').split('/')
        endpoint_name = endpoint_parts[-1] if endpoint_parts else endpoint
        
        # Convert endpoint to camelCase
        parts = endpoint_name.replace('-', '_').split('_')
        endpoint_name = parts[0] + ''.join(p.title() for p in parts[1:])
        
        return f"{prefix}_{endpoint_name}"
    
    def _extract_rate_limit_headers(self, headers: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract rate limit information from response headers.
        
        Args:
            headers: Response headers
            
        Returns:
            Dictionary of rate limit information
        """
        rate_limit_info = {}
        
        # Binance rate limit headers
        if 'x-mbx-used-weight' in headers:
            rate_limit_info['used_weight'] = int(headers['x-mbx-used-weight'])
        if 'x-mbx-used-weight-1m' in headers:
            rate_limit_info['used_weight_1m'] = int(headers['x-mbx-used-weight-1m'])
        if 'x-mbx-order-count-1m' in headers:
            rate_limit_info['order_count_1m'] = int(headers['x-mbx-order-count-1m'])
        if 'x-mbx-order-count-10s' in headers:
            rate_limit_info['order_count_10s'] = int(headers['x-mbx-order-count-10s'])
        if 'retry-after' in headers:
            rate_limit_info['retry_after'] = int(headers['retry-after'])
        
        # Coinbase rate limit headers
        if 'cb-before' in headers:
            rate_limit_info['cb_before'] = headers['cb-before']
        if 'cb-after' in headers:
            rate_limit_info['cb_after'] = headers['cb-after']
        
        # General rate limit headers
        if 'x-ratelimit-limit' in headers:
            rate_limit_info['limit'] = int(headers['x-ratelimit-limit'])
        if 'x-ratelimit-remaining' in headers:
            rate_limit_info['remaining'] = int(headers['x-ratelimit-remaining'])
        if 'x-ratelimit-reset' in headers:
            rate_limit_info['reset'] = int(headers['x-ratelimit-reset'])
        
        return rate_limit_info
    
    def _get_status_code_from_exception(self, exception: Exception) -> int:
        """
        Extract HTTP status code from a CCXT exception.
        
        Args:
            exception: CCXT exception
            
        Returns:
            HTTP status code
        """
        if hasattr(exception, 'code') and isinstance(getattr(exception, 'code'), int):
            return getattr(exception, 'code')
        
        # Some common error strings
        error_str = str(exception).lower()
        if 'timeout' in error_str:
            return 408  # Request Timeout
        if 'rate limit' in error_str or 'ratelimit' in error_str:
            return 429  # Too Many Requests
        if 'unauthorized' in error_str:
            return 401  # Unauthorized
        if 'forbidden' in error_str:
            return 403  # Forbidden
        if 'not found' in error_str:
            return 404  # Not Found
        if 'bad request' in error_str:
            return 400  # Bad Request
        
        # Default to internal server error
        return 500 