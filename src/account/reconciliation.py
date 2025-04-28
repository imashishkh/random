"""
Accounting and Reconciliation System

This module provides services for reconciling balances and recording accounting entries
for the forex trading platform.
"""

import os
import json
import logging
import smtplib
import requests
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from ..db.connection import get_db_connection
from ..exchange.binance import BinanceClient
from .wallet import get_wallet_by_id, get_user_wallets

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('accounting')


class ReconciliationStatus:
    """Status constants for reconciliation operations"""
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    RECONCILED = 'reconciled'
    DISCREPANCY = 'discrepancy'
    FAILED = 'failed'


class ReconciliationReport:
    """
    Class to hold reconciliation report data
    """
    def __init__(self, wallet_id: int, user_id: int, token_symbol: str, 
                 blockchain_balance: float, internal_balance: float, 
                 binance_balance: float, discrepancy: bool):
        self.wallet_id = wallet_id
        self.user_id = user_id
        self.token_symbol = token_symbol
        self.blockchain_balance = blockchain_balance
        self.internal_balance = internal_balance
        self.binance_balance = binance_balance
        self.discrepancy = discrepancy
        self.severity = self._calculate_severity()
        self.timestamp = datetime.now()
        self.resolution_status = ReconciliationStatus.DISCREPANCY if discrepancy else ReconciliationStatus.RECONCILED
        self.resolution_notes = None

    def _calculate_severity(self) -> str:
        """Calculate severity of discrepancy"""
        if not self.discrepancy:
            return "none"
            
        # Calculate percentage difference between internal and blockchain
        if self.blockchain_balance > 0:
            internal_diff_pct = abs(self.internal_balance - self.blockchain_balance) / self.blockchain_balance * 100
        else:
            internal_diff_pct = 100 if self.internal_balance > 0 else 0
            
        # Calculate percentage difference between internal and binance
        if self.binance_balance > 0:
            binance_diff_pct = abs(self.internal_balance - self.binance_balance) / self.binance_balance * 100
        else:
            binance_diff_pct = 100 if self.internal_balance > 0 else 0
            
        # Determine severity
        max_diff_pct = max(internal_diff_pct, binance_diff_pct)
        if max_diff_pct > 10:
            return "high"
        elif max_diff_pct > 5:
            return "medium"
        else:
            return "low"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'wallet_id': self.wallet_id,
            'user_id': self.user_id,
            'token_symbol': self.token_symbol,
            'blockchain_balance': self.blockchain_balance,
            'internal_balance': self.internal_balance,
            'binance_balance': self.binance_balance,
            'discrepancy': self.discrepancy,
            'severity': self.severity,
            'timestamp': self.timestamp.isoformat(),
            'resolution_status': self.resolution_status,
            'resolution_notes': self.resolution_notes
        }


class AccountingSystem:
    """
    System for managing accounting entries and reconciliation
    """
    
    def __init__(self, db_connection=None):
        """
        Initialize the accounting system.
        
        Args:
            db_connection: Database connection object
        """
        self.db = db_connection or get_db_connection()
        
        # Initialize binance client
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
        self.smtp_from = os.getenv('SMTP_FROM', 'accounting@forex-trading.com')
    
    def record_binance_transfer(self, user_id: int, amount: float, fee: float, 
                               token_symbol: str, tx_hash: str, reference: str) -> int:
        """
        Record a transfer to Binance in the accounting system.
        
        Args:
            user_id: User ID
            amount: Amount transferred
            fee: Fee amount (in the token's currency)
            token_symbol: Token symbol
            tx_hash: Transaction hash
            reference: Reference identifier (e.g., transfer UUID)
            
        Returns:
            ID of the created accounting entry
        """
        try:
            cursor = self.db.cursor()
            
            # Create accounting entry
            cursor.execute(
                """
                INSERT INTO accounting_entries
                (user_id, entry_type, amount, fee, token_symbol, tx_hash, reference, 
                 created_at, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
                RETURNING id
                """,
                (user_id, 'binance_transfer', amount, fee, token_symbol, tx_hash, 
                 reference, f"Transfer to Binance: {amount} {token_symbol}")
            )
            
            entry_id = cursor.fetchone()[0]
            self.db.commit()
            
            return entry_id
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error recording Binance transfer: {str(e)}")
            raise
    
    def record_deposit(self, user_id: int, wallet_id: int, amount: float, 
                      token_symbol: str, tx_hash: str) -> int:
        """
        Record a deposit in the accounting system.
        
        Args:
            user_id: User ID
            wallet_id: Wallet ID
            amount: Amount deposited
            token_symbol: Token symbol
            tx_hash: Transaction hash
            
        Returns:
            ID of the created accounting entry
        """
        try:
            cursor = self.db.cursor()
            
            # Create accounting entry
            cursor.execute(
                """
                INSERT INTO accounting_entries
                (user_id, entry_type, amount, token_symbol, tx_hash, wallet_id, 
                 created_at, description)
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
                RETURNING id
                """,
                (user_id, 'deposit', amount, token_symbol, tx_hash, wallet_id,
                 f"Deposit: {amount} {token_symbol}")
            )
            
            entry_id = cursor.fetchone()[0]
            self.db.commit()
            
            return entry_id
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error recording deposit: {str(e)}")
            raise
    
    def record_withdrawal(self, user_id: int, wallet_id: int, amount: float, fee: float,
                         token_symbol: str, tx_hash: str, to_address: str) -> int:
        """
        Record a withdrawal in the accounting system.
        
        Args:
            user_id: User ID
            wallet_id: Wallet ID
            amount: Amount withdrawn
            fee: Fee amount (in the token's currency)
            token_symbol: Token symbol
            tx_hash: Transaction hash
            to_address: Destination address
            
        Returns:
            ID of the created accounting entry
        """
        try:
            cursor = self.db.cursor()
            
            # Create accounting entry
            cursor.execute(
                """
                INSERT INTO accounting_entries
                (user_id, entry_type, amount, fee, token_symbol, tx_hash, wallet_id, 
                 to_address, created_at, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
                RETURNING id
                """,
                (user_id, 'withdrawal', amount, fee, token_symbol, tx_hash, wallet_id,
                 to_address, f"Withdrawal: {amount} {token_symbol} to {to_address}")
            )
            
            entry_id = cursor.fetchone()[0]
            self.db.commit()
            
            return entry_id
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error recording withdrawal: {str(e)}")
            raise
    
    def get_accounting_entries(self, user_id: int, entry_type: Optional[str] = None,
                              start_date: Optional[datetime] = None,
                              end_date: Optional[datetime] = None,
                              limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get accounting entries for a user.
        
        Args:
            user_id: User ID
            entry_type: Optional entry type filter
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Maximum number of records to return
            offset: Offset for pagination
            
        Returns:
            List of accounting entries
        """
        try:
            cursor = self.db.cursor()
            
            query = """
                SELECT id, user_id, entry_type, amount, fee, token_symbol, tx_hash,
                     wallet_id, to_address, reference, created_at, description
                FROM accounting_entries
                WHERE user_id = %s
            """
            
            params = [user_id]
            
            if entry_type:
                query += " AND entry_type = %s"
                params.append(entry_type)
                
            if start_date:
                query += " AND created_at >= %s"
                params.append(start_date)
                
            if end_date:
                query += " AND created_at <= %s"
                params.append(end_date)
                
            query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            
            entries = []
            for row in cursor.fetchall():
                (entry_id, user_id, entry_type, amount, fee, token_symbol, tx_hash,
                 wallet_id, to_address, reference, created_at, description) = row
                
                entries.append({
                    'id': entry_id,
                    'user_id': user_id,
                    'entry_type': entry_type,
                    'amount': float(amount),
                    'fee': float(fee) if fee is not None else None,
                    'token_symbol': token_symbol,
                    'tx_hash': tx_hash,
                    'wallet_id': wallet_id,
                    'to_address': to_address,
                    'reference': reference,
                    'created_at': created_at.isoformat() if created_at else None,
                    'description': description
                })
                
            return entries
            
        except Exception as e:
            logger.error(f"Error getting accounting entries: {str(e)}")
            raise
    
    def reconcile_wallet(self, wallet_id: int, token_symbol: str) -> ReconciliationReport:
        """
        Reconcile wallet balance with blockchain and Binance balances.
        
        Args:
            wallet_id: Wallet ID
            token_symbol: Token symbol
            
        Returns:
            Reconciliation report
        """
        try:
            # Get wallet details
            wallet = get_wallet_by_id(wallet_id, self.db)
            if not wallet:
                raise ValueError(f"Wallet {wallet_id} not found")
                
            user_id = wallet['user_id']
            address = wallet['address']
            
            # Get internal balance
            cursor = self.db.cursor()
            cursor.execute(
                """
                SELECT balance
                FROM wallet_balances 
                WHERE wallet_id = %s AND token_symbol = %s
                """,
                (wallet_id, token_symbol)
            )
            
            result = cursor.fetchone()
            internal_balance = float(result[0]) if result else 0
            
            # Get blockchain balance
            blockchain_balance = self._get_blockchain_balance(address, token_symbol)
            
            # Get Binance balance (if applicable)
            binance_balance = self._get_binance_balance(user_id, token_symbol)
            
            # Determine if there's a discrepancy
            # Allow a small tolerance for precision issues
            tolerance = 0.000001
            blockchain_diff = abs(internal_balance - blockchain_balance)
            binance_diff = abs(internal_balance - binance_balance)
            
            has_discrepancy = (blockchain_diff > tolerance) or (binance_diff > tolerance)
            
            # Create reconciliation report
            report = ReconciliationReport(
                wallet_id=wallet_id,
                user_id=user_id,
                token_symbol=token_symbol,
                blockchain_balance=blockchain_balance,
                internal_balance=internal_balance,
                binance_balance=binance_balance,
                discrepancy=has_discrepancy
            )
            
            # Save report
            self._save_reconciliation_report(report)
            
            # Send alert if significant discrepancy
            if has_discrepancy and report.severity != "low":
                self._send_discrepancy_alert(report)
            
            return report
            
        except Exception as e:
            logger.error(f"Error reconciling wallet: {str(e)}")
            raise
    
    def reconcile_all_wallets(self) -> List[ReconciliationReport]:
        """
        Reconcile all wallets in the system.
        
        Returns:
            List of reconciliation reports
        """
        try:
            cursor = self.db.cursor()
            
            # Get all wallets and their token balances
            cursor.execute(
                """
                SELECT w.id as wallet_id, w.user_id, wb.token_symbol
                FROM wallets w
                JOIN wallet_balances wb ON w.id = wb.wallet_id
                """
            )
            
            wallet_tokens = cursor.fetchall()
            
            reports = []
            for wallet_id, user_id, token_symbol in wallet_tokens:
                try:
                    report = self.reconcile_wallet(wallet_id, token_symbol)
                    reports.append(report)
                except Exception as e:
                    logger.error(f"Error reconciling wallet {wallet_id}, token {token_symbol}: {str(e)}")
            
            return reports
            
        except Exception as e:
            logger.error(f"Error reconciling all wallets: {str(e)}")
            raise
    
    def _get_blockchain_balance(self, address: str, token_symbol: str) -> float:
        """
        Get balance from blockchain.
        
        Args:
            address: Wallet address
            token_symbol: Token symbol
            
        Returns:
            Balance as a float
        """
        try:
            # For demonstration, returning a simulated balance
            # In a real implementation, this would query the blockchain
            # using a provider like web3.py
            
            # Simulate a blockchain query delay
            import time
            time.sleep(0.1)
            
            # Get the balance from internal DB as a placeholder
            # for demonstration purposes
            cursor = self.db.cursor()
            cursor.execute(
                """
                SELECT balance
                FROM wallet_balances wb
                JOIN wallets w ON wb.wallet_id = w.id
                WHERE w.address = %s AND wb.token_symbol = %s
                """,
                (address, token_symbol)
            )
            
            result = cursor.fetchone()
            
            # Simulate a slight difference occasionally for testing discrepancy detection
            from random import random
            balance = float(result[0]) if result else 0
            
            # 5% chance of discrepancy for testing
            if random() < 0.05:
                return balance * (1 + (random() * 0.02 - 0.01))  # ±1% difference
                
            return balance
            
        except Exception as e:
            logger.error(f"Error getting blockchain balance: {str(e)}")
            return 0
    
    def _get_binance_balance(self, user_id: int, token_symbol: str) -> float:
        """
        Get balance from Binance.
        
        Args:
            user_id: User ID
            token_symbol: Token symbol
            
        Returns:
            Balance as a float
        """
        try:
            # For demonstration, returning a simulated balance
            # In a real implementation, this would query the Binance API
            
            # Query DB for any account_transfers related to this user and token
            cursor = self.db.cursor()
            cursor.execute(
                """
                SELECT COALESCE(SUM(amount), 0) as total_transfer
                FROM fund_transfers
                WHERE user_id = %s AND token_symbol = %s AND status = 'completed'
                """,
                (user_id, token_symbol)
            )
            
            result = cursor.fetchone()
            transferred_amount = float(result[0]) if result and result[0] else 0
            
            # Simulate a slight difference occasionally for testing discrepancy detection
            from random import random
            
            # 5% chance of discrepancy for testing
            if random() < 0.05:
                return transferred_amount * (1 + (random() * 0.02 - 0.01))  # ±1% difference
                
            return transferred_amount
            
        except Exception as e:
            logger.error(f"Error getting Binance balance: {str(e)}")
            return 0
    
    def _save_reconciliation_report(self, report: ReconciliationReport) -> int:
        """
        Save reconciliation report to database.
        
        Args:
            report: Reconciliation report object
            
        Returns:
            ID of the saved report
        """
        try:
            cursor = self.db.cursor()
            
            cursor.execute(
                """
                INSERT INTO reconciliation_reports
                (wallet_id, user_id, token_symbol, blockchain_balance, internal_balance,
                 binance_balance, discrepancy, severity, created_at, resolution_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (report.wallet_id, report.user_id, report.token_symbol, 
                 report.blockchain_balance, report.internal_balance, report.binance_balance,
                 report.discrepancy, report.severity, report.timestamp, report.resolution_status)
            )
            
            report_id = cursor.fetchone()[0]
            self.db.commit()
            
            return report_id
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving reconciliation report: {str(e)}")
            raise
    
    def get_recent_reconciliation_reports(self, user_id: Optional[int] = None,
                                        status: Optional[str] = None,
                                        limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get recent reconciliation reports.
        
        Args:
            user_id: Optional user ID filter
            status: Optional status filter
            limit: Maximum number of records to return
            offset: Offset for pagination
            
        Returns:
            List of reconciliation reports
        """
        try:
            cursor = self.db.cursor()
            
            query = """
                SELECT id, wallet_id, user_id, token_symbol, blockchain_balance, 
                     internal_balance, binance_balance, discrepancy, severity, 
                     created_at, resolution_status, resolution_notes
                FROM reconciliation_reports
            """
            
            params = []
            where_added = False
            
            if user_id:
                query += " WHERE user_id = %s"
                params.append(user_id)
                where_added = True
                
            if status:
                query += " WHERE " if not where_added else " AND "
                query += "resolution_status = %s"
                params.append(status)
                
            query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            
            reports = []
            for row in cursor.fetchall():
                (report_id, wallet_id, user_id, token_symbol, blockchain_balance, 
                 internal_balance, binance_balance, discrepancy, severity, 
                 created_at, resolution_status, resolution_notes) = row
                
                reports.append({
                    'id': report_id,
                    'wallet_id': wallet_id,
                    'user_id': user_id,
                    'token_symbol': token_symbol,
                    'blockchain_balance': float(blockchain_balance),
                    'internal_balance': float(internal_balance),
                    'binance_balance': float(binance_balance),
                    'discrepancy': discrepancy,
                    'severity': severity,
                    'created_at': created_at.isoformat() if created_at else None,
                    'resolution_status': resolution_status,
                    'resolution_notes': resolution_notes
                })
                
            return reports
            
        except Exception as e:
            logger.error(f"Error getting reconciliation reports: {str(e)}")
            raise
    
    def resolve_discrepancy(self, report_id: int, resolution_notes: str, 
                          update_balance: bool = False) -> Dict[str, Any]:
        """
        Mark a discrepancy as resolved.
        
        Args:
            report_id: Reconciliation report ID
            resolution_notes: Notes about the resolution
            update_balance: Whether to update the internal balance to match blockchain
            
        Returns:
            Updated report details
        """
        try:
            cursor = self.db.cursor()
            
            # Get report details
            cursor.execute(
                """
                SELECT wallet_id, user_id, token_symbol, blockchain_balance, internal_balance,
                     binance_balance, discrepancy, severity
                FROM reconciliation_reports
                WHERE id = %s
                """,
                (report_id,)
            )
            
            report = cursor.fetchone()
            if not report:
                raise ValueError(f"Report {report_id} not found")
                
            (wallet_id, user_id, token_symbol, blockchain_balance, 
             internal_balance, binance_balance, discrepancy, severity) = report
            
            # Update report status
            cursor.execute(
                """
                UPDATE reconciliation_reports
                SET resolution_status = %s, resolution_notes = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (ReconciliationStatus.RECONCILED, resolution_notes, report_id)
            )
            
            # Update wallet balance if requested
            if update_balance and discrepancy:
                cursor.execute(
                    """
                    UPDATE wallet_balances
                    SET balance = %s, last_updated = NOW()
                    WHERE wallet_id = %s AND token_symbol = %s
                    """,
                    (blockchain_balance, wallet_id, token_symbol)
                )
                
                # Record this adjustment
                cursor.execute(
                    """
                    INSERT INTO accounting_entries
                    (user_id, entry_type, amount, token_symbol, wallet_id, reference, 
                     created_at, description)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
                    """,
                    (user_id, 'balance_adjustment', blockchain_balance - internal_balance, 
                     token_symbol, wallet_id, f"Report {report_id}",
                     f"Balance adjustment from reconciliation: {internal_balance} to {blockchain_balance}")
                )
                
            self.db.commit()
            
            # Return updated details
            return {
                'id': report_id,
                'wallet_id': wallet_id,
                'user_id': user_id,
                'token_symbol': token_symbol,
                'blockchain_balance': float(blockchain_balance),
                'internal_balance': float(internal_balance) if not update_balance else float(blockchain_balance),
                'binance_balance': float(binance_balance),
                'resolution_status': ReconciliationStatus.RECONCILED,
                'resolution_notes': resolution_notes,
                'balance_updated': update_balance
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error resolving discrepancy: {str(e)}")
            raise
    
    def _send_discrepancy_alert(self, report: ReconciliationReport) -> None:
        """
        Send alerts for discrepancies.
        
        Args:
            report: Reconciliation report
        """
        try:
            # Create alert message
            alert_message = f"""
Discrepancy Detected!

Wallet ID: {report.wallet_id}
User ID: {report.user_id}
Token: {report.token_symbol}
Severity: {report.severity.upper()}

Internal Balance: {report.internal_balance}
Blockchain Balance: {report.blockchain_balance}
Binance Balance: {report.binance_balance}

Timestamp: {report.timestamp.isoformat()}
            """
            
            # Send email notification if configured
            if self.notify_email and self.smtp_host:
                self._send_email_alert(self.notify_email, "Balance Discrepancy Alert", 
                                      alert_message, report)
            
            # Send Slack notification if configured
            if self.notify_slack:
                self._send_slack_alert(self.notify_slack, alert_message, report)
                
        except Exception as e:
            logger.error(f"Error sending discrepancy alert: {str(e)}")
    
    def _send_email_alert(self, recipient: str, subject: str, 
                         message: str, report: ReconciliationReport) -> None:
        """
        Send email alert.
        
        Args:
            recipient: Email recipient
            subject: Email subject
            message: Plain text message
            report: Reconciliation report
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_from
            msg['To'] = recipient
            msg['Subject'] = f"{subject} - {report.severity.upper()}"
            
            # Add severity indication to subject
            if report.severity == "high":
                msg['Subject'] = f"URGENT: {msg['Subject']}"
            
            # Create HTML content
            html = f"""
            <html>
              <head>
                <style>
                  .discrepancy-table {{ border-collapse: collapse; width: 100%; }}
                  .discrepancy-table td, .discrepancy-table th {{ border: 1px solid #ddd; padding: 8px; }}
                  .discrepancy-table tr:nth-child(even) {{ background-color: #f2f2f2; }}
                  .discrepancy-table th {{ padding-top: 12px; padding-bottom: 12px; text-align: left; background-color: #4CAF50; color: white; }}
                  .severity-high {{ color: red; font-weight: bold; }}
                  .severity-medium {{ color: orange; font-weight: bold; }}
                  .severity-low {{ color: yellow; }}
                </style>
              </head>
              <body>
                <h2>Balance Discrepancy Alert</h2>
                <p>A balance discrepancy has been detected with 
                <span class="severity-{report.severity}">{report.severity.upper()} severity</span>.</p>
                
                <table class="discrepancy-table">
                  <tr>
                    <th>Property</th>
                    <th>Value</th>
                  </tr>
                  <tr>
                    <td>Wallet ID</td>
                    <td>{report.wallet_id}</td>
                  </tr>
                  <tr>
                    <td>User ID</td>
                    <td>{report.user_id}</td>
                  </tr>
                  <tr>
                    <td>Token</td>
                    <td>{report.token_symbol}</td>
                  </tr>
                  <tr>
                    <td>Internal Balance</td>
                    <td>{report.internal_balance}</td>
                  </tr>
                  <tr>
                    <td>Blockchain Balance</td>
                    <td>{report.blockchain_balance}</td>
                  </tr>
                  <tr>
                    <td>Binance Balance</td>
                    <td>{report.binance_balance}</td>
                  </tr>
                  <tr>
                    <td>Timestamp</td>
                    <td>{report.timestamp.isoformat()}</td>
                  </tr>
                </table>
                
                <p>Please investigate this discrepancy immediately.</p>
              </body>
            </html>
            """
            
            # Attach plain and HTML versions
            msg.attach(MIMEText(message, 'plain'))
            msg.attach(MIMEText(html, 'html'))
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
                
            logger.info(f"Sent email alert for discrepancy on wallet {report.wallet_id}")
            
        except Exception as e:
            logger.error(f"Error sending email alert: {str(e)}")
    
    def _send_slack_alert(self, webhook_url: str, message: str, 
                         report: ReconciliationReport) -> None:
        """
        Send Slack alert.
        
        Args:
            webhook_url: Slack webhook URL
            message: Message text
            report: Reconciliation report
        """
        try:
            # Create color based on severity
            color = "#ff0000" if report.severity == "high" else "#ff9900" if report.severity == "medium" else "#ffff00"
            
            # Create payload
            payload = {
                "attachments": [
                    {
                        "fallback": f"Balance discrepancy detected - {report.severity.upper()} severity",
                        "color": color,
                        "pretext": f"*Balance Discrepancy Alert - {report.severity.upper()} Severity*",
                        "fields": [
                            {
                                "title": "Wallet ID",
                                "value": str(report.wallet_id),
                                "short": True
                            },
                            {
                                "title": "User ID",
                                "value": str(report.user_id),
                                "short": True
                            },
                            {
                                "title": "Token",
                                "value": report.token_symbol,
                                "short": True
                            },
                            {
                                "title": "Internal Balance",
                                "value": str(report.internal_balance),
                                "short": True
                            },
                            {
                                "title": "Blockchain Balance",
                                "value": str(report.blockchain_balance),
                                "short": True
                            },
                            {
                                "title": "Binance Balance",
                                "value": str(report.binance_balance),
                                "short": True
                            }
                        ],
                        "footer": f"Timestamp: {report.timestamp.isoformat()}"
                    }
                ]
            }
            
            # Send to Slack
            response = requests.post(webhook_url, json=payload)
            response.raise_for_status()
            
            logger.info(f"Sent Slack alert for discrepancy on wallet {report.wallet_id}")
            
        except Exception as e:
            logger.error(f"Error sending Slack alert: {str(e)}")


def get_accounting_system(db_connection=None):
    """
    Get an accounting system instance.
    
    Args:
        db_connection: Optional database connection
        
    Returns:
        AccountingSystem instance
    """
    return AccountingSystem(db_connection or get_db_connection()) 