from abc import ABC, abstractmethod


class TakeProfitStrategy(ABC):
    """
    Abstract base class for take profit strategies
    """
    
    @abstractmethod
    def calculate_take_profit_price(self, entry_price, current_price, position_side):
        """
        Calculate the take profit price based on the strategy
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
            
        Returns:
            float: The take profit price
        """
        pass
        
    def reset_tracking(self):
        """Reset any tracking data used by the strategy"""
        pass


class FixedTakeProfit(TakeProfitStrategy):
    """
    A take profit strategy based on a fixed profit percentage
    """
    
    def __init__(self, profit_percentage):
        """
        Initialize the fixed take profit strategy
        
        Args:
            profit_percentage (float): Target profit percentage (e.g., 0.05 for 5%)
        """
        self.profit_percentage = profit_percentage
        
    def calculate_take_profit_price(self, entry_price, current_price, position_side):
        """
        Calculate a take profit price based on a fixed percentage from entry
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price (not used in this strategy)
            position_side (str): Position side ("long" or "short")
            
        Returns:
            float: The calculated take profit price
        """
        if position_side == "long":
            return entry_price * (1 + self.profit_percentage)
        else:  # short
            return entry_price * (1 - self.profit_percentage)


class MultiLevelTakeProfit(TakeProfitStrategy):
    """
    A take profit strategy that offers multiple profit targets
    """
    
    def __init__(self, profit_levels, quantity_percentages=None):
        """
        Initialize the multi-level take profit strategy
        
        Args:
            profit_levels (list): List of profit percentages (e.g., [0.03, 0.05, 0.08])
            quantity_percentages (list, optional): List of percentages of position to close 
                                                 at each level (must sum to 1.0)
        """
        self.profit_levels = sorted(profit_levels)
        
        # If quantity percentages not provided, distribute evenly
        if quantity_percentages is None:
            self.quantity_percentages = [1.0 / len(profit_levels)] * len(profit_levels)
        else:
            # Validate that percentages sum to 1.0
            if sum(quantity_percentages) != 1.0:
                raise ValueError("Quantity percentages must sum to 1.0")
            if len(quantity_percentages) != len(profit_levels):
                raise ValueError("Number of quantity percentages must match number of profit levels")
                
            self.quantity_percentages = quantity_percentages
            
        # Track which levels have been reached
        self.reached_levels = [False] * len(self.profit_levels)
        # Track current target level
        self.current_target_index = 0
        
    def calculate_take_profit_price(self, entry_price, current_price, position_side):
        """
        Calculate the next take profit price based on multi-level strategy
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
            
        Returns:
            float: The next take profit price target
        """
        # Update which levels have been reached
        self._update_reached_levels(entry_price, current_price, position_side)
        
        # If all levels reached, no more take profit
        if all(self.reached_levels):
            return None
            
        # Find the next unreached level
        for i, reached in enumerate(self.reached_levels):
            if not reached:
                self.current_target_index = i
                break
                
        # Calculate the price for the current target
        if position_side == "long":
            return entry_price * (1 + self.profit_levels[self.current_target_index])
        else:  # short
            return entry_price * (1 - self.profit_levels[self.current_target_index])
    
    def _update_reached_levels(self, entry_price, current_price, position_side):
        """
        Update which profit levels have been reached
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
        """
        for i, profit_level in enumerate(self.profit_levels):
            take_profit_price = (
                entry_price * (1 + profit_level) if position_side == "long" 
                else entry_price * (1 - profit_level)
            )
            
            # Check if level has been reached
            if (position_side == "long" and current_price >= take_profit_price) or \
               (position_side == "short" and current_price <= take_profit_price):
                self.reached_levels[i] = True
                
    def get_quantity_percentage_for_current_level(self):
        """
        Get the percentage of the position that should be closed at the current level
        
        Returns:
            float: Percentage of position to close (0.0 to 1.0)
        """
        return self.quantity_percentages[self.current_target_index]
        
    def reset_tracking(self):
        """Reset tracked profit levels"""
        self.reached_levels = [False] * len(self.profit_levels)
        self.current_target_index = 0


class TrailingTakeProfit(TakeProfitStrategy):
    """
    A take profit strategy that trails the price movement to maximize profit
    """
    
    def __init__(self, activation_percentage, trailing_percentage):
        """
        Initialize the trailing take profit strategy
        
        Args:
            activation_percentage (float): Percentage gain to activate trailing (e.g., 0.03 for 3%)
            trailing_percentage (float): Percentage to trail behind price (e.g., 0.01 for 1%)
        """
        self.activation_percentage = activation_percentage
        self.trailing_percentage = trailing_percentage
        
        # Tracking variables
        self.is_activated = False
        self.highest_price = None
        self.lowest_price = None
        
    def calculate_take_profit_price(self, entry_price, current_price, position_side):
        """
        Calculate a trailing take profit price
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
            
        Returns:
            float: The calculated trailing take profit price
        """
        # Check if trailing is activated
        if not self.is_activated:
            # Calculate activation thresholds
            if position_side == "long":
                activation_price = entry_price * (1 + self.activation_percentage)
                if current_price >= activation_price:
                    self.is_activated = True
                    self.highest_price = current_price
                else:
                    # Not activated yet, return the activation threshold
                    return activation_price
            else:  # short
                activation_price = entry_price * (1 - self.activation_percentage)
                if current_price <= activation_price:
                    self.is_activated = True
                    self.lowest_price = current_price
                else:
                    # Not activated yet, return the activation threshold
                    return activation_price
        
        # If trailing is activated, update tracking
        if self.is_activated:
            if position_side == "long":
                # Update highest price
                if self.highest_price is None or current_price > self.highest_price:
                    self.highest_price = current_price
                # Calculate trailing take profit
                return self.highest_price * (1 - self.trailing_percentage)
            else:  # short
                # Update lowest price
                if self.lowest_price is None or current_price < self.lowest_price:
                    self.lowest_price = current_price
                # Calculate trailing take profit
                return self.lowest_price * (1 + self.trailing_percentage)
        
    def reset_tracking(self):
        """Reset trailing take profit tracking"""
        self.is_activated = False
        self.highest_price = None
        self.lowest_price = None


class RiskRewardTakeProfit(TakeProfitStrategy):
    """
    A take profit strategy based on a specified risk-reward ratio
    """
    
    def __init__(self, risk_reward_ratio, stop_loss_strategy):
        """
        Initialize the risk-reward take profit strategy
        
        Args:
            risk_reward_ratio (float): The target risk-reward ratio (e.g., 2.0)
            stop_loss_strategy: The stop loss strategy used to calculate risk
        """
        self.risk_reward_ratio = risk_reward_ratio
        self.stop_loss_strategy = stop_loss_strategy
        
    def calculate_take_profit_price(self, entry_price, current_price, position_side):
        """
        Calculate take profit price based on risk-reward ratio
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
            
        Returns:
            float: The calculated take profit price
        """
        # Get stop loss price to calculate risk
        stop_loss_price = self.stop_loss_strategy.calculate_stop_loss_price(
            entry_price, current_price, position_side
        )
        
        # If no stop loss, can't calculate take profit
        if stop_loss_price is None:
            return None
            
        # Calculate risk in price
        if position_side == "long":
            risk = entry_price - stop_loss_price
            # Calculate take profit based on risk and target ratio
            return entry_price + (risk * self.risk_reward_ratio)
        else:  # short
            risk = stop_loss_price - entry_price
            # Calculate take profit based on risk and target ratio
            return entry_price - (risk * self.risk_reward_ratio)


class CombinedTakeProfit(TakeProfitStrategy):
    """
    A strategy that combines multiple take profit strategies and selects the most conservative one
    """
    
    def __init__(self, strategies):
        """
        Initialize with a list of take profit strategies
        
        Args:
            strategies (list): List of TakeProfitStrategy objects
        """
        self.strategies = strategies
        
    def add_strategy(self, strategy):
        """
        Add a new strategy to the combination
        
        Args:
            strategy (TakeProfitStrategy): Strategy to add
        """
        self.strategies.append(strategy)
        
    def remove_strategy(self, strategy_index):
        """
        Remove a strategy from the combination
        
        Args:
            strategy_index (int): Index of the strategy to remove
        """
        if 0 <= strategy_index < len(self.strategies):
            self.strategies.pop(strategy_index)
            
    def calculate_take_profit_price(self, entry_price, current_price, position_side):
        """
        Calculate take profit using all strategies and select the most conservative one
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
            
        Returns:
            float: The most conservative take profit price
        """
        prices = []
        
        for strategy in self.strategies:
            try:
                price = strategy.calculate_take_profit_price(entry_price, current_price, position_side)
                if price is not None:
                    prices.append(price)
            except Exception:
                # Skip strategies that fail
                continue
                
        if not prices:
            return None
            
        # Select most conservative take profit (closest to current price)
        if position_side == "long":
            # For long positions, the lowest take profit is most conservative
            return min(prices)
        else:
            # For short positions, the highest take profit is most conservative
            return max(prices)
            
    def reset_tracking(self):
        """Reset tracking for all strategies"""
        for strategy in self.strategies:
            strategy.reset_tracking() 