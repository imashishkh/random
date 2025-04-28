"""
Slack Sender module for handling Slack-based notifications.

This module provides a class for sending formatted notifications to Slack channels
via webhooks with support for advanced formatting.
"""

import logging
import json
import requests
from typing import Dict, List, Any, Optional
import traceback

# Configure logger
logger = logging.getLogger(__name__)

class SlackSender:
    """
    SlackSender handles sending notifications to Slack channels via webhooks.
    
    Supports message formatting, attachments, and level-based icons.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Slack sender with configuration settings.
        
        Args:
            config: Dictionary with Slack configuration settings
        """
        self.config = config
        self.enabled = config.get("enabled", False)
        
        # Verify webhook URL exists if enabled
        if self.enabled and not self.config.get("webhook_url"):
            logger.warning("Slack sender initialized but webhook URL is missing")
            self.enabled = False
        
        if self.enabled:
            logger.info("Slack sender initialized")
        else:
            logger.info("Slack sender disabled")
        
        # Define level icons for Slack messages
        self.level_icons = {
            "info": ":information_source:",
            "warning": ":warning:",
            "error": ":x:",
            "critical": ":skull_and_crossbones:",
            "success": ":white_check_mark:",
            "debug": ":mag:"
        }
    
    def send_message(
        self, 
        message: str, 
        level: str = "info", 
        subject: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        blocks: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Send a message to Slack via webhook.
        
        Args:
            message: Message content
            level: Notification level (info, warning, error, success, etc.)
            subject: Optional subject/title (will be prepended to message)
            attachments: Optional Slack message attachments
            blocks: Optional Slack blocks for advanced formatting
            
        Returns:
            True if message was sent successfully, False otherwise
            
        Raises:
            Exception: Any error encountered during message sending (after logging)
        """
        if not self.enabled:
            logger.debug("Slack sender is disabled, skipping")
            return False
        
        try:
            # Format message with level-specific icon
            level_icon = self.level_icons.get(level.lower(), ":bell:")
            
            formatted_text = f"{level_icon} "
            
            # Add subject if provided
            if subject:
                formatted_text += f"*{subject}*\n"
            
            # Add message content
            formatted_text += message
            
            # Create payload
            payload = {
                "channel": self.config.get("channel", "#general"),
                "username": self.config.get("username", "Forex Trading Bot"),
                "text": formatted_text,
                "mrkdwn": True
            }
            
            # Add attachments if provided
            if attachments:
                payload["attachments"] = attachments
            
            # Add blocks if provided
            if blocks:
                payload["blocks"] = blocks
            
            # Send request to webhook
            response = requests.post(
                self.config["webhook_url"],
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"}
            )
            
            # Check response
            if response.status_code == 200:
                logger.info(f"Slack message sent successfully: {subject or message[:30]}...")
                return True
            else:
                error_msg = f"Error sending Slack message, status code: {response.status_code}, response: {response.text}"
                logger.error(error_msg)
                raise Exception(error_msg)
                
        except Exception as e:
            error_msg = f"Error sending Slack message: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            raise Exception(error_msg)
    
    def send_formatted_report(
        self,
        title: str,
        sections: List[Dict[str, Any]],
        level: str = "info"
    ) -> bool:
        """
        Send a formatted report with multiple sections to Slack.
        
        Args:
            title: Report title
            sections: List of section dictionaries, each with 'title' and 'content' keys
            level: Notification level
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug("Slack sender is disabled, skipping")
            return False
        
        # Create blocks for a nicely formatted report
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": title
                }
            },
            {
                "type": "divider"
            }
        ]
        
        # Add each section
        for section in sections:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{section['title']}*\n{section['content']}"
                }
            })
        
        # Add level-specific icon to message text
        level_icon = self.level_icons.get(level.lower(), ":bell:")
        text = f"{level_icon} {title}"
        
        return self.send_message(
            message=text,
            level=level,
            blocks=blocks
        ) 