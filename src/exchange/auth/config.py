"""
Authentication configuration settings.

This module provides configuration settings for the authentication system.
"""
import os
from typing import Dict, Any, List, Optional

# JWT settings
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# JWT asymmetric keys
JWT_USE_ASYMMETRIC = os.getenv("JWT_USE_ASYMMETRIC", "false").lower() == "true"
JWT_PRIVATE_KEY = os.getenv("JWT_PRIVATE_KEY")
JWT_PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY")

# API key settings
API_KEY_TIMESTAMP_WINDOW_MS = int(os.getenv("API_KEY_TIMESTAMP_WINDOW_MS", "5000"))

# WebSocket settings
WS_AUTH_TIMEOUT_SECONDS = float(os.getenv("WS_AUTH_TIMEOUT_SECONDS", "5.0"))
WS_TOKEN_REFRESH_THRESHOLD_SECONDS = int(os.getenv("WS_TOKEN_REFRESH_THRESHOLD_SECONDS", "300"))

# Rate limiting
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
DEFAULT_RATE_LIMIT = int(os.getenv("DEFAULT_RATE_LIMIT", "100"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

# Authentication enabled flag
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"

# Public paths (don't require authentication)
PUBLIC_PATHS = [
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/metrics"
]

# Additional public paths from environment (comma-separated)
if os.getenv("PUBLIC_PATHS"):
    PUBLIC_PATHS.extend(os.getenv("PUBLIC_PATHS").split(","))

# Exchange-specific settings
EXCHANGE_AUTH_SETTINGS: Dict[str, Dict[str, Any]] = {
    "binance": {
        "api_key_header": "X-MBX-APIKEY",
        "signature_method": "HMAC_SHA256",
        "use_timestamp": True,
    },
    "coinbase": {
        "api_key_header": "CB-ACCESS-KEY",
        "signature_method": "HMAC_SHA256",
        "use_timestamp": True,
    },
    "ftx": {
        "api_key_header": "FTX-KEY",
        "signature_method": "HMAC_SHA256",
        "use_timestamp": True,
    }
}

# Default settings
DEFAULT_EXCHANGE_SETTINGS = {
    "api_key_header": "API-Key",
    "signature_method": "HMAC_SHA256",
    "use_timestamp": True,
}

def get_exchange_auth_settings(exchange: str) -> Dict[str, Any]:
    """
    Get authentication settings for a specific exchange.
    
    Args:
        exchange: Name of the exchange
        
    Returns:
        Dict: Authentication settings
    """
    exchange = exchange.lower()
    return EXCHANGE_AUTH_SETTINGS.get(exchange, DEFAULT_EXCHANGE_SETTINGS)


def get_env_with_fallback(env_var: str, fallback: Any = None) -> Any:
    """
    Get environment variable with fallback value.
    
    Args:
        env_var: Environment variable name
        fallback: Fallback value
        
    Returns:
        Any: Environment variable value or fallback
    """
    value = os.getenv(env_var)
    if value is None:
        return fallback
    return value


def update_settings_from_env() -> None:
    """
    Update settings from environment variables.
    """
    global JWT_SECRET_KEY, JWT_ALGORITHM, JWT_ACCESS_TOKEN_EXPIRE_MINUTES, JWT_REFRESH_TOKEN_EXPIRE_DAYS
    global JWT_USE_ASYMMETRIC, JWT_PRIVATE_KEY, JWT_PUBLIC_KEY
    global API_KEY_TIMESTAMP_WINDOW_MS
    global WS_AUTH_TIMEOUT_SECONDS, WS_TOKEN_REFRESH_THRESHOLD_SECONDS
    global RATE_LIMIT_ENABLED, DEFAULT_RATE_LIMIT, RATE_LIMIT_WINDOW_SECONDS
    global AUTH_ENABLED, PUBLIC_PATHS
    
    # JWT settings
    JWT_SECRET_KEY = get_env_with_fallback("JWT_SECRET_KEY", JWT_SECRET_KEY)
    JWT_ALGORITHM = get_env_with_fallback("JWT_ALGORITHM", JWT_ALGORITHM)
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(get_env_with_fallback("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(get_env_with_fallback("JWT_REFRESH_TOKEN_EXPIRE_DAYS", JWT_REFRESH_TOKEN_EXPIRE_DAYS))
    
    # JWT asymmetric keys
    JWT_USE_ASYMMETRIC = get_env_with_fallback("JWT_USE_ASYMMETRIC", "false").lower() == "true"
    JWT_PRIVATE_KEY = get_env_with_fallback("JWT_PRIVATE_KEY", JWT_PRIVATE_KEY)
    JWT_PUBLIC_KEY = get_env_with_fallback("JWT_PUBLIC_KEY", JWT_PUBLIC_KEY)
    
    # API key settings
    API_KEY_TIMESTAMP_WINDOW_MS = int(get_env_with_fallback("API_KEY_TIMESTAMP_WINDOW_MS", API_KEY_TIMESTAMP_WINDOW_MS))
    
    # WebSocket settings
    WS_AUTH_TIMEOUT_SECONDS = float(get_env_with_fallback("WS_AUTH_TIMEOUT_SECONDS", WS_AUTH_TIMEOUT_SECONDS))
    WS_TOKEN_REFRESH_THRESHOLD_SECONDS = int(get_env_with_fallback("WS_TOKEN_REFRESH_THRESHOLD_SECONDS", WS_TOKEN_REFRESH_THRESHOLD_SECONDS))
    
    # Rate limiting
    RATE_LIMIT_ENABLED = get_env_with_fallback("RATE_LIMIT_ENABLED", "true").lower() == "true"
    DEFAULT_RATE_LIMIT = int(get_env_with_fallback("DEFAULT_RATE_LIMIT", DEFAULT_RATE_LIMIT))
    RATE_LIMIT_WINDOW_SECONDS = int(get_env_with_fallback("RATE_LIMIT_WINDOW_SECONDS", RATE_LIMIT_WINDOW_SECONDS))
    
    # Authentication enabled flag
    AUTH_ENABLED = get_env_with_fallback("AUTH_ENABLED", "true").lower() == "true"
    
    # Public paths
    if get_env_with_fallback("PUBLIC_PATHS"):
        PUBLIC_PATHS.extend(get_env_with_fallback("PUBLIC_PATHS").split(","))


# Update settings from environment when module is imported
update_settings_from_env()