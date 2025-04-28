"""
Unit tests for the StopLossManager class.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from src.agents.risk.stop_loss_manager import StopLossManager


@pytest.fixture
def stop_loss_manager():
    """Create a StopLossManager instance for testing."""
    entry_time = datetime(2023, 1, 1, 12, 0, 0)
    return StopLossManager(
        direction="long",
        entry_price=1.1000,
        entry_time=entry_time,
        capital_at_risk=100.0
    )


class TestStopLossManager:
    """Tests for the StopLossManager class."""

    def test_initialization(self):
        """Test StopLossManager initialization."""
        entry_time = datetime(2023, 1, 1, 12, 0, 0)
        
        # Test long position
        long_manager = StopLossManager(
            direction="long",
            entry_price=1.1000,
            entry_time=entry_time,
            capital_at_risk=100.0
        )
        
        assert long_manager.direction == "long"
        assert long_manager.entry_price == 1.1000
        assert long_manager.entry_time == entry_time
        assert long_manager.capital_at_risk == 100.0
        assert long_manager.stops == {}
        assert long_manager.current_price == 1.1000
        
        # Test short position
        short_manager = StopLossManager(
            direction="short",
            entry_price=1.1000,
            entry_time=entry_time,
            capital_at_risk=100.0
        )
        
        assert short_manager.direction == "short"

    def test_add_volatility_stop_long(self, stop_loss_manager):
        """Test adding a volatility-based stop loss for a long position."""
        stop_loss_manager.add_volatility_stop(atr_value=0.0050, atr_multiplier=3.0)
        
        assert "volatility" in stop_loss_manager.stops
        stop = stop_loss_manager.stops["volatility"]
        
        # For long position: entry_price - (atr_value * atr_multiplier)
        expected_stop_price = 1.1000 - (0.0050 * 3.0)  # 1.1000 - 0.0150 = 1.0850
        
        assert stop["price"] == expected_stop_price
        assert stop["type"] == "volatility"
        assert stop["params"]["atr"] == 0.0050
        assert stop["params"]["multiplier"] == 3.0

    def test_add_volatility_stop_short(self):
        """Test adding a volatility-based stop loss for a short position."""
        entry_time = datetime(2023, 1, 1, 12, 0, 0)
        short_manager = StopLossManager(
            direction="short",
            entry_price=1.1000,
            entry_time=entry_time,
            capital_at_risk=100.0
        )
        
        short_manager.add_volatility_stop(atr_value=0.0050, atr_multiplier=3.0)
        
        assert "volatility" in short_manager.stops
        stop = short_manager.stops["volatility"]
        
        # For short position: entry_price + (atr_value * atr_multiplier)
        expected_stop_price = 1.1000 + (0.0050 * 3.0)  # 1.1000 + 0.0150 = 1.1150
        
        assert stop["price"] == expected_stop_price
        assert stop["type"] == "volatility"
        assert stop["params"]["atr"] == 0.0050
        assert stop["params"]["multiplier"] == 3.0

    def test_add_percentage_stop_long(self, stop_loss_manager):
        """Test adding a percentage-based stop loss for a long position."""
        stop_loss_manager.add_percentage_stop(percentage=1.0)  # 1% stop
        
        assert "percentage" in stop_loss_manager.stops
        stop = stop_loss_manager.stops["percentage"]
        
        # For long position: entry_price * (1 - percentage/100)
        expected_stop_price = 1.1000 * (1 - 1.0/100)  # 1.1000 * 0.99 = 1.0890
        
        assert stop["price"] == pytest.approx(expected_stop_price)
        assert stop["type"] == "percentage"
        assert stop["params"]["percentage"] == 1.0

    def test_add_percentage_stop_short(self):
        """Test adding a percentage-based stop loss for a short position."""
        entry_time = datetime(2023, 1, 1, 12, 0, 0)
        short_manager = StopLossManager(
            direction="short",
            entry_price=1.1000,
            entry_time=entry_time,
            capital_at_risk=100.0
        )
        
        short_manager.add_percentage_stop(percentage=1.0)  # 1% stop
        
        assert "percentage" in short_manager.stops
        stop = short_manager.stops["percentage"]
        
        # For short position: entry_price * (1 + percentage/100)
        expected_stop_price = 1.1000 * (1 + 1.0/100)  # 1.1000 * 1.01 = 1.1110
        
        assert stop["price"] == pytest.approx(expected_stop_price)
        assert stop["type"] == "percentage"
        assert stop["params"]["percentage"] == 1.0

    def test_add_time_based_stop(self, stop_loss_manager):
        """Test adding a time-based stop loss."""
        stop_loss_manager.add_time_based_stop(
            max_duration_hours=24,
            min_profit_percentage=0.5
        )
        
        assert "time" in stop_loss_manager.stops
        stop = stop_loss_manager.stops["time"]
        
        # Expected expiry time: entry_time + timedelta(hours=max_duration_hours)
        expected_expiry = stop_loss_manager.entry_time + timedelta(hours=24)
        
        assert stop["expiry_time"] == expected_expiry
        assert stop["type"] == "time"
        assert stop["params"]["max_duration_hours"] == 24
        assert stop["params"]["min_profit_percentage"] == 0.5

    def test_add_trailing_stop_long(self, stop_loss_manager):
        """Test adding a trailing stop for a long position."""
        stop_loss_manager.add_trailing_stop(
            activation_percentage=0.5,  # Activate when price moves up 0.5%
            trail_percentage=0.2        # Trail by 0.2%
        )
        
        assert "trailing" in stop_loss_manager.stops
        stop = stop_loss_manager.stops["trailing"]
        
        # For long position: activation_level = entry_price * (1 + activation_percentage/100)
        expected_activation = 1.1000 * (1 + 0.5/100)  # 1.1000 * 1.005 = 1.1055
        
        assert stop["activation_level"] == pytest.approx(expected_activation)
        assert stop["trail_percentage"] == 0.2
        assert stop["activated"] is False
        assert stop["current_stop"] is None
        assert stop["type"] == "trailing"
        assert stop["params"]["activation_percentage"] == 0.5
        assert stop["params"]["trail_percentage"] == 0.2

    def test_add_trailing_stop_short(self):
        """Test adding a trailing stop for a short position."""
        entry_time = datetime(2023, 1, 1, 12, 0, 0)
        short_manager = StopLossManager(
            direction="short",
            entry_price=1.1000,
            entry_time=entry_time,
            capital_at_risk=100.0
        )
        
        short_manager.add_trailing_stop(
            activation_percentage=0.5,  # Activate when price moves down 0.5%
            trail_percentage=0.2        # Trail by 0.2%
        )
        
        assert "trailing" in short_manager.stops
        stop = short_manager.stops["trailing"]
        
        # For short position: activation_level = entry_price * (1 - activation_percentage/100)
        expected_activation = 1.1000 * (1 - 0.5/100)  # 1.1000 * 0.995 = 1.0945
        
        assert stop["activation_level"] == pytest.approx(expected_activation)
        assert stop["trail_percentage"] == 0.2
        assert stop["activated"] is False
        assert stop["current_stop"] is None

    def test_update_no_stops_triggered(self, stop_loss_manager):
        """Test update method when no stops are triggered."""
        # Set current price to a level that won't trigger any stops
        current_price = 1.1050  # Higher than entry, no stops
        current_time = stop_loss_manager.entry_time + timedelta(hours=1)
        
        result = stop_loss_manager.update(current_price, current_time)
        
        assert result["exit_signal"] is False
        assert result["current_price"] == current_price
        assert result["profit_percentage"] == pytest.approx(0.45)  # (1.1050 - 1.1000) / 1.1000 * 100

    def test_update_volatility_stop_triggered_long(self, stop_loss_manager):
        """Test update method when volatility stop is triggered for a long position."""
        # Add a volatility stop
        stop_loss_manager.add_volatility_stop(atr_value=0.0050, atr_multiplier=2.0)
        
        # Expected stop price: 1.1000 - (0.0050 * 2.0) = 1.0900
        # Set current price below stop to trigger it
        current_price = 1.0890
        current_time = stop_loss_manager.entry_time + timedelta(hours=1)
        
        result = stop_loss_manager.update(current_price, current_time)
        
        assert result["exit_signal"] is True
        assert result["exit_reason"] == "stop_loss_volatility"
        assert "stop_details" in result
        assert result["stop_details"]["type"] == "volatility"

    def test_update_percentage_stop_triggered_short(self):
        """Test update method when percentage stop is triggered for a short position."""
        entry_time = datetime(2023, 1, 1, 12, 0, 0)
        short_manager = StopLossManager(
            direction="short",
            entry_price=1.1000,
            entry_time=entry_time,
            capital_at_risk=100.0
        )
        
        # Add a percentage stop for short
        short_manager.add_percentage_stop(percentage=1.0)
        
        # Expected stop price: 1.1000 * (1 + 1/100) = 1.1110
        # Set current price above stop to trigger it
        current_price = 1.1120
        current_time = entry_time + timedelta(hours=1)
        
        result = short_manager.update(current_price, current_time)
        
        assert result["exit_signal"] is True
        assert result["exit_reason"] == "stop_loss_percentage"
        assert "stop_details" in result
        assert result["stop_details"]["type"] == "percentage"

    def test_update_time_stop_triggered(self, stop_loss_manager):
        """Test update method when time-based stop is triggered."""
        # Add a time-based stop
        stop_loss_manager.add_time_based_stop(
            max_duration_hours=4,
            min_profit_percentage=0.0  # No minimum profit requirement
        )
        
        # Set current time after expiry
        current_price = 1.1020  # Slight profit
        current_time = stop_loss_manager.entry_time + timedelta(hours=5)  # > 4 hours
        
        result = stop_loss_manager.update(current_price, current_time)
        
        assert result["exit_signal"] is True
        assert result["exit_reason"] == "stop_loss_time"
        assert "stop_details" in result
        assert result["stop_details"]["type"] == "time"

    def test_time_stop_not_triggered_insufficient_profit(self, stop_loss_manager):
        """Test time-based stop not triggered when profit requirement not met."""
        # Add a time-based stop with profit requirement
        stop_loss_manager.add_time_based_stop(
            max_duration_hours=4,
            min_profit_percentage=1.0  # Require 1% profit
        )
        
        # Set current time after expiry, but profit too small
        current_price = 1.1005  # Only 0.05% profit
        current_time = stop_loss_manager.entry_time + timedelta(hours=5)  # > 4 hours
        
        result = stop_loss_manager.update(current_price, current_time)
        
        # Should not exit because profit requirement not met
        assert result["exit_signal"] is False

    def test_update_trailing_stop_not_activated(self, stop_loss_manager):
        """Test trailing stop not activated when threshold not met."""
        # Add a trailing stop
        stop_loss_manager.add_trailing_stop(
            activation_percentage=1.0,  # Activate at 1% profit
            trail_percentage=0.3        # Trail by 0.3%
        )
        
        # Price moved up but not enough to activate trailing stop
        current_price = 1.1080  # 0.8% up, below 1% activation
        current_time = stop_loss_manager.entry_time + timedelta(hours=1)
        
        result = stop_loss_manager.update(current_price, current_time)
        
        assert result["exit_signal"] is False
        assert stop_loss_manager.stops["trailing"]["activated"] is False
        assert stop_loss_manager.stops["trailing"]["current_stop"] is None

    def test_update_trailing_stop_activated_not_triggered(self, stop_loss_manager):
        """Test trailing stop gets activated but not triggered."""
        # Add a trailing stop
        stop_loss_manager.add_trailing_stop(
            activation_percentage=0.5,  # Activate at 0.5% profit
            trail_percentage=0.2        # Trail by 0.2%
        )
        
        # Price moved up enough to activate trailing stop
        current_price = 1.1060  # 0.55% up, above 0.5% activation
        current_time = stop_loss_manager.entry_time + timedelta(hours=1)
        
        result = stop_loss_manager.update(current_price, current_time)
        
        assert result["exit_signal"] is False
        assert stop_loss_manager.stops["trailing"]["activated"] is True
        
        # Expected trail stop: current_price - (current_price * trail_percentage/100)
        expected_stop = 1.1060 - (1.1060 * 0.2/100)  # 1.1060 - 0.002212 ≈ 1.1038
        assert stop_loss_manager.stops["trailing"]["current_stop"] == pytest.approx(expected_stop)

    def test_update_trailing_stop_moves_up(self, stop_loss_manager):
        """Test trailing stop moves up as price increases."""
        # Add a trailing stop
        stop_loss_manager.add_trailing_stop(
            activation_percentage=0.5,  # Activate at 0.5% profit
            trail_percentage=0.2        # Trail by 0.2%
        )
        
        # First update: activate the trailing stop
        current_price = 1.1060  # 0.55% up, above 0.5% activation
        current_time = stop_loss_manager.entry_time + timedelta(hours=1)
        
        stop_loss_manager.update(current_price, current_time)
        first_stop = stop_loss_manager.stops["trailing"]["current_stop"]
        
        # Second update: price moves higher, stop should move up
        current_price = 1.1100  # Another move up
        stop_loss_manager.update(current_price, current_time)
        second_stop = stop_loss_manager.stops["trailing"]["current_stop"]
        
        assert second_stop > first_stop
        
        # Expected new trail stop: current_price - (current_price * trail_percentage/100)
        expected_stop = 1.1100 - (1.1100 * 0.2/100)
        assert second_stop == pytest.approx(expected_stop)

    def test_update_trailing_stop_triggered(self, stop_loss_manager):
        """Test trailing stop gets triggered when price falls below stop."""
        # Add a trailing stop
        stop_loss_manager.add_trailing_stop(
            activation_percentage=0.5,  # Activate at 0.5% profit
            trail_percentage=0.2        # Trail by 0.2%
        )
        
        # First update: activate the trailing stop
        current_price = 1.1060  # 0.55% up, above 0.5% activation
        current_time = stop_loss_manager.entry_time + timedelta(hours=1)
        
        stop_loss_manager.update(current_price, current_time)
        
        # Expected trail stop: 1.1060 - (1.1060 * 0.2/100) ≈ 1.1038
        
        # Second update: price drops below the trailing stop
        current_price = 1.1030  # Below trailing stop
        result = stop_loss_manager.update(current_price, current_time)
        
        assert result["exit_signal"] is True
        assert result["exit_reason"] == "stop_loss_trailing"
        assert "stop_details" in result
        assert result["stop_details"]["type"] == "trailing"

    def test_multiple_stops_priority(self, stop_loss_manager):
        """Test priority order when multiple stops are triggered."""
        # Add multiple stops
        stop_loss_manager.add_volatility_stop(atr_value=0.0050, atr_multiplier=2.0)  # Stop at 1.0900
        stop_loss_manager.add_percentage_stop(percentage=1.5)  # Stop at 1.0835
        stop_loss_manager.add_time_based_stop(max_duration_hours=24, min_profit_percentage=0)
        
        # Set price to trigger both volatility and percentage stops
        current_price = 1.0830  # Below both stops
        current_time = stop_loss_manager.entry_time + timedelta(hours=1)
        
        result = stop_loss_manager.update(current_price, current_time)
        
        # Volatility stop has higher priority and should be selected
        assert result["exit_signal"] is True
        assert result["exit_reason"] == "stop_loss_volatility"

    def test_calculate_profit_percentage_long(self, stop_loss_manager):
        """Test profit percentage calculation for long position."""
        # Create a method to directly test _calculate_profit_percentage
        profit_pct = stop_loss_manager._calculate_profit_percentage(1.1110)
        
        # Expected: ((1.1110 - 1.1000) / 1.1000) * 100 = 1.0%
        assert profit_pct == pytest.approx(1.0)
        
        # Test with loss
        profit_pct = stop_loss_manager._calculate_profit_percentage(1.0945)
        
        # Expected: ((1.0945 - 1.1000) / 1.1000) * 100 = -0.5%
        assert profit_pct == pytest.approx(-0.5)

    def test_calculate_profit_percentage_short(self):
        """Test profit percentage calculation for short position."""
        entry_time = datetime(2023, 1, 1, 12, 0, 0)
        short_manager = StopLossManager(
            direction="short",
            entry_price=1.1000,
            entry_time=entry_time,
            capital_at_risk=100.0
        )
        
        # Create a method to directly test _calculate_profit_percentage
        profit_pct = short_manager._calculate_profit_percentage(1.0890)
        
        # Expected: ((1.1000 - 1.0890) / 1.1000) * 100 = 1.0%
        assert profit_pct == pytest.approx(1.0)
        
        # Test with loss
        profit_pct = short_manager._calculate_profit_percentage(1.1055)
        
        # Expected: ((1.1000 - 1.1055) / 1.1000) * 100 = -0.5%
        assert profit_pct == pytest.approx(-0.5) 