"""
Binance API exceptions.

This module contains custom exceptions for the Binance API client.
"""

from typing import Any, Dict, Optional


class BinanceAPIException(Exception):
    """Base exception for Binance API errors."""
    
    def __init__(
        self, 
        status_code: Optional[int] = None,
        response: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        request_info: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize BinanceAPIException.
        
        Args:
            status_code: HTTP status code
            response: Response JSON from the API
            message: Error message
            request_info: Information about the request
        """
        self.status_code = status_code
        self.response = response
        self.request_info = request_info
        
        if message:
            self.message = message
        elif response and "msg" in response:
            self.message = response["msg"]
        elif response and "message" in response:
            self.message = response["message"]
        else:
            self.message = "Unknown Binance API error"
            
        self.code = response.get("code", -1) if response else -1
        
        super().__init__(self.message)
        
    def __str__(self) -> str:
        """String representation of the exception."""
        return (
            f"BinanceAPIException(status_code={self.status_code}, "
            f"code={self.code}, message={self.message})"
        )


class BinanceRequestException(Exception):
    """Exception raised for errors in the request to Binance API."""
    
    def __init__(self, message: str, request_info: Optional[Dict[str, Any]] = None):
        """
        Initialize BinanceRequestException.
        
        Args:
            message: Error message
            request_info: Information about the request
        """
        self.message = message
        self.request_info = request_info
        super().__init__(self.message)
        
    def __str__(self) -> str:
        """String representation of the exception."""
        return f"BinanceRequestException(message={self.message})"


class BinanceResponseException(Exception):
    """Exception raised for errors in the response from Binance API."""
    
    def __init__(self, message: str, response: Optional[Dict[str, Any]] = None):
        """
        Initialize BinanceResponseException.
        
        Args:
            message: Error message
            response: Response data
        """
        self.message = message
        self.response = response
        super().__init__(self.message)
        
    def __str__(self) -> str:
        """String representation of the exception."""
        return f"BinanceResponseException(message={self.message})"


class BinanceOrderException(BinanceAPIException):
    """Exception raised for errors related to orders."""
    
    def __str__(self) -> str:
        """String representation of the exception."""
        return f"BinanceOrderException(code={self.code}, message={self.message})"


class BinanceRateLimitException(BinanceAPIException):
    """Exception raised when the rate limit is exceeded."""
    
    def __init__(
        self,
        status_code: Optional[int] = None,
        response: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        request_info: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize BinanceRateLimitException.
        
        Args:
            status_code: HTTP status code
            response: Response JSON from the API
            message: Error message
            request_info: Information about the request
        """
        super().__init__(status_code, response, message, request_info)
        
        # Try to extract retry-after from headers
        self.retry_after = None
        if request_info and 'headers' in request_info:
            headers = request_info['headers']
            if 'Retry-After' in headers:
                try:
                    self.retry_after = int(headers['Retry-After'])
                except (ValueError, TypeError):
                    pass
        
    def __str__(self) -> str:
        """String representation of the exception."""
        retry_info = f", retry_after={self.retry_after}" if self.retry_after else ""
        return f"BinanceRateLimitException(code={self.code}, message={self.message}{retry_info})"


class BinanceWebSocketException(Exception):
    """Exception raised for WebSocket errors."""
    
    def __init__(self, message: str, connection_info: Optional[Dict[str, Any]] = None):
        """
        Initialize BinanceWebSocketException.
        
        Args:
            message: Error message
            connection_info: Information about the WebSocket connection
        """
        self.message = message
        self.connection_info = connection_info
        super().__init__(self.message)
        
    def __str__(self) -> str:
        """String representation of the exception."""
        return f"BinanceWebSocketException(message={self.message})"


class BinanceTimeoutException(BinanceRequestException):
    """Exception raised when a request to Binance API times out."""
    
    def __str__(self) -> str:
        """String representation of the exception."""
        return f"BinanceTimeoutException(message={self.message})"


def handle_binance_error(
    status_code: int, 
    response: Dict[str, Any],
    request_info: Optional[Dict[str, Any]] = None
) -> Exception:
    """
    Handle Binance API errors based on status code and response.
    
    Args:
        status_code: HTTP status code
        response: Response JSON from the API
        request_info: Information about the request
        
    Returns:
        Appropriate exception based on the error.
    """
    error_code = response.get('code', -1)
    
    # Rate limit error
    if status_code == 429 or error_code == -429:
        return BinanceRateLimitException(status_code, response, request_info=request_info)
    
    # Order errors
    if 4000 <= error_code < 5000:
        return BinanceOrderException(status_code, response, request_info=request_info)
    
    # Default API error
    return BinanceAPIException(status_code, response, request_info=request_info) 