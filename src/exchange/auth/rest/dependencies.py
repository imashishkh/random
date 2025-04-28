"""
FastAPI authentication dependencies for REST endpoints.

This module provides reusable dependency functions for FastAPI
to secure REST endpoints with various authentication methods.
"""
import logging
from typing import Optional, Dict, Any, List, Union

from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials

from .auth.jwt_handler import (
    validate_token, 
    get_token_from_authorization_header,
    JWTError
)
from .auth.api_key_handler import get_api_key_auth, ApiKeyError

# Configure logger
logger = logging.getLogger(__name__)

# OAuth2 schemes for different authentication flows
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
http_bearer = HTTPBearer(auto_error=False)

# Custom error messages
AUTH_REQUIRED = "Authentication required"
INVALID_TOKEN = "Invalid or expired token"
INVALID_SCOPE = "Insufficient permissions"
INVALID_API_KEY = "Invalid API key"
INVALID_SIGNATURE = "Invalid signature"


async def get_token_from_request(request: Request) -> Optional[str]:
    """
    Extract JWT token from various locations in the request.
    
    Checks in order:
    1. Authorization header (Bearer token)
    2. Query parameter "token"
    3. Cookie "access_token"
    
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


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme)
) -> Dict[str, Any]:
    """
    Validate JWT token and extract user information.
    
    Args:
        request: FastAPI request
        token: JWT token from OAuth2 scheme
        
    Returns:
        Dict: User information from token payload
        
    Raises:
        HTTPException: If token is missing or invalid
    """
    # Try to get token if not provided by OAuth2 scheme
    if not token:
        token = await get_token_from_request(request)
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_REQUIRED,
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Validate token
    is_valid, payload = validate_token(token)
    
    if not is_valid or not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_TOKEN,
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return payload


async def get_current_active_user(
    user_payload: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current active user with additional checks.
    
    Args:
        user_payload: User payload from JWT token
        
    Returns:
        Dict: User information
        
    Raises:
        HTTPException: If user is disabled or invalid
    """
    # Check if user is marked as disabled
    if user_payload.get("disabled", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    
    return user_payload


async def require_scopes(required_scopes: List[str]):
    """
    Create a dependency that requires specific scopes.
    
    Args:
        required_scopes: List of required scopes
        
    Returns:
        Callable: Dependency function
    """
    async def _require_scopes(
        user_payload: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        # Get user scopes from token
        user_scopes = user_payload.get("scopes", [])
        
        # Check if user has required scopes
        if not all(scope in user_scopes for scope in required_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=INVALID_SCOPE
            )
        
        return user_payload
    
    return _require_scopes


async def validate_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    x_api_signature: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    Validate API key authentication for REST requests.
    
    Args:
        request: FastAPI request
        x_api_key: API key from header
        x_api_signature: API signature from header
        
    Returns:
        Dict: API key information
        
    Raises:
        HTTPException: If authentication fails
    """
    # API key must be provided
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_API_KEY
        )
    
    # Extract exchange from request path if possible
    path_parts = request.url.path.split("/")
    exchange = "generic"  # Default
    
    for part in path_parts:
        if part.lower() in ["binance", "coinbase", "ftx"]:
            exchange = part.lower()
            break
    
    # Get parameters for signature validation
    params = {}
    
    # Add query parameters
    params.update(dict(request.query_params))
    
    # Try to add body parameters for POST/PUT requests
    if request.method in ["POST", "PUT"]:
        try:
            body = await request.json()
            if isinstance(body, dict):
                params.update(body)
        except Exception:
            # Not JSON body or empty
            pass
    
    # Validate API key and signature if provided
    try:
        api_auth = get_api_key_auth(exchange)
        
        # If signature is provided, validate it
        if x_api_signature:
            api_auth.authenticate_request(
                api_key=x_api_key,
                signature=x_api_signature,
                params=params,
                check_timestamp=True
            )
        
        # Return API key info (minimal)
        return {
            "api_key": x_api_key,
            "exchange": exchange
        }
    except ApiKeyError as e:
        # Log the error
        logger.warning(f"API key authentication failed: {str(e)}")
        
        # Return appropriate error
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message
        )
    except Exception as e:
        # Unexpected error
        logger.error(f"API key validation error: {str(e)}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication error"
        )


# Provide aliases with better names for imports
get_jwt_user = get_current_user
validate_jwt = get_current_user
validate_api_key_auth = validate_api_key 