#!/usr/bin/env python3
"""
Check Withdrawal Approvals Script

This script checks for stale withdrawal approval requests that have been pending
for longer than a specified time period and sends notifications if required.
"""

import os
import sys
import argparse
import logging
import datetime
from pathlib import Path
from typing import List, Dict, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# Add the parent directory to the path so we can import our modules
script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
project_root = script_dir.parent
sys.path.append(str(project_root))

# Import our modules
from dotenv import load_dotenv
from src.db import get_db_connection
from src.account.wallet import get_pending_withdrawal_approvals

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('withdrawal_approvals_check')

def get_stale_approvals(days: int) -> List[Dict[Any, Any]]:
    """
    Get withdrawal approval requests that have been pending for longer than the specified days.
    
    Args:
        days: Number of days to consider an approval request stale
    
    Returns:
        List of stale withdrawal approval requests
    """
    conn = get_db_connection()
    try:
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        
        # Get all pending withdrawal approvals
        all_pending = get_pending_withdrawal_approvals(conn)
        
        # Filter for those older than cutoff date
        stale_approvals = [
            approval for approval in all_pending 
            if approval['created_at'] < cutoff_date
        ]
        
        logger.info(f"Found {len(stale_approvals)} stale withdrawal approval requests (older than {days} days)")
        return stale_approvals
        
    except Exception as e:
        logger.error(f"Error getting stale withdrawal approvals: {str(e)}")
        return []
    finally:
        conn.close()

def send_email_notification(stale_approvals: List[Dict[Any, Any]]) -> bool:
    """
    Send email notification about stale withdrawal approvals.
    
    Args:
        stale_approvals: List of stale withdrawal approvals
    
    Returns:
        True if notification was sent successfully, False otherwise
    """
    smtp_server = os.getenv('SMTP_SERVER')
    smtp_port = os.getenv('SMTP_PORT', '587')
    smtp_user = os.getenv('SMTP_USER')
    smtp_password = os.getenv('SMTP_PASSWORD')
    admin_email = os.getenv('ADMIN_EMAIL')
    
    # Check if email configuration is available
    if not all([smtp_server, smtp_port, smtp_user, smtp_password, admin_email]):
        logger.error("Email configuration not complete. Check environment variables.")
        return False
    
    try:
        # Create email message
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = admin_email
        msg['Subject'] = f"ALERT: {len(stale_approvals)} Stale Withdrawal Approvals"
        
        # Create email body
        body = f"""
        <html>
        <body>
            <h2>Stale Withdrawal Approval Requests</h2>
            <p>The following withdrawal approval requests have been pending for too long:</p>
            <table border="1" cellpadding="5">
                <tr>
                    <th>ID</th>
                    <th>User ID</th>
                    <th>Amount</th>
                    <th>Wallet Address</th>
                    <th>Created</th>
                    <th>Days Pending</th>
                </tr>
        """
        
        for approval in stale_approvals:
            days_pending = (datetime.datetime.now() - approval['created_at']).days
            body += f"""
                <tr>
                    <td>{approval['id']}</td>
                    <td>{approval['user_id']}</td>
                    <td>{approval['amount']}</td>
                    <td>{approval['wallet_address']}</td>
                    <td>{approval['created_at'].strftime('%Y-%m-%d %H:%M:%S')}</td>
                    <td>{days_pending}</td>
                </tr>
            """
            
        body += """
            </table>
            <p>Please review these requests as soon as possible.</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        # Send email
        server = smtplib.SMTP(smtp_server, int(smtp_port))
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Notification email sent to {admin_email}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending email notification: {str(e)}")
        return False

def main():
    """Main function to check for stale withdrawal approvals"""
    parser = argparse.ArgumentParser(description='Check for stale withdrawal approvals')
    parser.add_argument('--days', type=int, default=3,
                        help='Number of days after which an approval is considered stale (default: 3)')
    parser.add_argument('--notify', action='store_true',
                        help='Send email notification if stale approvals are found')
    args = parser.parse_args()
    
    logger.info(f"Checking for withdrawal approvals older than {args.days} days")
    
    # Get stale approvals
    stale_approvals = get_stale_approvals(args.days)
    
    # Output findings
    if stale_approvals:
        logger.warning(f"Found {len(stale_approvals)} stale withdrawal approvals")
        
        # Print details to console
        for approval in stale_approvals:
            logger.info(f"Approval ID: {approval['id']}, User: {approval['user_id']}, "
                      f"Amount: {approval['amount']}, Created: {approval['created_at']}")
        
        # Send notification if requested
        if args.notify:
            send_email_notification(stale_approvals)
    else:
        logger.info("No stale withdrawal approvals found")

if __name__ == "__main__":
    main() 