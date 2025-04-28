"""
Notification Manager Module

This module provides a comprehensive notification management system with features like:
- Multiple notification severity levels
- Various notification channels (console, desktop, email, Telegram)
- Notification history and acknowledgment
- Rate limiting to prevent notification storms
"""

import os
import time
import json
import logging
import threading
import queue
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Set, Union
from enum import Enum, auto
import smtplib
from email.message import EmailMessage
import traceback

class NotificationLevel(Enum):
    """Notification severity levels."""
    DEBUG = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()

class NotificationChannel(Enum):
    """Notification delivery channels."""
    CONSOLE = auto()
    DESKTOP = auto()
    EMAIL = auto()
    TELEGRAM = auto()
    LOG = auto()

class NotificationStatus(Enum):
    """Notification status."""
    PENDING = auto()
    DELIVERED = auto()
    FAILED = auto()
    ACKNOWLEDGED = auto()

class Notification:
    """Represents a single notification."""
    
    def __init__(
        self, 
        title: str,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        source: str = "system",
        timestamp: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
        channels: Optional[List[NotificationChannel]] = None
    ):
        """
        Initialize a notification.
        
        Args:
            title: Notification title.
            message: Notification message.
            level: Notification severity level.
            source: Source of the notification.
            timestamp: Notification timestamp. Defaults to now.
            metadata: Additional metadata.
            channels: Delivery channels to use.
        """
        self.id = f"{int(time.time())}-{id(self)}"
        self.title = title
        self.message = message
        self.level = level
        self.source = source
        self.timestamp = timestamp or datetime.now()
        self.metadata = metadata or {}
        self.channels = channels or [NotificationChannel.CONSOLE, NotificationChannel.LOG]
        self.status = NotificationStatus.PENDING
        self.delivered_at: Optional[datetime] = None
        self.acknowledged_at: Optional[datetime] = None
        self.delivery_attempts = 0
        self.delivery_error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the notification to a dictionary.
        
        Returns:
            Dictionary representation of the notification.
        """
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'level': self.level.name,
            'source': self.source,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata,
            'channels': [ch.name for ch in self.channels],
            'status': self.status.name,
            'delivered_at': self.delivered_at.isoformat() if self.delivered_at else None,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'delivery_attempts': self.delivery_attempts,
            'delivery_error': self.delivery_error
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Notification':
        """
        Create a notification from a dictionary.
        
        Args:
            data: Dictionary representation of a notification.
            
        Returns:
            Notification instance.
        """
        notification = cls(
            title=data['title'],
            message=data['message'],
            level=NotificationLevel[data['level']],
            source=data['source'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            metadata=data['metadata'],
            channels=[NotificationChannel[ch] for ch in data['channels']]
        )
        
        notification.id = data['id']
        notification.status = NotificationStatus[data['status']]
        
        if data['delivered_at']:
            notification.delivered_at = datetime.fromisoformat(data['delivered_at'])
        
        if data['acknowledged_at']:
            notification.acknowledged_at = datetime.fromisoformat(data['acknowledged_at'])
        
        notification.delivery_attempts = data['delivery_attempts']
        notification.delivery_error = data['delivery_error']
        
        return notification

class NotificationManager:
    """
    Manager for handling system notifications with different severity levels
    and delivery methods.
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        history_limit: int = 1000,
        log_notifications: bool = True,
        notification_dir: Optional[str] = None
    ):
        """
        Initialize the NotificationManager.
        
        Args:
            config: Configuration dictionary.
            history_limit: Maximum number of notifications to keep in history.
            log_notifications: Whether to log notifications.
            notification_dir: Directory for notification persistence.
        """
        self.config = config or {}
        self.history_limit = history_limit
        self.log_notifications = log_notifications
        self.notification_dir = notification_dir or os.path.join(os.getcwd(), 'data', 'notifications')
        
        # Create notification directory if needed
        os.makedirs(self.notification_dir, exist_ok=True)
        
        # State
        self.notifications: List[Notification] = []
        self.notification_queue = queue.Queue()
        self.callbacks: Dict[str, Callable[[Notification], None]] = {}
        self.level_callbacks: Dict[NotificationLevel, List[Callable[[Notification], None]]] = {
            level: [] for level in NotificationLevel
        }
        self.rate_limits: Dict[str, Dict[str, Any]] = {}
        
        # Setup delivery threads
        self.delivery_thread = threading.Thread(
            target=self._delivery_worker,
            daemon=True
        )
        self.delivery_thread.start()
        
        # Load existing notifications
        self._load_notifications()
        
        # Set up logger
        self.logger = logging.getLogger(__name__)
    
    def _load_notifications(self) -> None:
        """Load existing notifications from disk."""
        history_file = os.path.join(self.notification_dir, 'notification_history.json')
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r') as f:
                    data = json.load(f)
                
                for notification_data in data:
                    try:
                        notification = Notification.from_dict(notification_data)
                        self.notifications.append(notification)
                    except Exception as e:
                        self.logger.warning(f"Failed to load notification: {e}")
                
                self.logger.info(f"Loaded {len(self.notifications)} notifications from history")
            except Exception as e:
                self.logger.error(f"Failed to load notification history: {e}")
    
    def _save_notifications(self) -> None:
        """Save notifications to disk."""
        history_file = os.path.join(self.notification_dir, 'notification_history.json')
        try:
            # Get the newest notifications up to the history limit
            notifications_to_save = sorted(
                self.notifications,
                key=lambda n: n.timestamp,
                reverse=True
            )[:self.history_limit]
            
            # Convert to dictionaries
            data = [n.to_dict() for n in notifications_to_save]
            
            # Save to file
            with open(history_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.logger.debug(f"Saved {len(notifications_to_save)} notifications to history")
        except Exception as e:
            self.logger.error(f"Failed to save notification history: {e}")
    
    def _delivery_worker(self) -> None:
        """Worker thread for notification delivery."""
        while True:
            try:
                notification = self.notification_queue.get()
                self._deliver_notification(notification)
                self.notification_queue.task_done()
            except Exception as e:
                self.logger.error(f"Error in notification delivery worker: {e}")
    
    def _deliver_notification(self, notification: Notification) -> None:
        """
        Deliver a notification through its specified channels.
        
        Args:
            notification: Notification to deliver.
        """
        notification.delivery_attempts += 1
        
        try:
            # Process each channel
            for channel in notification.channels:
                try:
                    if channel == NotificationChannel.CONSOLE:
                        self._deliver_console(notification)
                    elif channel == NotificationChannel.DESKTOP:
                        self._deliver_desktop(notification)
                    elif channel == NotificationChannel.EMAIL:
                        self._deliver_email(notification)
                    elif channel == NotificationChannel.TELEGRAM:
                        self._deliver_telegram(notification)
                    elif channel == NotificationChannel.LOG:
                        self._deliver_log(notification)
                except Exception as e:
                    self.logger.error(f"Failed to deliver notification to {channel.name}: {e}")
            
            # Update notification status
            notification.status = NotificationStatus.DELIVERED
            notification.delivered_at = datetime.now()
            notification.delivery_error = None
            
            # Call registered callbacks
            self._call_callbacks(notification)
            
            # Save notification history
            self._save_notifications()
            
        except Exception as e:
            notification.status = NotificationStatus.FAILED
            notification.delivery_error = str(e)
            self.logger.error(f"Failed to deliver notification: {e}")
            
            # Retry delivery later if appropriate
            if notification.delivery_attempts < 3:
                # Exponential backoff
                retry_delay = 5 * (2 ** (notification.delivery_attempts - 1))
                
                def requeue():
                    self.notification_queue.put(notification)
                
                threading.Timer(retry_delay, requeue).start()
    
    def _deliver_console(self, notification: Notification) -> None:
        """
        Deliver a notification to the console.
        
        Args:
            notification: Notification to deliver.
        """
        # Use different colors based on level
        level_colors = {
            NotificationLevel.DEBUG: '\033[36m',  # Cyan
            NotificationLevel.INFO: '\033[32m',   # Green
            NotificationLevel.WARNING: '\033[33m', # Yellow
            NotificationLevel.ERROR: '\033[31m',  # Red
            NotificationLevel.CRITICAL: '\033[35m' # Magenta
        }
        
        reset_color = '\033[0m'
        level_color = level_colors.get(notification.level, '\033[0m')
        
        # Format the message
        timestamp = notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        message = (
            f"{level_color}[{notification.level.name}]{reset_color} "
            f"{timestamp} - {notification.source}: "
            f"{notification.title} - {notification.message}"
        )
        
        # Print to console
        print(message)
    
    def _deliver_desktop(self, notification: Notification) -> None:
        """
        Deliver a notification as a desktop notification.
        
        Args:
            notification: Notification to deliver.
        """
        # Check if desktop notifications are enabled in config
        if not self.config.get('notifications', {}).get('desktop', {}).get('enabled', True):
            return
        
        # Desktop notifications require additional libraries
        # This is a simplified implementation
        try:
            # Try to use platform-specific notification library
            import platform
            system = platform.system()
            
            if system == 'Darwin':  # macOS
                try:
                    # Use osascript for macOS
                    import subprocess
                    script = f'''
                    display notification "{notification.message}" with title "{notification.title}"
                    '''
                    subprocess.run(['osascript', '-e', script], check=False)
                    return
                except Exception:
                    pass
            
            elif system == 'Linux':
                try:
                    # Use notify-send for Linux
                    import subprocess
                    subprocess.run([
                        'notify-send',
                        notification.title,
                        notification.message
                    ], check=False)
                    return
                except Exception:
                    pass
            
            elif system == 'Windows':
                try:
                    # Use Windows 10 toast notifications
                    from win10toast import ToastNotifier
                    toaster = ToastNotifier()
                    toaster.show_toast(
                        notification.title,
                        notification.message,
                        duration=5,
                        threaded=True
                    )
                    return
                except ImportError:
                    pass
            
            # Fallback to console if no desktop notification is available
            self.logger.warning("Desktop notifications not available, falling back to console")
            self._deliver_console(notification)
            
        except Exception as e:
            self.logger.error(f"Failed to deliver desktop notification: {e}")
            # Fallback to console
            self._deliver_console(notification)
    
    def _deliver_email(self, notification: Notification) -> None:
        """
        Deliver a notification via email.
        
        Args:
            notification: Notification to deliver.
        """
        # Check if email notifications are enabled in config
        email_config = self.config.get('notifications', {}).get('email', {})
        if not email_config.get('enabled', False):
            return
        
        # Check for required config values
        smtp_server = email_config.get('smtp_server')
        smtp_port = email_config.get('smtp_port', 587)
        smtp_user = email_config.get('smtp_user')
        smtp_password = email_config.get('smtp_password')
        from_address = email_config.get('from_address')
        to_addresses = email_config.get('to_addresses', [])
        use_tls = email_config.get('use_tls', True)
        
        if not (smtp_server and smtp_user and smtp_password and from_address and to_addresses):
            self.logger.warning("Incomplete email configuration, skipping email notification")
            return
        
        try:
            # Create message
            msg = EmailMessage()
            msg['Subject'] = f"[{notification.level.name}] {notification.title}"
            msg['From'] = from_address
            msg['To'] = ', '.join(to_addresses)
            
            # Create email body with notification details
            body = f"""
Notification from {notification.source}
Level: {notification.level.name}
Time: {notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')}

{notification.message}

---
Additional Information:
"""
            
            # Add metadata if available
            for key, value in notification.metadata.items():
                body += f"{key}: {value}\n"
            
            msg.set_content(body)
            
            # Send the email
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                if use_tls:
                    server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
            
            self.logger.info(f"Sent email notification to {', '.join(to_addresses)}")
            
        except Exception as e:
            self.logger.error(f"Failed to send email notification: {e}")
            raise
    
    def _deliver_telegram(self, notification: Notification) -> None:
        """
        Deliver a notification via Telegram.
        
        Args:
            notification: Notification to deliver.
        """
        # Check if Telegram notifications are enabled in config
        telegram_config = self.config.get('notifications', {}).get('telegram', {})
        if not telegram_config.get('enabled', False):
            return
        
        # Check for required config values
        bot_token = telegram_config.get('bot_token')
        chat_id = telegram_config.get('chat_id')
        
        if not (bot_token and chat_id):
            self.logger.warning("Incomplete Telegram configuration, skipping Telegram notification")
            return
        
        try:
            # Use requests to send Telegram message
            import requests
            
            # Format message
            message = f"*{notification.level.name}*: {notification.title}\n\n{notification.message}"
            
            # Add metadata if available
            if notification.metadata:
                message += "\n\n*Additional Information:*\n"
                for key, value in notification.metadata.items():
                    message += f"{key}: {value}\n"
            
            # Send the message
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            
            self.logger.info(f"Sent Telegram notification to chat {chat_id}")
            
        except ImportError:
            self.logger.error("Requests module not available, skipping Telegram notification")
        except Exception as e:
            self.logger.error(f"Failed to send Telegram notification: {e}")
            raise
    
    def _deliver_log(self, notification: Notification) -> None:
        """
        Deliver a notification to the log system.
        
        Args:
            notification: Notification to deliver.
        """
        if not self.log_notifications:
            return
        
        # Map notification levels to logging levels
        level_map = {
            NotificationLevel.DEBUG: logging.DEBUG,
            NotificationLevel.INFO: logging.INFO,
            NotificationLevel.WARNING: logging.WARNING,
            NotificationLevel.ERROR: logging.ERROR,
            NotificationLevel.CRITICAL: logging.CRITICAL
        }
        
        # Get the appropriate logging level
        log_level = level_map.get(notification.level, logging.INFO)
        
        # Create a structured log message
        log_data = {
            'notification_id': notification.id,
            'title': notification.title,
            'source': notification.source,
            'metadata': notification.metadata
        }
        
        # Log the message
        self.logger.log(
            log_level,
            f"{notification.title}: {notification.message}",
            extra=log_data
        )
    
    def _call_callbacks(self, notification: Notification) -> None:
        """
        Call registered callbacks for a notification.
        
        Args:
            notification: Delivered notification.
        """
        # Call general callbacks
        for callback_id, callback in list(self.callbacks.items()):
            try:
                callback(notification)
            except Exception as e:
                self.logger.error(f"Error in notification callback {callback_id}: {e}")
        
        # Call level-specific callbacks
        for callback in self.level_callbacks.get(notification.level, []):
            try:
                callback(notification)
            except Exception as e:
                self.logger.error(f"Error in level callback for {notification.level.name}: {e}")
    
    def _check_rate_limit(self, key: str, limit: int, period: int = 60) -> bool:
        """
        Check if a notification should be rate-limited.
        
        Args:
            key: Rate limit key (typically source + message type).
            limit: Maximum number of notifications in the period.
            period: Time period in seconds.
            
        Returns:
            True if the notification should be allowed, False if rate-limited.
        """
        now = time.time()
        
        # Initialize rate limit entry if not exists
        if key not in self.rate_limits:
            self.rate_limits[key] = {
                'count': 0,
                'first_timestamp': now,
                'last_timestamp': now
            }
        
        # Reset count if period has passed
        entry = self.rate_limits[key]
        if now - entry['first_timestamp'] > period:
            entry['count'] = 0
            entry['first_timestamp'] = now
        
        # Check if limit exceeded
        if entry['count'] >= limit:
            return False
        
        # Update rate limit
        entry['count'] += 1
        entry['last_timestamp'] = now
        return True
    
    def send_notification(
        self,
        title: str,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        source: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
        channels: Optional[List[NotificationChannel]] = None,
        rate_limit_key: Optional[str] = None,
        rate_limit: int = 10,
        rate_limit_period: int = 60
    ) -> Optional[str]:
        """
        Send a new notification.
        
        Args:
            title: Notification title.
            message: Notification message.
            level: Notification severity level.
            source: Source of the notification.
            metadata: Additional metadata.
            channels: Delivery channels to use.
            rate_limit_key: Key for rate limiting. If None, no rate limiting is applied.
            rate_limit: Maximum number of notifications with the same key in the period.
            rate_limit_period: Time period for rate limiting in seconds.
            
        Returns:
            Notification ID if sent, None if rate-limited.
        """
        # Apply rate limiting if key provided
        if rate_limit_key:
            if not self._check_rate_limit(rate_limit_key, rate_limit, rate_limit_period):
                self.logger.debug(f"Rate limit exceeded for {rate_limit_key}, notification dropped")
                return None
        
        # Create notification
        notification = Notification(
            title=title,
            message=message,
            level=level,
            source=source,
            metadata=metadata,
            channels=channels
        )
        
        # Add to history
        self.notifications.append(notification)
        
        # Trim history if needed
        if len(self.notifications) > self.history_limit * 1.1:
            # Keep the newest notifications
            self.notifications = sorted(
                self.notifications,
                key=lambda n: n.timestamp,
                reverse=True
            )[:self.history_limit]
        
        # Queue for delivery
        self.notification_queue.put(notification)
        
        return notification.id
    
    def notify_info(
        self, 
        title: str, 
        message: str, 
        source: str = "system",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Send an info notification.
        
        Args:
            title: Notification title.
            message: Notification message.
            source: Source of the notification.
            metadata: Additional metadata.
            
        Returns:
            Notification ID if sent, None if rate-limited.
        """
        return self.send_notification(
            title=title,
            message=message,
            level=NotificationLevel.INFO,
            source=source,
            metadata=metadata
        )
    
    def notify_warning(
        self, 
        title: str, 
        message: str, 
        source: str = "system",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Send a warning notification.
        
        Args:
            title: Notification title.
            message: Notification message.
            source: Source of the notification.
            metadata: Additional metadata.
            
        Returns:
            Notification ID if sent, None if rate-limited.
        """
        return self.send_notification(
            title=title,
            message=message,
            level=NotificationLevel.WARNING,
            source=source,
            metadata=metadata
        )
    
    def notify_error(
        self, 
        title: str, 
        message: str, 
        source: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
        exception: Optional[Exception] = None
    ) -> Optional[str]:
        """
        Send an error notification.
        
        Args:
            title: Notification title.
            message: Notification message.
            source: Source of the notification.
            metadata: Additional metadata.
            exception: Exception that caused the error.
            
        Returns:
            Notification ID if sent, None if rate-limited.
        """
        # Add exception details to metadata
        meta = metadata or {}
        if exception:
            meta['exception_type'] = type(exception).__name__
            meta['exception_message'] = str(exception)
            meta['traceback'] = traceback.format_exc()
        
        return self.send_notification(
            title=title,
            message=message,
            level=NotificationLevel.ERROR,
            source=source,
            metadata=meta
        )
    
    def notify_critical(
        self, 
        title: str, 
        message: str, 
        source: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
        exception: Optional[Exception] = None
    ) -> Optional[str]:
        """
        Send a critical notification.
        
        Args:
            title: Notification title.
            message: Notification message.
            source: Source of the notification.
            metadata: Additional metadata.
            exception: Exception that caused the error.
            
        Returns:
            Notification ID if sent, None if rate-limited.
        """
        # Add exception details to metadata
        meta = metadata or {}
        if exception:
            meta['exception_type'] = type(exception).__name__
            meta['exception_message'] = str(exception)
            meta['traceback'] = traceback.format_exc()
        
        # Critical notifications are sent to all channels by default
        return self.send_notification(
            title=title,
            message=message,
            level=NotificationLevel.CRITICAL,
            source=source,
            metadata=meta,
            channels=[
                NotificationChannel.CONSOLE,
                NotificationChannel.DESKTOP,
                NotificationChannel.EMAIL,
                NotificationChannel.TELEGRAM,
                NotificationChannel.LOG
            ]
        )
    
    def register_callback(
        self, 
        callback: Callable[[Notification], None],
        callback_id: Optional[str] = None
    ) -> str:
        """
        Register a callback for notifications.
        
        Args:
            callback: Function to call when a notification is delivered.
            callback_id: Optional ID for the callback. Defaults to auto-generated ID.
            
        Returns:
            Callback ID.
        """
        callback_id = callback_id or f"callback_{id(callback)}"
        self.callbacks[callback_id] = callback
        return callback_id
    
    def unregister_callback(self, callback_id: str) -> bool:
        """
        Unregister a notification callback.
        
        Args:
            callback_id: ID of the callback to remove.
            
        Returns:
            True if the callback was removed, False if not found.
        """
        if callback_id in self.callbacks:
            del self.callbacks[callback_id]
            return True
        return False
    
    def register_level_callback(
        self, 
        level: NotificationLevel,
        callback: Callable[[Notification], None]
    ) -> None:
        """
        Register a callback for a specific notification level.
        
        Args:
            level: Notification level to register for.
            callback: Function to call when a notification of this level is delivered.
        """
        self.level_callbacks[level].append(callback)
    
    def unregister_level_callback(
        self, 
        level: NotificationLevel,
        callback: Callable[[Notification], None]
    ) -> bool:
        """
        Unregister a level-specific notification callback.
        
        Args:
            level: Notification level to unregister from.
            callback: Callback to remove.
            
        Returns:
            True if the callback was removed, False if not found.
        """
        if callback in self.level_callbacks[level]:
            self.level_callbacks[level].remove(callback)
            return True
        return False
    
    def get_notification(self, notification_id: str) -> Optional[Notification]:
        """
        Get a notification by ID.
        
        Args:
            notification_id: Notification ID.
            
        Returns:
            Notification if found, None otherwise.
        """
        for notification in self.notifications:
            if notification.id == notification_id:
                return notification
        return None
    
    def acknowledge_notification(self, notification_id: str) -> bool:
        """
        Mark a notification as acknowledged.
        
        Args:
            notification_id: Notification ID.
            
        Returns:
            True if the notification was acknowledged, False if not found.
        """
        notification = self.get_notification(notification_id)
        if notification:
            notification.status = NotificationStatus.ACKNOWLEDGED
            notification.acknowledged_at = datetime.now()
            self._save_notifications()
            return True
        return False
    
    def get_notifications(
        self, 
        level: Optional[NotificationLevel] = None,
        source: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        status: Optional[NotificationStatus] = None,
        limit: int = 100,
        offset: int = 0,
        include_acknowledged: bool = False
    ) -> List[Notification]:
        """
        Get notifications with optional filtering.
        
        Args:
            level: Filter by notification level.
            source: Filter by notification source.
            start_time: Filter by minimum timestamp.
            end_time: Filter by maximum timestamp.
            status: Filter by notification status.
            limit: Maximum number of notifications to return.
            offset: Offset for pagination.
            include_acknowledged: Whether to include acknowledged notifications.
            
        Returns:
            List of matching notifications.
        """
        # Apply filters
        filtered = self.notifications
        
        if level:
            filtered = [n for n in filtered if n.level == level]
        
        if source:
            filtered = [n for n in filtered if n.source == source]
        
        if start_time:
            filtered = [n for n in filtered if n.timestamp >= start_time]
        
        if end_time:
            filtered = [n for n in filtered if n.timestamp <= end_time]
        
        if status:
            filtered = [n for n in filtered if n.status == status]
        
        if not include_acknowledged:
            filtered = [n for n in filtered if n.status != NotificationStatus.ACKNOWLEDGED]
        
        # Sort by timestamp (newest first)
        filtered.sort(key=lambda n: n.timestamp, reverse=True)
        
        # Apply pagination
        return filtered[offset:offset+limit]
    
    def get_notification_count(
        self, 
        level: Optional[NotificationLevel] = None,
        source: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        status: Optional[NotificationStatus] = None,
        include_acknowledged: bool = False
    ) -> int:
        """
        Get the count of notifications with optional filtering.
        
        Args:
            level: Filter by notification level.
            source: Filter by notification source.
            start_time: Filter by minimum timestamp.
            end_time: Filter by maximum timestamp.
            status: Filter by notification status.
            include_acknowledged: Whether to include acknowledged notifications.
            
        Returns:
            Number of matching notifications.
        """
        # Apply filters
        filtered = self.notifications
        
        if level:
            filtered = [n for n in filtered if n.level == level]
        
        if source:
            filtered = [n for n in filtered if n.source == source]
        
        if start_time:
            filtered = [n for n in filtered if n.timestamp >= start_time]
        
        if end_time:
            filtered = [n for n in filtered if n.timestamp <= end_time]
        
        if status:
            filtered = [n for n in filtered if n.status == status]
        
        if not include_acknowledged:
            filtered = [n for n in filtered if n.status != NotificationStatus.ACKNOWLEDGED]
        
        return len(filtered)
    
    def clear_notifications(
        self, 
        older_than: Optional[datetime] = None,
        status: Optional[NotificationStatus] = NotificationStatus.ACKNOWLEDGED
    ) -> int:
        """
        Clear notifications from history.
        
        Args:
            older_than: Clear notifications older than this time.
            status: Only clear notifications with this status. Default is ACKNOWLEDGED.
            
        Returns:
            Number of notifications cleared.
        """
        original_count = len(self.notifications)
        
        if older_than and status:
            self.notifications = [
                n for n in self.notifications 
                if n.timestamp >= older_than or n.status != status
            ]
        elif older_than:
            self.notifications = [
                n for n in self.notifications 
                if n.timestamp >= older_than
            ]
        elif status:
            self.notifications = [
                n for n in self.notifications 
                if n.status != status
            ]
        
        cleared_count = original_count - len(self.notifications)
        
        # Save updated notifications
        if cleared_count > 0:
            self._save_notifications()
        
        return cleared_count
    
    def shutdown(self) -> None:
        """Clean up resources and save state."""
        # Process any remaining notifications in the queue
        remaining = 0
        try:
            while True:
                self.notification_queue.get_nowait()
                self.notification_queue.task_done()
                remaining += 1
        except queue.Empty:
            pass
        
        if remaining > 0:
            self.logger.warning(f"Discarded {remaining} pending notifications during shutdown")
        
        # Save notifications
        self._save_notifications()
        
        self.logger.info("NotificationManager shut down")

# Singleton instance
_notification_manager_instance = None

def get_notification_manager(
    config: Optional[Dict[str, Any]] = None
) -> NotificationManager:
    """
    Get or create the singleton NotificationManager instance.
    
    Args:
        config: Configuration dictionary.
        
    Returns:
        NotificationManager instance.
    """
    global _notification_manager_instance
    if _notification_manager_instance is None:
        _notification_manager_instance = NotificationManager(config=config)
    return _notification_manager_instance 