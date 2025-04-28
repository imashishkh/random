"""
Fallback Mechanisms for System Failures
--------------------------------------
Provides failsafe mechanisms to handle system failures gracefully.
"""

import logging
import threading
import time
from typing import Dict, Any, Callable, List, Optional, Union
from enum import Enum
from datetime import datetime, timedelta
import json
import os

logger = logging.getLogger(__name__)

class SystemStatus(Enum):
    """System status enumeration."""
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    FAILED = "failed"


class FailureType(Enum):
    """Types of failures that can occur."""
    MODEL_INFERENCE = "model_inference"
    DATA_UNAVAILABLE = "data_unavailable"
    EXCHANGE_CONNECTION = "exchange_connection"
    STRATEGY_PERFORMANCE = "strategy_performance"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    UNKNOWN = "unknown"


class FallbackStrategy:
    """
    Implements fallback mechanisms to handle various failure scenarios in the system.
    """
    
    def __init__(self, 
                config_path: Optional[str] = None,
                status_check_interval: int = 60,
                recovery_check_interval: int = 30,
                log_dir: str = "logs/fallback"):
        """
        Initialize the fallback strategy manager.
        
        Args:
            config_path: Path to fallback configuration JSON
            status_check_interval: Interval for status checks in seconds
            recovery_check_interval: Interval for recovery attempts in seconds
            log_dir: Directory to store fallback logs
        """
        self.config_path = config_path
        self.status_check_interval = status_check_interval
        self.recovery_check_interval = recovery_check_interval
        self.log_dir = log_dir
        
        # Create log directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        
        # Load configuration
        self.config = self._load_config()
        
        # System status
        self.system_status = SystemStatus.OPERATIONAL
        self.subsystem_status = {}
        
        # Failure tracking
        self.active_failures = {}
        self.failure_history = []
        self.recovery_attempts = {}
        
        # Fallback actions
        self.fallback_actions = {
            FailureType.MODEL_INFERENCE: self._handle_model_inference_failure,
            FailureType.DATA_UNAVAILABLE: self._handle_data_unavailable,
            FailureType.EXCHANGE_CONNECTION: self._handle_exchange_connection_failure,
            FailureType.STRATEGY_PERFORMANCE: self._handle_strategy_performance_failure,
            FailureType.RESOURCE_EXHAUSTION: self._handle_resource_exhaustion,
            FailureType.UNKNOWN: self._handle_unknown_failure
        }
        
        # Recovery actions
        self.recovery_actions = {
            FailureType.MODEL_INFERENCE: self._recover_model_inference,
            FailureType.DATA_UNAVAILABLE: self._recover_data_availability,
            FailureType.EXCHANGE_CONNECTION: self._recover_exchange_connection,
            FailureType.STRATEGY_PERFORMANCE: self._recover_strategy_performance,
            FailureType.RESOURCE_EXHAUSTION: self._recover_resource_exhaustion,
            FailureType.UNKNOWN: self._recover_unknown_failure
        }
        
        # Callbacks for notifications
        self.notification_callbacks = []
        
        # Running state
        self.running = True
        
        # Start background threads
        self._start_status_check_thread()
        self._start_recovery_thread()
    
    def _load_config(self) -> Dict[str, Any]:
        """
        Load fallback configuration from file.
        
        Returns:
            Configuration dictionary
        """
        default_config = {
            "thresholds": {
                "model_inference": {
                    "error_rate_threshold": 0.1,  # 10% error rate
                    "timeout_threshold": 2.0      # 2 seconds
                },
                "data_unavailable": {
                    "max_missing_intervals": 5,
                    "max_delay_seconds": 60
                },
                "exchange_connection": {
                    "max_reconnect_attempts": 5,
                    "reconnect_interval_seconds": 30
                },
                "strategy_performance": {
                    "max_drawdown": 0.15,         # 15% max drawdown
                    "min_equity_threshold": 0.50  # 50% of initial equity
                },
                "resource_exhaustion": {
                    "memory_threshold": 0.9,      # 90% memory usage
                    "cpu_threshold": 0.95         # 95% CPU usage
                }
            },
            "fallback_actions": {
                "model_inference": {
                    "switch_to_baseline_model": True,
                    "use_rule_based_fallback": True
                },
                "data_unavailable": {
                    "use_cached_data": True,
                    "reduce_trading_frequency": True
                },
                "exchange_connection": {
                    "pause_trading": True,
                    "close_positions": True
                },
                "strategy_performance": {
                    "reduce_position_size": 0.5,  # 50% reduction
                    "tighten_risk_controls": True
                },
                "resource_exhaustion": {
                    "disable_non_critical_components": True,
                    "reduce_data_processing": True
                }
            },
            "recovery": {
                "automatic_recovery": True,
                "max_recovery_attempts": 3,
                "exponential_backoff": True,
                "backoff_factor": 2,
                "notify_on_recovery": True
            }
        }
        
        # If no config file specified, use defaults
        if not self.config_path:
            return default_config
        
        try:
            with open(self.config_path, 'r') as f:
                loaded_config = json.load(f)
                
            # Merge with defaults (shallow merge)
            for key, value in loaded_config.items():
                default_config[key] = value
                
            logger.info(f"Loaded fallback configuration from {self.config_path}")
            return default_config
            
        except Exception as e:
            logger.error(f"Failed to load fallback config from {self.config_path}: {str(e)}")
            logger.info("Using default fallback configuration")
            return default_config
    
    def register_failure(self, 
                        failure_type: Union[FailureType, str], 
                        subsystem: str,
                        details: Dict[str, Any] = None) -> None:
        """
        Register a system failure to trigger fallback mechanisms.
        
        Args:
            failure_type: Type of failure
            subsystem: Name of the affected subsystem
            details: Optional details about the failure
        """
        # Convert string to enum if needed
        if isinstance(failure_type, str):
            try:
                failure_type = FailureType(failure_type)
            except ValueError:
                failure_type = FailureType.UNKNOWN
        
        # Create failure record
        failure = {
            'type': failure_type,
            'subsystem': subsystem,
            'details': details or {},
            'timestamp': datetime.now(),
            'handled': False,
            'recovery_attempts': 0,
            'resolved': False,
            'resolved_timestamp': None
        }
        
        # Check if this is a new failure or update to existing one
        failure_key = f"{failure_type.value}_{subsystem}"
        
        with threading.Lock():
            if failure_key in self.active_failures:
                # Update existing failure with new details
                existing = self.active_failures[failure_key]
                existing['details'].update(details or {})
                existing['timestamp'] = failure['timestamp']
                logger.warning(f"Updated existing failure: {failure_key}")
            else:
                # Register new failure
                self.active_failures[failure_key] = failure
                self.failure_history.append(failure)
                logger.error(f"Registered new failure: {failure_type.value} in {subsystem}")
                
                # Handle the failure
                self._handle_failure(failure)
    
    def _handle_failure(self, failure: Dict[str, Any]) -> None:
        """
        Apply appropriate fallback actions for a failure.
        
        Args:
            failure: Failure record dictionary
        """
        failure_type = failure['type']
        
        try:
            # Mark as handled
            failure['handled'] = True
            
            # Update subsystem status
            self.subsystem_status[failure['subsystem']] = SystemStatus.DEGRADED
            
            # Apply specific fallback action
            if failure_type in self.fallback_actions:
                self.fallback_actions[failure_type](failure)
            else:
                # Default fallback
                self._handle_unknown_failure(failure)
            
            # Log the action
            self._log_fallback_action(failure)
            
            # Send notifications
            self._send_notifications(failure, "fallback_triggered")
            
            # Update system status based on active failures
            self._update_system_status()
            
        except Exception as e:
            logger.error(f"Error handling failure: {str(e)}")
    
    def _update_system_status(self) -> None:
        """Update overall system status based on subsystem statuses."""
        if not self.active_failures:
            self.system_status = SystemStatus.OPERATIONAL
            return
        
        # Check if any subsystem has failed
        failed = any(status == SystemStatus.FAILED for status in self.subsystem_status.values())
        
        if failed:
            self.system_status = SystemStatus.FAILED
        else:
            self.system_status = SystemStatus.DEGRADED
        
        logger.info(f"System status updated to: {self.system_status.value}")
    
    def _handle_model_inference_failure(self, failure: Dict[str, Any]) -> None:
        """
        Handle model inference failures.
        
        Args:
            failure: Failure record dictionary
        """
        config = self.config['fallback_actions']['model_inference']
        subsystem = failure['subsystem']
        details = failure['details']
        
        logger.info(f"Handling model inference failure in {subsystem}")
        
        # Switch to baseline model if enabled
        if config.get('switch_to_baseline_model', True):
            logger.info(f"Switching {subsystem} to baseline model")
            # In a real implementation, this would call the model switching API
            
        # Use rule-based fallback if enabled
        if config.get('use_rule_based_fallback', True):
            logger.info(f"Activating rule-based fallback for {subsystem}")
            # In a real implementation, this would activate rule-based strategies
    
    def _handle_data_unavailable(self, failure: Dict[str, Any]) -> None:
        """
        Handle data unavailability failures.
        
        Args:
            failure: Failure record dictionary
        """
        config = self.config['fallback_actions']['data_unavailable']
        subsystem = failure['subsystem']
        
        logger.info(f"Handling data unavailability in {subsystem}")
        
        # Use cached data if enabled
        if config.get('use_cached_data', True):
            logger.info(f"Using cached data for {subsystem}")
            # In a real implementation, this would switch to cached data source
            
        # Reduce trading frequency if enabled
        if config.get('reduce_trading_frequency', True):
            logger.info(f"Reducing trading frequency for {subsystem}")
            # In a real implementation, this would adjust trading parameters
    
    def _handle_exchange_connection_failure(self, failure: Dict[str, Any]) -> None:
        """
        Handle exchange connection failures.
        
        Args:
            failure: Failure record dictionary
        """
        config = self.config['fallback_actions']['exchange_connection']
        subsystem = failure['subsystem']
        
        logger.info(f"Handling exchange connection failure in {subsystem}")
        
        # Pause trading if enabled
        if config.get('pause_trading', True):
            logger.info(f"Pausing trading for {subsystem}")
            # In a real implementation, this would pause the trading system
            
        # Close positions if enabled
        if config.get('close_positions', True):
            logger.info(f"Closing positions for {subsystem}")
            # In a real implementation, this would close open positions
    
    def _handle_strategy_performance_failure(self, failure: Dict[str, Any]) -> None:
        """
        Handle strategy performance failures.
        
        Args:
            failure: Failure record dictionary
        """
        config = self.config['fallback_actions']['strategy_performance']
        subsystem = failure['subsystem']
        
        logger.info(f"Handling strategy performance failure in {subsystem}")
        
        # Reduce position size if enabled
        if reduction_factor := config.get('reduce_position_size'):
            logger.info(f"Reducing position size by factor {reduction_factor} for {subsystem}")
            # In a real implementation, this would adjust position sizing parameters
            
        # Tighten risk controls if enabled
        if config.get('tighten_risk_controls', True):
            logger.info(f"Tightening risk controls for {subsystem}")
            # In a real implementation, this would adjust risk parameters
    
    def _handle_resource_exhaustion(self, failure: Dict[str, Any]) -> None:
        """
        Handle resource exhaustion failures.
        
        Args:
            failure: Failure record dictionary
        """
        config = self.config['fallback_actions']['resource_exhaustion']
        subsystem = failure['subsystem']
        
        logger.info(f"Handling resource exhaustion in {subsystem}")
        
        # Disable non-critical components if enabled
        if config.get('disable_non_critical_components', True):
            logger.info(f"Disabling non-critical components for {subsystem}")
            # In a real implementation, this would disable non-essential processes
            
        # Reduce data processing if enabled
        if config.get('reduce_data_processing', True):
            logger.info(f"Reducing data processing for {subsystem}")
            # In a real implementation, this would adjust data processing parameters
    
    def _handle_unknown_failure(self, failure: Dict[str, Any]) -> None:
        """
        Handle unknown failure types.
        
        Args:
            failure: Failure record dictionary
        """
        subsystem = failure['subsystem']
        
        logger.info(f"Handling unknown failure in {subsystem}")
        
        # For unknown failures, take conservative actions
        logger.info(f"Taking conservative actions for unknown failure in {subsystem}")
        
        # In a real implementation, this would take conservative protective measures
    
    def _recover_model_inference(self, failure: Dict[str, Any]) -> bool:
        """
        Attempt to recover from model inference failure.
        
        Args:
            failure: Failure record dictionary
            
        Returns:
            True if recovery successful, False otherwise
        """
        # In a real implementation, this would attempt to reload models or restart inference service
        logger.info(f"Attempting to recover model inference for {failure['subsystem']}")
        time.sleep(2)  # Simulate recovery attempt
        
        # Simulate 70% chance of success
        import random
        return random.random() < 0.7
    
    def _recover_data_availability(self, failure: Dict[str, Any]) -> bool:
        """
        Attempt to recover from data unavailability.
        
        Args:
            failure: Failure record dictionary
            
        Returns:
            True if recovery successful, False otherwise
        """
        # In a real implementation, this would attempt to reconnect to data sources
        logger.info(f"Attempting to recover data availability for {failure['subsystem']}")
        time.sleep(2)  # Simulate recovery attempt
        
        # Simulate 80% chance of success
        import random
        return random.random() < 0.8
    
    def _recover_exchange_connection(self, failure: Dict[str, Any]) -> bool:
        """
        Attempt to recover from exchange connection failure.
        
        Args:
            failure: Failure record dictionary
            
        Returns:
            True if recovery successful, False otherwise
        """
        # In a real implementation, this would attempt to reconnect to the exchange
        logger.info(f"Attempting to recover exchange connection for {failure['subsystem']}")
        time.sleep(3)  # Simulate recovery attempt
        
        # Simulate 75% chance of success
        import random
        return random.random() < 0.75
    
    def _recover_strategy_performance(self, failure: Dict[str, Any]) -> bool:
        """
        Attempt to recover from strategy performance failure.
        
        Args:
            failure: Failure record dictionary
            
        Returns:
            True if recovery successful, False otherwise
        """
        # In a real implementation, this would adjust strategy parameters or switch strategies
        logger.info(f"Attempting to recover strategy performance for {failure['subsystem']}")
        time.sleep(2)  # Simulate recovery attempt
        
        # Simulate 60% chance of success
        import random
        return random.random() < 0.6
    
    def _recover_resource_exhaustion(self, failure: Dict[str, Any]) -> bool:
        """
        Attempt to recover from resource exhaustion.
        
        Args:
            failure: Failure record dictionary
            
        Returns:
            True if recovery successful, False otherwise
        """
        # In a real implementation, this would free resources or restart services
        logger.info(f"Attempting to recover from resource exhaustion for {failure['subsystem']}")
        time.sleep(4)  # Simulate recovery attempt
        
        # Simulate 90% chance of success
        import random
        return random.random() < 0.9
    
    def _recover_unknown_failure(self, failure: Dict[str, Any]) -> bool:
        """
        Attempt to recover from unknown failure.
        
        Args:
            failure: Failure record dictionary
            
        Returns:
            True if recovery successful, False otherwise
        """
        # For unknown failures, try a generic recovery procedure
        logger.info(f"Attempting to recover from unknown failure for {failure['subsystem']}")
        time.sleep(3)  # Simulate recovery attempt
        
        # Simulate 50% chance of success
        import random
        return random.random() < 0.5
    
    def _attempt_recovery(self, failure_key: str) -> None:
        """
        Attempt to recover from a failure.
        
        Args:
            failure_key: Key of the failure to recover from
        """
        with threading.Lock():
            if failure_key not in self.active_failures:
                return
            
            failure = self.active_failures[failure_key]
            failure_type = failure['type']
            
            # Check if automatic recovery is enabled
            if not self.config['recovery'].get('automatic_recovery', True):
                logger.info(f"Automatic recovery disabled for {failure_key}")
                return
            
            # Check maximum recovery attempts
            max_attempts = self.config['recovery'].get('max_recovery_attempts', 3)
            if failure['recovery_attempts'] >= max_attempts:
                logger.warning(f"Maximum recovery attempts reached for {failure_key}")
                
                # Mark subsystem as failed if max attempts reached
                self.subsystem_status[failure['subsystem']] = SystemStatus.FAILED
                self._update_system_status()
                return
            
            # Increment recovery attempts
            failure['recovery_attempts'] += 1
            
            # Log attempt
            logger.info(f"Recovery attempt {failure['recovery_attempts']}/{max_attempts} for {failure_key}")
            
            # Attempt recovery
            success = False
            try:
                if failure_type in self.recovery_actions:
                    success = self.recovery_actions[failure_type](failure)
                else:
                    success = self._recover_unknown_failure(failure)
            except Exception as e:
                logger.error(f"Error during recovery attempt for {failure_key}: {str(e)}")
            
            if success:
                logger.info(f"Recovery successful for {failure_key}")
                
                # Mark as resolved
                failure['resolved'] = True
                failure['resolved_timestamp'] = datetime.now()
                
                # Update status
                self.subsystem_status[failure['subsystem']] = SystemStatus.OPERATIONAL
                
                # Remove from active failures
                del self.active_failures[failure_key]
                
                # Update system status
                self._update_system_status()
                
                # Send notification
                self._send_notifications(failure, "recovery_successful")
            else:
                logger.warning(f"Recovery attempt failed for {failure_key}")
                
                # Calculate backoff for next attempt
                if self.config['recovery'].get('exponential_backoff', True):
                    base_interval = self.recovery_check_interval
                    factor = self.config['recovery'].get('backoff_factor', 2)
                    backoff = base_interval * (factor ** (failure['recovery_attempts'] - 1))
                    
                    # Set next recovery time
                    next_attempt = datetime.now() + timedelta(seconds=backoff)
                    self.recovery_attempts[failure_key] = next_attempt
                    
                    logger.info(f"Next recovery attempt for {failure_key} scheduled at {next_attempt}")
                
                # Send notification
                self._send_notifications(failure, "recovery_failed")
    
    def _log_fallback_action(self, failure: Dict[str, Any]) -> None:
        """
        Log a fallback action to file.
        
        Args:
            failure: Failure record dictionary
        """
        log_file = os.path.join(self.log_dir, 'fallback_actions.jsonl')
        
        # Prepare log entry
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'failure_type': failure['type'].value,
            'subsystem': failure['subsystem'],
            'details': failure['details'],
            'action': 'fallback_triggered'
        }
        
        try:
            with open(log_file, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to log fallback action: {str(e)}")
    
    def _send_notifications(self, failure: Dict[str, Any], event_type: str) -> None:
        """
        Send notifications to all registered callbacks.
        
        Args:
            failure: Failure record dictionary
            event_type: Type of event (fallback_triggered, recovery_successful, etc.)
        """
        notification = {
            'timestamp': datetime.now().isoformat(),
            'event_type': event_type,
            'failure_type': failure['type'].value,
            'subsystem': failure['subsystem'],
            'details': failure['details']
        }
        
        for callback in self.notification_callbacks:
            try:
                callback(notification)
            except Exception as e:
                logger.error(f"Error in notification callback: {str(e)}")
    
    def register_notification_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Register a callback for fallback and recovery notifications.
        
        Args:
            callback: Callable that accepts a notification dictionary
        """
        self.notification_callbacks.append(callback)
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        Get the current system status.
        
        Returns:
            Status dictionary
        """
        return {
            'overall': self.system_status.value,
            'subsystems': {k: v.value for k, v in self.subsystem_status.items()},
            'active_failures': len(self.active_failures),
            'failures': [
                {
                    'type': f['type'].value,
                    'subsystem': f['subsystem'],
                    'timestamp': f['timestamp'].isoformat(),
                    'recovery_attempts': f['recovery_attempts']
                }
                for f in self.active_failures.values()
            ],
            'timestamp': datetime.now().isoformat()
        }
    
    def get_failure_history(self, 
                           limit: int = 10, 
                           subsystem: Optional[str] = None,
                           failure_type: Optional[Union[FailureType, str]] = None) -> List[Dict[str, Any]]:
        """
        Get historical failure records.
        
        Args:
            limit: Maximum number of records to return
            subsystem: Filter by subsystem
            failure_type: Filter by failure type
            
        Returns:
            List of failure records
        """
        # Convert string to enum if needed
        if isinstance(failure_type, str):
            try:
                failure_type = FailureType(failure_type)
            except ValueError:
                failure_type = None
        
        # Apply filters
        filtered = self.failure_history
        
        if subsystem:
            filtered = [f for f in filtered if f['subsystem'] == subsystem]
            
        if failure_type:
            filtered = [f for f in filtered if f['type'] == failure_type]
        
        # Sort by timestamp (newest first) and limit
        sorted_failures = sorted(filtered, key=lambda f: f['timestamp'], reverse=True)[:limit]
        
        # Convert to serializable format
        result = []
        for failure in sorted_failures:
            f_copy = failure.copy()
            f_copy['type'] = failure['type'].value
            f_copy['timestamp'] = failure['timestamp'].isoformat()
            if f_copy['resolved_timestamp']:
                f_copy['resolved_timestamp'] = failure['resolved_timestamp'].isoformat()
            result.append(f_copy)
        
        return result
    
    def _status_check_thread(self) -> None:
        """Background thread for periodic status checks."""
        while self.running:
            try:
                # Just update system status based on active failures
                with threading.Lock():
                    self._update_system_status()
                
                # Wait for next check
                time.sleep(self.status_check_interval)
                
            except Exception as e:
                logger.error(f"Error in status check thread: {str(e)}")
                time.sleep(10)  # Wait a bit before trying again
    
    def _recovery_thread(self) -> None:
        """Background thread for recovery attempts."""
        while self.running:
            try:
                now = datetime.now()
                
                # Check for recovery attempts
                with threading.Lock():
                    # Get failures to attempt recovery for
                    to_recover = []
                    
                    for failure_key, failure in self.active_failures.items():
                        # If no scheduled time, attempt recovery
                        if failure_key not in self.recovery_attempts:
                            to_recover.append(failure_key)
                        # If scheduled time has passed, attempt recovery
                        elif now >= self.recovery_attempts[failure_key]:
                            to_recover.append(failure_key)
                    
                    # Attempt recovery for each failure
                    for failure_key in to_recover:
                        self._attempt_recovery(failure_key)
                
                # Wait for next check
                time.sleep(self.recovery_check_interval)
                
            except Exception as e:
                logger.error(f"Error in recovery thread: {str(e)}")
                time.sleep(10)  # Wait a bit before trying again
    
    def _start_status_check_thread(self) -> None:
        """Start the status check background thread."""
        thread = threading.Thread(target=self._status_check_thread, daemon=True)
        thread.start()
        logger.info("Status check thread started")
    
    def _start_recovery_thread(self) -> None:
        """Start the recovery background thread."""
        thread = threading.Thread(target=self._recovery_thread, daemon=True)
        thread.start()
        logger.info("Recovery thread started")
    
    def shutdown(self) -> None:
        """Gracefully shut down the fallback strategy manager."""
        logger.info("Fallback strategy manager shutting down...")
        self.running = False
        logger.info("Fallback strategy manager shutdown complete") 