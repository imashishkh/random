"""
Notifications Package

This package provides a notification system for sending alerts and notifications
via various channels including email and Slack.

Components:
- NotificationManager: Unified interface for sending notifications
- EmailSender: Handles email-based notifications
- SlackSender: Handles Slack-based notifications
"""

from .notification_manager import NotificationManager
from .email_sender import EmailSender
from .slack_sender import SlackSender

# Define package exports
__all__ = ["NotificationManager", "EmailSender", "SlackSender"] 