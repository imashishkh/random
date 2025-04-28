"""
Settings module for the Forex Trading application.

This module handles configuration loading from environment variables with sensible defaults
and validation. It uses Pydantic for data validation and settings management.
"""

import os
from typing import List, Optional, Set
from pydantic import BaseSettings, validator, PostgresDsn, AnyHttpUrl


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables with defaults.
    
    Attributes are grouped by functionality for easier management and understanding.
    """
    
    # API Configuration
    API_VERSION: str = "v1"
    API_DEBUG: bool = False
    
    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Security Settings
    SECRET_KEY: str
    API_KEYS: Set[str] = set()
    CORS_ORIGINS: List[AnyHttpUrl] = []
    SECURE_HEADERS: bool = True
    
    @validator("API_KEYS", pre=True)
    def parse_api_keys(cls, v):
        """Parse API keys from comma-separated string to set."""
        if isinstance(v, str):
            return {key.strip() for key in v.split(",") if key.strip()}
        return v
    
    @validator("CORS_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from comma-separated string to list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    # Database Configuration
    DATABASE_URL: PostgresDsn
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: int = 100  # requests per window
    RATE_LIMIT_WINDOW: int = 60  # seconds
    
    # Caching
    CACHE_ENABLED: bool = True
    CACHE_DEFAULT_TTL: int = 300  # seconds
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    @validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        """Validate log level is a proper level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()
    
    # External APIs
    MARKET_DATA_API_URL: Optional[AnyHttpUrl] = None
    MARKET_DATA_API_KEY: Optional[str] = None
    
    # Analytics Settings
    DEFAULT_TIMEFRAME: str = "1d"  # 1d, 1h, 15m, etc.
    MAX_HISTORICAL_DAYS: int = 365
    RISK_FREE_RATE: float = 0.02  # 2% annual risk-free rate
    
    class Config:
        """Configuration for the settings class."""
        env_file = ".env"
        case_sensitive = True


# Create settings instance
settings = Settings() 