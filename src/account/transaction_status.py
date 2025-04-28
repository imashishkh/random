"""
Transaction Status Module

This module provides functionality for tracking the status of blockchain transactions.
It includes a status tracking system for both deposits and withdrawals, with event-based
notifications and persistent status storage.
"""

import os
import json
import uuid
import logging
import threading
import time
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from .transaction_verification import get_verifier, VerificationStatus

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('transaction_status')


class TransactionType(Enum):
    """Transaction type enum"""
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    CONTRACT_INTERACTION = "contract_interaction"
    UNKNOWN = "unknown"


class TransactionStatus(Enum):
    """Transaction status enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    CONFIRMING = "confirming"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELED = "canceled"
    EXPIRED = "expired"
    MANUAL_REVIEW = "manual_review"
    UNKNOWN = "unknown"


class TransactionStatusManager:
    """
    Manager for tracking transaction statuses throughout their lifecycle
    """

    def __init__(self, db_connection_string: str = None, auto_start: bool = True):
        """
        Initialize the transaction status manager.
        
        Args:
            db_connection_string: Database connection string for persistence
            auto_start: Whether to automatically start the status update service
        """
        # Database connection
        self.db_connection_string = db_connection_string or os.getenv('DATABASE_URL')
        if not self.db_connection_string:
            raise ValueError("Database connection string not provided")
        
        # Transaction tracking dictionaries
        self._transactions = {}  # TX hash -> transaction metadata
        self._user_transactions = {}  # User ID -> set of tx hashes
        self._type_transactions = {}  # Transaction type -> set of tx hashes
        self._status_transactions = {}  # Status -> set of tx hashes
        
        # Listeners
        self._status_listeners = {}  # TX hash -> list of (callback, set of status)
        self._global_listeners = []  # List of (callback, set of status)
        
        # Locks for thread safety
        self._transactions_lock = threading.Lock()
        self._listeners_lock = threading.Lock()
        
        # Background monitoring
        self._status_thread = None
        self._stop_event = threading.Event()
        
        # Initialize the verification checker
        self._verifier = get_verifier()
        
        # Load existing transactions from database
        self._load_from_database()
        
        # Auto-start the status service if requested
        if auto_start:
            self.start_status_service()
    
    def register_transaction(self,
                            tx_hash: str,
                            tx_type: TransactionType,
                            user_id: int,
                            initial_status: TransactionStatus = TransactionStatus.PENDING,
                            metadata: Dict[str, Any] = None) -> bool:
        """
        Register a new transaction for status tracking.
        
        Args:
            tx_hash: Transaction hash
            tx_type: Transaction type
            user_id: User ID associated with the transaction
            initial_status: Initial status of the transaction
            metadata: Additional metadata to store with the transaction
            
        Returns:
            True if transaction was registered successfully, False otherwise
        """
        # Normalize transaction hash
        if not tx_hash.startswith('0x'):
            tx_hash = '0x' + tx_hash
        
        with self._transactions_lock:
            # Check if transaction already exists
            if tx_hash in self._transactions:
                logger.warning(f"Transaction {tx_hash} already registered")
                return False
            
            # Create transaction record
            transaction = {
                'tx_hash': tx_hash,
                'user_id': user_id,
                'type': tx_type.value,
                'status': initial_status.value,
                'created_at': datetime.now(),
                'updated_at': datetime.now(),
                'metadata': metadata or {},
                'history': [{
                    'status': initial_status.value,
                    'timestamp': datetime.now().isoformat(),
                    'reason': "Initial registration"
                }]
            }
            
            # Store in memory
            self._transactions[tx_hash] = transaction
            
            # Add to user index
            if user_id not in self._user_transactions:
                self._user_transactions[user_id] = set()
            self._user_transactions[user_id].add(tx_hash)
            
            # Add to type index
            if tx_type.value not in self._type_transactions:
                self._type_transactions[tx_type.value] = set()
            self._type_transactions[tx_type.value].add(tx_hash)
            
            # Add to status index
            if initial_status.value not in self._status_transactions:
                self._status_transactions[initial_status.value] = set()
            self._status_transactions[initial_status.value].add(tx_hash)
        
        # Save to database
        self._save_transaction_to_db(transaction)
        
        logger.info(f"Registered transaction {tx_hash} of type {tx_type.value} for user {user_id}")
        return True
    
    def update_transaction_status(self,
                                 tx_hash: str,
                                 new_status: TransactionStatus,
                                 reason: str = None) -> bool:
        """
        Update the status of a transaction and trigger listeners.
        
        Args:
            tx_hash: Transaction hash
            new_status: New status to set
            reason: Reason for the status change
            
        Returns:
            True if update was successful, False otherwise
        """
        # Normalize transaction hash
        if not tx_hash.startswith('0x'):
            tx_hash = '0x' + tx_hash
        
        with self._transactions_lock:
            # Check if transaction exists
            if tx_hash not in self._transactions:
                logger.warning(f"Cannot update non-existent transaction {tx_hash}")
                return False
            
            transaction = self._transactions[tx_hash]
            old_status = transaction['status']
            
            # Skip if status hasn't changed
            if old_status == new_status.value:
                logger.debug(f"Transaction {tx_hash} status unchanged: {old_status}")
                return True
            
            # Move transaction to new status index
            if old_status in self._status_transactions and tx_hash in self._status_transactions[old_status]:
                self._status_transactions[old_status].remove(tx_hash)
            
            if new_status.value not in self._status_transactions:
                self._status_transactions[new_status.value] = set()
            self._status_transactions[new_status.value].add(tx_hash)
            
            # Update transaction record
            transaction['status'] = new_status.value
            transaction['updated_at'] = datetime.now()
            transaction['history'].append({
                'status': new_status.value,
                'timestamp': datetime.now().isoformat(),
                'reason': reason or "Manual update"
            })
        
        # Save to database
        self._save_transaction_to_db(transaction)
        
        # Trigger listeners
        self._notify_listeners(tx_hash, old_status, new_status.value, transaction)
        
        logger.info(f"Updated transaction {tx_hash} status from {old_status} to {new_status.value}")
        return True
    
    def get_transaction_status(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get the current status and details of a transaction.
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            Dict containing transaction details or None if not found
        """
        # Normalize transaction hash
        if not tx_hash.startswith('0x'):
            tx_hash = '0x' + tx_hash
            
        with self._transactions_lock:
            if tx_hash not in self._transactions:
                return None
            
            # Return a copy to prevent modification
            return json.loads(json.dumps(self._transactions[tx_hash]))
    
    def get_user_transactions(self,
                             user_id: int,
                             tx_type: TransactionType = None,
                             status: TransactionStatus = None) -> List[Dict[str, Any]]:
        """
        Get all transactions for a specific user, optionally filtered.
        
        Args:
            user_id: User ID to get transactions for
            tx_type: Filter by transaction type (optional)
            status: Filter by transaction status (optional)
            
        Returns:
            List of transaction details
        """
        result = []
        
        with self._transactions_lock:
            if user_id not in self._user_transactions:
                return result
            
            tx_hashes = self._user_transactions[user_id]
            
            for tx_hash in tx_hashes:
                tx = self._transactions.get(tx_hash)
                if not tx:
                    continue
                
                # Apply type filter
                if tx_type and tx['type'] != tx_type.value:
                    continue
                
                # Apply status filter
                if status and tx['status'] != status.value:
                    continue
                
                # Add to result
                result.append(json.loads(json.dumps(tx)))
        
        return result
    
    def add_status_listener(self,
                           tx_hash: str,
                           callback: Callable[[str, str, str, Dict[str, Any]], None],
                           status_filter: Set[TransactionStatus] = None):
        """
        Add a listener for status changes on a specific transaction.
        
        Args:
            tx_hash: Transaction hash to listen for
            callback: Function to call when status changes
            status_filter: Set of statuses to trigger callback for (all if None)
        """
        # Normalize transaction hash
        if not tx_hash.startswith('0x'):
            tx_hash = '0x' + tx_hash
            
        # Convert status filter to values
        status_values = None
        if status_filter:
            status_values = {s.value for s in status_filter}
        
        with self._listeners_lock:
            if tx_hash not in self._status_listeners:
                self._status_listeners[tx_hash] = []
            
            self._status_listeners[tx_hash].append((callback, status_values))
    
    def add_global_listener(self,
                           callback: Callable[[str, str, str, Dict[str, Any]], None],
                           status_filter: Set[TransactionStatus] = None):
        """
        Add a listener for all transaction status changes.
        
        Args:
            callback: Function to call when any transaction status changes
            status_filter: Set of statuses to trigger callback for (all if None)
        """
        # Convert status filter to values
        status_values = None
        if status_filter:
            status_values = {s.value for s in status_filter}
            
        with self._listeners_lock:
            self._global_listeners.append((callback, status_values))
    
    def _notify_listeners(self, tx_hash: str, old_status: str, new_status: str, transaction: Dict[str, Any]):
        """Notify all relevant listeners of a status change"""
        with self._listeners_lock:
            # Call transaction-specific listeners
            if tx_hash in self._status_listeners:
                for callback, status_filter in self._status_listeners[tx_hash]:
                    if status_filter is None or new_status in status_filter:
                        try:
                            callback(tx_hash, old_status, new_status, transaction)
                        except Exception as e:
                            logger.error(f"Error in transaction listener callback: {str(e)}")
            
            # Call global listeners
            for callback, status_filter in self._global_listeners:
                if status_filter is None or new_status in status_filter:
                    try:
                        callback(tx_hash, old_status, new_status, transaction)
                    except Exception as e:
                        logger.error(f"Error in global listener callback: {str(e)}")
    
    def start_status_service(self):
        """Start the background status update service"""
        if self._status_thread and self._status_thread.is_alive():
            logger.warning("Status service is already running")
            return
        
        self._stop_event.clear()
        self._status_thread = threading.Thread(
            target=self._status_update_loop,
            daemon=True
        )
        self._status_thread.start()
        
        # Also ensure the verifier service is running
        self._verifier.start_verification_service()
        
        logger.info("Transaction status service started")
    
    def stop_status_service(self):
        """Stop the background status update service"""
        if not self._status_thread or not self._status_thread.is_alive():
            return
        
        logger.info("Stopping transaction status service")
        self._stop_event.set()
        self._status_thread.join(timeout=5.0)
        
        # Also stop the verifier service
        self._verifier.stop_verification_service()
        
        if self._status_thread.is_alive():
            logger.warning("Status thread didn't stop gracefully")
        else:
            logger.info("Transaction status service stopped")
    
    def _status_update_loop(self):
        """Background loop for updating transaction statuses"""
        while not self._stop_event.is_set():
            try:
                pending_transactions = []
                
                # Collect transactions needing verification
                with self._transactions_lock:
                    # Process transactions that need status updates
                    for status in [
                        TransactionStatus.PENDING.value,
                        TransactionStatus.PROCESSING.value,
                        TransactionStatus.CONFIRMING.value
                    ]:
                        if status in self._status_transactions:
                            pending_transactions.extend([
                                (tx_hash, self._transactions[tx_hash])
                                for tx_hash in self._status_transactions[status]
                                if tx_hash in self._transactions
                            ])
                
                # Process each transaction
                for tx_hash, tx in pending_transactions:
                    if self._stop_event.is_set():
                        break
                    
                    # Skip transactions that are too recent (avoid hammering the blockchain)
                    if tx['updated_at'] > datetime.now() - timedelta(seconds=15):
                        continue
                    
                    # Get latest verification status
                    verification_status, details = self._verifier.verify_transaction(tx_hash)
                    
                    # Map verification status to transaction status
                    new_status = None
                    reason = None
                    
                    if verification_status == VerificationStatus.CONFIRMED:
                        new_status = TransactionStatus.COMPLETED
                        reason = "Transaction confirmed on blockchain"
                    elif verification_status == VerificationStatus.FAILED:
                        new_status = TransactionStatus.FAILED
                        reason = "Transaction failed on blockchain"
                    elif verification_status == VerificationStatus.REJECTED:
                        new_status = TransactionStatus.REJECTED
                        reason = "Transaction rejected by blockchain"
                    elif verification_status == VerificationStatus.INVALID:
                        new_status = TransactionStatus.FAILED
                        reason = "Transaction invalid on blockchain"
                    elif verification_status == VerificationStatus.NOT_FOUND:
                        # Only expire after 24 hours
                        created_at = datetime.fromisoformat(tx['created_at'].isoformat())
                        if datetime.now() - created_at > timedelta(hours=24):
                            new_status = TransactionStatus.EXPIRED
                            reason = "Transaction not found after 24 hours"
                    else:  # PENDING
                        # Update confirming status based on confirmation count
                        if 'confirmations' in details and details['confirmations'] > 0:
                            if tx['status'] != TransactionStatus.CONFIRMING.value:
                                new_status = TransactionStatus.CONFIRMING
                                reason = f"Transaction has {details['confirmations']} confirmations"
                    
                    # Update status if needed
                    if new_status:
                        self.update_transaction_status(tx_hash, new_status, reason)
                    
                # Sleep between update cycles
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in status update loop: {str(e)}")
                time.sleep(60)  # Sleep longer on error
    
    def _load_from_database(self):
        """Load existing transactions from database"""
        try:
            conn = psycopg2.connect(self.db_connection_string)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Load transactions
            cursor.execute("""
                SELECT * FROM blockchain_transactions 
                WHERE created_at > NOW() - INTERVAL '30 days'
            """)
            
            rows = cursor.fetchall()
            
            with self._transactions_lock:
                for row in rows:
                    tx_hash = row['tx_hash']
                    if not tx_hash.startswith('0x'):
                        tx_hash = '0x' + tx_hash
                    
                    # Create transaction object
                    transaction = {
                        'tx_hash': tx_hash,
                        'user_id': row['user_id'],
                        'type': row.get('type', TransactionType.UNKNOWN.value),
                        'status': row.get('status', TransactionStatus.UNKNOWN.value),
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at'],
                        'metadata': row.get('metadata', {}),
                        'history': []
                    }
                    
                    # Load history if available
                    if row.get('status_history'):
                        transaction['history'] = row['status_history']
                    else:
                        # Create initial history entry
                        transaction['history'] = [{
                            'status': transaction['status'],
                            'timestamp': transaction['created_at'].isoformat(),
                            'reason': "Loaded from database"
                        }]
                    
                    # Add to indexes
                    self._transactions[tx_hash] = transaction
                    
                    if transaction['user_id'] not in self._user_transactions:
                        self._user_transactions[transaction['user_id']] = set()
                    self._user_transactions[transaction['user_id']].add(tx_hash)
                    
                    if transaction['type'] not in self._type_transactions:
                        self._type_transactions[transaction['type']] = set()
                    self._type_transactions[transaction['type']].add(tx_hash)
                    
                    if transaction['status'] not in self._status_transactions:
                        self._status_transactions[transaction['status']] = set()
                    self._status_transactions[transaction['status']].add(tx_hash)
            
            logger.info(f"Loaded {len(rows)} transactions from database")
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error loading transactions from database: {str(e)}")
    
    def _save_transaction_to_db(self, transaction: Dict[str, Any]):
        """Save a transaction to the database"""
        try:
            conn = psycopg2.connect(self.db_connection_string)
            cursor = conn.cursor()
            
            # Convert datetime to string for JSON serialization
            tx_data = json.loads(json.dumps(transaction, default=lambda x: x.isoformat() if isinstance(x, datetime) else x))
            
            # Check if transaction exists
            cursor.execute(
                "SELECT COUNT(*) FROM blockchain_transactions WHERE tx_hash = %s",
                (transaction['tx_hash'],)
            )
            
            exists = cursor.fetchone()[0] > 0
            
            if exists:
                # Update existing transaction
                cursor.execute("""
                    UPDATE blockchain_transactions
                    SET status = %s, 
                        updated_at = %s, 
                        metadata = %s,
                        status_history = %s
                    WHERE tx_hash = %s
                """, (
                    transaction['status'],
                    transaction['updated_at'],
                    json.dumps(transaction['metadata']),
                    json.dumps(transaction['history']),
                    transaction['tx_hash']
                ))
            else:
                # Insert new transaction
                cursor.execute("""
                    INSERT INTO blockchain_transactions
                    (tx_hash, from_address, to_address, block_number, value, chain_id, 
                     status, confirmations, user_id, created_at, updated_at, type, metadata, status_history)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    transaction['tx_hash'],
                    transaction['metadata'].get('from_address'),
                    transaction['metadata'].get('to_address'),
                    transaction['metadata'].get('block_number'),
                    transaction['metadata'].get('value'),
                    transaction['metadata'].get('chain_id'),
                    transaction['status'],
                    transaction['metadata'].get('confirmations', 0),
                    transaction['user_id'],
                    transaction['created_at'],
                    transaction['updated_at'],
                    transaction['type'],
                    json.dumps(transaction['metadata']),
                    json.dumps(transaction['history'])
                ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error saving transaction to database: {str(e)}")
    
    def sync_from_blockchain(self, tx_hash: str) -> bool:
        """
        Sync transaction details from blockchain.
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            True if sync was successful, False otherwise
        """
        # Normalize transaction hash
        if not tx_hash.startswith('0x'):
            tx_hash = '0x' + tx_hash
        
        try:
            # Get transaction from blockchain
            verification_status, details = self._verifier.verify_transaction(tx_hash)
            
            with self._transactions_lock:
                # Check if transaction exists
                if tx_hash not in self._transactions:
                    logger.warning(f"Cannot sync non-existent transaction {tx_hash}")
                    return False
                
                # Update blockchain metadata
                transaction = self._transactions[tx_hash]
                transaction['metadata'].update({
                    'from_address': details.get('from'),
                    'to_address': details.get('to'),
                    'block_number': details.get('blockNumber'),
                    'value': details.get('value'),
                    'confirmations': details.get('confirmations', 0),
                    'gas_used': details.get('gasUsed'),
                    'gas_price': details.get('gasPrice'),
                    'blockchain_status': verification_status.value,
                    'last_synced': datetime.now().isoformat(),
                })
                transaction['updated_at'] = datetime.now()
            
            # Save to database
            self._save_transaction_to_db(transaction)
            
            logger.info(f"Synced transaction {tx_hash} from blockchain")
            return True
            
        except Exception as e:
            logger.error(f"Error syncing transaction {tx_hash} from blockchain: {str(e)}")
            return False
    
    def get_transaction_by_criteria(self, 
                                   tx_type: TransactionType = None,
                                   status: TransactionStatus = None,
                                   user_id: int = None,
                                   limit: int = 100,
                                   offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get transactions matching specified criteria.
        
        Args:
            tx_type: Filter by transaction type (optional)
            status: Filter by transaction status (optional)
            user_id: Filter by user ID (optional)
            limit: Maximum number of transactions to return
            offset: Number of transactions to skip
            
        Returns:
            List of transaction details
        """
        result = []
        
        try:
            conn = psycopg2.connect(self.db_connection_string)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Build query
            query = "SELECT * FROM blockchain_transactions WHERE 1=1"
            params = []
            
            if tx_type:
                query += " AND type = %s"
                params.append(tx_type.value)
            
            if status:
                query += " AND status = %s"
                params.append(status.value)
            
            if user_id is not None:
                query += " AND user_id = %s"
                params.append(user_id)
            
            query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # Convert to transaction objects
            for row in rows:
                tx_hash = row['tx_hash']
                if not tx_hash.startswith('0x'):
                    tx_hash = '0x' + tx_hash
                
                # Create transaction object
                transaction = {
                    'tx_hash': tx_hash,
                    'user_id': row['user_id'],
                    'type': row.get('type', TransactionType.UNKNOWN.value),
                    'status': row.get('status', TransactionStatus.UNKNOWN.value),
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at'],
                    'metadata': row.get('metadata', {}),
                    'history': row.get('status_history', [])
                }
                
                result.append(transaction)
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error getting transactions by criteria: {str(e)}")
        
        return result


# Singleton instance
_status_manager_instance = None


def get_status_manager(reset=False) -> TransactionStatusManager:
    """
    Get global transaction status manager instance.
    
    Args:
        reset: Whether to create a new instance if one exists
        
    Returns:
        TransactionStatusManager instance
    """
    global _status_manager_instance
    
    if _status_manager_instance is None or reset:
        _status_manager_instance = TransactionStatusManager(
            db_connection_string=os.getenv('DATABASE_URL'),
            auto_start=True
        )
        
    return _status_manager_instance 