"""
Balance Reconciliation Service

This module provides services for reconciling balances between on-chain data,
internal database records, and Binance exchange balances.
"""

import os
import json
import logging
import datetime
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal

from web3 import Web3

from ..db.connection import get_db_connection
from ..exchange.binance import BinanceClient
from .wallet import get_wallet, get_wallet_by_id, get_bnb_balance, get_token_balance
from .reconciliation import AccountingSystem, get_accounting_system

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('reconciliation_service')


class DiscrepancyAlertService:
    """
    Service for alerting on significant balance discrepancies.
    """
    
    def __init__(self, email_enabled=True, slack_enabled=False):
        """
        Initialize the discrepancy alert service.
        
        Args:
            email_enabled: Whether to send email alerts
            slack_enabled: Whether to send Slack alerts
        """
        self.email_enabled = email_enabled and os.getenv('EMAIL_NOTIFICATIONS_ENABLED', 'true').lower() == 'true'
        self.slack_enabled = slack_enabled and os.getenv('SLACK_NOTIFICATIONS_ENABLED', 'false').lower() == 'true'
        
        # Email settings
        self.smtp_server = os.getenv('SMTP_SERVER')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.email_from = os.getenv('EMAIL_FROM', 'alerts@example.com')
        self.admin_emails = os.getenv('ADMIN_EMAILS', '').split(',')
        
        # Slack settings
        self.slack_webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    
    def send_discrepancy_alert(self, wallet_id, user_id, token_symbol, db_balance, 
                              chain_balance, binance_balance, chain_discrepancy, 
                              exchange_discrepancy):
        """
        Send alert for a significant balance discrepancy.
        
        Args:
            wallet_id: Wallet ID
            user_id: User ID
            token_symbol: Token symbol
            db_balance: Database balance
            chain_balance: On-chain balance
            binance_balance: Binance balance
            chain_discrepancy: Discrepancy between db and chain balances
            exchange_discrepancy: Discrepancy between db and exchange balances
            
        Returns:
            Dict with alert status
        """
        # Create alert message
        alert_subject = f"Balance Discrepancy Alert: Wallet {wallet_id}, {token_symbol}"
        
        alert_message = f"""
        Balance Discrepancy Detected
        ---------------------------
        Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        Wallet ID: {wallet_id}
        User ID: {user_id}
        Token: {token_symbol}
        
        Balances:
        - Database: {db_balance}
        - Blockchain: {chain_balance}
        - Binance: {binance_balance}
        
        Discrepancies:
        - Database vs Blockchain: {chain_discrepancy}
        - Database vs Binance: {exchange_discrepancy}
        
        Please investigate this discrepancy and take appropriate action.
        """
        
        results = {
            'email_sent': False,
            'slack_sent': False
        }
        
        # Send email alert
        if self.email_enabled:
            import smtplib
            from email.mime.text import MIMEText
            
            if not self.smtp_server or not self.smtp_username or not self.smtp_password or not self.admin_emails:
                logger.warning("Email notifications not properly configured")
            else:
                try:
                    # Create message
                    email_message = MIMEText(alert_message)
                    email_message['Subject'] = alert_subject
                    email_message['From'] = self.email_from
                    email_message['To'] = ', '.join(self.admin_emails)
                    
                    # Send email
                    with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                        server.starttls()
                        server.login(self.smtp_username, self.smtp_password)
                        server.send_message(email_message)
                    
                    logger.info(f"Sent email alert: {alert_subject}")
                    results['email_sent'] = True
                    
                except Exception as e:
                    logger.error(f"Error sending email alert: {str(e)}")
        
        # Send Slack alert
        if self.slack_enabled:
            import requests
            
            if not self.slack_webhook_url:
                logger.warning("Slack notifications not properly configured")
            else:
                try:
                    # Format message for Slack
                    slack_message = {
                        'text': f"*{alert_subject}*\n```{alert_message}```"
                    }
                    
                    # Send to Slack
                    response = requests.post(
                        self.slack_webhook_url,
                        json=slack_message,
                        headers={'Content-Type': 'application/json'}
                    )
                    
                    if response.status_code == 200:
                        logger.info(f"Sent Slack alert: {alert_subject}")
                        results['slack_sent'] = True
                    else:
                        logger.error(f"Error sending Slack alert: {response.status_code} {response.text}")
                        
                except Exception as e:
                    logger.error(f"Error sending Slack alert: {str(e)}")
        
        return results


class BalanceReconciliationService:
    """
    Service for reconciling balances between on-chain data, internal records, and Binance.
    """
    
    def __init__(self, db_connection=None, discrepancy_threshold=0.00001):
        """
        Initialize the balance reconciliation service.
        
        Args:
            db_connection: Database connection object
            discrepancy_threshold: Threshold for determining significant discrepancies
        """
        self.db = db_connection or get_db_connection()
        self.discrepancy_threshold = discrepancy_threshold
        self.web3 = Web3(Web3.HTTPProvider(os.getenv('BEP20_RPC_URL')))
        
        # Initialize binance client
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_API_SECRET')
        testnet = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'
        self.binance_client = BinanceClient(api_key, api_secret, testnet=testnet)
        
        # Initialize alert service
        self.alert_service = DiscrepancyAlertService()
        
        # Initialize accounting system
        self.accounting = get_accounting_system(self.db)
    
    def reconcile_all_wallets(self):
        """
        Reconcile balances for all wallets.
        
        Returns:
            Dict with reconciliation statistics
        """
        try:
            # Get all wallets
            cursor = self.db.cursor()
            cursor.execute("SELECT id, user_id, address, wallet_type FROM wallets")
            wallets = cursor.fetchall()
            
            stats = {
                'total_wallets': len(wallets),
                'reconciled': 0,
                'with_discrepancies': 0,
                'failed': 0
            }
            
            # Process each wallet
            for wallet_id, user_id, address, wallet_type in wallets:
                try:
                    result = self.reconcile_wallet(wallet_id)
                    
                    if result['has_discrepancies']:
                        stats['with_discrepancies'] += 1
                    
                    stats['reconciled'] += 1
                except Exception as e:
                    logger.error(f"Error reconciling wallet {wallet_id}: {str(e)}")
                    stats['failed'] += 1
            
            return stats
        
        except Exception as e:
            logger.error(f"Error in reconcile_all_wallets: {str(e)}")
            raise
    
    def reconcile_wallet(self, wallet_id):
        """
        Reconcile balances for a specific wallet.
        
        Args:
            wallet_id: ID of the wallet to reconcile
            
        Returns:
            Dict with reconciliation results
        """
        try:
            cursor = self.db.cursor()
            
            # Get wallet details
            cursor.execute(
                """
                SELECT user_id, address, wallet_type, chain_id
                FROM wallets WHERE id = %s
                """,
                (wallet_id,)
            )
            wallet = cursor.fetchone()
            
            if not wallet:
                raise ValueError(f"Wallet {wallet_id} not found")
                
            user_id, address, wallet_type, chain_id = wallet
            
            # Get wallet balances from DB
            cursor.execute(
                """
                SELECT token_symbol, token_address, balance
                FROM wallet_balances WHERE wallet_id = %s
                """,
                (wallet_id,)
            )
            db_balances = {row[0]: (row[1], float(row[2])) for row in cursor.fetchall()}
            
            results = {
                'wallet_id': wallet_id,
                'user_id': user_id,
                'address': address,
                'tokens_reconciled': 0,
                'has_discrepancies': False,
                'discrepancies': [],
                'reconciliation_date': datetime.datetime.now()
            }
            
            # Process each token
            for token_symbol, (token_address, db_balance) in db_balances.items():
                # Get on-chain balance
                if token_address:  # Token
                    chain_balance = self._get_token_balance(address, token_address)
                else:  # Native BNB
                    chain_balance = self._get_bnb_balance(address)
                
                # Get Binance balance if applicable
                binance_balance = self._get_binance_balance(user_id, token_symbol)
                
                # Calculate discrepancies
                chain_discrepancy = chain_balance - db_balance
                exchange_discrepancy = binance_balance - 0  # Assuming no balance should be on exchange unless transferred
                
                # Record reconciliation
                self._record_reconciliation(
                    wallet_id, token_symbol, db_balance, chain_balance, binance_balance,
                    chain_discrepancy, exchange_discrepancy
                )
                
                # Check for significant discrepancies
                if abs(chain_discrepancy) > self.discrepancy_threshold or abs(exchange_discrepancy) > self.discrepancy_threshold:
                    results['has_discrepancies'] = True
                    results['discrepancies'].append({
                        'token': token_symbol,
                        'db_balance': db_balance,
                        'chain_balance': chain_balance,
                        'binance_balance': binance_balance,
                        'chain_discrepancy': chain_discrepancy,
                        'exchange_discrepancy': exchange_discrepancy
                    })
                    
                    # Send alert for significant discrepancy
                    self.alert_service.send_discrepancy_alert(
                        wallet_id, user_id, token_symbol, db_balance, chain_balance,
                        binance_balance, chain_discrepancy, exchange_discrepancy
                    )
                
                results['tokens_reconciled'] += 1
            
            return results
            
        except Exception as e:
            logger.error(f"Error reconciling wallet {wallet_id}: {str(e)}")
            raise
    
    def _get_bnb_balance(self, address):
        """Get BNB balance from the blockchain."""
        wei_balance = self.web3.eth.get_balance(address)
        return float(Web3.from_wei(wei_balance, 'ether'))
    
    def _get_token_balance(self, address, token_address):
        """Get token balance from the blockchain."""
        # Load BEP20 ABI
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'abi', 'bep20.json'), 'r') as f:
            bep20_abi = json.load(f)
        
        token_contract = self.web3.eth.contract(address=token_address, abi=bep20_abi)
        wei_balance = token_contract.functions.balanceOf(address).call()
        
        # Get token decimals
        decimals = token_contract.functions.decimals().call()
        
        # Convert to human-readable form
        return float(wei_balance / (10 ** decimals))
    
    def _get_binance_balance(self, user_id, token_symbol):
        """
        Get token balance from Binance.
        
        For now, we'll assume there's a mapping from user_id to Binance API credentials.
        In a production system, this would be more sophisticated with proper credential management.
        """
        try:
            # Get user-specific Binance credentials
            # This is a placeholder - in reality, you'd retrieve the user's Binance API credentials
            binance_api_key = os.getenv(f'BINANCE_API_KEY_{user_id}', os.getenv('BINANCE_API_KEY'))
            binance_api_secret = os.getenv(f'BINANCE_API_SECRET_{user_id}', os.getenv('BINANCE_API_SECRET'))
            
            if not binance_api_key or not binance_api_secret:
                return 0.0  # No credentials, assume no balance
                
            # Initialize client with user's credentials
            client = BinanceClient(binance_api_key, binance_api_secret)
            
            # Get balance
            balance_data = client.get_balance()
            
            # Extract the specific token balance
            for balance in balance_data.get('info', {}).get('balances', []):
                if balance.get('asset') == token_symbol:
                    free = float(balance.get('free', 0))
                    locked = float(balance.get('locked', 0))
                    return free + locked
            
            return 0.0  # Token not found in balance
            
        except Exception as e:
            logger.error(f"Error getting Binance balance for user {user_id}, token {token_symbol}: {str(e)}")
            return 0.0
    
    def _record_reconciliation(self, wallet_id, token_symbol, db_balance, chain_balance, exchange_balance, chain_discrepancy, exchange_discrepancy):
        """Record the reconciliation result in the database."""
        try:
            cursor = self.db.cursor()
            
            status = 'matched'
            if abs(chain_discrepancy) > self.discrepancy_threshold or abs(exchange_discrepancy) > self.discrepancy_threshold:
                status = 'discrepancy'
            
            cursor.execute(
                """
                INSERT INTO balance_reconciliations
                (reconciliation_date, wallet_id, token_symbol, internal_balance, 
                blockchain_balance, exchange_balance, blockchain_discrepancy,
                exchange_discrepancy, status)
                VALUES
                (NOW(), %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    wallet_id, token_symbol, db_balance, chain_balance, exchange_balance,
                    chain_discrepancy, exchange_discrepancy, status
                )
            )
            
            reconciliation_id = cursor.fetchone()[0]
            self.db.commit()
            
            return reconciliation_id
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error recording reconciliation: {str(e)}")
            raise
    
    def resolve_discrepancy(self, reconciliation_id, resolution_notes, resolved_by, update_internal_balance=False):
        """
        Resolve a discrepancy by marking it as resolved and optionally updating internal balance.
        
        Args:
            reconciliation_id: Reconciliation record ID
            resolution_notes: Notes explaining the resolution
            resolved_by: User who resolved the discrepancy
            update_internal_balance: Whether to update the internal balance to match blockchain
            
        Returns:
            Boolean indicating success
        """
        try:
            cursor = self.db.cursor()
            
            # Get reconciliation record
            cursor.execute(
                """
                SELECT wallet_id, token_symbol, internal_balance, blockchain_balance, status
                FROM balance_reconciliations
                WHERE id = %s
                """,
                (reconciliation_id,)
            )
            
            reconciliation = cursor.fetchone()
            
            if not reconciliation:
                raise ValueError(f"Reconciliation record {reconciliation_id} not found")
                
            wallet_id, token_symbol, internal_balance, blockchain_balance, status = reconciliation
            
            if status == 'resolved':
                logger.warning(f"Reconciliation {reconciliation_id} already resolved")
                return True
                
            # Update reconciliation record
            cursor.execute(
                """
                UPDATE balance_reconciliations
                SET status = 'resolved', resolved_by = %s, resolution_notes = %s, resolved_at = NOW()
                WHERE id = %s
                """,
                (resolved_by, resolution_notes, reconciliation_id)
            )
            
            # Update internal balance if requested
            if update_internal_balance:
                # Get token address
                if token_symbol != 'BNB':
                    cursor.execute(
                        """
                        SELECT token_address FROM wallet_balances
                        WHERE wallet_id = %s AND token_symbol = %s
                        """,
                        (wallet_id, token_symbol)
                    )
                    token_result = cursor.fetchone()
                    token_address = token_result[0] if token_result else None
                else:
                    token_address = None
                
                # Update wallet balance
                cursor.execute(
                    """
                    UPDATE wallet_balances
                    SET balance = %s, last_updated = NOW()
                    WHERE wallet_id = %s AND token_symbol = %s
                    """,
                    (blockchain_balance, wallet_id, token_symbol)
                )
                
                logger.info(f"Updated internal balance for wallet {wallet_id}, token {token_symbol} from {internal_balance} to {blockchain_balance}")
            
            self.db.commit()
            logger.info(f"Resolved discrepancy {reconciliation_id}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error resolving discrepancy: {str(e)}")
            return False


def get_reconciliation_service(db_connection=None):
    """
    Get a reconciliation service instance.
    
    Args:
        db_connection: Optional database connection
        
    Returns:
        BalanceReconciliationService instance
    """
    return BalanceReconciliationService(db_connection or get_db_connection()) 