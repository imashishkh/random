from abc import ABC, abstractmethod


class StopLossStrategy(ABC):
    """
    Abstract base class for stop loss strategies
    """
    
    @abstractmethod
    def calculate_stop_loss_price(self, entry_price, current_price, position_side):
        """
        Calculate the stop loss price based on the strategy
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
            
        Returns:
            float: The stop loss price
        """
        pass
        
    def reset_tracking(self):
        """Reset any tracking data used by the strategy"""
        pass


class FixedStopLoss(StopLossStrategy):
    """
    A stop loss strategy that sets a fixed stop loss percentage from entry
    """
    
    def __init__(self, stop_loss_percentage):
        """
        Initialize the fixed stop loss strategy
        
        Args:
            stop_loss_percentage (float): Stop loss percentage (e.g., 0.02 for 2%)
        """
        self.stop_loss_percentage = stop_loss_percentage
        
    def calculate_stop_loss_price(self, entry_price, current_price, position_side):
        """
        Calculate stop loss price based on a fixed percentage from entry
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price (not used in this strategy)
            position_side (str): Position side ("long" or "short")
            
        Returns:
            float: The calculated stop loss price
        """
        if position_side == "long":
            return entry_price * (1 - self.stop_loss_percentage)
        else:  # short
            return entry_price * (1 + self.stop_loss_percentage)


class TrailingStopLoss(StopLossStrategy):
    """
    A stop loss strategy that trails price to lock in profits
    """
    
    def __init__(self, initial_percentage, trailing_percentage):
        """
        Initialize the trailing stop loss strategy
        
        Args:
            initial_percentage (float): Initial stop distance from entry (e.g., 0.02 for 2%)
            trailing_percentage (float): Trailing distance as price moves favorably (e.g., 0.01 for 1%)
        """
        self.initial_percentage = initial_percentage
        self.trailing_percentage = trailing_percentage
        
        # Tracking variables
        self.highest_price = None
        self.lowest_price = None
        
    def calculate_stop_loss_price(self, entry_price, current_price, position_side):
        """
        Calculate a trailing stop loss price
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
            
        Returns:
            float: The calculated trailing stop loss price
        """
        if position_side == "long":
            # Initial stop loss if no tracking yet
            if self.highest_price is None:
                self.highest_price = max(entry_price, current_price)
                return entry_price * (1 - self.initial_percentage)
                
            # Update highest price if new high reached
            if current_price > self.highest_price:
                self.highest_price = current_price
                
            # Calculate trailing stop based on highest price
            return self.highest_price * (1 - self.trailing_percentage)
            
        else:  # short
            # Initial stop loss if no tracking yet
            if self.lowest_price is None:
                self.lowest_price = min(entry_price, current_price)
                return entry_price * (1 + self.initial_percentage)
                
            # Update lowest price if new low reached
            if current_price < self.lowest_price:
                self.lowest_price = current_price
                
            # Calculate trailing stop based on lowest price
            return self.lowest_price * (1 + self.trailing_percentage)
            
    def reset_tracking(self):
        """Reset tracking of price extremes"""
        self.highest_price = None
        self.lowest_price = None


class ATRStopLoss(StopLossStrategy):
    """
    A stop loss strategy based on Average True Range (ATR) for volatility-based stops
    """
    
    def __init__(self, atr_multiplier, atr_value=None, atr_period=14):
        """
        Initialize the ATR-based stop loss strategy
        
        Args:
            atr_multiplier (float): Multiplier for ATR value (e.g., 2.0 for 2 * ATR)
            atr_value (float, optional): Precalculated ATR value. If None, must be calculated externally.
            atr_period (int, optional): Period for ATR calculation if calculating dynamically
        """
        self.atr_multiplier = atr_multiplier
        self.atr_value = atr_value
        self.atr_period = atr_period
        
    def set_atr_value(self, atr_value):
        """
        Update the ATR value
        
        Args:
            atr_value (float): The new ATR value
        """
        self.atr_value = atr_value
        
    def calculate_stop_loss_price(self, entry_price, current_price, position_side):
        """
        Calculate stop loss price based on ATR
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
            
        Returns:
            float: The calculated ATR-based stop loss price
            
        Raises:
            ValueError: If ATR value is not set
        """
        if self.atr_value is None:
            raise ValueError("ATR value is not set. Call set_atr_value() first.")
            
        atr_distance = self.atr_value * self.atr_multiplier
        
        if position_side == "long":
            return entry_price - atr_distance
        else:  # short
            return entry_price + atr_distance


class BreakEvenStopLoss(StopLossStrategy):
    """
    A stop loss strategy that moves to break-even after a certain profit threshold
    """
    
    def __init__(self, activation_percentage, breakeven_buffer=0.0):
        """
        Initialize the break-even stop loss strategy
        
        Args:
            activation_percentage (float): Profit percentage required to activate break-even (e.g., 0.01 for 1%)
            breakeven_buffer (float, optional): Buffer added to entry price for additional safety (e.g., 0.001 for 0.1%)
        """
        self.activation_percentage = activation_percentage
        self.breakeven_buffer = breakeven_buffer
        
        # Tracking variable to determine if break-even has been triggered
        self.breakeven_triggered = False
        
    def calculate_stop_loss_price(self, entry_price, current_price, position_side):
        """
        Calculate break-even stop loss price after reaching activation threshold
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
            
        Returns:
            float: The calculated break-even stop loss price or None if not activated
        """
        # Calculate profit percentage
        if position_side == "long":
            profit_pct = (current_price - entry_price) / entry_price
            activation_threshold = entry_price * (1 + self.activation_percentage)
            
            # Check if break-even should be activated
            if not self.breakeven_triggered and current_price >= activation_threshold:
                self.breakeven_triggered = True
                
            # Return break-even price if triggered
            if self.breakeven_triggered:
                return entry_price * (1 + self.breakeven_buffer)
            
        else:  # short
            profit_pct = (entry_price - current_price) / entry_price
            activation_threshold = entry_price * (1 - self.activation_percentage)
            
            # Check if break-even should be activated
            if not self.breakeven_triggered and current_price <= activation_threshold:
                self.breakeven_triggered = True
                
            # Return break-even price if triggered
            if self.breakeven_triggered:
                return entry_price * (1 - self.breakeven_buffer)
        
        # If not triggered, return None (use other stop loss strategies)
        return None
        
    def reset_tracking(self):
        """Reset break-even triggering"""
        self.breakeven_triggered = False


class IndicatorBasedStopLoss(StopLossStrategy):
    """
    A stop loss strategy based on technical indicator values (e.g., moving average, Bollinger Band)
    """
    
    def __init__(self, indicator_name, indicator_value_callback=None):
        """
        Initialize the indicator-based stop loss strategy
        
        Args:
            indicator_name (str): Name of the indicator being used
            indicator_value_callback (callable, optional): Callback function to get current indicator value
        """
        self.indicator_name = indicator_name
        self.indicator_value_callback = indicator_value_callback
        self.latest_indicator_value = None
        
    def set_indicator_value(self, value):
        """
        Update the indicator value
        
        Args:
            value (float): The current indicator value
        """
        self.latest_indicator_value = value
        
    def calculate_stop_loss_price(self, entry_price, current_price, position_side):
        """
        Calculate stop loss price based on indicator value
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
            
        Returns:
            float: The indicator-based stop loss price
            
        Raises:
            ValueError: If indicator value is not available
        """
        # Try to get indicator value from callback if available
        if self.indicator_value_callback is not None:
            self.latest_indicator_value = self.indicator_value_callback()
            
        # Check if we have a valid indicator value
        if self.latest_indicator_value is None:
            raise ValueError(f"Indicator value for {self.indicator_name} is not available")
            
        # Use indicator value as stop loss
        return self.latest_indicator_value 


class CombinedStopLoss(StopLossStrategy):
    """
    A strategy that combines multiple stop loss strategies and selects the most conservative one
    """
    
    def __init__(self, strategies):
        """
        Initialize with a list of stop loss strategies
        
        Args:
            strategies (list): List of StopLossStrategy objects
        """
        self.strategies = strategies
        
    def add_strategy(self, strategy):
        """
        Add a new strategy to the combination
        
        Args:
            strategy (StopLossStrategy): Strategy to add
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
            
    def calculate_stop_loss_price(self, entry_price, current_price, position_side):
        """
        Calculate stop loss using all strategies and select the most conservative one
        
        Args:
            entry_price (float): Entry price of the position
            current_price (float): Current market price
            position_side (str): Position side ("long" or "short")
            
        Returns:
            float: The most conservative stop loss price
        """
        prices = []
        
        for strategy in self.strategies:
            try:
                price = strategy.calculate_stop_loss_price(entry_price, current_price, position_side)
                if price is not None:
                    prices.append(price)
            except Exception:
                # Skip strategies that fail
                continue
                
        if not prices:
            return None
            
        # Select most conservative stop loss (closest to current price)
        if position_side == "long":
            # For long positions, the highest stop loss is most conservative
            return max(prices)
        else:
            # For short positions, the lowest stop loss is most conservative
            return min(prices)
            
    def reset_tracking(self):
        """Reset tracking for all strategies"""
        for strategy in self.strategies:
            strategy.reset_tracking() 