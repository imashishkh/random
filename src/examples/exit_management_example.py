from ..trading.exit_management import (
    ExitManager,
    FixedStopLoss,
    TrailingStopLoss,
    BreakEvenStopLoss,
    CombinedStopLoss,
    FixedTakeProfit,
    TrailingTakeProfit,
    MultiLevelTakeProfit
)


def basic_stop_loss_example():
    """Example of using a basic fixed stop loss"""
    print("\n--- Basic Fixed Stop Loss Example ---")
    
    # Create a fixed stop loss with 2% risk
    fixed_sl = FixedStopLoss(0.02)
    
    # Create an exit manager with only stop loss
    exit_manager = ExitManager(fixed_sl)
    
    # Test with a long position
    entry_price = 100.0
    current_price = 101.5
    
    # Calculate exit prices
    sl_price, tp_price = exit_manager.calculate_exit_prices(entry_price, current_price, "long")
    print(f"Long Position - Entry: {entry_price}, Current: {current_price}")
    print(f"Stop Loss Price: {sl_price}")
    print(f"Take Profit Price: {tp_price}")
    
    # Test with a short position
    entry_price = 100.0
    current_price = 98.5
    
    # Calculate exit prices
    sl_price, tp_price = exit_manager.calculate_exit_prices(entry_price, current_price, "short")
    print(f"\nShort Position - Entry: {entry_price}, Current: {current_price}")
    print(f"Stop Loss Price: {sl_price}")
    print(f"Take Profit Price: {tp_price}")


def combined_stop_loss_example():
    """Example of using a combined stop loss strategy"""
    print("\n--- Combined Stop Loss Example ---")
    
    # Create multiple stop loss strategies
    fixed_sl = FixedStopLoss(0.02)
    trailing_sl = TrailingStopLoss(0.02, 0.01)
    breakeven_sl = BreakEvenStopLoss(0.015)
    
    # Combine them
    combined_sl = CombinedStopLoss([fixed_sl, trailing_sl, breakeven_sl])
    
    # Create an exit manager with the combined strategy
    exit_manager = ExitManager(combined_sl)
    
    # Test with a long position simulation
    entry_price = 100.0
    
    # Price stays flat initially
    current_price = 100.0
    sl_price, _ = exit_manager.calculate_exit_prices(entry_price, current_price, "long")
    print(f"Long Position - Entry: {entry_price}, Current: {current_price}")
    print(f"Stop Loss Price: {sl_price}")
    
    # Price moves in favor (should trigger trailing)
    current_price = 102.0
    sl_price, _ = exit_manager.calculate_exit_prices(entry_price, current_price, "long")
    print(f"\nLong Position - Entry: {entry_price}, Current: {current_price}")
    print(f"Stop Loss Price: {sl_price}")
    
    # Price moves more in favor (trailing adjusts and break-even activates)
    current_price = 103.0
    sl_price, _ = exit_manager.calculate_exit_prices(entry_price, current_price, "long")
    print(f"\nLong Position - Entry: {entry_price}, Current: {current_price}")
    print(f"Stop Loss Price: {sl_price}")


def take_profit_example():
    """Example of using take profit strategies"""
    print("\n--- Take Profit Examples ---")
    
    # Fixed take profit with 5% target
    fixed_tp = FixedTakeProfit(0.05)
    
    # Multi-level take profit at 2%, 4%, and 7% levels
    multi_tp = MultiLevelTakeProfit(
        profit_levels=[0.02, 0.04, 0.07],
        quantity_percentages=[0.3, 0.3, 0.4]
    )
    
    # Trailing take profit that activates at 3% profit
    trailing_tp = TrailingTakeProfit(0.03, 0.01)
    
    # Create exit managers for each strategy
    fixed_manager = ExitManager(FixedStopLoss(0.02), fixed_tp)
    multi_manager = ExitManager(FixedStopLoss(0.02), multi_tp)
    trailing_manager = ExitManager(FixedStopLoss(0.02), trailing_tp)
    
    # Test with a long position at different price levels
    entry_price = 100.0
    
    # Initial prices
    current_price = 101.0
    print(f"Long Position - Entry: {entry_price}, Current: {current_price}")
    
    _, fixed_tp_price = fixed_manager.calculate_exit_prices(entry_price, current_price, "long")
    _, multi_tp_price = multi_manager.calculate_exit_prices(entry_price, current_price, "long")
    _, trailing_tp_price = trailing_manager.calculate_exit_prices(entry_price, current_price, "long")
    
    print(f"Fixed TP Price: {fixed_tp_price}")
    print(f"Multi-level TP Next Target: {multi_tp_price}")
    print(f"Trailing TP Price: {trailing_tp_price}")
    
    # Price moves more in favor
    current_price = 103.5
    print(f"\nLong Position - Entry: {entry_price}, Current: {current_price}")
    
    _, fixed_tp_price = fixed_manager.calculate_exit_prices(entry_price, current_price, "long")
    _, multi_tp_price = multi_manager.calculate_exit_prices(entry_price, current_price, "long")
    _, trailing_tp_price = trailing_manager.calculate_exit_prices(entry_price, current_price, "long")
    
    print(f"Fixed TP Price: {fixed_tp_price}")
    print(f"Multi-level TP Next Target: {multi_tp_price}")
    print(f"Trailing TP Price: {trailing_tp_price}")
    
    # Check if we should exit based on take profit at current price
    print("\nShould Exit?")
    print(f"Fixed TP: {fixed_manager.should_exit_position(entry_price, current_price, 'long')}")
    print(f"Multi-level TP: {multi_manager.should_exit_position(entry_price, current_price, 'long')}")
    
    # For multi-level, get the percentage to close
    if multi_manager.should_exit_position(entry_price, current_price, "long"):
        percent_to_close = multi_tp.get_quantity_percentage_for_current_level()
        print(f"Multi-level percent to close: {percent_to_close * 100}%")
    
    # For trailing TP, show how the level adjusts as price moves
    trailing_manager.reset_tracking()  # Reset to start fresh
    print("\nTrailing Take Profit Example")
    
    price_sequence = [100.0, 101.0, 102.0, 103.0, 103.5, 103.2, 103.8, 103.6]
    for i, current_price in enumerate(price_sequence):
        _, tp_price = trailing_manager.calculate_exit_prices(entry_price, current_price, "long")
        should_exit = trailing_manager.should_exit_position(entry_price, current_price, "long")
        print(f"Step {i}: Price: {current_price}, TP Level: {tp_price}, Exit: {should_exit}")


def complete_example():
    """Example of a full trading position lifecycle with exit management"""
    print("\n--- Complete Trading Example with Exit Management ---")
    
    # Create strategies
    stop_loss = CombinedStopLoss([
        FixedStopLoss(0.02),
        TrailingStopLoss(0.02, 0.01),
        BreakEvenStopLoss(0.03)
    ])
    
    take_profit = MultiLevelTakeProfit(
        profit_levels=[0.02, 0.04, 0.06],
        quantity_percentages=[0.4, 0.3, 0.3]
    )
    
    # Create exit manager
    exit_manager = ExitManager(stop_loss, take_profit)
    
    # Trading parameters
    entry_price = 100.0
    position_side = "long"
    position_size = 1.0  # Full position
    
    # Simulate price movements
    prices = [100.0, 100.5, 101.0, 102.0, 102.5, 101.8, 102.3, 103.0, 104.0, 103.5, 102.8, 102.0, 101.5, 99.0]
    
    remaining_position = position_size
    
    for i, current_price in enumerate(prices):
        sl_price, tp_price = exit_manager.calculate_exit_prices(entry_price, current_price, position_side)
        
        # Check risk-reward ratio
        risk_reward = exit_manager.get_current_risk_reward_ratio(
            entry_price, current_price, position_side
        )
        
        print(f"\nStep {i}: Price: {current_price}")
        print(f"Remaining Position: {remaining_position * 100}%")
        print(f"Stop Loss: {sl_price}, Take Profit: {tp_price}, R:R Ratio: {risk_reward:.2f}")
        
        # Check if we should exit based on stop loss
        if exit_manager.should_exit_position(
            entry_price, current_price, position_side, check_stop_loss=True, 
            check_take_profit=False
        ):
            print("STOP LOSS TRIGGERED - Closing full position")
            remaining_position = 0
            break
            
        # Check if we should exit based on take profit
        if exit_manager.should_exit_position(
            entry_price, current_price, position_side, check_stop_loss=False, 
            check_take_profit=True
        ) and remaining_position > 0:
            # For multi-level take profit, close partial position
            exit_percentage = take_profit.get_quantity_percentage_for_current_level()
            exit_size = min(exit_percentage, remaining_position)
            remaining_position -= exit_size
            
            print(f"TAKE PROFIT TRIGGERED - Closing {exit_size * 100}% of position")
            
            if remaining_position <= 0:
                print("Position fully closed")
                break
    
    # Final position result
    profit_loss = (current_price - entry_price) * position_side_multiplier(position_side)
    profit_loss_pct = profit_loss / entry_price
    
    print("\nTrading Result:")
    print(f"Entry Price: {entry_price}")
    print(f"Exit Price: {current_price}")
    print(f"Profit/Loss: {profit_loss:.2f} ({profit_loss_pct:.2%})")
    print(f"Remaining Position: {remaining_position * 100}%")


def position_side_multiplier(side):
    """Return the multiplier for P&L calculation based on position side"""
    return 1.0 if side == "long" else -1.0


if __name__ == "__main__":
    basic_stop_loss_example()
    combined_stop_loss_example()
    take_profit_example()
    complete_example() 