"""
Transaction monitoring and processing module for blockchain deposits.

This module provides functionality to monitor blockchain transactions to user
deposit addresses, process them according to confirmation thresholds, and
update user balances accordingly.
"""

import os
import time
import json
import logging
import threading
import datetime
import psycopg2
from enum import Enum, auto
from typing import List, Dict, Optional, Tuple, Any, Union
from web3 import Web3
from web3.exceptions import TransactionNotFound, BlockNotFound
from dotenv import load_dotenv

from .wallet import get_wallet_by_address, validate_address

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('transaction_monitor')

# Load environment variables
load_dotenv()

# Transaction status constants
class TxStatus(Enum):
    PENDING = "pending"
    CONFIRMING = "confirming"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    PROCESSED = "processed"

# Chain identifiers
class Chain(Enum):
    BSC = 56
    BSC_TESTNET = 97

# RPC URLs for different chains
RPC_ENDPOINTS = {
    Chain.BSC: os.getenv('BSC_RPC_URL', 'https://bsc-dataseed.binance.org'),
    Chain.BSC_TESTNET: os.getenv('BSC_TESTNET_RPC_URL', 'https://data-seed-prebsc-1-s1.binance.org:8545')
}

# Confirmation thresholds for different chains
CONFIRMATION_THRESHOLD = {
    Chain.BSC: int(os.getenv('BSC_CONFIRMATION_THRESHOLD', 15)),
    Chain.BSC_TESTNET: int(os.getenv('BSC_TESTNET_CONFIRMATION_THRESHOLD', 6))
}

# Database connection parameters
DB_PARAMS = {
    'dbname': os.getenv('DB_NAME', 'forex_trading'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432')
}

class TransactionProcessor:
    """
    Handles monitoring and processing of blockchain transactions.
    
    This class is responsible for scanning the blockchain for new transactions
    to monitored addresses, tracking confirmation status, and processing
    confirmed transactions to update user balances.
    """
    
    def __init__(self, chain: Chain = Chain.BSC, polling_interval: int = 60):
        """
        Initialize the transaction processor.
        
        Args:
            chain: The blockchain network to monitor
            polling_interval: How often to check for new transactions in seconds
        """
        self.chain = chain
        self.polling_interval = polling_interval
        self.web3 = None
        self.running = False
        self.last_processed_block = 0
        self.monitor_thread = None
        self._initialize_web3()
    
    def _initialize_web3(self) -> None:
        """Initialize Web3 connection to the blockchain."""
        try:
            rpc_url = RPC_ENDPOINTS[self.chain]
            self.web3 = Web3(Web3.HTTPProvider(rpc_url))
            if not self.web3.is_connected():
                logger.error(f"Failed to connect to {self.chain.name} network at {rpc_url}")
                raise ConnectionError(f"Cannot connect to {self.chain.name}")
            logger.info(f"Successfully connected to {self.chain.name} network")
        except Exception as e:
            logger.error(f"Error initializing Web3 connection: {str(e)}")
            raise
    
    def _get_db_connection(self):
        """Get a connection to the database."""
        try:
            return psycopg2.connect(**DB_PARAMS)
        except Exception as e:
            logger.error(f"Database connection error: {str(e)}")
            raise
    
    def _get_last_processed_block(self) -> int:
        """
        Get the last processed block from the database.
        
        Returns:
            int: The block number of the last processed block
        """
        try:
            connection = self._get_db_connection()
            cursor = connection.cursor()
            cursor.execute(
                "SELECT block_number FROM blockchain_sync_status WHERE chain_id = %s",
                (self.chain.value,)
            )
            result = cursor.fetchone()
            cursor.close()
            connection.close()
            
            if result:
                return result[0]
            else:
                # If no record exists, use current block - 5000 as default
                # This prevents scanning the entire blockchain history
                current_block = self.web3.eth.block_number
                default_block = max(current_block - 5000, 0)
                self._update_last_processed_block(default_block)
                return default_block
                
        except Exception as e:
            logger.error(f"Error getting last processed block: {str(e)}")
            # If there's an error, use a safe default
            return self.web3.eth.block_number - 100
    
    def _update_last_processed_block(self, block_number: int) -> None:
        """
        Update the last processed block in the database.
        
        Args:
            block_number: The block number to record as last processed
        """
        try:
            connection = self._get_db_connection()
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO blockchain_sync_status (chain_id, block_number, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (chain_id) DO UPDATE
                SET block_number = %s, updated_at = %s
                """,
                (self.chain.value, block_number, datetime.datetime.now(),
                 block_number, datetime.datetime.now())
            )
            connection.commit()
            cursor.close()
            connection.close()
            self.last_processed_block = block_number
        except Exception as e:
            logger.error(f"Error updating last processed block: {str(e)}")
    
    def _get_monitored_addresses(self) -> List[Dict[str, Any]]:
        """
        Get the list of user wallet addresses to monitor.
        
        Returns:
            List of dictionaries with address and user_id
        """
        try:
            connection = self._get_db_connection()
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT address, user_id FROM wallets
                WHERE chain_id = %s AND status = 'active'
                """,
                (self.chain.value,)
            )
            results = cursor.fetchall()
            cursor.close()
            connection.close()
            
            return [{'address': row[0], 'user_id': row[1]} for row in results]
        except Exception as e:
            logger.error(f"Error getting monitored addresses: {str(e)}")
            return []
    
    def _process_transaction_receipts(self) -> None:
        """
        Check unprocessed transactions and update their status based on confirmations.
        """
        try:
            connection = self._get_db_connection()
            cursor = connection.cursor()
            
            # Get unprocessed transactions
            cursor.execute(
                """
                SELECT id, tx_hash FROM blockchain_transactions
                WHERE chain_id = %s AND status IN (%s, %s)
                """,
                (self.chain.value, TxStatus.PENDING.value, TxStatus.CONFIRMING.value)
            )
            transactions = cursor.fetchall()
            
            current_block = self.web3.eth.block_number
            
            for tx_id, tx_hash in transactions:
                try:
                    receipt = self.web3.eth.get_transaction_receipt(tx_hash)
                    
                    if receipt is None:
                        # Transaction still pending
                        continue
                        
                    tx_block_number = receipt.blockNumber
                    confirmations = current_block - tx_block_number
                    
                    if receipt.status == 1:  # Success
                        if confirmations >= CONFIRMATION_THRESHOLD[self.chain]:
                            # Transaction is confirmed
                            cursor.execute(
                                """
                                UPDATE blockchain_transactions
                                SET status = %s, confirmations = %s, updated_at = %s
                                WHERE id = %s
                                """,
                                (TxStatus.CONFIRMED.value, confirmations, 
                                 datetime.datetime.now(), tx_id)
                            )
                            logger.info(f"Transaction {tx_hash} confirmed with {confirmations} confirmations")
                        else:
                            # Transaction is confirming
                            cursor.execute(
                                """
                                UPDATE blockchain_transactions
                                SET status = %s, confirmations = %s, updated_at = %s
                                WHERE id = %s
                                """,
                                (TxStatus.CONFIRMING.value, confirmations, 
                                 datetime.datetime.now(), tx_id)
                            )
                    else:
                        # Transaction failed
                        cursor.execute(
                            """
                            UPDATE blockchain_transactions
                            SET status = %s, confirmations = %s, updated_at = %s
                            WHERE id = %s
                            """,
                            (TxStatus.FAILED.value, confirmations, 
                             datetime.datetime.now(), tx_id)
                        )
                        logger.warning(f"Transaction {tx_hash} failed")
                
                except TransactionNotFound:
                    logger.warning(f"Transaction {tx_hash} not found on the blockchain")
                    
                except Exception as e:
                    logger.error(f"Error processing transaction {tx_hash}: {str(e)}")
            
            connection.commit()
            cursor.close()
            connection.close()
            
        except Exception as e:
            logger.error(f"Error in processing transaction receipts: {str(e)}")
    
    def _process_confirmed_transactions(self) -> None:
        """
        Process confirmed transactions to update user balances.
        """
        try:
            connection = self._get_db_connection()
            cursor = connection.cursor()
            
            # Get confirmed but unprocessed transactions
            cursor.execute(
                """
                SELECT id, tx_hash, to_address, value, user_id 
                FROM blockchain_transactions
                WHERE chain_id = %s AND status = %s
                """,
                (self.chain.value, TxStatus.CONFIRMED.value)
            )
            transactions = cursor.fetchall()
            
            for tx_id, tx_hash, to_address, value, user_id in transactions:
                try:
                    # Update user balance
                    cursor.execute(
                        """
                        UPDATE accounts
                        SET balance = balance + %s, updated_at = %s
                        WHERE user_id = %s
                        """,
                        (value, datetime.datetime.now(), user_id)
                    )
                    
                    # Log the deposit
                    cursor.execute(
                        """
                        INSERT INTO account_transactions
                        (user_id, type, amount, reference, created_at)
                        VALUES (%s, 'deposit', %s, %s, %s)
                        """,
                        (user_id, value, tx_hash, datetime.datetime.now())
                    )
                    
                    # Mark transaction as processed
                    cursor.execute(
                        """
                        UPDATE blockchain_transactions
                        SET status = %s, updated_at = %s
                        WHERE id = %s
                        """,
                        (TxStatus.PROCESSED.value, datetime.datetime.now(), tx_id)
                    )
                    
                    logger.info(f"Processed deposit of {value} for user {user_id} from transaction {tx_hash}")
                    
                except Exception as e:
                    logger.error(f"Error processing confirmed transaction {tx_hash}: {str(e)}")
            
            connection.commit()
            cursor.close()
            connection.close()
            
        except Exception as e:
            logger.error(f"Error in processing confirmed transactions: {str(e)}")
    
    def _scan_for_new_transactions(self) -> None:
        """
        Scan blockchain for new transactions to monitored addresses.
        """
        try:
            monitored_addresses = self._get_monitored_addresses()
            if not monitored_addresses:
                logger.info("No addresses to monitor")
                return
                
            current_block = self.web3.eth.block_number
            from_block = self.last_processed_block + 1
            to_block = min(current_block, from_block + 100)  # Process in chunks
            
            # Don't scan if we're already at the current block
            if from_block > current_block:
                return
                
            logger.info(f"Scanning blocks {from_block} to {to_block}")
            
            # Create set of monitored addresses for faster lookup
            monitored_address_set = {addr['address'].lower(): addr['user_id'] 
                                    for addr in monitored_addresses}
            
            # Process each block
            for block_num in range(from_block, to_block + 1):
                try:
                    block = self.web3.eth.get_block(block_num, full_transactions=True)
                    
                    for tx in block.transactions:
                        # Check if the transaction is to a monitored address
                        if hasattr(tx, 'to') and tx.to and tx.to.lower() in monitored_address_set:
                            to_address = tx.to.lower()
                            user_id = monitored_address_set[to_address]
                            
                            # Store the transaction
                            self._store_transaction(
                                tx_hash=tx.hash.hex(),
                                from_address=tx['from'],
                                to_address=to_address,
                                block_number=block_num,
                                value=self.web3.from_wei(tx.value, 'ether'),
                                user_id=user_id
                            )
                    
                except BlockNotFound:
                    logger.warning(f"Block {block_num} not found")
                except Exception as e:
                    logger.error(f"Error processing block {block_num}: {str(e)}")
            
            # Update the last processed block
            self._update_last_processed_block(to_block)
            
        except Exception as e:
            logger.error(f"Error scanning for new transactions: {str(e)}")
    
    def _store_transaction(self, tx_hash: str, from_address: str, to_address: str, 
                          block_number: int, value: float, user_id: int) -> None:
        """
        Store a new transaction in the database.
        
        Args:
            tx_hash: Transaction hash
            from_address: Sender address
            to_address: Recipient address
            block_number: Block number containing the transaction
            value: Transaction amount in native token
            user_id: User ID of the recipient
        """
        try:
            connection = self._get_db_connection()
            cursor = connection.cursor()
            
            # Check if transaction already exists
            cursor.execute(
                "SELECT id FROM blockchain_transactions WHERE tx_hash = %s",
                (tx_hash,)
            )
            
            if cursor.fetchone():
                cursor.close()
                connection.close()
                return  # Transaction already recorded
            
            # Insert new transaction
            cursor.execute(
                """
                INSERT INTO blockchain_transactions
                (tx_hash, from_address, to_address, block_number, value, 
                chain_id, status, confirmations, user_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (tx_hash, from_address, to_address, block_number, value,
                 self.chain.value, TxStatus.PENDING.value, 0, user_id,
                 datetime.datetime.now(), datetime.datetime.now())
            )
            
            connection.commit()
            cursor.close()
            connection.close()
            
            logger.info(f"Stored new transaction {tx_hash} to {to_address} with value {value}")
            
        except Exception as e:
            logger.error(f"Error storing transaction {tx_hash}: {str(e)}")
    
    def _monitor_loop(self) -> None:
        """
        Main monitoring loop that runs periodically.
        """
        while self.running:
            try:
                # Get the last processed block
                if self.last_processed_block == 0:
                    self.last_processed_block = self._get_last_processed_block()
                
                # Process existing transactions (update confirmations)
                self._process_transaction_receipts()
                
                # Process confirmed transactions (update balances)
                self._process_confirmed_transactions()
                
                # Scan for new transactions
                self._scan_for_new_transactions()
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                
            # Sleep for the polling interval
            time.sleep(self.polling_interval)
    
    def start(self) -> None:
        """
        Start the transaction monitoring service.
        """
        if self.running:
            logger.warning("Transaction processor is already running")
            return
            
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        logger.info(f"Transaction processor started for {self.chain.name}")
    
    def stop(self) -> None:
        """
        Stop the transaction monitoring service.
        """
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)
            logger.info("Transaction processor stopped")

# Utility functions

def get_transaction_by_hash(tx_hash: str) -> Optional[Dict[str, Any]]:
    """
    Get transaction details by hash.
    
    Args:
        tx_hash: Transaction hash to look up
        
    Returns:
        Transaction details or None if not found
    """
    try:
        connection = psycopg2.connect(**DB_PARAMS)
        cursor = connection.cursor()
        
        cursor.execute(
            """
            SELECT tx_hash, from_address, to_address, value, block_number,
                   chain_id, status, confirmations, created_at
            FROM blockchain_transactions
            WHERE tx_hash = %s
            """,
            (tx_hash,)
        )
        
        result = cursor.fetchone()
        cursor.close()
        connection.close()
        
        if result:
            return {
                'tx_hash': result[0],
                'from_address': result[1],
                'to_address': result[2],
                'value': float(result[3]),
                'block_number': result[4],
                'chain_id': result[5],
                'status': result[6],
                'confirmations': result[7],
                'created_at': result[8].isoformat() if result[8] else None
            }
        return None
        
    except Exception as e:
        logger.error(f"Error getting transaction by hash: {str(e)}")
        return None

def get_user_transactions(user_id: int, limit: int = 50, 
                         offset: int = 0) -> List[Dict[str, Any]]:
    """
    Get transactions for a specific user.
    
    Args:
        user_id: User ID to get transactions for
        limit: Maximum number of transactions to return
        offset: Offset for pagination
        
    Returns:
        List of transaction details
    """
    try:
        connection = psycopg2.connect(**DB_PARAMS)
        cursor = connection.cursor()
        
        cursor.execute(
            """
            SELECT tx_hash, from_address, to_address, value, block_number,
                   chain_id, status, confirmations, created_at
            FROM blockchain_transactions
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, limit, offset)
        )
        
        results = cursor.fetchall()
        cursor.close()
        connection.close()
        
        transactions = []
        for result in results:
            transactions.append({
                'tx_hash': result[0],
                'from_address': result[1],
                'to_address': result[2],
                'value': float(result[3]),
                'block_number': result[4],
                'chain_id': result[5],
                'status': result[6],
                'confirmations': result[7],
                'created_at': result[8].isoformat() if result[8] else None
            })
        
        return transactions
        
    except Exception as e:
        logger.error(f"Error getting user transactions: {str(e)}")
        return []

def get_deposit_stats(user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Get deposit statistics.
    
    Args:
        user_id: Optional user ID to filter stats for a specific user
        
    Returns:
        Dictionary with deposit statistics
    """
    try:
        connection = psycopg2.connect(**DB_PARAMS)
        cursor = connection.cursor()
        
        if user_id:
            cursor.execute(
                """
                SELECT COUNT(*), SUM(value), MAX(value), MIN(value), AVG(value)
                FROM blockchain_transactions
                WHERE user_id = %s AND status = %s
                """,
                (user_id, TxStatus.PROCESSED.value)
            )
        else:
            cursor.execute(
                """
                SELECT COUNT(*), SUM(value), MAX(value), MIN(value), AVG(value)
                FROM blockchain_transactions
                WHERE status = %s
                """,
                (TxStatus.PROCESSED.value,)
            )
        
        result = cursor.fetchone()
        cursor.close()
        connection.close()
        
        if result:
            return {
                'count': result[0] or 0,
                'total_value': float(result[1]) if result[1] else 0.0,
                'max_value': float(result[2]) if result[2] else 0.0,
                'min_value': float(result[3]) if result[3] else 0.0,
                'avg_value': float(result[4]) if result[4] else 0.0
            }
        return {
            'count': 0,
            'total_value': 0.0,
            'max_value': 0.0,
            'min_value': 0.0,
            'avg_value': 0.0
        }
        
    except Exception as e:
        logger.error(f"Error getting deposit stats: {str(e)}")
        return {
            'count': 0,
            'total_value': 0.0,
            'max_value': 0.0,
            'min_value': 0.0,
            'avg_value': 0.0
        }

def check_address_deposits(address: str) -> List[Dict[str, Any]]:
    """
    Get deposits for a specific address.
    
    Args:
        address: Wallet address to check
        
    Returns:
        List of deposits for the address
    """
    if not validate_address(address):
        logger.error(f"Invalid address format: {address}")
        return []
        
    try:
        connection = psycopg2.connect(**DB_PARAMS)
        cursor = connection.cursor()
        
        cursor.execute(
            """
            SELECT tx_hash, from_address, value, status, created_at
            FROM blockchain_transactions
            WHERE to_address = %s
            ORDER BY created_at DESC
            """,
            (address.lower(),)
        )
        
        results = cursor.fetchall()
        cursor.close()
        connection.close()
        
        deposits = []
        for result in results:
            deposits.append({
                'tx_hash': result[0],
                'from_address': result[1],
                'value': float(result[2]),
                'status': result[3],
                'created_at': result[4].isoformat() if result[4] else None
            })
        
        return deposits
        
    except Exception as e:
        logger.error(f"Error checking address deposits: {str(e)}")
        return [] 