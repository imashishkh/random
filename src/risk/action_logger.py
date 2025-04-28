"""
Action Logger Module

This module implements a logger for risk control actions and limit violations.
"""

import json
import logging
from datetime import datetime
import os


class ActionLogger:
    """
    Logger for risk control actions and violations.
    
    This class provides methods to log and track various actions related to
    risk management, including:
    - Limit violations
    - Warning messages
    - Position adjustments
    - Trade rejections
    """
    
    def __init__(self, log_file=None, console_output=True):
        """
        Initialize the action logger.
        
        Args:
            log_file (str, optional): Path to the log file
            console_output (bool): Whether to output logs to console
        """
        self.log_file = log_file
        self.console_output = console_output
        self.violations = []
        self.actions = []
        
        # Set up logger
        self.logger = logging.getLogger(__name__)
        
        if not self.logger.handlers:
            # Configure console handler
            if console_output:
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.INFO)
                formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
                console_handler.setFormatter(formatter)
                self.logger.addHandler(console_handler)
            
            # Configure file handler if log file is specified
            if log_file:
                # Ensure log directory exists
                log_dir = os.path.dirname(log_file)
                if log_dir and not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                    
                file_handler = logging.FileHandler(log_file)
                file_handler.setLevel(logging.INFO)
                formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
            
            self.logger.setLevel(logging.INFO)
            
    def log_limit_violation(self, violation_type, message, details=None):
        """
        Log a limit violation.
        
        Args:
            violation_type (str): Type of violation
            message (str): Violation message
            details (dict, optional): Additional violation details
        """
        timestamp = datetime.now().isoformat()
        
        violation_record = {
            "timestamp": timestamp,
            "type": violation_type,
            "message": message,
            "details": details or {}
        }
        
        self.violations.append(violation_record)
        self.logger.warning(f"VIOLATION: {violation_type} - {message}")
        
        if self.log_file:
            self._write_to_json_log(violation_record, 'violation')
    
    def log_position_adjustment(self, symbol, action, original_size, new_size, reason):
        """
        Log a position size adjustment.
        
        Args:
            symbol (str): Trading symbol
            action (str): Adjustment action (e.g., "REDUCE", "INCREASE", "REJECTED")
            original_size (float): Original position size
            new_size (float): New position size
            reason (str): Reason for adjustment
        """
        timestamp = datetime.now().isoformat()
        
        adjustment_record = {
            "timestamp": timestamp,
            "type": "position_adjustment",
            "symbol": symbol,
            "action": action,
            "original_size": original_size,
            "new_size": new_size,
            "reason": reason
        }
        
        self.actions.append(adjustment_record)
        self.logger.info(f"ADJUSTMENT: {symbol} {action} {original_size}->{new_size}: {reason}")
        
        if self.log_file:
            self._write_to_json_log(adjustment_record, 'action')
    
    def log_warning(self, message, details=None):
        """
        Log a warning message.
        
        Args:
            message (str): Warning message
            details (dict, optional): Additional warning details
        """
        timestamp = datetime.now().isoformat()
        
        warning_record = {
            "timestamp": timestamp,
            "type": "warning",
            "message": message,
            "details": details or {}
        }
        
        self.actions.append(warning_record)
        self.logger.warning(f"WARNING: {message}")
        
        if self.log_file:
            self._write_to_json_log(warning_record, 'action')
    
    def log_info(self, message, details=None):
        """
        Log an information message.
        
        Args:
            message (str): Information message
            details (dict, optional): Additional information details
        """
        timestamp = datetime.now().isoformat()
        
        info_record = {
            "timestamp": timestamp,
            "type": "info",
            "message": message,
            "details": details or {}
        }
        
        self.actions.append(info_record)
        self.logger.info(f"INFO: {message}")
        
        if self.log_file:
            self._write_to_json_log(info_record, 'action')
    
    def get_violations(self, clear=False):
        """
        Get the list of recorded violations.
        
        Args:
            clear (bool): Whether to clear the violations list after retrieval
            
        Returns:
            list: List of violation records
        """
        violations = self.violations.copy()
        
        if clear:
            self.violations = []
            
        return violations
    
    def get_actions(self, clear=False):
        """
        Get the list of recorded actions.
        
        Args:
            clear (bool): Whether to clear the actions list after retrieval
            
        Returns:
            list: List of action records
        """
        actions = self.actions.copy()
        
        if clear:
            self.actions = []
            
        return actions
    
    def clear_history(self):
        """Clear all action and violation history."""
        self.violations = []
        self.actions = []
        
    def _write_to_json_log(self, record, record_type):
        """
        Write a record to the JSON log file.
        
        Args:
            record (dict): Record to write
            record_type (str): Type of record ('action' or 'violation')
        """
        try:
            with open(self.log_file, 'a') as f:
                f.write(json.dumps({
                    "record_type": record_type,
                    "data": record
                }) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to write to log file: {e}") 