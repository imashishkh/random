"""
Tests for EmergencyKillSwitch

This module tests the functionality of the EmergencyKillSwitch class.
"""

import unittest
import time
from unittest.mock import MagicMock, patch, call

from src.risk.kill_switch import EmergencyKillSwitch


class TestEmergencyKillSwitch(unittest.TestCase):
    """Test suite for EmergencyKillSwitch class."""
    
    def setUp(self):
        """Set up test environment."""
        # Create mock exchange client
        self.mock_exchange = MagicMock()
        
        # Create mock action log
        self.mock_action_log = MagicMock()
        
        # Create test config
        self.test_config = {
            'close_positions_on_activation': True,
            'cancel_orders_on_activation': True,
            'notify_on_activation': False,  # Disable notifications for testing
            'authorized_deactivators': ['admin', 'risk_manager']
        }
        
        # Create kill switch
        self.kill_switch = EmergencyKillSwitch(
            exchange_client=self.mock_exchange,
            action_log=self.mock_action_log,
            config=self.test_config
        )
    
    def test_init_with_default_config(self):
        """Test initialization with default config."""
        # Create instance with no config
        ks = EmergencyKillSwitch()
        
        # Should have default config
        self.assertTrue(ks.config['close_positions_on_activation'])
        self.assertTrue(ks.config['cancel_orders_on_activation'])
        self.assertTrue(ks.config['notify_on_activation'])
        self.assertEqual(ks.config['authorized_deactivators'], [])
        self.assertIsNone(ks.config['auto_deactivation_timeout'])
    
    def test_is_active_initially_false(self):
        """Test that kill switch is initially inactive."""
        self.assertFalse(self.kill_switch.is_active())
    
    def test_activate_sets_active_state(self):
        """Test that activate method sets active state."""
        # Activate kill switch
        result = self.kill_switch.activate("Test activation", "test")
        
        # Should be active
        self.assertTrue(self.kill_switch.is_active())
        self.assertTrue(result['success'])
        
        # Should have internal state set
        self.assertEqual(self.kill_switch.triggered_by, "test")
        self.assertEqual(self.kill_switch.activation_reason, "Test activation")
        self.assertIsNotNone(self.kill_switch.triggered_at)
    
    def test_activate_logs_event(self):
        """Test that activate logs the event."""
        # Activate kill switch
        self.kill_switch.activate("Test activation", "test")
        
        # Action log should be called
        self.mock_action_log.log_kill_switch.assert_called_once()
        
        # Check call arguments
        call_args = self.mock_action_log.log_kill_switch.call_args[0][0]
        self.assertEqual(call_args['triggered_by'], "test")
        self.assertEqual(call_args['reason'], "Test activation")
    
    def test_activate_with_cancel_orders(self):
        """Test activate with cancel orders option."""
        # Setup mock response
        self.mock_exchange.cancel_all_orders.return_value = {"status": "success"}
        
        # Activate with cancel_orders=True
        result = self.kill_switch.activate(
            "Test activation", 
            "test",
            cancel_orders=True,
            close_positions=False
        )
        
        # Should call cancel_all_orders
        self.mock_exchange.cancel_all_orders.assert_called_once()
        
        # Should not call get_positions
        self.mock_exchange.get_positions.assert_not_called()
        
        # Check result
        self.assertTrue(result['success'])
        self.assertEqual(len(result['actions']), 1)
        self.assertEqual(result['actions'][0]['action'], 'cancel_orders')
    
    def test_activate_with_close_positions(self):
        """Test activate with close positions option."""
        # Setup mock responses
        self.mock_exchange.get_positions.return_value = [
            {'symbol': 'BTCUSDT', 'position_amount': '1.0'},
            {'symbol': 'ETHUSDT', 'position_amount': '-2.0'}
        ]
        self.mock_exchange.create_market_order.return_value = {"status": "success"}
        
        # Activate with close_positions=True
        result = self.kill_switch.activate(
            "Test activation", 
            "test",
            cancel_orders=False,
            close_positions=True
        )
        
        # Should call get_positions
        self.mock_exchange.get_positions.assert_called_once()
        
        # Should call create_market_order twice (once per position)
        self.assertEqual(self.mock_exchange.create_market_order.call_count, 2)
        
        # Check calls were made with correct arguments
        calls = [
            call(symbol='BTCUSDT', side='sell', amount=1.0, reduce_only=True),
            call(symbol='ETHUSDT', side='buy', amount=2.0, reduce_only=True)
        ]
        self.mock_exchange.create_market_order.assert_has_calls(calls, any_order=True)
        
        # Check result
        self.assertTrue(result['success'])
        self.assertEqual(len(result['actions']), 1)
        self.assertEqual(result['actions'][0]['action'], 'close_positions')
    
    def test_activate_when_already_active(self):
        """Test that activate when already active returns error."""
        # First activation
        self.kill_switch.activate("First activation", "test1")
        
        # Second activation should fail
        result = self.kill_switch.activate("Second activation", "test2")
        
        # Should not be successful
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'already_active')
        
        # Internal state should still reflect first activation
        self.assertEqual(self.kill_switch.triggered_by, "test1")
        self.assertEqual(self.kill_switch.activation_reason, "First activation")
    
    def test_activate_handles_exchange_errors(self):
        """Test that activate handles exchange errors gracefully."""
        # Setup mock to raise exception
        self.mock_exchange.cancel_all_orders.side_effect = Exception("Test error")
        
        # Activate with cancel_orders=True
        result = self.kill_switch.activate(
            "Test activation", 
            "test",
            cancel_orders=True,
            close_positions=False
        )
        
        # Should still be active
        self.assertTrue(self.kill_switch.is_active())
        
        # Should include error in actions
        self.assertTrue(result['success'])  # Overall success should be true
        self.assertEqual(len(result['actions']), 1)
        self.assertEqual(result['actions'][0]['action'], 'cancel_orders')
        self.assertFalse(result['actions'][0]['success'])
        self.assertIn('error', result['actions'][0])
    
    def test_activation_callbacks(self):
        """Test activation callbacks are called."""
        # Create mock callbacks
        pre_callback = MagicMock(return_value={"status": "pre_ok"})
        post_callback = MagicMock(return_value={"status": "post_ok"})
        
        # Add callbacks
        self.kill_switch.add_activation_callback(pre_callback, post_callback)
        
        # Activate kill switch
        result = self.kill_switch.activate("Test activation", "test")
        
        # Callbacks should be called
        pre_callback.assert_called_once()
        post_callback.assert_called_once()
        
        # Result should include callback results
        self.assertIn('callback_results', result)
        self.assertEqual(len(result['callback_results']), 2)
    
    def test_deactivate(self):
        """Test deactivation functionality."""
        # First activate
        self.kill_switch.activate("Test activation", "test")
        
        # Then deactivate
        result = self.kill_switch.deactivate("admin", "Test deactivation")
        
        # Should not be active anymore
        self.assertFalse(self.kill_switch.is_active())
        
        # Result should be successful
        self.assertTrue(result['success'])
        
        # Internal state should reflect deactivation
        self.assertEqual(self.kill_switch.deactivated_by, "admin")
        self.assertIsNotNone(self.kill_switch.deactivated_at)
    
    def test_deactivate_unauthorized(self):
        """Test deactivation by unauthorized user."""
        # First activate
        self.kill_switch.activate("Test activation", "test")
        
        # Then try to deactivate with unauthorized user
        result = self.kill_switch.deactivate("unauthorized_user", "Test deactivation")
        
        # Should still be active
        self.assertTrue(self.kill_switch.is_active())
        
        # Result should not be successful
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'unauthorized')
    
    def test_deactivate_when_not_active(self):
        """Test deactivation when not active."""
        # Try to deactivate when not active
        result = self.kill_switch.deactivate("admin", "Test deactivation")
        
        # Result should not be successful
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'not_active')
    
    def test_deactivation_callbacks(self):
        """Test deactivation callbacks are called."""
        # Create mock callbacks
        pre_callback = MagicMock()
        post_callback = MagicMock()
        
        # Add callbacks
        self.kill_switch.add_deactivation_callback(pre_callback, post_callback)
        
        # First activate
        self.kill_switch.activate("Test activation", "test")
        
        # Then deactivate
        self.kill_switch.deactivate("admin", "Test deactivation")
        
        # Callbacks should be called
        pre_callback.assert_called_once()
        post_callback.assert_called_once()
    
    def test_get_status_when_active(self):
        """Test get_status when active."""
        # Activate kill switch
        self.kill_switch.activate("Test activation", "test")
        
        # Get status
        status = self.kill_switch.get_status()
        
        # Check status
        self.assertTrue(status['active'])
        self.assertEqual(status['triggered_by'], "test")
        self.assertEqual(status['reason'], "Test activation")
        self.assertIn('active_duration', status)
    
    def test_get_status_when_inactive(self):
        """Test get_status when inactive."""
        # Get status
        status = self.kill_switch.get_status()
        
        # Check status
        self.assertFalse(status['active'])
        self.assertIn('config', status)
    
    def test_get_status_after_deactivation(self):
        """Test get_status after deactivation."""
        # Activate and then deactivate
        self.kill_switch.activate("Test activation", "test")
        self.kill_switch.deactivate("admin", "Test deactivation")
        
        # Get status
        status = self.kill_switch.get_status()
        
        # Check status
        self.assertFalse(status['active'])
        self.assertIn('last_activation', status)
        self.assertEqual(status['last_activation']['triggered_by'], "test")
        self.assertEqual(status['last_activation']['reason'], "Test activation")
        self.assertEqual(status['last_activation']['deactivated_by'], "admin")
    
    def test_configure(self):
        """Test configuration update."""
        # New config
        new_config = {
            'close_positions_on_activation': False,
            'authorized_deactivators': ['new_admin']
        }
        
        # Update config
        self.kill_switch.configure(new_config)
        
        # Check config updated
        self.assertFalse(self.kill_switch.config['close_positions_on_activation'])
        self.assertEqual(self.kill_switch.config['authorized_deactivators'], ['new_admin'])
        
        # Other config should remain unchanged
        self.assertTrue(self.kill_switch.config['cancel_orders_on_activation'])


if __name__ == '__main__':
    unittest.main() 