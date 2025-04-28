"""
Transaction Notification Module

This module provides notification functionality for transaction status updates,
supporting multiple notification channels (email, in-app, webhook).
"""

import os
import json
import logging
import smtplib
import requests
from typing import Dict, Any, List, Optional, Union
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from jinja2 import Template
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('transaction_notification')

# Load environment variables
load_dotenv()

# Email configuration
SMTP_SERVER = os.getenv('SMTP_SERVER', '')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
EMAIL_FROM = os.getenv('EMAIL_FROM', 'noreply@example.com')
EMAIL_ENABLED = os.getenv('EMAIL_NOTIFICATIONS_ENABLED', 'true').lower() == 'true'

# Webhook configuration
WEBHOOK_URL = os.getenv('NOTIFICATION_WEBHOOK_URL', '')
WEBHOOK_ENABLED = os.getenv('WEBHOOK_NOTIFICATIONS_ENABLED', 'false').lower() == 'true'

# Templates directory
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')

class NotificationType:
    """Constants for notification types"""
    TX_STATUS_CHANGE = "transaction_status_change"
    TX_CONFIRMED = "transaction_confirmed"
    TX_FAILED = "transaction_failed"
    DEPOSIT_RECEIVED = "deposit_received"
    WITHDRAWAL_PROCESSED = "withdrawal_processed"
    WITHDRAWAL_APPROVED = "withdrawal_approved"
    WITHDRAWAL_REJECTED = "withdrawal_rejected"

class TransactionNotifier:
    """
    Handles notifications for transaction status updates through multiple channels.
    
    Supports:
    - Email notifications
    - In-app notifications (stored in database)
    - Webhook notifications to external systems
    """
    
    def __init__(self, db_connection=None):
        """
        Initialize the transaction notifier
        
        Args:
            db_connection: Database connection for in-app notifications storage
        """
        self.db = db_connection
        
        # Set up notification channels
        self.channels = []
        
        if EMAIL_ENABLED:
            self.channels.append('email')
            
        if WEBHOOK_ENABLED:
            self.channels.append('webhook')
            
        if self.db:
            self.channels.append('in_app')
            
        logger.info(f"Initialized transaction notifier with channels: {self.channels}")
    
    def notify(self, 
               user_id: int, 
               notification_type: str, 
               data: Dict[str, Any], 
               channels: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Send notification to a user through specified channels
        
        Args:
            user_id: ID of the user to notify
            notification_type: Type of notification (use NotificationType constants)
            data: Data to include in the notification
            channels: Specific channels to use (defaults to all enabled channels)
            
        Returns:
            Results of notification attempts by channel
        """
        if channels is None:
            channels = self.channels
            
        results = {}
        timestamp = datetime.now().isoformat()
        
        # Prepare notification data
        notification_data = {
            'type': notification_type,
            'user_id': user_id,
            'timestamp': timestamp,
            'data': data
        }
        
        # Send through each requested channel
        for channel in channels:
            if channel not in self.channels:
                results[channel] = {
                    'success': False,
                    'error': f"Channel {channel} not enabled"
                }
                continue
                
            try:
                if channel == 'email':
                    result = self._send_email_notification(user_id, notification_type, data)
                elif channel == 'webhook':
                    result = self._send_webhook_notification(notification_data)
                elif channel == 'in_app':
                    result = self._store_in_app_notification(user_id, notification_type, data)
                else:
                    result = {
                        'success': False,
                        'error': f"Unknown channel: {channel}"
                    }
                    
                results[channel] = result
                
            except Exception as e:
                logger.error(f"Error sending {notification_type} notification to user {user_id} via {channel}: {str(e)}")
                results[channel] = {
                    'success': False,
                    'error': str(e)
                }
                
        return results
    
    def notify_transaction_status_change(self, 
                                        user_id: int, 
                                        tx_hash: str, 
                                        old_status: str, 
                                        new_status: str, 
                                        tx_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send notification for transaction status change
        
        Args:
            user_id: User ID
            tx_hash: Transaction hash
            old_status: Previous transaction status
            new_status: New transaction status
            tx_data: Transaction data (amount, currency, etc.)
            
        Returns:
            Results of notification attempts
        """
        data = {
            'tx_hash': tx_hash,
            'old_status': old_status,
            'new_status': new_status,
            'tx_data': tx_data,
            'timestamp': datetime.now().isoformat()
        }
        
        # Choose proper notification type based on status change
        if new_status.lower() in ['confirmed', 'completed']:
            notification_type = NotificationType.TX_CONFIRMED
        elif new_status.lower() in ['failed', 'rejected']:
            notification_type = NotificationType.TX_FAILED
        else:
            notification_type = NotificationType.TX_STATUS_CHANGE
            
        return self.notify(user_id, notification_type, data)
    
    def notify_deposit_received(self, 
                               user_id: int, 
                               amount: float, 
                               currency: str, 
                               tx_hash: str,
                               confirmations: int) -> Dict[str, Any]:
        """
        Send notification for deposit received
        
        Args:
            user_id: User ID
            amount: Deposit amount
            currency: Currency code
            tx_hash: Transaction hash
            confirmations: Number of confirmations
            
        Returns:
            Results of notification attempts
        """
        data = {
            'tx_hash': tx_hash,
            'amount': amount,
            'currency': currency,
            'confirmations': confirmations,
            'timestamp': datetime.now().isoformat()
        }
        
        return self.notify(user_id, NotificationType.DEPOSIT_RECEIVED, data)
    
    def notify_withdrawal_status(self, 
                                user_id: int, 
                                withdrawal_id: int, 
                                status: str, 
                                amount: float,
                                currency: str, 
                                tx_hash: Optional[str] = None) -> Dict[str, Any]:
        """
        Send notification for withdrawal status change
        
        Args:
            user_id: User ID
            withdrawal_id: Withdrawal request ID
            status: New status (approved, rejected, processed)
            amount: Withdrawal amount
            currency: Currency code
            tx_hash: Transaction hash (if processed)
            
        Returns:
            Results of notification attempts
        """
        data = {
            'withdrawal_id': withdrawal_id,
            'status': status,
            'amount': amount,
            'currency': currency,
            'timestamp': datetime.now().isoformat()
        }
        
        if tx_hash:
            data['tx_hash'] = tx_hash
            
        # Choose notification type based on status
        if status.lower() == 'approved':
            notification_type = NotificationType.WITHDRAWAL_APPROVED
        elif status.lower() == 'rejected':
            notification_type = NotificationType.WITHDRAWAL_REJECTED
        else:
            notification_type = NotificationType.WITHDRAWAL_PROCESSED
            
        return self.notify(user_id, notification_type, data)
    
    def _send_email_notification(self, 
                                user_id: int, 
                                notification_type: str, 
                                data: Dict[str, Any]) -> Dict[str, bool]:
        """
        Send email notification
        
        Args:
            user_id: User ID
            notification_type: Type of notification
            data: Notification data
            
        Returns:
            Result of email sending attempt
        """
        if not EMAIL_ENABLED or not SMTP_SERVER:
            return {
                'success': False,
                'error': "Email notifications not configured"
            }
            
        try:
            # Get user email from database
            user_email = self._get_user_email(user_id)
            if not user_email:
                return {
                    'success': False,
                    'error': f"Email address not found for user {user_id}"
                }
                
            # Load email template based on notification type
            subject, html_content = self._render_email_template(notification_type, data)
            
            # Create email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = EMAIL_FROM
            msg['To'] = user_email
            
            # Attach HTML content
            msg.attach(MIMEText(html_content, 'html'))
            
            # Send email
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
                
            logger.info(f"Sent email notification to user {user_id} ({user_email}): {notification_type}")
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Error sending email notification: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _render_email_template(self, notification_type: str, data: Dict[str, Any]) -> tuple:
        """
        Render email template for notification
        
        Args:
            notification_type: Type of notification
            data: Notification data
            
        Returns:
            Tuple of (subject, html_content)
        """
        # Map notification types to template files
        template_mapping = {
            NotificationType.TX_STATUS_CHANGE: 'transaction_status_change.html',
            NotificationType.TX_CONFIRMED: 'transaction_confirmed.html',
            NotificationType.TX_FAILED: 'transaction_failed.html',
            NotificationType.DEPOSIT_RECEIVED: 'deposit_received.html',
            NotificationType.WITHDRAWAL_PROCESSED: 'withdrawal_processed.html',
            NotificationType.WITHDRAWAL_APPROVED: 'withdrawal_approved.html',
            NotificationType.WITHDRAWAL_REJECTED: 'withdrawal_rejected.html'
        }
        
        # Set default template if type not found
        template_file = template_mapping.get(notification_type, 'default_notification.html')
        template_path = os.path.join(TEMPLATE_DIR, 'email', template_file)
        
        # Check if template exists, use default if not
        if not os.path.exists(template_path):
            logger.warning(f"Email template {template_path} not found, using default")
            template_path = os.path.join(TEMPLATE_DIR, 'email', 'default_notification.html')
            
        # Fallback to simple string template if file not found
        if not os.path.exists(template_path):
            logger.warning("Default email template not found, using built-in template")
            
            # Simple built-in template for common notifications
            if notification_type == NotificationType.TX_CONFIRMED:
                subject = f"Transaction Confirmed"
                html_template = """
                <h2>Transaction Confirmed</h2>
                <p>Your transaction with hash {{ tx_data.tx_hash }} has been confirmed.</p>
                <p>Amount: {{ tx_data.amount }} {{ tx_data.currency }}</p>
                <p>Time: {{ timestamp }}</p>
                """
            elif notification_type == NotificationType.DEPOSIT_RECEIVED:
                subject = f"Deposit Received"
                html_template = """
                <h2>Deposit Received</h2>
                <p>Your account has been credited with {{ amount }} {{ currency }}.</p>
                <p>Transaction hash: {{ tx_hash }}</p>
                <p>Confirmations: {{ confirmations }}</p>
                <p>Time: {{ timestamp }}</p>
                """
            elif notification_type == NotificationType.WITHDRAWAL_PROCESSED:
                subject = f"Withdrawal Processed"
                html_template = """
                <h2>Withdrawal Processed</h2>
                <p>Your withdrawal request #{{ withdrawal_id }} has been processed.</p>
                <p>Amount: {{ amount }} {{ currency }}</p>
                <p>Transaction hash: {{ tx_hash }}</p>
                <p>Time: {{ timestamp }}</p>
                """
            else:
                subject = f"Transaction Status Update"
                html_template = """
                <h2>Transaction Status Update</h2>
                <p>Your transaction status has been updated.</p>
                <p>Details: {{ data }}</p>
                <p>Time: {{ timestamp }}</p>
                """
        else:
            # Read template from file
            with open(template_path, 'r') as f:
                html_template = f.read()
                
            # Set subject based on notification type
            if notification_type == NotificationType.TX_CONFIRMED:
                subject = "Transaction Confirmed"
            elif notification_type == NotificationType.TX_FAILED:
                subject = "Transaction Failed"
            elif notification_type == NotificationType.DEPOSIT_RECEIVED:
                subject = "Deposit Received"
            elif notification_type == NotificationType.WITHDRAWAL_PROCESSED:
                subject = "Withdrawal Processed"
            elif notification_type == NotificationType.WITHDRAWAL_APPROVED:
                subject = "Withdrawal Approved"
            elif notification_type == NotificationType.WITHDRAWAL_REJECTED:
                subject = "Withdrawal Rejected"
            else:
                subject = "Transaction Status Update"
        
        # Render template with data
        template = Template(html_template)
        html_content = template.render(**data)
        
        return subject, html_content
    
    def _send_webhook_notification(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send webhook notification to external system
        
        Args:
            data: Notification data
            
        Returns:
            Result of webhook sending attempt
        """
        if not WEBHOOK_ENABLED or not WEBHOOK_URL:
            return {
                'success': False,
                'error': "Webhook notifications not configured"
            }
            
        try:
            # Add timestamp if not present
            if 'timestamp' not in data:
                data['timestamp'] = datetime.now().isoformat()
                
            # Send webhook request
            response = requests.post(
                WEBHOOK_URL,
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            # Check response
            response.raise_for_status()
            
            logger.info(f"Sent webhook notification: {data['type']} for user {data['user_id']}")
            return {
                'success': True,
                'status_code': response.status_code
            }
            
        except requests.RequestException as e:
            logger.error(f"Error sending webhook notification: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _store_in_app_notification(self, 
                                 user_id: int, 
                                 notification_type: str, 
                                 data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Store in-app notification in database
        
        Args:
            user_id: User ID
            notification_type: Type of notification
            data: Notification data
            
        Returns:
            Result of database storage attempt
        """
        if not self.db:
            return {
                'success': False,
                'error': "Database connection not available for in-app notifications"
            }
            
        try:
            # Prepare notification record
            notification = {
                'user_id': user_id,
                'type': notification_type,
                'data': json.dumps(data),
                'is_read': False,
                'created_at': datetime.now().isoformat()
            }
            
            # Store in database
            cursor = self.db.cursor()
            cursor.execute(
                """
                INSERT INTO user_notifications 
                (user_id, type, data, is_read, created_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    notification['user_id'],
                    notification['type'],
                    notification['data'],
                    notification['is_read'],
                    notification['created_at']
                )
            )
            
            notification_id = cursor.fetchone()[0]
            self.db.commit()
            
            logger.info(f"Stored in-app notification {notification_id} for user {user_id}: {notification_type}")
            return {
                'success': True,
                'notification_id': notification_id
            }
            
        except Exception as e:
            logger.error(f"Error storing in-app notification: {str(e)}")
            if self.db:
                self.db.rollback()
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_user_email(self, user_id: int) -> Optional[str]:
        """
        Get user email from database
        
        Args:
            user_id: User ID
            
        Returns:
            User email address or None if not found
        """
        if not self.db:
            return None
            
        try:
            cursor = self.db.cursor()
            cursor.execute(
                "SELECT email FROM users WHERE id = %s",
                (user_id,)
            )
            result = cursor.fetchone()
            
            if result:
                return result[0]
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving user email: {str(e)}")
            return None

# Helper functions

def get_notifier(db_connection=None) -> TransactionNotifier:
    """
    Get a configured transaction notifier instance
    
    Args:
        db_connection: Optional database connection
        
    Returns:
        TransactionNotifier instance
    """
    return TransactionNotifier(db_connection) 