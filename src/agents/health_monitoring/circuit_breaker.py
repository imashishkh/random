"""
Circuit Breaker Pattern Implementation

This module provides circuit breaker implementations for protecting the system
from cascading failures by temporarily disabling operations when failure thresholds
are exceeded.
"""

import time
import threading
import logging
from enum import Enum
from typing import Any, Dict, List, Callable, Optional, TypeVar, Generic, Union
from datetime import datetime

from ...utils.logging.logger import get_logger

logger = get_logger()

# Type variables for generic method execution
T = TypeVar('T')
R = TypeVar('R')

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"         # Normal operation, requests allowed
    OPEN = "open"             # Circuit tripped, all requests fail fast
    HALF_OPEN = "half_open"   # Testing state, allowing limited requests


class CircuitBreakerError(Exception):
    """Exception raised when a circuit breaker prevents operation execution"""
    
    def __init__(self, circuit_name: str, state: CircuitState, last_failure: Optional[str] = None):
        self.circuit_name = circuit_name
        self.state = state
        self.last_failure = last_failure
        message = f"Circuit '{circuit_name}' is {state.value}"
        if last_failure:
            message += f" due to: {last_failure}"
        super().__init__(message)


class CircularBuffer:
    """Fixed-size buffer that overwrites oldest items when full"""
    
    def __init__(self, capacity: int):
        self.capacity = max(capacity, 1)
        self.buffer: List[Any] = []
        
    def add(self, item: Any) -> None:
        """Add an item to the buffer, overwriting oldest if full"""
        if len(self.buffer) >= self.capacity:
            self.buffer.pop(0)  # Remove oldest item
        self.buffer.append(item)
        
    def get_all(self) -> List[Any]:
        """Get all items currently in the buffer"""
        return self.buffer.copy()
    
    def get_latest(self) -> Optional[Any]:
        """Get the most recently added item, or None if buffer is empty"""
        if not self.buffer:
            return None
        return self.buffer[-1]
    
    def clear(self) -> None:
        """Clear the buffer"""
        self.buffer.clear()
        
    def count(self) -> int:
        """Get the number of items in the buffer"""
        return len(self.buffer)


class CircuitBreaker:
    """
    Implementation of the circuit breaker pattern.
    
    The circuit breaker pattern helps prevent cascading failures by
    temporarily disabling operations when a certain threshold of
    failures is reached.
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
        reset_timeout: float = 300.0
    ):
        """
        Initialize the circuit breaker.
        
        Args:
            name: Name identifier for this circuit breaker
            failure_threshold: Number of consecutive failures to trip the circuit
            recovery_timeout: Seconds to wait before attempting recovery (half-open)
            half_open_max_calls: Maximum calls to allow in half-open state
            reset_timeout: Seconds after which to reset failure count if no failures
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.reset_timeout = reset_timeout
        
        # State tracking
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0
        self._last_success_time = time.time()
        self._half_open_calls = 0
        self._state_change_time = time.time()
        
        # Metrics
        self._total_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0
        self._short_circuited_calls = 0
        
        # Lock for thread safety
        self._lock = threading.RLock()
        
        logger.info(f"CircuitBreaker '{name}' initialized with threshold {failure_threshold}")

    @property
    def state(self) -> CircuitState:
        """Get the current circuit state."""
        with self._lock:
            self._check_state_transition()
            return self._state
            
    @property
    def failure_count(self) -> int:
        """Get the current failure count."""
        with self._lock:
            return self._failure_count
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED
        
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (no operations allowed)."""
        return self.state == CircuitState.OPEN
        
    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (limited operations)."""
        return self.state == CircuitState.HALF_OPEN
    
    @property
    def metrics(self) -> Dict[str, Any]:
        """Get circuit breaker metrics."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "total_calls": self._total_calls,
                "successful_calls": self._successful_calls,
                "failed_calls": self._failed_calls,
                "short_circuited_calls": self._short_circuited_calls,
                "last_failure_time": self._last_failure_time,
                "last_success_time": self._last_success_time,
                "state_change_time": self._state_change_time,
                "time_in_current_state": time.time() - self._state_change_time
            }
    
    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function through the circuit breaker.
        
        If the circuit is open, fail fast without calling the function.
        If the circuit is half-open, allow a limited number of calls.
        If the circuit is closed, operate normally.
        
        Args:
            func: Function to execute
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            Result of function execution
            
        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Any exception raised by the function
        """
        with self._lock:
            self._total_calls += 1
            
            # Check for state transitions before executing
            self._check_state_transition()
            
            current_state = self._state
            
            # Fail fast if circuit is open
            if current_state == CircuitState.OPEN:
                logger.debug(f"Circuit '{self.name}' is OPEN, failing fast")
                self._short_circuited_calls += 1
                raise CircuitBreakerError(f"Circuit '{self.name}' is OPEN")
                
            # Control access in half-open state
            if current_state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    logger.debug(f"Circuit '{self.name}' is HALF_OPEN, max calls reached, failing fast")
                    self._short_circuited_calls += 1
                    raise CircuitBreakerError(f"Circuit '{self.name}' is HALF_OPEN and max calls reached")
                self._half_open_calls += 1
                
        # Execute the function (outside the lock to prevent deadlocks)
        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise
    
    def reset(self) -> None:
        """Force reset the circuit breaker to closed state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_success_time = time.time()
            self._half_open_calls = 0
            self._state_change_time = time.time()
            logger.info(f"Circuit '{self.name}' manually reset to CLOSED state")
    
    def trip(self) -> None:
        """Force trip the circuit breaker to open state."""
        with self._lock:
            if self._state != CircuitState.OPEN:
                self._state = CircuitState.OPEN
                self._state_change_time = time.time()
                logger.info(f"Circuit '{self.name}' manually tripped to OPEN state")
    
    def _record_success(self) -> None:
        """Record a successful operation."""
        with self._lock:
            self._successful_calls += 1
            self._last_success_time = time.time()
            
            # If we're half-open and succeeded, close the circuit
            if self._state == CircuitState.HALF_OPEN:
                logger.info(f"Circuit '{self.name}' recovered, transitioning from HALF_OPEN to CLOSED")
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._half_open_calls = 0
                self._state_change_time = time.time()
                
            # Reset failure count after a successful call if we've been closed for a while
            elif (self._state == CircuitState.CLOSED and 
                  self._failure_count > 0 and 
                  time.time() - self._last_failure_time > self.reset_timeout):
                self._failure_count = 0
    
    def _record_failure(self) -> None:
        """Record a failed operation."""
        with self._lock:
            self._failed_calls += 1
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            # If we're half-open and failed, reopen the circuit
            if self._state == CircuitState.HALF_OPEN:
                logger.warning(f"Circuit '{self.name}' failed in HALF_OPEN state, reopening circuit")
                self._state = CircuitState.OPEN
                self._state_change_time = time.time()
                
            # If we've reached the threshold, trip the circuit
            elif self._state == CircuitState.CLOSED and self._failure_count >= self.failure_threshold:
                logger.warning(
                    f"Circuit '{self.name}' tripped after {self._failure_count} failures, "
                    f"transitioning from CLOSED to OPEN"
                )
                self._state = CircuitState.OPEN
                self._state_change_time = time.time()
    
    def _check_state_transition(self) -> None:
        """Check for and apply any pending state transitions."""
        current_time = time.time()
        
        # Check if we need to transition from OPEN to HALF_OPEN
        if (self._state == CircuitState.OPEN and 
            current_time - self._state_change_time > self.recovery_timeout):
            logger.info(
                f"Circuit '{self.name}' recovery timeout elapsed, "
                f"transitioning from OPEN to HALF_OPEN"
            )
            self._state = CircuitState.HALF_OPEN
            self._half_open_calls = 0
            self._state_change_time = current_time


class MarketAwareCircuitBreaker(CircuitBreaker):
    """
    Circuit breaker that adjusts thresholds based on market conditions.
    
    This extension adapts failure thresholds based on market volatility,
    allowing more failures during high volatility periods.
    """
    
    def __init__(
        self,
        name: str,
        market_volatility_service: Any,
        **kwargs: Any
    ):
        """
        Initialize the market-aware circuit breaker.
        
        Args:
            name: Circuit breaker name for identification
            market_volatility_service: Service that provides market volatility data
            **kwargs: Additional parameters passed to CircuitBreaker constructor
        """
        super().__init__(name, **kwargs)
        self.market_volatility_service = market_volatility_service
        self.default_failure_threshold = kwargs.get("failure_threshold", 5)
        
        logger.info(f"Initialized market-aware circuit breaker: {name}")
    
    def execute(self, func: Callable[..., R], market_pair: Optional[str] = None, *args: Any, **kwargs: Any) -> R:
        """
        Execute a function with market-aware threshold adjustment.
        
        Args:
            func: Function to execute
            market_pair: Optional currency pair to check volatility for
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            The result of the function execution
            
        Raises:
            CircuitBreakerError: If the circuit is OPEN or HALF_OPEN with max calls reached
            Any exception raised by the executed function
        """
        # Adjust thresholds based on market volatility if pair provided
        if market_pair:
            try:
                volatility = self.market_volatility_service.get_volatility(market_pair)
                original_threshold = self.failure_threshold
                
                # Higher volatility = more tolerant of failures
                if volatility > 0.8:  # High volatility
                    self.failure_threshold = int(original_threshold * 1.5)
                    logger.debug(f"Adjusted failure threshold to {self.failure_threshold} due to high volatility ({volatility:.2f}) for {market_pair}")
                elif volatility < 0.2:  # Low volatility
                    self.failure_threshold = int(original_threshold * 0.8)
                    logger.debug(f"Adjusted failure threshold to {self.failure_threshold} due to low volatility ({volatility:.2f}) for {market_pair}")
                
                try:
                    return super().execute(func, *args, **kwargs)
                finally:
                    # Restore original threshold
                    self.failure_threshold = original_threshold
                    
            except Exception as e:
                logger.error(f"Error adjusting for market volatility: {str(e)}")
                # Fall back to standard execution if volatility check fails
                return super().execute(func, *args, **kwargs)
        
        # Standard execution if no market pair provided
        return super().execute(func, *args, **kwargs)
    
    def _record_failure(self, execution_time: float, error: str) -> None:
        """
        Record a failure with additional market context.
        
        Args:
            execution_time: Time taken for the operation in seconds
            error: Error message or reason for failure
        """
        super()._record_failure(execution_time, error)
        
        # Add market condition context to the most recent event
        try:
            if self.metrics["recent_events"]:
                last_event = self.metrics["recent_events"][-1]
                if isinstance(last_event, dict):
                    last_event["market_conditions"] = {
                        "overall_volatility": self.market_volatility_service.get_overall_volatility(),
                        "trading_hours": self.market_volatility_service.is_active_trading_hours(),
                        "news_events": self.market_volatility_service.get_recent_news_events()
                    }
        except Exception as e:
            logger.error(f"Error adding market context to failure: {str(e)}")


# Helper function for circuit breaker management
class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers centrally.
    
    This allows retrieving or creating circuit breakers by name,
    and getting aggregated status information.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CircuitBreakerRegistry, cls).__new__(cls)
            cls._instance._circuit_breakers = {}
            cls._instance._lock = threading.RLock()
        return cls._instance
    
    def get_or_create(self, name: str, **kwargs: Any) -> CircuitBreaker:
        """
        Get an existing circuit breaker or create a new one.
        
        Args:
            name: Circuit breaker name
            **kwargs: Parameters for circuit breaker creation if new
            
        Returns:
            Existing or new circuit breaker instance
        """
        with self._lock:
            if name not in self._circuit_breakers:
                # Create a new circuit breaker
                self._circuit_breakers[name] = CircuitBreaker(name, **kwargs)
                logger.debug(f"Created new circuit breaker: {name}")
            return self._circuit_breakers[name]
    
    def get_or_create_market_aware(self, name: str, market_volatility_service: Any, **kwargs: Any) -> MarketAwareCircuitBreaker:
        """
        Get an existing market-aware circuit breaker or create a new one.
        
        Args:
            name: Circuit breaker name
            market_volatility_service: Market volatility service
            **kwargs: Parameters for circuit breaker creation if new
            
        Returns:
            Existing or new market-aware circuit breaker instance
        """
        with self._lock:
            if name not in self._circuit_breakers:
                # Create a new market-aware circuit breaker
                self._circuit_breakers[name] = MarketAwareCircuitBreaker(
                    name, market_volatility_service, **kwargs
                )
                logger.debug(f"Created new market-aware circuit breaker: {name}")
            return self._circuit_breakers[name]
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """
        Get an existing circuit breaker by name.
        
        Args:
            name: Circuit breaker name
            
        Returns:
            Circuit breaker instance or None if not found
        """
        with self._lock:
            return self._circuit_breakers.get(name)
    
    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """
        Get state information for all circuit breakers.
        
        Returns:
            Dictionary mapping circuit breaker names to their state information
        """
        with self._lock:
            return {name: cb.metrics for name, cb in self._circuit_breakers.items()}
    
    def get_open_circuits(self) -> List[str]:
        """
        Get names of all circuit breakers currently in OPEN state.
        
        Returns:
            List of circuit breaker names in OPEN state
        """
        with self._lock:
            return [name for name, cb in self._circuit_breakers.items() 
                   if cb.state == CircuitState.OPEN]
    
    def reset_all(self) -> None:
        """Reset all circuit breakers to CLOSED state"""
        with self._lock:
            for name, cb in self._circuit_breakers.items():
                cb.reset()
            logger.warning(f"Reset all {len(self._circuit_breakers)} circuit breakers to CLOSED state")


# Singleton accessor
def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get the global circuit breaker registry instance"""
    return CircuitBreakerRegistry() 