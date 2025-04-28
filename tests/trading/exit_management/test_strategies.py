import unittest
import time
from src.trading.exit_management import (
    Position,
    MarketData,
    ExitStrategyType,
    FixedStopLoss,
    TrailingStopLoss,
    AtrStopLoss,
    TimeBasedStopLoss,
    FixedTakeProfit,
    PartialExitStrategy,
    ScaledExitStrategy
)


class TestStopLossStrategies(unittest.TestCase):
    """Test cases for stop-loss strategies"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.long_position = Position(
            symbol="BTCUSDT",
            position_id="test_long",
            entry_price=50000.0,
            quantity=1.0,
            side="BUY",
            open_time=int(time.time())
        )
        
        self.short_position = Position(
            symbol="BTCUSDT",
            position_id="test_short",
            entry_price=50000.0,
            quantity=1.0,
            side="SELL",
            open_time=int(time.time())
        )
        
        self.market_data = MarketData(
            symbol="BTCUSDT",
            last_price=50000.0,
            timestamp=int(time.time()),
            atr=1500.0
        )
    
    def test_fixed_stop_loss_percentage(self):
        """Test fixed stop-loss with percentage"""
        stop_loss = FixedStopLoss(percentage=0.05)  # 5% stop-loss
        
        # Test for long position
        levels = stop_loss.calculate_exit_levels(self.long_position, self.market_data)
        self.assertEqual(len(levels), 1)
        self.assertEqual(levels[0], 47500.0)  # 50000 * (1 - 0.05)
        
        # Test for short position
        levels = stop_loss.calculate_exit_levels(self.short_position, self.market_data)
        self.assertEqual(len(levels), 1)
        self.assertEqual(levels[0], 52500.0)  # 50000 * (1 + 0.05)
    
    def test_fixed_stop_loss_price(self):
        """Test fixed stop-loss with absolute price"""
        # For long position
        stop_loss = FixedStopLoss(price=48000.0)
        levels = stop_loss.calculate_exit_levels(self.long_position, self.market_data)
        self.assertEqual(len(levels), 1)
        self.assertEqual(levels[0], 48000.0)
        
        # For short position
        stop_loss = FixedStopLoss(price=52000.0)
        levels = stop_loss.calculate_exit_levels(self.short_position, self.market_data)
        self.assertEqual(len(levels), 1)
        self.assertEqual(levels[0], 52000.0)
    
    def test_trailing_stop_loss(self):
        """Test trailing stop-loss"""
        stop_loss = TrailingStopLoss(trail_percentage=0.03)  # 3% trailing stop
        
        # Initial stop for long position
        levels = stop_loss.calculate_exit_levels(self.long_position, self.market_data)
        self.assertEqual(levels[0], 48500.0)  # 50000 * (1 - 0.03)
        
        # Price moves up, stop should move up
        self.market_data.last_price = 52000.0
        levels = stop_loss.calculate_exit_levels(self.long_position, self.market_data)
        self.assertEqual(levels[0], 50440.0)  # 52000 * (1 - 0.03)
        
        # Price moves back down, stop should stay at previous level
        self.market_data.last_price = 51000.0
        levels = stop_loss.calculate_exit_levels(self.long_position, self.market_data)
        self.assertEqual(levels[0], 50440.0)  # Still the same as previous
    
    def test_atr_stop_loss(self):
        """Test ATR-based stop-loss"""
        stop_loss = AtrStopLoss(atr_multiplier=2.0)
        
        # Test for long position
        levels = stop_loss.calculate_exit_levels(self.long_position, self.market_data)
        self.assertEqual(len(levels), 1)
        self.assertEqual(levels[0], 47000.0)  # 50000 - (1500 * 2)
        
        # Test for short position
        levels = stop_loss.calculate_exit_levels(self.short_position, self.market_data)
        self.assertEqual(len(levels), 1)
        self.assertEqual(levels[0], 53000.0)  # 50000 + (1500 * 2)
    
    def test_time_based_stop_loss(self):
        """Test time-based stop-loss"""
        # Create a position that's already old
        old_position = Position(
            symbol="BTCUSDT",
            position_id="test_old",
            entry_price=50000.0,
            quantity=1.0,
            side="BUY",
            open_time=int(time.time()) - 3600  # 1 hour ago
        )
        
        # Create time-based stop with 30 minute expiry
        stop_loss = TimeBasedStopLoss(max_duration_seconds=1800, price_buffer_percentage=0.005)
        
        # Old position should trigger exit
        levels = stop_loss.calculate_exit_levels(old_position, self.market_data)
        self.assertEqual(len(levels), 1)
        self.assertEqual(levels[0], 49750.0)  # 50000 * (1 - 0.005)
        
        # New position should not trigger exit
        levels = stop_loss.calculate_exit_levels(self.long_position, self.market_data)
        self.assertEqual(len(levels), 0)


class TestTakeProfitStrategies(unittest.TestCase):
    """Test cases for take-profit strategies"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.long_position = Position(
            symbol="BTCUSDT",
            position_id="test_long",
            entry_price=50000.0,
            quantity=1.0,
            side="BUY",
            open_time=int(time.time())
        )
        
        self.short_position = Position(
            symbol="BTCUSDT",
            position_id="test_short",
            entry_price=50000.0,
            quantity=1.0,
            side="SELL",
            open_time=int(time.time())
        )
        
        self.market_data = MarketData(
            symbol="BTCUSDT",
            last_price=50000.0,
            timestamp=int(time.time()),
            atr=1500.0
        )
    
    def test_fixed_take_profit(self):
        """Test fixed take-profit"""
        take_profit = FixedTakeProfit(percentage=0.1)  # 10% profit target
        
        # Test for long position
        levels = take_profit.calculate_exit_levels(self.long_position, self.market_data)
        self.assertEqual(len(levels), 1)
        self.assertEqual(levels[0], 55000.0)  # 50000 * (1 + 0.1)
        
        # Test for short position
        levels = take_profit.calculate_exit_levels(self.short_position, self.market_data)
        self.assertEqual(len(levels), 1)
        self.assertEqual(levels[0], 45000.0)  # 50000 * (1 - 0.1)
        
        # Test with fixed price
        take_profit = FixedTakeProfit(price=56000.0)
        levels = take_profit.calculate_exit_levels(self.long_position, self.market_data)
        self.assertEqual(levels[0], 56000.0)
    
    def test_partial_exit_strategy(self):
        """Test partial exit strategy"""
        take_profit = PartialExitStrategy(levels=[
            {"percentage": 0.05, "quantity_percentage": 0.3},
            {"percentage": 0.1, "quantity_percentage": 0.3},
            {"percentage": 0.2, "quantity_percentage": 0.4}
        ])
        
        # Test for long position
        levels = take_profit.calculate_exit_levels(self.long_position, self.market_data)
        self.assertEqual(len(levels), 3)
        self.assertEqual(levels[0], 52500.0)  # 50000 * (1 + 0.05)
        self.assertEqual(levels[1], 55000.0)  # 50000 * (1 + 0.1)
        self.assertEqual(levels[2], 60000.0)  # 50000 * (1 + 0.2)
        
        # Test order generation
        orders = take_profit.generate_exit_orders(self.long_position, self.market_data)
        self.assertEqual(len(orders), 3)
        self.assertEqual(orders[0].quantity, 0.3)  # 30% of position
        self.assertEqual(orders[1].quantity, 0.3)  # 30% of position
        self.assertEqual(orders[2].quantity, 0.4)  # 40% of position
    
    def test_scaled_exit_strategy(self):
        """Test scaled exit strategy"""
        take_profit = ScaledExitStrategy(
            base_percentage=0.05,
            scale_factor=2.0,
            levels=3
        )
        
        # Test for long position
        levels = take_profit.calculate_exit_levels(self.long_position, self.market_data)
        self.assertEqual(len(levels), 3)
        self.assertEqual(levels[0], 52500.0)  # 50000 * (1 + 0.05)
        self.assertEqual(levels[1], 55000.0)  # 50000 * (1 + 0.1)
        self.assertEqual(levels[2], 60000.0)  # 50000 * (1 + 0.2)
        
        # Test order generation
        orders = take_profit.generate_exit_orders(self.long_position, self.market_data)
        self.assertEqual(len(orders), 3)
        self.assertEqual(orders[0].quantity, 1/3)  # Equal distribution
        self.assertEqual(orders[1].quantity, 1/3)
        self.assertEqual(orders[2].quantity, 1/3)


if __name__ == '__main__':
    unittest.main() 