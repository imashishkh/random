"""
Tests for the PositionLimiter class in the risk management system.

This module contains unit tests for the PositionLimiter class which is responsible
for enforcing position size and exposure limits.
"""

import unittest
import time
from unittest.mock import MagicMock, patch

# Import the PositionLimiter class
from src.risk.position_limiter import PositionLimiter


class TestPositionLimiter(unittest.TestCase):
    """Test cases for the PositionLimiter class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a mock action log
        self.action_log = MagicMock()
        
        # Test configuration
        self.config = {
            'max_position_size': {'BTCUSDT': 1.0, 'ETHUSDT': 5.0},
            'default_max_position_size': 0.5,
            'max_portfolio_exposure': 10.0,
            'max_drawdown_percentage': 15.0,
            'max_daily_loss_percentage': 5.0,
            'max_holding_time': 3600,  # 1 hour
            'enable_alerts': True,
            'alert_threshold': 0.8,
            'enforce_limits': True
        }
        
        # Create the PositionLimiter instance
        self.limiter = PositionLimiter(self.action_log, self.config)
        
        # Sample positions
        self.sample_positions = [
            {'symbol': 'BTCUSDT', 'position_amount': '0.5', 'entry_price': '40000'},
            {'symbol': 'ETHUSDT', 'position_amount': '2.0', 'entry_price': '2000'}
        ]

    def test_initialization(self):
        """Test initialization with default and custom config."""
        # Test with default config
        limiter = PositionLimiter()
        self.assertEqual(limiter.current_equity, 0.0)
        self.assertEqual(limiter.peak_equity, 0.0)
        self.assertEqual(limiter.positions, {})
        
        # Test with custom config
        self.assertEqual(self.limiter.config['max_position_size']['BTCUSDT'], 1.0)
        self.assertEqual(self.limiter.config['max_portfolio_exposure'], 10.0)
        self.assertEqual(self.limiter.config['max_holding_time'], 3600)

    def test_configure(self):
        """Test configuration updates."""
        # Update config values
        new_config = {
            'max_position_size': {'BTCUSDT': 2.0},
            'max_portfolio_exposure': 20.0
        }
        
        self.limiter.configure(new_config)
        
        # Check if values were updated
        self.assertEqual(self.limiter.config['max_position_size']['BTCUSDT'], 2.0)
        self.assertEqual(self.limiter.config['max_portfolio_exposure'], 20.0)
        
        # Check that other values remain unchanged
        self.assertEqual(self.limiter.config['max_position_size']['ETHUSDT'], 5.0)
        self.assertEqual(self.limiter.config['max_holding_time'], 3600)

    def test_update_positions(self):
        """Test position updates and tracking."""
        # Initial position update
        self.limiter.update_positions(self.sample_positions)
        
        # Check if positions are tracked
        self.assertIn('BTCUSDT', self.limiter.positions)
        self.assertIn('ETHUSDT', self.limiter.positions)
        
        self.assertEqual(self.limiter.positions['BTCUSDT']['size'], 0.5)
        self.assertEqual(self.limiter.positions['ETHUSDT']['size'], 2.0)
        
        # Update with a modified position
        updated_positions = [
            {'symbol': 'BTCUSDT', 'position_amount': '0.8', 'entry_price': '41000'},
            {'symbol': 'ETHUSDT', 'position_amount': '0', 'entry_price': '0'}  # Closed position
        ]
        
        self.limiter.update_positions(updated_positions)
        
        # Check if positions are updated correctly
        self.assertIn('BTCUSDT', self.limiter.positions)
        self.assertNotIn('ETHUSDT', self.limiter.positions)  # Should be removed
        
        self.assertEqual(self.limiter.positions['BTCUSDT']['size'], 0.8)

    def test_set_account_equity(self):
        """Test account equity tracking and updates."""
        # Initial equity
        self.limiter.set_account_equity(10000.0)
        self.assertEqual(self.limiter.starting_equity, 10000.0)
        self.assertEqual(self.limiter.peak_equity, 10000.0)
        self.assertEqual(self.limiter.current_equity, 10000.0)
        self.assertEqual(self.limiter.daily_starting_equity, 10000.0)
        
        # Increase equity - should update peak
        self.limiter.set_account_equity(11000.0)
        self.assertEqual(self.limiter.starting_equity, 10000.0)  # Unchanged
        self.assertEqual(self.limiter.peak_equity, 11000.0)  # Updated
        self.assertEqual(self.limiter.current_equity, 11000.0)
        
        # Decrease equity - peak should remain
        self.limiter.set_account_equity(10500.0)
        self.assertEqual(self.limiter.peak_equity, 11000.0)  # Unchanged
        self.assertEqual(self.limiter.current_equity, 10500.0)

    @patch('time.time')
    @patch('time.strftime')
    def test_daily_equity_reset(self, mock_strftime, mock_time):
        """Test that daily equity resets on a new day."""
        # Mock time functions
        mock_time.return_value = 1000000  # Some fixed timestamp
        mock_strftime.side_effect = lambda fmt, *args: "2023-01-01" if not args else "2023-01-01"
        
        # Set initial equity
        self.limiter.set_account_equity(10000.0)
        self.assertEqual(self.limiter.daily_starting_equity, 10000.0)
        
        # Update equity
        self.limiter.set_account_equity(9500.0)
        self.assertEqual(self.limiter.daily_starting_equity, 10000.0)  # Unchanged
        
        # Simulate next day
        mock_strftime.side_effect = lambda fmt, *args: "2023-01-02" if not args else "2023-01-01"
        
        # Update equity on new day
        self.limiter.set_account_equity(9500.0)
        self.assertEqual(self.limiter.daily_starting_equity, 9500.0)  # Reset for new day

    def test_can_enter_position_within_limits(self):
        """Test that positions within limits are allowed."""
        # Set initial positions
        self.limiter.update_positions(self.sample_positions)
        
        # Test entering a position within limits
        result, violation = self.limiter.can_enter_position('BTCUSDT', 0.3)
        self.assertTrue(result)
        self.assertIsNone(violation)
        
        # Test entering a new symbol within default limit
        result, violation = self.limiter.can_enter_position('XRPUSDT', 0.4)
        self.assertTrue(result)
        self.assertIsNone(violation)

    def test_can_enter_position_exceeding_symbol_limit(self):
        """Test that positions exceeding symbol limits are rejected."""
        # Set initial positions
        self.limiter.update_positions(self.sample_positions)
        
        # Test exceeding symbol limit
        result, violation = self.limiter.can_enter_position('BTCUSDT', 0.6)  # Would make total 1.1
        self.assertFalse(result)
        self.assertEqual(violation['type'], 'max_position_size')
        self.assertEqual(violation['symbol'], 'BTCUSDT')
        
        # Test exceeding default limit
        result, violation = self.limiter.can_enter_position('XRPUSDT', 0.6)  # Default limit is 0.5
        self.assertFalse(result)
        self.assertEqual(violation['type'], 'max_position_size')
        self.assertEqual(violation['symbol'], 'XRPUSDT')

    def test_can_enter_position_exceeding_exposure_limit(self):
        """Test that positions exceeding portfolio exposure limits are rejected."""
        # Set initial positions
        self.limiter.update_positions(self.sample_positions)
        # Current exposure is 0.5 + 2.0 = 2.5
        
        # Test exceeding exposure limit
        result, violation = self.limiter.can_enter_position('XRPUSDT', 8.0)  # Would make total 10.5
        self.assertFalse(result)
        self.assertEqual(violation['type'], 'max_portfolio_exposure')

    def test_check_order(self):
        """Test order checking functionality."""
        # Set initial positions
        self.limiter.update_positions(self.sample_positions)
        
        # Valid buy order
        buy_order = {'symbol': 'BTCUSDT', 'quantity': 0.3, 'side': 'BUY'}
        result, violation = self.limiter.check_order(buy_order)
        self.assertTrue(result)
        self.assertIsNone(violation)
        
        # Valid sell order (reduces position)
        sell_order = {'symbol': 'BTCUSDT', 'quantity': 0.3, 'side': 'SELL'}
        result, violation = self.limiter.check_order(sell_order)
        self.assertTrue(result)
        self.assertIsNone(violation)
        
        # Invalid buy order (exceeds limit)
        large_buy_order = {'symbol': 'BTCUSDT', 'quantity': 0.6, 'side': 'BUY'}
        result, violation = self.limiter.check_order(large_buy_order)
        self.assertFalse(result)
        self.assertEqual(violation['type'], 'max_position_size')

    @patch('time.time')
    def test_holding_time_limits(self, mock_time):
        """Test position holding time limits."""
        # Mock initial time
        start_time = 1000000
        mock_time.return_value = start_time
        
        # Set initial positions
        self.limiter.update_positions(self.sample_positions)
        
        # Advance time to just below limit
        mock_time.return_value = start_time + 3500  # 1 hour limit is 3600
        self.limiter._check_holding_time_limits()
        
        # Check that no violations are recorded
        self.assertEqual(len(self.limiter.violations), 0)
        
        # Advance time beyond limit
        mock_time.return_value = start_time + 3700
        self.limiter._check_holding_time_limits()
        
        # Check that violations are recorded
        self.assertEqual(len(self.limiter.violations), 2)  # Both positions exceed
        self.assertEqual(self.limiter.violations[0]['type'], 'max_holding_time')
        
        # Verify action log was called
        self.action_log.log_limit_violation.assert_called()

    def test_drawdown_limit(self):
        """Test drawdown limits."""
        # Set initial equity
        self.limiter.set_account_equity(10000.0)
        
        # Reduce equity to approach drawdown limit
        self.limiter.set_account_equity(8600.0)  # 14% drawdown
        
        # Check drawdown limit - should pass
        self.assertTrue(self.limiter._check_drawdown_limit())
        
        # Reduce equity to exceed drawdown limit
        self.limiter.set_account_equity(8400.0)  # 16% drawdown
        
        # Check drawdown limit - should fail
        self.assertFalse(self.limiter._check_drawdown_limit())
        
        # Verify violation was recorded
        self.assertEqual(len(self.limiter.violations), 1)
        self.assertEqual(self.limiter.violations[0]['type'], 'max_drawdown')

    def test_daily_loss_limit(self):
        """Test daily loss limits."""
        # Set initial equity
        self.limiter.set_account_equity(10000.0)
        
        # Reduce equity to approach daily loss limit
        self.limiter.set_account_equity(9550.0)  # 4.5% daily loss
        
        # Check daily loss limit - should pass
        self.assertTrue(self.limiter._check_daily_loss_limit())
        
        # Reduce equity to exceed daily loss limit
        self.limiter.set_account_equity(9450.0)  # 5.5% daily loss
        
        # Check daily loss limit - should fail
        self.assertFalse(self.limiter._check_daily_loss_limit())
        
        # Verify violation was recorded
        self.assertEqual(len(self.limiter.violations), 1)
        self.assertEqual(self.limiter.violations[0]['type'], 'max_daily_loss')

    def test_alerts(self):
        """Test alert triggering."""
        # Set initial equity
        self.limiter.set_account_equity(10000.0)
        
        # Approach drawdown limit to trigger alert
        self.limiter.set_account_equity(8800.0)  # 12% drawdown (80% of 15% limit)
        
        # Check drawdown limit - should trigger alert
        self.limiter._check_drawdown_limit()
        
        # Verify warning was logged
        self.action_log.log_warning.assert_called_once()
        
        # Reset mock
        self.action_log.log_warning.reset_mock()
        
        # Check again - should not trigger alert due to cooldown
        self.limiter._check_drawdown_limit()
        self.action_log.log_warning.assert_not_called()

    def test_get_violations(self):
        """Test retrieving and clearing violations."""
        # Create some violations
        self.limiter.violations = [
            {'type': 'max_position_size', 'symbol': 'BTCUSDT', 'timestamp': 1000000},
            {'type': 'max_drawdown', 'timestamp': 1000001}
        ]
        
        # Get violations without clearing
        violations = self.limiter.get_violations(clear=False)
        self.assertEqual(len(violations), 2)
        self.assertEqual(len(self.limiter.violations), 2)  # Still there
        
        # Get violations with clearing
        violations = self.limiter.get_violations(clear=True)
        self.assertEqual(len(violations), 2)
        self.assertEqual(len(self.limiter.violations), 0)  # Cleared

    def test_get_status(self):
        """Test status reporting."""
        # Set up test state
        self.limiter.set_account_equity(10000.0)
        self.limiter.update_positions(self.sample_positions)
        
        # Get status report
        status = self.limiter.get_status()
        
        # Verify status data
        self.assertEqual(status['equity']['current'], 10000.0)
        self.assertEqual(status['equity']['starting'], 10000.0)
        self.assertEqual(status['exposure'], 2.5)  # 0.5 + 2.0
        self.assertEqual(status['limits']['max_position_size']['BTCUSDT'], 1.0)
        self.assertTrue('positions' in status)
        self.assertEqual(len(status['positions']), 2)


if __name__ == '__main__':
    unittest.main() 