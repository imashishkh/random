"""
Tests for MongoDB modules.

These tests require a running MongoDB instance. Tests will create
temporary collections with a test_ prefix that will be dropped after testing.
"""

import unittest
import os
import sys
import logging
import datetime
import uuid
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Import modules to test
from src.db.mongodb_connection import (
    get_mongodb_client, get_mongodb_database, 
    get_collection, close_mongodb_connection
)
from src.db.mongodb_operations import (
    create_trade, get_trade_by_id, get_trades, update_trade, close_trade, delete_trade,
    create_account, get_account_by_id, get_accounts, update_account, delete_account
)

# Configure logging - set to ERROR to minimize output during tests
logging.basicConfig(level=logging.ERROR)

# Test database name - this will be created and dropped during testing
TEST_DB_NAME = "forex_trading_test"

# Set test environment variables
os.environ["MONGODB_DB_NAME"] = TEST_DB_NAME


class TestMongoDBConnection(unittest.TestCase):
    """Test MongoDB connection functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test database."""
        try:
            cls.client = get_mongodb_client()
            # Verify we can connect to MongoDB
            cls.client.admin.command('ping')
        except Exception as e:
            raise unittest.SkipTest(f"MongoDB server not available: {e}")
    
    @classmethod
    def tearDownClass(cls):
        """Drop test database and close connection."""
        if hasattr(cls, 'client'):
            cls.client.drop_database(TEST_DB_NAME)
            close_mongodb_connection()
    
    def test_get_mongodb_database(self):
        """Test getting MongoDB database."""
        db = get_mongodb_database()
        self.assertIsNotNone(db)
        self.assertEqual(db.name, TEST_DB_NAME)
    
    def test_get_collection(self):
        """Test getting a collection."""
        collection = get_collection('trades')
        self.assertIsNotNone(collection)
        self.assertEqual(collection.name, 'trades')


class TestMongoDBOperations(unittest.TestCase):
    """Test MongoDB CRUD operations."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test database."""
        try:
            cls.client = get_mongodb_client()
            # Verify we can connect to MongoDB
            cls.client.admin.command('ping')
            cls.db = get_mongodb_database()
        except Exception as e:
            raise unittest.SkipTest(f"MongoDB server not available: {e}")
    
    @classmethod
    def tearDownClass(cls):
        """Drop test database and close connection."""
        if hasattr(cls, 'client'):
            cls.client.drop_database(TEST_DB_NAME)
            close_mongodb_connection()
    
    def test_account_crud(self):
        """Test account CRUD operations."""
        # Create account
        account_data = {
            'account_id': str(uuid.uuid4()),
            'name': 'Test Account',
            'broker': 'Test Broker',
            'account_type': 'DEMO',
            'currency': 'USD',
            'balance': 10000.0,
            'equity': 10000.0,
            'leverage': 100,
            'is_active': True
        }
        
        account_id = create_account(account_data)
        self.assertIsNotNone(account_id)
        
        # Get account
        account = get_account_by_id(account_id)
        self.assertIsNotNone(account)
        self.assertEqual(account['name'], 'Test Account')
        
        # Update account
        update_result = update_account(account_id, {'balance': 11000.0})
        self.assertTrue(update_result)
        
        # Verify update
        updated_account = get_account_by_id(account_id)
        self.assertEqual(updated_account['balance'], 11000.0)
        
        # Get all accounts
        accounts = get_accounts()
        self.assertGreaterEqual(len(accounts), 1)
        
        # Delete account
        delete_result = delete_account(account_id)
        self.assertTrue(delete_result)
        
        # Verify deletion
        deleted_account = get_account_by_id(account_id)
        self.assertIsNone(deleted_account)
    
    def test_trade_crud(self):
        """Test trade CRUD operations."""
        # First create an account for the trade
        account_data = {
            'account_id': str(uuid.uuid4()),
            'name': 'Trade Test Account',
            'broker': 'Test Broker',
            'currency': 'USD',
            'balance': 10000.0,
            'is_active': True
        }
        
        account_id = create_account(account_data)
        
        # Create trade
        trade_data = {
            'trade_id': str(uuid.uuid4()),
            'account_id': account_id,
            'symbol': 'EURUSD',
            'direction': 'BUY',
            'open_time': datetime.datetime.utcnow(),
            'open_price': 1.1000,
            'lot_size': 0.1,
            'status': 'OPEN'
        }
        
        trade_id = create_trade(trade_data)
        self.assertIsNotNone(trade_id)
        
        # Get trade
        trade = get_trade_by_id(trade_id)
        self.assertIsNotNone(trade)
        self.assertEqual(trade['symbol'], 'EURUSD')
        
        # Update trade
        update_result = update_trade(trade_id, {'notes': 'Test note'})
        self.assertTrue(update_result)
        
        # Verify update
        updated_trade = get_trade_by_id(trade_id)
        self.assertEqual(updated_trade['notes'], 'Test note')
        
        # Get all trades
        trades = get_trades(account_id=account_id)
        self.assertGreaterEqual(len(trades), 1)
        
        # Close trade
        close_result = close_trade(
            trade_id=trade_id,
            close_price=1.1050,
            pnl=5.0
        )
        self.assertTrue(close_result)
        
        # Verify trade is closed
        closed_trade = get_trade_by_id(trade_id)
        self.assertEqual(closed_trade['status'], 'CLOSED')
        self.assertEqual(closed_trade['pnl'], 5.0)
        
        # Delete trade
        delete_result = delete_trade(trade_id)
        self.assertTrue(delete_result)
        
        # Clean up test account
        delete_account(account_id)


if __name__ == '__main__':
    unittest.main() 