"""
Position Sizer Module

This module implements position sizing algorithms for trading systems.
It calculates optimal position sizes based on risk parameters.
"""

import logging


class PositionSizer:
    """
    Position sizing utility for calculating appropriate position sizes based on risk parameters.
    
    This class provides methods to:
    - Calculate position size based on account risk percentage
    - Calculate position size based on fixed lot size
    - Calculate position size based on volatility (ATR)
    - Apply position limits based on risk controls
    """
    
    def __init__(self, account_size=10000, default_risk_pct=2.0, max_risk_pct=5.0, 
                 min_position_size=0.01, max_position_size=10.0, 
                 position_limiter=None):
        """
        Initialize the position sizer with default parameters.
        
        Args:
            account_size (float): Account size/equity in base currency
            default_risk_pct (float): Default risk percentage per trade
            max_risk_pct (float): Maximum allowable risk percentage per trade
            min_position_size (float): Minimum position size in lots
            max_position_size (float): Maximum position size in lots
            position_limiter (PositionLimiter, optional): Position limiter instance for additional constraints
        """
        self.account_size = account_size
        self.default_risk_pct = default_risk_pct
        self.max_risk_pct = max_risk_pct
        self.min_position_size = min_position_size
        self.max_position_size = max_position_size
        self.position_limiter = position_limiter
        self.logger = logging.getLogger(__name__)
    
    def update_account_size(self, account_size):
        """
        Update the account size/equity.
        
        Args:
            account_size (float): New account size
        """
        self.account_size = account_size
        if self.position_limiter:
            self.position_limiter.set_account_equity(account_size)
    
    def size_by_risk(self, symbol, entry_price, stop_price, risk_pct=None, pip_value=10, 
                     additional_constraints=None):
        """
        Calculate position size based on risk percentage.
        
        Args:
            symbol (str): Symbol to trade
            entry_price (float): Entry price
            stop_price (float): Stop loss price
            risk_pct (float, optional): Risk percentage, defaults to self.default_risk_pct
            pip_value (float): Value of one pip in account currency
            additional_constraints (dict, optional): Additional constraints to consider
            
        Returns:
            float: Position size in lots
            dict: Additional information about the calculation
        """
        if risk_pct is None:
            risk_pct = self.default_risk_pct
        
        # Enforce maximum risk percentage
        risk_pct = min(risk_pct, self.max_risk_pct)
        
        # Calculate dollar risk
        dollar_risk = self.account_size * (risk_pct / 100)
        
        # Calculate pip risk
        pip_risk = abs(entry_price - stop_price) * 10000  # Convert to pips
        
        # Calculate position size
        if pip_risk == 0:
            self.logger.warning(f"Zero pip risk for {symbol}. Using minimum position size.")
            position_size = self.min_position_size
        else:
            # Convert to standard lots
            position_size = dollar_risk / (pip_risk * pip_value)
        
        # Enforce min/max position size
        position_size = max(min(position_size, self.max_position_size), self.min_position_size)
        
        # Apply additional position limits if position_limiter is available
        if self.position_limiter:
            # Check if entering this position would violate any limits
            can_enter = self.position_limiter.can_enter_position(symbol, position_size)
            if not can_enter:
                self.logger.warning(f"Position size limited due to risk controls for {symbol}")
                # Get max allowed position size from the limiter
                max_allowed = self.position_limiter.get_max_allowed_position_size(symbol)
                if max_allowed is not None:
                    position_size = min(position_size, max_allowed)
        
        return position_size, {
            'account_size': self.account_size,
            'risk_pct': risk_pct,
            'dollar_risk': dollar_risk,
            'pip_risk': pip_risk,
            'original_position_size': position_size,
            'final_position_size': position_size
        }
    
    def size_by_fixed_lot(self, symbol, lot_size=None):
        """
        Calculate position size based on fixed lot size.
        
        Args:
            symbol (str): Symbol to trade
            lot_size (float, optional): Fixed lot size, defaults to self.min_position_size
            
        Returns:
            float: Position size in lots
            dict: Additional information about the calculation
        """
        if lot_size is None:
            lot_size = self.min_position_size
        
        # Enforce min/max position size
        position_size = max(min(lot_size, self.max_position_size), self.min_position_size)
        
        # Apply additional position limits if position_limiter is available
        if self.position_limiter:
            can_enter = self.position_limiter.can_enter_position(symbol, position_size)
            if not can_enter:
                self.logger.warning(f"Fixed lot size limited due to risk controls for {symbol}")
                max_allowed = self.position_limiter.get_max_allowed_position_size(symbol)
                if max_allowed is not None:
                    position_size = min(position_size, max_allowed)
        
        return position_size, {
            'account_size': self.account_size,
            'original_lot_size': lot_size,
            'final_position_size': position_size
        }
    
    def size_by_volatility(self, symbol, atr, risk_factor=1.0, risk_pct=None, pip_value=10):
        """
        Calculate position size based on volatility (ATR).
        
        Args:
            symbol (str): Symbol to trade
            atr (float): Average True Range value
            risk_factor (float): Risk factor to multiply ATR by
            risk_pct (float, optional): Risk percentage, defaults to self.default_risk_pct
            pip_value (float): Value of one pip in account currency
            
        Returns:
            float: Position size in lots
            dict: Additional information about the calculation
        """
        if risk_pct is None:
            risk_pct = self.default_risk_pct
        
        # Enforce maximum risk percentage
        risk_pct = min(risk_pct, self.max_risk_pct)
        
        # Calculate dollar risk
        dollar_risk = self.account_size * (risk_pct / 100)
        
        # Calculate pip risk using ATR
        pip_risk = atr * risk_factor * 10000  # Convert to pips
        
        # Calculate position size
        if pip_risk == 0:
            self.logger.warning(f"Zero ATR pip risk for {symbol}. Using minimum position size.")
            position_size = self.min_position_size
        else:
            # Convert to standard lots
            position_size = dollar_risk / (pip_risk * pip_value)
        
        # Enforce min/max position size
        position_size = max(min(position_size, self.max_position_size), self.min_position_size)
        
        # Apply additional position limits if position_limiter is available
        if self.position_limiter:
            can_enter = self.position_limiter.can_enter_position(symbol, position_size)
            if not can_enter:
                self.logger.warning(f"Volatility-based position size limited due to risk controls for {symbol}")
                max_allowed = self.position_limiter.get_max_allowed_position_size(symbol)
                if max_allowed is not None:
                    position_size = min(position_size, max_allowed)
        
        return position_size, {
            'account_size': self.account_size,
            'risk_pct': risk_pct,
            'dollar_risk': dollar_risk,
            'atr': atr,
            'risk_factor': risk_factor,
            'pip_risk': pip_risk,
            'original_position_size': position_size,
            'final_position_size': position_size
        }
    
    def get_max_allowed_position_size(self, symbol):
        """
        Get maximum allowed position size for a symbol based on risk controls.
        
        Args:
            symbol (str): Symbol to check
            
        Returns:
            float: Maximum allowed position size, or None if no limits apply
        """
        if self.position_limiter:
            return self.position_limiter.get_max_allowed_position_size(symbol)
        return self.max_position_size 