"""
Authentication and authorization middleware for the Forex Trading AI System.
Provides IP whitelisting, request rate limiting, and security headers.
"""
import os
import time
import logging
from typing import Dict, List, Optional, Set, Tuple, Callable
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from pydantic import BaseModel

from ..cache import redis_client

# Configure logging
logger = logging.getLogger(__name__)

# Constants
WHITELIST_ENV_PREFIX = "IP_WHITELIST_"
DEFAULT_RATE_LIMIT = int(os.getenv("DEFAULT_RATE_LIMIT", "100"))  # requests per minute
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # window in seconds
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
IP_WHITELIST_ENABLED = os.getenv("IP_WHITELIST_ENABLED", "false").lower() == "true"


class RateLimitExceeded(HTTPException):
    """Exception raised when a rate limit is exceeded"""
    def __init__(self, detail: str = "Rate limit exceeded"):
        super().__init__(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)


class IPWhitelistConfig(BaseModel):
    """IP whitelist configuration"""
    enabled: bool = False
    whitelist: Set[str] = set()
    network_whitelist: List[str] = []


# Load IP whitelist from environment variables
def load_ip_whitelist() -> IPWhitelistConfig:
    """
    Load IP whitelist configuration from environment variables.
    
    Returns:
        IPWhitelistConfig: Whitelist configuration
    """
    config = IPWhitelistConfig(enabled=IP_WHITELIST_ENABLED)
    
    # Add specific IPs from environment
    for key, value in os.environ.items():
        if key.startswith(WHITELIST_ENV_PREFIX):
            # Split comma-separated IPs or networks
            ips = [ip.strip() for ip in value.split(",")]
            for ip in ips:
                if "/" in ip:  # CIDR notation
                    config.network_whitelist.append(ip)
                else:
                    config.whitelist.add(ip)
    
    # Always allow localhost
    config.whitelist.add("127.0.0.1")
    config.whitelist.add("::1")
    
    # Log the configuration
    logger.info(f"IP whitelist enabled: {config.enabled}")
    logger.info(f"Whitelisted IPs: {config.whitelist}")
    logger.info(f"Whitelisted networks: {config.network_whitelist}")
    
    return config


# Cache IP whitelist in memory
ip_whitelist_config = load_ip_whitelist()


def is_ip_whitelisted(ip: str) -> bool:
    """
    Check if an IP is in the whitelist.
    
    Args:
        ip: IP address to check
    
    Returns:
        bool: True if IP is whitelisted, False otherwise
    """
    if not ip_whitelist_config.enabled:
        return True
    
    # Direct IP match
    if ip in ip_whitelist_config.whitelist:
        return True
    
    # Network match
    try:
        client_ip = ip_address(ip)
        for network_str in ip_whitelist_config.network_whitelist:
            network = ip_network(network_str)
            if client_ip in network:
                return True
    except ValueError:
        logger.warning(f"Invalid IP address format: {ip}")
    
    return False


async def check_rate_limit(request: Request) -> Tuple[bool, int, int]:
    """
    Check if the request exceeds the rate limit.
    
    Args:
        request: FastAPI request object
    
    Returns:
        Tuple of (limit_exceeded, current_count, limit)
    """
    if not RATE_LIMIT_ENABLED:
        return False, 0, DEFAULT_RATE_LIMIT
    
    # Get client identifier (IP address or API key if present)
    client_id = get_client_id(request)
    
    # Redis rate limiting implementation
    key = f"rate_limit:{client_id}"
    limit = DEFAULT_RATE_LIMIT
    
    try:
        current = redis_client.increment(key)
        if current == 1:
            # Set expiry for new keys
            redis_client.set_key_expiry(key, RATE_LIMIT_WINDOW)
        
        # Check if limit exceeded
        limit_exceeded = current > limit
        return limit_exceeded, current, limit
    except Exception as e:
        logger.error(f"Rate limit check failed: {e}")
        # Fail open
        return False, 0, limit


def get_client_id(request: Request) -> str:
    """
    Get a unique identifier for the client.
    
    Args:
        request: FastAPI request object
    
    Returns:
        str: Client identifier
    """
    # Use API key if available in header
    api_key = request.headers.get("X-API-Key")
    if api_key:
        # Extract key prefix only
        parts = api_key.split("_")
        if len(parts) >= 2:
            return f"apikey:{parts[0]}_{parts[1]}"
    
    # Fall back to IP address
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Middleware for IP whitelisting, rate limiting, and security headers.
    """
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """
        Process the request through the security middleware.
        
        Args:
            request: FastAPI request
            call_next: Next endpoint in the middleware chain
        
        Returns:
            Response: FastAPI response
        
        Raises:
            HTTPException: If the request is blocked by security checks
        """
        # Skip security checks for health endpoint
        if request.url.path == "/health":
            return await call_next(request)
        
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        
        # Check IP whitelist
        if not is_ip_whitelisted(client_ip):
            logger.warning(f"Blocked request from non-whitelisted IP: {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        
        # Check rate limit
        limit_exceeded, current, limit = await check_rate_limit(request)
        if limit_exceeded:
            logger.warning(f"Rate limit exceeded for {get_client_id(request)}: {current}/{limit}")
            raise RateLimitExceeded()
        
        # Process the request
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Add rate limit headers
        if RATE_LIMIT_ENABLED:
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current))
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + RATE_LIMIT_WINDOW)
        
        return response


def setup_security(app: FastAPI) -> FastAPI:
    """
    Set up security middleware and routes for a FastAPI application.
    
    Args:
        app: FastAPI application
    
    Returns:
        FastAPI: The same application with security configured
    """
    # Add security middleware
    app.add_middleware(SecurityMiddleware)
    
    # Log security configuration
    logger.info("Security middleware configured")
    logger.info(f"Rate limiting enabled: {RATE_LIMIT_ENABLED}")
    logger.info(f"Rate limit: {DEFAULT_RATE_LIMIT} requests per {RATE_LIMIT_WINDOW} seconds")
    
    return app 