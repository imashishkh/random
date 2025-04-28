"""
Advanced Rate Limiter for Exchange Communications

This module provides enhanced rate limiting functionality for exchange API
communications with support for different rate limit types, weights, and
dynamic adjustment based on exchange responses.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Tuple, Callable, Awaitable
import aiohttp

# Configure logger
logger = logging.getLogger(__name__)


class RateLimitType(Enum):
    """Type of rate limit enforced by an exchange."""
    REQUESTS = "requests"  # Limit based on number of requests
    WEIGHT = "weight"      # Limit based on request weight
    ORDERS = "orders"      # Limit specifically for order operations
    TRADING = "trading"    # Limit specifically for trading operations


@dataclass
class RateLimit:
    """Represents a rate limit for an exchange endpoint."""
    limit_type: RateLimitType
    limit: int
    window_ms: int
    scope: str = "global"  # global, ip, uid, market, etc.
    endpoint: Optional[str] = None  # Specific endpoint or None for all
    weight_map: Dict[str, int] = field(default_factory=dict)  # Method -> weight mapping
    current_usage: int = 0
    reset_time: float = field(default_factory=time.time)
    
    def __post_init__(self):
        """Initialize with the current time if reset_time is not set."""
        if not self.weight_map:
            # Default weight is 1 for all methods if not specified
            self.weight_map = {"DEFAULT": 1}
        
        # Ensure reset_time is a timestamp
        if isinstance(self.reset_time, time.struct_time):
            self.reset_time = time.mktime(self.reset_time)


class RateLimiter:
    """
    Advanced rate limiter for exchange API communications.
    
    Features:
    - Supports multiple rate limit types (requests, weights, orders)
    - Handles per-endpoint and global rate limits
    - Dynamically adjusts based on exchange response headers
    - Provides retry and throttling mechanisms
    """
    
    def __init__(
        self,
        exchange: str,
        default_rate_limits: Optional[List[RateLimit]] = None,
        safety_factor: float = 0.95,  # Use 95% of available rate limits by default
        retry_after_ms: int = 500,
        max_retries: int = 3,
        enabled: bool = True
    ):
        """
        Initialize the rate limiter.
        
        Args:
            exchange: Name of the exchange
            default_rate_limits: List of rate limits to apply
            safety_factor: Factor to multiply rate limits by (0.0-1.0)
            retry_after_ms: Time to wait before retrying when rate limited (ms)
            max_retries: Maximum number of retries before giving up
            enabled: Whether rate limiting is enabled
        """
        self.exchange = exchange.lower()
        self.rate_limits = default_rate_limits or []
        self.safety_factor = max(0.0, min(1.0, safety_factor))  # Clamp between 0 and 1
        self.retry_after_ms = retry_after_ms
        self.max_retries = max_retries
        self.enabled = enabled
        self.locked_endpoints: Set[str] = set()
        self.last_request_time: Dict[str, float] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        
        # Add exchange-specific default rate limits if none provided
        if not default_rate_limits:
            self._add_exchange_defaults()
    
    def _add_exchange_defaults(self):
        """Add default rate limits based on the exchange."""
        if self.exchange == 'binance':
            # Binance rate limits (as of 2024)
            self.rate_limits.extend([
                RateLimit(
                    limit_type=RateLimitType.WEIGHT,
                    limit=1200,
                    window_ms=60000,  # 1 minute
                    scope="ip"
                ),
                RateLimit(
                    limit_type=RateLimitType.REQUESTS,
                    limit=50,
                    window_ms=10000,  # 10 seconds
                    endpoint="/api/v3/order",
                    scope="ip"
                ),
                # Example weight map for specific endpoints
                RateLimit(
                    limit_type=RateLimitType.WEIGHT,
                    limit=100,
                    window_ms=10000,
                    endpoint="/api/v3/klines",
                    weight_map={
                        "GET": 1,  # Default weight 
                        "GET_MANY": 2,  # Weight when requesting multiple candles
                        "GET_MAX": 5,  # Weight when requesting max candles
                    }
                )
            ])
        elif self.exchange == 'coinbase':
            # Coinbase Pro rate limits
            self.rate_limits.append(
                RateLimit(
                    limit_type=RateLimitType.REQUESTS,
                    limit=3,
                    window_ms=1000,  # 3 requests per second
                    scope="ip"
                )
            )
        elif self.exchange == 'ftx':
            # FTX rate limits
            self.rate_limits.extend([
                RateLimit(
                    limit_type=RateLimitType.REQUESTS,
                    limit=30,
                    window_ms=1000,  # 30 requests per second
                    scope="ip"
                )
            ])
        else:
            # Default conservative rate limit for unknown exchanges
            self.rate_limits.append(
                RateLimit(
                    limit_type=RateLimitType.REQUESTS,
                    limit=10,
                    window_ms=1000,  # 10 requests per second
                    scope="global"
                )
            )
    
    async def _get_lock(self, endpoint: str) -> asyncio.Lock:
        """
        Get a lock for a specific endpoint, creating it if needed.
        
        Args:
            endpoint: API endpoint to get lock for
            
        Returns:
            asyncio.Lock: Lock for the endpoint
        """
        if endpoint not in self._locks:
            self._locks[endpoint] = asyncio.Lock()
        return self._locks[endpoint]
    
    def _get_applicable_limits(self, endpoint: str, method: str = "GET") -> List[RateLimit]:
        """
        Get all rate limits that apply to the specified endpoint and method.
        
        Args:
            endpoint: API endpoint being called
            method: HTTP method (GET, POST, etc.)
            
        Returns:
            List[RateLimit]: List of applicable rate limits
        """
        applicable_limits = []
        
        for rate_limit in self.rate_limits:
            # Check if the rate limit applies globally
            if rate_limit.endpoint is None:
                applicable_limits.append(rate_limit)
                continue
                
            # Check for exact endpoint match
            if rate_limit.endpoint == endpoint:
                applicable_limits.append(rate_limit)
                continue
                
            # Check for pattern matching (TODO: implement more sophisticated matching)
            if endpoint.startswith(rate_limit.endpoint):
                applicable_limits.append(rate_limit)
                
        return applicable_limits
    
    def _get_weight(self, rate_limit: RateLimit, method: str, options: Optional[Dict[str, Any]] = None) -> int:
        """
        Get the weight for a specific method and endpoint.
        
        Args:
            rate_limit: Rate limit to check weight for
            method: HTTP method (GET, POST, etc.)
            options: Additional options that might affect weight
            
        Returns:
            int: Weight of the request
        """
        options = options or {}
        
        # Check if the method has a specific weight
        if method in rate_limit.weight_map:
            weight = rate_limit.weight_map[method]
        # Check for method-specific weights with options
        elif f"{method}_MANY" in rate_limit.weight_map and options.get("limit", 0) > 100:
            weight = rate_limit.weight_map[f"{method}_MANY"]
        elif f"{method}_MAX" in rate_limit.weight_map and options.get("limit", 0) > 500:
            weight = rate_limit.weight_map[f"{method}_MAX"]
        # Use DEFAULT weight if available
        elif "DEFAULT" in rate_limit.weight_map:
            weight = rate_limit.weight_map["DEFAULT"]
        # Fallback to weight of 1
        else:
            weight = 1
            
        return weight
    
    def update_from_response_headers(self, response_headers: Dict[str, str]) -> None:
        """
        Update rate limits based on response headers from the exchange.
        
        Args:
            response_headers: HTTP response headers
        """
        if not response_headers or not self.enabled:
            return
            
        try:
            # Handle exchange-specific rate limit headers
            if self.exchange == 'binance':
                # Examples of Binance rate limit headers:
                # X-MBX-USED-WEIGHT -> 12
                # X-MBX-USED-WEIGHT-1M -> 12
                # X-MBX-ORDER-COUNT-10S -> 1
                # X-MBX-ORDER-COUNT-1D -> 10
                
                for header, value in response_headers.items():
                    if not header.startswith('X-MBX-'):
                        continue
                        
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        continue
                        
                    if 'USED-WEIGHT-1M' in header:
                        # Update the IP-based weight limit
                        for rate_limit in self.rate_limits:
                            if (rate_limit.limit_type == RateLimitType.WEIGHT and 
                                rate_limit.window_ms == 60000 and
                                rate_limit.scope == "ip"):
                                rate_limit.current_usage = value
                                break
                    elif 'ORDER-COUNT-10S' in header:
                        # Update the order rate limit
                        for rate_limit in self.rate_limits:
                            if (rate_limit.limit_type == RateLimitType.REQUESTS and 
                                rate_limit.window_ms == 10000 and
                                rate_limit.endpoint == "/api/v3/order"):
                                rate_limit.current_usage = value
                                break
            
            elif self.exchange == 'coinbase':
                # Coinbase Pro uses CB-AFTER, CB-BEFORE, and CB-PUB headers
                if 'CB-AFTER' in response_headers:
                    # This header provides a cursor for pagination
                    pass
                    
            elif self.exchange == 'ftx':
                # FTX doesn't provide rate limit headers, but we could update based on 429 responses
                pass
                
        except Exception as e:
            logger.warning(f"Error updating rate limits from headers: {str(e)}")
    
    def _should_throttle(self, applicable_limits: List[RateLimit], method: str, options: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[float]]:
        """
        Check if a request should be throttled based on applicable rate limits.
        
        Args:
            applicable_limits: List of applicable rate limits
            method: HTTP method (GET, POST, etc.)
            options: Additional options that might affect weight/throttling
            
        Returns:
            Tuple[bool, Optional[float]]: (should_throttle, wait_time_sec)
        """
        if not self.enabled or not applicable_limits:
            return False, None
            
        current_time = time.time()
        max_wait_time = 0.0
        
        for rate_limit in applicable_limits:
            # Reset usage if window has passed
            if current_time * 1000 >= rate_limit.reset_time:
                rate_limit.current_usage = 0
                rate_limit.reset_time = current_time * 1000 + rate_limit.window_ms
            
            # Calculate effective limit with safety factor
            effective_limit = int(rate_limit.limit * self.safety_factor)
            
            # Calculate weight for this request
            weight = self._get_weight(rate_limit, method, options)
            
            # Check if this request would exceed the rate limit
            if rate_limit.current_usage + weight > effective_limit:
                # Calculate wait time
                wait_time = (rate_limit.reset_time / 1000) - current_time
                max_wait_time = max(max_wait_time, wait_time)
        
        if max_wait_time > 0:
            return True, max_wait_time
        return False, None
        
    async def acquire(
        self,
        endpoint: str,
        method: str = "GET",
        options: Optional[Dict[str, Any]] = None,
        ignore_limits: bool = False
    ) -> None:
        """
        Acquire permission to make a request, throttling if necessary.
        
        Args:
            endpoint: API endpoint being called
            method: HTTP method (GET, POST, etc.)
            options: Additional options that might affect weight
            ignore_limits: Whether to ignore rate limits for this request
        """
        if not self.enabled or ignore_limits:
            return
            
        # Get lock for this endpoint
        lock = await self._get_lock(endpoint)
        
        async with lock:
            # Get applicable rate limits
            applicable_limits = self._get_applicable_limits(endpoint, method)
            
            # Check if we should throttle
            should_throttle, wait_time = self._should_throttle(applicable_limits, method, options)
            
            if should_throttle and wait_time is not None:
                logger.debug(f"Rate limiting {method} {endpoint} for {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
            
            # Record request time
            current_time = time.time()
            self.last_request_time[endpoint] = current_time
            
            # Update usage for all applicable limits
            for rate_limit in applicable_limits:
                weight = self._get_weight(rate_limit, method, options)
                rate_limit.current_usage += weight
    
    async def release(
        self,
        endpoint: str,
        method: str = "GET",
        response_headers: Optional[Dict[str, str]] = None,
        status_code: Optional[int] = None
    ) -> None:
        """
        Release a rate limit lock after a request, updating based on response.
        
        Args:
            endpoint: API endpoint that was called
            method: HTTP method that was used
            response_headers: Response headers from the request
            status_code: HTTP status code from the response
        """
        if not self.enabled:
            return
            
        # Update rate limits from response headers
        if response_headers:
            self.update_from_response_headers(response_headers)
            
        # Handle rate limit responses (429 Too Many Requests)
        if status_code == 429:
            logger.warning(f"Rate limit exceeded for {method} {endpoint}")
            
            # Lock this endpoint for a period
            self.locked_endpoints.add(endpoint)
            
            # Schedule unlock after retry_after_ms
            async def _unlock():
                await asyncio.sleep(self.retry_after_ms / 1000)
                if endpoint in self.locked_endpoints:
                    self.locked_endpoints.remove(endpoint)
                    
            asyncio.create_task(_unlock())
    
    async def execute_with_rate_limit(
        self,
        func: Callable[[], Awaitable[Any]],
        endpoint: str,
        method: str = "GET",
        options: Optional[Dict[str, Any]] = None,
        retry_on_rate_limit: bool = True
    ) -> Any:
        """
        Execute a function with rate limiting applied.
        
        Args:
            func: Async function to execute
            endpoint: API endpoint being called
            method: HTTP method (GET, POST, etc.)
            options: Additional options for the request
            retry_on_rate_limit: Whether to retry on rate limit errors
            
        Returns:
            Any: Result of the function call
        """
        retries = 0
        
        while True:
            try:
                # Acquire rate limit
                await self.acquire(endpoint, method, options)
                
                # Execute the function
                result = await func()
                
                # Get headers and status code if possible
                headers = getattr(result, 'headers', None)
                status = getattr(result, 'status', None)
                
                # Release rate limit
                await self.release(endpoint, method, headers, status)
                
                # Handle rate limit response
                if status == 429 and retry_on_rate_limit and retries < self.max_retries:
                    retries += 1
                    retry_after = headers.get('Retry-After', self.retry_after_ms / 1000)
                    
                    try:
                        retry_after = float(retry_after)
                    except (ValueError, TypeError):
                        retry_after = self.retry_after_ms / 1000
                        
                    logger.warning(f"Rate limited, retrying after {retry_after}s (attempt {retries}/{self.max_retries})")
                    await asyncio.sleep(retry_after)
                    continue
                    
                return result
                
            except aiohttp.ClientResponseError as e:
                # Handle rate limit exceptions
                if e.status == 429 and retry_on_rate_limit and retries < self.max_retries:
                    retries += 1
                    retry_after = e.headers.get('Retry-After', self.retry_after_ms / 1000)
                    
                    try:
                        retry_after = float(retry_after)
                    except (ValueError, TypeError):
                        retry_after = self.retry_after_ms / 1000
                        
                    logger.warning(f"Rate limited, retrying after {retry_after}s (attempt {retries}/{self.max_retries})")
                    
                    # Release rate limit
                    await self.release(endpoint, method, e.headers, e.status)
                    
                    await asyncio.sleep(retry_after)
                else:
                    # Release rate limit
                    await self.release(endpoint, method, getattr(e, 'headers', None), getattr(e, 'status', None))
                    raise
                    
            except Exception as e:
                # Release rate limit and re-raise the exception
                await self.release(endpoint, method)
                raise 