"""
Transaction Tracker Module

This module manages the lifecycle of blockchain transactions, tracking their status from initiation 
through confirmation/rejection, and providing a centralized way to query transaction status.
"""

import os
import time
import logging
import threading
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union
from datetime import datetime, timedelta

from dotenv import load_dotenv
from web3 import Web3

# Local imports
from .transaction_verification import TransactionVerifier, VerificationStatus
from .notification import get_notifier, NotificationType

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('transaction_tracker')

# Load environment variables
load_dotenv()

# Constants
CONFIRMATION_THRESHOLD = int(os.getenv('CONFIRMATION_THRESHOLD', '12'))
VERIFICATION_INTERVAL = int(os.getenv('VERIFICATION_INTERVAL', '60'))  # seconds
MAX_VERIFICATION_ATTEMPTS = int(os.getenv('MAX_VERIFICATION_ATTEMPTS', '100'))
BSC_RPC_URL = os.getenv('BSC_RPC_URL', 'https://bsc-dataseed.binance.org/')
ENABLE_NOTIFICATIONS = os.getenv('ENABLE_TX_NOTIFICATIONS', 'true').lower() == 'true'


class TransactionStatus(Enum):
    """Transaction status enum"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    DROPPED = "dropped"
    STUCK = "stuck"


class TransactionType(Enum):
    """Transaction type enum"""
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    OTHER = "other"


class TransactionTracker:
    """
    Tracks blockchain transactions throughout their lifecycle
    
    Features:
    - Track multiple transactions simultaneously
    - Automatic status updates through background verification
    - Confirmation threshold check
    - Notification of status changes
    - Historical status tracking
    """
    
    def __init__(self, db_connection=None, verification_interval=VERIFICATION_INTERVAL):
        """
        Initialize transaction tracker
        
        Args:
            db_connection: Database connection for persistence
            verification_interval: Seconds between verification attempts
        """
        self.db = db_connection
        self.verification_interval = verification_interval
        self.transactions = {}  # In-memory store of tracked transactions
        self.verifier = TransactionVerifier()
        self.notifier = get_notifier(db_connection) if ENABLE_NOTIFICATIONS else None
        
        # Setup web3 connection 
        self.web3 = Web3(Web3.HTTPProvider(BSC_RPC_URL))
        
        # Thread for background verification
        self.stop_event = threading.Event()
        self.verification_thread = None
        
        # Load existing transactions from database if available
        if self.db:
            self._load_transactions_from_db()
            
        logger.info("Transaction tracker initialized")
    
    def start_background_verification(self):
        """Start background verification process"""
        if self.verification_thread and self.verification_thread.is_alive():
            logger.warning("Background verification already running")
            return
            
        self.stop_event.clear()
        self.verification_thread = threading.Thread(
            target=self._verification_worker,
            daemon=True
        )
        self.verification_thread.start()
        logger.info("Started background transaction verification")
    
    def stop_background_verification(self):
        """Stop background verification process"""
        if not self.verification_thread or not self.verification_thread.is_alive():
            logger.warning("Background verification not running")
            return
            
        self.stop_event.set()
        self.verification_thread.join(timeout=10)
        logger.info("Stopped background transaction verification")
    
    def track_transaction(self, 
                          tx_hash: str, 
                          user_id: int, 
                          tx_type: Union[str, TransactionType],
                          chain_id: int = 56,  # BSC by default
                          amount: Optional[float] = None, 
                          currency: Optional[str] = None,
                          metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Start tracking a transaction
        
        Args:
            tx_hash: Transaction hash
            user_id: User ID associated with transaction
            tx_type: Transaction type (deposit, withdrawal, etc.)
            chain_id: Blockchain ID (default: BSC mainnet 56)
            amount: Transaction amount (if applicable)
            currency: Currency code (if applicable)
            metadata: Additional metadata for the transaction
            
        Returns:
            Transaction record with tracking info
        """
        # Normalize transaction type
        if isinstance(tx_type, str):
            try:
                tx_type = TransactionType(tx_type.lower())
            except ValueError:
                tx_type = TransactionType.OTHER
                
        # Validate transaction hash
        if not self.verifier.is_valid_tx_hash(tx_hash):
            raise ValueError(f"Invalid transaction hash: {tx_hash}")
            
        # Create transaction record
        tx_record = {
            'tx_hash': tx_hash,
            'user_id': user_id,
            'type': tx_type.value,
            'chain_id': chain_id,
            'amount': amount,
            'currency': currency,
            'status': TransactionStatus.PENDING.value,
            'confirmations': 0,
            'verification_attempts': 0,
            'last_verified_at': None,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'status_history': [
                {
                    'status': TransactionStatus.PENDING.value,
                    'timestamp': datetime.now().isoformat()
                }
            ],
            'metadata': metadata or {}
        }
        
        # Store transaction
        self.transactions[tx_hash] = tx_record
        
        # Persist to database if available
        if self.db:
            self._save_transaction_to_db(tx_record)
            
        logger.info(f"Started tracking transaction {tx_hash} for user {user_id} ({tx_type.value})")
        return tx_record
    
    def verify_transaction(self, tx_hash: str) -> Dict[str, Any]:
        """
        Manually verify a transaction and update its status
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            Updated transaction record
        """
        if tx_hash not in self.transactions:
            raise ValueError(f"Transaction {tx_hash} not being tracked")
            
        tx_record = self.transactions[tx_hash]
        
        # Verify transaction
        verification_result = self.verifier.verify_transaction(tx_hash, tx_record['chain_id'])
        
        # Update transaction status based on verification
        old_status = tx_record['status']
        
        if verification_result['status'] == VerificationStatus.VERIFIED.value:
            # Get transaction receipt
            try:
                receipt = self.web3.eth.get_transaction_receipt(tx_hash)
                block_number = receipt.get('blockNumber')
                latest_block = self.web3.eth.block_number
                confirmations = 0
                
                if block_number is not None and latest_block:
                    confirmations = latest_block - block_number
                    
                # Check if transaction was successful
                if receipt.get('status') == 1:
                    # Check confirmation threshold
                    if confirmations >= CONFIRMATION_THRESHOLD:
                        new_status = TransactionStatus.CONFIRMED.value
                    else:
                        new_status = TransactionStatus.PENDING.value
                else:
                    new_status = TransactionStatus.FAILED.value
                    
                # Update confirmations
                tx_record['confirmations'] = confirmations
                
            except Exception as e:
                logger.error(f"Error getting transaction receipt for {tx_hash}: {str(e)}")
                new_status = TransactionStatus.PENDING.value
                
        elif verification_result['status'] == VerificationStatus.FAILED.value:
            # Check number of verification attempts
            if tx_record['verification_attempts'] > MAX_VERIFICATION_ATTEMPTS:
                # Transaction might be dropped or stuck
                time_since_creation = datetime.now() - datetime.fromisoformat(tx_record['created_at'])
                
                if time_since_creation > timedelta(hours=24):
                    new_status = TransactionStatus.DROPPED.value
                else:
                    new_status = TransactionStatus.STUCK.value
            else:
                new_status = tx_record['status']  # Keep current status
                
        else:
            new_status = TransactionStatus.UNKNOWN.value
            
        # Update transaction record
        tx_record['status'] = new_status
        tx_record['verification_attempts'] += 1
        tx_record['last_verified_at'] = datetime.now().isoformat()
        tx_record['updated_at'] = datetime.now().isoformat()
        
        # Record status change in history if status changed
        if new_status != old_status:
            tx_record['status_history'].append({
                'status': new_status,
                'timestamp': datetime.now().isoformat()
            })
            
            # Send notification if enabled
            if self.notifier and ENABLE_NOTIFICATIONS:
                self.notifier.notify_transaction_status_change(
                    user_id=tx_record['user_id'],
                    tx_hash=tx_hash,
                    old_status=old_status,
                    new_status=new_status,
                    tx_data=tx_record
                )
                
            logger.info(f"Transaction {tx_hash} status changed: {old_status} -> {new_status}")
            
            # Handle special case for deposit confirmations
            if new_status == TransactionStatus.CONFIRMED.value and tx_record['type'] == TransactionType.DEPOSIT.value:
                if self.notifier and ENABLE_NOTIFICATIONS:
                    self.notifier.notify_deposit_received(
                        user_id=tx_record['user_id'],
                        amount=tx_record['amount'],
                        currency=tx_record['currency'],
                        tx_hash=tx_hash,
                        confirmations=tx_record['confirmations']
                    )
                    
                # Trigger deposit processing (to be implemented)
                self._process_confirmed_deposit(tx_record)
        
        # Update in database if available
        if self.db:
            self._update_transaction_in_db(tx_record)
            
        return tx_record
    
    def get_transaction_status(self, tx_hash: str) -> Dict[str, Any]:
        """
        Get the current status of a tracked transaction
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            Transaction status info
        """
        if tx_hash not in self.transactions:
            # Try to load from database if available
            if self.db:
                tx_record = self._load_transaction_from_db(tx_hash)
                if tx_record:
                    return tx_record
                    
            raise ValueError(f"Transaction {tx_hash} not being tracked")
            
        return self.transactions[tx_hash]
    
    def get_transactions_by_user(self, 
                               user_id: int, 
                               status: Optional[Union[str, TransactionStatus]] = None, 
                               tx_type: Optional[Union[str, TransactionType]] = None) -> List[Dict[str, Any]]:
        """
        Get all transactions for a specific user with optional filters
        
        Args:
            user_id: User ID
            status: Filter by transaction status
            tx_type: Filter by transaction type
            
        Returns:
            List of matching transaction records
        """
        # Normalize status if provided
        if status is not None and isinstance(status, str):
            try:
                status = TransactionStatus(status.lower()).value
            except ValueError:
                status = None
                
        # Normalize type if provided
        if tx_type is not None and isinstance(tx_type, str):
            try:
                tx_type = TransactionType(tx_type.lower()).value
            except ValueError:
                tx_type = None
        elif tx_type is not None:
            tx_type = tx_type.value
            
        # If database is available, query from there
        if self.db:
            return self._get_transactions_from_db(user_id, status, tx_type)
            
        # Otherwise filter from in-memory store
        results = []
        for tx_record in self.transactions.values():
            if tx_record['user_id'] != user_id:
                continue
                
            if status is not None and tx_record['status'] != status:
                continue
                
            if tx_type is not None and tx_record['type'] != tx_type:
                continue
                
            results.append(tx_record)
            
        return results
    
    def set_confirmation_callback(self, 
                                tx_hash: str, 
                                callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Set a callback function to be called when a transaction is confirmed
        
        Args:
            tx_hash: Transaction hash
            callback: Function to call with transaction record when confirmed
        """
        if tx_hash not in self.transactions:
            raise ValueError(f"Transaction {tx_hash} not being tracked")
            
        self.transactions[tx_hash]['metadata']['confirmation_callback'] = callback
        logger.debug(f"Set confirmation callback for transaction {tx_hash}")
    
    def _verification_worker(self):
        """Background worker to verify transactions periodically"""
        logger.info("Transaction verification worker started")
        
        while not self.stop_event.is_set():
            try:
                # Get all pending transactions
                pending_txs = [
                    tx_hash for tx_hash, tx_record in self.transactions.items()
                    if tx_record['status'] in [
                        TransactionStatus.PENDING.value,
                        TransactionStatus.UNKNOWN.value,
                        TransactionStatus.STUCK.value
                    ]
                ]
                
                # Verify each pending transaction
                for tx_hash in pending_txs:
                    try:
                        self.verify_transaction(tx_hash)
                    except Exception as e:
                        logger.error(f"Error verifying transaction {tx_hash}: {str(e)}")
                        
                # Refresh from database if available
                if self.db:
                    self._load_transactions_from_db()
                    
            except Exception as e:
                logger.error(f"Error in transaction verification worker: {str(e)}")
                
            # Wait for next verification interval
            self.stop_event.wait(self.verification_interval)
            
        logger.info("Transaction verification worker stopped")
    
    def _process_confirmed_deposit(self, tx_record: Dict[str, Any]):
        """
        Process a confirmed deposit transaction
        
        Args:
            tx_record: Transaction record
        """
        logger.info(f"Processing confirmed deposit: {tx_record['tx_hash']}")
        
        # Placeholder for deposit processing logic
        # This should update user balances, create accounting entries, etc.
        # Implementation depends on specific business requirements
        
        # Check if a confirmation callback is registered
        if 'confirmation_callback' in tx_record.get('metadata', {}):
            try:
                callback = tx_record['metadata']['confirmation_callback']
                callback(tx_record)
                logger.info(f"Executed confirmation callback for {tx_record['tx_hash']}")
            except Exception as e:
                logger.error(f"Error executing confirmation callback: {str(e)}")
    
    def _load_transactions_from_db(self):
        """Load tracked transactions from database"""
        if not self.db:
            return
            
        try:
            cursor = self.db.cursor()
            cursor.execute(
                """
                SELECT bt.*, array_agg(bs.status || '|' || bs.created_at) as status_history
                FROM blockchain_transactions bt
                LEFT JOIN blockchain_tx_status_history bs ON bt.tx_hash = bs.tx_hash
                WHERE bt.status NOT IN ('confirmed', 'failed', 'dropped')
                GROUP BY bt.id, bt.tx_hash
                """
            )
            
            rows = cursor.fetchall()
            column_names = [desc[0] for desc in cursor.description]
            
            # Process each row
            for row in rows:
                tx_data = dict(zip(column_names, row))
                
                # Convert status history to expected format
                status_history = []
                if tx_data.get('status_history'):
                    for entry in tx_data['status_history']:
                        if entry and '|' in entry:
                            status, timestamp = entry.split('|', 1)
                            status_history.append({
                                'status': status,
                                'timestamp': timestamp
                            })
                
                # Add to in-memory store
                tx_hash = tx_data['tx_hash']
                self.transactions[tx_hash] = {
                    'tx_hash': tx_hash,
                    'user_id': tx_data['user_id'],
                    'type': tx_data.get('type', 'other'),
                    'chain_id': tx_data.get('chain_id', 56),
                    'amount': tx_data.get('amount'),
                    'currency': tx_data.get('currency'),
                    'status': tx_data['status'],
                    'confirmations': tx_data.get('confirmations', 0),
                    'verification_attempts': tx_data.get('verification_attempts', 0),
                    'last_verified_at': tx_data.get('last_verified_at'),
                    'created_at': tx_data['created_at'].isoformat() if isinstance(tx_data['created_at'], datetime) else tx_data['created_at'],
                    'updated_at': tx_data['updated_at'].isoformat() if isinstance(tx_data['updated_at'], datetime) else tx_data['updated_at'],
                    'status_history': status_history,
                    'metadata': tx_data.get('metadata', {}) if isinstance(tx_data.get('metadata'), dict) else {}
                }
                
            logger.info(f"Loaded {len(rows)} transactions from database")
            
        except Exception as e:
            logger.error(f"Error loading transactions from database: {str(e)}")
    
    def _load_transaction_from_db(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """
        Load a specific transaction from database
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            Transaction record if found, None otherwise
        """
        if not self.db:
            return None
            
        try:
            cursor = self.db.cursor()
            cursor.execute(
                """
                SELECT bt.*, array_agg(bs.status || '|' || bs.created_at) as status_history
                FROM blockchain_transactions bt
                LEFT JOIN blockchain_tx_status_history bs ON bt.tx_hash = bs.tx_hash
                WHERE bt.tx_hash = %s
                GROUP BY bt.id, bt.tx_hash
                """,
                (tx_hash,)
            )
            
            row = cursor.fetchone()
            if not row:
                return None
                
            column_names = [desc[0] for desc in cursor.description]
            tx_data = dict(zip(column_names, row))
            
            # Convert status history to expected format
            status_history = []
            if tx_data.get('status_history'):
                for entry in tx_data['status_history']:
                    if entry and '|' in entry:
                        status, timestamp = entry.split('|', 1)
                        status_history.append({
                            'status': status,
                            'timestamp': timestamp
                        })
            
            # Construct transaction record
            tx_record = {
                'tx_hash': tx_hash,
                'user_id': tx_data['user_id'],
                'type': tx_data.get('type', 'other'),
                'chain_id': tx_data.get('chain_id', 56),
                'amount': tx_data.get('amount'),
                'currency': tx_data.get('currency'),
                'status': tx_data['status'],
                'confirmations': tx_data.get('confirmations', 0),
                'verification_attempts': tx_data.get('verification_attempts', 0),
                'last_verified_at': tx_data.get('last_verified_at'),
                'created_at': tx_data['created_at'].isoformat() if isinstance(tx_data['created_at'], datetime) else tx_data['created_at'],
                'updated_at': tx_data['updated_at'].isoformat() if isinstance(tx_data['updated_at'], datetime) else tx_data['updated_at'],
                'status_history': status_history,
                'metadata': tx_data.get('metadata', {}) if isinstance(tx_data.get('metadata'), dict) else {}
            }
            
            # Add to in-memory store
            self.transactions[tx_hash] = tx_record
            
            return tx_record
            
        except Exception as e:
            logger.error(f"Error loading transaction {tx_hash} from database: {str(e)}")
            return None
    
    def _save_transaction_to_db(self, tx_record: Dict[str, Any]) -> bool:
        """
        Save transaction to database
        
        Args:
            tx_record: Transaction record
            
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            return False
            
        try:
            cursor = self.db.cursor()
            
            # Check if transaction already exists
            cursor.execute(
                "SELECT id FROM blockchain_transactions WHERE tx_hash = %s",
                (tx_record['tx_hash'],)
            )
            
            if cursor.fetchone():
                # Update existing record
                return self._update_transaction_in_db(tx_record)
                
            # Insert new transaction
            cursor.execute(
                """
                INSERT INTO blockchain_transactions
                (tx_hash, user_id, from_address, to_address, block_number, value, chain_id, 
                 type, status, confirmations, verification_attempts, last_verified_at, 
                 amount, currency, metadata, created_at, updated_at)
                VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    tx_record['tx_hash'],
                    tx_record['user_id'],
                    tx_record.get('metadata', {}).get('from_address'),
                    tx_record.get('metadata', {}).get('to_address'),
                    tx_record.get('metadata', {}).get('block_number'),
                    tx_record.get('metadata', {}).get('value'),
                    tx_record['chain_id'],
                    tx_record['type'],
                    tx_record['status'],
                    tx_record['confirmations'],
                    tx_record['verification_attempts'],
                    tx_record['last_verified_at'],
                    tx_record['amount'],
                    tx_record['currency'],
                    json.dumps(tx_record.get('metadata', {})),
                    tx_record['created_at'],
                    tx_record['updated_at']
                )
            )
            
            tx_id = cursor.fetchone()[0]
            
            # Insert initial status history
            cursor.execute(
                """
                INSERT INTO blockchain_tx_status_history
                (tx_hash, status, created_at)
                VALUES (%s, %s, %s)
                """,
                (
                    tx_record['tx_hash'],
                    tx_record['status'],
                    tx_record['created_at']
                )
            )
            
            self.db.commit()
            logger.debug(f"Saved transaction {tx_record['tx_hash']} to database with ID {tx_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving transaction to database: {str(e)}")
            if self.db:
                self.db.rollback()
            return False
    
    def _update_transaction_in_db(self, tx_record: Dict[str, Any]) -> bool:
        """
        Update transaction in database
        
        Args:
            tx_record: Transaction record
            
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            return False
            
        try:
            cursor = self.db.cursor()
            
            # Update transaction record
            cursor.execute(
                """
                UPDATE blockchain_transactions SET
                status = %s,
                confirmations = %s,
                verification_attempts = %s,
                last_verified_at = %s,
                updated_at = %s,
                metadata = %s
                WHERE tx_hash = %s
                """,
                (
                    tx_record['status'],
                    tx_record['confirmations'],
                    tx_record['verification_attempts'],
                    tx_record['last_verified_at'],
                    tx_record['updated_at'],
                    json.dumps(tx_record.get('metadata', {})),
                    tx_record['tx_hash']
                )
            )
            
            # Add status history entry if status changed
            if tx_record['status_history'] and len(tx_record['status_history']) > 0:
                latest_status = tx_record['status_history'][-1]
                
                # Check if this status change is already recorded
                cursor.execute(
                    """
                    SELECT id FROM blockchain_tx_status_history
                    WHERE tx_hash = %s AND status = %s AND created_at = %s
                    """,
                    (
                        tx_record['tx_hash'],
                        latest_status['status'],
                        latest_status['timestamp']
                    )
                )
                
                if not cursor.fetchone():
                    # Insert new status history entry
                    cursor.execute(
                        """
                        INSERT INTO blockchain_tx_status_history
                        (tx_hash, status, created_at)
                        VALUES (%s, %s, %s)
                        """,
                        (
                            tx_record['tx_hash'],
                            latest_status['status'],
                            latest_status['timestamp']
                        )
                    )
            
            self.db.commit()
            logger.debug(f"Updated transaction {tx_record['tx_hash']} in database")
            return True
            
        except Exception as e:
            logger.error(f"Error updating transaction in database: {str(e)}")
            if self.db:
                self.db.rollback()
            return False
    
    def _get_transactions_from_db(self, 
                                user_id: int, 
                                status: Optional[str] = None, 
                                tx_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get transactions from database with filters
        
        Args:
            user_id: User ID
            status: Transaction status filter
            tx_type: Transaction type filter
            
        Returns:
            List of matching transaction records
        """
        if not self.db:
            return []
            
        try:
            cursor = self.db.cursor()
            
            # Build query based on filters
            query = """
                SELECT bt.*, array_agg(bs.status || '|' || bs.created_at) as status_history
                FROM blockchain_transactions bt
                LEFT JOIN blockchain_tx_status_history bs ON bt.tx_hash = bs.tx_hash
                WHERE bt.user_id = %s
            """
            params = [user_id]
            
            if status:
                query += " AND bt.status = %s"
                params.append(status)
                
            if tx_type:
                query += " AND bt.type = %s"
                params.append(tx_type)
                
            query += " GROUP BY bt.id, bt.tx_hash ORDER BY bt.created_at DESC"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            column_names = [desc[0] for desc in cursor.description]
            
            results = []
            for row in rows:
                tx_data = dict(zip(column_names, row))
                
                # Convert status history to expected format
                status_history = []
                if tx_data.get('status_history'):
                    for entry in tx_data['status_history']:
                        if entry and '|' in entry:
                            status, timestamp = entry.split('|', 1)
                            status_history.append({
                                'status': status,
                                'timestamp': timestamp
                            })
                
                # Construct transaction record
                tx_record = {
                    'tx_hash': tx_data['tx_hash'],
                    'user_id': tx_data['user_id'],
                    'type': tx_data.get('type', 'other'),
                    'chain_id': tx_data.get('chain_id', 56),
                    'amount': tx_data.get('amount'),
                    'currency': tx_data.get('currency'),
                    'status': tx_data['status'],
                    'confirmations': tx_data.get('confirmations', 0),
                    'verification_attempts': tx_data.get('verification_attempts', 0),
                    'last_verified_at': tx_data.get('last_verified_at'),
                    'created_at': tx_data['created_at'].isoformat() if isinstance(tx_data['created_at'], datetime) else tx_data['created_at'],
                    'updated_at': tx_data['updated_at'].isoformat() if isinstance(tx_data['updated_at'], datetime) else tx_data['updated_at'],
                    'status_history': status_history,
                    'metadata': tx_data.get('metadata', {}) if isinstance(tx_data.get('metadata'), dict) else {}
                }
                
                results.append(tx_record)
                
                # Update in-memory cache
                self.transactions[tx_data['tx_hash']] = tx_record
                
            return results
            
        except Exception as e:
            logger.error(f"Error getting transactions from database: {str(e)}")
            return []

# Helper functions

def get_tracker(db_connection=None) -> TransactionTracker:
    """
    Get a configured transaction tracker instance
    
    Args:
        db_connection: Optional database connection
        
    Returns:
        TransactionTracker instance
    """
    return TransactionTracker(db_connection) 