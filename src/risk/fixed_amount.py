"""
Fixed Amount Position Sizer implementation.

This module provides a position sizer that allocates a fixed amount of capital
for each trade, regardless of market conditions or account equity.
"""

import logging
from typing import Dict, Any, Optional

import pandas as pd

from .base import PositionSizer, PositionSizingResult

logger = logging.getLogger(__name__)


class FixedAmountSizer(PositionSizer):
    """
    Position sizer that allocates a fixed amount of currency for each trade.
    
    This is the simplest position sizing method where a predetermined fixed amount
    of capital is risked on each trade regardless of account size or market conditions.
    """
    
    def __init__(self, 
                 fixed_amount: float = 100.0,
                 max_position_size: Optional[float] = None,
                 **kwargs):
        """
        Initialize the Fixed Amount position sizer.
        
        Args:
            fixed_amount: The fixed amount of account currency to risk per trade
            max_position_size: Optional maximum position size in base currency units
            **kwargs: Additional parameters for future extensibility
        """
        super().__init__(**kwargs)
        self.fixed_amount = fixed_amount
        self.max_position_size = max_position_size
        logger.info(f"Initialized FixedAmountSizer with fixed_amount={fixed_amount}")
        
    def calculate_position_size(self, 
                               equity: float,
                               entry_price: float,
                               stop_loss: Optional[float] = None,
                               take_profit: Optional[float] = None,
                               market_data: Optional[pd.DataFrame] = None,
                               confidence: float = 1.0,
                               **kwargs) -> PositionSizingResult:
        """
        Calculate position size based on a fixed amount of capital.
        
        Args:
            equity: Current account equity
            entry_price: Intended entry price for the position
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            market_data: Optional DataFrame with market data
            confidence: Signal confidence level between 0 and 1
            **kwargs: Additional parameters
            
        Returns:
            PositionSizingResult with position sizing details
        """
        # Calculate base position size (units of the base currency)
        position_size = self.fixed_amount / entry_price
        
        # Apply confidence factor if specified
        if confidence < 1.0:
            position_size *= confidence
            
        # Apply maximum position size limit if specified
        if self.max_position_size is not None and position_size > self.max_position_size:
            position_size = self.max_position_size
            logger.info(f"Position size limited to max: {position_size}")
            
        # Calculate risk metrics
        risk_amount = self.fixed_amount
        risk_percent = (risk_amount / equity) * 100 if equity > 0 else 0
        
        # Calculate stop loss risk if stop loss is provided
        if stop_loss is not None:
            price_risk = abs(entry_price - stop_loss)
            risk_amount = position_size * price_risk
            
        result = PositionSizingResult(
            size=position_size,
            value=position_size * entry_price,
            risk_amount=risk_amount,
            risk_percent=risk_percent,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            margin_required=None,  # Would need to be calculated based on leverage and broker rules
            leverage=1.0,  # Default leverage
            confidence=confidence,
            metadata={
                "sizer_type": "fixed_amount",
                "fixed_amount": self.fixed_amount
            }
        )
        
        # Validate the position size
        return self.validate_position(result, equity, **kwargs)
    
    def validate_position(self, 
                         position: PositionSizingResult, 
                         equity: float,
                         max_risk_percent: float = 2.0, 
                         **kwargs) -> PositionSizingResult:
        """
        Validate and potentially adjust the position based on risk parameters.
        
        Args:
            position: The calculated position sizing result
            equity: Current account equity
            max_risk_percent: Maximum allowable risk as percentage of equity
            **kwargs: Additional parameters
            
        Returns:
            Validated and potentially adjusted position sizing result
        """
        # Validate risk percentage against maximum allowed
        if position["risk_percent"] > max_risk_percent:
            # Adjust position size to meet risk constraints
            adjustment_factor = max_risk_percent / position["risk_percent"]
            position["size"] *= adjustment_factor
            position["value"] *= adjustment_factor
            position["risk_amount"] *= adjustment_factor
            position["risk_percent"] = max_risk_percent
            
            logger.warning(
                f"Position size adjusted to meet max risk percent of {max_risk_percent}%. "
                f"New size: {position['size']:.2f}, Risk: {position['risk_percent']:.2f}%"
            )
            
            # Update metadata to reflect the adjustment
            if "metadata" in position:
                position["metadata"]["adjusted"] = True
                position["metadata"]["adjustment_reason"] = "max_risk_percent"
                
        return position
    
    def update_parameters(self, params: Dict[str, Any]) -> None:
        """
        Update the position sizer parameters.
        
        Args:
            params: Dictionary of parameters to update
        """
        if "fixed_amount" in params:
            self.fixed_amount = params["fixed_amount"]
            logger.info(f"Updated fixed_amount to {self.fixed_amount}")
            
        if "max_position_size" in params:
            self.max_position_size = params["max_position_size"]
            logger.info(f"Updated max_position_size to {self.max_position_size}") 