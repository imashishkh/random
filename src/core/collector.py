"""
Base data collector module.

This module provides the base class for all data collectors with common
functionality like error handling, retry logic, and logging.
"""

import time
import logging
import traceback
import random
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, Callable, TypeVar, Generic
from datetime import datetime, timedelta
from functools import wraps
from pydantic import BaseModel, ValidationError


# Setup logger
logger = logging.getLogger(__name__)

# Type variable for the data collector result
T = TypeVar('T')


class RetrySettings(BaseModel):
    """Settings for retry logic."""
    max_retries: int = 3
    initial_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    backoff_factor: float = 2.0
    jitter: float = 0.1
    retry_on_exceptions: List[type] = []
    retry_on_status_codes: List[int] = []


class RateLimitSettings(BaseModel):
    """Settings for rate limiting."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    enabled: bool = True


class CollectorError(Exception):
    """Base exception for collector errors."""
    pass


class RequestError(CollectorError):
    """Exception for request errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, response: Any = None):
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class ValidationError(CollectorError):
    """Exception for data validation errors."""
    pass


class AuthenticationError(CollectorError):
    """Exception for authentication errors."""
    pass


class RateLimitError(CollectorError):
    """Exception for rate limit exceeded errors."""
    pass


class CircuitBreakerState:
    """Circuit breaker state manager to prevent repeated failures."""
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout  # seconds
        self.last_failure_time: Optional[datetime] = None
        self.is_open = False
    
    def record_failure(self):
        """Record a failure and potentially open the circuit."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.failure_count >= self.failure_threshold:
            self.is_open = True
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
    
    def record_success(self):
        """Record a success and reset the failure count."""
        self.failure_count = 0
        self.is_open = False
    
    def can_try(self) -> bool:
        """Check if a request can be attempted."""
        if not self.is_open:
            return True
        
        # Check if recovery timeout has elapsed
        if self.last_failure_time and datetime.utcnow() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
            logger.info("Circuit breaker recovery timeout elapsed, allowing trial request")
            return True
        
        return False


class BaseCollector(Generic[T], ABC):
    """Base class for all data collectors with common functionality."""
    
    def __init__(
        self,
        name: str,
        retry_settings: Optional[RetrySettings] = None,
        rate_limit_settings: Optional[RateLimitSettings] = None,
        circuit_breaker_failure_threshold: int = 5,
        circuit_breaker_recovery_timeout: int = 60
    ):
        """Initialize the collector with the given settings.
        
        Args:
            name: Unique name for this collector
            retry_settings: Settings for retry logic
            rate_limit_settings: Settings for rate limiting
            circuit_breaker_failure_threshold: Number of failures before opening circuit
            circuit_breaker_recovery_timeout: Seconds to wait before trying again after circuit opens
        """
        self.name = name
        self.retry_settings = retry_settings or RetrySettings()
        self.rate_limit_settings = rate_limit_settings or RateLimitSettings()
        
        # Initialize circuit breaker
        self.circuit_breaker = CircuitBreakerState(
            failure_threshold=circuit_breaker_failure_threshold,
            recovery_timeout=circuit_breaker_recovery_timeout
        )
        
        # Initialize rate limiting counters
        self.request_timestamps: List[datetime] = []
        
        logger.info(f"Initialized {self.name} collector")
    
    @abstractmethod
    async def collect(self, *args, **kwargs) -> T:
        """Collect data from the source. Must be implemented by subclasses."""
        pass
    
    @abstractmethod
    async def validate(self, data: Any) -> T:
        """Validate and process the collected data. Must be implemented by subclasses."""
        pass
    
    async def process_with_retry(
        self, 
        func: Callable[..., Any], 
        *args, 
        retry_settings: Optional[RetrySettings] = None,
        **kwargs
    ) -> Any:
        """Execute a function with retry logic.
        
        Args:
            func: The function to execute
            *args: Arguments to pass to the function
            retry_settings: Override default retry settings
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            The result of the function
            
        Raises:
            CollectorError: If the function fails after all retries
        """
        settings = retry_settings or self.retry_settings
        retry_count = 0
        last_exception = None
        
        # Check circuit breaker before attempting
        if not self.circuit_breaker.can_try():
            logger.warning(f"{self.name}: Circuit breaker open, skipping request")
            raise CollectorError(f"Circuit breaker open for {self.name}")
        
        # Check rate limits before attempting
        if not self._check_rate_limits():
            logger.warning(f"{self.name}: Rate limit exceeded")
            raise RateLimitError(f"Rate limit exceeded for {self.name}")
        
        while retry_count <= settings.max_retries:
            try:
                # Log attempt
                if retry_count > 0:
                    logger.info(f"{self.name}: Retry attempt {retry_count} of {settings.max_retries}")
                
                # Record request for rate limiting
                self._record_request()
                
                # Execute function
                result = await func(*args, **kwargs)
                
                # Record success for circuit breaker
                self.circuit_breaker.record_success()
                
                return result
                
            except Exception as e:
                retry_count += 1
                last_exception = e
                
                # Check if we should retry based on exception type
                should_retry = False
                if not settings.retry_on_exceptions:
                    # Retry on any exception if no specific exceptions are specified
                    should_retry = True
                else:
                    # Check if exception is in the retry list
                    for exception_type in settings.retry_on_exceptions:
                        if isinstance(e, exception_type):
                            should_retry = True
                            break
                
                # Check status code for RequestError
                if isinstance(e, RequestError) and settings.retry_on_status_codes:
                    if e.status_code in settings.retry_on_status_codes:
                        should_retry = True
                
                # Don't retry if max retries reached
                if retry_count > settings.max_retries:
                    should_retry = False
                
                if should_retry:
                    # Calculate delay with exponential backoff and jitter
                    delay = min(
                        settings.initial_delay * (settings.backoff_factor ** (retry_count - 1)),
                        settings.max_delay
                    )
                    
                    # Add jitter
                    jitter_amount = delay * settings.jitter
                    delay = delay + (jitter_amount * (2 * (0.5 - random.random())))
                    
                    logger.warning(
                        f"{self.name}: Request failed, retrying in {delay:.2f}s: {str(e)}"
                    )
                    
                    # Wait before retrying
                    await asyncio.sleep(delay)
                else:
                    # Record failure for circuit breaker
                    self.circuit_breaker.record_failure()
                    
                    # Log and re-raise
                    logger.error(
                        f"{self.name}: Request failed with no more retries: {str(e)}\n{traceback.format_exc()}"
                    )
                    raise
        
        # Record failure for circuit breaker
        self.circuit_breaker.record_failure()
        
        # If we got here, all retries failed
        logger.error(f"{self.name}: All retry attempts failed")
        if last_exception:
            raise last_exception
        else:
            raise CollectorError(f"All retry attempts failed for {self.name}")
    
    def _record_request(self):
        """Record a request for rate limiting."""
        now = datetime.utcnow()
        self.request_timestamps.append(now)
        
        # Clean up old timestamps
        day_ago = now - timedelta(days=1)
        self.request_timestamps = [t for t in self.request_timestamps if t > day_ago]
    
    def _check_rate_limits(self) -> bool:
        """Check if the request would exceed rate limits.
        
        Returns:
            bool: True if request is allowed, False if rate limit would be exceeded
        """
        if not self.rate_limit_settings.enabled:
            return True
        
        now = datetime.utcnow()
        
        # Check daily limit
        day_ago = now - timedelta(days=1)
        requests_last_day = len([t for t in self.request_timestamps if t > day_ago])
        if requests_last_day >= self.rate_limit_settings.requests_per_day:
            return False
        
        # Check hourly limit
        hour_ago = now - timedelta(hours=1)
        requests_last_hour = len([t for t in self.request_timestamps if t > hour_ago])
        if requests_last_hour >= self.rate_limit_settings.requests_per_hour:
            return False
        
        # Check minute limit
        minute_ago = now - timedelta(minutes=1)
        requests_last_minute = len([t for t in self.request_timestamps if t > minute_ago])
        if requests_last_minute >= self.rate_limit_settings.requests_per_minute:
            return False
        
        return True
    
    async def collect_and_validate(self, *args, **kwargs) -> T:
        """Collect and validate data in one operation.
        
        This is a convenience method that combines collect() and validate().
        
        Args:
            *args: Arguments to pass to collect()
            **kwargs: Keyword arguments to pass to collect()
            
        Returns:
            Validated data of type T
        """
        raw_data = await self.collect(*args, **kwargs)
        return await self.validate(raw_data) 