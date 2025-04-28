"""
Tests for the Data Manager module.

This module contains unit tests for the DataManager class and its components.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from .data_manager import DataManager
from .data_source import DataSourceAdapter, DataSourceFactory
from .preprocessor import DataPreprocessor, PreprocessorFactory


class MockDataSourceAdapter(DataSourceAdapter):
    """Mock implementation of DataSourceAdapter for testing."""
    
    def __init__(self, source_type='mock', exchange='mock_exchange'):
        super().__init__(source_type, exchange)
        self.fetch_ohlcv_called = False
        self.fetch_ticker_called = False
        
    async def fetch_ohlcv(self, symbol, timeframe='1h', limit=100, since=None):
        """Mock implementation that returns fake OHLCV data."""
        self.fetch_ohlcv_called = True
        
        # Create a simple DataFrame with test data
        dates = pd.date_range(
            start=since if since else datetime.now() - timedelta(days=5),
            periods=limit,
            freq=self._get_freq(timeframe)
        )
        
        data = {
            'timestamp': dates,
            'open': np.random.normal(100, 5, limit),
            'high': np.random.normal(105, 5, limit),
            'low': np.random.normal(95, 5, limit),
            'close': np.random.normal(100, 5, limit),
            'volume': np.random.normal(1000, 100, limit)
        }
        
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        return df
    
    async def fetch_ticker(self, symbol):
        """Mock implementation that returns fake ticker data."""
        self.fetch_ticker_called = True
        return {
            'symbol': symbol,
            'last': 100.0,
            'bid': 99.5,
            'ask': 100.5,
            'volume': 1000.0,
            'timestamp': datetime.now().timestamp()
        }
    
    async def fetch_fundamental_data(self, symbol, data_type='financial_statements'):
        """Mock implementation that returns fake fundamental data."""
        return {
            'symbol': symbol,
            'data_type': data_type,
            'revenue': 1000000,
            'profit': 500000,
            'assets': 2000000,
            'liabilities': 1000000
        }
    
    async def fetch_news(self, symbol, limit=10, since=None):
        """Mock implementation that returns fake news data."""
        return [{
            'symbol': symbol,
            'title': f'News about {symbol}',
            'content': f'This is a test news article about {symbol}',
            'timestamp': datetime.now().timestamp(),
            'source': 'Mock News'
        } for _ in range(limit)]
    
    async def fetch_economic_indicators(self, indicator, country=None, limit=1):
        """Mock implementation that returns fake economic indicator data."""
        return {
            'indicator': indicator,
            'country': country or 'global',
            'value': 3.5,
            'timestamp': datetime.now().timestamp()
        }
    
    def _get_freq(self, timeframe):
        """Convert timeframe string to pandas frequency string."""
        if timeframe == '1m':
            return 'T'
        elif timeframe == '5m':
            return '5T'
        elif timeframe == '15m':
            return '15T'
        elif timeframe == '30m':
            return '30T'
        elif timeframe == '1h':
            return 'H'
        elif timeframe == '4h':
            return '4H'
        elif timeframe == '1d':
            return 'D'
        elif timeframe == '1w':
            return 'W'
        return 'H'  # Default to hourly


class MockPreprocessor(DataPreprocessor):
    """Mock implementation of DataPreprocessor for testing."""
    
    def __init__(self):
        super().__init__()
        self.process_called = False
        
    def process(self, data):
        """Mock implementation that adds a test column to the data."""
        self.process_called = True
        
        if isinstance(data, pd.DataFrame):
            data['processed'] = True
            data['test_indicator'] = np.random.normal(0, 1, len(data))
            return data
        return data


class TestDataManager(unittest.TestCase):
    """Test case for the DataManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a mock data source factory
        self.mock_source = MockDataSourceAdapter()
        self.mock_source_factory = MagicMock(spec=DataSourceFactory)
        self.mock_source_factory.get_data_source.return_value = self.mock_source
        
        # Create a mock preprocessor factory
        self.mock_preprocessor = MockPreprocessor()
        self.mock_preprocessor_factory = MagicMock(spec=PreprocessorFactory)
        self.mock_preprocessor_factory.get_preprocessor.return_value = self.mock_preprocessor
        
        # Create patches
        self.data_source_factory_patch = patch(
            'src.data_manager.data_manager.DataSourceFactory',
            return_value=self.mock_source_factory
        )
        self.preprocessor_factory_patch = patch(
            'src.data_manager.data_manager.PreprocessorFactory',
            return_value=self.mock_preprocessor_factory
        )
        
        # Start patches
        self.data_source_factory_mock = self.data_source_factory_patch.start()
        self.preprocessor_factory_mock = self.preprocessor_factory_patch.start()
        
        # Create a DataManager instance with mocked dependencies
        self.data_manager = DataManager(
            default_source_type='mock',
            default_exchange='mock_exchange',
            use_cache=False,  # Disable caching for tests
            use_fallbacks=False  # Disable fallbacks for simplicity
        )
    
    def tearDown(self):
        """Tear down test fixtures."""
        # Stop patches
        self.data_source_factory_patch.stop()
        self.preprocessor_factory_patch.stop()
    
    def test_initialization(self):
        """Test that the DataManager initializes correctly."""
        self.assertIsNotNone(self.data_manager)
        self.assertEqual(self.data_manager._default_source_type, 'mock')
        self.assertEqual(self.data_manager._default_exchange, 'mock_exchange')
        self.assertFalse(self.data_manager._use_cache)
        self.assertFalse(self.data_manager._use_fallbacks)
    
    def test_get_market_data(self):
        """Test that get_market_data calls the data source and returns correctly."""
        # Create an event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Call the method
            result = loop.run_until_complete(
                self.data_manager.get_market_data(
                    symbol='BTC/USDT',
                    timeframe='1h',
                    limit=10,
                    preprocess=False
                )
            )
            
            # Verify the result
            self.assertIsInstance(result, pd.DataFrame)
            self.assertEqual(len(result), 10)
            self.assertTrue(self.mock_source.fetch_ohlcv_called)
            self.assertFalse(self.mock_preprocessor.process_called)
        finally:
            loop.close()
    
    def test_get_market_data_with_preprocessing(self):
        """Test that get_market_data with preprocessing calls the preprocessor."""
        # Create an event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Call the method with preprocessing
            result = loop.run_until_complete(
                self.data_manager.get_market_data(
                    symbol='BTC/USDT',
                    timeframe='1h',
                    limit=10,
                    preprocess=True
                )
            )
            
            # Verify the result
            self.assertIsInstance(result, pd.DataFrame)
            self.assertEqual(len(result), 10)
            self.assertTrue(self.mock_source.fetch_ohlcv_called)
            self.assertTrue(self.mock_preprocessor.process_called)
            self.assertTrue('processed' in result.columns)
            self.assertTrue('test_indicator' in result.columns)
        finally:
            loop.close()
    
    def test_get_multi_symbol_data(self):
        """Test that get_multi_symbol_data fetches data for multiple symbols."""
        # Create an event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Call the method
            symbols = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT']
            result = loop.run_until_complete(
                self.data_manager.get_multi_symbol_data(
                    symbols=symbols,
                    timeframe='1h',
                    limit=10,
                    preprocess=True
                )
            )
            
            # Verify the result
            self.assertIsInstance(result, dict)
            self.assertEqual(len(result), len(symbols))
            for symbol in symbols:
                self.assertIn(symbol, result)
                self.assertIsInstance(result[symbol], pd.DataFrame)
                self.assertEqual(len(result[symbol]), 10)
                self.assertTrue('processed' in result[symbol].columns)
        finally:
            loop.close()
    
    def test_get_fundamental_data(self):
        """Test that get_fundamental_data calls the data source correctly."""
        # Create an event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Call the method
            result = loop.run_until_complete(
                self.data_manager.get_fundamental_data(
                    symbol='AAPL',
                    data_type='financial_statements'
                )
            )
            
            # Verify the result
            self.assertIsInstance(result, dict)
            self.assertEqual(result['symbol'], 'AAPL')
            self.assertEqual(result['data_type'], 'financial_statements')
        finally:
            loop.close()
    
    def test_get_news(self):
        """Test that get_news calls the data source correctly."""
        # Create an event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Call the method
            result = loop.run_until_complete(
                self.data_manager.get_news(
                    symbol='AAPL',
                    limit=5
                )
            )
            
            # Verify the result
            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 5)
            self.assertEqual(result[0]['symbol'], 'AAPL')
        finally:
            loop.close()
    
    def test_get_economic_indicators(self):
        """Test that get_economic_indicators calls the data source correctly."""
        # Create an event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Call the method
            result = loop.run_until_complete(
                self.data_manager.get_economic_indicators(
                    indicator='GDP',
                    country='US'
                )
            )
            
            # Verify the result
            self.assertIsInstance(result, dict)
            self.assertEqual(result['indicator'], 'GDP')
            self.assertEqual(result['country'], 'US')
        finally:
            loop.close()


if __name__ == '__main__':
    unittest.main() 