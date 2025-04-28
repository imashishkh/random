"""
Order throttling module for the execution system.
Provides rate limiting mechanisms to prevent excessive order flow.
"""
import abc
import time
import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple, Union
from datetime import datetime, timedelta
from threading import Lock

from .execution.core.base import Order

# Configure logger
logger = logging.getLogger(__name__)

class ThrottlingResult:
    """Class representing the result of a throttling check."""
    
    def __init__(self, allowed: bool, wait_time: float = 0, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        """
        Initialize a throttling result.
        
        Args:
            allowed: Whether the order is allowed to proceed
            wait_time: Time in seconds to wait before retrying (if not allowed)
            message: Optional message explaining the result
            details: Optional details about the throttling
        """
        self.allowed = allowed
        self.wait_time = wait_time
        self.message = message
        self.details = details or {}
        
    def __bool__(self) -> bool:
        """Return whether the order is allowed to proceed."""
        return self.allowed

class BaseThrottler(abc.ABC):
    """Abstract base class for order throttlers."""
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize a throttler.
        
        Args:
            name: Throttler name
            config: Optional configuration
        """
        self.name = name
        self.config = config or {}
        logger.info(f"Initialized throttler: {name}")
    
    @abc.abstractmethod
    def check(self, order: Order, context: Optional[Dict[str, Any]] = None) -> ThrottlingResult:
        """
        Check if an order can proceed based on throttling rules.
        
        Args:
            order: Order to check
            context: Optional context information
            
        Returns:
            ThrottlingResult indicating whether the order is allowed to proceed
        """
        pass
    
    def _create_result(self, allowed: bool, wait_time: float = 0, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> ThrottlingResult:
        """
        Create a throttling result.
        
        Args:
            allowed: Whether the order is allowed to proceed
            wait_time: Time in seconds to wait before retrying (if not allowed)
            message: Optional message explaining the result
            details: Optional details about the throttling
            
        Returns:
            ThrottlingResult
        """
        result = ThrottlingResult(allowed, wait_time, message, details)
        
        if not allowed:
            logger.warning(f"Throttling applied: {self.name} - {message} (wait: {wait_time}s)")
        
        return result

class OrderThrottler:
    """
    Composite throttler that runs a chain of throttling checks on an order.
    Uses the Chain of Responsibility pattern.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the order throttler.
        
        Args:
            config: Optional configuration
        """
        self.throttlers: List[BaseThrottler] = []
        self.config = config or {}
        logger.info("Initialized order throttler")
    
    def add_throttler(self, throttler: BaseThrottler) -> None:
        """
        Add a throttler to the chain.
        
        Args:
            throttler: Throttler to add
        """
        self.throttlers.append(throttler)
        logger.info(f"Added throttler: {throttler.name}")
    
    def check(self, order: Order, context: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[float], Optional[str], Optional[Dict[str, Any]]]:
        """
        Check if an order can proceed based on all registered throttlers.
        
        Args:
            order: Order to check
            context: Optional context information
            
        Returns:
            Tuple of (allowed, wait_time, message, details)
        """
        context = context or {}
        
        logger.info(f"Checking throttling for order {order.client_order_id}")
        
        max_wait_time = 0
        combined_details = {}
        
        for throttler in self.throttlers:
            result = throttler.check(order, context)
            
            if not result.allowed:
                # If multiple throttlers reject the order, return the one with the longest wait time
                if result.wait_time > max_wait_time:
                    max_wait_time = result.wait_time
                    message = result.message
                    details = result.details
                    
                    # Accumulate details from all throttlers
                    combined_details.update(details)
                    combined_details["throttler"] = throttler.name
                
        if max_wait_time > 0:
            return False, max_wait_time, message, combined_details
        
        return True, None, None, None
    
    async def wait_if_needed(self, order: Order, context: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Check throttling and wait if necessary.
        
        Args:
            order: Order to check
            context: Optional context information
            
        Returns:
            Tuple of (success, error_message, error_details)
        """
        allowed, wait_time, message, details = self.check(order, context)
        
        if not allowed and wait_time is not None:
            logger.info(f"Throttling: waiting for {wait_time}s before processing order {order.client_order_id}")
            await asyncio.sleep(wait_time)
            
            # Recheck after waiting
            allowed, wait_time, message, details = self.check(order, context)
            
            if not allowed:
                return False, message, details
        
        return True, None, None 