"""
Unit tests for the BEP20 wallet integration.
"""
import unittest
from unittest.mock import patch, MagicMock
import os
import json
from web3 import Web3

from .models import Wallet, WalletType
from . import wallet


class TestWalletModule(unittest.TestCase):
    """Test class for the wallet module."""
    
    def setUp(self):
        """Set up test environment."""
        # Test encryption key
        os.environ['WALLET_ENCRYPTION_KEY'] = 'OzMPLzkfqQQKHOGPg9q8SZfIOlJbkBqn-JFfBKLYTvA='
        
        # Test user ID
        self.user_id = "test_user_123"
        
        # Test wallet data
        self.test_address = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
        self.test_private_key = "0x5367d0bbadad9f8b0e2863bc9c69a7c012b9f83a96ce407b24cc26c69afd2a0c"
        self.test_password = "StrongTestPassword123!"
        
    @patch('src.account.wallet.save_wallet_to_db')
    def test_create_wallet(self, mock_save_wallet):
        """Test wallet creation."""
        # Mock save_wallet_to_db to return a wallet ID
        mock_save_wallet.return_value = 1
        
        # Test wallet creation
        test_wallet = wallet.create_wallet(
            user_id=self.user_id,
            chain_id=wallet.BSC_TESTNET_CHAIN_ID,
            wallet_type=WalletType.HOT,
            password=self.test_password,
            name="Test Wallet"
        )
        
        # Assertions
        self.assertEqual(test_wallet.user_id, self.user_id)
        self.assertEqual(test_wallet.chain_id, wallet.BSC_TESTNET_CHAIN_ID)
        self.assertEqual(test_wallet.wallet_type, WalletType.HOT)
        self.assertEqual(test_wallet.name, "Test Wallet")
        self.assertTrue(test_wallet.encrypted_private_key is not None)
        self.assertTrue(test_wallet.address.startswith("0x"))
        self.assertEqual(len(test_wallet.address), 42)
        
        # Verify save_wallet_to_db was called once
        mock_save_wallet.assert_called_once()
        
    def test_encrypt_decrypt_private_key(self):
        """Test private key encryption and decryption."""
        # Encrypt a test private key
        encrypted = wallet.encrypt_private_key(self.test_private_key, self.test_password)
        
        # Check that encrypted data is a JSON string
        self.assertTrue(isinstance(encrypted, str))
        encrypted_data = json.loads(encrypted)
        self.assertTrue('salt' in encrypted_data)
        self.assertTrue('data' in encrypted_data)
        
        # Decrypt the private key
        decrypted = wallet.decrypt_private_key(encrypted, self.test_password)
        
        # Check that decryption returns the original private key
        self.assertEqual(decrypted, self.test_private_key)
        
        # Test decryption with wrong password
        with self.assertRaises(ValueError):
            wallet.decrypt_private_key(encrypted, "WrongPassword")
            
    def test_derive_key(self):
        """Test key derivation."""
        # Derive a key with a specific password and salt
        password = "TestPassword"
        salt = b'0123456789abcdef'
        
        # Call derive_key with the same password and salt twice
        key1, salt1 = wallet.derive_key(password, salt)
        key2, salt2 = wallet.derive_key(password, salt)
        
        # Check that the same inputs produce the same outputs
        self.assertEqual(key1, key2)
        self.assertEqual(salt1, salt2)
        
        # Call derive_key with different passwords
        key3, _ = wallet.derive_key("DifferentPassword", salt)
        
        # Check that different passwords produce different keys
        self.assertNotEqual(key1, key3)
        
    def test_is_valid_bep20_address(self):
        """Test BEP20 address validation."""
        # Valid address
        self.assertTrue(wallet.is_valid_bep20_address(self.test_address))
        
        # Invalid addresses
        self.assertFalse(wallet.is_valid_bep20_address("0x1234"))  # Too short
        self.assertFalse(wallet.is_valid_bep20_address("1234567890abcdef1234567890abcdef12345678"))  # Missing 0x prefix
        self.assertFalse(wallet.is_valid_bep20_address("0xXYZ4567890abcdef1234567890abcdef12345678"))  # Invalid characters
        
    @patch('src.account.wallet.save_wallet_to_db')
    def test_import_wallet_from_private_key(self, mock_save_wallet):
        """Test wallet import from private key."""
        # Mock save_wallet_to_db to return a wallet ID
        mock_save_wallet.return_value = 1
        
        # Test wallet import
        test_wallet = wallet.import_wallet_from_private_key(
            user_id=self.user_id,
            private_key=self.test_private_key,
            chain_id=wallet.BSC_TESTNET_CHAIN_ID,
            wallet_type=WalletType.HOT,
            password=self.test_password,
            name="Imported Wallet"
        )
        
        # Assertions
        self.assertEqual(test_wallet.user_id, self.user_id)
        self.assertEqual(test_wallet.chain_id, wallet.BSC_TESTNET_CHAIN_ID)
        self.assertEqual(test_wallet.wallet_type, WalletType.HOT)
        self.assertEqual(test_wallet.name, "Imported Wallet")
        self.assertTrue(test_wallet.encrypted_private_key is not None)
        
        # Verify save_wallet_to_db was called once
        mock_save_wallet.assert_called_once()
        
    @patch('src.db.connection.execute_query')
    def test_get_wallets_by_user_id(self, mock_execute_query):
        """Test retrieving wallets by user ID."""
        # Mock database response
        mock_execute_query.return_value = [
            {
                'id': 1,
                'user_id': self.user_id,
                'address': self.test_address,
                'wallet_type': 'hot',
                'chain_id': wallet.BSC_TESTNET_CHAIN_ID,
                'encrypted_private_key': 'encrypted_key_data',
                'name': 'Test Wallet',
                'is_default': True,
                'created_at': '2023-01-01T00:00:00',
                'updated_at': '2023-01-01T00:00:00'
            }
        ]
        
        # Call get_wallets_by_user_id
        wallets = wallet.get_wallets_by_user_id(self.user_id)
        
        # Assertions
        self.assertEqual(len(wallets), 1)
        self.assertEqual(wallets[0].user_id, self.user_id)
        self.assertEqual(wallets[0].address, self.test_address)
        self.assertEqual(wallets[0].wallet_type, WalletType.HOT)
        
        # Verify execute_query was called with correct parameters
        mock_execute_query.assert_called_once()
        args = mock_execute_query.call_args[0]
        self.assertTrue(self.user_id in args[1])
        
    @patch('src.account.wallet.get_web3')
    def test_get_bnb_balance(self, mock_get_web3):
        """Test BNB balance retrieval."""
        # Create mock Web3 instance
        mock_web3 = MagicMock()
        mock_eth = MagicMock()
        mock_web3.eth = mock_eth
        mock_web3.from_wei.return_value = 1.5
        mock_eth.get_balance.return_value = 1500000000000000000  # 1.5 BNB in wei
        
        # Set up the mock
        mock_get_web3.return_value = mock_web3
        
        # Call get_bnb_balance
        balance = wallet.get_bnb_balance(self.test_address, wallet.BSC_TESTNET_CHAIN_ID)
        
        # Assertions
        self.assertEqual(balance, 1.5)
        mock_eth.get_balance.assert_called_once_with(self.test_address)
        mock_web3.from_wei.assert_called_once()
        
    @patch('src.account.wallet.get_web3')
    def test_get_token_balance(self, mock_get_web3):
        """Test token balance retrieval."""
        # Create mock objects
        mock_web3 = MagicMock()
        mock_contract = MagicMock()
        mock_functions = MagicMock()
        mock_balance_func = MagicMock()
        mock_decimals_func = MagicMock()
        
        # Set up the mock chain
        mock_get_web3.return_value = mock_web3
        mock_web3.eth.contract.return_value = mock_contract
        mock_contract.functions = mock_functions
        mock_functions.balanceOf.return_value = mock_balance_func
        mock_functions.decimals.return_value = mock_decimals_func
        mock_balance_func.call.return_value = 15000000000  # 15 tokens with 9 decimals
        mock_decimals_func.call.return_value = 9
        
        # Test token contract address
        token_address = "0x0123456789abcdef0123456789abcdef01234567"
        
        # Call get_token_balance
        balance = wallet.get_token_balance(self.test_address, token_address, wallet.BSC_TESTNET_CHAIN_ID)
        
        # Assertions
        self.assertEqual(balance, 15.0)
        mock_web3.eth.contract.assert_called_once_with(address=token_address, abi=wallet.BEP20_ABI)
        mock_functions.balanceOf.assert_called_once_with(self.test_address)
        mock_functions.decimals.assert_called_once()
        mock_balance_func.call.assert_called_once()
        mock_decimals_func.call.assert_called_once()


if __name__ == '__main__':
    unittest.main() 