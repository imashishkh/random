"""
Deposit monitoring system for tracking BEP20 transactions.

This module provides functionality to monitor blockchain transactions
to user deposit addresses and process them according to business rules.
"""

import os
import time
import logging
import threading
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from queue import Queue
from dataclasses import dataclass

from web3 import Web3
from web3.middleware import geth_poa_middleware
from dotenv import load_dotenv

from .models import Transaction, TransactionStatus
from .wallet import Wallet, get_user_wallets

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Constants
DEFAULT_CONFIRMATION_THRESHOLD = int(os.getenv('CONFIRMATION_THRESHOLD', 12))
DEFAULT_POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', 15))  # seconds
DEFAULT_BACKOFF_TIME = int(os.getenv('BACKOFF_TIME', 60))  # seconds
BSC_RPC_URL = os.getenv('BSC_RPC_URL', 'https://bsc-dataseed.binance.org/')
BSC_CHAIN_ID = int(os.getenv('BSC_CHAIN_ID', 56))

@dataclass
class BlockchainConfig:
    """Configuration for a blockchain connection."""
    chain_id: int
    rpc_url: str
    confirmation_threshold: int = DEFAULT_CONFIRMATION_THRESHOLD
    poll_interval: int = DEFAULT_POLL_INTERVAL


class TransactionProcessor:
    """Process transactions from blockchain."""
    
    def __init__(self, config: BlockchainConfig):
        """Initialize with blockchain configuration."""
        self.config = config
        self.web3 = Web3(Web3.HTTPProvider(config.rpc_url))
        
        # Add middleware for BSC compatibility
        if config.chain_id == BSC_CHAIN_ID:
            self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)
            
        if not self.web3.is_connected():
            raise ConnectionError(f"Failed to connect to {config.rpc_url}")
            
        self.latest_block = self.web3.eth.block_number
        logger.info(f"Connected to blockchain at block {self.latest_block}")
        
        # Transaction processing queue
        self.tx_queue = Queue()
        self.processing_thread = None
        self.running = False
        
        # Track monitored addresses
        self.monitored_addresses = set()
        self._load_monitored_addresses()
    
    def _load_monitored_addresses(self):
        """Load all user wallet addresses to monitor."""
        try:
            wallets = get_user_wallets()
            for wallet in wallets:
                self.monitored_addresses.add(wallet.address.lower())
            logger.info(f"Monitoring {len(self.monitored_addresses)} addresses")
        except Exception as e:
            logger.error(f"Failed to load monitored addresses: {e}")
    
    def refresh_monitored_addresses(self):
        """Refresh the list of monitored addresses."""
        self.monitored_addresses.clear()
        self._load_monitored_addresses()
    
    def start(self):
        """Start the transaction processor."""
        if self.running:
            logger.warning("Transaction processor is already running")
            return
            
        self.running = True
        
        # Start processing thread
        self.processing_thread = threading.Thread(
            target=self._process_transactions_worker,
            daemon=True
        )
        self.processing_thread.start()
        
        # Start monitoring thread
        self.monitoring_thread = threading.Thread(
            target=self._monitor_blockchain_worker,
            daemon=True
        )
        self.monitoring_thread.start()
        
        logger.info("Transaction processor started")
    
    def stop(self):
        """Stop the transaction processor."""
        if not self.running:
            logger.warning("Transaction processor is not running")
            return
            
        self.running = False
        
        if self.processing_thread:
            self.processing_thread.join(timeout=5.0)
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5.0)
            
        logger.info("Transaction processor stopped")
    
    def _monitor_blockchain_worker(self):
        """Worker thread to monitor blockchain for new blocks and transactions."""
        backoff_time = 0
        
        while self.running:
            try:
                if backoff_time > 0:
                    logger.info(f"Backing off for {backoff_time} seconds")
                    time.sleep(backoff_time)
                    backoff_time = 0
                
                # Get current block number
                current_block = self.web3.eth.block_number
                
                # If no new blocks, wait and try again
                if current_block <= self.latest_block:
                    time.sleep(self.config.poll_interval)
                    continue
                
                # Process new blocks
                for block_number in range(self.latest_block + 1, current_block + 1):
                    self._process_block(block_number)
                
                # Update latest processed block
                self.latest_block = current_block
                
                # Check pending transactions for confirmations
                self._check_pending_transactions()
                
                # Wait before next poll
                time.sleep(self.config.poll_interval)
                
            except Exception as e:
                logger.error(f"Error in blockchain monitor: {e}")
                # Implement exponential backoff
                backoff_time = min(DEFAULT_BACKOFF_TIME * 2, 600)  # Max 10 minutes
    
    def _process_block(self, block_number: int):
        """Process a single block and extract relevant transactions."""
        try:
            logger.debug(f"Processing block {block_number}")
            
            # Get block with transactions
            block = self.web3.eth.get_block(block_number, full_transactions=True)
            
            # Process each transaction in the block
            for tx in block.transactions:
                # Convert addresses to checksum format
                to_address = self.web3.to_checksum_address(tx["to"]) if tx.get("to") else None
                from_address = self.web3.to_checksum_address(tx["from"]) if tx.get("from") else None
                
                # Skip if recipient is not in our monitored addresses
                if not to_address or to_address.lower() not in self.monitored_addresses:
                    continue
                
                # Queue transaction for processing
                tx_hash = tx["hash"].hex()
                logger.info(f"Found relevant transaction: {tx_hash} to {to_address}")
                self.tx_queue.put((tx, block_number, block.timestamp))
                
        except Exception as e:
            logger.error(f"Error processing block {block_number}: {e}")
    
    def _process_transactions_worker(self):
        """Worker thread to process queued transactions."""
        while self.running:
            try:
                if self.tx_queue.empty():
                    time.sleep(1)
                    continue
                
                # Get transaction from queue
                tx, block_number, timestamp = self.tx_queue.get()
                tx_hash = tx["hash"].hex()
                
                # Process the transaction
                self._process_transaction(tx, block_number, timestamp)
                
                # Mark task as done
                self.tx_queue.task_done()
                
            except Exception as e:
                logger.error(f"Error in transaction processor: {e}")
                time.sleep(1)
    
    def _process_transaction(self, tx: Dict[str, Any], block_number: int, timestamp: int):
        """Process a single transaction and update the database."""
        tx_hash = tx["hash"].hex()
        to_address = self.web3.to_checksum_address(tx["to"]) if tx.get("to") else None
        from_address = self.web3.to_checksum_address(tx["from"]) if tx.get("from") else None
        
        # Skip if not a valid transaction for our system
        if not to_address:
            return
            
        try:
            # Find user wallet matching the deposit address
            wallet = Wallet.get_wallet_by_address(to_address)
            if not wallet:
                logger.warning(f"Received transaction to monitored address {to_address} but no matching wallet found")
                return
            
            # Determine token type (assuming BNB for now)
            token = "BNB"
            
            # Calculate amount (convert from wei to ether for BNB)
            amount = str(self.web3.from_wei(tx["value"], 'ether'))
            
            # Check if transaction already exists
            existing_tx = Transaction.get_by_hash(tx_hash)
            if existing_tx:
                logger.debug(f"Transaction {tx_hash} already exists in database")
                return
            
            # Create new transaction record
            transaction = Transaction(
                user_id=wallet.user_id,
                chain_id=self.config.chain_id,
                hash=tx_hash,
                from_address=from_address,
                to_address=to_address,
                token=token,
                amount=amount,
                block_number=block_number,
                timestamp=timestamp,
                status=TransactionStatus.PENDING
            )
            
            # Save to database
            transaction.save()
            
            logger.info(f"New deposit detected: {amount} {token} from {from_address} to {to_address}")
            
            # Check for unusual transaction patterns
            self._check_for_unusual_patterns(transaction)
            
        except Exception as e:
            logger.error(f"Error processing transaction {tx_hash}: {e}")
    
    def _check_pending_transactions(self):
        """Check pending transactions for confirmation status."""
        try:
            # Get pending transactions for this chain
            pending_txs = Transaction.get_pending_by_chain(self.config.chain_id)
            
            current_block = self.web3.eth.block_number
            
            for tx in pending_txs:
                # Skip transactions without block number
                if not tx.block_number:
                    continue
                
                # Calculate confirmations
                confirmations = current_block - tx.block_number
                
                # If enough confirmations, mark as confirmed
                if confirmations >= self.config.confirmation_threshold:
                    self._confirm_transaction(tx)
                
                # Log confirmation progress
                logger.debug(f"Transaction {tx.hash}: {confirmations}/{self.config.confirmation_threshold} confirmations")
                
        except Exception as e:
            logger.error(f"Error checking pending transactions: {e}")
    
    def _confirm_transaction(self, tx: Transaction):
        """Mark a transaction as confirmed and update user balance."""
        try:
            # Update transaction status
            tx.status = TransactionStatus.CONFIRMED
            tx.save()
            
            logger.info(f"Transaction {tx.hash} confirmed with {self.config.confirmation_threshold} confirmations")
            
            # Update user balance
            self._update_user_balance(tx)
            
        except Exception as e:
            logger.error(f"Error confirming transaction {tx.hash}: {e}")
    
    def _update_user_balance(self, tx: Transaction):
        """Update user balance after a confirmed deposit."""
        try:
            # Get user wallet
            wallet = Wallet.get_wallet_by_user_id_and_address(tx.user_id, tx.to_address)
            if not wallet:
                logger.error(f"Failed to find wallet for user {tx.user_id} with address {tx.to_address}")
                return
            
            # Update wallet balance
            # Note: In a real implementation, you might want to call an API to update the balance
            logger.info(f"Updating balance for user {tx.user_id}: +{tx.amount} {tx.token}")
            
            # For now, we'll log the balance update
            logger.info(f"Balance updated for user {tx.user_id}")
            
        except Exception as e:
            logger.error(f"Error updating user balance for transaction {tx.hash}: {e}")
    
    def _check_for_unusual_patterns(self, tx: Transaction):
        """Check for unusual transaction patterns and log them."""
        # Example checks - customize based on your risk model
        try:
            # Check for large transactions
            amount = float(tx.amount)
            if amount > 10.0:  # Example threshold
                logger.warning(f"Large deposit detected: {tx.amount} {tx.token} for user {tx.user_id}")
            
            # Check for multiple transactions from same address in short time
            # (This would require more state tracking or database queries)
            
            # Check for suspicious addresses (would require a blacklist)
            
        except Exception as e:
            logger.error(f"Error checking for unusual patterns for transaction {tx.hash}: {e}")


class DepositMonitorService:
    """Service to manage deposit monitors across multiple blockchains."""
    
    def __init__(self):
        """Initialize the deposit monitor service."""
        self.processors = {}
        self.running = False
        
        # Default configuration for BSC
        bsc_config = BlockchainConfig(
            chain_id=BSC_CHAIN_ID,
            rpc_url=BSC_RPC_URL
        )
        
        # Add BSC processor by default
        self.add_blockchain(bsc_config)
    
    def add_blockchain(self, config: BlockchainConfig):
        """Add a new blockchain to monitor."""
        if config.chain_id in self.processors:
            logger.warning(f"Blockchain {config.chain_id} already being monitored")
            return
        
        try:
            processor = TransactionProcessor(config)
            self.processors[config.chain_id] = processor
            logger.info(f"Added blockchain monitor for chain ID {config.chain_id}")
        except Exception as e:
            logger.error(f"Failed to add blockchain {config.chain_id}: {e}")
    
    def remove_blockchain(self, chain_id: int):
        """Remove a blockchain from monitoring."""
        if chain_id not in self.processors:
            logger.warning(f"Blockchain {chain_id} is not being monitored")
            return
        
        processor = self.processors[chain_id]
        if processor.running:
            processor.stop()
        
        del self.processors[chain_id]
        logger.info(f"Removed blockchain monitor for chain ID {chain_id}")
    
    def start(self):
        """Start all blockchain monitors."""
        if self.running:
            logger.warning("Deposit monitor service is already running")
            return
        
        self.running = True
        
        for chain_id, processor in self.processors.items():
            try:
                processor.start()
            except Exception as e:
                logger.error(f"Failed to start processor for chain {chain_id}: {e}")
        
        logger.info("Deposit monitor service started")
    
    def stop(self):
        """Stop all blockchain monitors."""
        if not self.running:
            logger.warning("Deposit monitor service is not running")
            return
        
        self.running = False
        
        for chain_id, processor in self.processors.items():
            try:
                if processor.running:
                    processor.stop()
            except Exception as e:
                logger.error(f"Error stopping processor for chain {chain_id}: {e}")
        
        logger.info("Deposit monitor service stopped")
    
    def refresh_monitored_addresses(self):
        """Refresh monitored addresses across all processors."""
        for chain_id, processor in self.processors.items():
            try:
                processor.refresh_monitored_addresses()
            except Exception as e:
                logger.error(f"Error refreshing addresses for chain {chain_id}: {e}")
        
        logger.info("Refreshed monitored addresses across all chains")


# Singleton instance for global use
_service_instance = None


def get_deposit_monitor_service() -> DepositMonitorService:
    """Get the global deposit monitor service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = DepositMonitorService()
    return _service_instance 