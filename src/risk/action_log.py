"""
Risk Action Log

This module provides a specialized logger for risk control actions,
supporting both file-based logging and database storage for auditability.
"""

import os
import json
import time
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

# Configure logger
logger = logging.getLogger(__name__)

class RiskActionLog:
    """
    Risk Action Log for tracking risk control events.
    
    This class provides:
    - Structured logging of all risk control actions
    - Support for both file and database backends
    - Severity level classification for events
    - Queryable history for auditing and analysis
    """
    
    def __init__(
        self, 
        log_file_path: str = None, 
        db_connection: Any = None,
        log_level: str = "INFO"
    ):
        """
        Initialize the Risk Action Log.
        
        Args:
            log_file_path: Path to log file (defaults to risk_actions.log in current directory)
            db_connection: Optional database connection for persistent storage
            log_level: Default logging level (INFO, WARNING, ERROR, CRITICAL)
        """
        self.db_connection = db_connection
        
        # Set up file logger
        self.logger = logging.getLogger('RiskActionLog')
        self.logger.setLevel(getattr(logging, log_level))
        
        # Ensure logger doesn't propagate to root logger
        self.logger.propagate = False
        
        # Determine log file path
        self.log_file_path = log_file_path or os.path.join(os.getcwd(), 'risk_actions.log')
        
        # Create file handler if it doesn't exist already
        if not self.logger.handlers:
            # Create file handler
            file_handler = logging.FileHandler(self.log_file_path)
            file_handler.setLevel(logging.INFO)
            
            # Create formatter
            formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            
            # Add handlers
            self.logger.addHandler(file_handler)
            
        logger.info(f"Initialized Risk Action Log with file: {self.log_file_path}")
    
    def log_event(
        self, 
        event_type: str, 
        event_data: Dict[str, Any], 
        severity: str = 'INFO'
    ) -> bool:
        """
        Log a risk control event.
        
        Args:
            event_type: Type of event (WARNING, HARD_LIMIT, CIRCUIT_BREAKER, KILL_SWITCH)
            event_data: Dictionary with event details
            severity: Log severity (INFO, WARNING, ERROR, CRITICAL)
            
        Returns:
            bool: Success status
        """
        # Add timestamp if not present
        if 'timestamp' not in event_data:
            event_data['timestamp'] = time.time()
            
        # Format timestamp as ISO for human readability
        if 'human_time' not in event_data:
            event_data['human_time'] = datetime.fromtimestamp(
                event_data['timestamp']
            ).isoformat()
        
        # Format the data as JSON
        event_json = json.dumps({
            'event_type': event_type,
            'severity': severity,
            'data': event_data
        })
        
        # Log to file based on severity
        log_fn = getattr(self.logger, severity.lower(), self.logger.info)
        log_fn(event_json)
        
        # Store in database if available
        if self.db_connection:
            try:
                return self._store_in_database(event_type, event_data, severity)
            except Exception as e:
                logger.error(f"Failed to store event in database: {str(e)}")
                return False
                
        return True
    
    def _store_in_database(
        self, 
        event_type: str, 
        event_data: Dict[str, Any], 
        severity: str
    ) -> bool:
        """
        Store event in database for queryable history.
        
        Args:
            event_type: Type of event
            event_data: Event data dictionary
            severity: Event severity level
            
        Returns:
            bool: Success status
        """
        try:
            # Implementation will vary based on database type
            # This is a placeholder for database implementation
            cursor = self.db_connection.cursor()
            
            # Insert into database
            query = """
                INSERT INTO risk_events
                (timestamp, event_type, severity, event_data)
                VALUES (?, ?, ?, ?)
            """
            cursor.execute(
                query,
                (
                    event_data.get('timestamp', time.time()), 
                    event_type, 
                    severity, 
                    json.dumps(event_data)
                )
            )
            self.db_connection.commit()
            return True
        except Exception as e:
            logger.error(f"Database error during event logging: {str(e)}")
            return False
    
    def query_events(
        self, 
        event_type: Optional[str] = None, 
        start_time: Optional[float] = None,
        end_time: Optional[float] = None, 
        severity: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query historical events with filters.
        
        Args:
            event_type: Filter by event type
            start_time: Filter by minimum timestamp (inclusive)
            end_time: Filter by maximum timestamp (inclusive)
            severity: Filter by severity level
            limit: Maximum number of results to return
            
        Returns:
            List of matching events
        """
        if not self.db_connection:
            logger.warning("Cannot query events: No database connection available")
            return []
            
        try:
            cursor = self.db_connection.cursor()
            
            # Build query
            query = "SELECT * FROM risk_events WHERE 1=1"
            params = []
            
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)
                
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)
                
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)
                
            if severity:
                query += " AND severity = ?"
                params.append(severity)
                
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            # Execute query
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            # Format results
            events = []
            for row in results:
                try:
                    event_data = json.loads(row['event_data'])
                except (json.JSONDecodeError, TypeError):
                    event_data = row['event_data']
                    
                events.append({
                    'id': row['id'],
                    'timestamp': row['timestamp'],
                    'event_type': row['event_type'],
                    'severity': row['severity'],
                    'data': event_data
                })
                
            return events
        except Exception as e:
            logger.error(f"Failed to query events: {str(e)}")
            return []
    
    def get_recent_events(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recent risk events.
        
        Args:
            count: Number of events to retrieve
            
        Returns:
            List of recent events
        """
        return self.query_events(limit=count)
    
    def get_recent_events_by_type(self, event_type: str, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recent risk events of a specific type.
        
        Args:
            event_type: Event type to filter by
            count: Number of events to retrieve
            
        Returns:
            List of recent events of the specified type
        """
        return self.query_events(event_type=event_type, limit=count)
    
    def log_warning(self, details: Dict[str, Any]) -> bool:
        """
        Log a warning event (approaching limits).
        
        Args:
            details: Warning details
            
        Returns:
            bool: Success status
        """
        return self.log_event("WARNING", details, "WARNING")
    
    def log_limit_violation(self, details: Dict[str, Any]) -> bool:
        """
        Log a hard limit violation.
        
        Args:
            details: Violation details
            
        Returns:
            bool: Success status
        """
        return self.log_event("LIMIT_VIOLATION", details, "ERROR")
    
    def log_circuit_breaker(self, details: Dict[str, Any]) -> bool:
        """
        Log a circuit breaker event.
        
        Args:
            details: Circuit breaker details
            
        Returns:
            bool: Success status
        """
        return self.log_event("CIRCUIT_BREAKER", details, "ERROR")
    
    def log_kill_switch(self, details: Dict[str, Any]) -> bool:
        """
        Log a kill switch activation.
        
        Args:
            details: Kill switch details
            
        Returns:
            bool: Success status
        """
        return self.log_event("KILL_SWITCH", details, "CRITICAL") 