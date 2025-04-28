"""
Unit tests for the IndicatorCalculator class.
"""
import unittest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
import os
import tempfile
import pickle
import hashlib
import json

from .calculator import IndicatorCalculator
from .factory import IndicatorFactory


class TestIndicatorCalculator(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures, if any."""
        # Mock Redis client
        self.redis_client = MagicMock()
        self.redis_client.get.return_value = None
        
        # Create a temporary directory for disk cache
        self.temp_dir = tempfile.mkdtemp()
        
        # Create calculator instance
        self.calculator = IndicatorCalculator(
            redis_client=self.redis_client,
            disk_cache_dir=self.temp_dir,
            cache_ttl=3600
        )
        
        # Sample market data
        self.market_data = pd.DataFrame({
            'open': np.random.uniform(100, 200, 100),
            'high': np.random.uniform(150, 250, 100),
            'low': np.random.uniform(50, 150, 100),
            'close': np.random.uniform(100, 200, 100),
            'volume': np.random.uniform(1000, 10000, 100)
        })
        
        # Sample metadata
        self.metadata = {
            'symbol': 'EUR/USD',
            'timeframe': '1h'
        }

    def tearDown(self):
        """Tear down test fixtures, if any."""
        # Clean up the temporary directory
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_calculate_no_cache(self):
        """Test calculate method with caching disabled."""
        # Register a mock indicator
        def mock_sma(data, period=14):
            return pd.Series(np.ones(len(data)) * 150, index=data.index)
        
        IndicatorFactory.register('MOCK_SMA', mock_sma)
        
        # Calculate with cache disabled
        result = self.calculator.calculate(
            'MOCK_SMA',
            self.market_data,
            params={'period': 14},
            use_cache=False,
            metadata=self.metadata
        )
        
        # Verify result
        self.assertIsInstance(result, pd.Series)
        self.assertEqual(len(result), len(self.market_data))
        self.assertTrue(all(result == 150))
        
        # Verify no cache operations were performed
        self.redis_client.get.assert_not_called()
        self.redis_client.setex.assert_not_called()

    def test_redis_cache_hit(self):
        """Test calculate method with Redis cache hit."""
        # Create mock cached result
        mock_result = pd.Series(np.ones(len(self.market_data)) * 200)
        cached_data = pickle.dumps(mock_result)
        
        # Set up Redis mock to return the cached result
        self.redis_client.get.return_value = cached_data
        
        # Calculate with cache enabled
        result = self.calculator.calculate(
            'SMA',
            self.market_data,
            params={'period': 14},
            use_cache=True,
            metadata=self.metadata
        )
        
        # Verify result matches cached data
        self.assertIsInstance(result, pd.Series)
        self.assertTrue(all(result == 200))
        
        # Verify Redis get was called
        self.redis_client.get.assert_called_once()

    def test_disk_cache_hit(self):
        """Test calculate method with disk cache hit."""
        # Create mock cached result
        mock_result = pd.Series(np.ones(len(self.market_data)) * 250)
        
        # Generate cache key
        cache_key = self.calculator._generate_cache_key(
            'SMA',
            self.market_data,
            {'period': 14},
            self.metadata
        )
        
        # Convert the Redis key to a disk path
        disk_key = hashlib.md5(cache_key.encode()).hexdigest()
        cache_path = os.path.join(self.temp_dir, disk_key)
        
        # Write to disk cache
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, 'wb') as f:
            pickle.dump(mock_result, f)
        
        # Set up Redis mock to return None (cache miss)
        self.redis_client.get.return_value = None
        
        # Calculate with cache enabled
        with patch.object(IndicatorFactory, 'get') as mock_get:
            result = self.calculator.calculate(
                'SMA',
                self.market_data,
                params={'period': 14},
                use_cache=True,
                metadata=self.metadata
            )
            
            # Verify factory.get was not called (cached result used)
            mock_get.assert_not_called()
        
        # Verify result matches disk cached data
        self.assertIsInstance(result, pd.Series)
        self.assertTrue(all(result == 250))

    def test_cache_key_generation(self):
        """Test cache key generation for consistency."""
        # Generate cache key
        key1 = self.calculator._generate_cache_key(
            'SMA',
            self.market_data,
            {'period': 14},
            self.metadata
        )
        
        # Generate another key with the same inputs
        key2 = self.calculator._generate_cache_key(
            'SMA',
            self.market_data,
            {'period': 14},
            self.metadata
        )
        
        # Generate a different key with different params
        key3 = self.calculator._generate_cache_key(
            'SMA',
            self.market_data,
            {'period': 20},
            self.metadata
        )
        
        # Verify keys
        self.assertEqual(key1, key2)  # Same inputs should produce same key
        self.assertNotEqual(key1, key3)  # Different inputs should produce different key

    def test_batch_calculate(self):
        """Test batch calculation of multiple indicators."""
        # Register mock indicators
        def mock_sma(data, period=14):
            return pd.Series(np.ones(len(data)) * 150, index=data.index)
        
        def mock_rsi(data, period=14):
            return pd.Series(np.ones(len(data)) * 50, index=data.index)
        
        IndicatorFactory.register('MOCK_SMA', mock_sma)
        IndicatorFactory.register('MOCK_RSI', mock_rsi)
        
        # Define indicators to calculate
        indicators = [
            {'name': 'MOCK_SMA', 'params': {'period': 14}},
            {'name': 'MOCK_RSI', 'params': {'period': 14}}
        ]
        
        # Perform batch calculation
        results = self.calculator.batch_calculate(
            indicators,
            self.market_data,
            use_cache=False,
            metadata=self.metadata
        )
        
        # Verify results
        self.assertIsInstance(results, dict)
        self.assertEqual(len(results), 2)
        self.assertIn('MOCK_SMA', results)
        self.assertIn('MOCK_RSI', results)
        self.assertTrue(all(results['MOCK_SMA'] == 150))
        self.assertTrue(all(results['MOCK_RSI'] == 50))

    def test_invalidate_cache_entry(self):
        """Test cache invalidation for a specific entry."""
        # Generate cache key
        cache_key = self.calculator._generate_cache_key(
            'SMA',
            self.market_data,
            {'period': 14},
            self.metadata
        )
        
        # Invalidate the cache entry
        self.calculator.invalidate_cache_entry(
            'SMA',
            self.market_data,
            {'period': 14},
            self.metadata
        )
        
        # Verify Redis delete was called
        self.redis_client.delete.assert_called_once_with(cache_key)
        
        # Verify disk cache was deleted if it exists
        disk_key = hashlib.md5(cache_key.encode()).hexdigest()
        cache_path = os.path.join(self.temp_dir, disk_key)
        self.assertFalse(os.path.exists(cache_path))


if __name__ == '__main__':
    unittest.main() 