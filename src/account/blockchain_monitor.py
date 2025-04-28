"""
Blockchain Transaction Monitoring System

This module implements a system for monitoring blockchain transactions
to user deposit addresses. It includes:
- A blockchain listener that watches for transactions
- Transaction verification with configurable confirmation thresholds
- A processing queue for handling deposits
- Balance synchronization between blockchain and database
"""

import os
import sys
import json
import time
import logging
import threading
import queue
from typing import Dict, List, Set, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from pathlib import Path
from web3 import Web3
from web3.exceptions import BlockNotFound, TransactionNotFound
import psycopg2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('blockchain_monitor')

# Import our modules
try:
    from src.db import get_db_connection
    from src.account.wallet import get_all_wallet_addresses, update_wallet_balance
except ImportError:
    # Handle relative imports when running as standalone
    current_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    project_root = current_dir.parent.parent
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    from src.db import get_db_connection
    from src.account.wallet import get_all_wallet_addresses, update_wallet_balance


class TransactionProcessor:
    """Processes blockchain transactions and updates user balances."""
    
    def __init__(self, config_path: str = "config/monitor_settings.json"):
        """
        Initialize the transaction processor.
        
        Args:
            config_path: Path to the configuration file
        """
        self.config = self._load_config(config_path)
        self.network = self._get_network_config()
        self.w3 = self._initialize_web3()
        self.tx_queue = queue.Queue()
        self.user_addresses = set()
        self.running = False
        self.last_processed_block = self._get_last_processed_block()
        self.retry_count = 0
        self.syncing = False
        self.confirmation_threshold = self.config["monitoring"]["confirmation_threshold"]
        
        # Initialize threading locks
        self.db_lock = threading.Lock()
        self.address_lock = threading.Lock()
        
        # Create worker threads
        self.listener_thread = None
        self.processor_thread = None
        self.balance_sync_thread = None
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """
        Load configuration from a JSON file.
        
        Args:
            config_path: Path to the configuration file
            
        Returns:
            Configuration dictionary
        """
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"Loaded configuration from {config_path}")
            return config
        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            # Use default configuration
            return {
                "network": {
                    "bsc_mainnet": {
                        "rpc_url": "https://bsc-dataseed.binance.org/",
                        "chain_id": 56,
                        "block_time": 3,
                        "confirmation_blocks": 12,
                        "retry_interval": 5,
                        "max_retries": 5
                    }
                },
                "monitoring": {
                    "enabled": True,
                    "polling_interval": 30,
                    "batch_size": 100,
                    "log_level": "INFO",
                    "confirmation_threshold": 12,
                    "max_blocks_per_batch": 50,
                    "alert_on_reorg": True,
                    "balance_check_interval": 900
                },
                "database": {
                    "batch_size": 50,
                    "transaction_retention_days": 90,
                    "max_retry_count": 3,
                    "retry_delay_seconds": 5
                }
            }
    
    def _get_network_config(self) -> Dict[str, Any]:
        """
        Get the active network configuration.
        
        Returns:
            Network configuration dictionary
        """
        # Get from environment or use mainnet as default
        network_name = os.getenv("BLOCKCHAIN_NETWORK", "bsc_mainnet")
        return self.config["network"][network_name]
    
    def _initialize_web3(self) -> Web3:
        """
        Initialize Web3 connection to the blockchain.
        
        Returns:
            Web3 instance
        """
        rpc_url = self.network["rpc_url"]
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        # Verify connection
        if not w3.is_connected():
            logger.error(f"Failed to connect to blockchain RPC: {rpc_url}")
            raise ConnectionError(f"Could not connect to {rpc_url}")
        
        logger.info(f"Connected to blockchain at {rpc_url}")
        return w3
    
    def _get_last_processed_block(self) -> int:
        """
        Get the last processed block from the database.
        
        Returns:
            Last processed block number
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            chain_id = self.network["chain_id"]
            
            # Query the blockchain_sync_status table
            query = """
            SELECT block_number FROM blockchain_sync_status 
            WHERE chain_id = %s
            """
            
            cursor.execute(query, (chain_id,))
            result = cursor.fetchone()
            
            if result:
                last_block = result[0]
                logger.info(f"Last processed block from database: {last_block}")
                return last_block
            else:
                # If no record exists, insert one with the current block number
                current_block = self.w3.eth.block_number - self.confirmation_threshold
                
                insert_query = """
                INSERT INTO blockchain_sync_status (chain_id, block_number, updated_at)
                VALUES (%s, %s, NOW())
                """
                
                cursor.execute(insert_query, (chain_id, current_block))
                conn.commit()
                
                logger.info(f"Initialized sync status with block {current_block}")
                return current_block
                
        except Exception as e:
            logger.error(f"Error getting last processed block: {str(e)}")
            # If there's an error, start from a safe recent block
            current_block = self.w3.eth.block_number - self.confirmation_threshold
            logger.info(f"Using current block minus threshold: {current_block}")
            return current_block
        finally:
            if 'conn' in locals():
                conn.close()
    
    def _update_last_processed_block(self, block_number: int) -> None:
        """
        Update the last processed block in the database.
        
        Args:
            block_number: The latest processed block number
        """
        with self.db_lock:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                chain_id = self.network["chain_id"]
                
                # Update the blockchain_sync_status table
                query = """
                UPDATE blockchain_sync_status 
                SET block_number = %s, updated_at = NOW()
                WHERE chain_id = %s
                """
                
                cursor.execute(query, (block_number, chain_id))
                conn.commit()
                
                self.last_processed_block = block_number
                
            except Exception as e:
                logger.error(f"Error updating last processed block: {str(e)}")
            finally:
                if 'conn' in locals():
                    conn.close()
    
    def _refresh_user_addresses(self) -> None:
        """Refresh the set of user wallet addresses to monitor."""
        with self.address_lock:
            try:
                conn = get_db_connection()
                addresses = get_all_wallet_addresses(conn)
                
                # Update the set of addresses
                self.user_addresses = set(addr.lower() for addr in addresses)
                logger.info(f"Refreshed user addresses: {len(self.user_addresses)} addresses loaded")
                
            except Exception as e:
                logger.error(f"Error refreshing user addresses: {str(e)}")
            finally:
                if 'conn' in locals():
                    conn.close()
    
    def _process_block(self, block_number: int) -> List[Dict[str, Any]]:
        """
        Process a block and extract relevant transactions.
        
        Args:
            block_number: Block number to process
            
        Returns:
            List of transactions relevant to user addresses
        """
        try:
            # Get block with full transaction objects
            block = self.w3.eth.get_block(block_number, full_transactions=True)
            transactions = block['transactions']
            
            # Current block timestamp
            block_timestamp = datetime.fromtimestamp(block['timestamp'])
            
            relevant_txs = []
            
            for tx in transactions:
                tx_dict = dict(tx)
                # Convert to lowercase for comparison
                to_address = tx_dict.get('to', '').lower() if tx_dict.get('to') else ''
                
                # Check if this transaction is to one of our user addresses
                if to_address in self.user_addresses:
                    # Convert values to human-readable format
                    value_wei = tx_dict.get('value', 0)
                    value_ether = self.w3.from_wei(value_wei, 'ether')
                    
                    # Format transaction for our system
                    relevant_tx = {
                        'tx_hash': tx_dict['hash'].hex(),
                        'from_address': tx_dict['from'].lower(),
                        'to_address': to_address,
                        'block_number': block_number,
                        'value': value_ether,
                        'chain_id': self.network['chain_id'],
                        'status': 'pending',
                        'confirmations': 0,
                        'created_at': block_timestamp,
                        'user_id': self._get_user_id_for_address(to_address)
                    }
                    
                    relevant_txs.append(relevant_tx)
                    
                    # Add to processing queue
                    self.tx_queue.put(relevant_tx)
            
            # Log summary for this block
            if relevant_txs:
                logger.info(f"Block {block_number}: Found {len(relevant_txs)} relevant transactions")
            
            return relevant_txs
            
        except BlockNotFound:
            logger.warning(f"Block {block_number} not found, possibly a chain reorganization")
            # Handle chain reorganization
            if self.config["monitoring"]["alert_on_reorg"]:
                self._handle_chain_reorganization(block_number)
            return []
            
        except Exception as e:
            logger.error(f"Error processing block {block_number}: {str(e)}")
            self.retry_count += 1
            
            # If we exceed max retries, skip this block
            if self.retry_count > self.network["max_retries"]:
                logger.error(f"Max retries exceeded for block {block_number}, skipping")
                self.retry_count = 0
                return []
                
            # Otherwise wait and let the next cycle retry
            time.sleep(self.network["retry_interval"])
            return []
    
    def _handle_chain_reorganization(self, block_number: int) -> None:
        """
        Handle a chain reorganization event.
        
        Args:
            block_number: The block number where reorganization was detected
        """
        logger.warning(f"Chain reorganization detected at block {block_number}")
        
        # Roll back to a safe block
        safe_block = block_number - self.confirmation_threshold - 5
        if safe_block < 0:
            safe_block = 0
        
        logger.info(f"Rolling back to safe block {safe_block}")
        self._update_last_processed_block(safe_block)
        
        # Mark affected transactions for review
        with self.db_lock:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Update transactions in affected blocks
                query = """
                UPDATE blockchain_transactions 
                SET status = 'reorg', updated_at = NOW()
                WHERE block_number > %s AND chain_id = %s AND status != 'confirmed'
                """
                
                cursor.execute(query, (safe_block, self.network["chain_id"]))
                affected_rows = cursor.rowcount
                conn.commit()
                
                logger.info(f"Marked {affected_rows} transactions as affected by reorganization")
                
                # Send notification about the reorg
                self._send_reorg_notification(block_number, affected_rows)
                
            except Exception as e:
                logger.error(f"Error handling chain reorganization: {str(e)}")
            finally:
                if 'conn' in locals():
                    conn.close()
    
    def _send_reorg_notification(self, block_number: int, affected_txs: int) -> None:
        """
        Send notification about chain reorganization.
        
        Args:
            block_number: Block where reorganization was detected
            affected_txs: Number of affected transactions
        """
        # This would integrate with a notification system
        message = (
            f"ALERT: Chain reorganization detected at block {block_number}. "
            f"{affected_txs} transactions affected and marked for review."
        )
        logger.warning(message)
        
        # TODO: Implement actual notification sending (email, Slack, etc.)
    
    def _get_user_id_for_address(self, address: str) -> Optional[int]:
        """
        Get user ID associated with a wallet address.
        
        Args:
            address: Wallet address
            
        Returns:
            User ID or None if not found
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            query = """
            SELECT user_id FROM wallets 
            WHERE LOWER(address) = LOWER(%s)
            """
            
            cursor.execute(query, (address,))
            result = cursor.fetchone()
            
            if result:
                return result[0]
            return None
            
        except Exception as e:
            logger.error(f"Error getting user ID for address {address}: {str(e)}")
            return None
        finally:
            if 'conn' in locals():
                conn.close()
    
    def _save_transaction(self, transaction: Dict[str, Any]) -> bool:
        """
        Save a transaction to the database.
        
        Args:
            transaction: Transaction data
            
        Returns:
            True if successful, False otherwise
        """
        with self.db_lock:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Check if transaction already exists
                check_query = """
                SELECT id FROM blockchain_transactions 
                WHERE tx_hash = %s AND chain_id = %s
                """
                
                cursor.execute(check_query, (transaction['tx_hash'], transaction['chain_id']))
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing transaction
                    update_query = """
                    UPDATE blockchain_transactions 
                    SET status = %s, confirmations = %s, updated_at = NOW()
                    WHERE tx_hash = %s AND chain_id = %s
                    """
                    
                    cursor.execute(update_query, (
                        transaction['status'],
                        transaction['confirmations'],
                        transaction['tx_hash'],
                        transaction['chain_id']
                    ))
                    
                else:
                    # Insert new transaction
                    insert_query = """
                    INSERT INTO blockchain_transactions 
                    (tx_hash, from_address, to_address, block_number, value, 
                     chain_id, status, confirmations, user_id, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """
                    
                    cursor.execute(insert_query, (
                        transaction['tx_hash'],
                        transaction['from_address'],
                        transaction['to_address'],
                        transaction['block_number'],
                        transaction['value'],
                        transaction['chain_id'],
                        transaction['status'],
                        transaction['confirmations'],
                        transaction['user_id'],
                        transaction['created_at']
                    ))
                
                conn.commit()
                return True
                
            except Exception as e:
                logger.error(f"Error saving transaction {transaction['tx_hash']}: {str(e)}")
                return False
            finally:
                if 'conn' in locals():
                    conn.close()
    
    def _process_transaction_queue(self) -> None:
        """Process transactions in the queue."""
        batch_size = self.config["database"]["batch_size"]
        processed = 0
        
        while not self.tx_queue.empty() and processed < batch_size:
            try:
                # Get transaction from queue
                tx = self.tx_queue.get_nowait()
                
                # Get current block for confirmation calculation
                current_block = self.w3.eth.block_number
                tx_block = tx['block_number']
                
                # Calculate confirmations
                confirmations = current_block - tx_block if current_block > tx_block else 0
                tx['confirmations'] = confirmations
                
                # Update status based on confirmations
                if confirmations >= self.confirmation_threshold:
                    tx['status'] = 'confirmed'
                    
                    # If confirmed and this is new or status changed, update user balance
                    self._update_user_balance_on_deposit(tx)
                
                # Save transaction to database
                self._save_transaction(tx)
                
                # Mark task as done
                self.tx_queue.task_done()
                processed += 1
                
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"Error processing transaction: {str(e)}")
    
    def _update_user_balance_on_deposit(self, transaction: Dict[str, Any]) -> None:
        """
        Update user balance when a deposit is confirmed.
        
        Args:
            transaction: Confirmed transaction data
        """
        if transaction['status'] != 'confirmed' or not transaction['user_id']:
            return
            
        try:
            conn = get_db_connection()
            
            # Generate a reference for this deposit
            reference = f"deposit-{transaction['tx_hash'][:10]}"
            
            # Get wallet ID
            cursor = conn.cursor()
            query = """
            SELECT id FROM wallets 
            WHERE LOWER(address) = LOWER(%s) AND user_id = %s
            """
            
            cursor.execute(query, (transaction['to_address'], transaction['user_id']))
            result = cursor.fetchone()
            
            if not result:
                logger.error(f"Wallet not found for address {transaction['to_address']} and user {transaction['user_id']}")
                return
                
            wallet_id = result[0]
            
            # Update wallet balance
            update_wallet_balance(
                conn, 
                wallet_id, 
                float(transaction['value']), 
                'deposit', 
                reference
            )
            
            logger.info(
                f"Updated balance for user {transaction['user_id']}, "
                f"wallet {wallet_id}, amount {transaction['value']}, "
                f"tx {transaction['tx_hash']}"
            )
            
            # Record in account_transactions
            account_tx_query = """
            INSERT INTO account_transactions 
            (user_id, type, amount, reference, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            """
            
            cursor.execute(account_tx_query, (
                transaction['user_id'], 
                'deposit', 
                transaction['value'], 
                reference
            ))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error updating user balance for transaction {transaction['tx_hash']}: {str(e)}")
        finally:
            if 'conn' in locals():
                conn.close()
    
    def _sync_blockchain_listener(self) -> None:
        """Main blockchain listening loop."""
        logger.info("Blockchain listener thread started")
        
        polling_interval = self.config["monitoring"]["polling_interval"]
        max_blocks_per_batch = self.config["monitoring"]["max_blocks_per_batch"]
        
        while self.running:
            try:
                # Refresh user addresses periodically
                self._refresh_user_addresses()
                
                # Get current block
                current_block = self.w3.eth.block_number
                
                # Determine safe block (accounting for confirmation threshold)
                safe_block = current_block - self.confirmation_threshold
                
                # Process new blocks
                if safe_block > self.last_processed_block:
                    # Determine range to process
                    start_block = self.last_processed_block + 1
                    end_block = min(safe_block, start_block + max_blocks_per_batch - 1)
                    
                    logger.info(f"Processing blocks {start_block} to {end_block}")
                    
                    # Process each block
                    for block_num in range(start_block, end_block + 1):
                        if not self.running:
                            break
                            
                        self._process_block(block_num)
                        
                        # Update last processed block
                        self._update_last_processed_block(block_num)
                    
                    # Reset retry counter on successful processing
                    self.retry_count = 0
                    
                # Process transaction queue
                self._process_transaction_queue()
                
            except Exception as e:
                logger.error(f"Error in blockchain listener: {str(e)}")
                self.retry_count += 1
                
                # If we exceed max retries, wait longer
                if self.retry_count > self.network["max_retries"]:
                    logger.error(f"Max retries exceeded in listener, waiting {self.network['retry_interval'] * 2}s")
                    time.sleep(self.network["retry_interval"] * 2)
                    self.retry_count = 0
            
            # Wait before next check
            time.sleep(polling_interval)
    
    def _sync_wallet_balances(self) -> None:
        """Periodically sync on-chain balances with database balances."""
        logger.info("Balance synchronization thread started")
        
        sync_interval = self.config["monitoring"]["balance_check_interval"]
        
        while self.running:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Get all wallets
                query = """
                SELECT id, address, user_id FROM wallets
                """
                
                cursor.execute(query)
                wallets = cursor.fetchall()
                
                logger.info(f"Starting balance sync for {len(wallets)} wallets")
                
                for wallet_id, address, user_id in wallets:
                    if not self.running:
                        break
                        
                    try:
                        # Get on-chain balance
                        balance_wei = self.w3.eth.get_balance(Web3.to_checksum_address(address))
                        balance_ether = self.w3.from_wei(balance_wei, 'ether')
                        
                        # Get database balance
                        balance_query = """
                        SELECT balance FROM wallet_balances 
                        WHERE wallet_id = %s
                        """
                        
                        cursor.execute(balance_query, (wallet_id,))
                        result = cursor.fetchone()
                        
                        if result:
                            db_balance = float(result[0])
                            
                            # Check for discrepancy
                            discrepancy = float(balance_ether) - db_balance
                            
                            # If significant discrepancy found
                            if abs(discrepancy) > 0.00001:  # Adjust threshold as needed
                                logger.warning(
                                    f"Balance discrepancy for wallet {wallet_id} "
                                    f"(address: {address}): "
                                    f"chain={balance_ether}, db={db_balance}, "
                                    f"diff={discrepancy}"
                                )
                                
                                # Record discrepancy but don't auto-correct
                                # This requires manual review
                                discrepancy_query = """
                                INSERT INTO balance_discrepancies 
                                (wallet_id, chain_balance, db_balance, difference, created_at)
                                VALUES (%s, %s, %s, %s, NOW())
                                """
                                
                                cursor.execute(discrepancy_query, (
                                    wallet_id, 
                                    float(balance_ether), 
                                    db_balance, 
                                    discrepancy
                                ))
                                conn.commit()
                        
                    except Exception as e:
                        logger.error(f"Error checking balance for wallet {wallet_id}: {str(e)}")
                
                logger.info("Wallet balance synchronization completed")
                
            except Exception as e:
                logger.error(f"Error in balance synchronization: {str(e)}")
            finally:
                if 'conn' in locals():
                    conn.close()
            
            # Wait before next sync
            time.sleep(sync_interval)
    
    def start(self) -> None:
        """Start the transaction monitoring system."""
        if self.running:
            logger.warning("Transaction monitoring system is already running")
            return
            
        logger.info("Starting transaction monitoring system")
        self.running = True
        
        # Start blockchain listener thread
        self.listener_thread = threading.Thread(
            target=self._sync_blockchain_listener,
            daemon=True
        )
        self.listener_thread.start()
        
        # Start balance sync thread
        self.balance_sync_thread = threading.Thread(
            target=self._sync_wallet_balances,
            daemon=True
        )
        self.balance_sync_thread.start()
        
        logger.info("Transaction monitoring system started")
    
    def stop(self) -> None:
        """Stop the transaction monitoring system."""
        if not self.running:
            logger.warning("Transaction monitoring system is not running")
            return
            
        logger.info("Stopping transaction monitoring system")
        self.running = False
        
        # Wait for threads to finish
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join(timeout=5.0)
            
        if self.balance_sync_thread and self.balance_sync_thread.is_alive():
            self.balance_sync_thread.join(timeout=5.0)
            
        logger.info("Transaction monitoring system stopped")


# Create a database table for balance discrepancies if needed
def create_balance_discrepancies_table() -> None:
    """Create the balance_discrepancies table if it doesn't exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'balance_discrepancies'
        )
        """)
        
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            cursor.execute("""
            CREATE TABLE balance_discrepancies (
                id SERIAL PRIMARY KEY,
                wallet_id INTEGER NOT NULL REFERENCES wallets(id),
                chain_balance NUMERIC(30, 18) NOT NULL,
                db_balance NUMERIC(30, 18) NOT NULL,
                difference NUMERIC(30, 18) NOT NULL,
                resolved BOOLEAN DEFAULT FALSE,
                resolution_notes TEXT,
                created_at TIMESTAMP NOT NULL,
                resolved_at TIMESTAMP
            );
            CREATE INDEX idx_balance_discrepancies_wallet_id ON balance_discrepancies(wallet_id);
            CREATE INDEX idx_balance_discrepancies_created_at ON balance_discrepancies(created_at);
            """)
            
            conn.commit()
            logger.info("Created balance_discrepancies table")
        
    except Exception as e:
        logger.error(f"Error creating balance_discrepancies table: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()


# Singleton instance
_monitor_instance = None

def get_monitor_instance(config_path: str = "config/monitor_settings.json") -> TransactionProcessor:
    """
    Get or create the transaction monitor instance.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        TransactionProcessor instance
    """
    global _monitor_instance
    
    if _monitor_instance is None:
        _monitor_instance = TransactionProcessor(config_path)
        
    return _monitor_instance

def start_monitoring(config_path: str = "config/monitor_settings.json") -> None:
    """
    Start the transaction monitoring system.
    
    Args:
        config_path: Path to the configuration file
    """
    # Create tables if needed
    create_balance_discrepancies_table()
    
    # Get monitor instance and start
    monitor = get_monitor_instance(config_path)
    monitor.start()

def stop_monitoring() -> None:
    """Stop the transaction monitoring system."""
    global _monitor_instance
    
    if _monitor_instance is not None:
        _monitor_instance.stop()
        _monitor_instance = None


if __name__ == "__main__":
    # Create tables if needed
    create_balance_discrepancies_table()
    
    # Start monitoring
    monitor = TransactionProcessor()
    
    try:
        monitor.start()
        
        # Keep the main thread running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Stopping monitoring due to keyboard interrupt")
        monitor.stop()
    except Exception as e:
        logger.error(f"Error in main thread: {str(e)}")
        monitor.stop() 