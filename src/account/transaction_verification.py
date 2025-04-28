"""
Transaction Verification Module

This module provides functionality for verifying blockchain transactions on the BEP20 network.
It includes methods for validating transaction details, checking confirmation status,
and verifying smart contract interactions.
"""

import os
import time
import logging
import threading
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Tuple
from datetime import datetime

from web3 import Web3
from web3.exceptions import TransactionNotFound
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('transaction_verification')

# Constants
DEFAULT_CONFIRMATIONS = int(os.getenv('DEFAULT_CONFIRMATIONS', '12'))
RPC_URL = os.getenv('BEP20_RPC_URL', 'https://bsc-dataseed.binance.org/')
CHAIN_ID = int(os.getenv('CHAIN_ID', '56'))  # BSC Mainnet by default


class VerificationStatus(Enum):
    """Transaction verification status enum."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    REJECTED = "rejected"
    INVALID = "invalid"
    NOT_FOUND = "not_found"


class TransactionVerifier:
    """Class for verifying blockchain transactions."""
    
    def __init__(self, 
                 rpc_url: str = None, 
                 chain_id: int = None,
                 required_confirmations: int = None):
        """
        Initialize the transaction verifier.
        
        Args:
            rpc_url: Blockchain RPC URL, defaults to environment variable
            chain_id: Chain ID for the blockchain network
            required_confirmations: Number of confirmations required for transaction finality
        """
        self.rpc_url = rpc_url or RPC_URL
        self.chain_id = chain_id or CHAIN_ID
        self.required_confirmations = required_confirmations or DEFAULT_CONFIRMATIONS
        
        self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
        if not self.web3.is_connected():
            logger.error(f"Failed to connect to the blockchain at {self.rpc_url}")
            raise ConnectionError(f"Could not connect to blockchain at {self.rpc_url}")
        
        # Cache to store verified transactions
        self._cache = {}
        self._cache_lock = threading.Lock()
        
        # Background verification thread
        self._verification_thread = None
        self._stop_event = threading.Event()
        self._verification_queue = []
        self._queue_lock = threading.Lock()
        
        logger.info(f"TransactionVerifier initialized with RPC {self.rpc_url}, "
                   f"chain ID {self.chain_id}, confirmations {self.required_confirmations}")
    
    def verify_transaction(self, 
                           tx_hash: str, 
                           expected_to_address: str = None,
                           expected_from_address: str = None,
                           expected_value: int = None) -> Tuple[VerificationStatus, Dict[str, Any]]:
        """
        Verify a transaction.
        
        Args:
            tx_hash: Transaction hash to verify
            expected_to_address: Expected recipient address (optional)
            expected_from_address: Expected sender address (optional)
            expected_value: Expected transaction value in wei (optional)
            
        Returns:
            Tuple of verification status and transaction details
        """
        if not Web3.is_checksum_address(expected_to_address or "0x0000000000000000000000000000000000000000"):
            if expected_to_address:
                expected_to_address = Web3.to_checksum_address(expected_to_address)
        
        if not Web3.is_checksum_address(expected_from_address or "0x0000000000000000000000000000000000000000"):
            if expected_from_address:
                expected_from_address = Web3.to_checksum_address(expected_from_address)
        
        logger.info(f"Verifying transaction {tx_hash}")
        
        try:
            # Normalize transaction hash
            if not tx_hash.startswith('0x'):
                tx_hash = '0x' + tx_hash
                
            # Check if cached
            with self._cache_lock:
                if tx_hash in self._cache:
                    cached_status, cached_data, cache_time = self._cache[tx_hash]
                    # Use cache if recent (within 2 minutes)
                    if (datetime.now() - cache_time).total_seconds() < 120:
                        logger.debug(f"Using cached verification for {tx_hash}")
                        return cached_status, cached_data
            
            # Get transaction
            tx_receipt = None
            tx = self.web3.eth.get_transaction(tx_hash)
            
            # If transaction found but not yet mined
            if tx is None:
                logger.warning(f"Transaction {tx_hash} not found")
                return VerificationStatus.NOT_FOUND, {}
                
            if tx.blockNumber is not None:
                tx_receipt = self.web3.eth.get_transaction_receipt(tx_hash)
            
            # Verify transaction details
            if expected_to_address and tx.to and tx.to.lower() != expected_to_address.lower():
                logger.warning(f"Transaction recipient mismatch: {tx.to} != {expected_to_address}")
                return VerificationStatus.INVALID, self._extract_tx_details(tx, tx_receipt)
                
            if expected_from_address and tx['from'].lower() != expected_from_address.lower():
                logger.warning(f"Transaction sender mismatch: {tx['from']} != {expected_from_address}")
                return VerificationStatus.INVALID, self._extract_tx_details(tx, tx_receipt)
                
            if expected_value is not None and tx.value != expected_value:
                logger.warning(f"Transaction value mismatch: {tx.value} != {expected_value}")
                return VerificationStatus.INVALID, self._extract_tx_details(tx, tx_receipt)
            
            # Check confirmation status
            if tx_receipt is None:
                status = VerificationStatus.PENDING
            elif tx_receipt.status == 0:
                status = VerificationStatus.FAILED
            else:
                current_block = self.web3.eth.block_number
                confirmations = current_block - tx_receipt.blockNumber + 1
                
                if confirmations >= self.required_confirmations:
                    status = VerificationStatus.CONFIRMED
                else:
                    status = VerificationStatus.PENDING
            
            # Extract transaction details
            tx_details = self._extract_tx_details(tx, tx_receipt)
            
            # Update cache
            with self._cache_lock:
                self._cache[tx_hash] = (status, tx_details, datetime.now())
                
                # Cleanup cache if too large (keep last 1000 transactions)
                if len(self._cache) > 1000:
                    # Sort by cache time and remove oldest
                    oldest_key = sorted(self._cache.items(), key=lambda x: x[1][2])[0][0]
                    del self._cache[oldest_key]
            
            return status, tx_details
            
        except TransactionNotFound:
            logger.warning(f"Transaction {tx_hash} not found")
            return VerificationStatus.NOT_FOUND, {}
            
        except Exception as e:
            logger.error(f"Error verifying transaction {tx_hash}: {str(e)}")
            return VerificationStatus.INVALID, {"error": str(e)}
    
    def _extract_tx_details(self, tx, tx_receipt) -> Dict[str, Any]:
        """Extract relevant transaction details from web3 transaction object."""
        details = {
            "hash": tx['hash'].hex(),
            "from": tx['from'],
            "to": tx['to'],
            "value": tx['value'],
            "gas": tx['gas'],
            "gasPrice": tx['gasPrice'],
            "nonce": tx['nonce'],
            "blockNumber": tx['blockNumber'],
            "blockHash": tx['blockHash'].hex() if tx['blockHash'] else None,
        }
        
        if tx_receipt:
            details.update({
                "status": tx_receipt['status'],
                "gasUsed": tx_receipt['gasUsed'],
                "effectiveGasPrice": tx_receipt.get('effectiveGasPrice'),
                "cumulativeGasUsed": tx_receipt['cumulativeGasUsed'],
                "logs": [log.args for log in tx_receipt.get('logs', [])],
                "confirmations": 0  # Will be calculated later if needed
            })
            
            # Calculate confirmations
            if tx_receipt['blockNumber'] is not None:
                current_block = self.web3.eth.block_number
                details['confirmations'] = current_block - tx_receipt['blockNumber'] + 1
        
        return details
    
    def start_verification_service(self):
        """Start background verification service."""
        if self._verification_thread and self._verification_thread.is_alive():
            logger.warning("Verification service already running")
            return
            
        self._stop_event.clear()
        self._verification_thread = threading.Thread(
            target=self._verification_loop,
            daemon=True
        )
        self._verification_thread.start()
        logger.info("Transaction verification service started")
    
    def stop_verification_service(self):
        """Stop background verification service."""
        if not self._verification_thread or not self._verification_thread.is_alive():
            return
            
        logger.info("Stopping transaction verification service")
        self._stop_event.set()
        self._verification_thread.join(timeout=5.0)
        if self._verification_thread.is_alive():
            logger.warning("Verification thread didn't stop gracefully")
        else:
            logger.info("Transaction verification service stopped")
    
    def add_to_verification_queue(self, 
                                 tx_hash: str, 
                                 callback: Callable[[str, VerificationStatus, Dict], None],
                                 expected_to_address: str = None,
                                 expected_from_address: str = None,
                                 expected_value: int = None):
        """
        Add a transaction to the verification queue.
        
        Args:
            tx_hash: Transaction hash to verify
            callback: Function to call when verification completes
            expected_to_address: Expected recipient address (optional)
            expected_from_address: Expected sender address (optional)
            expected_value: Expected transaction value in wei (optional)
        """
        with self._queue_lock:
            self._verification_queue.append({
                'tx_hash': tx_hash,
                'callback': callback,
                'expected_to_address': expected_to_address,
                'expected_from_address': expected_from_address,
                'expected_value': expected_value,
                'added_at': datetime.now()
            })
        logger.debug(f"Added transaction {tx_hash} to verification queue")
        
        # Start service if not running
        if (not self._verification_thread or 
            not self._verification_thread.is_alive()):
            self.start_verification_service()
    
    def _verification_loop(self):
        """Background verification loop."""
        while not self._stop_event.is_set():
            try:
                with self._queue_lock:
                    if not self._verification_queue:
                        # No transactions to verify, sleep and continue
                        time.sleep(5)
                        continue
                    
                    # Process a copy of the queue to avoid lock contention
                    queue_copy = self._verification_queue.copy()
                    
                for item in queue_copy:
                    if self._stop_event.is_set():
                        break
                        
                    tx_hash = item['tx_hash']
                    status, details = self.verify_transaction(
                        tx_hash,
                        item['expected_to_address'],
                        item['expected_from_address'],
                        item['expected_value']
                    )
                    
                    # If transaction is final (confirmed, failed, rejected, invalid)
                    # or has been pending for too long (24 hours), remove from queue
                    remove_from_queue = False
                    
                    if status in [
                        VerificationStatus.CONFIRMED, 
                        VerificationStatus.FAILED,
                        VerificationStatus.REJECTED,
                        VerificationStatus.INVALID
                    ]:
                        remove_from_queue = True
                    elif status == VerificationStatus.NOT_FOUND:
                        # Check if transaction has been in queue for over 24 hours
                        age = (datetime.now() - item['added_at']).total_seconds() / 3600
                        if age > 24:
                            remove_from_queue = True
                    
                    # Call the callback if provided
                    if item['callback']:
                        try:
                            item['callback'](tx_hash, status, details)
                        except Exception as e:
                            logger.error(f"Error in verification callback for {tx_hash}: {str(e)}")
                    
                    # Remove from queue if done
                    if remove_from_queue:
                        with self._queue_lock:
                            self._verification_queue = [
                                q for q in self._verification_queue 
                                if q['tx_hash'] != tx_hash
                            ]
                
                # Sleep between verification cycles
                time.sleep(15)
                
            except Exception as e:
                logger.error(f"Error in verification loop: {str(e)}")
                time.sleep(30)  # Sleep longer on error
    
    def verify_contract_interaction(self, 
                                   tx_hash: str, 
                                   contract_address: str,
                                   method_name: str = None,
                                   expected_params: Dict = None) -> Tuple[bool, Dict]:
        """
        Verify a smart contract interaction.
        
        Args:
            tx_hash: Transaction hash
            contract_address: Smart contract address
            method_name: Expected method name (optional)
            expected_params: Expected parameters (optional)
            
        Returns:
            Tuple of verification result (boolean) and details dict
        """
        # This is a simplified implementation - in a real system you'd need:
        # 1. Contract ABI to decode method calls and events
        # 2. Logic to compare expected vs actual parameters
        # 3. Event logs verification
        
        if not Web3.is_checksum_address(contract_address):
            contract_address = Web3.to_checksum_address(contract_address)
        
        status, details = self.verify_transaction(tx_hash)
        
        # Check if transaction is to the contract
        if details.get('to') and details['to'].lower() != contract_address.lower():
            return False, {"error": "Transaction not sent to specified contract"}
        
        # For more advanced verification, we'd need to:
        # 1. Get contract ABI
        # 2. Create contract instance
        # 3. Decode function calls and event logs
        
        return (status == VerificationStatus.CONFIRMED), details


# Singleton instance
_verifier_instance = None


def get_verifier(reset=False) -> TransactionVerifier:
    """
    Get global transaction verifier instance.
    
    Args:
        reset: Whether to create a new instance if one exists
        
    Returns:
        TransactionVerifier instance
    """
    global _verifier_instance
    
    if _verifier_instance is None or reset:
        _verifier_instance = TransactionVerifier(
            rpc_url=os.getenv('BEP20_RPC_URL'),
            chain_id=int(os.getenv('CHAIN_ID', '56')),
            required_confirmations=int(os.getenv('DEFAULT_CONFIRMATIONS', '12'))
        )
        
    return _verifier_instance 