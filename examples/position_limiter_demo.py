"""
Position Limiter Demo

This script demonstrates how to use the PositionLimiter class 
in a simulated trading scenario to enforce risk management rules.
"""

import sys
import time
import random
from datetime import datetime

# Add the project root to the path
sys.path.append('/Users/ashish/Projects/Forex Trading v4')

# Import the PositionLimiter class
from src.risk.position_limiter import PositionLimiter


class ActionLogger:
    """Simple logger to display actions and alerts."""
    
    def log_info(self, message):
        """Log informational message."""
        print(f"[INFO] {datetime.now().strftime('%H:%M:%S')} - {message}")
    
    def log_warning(self, message):
        """Log warning message."""
        print(f"[WARNING] {datetime.now().strftime('%H:%M:%S')} - {message}")
    
    def log_error(self, message):
        """Log error message."""
        print(f"[ERROR] {datetime.now().strftime('%H:%M:%S')} - {message}")
    
    def log_limit_violation(self, violation):
        """Log limit violation."""
        print(f"[VIOLATION] {datetime.now().strftime('%H:%M:%S')} - {violation['type']} violated!")
        print(f"  Details: {violation}")


def simulate_trading():
    """Simulate a trading session with position limits."""
    # Create logger
    logger = ActionLogger()
    
    # Create position limiter with custom configuration
    config = {
        'max_position_size': {'BTCUSDT': 1.0, 'ETHUSDT': 2.0, 'LTCUSDT': 5.0},
        'default_max_position_size': 0.5,
        'max_portfolio_exposure': 5.0,
        'max_drawdown_percentage': 10.0,
        'max_daily_loss_percentage': 5.0,
        'max_holding_time': 60,  # 60 seconds for demo purposes
        'enable_alerts': True,
        'alert_threshold': 0.8,
        'enforce_limits': True
    }
    
    limiter = PositionLimiter(logger, config)
    
    # Set initial account equity
    limiter.set_account_equity(10000.0)
    logger.log_info(f"Starting trading session with equity: $10,000")
    
    # Available trading pairs
    symbols = ['BTCUSDT', 'ETHUSDT', 'LTCUSDT', 'ADAUSDT', 'SOLUSDT']
    
    # Simulate trading for 2 minutes
    start_time = time.time()
    positions = []
    
    while time.time() - start_time < 120:
        # Randomly decide to attempt opening a position, closing, or updating equity
        action = random.choice(['open', 'close', 'update_equity', 'check_limits'])
        
        if action == 'open':
            # Try to open a new position
            symbol = random.choice(symbols)
            size = round(random.uniform(0.1, 1.5), 2)
            
            # Check if we can enter this position
            can_enter, violation = limiter.can_enter_position(symbol, size)
            
            if can_enter:
                # Create a new position
                entry_price = 1000 * random.uniform(0.9, 1.1)  # Simulated price
                new_position = {
                    'symbol': symbol,
                    'position_amount': str(size),
                    'entry_price': str(entry_price)
                }
                
                # Add to our positions list
                positions.append(new_position)
                
                # Update the position limiter
                limiter.update_positions(positions)
                
                logger.log_info(f"Opened position: {symbol} - Size: {size}")
            else:
                # Position rejected
                logger.log_info(f"Position rejected: {symbol} - Size: {size}")
                logger.log_info(f"Reason: {violation['type']}")
        
        elif action == 'close' and positions:
            # Close a random position
            position_to_close = random.choice(positions)
            index = positions.index(position_to_close)
            
            # Set position amount to zero to close it
            positions[index] = {
                'symbol': position_to_close['symbol'],
                'position_amount': '0',
                'entry_price': '0'
            }
            
            # Update the position limiter
            limiter.update_positions(positions)
            
            # Clean up positions list by removing closed positions
            positions = [p for p in positions if float(p['position_amount']) > 0]
            
            logger.log_info(f"Closed position: {position_to_close['symbol']}")
        
        elif action == 'update_equity':
            # Simulate equity changes
            change_pct = random.uniform(-3, 3)  # -3% to +3%
            new_equity = limiter.current_equity * (1 + change_pct/100)
            limiter.set_account_equity(new_equity)
            
            logger.log_info(f"Updated equity: ${new_equity:.2f} (change: {change_pct:.2f}%)")
        
        elif action == 'check_limits':
            # Check all limits and get any violations
            limiter._check_holding_time_limits()
            limiter._check_drawdown_limit()
            limiter._check_daily_loss_limit()
            
            # Get and display violations
            violations = limiter.get_violations(clear=True)
            if violations:
                logger.log_info(f"Found {len(violations)} violations")
                
                # If we hit a limit, simulate closing positions
                if positions:
                    symbol_to_close = positions[0]['symbol']
                    logger.log_info(f"Emergency closing position: {symbol_to_close}")
                    positions[0] = {
                        'symbol': positions[0]['symbol'],
                        'position_amount': '0',
                        'entry_price': '0'
                    }
                    # Update limiter
                    limiter.update_positions(positions)
                    # Clean up positions list
                    positions = [p for p in positions if float(p['position_amount']) > 0]
        
        # Get current status
        status = limiter.get_status()
        
        # Display current exposure and positions
        logger.log_info(f"Current exposure: {status['exposure']:.2f}/{config['max_portfolio_exposure']}")
        logger.log_info(f"Active positions: {len(status['positions'])}")
        
        # Wait a bit before the next action
        time.sleep(2)
    
    # End of trading session
    logger.log_info("Trading session completed")
    logger.log_info(f"Final equity: ${limiter.current_equity:.2f}")
    
    # Show summary
    start_equity = limiter.starting_equity
    final_equity = limiter.current_equity
    profit_loss = final_equity - start_equity
    profit_loss_pct = (profit_loss / start_equity) * 100
    
    logger.log_info(f"Session P&L: ${profit_loss:.2f} ({profit_loss_pct:.2f}%)")
    logger.log_info(f"Maximum drawdown: {((limiter.peak_equity - limiter.current_equity) / limiter.peak_equity) * 100:.2f}%")


if __name__ == "__main__":
    print("===== Position Limiter Demo =====")
    print("This demo simulates a trading session with position limits.")
    print("Press Ctrl+C to stop the demo at any time.")
    print("")
    
    try:
        simulate_trading()
    except KeyboardInterrupt:
        print("\nDemo stopped by user")
    except Exception as e:
        print(f"\nError occurred: {e}") 