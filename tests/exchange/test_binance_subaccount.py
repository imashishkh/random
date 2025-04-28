"""
Tests for Binance sub-account creation functionality.
"""

import os
import unittest
from unittest.mock import patch, MagicMock

from src.exchange.binance_api_client import BinanceApiClient
from src.exchange.exceptions import AuthenticationError, ExchangeError


class TestBinanceSubaccountCreation(unittest.TestCase):
    """Test cases for Binance sub-account creation functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock environment variables
        self.env_patcher = patch.dict('os.environ', {
            'BINANCE_API_KEY': 'test_api_key',
            'BINANCE_API_SECRET': 'test_api_secret'
        })
        self.env_patcher.start()
        
        # Create the client
        self.client = BinanceApiClient(
            testnet=True,
            enable_rate_limit=False
        )
        
        # Replace the make_request method with a mock
        self.client.make_request = MagicMock()
    
    def tearDown(self):
        """Clean up after tests."""
        self.env_patcher.stop()
    
    def test_create_virtual_subaccount_success(self):
        """Test successful sub-account creation."""
        # Setup mock response
        mock_response = {
            "subAccountId": "test-subaccount-123",
            "email": "test@example.com",
            "status": "ACTIVE",
            "activated": True,
            "createTime": 1620000000000
        }
        self.client.make_request.return_value = mock_response
        
        # Call the method
        result = self.client.create_virtual_subaccount(
            subaccount_name="TestAccount",
            email="test@example.com"
        )
        
        # Verify the result
        self.assertEqual(result, mock_response)
        
        # Verify the correct API endpoint was called
        self.client.make_request.assert_called_once()
        args, kwargs = self.client.make_request.call_args
        self.assertEqual(args[0], 'POST')
        self.assertEqual(args[1], '/sapi/v1/sub-account/virtualSubAccount')
        self.assertTrue(kwargs['authenticated'])
        self.assertEqual(kwargs['rate_limit_category'], 'account')
        
        # Verify correct parameters were passed
        params = kwargs['params']
        self.assertEqual(params['subAccountString'], 'TestAccount')
        self.assertEqual(params['email'], 'test@example.com')
        self.assertIn('recvWindow', params)
    
    def test_create_virtual_subaccount_missing_credentials(self):
        """Test sub-account creation with missing credentials."""
        # Remove the API credentials
        with patch.dict('os.environ', {}, clear=True):
            client = BinanceApiClient(testnet=True)
            
            # Mock the make_request method to raise AuthenticationError
            client.make_request = MagicMock(side_effect=AuthenticationError(
                "API key and secret required for authenticated requests"
            ))
            
            # Call the method and expect an exception
            with self.assertRaises(AuthenticationError):
                client.create_virtual_subaccount(
                    subaccount_name="TestAccount",
                    email="test@example.com"
                )
    
    def test_create_subaccount_api_key_success(self):
        """Test successful API key generation for a sub-account."""
        # Setup mock response
        mock_response = {
            "apiKey": "FAKE_API_KEY",
            "secretKey": "FAKE_SECRET_KEY",
            "permissions": ["READ_INFO", "SPOT_TRADING"],
            "isRestricted": False,
            "keyType": "Ed25519",
            "createTime": 1620000000000
        }
        self.client.make_request.return_value = mock_response
        
        # Call the method
        result = self.client.create_subaccount_api_key(
            subaccount_id="test-subaccount-123",
            label="Trading Bot",
            permissions=["READ_INFO", "SPOT_TRADING"],
            key_type="Ed25519"
        )
        
        # Verify the result
        self.assertEqual(result, mock_response)
        
        # Verify the correct API endpoint was called
        self.client.make_request.assert_called_once()
        args, kwargs = self.client.make_request.call_args
        self.assertEqual(args[0], 'POST')
        self.assertEqual(args[1], '/sapi/v1/sub-account/apiKey')
        self.assertTrue(kwargs['authenticated'])
        self.assertEqual(kwargs['rate_limit_category'], 'account')
        
        # Verify correct parameters were passed
        params = kwargs['params']
        self.assertEqual(params['subAccountId'], 'test-subaccount-123')
        self.assertEqual(params['subAccountApiKey'], 'Trading Bot')
        self.assertEqual(params['permissions'], 'READ_INFO,SPOT_TRADING')
        self.assertEqual(params['isRestricted'], 'false')
        self.assertEqual(params['keyType'], 'Ed25519')
        self.assertIn('recvWindow', params)
    
    def test_create_subaccount_api_key_with_ip_restriction(self):
        """Test API key generation with IP restrictions."""
        # Setup mock response
        mock_response = {
            "apiKey": "FAKE_API_KEY",
            "secretKey": "FAKE_SECRET_KEY",
            "permissions": ["READ_INFO"],
            "isRestricted": True,
            "keyType": "RSA",
            "createTime": 1620000000000
        }
        self.client.make_request.return_value = mock_response
        
        # Call the method with IP restrictions
        ip_list = "192.168.1.1,10.0.0.1"
        result = self.client.create_subaccount_api_key(
            subaccount_id="test-subaccount-123",
            label="Restricted API Key",
            permissions=["READ_INFO"],
            ip_restrict=True,
            ip_list=ip_list,
            key_type="RSA"
        )
        
        # Verify the result
        self.assertEqual(result, mock_response)
        
        # Verify the correct API endpoint was called
        args, kwargs = self.client.make_request.call_args
        
        # Verify correct parameters were passed
        params = kwargs['params']
        self.assertEqual(params['isRestricted'], 'true')
        self.assertEqual(params['ipRestrict'], '192.168.1.1,10.0.0.1')
        self.assertEqual(params['keyType'], 'RSA')


if __name__ == '__main__':
    unittest.main() 