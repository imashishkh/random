#!/usr/bin/env python3
"""
Send Notification Script

This script provides a command-line interface to send notifications
using the Forex Trading Bot notification system.

Usage:
    python send_notification.py --level info --subject "Test Subject" --message "Test message"
    python send_notification.py --level error --subject "Error Alert" --message "System failure detected"
    python send_notification.py --level warning --subject "Warning" --message "Low disk space"
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Import notification manager
from src.notifications import NotificationManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Send a notification from the command line")
    
    parser.add_argument(
        "--level", 
        choices=["info", "warning", "error", "debug", "critical"],
        default="info",
        help="Notification level"
    )
    
    parser.add_argument(
        "--subject", 
        required=True,
        help="Notification subject/title"
    )
    
    parser.add_argument(
        "--message", 
        required=True,
        help="Notification message"
    )
    
    parser.add_argument(
        "--config", 
        default=None,
        help="Path to notification config file (default: config/notification_config.json)"
    )
    
    parser.add_argument(
        "--channels", 
        nargs="+",
        choices=["email", "slack"],
        help="Specific channels to use (default: all enabled channels)"
    )
    
    parser.add_argument(
        "--recipients", 
        nargs="+",
        help="Email recipients (overrides config defaults)"
    )
    
    return parser.parse_args()

def main():
    """Run the notification script."""
    args = parse_args()
    
    # Determine config path
    config_path = args.config
    if not config_path:
        config_path = os.path.join(project_root, "config", "notification_config.json")
    
    # Initialize notification manager
    try:
        notification_manager = NotificationManager(config_path=config_path)
    except FileNotFoundError:
        print(f"Error: Notification config file not found at {config_path}")
        print("You can create one using the template in docs/notifications.md")
        return 1
    except Exception as e:
        print(f"Error initializing notification system: {str(e)}")
        return 1
    
    # Send notification
    channels = args.channels
    
    # Determine which notification method to use based on level
    if args.level == "info":
        send_method = notification_manager.send_info
    elif args.level == "warning":
        send_method = notification_manager.send_warning
    elif args.level == "error":
        send_method = notification_manager.send_error
    else:
        # For other levels, use the generic method
        results = notification_manager.send_notification(
            level=args.level,
            subject=args.subject,
            message=args.message,
            email_recipients=args.recipients,
            channels=channels
        )
        print_results(results)
        return 0
    
    # Send notification using the appropriate method
    results = send_method(
        subject=args.subject,
        message=args.message
    )
    
    print_results(results)
    return 0

def print_results(results):
    """Print notification results in a user-friendly format."""
    if not results:
        print("No notifications were sent. Check your notification level settings.")
        return
    
    print("\nNotification Results:")
    print("---------------------")
    
    for channel, success in results.items():
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"{channel.capitalize()}: {status}")

if __name__ == "__main__":
    sys.exit(main()) 