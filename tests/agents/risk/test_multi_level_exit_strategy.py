"""
Unit tests for the MultiLevelExitStrategy class.

This module contains tests that verify the functionality of the 
MultiLevelExitStrategy class, which manages position exits at 
multiple take profit levels.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.agents.risk.exit_strategy import MultiLevelExitStrategy


@pytest.fixture
def default_exit_strategy():
    """Create a default exit strategy for long position."""
    return MultiLevelExitStrategy(
        entry_price=100.0,
        direction="long",
        position_size=1.0,
        stop_loss_price=90.0
    )


@pytest.fixture
def custom_exit_strategy():
    """Create a custom exit strategy for short position."""
    return MultiLevelExitStrategy(
        entry_price=100.0,
        direction="short",
        position_size=2.0,
        stop_loss_price=110.0,
        risk_reward_matrix=[
            {"target_rr": 1.5, "exit_percentage": 50},
            {"target_rr": 3.0, "exit_percentage": 50}
        ]
    )


class TestMultiLevelExitStrategy:
    """Tests for the MultiLevelExitStrategy class."""
    
    def test_initialization_with_defaults(self, default_exit_strategy):
        """Test initialization with default settings."""
        strategy = default_exit_strategy
        
        # Check basic properties
        assert strategy.entry_price == 100.0
        assert strategy.direction == "long"
        assert strategy.initial_position_size == 1.0
        assert strategy.current_position_size == 1.0
        assert strategy.stop_loss_price == 90.0
        
        # Check default risk_reward_matrix
        assert len(strategy.risk_reward_matrix) == 3
        assert strategy.risk_reward_matrix[0]["target_rr"] == 1.0
        assert strategy.risk_reward_matrix[0]["exit_percentage"] == 33
        assert strategy.risk_reward_matrix[1]["target_rr"] == 2.0
        assert strategy.risk_reward_matrix[1]["exit_percentage"] == 33
        assert strategy.risk_reward_matrix[2]["target_rr"] == 3.0
        assert strategy.risk_reward_matrix[2]["exit_percentage"] == 34
        
        # Check calculated stop distance
        assert strategy.stop_distance == 10.0
        
        # Check take profit levels
        assert len(strategy.take_profit_levels) == 3
        
        # Check first level
        level1 = strategy.take_profit_levels[0]
        assert level1["id"] == 1
        assert level1["risk_reward"] == 1.0
        assert level1["price"] == 110.0  # entry + (stop_distance * rr)
        assert level1["exit_percentage"] == 33
        assert level1["size_to_exit"] == 0.33
        assert level1["executed"] is False
        
        # Check third level
        level3 = strategy.take_profit_levels[2]
        assert level3["id"] == 3
        assert level3["risk_reward"] == 3.0
        assert level3["price"] == 130.0  # entry + (stop_distance * rr)
        assert level3["exit_percentage"] == 34
        assert level3["size_to_exit"] == 0.34
        assert level3["executed"] is False
    
    def test_initialization_with_custom_settings(self, custom_exit_strategy):
        """Test initialization with custom settings."""
        strategy = custom_exit_strategy
        
        # Check basic properties
        assert strategy.entry_price == 100.0
        assert strategy.direction == "short"
        assert strategy.initial_position_size == 2.0
        assert strategy.current_position_size == 2.0
        assert strategy.stop_loss_price == 110.0
        
        # Check custom risk_reward_matrix
        assert len(strategy.risk_reward_matrix) == 2
        assert strategy.risk_reward_matrix[0]["target_rr"] == 1.5
        assert strategy.risk_reward_matrix[0]["exit_percentage"] == 50
        assert strategy.risk_reward_matrix[1]["target_rr"] == 3.0
        assert strategy.risk_reward_matrix[1]["exit_percentage"] == 50
        
        # Check calculated stop distance
        assert strategy.stop_distance == 10.0
        
        # Check take profit levels
        assert len(strategy.take_profit_levels) == 2
        
        # Check first level for short position
        level1 = strategy.take_profit_levels[0]
        assert level1["id"] == 1
        assert level1["risk_reward"] == 1.5
        assert level1["price"] == 85.0  # entry - (stop_distance * rr)
        assert level1["exit_percentage"] == 50
        assert level1["size_to_exit"] == 1.0
        assert level1["executed"] is False
        
        # Check second level for short position
        level2 = strategy.take_profit_levels[1]
        assert level2["id"] == 2
        assert level2["risk_reward"] == 3.0
        assert level2["price"] == 70.0  # entry - (stop_distance * rr)
        assert level2["exit_percentage"] == 50
        assert level2["size_to_exit"] == 1.0
        assert level2["executed"] is False
    
    def test_calculate_price_level_long(self, default_exit_strategy):
        """Test price level calculation for long position."""
        strategy = default_exit_strategy
        
        # Test with different risk-reward ratios
        assert strategy._calculate_price_level(1.0) == 110.0
        assert strategy._calculate_price_level(2.0) == 120.0
        assert strategy._calculate_price_level(3.0) == 130.0
        assert strategy._calculate_price_level(4.5) == 145.0
    
    def test_calculate_price_level_short(self, custom_exit_strategy):
        """Test price level calculation for short position."""
        strategy = custom_exit_strategy
        
        # Test with different risk-reward ratios
        assert strategy._calculate_price_level(1.0) == 90.0
        assert strategy._calculate_price_level(1.5) == 85.0
        assert strategy._calculate_price_level(3.0) == 70.0
        assert strategy._calculate_price_level(4.5) == 55.0
    
    def test_size_to_exit_calculation(self, default_exit_strategy):
        """Test the calculation of size to exit."""
        strategy = default_exit_strategy
        
        # Check that exit sizes sum to total position size
        total_exit_size = sum(level["size_to_exit"] for level in strategy.take_profit_levels)
        assert pytest.approx(total_exit_size) == strategy.initial_position_size
        
        # Check individual exit sizes
        assert pytest.approx(strategy.take_profit_levels[0]["size_to_exit"]) == 0.33
        assert pytest.approx(strategy.take_profit_levels[1]["size_to_exit"]) == 0.33
        assert pytest.approx(strategy.take_profit_levels[2]["size_to_exit"]) == 0.34
    
    def test_update_no_exits_triggered(self, default_exit_strategy):
        """Test update method when no exits are triggered."""
        strategy = default_exit_strategy
        
        # Update with price below first take profit level
        result = strategy.update(current_price=105.0)
        
        # Check result
        assert result["exit_signal"] is False
        assert result["current_position_size"] == 1.0
        assert len(result["pending_levels"]) == 3
        
        # Check strategy state
        assert strategy.current_position_size == 1.0
        assert len(strategy.exit_levels_executed) == 0
        assert all(not level["executed"] for level in strategy.take_profit_levels)
    
    def test_update_first_exit_triggered_long(self, default_exit_strategy):
        """Test update method when first exit is triggered for long position."""
        strategy = default_exit_strategy
        
        # Update with price at first take profit level
        result = strategy.update(current_price=110.0)
        
        # Check result
        assert result["exit_signal"] is True
        assert result["exit_reason"] == "take_profit"
        assert result["exit_price"] == 110.0
        assert pytest.approx(result["exit_size"]) == 0.33
        assert pytest.approx(result["remaining_size"]) == 0.67
        assert len(result["executed_levels"]) == 1
        assert result["executed_levels"][0]["id"] == 1
        assert result["is_full_exit"] is False
        
        # Check strategy state
        assert pytest.approx(strategy.current_position_size) == 0.67
        assert len(strategy.exit_levels_executed) == 1
        assert strategy.take_profit_levels[0]["executed"] is True
        assert strategy.take_profit_levels[1]["executed"] is False
        assert strategy.take_profit_levels[2]["executed"] is False
    
    def test_update_first_exit_triggered_short(self, custom_exit_strategy):
        """Test update method when first exit is triggered for short position."""
        strategy = custom_exit_strategy
        
        # Update with price at first take profit level
        result = strategy.update(current_price=85.0)
        
        # Check result
        assert result["exit_signal"] is True
        assert result["exit_reason"] == "take_profit"
        assert result["exit_price"] == 85.0
        assert pytest.approx(result["exit_size"]) == 1.0
        assert pytest.approx(result["remaining_size"]) == 1.0
        assert len(result["executed_levels"]) == 1
        assert result["executed_levels"][0]["id"] == 1
        assert result["is_full_exit"] is False
        
        # Check strategy state
        assert pytest.approx(strategy.current_position_size) == 1.0
        assert len(strategy.exit_levels_executed) == 1
        assert strategy.take_profit_levels[0]["executed"] is True
        assert strategy.take_profit_levels[1]["executed"] is False
    
    def test_update_multiple_exits_triggered(self, default_exit_strategy):
        """Test update method when multiple exits are triggered at once."""
        strategy = default_exit_strategy
        
        # Update with price above all take profit levels
        result = strategy.update(current_price=135.0)
        
        # Check result
        assert result["exit_signal"] is True
        assert result["exit_reason"] == "take_profit"
        assert result["exit_price"] == 135.0
        assert pytest.approx(result["exit_size"]) == 1.0
        assert pytest.approx(result["remaining_size"]) == 0.0
        assert len(result["executed_levels"]) == 3
        assert result["is_full_exit"] is True
        
        # Check strategy state
        assert pytest.approx(strategy.current_position_size) == 0.0
        assert len(strategy.exit_levels_executed) == 3
        assert all(level["executed"] for level in strategy.take_profit_levels)
    
    def test_update_no_duplicate_exits(self, default_exit_strategy):
        """Test that exits aren't triggered multiple times."""
        strategy = default_exit_strategy
        
        # Trigger first exit
        strategy.update(current_price=110.0)
        
        # Try to trigger it again with same price
        result = strategy.update(current_price=110.0)
        
        # Check no exit was triggered this time
        assert result["exit_signal"] is False
        assert pytest.approx(strategy.current_position_size) == 0.67
        assert len(strategy.exit_levels_executed) == 1
    
    def test_sequential_exits(self, default_exit_strategy):
        """Test sequential triggering of exits."""
        strategy = default_exit_strategy
        
        # Trigger first exit
        result1 = strategy.update(current_price=110.0)
        assert result1["exit_signal"] is True
        assert pytest.approx(result1["exit_size"]) == 0.33
        assert pytest.approx(strategy.current_position_size) == 0.67
        
        # Trigger second exit
        result2 = strategy.update(current_price=120.0)
        assert result2["exit_signal"] is True
        assert pytest.approx(result2["exit_size"]) == 0.33
        assert pytest.approx(strategy.current_position_size) == 0.34
        
        # Trigger third exit
        result3 = strategy.update(current_price=130.0)
        assert result3["exit_signal"] is True
        assert pytest.approx(result3["exit_size"]) == 0.34
        assert pytest.approx(strategy.current_position_size) == 0.0
        assert result3["is_full_exit"] is True
    
    def test_get_status(self, default_exit_strategy):
        """Test get_status method."""
        strategy = default_exit_strategy
        
        # Check initial status
        status = strategy.get_status()
        assert status["initial_position_size"] == 1.0
        assert status["current_position_size"] == 1.0
        assert len(status["take_profit_levels"]) == 3
        assert len(status["executed_levels"]) == 0
        assert len(status["pending_levels"]) == 3
        
        # Trigger an exit and check updated status
        strategy.update(current_price=110.0)
        status = strategy.get_status()
        assert status["initial_position_size"] == 1.0
        assert pytest.approx(status["current_position_size"]) == 0.67
        assert len(status["take_profit_levels"]) == 3
        assert len(status["executed_levels"]) == 1
        assert len(status["pending_levels"]) == 2
    
    def test_adjust_exit_levels_pending_only(self, default_exit_strategy):
        """Test adjusting only pending exit levels."""
        strategy = default_exit_strategy
        
        # Trigger first exit
        strategy.update(current_price=110.0)
        
        # Adjust remaining levels
        new_levels = [
            {"target_rr": 2.5, "exit_percentage": 50},
            {"target_rr": 4.0, "exit_percentage": 50}
        ]
        strategy.adjust_exit_levels(new_levels, apply_to_pending_only=True)
        
        # Check updated take profit levels
        assert len(strategy.take_profit_levels) == 3
        
        # First level should remain executed
        assert strategy.take_profit_levels[0]["executed"] is True
        assert strategy.take_profit_levels[0]["id"] == 1
        assert strategy.take_profit_levels[0]["risk_reward"] == 1.0
        assert strategy.take_profit_levels[0]["price"] == 110.0
        
        # New levels should be added
        assert strategy.take_profit_levels[1]["executed"] is False
        assert strategy.take_profit_levels[1]["id"] == 2
        assert strategy.take_profit_levels[1]["risk_reward"] == 2.5
        assert strategy.take_profit_levels[1]["price"] == 125.0
        assert pytest.approx(strategy.take_profit_levels[1]["size_to_exit"]) == 0.5
        
        assert strategy.take_profit_levels[2]["executed"] is False
        assert strategy.take_profit_levels[2]["id"] == 3
        assert strategy.take_profit_levels[2]["risk_reward"] == 4.0
        assert strategy.take_profit_levels[2]["price"] == 140.0
        assert pytest.approx(strategy.take_profit_levels[2]["size_to_exit"]) == 0.5
    
    def test_adjust_exit_levels_all(self, default_exit_strategy):
        """Test adjusting all exit levels."""
        strategy = default_exit_strategy
        
        # Trigger first exit
        strategy.update(current_price=110.0)
        
        # Adjust all levels
        new_levels = [
            {"target_rr": 1.5, "exit_percentage": 40},
            {"target_rr": 3.0, "exit_percentage": 60}
        ]
        strategy.adjust_exit_levels(new_levels, apply_to_pending_only=False)
        
        # Check updated take profit levels
        assert len(strategy.take_profit_levels) == 2
        assert all(not level["executed"] for level in strategy.take_profit_levels)
        
        # Position size should be reset
        assert strategy.current_position_size == 1.0
        assert len(strategy.exit_levels_executed) == 0
        
        # Check new levels
        assert strategy.take_profit_levels[0]["id"] == 1
        assert strategy.take_profit_levels[0]["risk_reward"] == 1.5
        assert strategy.take_profit_levels[0]["price"] == 115.0
        assert pytest.approx(strategy.take_profit_levels[0]["size_to_exit"]) == 0.4
        
        assert strategy.take_profit_levels[1]["id"] == 2
        assert strategy.take_profit_levels[1]["risk_reward"] == 3.0
        assert strategy.take_profit_levels[1]["price"] == 130.0
        assert pytest.approx(strategy.take_profit_levels[1]["size_to_exit"]) == 0.6 