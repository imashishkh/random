"""
Tests for the SecretManager implementation.

These tests verify that the SecretManager correctly encrypts, decrypts,
and manages secrets.
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta

from src.security.secrets import create_secret_manager
from src.security.secrets.base import SecretStatus


class TestSecretManager(unittest.TestCase):
    """Test suite for the SecretManager implementation."""
    
    def setUp(self):
        """Set up test environment."""
        # Create a temporary directory for test secrets
        self.test_dir = tempfile.mkdtemp()
        
        # Create a secret manager with the test directory
        self.secret_manager = create_secret_manager(
            manager_type='keyring',
            config={'secrets_dir': self.test_dir}
        )
        
        # Test data
        self.sub_account_id = 'test-account-123'
        self.secret_data = {'api_key': 'test-api-key', 'api_secret': 'test-api-secret'}
        self.metadata = {'exchange': 'binance', 'permissions': ['read', 'trade']}
    
    def tearDown(self):
        """Clean up after tests."""
        # Remove the temporary directory
        shutil.rmtree(self.test_dir)
    
    def test_store_and_retrieve_secret(self):
        """Test storing and retrieving a secret."""
        # Store a secret
        self.secret_manager.store_secret(
            self.sub_account_id,
            self.secret_data,
            metadata=self.metadata
        )
        
        # Verify the secret exists
        self.assertTrue(self.secret_manager.secret_exists(self.sub_account_id))
        
        # Retrieve the secret
        retrieved_secret = self.secret_manager.retrieve_secret(self.sub_account_id)
        
        # Verify the retrieved secret matches the original
        self.assertEqual(retrieved_secret['api_key'], self.secret_data['api_key'])
        self.assertEqual(retrieved_secret['api_secret'], self.secret_data['api_secret'])
    
    def test_list_secrets(self):
        """Test listing secrets."""
        # Store multiple secrets
        account_ids = [f'test-account-{i}' for i in range(3)]
        for account_id in account_ids:
            self.secret_manager.store_secret(account_id, self.secret_data)
        
        # List secrets
        secrets = self.secret_manager.list_secrets()
        
        # Verify all account IDs are in the list
        for account_id in account_ids:
            self.assertIn(account_id, secrets)
    
    def test_delete_secret(self):
        """Test deleting a secret."""
        # Store a secret
        self.secret_manager.store_secret(self.sub_account_id, self.secret_data)
        
        # Verify the secret exists
        self.assertTrue(self.secret_manager.secret_exists(self.sub_account_id))
        
        # Delete the secret
        self.secret_manager.delete_secret(self.sub_account_id)
        
        # Verify the secret no longer exists
        self.assertFalse(self.secret_manager.secret_exists(self.sub_account_id))
    
    def test_rotate_secret(self):
        """Test rotating a secret."""
        # Store a secret
        self.secret_manager.store_secret(self.sub_account_id, self.secret_data)
        
        # Rotate with new data
        new_secret_data = {'api_key': 'new-api-key', 'api_secret': 'new-api-secret'}
        self.secret_manager.rotate_secret(self.sub_account_id, new_secret_data)
        
        # Retrieve the secret
        retrieved_secret = self.secret_manager.retrieve_secret(self.sub_account_id)
        
        # Verify the retrieved secret matches the new data
        self.assertEqual(retrieved_secret['api_key'], new_secret_data['api_key'])
        self.assertEqual(retrieved_secret['api_secret'], new_secret_data['api_secret'])
    
    def test_expired_secret(self):
        """Test handling of expired secrets."""
        # Store a secret with an expiration in the past
        expiration = datetime.now() - timedelta(hours=1)  # 1 hour ago
        self.secret_manager.store_secret(
            self.sub_account_id,
            self.secret_data,
            expiration=expiration
        )
        
        # Verify the secret exists
        self.assertTrue(self.secret_manager.secret_exists(self.sub_account_id))
        
        # Attempt to retrieve the secret should raise ValueError
        with self.assertRaises(ValueError):
            self.secret_manager.retrieve_secret(self.sub_account_id)
    
    def test_nonexistent_secret(self):
        """Test handling of nonexistent secrets."""
        # Attempt to retrieve a nonexistent secret should raise KeyError
        with self.assertRaises(KeyError):
            self.secret_manager.retrieve_secret('nonexistent-account')
        
        # Attempt to delete a nonexistent secret should raise KeyError
        with self.assertRaises(KeyError):
            self.secret_manager.delete_secret('nonexistent-account')
        
        # Attempt to rotate a nonexistent secret should raise KeyError
        with self.assertRaises(KeyError):
            self.secret_manager.rotate_secret('nonexistent-account')


if __name__ == "__main__":
    unittest.main() 