"""
Exchange Exceptions

This module defines custom exceptions for exchange operations.
"""

from typing import Any, Dict, Optional


class ExchangeError(Exception):
    """Base class for all exchange-related exceptions."""
    
    def __init__(self, message: str, code: Optional[int] = None, 
                 details: Optional[Dict[str, Any]] = None):
        """
        Initialize the exception.
        
        Args:
            message: Error message.
            code: Error code.
            details: Additional error details.
        """
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)
    
    def __str__(self) -> str:
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


class AuthenticationError(ExchangeError):
    """Exception raised when authentication fails."""
    pass


class RateLimitError(ExchangeError):
    """Exception raised when rate limits are exceeded."""
    
    def __init__(self, message: str, code: Optional[int] = None, 
                 retry_after: Optional[int] = None, 
                 details: Optional[Dict[str, Any]] = None):
        """
        Initialize the exception.
        
        Args:
            message: Error message.
            code: Error code.
            retry_after: Suggested time to wait before retrying in seconds.
            details: Additional error details.
        """
        super().__init__(message, code, details)
        self.retry_after = retry_after


class InsufficientFundsError(ExchangeError):
    """Exception raised when account has insufficient funds."""
    pass


class InvalidOrderError(ExchangeError):
    """Exception raised when an order is invalid."""
    pass


class CircuitBreakerError(ExchangeError):
    """Exception raised when a circuit breaker is open."""
    
    def __init__(self, message: str, category: str, 
                 retry_after: Optional[float] = None,
                 details: Optional[Dict[str, Any]] = None):
        """
        Initialize the exception.
        
        Args:
            message: Error message.
            category: Circuit breaker category.
            retry_after: Suggested time to wait before retrying in seconds.
            details: Additional error details.
        """
        super().__init__(message, None, details)
        self.category = category
        self.retry_after = retry_after


class NetworkError(ExchangeError):
    """Exception raised when a network error occurs."""
    pass


class ServerError(ExchangeError):
    """Exception raised when the exchange server returns an error."""
    pass


class TimeoutError(ExchangeError):
    """Exception raised when a request times out."""
    pass


class ExchangeOperationError(ExchangeError):
    """Exception raised for general exchange operation errors."""
    pass


class SymbolNotFoundError(ExchangeError):
    """Exception raised when a symbol is not found."""
    pass


class ExchangeMaintenanceError(ExchangeError):
    """Exception raised when the exchange is in maintenance mode."""
    pass


class WebSocketError(ExchangeError):
    """Exception raised for WebSocket connection issues."""
    pass 