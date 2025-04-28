"""
Unit tests for the TechnicalAnalysisAgent base class.
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from .technical_analysis.agent import TechnicalAnalysisAgent


class MockTechnicalAnalysisAgent(TechnicalAnalysisAgent):
    """Mock implementation of TechnicalAnalysisAgent for testing."""
    
    def compute_indicators(self, data):
        self.indicators = {
            'mock_indicator': pd.Series(np.random.random(len(data)), index=data.index)
        }
        return self.indicators
    
    def generate_signals(self, data):
        if not self.indicators:
            self.compute_indicators(data)
            
        signals = []
        for i in range(10, len(data), 20):  # Generate a signal every 20 periods
            signal_type = 'buy' if i % 40 == 10 else 'sell'  # Alternate buy/sell
            signal = {
                'type': signal_type,
                'timestamp': data.index[i],
                'indicator': 'mock_indicator',
                'value': self.indicators['mock_indicator'].iloc[i]
            }
            signal['confidence'] = self.get_confidence_level(signal, data)
            signals.append(signal)
            
        self.signals = signals
        return signals
    
    def get_confidence_level(self, signal, data):
        # Simple mock implementation
        return 0.7  # Fixed confidence


class TestTechnicalAnalysisAgent(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        # Create a sample DataFrame with OHLCV data
        dates = pd.date_range(start='2023-01-01', periods=100, freq='1D')
        np.random.seed(42)  # For reproducible tests
        
        # Generate sample price data with some trend
        base_price = 100.0
        price_changes = np.random.normal(0.0005, 0.01, len(dates))
        closes = base_price * (1 + np.cumsum(price_changes))
        
        # Generate OHLC data
        opens = closes - np.random.normal(0, 0.005, len(dates))
        highs = np.maximum(opens, closes) + np.abs(np.random.normal(0, 0.005, len(dates)))
        lows = np.minimum(opens, closes) - np.abs(np.random.normal(0, 0.005, len(dates)))
        
        # Generate volume
        volume = 1000000 + 500000 * np.random.random(len(dates))
        
        self.data = pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volume
        }, index=dates)
        
        # Create a mock agent instance
        self.agent = MockTechnicalAnalysisAgent(name="TestAgent")

    def test_initialization(self):
        """Test that agent initializes correctly."""
        self.assertEqual(self.agent.name, "TestAgent")
        self.assertIsInstance(self.agent.config, dict)
        self.assertFalse(self.agent.signals)  # Empty signals list
        
        # Check library availability flags
        self.assertIsNotNone(self.agent.talib_available)
        self.assertIsNotNone(self.agent.pandas_ta_available)

    def test_compute_indicator(self):
        """Test computing a single indicator."""
        # Mock the IndicatorFactory.get method
        with patch('src.indicators.factory.IndicatorFactory.get') as mock_get:
            # Create a mock function that returns a simple Series
            mock_indicator = MagicMock(return_value=pd.Series(np.ones(len(self.data)), index=self.data.index))
            mock_get.return_value = mock_indicator
            
            # Compute an indicator
            result = self.agent.compute_indicator('RSI', self.data, {'timeperiod': 14})
            
            # Check that IndicatorFactory.get was called correctly
            mock_get.assert_called_once_with('RSI')
            
            # Check that the mock indicator function was called with the data and params
            mock_indicator.assert_called_once()
            
            # Check that the result is as expected
            self.assertIsInstance(result, pd.Series)
            self.assertEqual(len(result), len(self.data))
            
            # Check that the indicator was stored
            self.assertIn('RSI', self.agent.indicators)
            self.assertEqual(self.agent.indicators['RSI'], result)

    def test_generate_signals_creates_indicators(self):
        """Test that generate_signals computes indicators if not already done."""
        # Ensure indicators are empty
        self.agent.indicators = {}
        
        # Call generate_signals
        signals = self.agent.generate_signals(self.data)
        
        # Check that indicators were computed
        self.assertNotEqual(self.agent.indicators, {})
        self.assertIn('mock_indicator', self.agent.indicators)

    def test_backtest(self):
        """Test the backtest method."""
        # Generate signals first
        signals = self.agent.generate_signals(self.data)
        
        # Run backtest
        results = self.agent.backtest(self.data)
        
        # Check results structure
        self.assertIsInstance(results, dict)
        self.assertIn('signals', results)
        self.assertIn('win_rate', results)
        self.assertIn('avg_profit', results)
        self.assertIn('total_signals', results)
        
        # Check results are reasonable
        self.assertGreaterEqual(results['win_rate'], 0)
        self.assertLessEqual(results['win_rate'], 1)
        
        # Store backtest results
        self.assertEqual(self.agent.backtest_results, results)

    def test_backtest_with_date_range(self):
        """Test backtest with date range filtering."""
        # Generate signals first
        signals = self.agent.generate_signals(self.data)
        
        # Define a narrower date range
        start_date = self.data.index[20].strftime('%Y-%m-%d')
        end_date = self.data.index[80].strftime('%Y-%m-%d')
        
        # Run backtest with date range
        results = self.agent.backtest(self.data, start_date=start_date, end_date=end_date)
        
        # Check results
        self.assertIsInstance(results, dict)
        
        # Verify that only signals within the date range were evaluated
        for signal_result in results['signals']:
            signal_date = pd.to_datetime(signal_result['timestamp'])
            self.assertGreaterEqual(signal_date, pd.to_datetime(start_date))
            self.assertLessEqual(signal_date, pd.to_datetime(end_date))

    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        # Generate signals and run backtest to populate the agent
        self.agent.generate_signals(self.data)
        self.agent.backtest(self.data)
        
        # Convert to dict
        agent_dict = self.agent.to_dict()
        
        # Check dict structure
        self.assertIn('name', agent_dict)
        self.assertIn('type', agent_dict)
        self.assertIn('config', agent_dict)
        self.assertIn('backtest_results', agent_dict)
        
        # Recreate from dict
        new_agent = MockTechnicalAnalysisAgent.from_dict(agent_dict)
        
        # Check new agent
        self.assertEqual(new_agent.name, self.agent.name)
        self.assertEqual(new_agent.backtest_results, self.agent.backtest_results)

    def test_get_index_from_timestamp(self):
        """Test _get_index_from_timestamp utility method."""
        # Get a timestamp from the data
        timestamp = self.data.index[50]
        
        # Get the index
        index = self.agent._get_index_from_timestamp(timestamp, self.data)
        
        # Check result
        self.assertEqual(index, 50)


if __name__ == '__main__':
    unittest.main() 