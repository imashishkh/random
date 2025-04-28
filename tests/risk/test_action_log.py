"""
Tests for RiskActionLog

This module tests the functionality of the RiskActionLog class.
"""

import os
import json
import unittest
import tempfile
import time
from unittest.mock import MagicMock, patch

from src.risk.action_log import RiskActionLog


class TestRiskActionLog(unittest.TestCase):
    """Test suite for RiskActionLog class."""
    
    def setUp(self):
        """Set up test environment."""
        # Create a temporary log file
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_file_path = os.path.join(self.temp_dir.name, "test_risk_actions.log")
        
        # Create mock database connection
        self.mock_db = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_db.cursor.return_value = self.mock_cursor
        
        # Create RiskActionLog instance
        self.action_log = RiskActionLog(
            log_file_path=self.log_file_path,
            db_connection=self.mock_db
        )
    
    def tearDown(self):
        """Clean up after tests."""
        self.temp_dir.cleanup()
    
    def test_init_creates_log_file(self):
        """Test log file creation during initialization."""
        # Log file should be created
        self.assertTrue(os.path.exists(self.log_file_path))
    
    def test_log_event_writes_to_file(self):
        """Test that log_event writes to the log file."""
        # Log a test event
        event_type = "TEST_EVENT"
        event_data = {"test_key": "test_value"}
        
        result = self.action_log.log_event(event_type, event_data)
        
        # Check result
        self.assertTrue(result)
        
        # Check file contains the event
        with open(self.log_file_path, 'r') as f:
            log_content = f.read()
            
        self.assertIn(event_type, log_content)
        self.assertIn("test_key", log_content)
        self.assertIn("test_value", log_content)
    
    def test_log_event_stores_in_database(self):
        """Test that log_event stores event in database."""
        # Log a test event
        event_type = "TEST_EVENT"
        event_data = {"test_key": "test_value"}
        
        result = self.action_log.log_event(event_type, event_data)
        
        # Check result
        self.assertTrue(result)
        
        # Check database was called
        self.mock_db.cursor.assert_called_once()
        self.mock_cursor.execute.assert_called_once()
        self.mock_db.commit.assert_called_once()
    
    def test_log_event_handles_db_error(self):
        """Test that log_event handles database errors gracefully."""
        # Make database throw exception
        self.mock_cursor.execute.side_effect = Exception("Test exception")
        
        # Log a test event
        event_type = "TEST_EVENT"
        event_data = {"test_key": "test_value"}
        
        result = self.action_log.log_event(event_type, event_data)
        
        # Check result is False due to db error
        self.assertFalse(result)
        
        # Check file still contains the event
        with open(self.log_file_path, 'r') as f:
            log_content = f.read()
            
        self.assertIn(event_type, log_content)
    
    def test_query_events_no_db(self):
        """Test that query_events returns empty list when no database."""
        # Create action log without database
        action_log = RiskActionLog(log_file_path=self.log_file_path)
        
        # Query events
        results = action_log.query_events()
        
        # Should return empty list
        self.assertEqual(results, [])
    
    def test_query_events_with_filters(self):
        """Test that query_events builds correct query with filters."""
        # Prepare mock cursor to return empty result
        self.mock_cursor.fetchall.return_value = []
        
        # Query with filters
        event_type = "TEST_EVENT"
        start_time = 1000.0
        end_time = 2000.0
        severity = "WARNING"
        
        self.action_log.query_events(
            event_type=event_type,
            start_time=start_time,
            end_time=end_time,
            severity=severity
        )
        
        # Check correct SQL query was built
        execute_call = self.mock_cursor.execute.call_args[0]
        query = execute_call[0]
        params = execute_call[1]
        
        # Check query contains all filters
        self.assertIn("event_type = ?", query)
        self.assertIn("timestamp >= ?", query)
        self.assertIn("timestamp <= ?", query)
        self.assertIn("severity = ?", query)
        
        # Check params contains all filter values
        self.assertIn(event_type, params)
        self.assertIn(start_time, params)
        self.assertIn(end_time, params)
        self.assertIn(severity, params)
    
    def test_convenience_methods(self):
        """Test convenience logging methods."""
        # Patch the log_event method
        with patch.object(self.action_log, 'log_event') as mock_log_event:
            # Log warning
            details = {"test": "warning"}
            self.action_log.log_warning(details)
            mock_log_event.assert_called_with("WARNING", details, "WARNING")
            
            # Log limit violation
            details = {"test": "violation"}
            self.action_log.log_limit_violation(details)
            mock_log_event.assert_called_with("LIMIT_VIOLATION", details, "ERROR")
            
            # Log circuit breaker
            details = {"test": "breaker"}
            self.action_log.log_circuit_breaker(details)
            mock_log_event.assert_called_with("CIRCUIT_BREAKER", details, "ERROR")
            
            # Log kill switch
            details = {"test": "kill_switch"}
            self.action_log.log_kill_switch(details)
            mock_log_event.assert_called_with("KILL_SWITCH", details, "CRITICAL")


if __name__ == '__main__':
    unittest.main() 