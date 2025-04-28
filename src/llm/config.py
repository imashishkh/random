"""
LLM Configuration Module

This module handles the configuration for LLM services, providing
secure management of API keys and LLM settings.
"""

import os
from typing import Dict, Optional, Any
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()


class LLMConfig(BaseModel):
    """Configuration for LLM models and API settings."""
    
    # OpenAI API configuration
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_org_id: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_ORG_ID", None))
    
    # Default model settings
    default_model: str = Field(
        default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o")
    )
    default_temperature: float = Field(
        default_factory=lambda: float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
    )
    default_max_tokens: Optional[int] = Field(
        default_factory=lambda: int(os.getenv("OPENAI_MAX_TOKENS", "2000"))
    )
    
    # Retry configuration
    max_retries: int = Field(
        default_factory=lambda: int(os.getenv("LLM_MAX_RETRIES", "3"))
    )
    retry_min_wait: int = Field(
        default_factory=lambda: int(os.getenv("LLM_RETRY_MIN_WAIT", "1"))
    )
    retry_max_wait: int = Field(
        default_factory=lambda: int(os.getenv("LLM_RETRY_MAX_WAIT", "10"))
    )
    
    # Timeout settings
    request_timeout: int = Field(
        default_factory=lambda: int(os.getenv("LLM_REQUEST_TIMEOUT", "30"))
    )
    
    @validator("openai_api_key")
    def validate_openai_api_key(cls, v):
        """Validate that the OpenAI API key is provided."""
        if not v:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        return v
    
    @validator("default_temperature")
    def validate_temperature(cls, v):
        """Validate that the temperature is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError("Temperature must be between 0 and 1")
        return v


# Global instance of LLM configuration
try:
    llm_config = LLMConfig()
    logging.info("LLM configuration loaded successfully")
except Exception as e:
    logging.error(f"Failed to load LLM configuration: {str(e)}")
    raise


def get_llm_config() -> LLMConfig:
    """
    Get the LLM configuration.
    
    Returns:
        LLMConfig: The LLM configuration.
    """
    return llm_config 