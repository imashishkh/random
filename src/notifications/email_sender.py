"""
Email Sender module for handling email-based notifications.

This module provides a class for sending formatted email notifications via SMTP.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Any, Optional
import traceback

# Configure logger
logger = logging.getLogger(__name__)

class EmailSender:
    """
    EmailSender handles sending emails using SMTP with support for HTML formatting,
    TLS, and customizable templates.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the email sender with configuration settings.
        
        Args:
            config: Dictionary with email configuration settings
        """
        self.config = config
        self.enabled = config.get("enabled", False)
        
        if self.enabled:
            logger.info("Email sender initialized")
        else:
            logger.info("Email sender disabled")
        
        # HTML template with placeholders for subject, message, and level
        self.default_html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; }
                .header { padding: 10px; background-color: #f8f8f8; border-bottom: 1px solid #ddd; }
                .content { padding: 20px; }
                .footer { padding: 10px; font-size: 12px; color: #777; border-top: 1px solid #ddd; }
                .info { border-left: 4px solid #2196F3; }
                .warning { border-left: 4px solid #FFC107; }
                .error { border-left: 4px solid #F44336; }
                .success { border-left: 4px solid #4CAF50; }
            </style>
        </head>
        <body>
            <div class="header">
                <h2>{subject}</h2>
            </div>
            <div class="content {level}">
                <p><strong>{level_title}:</strong> {message}</p>
            </div>
            <div class="footer">
                <p>Sent by Forex Trading Bot</p>
            </div>
        </body>
        </html>
        """
    
    def send_email(
        self, 
        subject: str, 
        message: str, 
        level: str = "info",
        recipients: Optional[List[str]] = None,
        html_template: Optional[str] = None
    ) -> bool:
        """
        Send an email notification.
        
        Args:
            subject: Email subject
            message: Plain text message
            level: Notification level (info, warning, error, success)
            recipients: List of email recipients (uses config default if None)
            html_template: Custom HTML template to use (uses default if None)
            
        Returns:
            True if email was sent successfully, False otherwise
            
        Raises:
            Exception: Any error encountered during email sending (after logging)
        """
        if not self.enabled:
            logger.debug("Email sender is disabled, skipping")
            return False
        
        if recipients is None:
            recipients = self.config.get("recipients", [])
        
        if not recipients:
            logger.warning("No recipients specified for email")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.config["from_email"]
            msg["To"] = ", ".join(recipients)
            
            # Add plain text part
            msg.attach(MIMEText(message, "plain"))
            
            # Add HTML part with appropriate styling based on level
            template = html_template or self.config.get("html_template") or self.default_html_template
            level_titles = {
                "info": "Info",
                "warning": "Warning",
                "error": "Error",
                "success": "Success",
                "debug": "Debug"
            }
            
            level_title = level_titles.get(level.lower(), "Notification")
            
            html_content = template.format(
                subject=subject,
                message=message,
                level=level.lower(),
                level_title=level_title
            )
            
            msg.attach(MIMEText(html_content, "html"))
            
            # Connect to SMTP server
            if self.config.get("use_tls", True):
                smtp = smtplib.SMTP(
                    self.config["smtp_server"], 
                    self.config["smtp_port"]
                )
                smtp.starttls()
            else:
                smtp = smtplib.SMTP(
                    self.config["smtp_server"], 
                    self.config["smtp_port"]
                )
            
            # Login and send
            smtp.login(
                self.config["username"], 
                self.config["password"]
            )
            
            smtp.send_message(msg)
            smtp.quit()
            
            logger.info(f"Email sent successfully to {len(recipients)} recipients: {subject}")
            return True
            
        except Exception as e:
            error_msg = f"Error sending email: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            raise Exception(error_msg) 