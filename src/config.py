"""
Configuration settings for the application.

This module loads configuration from environment variables with
sensible defaults and validation.
"""
import os
from typing import Optional, Dict, Any, List
from pydantic import BaseSettings, validator, Field, ConfigDict

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Configuration
    API_VERSION: str = "v1"
    API_PREFIX: str = f"/api/{API_VERSION}"
    API_TITLE: str = "Forex Trading Analytics API"
    API_DESCRIPTION: str = "API for trading analytics, risk metrics, and reporting"
    API_DEBUG: bool = False
    
    # Server Configuration
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    
    # Security
    SECRET_KEY: str
    API_KEY_HEADER: str = "X-API-Key"
    API_KEYS: List[str] = []
    CORS_ORIGINS: List[str] = ["*"]
    SECURE_HEADERS: bool = True
    
    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    
    # Database Configuration
    DATABASE_URL: str
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: int = 100
    RATE_LIMIT_WINDOW: int = 60
    
    # Caching
    CACHE_ENABLED: bool = True
    CACHE_DEFAULT_TTL: int = 300  # 5 minutes
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # External APIs
    MARKET_DATA_API_URL: Optional[str] = None
    MARKET_DATA_API_KEY: Optional[str] = None
    
    # Analytics Settings
    DEFAULT_TIMEFRAME: str = "1d"
    MAX_HISTORICAL_DAYS: int = 365
    RISK_FREE_RATE: float = 0.02
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )
    
    @validator("API_KEYS", pre=True)
    def parse_api_keys(cls, v):
        """Parse API keys from comma-separated string."""
        if isinstance(v, str):
            return [key.strip() for key in v.split(",") if key.strip()]
        return v
    
    @validator("CORS_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from comma-separated string."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
    @validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v.upper()

settings = Settings() 