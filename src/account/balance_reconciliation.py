"""
Balance Reconciliation System

This module provides functionality for reconciling balances between the internal database,
the blockchain, and Binance exchange. It detects discrepancies, logs them, and generates
alerts when necessary.
"""

import os
import logging
import json
import time
import threading
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import requests

from ..db.connection import get_db_connection
from ..exchange.binance import BinanceClient
from .wallet import get_wallet_by_id, get_user_wallets, get_wallet_balance
from ..blockchain.provider import get_blockchain_provider

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('reconciliation')

class DiscrepancySeverity:
    """Severity levels for balance discrepancies"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ReconciliationStatus:
    """Status constants for reconciliation records"""
    PENDING = "pending"
    RESOLVED = "resolved"
    INVESTIGATING = "investigating"

class BalanceReconciler:
    """
    Handles reconciliation of balances between blockchain, internal database, 
    and Binance exchange
    """
    
    def __init__(self, db_connection=None):
        """
        Initialize the balance reconciler
        
        Args:
            db_connection: Database connection (optional, will create if not provided)
        """
        self.db = db_connection or get_db_connection()
        self.blockchain_provider = get_blockchain_provider()
        
        # Initialize Binance client
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_API_SECRET')
        testnet = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'
        self.binance_client = BinanceClient(api_key, api_secret, testnet=testnet)
        
        # Configure notification settings
        self.notify_email = os.getenv('NOTIFICATION_EMAIL')
        self.notify_slack = os.getenv('NOTIFICATION_SLACK_WEBHOOK')
        self.smtp_host = os.getenv('SMTP_HOST')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.smtp_from = os.getenv('SMTP_FROM', 'reconciliation@forex-trading.com')
        
        # Tolerance threshold for discrepancies (in percentage)
        self.tolerance_threshold = float(os.getenv('RECONCILIATION_TOLERANCE', '0.1'))
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
    def reconcile_wallet(self, wallet_id: int, token_symbol: str) -> Dict[str, Any]:
        """
        Reconcile balances for a specific wallet and token
        
        Args:
            wallet_id: The ID of the wallet to reconcile
            token_symbol: The token symbol to reconcile
            
        Returns:
            Dictionary with reconciliation results
        """
        try:
            # Get wallet details
            wallet = get_wallet_by_id(wallet_id)
            if not wallet:
                logger.error(f"Wallet not found: {wallet_id}")
                return {"error": "Wallet not found"}
            
            user_id = wallet["user_id"]
            wallet_address = wallet["address"]
            
            # Get balances from different sources
            internal_balance = get_wallet_balance(wallet_id, token_symbol)
            blockchain_balance = self._get_blockchain_balance(wallet_address, token_symbol)
            binance_balance = self._get_binance_balance(user_id, token_symbol)
            
            # Calculate discrepancies
            internal_blockchain_diff = abs(internal_balance - blockchain_balance)
            internal_binance_diff = abs(internal_balance - binance_balance)
            
            # Check if discrepancy exceeds tolerance
            internal_blockchain_pct = (internal_blockchain_diff / blockchain_balance * 100) if blockchain_balance > 0 else 0
            internal_binance_pct = (internal_binance_diff / binance_balance * 100) if binance_balance > 0 else 0
            
            has_discrepancy = (internal_blockchain_pct > self.tolerance_threshold or 
                               internal_binance_pct > self.tolerance_threshold)
            
            # Determine severity
            severity = self._calculate_severity(
                internal_blockchain_pct, internal_binance_pct,
                internal_balance, blockchain_balance, binance_balance
            )
            
            # Create reconciliation record
            reconciliation_id = self._create_reconciliation_record(
                wallet_id, user_id, token_symbol,
                internal_balance, blockchain_balance, binance_balance,
                has_discrepancy, severity
            )
            
            # Send alerts if discrepancy detected
            if has_discrepancy:
                self._handle_discrepancy(
                    reconciliation_id, wallet_id, user_id, token_symbol,
                    internal_balance, blockchain_balance, binance_balance,
                    severity
                )
            
            # Return reconciliation data
            return {
                "reconciliation_id": reconciliation_id,
                "wallet_id": wallet_id,
                "user_id": user_id,
                "token_symbol": token_symbol,
                "internal_balance": float(internal_balance),
                "blockchain_balance": float(blockchain_balance),
                "binance_balance": float(binance_balance),
                "has_discrepancy": has_discrepancy,
                "severity": severity,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error reconciling wallet {wallet_id} for token {token_symbol}: {str(e)}")
            return {"error": str(e)}
    
    def reconcile_all_wallets(self) -> List[Dict[str, Any]]:
        """
        Reconcile all wallets in the system
        
        Returns:
            List of reconciliation results
        """
        results = []
        wallets = get_user_wallets()
        
        for wallet in wallets:
            wallet_id = wallet["id"]
            user_id = wallet["user_id"]
            
            # Get tokens associated with this wallet
            cursor = self.db.cursor()
            cursor.execute(
                "SELECT DISTINCT token_symbol FROM wallet_balances WHERE wallet_id = %s",
                (wallet_id,)
            )
            tokens = [row[0] for row in cursor.fetchall()]
            
            # Reconcile each token
            for token_symbol in tokens:
                result = self.reconcile_wallet(wallet_id, token_symbol)
                results.append(result)
        
        return results
    
    def _get_blockchain_balance(self, address: str, token_symbol: str) -> Decimal:
        """
        Get balance from blockchain
        
        Args:
            address: Wallet address
            token_symbol: Token symbol
            
        Returns:
            Balance as Decimal
        """
        try:
            balance = self.blockchain_provider.get_token_balance(address, token_symbol)
            return Decimal(str(balance))
        except Exception as e:
            logger.error(f"Error getting blockchain balance for {address}, token {token_symbol}: {str(e)}")
            return Decimal('0')
    
    def _get_binance_balance(self, user_id: int, token_symbol: str) -> Decimal:
        """
        Get balance from Binance
        
        Args:
            user_id: User ID
            token_symbol: Token symbol
            
        Returns:
            Balance as Decimal
        """
        try:
            # Get Binance account info for user
            cursor = self.db.cursor()
            cursor.execute(
                "SELECT binance_api_key, binance_api_secret FROM users WHERE id = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                logger.warning(f"User {user_id} not found or no Binance API credentials")
                return Decimal('0')
            
            api_key, api_secret = row
            
            if not api_key or not api_secret:
                logger.warning(f"User {user_id} has no Binance API credentials")
                return Decimal('0')
            
            # Use user-specific credentials
            client = BinanceClient(api_key, api_secret)
            balance = client.get_asset_balance(token_symbol)
            
            return Decimal(str(balance["free"])) + Decimal(str(balance["locked"]))
        except Exception as e:
            logger.error(f"Error getting Binance balance for user {user_id}, token {token_symbol}: {str(e)}")
            return Decimal('0')
    
    def _calculate_severity(self, blockchain_diff_pct: float, binance_diff_pct: float,
                          internal_balance: Decimal, blockchain_balance: Decimal,
                          binance_balance: Decimal) -> str:
        """
        Calculate severity of discrepancy
        
        Args:
            blockchain_diff_pct: Percentage difference between internal and blockchain
            binance_diff_pct: Percentage difference between internal and Binance
            internal_balance: Internal balance
            blockchain_balance: Blockchain balance
            binance_balance: Binance balance
            
        Returns:
            Severity level as string
        """
        max_diff_pct = max(blockchain_diff_pct, binance_diff_pct)
        
        # Calculate absolute differences
        blockchain_diff = abs(internal_balance - blockchain_balance)
        binance_diff = abs(internal_balance - binance_balance)
        
        # Get the maximum absolute difference
        max_diff = max(blockchain_diff, binance_diff)
        
        # Critical if difference is large in both percentage and absolute terms
        if max_diff_pct > 10 and max_diff > 1000:
            return DiscrepancySeverity.CRITICAL
        elif max_diff_pct > 5:
            return DiscrepancySeverity.HIGH
        elif max_diff_pct > 2:
            return DiscrepancySeverity.MEDIUM
        else:
            return DiscrepancySeverity.LOW
    
    def _create_reconciliation_record(self, wallet_id: int, user_id: int, token_symbol: str,
                                   internal_balance: Decimal, blockchain_balance: Decimal,
                                   binance_balance: Decimal, has_discrepancy: bool,
                                   severity: str) -> int:
        """
        Create a reconciliation record in the database
        
        Args:
            wallet_id: Wallet ID
            user_id: User ID
            token_symbol: Token symbol
            internal_balance: Internal balance
            blockchain_balance: Blockchain balance
            binance_balance: Binance balance
            has_discrepancy: Whether a discrepancy was detected
            severity: Severity level
            
        Returns:
            ID of created record
        """
        try:
            cursor = self.db.cursor()
            discrepancy_amount = max(
                abs(internal_balance - blockchain_balance),
                abs(internal_balance - binance_balance)
            )
            
            discrepancy_status = ReconciliationStatus.PENDING if has_discrepancy else ReconciliationStatus.RESOLVED
            
            cursor.execute(
                """
                INSERT INTO reconciliation_reports
                (wallet_id, user_id, token_symbol, blockchain_balance, internal_balance,
                 binance_balance, discrepancy_amount, discrepancy_status, severity,
                 reconciliation_date, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                (wallet_id, user_id, token_symbol, blockchain_balance, internal_balance,
                 binance_balance, discrepancy_amount, discrepancy_status, severity)
            )
            
            record_id = cursor.fetchone()[0]
            self.db.commit()
            
            return record_id
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating reconciliation record: {str(e)}")
            raise
    
    def _handle_discrepancy(self, reconciliation_id: int, wallet_id: int, user_id: int,
                          token_symbol: str, internal_balance: Decimal, 
                          blockchain_balance: Decimal, binance_balance: Decimal,
                          severity: str) -> None:
        """
        Handle a detected discrepancy
        
        Args:
            reconciliation_id: ID of reconciliation record
            wallet_id: Wallet ID
            user_id: User ID
            token_symbol: Token symbol
            internal_balance: Internal balance
            blockchain_balance: Blockchain balance
            binance_balance: Binance balance
            severity: Severity level
        """
        # Prepare notification data
        notification_data = {
            "reconciliation_id": reconciliation_id,
            "wallet_id": wallet_id,
            "user_id": user_id,
            "token_symbol": token_symbol,
            "internal_balance": float(internal_balance),
            "blockchain_balance": float(blockchain_balance),
            "binance_balance": float(binance_balance),
            "severity": severity,
            "timestamp": datetime.now().isoformat()
        }
        
        # Log the discrepancy
        logger.warning(f"Balance discrepancy detected: {json.dumps(notification_data)}")
        
        # Send email notification if configured
        if self.notify_email:
            self._send_email_notification(notification_data)
        
        # Send Slack notification if configured
        if self.notify_slack:
            self._send_slack_notification(notification_data)
    
    def _send_email_notification(self, data: Dict[str, Any]) -> None:
        """
        Send email notification about discrepancy
        
        Args:
            data: Discrepancy data
        """
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.smtp_from
            msg['To'] = self.notify_email
            msg['Subject'] = f"[{data['severity'].upper()}] Balance Discrepancy Detected - {data['token_symbol']}"
            
            # Create HTML body
            body = f"""
            <html>
            <body>
                <h2>Balance Discrepancy Detected</h2>
                <p><strong>Severity:</strong> {data['severity'].upper()}</p>
                <p><strong>Time:</strong> {data['timestamp']}</p>
                <p><strong>Token:</strong> {data['token_symbol']}</p>
                <p><strong>User ID:</strong> {data['user_id']}</p>
                <p><strong>Wallet ID:</strong> {data['wallet_id']}</p>
                
                <h3>Balances:</h3>
                <ul>
                    <li><strong>Internal Balance:</strong> {data['internal_balance']}</li>
                    <li><strong>Blockchain Balance:</strong> {data['blockchain_balance']}</li>
                    <li><strong>Binance Balance:</strong> {data['binance_balance']}</li>
                </ul>
                
                <p>Please investigate this discrepancy immediately.</p>
                <p>You can view the full report in the admin dashboard.</p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(body, 'html'))
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
                
            logger.info(f"Email notification sent to {self.notify_email}")
            
        except Exception as e:
            logger.error(f"Error sending email notification: {str(e)}")
    
    def _send_slack_notification(self, data: Dict[str, Any]) -> None:
        """
        Send Slack notification about discrepancy
        
        Args:
            data: Discrepancy data
        """
        try:
            # Create message
            severity_emoji = {
                DiscrepancySeverity.LOW: ":large_blue_circle:",
                DiscrepancySeverity.MEDIUM: ":warning:",
                DiscrepancySeverity.HIGH: ":rotating_light:",
                DiscrepancySeverity.CRITICAL: ":sos:"
            }
            
            emoji = severity_emoji.get(data['severity'], ":warning:")
            
            message = {
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{emoji} Balance Discrepancy Detected"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Severity:*\n{data['severity'].upper()}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Token:*\n{data['token_symbol']}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*User ID:*\n{data['user_id']}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Wallet ID:*\n{data['wallet_id']}"
                            }
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Balances:*"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Internal:*\n{data['internal_balance']}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Blockchain:*\n{data['blockchain_balance']}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Binance:*\n{data['binance_balance']}"
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"Reported at {data['timestamp']}"
                            }
                        ]
                    }
                ]
            }
            
            # Send to Slack
            response = requests.post(
                self.notify_slack,
                headers={"Content-Type": "application/json"},
                data=json.dumps(message)
            )
            
            response.raise_for_status()
            logger.info("Slack notification sent successfully")
            
        except Exception as e:
            logger.error(f"Error sending Slack notification: {str(e)}")
    
    def resolve_discrepancy(self, reconciliation_id: int, resolution_notes: str,
                          resolved_by: str, update_balance: bool = False) -> bool:
        """
        Mark a discrepancy as resolved
        
        Args:
            reconciliation_id: ID of reconciliation record
            resolution_notes: Notes about the resolution
            resolved_by: Username/ID of person who resolved it
            update_balance: Whether to update internal balance to match blockchain
            
        Returns:
            Success status
        """
        try:
            cursor = self.db.cursor()
            
            # Get reconciliation report
            cursor.execute(
                """
                SELECT wallet_id, user_id, token_symbol, blockchain_balance, internal_balance
                FROM reconciliation_reports
                WHERE id = %s
                """,
                (reconciliation_id,)
            )
            
            row = cursor.fetchone()
            if not row:
                logger.error(f"Reconciliation report not found: {reconciliation_id}")
                return False
                
            wallet_id, user_id, token_symbol, blockchain_balance, internal_balance = row
            
            # Update reconciliation report
            cursor.execute(
                """
                UPDATE reconciliation_reports
                SET discrepancy_status = %s, resolution_notes = %s, resolved_by = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (ReconciliationStatus.RESOLVED, resolution_notes, resolved_by, reconciliation_id)
            )
            
            # Update internal balance if requested
            if update_balance:
                cursor.execute(
                    """
                    UPDATE wallet_balances
                    SET balance = %s, updated_at = NOW()
                    WHERE wallet_id = %s AND token_symbol = %s
                    """,
                    (blockchain_balance, wallet_id, token_symbol)
                )
                
                # Log this adjustment
                cursor.execute(
                    """
                    INSERT INTO accounting_entries
                    (user_id, entry_type, amount, token_symbol, wallet_id, notes, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, 'completed', NOW())
                    """,
                    (user_id, 'balance_adjustment', 
                     blockchain_balance - internal_balance, 
                     token_symbol, wallet_id,
                     f"Balance adjustment from reconciliation #{reconciliation_id}")
                )
            
            self.db.commit()
            logger.info(f"Discrepancy {reconciliation_id} marked as resolved by {resolved_by}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error resolving discrepancy: {str(e)}")
            return False
    
    def get_pending_discrepancies(self, severity: Optional[str] = None, 
                              limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get list of pending discrepancies
        
        Args:
            severity: Filter by severity level
            limit: Maximum number of results
            
        Returns:
            List of discrepancy records
        """
        try:
            cursor = self.db.cursor()
            
            query = """
                SELECT id, wallet_id, user_id, token_symbol, blockchain_balance, 
                       internal_balance, binance_balance, discrepancy_amount, 
                       severity, reconciliation_date, created_at
                FROM reconciliation_reports
                WHERE discrepancy_status = %s
            """
            params = [ReconciliationStatus.PENDING]
            
            if severity:
                query += " AND severity = %s"
                params.append(severity)
                
            query += " ORDER BY severity DESC, created_at DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "wallet_id": row[1],
                    "user_id": row[2],
                    "token_symbol": row[3],
                    "blockchain_balance": float(row[4]),
                    "internal_balance": float(row[5]),
                    "binance_balance": float(row[6]),
                    "discrepancy_amount": float(row[7]),
                    "severity": row[8],
                    "reconciliation_date": row[9].isoformat() if row[9] else None,
                    "created_at": row[10].isoformat() if row[10] else None
                })
                
            return results
            
        except Exception as e:
            logger.error(f"Error getting pending discrepancies: {str(e)}")
            return []

def get_balance_reconciler(db_connection=None):
    """
    Get or create a BalanceReconciler instance
    
    Args:
        db_connection: Database connection (optional)
        
    Returns:
        BalanceReconciler instance
    """
    return BalanceReconciler(db_connection) 