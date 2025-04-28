"""
Unit tests for the deposit monitoring system.

This module contains tests for the blockchain transaction monitoring,
confirmation tracking, and balance synchronization functionality.
"""

import os
import unittest
from unittest.mock import patch, MagicMock
import datetime
from web3 import Web3
from web3.types import BlockData, TxData, TxReceipt

from .deposit_monitor import (
    TransactionProcessor, 
    BlockchainConfig,
    DepositMonitorService,
    DEFAULT_CONFIRMATION_THRESHOLD
)
from .models import Transaction, TransactionStatus


class MockWeb3Provider:
    """Mock Web3 provider for testing blockchain interactions."""
    
    def __init__(self):
        """Initialize with mock blockchain data."""
        self.eth = MagicMock()
        self.eth.block_number = 1000
        self.eth.get_block.return_value = self._create_mock_block()
        self.middleware_onion = MagicMock()
        self.middleware_onion.inject = MagicMock()
        self.is_connected = MagicMock(return_value=True)
        self.to_checksum_address = lambda addr: Web3.to_checksum_address(addr) if isinstance(addr, str) else None
        self.from_wei = lambda amount, unit: float(amount) / 10**18  # Simple conversion
        
    def _create_mock_block(self, block_number=1000):
        """Create a mock block with transactions."""
        mock_block = MagicMock(spec=BlockData)
        mock_block.number = block_number
        mock_block.timestamp = int(datetime.datetime.now().timestamp())
        
        # Create mock transactions
        tx1 = MagicMock(spec=TxData)
        tx1.__getitem__ = lambda self, key: {
            "hash": b"tx_hash_1",
            "from": "0x1111111111111111111111111111111111111111",
            "to": "0x2222222222222222222222222222222222222222",
            "value": 1000000000000000000  # 1 ETH in wei
        }.get(key)
        tx1.get = lambda key, default=None: tx1.__getitem__(key) if key in ["hash", "from", "to", "value"] else default
        tx1["hash"].hex = lambda: "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        
        tx2 = MagicMock(spec=TxData)
        tx2.__getitem__ = lambda self, key: {
            "hash": b"tx_hash_2",
            "from": "0x3333333333333333333333333333333333333333",
            "to": "0x4444444444444444444444444444444444444444",
            "value": 2000000000000000000  # 2 ETH in wei
        }.get(key)
        tx2.get = lambda key, default=None: tx2.__getitem__(key) if key in ["hash", "from", "to", "value"] else default
        tx2["hash"].hex = lambda: "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        
        mock_block.transactions = [tx1, tx2]
        return mock_block


class TestDepositMonitor(unittest.TestCase):
    """Test cases for deposit monitoring functionality."""
    
    @patch('web3.Web3.HTTPProvider')
    @patch('src.account.deposit_monitor.get_user_wallets')
    def setUp(self, mock_get_wallets, mock_http_provider):
        """Set up test environment."""
        # Mock Web3 provider
        self.mock_web3 = MockWeb3Provider()
        mock_http_provider.return_value = self.mock_web3
        
        # Mock user wallets
        mock_wallet = MagicMock()
        mock_wallet.address = "0x2222222222222222222222222222222222222222"
        mock_wallet.user_id = "user123"
        mock_get_wallets.return_value = [mock_wallet]
        
        # Create test configuration
        self.config = BlockchainConfig(
            chain_id=56,
            rpc_url="https://example.com/rpc",
            confirmation_threshold=3,
            poll_interval=1
        )
        
        # Initialize processor with mocks
        with patch('web3.Web3', return_value=self.mock_web3):
            self.processor = TransactionProcessor(self.config)
            self.processor.web3 = self.mock_web3
    
    @patch('src.account.models.Transaction.save')
    @patch('src.account.models.Transaction.get_by_hash')
    def test_process_transaction(self, mock_get_by_hash, mock_save):
        """Test processing a blockchain transaction."""
        # Mock transaction not existing yet
        mock_get_by_hash.return_value = None
        mock_save.return_value = True
        
        # Create mock transaction data
        tx_data = {
            "hash": b"test_hash",
            "from": "0x1111111111111111111111111111111111111111",
            "to": "0x2222222222222222222222222222222222222222",
            "value": 1000000000000000000  # 1 ETH in wei
        }
        
        # Mock transaction object methods
        tx = MagicMock()
        tx.__getitem__ = lambda self, key: tx_data.get(key)
        tx.get = lambda key, default=None: tx_data.get(key, default)
        tx["hash"].hex = lambda: "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        
        # Process the transaction
        self.processor._process_transaction(tx, 1000, int(datetime.datetime.now().timestamp()))
        
        # Verify transaction was saved
        self.assertTrue(mock_save.called)
    
    @patch('src.account.wallet.Wallet.get_wallet_by_address')
    @patch('src.account.models.Transaction.save')
    @patch('src.account.models.Transaction.get_by_hash')
    def test_process_new_deposit(self, mock_get_by_hash, mock_save, mock_get_wallet):
        """Test processing a new deposit transaction."""
        # Mock transaction and wallet data
        mock_get_by_hash.return_value = None
        mock_save.return_value = True
        
        mock_wallet = MagicMock()
        mock_wallet.user_id = "user123"
        mock_get_wallet.return_value = mock_wallet
        
        # Create mock transaction data for a deposit
        tx_data = {
            "hash": b"deposit_hash",
            "from": "0x1111111111111111111111111111111111111111",
            "to": "0x2222222222222222222222222222222222222222",
            "value": 5000000000000000000  # 5 ETH in wei
        }
        
        # Mock transaction object methods
        tx = MagicMock()
        tx.__getitem__ = lambda self, key: tx_data.get(key)
        tx.get = lambda key, default=None: tx_data.get(key, default)
        tx["hash"].hex = lambda: "0xdeposit1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        
        # Process the transaction
        self.processor._process_transaction(tx, 1000, int(datetime.datetime.now().timestamp()))
        
        # Verify transaction was saved
        self.assertTrue(mock_save.called)
        
        # Verify wallet lookup was performed
        mock_get_wallet.assert_called_with("0x2222222222222222222222222222222222222222")
    
    @patch('src.account.models.Transaction.get_pending_by_chain')
    def test_check_pending_transactions(self, mock_get_pending):
        """Test checking and updating pending transactions."""
        # Create mock pending transactions
        mock_tx = MagicMock(spec=Transaction)
        mock_tx.hash = "0xpending1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        mock_tx.block_number = 990  # 10 blocks old
        mock_tx.status = TransactionStatus.PENDING
        mock_tx.save = MagicMock(return_value=True)
        
        mock_get_pending.return_value = [mock_tx]
        
        # Check pending transactions with current block at 1000
        # Should confirm transactions with at least 3 confirmations (set in config)
        with patch.object(self.processor, '_confirm_transaction') as mock_confirm:
            self.processor._check_pending_transactions()
            mock_confirm.assert_called_with(mock_tx)
    
    @patch('src.account.deposit_monitor.Transaction')
    def test_confirm_transaction(self, mock_tx_class):
        """Test transaction confirmation process."""
        # Create mock transaction
        mock_tx = MagicMock(spec=Transaction)
        mock_tx.hash = "0xconfirm1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        mock_tx.status = TransactionStatus.PENDING
        mock_tx.save = MagicMock(return_value=True)
        
        # Setup for update_user_balance
        with patch.object(self.processor, '_update_user_balance') as mock_update_balance:
            # Confirm the transaction
            self.processor._confirm_transaction(mock_tx)
            
            # Verify status was updated
            self.assertEqual(mock_tx.status, TransactionStatus.CONFIRMED)
            self.assertTrue(mock_tx.save.called)
            
            # Verify balance was updated
            mock_update_balance.assert_called_with(mock_tx)
    
    def test_service_initialization(self):
        """Test deposit monitor service initialization."""
        # Create service instance
        service = DepositMonitorService()
        
        # Verify a BSC processor was added by default
        self.assertIn(56, service.processors)  # BSC chain ID is 56
        
        # Test adding a new blockchain
        test_config = BlockchainConfig(
            chain_id=97,  # BSC testnet
            rpc_url="https://data-seed-prebsc-1-s1.binance.org:8545"
        )
        
        with patch('src.account.deposit_monitor.TransactionProcessor') as mock_processor_class:
            mock_processor = MagicMock()
            mock_processor_class.return_value = mock_processor
            
            service.add_blockchain(test_config)
            self.assertIn(97, service.processors)
            
            # Test starting the service
            service.start()
            mock_processor.start.assert_called()
            
            # Test stopping the service
            service.running = True
            mock_processor.running = True
            service.stop()
            mock_processor.stop.assert_called()


if __name__ == '__main__':
    unittest.main() 