"""
Tests for MarketCircuitBreaker

This module tests the functionality of the MarketCircuitBreaker class.
"""

import unittest
import time
from unittest.mock import MagicMock, patch

from src.risk.circuit_breaker import MarketCircuitBreaker


class TestMarketCircuitBreaker(unittest.TestCase):
    """Test suite for MarketCircuitBreaker class."""
    
    def setUp(self):
        """Set up test environment."""
        # Create mock action log
        self.mock_action_log = MagicMock()
        
        # Create test config
        self.test_config = {
            'enabled': True,
            'thresholds': {
                'TEST1': {
                    'percentage': 3.0,
                    'cooldown_period': 60,  # 1 minute for faster testing
                    'description': 'Test threshold 1'
                },
                'TEST2': {
                    'percentage': 5.0,
                    'cooldown_period': 120,  # 2 minutes
                    'description': 'Test threshold 2'
                }
            },
            'progressive_cooldown': {
                'enabled': True,
                'window': 300,   # 5 minutes for faster testing
                'multiplier': 2,
                'max_multiplier': 4
            }
        }
        
        # Create circuit breaker
        self.circuit_breaker = MarketCircuitBreaker(
            config=self.test_config,
            action_log=self.mock_action_log
        )
    
    def test_init_with_default_config(self):
        """Test initialization with default config."""
        # Create instance with no config
        cb = MarketCircuitBreaker()
        
        # Should have default config
        self.assertTrue(cb.config['enabled'])
        self.assertIn('LEVEL1', cb.config['thresholds'])
        self.assertIn('LEVEL2', cb.config['thresholds'])
        self.assertIn('LEVEL3', cb.config['thresholds'])
        self.assertTrue(cb.config['progressive_cooldown']['enabled'])
    
    def test_price_volatility_check_below_threshold(self):
        """Test price volatility check when below threshold."""
        symbol = "BTCUSDT"
        current_price = 10300
        reference_price = 10000  # 3% change
        
        # Should not trigger (exactly at threshold)
        should_halt, details = self.circuit_breaker.check_price_volatility(
            symbol, current_price, reference_price
        )
        
        # Should not halt trading
        self.assertFalse(should_halt)
        self.assertIsNone(details)
    
    def test_price_volatility_check_above_threshold(self):
        """Test price volatility check when above threshold."""
        symbol = "BTCUSDT"
        current_price = 10500
        reference_price = 10000  # 5% change
        
        # Should trigger TEST2 threshold
        should_halt, details = self.circuit_breaker.check_price_volatility(
            symbol, current_price, reference_price
        )
        
        # Should halt trading
        self.assertTrue(should_halt)
        self.assertIsNotNone(details)
        self.assertEqual(details['level'], 'TEST2')
        self.assertEqual(details['price_change_pct'], 5.0)
        self.assertEqual(details['symbol'], symbol)
        self.assertTrue(details['active'])
        
        # Action log should be called
        self.mock_action_log.log_circuit_breaker.assert_called_once()
    
    def test_multiple_threshold_levels(self):
        """Test that highest threshold level is triggered."""
        symbol = "ETHUSDT"
        
        # First test with 4% change (should trigger TEST1)
        current_price = 1040
        reference_price = 1000
        should_halt, details = self.circuit_breaker.check_price_volatility(
            symbol, current_price, reference_price
        )
        
        self.assertTrue(should_halt)
        self.assertEqual(details['level'], 'TEST1')
        
        # Reset for new test
        self.circuit_breaker.reset(symbol)
        
        # Now test with 6% change (should trigger TEST2)
        current_price = 1060
        reference_price = 1000
        should_halt, details = self.circuit_breaker.check_price_volatility(
            symbol, current_price, reference_price
        )
        
        self.assertTrue(should_halt)
        self.assertEqual(details['level'], 'TEST2')
    
    def test_is_in_cooldown(self):
        """Test cooldown period functionality."""
        symbol = "BTCUSDT"
        
        # Trigger circuit breaker
        current_price = 10500
        reference_price = 10000  # 5% change
        self.circuit_breaker.check_price_volatility(symbol, current_price, reference_price)
        
        # Should be in cooldown
        self.assertTrue(self.circuit_breaker.is_in_cooldown(symbol))
        
        # Check other symbol is not in cooldown
        self.assertFalse(self.circuit_breaker.is_in_cooldown("ETHUSDT"))
    
    def test_can_trade(self):
        """Test can_trade method."""
        symbol = "BTCUSDT"
        
        # Initially trading is allowed
        self.assertTrue(self.circuit_breaker.can_trade(symbol))
        
        # Trigger circuit breaker
        current_price = 10500
        reference_price = 10000
        self.circuit_breaker.check_price_volatility(symbol, current_price, reference_price)
        
        # Trading should be halted
        self.assertFalse(self.circuit_breaker.can_trade(symbol))
        
        # Trading should still be allowed for other symbols
        self.assertTrue(self.circuit_breaker.can_trade("ETHUSDT"))
    
    def test_progressive_cooldown(self):
        """Test progressive cooldown functionality."""
        symbol = "BTCUSDT"
        
        # Mock time to control progression
        original_time = time.time
        
        try:
            # Start with a fixed time
            mock_time = 1000000.0
            time.time = MagicMock(return_value=mock_time)
            
            # First trigger
            current_price = 10500
            reference_price = 10000
            self.circuit_breaker.check_price_volatility(symbol, current_price, reference_price)
            
            # Get the first cooldown period
            first_status = self.circuit_breaker.get_status(symbol)
            first_cooldown = first_status['cooldown_period']
            
            # Should be base cooldown period (120 seconds for TEST2)
            self.assertEqual(first_cooldown, 120)
            
            # Advance time but stay within the window
            mock_time += 150  # Past first cooldown
            time.time = MagicMock(return_value=mock_time)
            
            # Reset breaker manually to simulate cooldown end
            self.circuit_breaker.reset(symbol)
            
            # Second trigger
            self.circuit_breaker.check_price_volatility(symbol, current_price, reference_price)
            
            # Get the second cooldown period
            second_status = self.circuit_breaker.get_status(symbol)
            second_cooldown = second_status['cooldown_period']
            
            # Should be multiplied (120 * 2 = 240 seconds)
            self.assertEqual(second_cooldown, 240)
            
        finally:
            # Restore original time function
            time.time = original_time
    
    def test_reset(self):
        """Test reset functionality."""
        # Trigger circuit breakers for two symbols
        symbols = ["BTCUSDT", "ETHUSDT"]
        current_price = 10500
        reference_price = 10000
        
        for symbol in symbols:
            self.circuit_breaker.check_price_volatility(symbol, current_price, reference_price)
            self.assertTrue(self.circuit_breaker.is_in_cooldown(symbol))
        
        # Reset one symbol
        self.circuit_breaker.reset(symbols[0])
        
        # First symbol should not be in cooldown, second should be
        self.assertFalse(self.circuit_breaker.is_in_cooldown(symbols[0]))
        self.assertTrue(self.circuit_breaker.is_in_cooldown(symbols[1]))
        
        # Reset all
        self.circuit_breaker.reset()
        
        # Both should not be in cooldown
        for symbol in symbols:
            self.assertFalse(self.circuit_breaker.is_in_cooldown(symbol))
    
    def test_enable_disable(self):
        """Test enable/disable functionality."""
        symbol = "BTCUSDT"
        
        # Trigger circuit breaker
        current_price = 10500
        reference_price = 10000
        self.circuit_breaker.check_price_volatility(symbol, current_price, reference_price)
        
        # Trading should be halted
        self.assertFalse(self.circuit_breaker.can_trade(symbol))
        
        # Disable circuit breaker
        self.circuit_breaker.disable()
        
        # Trading should be allowed even with active breaker
        self.assertTrue(self.circuit_breaker.can_trade(symbol))
        
        # Enable circuit breaker
        self.circuit_breaker.enable()
        
        # Trading should be halted again
        self.assertFalse(self.circuit_breaker.can_trade(symbol))
    
    def test_configure(self):
        """Test configuration update."""
        # Update configuration
        new_config = {
            'enabled': False,
            'thresholds': {
                'TEST1': {
                    'percentage': 4.0  # Change threshold
                },
                'NEW_LEVEL': {  # Add new level
                    'percentage': 8.0,
                    'cooldown_period': 300,
                    'description': 'New test level'
                }
            }
        }
        
        self.circuit_breaker.configure(new_config)
        
        # Check config was updated
        self.assertFalse(self.circuit_breaker.config['enabled'])
        self.assertEqual(self.circuit_breaker.config['thresholds']['TEST1']['percentage'], 4.0)
        self.assertIn('NEW_LEVEL', self.circuit_breaker.config['thresholds'])
    
    def test_get_status(self):
        """Test get_status method."""
        # Initially no active breakers
        status = self.circuit_breaker.get_status()
        self.assertEqual(len(status['active_breakers']), 0)
        
        # Trigger breakers for two symbols
        symbols = ["BTCUSDT", "ETHUSDT"]
        current_price = 10500
        reference_price = 10000
        
        for symbol in symbols:
            self.circuit_breaker.check_price_volatility(symbol, current_price, reference_price)
        
        # Should have two active breakers
        status = self.circuit_breaker.get_status()
        self.assertEqual(len(status['active_breakers']), 2)
        
        # Check individual status
        symbol_status = self.circuit_breaker.get_status(symbols[0])
        self.assertTrue(symbol_status['active'])
        self.assertEqual(symbol_status['symbol'], symbols[0])
        self.assertGreater(symbol_status['cooldown_remaining'], 0)
    
    def test_get_active_breakers(self):
        """Test get_active_breakers method."""
        # Trigger breakers for two symbols
        symbols = ["BTCUSDT", "ETHUSDT"]
        current_price = 10500
        reference_price = 10000
        
        for symbol in symbols:
            self.circuit_breaker.check_price_volatility(symbol, current_price, reference_price)
        
        # Should have two active breakers
        active_breakers = self.circuit_breaker.get_active_breakers()
        self.assertEqual(len(active_breakers), 2)
        
        # Check breaker info
        for breaker in active_breakers:
            self.assertTrue(breaker['active'])
            self.assertIn(breaker['symbol'], symbols)
            self.assertGreater(breaker['cooldown_remaining'], 0)


if __name__ == '__main__':
    unittest.main() 