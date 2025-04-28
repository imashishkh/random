"""
Exit strategy implementations for trading positions.

This module contains classes that handle different exit strategies
for trading positions, including multi-level take profit targets.
"""

from typing import Dict, List, Literal, Optional, Any
from datetime import datetime


class MultiLevelExitStrategy:
    """
    Implements a sophisticated multi-level exit strategy for trading positions.
    
    This strategy allows for partial position exits at multiple take profit
    levels, each defined by a risk-reward ratio and percentage of position
    to exit at that level.
    """
    
    def __init__(
        self,
        entry_price: float,
        direction: Literal["long", "short"],
        position_size: float,
        stop_loss_price: float,
        risk_reward_matrix: List[Dict[str, float]] = None
    ):
        """
        Initialize a multi-level exit strategy.
        
        Args:
            entry_price: Entry price of the position
            direction: "long" or "short" position direction
            position_size: Total position size in base units
            stop_loss_price: Stop loss price level
            risk_reward_matrix: List of dictionaries defining exit levels, each containing:
                - target_rr: Target risk-reward ratio for this level
                - exit_percentage: Percentage of position to exit at this level
                Default is [[1.0, 33%], [2.0, 33%], [3.0, 34%]]
        """
        self.entry_price = entry_price
        self.direction = direction
        self.initial_position_size = position_size
        self.current_position_size = position_size
        self.stop_loss_price = stop_loss_price
        self.exit_levels_executed = []
        
        # Default risk-reward matrix if not provided
        self.risk_reward_matrix = risk_reward_matrix or [
            {"target_rr": 1.0, "exit_percentage": 33},
            {"target_rr": 2.0, "exit_percentage": 33},
            {"target_rr": 3.0, "exit_percentage": 34}
        ]
        
        # Calculate stop distance
        self.stop_distance = abs(entry_price - stop_loss_price)
        
        # Calculate actual take profit levels
        self.take_profit_levels = []
        for i, level in enumerate(self.risk_reward_matrix):
            target_rr = level["target_rr"]
            exit_percentage = level["exit_percentage"]
            
            # Calculate the exit size
            exit_size = (exit_percentage / 100) * self.initial_position_size
            
            # Calculate price level based on R:R
            price_level = self._calculate_price_level(target_rr)
                
            self.take_profit_levels.append({
                "id": i + 1,
                "risk_reward": target_rr,
                "price": price_level,
                "exit_percentage": exit_percentage,
                "size_to_exit": exit_size,
                "executed": False
            })
    
    def _calculate_price_level(self, risk_reward: float) -> float:
        """
        Calculate price level for a given risk-reward ratio.
        
        Args:
            risk_reward: The risk-reward ratio
            
        Returns:
            Price level for the given risk-reward ratio
        """
        # Calculate price move based on R:R
        price_move = self.stop_distance * risk_reward
        
        # Apply price move based on direction
        if self.direction == "long":
            return self.entry_price + price_move
        else:
            return self.entry_price - price_move
    
    def update(self, current_price: float) -> Dict[str, Any]:
        """
        Update exit strategy and check if any exit levels are triggered.
        
        Args:
            current_price: Current market price
            
        Returns:
            Dictionary with exit information:
            - exit_signal: Whether an exit should be executed
            - exit_reason: Reason for exit (if exit_signal is True)
            - exit_price: Current price (if exit_signal is True)
            - exit_size: Size to exit (if exit_signal is True)
            - remaining_size: Remaining position size after exit
            - executed_levels: List of levels executed in this update
            - is_full_exit: Whether this is a full position exit
        """
        exits_to_execute = []
        
        # Find which levels should be executed
        for level in self.take_profit_levels:
            if level["executed"]:
                continue
                
            # Check if price has reached the take profit level
            level_triggered = False
            if self.direction == "long" and current_price >= level["price"]:
                level_triggered = True
            elif self.direction == "short" and current_price <= level["price"]:
                level_triggered = True
                
            if level_triggered:
                level["executed"] = True
                exits_to_execute.append(level)
        
        # If we have exits to execute
        if exits_to_execute:
            # Calculate total size to exit
            total_exit_size = sum(level["size_to_exit"] for level in exits_to_execute)
            
            # Update remaining position size
            self.current_position_size -= total_exit_size
            
            # Track executed exits
            self.exit_levels_executed.extend(exits_to_execute)
            
            return {
                "exit_signal": True,
                "exit_reason": "take_profit",
                "exit_price": current_price,
                "exit_size": total_exit_size,
                "remaining_size": self.current_position_size,
                "executed_levels": exits_to_execute,
                "is_full_exit": self.current_position_size <= 0
            }
            
        return {
            "exit_signal": False,
            "current_position_size": self.current_position_size,
            "pending_levels": [lvl for lvl in self.take_profit_levels if not lvl["executed"]]
        }
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current exit strategy status.
        
        Returns:
            Dictionary with current status information
        """
        return {
            "initial_position_size": self.initial_position_size,
            "current_position_size": self.current_position_size,
            "take_profit_levels": self.take_profit_levels,
            "executed_levels": self.exit_levels_executed,
            "pending_levels": [lvl for lvl in self.take_profit_levels if not lvl["executed"]]
        }
        
    def adjust_exit_levels(
        self, 
        new_levels: List[Dict[str, float]],
        apply_to_pending_only: bool = True
    ) -> None:
        """
        Adjust take profit levels dynamically during trade.
        
        Args:
            new_levels: List of new exit levels
            apply_to_pending_only: If True, only modify levels not yet executed
        """
        if apply_to_pending_only:
            # Replace only pending levels
            executed_levels = [lvl for lvl in self.take_profit_levels if lvl["executed"]]
            new_take_profit_levels = []
            
            # Add executed levels first
            new_take_profit_levels.extend(executed_levels)
            
            # Add new levels with proper IDs
            next_id = len(executed_levels) + 1
            for level in new_levels:
                level_copy = level.copy()
                price_level = self._calculate_price_level(level["target_rr"])
                exit_size = (level["exit_percentage"] / 100) * self.initial_position_size
                
                level_copy["id"] = next_id
                level_copy["risk_reward"] = level["target_rr"]
                level_copy["price"] = price_level
                level_copy["size_to_exit"] = exit_size
                level_copy["executed"] = False
                new_take_profit_levels.append(level_copy)
                next_id += 1
                
            self.take_profit_levels = new_take_profit_levels
        else:
            # Replace all levels
            self.take_profit_levels = []
            for i, level in enumerate(new_levels):
                level_copy = level.copy()
                price_level = self._calculate_price_level(level["target_rr"])
                exit_size = (level["exit_percentage"] / 100) * self.initial_position_size
                
                level_copy["id"] = i + 1
                level_copy["risk_reward"] = level["target_rr"]
                level_copy["price"] = price_level
                level_copy["size_to_exit"] = exit_size
                level_copy["executed"] = False
                self.take_profit_levels.append(level_copy)
                
            # Reset tracking
            self.current_position_size = self.initial_position_size
            self.exit_levels_executed = [] 