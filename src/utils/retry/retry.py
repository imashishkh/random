"""
Retry Utilities

This module provides retry functionality for API calls and other operations
that may fail transiently.
"""

import logging
from typing import Callable, Any, Type, List, Union
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError
)

from ...llm.config import get_llm_config

# Get logger
logger = logging.getLogger(__name__)

# Get configuration
llm_config = get_llm_config()


def create_retry_decorator(
    exception_types: List[Type[Exception]],
    max_attempts: int = None,
    min_wait: int = None,
    max_wait: int = None
) -> Callable:
    """
    Create a retry decorator with the specified parameters.
    
    Args:
        exception_types: List of exception types to retry on.
        max_attempts: Maximum number of retry attempts.
        min_wait: Minimum wait time between retries (seconds).
        max_wait: Maximum wait time between retries (seconds).
        
    Returns:
        A retry decorator configured with the specified parameters.
    """
    # Use configuration values if not explicitly provided
    max_attempts = max_attempts or llm_config.max_retries
    min_wait = min_wait or llm_config.retry_min_wait
    max_wait = max_wait or llm_config.retry_max_wait
    
    # Create retry decorator
    return retry(
        retry=retry_if_exception_type(tuple(exception_types)),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )


# Common retry decorators for different scenarios
def retry_openai_api(func: Callable) -> Callable:
    """
    Retry decorator specifically for OpenAI API calls.
    
    This handles common OpenAI API errors with appropriate retry logic.
    
    Args:
        func: The function to decorate.
        
    Returns:
        The decorated function with retry logic.
    """
    # Import here to avoid circular imports
    from openai import (
        APIError, APIConnectionError, RateLimitError, Timeout
    )
    
    # Create and apply retry decorator
    decorator = create_retry_decorator(
        exception_types=[APIError, APIConnectionError, RateLimitError, Timeout]
    )
    return decorator(func)


def retry_network_operations(func: Callable) -> Callable:
    """
    Retry decorator for general network operations.
    
    Args:
        func: The function to decorate.
        
    Returns:
        The decorated function with retry logic.
    """
    import requests
    
    # Create and apply retry decorator
    decorator = create_retry_decorator(
        exception_types=[
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.RequestException
        ]
    )
    return decorator(func) 