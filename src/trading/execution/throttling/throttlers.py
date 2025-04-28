"""
Implementations of common order throttlers.
"""
import time
import logging
from typing import Dict, Any, Optional, List, Set, Deque
from datetime import datetime, timedelta
from collections import deque, defaultdict
from threading import Lock

from .execution.core.base import Order
from .execution.throttling.base import BaseThrottler, ThrottlingResult

# Configure logger
logger = logging.getLogger(__name__)

class TokenBucketThrottler(BaseThrottler):
    """
    Implements the token bucket algorithm for rate limiting.
    Allows bursts of orders up to a configured bucket size, but maintains
    an average rate over time.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the token bucket throttler.
        
        Args:
            config: Configuration with the following keys:
                - tokens_per_second: Rate at which tokens are added to the bucket
                - bucket_size: Maximum number of tokens the bucket can hold
                - scope: What to group orders by ('global', 'symbol', 'strategy', etc.)
        """
        super().__init__("TokenBucketThrottler", config)
        
        self.tokens_per_second = self.config.get("tokens_per_second", 1.0)
        self.bucket_size = self.config.get("bucket_size", 10)
        self.scope = self.config.get("scope", "global")
        
        # Initialize buckets
        self.buckets: Dict[str, Dict[str, Any]] = {}
        self.lock = Lock()  # Thread safety
        
        logger.info(f"Initialized TokenBucketThrottler with rate={self.tokens_per_second}/s, "
                   f"bucket_size={self.bucket_size}, scope={self.scope}")
    
    def _get_bucket_key(self, order: Order) -> str:
        """
        Get the bucket key for an order based on the scope.
        
        Args:
            order: Order to get key for
            
        Returns:
            Bucket key
        """
        if self.scope == "global":
            return "global"
        elif self.scope == "symbol":
            return order.symbol
        elif self.scope == "strategy":
            return order.strategy_id or "default"
        elif self.scope == "exchange":
            return order.exchange or "default"
        else:
            # Default to global
            return "global"
    
    def check(self, order: Order, context: Optional[Dict[str, Any]] = None) -> ThrottlingResult:
        """
        Check if an order can proceed based on the token bucket algorithm.
        
        Args:
            order: Order to check
            context: Optional context information
            
        Returns:
            ThrottlingResult indicating whether the order is allowed to proceed
        """
        context = context or {}
        now = time.time()
        
        # Get the bucket key for this order
        bucket_key = self._get_bucket_key(order)
        
        with self.lock:
            # Get or create the bucket
            if bucket_key not in self.buckets:
                self.buckets[bucket_key] = {
                    "tokens": self.bucket_size,
                    "last_refill": now
                }
            
            bucket = self.buckets[bucket_key]
            
            # Calculate time since last refill
            time_since_refill = now - bucket["last_refill"]
            
            # Add tokens based on elapsed time
            new_tokens = time_since_refill * self.tokens_per_second
            bucket["tokens"] = min(bucket["tokens"] + new_tokens, self.bucket_size)
            bucket["last_refill"] = now
            
            # Cost for this order (default to 1 token)
            cost = context.get("token_cost", 1)
            
            # Check if we have enough tokens
            if bucket["tokens"] >= cost:
                # We have enough tokens, consume them
                bucket["tokens"] -= cost
                return self._create_result(True)
            else:
                # Not enough tokens, calculate wait time
                wait_time = (cost - bucket["tokens"]) / self.tokens_per_second
                return self._create_result(
                    False,
                    wait_time,
                    f"Rate limit exceeded for {bucket_key}",
                    {
                        "bucket_key": bucket_key,
                        "available_tokens": bucket["tokens"],
                        "required_tokens": cost,
                        "wait_time": wait_time
                    }
                )

class FixedWindowThrottler(BaseThrottler):
    """
    Implements fixed window rate limiting.
    Allows a maximum number of orders within a specific time window.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the fixed window throttler.
        
        Args:
            config: Configuration with the following keys:
                - max_orders: Maximum number of orders allowed in the window
                - window_seconds: Size of the time window in seconds
                - scope: What to group orders by ('global', 'symbol', 'strategy', etc.)
        """
        super().__init__("FixedWindowThrottler", config)
        
        self.max_orders = self.config.get("max_orders", 10)
        self.window_seconds = self.config.get("window_seconds", 60)
        self.scope = self.config.get("scope", "global")
        
        # Initialize windows
        self.windows: Dict[str, List[float]] = defaultdict(list)
        self.lock = Lock()  # Thread safety
        
        logger.info(f"Initialized FixedWindowThrottler with max_orders={self.max_orders}, "
                   f"window_seconds={self.window_seconds}, scope={self.scope}")
    
    def _get_window_key(self, order: Order) -> str:
        """
        Get the window key for an order based on the scope.
        
        Args:
            order: Order to get key for
            
        Returns:
            Window key
        """
        if self.scope == "global":
            return "global"
        elif self.scope == "symbol":
            return order.symbol
        elif self.scope == "strategy":
            return order.strategy_id or "default"
        elif self.scope == "exchange":
            return order.exchange or "default"
        else:
            # Default to global
            return "global"
    
    def check(self, order: Order, context: Optional[Dict[str, Any]] = None) -> ThrottlingResult:
        """
        Check if an order can proceed based on the fixed window algorithm.
        
        Args:
            order: Order to check
            context: Optional context information
            
        Returns:
            ThrottlingResult indicating whether the order is allowed to proceed
        """
        context = context or {}
        now = time.time()
        
        # Get the window key for this order
        window_key = self._get_window_key(order)
        
        with self.lock:
            # Get the window for this key
            window = self.windows[window_key]
            
            # Remove timestamps older than the window
            cutoff = now - self.window_seconds
            window = [ts for ts in window if ts > cutoff]
            self.windows[window_key] = window
            
            # Check if we're under the limit
            if len(window) < self.max_orders:
                # We're under the limit, add this order's timestamp
                window.append(now)
                return self._create_result(True)
            else:
                # We're at the limit, calculate wait time
                # Wait until the oldest order exits the window
                wait_time = window[0] + self.window_seconds - now
                return self._create_result(
                    False,
                    wait_time,
                    f"Rate limit exceeded for {window_key}",
                    {
                        "window_key": window_key,
                        "current_count": len(window),
                        "max_count": self.max_orders,
                        "wait_time": wait_time
                    }
                )

class SlidingWindowThrottler(BaseThrottler):
    """
    Implements sliding window rate limiting.
    More accurate than fixed window, but more resource intensive.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the sliding window throttler.
        
        Args:
            config: Configuration with the following keys:
                - max_orders: Maximum number of orders allowed in the window
                - window_seconds: Size of the time window in seconds
                - scope: What to group orders by ('global', 'symbol', 'strategy', etc.)
        """
        super().__init__("SlidingWindowThrottler", config)
        
        self.max_orders = self.config.get("max_orders", 10)
        self.window_seconds = self.config.get("window_seconds", 60)
        self.scope = self.config.get("scope", "global")
        
        # Initialize windows (deque for efficient timestamp management)
        self.windows: Dict[str, Deque[float]] = defaultdict(deque)
        self.lock = Lock()  # Thread safety
        
        logger.info(f"Initialized SlidingWindowThrottler with max_orders={self.max_orders}, "
                   f"window_seconds={self.window_seconds}, scope={self.scope}")
    
    def _get_window_key(self, order: Order) -> str:
        """
        Get the window key for an order based on the scope.
        
        Args:
            order: Order to get key for
            
        Returns:
            Window key
        """
        if self.scope == "global":
            return "global"
        elif self.scope == "symbol":
            return order.symbol
        elif self.scope == "strategy":
            return order.strategy_id or "default"
        elif self.scope == "exchange":
            return order.exchange or "default"
        else:
            # Default to global
            return "global"
    
    def check(self, order: Order, context: Optional[Dict[str, Any]] = None) -> ThrottlingResult:
        """
        Check if an order can proceed based on the sliding window algorithm.
        
        Args:
            order: Order to check
            context: Optional context information
            
        Returns:
            ThrottlingResult indicating whether the order is allowed to proceed
        """
        context = context or {}
        now = time.time()
        
        # Get the window key for this order
        window_key = self._get_window_key(order)
        
        with self.lock:
            # Get the window for this key
            window = self.windows[window_key]
            
            # Remove timestamps older than the window
            cutoff = now - self.window_seconds
            while window and window[0] < cutoff:
                window.popleft()
            
            # Check if we're under the limit
            if len(window) < self.max_orders:
                # We're under the limit, add this order's timestamp
                window.append(now)
                return self._create_result(True)
            else:
                # We're at the limit, calculate wait time
                # Wait until the oldest order exits the window
                wait_time = window[0] + self.window_seconds - now
                return self._create_result(
                    False,
                    wait_time,
                    f"Rate limit exceeded for {window_key}",
                    {
                        "window_key": window_key,
                        "current_count": len(window),
                        "max_count": self.max_orders,
                        "wait_time": wait_time
                    }
                )

class DynamicThrottler(BaseThrottler):
    """
    Dynamic throttler that adjusts rate limits based on system load and market conditions.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the dynamic throttler.
        
        Args:
            config: Configuration with the following keys:
                - base_rate: Base rate of orders per second
                - max_rate: Maximum rate of orders per second
                - system_load_factor: How much to factor in system load (0-1)
                - market_volatility_factor: How much to factor in market volatility (0-1)
                - scope: What to group orders by ('global', 'symbol', 'strategy', etc.)
        """
        super().__init__("DynamicThrottler", config)
        
        self.base_rate = self.config.get("base_rate", 1.0)
        self.max_rate = self.config.get("max_rate", 10.0)
        self.system_load_factor = self.config.get("system_load_factor", 0.5)
        self.market_volatility_factor = self.config.get("market_volatility_factor", 0.5)
        self.scope = self.config.get("scope", "global")
        
        # Use token bucket algorithm internally
        self.token_buckets: Dict[str, Dict[str, Any]] = {}
        self.lock = Lock()  # Thread safety
        
        logger.info(f"Initialized DynamicThrottler with base_rate={self.base_rate}, "
                   f"max_rate={self.max_rate}, scope={self.scope}")
    
    def _get_bucket_key(self, order: Order) -> str:
        """
        Get the bucket key for an order based on the scope.
        
        Args:
            order: Order to get key for
            
        Returns:
            Bucket key
        """
        if self.scope == "global":
            return "global"
        elif self.scope == "symbol":
            return order.symbol
        elif self.scope == "strategy":
            return order.strategy_id or "default"
        elif self.scope == "exchange":
            return order.exchange or "default"
        else:
            # Default to global
            return "global"
    
    def _calculate_current_rate(self, context: Dict[str, Any]) -> float:
        """
        Calculate the current rate based on system load and market conditions.
        
        Args:
            context: Context with system_load and market_volatility
            
        Returns:
            Current rate in tokens per second
        """
        system_load = context.get("system_load", 0.0)
        market_volatility = context.get("market_volatility", 0.0)
        
        # Calculate rate reduction factors
        system_factor = 1.0 - (system_load * self.system_load_factor)
        volatility_factor = 1.0 - (market_volatility * self.market_volatility_factor)
        
        # Calculate current rate
        rate = self.base_rate * system_factor * volatility_factor
        
        # Ensure rate is within bounds
        rate = max(0.1, min(rate, self.max_rate))
        
        return rate
    
    def check(self, order: Order, context: Optional[Dict[str, Any]] = None) -> ThrottlingResult:
        """
        Check if an order can proceed based on dynamic conditions.
        
        Args:
            order: Order to check
            context: Context with system_load and market_volatility
            
        Returns:
            ThrottlingResult indicating whether the order is allowed to proceed
        """
        context = context or {}
        now = time.time()
        
        # Get the bucket key for this order
        bucket_key = self._get_bucket_key(order)
        
        with self.lock:
            # Get or create the bucket
            if bucket_key not in self.token_buckets:
                self.token_buckets[bucket_key] = {
                    "tokens": self.max_rate,  # Start with full bucket
                    "last_refill": now,
                    "current_rate": self.base_rate
                }
            
            bucket = self.token_buckets[bucket_key]
            
            # Calculate current rate based on conditions
            current_rate = self._calculate_current_rate(context)
            bucket["current_rate"] = current_rate
            
            # Calculate time since last refill
            time_since_refill = now - bucket["last_refill"]
            
            # Add tokens based on elapsed time and current rate
            new_tokens = time_since_refill * current_rate
            bucket["tokens"] = min(bucket["tokens"] + new_tokens, self.max_rate)
            bucket["last_refill"] = now
            
            # Cost for this order (default to 1 token)
            cost = context.get("token_cost", 1)
            
            # Check if we have enough tokens
            if bucket["tokens"] >= cost:
                # We have enough tokens, consume them
                bucket["tokens"] -= cost
                return self._create_result(True)
            else:
                # Not enough tokens, calculate wait time
                wait_time = (cost - bucket["tokens"]) / current_rate
                return self._create_result(
                    False,
                    wait_time,
                    f"Dynamic rate limit exceeded for {bucket_key}",
                    {
                        "bucket_key": bucket_key,
                        "available_tokens": bucket["tokens"],
                        "required_tokens": cost,
                        "current_rate": current_rate,
                        "wait_time": wait_time
                    }
                )

# Export the throttlers
__all__ = [
    "TokenBucketThrottler",
    "FixedWindowThrottler",
    "SlidingWindowThrottler",
    "DynamicThrottler"
] 