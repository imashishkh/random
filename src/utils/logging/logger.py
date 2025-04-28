"""
Logging Utility

Provides standardized logging configuration for the application.
"""

import os
import sys
import logging
from typing import Optional, Dict, Any


def configure_logging(
    level: str = "INFO",
    log_format: Optional[str] = None,
    log_file: Optional[str] = None
) -> None:
    """
    Configure logging settings.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_format: Custom log format string.
        log_file: Path to log file (logs to console if None).
    """
    # Set default log format if not provided
    if log_format is None:
        log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    
    # Convert string level to logging level
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        filename=log_file,
        filemode='a' if log_file else None
    )
    
    # If logging to file, also add console handler for convenience
    if log_file:
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(numeric_level)
        console.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(console)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (uses module name if None).
        
    Returns:
        Configured logger instance.
    """
    if name is None:
        # Get the calling module's name if not provided
        import inspect
        frame = inspect.stack()[1]
        module = inspect.getmodule(frame[0])
        name = module.__name__ if module else "root"
    
    return logging.getLogger(name)


def log_llm_request(logger: logging.Logger, model: str, messages: list, **kwargs) -> None:
    """
    Log an LLM request.
    
    Args:
        logger: Logger instance
        model: The model being used
        messages: The messages being sent to the LLM
        **kwargs: Additional parameters to log
    """
    try:
        # Only log in debug mode to avoid excessive output
        if logger.level <= logging.DEBUG:
            # Create a summary of the request that doesn't include the full text
            request_summary = {
                "model": model,
                "message_count": len(messages),
                "message_types": [msg.get("role", "unknown") for msg in messages],
                **{k: v for k, v in kwargs.items() if k not in ["api_key", "token", "secret"]}
            }
            logger.debug(f"LLM Request: {request_summary}")
    except Exception as e:
        logger.error(f"Error logging LLM request: {str(e)}")


def log_llm_response(logger: logging.Logger, model: str, response: Dict[str, Any], **kwargs) -> None:
    """
    Log an LLM response.
    
    Args:
        logger: Logger instance
        model: The model being used
        response: The response from the LLM
        **kwargs: Additional parameters to log
    """
    try:
        # Only log in debug mode to avoid excessive output
        if logger.level <= logging.DEBUG:
            # Create a summary of the response
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            tokens = response.get("usage", {})
            response_summary = {
                "model": model,
                "content_length": len(content) if content else 0,
                "tokens": tokens,
                **kwargs
            }
            logger.debug(f"LLM Response: {response_summary}")
    except Exception as e:
        logger.error(f"Error logging LLM response: {str(e)}") 