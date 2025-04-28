from .stop_loss_strategies import StopLossStrategy
from .take_profit_strategies import TakeProfitStrategy


class ExitManager:
    """
    Manages exit strategies for trading positions.
    
    Combines stop loss and take profit strategies to determine when to exit positions.
    """
    
    def __init__(self, stop_loss_strategy, take_profit_strategy=None):
        """
        Initialize the exit manager
        
        Args:
            stop_loss_strategy (StopLossStrategy): The stop loss strategy to use
            take_profit_strategy (TakeProfitStrategy, optional): The take profit strategy to use
        """
        self.stop_loss_strategy = stop_loss_strategy
        self.take_profit_strategy = take_profit_strategy
        
    def set_stop_loss_strategy(self, stop_loss_strategy):
        """
        Set or update the stop loss strategy
        
        Args:
            stop_loss_strategy (StopLossStrategy): The new stop loss strategy
        """
        self.stop_loss_strategy = stop_loss_strategy
        
    def set_take_profit_strategy(self, take_profit_strategy):
        """
        Set or update the take profit strategy
        
        Args:
            take_profit_strategy (TakeProfitStrategy): The new take profit strategy
        """
        self.take_profit_strategy = take_profit_strategy
        
    def calculate_exit_prices(self, entry_price, current_price, position_side):
        """
        Calculate both stop loss and take profit prices
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
            
        Returns:
            dict: A dictionary with 'stop_loss' and 'take_profit' prices
        """
        stop_loss = self.stop_loss_strategy.calculate_stop_loss_price(
            entry_price, current_price, position_side
        )
        
        take_profit = None
        if self.take_profit_strategy:
            take_profit = self.take_profit_strategy.calculate_take_profit_price(
                entry_price, current_price, position_side
            )
            
        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit
        }
    
    def should_exit_position(self, entry_price, current_price, position_side):
        """
        Determine if a position should be exited based on current price and strategies
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
            
        Returns:
            tuple: (bool, str) - Whether to exit and the reason ('stop_loss', 'take_profit', or None)
        """
        exit_prices = self.calculate_exit_prices(entry_price, current_price, position_side)
        
        # Check if stop loss is triggered
        if position_side == "long" and current_price <= exit_prices['stop_loss']:
            return True, 'stop_loss'
        elif position_side == "short" and current_price >= exit_prices['stop_loss']:
            return True, 'stop_loss'
            
        # Check if take profit is triggered (if a take profit strategy exists)
        if self.take_profit_strategy and exit_prices['take_profit']:
            if position_side == "long" and current_price >= exit_prices['take_profit']:
                return True, 'take_profit'
            elif position_side == "short" and current_price <= exit_prices['take_profit']:
                return True, 'take_profit'
                
        # No exit condition met
        return False, None
    
    def reset_tracking(self):
        """Reset all tracking in the strategies"""
        self.stop_loss_strategy.reset_tracking()
        if self.take_profit_strategy:
            self.take_profit_strategy.reset_tracking()
            
    def get_current_risk_reward_ratio(self, entry_price, current_price, position_side):
        """
        Calculate the current risk-to-reward ratio based on stop loss and take profit
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
            
        Returns:
            float or None: The risk-reward ratio or None if take profit is not set
        """
        if not self.take_profit_strategy:
            return None
            
        exit_prices = self.calculate_exit_prices(entry_price, current_price, position_side)
        
        # If either stop loss or take profit is None, can't calculate ratio
        if exit_prices['stop_loss'] is None or exit_prices['take_profit'] is None:
            return None
            
        # Calculate potential loss and gain
        if position_side == "long":
            potential_loss = entry_price - exit_prices['stop_loss']
            potential_gain = exit_prices['take_profit'] - entry_price
        else:  # short
            potential_loss = exit_prices['stop_loss'] - entry_price
            potential_gain = entry_price - exit_prices['take_profit']
            
        # Prevent division by zero
        if potential_loss == 0:
            return None
            
        # Return the ratio
        return potential_gain / potential_loss 