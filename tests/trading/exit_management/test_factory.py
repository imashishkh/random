import unittest
from src.trading.exit_management import (
    ExitStrategyFactory,
    ExitStrategyConfig,
    ExitStrategyType,
    FixedStopLoss,
    TrailingStopLoss,
    AtrStopLoss,
    TimeBasedStopLoss,
    FixedTakeProfit,
    TrailingTakeProfit,
    PartialExitStrategy,
    ScaledExitStrategy
)


class TestExitStrategyFactory(unittest.TestCase):
    """Test cases for the exit strategy factory"""
    
    def test_create_fixed_stop_loss(self):
        """Test creating a fixed stop-loss strategy"""
        config = ExitStrategyConfig(
            strategy_type=ExitStrategyType.FIXED_STOP_LOSS,
            parameters={"percentage": 0.05}
        )
        
        strategy = ExitStrategyFactory.create_strategy(config)
        
        self.assertIsInstance(strategy, FixedStopLoss)
        self.assertEqual(strategy.percentage, 0.05)
        self.assertIsNone(strategy.fixed_price)
        
        # Test with fixed price
        config = ExitStrategyConfig(
            strategy_type=ExitStrategyType.FIXED_STOP_LOSS,
            parameters={"price": 48000.0}
        )
        
        strategy = ExitStrategyFactory.create_strategy(config)
        
        self.assertIsInstance(strategy, FixedStopLoss)
        self.assertIsNone(strategy.percentage)
        self.assertEqual(strategy.fixed_price, 48000.0)
    
    def test_create_trailing_stop_loss(self):
        """Test creating a trailing stop-loss strategy"""
        config = ExitStrategyConfig(
            strategy_type=ExitStrategyType.TRAILING_STOP_LOSS,
            parameters={
                "trail_percentage": 0.03,
                "activation_percentage": 0.01
            }
        )
        
        strategy = ExitStrategyFactory.create_strategy(config)
        
        self.assertIsInstance(strategy, TrailingStopLoss)
        self.assertEqual(strategy.trail_percentage, 0.03)
        self.assertEqual(strategy.activation_percentage, 0.01)
        
        # Test without activation percentage
        config = ExitStrategyConfig(
            strategy_type=ExitStrategyType.TRAILING_STOP_LOSS,
            parameters={"trail_percentage": 0.03}
        )
        
        strategy = ExitStrategyFactory.create_strategy(config)
        
        self.assertIsInstance(strategy, TrailingStopLoss)
        self.assertEqual(strategy.trail_percentage, 0.03)
        self.assertIsNone(strategy.activation_percentage)
    
    def test_create_atr_stop_loss(self):
        """Test creating an ATR-based stop-loss strategy"""
        config = ExitStrategyConfig(
            strategy_type=ExitStrategyType.ATR_STOP_LOSS,
            parameters={
                "atr_multiplier": 2.5,
                "period": 14
            }
        )
        
        strategy = ExitStrategyFactory.create_strategy(config)
        
        self.assertIsInstance(strategy, AtrStopLoss)
        self.assertEqual(strategy.atr_multiplier, 2.5)
        self.assertEqual(strategy.period, 14)
    
    def test_create_time_based_stop_loss(self):
        """Test creating a time-based stop-loss strategy"""
        config = ExitStrategyConfig(
            strategy_type=ExitStrategyType.TIME_BASED_STOP_LOSS,
            parameters={
                "max_duration_seconds": 3600,
                "price_buffer_percentage": 0.01
            }
        )
        
        strategy = ExitStrategyFactory.create_strategy(config)
        
        self.assertIsInstance(strategy, TimeBasedStopLoss)
        self.assertEqual(strategy.max_duration_seconds, 3600)
        self.assertEqual(strategy.price_buffer_percentage, 0.01)
    
    def test_create_fixed_take_profit(self):
        """Test creating a fixed take-profit strategy"""
        config = ExitStrategyConfig(
            strategy_type=ExitStrategyType.FIXED_TAKE_PROFIT,
            parameters={"percentage": 0.1}
        )
        
        strategy = ExitStrategyFactory.create_strategy(config)
        
        self.assertIsInstance(strategy, FixedTakeProfit)
        self.assertEqual(strategy.percentage, 0.1)
    
    def test_create_trailing_take_profit(self):
        """Test creating a trailing take-profit strategy"""
        config = ExitStrategyConfig(
            strategy_type=ExitStrategyType.TRAILING_TAKE_PROFIT,
            parameters={
                "activation_percentage": 0.05,
                "trail_percentage": 0.02
            }
        )
        
        strategy = ExitStrategyFactory.create_strategy(config)
        
        self.assertIsInstance(strategy, TrailingTakeProfit)
        self.assertEqual(strategy.activation_percentage, 0.05)
        self.assertEqual(strategy.trail_percentage, 0.02)
    
    def test_create_partial_exit(self):
        """Test creating a partial exit strategy"""
        config = ExitStrategyConfig(
            strategy_type=ExitStrategyType.PARTIAL_EXIT,
            parameters={
                "levels": [
                    {"percentage": 0.05, "quantity_percentage": 0.3},
                    {"percentage": 0.1, "quantity_percentage": 0.3},
                    {"percentage": 0.2, "quantity_percentage": 0.4}
                ]
            }
        )
        
        strategy = ExitStrategyFactory.create_strategy(config)
        
        self.assertIsInstance(strategy, PartialExitStrategy)
        self.assertEqual(len(strategy.levels), 3)
        self.assertEqual(strategy.levels[0]["percentage"], 0.05)
    
    def test_create_scaled_exit(self):
        """Test creating a scaled exit strategy"""
        config = ExitStrategyConfig(
            strategy_type=ExitStrategyType.SCALED_EXIT,
            parameters={
                "base_percentage": 0.05,
                "scale_factor": 2.0,
                "levels": 3,
                "max_percentage": 0.2
            }
        )
        
        strategy = ExitStrategyFactory.create_strategy(config)
        
        self.assertIsInstance(strategy, ScaledExitStrategy)
        self.assertEqual(strategy.base_percentage, 0.05)
        self.assertEqual(strategy.scale_factor, 2.0)
        self.assertEqual(strategy.levels, 3)
        self.assertEqual(strategy.max_percentage, 0.2)
    
    def test_invalid_strategy_type(self):
        """Test error handling for invalid strategy type"""
        config = ExitStrategyConfig(
            strategy_type="INVALID_TYPE",
            parameters={}
        )
        
        with self.assertRaises(ValueError):
            ExitStrategyFactory.create_strategy(config)
    
    def test_default_strategies(self):
        """Test creating default strategies"""
        stop_loss = ExitStrategyFactory.create_default_stop_loss(risk_percentage=0.02)
        take_profit = ExitStrategyFactory.create_default_take_profit(reward_percentage=0.05)
        
        self.assertIsInstance(stop_loss, FixedStopLoss)
        self.assertEqual(stop_loss.percentage, 0.02)
        
        self.assertIsInstance(take_profit, FixedTakeProfit)
        self.assertEqual(take_profit.percentage, 0.05)


if __name__ == '__main__':
    unittest.main() 