"""
Unit tests for the PositionDataFetcher class
"""

import unittest
from unittest.mock import patch, MagicMock, ANY
import time
import json
from src.risk.position_fetcher import PositionDataFetcher
from src.exchange.exceptions import RateLimitError, NetworkError


class TestPositionDataFetcher(unittest.TestCase):
    """Test cases for PositionDataFetcher"""
    
    def setUp(self):
        """Setup test environment before each test"""
        # Create patcher for BinanceApiClient
        self.client_patcher = patch('src.risk.position_fetcher.BinanceApiClient')
        self.mock_client_class = self.client_patcher.start()
        self.mock_client = self.mock_client_class.return_value
        
        # Sample position data for testing
        self.sample_position_data = [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.5",
                "entryPrice": "50000",
                "markPrice": "51000",
                "unRealizedProfit": "500",
                "liquidationPrice": "45000",
                "leverage": "10",
                "marginType": "isolated",
                "isolatedMargin": "2500",
                "isAutoAddMargin": "false",
                "positionSide": "BOTH",
                "breakEvenPrice": "50100"
            },
            {
                "symbol": "ETHUSDT",
                "positionAmt": "0",  # Zero position, should be filtered out
                "entryPrice": "0",
                "markPrice": "2000",
                "unRealizedProfit": "0",
                "liquidationPrice": "0",
                "leverage": "10",
                "marginType": "cross",
                "isolatedMargin": "0",
                "isAutoAddMargin": "false",
                "positionSide": "BOTH",
                "breakEvenPrice": "0"
            },
            {
                "symbol": "SOLUSDT",
                "positionAmt": "-10",  # Short position
                "entryPrice": "100",
                "markPrice": "95",
                "unRealizedProfit": "50",
                "liquidationPrice": "110",
                "leverage": "5",
                "marginType": "cross",
                "isolatedMargin": "0",
                "isAutoAddMargin": "false",
                "positionSide": "BOTH",
                "breakEvenPrice": "99.5"
            }
        ]
        
    def tearDown(self):
        """Clean up after each test"""
        self.client_patcher.stop()
        
        # Reset singleton instance
        PositionDataFetcher._instance = None
    
    def test_fetch_positions_success(self):
        """Test successful position fetching"""
        # Configure mock
        self.mock_client.make_request.return_value = self.sample_position_data
        
        # Create fetcher and get positions
        fetcher = PositionDataFetcher(api_key="test_key", api_secret="test_secret")
        positions = fetcher.fetch_positions()
        
        # Verify results
        self.assertEqual(len(positions), 2)  # Zero position should be filtered out
        self.assertEqual(positions[0]['symbol'], "BTCUSDT")
        self.assertEqual(positions[1]['symbol'], "SOLUSDT")
        self.assertEqual(positions[0]['position_amount'], 0.5)
        self.assertEqual(positions[1]['position_amount'], -10)
        self.assertEqual(positions[0]['notional_value'], 0.5 * 51000)
        
        # Verify API call
        self.mock_client.make_request.assert_called_once_with(
            method="GET",
            endpoint="/fapi/v2/positionRisk",
            authenticated=True,
            rate_limit_category="trading"
        )
    
    def test_caching_behavior(self):
        """Test that caching works correctly"""
        # Configure mock
        self.mock_client.make_request.return_value = self.sample_position_data
        
        # Create fetcher with short cache TTL
        fetcher = PositionDataFetcher(cache_ttl_seconds=1)
        
        # First call should hit the API
        positions1 = fetcher.fetch_positions()
        self.assertEqual(len(positions1), 2)
        self.mock_client.make_request.assert_called_once()
        
        # Second immediate call should use cache
        self.mock_client.make_request.reset_mock()
        positions2 = fetcher.fetch_positions()
        self.assertEqual(len(positions2), 2)
        self.mock_client.make_request.assert_not_called()
        
        # Call with force_refresh should ignore cache
        self.mock_client.make_request.reset_mock()
        positions3 = fetcher.fetch_positions(force_refresh=True)
        self.assertEqual(len(positions3), 2)
        self.mock_client.make_request.assert_called_once()
        
        # Wait for cache to expire
        time.sleep(1.5)
        
        # Call after cache expired should hit API again
        self.mock_client.make_request.reset_mock()
        positions4 = fetcher.fetch_positions()
        self.assertEqual(len(positions4), 2)
        self.mock_client.make_request.assert_called_once()
    
    @patch('src.risk.position_fetcher.time')
    def test_transform_position_data(self, mock_time):
        """Test position data transformation"""
        # Set mock time
        mock_time.time.return_value = 1000
        
        # Configure mock client
        self.mock_client.make_request.return_value = self.sample_position_data
        
        # Create fetcher and get positions
        fetcher = PositionDataFetcher()
        positions = fetcher.fetch_positions()
        
        # Check first position transformation
        btc_position = positions[0]
        self.assertEqual(btc_position['symbol'], "BTCUSDT")
        self.assertEqual(btc_position['position_amount'], 0.5)
        self.assertEqual(btc_position['entry_price'], 50000)
        self.assertEqual(btc_position['mark_price'], 51000)
        self.assertEqual(btc_position['unreal_pnl'], 500)
        self.assertEqual(btc_position['liquidation_price'], 45000)
        self.assertEqual(btc_position['leverage'], 10)
        self.assertEqual(btc_position['notional_value'], 25500)  # 0.5 * 51000
        self.assertEqual(btc_position['margin_type'], "isolated")
        self.assertEqual(btc_position['isolated_margin'], 2500)
        self.assertEqual(btc_position['is_auto_add_margin'], False)
        self.assertEqual(btc_position['position_side'], "BOTH")
        self.assertEqual(btc_position['break_even_price'], 50100)
        self.assertEqual(btc_position['timestamp'], 1000 * 1000)
        self.assertIn('raw', btc_position)
    
    def test_get_position_by_symbol(self):
        """Test fetching a position by symbol"""
        # Configure mock
        self.mock_client.make_request.return_value = self.sample_position_data
        
        # Create fetcher
        fetcher = PositionDataFetcher()
        
        # Get specific positions
        btc_position = fetcher.get_position_by_symbol("BTCUSDT")
        sol_position = fetcher.get_position_by_symbol("SOLUSDT")
        nonexistent_position = fetcher.get_position_by_symbol("DOGEUSDT")
        
        # Verify results
        self.assertIsNotNone(btc_position)
        self.assertEqual(btc_position['symbol'], "BTCUSDT")
        
        self.assertIsNotNone(sol_position)
        self.assertEqual(sol_position['symbol'], "SOLUSDT")
        
        self.assertIsNone(nonexistent_position)
    
    def test_error_handling(self):
        """Test error handling for API failures"""
        # Configure mock to raise an error
        self.mock_client.make_request.side_effect = NetworkError("Connection failed")
        
        # Create fetcher
        fetcher = PositionDataFetcher()
        
        # Attempt to fetch positions (should raise error on first try with empty cache)
        with self.assertRaises(NetworkError):
            fetcher.fetch_positions()
        
        # Set a mock successful response to populate cache
        self.mock_client.make_request.side_effect = None
        self.mock_client.make_request.return_value = self.sample_position_data
        fetcher.fetch_positions()
        
        # Now set error again
        self.mock_client.make_request.side_effect = NetworkError("Connection failed")
        
        # Should return cached data on error
        positions = fetcher.fetch_positions()
        self.assertEqual(len(positions), 2)
    
    def test_rate_limit_handling(self):
        """Test handling of rate limit errors"""
        # First set normal response to populate cache
        self.mock_client.make_request.return_value = self.sample_position_data
        fetcher = PositionDataFetcher()
        fetcher.fetch_positions()
        
        # Then simulate rate limit error
        self.mock_client.make_request.side_effect = RateLimitError("Rate limit exceeded")
        
        # Should return cached data on rate limit error
        positions = fetcher.fetch_positions()
        self.assertEqual(len(positions), 2)
    
    def test_singleton_pattern(self):
        """Test that the singleton pattern works correctly"""
        # Create two instances of PositionDataFetcher
        fetcher1 = PositionDataFetcher(api_key="test1", api_secret="secret1")
        fetcher2 = PositionDataFetcher(api_key="test2", api_secret="secret2")
        
        # They should be the same object
        self.assertIs(fetcher1, fetcher2)
        
        # The second initialization should not override the first one's parameters
        self.assertEqual(fetcher2.api_key, "test1")
        self.assertEqual(fetcher2.api_secret, "secret1")
    
    def test_get_total_exposure(self):
        """Test calculation of total exposure"""
        # Configure mock
        self.mock_client.make_request.return_value = self.sample_position_data
        
        # Create fetcher
        fetcher = PositionDataFetcher()
        
        # Calculate total exposure
        total_exposure = fetcher.get_total_exposure()
        
        # Expected: BTC (0.5 * 51000) + SOL (10 * 95) = 25500 + 950 = 26450
        self.assertEqual(total_exposure, 26450)


if __name__ == '__main__':
    unittest.main()
