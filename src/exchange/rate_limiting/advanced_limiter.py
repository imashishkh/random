"""
Advanced Rate Limiter for Exchange Communications

This module provides an enhanced rate limiting system that works across all 
connection types (REST API, WebSocket) with support for:
- Token bucket algorithm with different endpoint weights
- Dynamic adjustment based on exchange headers
- Intelligent queuing and prioritization
- Multiple rate limit tiers
- Automatic throttling to prevent hitting limits
"""
import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Dict, List, Optional, Any, Set, Tuple, Callable, Awaitable, Union
import aiohttp

from ...utils import ThreadSafeSingleton
from ...utils.logging import get_structured_logger

# Configure logger
logger = get_structured_logger(__name__)


class RateLimitType(Enum):
    """Type of rate limit enforced by an exchange."""
    REQUESTS = "requests"  # Limit based on number of requests
    WEIGHT = "weight"      # Limit based on request weight
    ORDERS = "orders"      # Limit specifically for order operations
    TRADING = "trading"    # Limit specifically for trading operations


class RequestPriority(Enum):
    """Priority levels for API requests."""
    CRITICAL = 0  # System-critical operations (e.g., emergency stop)
    HIGH = 1      # User-initiated actions (e.g., placing orders)
    NORMAL = 2    # Regular operations (e.g., fetching account data)
    LOW = 3       # Background operations (e.g., historical data)
    LOWEST = 4    # Least important (e.g., analytics, non-critical updates)


class ConnectionType(Enum):
    """Types of connections to the exchange."""
    REST = "rest"
    WEBSOCKET = "websocket"
    WEBSOCKET_PRIVATE = "websocket_private"
    FUTURES = "futures"


class RateLimitTier(Enum):
    """Rate limit tiers based on API usage levels."""
    DEFAULT = 0   # Default tier for all users
    PREMIUM = 1   # Higher limits for premium users
    VIP = 2       # Very high limits for VIP users
    PARTNER = 3   # Partner-level API access 


class TokenBucket:
    """
    TokenBucket implementation for rate limiting.
    
    The token bucket algorithm allows for burstiness while still maintaining
    a long-term rate limit. Tokens are added to the bucket at a fixed rate,
    and each request consumes one or more tokens.
    """
    
    def __init__(
        self,
        capacity: float,
        refill_rate: float,
        initial_tokens: Optional[float] = None,
        refill_interval: float = 1.0
    ):
        """
        Initialize a token bucket.
        
        Args:
            capacity: Maximum number of tokens in the bucket
            refill_rate: Number of tokens added per second
            initial_tokens: Initial number of tokens (defaults to capacity)
            refill_interval: How often to refill tokens (in seconds)
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = initial_tokens if initial_tokens is not None else capacity
        self.refill_interval = refill_interval
        self.last_refill_time = time.time()
        self.lock = threading.RLock()  # For thread safety
        
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill_time
        
        if elapsed < self.refill_interval:
            return
            
        new_tokens = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill_time = now
        
    def consume(self, tokens: float = 1.0) -> bool:
        """
        Try to consume tokens from the bucket.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were consumed, False if not enough tokens
        """
        with self.lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
            
    def wait_time_for(self, tokens: float = 1.0) -> float:
        """
        Calculate time needed to wait for required tokens.
        
        Args:
            tokens: Number of tokens needed
            
        Returns:
            Time in seconds to wait, or 0 if tokens are available now
        """
        with self.lock:
            self._refill()
            
            if self.tokens >= tokens:
                return 0.0
                
            needed_tokens = tokens - self.tokens
            return needed_tokens / self.refill_rate 


@dataclass
class RateLimitConfig:
    """Configuration for a specific rate limit."""
    name: str
    tier: RateLimitTier
    bucket_capacity: int
    refill_rate: float  # tokens per second
    weight_map: Dict[str, int] = field(default_factory=dict)
    scope: str = "ip"  # ip, user, global, etc.
    applies_to: Set[str] = field(default_factory=set)  # empty means applies to all
    
    def __post_init__(self):
        """Ensure weight_map has at least a default entry."""
        if not self.weight_map:
            self.weight_map = {"DEFAULT": 1}
            
    def get_weight(self, method: str, options: Optional[Dict[str, Any]] = None) -> int:
        """Get the weight for a specific method and options."""
        options = options or {}
        
        # Check for exact method match
        if method in self.weight_map:
            return self.weight_map[method]
            
        # Check for method variants based on options
        if options.get("limit"):
            limit = options["limit"]
            if limit > 500 and f"{method}_HEAVY" in self.weight_map:
                return self.weight_map[f"{method}_HEAVY"]
            elif limit > 100 and f"{method}_MEDIUM" in self.weight_map:
                return self.weight_map[f"{method}_MEDIUM"]
                
        # Use default if no specific match
        return self.weight_map.get("DEFAULT", 1)
        
    def applies_to_endpoint(self, endpoint: str) -> bool:
        """Check if this limit applies to the given endpoint."""
        # Empty set means applies to all endpoints
        if not self.applies_to:
            return True
            
        # Check for exact match
        if endpoint in self.applies_to:
            return True
            
        # Check for prefix match
        for prefix in self.applies_to:
            if prefix.endswith('*') and endpoint.startswith(prefix[:-1]):
                return True
                
        return False


class RateLimitRegistry:
    """
    Registry of all rate limits for the application.
    
    Manages the configurations for different rate limits and provides
    access to the appropriate limits for a given endpoint and method.
    """
    
    def __init__(self):
        """Initialize the registry with default limits."""
        self.configs: List[RateLimitConfig] = []
        self.active_tier = RateLimitTier.DEFAULT
        self._initialize_defaults()
        
    def _initialize_defaults(self):
        """Initialize with default Binance API rate limits."""
        # Overall request weight limit (1200 per minute)
        self.configs.append(RateLimitConfig(
            name="weight_limit",
            tier=RateLimitTier.DEFAULT,
            bucket_capacity=1200,
            refill_rate=1200/60,  # 1200 per minute = 20 per second
            scope="ip"
        ))
        
        # Order rate limit (50 per 10 seconds)
        self.configs.append(RateLimitConfig(
            name="order_limit",
            tier=RateLimitTier.DEFAULT,
            bucket_capacity=50,
            refill_rate=50/10,  # 50 per 10 seconds = 5 per second
            scope="ip",
            applies_to={"/api/v3/order", "/api/v3/batchOrders"}
        ))
        
        # Different endpoint weights
        klines_config = RateLimitConfig(
            name="klines_weights",
            tier=RateLimitTier.DEFAULT,
            bucket_capacity=1200,
            refill_rate=1200/60,
            scope="ip",
            applies_to={"/api/v3/klines"},
            weight_map={
                "GET": 1,
                "GET_MEDIUM": 2,  # When requesting 100-500 candles
                "GET_HEAVY": 5,   # When requesting 500+ candles
            }
        )
        self.configs.append(klines_config)
        
        # Add VIP tier with higher limits
        self.configs.append(RateLimitConfig(
            name="weight_limit_vip",
            tier=RateLimitTier.VIP,
            bucket_capacity=2400,  # Double the default
            refill_rate=2400/60,
            scope="ip"
        ))
        
    def get_applicable_configs(self, endpoint: str, tier: Optional[RateLimitTier] = None) -> List[RateLimitConfig]:
        """
        Get all configurations that apply to an endpoint.
        
        Args:
            endpoint: API endpoint
            tier: Rate limit tier to use (defaults to active tier)
            
        Returns:
            List of applicable rate limit configurations
        """
        tier = tier or self.active_tier
        result = []
        
        for config in self.configs:
            # Check tier - only use equal or lower tiers
            if config.tier.value > tier.value:
                continue
                
            # Check if applies to the endpoint
            if config.applies_to_endpoint(endpoint):
                result.append(config)
                
        return result
        
    def set_active_tier(self, tier: RateLimitTier):
        """Set the active rate limit tier."""
        self.active_tier = tier
        
    def add_config(self, config: RateLimitConfig):
        """Add a new rate limit configuration."""
        self.configs.append(config)
        
    def remove_config(self, name: str, tier: RateLimitTier):
        """Remove a rate limit configuration by name and tier."""
        self.configs = [c for c in self.configs if 
                       not (c.name == name and c.tier == tier)] 


@dataclass
class RateLimitStatus:
    """Status of a particular rate limit."""
    current_usage: int
    limit: int
    reset_time: float
    
    @property
    def usage_percentage(self) -> float:
        """Get the current usage as a percentage of the limit."""
        if self.limit == 0:
            return 100.0
        return (self.current_usage / self.limit) * 100.0
        
    @property
    def time_to_reset(self) -> float:
        """Get the time until the rate limit resets (in seconds)."""
        now = time.time()
        return max(0.0, self.reset_time - now)
        
    @property
    def is_critical(self) -> bool:
        """Check if the usage is at a critical level (>90%)."""
        return self.usage_percentage > 90.0


class RateLimitMonitor:
    """
    Monitors and analyzes rate limit headers from Binance.
    
    Provides dynamic adjustment of rate limits based on the
    actual usage reported by the exchange.
    """
    
    def __init__(self):
        """Initialize the monitor."""
        self.weight_status: Dict[str, RateLimitStatus] = {}
        self.order_status: Dict[str, RateLimitStatus] = {}
        self.last_update_time = 0.0
        self.ip_banned_until: Optional[float] = None
        
    def update_from_headers(self, headers: Dict[str, str]) -> None:
        """
        Update rate limit status from response headers.
        
        Args:
            headers: HTTP response headers
        """
        if not headers:
            return
            
        now = time.time()
        self.last_update_time = now
        
        # Process Binance-specific headers
        try:
            # Weight limits
            if 'X-MBX-USED-WEIGHT-1M' in headers:
                weight = int(headers['X-MBX-USED-WEIGHT-1M'])
                self.weight_status['1m'] = RateLimitStatus(
                    current_usage=weight,
                    limit=1200,  # Default weight limit
                    reset_time=now + 60  # 1 minute
                )
                
            # Order limits
            if 'X-MBX-ORDER-COUNT-10S' in headers:
                count = int(headers['X-MBX-ORDER-COUNT-10S'])
                self.order_status['10s'] = RateLimitStatus(
                    current_usage=count,
                    limit=50,  # Default order limit for 10s
                    reset_time=now + 10  # 10 seconds
                )
                
            if 'X-MBX-ORDER-COUNT-1D' in headers:
                count = int(headers['X-MBX-ORDER-COUNT-1D'])
                self.order_status['1d'] = RateLimitStatus(
                    current_usage=count,
                    limit=160000,  # Default order limit for 1 day
                    reset_time=now + 86400  # 24 hours
                )
                
            # Check for retry-after header (indicates IP ban)
            if 'Retry-After' in headers:
                retry_after = int(headers['Retry-After'])
                self.ip_banned_until = now + retry_after
                logger.warning(f"IP temporarily banned by Binance for {retry_after} seconds")
                
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing rate limit headers: {e}")
            
    def get_throttle_factor(self) -> float:
        """
        Get a throttling factor based on current usage.
        
        Returns:
            Factor between 0.0-1.0 to multiply request rate by
            (e.g., 0.5 means send at half speed)
        """
        # Default to no throttling
        factor = 1.0
        
        # Check for IP ban
        if self.ip_banned_until and time.time() < self.ip_banned_until:
            return 0.0  # Complete throttling
            
        # Check weight limits
        for status in self.weight_status.values():
            if status.usage_percentage > 80.0:
                # Calculate a factor based on usage
                new_factor = max(0.1, (100.0 - status.usage_percentage) / 20.0)
                factor = min(factor, new_factor)
                
        # Check order limits similarly
        for status in self.order_status.values():
            if status.usage_percentage > 80.0:
                new_factor = max(0.1, (100.0 - status.usage_percentage) / 20.0)
                factor = min(factor, new_factor)
                
        return factor
        
    def should_backoff(self) -> Tuple[bool, float]:
        """
        Determine if we should backoff from sending requests.
        
        Returns:
            Tuple of (should_backoff, backoff_time)
        """
        # Check for IP ban
        if self.ip_banned_until and time.time() < self.ip_banned_until:
            return True, self.ip_banned_until - time.time()
            
        # Check for critical usage
        for status in list(self.weight_status.values()) + list(self.order_status.values()):
            if status.is_critical:
                # Back off until reset
                return True, status.time_to_reset
                
        return False, 0.0
        
    def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get a summary of current rate limit usage.
        
        Returns:
            Dictionary with usage statistics
        """
        return {
            'weight': {k: {'usage': v.current_usage, 'limit': v.limit, 
                          'usage_pct': v.usage_percentage, 
                          'reset_in': v.time_to_reset}
                      for k, v in self.weight_status.items()},
            'orders': {k: {'usage': v.current_usage, 'limit': v.limit, 
                          'usage_pct': v.usage_percentage, 
                          'reset_in': v.time_to_reset}
                       for k, v in self.order_status.items()},
            'ip_banned': bool(self.ip_banned_until and time.time() < self.ip_banned_until),
            'throttle_factor': self.get_throttle_factor(),
            'last_update': self.last_update_time
        } 


@dataclass(order=True)
class QueuedRequest:
    """A request in the priority queue."""
    priority: int
    timestamp: float = field(compare=True)
    weight: int = field(compare=False)
    endpoint: str = field(compare=False)
    method: str = field(compare=False)
    params: Dict[str, Any] = field(compare=False, default_factory=dict)
    execute_func: Optional[Callable] = field(compare=False, default=None)
    future: Optional[asyncio.Future] = field(compare=False, default=None)
    
    def __post_init__(self):
        """Ensure timestamp is set if not provided."""
        if not hasattr(self, 'timestamp') or self.timestamp is None:
            self.timestamp = time.time()


class PriorityRequestQueue:
    """
    Priority queue for API requests.
    
    Implements intelligent queuing with the following features:
    - Prioritization based on request type
    - Fairness within priority levels (FIFO for same priority)
    - Support for both sync and async execution
    - Automatic retry of failed requests
    """
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize the priority queue.
        
        Args:
            max_size: Maximum queue size before rejecting new requests
        """
        self.queue: List[QueuedRequest] = []
        self.max_size = max_size
        self.lock = asyncio.Lock()
        
    async def enqueue(
        self, 
        endpoint: str,
        method: str,
        priority: RequestPriority,
        weight: int = 1,
        params: Optional[Dict[str, Any]] = None,
        execute_func: Optional[Callable] = None
    ) -> asyncio.Future:
        """
        Add a request to the queue.
        
        Args:
            endpoint: API endpoint
            method: HTTP method
            priority: Request priority
            weight: Request weight
            params: Request parameters
            execute_func: Function to execute when request is dequeued
            
        Returns:
            Future that will be resolved when request is executed
        """
        async with self.lock:
            if len(self.queue) >= self.max_size:
                raise ValueError(f"Queue is full (max size: {self.max_size})")
                
            future = asyncio.Future()
            request = QueuedRequest(
                priority=priority.value,
                timestamp=time.time(),
                weight=weight,
                endpoint=endpoint,
                method=method,
                params=params or {},
                execute_func=execute_func,
                future=future
            )
            
            import heapq
            heapq.heappush(self.queue, request)
            return future
            
    async def dequeue(self) -> Optional[QueuedRequest]:
        """
        Remove and return the highest priority request.
        
        Returns:
            The next request to process, or None if queue is empty
        """
        async with self.lock:
            if not self.queue:
                return None
                
            import heapq
            return heapq.heappop(self.queue)
            
    async def peek(self) -> Optional[QueuedRequest]:
        """
        View the highest priority request without removing it.
        
        Returns:
            The next request to process, or None if queue is empty
        """
        async with self.lock:
            if not self.queue:
                return None
                
            return self.queue[0]
    
    async def execute_next(self, bucket: Optional[TokenBucket] = None) -> bool:
        """
        Execute the next request in the queue if possible.
        
        Args:
            bucket: Token bucket to check for capacity
            
        Returns:
            True if a request was executed, False otherwise
        """
        request = await self.peek()
        if not request:
            return False
            
        # Check if we have capacity
        if bucket and not bucket.consume(request.weight):
            return False
            
        # Remove from queue
        await self.dequeue()
        
        # Execute the request
        try:
            if request.execute_func:
                result = request.execute_func(
                    request.endpoint,
                    request.method,
                    request.params
                )
                request.future.set_result(result)
            else:
                request.future.set_result(None)
        except Exception as e:
            request.future.set_exception(e)
            
        return True 


class AdvancedRateLimiter(metaclass=ThreadSafeSingleton):
    """
    Advanced centralized rate limiter for Binance API.
    
    Features:
    - Works across all connection types (REST, WebSocket)
    - Uses token bucket algorithm with support for different endpoint weights
    - Tracks rate limit headers from Binance and adjusts limits dynamically
    - Implements intelligent queuing and prioritization of requests
    - Supports multiple rate limit tiers
    - Provides automatic throttling to avoid hitting limits
    """
    
    def __init__(self, enable_rate_limit: bool = True):
        """
        Initialize the advanced rate limiter.
        
        Args:
            enable_rate_limit: Whether to enable rate limiting
        """
        self.enable_rate_limit = enable_rate_limit
        self.registry = RateLimitRegistry()
        self.monitor = RateLimitMonitor()
        
        # Token buckets for different limit types
        self.buckets: Dict[str, TokenBucket] = {}
        
        # Priority queues for different connection types
        self.queues: Dict[ConnectionType, PriorityRequestQueue] = {
            conn_type: PriorityRequestQueue() 
            for conn_type in ConnectionType
        }
        
        # Locks for thread safety
        self.lock = threading.RLock()
        self.async_lock = asyncio.Lock()
        
        # Create default buckets
        self._initialize_buckets()
        
        # Flag to track if the queue processor is running
        self._queue_processor_running = False
        
        logger.info("Initialized Advanced Rate Limiter")
        
    def _initialize_buckets(self) -> None:
        """Initialize token buckets based on registry configurations."""
        with self.lock:
            for config in self.registry.configs:
                if config.tier == self.registry.active_tier:
                    bucket_id = f"{config.name}_{config.tier.name}"
                    self.buckets[bucket_id] = TokenBucket(
                        capacity=config.bucket_capacity,
                        refill_rate=config.refill_rate
                    )
                    logger.debug(f"Created bucket {bucket_id} with capacity {config.bucket_capacity}")
    
    def _get_applicable_buckets(self, endpoint: str) -> List[Tuple[str, TokenBucket]]:
        """
        Get all buckets that apply to an endpoint.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            List of (bucket_id, bucket) tuples
        """
        with self.lock:
            configs = self.registry.get_applicable_configs(endpoint)
            result = []
            
            for config in configs:
                bucket_id = f"{config.name}_{config.tier.name}"
                if bucket_id in self.buckets:
                    result.append((bucket_id, self.buckets[bucket_id]))
                    
            return result
    
    def _calculate_weight(self, endpoint: str, method: str, options: Optional[Dict[str, Any]] = None) -> int:
        """
        Calculate the weight for a request.
        
        Args:
            endpoint: API endpoint
            method: HTTP method
            options: Request options
            
        Returns:
            Weight of the request
        """
        configs = self.registry.get_applicable_configs(endpoint)
        
        # Start with default weight of 1
        weight = 1
        
        for config in configs:
            # Check for endpoint-specific weight
            if config.applies_to_endpoint(endpoint):
                config_weight = config.get_weight(method, options)
                if config_weight > weight:
                    weight = config_weight
                    
        return weight 

    def pre_request(
        self,
        endpoint: str,
        method: str = "GET",
        options: Optional[Dict[str, Any]] = None,
        connection_type: ConnectionType = ConnectionType.REST,
        priority: RequestPriority = RequestPriority.NORMAL
    ) -> float:
        """
        Handle pre-request rate limiting (synchronous version).
        
        Should be called before making an API request.
        
        Args:
            endpoint: API endpoint
            method: HTTP method
            options: Request options
            connection_type: Type of connection
            priority: Request priority
            
        Returns:
            Time waited in seconds, or 0 if no wait needed
        """
        if not self.enable_rate_limit:
            return 0.0
            
        with self.lock:
            # Check if we should back off
            should_backoff, backoff_time = self.monitor.should_backoff()
            if should_backoff:
                logger.warning(f"Backing off for {backoff_time:.2f} seconds due to rate limits")
                time.sleep(backoff_time)
                return backoff_time
                
            # Calculate request weight
            weight = self._calculate_weight(endpoint, method, options)
            
            # Check all applicable buckets
            applicable_buckets = self._get_applicable_buckets(endpoint)
            
            if not applicable_buckets:
                # No applicable buckets, allow request
                return 0.0
                
            # Check if any bucket doesn't have capacity
            wait_time = 0.0
            for bucket_id, bucket in applicable_buckets:
                if not bucket.consume(weight):
                    # Calculate wait time
                    bucket_wait = bucket.wait_time_for(weight)
                    wait_time = max(wait_time, bucket_wait)
            
            if wait_time > 0:
                # Need to wait
                logger.debug(f"Rate limited, waiting {wait_time:.2f}s for {endpoint}")
                time.sleep(wait_time)
                
                # Try again after waiting
                return wait_time + self.pre_request(
                    endpoint, method, options, connection_type, priority
                )
                
            # Apply throttling based on monitor recommendations
            throttle_factor = self.monitor.get_throttle_factor()
            if throttle_factor < 1.0:
                throttle_wait = (1.0 - throttle_factor) * 0.1  # Max 100ms at 0 factor
                if throttle_wait > 0:
                    logger.debug(f"Throttling by {throttle_wait:.2f}s (factor: {throttle_factor:.2f})")
                    time.sleep(throttle_wait)
                    return throttle_wait
                    
            return wait_time
            
    async def pre_request_async(
        self,
        endpoint: str,
        method: str = "GET",
        options: Optional[Dict[str, Any]] = None,
        connection_type: ConnectionType = ConnectionType.REST,
        priority: RequestPriority = RequestPriority.NORMAL,
        enqueue_if_limited: bool = True
    ) -> float:
        """
        Handle pre-request rate limiting (async version).
        
        Args:
            endpoint: API endpoint
            method: HTTP method
            options: Request options
            connection_type: Type of connection
            priority: Request priority
            enqueue_if_limited: Whether to enqueue the request if rate limited
            
        Returns:
            Time waited in seconds, or 0 if no wait needed
        """
        if not self.enable_rate_limit:
            return 0.0
            
        async with self.async_lock:
            # Check if we should back off
            should_backoff, backoff_time = self.monitor.should_backoff()
            if should_backoff:
                logger.warning(f"Backing off for {backoff_time:.2f} seconds due to rate limits")
                await asyncio.sleep(backoff_time)
                return backoff_time
                
            # Calculate request weight
            weight = self._calculate_weight(endpoint, method, options)
            
            # Check all applicable buckets
            applicable_buckets = self._get_applicable_buckets(endpoint)
            
            if not applicable_buckets:
                # No applicable buckets, allow request
                return 0.0
                
            # Check if any bucket doesn't have capacity
            wait_time = 0.0
            for bucket_id, bucket in applicable_buckets:
                if not bucket.consume(weight):
                    # Calculate wait time
                    bucket_wait = bucket.wait_time_for(weight)
                    wait_time = max(wait_time, bucket_wait)
            
            if wait_time > 0:
                if enqueue_if_limited:
                    # Enqueue for later execution
                    logger.debug(f"Rate limited, enqueueing request to {endpoint}")
                    queue = self.queues[connection_type]
                    await queue.enqueue(
                        endpoint=endpoint,
                        method=method,
                        priority=priority,
                        weight=weight,
                        params=options
                    )
                    return wait_time
                else:
                    # Need to wait
                    logger.debug(f"Rate limited, waiting {wait_time:.2f}s for {endpoint}")
                    await asyncio.sleep(wait_time)
                    
                    # Try again after waiting
                    return wait_time + await self.pre_request_async(
                        endpoint, method, options, connection_type, priority, enqueue_if_limited
                    )
                
            # Apply throttling based on monitor recommendations
            throttle_factor = self.monitor.get_throttle_factor()
            if throttle_factor < 1.0:
                throttle_wait = (1.0 - throttle_factor) * 0.1  # Max 100ms at 0 factor
                if throttle_wait > 0:
                    logger.debug(f"Throttling by {throttle_wait:.2f}s (factor: {throttle_factor:.2f})")
                    await asyncio.sleep(throttle_wait)
                    return throttle_wait
                    
            return wait_time
            
    def post_request(self, headers: Optional[Dict[str, str]] = None) -> None:
        """
        Process post-request operations.
        
        Args:
            headers: Response headers
        """
        if not self.enable_rate_limit or not headers:
            return
            
        with self.lock:
            self.monitor.update_from_headers(headers)
            
    async def post_request_async(self, headers: Optional[Dict[str, str]] = None) -> None:
        """
        Process post-request operations (async version).
        
        Args:
            headers: Response headers
        """
        if not self.enable_rate_limit or not headers:
            return
            
        async with self.async_lock:
            self.monitor.update_from_headers(headers) 

    async def start_queue_processor(self) -> None:
        """Start the background queue processor."""
        if self._queue_processor_running:
            return
            
        self._queue_processor_running = True
        asyncio.create_task(self._process_queues())
        
    async def _process_queues(self) -> None:
        """Process queued requests in the background."""
        while self._queue_processor_running:
            processed = False
            
            # Process each connection type queue
            for conn_type, queue in self.queues.items():
                # Check for a request to process
                request = await queue.peek()
                if not request:
                    continue
                    
                # Check if all applicable buckets have capacity
                weight = request.weight
                can_process = True
                
                for bucket_id, bucket in self._get_applicable_buckets(request.endpoint):
                    if not bucket.consume(weight):
                        can_process = False
                        break
                        
                if can_process:
                    # Execute the request
                    await queue.execute_next(None)  # Pass None as we've already consumed tokens
                    processed = True
                    
            # If nothing processed, sleep briefly
            if not processed:
                await asyncio.sleep(0.01)
                
    def stop_queue_processor(self) -> None:
        """Stop the background queue processor."""
        self._queue_processor_running = False
        
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current rate limiter status.
        
        Returns:
            Dictionary with status information
        """
        with self.lock:
            return {
                "limits": self.monitor.get_usage_stats(),
                "buckets": {
                    bucket_id: {
                        "tokens": bucket.tokens,
                        "capacity": bucket.capacity,
                        "refill_rate": bucket.refill_rate
                    }
                    for bucket_id, bucket in self.buckets.items()
                },
                "queues": {
                    conn_type.name: len(queue.queue)
                    for conn_type, queue in self.queues.items()
                },
                "throttle_factor": self.monitor.get_throttle_factor(),
                "tier": self.registry.active_tier.name
            }
    
    def set_tier(self, tier: RateLimitTier) -> None:
        """
        Set the active rate limit tier.
        
        Args:
            tier: New rate limit tier
        """
        with self.lock:
            if tier == self.registry.active_tier:
                return
                
            self.registry.set_active_tier(tier)
            self._initialize_buckets()
            logger.info(f"Switched to rate limit tier: {tier.name}")
            
    def reset(self) -> None:
        """Reset all rate limits to their initial state."""
        with self.lock:
            self._initialize_buckets()
            self.monitor = RateLimitMonitor()
            logger.info("Reset all rate limits")


def rate_limited(
    priority: RequestPriority = RequestPriority.NORMAL,
    connection_type: ConnectionType = ConnectionType.REST,
    custom_endpoint: Optional[str] = None
):
    """
    Decorator for rate-limited API calls.
    
    Makes it easy to add rate limiting to any function that makes API calls.
    
    Args:
        priority: Priority level for the request
        connection_type: Type of connection being used
        custom_endpoint: Override the endpoint (defaults to function name)
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get the rate limiter
            limiter = AdvancedRateLimiter()
            
            # Determine endpoint from function name or custom endpoint
            endpoint = custom_endpoint or f"/{func.__name__}"
            
            # Extract method and options if available
            method = kwargs.get('method', 'GET')
            options = kwargs.get('params')
            
            # Apply rate limiting
            limiter.pre_request(
                endpoint=endpoint,
                method=method,
                options=options,
                connection_type=connection_type,
                priority=priority
            )
            
            # Call the function
            result = func(*args, **kwargs)
            
            # Process the response if it has headers
            if hasattr(result, 'headers'):
                limiter.post_request(result.headers)
                
            return result
            
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get the rate limiter
            limiter = AdvancedRateLimiter()
            
            # Determine endpoint from function name or custom endpoint
            endpoint = custom_endpoint or f"/{func.__name__}"
            
            # Extract method and options if available
            method = kwargs.get('method', 'GET')
            options = kwargs.get('params')
            
            # Apply rate limiting
            await limiter.pre_request_async(
                endpoint=endpoint,
                method=method,
                options=options,
                connection_type=connection_type,
                priority=priority
            )
            
            # Call the function
            result = await func(*args, **kwargs)
            
            # Process the response if it has headers
            if hasattr(result, 'headers'):
                await limiter.post_request_async(result.headers)
                
            return result
            
        # Choose the appropriate wrapper based on whether the function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper
            
    return decorator 