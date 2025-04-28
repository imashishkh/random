import unittest
from unittest.mock import Mock, patch
from src.trading.exit_management import (
    ExitManager,
    FixedStopLoss,
    TrailingStopLoss,
    FixedTakeProfit,
    TrailingTakeProfit,
    Position
)


class TestExitManager(unittest.TestCase):
    """Test cases for the ExitManager class"""

    def setUp(self):
        """Set up test fixtures"""
        self.fixed_stop_loss = FixedStopLoss(risk_percentage=0.02)
        self.trailing_stop_loss = TrailingStopLoss(initial_percentage=0.02, trailing_percentage=0.01)
        self.fixed_take_profit = FixedTakeProfit(reward_percentage=0.03)
        self.trailing_take_profit = TrailingTakeProfit(initial_percentage=0.03, trailing_percentage=0.01)
        
        self.exit_manager = ExitManager()
    
    def test_initialization(self):
        """Test if the manager is properly initialized"""
        self.assertEqual(self.exit_manager.position_exit_strategies, {})
    
    def test_register_exit_strategy(self):
        """Test registration of exit strategies for a position"""
        # Setup
        position = Mock(spec=Position)
        position.id = "position1"
        
        # Register stop loss and take profit strategies
        self.exit_manager.register_exit_strategy(
            position=position,
            stop_loss_strategy=self.fixed_stop_loss,
            take_profit_strategy=self.fixed_take_profit
        )
        
        # Verify
        self.assertIn(position.id, self.exit_manager.position_exit_strategies)
        strategies = self.exit_manager.position_exit_strategies[position.id]
        self.assertEqual(strategies['stop_loss'], self.fixed_stop_loss)
        self.assertEqual(strategies['take_profit'], self.fixed_take_profit)
    
    def test_update_exit_strategy(self):
        """Test updating exit strategies for a position"""
        # Setup
        position = Mock(spec=Position)
        position.id = "position1"
        
        # Register initial strategies
        self.exit_manager.register_exit_strategy(
            position=position,
            stop_loss_strategy=self.fixed_stop_loss,
            take_profit_strategy=self.fixed_take_profit
        )
        
        # Update strategies
        self.exit_manager.update_exit_strategy(
            position=position,
            stop_loss_strategy=self.trailing_stop_loss,
            take_profit_strategy=self.trailing_take_profit
        )
        
        # Verify
        strategies = self.exit_manager.position_exit_strategies[position.id]
        self.assertEqual(strategies['stop_loss'], self.trailing_stop_loss)
        self.assertEqual(strategies['take_profit'], self.trailing_take_profit)
    
    def test_get_exit_strategy(self):
        """Test retrieving exit strategies for a position"""
        # Setup
        position = Mock(spec=Position)
        position.id = "position1"
        
        # Register strategies
        self.exit_manager.register_exit_strategy(
            position=position,
            stop_loss_strategy=self.fixed_stop_loss,
            take_profit_strategy=self.fixed_take_profit
        )
        
        # Get strategies
        stop_loss, take_profit = self.exit_manager.get_exit_strategy(position)
        
        # Verify
        self.assertEqual(stop_loss, self.fixed_stop_loss)
        self.assertEqual(take_profit, self.fixed_take_profit)
    
    def test_get_exit_strategy_nonexistent(self):
        """Test retrieving exit strategies for a position without registered strategies"""
        # Setup
        position = Mock(spec=Position)
        position.id = "position_nonexistent"
        
        # Get strategies for a position without registered strategies
        stop_loss, take_profit = self.exit_manager.get_exit_strategy(position)
        
        # Verify
        self.assertIsNone(stop_loss)
        self.assertIsNone(take_profit)
    
    def test_calculate_exit_prices(self):
        """Test calculation of exit prices for a position"""
        # Setup
        position = Mock(spec=Position)
        position.id = "position1"
        position.entry_price = 50000.0
        position.side = "long"
        position.current_price = 50000.0
        
        # Register strategies
        self.exit_manager.register_exit_strategy(
            position=position,
            stop_loss_strategy=self.fixed_stop_loss,
            take_profit_strategy=self.fixed_take_profit
        )
        
        # Calculate expected prices
        expected_stop_loss_price = 50000.0 * (1 - 0.02)
        expected_take_profit_price = 50000.0 * (1 + 0.03)
        
        # Calculate exit prices
        stop_loss_price, take_profit_price = self.exit_manager.calculate_exit_prices(position)
        
        # Verify
        self.assertEqual(stop_loss_price, expected_stop_loss_price)
        self.assertEqual(take_profit_price, expected_take_profit_price)
    
    def test_calculate_exit_prices_nonexistent(self):
        """Test calculation of exit prices for a position without registered strategies"""
        # Setup
        position = Mock(spec=Position)
        position.id = "position_nonexistent"
        
        # Calculate exit prices for a position without registered strategies
        stop_loss_price, take_profit_price = self.exit_manager.calculate_exit_prices(position)
        
        # Verify
        self.assertIsNone(stop_loss_price)
        self.assertIsNone(take_profit_price)
    
    def test_should_exit_long_position_stop_loss_triggered(self):
        """Test exit decision when stop loss is triggered for a long position"""
        # Setup
        position = Mock(spec=Position)
        position.id = "position1"
        position.entry_price = 50000.0
        position.side = "long"
        position.current_price = 49000.0  # Below stop loss price (50000 * 0.98 = 49000)
        
        # Register strategies
        self.exit_manager.register_exit_strategy(
            position=position,
            stop_loss_strategy=self.fixed_stop_loss,
            take_profit_strategy=self.fixed_take_profit
        )
        
        # Check if should exit
        should_exit, reason = self.exit_manager.should_exit(position)
        
        # Verify
        self.assertTrue(should_exit)
        self.assertEqual(reason, "Stop Loss triggered")
    
    def test_should_exit_long_position_take_profit_triggered(self):
        """Test exit decision when take profit is triggered for a long position"""
        # Setup
        position = Mock(spec=Position)
        position.id = "position1"
        position.entry_price = 50000.0
        position.side = "long"
        position.current_price = 51500.0  # Above take profit price (50000 * 1.03 = 51500)
        
        # Register strategies
        self.exit_manager.register_exit_strategy(
            position=position,
            stop_loss_strategy=self.fixed_stop_loss,
            take_profit_strategy=self.fixed_take_profit
        )
        
        # Check if should exit
        should_exit, reason = self.exit_manager.should_exit(position)
        
        # Verify
        self.assertTrue(should_exit)
        self.assertEqual(reason, "Take Profit triggered")
    
    def test_should_exit_short_position_stop_loss_triggered(self):
        """Test exit decision when stop loss is triggered for a short position"""
        # Setup
        position = Mock(spec=Position)
        position.id = "position1"
        position.entry_price = 50000.0
        position.side = "short"
        position.current_price = 51000.0  # Above stop loss price (50000 * 1.02 = 51000)
        
        # Register strategies
        self.exit_manager.register_exit_strategy(
            position=position,
            stop_loss_strategy=self.fixed_stop_loss,
            take_profit_strategy=self.fixed_take_profit
        )
        
        # Check if should exit
        should_exit, reason = self.exit_manager.should_exit(position)
        
        # Verify
        self.assertTrue(should_exit)
        self.assertEqual(reason, "Stop Loss triggered")
    
    def test_should_exit_short_position_take_profit_triggered(self):
        """Test exit decision when take profit is triggered for a short position"""
        # Setup
        position = Mock(spec=Position)
        position.id = "position1"
        position.entry_price = 50000.0
        position.side = "short"
        position.current_price = 48500.0  # Below take profit price (50000 * 0.97 = 48500)
        
        # Register strategies
        self.exit_manager.register_exit_strategy(
            position=position,
            stop_loss_strategy=self.fixed_stop_loss,
            take_profit_strategy=self.fixed_take_profit
        )
        
        # Check if should exit
        should_exit, reason = self.exit_manager.should_exit(position)
        
        # Verify
        self.assertTrue(should_exit)
        self.assertEqual(reason, "Take Profit triggered")
    
    def test_should_not_exit_no_triggers(self):
        """Test exit decision when no exit triggers are hit"""
        # Setup
        position = Mock(spec=Position)
        position.id = "position1"
        position.entry_price = 50000.0
        position.side = "long"
        position.current_price = 50200.0  # Above stop loss but below take profit
        
        # Register strategies
        self.exit_manager.register_exit_strategy(
            position=position,
            stop_loss_strategy=self.fixed_stop_loss,
            take_profit_strategy=self.fixed_take_profit
        )
        
        # Check if should exit
        should_exit, reason = self.exit_manager.should_exit(position)
        
        # Verify
        self.assertFalse(should_exit)
        self.assertIsNone(reason)
    
    def test_should_not_exit_no_strategies(self):
        """Test exit decision for a position without registered strategies"""
        # Setup
        position = Mock(spec=Position)
        position.id = "position_nonexistent"
        
        # Check if should exit
        should_exit, reason = self.exit_manager.should_exit(position)
        
        # Verify
        self.assertFalse(should_exit)
        self.assertIsNone(reason)
    
    def test_deregister_exit_strategy(self):
        """Test deregistration of exit strategies for a position"""
        # Setup
        position = Mock(spec=Position)
        position.id = "position1"
        
        # Register strategies
        self.exit_manager.register_exit_strategy(
            position=position,
            stop_loss_strategy=self.fixed_stop_loss,
            take_profit_strategy=self.fixed_take_profit
        )
        
        # Verify registration
        self.assertIn(position.id, self.exit_manager.position_exit_strategies)
        
        # Deregister strategies
        self.exit_manager.deregister_exit_strategy(position)
        
        # Verify deregistration
        self.assertNotIn(position.id, self.exit_manager.position_exit_strategies)


if __name__ == '__main__':
    unittest.main() 