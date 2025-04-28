import unittest
from unittest.mock import Mock
from src.trading.exit_management import (
    FixedStopLoss,
    TrailingStopLoss,
    Position
)


class TestFixedStopLoss(unittest.TestCase):
    """Test cases for the FixedStopLoss strategy"""

    def setUp(self):
        """Set up test fixtures"""
        self.risk_percentage = 0.02
        self.stop_loss = FixedStopLoss(risk_percentage=self.risk_percentage)
        
    def test_initialization(self):
        """Test if the strategy is properly initialized"""
        self.assertEqual(self.stop_loss.risk_percentage, self.risk_percentage)
        self.assertEqual(self.stop_loss.name, "Fixed Stop Loss")
    
    def test_calculate_stop_loss_price_long(self):
        """Test calculation of stop loss price for a long position"""
        entry_price = 50000.0
        current_price = 51000.0  # Current price is higher than entry price
        position_side = "long"
        
        expected_price = entry_price * (1 - self.risk_percentage)  # 49000.0
        
        stop_loss_price = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=current_price,
            position_side=position_side
        )
        
        self.assertEqual(stop_loss_price, expected_price)
    
    def test_calculate_stop_loss_price_short(self):
        """Test calculation of stop loss price for a short position"""
        entry_price = 50000.0
        current_price = 49000.0  # Current price is lower than entry price
        position_side = "short"
        
        expected_price = entry_price * (1 + self.risk_percentage)  # 51000.0
        
        stop_loss_price = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=current_price,
            position_side=position_side
        )
        
        self.assertEqual(stop_loss_price, expected_price)
    
    def test_invalid_position_side(self):
        """Test behavior with invalid position side"""
        entry_price = 50000.0
        current_price = 51000.0
        position_side = "invalid"
        
        with self.assertRaises(ValueError):
            self.stop_loss.calculate_stop_loss_price(
                entry_price=entry_price,
                current_price=current_price,
                position_side=position_side
            )
    
    def test_calculate_stop_loss_price_unchanged(self):
        """Test that stop loss price remains fixed even when price changes"""
        entry_price = 50000.0
        position_side = "long"
        
        # Initial calculation with price equal to entry
        initial_price = entry_price
        initial_stop_loss = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=initial_price,
            position_side=position_side
        )
        
        # Price increases
        higher_price = 55000.0
        higher_stop_loss = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=higher_price,
            position_side=position_side
        )
        
        # Price decreases
        lower_price = 45000.0
        lower_stop_loss = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=lower_price,
            position_side=position_side
        )
        
        # All stop loss prices should be the same regardless of current price
        self.assertEqual(initial_stop_loss, higher_stop_loss)
        self.assertEqual(initial_stop_loss, lower_stop_loss)


class TestTrailingStopLoss(unittest.TestCase):
    """Test cases for the TrailingStopLoss strategy"""

    def setUp(self):
        """Set up test fixtures"""
        self.initial_percentage = 0.02
        self.trailing_percentage = 0.01
        self.stop_loss = TrailingStopLoss(
            initial_percentage=self.initial_percentage,
            trailing_percentage=self.trailing_percentage
        )
        
    def test_initialization(self):
        """Test if the strategy is properly initialized"""
        self.assertEqual(self.stop_loss.initial_percentage, self.initial_percentage)
        self.assertEqual(self.stop_loss.trailing_percentage, self.trailing_percentage)
        self.assertEqual(self.stop_loss.name, "Trailing Stop Loss")
        self.assertIsNone(self.stop_loss.highest_price)
        self.assertIsNone(self.stop_loss.lowest_price)
    
    def test_calculate_initial_stop_loss_price_long(self):
        """Test the initial stop loss price calculation for a long position"""
        entry_price = 50000.0
        current_price = entry_price  # First price update is equal to entry
        position_side = "long"
        
        expected_price = entry_price * (1 - self.initial_percentage)  # 49000.0
        
        stop_loss_price = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=current_price,
            position_side=position_side
        )
        
        self.assertEqual(stop_loss_price, expected_price)
        self.assertEqual(self.stop_loss.highest_price, current_price)
    
    def test_calculate_initial_stop_loss_price_short(self):
        """Test the initial stop loss price calculation for a short position"""
        entry_price = 50000.0
        current_price = entry_price  # First price update is equal to entry
        position_side = "short"
        
        expected_price = entry_price * (1 + self.initial_percentage)  # 51000.0
        
        stop_loss_price = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=current_price,
            position_side=position_side
        )
        
        self.assertEqual(stop_loss_price, expected_price)
        self.assertEqual(self.stop_loss.lowest_price, current_price)
    
    def test_trailing_stop_loss_long_price_increases(self):
        """Test trailing stop loss adjustment when price increases for a long position"""
        entry_price = 50000.0
        position_side = "long"
        
        # Initial calculation
        initial_price = entry_price
        initial_stop_loss = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=initial_price,
            position_side=position_side
        )
        
        # Price increases - stop loss should be raised based on trailing percentage
        higher_price = 55000.0
        trailing_stop_loss = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=higher_price,
            position_side=position_side
        )
        
        expected_new_stop_loss = higher_price * (1 - self.trailing_percentage)  # 54450.0
        
        self.assertEqual(trailing_stop_loss, expected_new_stop_loss)
        self.assertGreater(trailing_stop_loss, initial_stop_loss)
        self.assertEqual(self.stop_loss.highest_price, higher_price)
    
    def test_trailing_stop_loss_long_price_decreases(self):
        """Test trailing stop loss remains unchanged when price decreases for a long position"""
        entry_price = 50000.0
        position_side = "long"
        
        # Initial calculation
        initial_price = entry_price
        initial_stop_loss = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=initial_price,
            position_side=position_side
        )
        
        # Price increases - stop loss should rise
        higher_price = 55000.0
        higher_stop_loss = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=higher_price,
            position_side=position_side
        )
        
        # Price decreases but still above initial - stop loss should remain at previous level
        middle_price = 52000.0
        middle_stop_loss = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=middle_price,
            position_side=position_side
        )
        
        self.assertEqual(middle_stop_loss, higher_stop_loss)
        self.assertEqual(self.stop_loss.highest_price, higher_price)
    
    def test_trailing_stop_loss_short_price_decreases(self):
        """Test trailing stop loss adjustment when price decreases for a short position"""
        entry_price = 50000.0
        position_side = "short"
        
        # Initial calculation
        initial_price = entry_price
        initial_stop_loss = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=initial_price,
            position_side=position_side
        )
        
        # Price decreases - stop loss should be lowered based on trailing percentage
        lower_price = 45000.0
        trailing_stop_loss = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=lower_price,
            position_side=position_side
        )
        
        expected_new_stop_loss = lower_price * (1 + self.trailing_percentage)  # 45450.0
        
        self.assertEqual(trailing_stop_loss, expected_new_stop_loss)
        self.assertLess(trailing_stop_loss, initial_stop_loss)
        self.assertEqual(self.stop_loss.lowest_price, lower_price)
    
    def test_trailing_stop_loss_short_price_increases(self):
        """Test trailing stop loss remains unchanged when price increases for a short position"""
        entry_price = 50000.0
        position_side = "short"
        
        # Initial calculation
        initial_price = entry_price
        initial_stop_loss = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=initial_price,
            position_side=position_side
        )
        
        # Price decreases - stop loss should lower
        lower_price = 45000.0
        lower_stop_loss = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=lower_price,
            position_side=position_side
        )
        
        # Price increases but still below initial - stop loss should remain at previous level
        middle_price = 48000.0
        middle_stop_loss = self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=middle_price,
            position_side=position_side
        )
        
        self.assertEqual(middle_stop_loss, lower_stop_loss)
        self.assertEqual(self.stop_loss.lowest_price, lower_price)
    
    def test_invalid_position_side(self):
        """Test behavior with invalid position side"""
        entry_price = 50000.0
        current_price = 51000.0
        position_side = "invalid"
        
        with self.assertRaises(ValueError):
            self.stop_loss.calculate_stop_loss_price(
                entry_price=entry_price,
                current_price=current_price,
                position_side=position_side
            )
    
    def test_reset_tracking(self):
        """Test resetting the price tracking"""
        entry_price = 50000.0
        position_side = "long"
        
        # Calculate stop loss to initialize tracking
        self.stop_loss.calculate_stop_loss_price(
            entry_price=entry_price,
            current_price=55000.0,
            position_side=position_side
        )
        
        # Verify tracking is active
        self.assertIsNotNone(self.stop_loss.highest_price)
        
        # Reset tracking
        self.stop_loss.reset_tracking()
        
        # Verify tracking is reset
        self.assertIsNone(self.stop_loss.highest_price)
        self.assertIsNone(self.stop_loss.lowest_price)


if __name__ == '__main__':
    unittest.main() 