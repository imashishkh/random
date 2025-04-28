"""
Enhanced Logging Manager Module

This module provides a comprehensive logging management system with features like:
- Structured logging with multiple levels
- Log filtering by source, level, and time period
- Log search functionality
- Log export
- Real-time log streaming
- Log rotation and cleanup
"""

import os
import sys
import time
import json
import logging
import gzip
import shutil
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Union, TextIO, Set, Pattern
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import threading
import queue

# Import the existing logging utilities
from .logging.logger import configure_logging, get_logger
from .logging.structured_logger import (
    configure_structured_logging, 
    get_structured_logger
)

# Custom formatter for structured logs
class StructuredFormatter(logging.Formatter):
    """Formatter that outputs JSON strings with specific fields."""
    
    def format(self, record):
        """Format a record as JSON."""
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'thread': record.threadName,
            'message': record.getMessage(),
            'module': record.module,
            'filename': record.filename,
            'lineno': record.lineno,
        }
        
        # Add exception info if available
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': self.formatException(record.exc_info)
            }
        
        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in {
                'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
                'funcName', 'id', 'levelname', 'levelno', 'lineno', 'module',
                'msecs', 'message', 'msg', 'name', 'pathname', 'process',
                'processName', 'relativeCreated', 'stack_info', 'thread', 'threadName'
            }:
                log_data[key] = value
        
        return json.dumps(log_data)

# Stream handler that supports callbacks for real-time log processing
class CallbackStreamHandler(logging.StreamHandler):
    """Stream handler that calls a callback function for each log record."""
    
    def __init__(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Initialize with a callback function.
        
        Args:
            callback: Function to call with each formatted log record.
        """
        super().__init__()
        self.callback = callback
    
    def emit(self, record):
        """
        Emit a record and call the callback function.
        
        Args:
            record: Log record to emit.
        """
        try:
            msg = self.format(record)
            self.callback(json.loads(msg))
        except Exception:
            self.handleError(record)

# Background thread for log processing
class LogProcessorThread(threading.Thread):
    """Background thread for processing logs."""
    
    def __init__(self, log_queue: queue.Queue, callback: Callable[[Dict[str, Any]], None]):
        """
        Initialize the log processor thread.
        
        Args:
            log_queue: Queue for log records.
            callback: Function to call with each log record.
        """
        super().__init__(daemon=True)
        self.log_queue = log_queue
        self.callback = callback
        self.stop_event = threading.Event()
    
    def run(self):
        """Process logs from the queue until stopped."""
        while not self.stop_event.is_set():
            try:
                record = self.log_queue.get(timeout=0.5)
                self.callback(record)
                self.log_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                # Log to stderr as a fallback
                print(f"Error processing log record: {e}", file=sys.stderr)
    
    def stop(self):
        """Signal the thread to stop processing."""
        self.stop_event.set()
        self.join(timeout=2.0)

class LogManager:
    """
    Enhanced Log Manager for centralized logging with advanced features.
    """
    
    def __init__(
        self, 
        log_dir: str = None,
        log_level: str = "INFO",
        log_format: str = None,
        max_size: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 10,
        use_json: bool = True,
        log_to_console: bool = True,
        log_to_file: bool = True,
        retention_days: int = 30,
        include_hostname: bool = True,
        include_process_info: bool = True,
        sanitize_sensitive_data: bool = True,
        sensitive_patterns: List[Pattern] = None
    ):
        """
        Initialize the LogManager.
        
        Args:
            log_dir: Directory for log files. Defaults to 'logs/'.
            log_level: Minimum logging level. Defaults to 'INFO'.
            log_format: Custom log format string. Defaults to None (use structured format).
            max_size: Maximum size of log files before rotation in bytes. Defaults to 10MB.
            backup_count: Number of backup files to keep. Defaults to 10.
            use_json: Whether to use JSON format for logs. Defaults to True.
            log_to_console: Whether to log to console. Defaults to True.
            log_to_file: Whether to log to file. Defaults to True.
            retention_days: Number of days to keep old logs. Defaults to 30.
            include_hostname: Whether to include the hostname in logs. Defaults to True.
            include_process_info: Whether to include process info in logs. Defaults to True.
            sanitize_sensitive_data: Whether to sanitize sensitive data. Defaults to True.
            sensitive_patterns: Regex patterns to identify sensitive data.
        """
        # Set up directories
        self.log_dir = log_dir or os.path.join(os.getcwd(), 'logs')
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Settings
        self.log_level = log_level.upper()
        self.log_format = log_format
        self.max_size = max_size
        self.backup_count = backup_count
        self.use_json = use_json
        self.retention_days = retention_days
        self.log_to_console = log_to_console
        self.log_to_file = log_to_file
        
        # Additional settings
        self.include_hostname = include_hostname
        self.include_process_info = include_process_info
        self.sanitize_sensitive_data = sanitize_sensitive_data
        self.sensitive_patterns = sensitive_patterns or [
            re.compile(r'password', re.IGNORECASE),
            re.compile(r'secret', re.IGNORECASE),
            re.compile(r'token', re.IGNORECASE),
            re.compile(r'api[_-]?key', re.IGNORECASE),
            re.compile(r'auth', re.IGNORECASE),
            re.compile(r'credential', re.IGNORECASE)
        ]
        
        # State
        self.loggers = {}
        self.log_queue = queue.Queue()
        self.log_callbacks = set()
        self.log_processor = None
        
        # Set up the root logger
        self._configure_root_logger()
        
        # Start log processor thread if needed
        self._start_log_processor()
        
        # Schedule log cleanup
        self._schedule_log_cleanup()
        
        # Get a logger for this class
        self.logger = self.get_logger(__name__)
        self.logger.info("LogManager initialized")
    
    def _configure_root_logger(self):
        """Configure the root logger with handlers."""
        # Get the numeric log level
        num_level = getattr(logging, self.log_level, logging.INFO)
        
        # Reset root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(num_level)
        
        # Remove existing handlers
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
        
        # Set up formatter
        if self.use_json:
            formatter = StructuredFormatter()
        else:
            if self.log_format:
                formatter = logging.Formatter(self.log_format)
            else:
                formatter = logging.Formatter(
                    '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
                )
        
        # Add console handler if requested
        if self.log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(num_level)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
        
        # Add file handler if requested
        if self.log_to_file:
            log_file = os.path.join(self.log_dir, 'app.log')
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=self.max_size,
                backupCount=self.backup_count
            )
            file_handler.setLevel(num_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        
        # Add callback handler for real-time processing
        callback_handler = CallbackStreamHandler(self._process_log_record)
        callback_handler.setLevel(num_level)
        callback_handler.setFormatter(formatter)
        root_logger.addHandler(callback_handler)
    
    def _process_log_record(self, record: Dict[str, Any]):
        """
        Process a log record for real-time callbacks.
        
        Args:
            record: Log record as a dictionary.
        """
        # Sanitize sensitive data if needed
        if self.sanitize_sensitive_data:
            record = self._sanitize_log_record(record)
        
        # Add to queue for background processing
        self.log_queue.put(record)
    
    def _sanitize_log_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize sensitive data in a log record.
        
        Args:
            record: Log record to sanitize.
            
        Returns:
            Sanitized log record.
        """
        def sanitize_value(key, value):
            if isinstance(value, str):
                for pattern in self.sensitive_patterns:
                    if pattern.search(key):
                        return '********'
            
            if isinstance(value, dict):
                return sanitize_dict(value)
            
            if isinstance(value, list):
                return [sanitize_value(f"{key}[{i}]", item) for i, item in enumerate(value)]
            
            return value
        
        def sanitize_dict(d):
            return {k: sanitize_value(k, v) for k, v in d.items()}
        
        # Create a copy of the record to avoid modifying the original
        sanitized = record.copy()
        
        # Sanitize message field
        message = sanitized.get('message', '')
        if isinstance(message, str):
            for pattern in self.sensitive_patterns:
                message = pattern.sub(lambda m: f"{m.group(0)[:2]}********", message)
            sanitized['message'] = message
        
        # Sanitize other fields
        return sanitize_dict(sanitized)
    
    def _start_log_processor(self):
        """Start the background log processor thread."""
        def process_log(record):
            # Call all registered callbacks with the log record
            for callback in list(self.log_callbacks):
                try:
                    callback(record)
                except Exception as e:
                    print(f"Error in log callback: {e}", file=sys.stderr)
        
        self.log_processor = LogProcessorThread(self.log_queue, process_log)
        self.log_processor.start()
    
    def _schedule_log_cleanup(self):
        """Schedule periodic log cleanup."""
        # This is a simplified implementation
        # In a production system, you might use a proper scheduler like APScheduler
        def cleanup_task():
            self.cleanup_old_logs()
            
            # Schedule the next cleanup
            cleanup_thread = threading.Timer(
                86400,  # Run once per day
                cleanup_task
            )
            cleanup_thread.daemon = True
            cleanup_thread.start()
        
        # Start initial cleanup
        cleanup_thread = threading.Timer(3600, cleanup_task)  # First run after 1 hour
        cleanup_thread.daemon = True
        cleanup_thread.start()
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        Get a logger instance.
        
        Args:
            name: Logger name.
            
        Returns:
            Configured logger instance.
        """
        if name in self.loggers:
            return self.loggers[name]
        
        logger = logging.getLogger(name)
        self.loggers[name] = logger
        return logger
    
    def get_structured_logger(self, name: str) -> Any:
        """
        Get a structured logger instance.
        
        Args:
            name: Logger name.
            
        Returns:
            Configured structured logger instance.
        """
        # Use the existing structured logger functionality
        return get_structured_logger(name)
    
    def register_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Register a callback function for real-time log processing.
        
        Args:
            callback: Function to call with each log record.
        """
        self.log_callbacks.add(callback)
    
    def unregister_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Unregister a callback function.
        
        Args:
            callback: Function to remove from callbacks.
        """
        if callback in self.log_callbacks:
            self.log_callbacks.remove(callback)
    
    def set_level(self, level: str) -> None:
        """
        Set the logging level.
        
        Args:
            level: New logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        """
        level = level.upper()
        num_level = getattr(logging, level, None)
        if num_level is None:
            self.logger.error(f"Invalid log level: {level}")
            return
        
        # Update the root logger
        logging.getLogger().setLevel(num_level)
        
        # Update all handlers
        for handler in logging.getLogger().handlers:
            handler.setLevel(num_level)
        
        self.log_level = level
        self.logger.info(f"Log level set to {level}")
    
    def get_logs(
        self, 
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        levels: Optional[List[str]] = None,
        logger_names: Optional[List[str]] = None,
        search_text: Optional[str] = None,
        limit: int = 1000,
        order_by: str = 'desc'
    ) -> List[Dict[str, Any]]:
        """
        Get logs based on various filters.
        
        Args:
            start_time: Start time for logs. Defaults to 24 hours ago.
            end_time: End time for logs. Defaults to now.
            levels: List of log levels to include. Defaults to all levels.
            logger_names: List of logger names to include. Defaults to all loggers.
            search_text: Text to search for in log messages. Defaults to None.
            limit: Maximum number of logs to return. Defaults to 1000.
            order_by: Order of logs ('asc' or 'desc'). Defaults to 'desc'.
            
        Returns:
            List of matching log records.
        """
        # Set default times if not provided
        if start_time is None:
            start_time = datetime.now() - timedelta(days=1)
        if end_time is None:
            end_time = datetime.now()
        
        # Normalize levels to uppercase if provided
        if levels:
            levels = [level.upper() for level in levels]
        
        # Compile search regex if provided
        search_regex = None
        if search_text:
            try:
                search_regex = re.compile(search_text, re.IGNORECASE)
            except re.error:
                # Fall back to simple substring search if not a valid regex
                pass
        
        # Get log files in the date range
        log_files = self._get_log_files_in_range(start_time, end_time)
        
        # Process log files
        logs = []
        for log_file in log_files:
            file_logs = self._parse_log_file(
                log_file, 
                start_time, 
                end_time, 
                levels, 
                logger_names, 
                search_text, 
                search_regex
            )
            logs.extend(file_logs)
        
        # Sort logs
        if order_by.lower() == 'asc':
            logs.sort(key=lambda x: x.get('timestamp', ''))
        else:
            logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Apply limit
        return logs[:limit]
    
    def _get_log_files_in_range(
        self, 
        start_time: datetime, 
        end_time: datetime
    ) -> List[str]:
        """
        Get log files that contain records in the given time range.
        
        Args:
            start_time: Start time for logs.
            end_time: End time for logs.
            
        Returns:
            List of log file paths.
        """
        log_files = []
        
        # Add the main log file
        main_log_file = os.path.join(self.log_dir, 'app.log')
        if os.path.exists(main_log_file):
            log_files.append(main_log_file)
        
        # Add rotated log files
        for i in range(1, self.backup_count + 1):
            rotated_file = f"{main_log_file}.{i}"
            if os.path.exists(rotated_file):
                log_files.append(rotated_file)
            
            # Also check for compressed rotated files
            gzip_file = f"{rotated_file}.gz"
            if os.path.exists(gzip_file):
                log_files.append(gzip_file)
        
        # Get modification times and filter by date range
        filtered_files = []
        for log_file in log_files:
            # Check if the file was modified in the date range
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
                # If file was modified after start_time - 1 day, it might contain logs in the range
                if mtime >= start_time - timedelta(days=1):
                    filtered_files.append(log_file)
            except Exception:
                # If there's an error getting the modification time, include the file just in case
                filtered_files.append(log_file)
        
        return filtered_files
    
    def _parse_log_file(
        self, 
        log_file: str,
        start_time: datetime,
        end_time: datetime,
        levels: Optional[List[str]],
        logger_names: Optional[List[str]],
        search_text: Optional[str],
        search_regex: Optional[Pattern]
    ) -> List[Dict[str, Any]]:
        """
        Parse a log file and extract matching records.
        
        Args:
            log_file: Path to log file.
            start_time: Start time for logs.
            end_time: End time for logs.
            levels: List of log levels to include.
            logger_names: List of logger names to include.
            search_text: Text to search for in log messages.
            search_regex: Compiled regex for search.
            
        Returns:
            List of matching log records.
        """
        logs = []
        
        # Open the file, handling gzip if needed
        try:
            if log_file.endswith('.gz'):
                opener = gzip.open
                mode = 'rt'
            else:
                opener = open
                mode = 'r'
            
            with opener(log_file, mode) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Parse the log record
                    try:
                        record = json.loads(line) if self.use_json else self._parse_text_log(line)
                        
                        # Apply filters
                        if not self._matches_filters(
                            record, 
                            start_time, 
                            end_time, 
                            levels, 
                            logger_names, 
                            search_text, 
                            search_regex
                        ):
                            continue
                        
                        logs.append(record)
                    except json.JSONDecodeError:
                        # Skip if not a valid JSON record
                        pass
                    except Exception as e:
                        self.logger.warning(f"Error parsing log record: {e}")
        
        except Exception as e:
            self.logger.error(f"Error reading log file {log_file}: {e}")
        
        return logs
    
    def _parse_text_log(self, line: str) -> Dict[str, Any]:
        """
        Parse a text log line into a structured record.
        
        Args:
            line: Log line to parse.
            
        Returns:
            Structured log record.
            
        Raises:
            ValueError: If the line cannot be parsed.
        """
        # This is a simple implementation that assumes a specific format
        # In a real system, you would have a more robust parser
        
        # Example format: "2023-01-01 12:00:00,123 [INFO] logger_name: Message"
        try:
            # Split timestamp, level, and message
            timestamp_str, rest = line.split(' [', 1)
            level, rest = rest.split('] ', 1)
            logger_name, message = rest.split(': ', 1)
            
            # Parse timestamp
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
            
            return {
                'timestamp': timestamp.isoformat(),
                'level': level,
                'logger': logger_name,
                'message': message
            }
        except Exception:
            # If parsing fails, just return the raw line
            return {
                'timestamp': datetime.now().isoformat(),
                'level': 'UNKNOWN',
                'logger': 'parser',
                'message': line
            }
    
    def _matches_filters(
        self,
        record: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        levels: Optional[List[str]],
        logger_names: Optional[List[str]],
        search_text: Optional[str],
        search_regex: Optional[Pattern]
    ) -> bool:
        """
        Check if a log record matches the given filters.
        
        Args:
            record: Log record to check.
            start_time: Start time for logs.
            end_time: End time for logs.
            levels: List of log levels to include.
            logger_names: List of logger names to include.
            search_text: Text to search for in log messages.
            search_regex: Compiled regex for search.
            
        Returns:
            True if the record matches all filters, False otherwise.
        """
        # Check timestamp
        try:
            timestamp_str = record.get('timestamp', '')
            if timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                if timestamp < start_time or timestamp > end_time:
                    return False
        except (ValueError, TypeError):
            # If timestamp is invalid, assume it matches
            pass
        
        # Check level
        if levels:
            record_level = record.get('level', '')
            if record_level not in levels:
                return False
        
        # Check logger name
        if logger_names:
            record_logger = record.get('logger', '')
            if record_logger not in logger_names:
                return False
        
        # Check search text
        if search_text or search_regex:
            message = record.get('message', '')
            
            if search_regex:
                if not search_regex.search(message):
                    # Also search in the full record for nested fields
                    record_str = json.dumps(record)
                    if not search_regex.search(record_str):
                        return False
            elif search_text:
                if search_text.lower() not in message.lower():
                    # Also search in the full record for nested fields
                    record_str = json.dumps(record)
                    if search_text.lower() not in record_str.lower():
                        return False
        
        return True
    
    def export_logs(
        self,
        export_path: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        levels: Optional[List[str]] = None,
        logger_names: Optional[List[str]] = None,
        search_text: Optional[str] = None,
        format: str = 'json'
    ) -> bool:
        """
        Export logs to a file.
        
        Args:
            export_path: Path to export logs to.
            start_time: Start time for logs. Defaults to 24 hours ago.
            end_time: End time for logs. Defaults to now.
            levels: List of log levels to include. Defaults to all levels.
            logger_names: List of logger names to include. Defaults to all loggers.
            search_text: Text to search for in log messages. Defaults to None.
            format: Export format ('json', 'csv', 'txt'). Defaults to 'json'.
            
        Returns:
            True if export successful, False otherwise.
        """
        try:
            # Get logs with filters
            logs = self.get_logs(
                start_time=start_time,
                end_time=end_time,
                levels=levels,
                logger_names=logger_names,
                search_text=search_text,
                limit=100000,  # Large limit for export
                order_by='asc'  # Chronological order for export
            )
            
            # Create directory if needed
            os.makedirs(os.path.dirname(os.path.abspath(export_path)), exist_ok=True)
            
            # Export based on format
            if format.lower() == 'json':
                with open(export_path, 'w') as f:
                    json.dump(logs, f, indent=2)
            
            elif format.lower() == 'csv':
                import csv
                with open(export_path, 'w', newline='') as f:
                    # Determine all possible fields
                    all_fields = set()
                    for log in logs:
                        all_fields.update(log.keys())
                    
                    # Prioritize common fields
                    common_fields = ['timestamp', 'level', 'logger', 'message']
                    fieldnames = common_fields + sorted(field for field in all_fields if field not in common_fields)
                    
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for log in logs:
                        writer.writerow(log)
            
            elif format.lower() == 'txt':
                with open(export_path, 'w') as f:
                    for log in logs:
                        timestamp = log.get('timestamp', '')
                        level = log.get('level', 'UNKNOWN')
                        logger_name = log.get('logger', '')
                        message = log.get('message', '')
                        
                        f.write(f"{timestamp} [{level}] {logger_name}: {message}\n")
            
            else:
                self.logger.error(f"Unsupported export format: {format}")
                return False
            
            self.logger.info(f"Exported {len(logs)} logs to {export_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export logs: {e}")
            return False
    
    def cleanup_old_logs(self) -> int:
        """
        Clean up old logs based on retention policy.
        
        Returns:
            Number of files deleted.
        """
        try:
            deleted_count = 0
            retention_date = datetime.now() - timedelta(days=self.retention_days)
            
            for root, _, files in os.walk(self.log_dir):
                for file in files:
                    if file.startswith('app.log.') or file.endswith('.gz'):
                        file_path = os.path.join(root, file)
                        file_date = datetime.fromtimestamp(os.path.getmtime(file_path))
                        
                        if file_date < retention_date:
                            os.remove(file_path)
                            deleted_count += 1
                            self.logger.debug(f"Deleted old log file: {file_path}")
            
            self.logger.info(f"Cleaned up {deleted_count} old log files")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Failed to clean up old logs: {e}")
            return 0
    
    def get_log_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get statistics about logs.
        
        Args:
            start_time: Start time for stats. Defaults to 24 hours ago.
            end_time: End time for stats. Defaults to now.
            
        Returns:
            Dictionary with log statistics.
        """
        # Set default times if not provided
        if start_time is None:
            start_time = datetime.now() - timedelta(days=1)
        if end_time is None:
            end_time = datetime.now()
        
        try:
            # Get logs in time range
            logs = self.get_logs(
                start_time=start_time,
                end_time=end_time,
                limit=100000  # Large limit for stats
            )
            
            # Calculate statistics
            level_counts = {}
            logger_counts = {}
            error_counts = {}
            hourly_counts = {}
            
            for log in logs:
                # Level counts
                level = log.get('level', 'UNKNOWN')
                level_counts[level] = level_counts.get(level, 0) + 1
                
                # Logger counts
                logger_name = log.get('logger', 'unknown')
                logger_counts[logger_name] = logger_counts.get(logger_name, 0) + 1
                
                # Error tracking (if level is ERROR or higher)
                if level in ('ERROR', 'CRITICAL', 'FATAL'):
                    message = log.get('message', '')
                    error_key = message[:100]  # First 100 chars as key
                    error_counts[error_key] = error_counts.get(error_key, 0) + 1
                
                # Hourly distribution
                try:
                    timestamp_str = log.get('timestamp', '')
                    if timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        hour_key = timestamp.strftime('%Y-%m-%d %H:00')
                        hourly_counts[hour_key] = hourly_counts.get(hour_key, 0) + 1
                except (ValueError, TypeError):
                    pass
            
            # Sort data for the result
            top_errors = sorted(
                [{'message': k, 'count': v} for k, v in error_counts.items()],
                key=lambda x: x['count'],
                reverse=True
            )[:10]  # Top 10 errors
            
            top_loggers = sorted(
                [{'logger': k, 'count': v} for k, v in logger_counts.items()],
                key=lambda x: x['count'],
                reverse=True
            )[:10]  # Top 10 loggers
            
            # Generate hourly series with all hours in range
            hourly_series = []
            current = start_time.replace(minute=0, second=0, microsecond=0)
            while current <= end_time:
                hour_key = current.strftime('%Y-%m-%d %H:00')
                hourly_series.append({
                    'hour': hour_key,
                    'count': hourly_counts.get(hour_key, 0)
                })
                current += timedelta(hours=1)
            
            return {
                'total_logs': len(logs),
                'by_level': [{'level': k, 'count': v} for k, v in level_counts.items()],
                'top_errors': top_errors,
                'top_loggers': top_loggers,
                'hourly_distribution': hourly_series,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get log stats: {e}")
            return {
                'error': str(e),
                'total_logs': 0,
                'by_level': [],
                'top_errors': [],
                'top_loggers': [],
                'hourly_distribution': [],
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat()
            }
    
    def shutdown(self):
        """Clean up resources used by the LogManager."""
        # Stop the log processor thread
        if self.log_processor:
            self.log_processor.stop()
        
        # Clear callbacks
        self.log_callbacks.clear()
        
        # Flush any remaining logs
        logging.shutdown()
        
        self.logger.info("LogManager shut down")

# Singleton instance
_log_manager_instance = None

def get_log_manager(
    log_dir: str = None,
    log_level: str = "INFO",
    use_json: bool = True
) -> LogManager:
    """
    Get or create the singleton LogManager instance.
    
    Args:
        log_dir: Directory for log files.
        log_level: Minimum logging level.
        use_json: Whether to use JSON format for logs.
        
    Returns:
        LogManager instance.
    """
    global _log_manager_instance
    if _log_manager_instance is None:
        _log_manager_instance = LogManager(
            log_dir=log_dir,
            log_level=log_level,
            use_json=use_json
        )
    return _log_manager_instance 