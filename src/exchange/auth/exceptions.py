"""
Authentication exceptions and error handlers.

Unified error handling for both REST and WebSocket authentication.
"""
import logging
from typing import Dict, Any, Optional, Union
from fastapi import Request, status
from fastapi.responses import JSONResponse

# Import JWT exceptions
from .auth.jwt_handler import JWTError, ExpiredJWTError, InvalidJWTError

# Import API key exceptions
from .auth.api_key_handler import ApiKeyError, InvalidSignatureError, TimestampExpiredError

# Configure logger
logger = logging.getLogger(__name__)

# Error codes
AUTH_ERROR_CODES = {
    # General authentication errors
    "AUTH_REQUIRED": "Authentication required",
    "INVALID_CREDENTIALS": "Invalid credentials",
    "INSUFFICIENT_PERMISSIONS": "Insufficient permissions",
    "RATE_LIMITED": "Rate limit exceeded",
    
    # JWT errors
    "TOKEN_EXPIRED": "Authentication token has expired",
    "INVALID_TOKEN": "Invalid authentication token",
    "MISSING_TOKEN": "Authentication token is required",
    
    # API key errors
    "INVALID_SIGNATURE": "Invalid request signature",
    "TIMESTAMP_EXPIRED": "Request timestamp is outside of allowed window",
    "INVALID_API_KEY": "Invalid API key",
    "MISSING_API_KEY": "API key is required",
    
    # WebSocket errors
    "WS_AUTH_TIMEOUT": "WebSocket authentication timeout",
    "WS_INVALID_AUTH_FORMAT": "Invalid WebSocket authentication format"
}


class AuthenticationError(Exception):
    """Base class for authentication errors."""
    
    def __init__(self, 
                error_code: str, 
                message: str = None, 
                status_code: int = status.HTTP_401_UNAUTHORIZED,
                extra_data: Optional[Dict[str, Any]] = None):
        """
        Initialize the authentication error.
        
        Args:
            error_code: Error code
            message: Error message (defaults to standard message for error code)
            status_code: HTTP status code
            extra_data: Additional data to include in the response
        """
        self.error_code = error_code
        self.message = message or AUTH_ERROR_CODES.get(error_code, "Authentication error")
        self.status_code = status_code
        self.extra_data = extra_data or {}
        super().__init__(self.message)


class InsufficientPermissionsError(AuthenticationError):
    """Exception raised when user has insufficient permissions."""
    
    def __init__(self, message: str = None, extra_data: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code="INSUFFICIENT_PERMISSIONS",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            extra_data=extra_data
        )


class RateLimitExceededError(AuthenticationError):
    """Exception raised when rate limit is exceeded."""
    
    def __init__(self, message: str = None, extra_data: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code="RATE_LIMITED",
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            extra_data=extra_data
        )


def get_error_response(
    error_code: str,
    message: str = None,
    status_code: int = status.HTTP_401_UNAUTHORIZED,
    extra_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a standard error response.
    
    Args:
        error_code: Error code
        message: Error message (defaults to standard message for error code)
        status_code: HTTP status code
        extra_data: Additional data to include in the response
        
    Returns:
        Dict: Error response data
    """
    response = {
        "error": {
            "code": error_code,
            "message": message or AUTH_ERROR_CODES.get(error_code, "Authentication error"),
            "status": status_code
        }
    }
    
    # Add extra data if provided
    if extra_data:
        response["error"]["details"] = extra_data
    
    return response


async def handle_auth_exception(request: Request, exc: AuthenticationError) -> JSONResponse:
    """
    Handle authentication exceptions for FastAPI.
    
    Args:
        request: FastAPI request
        exc: Authentication exception
        
    Returns:
        JSONResponse: Error response
    """
    # Log the error
    client_ip = request.client.host if request.client else "unknown"
    logger.warning(f"Authentication error from {client_ip}: {exc.error_code} - {exc.message}")
    
    # Create error response
    response_data = get_error_response(
        error_code=exc.error_code,
        message=exc.message,
        status_code=exc.status_code,
        extra_data=exc.extra_data
    )
    
    # Add WWW-Authenticate header for 401 responses
    headers = {}
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        headers["WWW-Authenticate"] = "Bearer"
    
    return JSONResponse(
        status_code=exc.status_code,
        content=response_data,
        headers=headers
    )


async def handle_jwt_error(request: Request, exc: JWTError) -> JSONResponse:
    """
    Handle JWT exceptions for FastAPI.
    
    Args:
        request: FastAPI request
        exc: JWT exception
        
    Returns:
        JSONResponse: Error response
    """
    # Log the error
    client_ip = request.client.host if request.client else "unknown"
    logger.warning(f"JWT error from {client_ip}: {exc.error_code} - {exc.message}")
    
    # Create error response
    response_data = get_error_response(
        error_code=exc.error_code,
        message=exc.message,
        status_code=status.HTTP_401_UNAUTHORIZED
    )
    
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=response_data,
        headers={"WWW-Authenticate": "Bearer"}
    )


async def handle_api_key_error(request: Request, exc: ApiKeyError) -> JSONResponse:
    """
    Handle API key exceptions for FastAPI.
    
    Args:
        request: FastAPI request
        exc: API key exception
        
    Returns:
        JSONResponse: Error response
    """
    # Log the error
    client_ip = request.client.host if request.client else "unknown"
    logger.warning(f"API key error from {client_ip}: {exc.error_code} - {exc.message}")
    
    # Create error response
    response_data = get_error_response(
        error_code=exc.error_code,
        message=exc.message,
        status_code=status.HTTP_401_UNAUTHORIZED
    )
    
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=response_data
    )


def register_exception_handlers(app):
    """
    Register authentication exception handlers with FastAPI app.
    
    Args:
        app: FastAPI application
    """
    # Register general authentication exception handler
    app.add_exception_handler(AuthenticationError, handle_auth_exception)
    
    # Register JWT exception handlers
    app.add_exception_handler(JWTError, handle_jwt_error)
    app.add_exception_handler(ExpiredJWTError, handle_jwt_error)
    app.add_exception_handler(InvalidJWTError, handle_jwt_error)
    
    # Register API key exception handlers
    app.add_exception_handler(ApiKeyError, handle_api_key_error)
    app.add_exception_handler(InvalidSignatureError, handle_api_key_error)
    app.add_exception_handler(TimestampExpiredError, handle_api_key_error)
    
    # Register authorization error handler
    app.add_exception_handler(InsufficientPermissionsError, handle_auth_exception)
    
    # Register rate limit error handler
    app.add_exception_handler(RateLimitExceededError, handle_auth_exception) 