"""
Test module for the MarketDataRepository.
"""
import time
import unittest
from .market_data.repository import MarketDataRepository

class TestMarketDataRepository(unittest.TestCase):
    """Test cases for the MarketDataRepository class."""
    
    def setUp(self):
        """Set up a fresh repository for each test."""
        self.repository = MarketDataRepository()
    
    def test_update_and_get_trade(self):
        """Test updating and retrieving trade data."""
        # Create test trade data
        trade_data = {
            "symbol": "BTCUSDT",
            "price": 50000.0,
            "quantity": 1.5,
            "timestamp": int(time.time() * 1000)
        }
        
        # Update repository
        self.repository.update_trade(trade_data)
        
        # Retrieve data
        retrieved_data = self.repository.get_latest_trade("BTCUSDT")
        
        # Verify data
        self.assertIsNotNone(retrieved_data)
        self.assertEqual(retrieved_data, trade_data)
    
    def test_update_and_get_ticker(self):
        """Test updating and retrieving ticker data."""
        # Create test ticker data
        ticker_data = {
            "symbol": "ETHUSDT",
            "price": 3000.0,
            "volume": 100.0,
            "timestamp": int(time.time() * 1000)
        }
        
        # Update repository
        self.repository.update_ticker(ticker_data)
        
        # Retrieve data
        retrieved_data = self.repository.get_latest_ticker("ETHUSDT")
        
        # Verify data
        self.assertIsNotNone(retrieved_data)
        self.assertEqual(retrieved_data, ticker_data)
    
    def test_update_and_get_book_ticker(self):
        """Test updating and retrieving book ticker data."""
        # Create test book ticker data
        book_ticker_data = {
            "symbol": "LTCUSDT",
            "bid_price": 200.0,
            "bid_qty": 5.0,
            "ask_price": 201.0,
            "ask_qty": 3.0,
            "timestamp": int(time.time() * 1000)
        }
        
        # Update repository
        self.repository.update_book_ticker(book_ticker_data)
        
        # Retrieve data
        retrieved_data = self.repository.get_latest_book_ticker("LTCUSDT")
        
        # Verify data
        self.assertIsNotNone(retrieved_data)
        self.assertEqual(retrieved_data, book_ticker_data)
    
    def test_ttl_expiration(self):
        """Test that data expires based on TTL."""
        # Create test trade data
        trade_data = {
            "symbol": "XRPUSDT",
            "price": 1.0,
            "quantity": 1000.0,
            "timestamp": int(time.time() * 1000)
        }
        
        # Set a very short TTL
        self.repository.set_ttl("trades", 0.1)  # 100ms TTL
        
        # Update repository
        self.repository.update_trade(trade_data)
        
        # Verify data is available immediately
        retrieved_data = self.repository.get_latest_trade("XRPUSDT")
        self.assertIsNotNone(retrieved_data)
        
        # Wait for TTL to expire
        time.sleep(0.2)
        
        # Verify data is no longer available
        retrieved_data = self.repository.get_latest_trade("XRPUSDT")
        self.assertIsNone(retrieved_data)
    
    def test_clean_expired_data(self):
        """Test cleaning expired data."""
        # Create test data for multiple symbols
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]
        
        # Set a short TTL
        self.repository.set_ttl("trades", 0.1)  # 100ms TTL
        
        # Update repository
        for symbol in symbols:
            trade_data = {
                "symbol": symbol,
                "price": 1.0,
                "quantity": 1.0,
                "timestamp": int(time.time() * 1000)
            }
            self.repository.update_trade(trade_data)
        
        # Verify all data is stored
        self.assertEqual(len(self.repository.trades), 3)
        
        # Wait for TTL to expire
        time.sleep(0.2)
        
        # Clean expired data
        self.repository.clean_expired_data()
        
        # Verify all data was cleaned
        self.assertEqual(len(self.repository.trades), 0)

if __name__ == "__main__":
    unittest.main() 