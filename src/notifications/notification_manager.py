"""
Notification Manager module for handling alerts and notifications.

This module provides a unified interface for sending various types of notifications
including emails, Slack messages, and integration with other alert systems.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
import traceback

# Import sender classes
from .email_sender import EmailSender
from .slack_sender import SlackSender

# Configure logger
logger = logging.getLogger(__name__)

class NotificationManager:
    """
    NotificationManager provides a unified interface for sending notifications
    across different channels (email, Slack, etc.).
    
    This class handles notification formatting, delivery, and tracking.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the notification manager with configuration settings.
        
        Args:
            config_path: Path to notification configuration file
        """
        self.config = self._load_config(config_path)
        self.notification_history = []
        
        # Initialize notification channels
        self._init_email()
        self._init_slack()
        
        logger.info("NotificationManager initialized")
    
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """
        Load notification configuration from a file or use environment variables.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Configuration dictionary
        """
        config = {
            "email": {
                "enabled": os.getenv("NOTIFICATION_EMAIL_ENABLED", "false").lower() == "true",
                "smtp_server": os.getenv("NOTIFICATION_EMAIL_SMTP_SERVER", "smtp.gmail.com"),
                "smtp_port": int(os.getenv("NOTIFICATION_EMAIL_SMTP_PORT", "587")),
                "username": os.getenv("NOTIFICATION_EMAIL_USERNAME", ""),
                "password": os.getenv("NOTIFICATION_EMAIL_PASSWORD", ""),
                "from_email": os.getenv("NOTIFICATION_EMAIL_FROM", ""),
                "recipients": os.getenv("NOTIFICATION_EMAIL_RECIPIENTS", "").split(","),
                "use_tls": os.getenv("NOTIFICATION_EMAIL_USE_TLS", "true").lower() == "true"
            },
            "slack": {
                "enabled": os.getenv("NOTIFICATION_SLACK_ENABLED", "false").lower() == "true",
                "webhook_url": os.getenv("NOTIFICATION_SLACK_WEBHOOK_URL", ""),
                "channel": os.getenv("NOTIFICATION_SLACK_CHANNEL", "#alerts"),
                "username": os.getenv("NOTIFICATION_SLACK_USERNAME", "TradingBot")
            },
            "general": {
                "environment": os.getenv("ENVIRONMENT", "development"),
                "log_notifications": os.getenv("NOTIFICATION_LOG_ENABLED", "true").lower() == "true",
                "notification_level": os.getenv("NOTIFICATION_LEVEL", "info")
            }
        }
        
        # Override with config file if provided
        if config_path:
            if not os.path.exists(config_path):
                raise FileNotFoundError(f"Notification configuration file not found: {config_path}")
                
            try:
                with open(config_path, 'r') as f:
                    file_config = json.load(f)
                
                # Update the config with file values
                # Update email config
                if "email" in file_config:
                    for key, value in file_config["email"].items():
                        config["email"][key] = value
                
                # Update slack config
                if "slack" in file_config:
                    for key, value in file_config["slack"].items():
                        config["slack"][key] = value
                
                # Update general config
                if "general" in file_config:
                    for key, value in file_config["general"].items():
                        config["general"][key] = value
                
                logger.info(f"Loaded notification configuration from {config_path}")
            except Exception as e:
                logger.error(f"Error loading notification config from {config_path}: {str(e)}")
                logger.error(traceback.format_exc())
        
        return config
    
    def _init_email(self) -> None:
        """Initialize email notification sender."""
        try:
            self.email_sender = EmailSender(self.config["email"])
            self.email_enabled = self.email_sender.enabled
        except Exception as e:
            logger.error(f"Error initializing email sender: {str(e)}")
            logger.error(traceback.format_exc())
            self.email_enabled = False
            self.email_sender = None
    
    def _init_slack(self) -> None:
        """Initialize Slack notification sender."""
        try:
            self.slack_sender = SlackSender(self.config["slack"])
            self.slack_enabled = self.slack_sender.enabled
        except Exception as e:
            logger.error(f"Error initializing Slack sender: {str(e)}")
            logger.error(traceback.format_exc())
            self.slack_enabled = False
            self.slack_sender = None
    
    def _should_notify(self, level: str) -> bool:
        """
        Check if a notification should be sent based on its level.
        
        Args:
            level: Notification level (debug, info, warning, error, critical)
            
        Returns:
            True if notification should be sent, False otherwise
        """
        level_order = {
            "debug": 0,
            "info": 1,
            "warning": 2,
            "error": 3,
            "critical": 4
        }
        
        config_level = self.config["general"]["notification_level"].lower()
        if config_level not in level_order:
            logger.warning(f"Invalid notification level in config: {config_level}, defaulting to 'info'")
            config_level = "info"
        
        return level_order.get(level.lower(), 0) >= level_order[config_level]
    
    def _log_notification(self, channel: str, level: str, subject: str, message: str) -> None:
        """
        Log a notification for tracking purposes.
        
        Args:
            channel: Notification channel (email, slack, etc.)
            level: Notification level
            subject: Notification subject
            message: Notification message
        """
        if not self.config["general"]["log_notifications"]:
            return
        
        notification_record = {
            "timestamp": datetime.now().isoformat(),
            "channel": channel,
            "level": level,
            "subject": subject,
            "message": message[:100] + "..." if len(message) > 100 else message,
            "environment": self.config["general"]["environment"]
        }
        
        self.notification_history.append(notification_record)
        
        # Prevent history from growing too large
        if len(self.notification_history) > 1000:
            self.notification_history = self.notification_history[-1000:]
    
    def send_notification(self, 
                         level: str, 
                         subject: str, 
                         message: str,
                         html_message: Optional[str] = None,
                         email_recipients: Optional[List[str]] = None,
                         slack_attachments: Optional[List[Dict[str, Any]]] = None,
                         channels: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        Send a notification across enabled channels.
        
        Args:
            level: Notification level (debug, info, warning, error, critical)
            subject: Notification subject/title
            message: Notification message
            html_message: HTML formatted message for email (optional)
            email_recipients: Override default email recipients (optional)
            slack_attachments: Attachments for Slack messages (optional)
            channels: List of channels to use (default: all enabled)
            
        Returns:
            Dictionary of channels and their send status
        """
        if not self._should_notify(level):
            return {}
        
        # Determine which channels to use
        if channels is None:
            channels = []
            if self.email_enabled:
                channels.append("email")
            if self.slack_enabled:
                channels.append("slack")
        
        results = {}
        
        # Add environment to subject for non-production environments
        env = self.config["general"]["environment"].upper()
        formatted_subject = f"[{env}] {subject}" if env.lower() != "production" else subject
        
        # Send to each channel
        for channel in channels:
            if channel == "email" and self.email_sender:
                try:
                    results["email"] = self.email_sender.send_email(
                        subject=formatted_subject,
                        message=message,
                        level=level,
                        recipients=email_recipients
                    )
                    if results["email"]:
                        self._log_notification("email", level, subject, message)
                except Exception as e:
                    logger.error(f"Error sending email notification: {str(e)}")
                    results["email"] = False
                    
            elif channel == "slack" and self.slack_sender:
                try:
                    results["slack"] = self.slack_sender.send_message(
                        message=message,
                        level=level,
                        subject=formatted_subject,
                        attachments=slack_attachments
                    )
                    if results["slack"]:
                        self._log_notification("slack", level, subject, message)
                except Exception as e:
                    logger.error(f"Error sending Slack notification: {str(e)}")
                    results["slack"] = False
                    
            else:
                logger.warning(f"Unknown or unavailable notification channel: {channel}")
        
        return results
    
    def send_error(self, subject: str, message: str, exception: Optional[Exception] = None) -> Dict[str, bool]:
        """
        Send an error notification.
        
        Args:
            subject: Error subject/title
            message: Error message
            exception: Optional exception to include in the message
            
        Returns:
            Dictionary of channels and their send status
        """
        full_message = message
        
        if exception:
            full_message += f"\n\nException: {str(exception)}"
            full_message += f"\n\nTraceback:\n{traceback.format_exc()}"
        
        return self.send_notification("error", subject, full_message)
    
    def send_warning(self, subject: str, message: str) -> Dict[str, bool]:
        """
        Send a warning notification.
        
        Args:
            subject: Warning subject/title
            message: Warning message
            
        Returns:
            Dictionary of channels and their send status
        """
        return self.send_notification("warning", subject, message)
    
    def send_info(self, subject: str, message: str) -> Dict[str, bool]:
        """
        Send an informational notification.
        
        Args:
            subject: Info subject/title
            message: Info message
            
        Returns:
            Dictionary of channels and their send status
        """
        return self.send_notification("info", subject, message)
    
    def get_notification_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent notification history.
        
        Args:
            limit: Maximum number of notifications to return
            
        Returns:
            List of notification records
        """
        return self.notification_history[-limit:] if self.notification_history else []
    
    def format_model_validation_message(self, validation_results: Dict[str, Any], 
                                       thresholds: Optional[Dict[str, float]] = None,
                                       timestamp: Optional[str] = None) -> str:
        """
        Format a message for model validation results.
        
        Args:
            validation_results: Dictionary with validation metrics
            thresholds: Dictionary with validation thresholds (optional)
            timestamp: Optional timestamp string
            
        Returns:
            Formatted message string
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat()
            
        message = f"Model Validation Results ({timestamp})\n\n"
        
        # Add model information
        if "model_id" in validation_results:
            message += f"Model ID: {validation_results['model_id']}\n"
        if "model_type" in validation_results:
            message += f"Model Type: {validation_results['model_type']}\n"
        if "agent_type" in validation_results:
            message += f"Agent Type: {validation_results['agent_type']}\n"
        if "model_version" in validation_results:
            message += f"Version: {validation_results['model_version']}\n"
        if "model_name" in validation_results:
            message += f"Model Name: {validation_results['model_name']}\n"
            
        message += "\nMetrics:\n"
        
        # Add metrics and indicate pass/fail if thresholds provided
        metrics = validation_results.get("metrics", {})
        if not metrics and isinstance(validation_results.get("accuracy"), (int, float)):
            # Handle simplified metric format
            metrics = {
                "accuracy": validation_results.get("accuracy", 0),
                "precision": validation_results.get("precision", 0),
                "recall": validation_results.get("recall", 0),
                "f1_score": validation_results.get("f1_score", 0)
            }
            
        for metric_name, metric_value in metrics.items():
            if isinstance(metric_value, (int, float)):
                value_str = f"{metric_value:.4f}" if isinstance(metric_value, float) else str(metric_value)
                
                if thresholds and metric_name in thresholds:
                    threshold = thresholds[metric_name]
                    
                    # Determine if passed threshold
                    if metric_name.startswith("min_"):
                        passed = metric_value >= threshold
                    else:
                        passed = metric_value <= threshold
                    
                    status = "✅ PASS" if passed else "❌ FAIL"
                    message += f"- {metric_name}: {value_str} (threshold: {threshold:.4f}) {status}\n"
                else:
                    # Format percentages
                    if 0 <= metric_value <= 1 and metric_name in ["accuracy", "precision", "recall", "f1_score"]:
                        value_str = f"{metric_value * 100:.1f}%"
                    
                    message += f"- {metric_name}: {value_str}\n"
        
        # Overall status
        if "passed_validation" in validation_results:
            overall = "✅ PASSED" if validation_results["passed_validation"] else "❌ FAILED"
            message += f"\nOverall Validation: {overall}\n"
            
        # Add validation details if available
        if "details" in validation_results:
            message += f"\nDetails:\n{validation_results['details']}\n"
            
        return message
    
    def format_deployment_message(self, deployment_results: Dict[str, Any],
                                timestamp: Optional[str] = None) -> str:
        """
        Format a message for model deployment results.
        
        Args:
            deployment_results: Dictionary with deployment information
            timestamp: Optional timestamp string
            
        Returns:
            Formatted message string
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat()
            
        message = f"Model Deployment Results ({timestamp})\n\n"
        
        # Add model information
        if "model_id" in deployment_results:
            message += f"Model ID: {deployment_results['model_id']}\n"
        if "model_type" in deployment_results:
            message += f"Model Type: {deployment_results['model_type']}\n"
        if "agent_type" in deployment_results:
            message += f"Agent Type: {deployment_results['agent_type']}\n"
        if "model_version" in deployment_results:
            message += f"Version: {deployment_results['model_version']}\n"
        if "model_name" in deployment_results:
            message += f"Model Name: {deployment_results['model_name']}\n"
            
        # Add deployment status
        status_field = next((f for f in ["status", "deployment_status"] if f in deployment_results), None)
        if status_field:
            status_value = deployment_results[status_field]
            if isinstance(status_value, bool):
                status = "✅ SUCCESS" if status_value else "❌ FAILED"
            else:
                status = f"✅ SUCCESS" if status_value.lower() == "success" else f"❌ {status_value.upper()}"
            message += f"\nDeployment Status: {status}\n"
            
        # Add environment
        if "environment" in deployment_results:
            message += f"Environment: {deployment_results['environment']}\n"
            
        # Add deployment location
        if "deployment_location" in deployment_results:
            message += f"Deployment Location: {deployment_results['deployment_location']}\n"
            
        # Add timestamp if provided in results
        if "timestamp" in deployment_results:
            message += f"Timestamp: {deployment_results['timestamp']}\n"
            
        # Add server information if available
        if "server_info" in deployment_results:
            message += f"\nServer Information:\n"
            server_info = deployment_results["server_info"]
            if isinstance(server_info, dict):
                for key, value in server_info.items():
                    message += f"- {key}: {value}\n"
            else:
                message += f"{server_info}\n"
            
        # Add metrics if available
        if "metrics" in deployment_results:
            message += f"\nMetrics:\n"
            metrics = deployment_results["metrics"]
            for metric_name, metric_value in metrics.items():
                if isinstance(metric_value, float):
                    message += f"- {metric_name}: {metric_value:.4f}\n"
                else:
                    message += f"- {metric_name}: {metric_value}\n"
                
        # Add details if available
        if "details" in deployment_results:
            message += f"\nDetails:\n{deployment_results['details']}\n"
            
        return message 