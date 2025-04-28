import unittest
from unittest.mock import Mock
from src.trading.exit_management import (
    FixedTakeProfit,
    TrailingTakeProfit,
    Position
)


class TestFixedTakeProfit(unittest.TestCase):
    """Test cases for the FixedTakeProfit strategy"""

    def setUp(self):
        """Set up test fixtures"""
        self.profit_percentage = 0.05
        self.take_profit = FixedTakeProfit(profit_percentage=self.profit_percentage)

    def test_initialization(self):
        """Test if the strategy is properly initialized"""
        self.assertEqual(self.take_profit.profit_percentage, self.profit_percentage)

    def test_calculate_take_profit_price_long(self):
        """Test calculation of take profit price for a long position"""
        entry_price = 50000.0
        current_price = 51000.0  # Current price is higher than entry price
        position_side = "long"
        
        expected_price = entry_price * (1 + self.profit_percentage)  # 52500.0
        
        take_profit_price = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=current_price,
            position_side=position_side
        )
        
        self.assertEqual(take_profit_price, expected_price)

    def test_calculate_take_profit_price_short(self):
        """Test calculation of take profit price for a short position"""
        entry_price = 50000.0
        current_price = 49000.0  # Current price is lower than entry price
        position_side = "short"
        
        expected_price = entry_price * (1 - self.profit_percentage)  # 47500.0
        
        take_profit_price = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=current_price,
            position_side=position_side
        )
        
        self.assertEqual(take_profit_price, expected_price)

    def test_invalid_position_side(self):
        """Test behavior with invalid position side"""
        entry_price = 50000.0
        current_price = 51000.0
        position_side = "invalid"
        
        with self.assertRaises(ValueError):
            self.take_profit.calculate_take_profit_price(
                entry_price=entry_price,
                current_price=current_price,
                position_side=position_side
            )

    def test_calculate_take_profit_price_unchanged(self):
        """Test that take profit price remains fixed even when price changes"""
        entry_price = 50000.0
        position_side = "long"
        
        # Initial calculation with price equal to entry
        initial_price = entry_price
        initial_take_profit = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=initial_price,
            position_side=position_side
        )
        
        # Price increases
        higher_price = 55000.0
        higher_take_profit = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=higher_price,
            position_side=position_side
        )
        
        # Price decreases
        lower_price = 45000.0
        lower_take_profit = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=lower_price,
            position_side=position_side
        )
        
        # All take profit prices should be the same regardless of current price
        self.assertEqual(initial_take_profit, higher_take_profit)
        self.assertEqual(initial_take_profit, lower_take_profit)


class TestTrailingTakeProfit(unittest.TestCase):
    """Test cases for the TrailingTakeProfit strategy"""

    def setUp(self):
        """Set up test fixtures"""
        self.initial_percentage = 0.05
        self.trailing_percentage = 0.02
        self.take_profit = TrailingTakeProfit(
            initial_percentage=self.initial_percentage,
            trailing_percentage=self.trailing_percentage
        )

    def test_initialization(self):
        """Test if the strategy is properly initialized"""
        self.assertEqual(self.take_profit.initial_percentage, self.initial_percentage)
        self.assertEqual(self.take_profit.trailing_percentage, self.trailing_percentage)
        self.assertIsNone(self.take_profit.highest_price)
        self.assertIsNone(self.take_profit.lowest_price)

    def test_calculate_initial_take_profit_price_long(self):
        """Test the initial take profit price calculation for a long position"""
        entry_price = 50000.0
        current_price = entry_price  # First price update is equal to entry
        position_side = "long"
        
        expected_price = entry_price * (1 + self.initial_percentage)  # 52500.0
        
        take_profit_price = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=current_price,
            position_side=position_side
        )
        
        self.assertEqual(take_profit_price, expected_price)
        self.assertEqual(self.take_profit.highest_price, current_price)

    def test_calculate_initial_take_profit_price_short(self):
        """Test the initial take profit price calculation for a short position"""
        entry_price = 50000.0
        current_price = entry_price  # First price update is equal to entry
        position_side = "short"
        
        expected_price = entry_price * (1 - self.initial_percentage)  # 47500.0
        
        take_profit_price = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=current_price,
            position_side=position_side
        )
        
        self.assertEqual(take_profit_price, expected_price)
        self.assertEqual(self.take_profit.lowest_price, current_price)

    def test_trailing_take_profit_long_price_increases(self):
        """Test trailing take profit adjustment when price increases for a long position"""
        entry_price = 50000.0
        position_side = "long"
        
        # Initial calculation
        initial_price = entry_price
        initial_take_profit = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=initial_price,
            position_side=position_side
        )
        
        # Price increases - take profit should be raised based on trailing percentage
        higher_price = 55000.0
        trailing_take_profit = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=higher_price,
            position_side=position_side
        )
        
        expected_new_take_profit = higher_price * (1 + self.trailing_percentage)  # 56100.0
        
        self.assertEqual(trailing_take_profit, expected_new_take_profit)
        self.assertGreater(trailing_take_profit, initial_take_profit)
        self.assertEqual(self.take_profit.highest_price, higher_price)

    def test_trailing_take_profit_long_price_decreases(self):
        """Test trailing take profit remains unchanged when price decreases for a long position"""
        entry_price = 50000.0
        position_side = "long"
        
        # Initial calculation
        initial_price = entry_price
        initial_take_profit = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=initial_price,
            position_side=position_side
        )
        
        # Price increases - take profit should rise
        higher_price = 55000.0
        higher_take_profit = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=higher_price,
            position_side=position_side
        )
        
        # Price decreases but still above initial - take profit should remain at previous level
        middle_price = 52000.0
        middle_take_profit = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=middle_price,
            position_side=position_side
        )
        
        self.assertEqual(middle_take_profit, higher_take_profit)
        self.assertEqual(self.take_profit.highest_price, higher_price)

    def test_trailing_take_profit_short_price_decreases(self):
        """Test trailing take profit adjustment when price decreases for a short position"""
        entry_price = 50000.0
        position_side = "short"
        
        # Initial calculation
        initial_price = entry_price
        initial_take_profit = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=initial_price,
            position_side=position_side
        )
        
        # Price decreases - take profit should be lowered based on trailing percentage
        lower_price = 45000.0
        trailing_take_profit = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=lower_price,
            position_side=position_side
        )
        
        expected_new_take_profit = lower_price * (1 - self.trailing_percentage)  # 44100.0
        
        self.assertEqual(trailing_take_profit, expected_new_take_profit)
        self.assertLess(trailing_take_profit, initial_take_profit)
        self.assertEqual(self.take_profit.lowest_price, lower_price)

    def test_trailing_take_profit_short_price_increases(self):
        """Test trailing take profit remains unchanged when price increases for a short position"""
        entry_price = 50000.0
        position_side = "short"
        
        # Initial calculation
        initial_price = entry_price
        initial_take_profit = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=initial_price,
            position_side=position_side
        )
        
        # Price decreases - take profit should lower
        lower_price = 45000.0
        lower_take_profit = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=lower_price,
            position_side=position_side
        )
        
        # Price increases but still below initial - take profit should remain at previous level
        middle_price = 48000.0
        middle_take_profit = self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=middle_price,
            position_side=position_side
        )
        
        self.assertEqual(middle_take_profit, lower_take_profit)
        self.assertEqual(self.take_profit.lowest_price, lower_price)

    def test_invalid_position_side(self):
        """Test behavior with invalid position side"""
        entry_price = 50000.0
        current_price = 51000.0
        position_side = "invalid"
        
        with self.assertRaises(ValueError):
            self.take_profit.calculate_take_profit_price(
                entry_price=entry_price,
                current_price=current_price,
                position_side=position_side
            )

    def test_reset_tracking(self):
        """Test resetting the price tracking"""
        entry_price = 50000.0
        position_side = "long"
        
        # Calculate take profit to initialize tracking
        self.take_profit.calculate_take_profit_price(
            entry_price=entry_price,
            current_price=55000.0,
            position_side=position_side
        )
        
        # Verify tracking is active
        self.assertIsNotNone(self.take_profit.highest_price)
        
        # Reset tracking
        self.take_profit.reset_tracking()
        
        # Verify tracking is reset
        self.assertIsNone(self.take_profit.highest_price)
        self.assertIsNone(self.take_profit.lowest_price)


if __name__ == '__main__':
    unittest.main() 