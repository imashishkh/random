"""
Risk management functionality.

This module provides functions for risk management and assessment,
including risk calculations, exposure monitoring, and risk metrics.
"""
import logging
import math
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime, timedelta

from .models import Position, PositionSide, RiskMetrics

# Configure logger
logger = logging.getLogger(__name__)


class RiskManager:
    """Risk manager for assessing and managing trading risk."""
    
    def __init__(self, max_risk_per_trade: float = 2.0, max_total_risk: float = 10.0):
        """
        Initialize the risk manager.
        
        Args:
            max_risk_per_trade: Maximum risk percentage per trade (default: 2%)
            max_total_risk: Maximum total risk percentage (default: 10%)
        """
        self.max_risk_per_trade = max_risk_per_trade
        self.max_total_risk = max_total_risk
        
        logger.info(f"Initialized risk manager with max risk per trade: {max_risk_per_trade}%, max total risk: {max_total_risk}%")
    
    def calculate_position_risk(self, position: Position, account_value: float,
                              current_price: Optional[float] = None) -> float:
        """
        Calculate the risk of a position as a percentage of account value.
        
        Args:
            position: Position to assess
            account_value: Total account value
            current_price: Current market price (if None, uses entry price)
            
        Returns:
            Risk percentage (0-100)
        """
        try:
            if position.status == PositionStatus.CLOSED or position.amount <= 0 or account_value <= 0:
                return 0.0
            
            # If stop loss is set, calculate risk based on distance to stop loss
            if position.stop_loss:
                price_risk = abs(position.entry_price - position.stop_loss)
                position_value = position.amount * position.entry_price
                
                # Risk amount = position size * price risk
                risk_amount = position_value * (price_risk / position.entry_price)
                
                # For leveraged positions, multiply by leverage
                if position.leverage > 1.0:
                    risk_amount *= position.leverage
                
                # Risk percentage = (risk amount / account value) * 100
                risk_percent = (risk_amount / account_value) * 100
                
                return risk_percent
            
            # If no stop loss, use a default risk based on position size
            position_value = position.amount * position.entry_price
            
            # For leveraged positions, calculate based on margin
            if position.leverage > 1.0:
                position_margin = position_value / position.leverage
                # Assume potential loss of entire margin
                risk_percent = (position_margin / account_value) * 100
            else:
                # Assume a default risk of 5% of position value
                risk_amount = position_value * 0.05
                risk_percent = (risk_amount / account_value) * 100
            
            return risk_percent
        
        except Exception as e:
            logger.error(f"Error calculating position risk: {str(e)}")
            raise
    
    def calculate_total_risk(self, positions: List[Position], account_value: float) -> float:
        """
        Calculate the total risk across all positions.
        
        Args:
            positions: List of positions
            account_value: Total account value
            
        Returns:
            Total risk percentage (0-100)
        """
        try:
            if not positions or account_value <= 0:
                return 0.0
            
            # Sum individual position risks
            total_risk = sum(self.calculate_position_risk(position, account_value) 
                          for position in positions 
                          if position.status != PositionStatus.CLOSED)
            
            # Add correlation factor (simplified)
            # In reality, this would be more complex, considering correlations between assets
            # This is a very simple approximation that reduces risk slightly due to diversification
            num_open_positions = sum(1 for p in positions if p.status != PositionStatus.CLOSED)
            if num_open_positions > 1:
                # Apply a simple diversification discount
                diversification_factor = math.sqrt(num_open_positions) / num_open_positions
                total_risk *= diversification_factor
            
            return total_risk
        
        except Exception as e:
            logger.error(f"Error calculating total risk: {str(e)}")
            raise
    
    def is_trade_within_risk_limits(self, potential_risk: float, current_total_risk: float) -> bool:
        """
        Check if a potential trade is within risk limits.
        
        Args:
            potential_risk: Risk percentage of the potential trade
            current_total_risk: Current total risk percentage
            
        Returns:
            True if within limits, False otherwise
        """
        # Check individual trade risk limit
        if potential_risk > self.max_risk_per_trade:
            logger.warning(f"Trade exceeds max risk per trade: {potential_risk}% > {self.max_risk_per_trade}%")
            return False
        
        # Check total risk limit
        if potential_risk + current_total_risk > self.max_total_risk:
            logger.warning(f"Trade would exceed max total risk: {potential_risk + current_total_risk}% > {self.max_total_risk}%")
            return False
        
        return True
    
    def calculate_max_position_size(self, account_value: float, entry_price: float, 
                                  stop_loss: float, leverage: float = 1.0) -> float:
        """
        Calculate maximum position size based on risk limits.
        
        Args:
            account_value: Total account value
            entry_price: Planned entry price
            stop_loss: Planned stop loss price
            leverage: Leverage multiplier
            
        Returns:
            Maximum position size
        """
        try:
            if entry_price <= 0 or stop_loss <= 0 or account_value <= 0:
                raise ValueError("Entry price, stop loss, and account value must be positive")
            
            # Calculate risk per trade in currency
            max_risk_amount = account_value * (self.max_risk_per_trade / 100)
            
            # Calculate price difference to stop loss
            price_diff = abs(entry_price - stop_loss)
            
            if price_diff == 0:
                raise ValueError("Entry price and stop loss cannot be the same")
            
            # Calculate position size that would risk the maximum allowed
            max_size_in_base = max_risk_amount / price_diff
            
            # Convert to asset amount
            max_position_size = max_size_in_base / entry_price
            
            # Adjust for leverage if applicable
            if leverage > 1.0:
                # With leverage, we can take a larger position with the same risk
                # However, this assumes the stop loss is placed correctly
                max_position_size = max_position_size * leverage
            
            logger.info(f"Calculated max position size: {max_position_size} at entry: {entry_price}, stop: {stop_loss}")
            return max_position_size
        
        except Exception as e:
            logger.error(f"Error calculating max position size: {str(e)}")
            raise
    
    def calculate_drawdown(self, 
                         starting_balance: float, 
                         current_balance: float) -> Tuple[float, float]:
        """
        Calculate drawdown metrics.
        
        Args:
            starting_balance: Initial account balance
            current_balance: Current account balance
            
        Returns:
            Tuple of (drawdown_percentage, drawdown_amount)
        """
        try:
            if starting_balance <= 0:
                raise ValueError("Starting balance must be positive")
            
            # Calculate drawdown amount
            drawdown_amount = starting_balance - current_balance
            
            # Calculate drawdown percentage
            drawdown_percent = (drawdown_amount / starting_balance) * 100
            
            # If current balance is higher than starting, no drawdown
            if drawdown_percent < 0:
                drawdown_percent = 0
                drawdown_amount = 0
            
            return drawdown_percent, drawdown_amount
        
        except Exception as e:
            logger.error(f"Error calculating drawdown: {str(e)}")
            raise
    
    def calculate_margin_level(self, account_value: float, used_margin: float) -> float:
        """
        Calculate margin level.
        
        Args:
            account_value: Total account value
            used_margin: Margin currently in use
            
        Returns:
            Margin level percentage
        """
        try:
            if account_value <= 0:
                raise ValueError("Account value must be positive")
            
            # If no margin used, return 100% margin level
            if used_margin <= 0:
                return 100.0
            
            # Calculate margin level
            margin_level = (account_value / used_margin) * 100
            
            return margin_level
        
        except Exception as e:
            logger.error(f"Error calculating margin level: {str(e)}")
            raise
    
    def is_margin_call(self, margin_level: float, margin_call_level: float = 80.0) -> bool:
        """
        Check if margin level is at margin call level.
        
        Args:
            margin_level: Current margin level percentage
            margin_call_level: Margin call threshold percentage
            
        Returns:
            True if margin call, False otherwise
        """
        return margin_level <= margin_call_level
    
    def is_liquidation(self, margin_level: float, liquidation_level: float = 50.0) -> bool:
        """
        Check if margin level is at liquidation level.
        
        Args:
            margin_level: Current margin level percentage
            liquidation_level: Liquidation threshold percentage
            
        Returns:
            True if liquidation, False otherwise
        """
        return margin_level <= liquidation_level 