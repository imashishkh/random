"""
Rate Limiter for Exchange APIs

This module provides rate limiting functionality for exchange API clients
to prevent hitting rate limits and getting banned.
"""

import time
import threading
from typing import Dict, Any, Optional
from dataclasses import dataclass
from collections import defaultdict, deque

from ..utils import ThreadSafeSingleton
from ..utils.logging import get_structured_logger

# Get structured logger
logger = get_structured_logger(__name__)


@dataclass
class RateLimitInfo:
    """Rate limit information for an endpoint or group."""
    limit: int  # Maximum request count
    interval: int  # Time interval in seconds
    current_count: int = 0  # Current usage count
    reset_time: float = 0  # Time when the limit resets


class SlidingWindowCounter:
    """
    Sliding window rate limiter implementation.
    
    This tracks requests over a sliding window of time rather than
    using fixed buckets, providing more accurate rate limiting.
    """
    
    def __init__(self, window_size: int = 60):
        """
        Initialize sliding window counter.
        
        Args:
            window_size: Window size in seconds.
        """
        self.window_size = window_size
        self.requests = deque()
        self.lock = threading.RLock()
    
    def add_request(self) -> int:
        """
        Add a request and return the current count in the window.
        
        Returns:
            Current number of requests in the window.
        """
        with self.lock:
            now = time.time()
            
            # Remove expired timestamps
            while self.requests and self.requests[0] <= now - self.window_size:
                self.requests.popleft()
            
            # Add current timestamp
            self.requests.append(now)
            
            return len(self.requests)
    
    def current_count(self) -> int:
        """
        Get the current count of requests in the window.
        
        Returns:
            Current number of requests in the window.
        """
        with self.lock:
            now = time.time()
            
            # Remove expired timestamps
            while self.requests and self.requests[0] <= now - self.window_size:
                self.requests.popleft()
            
            return len(self.requests)
    
    def allow_request(self, limit: int) -> bool:
        """
        Check if a request is allowed based on the limit.
        
        Args:
            limit: Maximum number of requests allowed in the window.
            
        Returns:
            True if the request is allowed, False otherwise.
        """
        return self.current_count() < limit


class RateLimiter(metaclass=ThreadSafeSingleton):
    """
    Thread-safe rate limiter for API clients.
    
    This singleton class manages rate limits for different endpoints
    and prevents exceeding those limits by tracking usage and waiting
    when necessary.
    """
    
    def __init__(self):
        """Initialize the rate limiter."""
        self.endpoint_limits: Dict[str, RateLimitInfo] = {}
        self.sliding_windows: Dict[str, SlidingWindowCounter] = defaultdict(SlidingWindowCounter)
        self.lock = threading.RLock()
    
    def set_limit(self, endpoint: str, limit: int, interval: int) -> None:
        """
        Set or update a rate limit for an endpoint.
        
        Args:
            endpoint: API endpoint or group name.
            limit: Maximum request count.
            interval: Time interval in seconds.
        """
        with self.lock:
            self.endpoint_limits[endpoint] = RateLimitInfo(
                limit=limit,
                interval=interval
            )
            logger.debug("Rate limit set", endpoint=endpoint, limit=limit, interval=interval)
    
    def update_from_headers(self, endpoint: str, headers: Dict[str, Any]) -> None:
        """
        Update rate limit info from API response headers.
        
        Args:
            endpoint: API endpoint or group name.
            headers: Response headers containing rate limit information.
        """
        with self.lock:
            # Look for common rate limit headers
            if 'X-MBX-USED-WEIGHT' in headers and 'X-MBX-USED-WEIGHT-1M' in headers:
                # Binance-specific handling
                used = int(headers.get('X-MBX-USED-WEIGHT', 0))
                limit = int(headers.get('X-MBX-ORDER-COUNT-1M', 1200))  # Default to 1200 if not provided
                
                if endpoint in self.endpoint_limits:
                    self.endpoint_limits[endpoint].current_count = used
                    self.endpoint_limits[endpoint].limit = limit
                    logger.debug("Updated rate limit from headers", 
                                 endpoint=endpoint, used=used, limit=limit)
    
    def has_capacity(self, endpoint: str) -> bool:
        """
        Check if there is capacity available for an endpoint.
        
        Args:
            endpoint: API endpoint or group name.
            
        Returns:
            True if capacity is available, False otherwise.
        """
        with self.lock:
            # Check if we have info for this endpoint
            if endpoint not in self.endpoint_limits:
                return True
            
            # Get limit info
            limit_info = self.endpoint_limits[endpoint]
            
            # Check sliding window count
            return self.sliding_windows[endpoint].allow_request(limit_info.limit)
    
    def track_request(self, endpoint: str) -> None:
        """
        Track a request to an endpoint.
        
        Args:
            endpoint: API endpoint or group name.
        """
        with self.lock:
            # Add to sliding window
            count = self.sliding_windows[endpoint].add_request()
            
            # If we have limit info, update the current count
            if endpoint in self.endpoint_limits:
                self.endpoint_limits[endpoint].current_count = count
            
            logger.debug("Request tracked", endpoint=endpoint, count=count)
    
    def wait_if_needed(self, endpoint: str, timeout: float = 30.0) -> float:
        """
        Wait if needed to respect rate limits.
        
        Args:
            endpoint: API endpoint or group name.
            timeout: Maximum time to wait in seconds.
            
        Returns:
            Time waited in seconds, 0 if no wait was needed.
        """
        start_time = time.time()
        wait_time = 0.0
        
        with self.lock:
            # If no limit info or has capacity, no need to wait
            if endpoint not in self.endpoint_limits or self.has_capacity(endpoint):
                return 0.0
            
            # Calculate wait time based on sliding window
            limit_info = self.endpoint_limits[endpoint]
            current = self.sliding_windows[endpoint].current_count()
            
            if current >= limit_info.limit:
                # Need to wait for oldest request to expire
                window = self.sliding_windows[endpoint]
                if window.requests:
                    oldest = window.requests[0]
                    wait_time = (oldest + limit_info.interval) - time.time()
                else:
                    wait_time = 0.1  # Small delay if no requests (shouldn't happen)
            
            # Cap at timeout
            wait_time = min(wait_time, timeout)
            
            # Don't wait if no need
            if wait_time <= 0:
                return 0.0
        
        # Release lock during wait
        logger.info("Rate limit reached, waiting", 
                    endpoint=endpoint, wait_time=wait_time,
                    current=current, limit=limit_info.limit)
        
        # Sleep and return actual wait time
        time.sleep(wait_time)
        return time.time() - start_time
    
    def pre_request(self, endpoint: str, timeout: float = 30.0) -> float:
        """
        Handle pre-request rate limiting.
        
        This should be called before making an API request.
        
        Args:
            endpoint: API endpoint or group name.
            timeout: Maximum time to wait in seconds.
            
        Returns:
            Time waited in seconds.
        """
        return self.wait_if_needed(endpoint, timeout)
    
    def post_request(self, endpoint: str, headers: Optional[Dict[str, Any]] = None) -> None:
        """
        Handle post-request rate limiting updates.
        
        This should be called after receiving an API response.
        
        Args:
            endpoint: API endpoint or group name.
            headers: Response headers, used to update rate limit info.
        """
        self.track_request(endpoint)
        
        if headers:
            self.update_from_headers(endpoint, headers) 