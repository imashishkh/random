"""
Position sizing implementations for the Forex Trading platform.

This module contains concrete implementations of the PositionSizer 
abstract base class, providing various algorithms for calculating position sizes.
"""

import logging
from typing import Any, Dict, Optional, Union

import numpy as np
import pandas as pd

from .base import PositionSizer, PositionSizingResult, VolatilityCalculator

logger = logging.getLogger(__name__)


class FixedAmountSizer(PositionSizer):
    """
    Position sizer that allocates a fixed amount of capital per trade.
    
    This is the simplest position sizing method, always risking a fixed
    monetary amount regardless of account size or market conditions.
    """
    
    def __init__(
        self, 
        fixed_amount: float = 100.0,
        max_position_size: Optional[float] = None,
        **kwargs
    ):
        """
        Initialize the fixed amount position sizer.
        
        Args:
            fixed_amount: The fixed amount of capital to risk per trade
            max_position_size: Maximum allowable position size
            **kwargs: Additional parameters
        """
        super().__init__(**kwargs)
        self.fixed_amount = fixed_amount
        self.max_position_size = max_position_size
        
    def calculate_position_size(
        self,
        account_equity: float,
        symbol: str,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        market_data: Optional[pd.DataFrame] = None,
        confidence: float = 1.0,
        **kwargs
    ) -> PositionSizingResult:
        """
        Calculate position size based on a fixed amount of capital.
        
        Args:
            account_equity: Current account equity
            symbol: Trading symbol
            entry_price: Planned entry price
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            market_data: Optional market data for additional calculations
            confidence: Signal confidence level between 0.0 and 1.0
            **kwargs: Additional parameters
            
        Returns:
            PositionSizingResult with position sizing information
        """
        logger.debug(f"Calculating position size for {symbol} using fixed amount: {self.fixed_amount}")
        
        # Calculate position size based on fixed amount
        position_value = self.fixed_amount * confidence
        
        # Calculate position size in units based on entry price
        position_size = position_value / entry_price
        
        # Apply maximum position size if specified
        if self.max_position_size is not None and position_size > self.max_position_size:
            position_size = self.max_position_size
            position_value = position_size * entry_price
            logger.warning(f"Position size for {symbol} reduced to maximum: {self.max_position_size}")
        
        # Calculate risk percentage
        risk_percent = (position_value / account_equity) * 100
        
        # Calculate risk amount if stop loss is provided
        risk_amount = 0.0
        if stop_loss is not None:
            if entry_price > stop_loss:  # Long position
                risk_amount = position_size * (entry_price - stop_loss)
            else:  # Short position
                risk_amount = position_size * (stop_loss - entry_price)
        
        return {
            "size": position_size,
            "value": position_value,
            "risk_amount": risk_amount,
            "risk_percent": risk_percent,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "margin_required": position_value,  # Assuming no leverage
            "leverage": 1.0,  # Default leverage
            "confidence": confidence,
            "metadata": {"sizer_type": "fixed_amount"}
        }
    
    def update_parameters(self, **kwargs) -> None:
        """
        Update the position sizer parameters.
        
        Args:
            **kwargs: Parameters to update
        """
        if "fixed_amount" in kwargs:
            self.fixed_amount = float(kwargs["fixed_amount"])
            logger.info(f"Updated fixed amount to {self.fixed_amount}")
            
        if "max_position_size" in kwargs:
            self.max_position_size = float(kwargs["max_position_size"])
            logger.info(f"Updated max position size to {self.max_position_size}")


class FixedPercentSizer(PositionSizer):
    """
    Position sizer that risks a fixed percentage of account equity per trade.
    
    This method scales position sizes relative to the account size, allowing
    positions to grow or shrink with the account balance.
    """
    
    def __init__(
        self, 
        risk_percent: float = 1.0,
        max_risk_percent: float = 2.0,
        max_position_size: Optional[float] = None,
        **kwargs
    ):
        """
        Initialize the fixed percentage position sizer.
        
        Args:
            risk_percent: Percentage of account equity to risk per trade (e.g., 1.0 for 1%)
            max_risk_percent: Maximum allowable risk percentage per trade
            max_position_size: Maximum allowable position size
            **kwargs: Additional parameters
        """
        super().__init__(**kwargs)
        self.risk_percent = risk_percent
        self.max_risk_percent = max_risk_percent
        self.max_position_size = max_position_size
        
    def calculate_position_size(
        self,
        account_equity: float,
        symbol: str,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        market_data: Optional[pd.DataFrame] = None,
        confidence: float = 1.0,
        **kwargs
    ) -> PositionSizingResult:
        """
        Calculate position size based on a fixed percentage of account equity.
        
        Args:
            account_equity: Current account equity
            symbol: Trading symbol
            entry_price: Planned entry price
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            market_data: Optional market data for additional calculations
            confidence: Signal confidence level between 0.0 and 1.0
            **kwargs: Additional parameters
            
        Returns:
            PositionSizingResult with position sizing information
        """
        logger.debug(f"Calculating position size for {symbol} using fixed percentage: {self.risk_percent}%")
        
        # Apply confidence to risk percentage
        adjusted_risk_percent = self.risk_percent * confidence
        
        # Calculate position value based on percentage of account equity
        position_value = (adjusted_risk_percent / 100) * account_equity
        position_size = position_value / entry_price
        
        # Calculate risk amount if stop loss is provided
        risk_amount = 0.0
        if stop_loss is not None:
            price_distance = abs(entry_price - stop_loss)
            
            # If we have a stop loss, calculate position size to risk the specified percentage
            if price_distance > 0:
                position_size = (adjusted_risk_percent / 100) * account_equity / price_distance
                position_value = position_size * entry_price
                
                if entry_price > stop_loss:  # Long position
                    risk_amount = position_size * (entry_price - stop_loss)
                else:  # Short position
                    risk_amount = position_size * (stop_loss - entry_price)
        
        # Apply maximum position size if specified
        if self.max_position_size is not None and position_size > self.max_position_size:
            position_size = self.max_position_size
            position_value = position_size * entry_price
            logger.warning(f"Position size for {symbol} reduced to maximum: {self.max_position_size}")
        
        return {
            "size": position_size,
            "value": position_value,
            "risk_amount": risk_amount,
            "risk_percent": adjusted_risk_percent,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "margin_required": position_value,  # Assuming no leverage
            "leverage": 1.0,  # Default leverage
            "confidence": confidence,
            "metadata": {"sizer_type": "fixed_percent"}
        }
    
    def update_parameters(self, **kwargs) -> None:
        """
        Update the position sizer parameters.
        
        Args:
            **kwargs: Parameters to update
        """
        if "risk_percent" in kwargs:
            self.risk_percent = float(kwargs["risk_percent"])
            logger.info(f"Updated risk percentage to {self.risk_percent}%")
            
        if "max_risk_percent" in kwargs:
            self.max_risk_percent = float(kwargs["max_risk_percent"])
            logger.info(f"Updated max risk percentage to {self.max_risk_percent}%")
            
        if "max_position_size" in kwargs:
            self.max_position_size = float(kwargs["max_position_size"])
            logger.info(f"Updated max position size to {self.max_position_size}")


class KellyCriterionSizer(PositionSizer):
    """
    Position sizer that uses the Kelly Criterion formula to calculate position sizes.
    
    The Kelly Criterion is a formula for bet sizing that maximizes the logarithm
    of wealth over the long term, taking into account win rate and risk/reward ratios.
    """
    
    def __init__(
        self, 
        win_rate: float = 0.55,
        max_kelly_percentage: float = 0.25,  # Kelly limit of 25%
        max_position_size: Optional[float] = None,
        historical_win_rate: Optional[Dict[str, float]] = None,
        **kwargs
    ):
        """
        Initialize the Kelly Criterion position sizer.
        
        Args:
            win_rate: Default win rate if historical data not available
            max_kelly_percentage: Maximum percentage of Kelly to use (conservative approach)
            max_position_size: Maximum allowable position size
            historical_win_rate: Dictionary mapping symbols to their historical win rates
            **kwargs: Additional parameters
        """
        super().__init__(**kwargs)
        self.win_rate = win_rate
        self.max_kelly_percentage = max_kelly_percentage
        self.max_position_size = max_position_size
        self.historical_win_rate = historical_win_rate or {}
        
    def calculate_position_size(
        self,
        account_equity: float,
        symbol: str,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        market_data: Optional[pd.DataFrame] = None,
        confidence: float = 1.0,
        **kwargs
    ) -> PositionSizingResult:
        """
        Calculate position size using the Kelly Criterion formula.
        
        Args:
            account_equity: Current account equity
            symbol: Trading symbol
            entry_price: Planned entry price
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            market_data: Optional market data for additional calculations
            confidence: Signal confidence level between 0.0 and 1.0
            **kwargs: Additional parameters
            
        Returns:
            PositionSizingResult with position sizing information
        """
        logger.debug(f"Calculating position size for {symbol} using Kelly Criterion")
        
        # Determine win rate to use (symbol-specific if available, otherwise default)
        used_win_rate = self.historical_win_rate.get(symbol, self.win_rate)
        
        # We need both stop loss and take profit to calculate risk/reward ratio
        if stop_loss is None or take_profit is None:
            logger.warning(f"Stop loss and take profit required for Kelly Criterion. Using default risk percent.")
            
            # Default to 1% risk if we can't calculate Kelly
            position_value = 0.01 * account_equity * confidence
            position_size = position_value / entry_price
            risk_percent = 1.0 * confidence
            risk_amount = 0.0
            
            if stop_loss is not None:
                if entry_price > stop_loss:  # Long position
                    risk_amount = position_size * (entry_price - stop_loss)
                else:  # Short position
                    risk_amount = position_size * (stop_loss - entry_price)
                    
        else:
            # Calculate risk/reward ratio
            if entry_price > stop_loss:  # Long position
                risk = entry_price - stop_loss
                reward = take_profit - entry_price
            else:  # Short position
                risk = stop_loss - entry_price
                reward = entry_price - take_profit
                
            # Avoid division by zero
            if risk <= 0:
                logger.warning(f"Invalid risk value for Kelly calculation: {risk}")
                risk = 0.01  # default small value to avoid division by zero
                
            reward_risk_ratio = reward / risk
            
            # Calculate Kelly percentage: K% = W - [(1-W)/R]
            # where W is win rate and R is reward/risk ratio
            kelly_percentage = used_win_rate - ((1 - used_win_rate) / reward_risk_ratio)
            
            # Apply max Kelly limit (conservative approach)
            kelly_percentage = min(kelly_percentage, self.max_kelly_percentage)
            
            # Adjust with confidence
            kelly_percentage = kelly_percentage * confidence
            
            # Calculate position value based on Kelly percentage
            position_value = kelly_percentage * account_equity
            position_size = position_value / entry_price
            
            # Calculate risk amount
            if entry_price > stop_loss:  # Long position
                risk_amount = position_size * (entry_price - stop_loss)
            else:  # Short position
                risk_amount = position_size * (stop_loss - entry_price)
                
            # Calculate risk percentage
            risk_percent = (risk_amount / account_equity) * 100
        
        # Apply maximum position size if specified
        if self.max_position_size is not None and position_size > self.max_position_size:
            position_size = self.max_position_size
            position_value = position_size * entry_price
            
            # Recalculate risk amount with new position size
            if stop_loss is not None:
                if entry_price > stop_loss:  # Long position
                    risk_amount = position_size * (entry_price - stop_loss)
                else:  # Short position
                    risk_amount = position_size * (stop_loss - entry_price)
                    
            logger.warning(f"Position size for {symbol} reduced to maximum: {self.max_position_size}")
        
        return {
            "size": position_size,
            "value": position_value,
            "risk_amount": risk_amount,
            "risk_percent": risk_percent,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "margin_required": position_value,  # Assuming no leverage
            "leverage": 1.0,  # Default leverage
            "confidence": confidence,
            "metadata": {
                "sizer_type": "kelly_criterion",
                "win_rate": used_win_rate,
                "reward_risk_ratio": reward_risk_ratio if 'reward_risk_ratio' in locals() else None,
                "kelly_percentage": kelly_percentage if 'kelly_percentage' in locals() else None
            }
        }
    
    def update_parameters(self, **kwargs) -> None:
        """
        Update the position sizer parameters.
        
        Args:
            **kwargs: Parameters to update
        """
        if "win_rate" in kwargs:
            self.win_rate = float(kwargs["win_rate"])
            logger.info(f"Updated default win rate to {self.win_rate}")
            
        if "max_kelly_percentage" in kwargs:
            self.max_kelly_percentage = float(kwargs["max_kelly_percentage"])
            logger.info(f"Updated max Kelly percentage to {self.max_kelly_percentage}")
            
        if "max_position_size" in kwargs:
            self.max_position_size = float(kwargs["max_position_size"])
            logger.info(f"Updated max position size to {self.max_position_size}")
            
        if "historical_win_rate" in kwargs:
            # Update individual win rates, don't replace the entire dictionary
            if isinstance(kwargs["historical_win_rate"], dict):
                self.historical_win_rate.update(kwargs["historical_win_rate"])
                logger.info(f"Updated historical win rates for {len(kwargs['historical_win_rate'])} symbols")


class VolatilityAdjustedSizer(PositionSizer):
    """
    Position sizer that adjusts position size based on market volatility.
    
    This method uses volatility metrics like ATR to adjust position sizes,
    reducing exposure in volatile markets and increasing it in calmer markets.
    """
    
    def __init__(
        self, 
        base_risk_percent: float = 1.0,
        atr_periods: int = 14,
        atr_factor: float = 1.0,
        volatility_multiplier: float = 1.0,
        min_position_size: Optional[float] = None,
        max_position_size: Optional[float] = None,
        **kwargs
    ):
        """
        Initialize the volatility-adjusted position sizer.
        
        Args:
            base_risk_percent: Base percentage of account equity to risk (e.g., 1.0 for 1%)
            atr_periods: Number of periods for ATR calculation
            atr_factor: Factor to multiply ATR by for stop loss calculation
            volatility_multiplier: Factor to adjust position size based on volatility regime
            min_position_size: Minimum allowable position size
            max_position_size: Maximum allowable position size
            **kwargs: Additional parameters
        """
        super().__init__(**kwargs)
        self.base_risk_percent = base_risk_percent
        self.atr_periods = atr_periods
        self.atr_factor = atr_factor
        self.volatility_multiplier = volatility_multiplier
        self.min_position_size = min_position_size
        self.max_position_size = max_position_size
        
    def calculate_position_size(
        self,
        account_equity: float,
        symbol: str,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        market_data: Optional[pd.DataFrame] = None,
        confidence: float = 1.0,
        **kwargs
    ) -> PositionSizingResult:
        """
        Calculate position size adjusting for market volatility.
        
        Args:
            account_equity: Current account equity
            symbol: Trading symbol
            entry_price: Planned entry price
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            market_data: Optional market data for additional calculations
            confidence: Signal confidence level between 0.0 and 1.0
            **kwargs: Additional parameters
            
        Returns:
            PositionSizingResult with position sizing information
        """
        logger.debug(f"Calculating volatility-adjusted position size for {symbol}")
        
        # We need market data to calculate volatility
        if market_data is None or len(market_data) < self.atr_periods:
            logger.warning(f"Insufficient market data for {symbol}. Using base risk percent.")
            
            # Default to base risk percent if we can't calculate volatility
            risk_percent = self.base_risk_percent * confidence
            position_value = (risk_percent / 100) * account_equity
            position_size = position_value / entry_price
            
            # Calculate risk amount if stop loss is provided
            risk_amount = 0.0
            if stop_loss is not None:
                if entry_price > stop_loss:  # Long position
                    risk_amount = position_size * (entry_price - stop_loss)
                else:  # Short position
                    risk_amount = position_size * (stop_loss - entry_price)
                    
        else:
            # Calculate Average True Range (ATR)
            atr = VolatilityCalculator.calculate_atr(market_data, periods=self.atr_periods)
            
            # Calculate volatility regime
            is_high_volatility = VolatilityCalculator.detect_volatility_regime(market_data)
            
            # Adjust volatility multiplier based on regime
            vol_multiplier = self.volatility_multiplier
            if is_high_volatility:
                vol_multiplier *= 0.75  # Reduce position size in high volatility
            else:
                vol_multiplier *= 1.25  # Increase position size in low volatility
                
            # Calculate ATR-based stop loss if not provided
            calculated_stop_loss = stop_loss
            if calculated_stop_loss is None:
                # Determine if it's a long or short position based on take_profit
                if take_profit is not None and take_profit > entry_price:  # Long position
                    calculated_stop_loss = entry_price - (atr * self.atr_factor)
                else:  # Short position or no take_profit
                    calculated_stop_loss = entry_price + (atr * self.atr_factor)
            
            # Calculate risk amount based on ATR
            if calculated_stop_loss is not None:
                price_distance = abs(entry_price - calculated_stop_loss)
                
                # Adjust risk percent with confidence and volatility
                adjusted_risk_percent = self.base_risk_percent * confidence * vol_multiplier
                
                # Calculate position size based on adjusted risk and ATR
                position_size = (adjusted_risk_percent / 100) * account_equity / price_distance
                position_value = position_size * entry_price
                
                # Calculate actual risk amount and percentage
                if entry_price > calculated_stop_loss:  # Long position
                    risk_amount = position_size * (entry_price - calculated_stop_loss)
                else:  # Short position
                    risk_amount = position_size * (calculated_stop_loss - entry_price)
                    
                risk_percent = (risk_amount / account_equity) * 100
            else:
                # Fallback if we couldn't calculate a stop loss
                risk_percent = self.base_risk_percent * confidence * vol_multiplier
                position_value = (risk_percent / 100) * account_equity
                position_size = position_value / entry_price
                risk_amount = 0.0
        
        # Apply position size limits if specified
        if self.min_position_size is not None and position_size < self.min_position_size:
            position_size = self.min_position_size
            position_value = position_size * entry_price
            logger.warning(f"Position size for {symbol} increased to minimum: {self.min_position_size}")
            
        if self.max_position_size is not None and position_size > self.max_position_size:
            position_size = self.max_position_size
            position_value = position_size * entry_price
            logger.warning(f"Position size for {symbol} reduced to maximum: {self.max_position_size}")
            
        # Recalculate risk amount with adjusted position size if stop loss is provided
        if stop_loss is not None:
            if entry_price > stop_loss:  # Long position
                risk_amount = position_size * (entry_price - stop_loss)
            else:  # Short position
                risk_amount = position_size * (stop_loss - entry_price)
                
            # Recalculate risk percentage
            risk_percent = (risk_amount / account_equity) * 100
        
        return {
            "size": position_size,
            "value": position_value,
            "risk_amount": risk_amount,
            "risk_percent": risk_percent,
            "entry_price": entry_price,
            "stop_loss": stop_loss if stop_loss is not None else (calculated_stop_loss if 'calculated_stop_loss' in locals() else None),
            "take_profit": take_profit,
            "margin_required": position_value,  # Assuming no leverage
            "leverage": 1.0,  # Default leverage
            "confidence": confidence,
            "metadata": {
                "sizer_type": "volatility_adjusted",
                "atr": atr if 'atr' in locals() else None,
                "is_high_volatility": is_high_volatility if 'is_high_volatility' in locals() else None,
                "vol_multiplier": vol_multiplier if 'vol_multiplier' in locals() else None
            }
        }
    
    def update_parameters(self, **kwargs) -> None:
        """
        Update the position sizer parameters.
        
        Args:
            **kwargs: Parameters to update
        """
        if "base_risk_percent" in kwargs:
            self.base_risk_percent = float(kwargs["base_risk_percent"])
            logger.info(f"Updated base risk percentage to {self.base_risk_percent}%")
            
        if "atr_periods" in kwargs:
            self.atr_periods = int(kwargs["atr_periods"])
            logger.info(f"Updated ATR periods to {self.atr_periods}")
            
        if "atr_factor" in kwargs:
            self.atr_factor = float(kwargs["atr_factor"])
            logger.info(f"Updated ATR factor to {self.atr_factor}")
            
        if "volatility_multiplier" in kwargs:
            self.volatility_multiplier = float(kwargs["volatility_multiplier"])
            logger.info(f"Updated volatility multiplier to {self.volatility_multiplier}")
            
        if "min_position_size" in kwargs:
            self.min_position_size = float(kwargs["min_position_size"])
            logger.info(f"Updated min position size to {self.min_position_size}")
            
        if "max_position_size" in kwargs:
            self.max_position_size = float(kwargs["max_position_size"])
            logger.info(f"Updated max position size to {self.max_position_size}") 