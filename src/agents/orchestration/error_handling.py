"""
Error Handling for Async Agent Orchestration

This module provides error classification and handling strategies for the
async agent process management system using TaskGroup.
"""

import logging
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories of errors that can occur in agent execution"""
    TRANSIENT_NETWORK = "transient_network"  # Temporary network issues
    EXCHANGE_RATE_LIMIT = "exchange_rate_limit"  # Exchange API rate limiting
    MARKET_DATA_UNAVAILABLE = "market_data_unavailable"  # Market data not available
    AUTHENTICATION_FAILURE = "authentication_failure"  # Authentication issues
    INSUFFICIENT_FUNDS = "insufficient_funds"  # Insufficient funds for trading
    INVALID_ORDER = "invalid_order"  # Invalid order parameters
    RISK_LIMIT_EXCEEDED = "risk_limit_exceeded"  # Risk management limits exceeded
    INTERNAL_ERROR = "internal_error"  # Internal agent error
    UNKNOWN = "unknown"  # Unknown error type


class BaseAgentError(Exception):
    """Base class for all agent-related errors"""
    
    def __init__(
        self, 
        message: str, 
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the agent error with metadata.
        
        Args:
            message: Error message
            category: Error category for classification
            details: Additional error details
        """
        self.category = category
        self.details = details or {}
        super().__init__(message)


class RecoverableError(BaseAgentError):
    """
    Error that can be recovered from without terminating the agent.
    
    These errors typically represent transient issues that might resolve
    with retries or simple recovery procedures.
    """
    
    def __init__(
        self, 
        message: str, 
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        retry_after: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize a recoverable error.
        
        Args:
            message: Error message
            category: Error category for classification
            retry_after: Suggested time in seconds to wait before retry
            details: Additional error details
        """
        self.retry_after = retry_after
        super().__init__(message, category, details)


class NonRecoverableError(BaseAgentError):
    """
    Error that cannot be recovered from and requires agent termination.
    
    These errors represent serious issues that prevent the agent from
    functioning correctly and require external intervention.
    """
    
    def __init__(
        self, 
        message: str, 
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize a non-recoverable error.
        
        Args:
            message: Error message
            category: Error category for classification
            details: Additional error details
        """
        super().__init__(message, category, details)


class TaskCancellationError(NonRecoverableError):
    """Error raised when a task is cancelled by the system."""
    
    def __init__(self, message: str = "Task was cancelled", details: Optional[Dict[str, Any]] = None):
        """Initialize a task cancellation error."""
        super().__init__(message, ErrorCategory.INTERNAL_ERROR, details)


class ShutdownError(BaseAgentError):
    """Error raised during the shutdown process."""
    
    def __init__(
        self, 
        message: str, 
        stage: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize a shutdown error.
        
        Args:
            message: Error message
            stage: The shutdown stage where the error occurred
            details: Additional error details
        """
        self.stage = stage
        details = details or {}
        details["shutdown_stage"] = stage
        super().__init__(message, ErrorCategory.INTERNAL_ERROR, details)


class RiskApprovalError(RecoverableError):
    """Error raised when a trade is rejected by risk management."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize a risk approval error."""
        super().__init__(message, ErrorCategory.RISK_LIMIT_EXCEEDED, details=details)


class TradeExecutionError(RecoverableError):
    """Error raised during trade execution."""
    
    def __init__(
        self, 
        message: str, 
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        retry_after: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize a trade execution error."""
        super().__init__(message, category, retry_after, details)


# Helper functions for error categorization and handling

def categorize_error(error: Exception) -> ErrorCategory:
    """
    Categorize an exception based on its type and message.
    
    Args:
        error: The exception to categorize
        
    Returns:
        ErrorCategory for the exception
    """
    if isinstance(error, BaseAgentError):
        return error.category
        
    error_str = str(error).lower()
    
    # Network-related errors
    if any(s in error_str for s in ["network", "connection", "timeout", "conn", "socket"]):
        return ErrorCategory.TRANSIENT_NETWORK
        
    # Rate limiting
    if any(s in error_str for s in ["rate limit", "too many requests", "429"]):
        return ErrorCategory.EXCHANGE_RATE_LIMIT
        
    # Authentication
    if any(s in error_str for s in ["auth", "unauthorized", "permission", "token", "credential"]):
        return ErrorCategory.AUTHENTICATION_FAILURE
        
    # Funds
    if any(s in error_str for s in ["insufficient", "balance", "funds"]):
        return ErrorCategory.INSUFFICIENT_FUNDS
        
    # Invalid order
    if any(s in error_str for s in ["invalid", "order", "parameter"]):
        return ErrorCategory.INVALID_ORDER
        
    # Market data
    if any(s in error_str for s in ["market data", "price", "not available"]):
        return ErrorCategory.MARKET_DATA_UNAVAILABLE
        
    return ErrorCategory.UNKNOWN


def is_error_recoverable(error: Exception) -> bool:
    """
    Determine if an error is recoverable.
    
    Args:
        error: The exception to check
        
    Returns:
        True if the error is recoverable, False otherwise
    """
    if isinstance(error, RecoverableError):
        return True
    elif isinstance(error, NonRecoverableError):
        return False
        
    # Categorize the error and check if it's a recoverable category
    category = categorize_error(error)
    
    recoverable_categories = [
        ErrorCategory.TRANSIENT_NETWORK,
        ErrorCategory.EXCHANGE_RATE_LIMIT,
        ErrorCategory.MARKET_DATA_UNAVAILABLE
    ]
    
    return category in recoverable_categories


class BackoffStrategy:
    """Base class for backoff strategies."""
    
    def delay(self, attempt: int) -> float:
        """
        Calculate delay for the given attempt.
        
        Args:
            attempt: Current attempt number (1-based)
            
        Returns:
            Delay in seconds
        """
        raise NotImplementedError("Subclasses must implement this method")


class ExponentialBackoff(BackoffStrategy):
    """Exponential backoff strategy with jitter."""
    
    def __init__(
        self, 
        initial: float = 1.0, 
        maximum: float = 60.0,
        factor: float = 2.0,
        jitter: float = 0.1
    ):
        """
        Initialize exponential backoff.
        
        Args:
            initial: Initial delay in seconds
            maximum: Maximum delay in seconds
            factor: Exponential factor
            jitter: Jitter factor (0-1) to randomize delay
        """
        self.initial = initial
        self.maximum = maximum
        self.factor = factor
        self.jitter = jitter
        
    def delay(self, attempt: int) -> float:
        """
        Calculate delay with exponential backoff.
        
        Args:
            attempt: Current attempt number (1-based)
            
        Returns:
            Delay in seconds
        """
        import random
        
        # Calculate exponential delay
        delay = min(self.maximum, self.initial * (self.factor ** (attempt - 1)))
        
        # Add jitter if needed
        if self.jitter > 0:
            jitter_amount = delay * self.jitter
            delay = random.uniform(delay - jitter_amount, delay + jitter_amount)
            
        return delay 