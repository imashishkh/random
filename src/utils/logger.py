"""
Forex Trading Dashboard - Logging System

This module provides a comprehensive logging system for the Forex Trading Dashboard.
It supports multiple output destinations, log levels, and structured logging.
"""

import os
import sys
import json
import logging
import logging.handlers
from typing import Dict, Any, List, Optional, Union, Set
from datetime import datetime
import time
import threading
from dataclasses import dataclass, field, asdict

# Import the config manager
from .config_manager import config_manager

# Logger instance cache to avoid creating multiple loggers
_loggers = {}

# Get logger function for external use
def get_logger(component_name: str = "root") -> 'ForexLogger':
    """
    Get a logger instance for the given component name.
    
    Args:
        component_name: Name of the component requesting the logger
        
    Returns:
        ForexLogger instance
    """
    global _loggers
    
    if component_name not in _loggers:
        _loggers[component_name] = ForexLogger()
    
    return _loggers[component_name]

# ForexLogRecord dataclass to store log records in a structured format
@dataclass
class ForexLogRecord:
    """
    Structured log record for the Forex Trading Dashboard.
    """
    created: float
    message: str
    level: str
    component: str = ""
    tags: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the log record to a dictionary."""
        return asdict(self)

class ForexLogger:
    """
    Forex Trading Dashboard logger that supports multiple outputs, 
    structured logging, and in-memory log storage.
    """
    # Log level mapping
    LEVELS = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    
    def __init__(self):
        """Initialize the logger with default settings."""
        # Initialize lock for thread safety
        self._lock = threading.RLock()
        
        # Initialize in-memory logs
        self._logs: List[Dict[str, Any]] = []
        self._max_memory_logs = 1000
        
        # Create the logger
        self._logger = logging.getLogger("forex_dashboard")
        self._logger.setLevel(logging.DEBUG)
        
        # Prevent log propagation to the root logger
        self._logger.propagate = False
        
        # Will be initialized when configure() is called
        self._console_handler = None
        self._file_handler = None
        self._json_handler = None
        
        # Add a handler that captures logs in memory
        self._memory_handler = logging.Handler()
        self._memory_handler.setLevel(logging.DEBUG)
        self._memory_handler.setFormatter(logging.Formatter("%(message)s"))
        self._memory_handler.emit = self._emit_to_memory
        self._logger.addHandler(self._memory_handler)
        
        # Ensure configuration manager is initialized
        if not hasattr(config_manager, '_initialized') or not config_manager._initialized:
            config_manager.initialize()
        
        # Register callback for logging configuration changes
        config_manager.register_callback('logging', self._config_changed_callback)
        
        # Configure from config
        self.configure()
    
    def _config_changed_callback(self, section: str, value: Any) -> None:
        """
        Callback function for configuration changes.
        
        Args:
            section: Configuration section that changed
            value: New value for the section
        """
        # Reconfigure logger when logging settings change
        self.configure()
    
    def configure(self):
        """
        Configure the logger based on the configuration settings.
        This method can be called to reconfigure the logger when settings change.
        """
        with self._lock:
            # Get logging configuration
            log_config = config_manager.get_config('logging', {})
            
            # Remove existing handlers
            if self._console_handler:
                self._logger.removeHandler(self._console_handler)
                self._console_handler = None
            
            if self._file_handler:
                self._logger.removeHandler(self._file_handler)
                self._file_handler = None
            
            if self._json_handler:
                self._logger.removeHandler(self._json_handler)
                self._json_handler = None
            
            # Configure log level
            log_level_str = log_config.get('level', 'INFO')
            log_level = self.LEVELS.get(log_level_str, logging.INFO)
            self._logger.setLevel(log_level)
            
            # Configure in-memory log settings
            self._max_memory_logs = log_config.get('max_memory_logs', 1000)
            
            # Configure console logging
            if log_config.get('console_enabled', True):
                self._console_handler = logging.StreamHandler()
                self._console_handler.setLevel(log_level)
                
                # Create formatter
                fmt = log_config.get('console_format', 
                                   '%(asctime)s - %(levelname)s - %(message)s')
                formatter = logging.Formatter(fmt, 
                                           datefmt='%Y-%m-%d %H:%M:%S')
                self._console_handler.setFormatter(formatter)
                self._logger.addHandler(self._console_handler)
            
            # Configure file logging
            if log_config.get('file_enabled', False):
                log_dir = log_config.get('log_directory', 'logs')
                
                # Create log directory if it doesn't exist
                if not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                
                log_file = os.path.join(log_dir, log_config.get('log_filename', 'forex.log'))
                
                # Set up rotating file handler
                max_bytes = log_config.get('max_file_size_mb', 10) * 1024 * 1024
                backup_count = log_config.get('backup_count', 5)
                
                self._file_handler = logging.handlers.RotatingFileHandler(
                    log_file, maxBytes=max_bytes, backupCount=backup_count
                )
                
                self._file_handler.setLevel(log_level)
                
                # Create formatter
                fmt = log_config.get('file_format', 
                                   '%(asctime)s - %(levelname)s - %(message)s')
                formatter = logging.Formatter(fmt, 
                                           datefmt='%Y-%m-%d %H:%M:%S')
                self._file_handler.setFormatter(formatter)
                self._logger.addHandler(self._file_handler)
            
            # Configure JSON logging
            if log_config.get('json_enabled', False):
                log_dir = log_config.get('log_directory', 'logs')
                
                # Create log directory if it doesn't exist
                if not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                
                json_log_file = os.path.join(
                    log_dir, 
                    log_config.get('json_filename', 'forex.json.log')
                )
                
                # Set up rotating file handler
                max_bytes = log_config.get('max_file_size_mb', 10) * 1024 * 1024
                backup_count = log_config.get('backup_count', 5)
                
                self._json_handler = logging.handlers.RotatingFileHandler(
                    json_log_file, maxBytes=max_bytes, backupCount=backup_count
                )
                
                self._json_handler.setLevel(log_level)
                self._json_handler.setFormatter(logging.Formatter("%(message)s"))
                self._json_handler.emit = self._emit_json
                self._logger.addHandler(self._json_handler)
            
            # Log a message when the configuration is applied
            self.info(
                "Logger configuration updated", 
                component="ForexLogger", 
                tags=["config"]
            )
    
    def _emit_to_memory(self, record):
        """
        Custom emit method to store logs in memory.
        
        Args:
            record: Log record to store
        """
        if not hasattr(record, 'forex_record'):
            return
            
        with self._lock:
            # Add to in-memory logs
            self._logs.append(record.forex_record.to_dict())
            
            # Trim logs if needed
            if len(self._logs) > self._max_memory_logs:
                self._logs = self._logs[-self._max_memory_logs:]
    
    def _emit_json(self, record):
        """
        Custom emit method to write JSON formatted logs to file.
        
        Args:
            record: Log record to write
        """
        if not hasattr(record, 'forex_record'):
            return
            
        try:
            # Format as JSON
            log_entry = record.forex_record.to_dict()
            json_str = json.dumps(log_entry) + "\n"
            
            # Write to file
            self._json_handler.stream.write(json_str)
            self._json_handler.stream.flush()
        except Exception:
            self._logger.handleError(record)
    
    def _log(self, level: str, message: str, component: str = "", 
             tags: Optional[List[str]] = None, 
             extra: Optional[Dict[str, Any]] = None):
        """
        Internal logging method.
        
        Args:
            level: Log level
            message: Log message
            component: Component name
            tags: List of tags
            extra: Extra information
        """
        if level not in self.LEVELS:
            level = "INFO"
            
        # Create a ForexLogRecord
        log_record = ForexLogRecord(
            created=time.time(),
            message=message,
            level=level,
            component=component,
            tags=tags or [],
            extra=extra or {}
        )
        
        # Create a standard log record
        record = logging.LogRecord(
            name=self._logger.name,
            level=self.LEVELS[level],
            pathname=__file__,
            lineno=0,
            msg=message,
            args=(),
            exc_info=None
        )
        
        # Attach the ForexLogRecord to the standard record
        record.forex_record = log_record
        
        # Log the record
        self._logger.handle(record)
    
    def debug(self, message: str, component: str = "", 
              tags: Optional[List[str]] = None, 
              extra: Optional[Dict[str, Any]] = None):
        """
        Log a debug message.
        
        Args:
            message: Log message
            component: Component name
            tags: List of tags
            extra: Extra information
        """
        self._log("DEBUG", message, component, tags, extra)
    
    def info(self, message: str, component: str = "", 
             tags: Optional[List[str]] = None, 
             extra: Optional[Dict[str, Any]] = None):
        """
        Log an info message.
        
        Args:
            message: Log message
            component: Component name
            tags: List of tags
            extra: Extra information
        """
        self._log("INFO", message, component, tags, extra)
    
    def warning(self, message: str, component: str = "", 
                tags: Optional[List[str]] = None, 
                extra: Optional[Dict[str, Any]] = None):
        """
        Log a warning message.
        
        Args:
            message: Log message
            component: Component name
            tags: List of tags
            extra: Extra information
        """
        self._log("WARNING", message, component, tags, extra)
    
    def error(self, message: str, component: str = "", 
              tags: Optional[List[str]] = None, 
              extra: Optional[Dict[str, Any]] = None):
        """
        Log an error message.
        
        Args:
            message: Log message
            component: Component name
            tags: List of tags
            extra: Extra information
        """
        self._log("ERROR", message, component, tags, extra)
    
    def critical(self, message: str, component: str = "", 
                 tags: Optional[List[str]] = None, 
                 extra: Optional[Dict[str, Any]] = None):
        """
        Log a critical message.
        
        Args:
            message: Log message
            component: Component name
            tags: List of tags
            extra: Extra information
        """
        self._log("CRITICAL", message, component, tags, extra)
    
    def get_logs(self, level: Optional[str] = None, 
                component: Optional[str] = None, 
                tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get logs from memory.
        
        Args:
            level: Filter by log level
            component: Filter by component
            tag: Filter by tag
        
        Returns:
            List of log entries
        """
        with self._lock:
            # Copy logs
            logs = self._logs.copy()
        
        # Apply filters
        if level:
            logs = [log for log in logs if log['level'] == level]
        
        if component:
            logs = [log for log in logs if log['component'] == component]
        
        if tag:
            logs = [log for log in logs if tag in log['tags']]
        
        return logs
    
    def clear_logs(self):
        """Clear in-memory logs."""
        with self._lock:
            self._logs = []
    
    def set_level(self, level: str):
        """
        Set the log level.
        
        Args:
            level: Log level
        """
        if level in self.LEVELS:
            # Update configuration using the config manager
            config_manager.set_config('logging.level', level, persist=True)
            
            # Logger will be reconfigured automatically via the callback

# Create a singleton instance
forex_logger = ForexLogger()

# Provide direct access to logging methods for convenience
debug = forex_logger.debug
info = forex_logger.info
warning = forex_logger.warning
error = forex_logger.error
critical = forex_logger.critical
get_logs = forex_logger.get_logs
clear_logs = forex_logger.clear_logs
set_level = forex_logger.set_level

# Alias
logger = forex_logger 