"""
Authentication module for exchange communications.

This module provides unified authentication services for REST and WebSocket
interfaces, supporting various authentication methods including API key/secret,
JWT tokens, and session-based authentication.

Features:
- JWT-based authentication
- API key/secret authentication with HMAC signing
- WebSocket authentication
- REST API authentication
- Integration with Secret Manager
- Rate limiting
- Unified error handling
"""

from .auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_token,
    refresh_access_token,
    is_token_about_to_expire,
    JWTError,
    ExpiredJWTError,
    InvalidJWTError
)

from .auth.api_key_handler import (
    get_api_key_auth,
    ApiKeyError,
    InvalidSignatureError,
    TimestampExpiredError
)

from .auth.exceptions import (
    AuthenticationError,
    InsufficientPermissionsError,
    RateLimitExceededError,
    register_exception_handlers
)

# Import REST authentication
from .auth.rest import (
    get_current_user,
    get_current_active_user,
    require_scopes,
    validate_api_key
)

# Import WebSocket authentication
from .auth.websocket import (
    authenticate_ws_connection,
    authenticate_ws_with_message,
    validate_ws_token_on_connect,
    validate_ws_message_auth,
    refresh_ws_token,
    WebSocketAuthMiddleware
)

# Helper function to setup authentication
def setup_auth(app, 
              auth_enabled: bool = True, 
              public_paths: list = None, 
              rate_limit: int = 100,
              rate_limit_enabled: bool = True):
    """
    Setup authentication for a FastAPI application.
    
    Args:
        app: FastAPI application
        auth_enabled: Whether authentication is enabled
        public_paths: List of paths that don't require authentication
        rate_limit: Maximum number of requests per minute
        rate_limit_enabled: Whether rate limiting is enabled
        
    Returns:
        app: FastAPI application with authentication setup
    """
    from fastapi import FastAPI
    from src.exchange.auth.rest.middleware import (
        AuthenticationMiddleware, 
        RateLimitMiddleware
    )
    
    # Default public paths
    if public_paths is None:
        public_paths = [
            "/docs", 
            "/redoc", 
            "/openapi.json",
            "/health",
            "/metrics"
        ]
    
    # Add authentication middleware
    app.add_middleware(
        AuthenticationMiddleware,
        public_paths=public_paths,
        auth_enabled=auth_enabled
    )
    
    # Add rate limit middleware
    if rate_limit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            rate_limit=rate_limit,
            window_seconds=60,
            enabled=rate_limit_enabled,
            public_paths=public_paths
        )
    
    # Register exception handlers
    register_exception_handlers(app)
    
    return app

__all__ = [
    # JWT authentication
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "validate_token",
    "refresh_access_token",
    "is_token_about_to_expire",
    "JWTError",
    "ExpiredJWTError",
    "InvalidJWTError",
    
    # API key authentication
    "get_api_key_auth",
    "ApiKeyError",
    "InvalidSignatureError",
    "TimestampExpiredError",
    
    # Exceptions
    "AuthenticationError",
    "InsufficientPermissionsError",
    "RateLimitExceededError",
    "register_exception_handlers",
    
    # REST authentication
    "get_current_user",
    "get_current_active_user",
    "require_scopes",
    "validate_api_key",
    
    # WebSocket authentication
    "authenticate_ws_connection",
    "authenticate_ws_with_message",
    "validate_ws_token_on_connect",
    "validate_ws_message_auth",
    "refresh_ws_token",
    "WebSocketAuthMiddleware",
    
    # Setup function
    "setup_auth"
] 