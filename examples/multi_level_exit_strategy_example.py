#!/usr/bin/env python
"""
Example demonstrating the usage of MultiLevelExitStrategy.

This script shows how to implement a multi-level exit strategy for a forex trading position,
with partial exits at different risk-reward levels.
"""

import os
import sys
import time
from datetime import datetime

# Add the project root directory to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.agents.risk.exit_strategy import MultiLevelExitStrategy

def simulate_price_movement(start_price, direction, volatility=0.01, max_steps=100):
    """
    Simulate price movement for demonstration purposes.
    
    Args:
        start_price: Starting price
        direction: Overall trend direction ("up", "down", or "sideways")
        volatility: Price volatility factor
        max_steps: Maximum number of steps to simulate
        
    Yields:
        Simulated price at each step
    """
    import random
    
    current_price = start_price
    
    # Direction factors
    if direction == "up":
        trend_factor = 0.001  # Upward bias
    elif direction == "down":
        trend_factor = -0.001  # Downward bias
    else:
        trend_factor = 0  # Sideways
    
    for _ in range(max_steps):
        # Random component (normally distributed)
        random_factor = random.normalvariate(0, volatility)
        
        # Calculate price movement
        movement = current_price * (trend_factor + random_factor)
        current_price += movement
        
        # Ensure price stays positive
        current_price = max(current_price, 0.0001)
        
        yield current_price
        
        # Small delay to simulate real-time updates
        time.sleep(0.1)

def main():
    """Run the multi-level exit strategy example."""
    print("=" * 60)
    print("MULTI-LEVEL EXIT STRATEGY EXAMPLE")
    print("=" * 60)
    
    # Trade parameters
    entry_price = 1.1000
    stop_loss_price = 1.0950  # 50 pips stop loss
    position_size = 10000  # 10,000 units
    direction = "long"
    
    print(f"Trade Setup:")
    print(f"  - Direction: {direction.upper()}")
    print(f"  - Entry Price: {entry_price:.4f}")
    print(f"  - Stop Loss: {stop_loss_price:.4f}")
    print(f"  - Position Size: {position_size} units")
    print()
    
    # Custom risk-reward matrix
    risk_reward_matrix = [
        {"target_rr": 1.0, "exit_percentage": 30},  # 30% at 1:1 R:R
        {"target_rr": 2.0, "exit_percentage": 30},  # 30% at 2:1 R:R
        {"target_rr": 3.0, "exit_percentage": 40}   # 40% at 3:1 R:R
    ]
    
    # Create multi-level exit strategy
    exit_strategy = MultiLevelExitStrategy(
        entry_price=entry_price,
        direction=direction,
        position_size=position_size,
        stop_loss_price=stop_loss_price,
        risk_reward_matrix=risk_reward_matrix
    )
    
    # Display exit levels
    print("Exit Strategy - Take Profit Levels:")
    for level in exit_strategy.take_profit_levels:
        print(f"  - Level {level['id']}: {level['price']:.4f} "
              f"(R:R {level['risk_reward']:.1f}:1, "
              f"{level['exit_percentage']}% of position = "
              f"{level['size_to_exit']:.1f} units)")
    print()
    
    # Simulate price movement
    print("Starting price simulation...")
    print(f"{'Time':<20} {'Price':<10} {'Action':<30} {'Position':<10}")
    print("-" * 70)
    
    # Print initial position
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{current_time:<20} {entry_price:.4f} {'ENTRY':<30} {position_size:<10}")
    
    price_simulator = simulate_price_movement(
        start_price=entry_price,
        direction="up",  # Simulating upward trend to hit take profit levels
        volatility=0.0005,
        max_steps=300
    )
    
    total_profit = 0
    
    for price in price_simulator:
        # Update exit strategy with current price
        result = exit_strategy.update(price)
        
        if result["exit_signal"]:
            # Get current time for logging
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Calculate the profit for this exit
            if direction == "long":
                exit_profit = (price - entry_price) * result["exit_size"]
            else:
                exit_profit = (entry_price - price) * result["exit_size"]
            
            total_profit += exit_profit
            
            # Format action text
            levels_text = ", ".join([f"Level {l['id']}" for l in result["executed_levels"]])
            action = f"EXIT {result['exit_size']:.1f} units at {levels_text}"
            
            # Print exit information
            print(f"{current_time:<20} {price:.4f} {action:<30} {result['remaining_size']:<10}")
            
            # If this is a full exit, we'll stop the simulation
            if result["is_full_exit"]:
                break
        
        # Check if we've hit all exit levels
        if len(exit_strategy.exit_levels_executed) == len(exit_strategy.take_profit_levels):
            break
    
    # Print final results
    print("-" * 70)
    print(f"Trade complete!")
    print(f"Total profit: {total_profit:.2f} ({(total_profit/position_size)*100:.2f}% of initial position)")
    
    # Show final status
    final_status = exit_strategy.get_status()
    print("\nFinal Status:")
    print(f"  - Executed levels: {len(final_status['executed_levels'])}/{len(final_status['take_profit_levels'])}")
    print(f"  - Remaining position size: {final_status['current_position_size']:.1f} units")
    
    print("\nExample complete.")

if __name__ == "__main__":
    main() 