"""
Tests for the Risk Manager implementation.
"""

import unittest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock, call
import logging
import time
from datetime import datetime

from src.risk.manager import RiskManager


class TestRiskManager(unittest.TestCase):
    """Test suite for the Risk Manager."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Disable logging for tests
        logging.disable(logging.CRITICAL)
        
        # Create a risk manager with test configuration
        self.risk_manager = RiskManager(account_balance=10000.0)
        
        # Configure global limits
        self.risk_manager.set_global_limits(
            max_global_exposure=0.8,
            max_agent_exposure={'test_agent': 0.4},
            max_symbol_exposure={'BTCUSDT': 0.3}
        )
        
        # Sample market data for position sizing
        self.market_data = pd.DataFrame({
            'open': np.arange(100, 120),
            'high': np.arange(105, 125),
            'low': np.arange(95, 115),
            'close': np.arange(102, 122),
            'volume': np.random.rand(20) * 1000
        })
    
    def tearDown(self):
        """Clean up after tests."""
        # Re-enable logging
        logging.disable(logging.NOTSET)
    
    def test_init(self):
        """Test initialization of risk manager."""
        self.assertEqual(self.risk_manager.account_balance, 10000.0)
        self.assertEqual(self.risk_manager.params['max_risk_per_trade'], 0.02)
        self.assertEqual(self.risk_manager.params['max_global_exposure'], 0.8)
        self.assertFalse(self.risk_manager._circuit_breaker_active)
    
    def test_position_size_calculation(self):
        """Test position size calculation."""
        result = self.risk_manager.calculate_position_size(
            symbol='BTCUSDT',
            market_data=self.market_data
        )
        
        # Verify the result has expected keys
        self.assertIn('size', result)
        self.assertIn('value', result)
        self.assertIn('risk_amount', result)
        self.assertIn('risk_percent', result)
        self.assertIn('metadata', result)
        
        # Verify size is positive
        self.assertGreater(result['size'], 0)
        
        # Verify risk amount is reasonable
        self.assertLessEqual(result['risk_amount'], self.risk_manager.account_balance * 0.02)
    
    def test_global_exposure_limit(self):
        """Test enforcement of global exposure limit."""
        # Setup: Add a position that takes up 75% of account balance
        self.risk_manager._global_positions = {
            'ETHUSDT': {
                'symbol': 'ETHUSDT',
                'position_amount': 10.0,
                'entry_price': 750.0,
                'mark_price': 750.0,
                'notional_value': 7500.0  # 75% of 10,000
            }
        }
        
        # Try to add a position that would exceed the global limit
        result = self.risk_manager.calculate_position_size(
            symbol='BTCUSDT',
            market_data=self.market_data,
            risk_params={'risk_per_trade': 0.1}  # 10% risk would exceed 80% global limit
        )
        
        # Verify the position was reduced to fit within limits
        self.assertTrue(result['metadata'].get('adjusted', False))
        self.assertEqual(result['metadata'].get('adjustment_reason'), 'global_exposure_limit')
        self.assertLessEqual(result['value'], self.risk_manager.account_balance * 0.05)  # 5% remaining capacity
    
    def test_zero_position_when_no_capacity(self):
        """Test that position size is zero when no capacity remains."""
        # Setup: Add a position that takes up 85% of account balance (over the limit)
        self.risk_manager._global_positions = {
            'ETHUSDT': {
                'symbol': 'ETHUSDT',
                'position_amount': 10.0,
                'entry_price': 850.0,
                'mark_price': 850.0,
                'notional_value': 8500.0  # 85% of 10,000
            }
        }
        
        # Try to add a new position
        result = self.risk_manager.calculate_position_size(
            symbol='BTCUSDT',
            market_data=self.market_data
        )
        
        # Verify the position was rejected
        self.assertEqual(result['size'], 0)
        self.assertEqual(result['value'], 0)
        self.assertTrue(result['metadata'].get('adjusted', False))
        self.assertEqual(result['metadata'].get('adjustment_reason'), 'global_exposure_limit')
    
    @patch('src.risk.manager.RiskManager.fetch_binance_position_risk')
    def test_check_risk_limits(self, mock_fetch):
        """Test checking risk limits."""
        # Setup: Mock position data
        mock_fetch.return_value = [
            {
                'symbol': 'BTCUSDT',
                'position_amount': 1.0,
                'entry_price': 50000.0,
                'mark_price': 50000.0,
                'notional_value': 5000.0  # 50% of 10,000
            },
            {
                'symbol': 'ETHUSDT',
                'position_amount': 5.0,
                'entry_price': 2000.0,
                'mark_price': 2000.0,
                'notional_value': 10000.0  # 100% of 10,000
            }
        ]
        
        # Check risk limits
        result = self.risk_manager.check_risk_limits()
        
        # Verify the result
        self.assertEqual(mock_fetch.call_count, 1)
        self.assertIn('global_exposure', result)
        self.assertIn('symbol_exposure', result)
        self.assertIn('violations', result)
        
        # Verify global exposure calculation
        self.assertEqual(result['global_exposure'], 1.5)  # 150% of account balance
        
        # Verify violations
        self.assertGreaterEqual(len(result['violations']), 1)
        self.assertEqual(result['violations'][0]['type'], 'global_exposure')
        self.assertEqual(result['violations'][0]['severity'], 'hard')  # Should be hard since >120% of limit
    
    @patch('src.risk.manager.RiskManager._send_slack_alert')
    def test_handle_violations(self, mock_slack):
        """Test handling of risk limit violations."""
        # Setup: Configure Slack alerts
        self.risk_manager.configure_slack_alerts('https://slack.webhook.url')
        
        # Create test violations
        violations = [
            {
                'type': 'global_exposure',
                'severity': 'soft',
                'current': 0.85,
                'limit': 0.8
            },
            {
                'type': 'symbol_exposure',
                'symbol': 'BTCUSDT',
                'severity': 'hard',
                'current': 0.4,
                'limit': 0.3
            }
        ]
        
        # Handle violations
        self.risk_manager._handle_violations(violations)
        
        # Verify alerts were sent
        self.assertEqual(mock_slack.call_count, 2)
        # First call should be a warning (soft)
        self.assertEqual(mock_slack.call_args_list[0][0][1], 'soft')
        # Second call should be critical (hard)
        self.assertEqual(mock_slack.call_args_list[1][0][1], 'hard')
    
    @patch('src.exchange.BinanceClient')
    def test_emergency_shutdown(self, mock_client_class):
        """Test emergency shutdown functionality."""
        # Setup: Mock Binance client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock position data
        self.risk_manager.fetch_binance_position_risk = MagicMock(return_value=[
            {
                'symbol': 'BTCUSDT',
                'position_amount': 1.0,
                'entry_price': 50000.0,
                'mark_price': 50000.0,
                'notional_value': 5000.0
            },
            {
                'symbol': 'ETHUSDT',
                'position_amount': -5.0,  # Short position
                'entry_price': 2000.0,
                'mark_price': 2000.0,
                'notional_value': 10000.0
            }
        ])
        
        # Mock successful order creation
        mock_client.create_order.return_value = {'orderId': '12345'}
        
        # Mock Slack alert
        self.risk_manager._send_emergency_alert = MagicMock()
        
        # Execute emergency shutdown
        result = self.risk_manager.emergency_shutdown(reason="test_shutdown")
        
        # Verify positions were fetched
        self.assertEqual(self.risk_manager.fetch_binance_position_risk.call_count, 1)
        
        # Verify orders were created to close positions
        self.assertEqual(mock_client.create_order.call_count, 2)
        
        # Verify order parameters
        calls = [
            call(symbol='BTCUSDT', side='SELL', type='MARKET', quantity=1.0, reduceOnly=True),
            call(symbol='ETHUSDT', side='BUY', type='MARKET', quantity=5.0, reduceOnly=True)
        ]
        mock_client.create_order.assert_has_calls(calls, any_order=True)
        
        # Verify emergency alert was sent
        self.assertEqual(self.risk_manager._send_emergency_alert.call_count, 1)
        
        # Verify result
        self.assertTrue(result['success'])
        self.assertEqual(len(result['closed_positions']), 2)
    
    def test_circuit_breaker_activation(self):
        """Test circuit breaker activation and impact on position sizing."""
        # Activate the circuit breaker
        self.risk_manager._circuit_breaker_active = True
        self.risk_manager._circuit_breaker_end_time = time.time() + 300  # 5 minutes
        
        # Try to calculate position size while circuit breaker is active
        result = self.risk_manager.calculate_position_size(
            symbol='BTCUSDT',
            market_data=self.market_data
        )
        
        # Verify the position was blocked
        self.assertEqual(result['size'], 0)
        self.assertEqual(result['value'], 0)
        self.assertTrue(result['metadata'].get('adjusted', False))
        self.assertEqual(result['metadata'].get('adjustment_reason'), 'circuit_breaker_active')
        
        # Test circuit breaker expiration
        # Set end time to the past
        self.risk_manager._circuit_breaker_end_time = time.time() - 10
        
        # Try to calculate position size after expiration
        result = self.risk_manager.calculate_position_size(
            symbol='BTCUSDT',
            market_data=self.market_data
        )
        
        # Verify circuit breaker was deactivated and position was allowed
        self.assertFalse(self.risk_manager._circuit_breaker_active)
        self.assertIsNone(self.risk_manager._circuit_breaker_end_time)
        self.assertGreater(result['size'], 0)


if __name__ == '__main__':
    unittest.main() 