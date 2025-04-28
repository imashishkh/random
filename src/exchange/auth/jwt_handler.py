"""
JWT token handler for authentication.

Provides JWT token generation, validation, and refresh functionality
for both REST and WebSocket connections.
"""
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, Union

import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError, DecodeError

# Configure logging
logger = logging.getLogger(__name__)

# Constants
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Check if we're using asymmetric keys
JWT_USE_ASYMMETRIC = os.getenv("JWT_USE_ASYMMETRIC", "false").lower() == "true"
JWT_PRIVATE_KEY = os.getenv("JWT_PRIVATE_KEY")
JWT_PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY")


class JWTError(Exception):
    """Base exception for JWT-related errors."""
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        self.message = message
        super().__init__(self.message)


class ExpiredJWTError(JWTError):
    """Exception raised when a JWT token is expired."""
    def __init__(self, message: str = "Token has expired"):
        super().__init__("TOKEN_EXPIRED", message)


class InvalidJWTError(JWTError):
    """Exception raised when a JWT token is invalid."""
    def __init__(self, message: str = "Invalid token"):
        super().__init__("INVALID_TOKEN", message)


def create_token(subject: Union[str, int], 
                 scopes: Optional[list] = None, 
                 expires_delta: Optional[timedelta] = None,
                 additional_claims: Optional[Dict[str, Any]] = None,
                 is_refresh_token: bool = False) -> str:
    """
    Create a JWT token.
    
    Args:
        subject: Subject identifier (user ID, API key, etc.)
        scopes: Optional list of permission scopes
        expires_delta: Optional expiration time delta
        additional_claims: Optional additional claims to include
        is_refresh_token: Whether this is a refresh token
        
    Returns:
        str: Encoded JWT token
        
    Raises:
        ValueError: If JWT keys are not configured properly
    """
    if JWT_USE_ASYMMETRIC and not JWT_PRIVATE_KEY:
        raise ValueError("JWT_PRIVATE_KEY environment variable is required for asymmetric tokens")
    
    if not JWT_USE_ASYMMETRIC and not JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY environment variable is required")
    
    # Set default expiration
    if expires_delta is None:
        if is_refresh_token:
            expires_delta = timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        else:
            expires_delta = timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Create token data
    current_time = datetime.utcnow()
    token_data = {
        "sub": str(subject),
        "iat": current_time,
        "exp": current_time + expires_delta,
        "type": "refresh" if is_refresh_token else "access"
    }
    
    # Add scopes if provided
    if scopes:
        token_data["scopes"] = scopes
    
    # Add any additional claims
    if additional_claims:
        token_data.update(additional_claims)
    
    # Encode the token
    if JWT_USE_ASYMMETRIC:
        encoded_token = jwt.encode(
            token_data,
            JWT_PRIVATE_KEY,
            algorithm=JWT_ALGORITHM
        )
    else:
        encoded_token = jwt.encode(
            token_data,
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM
        )
    
    return encoded_token


def create_access_token(subject: Union[str, int],
                        scopes: Optional[list] = None,
                        expires_delta: Optional[timedelta] = None,
                        additional_claims: Optional[Dict[str, Any]] = None) -> str:
    """
    Create an access token.
    
    Args:
        subject: Subject identifier (user ID, API key, etc.)
        scopes: Optional list of permission scopes
        expires_delta: Optional expiration time delta
        additional_claims: Optional additional claims to include
        
    Returns:
        str: Encoded access token
    """
    return create_token(
        subject=subject,
        scopes=scopes,
        expires_delta=expires_delta,
        additional_claims=additional_claims,
        is_refresh_token=False
    )


def create_refresh_token(subject: Union[str, int],
                         scopes: Optional[list] = None,
                         expires_delta: Optional[timedelta] = None,
                         additional_claims: Optional[Dict[str, Any]] = None) -> str:
    """
    Create a refresh token.
    
    Args:
        subject: Subject identifier (user ID, API key, etc.)
        scopes: Optional list of permission scopes
        expires_delta: Optional expiration time delta
        additional_claims: Optional additional claims to include
        
    Returns:
        str: Encoded refresh token
    """
    return create_token(
        subject=subject,
        scopes=scopes,
        expires_delta=expires_delta,
        additional_claims=additional_claims,
        is_refresh_token=True
    )


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token to validate
        
    Returns:
        Dict: Token payload
        
    Raises:
        ExpiredJWTError: If token has expired
        InvalidJWTError: If token is invalid
    """
    if JWT_USE_ASYMMETRIC and not JWT_PUBLIC_KEY:
        raise ValueError("JWT_PUBLIC_KEY environment variable is required for asymmetric tokens")
    
    if not JWT_USE_ASYMMETRIC and not JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY environment variable is required")
    
    try:
        # Decode the token
        key = JWT_PUBLIC_KEY if JWT_USE_ASYMMETRIC else JWT_SECRET_KEY
        
        payload = jwt.decode(
            token,
            key,
            algorithms=[JWT_ALGORITHM]
        )
        
        return payload
    except ExpiredSignatureError:
        logger.warning("Expired JWT token")
        raise ExpiredJWTError()
    except (InvalidTokenError, DecodeError) as e:
        logger.warning(f"Invalid JWT token: {str(e)}")
        raise InvalidJWTError(str(e))


def validate_token(token: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Validate a JWT token and return its payload.
    
    Args:
        token: JWT token to validate
        
    Returns:
        Tuple of (is_valid, payload)
    """
    try:
        payload = decode_token(token)
        return True, payload
    except (ExpiredJWTError, InvalidJWTError):
        return False, {}


def get_token_payload(token: str) -> Dict[str, Any]:
    """
    Get the payload from a JWT token without full validation.
    
    This function only validates the token format, not the signature.
    Useful for debugging or non-security-critical operations.
    
    Args:
        token: JWT token
        
    Returns:
        Dict: Token payload or empty dict if invalid
    """
    try:
        # Get payload without verification
        payload = jwt.decode(
            token,
            options={"verify_signature": False}
        )
        return payload
    except Exception as e:
        logger.debug(f"Error decoding token: {str(e)}")
        return {}


def refresh_access_token(refresh_token: str) -> str:
    """
    Generate a new access token from a refresh token.
    
    Args:
        refresh_token: Refresh token
        
    Returns:
        str: New access token
        
    Raises:
        ExpiredJWTError: If refresh token has expired
        InvalidJWTError: If refresh token is invalid or not a refresh token
    """
    # Decode and validate the refresh token
    payload = decode_token(refresh_token)
    
    # Ensure it's a refresh token
    if payload.get("type") != "refresh":
        raise InvalidJWTError("Not a refresh token")
    
    # Create a new access token with the same subject and scopes
    subject = payload["sub"]
    scopes = payload.get("scopes", [])
    
    # Don't copy certain claims from the refresh token
    additional_claims = {k: v for k, v in payload.items() 
                        if k not in ["sub", "exp", "iat", "type", "scopes"]}
    
    return create_access_token(
        subject=subject,
        scopes=scopes,
        additional_claims=additional_claims
    )


def is_token_about_to_expire(token: str, threshold_seconds: int = 60) -> bool:
    """
    Check if a token is about to expire within the threshold.
    
    Args:
        token: JWT token to check
        threshold_seconds: Seconds threshold before expiration
        
    Returns:
        bool: True if token will expire within threshold, False otherwise
    """
    try:
        payload = get_token_payload(token)
        if "exp" not in payload:
            return True
        
        exp_time = payload["exp"]
        current_time = int(time.time())
        
        return (exp_time - current_time) < threshold_seconds
    except Exception:
        # If there's any error parsing the token, assume it's about to expire
        return True


def get_token_from_authorization_header(header_value: str) -> Optional[str]:
    """
    Extract token from Authorization header.
    
    Args:
        header_value: Value of the Authorization header
        
    Returns:
        str: Token if found, None otherwise
    """
    if not header_value:
        return None
    
    parts = header_value.split()
    
    # Check format (Bearer token or JWT token)
    if len(parts) == 2 and parts[0].lower() in ["bearer", "jwt"]:
        return parts[1]
    
    # If it's just a token without prefix
    if len(parts) == 1 and len(parts[0]) > 20:  # Arbitrary length check
        return parts[0]
    
    return None 