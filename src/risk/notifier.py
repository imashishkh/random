"""
Risk Notifier Implementation

This module provides the RiskNotifier class for sending formatted risk alerts
to various notification channels, with primary support for Slack webhooks.
"""

import json
import time
import logging
import requests
import os
from enum import Enum
from typing import Dict, Any, Optional, List, Union, Callable
from datetime import datetime
from dataclasses import dataclass, field
import threading
from collections import defaultdict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class NotificationLevel(Enum):
    """Notification severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class NotificationConfig:
    """Configuration for the notification system."""
    slack_webhook_url: Optional[str] = None
    rate_limit_period: int = 60  # seconds
    rate_limit_count: Dict[str, int] = field(default_factory=lambda: {
        NotificationLevel.INFO.value: 5,      # 5 info notifications per period
        NotificationLevel.WARNING.value: 3,    # 3 warning notifications per period
        NotificationLevel.CRITICAL.value: 1,   # 1 critical notification per period
    })
    templates: Dict[str, str] = field(default_factory=dict)
    disable_notifications: bool = False
    fallback_to_logging: bool = True


@dataclass
class NotificationTemplate:
    """Template for a notification message."""
    title: str
    message: str
    fields: Dict[str, Any] = field(default_factory=dict)
    actions: List[Dict[str, str]] = field(default_factory=list)


class RiskNotifier:
    """
    Risk Notifier that handles sending alerts about risk events
    through various channels, primarily Slack.
    
    This class is responsible for:
    1. Sending formatted alerts via Slack webhooks
    2. Providing different notification levels (info, warning, critical)
    3. Managing templates for different alert types
    4. Rate limiting to prevent notification spam
    5. Falling back to logging when webhooks aren't configured
    """
    
    def __init__(self, config: Optional[NotificationConfig] = None):
        """
        Initialize the risk notifier.
        
        Args:
            config: Configuration for the notifier
        """
        self.config = config or NotificationConfig()
        
        # If no webhook URL is provided in config, check .env
        if self.config.slack_webhook_url is None:
            self.config.slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
        
        # Rate limiting state
        self._notification_counts: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.RLock()
        
        # Predefined templates
        self._initialize_default_templates()
        
        logger.info("Risk notifier initialized")
        if self.config.slack_webhook_url:
            logger.info("Slack webhook URL configured from environment")
        else:
            logger.warning("No Slack webhook URL configured, notifications will fall back to logging only")
    
    def _initialize_default_templates(self) -> None:
        """Initialize default notification templates."""
        default_templates = {
            "global_exposure_exceeded": NotificationTemplate(
                title="Global Exposure Limit Exceeded",
                message="Total portfolio exposure of {current_exposure:.2%} exceeds the {limit_type} limit of {exposure_limit:.2%}",
                fields={
                    "Portfolio Value": "${portfolio_value:,.2f}",
                    "Total Exposure": "{current_exposure:.2%}",
                    "Limit": "{exposure_limit:.2%}",
                }
            ),
            "symbol_exposure_exceeded": NotificationTemplate(
                title="Symbol Exposure Limit Exceeded",
                message="Exposure to {symbol} of {current_exposure:.2%} exceeds the {limit_type} limit of {exposure_limit:.2%}",
                fields={
                    "Symbol": "{symbol}",
                    "Position Size": "{position_size:,.2f}",
                    "Position Value": "${position_value:,.2f}",
                    "Current Exposure": "{current_exposure:.2%}",
                    "Limit": "{exposure_limit:.2%}",
                }
            ),
            "circuit_breaker_activated": NotificationTemplate(
                title="Circuit Breaker Activated",
                message="Trading circuit breaker activated due to {reason}. Trading paused for {duration} seconds.",
                fields={
                    "Reason": "{reason}",
                    "Duration": "{duration} seconds",
                    "Activated At": "{activated_at}",
                    "Will Resume At": "{resume_at}",
                }
            ),
            "emergency_shutdown": NotificationTemplate(
                title="EMERGENCY SHUTDOWN INITIATED",
                message="Emergency shutdown has been triggered due to {reason}. All positions are being closed.",
                fields={
                    "Reason": "{reason}",
                    "Triggered At": "{triggered_at}",
                    "Positions Closed": "{positions_closed}",
                    "Failures": "{failures}",
                },
                actions=[
                    {"text": "View Details", "url": "{dashboard_url}"},
                    {"text": "Reset System", "url": "{reset_url}"}
                ]
            ),
        }
        
        # Add templates to config if not already present
        for name, template in default_templates.items():
            if name not in self.config.templates:
                self.config.templates[name] = template
    
    def configure(self, config: NotificationConfig) -> None:
        """
        Configure the notifier.
        
        Args:
            config: New configuration
        """
        self.config = config
        
        # If no webhook URL is provided in config, check .env
        if self.config.slack_webhook_url is None:
            self.config.slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
            
        logger.info("Risk notifier reconfigured")
    
    def set_slack_webhook(self, webhook_url: str) -> None:
        """
        Set the Slack webhook URL.
        
        Args:
            webhook_url: Slack webhook URL
        """
        self.config.slack_webhook_url = webhook_url
        logger.info("Slack webhook URL configured")
    
    def add_template(self, name: str, template: NotificationTemplate) -> None:
        """
        Add a notification template.
        
        Args:
            name: Template name
            template: Template configuration
        """
        self.config.templates[name] = template
        logger.info(f"Added notification template: {name}")
    
    def notify(self, 
              level: Union[NotificationLevel, str], 
              template_name: str, 
              data: Dict[str, Any]) -> bool:
        """
        Send a notification using a template.
        
        Args:
            level: Notification level
            template_name: Template to use
            data: Data to inject into the template
            
        Returns:
            True if notification was sent, False otherwise
        """
        # Convert string level to enum if needed
        if isinstance(level, str):
            level = NotificationLevel(level)
        
        # Check if notifications are disabled
        if self.config.disable_notifications:
            logger.debug(f"Notification suppressed (disabled): {template_name}")
            return False
        
        # Check rate limiting
        if not self._check_rate_limit(level.value):
            logger.warning(f"Notification suppressed (rate limited): {level.value} - {template_name}")
            return False
        
        # Get template
        template = self.config.templates.get(template_name)
        if not template:
            logger.error(f"Template not found: {template_name}")
            return False
        
        # Format message from template
        try:
            title = template.title.format(**data)
            message = template.message.format(**data)
            
            # Format fields
            fields = {}
            for field_name, field_template in template.fields.items():
                fields[field_name] = field_template.format(**data)
            
            # Format actions
            actions = []
            for action in template.actions:
                formatted_action = {k: v.format(**data) for k, v in action.items()}
                actions.append(formatted_action)
            
            # Send to Slack
            return self._send_to_slack(level.value, title, message, fields, actions)
        except KeyError as e:
            logger.error(f"Missing data for template {template_name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error formatting notification: {e}")
            return False
    
    def notify_simple(self, 
                     level: Union[NotificationLevel, str], 
                     title: str, 
                     message: str) -> bool:
        """
        Send a simple notification without a template.
        
        Args:
            level: Notification level
            title: Alert title
            message: Alert message
            
        Returns:
            True if notification was sent, False otherwise
        """
        # Convert string level to enum if needed
        if isinstance(level, str):
            level = NotificationLevel(level)
        
        # Check if notifications are disabled
        if self.config.disable_notifications:
            logger.debug(f"Simple notification suppressed (disabled): {title}")
            return False
        
        # Check rate limiting
        if not self._check_rate_limit(level.value):
            logger.warning(f"Simple notification suppressed (rate limited): {level.value} - {title}")
            return False
        
        # Send to Slack
        return self._send_to_slack(level.value, title, message, {}, [])
    
    def _check_rate_limit(self, level: str) -> bool:
        """
        Check if a notification is allowed by rate limits.
        
        Args:
            level: Notification level
            
        Returns:
            True if allowed, False if rate limited
        """
        with self._lock:
            now = time.time()
            
            # Get the notification timestamps for this level
            timestamps = self._notification_counts[level]
            
            # Remove timestamps outside the rate limit period
            period_start = now - self.config.rate_limit_period
            timestamps = [ts for ts in timestamps if ts >= period_start]
            self._notification_counts[level] = timestamps
            
            # Check if we've hit the limit
            limit = self.config.rate_limit_count.get(level, 1)
            if len(timestamps) >= limit:
                return False
            
            # Add current timestamp and allow
            timestamps.append(now)
            return True
    
    def _send_to_slack(self, 
                      level: str, 
                      title: str, 
                      message: str, 
                      fields: Dict[str, str] = None,
                      actions: List[Dict[str, str]] = None) -> bool:
        """
        Send a notification to Slack.
        
        Args:
            level: Notification level
            title: Alert title
            message: Alert message
            fields: Optional fields for the message
            actions: Optional action buttons
            
        Returns:
            True if sent successfully, False otherwise
        """
        # Always log the message
        log_level = {
            NotificationLevel.INFO.value: logging.INFO,
            NotificationLevel.WARNING.value: logging.WARNING,
            NotificationLevel.CRITICAL.value: logging.CRITICAL
        }.get(level, logging.INFO)
        
        logger.log(log_level, f"RISK ALERT ({level.upper()}): {title} - {message}")
        
        # If no webhook URL, just log
        if not self.config.slack_webhook_url:
            if self.config.fallback_to_logging:
                logger.info(f"Slack notification not sent (no webhook URL): {title}")
            return self.config.fallback_to_logging
        
        try:
            # Set color based on level
            color = {
                NotificationLevel.INFO.value: "#36a64f",
                NotificationLevel.WARNING.value: "#ffcc00",
                NotificationLevel.CRITICAL.value: "#ff0000"
            }.get(level, "#36a64f")
            
            # Create blocks for modern Slack formatting
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": title,
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message
                    }
                }
            ]
            
            # Add fields if provided
            if fields and len(fields) > 0:
                field_blocks = []
                for name, value in fields.items():
                    field_blocks.append({
                        "type": "mrkdwn",
                        "text": f"*{name}*\n{value}"
                    })
                
                # Create field blocks with max 2 fields per row
                for i in range(0, len(field_blocks), 2):
                    block_fields = field_blocks[i:i+2]
                    blocks.append({
                        "type": "section",
                        "fields": block_fields
                    })
            
            # Add context with timestamp
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Time:* <!date^{int(datetime.now().timestamp())}^{{date_num}} {{time_secs}}|{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}>"
                    }
                ]
            })
            
            # Add actions if provided
            if actions and len(actions) > 0:
                action_elements = []
                for action in actions:
                    action_elements.append({
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": action.get("text", "View"),
                            "emoji": True
                        },
                        "url": action.get("url", "")
                    })
                
                blocks.append({
                    "type": "actions",
                    "elements": action_elements
                })
            
            # Create payload with both attachments (for color) and blocks (for formatting)
            payload = {
                "attachments": [
                    {
                        "color": color,
                        "blocks": blocks
                    }
                ]
            }
            
            # Send to Slack
            response = requests.post(
                self.config.slack_webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code != 200:
                logger.warning(f"Failed to send Slack notification: {response.text}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
            return False 