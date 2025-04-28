"""
REST authentication middleware.

This module provides middleware for authenticating REST API requests.
"""
import logging
from typing import Dict, Any, Optional, Union, List
import time

from fastapi import Request, Response, status
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from .auth.jwt_handler import (
    get_token_from_authorization_header,
    validate_token
)
from .auth.exceptions import (
    AuthenticationError,
    RateLimitExceededError
)

# Configure logger
logger = logging.getLogger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware for authenticating REST API requests.
    
    This middleware checks for a valid JWT token in the request
    headers, query parameters, or cookies.
    """
    
    def __init__(
        self,
        app,
        public_paths: Optional[List[str]] = None,
        auth_enabled: bool = True
    ):
        """
        Initialize the authentication middleware.
        
        Args:
            app: FastAPI application
            public_paths: List of paths that don't require authentication
            auth_enabled: Whether authentication is enabled
        """
        super().__init__(app)
        self.public_paths = public_paths or []
        self.auth_enabled = auth_enabled
    
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint
    ) -> Response:
        """
        Process the request through the authentication middleware.
        
        Args:
            request: FastAPI request
            call_next: Next endpoint in the middleware chain
            
        Returns:
            Response: FastAPI response
        """
        # Skip authentication if disabled or for public paths
        if not self.auth_enabled or self._is_public_path(request.url.path):
            return await call_next(request)
        
        # Skip authentication for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Get token from various sources
        token = self._get_token_from_request(request)
        
        if not token:
            # No token found, let the endpoint handle it
            # The endpoint can still enforce authentication if needed
            return await call_next(request)
        
        # Validate token
        is_valid, payload = validate_token(token)
        
        if not is_valid:
            # Invalid token, let the endpoint handle it
            return await call_next(request)
        
        # Add user information to request state
        request.state.user = payload
        request.state.token = token
        
        # Continue processing the request
        return await call_next(request)
    
    def _is_public_path(self, path: str) -> bool:
        """
        Check if a path is in the public paths list.
        
        Args:
            path: Request path
            
        Returns:
            bool: True if path is public, False otherwise
        """
        # Exact match
        if path in self.public_paths:
            return True
        
        # Check for prefix matches (e.g., /public/)
        for public_path in self.public_paths:
            if public_path.endswith("*") and path.startswith(public_path[:-1]):
                return True
        
        return False
    
    def _get_token_from_request(self, request: Request) -> Optional[str]:
        """
        Extract JWT token from various locations in the request.
        
        Args:
            request: FastAPI request
            
        Returns:
            str: JWT token if found, None otherwise
        """
        # Check Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header:
            token = get_token_from_authorization_header(auth_header)
            if token:
                return token
        
        # Check query parameter
        token = request.query_params.get("token")
        if token:
            return token
        
        # Check cookie
        if "access_token" in request.cookies:
            return request.cookies.get("access_token")
        
        return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware for rate limiting REST API requests.
    
    This middleware implements a simple in-memory rate limiter.
    For production, consider using a Redis-based rate limiter.
    """
    
    def __init__(
        self,
        app,
        rate_limit: int = 100,  # requests per minute
        window_seconds: int = 60,
        enabled: bool = True,
        public_paths: Optional[List[str]] = None
    ):
        """
        Initialize the rate limiting middleware.
        
        Args:
            app: FastAPI application
            rate_limit: Maximum number of requests per window
            window_seconds: Window duration in seconds
            enabled: Whether rate limiting is enabled
            public_paths: List of paths exempt from rate limiting
        """
        super().__init__(app)
        self.rate_limit = rate_limit
        self.window_seconds = window_seconds
        self.enabled = enabled
        self.public_paths = public_paths or []
        
        # Request counters
        self.request_counts = {}
        self.request_windows = {}
    
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint
    ) -> Response:
        """
        Process the request through the rate limiting middleware.
        
        Args:
            request: FastAPI request
            call_next: Next endpoint in the middleware chain
            
        Returns:
            Response: FastAPI response
            
        Raises:
            RateLimitExceededError: If rate limit is exceeded
        """
        # Skip rate limiting if disabled or for exempt paths
        if not self.enabled or self._is_exempt_path(request.url.path):
            return await call_next(request)
        
        # Skip rate limiting for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Get client identifier
        client_id = self._get_client_id(request)
        
        # Check rate limit
        current_time = int(time.time())
        current_window = current_time // self.window_seconds
        
        # Reset counter if window has changed
        if client_id in self.request_windows and self.request_windows[client_id] != current_window:
            self.request_counts[client_id] = 0
        
        # Update window and increment counter
        self.request_windows[client_id] = current_window
        self.request_counts[client_id] = self.request_counts.get(client_id, 0) + 1
        
        # Check if limit exceeded
        if self.request_counts[client_id] > self.rate_limit:
            retry_after = self.window_seconds - (current_time % self.window_seconds)
            
            # Log the rate limit exceeded event
            client_ip = request.client.host if request.client else "unknown"
            logger.warning(f"Rate limit exceeded for {client_ip} ({client_id})")
            
            raise RateLimitExceededError(
                message=f"Rate limit of {self.rate_limit} requests per {self.window_seconds} seconds exceeded",
                extra_data={"retry_after": retry_after}
            )
        
        # Continue processing the request
        return await call_next(request)
    
    def _is_exempt_path(self, path: str) -> bool:
        """
        Check if a path is exempt from rate limiting.
        
        Args:
            path: Request path
            
        Returns:
            bool: True if path is exempt, False otherwise
        """
        # Exact match
        if path in self.public_paths:
            return True
        
        # Check for prefix matches (e.g., /public/)
        for exempt_path in self.public_paths:
            if exempt_path.endswith("*") and path.startswith(exempt_path[:-1]):
                return True
        
        return False
    
    def _get_client_id(self, request: Request) -> str:
        """
        Get a unique identifier for the client.
        
        Args:
            request: FastAPI request
            
        Returns:
            str: Client identifier
        """
        # Use API key if available in header
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"apikey:{api_key}"
        
        # Use user ID from token if available
        if hasattr(request.state, "user") and "sub" in request.state.user:
            return f"user:{request.state.user['sub']}"
        
        # Fall back to IP address
        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}" 