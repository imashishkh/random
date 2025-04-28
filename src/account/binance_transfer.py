"""
Binance Transfer Service

This module provides services for transferring funds to Binance.
"""

import os
import json
import logging
import uuid
from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import datetime

from ..db.connection import get_db_connection
from ..exchange.binance import BinanceClient
from .wallet import get_wallet_by_id
from .reconciliation import AccountingSystem, get_accounting_system

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('binance_transfer')


class TransferStatus:
    """Status constants for transfer operations"""
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class BinanceTransferService:
    """
    Service for transferring funds from user wallets to Binance.
    """
    
    def __init__(self, db_connection=None):
        """
        Initialize the Binance transfer service.
        
        Args:
            db_connection: Database connection object
        """
        self.db = db_connection or get_db_connection()
        
        # Initialize binance client
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_API_SECRET')
        testnet = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'
        self.binance_client = BinanceClient(api_key, api_secret, testnet=testnet)
        
        # Initialize accounting system
        self.accounting = get_accounting_system(self.db)
    
    def create_transfer_request(self, user_id: int, wallet_id: int, amount: float, 
                               token_symbol: str, memo: str = "") -> Dict[str, Any]:
        """
        Create a new transfer request to move funds to Binance.
        
        Args:
            user_id: User ID
            wallet_id: Wallet ID to transfer from
            amount: Amount to transfer
            token_symbol: Token symbol (e.g., BNB, BUSD)
            memo: Optional memo for the transfer
            
        Returns:
            Dict with details of the created transfer request
        """
        try:
            # Validate inputs
            if amount <= 0:
                raise ValueError("Transfer amount must be greater than zero")
                
            # Get wallet info
            wallet = get_wallet_by_id(wallet_id, self.db)
            if not wallet:
                raise ValueError(f"Wallet {wallet_id} not found")
                
            if wallet['user_id'] != user_id:
                raise ValueError("Wallet does not belong to this user")
                
            # Check if token exists in wallet balance
            cursor = self.db.cursor()
            cursor.execute(
                """
                SELECT token_address, balance
                FROM wallet_balances 
                WHERE wallet_id = %s AND token_symbol = %s
                """,
                (wallet_id, token_symbol)
            )
            
            token_balance = cursor.fetchone()
            if not token_balance:
                raise ValueError(f"Token {token_symbol} not found in wallet {wallet_id}")
                
            token_address, balance = token_balance
            
            # Check sufficient balance
            if float(balance) < amount:
                raise ValueError(f"Insufficient balance. Available: {balance}, Requested: {amount}")
            
            # Generate transfer ID
            transfer_id = str(uuid.uuid4())
            
            # Create transfer record
            cursor.execute(
                """
                INSERT INTO fund_transfers
                (transfer_id, user_id, wallet_id, amount, token_symbol, status, 
                created_at, updated_at, memo)
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), %s)
                RETURNING id
                """,
                (transfer_id, user_id, wallet_id, amount, token_symbol, 
                TransferStatus.PENDING, memo)
            )
            
            internal_id = cursor.fetchone()[0]
            self.db.commit()
            
            # Return transfer details
            return {
                'id': internal_id,
                'transfer_id': transfer_id,
                'user_id': user_id,
                'wallet_id': wallet_id,
                'amount': amount,
                'token_symbol': token_symbol,
                'status': TransferStatus.PENDING,
                'created_at': datetime.now().isoformat(),
                'memo': memo
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating transfer request: {str(e)}")
            raise
    
    def process_transfer(self, transfer_id: str) -> Dict[str, Any]:
        """
        Process a pending transfer request.
        
        Args:
            transfer_id: The UUID of the transfer to process
            
        Returns:
            Dict with the updated transfer details
        """
        try:
            cursor = self.db.cursor()
            
            # Get transfer details
            cursor.execute(
                """
                SELECT id, user_id, wallet_id, amount, token_symbol, status, memo
                FROM fund_transfers
                WHERE transfer_id = %s
                """,
                (transfer_id,)
            )
            
            transfer = cursor.fetchone()
            if not transfer:
                raise ValueError(f"Transfer {transfer_id} not found")
                
            internal_id, user_id, wallet_id, amount, token_symbol, status, memo = transfer
            
            # Check if already processed
            if status != TransferStatus.PENDING:
                logger.warning(f"Transfer {transfer_id} is already in status {status}")
                
                # Return current state
                return {
                    'id': internal_id,
                    'transfer_id': transfer_id,
                    'user_id': user_id,
                    'wallet_id': wallet_id,
                    'amount': float(amount),
                    'token_symbol': token_symbol,
                    'status': status,
                    'memo': memo
                }
            
            # Update status to processing
            cursor.execute(
                """
                UPDATE fund_transfers
                SET status = %s, updated_at = NOW()
                WHERE transfer_id = %s
                """,
                (TransferStatus.PROCESSING, transfer_id)
            )
            self.db.commit()
            
            try:
                # Get wallet details
                wallet = get_wallet_by_id(wallet_id, self.db)
                
                # Get deposit address from Binance
                deposit_addresses = self.binance_client.get_deposit_address(token_symbol)
                if not deposit_addresses or 'address' not in deposit_addresses:
                    raise ValueError(f"Could not get deposit address for {token_symbol}")
                
                binance_address = deposit_addresses['address']
                network = deposit_addresses.get('network', 'BSC')
                
                # Prepare transfer details for blockchain transaction
                # In a real implementation, you'd use a secure signing service
                # This is a placeholder for the transfer logic
                tx_details = {
                    'from_address': wallet['address'],
                    'to_address': binance_address,
                    'amount': amount,
                    'token_symbol': token_symbol,
                    'network': network,
                    'memo': memo,
                }
                
                # For demonstration, we'll simulate a successful transfer
                # In reality, you would:
                # 1. Create and sign the transaction
                # 2. Send it to the blockchain
                # 3. Monitor for confirmation
                # 4. Update status accordingly
                simulated_tx_hash = f"0x{uuid.uuid4().hex}"
                
                # Update transfer record with transaction hash
                cursor.execute(
                    """
                    UPDATE fund_transfers
                    SET tx_hash = %s, binance_address = %s, status = %s, updated_at = NOW()
                    WHERE transfer_id = %s
                    """,
                    (simulated_tx_hash, binance_address, TransferStatus.COMPLETED, transfer_id)
                )
                
                # Update wallet balance
                cursor.execute(
                    """
                    UPDATE wallet_balances
                    SET balance = balance - %s, last_updated = NOW()
                    WHERE wallet_id = %s AND token_symbol = %s
                    """,
                    (amount, wallet_id, token_symbol)
                )
                
                # Record the transfer in the accounting system
                # Calculate fee (this would be determined by the actual blockchain transaction)
                estimated_fee = 0.0002  # Placeholder BNB fee
                
                self.accounting.record_binance_transfer(
                    user_id=user_id,
                    amount=float(amount),
                    fee=estimated_fee,
                    token_symbol=token_symbol,
                    tx_hash=simulated_tx_hash,
                    reference=transfer_id
                )
                
                self.db.commit()
                
                # Return updated details
                return {
                    'id': internal_id,
                    'transfer_id': transfer_id,
                    'user_id': user_id,
                    'wallet_id': wallet_id,
                    'amount': float(amount),
                    'token_symbol': token_symbol,
                    'status': TransferStatus.COMPLETED,
                    'tx_hash': simulated_tx_hash,
                    'binance_address': binance_address,
                    'memo': memo
                }
                
            except Exception as e:
                # Mark as failed
                cursor.execute(
                    """
                    UPDATE fund_transfers
                    SET status = %s, failure_reason = %s, updated_at = NOW()
                    WHERE transfer_id = %s
                    """,
                    (TransferStatus.FAILED, str(e), transfer_id)
                )
                self.db.commit()
                
                logger.error(f"Error processing transfer {transfer_id}: {str(e)}")
                raise
                
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error in process_transfer: {str(e)}")
            raise
    
    def get_transfer_status(self, transfer_id: str) -> Dict[str, Any]:
        """
        Get the current status of a transfer.
        
        Args:
            transfer_id: The UUID of the transfer
            
        Returns:
            Dict with the transfer details
        """
        try:
            cursor = self.db.cursor()
            
            cursor.execute(
                """
                SELECT id, user_id, wallet_id, amount, token_symbol, status, 
                      tx_hash, binance_address, created_at, updated_at, memo, 
                      failure_reason
                FROM fund_transfers
                WHERE transfer_id = %s
                """,
                (transfer_id,)
            )
            
            transfer = cursor.fetchone()
            if not transfer:
                raise ValueError(f"Transfer {transfer_id} not found")
                
            (internal_id, user_id, wallet_id, amount, token_symbol, status, 
             tx_hash, binance_address, created_at, updated_at, memo, failure_reason) = transfer
            
            return {
                'id': internal_id,
                'transfer_id': transfer_id,
                'user_id': user_id,
                'wallet_id': wallet_id,
                'amount': float(amount),
                'token_symbol': token_symbol,
                'status': status,
                'tx_hash': tx_hash,
                'binance_address': binance_address,
                'created_at': created_at.isoformat() if created_at else None,
                'updated_at': updated_at.isoformat() if updated_at else None,
                'memo': memo,
                'failure_reason': failure_reason
            }
            
        except Exception as e:
            logger.error(f"Error getting transfer status: {str(e)}")
            raise
    
    def list_user_transfers(self, user_id: int, limit: int = 10, offset: int = 0, 
                           status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List transfers for a specific user.
        
        Args:
            user_id: User ID
            limit: Maximum number of records to return
            offset: Offset for pagination
            status: Optional status filter
            
        Returns:
            List of transfer records
        """
        try:
            cursor = self.db.cursor()
            
            query = """
                SELECT id, transfer_id, wallet_id, amount, token_symbol, status, 
                      tx_hash, binance_address, created_at, updated_at, memo, 
                      failure_reason
                FROM fund_transfers
                WHERE user_id = %s
            """
            
            params = [user_id]
            
            if status:
                query += " AND status = %s"
                params.append(status)
                
            query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            
            transfers = []
            for row in cursor.fetchall():
                (internal_id, transfer_id, wallet_id, amount, token_symbol, status, 
                 tx_hash, binance_address, created_at, updated_at, memo, failure_reason) = row
                
                transfers.append({
                    'id': internal_id,
                    'transfer_id': transfer_id,
                    'user_id': user_id,
                    'wallet_id': wallet_id,
                    'amount': float(amount),
                    'token_symbol': token_symbol,
                    'status': status,
                    'tx_hash': tx_hash,
                    'binance_address': binance_address,
                    'created_at': created_at.isoformat() if created_at else None,
                    'updated_at': updated_at.isoformat() if updated_at else None,
                    'memo': memo,
                    'failure_reason': failure_reason
                })
                
            return transfers
            
        except Exception as e:
            logger.error(f"Error listing user transfers: {str(e)}")
            raise
    
    def cancel_transfer(self, transfer_id: str, user_id: int) -> Dict[str, Any]:
        """
        Cancel a pending transfer.
        
        Args:
            transfer_id: Transfer UUID
            user_id: User ID (for authorization)
            
        Returns:
            Dict with the updated transfer details
        """
        try:
            cursor = self.db.cursor()
            
            # Get transfer details
            cursor.execute(
                """
                SELECT id, user_id, wallet_id, amount, token_symbol, status
                FROM fund_transfers
                WHERE transfer_id = %s
                """,
                (transfer_id,)
            )
            
            transfer = cursor.fetchone()
            if not transfer:
                raise ValueError(f"Transfer {transfer_id} not found")
                
            internal_id, db_user_id, wallet_id, amount, token_symbol, status = transfer
            
            # Verify user ownership
            if db_user_id != user_id:
                raise ValueError("Not authorized to cancel this transfer")
                
            # Check if can be cancelled
            if status != TransferStatus.PENDING:
                raise ValueError(f"Cannot cancel transfer in status {status}")
            
            # Update status to cancelled
            cursor.execute(
                """
                UPDATE fund_transfers
                SET status = %s, updated_at = NOW()
                WHERE transfer_id = %s
                """,
                (TransferStatus.CANCELLED, transfer_id)
            )
            self.db.commit()
            
            # Return updated details
            return {
                'id': internal_id,
                'transfer_id': transfer_id,
                'user_id': user_id,
                'wallet_id': wallet_id,
                'amount': float(amount),
                'token_symbol': token_symbol,
                'status': TransferStatus.CANCELLED
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error cancelling transfer: {str(e)}")
            raise


def get_binance_transfer_service(db_connection=None):
    """
    Get a Binance transfer service instance.
    
    Args:
        db_connection: Optional database connection
        
    Returns:
        BinanceTransferService instance
    """
    return BinanceTransferService(db_connection or get_db_connection()) 