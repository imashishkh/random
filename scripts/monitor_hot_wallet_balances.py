#!/usr/bin/env python3
"""
Hot Wallet Balance Monitor

This script monitors hot wallet balances and sends alerts when:
1. Balances are too low and need replenishment
2. Balances are too high (security risk) and should be moved to cold storage
3. Unusual balance changes that might indicate security issues

It's designed to be run as a scheduled task (e.g., via cron).
"""

import os
import sys
import argparse
import logging
import json
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Any, Tuple
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
from datetime import datetime, timedelta
import time

# Add project root to path for imports
script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
project_root = script_dir.parent
sys.path.append(str(project_root))

from dotenv import load_dotenv
from src.db import get_db_connection
from src.account.wallet import (
    get_wallet_by_address, get_wallet_balances, get_token_balance,
    get_bnb_balance, get_web3, BEP20_ABI
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/hot_wallet_monitor.log')
    ]
)
logger = logging.getLogger('hot_wallet_monitor')

# Default thresholds
DEFAULT_LOW_BNB_THRESHOLD = Decimal('0.1')  # BNB
DEFAULT_HIGH_BNB_THRESHOLD = Decimal('1.0')  # BNB
DEFAULT_LOW_TOKEN_THRESHOLD = Decimal('100')  # Tokens
DEFAULT_HIGH_TOKEN_THRESHOLD = Decimal('1000')  # Tokens

def get_hot_wallets() -> List[Dict[str, Any]]:
    """
    Get all hot wallets from the database.
    
    Returns:
        List of hot wallet data
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        query = """
        SELECT w.id, w.address, w.user_id, w.chain_id
        FROM wallets w
        WHERE w.wallet_type = 'hot'
        """
        
        cursor.execute(query)
        hot_wallets = cursor.fetchall()
        
        logger.info(f"Found {len(hot_wallets)} hot wallets")
        return hot_wallets
        
    except Exception as e:
        logger.error(f"Error getting hot wallets: {str(e)}")
        return []
    finally:
        conn.close()

def check_wallet_balances(
    wallets: List[Dict[str, Any]],
    low_bnb_threshold: Decimal,
    high_bnb_threshold: Decimal,
    low_token_threshold: Decimal,
    high_token_threshold: Decimal
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Check wallet balances and identify those with issues.
    
    Args:
        wallets: List of wallet data
        low_bnb_threshold: Threshold for low BNB balance
        high_bnb_threshold: Threshold for high BNB balance
        low_token_threshold: Threshold for low token balance
        high_token_threshold: Threshold for high token balance
    
    Returns:
        Tuple of (low_balance_wallets, high_balance_wallets, unusual_change_wallets)
    """
    low_balance_wallets = []
    high_balance_wallets = []
    unusual_change_wallets = []
    
    for wallet in wallets:
        wallet_id = wallet['id']
        address = wallet['address']
        chain_id = wallet['chain_id']
        
        try:
            # Get current balances
            bnb_balance = Decimal(str(get_bnb_balance(address, chain_id)))
            
            # Get balances from database for comparison
            balances = get_wallet_balances(wallet_id)
            
            # Check BNB balance
            if bnb_balance < low_bnb_threshold:
                low_balance_wallets.append({
                    'wallet_id': wallet_id,
                    'address': address,
                    'token': 'BNB',
                    'balance': bnb_balance,
                    'threshold': low_bnb_threshold
                })
            elif bnb_balance > high_bnb_threshold:
                high_balance_wallets.append({
                    'wallet_id': wallet_id,
                    'address': address,
                    'token': 'BNB',
                    'balance': bnb_balance,
                    'threshold': high_bnb_threshold
                })
            
            # Get token balances
            web3 = get_web3(chain_id)
            
            # Check for token balances by querying all tokens in the wallet_balances table
            query = """
            SELECT token_address, token_symbol, balance 
            FROM wallet_balances 
            WHERE wallet_id = %s AND token_address IS NOT NULL
            """
            
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(query, (wallet_id,))
                token_records = cursor.fetchall()
                
                for token in token_records:
                    token_address = token['token_address']
                    token_symbol = token['token_symbol']
                    stored_balance = Decimal(token['balance'])
                    
                    # Get current token balance
                    current_balance = Decimal(str(get_token_balance(
                        address, token_address, chain_id
                    )))
                    
                    # Check for low balance
                    if current_balance < low_token_threshold:
                        low_balance_wallets.append({
                            'wallet_id': wallet_id,
                            'address': address,
                            'token': token_symbol,
                            'token_address': token_address,
                            'balance': current_balance,
                            'threshold': low_token_threshold
                        })
                    
                    # Check for high balance
                    elif current_balance > high_token_threshold:
                        high_balance_wallets.append({
                            'wallet_id': wallet_id,
                            'address': address,
                            'token': token_symbol,
                            'token_address': token_address,
                            'balance': current_balance,
                            'threshold': high_token_threshold
                        })
                    
                    # Check for unusual balance changes (more than 20% change)
                    if stored_balance > 0:
                        change_percent = abs(current_balance - stored_balance) / stored_balance * 100
                        if change_percent > 20:  # More than 20% change
                            unusual_change_wallets.append({
                                'wallet_id': wallet_id,
                                'address': address,
                                'token': token_symbol,
                                'token_address': token_address,
                                'previous_balance': stored_balance,
                                'current_balance': current_balance,
                                'change_percent': change_percent
                            })
                            
                    # Update the balance in database
                    update_query = """
                    UPDATE wallet_balances 
                    SET balance = %s, last_updated = NOW() 
                    WHERE wallet_id = %s AND token_address = %s
                    """
                    cursor.execute(update_query, (str(current_balance), wallet_id, token_address))
                    conn.commit()
                
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Error checking balances for wallet {address}: {str(e)}")
    
    return low_balance_wallets, high_balance_wallets, unusual_change_wallets

def send_alert_email(
    low_balance_wallets: List[Dict[str, Any]],
    high_balance_wallets: List[Dict[str, Any]],
    unusual_change_wallets: List[Dict[str, Any]]
) -> bool:
    """
    Send email alert about wallet balance issues.
    
    Args:
        low_balance_wallets: List of wallets with low balance
        high_balance_wallets: List of wallets with high balance
        unusual_change_wallets: List of wallets with unusual balance changes
    
    Returns:
        True if alert was sent successfully, False otherwise
    """
    # Check if there are any issues to report
    if not (low_balance_wallets or high_balance_wallets or unusual_change_wallets):
        logger.info("No issues to report")
        return True
    
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
        msg['Subject'] = "ALERT: Hot Wallet Balance Issues"
        
        # Create email body
        body = """
        <html>
        <body>
            <h2>Hot Wallet Balance Monitor Alert</h2>
        """
        
        # Add low balance wallets
        if low_balance_wallets:
            body += f"""
            <h3>🔴 Low Balance Wallets ({len(low_balance_wallets)})</h3>
            <p>The following wallets have balances below threshold and need replenishment:</p>
            <table border="1" cellpadding="5">
                <tr>
                    <th>Wallet ID</th>
                    <th>Address</th>
                    <th>Token</th>
                    <th>Balance</th>
                    <th>Threshold</th>
                </tr>
            """
            
            for wallet in low_balance_wallets:
                body += f"""
                <tr>
                    <td>{wallet['wallet_id']}</td>
                    <td>{wallet['address']}</td>
                    <td>{wallet['token']}</td>
                    <td>{wallet['balance']}</td>
                    <td>{wallet['threshold']}</td>
                </tr>
                """
                
            body += "</table>"
        
        # Add high balance wallets
        if high_balance_wallets:
            body += f"""
            <h3>🟠 High Balance Wallets ({len(high_balance_wallets)})</h3>
            <p>The following wallets have balances above threshold and funds should be moved to cold storage:</p>
            <table border="1" cellpadding="5">
                <tr>
                    <th>Wallet ID</th>
                    <th>Address</th>
                    <th>Token</th>
                    <th>Balance</th>
                    <th>Threshold</th>
                </tr>
            """
            
            for wallet in high_balance_wallets:
                body += f"""
                <tr>
                    <td>{wallet['wallet_id']}</td>
                    <td>{wallet['address']}</td>
                    <td>{wallet['token']}</td>
                    <td>{wallet['balance']}</td>
                    <td>{wallet['threshold']}</td>
                </tr>
                """
                
            body += "</table>"
        
        # Add unusual change wallets
        if unusual_change_wallets:
            body += f"""
            <h3>⚠️ Unusual Balance Changes ({len(unusual_change_wallets)})</h3>
            <p>The following wallets have unusual balance changes that should be investigated:</p>
            <table border="1" cellpadding="5">
                <tr>
                    <th>Wallet ID</th>
                    <th>Address</th>
                    <th>Token</th>
                    <th>Previous Balance</th>
                    <th>Current Balance</th>
                    <th>Change %</th>
                </tr>
            """
            
            for wallet in unusual_change_wallets:
                body += f"""
                <tr>
                    <td>{wallet['wallet_id']}</td>
                    <td>{wallet['address']}</td>
                    <td>{wallet['token']}</td>
                    <td>{wallet['previous_balance']}</td>
                    <td>{wallet['current_balance']}</td>
                    <td>{wallet['change_percent']:.2f}%</td>
                </tr>
                """
                
            body += "</table>"
            
        body += """
            <p>Please take appropriate action based on these alerts.</p>
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
        
        logger.info(f"Alert email sent to {admin_email}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending email alert: {str(e)}")
        return False

def main():
    """Main function to monitor hot wallet balances"""
    parser = argparse.ArgumentParser(description='Monitor hot wallet balances')
    parser.add_argument('--low-bnb', type=float, 
                        default=float(os.getenv('LOW_BNB_THRESHOLD', DEFAULT_LOW_BNB_THRESHOLD)),
                        help=f'Threshold for low BNB balance (default: {DEFAULT_LOW_BNB_THRESHOLD})')
    parser.add_argument('--high-bnb', type=float, 
                        default=float(os.getenv('HIGH_BNB_THRESHOLD', DEFAULT_HIGH_BNB_THRESHOLD)),
                        help=f'Threshold for high BNB balance (default: {DEFAULT_HIGH_BNB_THRESHOLD})')
    parser.add_argument('--low-token', type=float, 
                        default=float(os.getenv('LOW_TOKEN_THRESHOLD', DEFAULT_LOW_TOKEN_THRESHOLD)),
                        help=f'Threshold for low token balance (default: {DEFAULT_LOW_TOKEN_THRESHOLD})')
    parser.add_argument('--high-token', type=float, 
                        default=float(os.getenv('HIGH_TOKEN_THRESHOLD', DEFAULT_HIGH_TOKEN_THRESHOLD)),
                        help=f'Threshold for high token balance (default: {DEFAULT_HIGH_TOKEN_THRESHOLD})')
    parser.add_argument('--no-alert', action='store_true',
                        help='Do not send alert emails')
    args = parser.parse_args()
    
    # Convert thresholds to Decimal
    low_bnb_threshold = Decimal(str(args.low_bnb))
    high_bnb_threshold = Decimal(str(args.high_bnb))
    low_token_threshold = Decimal(str(args.low_token))
    high_token_threshold = Decimal(str(args.high_token))
    
    logger.info("Starting hot wallet balance monitor")
    logger.info(f"Thresholds - Low BNB: {low_bnb_threshold}, High BNB: {high_bnb_threshold}")
    logger.info(f"Thresholds - Low Token: {low_token_threshold}, High Token: {high_token_threshold}")
    
    # Get hot wallets
    hot_wallets = get_hot_wallets()
    
    if not hot_wallets:
        logger.warning("No hot wallets found")
        return
    
    # Check balances
    low_balance_wallets, high_balance_wallets, unusual_change_wallets = check_wallet_balances(
        hot_wallets, low_bnb_threshold, high_bnb_threshold, low_token_threshold, high_token_threshold
    )
    
    # Log findings
    if low_balance_wallets:
        logger.warning(f"Found {len(low_balance_wallets)} wallets with low balance")
        for wallet in low_balance_wallets:
            logger.warning(f"Low balance - Wallet {wallet['address']}: {wallet['balance']} {wallet['token']}")
    
    if high_balance_wallets:
        logger.warning(f"Found {len(high_balance_wallets)} wallets with high balance")
        for wallet in high_balance_wallets:
            logger.warning(f"High balance - Wallet {wallet['address']}: {wallet['balance']} {wallet['token']}")
    
    if unusual_change_wallets:
        logger.warning(f"Found {len(unusual_change_wallets)} wallets with unusual balance changes")
        for wallet in unusual_change_wallets:
            logger.warning(
                f"Unusual change - Wallet {wallet['address']}: {wallet['token']} "
                f"changed from {wallet['previous_balance']} to {wallet['current_balance']} "
                f"({wallet['change_percent']:.2f}%)"
            )
    
    # Send alert if needed and not disabled
    if not args.no_alert and (low_balance_wallets or high_balance_wallets or unusual_change_wallets):
        send_alert_email(low_balance_wallets, high_balance_wallets, unusual_change_wallets)
    else:
        logger.info("No alerts sent")
    
    logger.info("Hot wallet balance monitor completed")

if __name__ == "__main__":
    main() 