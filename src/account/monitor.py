"""
Blockchain Transaction Monitor Module

This module provides functionality for monitoring blockchain transactions,
processing deposits to user wallets, and synchronizing balances.
"""

import os
import time
import logging
import threading
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from decimal import Decimal

import psycopg2
from web3 import Web3
from web3.middleware import geth_poa_middleware

from .wallet import Wallet, WalletType, get_user_wallets, validate_address
from ..config import get_config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TransactionMonitor:
    """
    Monitors blockchain transactions and processes deposits to user wallets.
    
    This class provides methods to:
    - Listen for incoming blockchain transactions
    - Process transactions based on confirmation thresholds
    - Update user balances when deposits are confirmed
    - Handle network disruptions
    - Log unusual transaction patterns
    """
    
    def __init__(self, chain_id: int = 56, poll_interval: int = 60, confirmations_required: int = 12):
        """
        Initialize the transaction monitor.
        
        Args:
            chain_id: The blockchain network ID (default: 56 for BSC mainnet)
            poll_interval: How often to check for new blocks in seconds
            confirmations_required: Number of confirmations required for a transaction to be considered final
        """
        self.chain_id = chain_id
        self.poll_interval = poll_interval
        self.confirmations_required = confirmations_required
        self.running = False
        self.monitor_thread = None
        
        # Load configuration
        config = get_config()
        
        # Setup Web3 connection
        if chain_id == 56:  # BSC Mainnet
            rpc_url = config.get('BSC_RPC_URL', 'https://bsc-dataseed.binance.org/')
        elif chain_id == 97:  # BSC Testnet
            rpc_url = config.get('BSC_TESTNET_RPC_URL', 'https://data-seed-prebsc-1-s1.binance.org:8545/')
        else:
            raise ValueError(f"Unsupported chain_id: {chain_id}")
        
        self.web3 = Web3(Web3.HTTPProvider(rpc_url))
        # Add middleware for POA chains like BSC
        self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # Validate connection
        if not self.web3.is_connected():
            logger.error(f"Failed to connect to blockchain RPC: {rpc_url}")
            raise ConnectionError(f"Could not connect to blockchain RPC: {rpc_url}")
        
        logger.info(f"Connected to blockchain - Chain ID: {self.web3.eth.chain_id}")
        
        # Database connection params
        self.db_params = {
            'dbname': config.get('DB_NAME', 'forex'),
            'user': config.get('DB_USER', 'postgres'),
            'password': config.get('DB_PASSWORD', ''),
            'host': config.get('DB_HOST', 'localhost'),
            'port': config.get('DB_PORT', '5432')
        }
        
        # Cache of user addresses for quick lookup
        self.user_addresses = {}
        self._load_user_addresses()
    
    def _get_db_connection(self):
        """Get a connection to the database."""
        try:
            return psycopg2.connect(**self.db_params)
        except Exception as e:
            logger.error(f"Database connection error: {str(e)}")
            raise
    
    def _load_user_addresses(self):
        """Load all user addresses into memory for quick lookup."""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            query = """
            SELECT address, user_id 
            FROM wallets 
            WHERE wallet_type = %s
            """
            
            cursor.execute(query, (WalletType.BEP20.value,))
            results = cursor.fetchall()
            
            self.user_addresses = {row[0].lower(): row[1] for row in results}
            logger.info(f"Loaded {len(self.user_addresses)} user addresses for monitoring")
            
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to load user addresses: {str(e)}")
    
    def _get_last_processed_block(self) -> int:
        """Get the last processed block number from the database."""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            query = """
            SELECT block_number 
            FROM blockchain_sync_status 
            WHERE chain_id = %s
            """
            
            cursor.execute(query, (self.chain_id,))
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if result:
                return result[0]
            else:
                # If no record exists, insert a new one with the current block number
                current_block = self.web3.eth.block_number
                self._update_last_processed_block(current_block - 100)  # Start 100 blocks back for safety
                return current_block - 100
        except Exception as e:
            logger.error(f"Failed to get last processed block: {str(e)}")
            # Default to current block - 100 if there's an error
            return self.web3.eth.block_number - 100
    
    def _update_last_processed_block(self, block_number: int):
        """Update the last processed block number in the database."""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            query = """
            INSERT INTO blockchain_sync_status (chain_id, block_number, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (chain_id) 
            DO UPDATE SET block_number = %s, updated_at = %s
            """
            
            now = datetime.now()
            cursor.execute(query, (self.chain_id, block_number, now, block_number, now))
            conn.commit()
            
            cursor.close()
            conn.close()
            
            logger.debug(f"Updated last processed block to {block_number}")
        except Exception as e:
            logger.error(f"Failed to update last processed block: {str(e)}")
    
    def _process_block(self, block_number: int):
        """
        Process a single block and extract transactions to monitored addresses.
        
        Args:
            block_number: The block number to process
        """
        try:
            # Get block with transactions
            block = self.web3.eth.get_block(block_number, full_transactions=True)
            
            if not block or not hasattr(block, 'transactions'):
                logger.warning(f"No transactions found in block {block_number}")
                return
            
            relevant_txs = []
            
            # Process each transaction in the block
            for tx in block.transactions:
                # Check if the transaction is to one of our monitored addresses
                to_address = tx.get('to')
                if not to_address:
                    continue  # Skip contract creation transactions
                
                to_address = to_address.lower()
                
                if to_address in self.user_addresses:
                    user_id = self.user_addresses[to_address]
                    
                    # Convert transaction to our format
                    processed_tx = {
                        'tx_hash': tx.get('hash').hex(),
                        'from_address': tx.get('from').lower(),
                        'to_address': to_address,
                        'block_number': block_number,
                        'value': Decimal(tx.get('value')) / Decimal(10**18),  # Convert from wei to ETH/BNB
                        'chain_id': self.chain_id,
                        'status': 'pending',
                        'confirmations': 0,
                        'user_id': user_id,
                        'created_at': datetime.now()
                    }
                    
                    relevant_txs.append(processed_tx)
            
            # Store relevant transactions in database
            if relevant_txs:
                self._store_transactions(relevant_txs)
                logger.info(f"Processed block {block_number}, found {len(relevant_txs)} relevant transactions")
            else:
                logger.debug(f"Processed block {block_number}, no relevant transactions found")
                
        except Exception as e:
            logger.error(f"Error processing block {block_number}: {str(e)}")
    
    def _store_transactions(self, transactions: List[Dict[str, Any]]):
        """
        Store transactions in the database.
        
        Args:
            transactions: List of transaction dictionaries to store
        """
        if not transactions:
            return
        
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Insert transactions
            for tx in transactions:
                query = """
                INSERT INTO blockchain_transactions 
                (tx_hash, from_address, to_address, block_number, value, chain_id, status, confirmations, user_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tx_hash) DO NOTHING
                """
                
                now = datetime.now()
                cursor.execute(query, (
                    tx['tx_hash'],
                    tx['from_address'],
                    tx['to_address'],
                    tx['block_number'],
                    tx['value'],
                    tx['chain_id'],
                    tx['status'],
                    tx['confirmations'],
                    tx['user_id'],
                    tx['created_at'],
                    now
                ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error storing transactions: {str(e)}")
    
    def _update_transaction_confirmations(self):
        """Update confirmation counts for pending transactions."""
        try:
            current_block = self.web3.eth.block_number
            
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Get all pending transactions
            query = """
            SELECT tx_hash, block_number, user_id, value
            FROM blockchain_transactions
            WHERE status = 'pending' AND chain_id = %s
            """
            
            cursor.execute(query, (self.chain_id,))
            pending_txs = cursor.fetchall()
            
            confirmed_txs = []
            
            for tx_hash, block_number, user_id, value in pending_txs:
                # Calculate confirmations
                confirmations = current_block - block_number + 1
                
                # Update confirmations in database
                update_query = """
                UPDATE blockchain_transactions
                SET confirmations = %s, updated_at = %s
                WHERE tx_hash = %s
                """
                
                cursor.execute(update_query, (confirmations, datetime.now(), tx_hash))
                
                # Check if transaction has enough confirmations
                if confirmations >= self.confirmations_required:
                    # Mark as confirmed
                    confirm_query = """
                    UPDATE blockchain_transactions
                    SET status = 'confirmed', updated_at = %s
                    WHERE tx_hash = %s
                    """
                    
                    cursor.execute(confirm_query, (datetime.now(), tx_hash))
                    
                    # Add to list for balance update
                    confirmed_txs.append((tx_hash, user_id, value))
            
            conn.commit()
            
            # Process confirmed transactions
            if confirmed_txs:
                logger.info(f"Processing {len(confirmed_txs)} newly confirmed transactions")
                for tx_hash, user_id, value in confirmed_txs:
                    self._process_deposit(tx_hash, user_id, value, cursor)
                
                conn.commit()
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error updating transaction confirmations: {str(e)}")
    
    def _process_deposit(self, tx_hash: str, user_id: int, amount: Decimal, cursor):
        """
        Process a confirmed deposit transaction.
        
        Args:
            tx_hash: The transaction hash
            user_id: The user ID to credit
            amount: The amount to credit
            cursor: Database cursor for transaction
        """
        try:
            # Insert account transaction
            query = """
            INSERT INTO account_transactions
            (user_id, type, amount, reference, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """
            
            cursor.execute(query, (
                user_id,
                'deposit',
                amount,
                tx_hash,
                datetime.now()
            ))
            
            # Update user balance
            balance_query = """
            UPDATE users
            SET balance = balance + %s, updated_at = %s
            WHERE id = %s
            """
            
            cursor.execute(balance_query, (amount, datetime.now(), user_id))
            
            logger.info(f"Processed deposit: User {user_id}, Amount {amount}, Tx {tx_hash}")
            
        except Exception as e:
            logger.error(f"Error processing deposit for tx {tx_hash}: {str(e)}")
            raise
    
    def _monitor_loop(self):
        """Main monitoring loop that runs in a separate thread."""
        logger.info(f"Starting blockchain monitor for chain ID {self.chain_id}")
        
        while self.running:
            try:
                # Get current block and last processed block
                current_block = self.web3.eth.block_number
                last_processed_block = self._get_last_processed_block()
                
                # Process new blocks
                if current_block > last_processed_block:
                    blocks_to_process = min(current_block - last_processed_block, 100)  # Limit to 100 blocks per iteration
                    logger.info(f"Processing {blocks_to_process} new blocks from {last_processed_block + 1} to {last_processed_block + blocks_to_process}")
                    
                    for block_num in range(last_processed_block + 1, last_processed_block + blocks_to_process + 1):
                        self._process_block(block_num)
                    
                    # Update last processed block
                    self._update_last_processed_block(last_processed_block + blocks_to_process)
                
                # Update confirmations for pending transactions
                self._update_transaction_confirmations()
                
                # Refresh user addresses occasionally
                if int(time.time()) % 300 == 0:  # Every 5 minutes
                    self._load_user_addresses()
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {str(e)}")
            
            # Sleep until next poll
            time.sleep(self.poll_interval)
    
    def start(self):
        """Start the blockchain monitor."""
        if self.running:
            logger.warning("Monitor is already running")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        logger.info("Blockchain transaction monitor started")
    
    def stop(self):
        """Stop the blockchain monitor."""
        if not self.running:
            logger.warning("Monitor is not running")
            return
        
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)
        
        logger.info("Blockchain transaction monitor stopped")
    
    def check_transaction_status(self, tx_hash: str) -> Dict[str, Any]:
        """
        Check the status of a specific transaction.
        
        Args:
            tx_hash: The transaction hash to check
            
        Returns:
            Dictionary with transaction details
        """
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            query = """
            SELECT * FROM blockchain_transactions
            WHERE tx_hash = %s
            """
            
            cursor.execute(query, (tx_hash,))
            columns = [desc[0] for desc in cursor.description]
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if result:
                # Convert to dictionary
                tx_info = dict(zip(columns, result))
                return tx_info
            else:
                # If not in our database, try to get from blockchain
                try:
                    tx = self.web3.eth.get_transaction(tx_hash)
                    if tx:
                        return {
                            'tx_hash': tx_hash,
                            'from_address': tx.get('from').lower(),
                            'to_address': tx.get('to').lower() if tx.get('to') else None,
                            'block_number': tx.get('blockNumber'),
                            'value': Decimal(tx.get('value')) / Decimal(10**18),
                            'status': 'external',
                            'chain_id': self.chain_id
                        }
                except:
                    pass
                
                return {'tx_hash': tx_hash, 'status': 'not_found'}
        except Exception as e:
            logger.error(f"Error checking transaction status for {tx_hash}: {str(e)}")
            return {'tx_hash': tx_hash, 'status': 'error', 'error': str(e)}
    
    def get_user_deposits(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get deposits for a specific user.
        
        Args:
            user_id: The user ID to get deposits for
            limit: Maximum number of deposits to return
            
        Returns:
            List of deposit transactions
        """
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            query = """
            SELECT bt.tx_hash, bt.from_address, bt.to_address, bt.block_number, 
                   bt.value, bt.status, bt.confirmations, bt.created_at
            FROM blockchain_transactions bt
            WHERE bt.user_id = %s
            ORDER BY bt.created_at DESC
            LIMIT %s
            """
            
            cursor.execute(query, (user_id, limit))
            columns = [desc[0] for desc in cursor.description]
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            deposits = []
            for row in results:
                deposits.append(dict(zip(columns, row)))
            
            return deposits
        except Exception as e:
            logger.error(f"Error getting deposits for user {user_id}: {str(e)}")
            return []
    
    def check_unusual_activity(self, threshold_amount: Decimal = Decimal('10.0'), 
                               time_window_hours: int = 24) -> List[Dict[str, Any]]:
        """
        Check for unusual deposit patterns.
        
        Args:
            threshold_amount: Minimum amount to consider unusual
            time_window_hours: Time window to check for patterns
            
        Returns:
            List of unusual transactions
        """
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            query = """
            SELECT bt.tx_hash, bt.from_address, bt.to_address, bt.value, 
                   bt.user_id, bt.created_at, u.username
            FROM blockchain_transactions bt
            JOIN users u ON bt.user_id = u.id
            WHERE bt.created_at > NOW() - INTERVAL %s HOUR
            AND bt.value >= %s
            ORDER BY bt.value DESC
            """
            
            cursor.execute(query, (time_window_hours, threshold_amount))
            columns = [desc[0] for desc in cursor.description]
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            unusual_txs = []
            for row in results:
                unusual_txs.append(dict(zip(columns, row)))
            
            return unusual_txs
        except Exception as e:
            logger.error(f"Error checking for unusual activity: {str(e)}")
            return []

def get_monitor(chain_id: int = 56) -> TransactionMonitor:
    """
    Factory function to get or create a transaction monitor.
    
    Args:
        chain_id: Blockchain network ID
        
    Returns:
        TransactionMonitor instance
    """
    # This could be enhanced to maintain a singleton per chain_id
    return TransactionMonitor(chain_id=chain_id) 