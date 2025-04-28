"""
Fixed Percentage Position Sizer implementation.

This module provides a position sizer that allocates a fixed percentage of account
equity for each trade, adjusting position size as account equity changes.
"""

import logging
from typing import Dict, Any, Optional

import pandas as pd

from .base import PositionSizer, PositionSizingResult

logger = logging.getLogger(__name__)


class FixedPercentSizer(PositionSizer):
    """
    Position sizer that allocates a fixed percentage of account equity for each trade.
    
    This method adjusts position sizes automatically as account equity changes, which
    helps in capital preservation during drawdowns and compounds gains during profitable periods.
    """
    
    def __init__(self, 
                 risk_percent: float = 1.0,
                 max_position_size: Optional[float] = None,
                 **kwargs):
        """
        Initialize the Fixed Percentage position sizer.
        
        Args:
            risk_percent: The percentage of account equity to risk per trade (e.g., 1.0 for 1%)
            max_position_size: Optional maximum position size in base currency units
            **kwargs: Additional parameters for future extensibility
        """
        super().__init__(**kwargs)
        self.risk_percent = risk_percent
        self.max_position_size = max_position_size
        logger.info(f"Initialized FixedPercentSizer with risk_percent={risk_percent}%")
        
    def calculate_position_size(self, 
                               equity: float,
                               entry_price: float,
                               stop_loss: Optional[float] = None,
                               take_profit: Optional[float] = None,
                               market_data: Optional[pd.DataFrame] = None,
                               confidence: float = 1.0,
                               **kwargs) -> PositionSizingResult:
        """
        Calculate position size based on a fixed percentage of account equity.
        
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
        # Calculate the risk amount based on equity and risk percentage
        risk_amount = equity * (self.risk_percent / 100)
        
        # Apply confidence factor if specified
        if confidence < 1.0:
            risk_amount *= confidence
        
        # Calculate position size based on risk amount
        if stop_loss is not None and stop_loss != entry_price:
            # Calculate position size based on stop loss
            price_risk = abs(entry_price - stop_loss)
            position_size = risk_amount / price_risk
        else:
            # If no stop loss, use a percentage of equity divided by price
            position_size = risk_amount / entry_price
            
        # Apply maximum position size limit if specified
        if self.max_position_size is not None and position_size > self.max_position_size:
            position_size = self.max_position_size
            logger.info(f"Position size limited to max: {position_size}")
            
        # Recalculate risk amount and percentage based on the final position size
        if stop_loss is not None:
            actual_risk_amount = position_size * abs(entry_price - stop_loss)
        else:
            actual_risk_amount = position_size * entry_price
            
        risk_percent = (actual_risk_amount / equity) * 100 if equity > 0 else 0
        
        result = PositionSizingResult(
            size=position_size,
            value=position_size * entry_price,
            risk_amount=actual_risk_amount,
            risk_percent=risk_percent,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            margin_required=None,  # Would need to be calculated based on leverage and broker rules
            leverage=1.0,  # Default leverage
            confidence=confidence,
            metadata={
                "sizer_type": "fixed_percent",
                "risk_percent": self.risk_percent
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
        if "risk_percent" in params:
            self.risk_percent = params["risk_percent"]
            logger.info(f"Updated risk_percent to {self.risk_percent}%")
            
        if "max_position_size" in params:
            self.max_position_size = params["max_position_size"]
            logger.info(f"Updated max_position_size to {self.max_position_size}") 