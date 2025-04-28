"""
Structured Logging Utility

Provides structured logging capabilities using structlog for
better logging organization and easier parsing.
"""

import sys
import uuid
import logging
import time
from typing import Dict, Any, Optional

import structlog
from structlog.types import Processor
from structlog.stdlib import BoundLogger, LoggerFactory
from structlog.processors import (
    TimeStamper, JSONRenderer, format_exc_info,
    UnicodeDecoder, StackInfoRenderer
)


def add_request_id() -> Processor:
    """
    Processor for automatically adding a request ID to all log entries.
    
    Returns:
        A processor that adds a unique request ID.
    """
    def processor(logger, name, event_dict):
        if 'request_id' not in event_dict:
            event_dict['request_id'] = str(uuid.uuid4())
        return event_dict
    return processor


def add_process_time() -> Processor:
    """
    Processor for adding process time to track duration.
    
    Returns:
        A processor that adds process time.
    """
    start_time = time.time()
    def processor(logger, name, event_dict):
        event_dict['process_time'] = time.time() - start_time
        return event_dict
    return processor


def sanitize_data() -> Processor:
    """
    Processor to sanitize sensitive data from logs.
    
    Returns:
        A processor that sanitizes sensitive data.
    """
    sensitive_keys = {'api_key', 'secret', 'password', 'token', 'auth'}
    
    def processor(logger, name, event_dict):
        for key, value in list(event_dict.items()):
            if isinstance(value, dict):
                for inner_key in list(value.keys()):
                    if any(s in inner_key.lower() for s in sensitive_keys):
                        value[inner_key] = '********'
            elif any(s in key.lower() for s in sensitive_keys) and value:
                event_dict[key] = '********'
        return event_dict
    return processor


def configure_structured_logging(
    level: str = "INFO",
    json_format: bool = False,
    include_timestamp: bool = True,
    include_request_id: bool = True,
    include_process_time: bool = False,
    sanitize: bool = True,
    log_file: Optional[str] = None
) -> None:
    """
    Configure structured logging.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: Whether to output logs in JSON format.
        include_timestamp: Whether to include timestamps in logs.
        include_request_id: Whether to add request IDs to logs.
        include_process_time: Whether to track process time.
        sanitize: Whether to sanitize sensitive data.
        log_file: Path to log file (logs to stdout if None).
    """
    # Set root logger level
    level_num = getattr(logging, level.upper(), logging.INFO)
    logging.root.setLevel(level_num)
    
    # Configure handlers
    handlers = []
    
    # Console handler always added
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level_num)
    handlers.append(console_handler)
    
    # File handler if requested
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level_num)
        handlers.append(file_handler)
    
    # Configure processors
    processors = [
        format_exc_info,
        StackInfoRenderer(),
        UnicodeDecoder(),
    ]
    
    # Optional processors
    if include_timestamp:
        processors.append(TimeStamper(fmt="iso"))
    
    if include_request_id:
        processors.append(add_request_id())
    
    if include_process_time:
        processors.append(add_process_time())
    
    if sanitize:
        processors.append(sanitize_data())
    
    # Add renderer based on format
    if json_format:
        processors.append(JSONRenderer())
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=LoggerFactory(),
        wrapper_class=BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_structured_logger(name: Optional[str] = None) -> BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (uses module name if None).
        
    Returns:
        Configured structlog logger instance.
    """
    if name is None:
        # Get the calling module's name if not provided
        import inspect
        frame = inspect.stack()[1]
        module = inspect.getmodule(frame[0])
        name = module.__name__ if module else "root"
    
    return structlog.get_logger(name) 