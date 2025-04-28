import unittest
from unittest.mock import Mock, patch
from src.trading.exit_management import (
    ExitStrategyFactory,
    ExitStrategyType,
    ExitStrategyConfig,
    FixedStopLoss,
    TrailingStopLoss,
    FixedTakeProfit,
    TrailingTakeProfit,
    Position
)


class TestExitStrategyFactory(unittest.TestCase):
    """Test cases for the ExitStrategyFactory class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.default_risk_percentage = 0.02
        self.default_reward_percentage = 0.05
        self.factory = ExitStrategyFactory(
            default_risk_percentage=self.default_risk_percentage,
            default_reward_percentage=self.default_reward_percentage
        )
        
        # Sample position data
        self.position = Mock(spec=Position)
        self.position.entry_price = 50000.0
        self.position.side = "long"
    
    def test_initialization(self):
        """Test if the factory is properly initialized"""
        self.assertEqual(self.factory._default_risk_percentage, self.default_risk_percentage)
        self.assertEqual(self.factory._default_reward_percentage, self.default_reward_percentage)
    
    def test_create_default_stop_loss(self):
        """Test creating a default stop loss strategy"""
        # Call the method
        strategy = self.factory.create_default_stop_loss()
        
        # Verify
        self.assertIsInstance(strategy, FixedStopLoss)
        self.assertEqual(strategy.risk_percentage, self.default_risk_percentage)
    
    def test_create_default_take_profit(self):
        """Test creating a default take profit strategy"""
        # Call the method
        strategy = self.factory.create_default_take_profit()
        
        # Verify
        self.assertIsInstance(strategy, FixedTakeProfit)
        self.assertEqual(strategy.reward_percentage, self.default_reward_percentage)
    
    def test_create_fixed_stop_loss(self):
        """Test creating a fixed stop loss strategy"""
        # Setup
        config = ExitStrategyConfig(
            type=ExitStrategyType.FIXED_STOP_LOSS,
            params={"risk_percentage": 0.03}
        )
        
        # Call the method
        strategy = self.factory.create_strategy(config)
        
        # Verify
        self.assertIsInstance(strategy, FixedStopLoss)
        self.assertEqual(strategy.risk_percentage, 0.03)
    
    def test_create_trailing_stop_loss(self):
        """Test creating a trailing stop loss strategy"""
        # Setup
        config = ExitStrategyConfig(
            type=ExitStrategyType.TRAILING_STOP_LOSS,
            params={"initial_percentage": 0.02, "step_percentage": 0.005}
        )
        
        # Call the method
        strategy = self.factory.create_strategy(config)
        
        # Verify
        self.assertIsInstance(strategy, TrailingStopLoss)
        self.assertEqual(strategy.initial_percentage, 0.02)
        self.assertEqual(strategy.step_percentage, 0.005)
    
    def test_create_fixed_take_profit(self):
        """Test creating a fixed take profit strategy"""
        # Setup
        config = ExitStrategyConfig(
            type=ExitStrategyType.FIXED_TAKE_PROFIT,
            params={"reward_percentage": 0.06}
        )
        
        # Call the method
        strategy = self.factory.create_strategy(config)
        
        # Verify
        self.assertIsInstance(strategy, FixedTakeProfit)
        self.assertEqual(strategy.reward_percentage, 0.06)
    
    def test_create_trailing_take_profit(self):
        """Test creating a trailing take profit strategy"""
        # Setup
        config = ExitStrategyConfig(
            type=ExitStrategyType.TRAILING_TAKE_PROFIT,
            params={"initial_percentage": 0.04, "step_percentage": 0.01}
        )
        
        # Call the method
        strategy = self.factory.create_strategy(config)
        
        # Verify
        self.assertIsInstance(strategy, TrailingTakeProfit)
        self.assertEqual(strategy.initial_percentage, 0.04)
        self.assertEqual(strategy.step_percentage, 0.01)
    
    def test_create_strategy_invalid_type(self):
        """Test handling of invalid strategy type"""
        # Setup
        config = ExitStrategyConfig(
            type="INVALID_TYPE",
            params={}
        )
        
        # Call the method and verify it raises ValueError
        with self.assertRaises(ValueError):
            self.factory.create_strategy(config)
    
    def test_create_strategy_missing_params(self):
        """Test handling of missing required parameters"""
        # Setup for fixed stop loss with missing risk_percentage
        config = ExitStrategyConfig(
            type=ExitStrategyType.FIXED_STOP_LOSS,
            params={}
        )
        
        # Call the method and verify it raises ValueError
        with self.assertRaises(ValueError):
            self.factory.create_strategy(config)
        
        # Setup for trailing stop loss with missing parameters
        config = ExitStrategyConfig(
            type=ExitStrategyType.TRAILING_STOP_LOSS,
            params={"initial_percentage": 0.02}  # Missing step_percentage
        )
        
        # Call the method and verify it raises ValueError
        with self.assertRaises(ValueError):
            self.factory.create_strategy(config)


if __name__ == '__main__':
    unittest.main() 