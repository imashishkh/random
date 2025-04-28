"""
Position Sizing and Risk Management Base Classes

This module provides the base classes for the position sizing and risk management system.
It defines the interfaces that all concrete implementations must follow.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple, Union, TypedDict
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class PositionSizingResult(TypedDict):
    """Type definition for position sizing results."""
    size: float
    value: float  # Position value in account currency
    risk_amount: float  # Amount at risk in account currency
    risk_percent: float  # Percentage of account at risk
    entry_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    margin_required: float
    leverage: float
    confidence: float  # Confidence level in the position sizing (0.0 to 1.0)
    metadata: Dict[str, Any]  # Additional algorithm-specific data


class PositionSizer(ABC):
    """
    Abstract base class for all position sizing algorithms.
    
    This class defines the interface that all position sizers must implement.
    Position sizers calculate the appropriate position size based on account
    equity, risk parameters, and market conditions.
    """
    
    def __init__(self, **kwargs):
        """
        Initialize the position sizer.
        
        Args:
            **kwargs: Algorithm-specific parameters
        """
        pass
    
    @abstractmethod
    def calculate_position_size(
        self,
        equity: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        market_data: Optional[pd.DataFrame] = None,
        confidence: float = 1.0,
        **kwargs
    ) -> PositionSizingResult:
        """
        Calculate the appropriate position size.
        
        Args:
            equity: Current account equity
            entry_price: Planned entry price
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            market_data: Optional market data for additional calculations
            confidence: Signal confidence level between 0.0 and 1.0
            **kwargs: Additional parameters
                
        Returns:
            PositionSizingResult containing calculated position size and metadata
        """
        pass
    
    @abstractmethod
    def update_parameters(self, **kwargs) -> None:
        """
        Update the position sizer parameters.
        
        Args:
            **kwargs: Parameters to update
        """
        pass


class VolatilityCalculator:
    """
    Class for calculating various volatility metrics.
    
    This class provides methods to calculate different volatility measures
    that can be used by position sizers and risk managers.
    """
    
    @staticmethod
    def calculate_atr(
        data: pd.DataFrame, 
        period: int = 14,
        column_high: str = 'high',
        column_low: str = 'low',
        column_close: str = 'close'
    ) -> pd.Series:
        """
        Calculate the Average True Range (ATR) for the given data.
        
        Args:
            data: DataFrame containing price data
            period: Period for ATR calculation
            column_high: Name of high price column
            column_low: Name of low price column
            column_close: Name of close price column
            
        Returns:
            Series containing ATR values
        """
        if len(data) < period + 1:
            logger.warning(f"Not enough data to calculate ATR with period {period}")
            return pd.Series(np.nan, index=data.index)
        
        high = data[column_high]
        low = data[column_low]
        close = data[column_close]
        
        # Calculate True Range
        prev_close = close.shift(1)
        tr1 = high - low  # Current high - current low
        tr2 = (high - prev_close).abs()  # Current high - previous close
        tr3 = (low - prev_close).abs()  # Current low - previous close
        
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Calculate ATR
        atr = true_range.rolling(window=period).mean()
        
        return atr
    
    @staticmethod
    def calculate_historical_volatility(
        data: pd.DataFrame,
        period: int = 20,
        annualization_factor: float = 252,  # Trading days in a year, use 365 for 24/7 markets
        column_close: str = 'close'
    ) -> pd.Series:
        """
        Calculate historical volatility based on log returns.
        
        Args:
            data: DataFrame containing price data
            period: Period for volatility calculation
            annualization_factor: Factor to annualize the volatility
            column_close: Name of close price column
            
        Returns:
            Series containing annualized volatility values
        """
        if len(data) < period + 1:
            logger.warning(f"Not enough data to calculate volatility with period {period}")
            return pd.Series(np.nan, index=data.index)
        
        # Calculate log returns
        close = data[column_close]
        log_returns = np.log(close / close.shift(1))
        
        # Calculate rolling standard deviation of returns
        rolling_std = log_returns.rolling(window=period).std()
        
        # Annualize the volatility
        annualized_vol = rolling_std * np.sqrt(annualization_factor)
        
        return annualized_vol
    
    @staticmethod
    def detect_volatility_regime(
        volatility: pd.Series,
        lookback_period: int = 100,
        high_vol_percentile: float = 0.8,
        low_vol_percentile: float = 0.2
    ) -> Dict[str, Any]:
        """
        Detect the current volatility regime by comparing recent volatility 
        to historical levels.
        
        Args:
            volatility: Series of volatility values
            lookback_period: Historical period to compare against
            high_vol_percentile: Percentile threshold for high volatility
            low_vol_percentile: Percentile threshold for low volatility
            
        Returns:
            Dictionary containing:
                - regime: Current volatility regime ('high', 'normal', or 'low')
                - current_volatility: Current volatility value
                - historical_percentile: Percentile of current volatility 
                  compared to lookback period
                - high_threshold: Threshold for high volatility
                - low_threshold: Threshold for low volatility
        """
        if len(volatility) < lookback_period:
            logger.warning(f"Not enough data to detect volatility regime with period {lookback_period}")
            return {
                'regime': 'unknown',
                'current_volatility': np.nan,
                'historical_percentile': np.nan,
                'high_threshold': np.nan,
                'low_threshold': np.nan
            }
        
        # Get the most recent volatility value
        current_vol = volatility.iloc[-1]
        
        # Calculate historical percentiles
        historical_vol = volatility.iloc[-lookback_period:-1]
        high_threshold = historical_vol.quantile(high_vol_percentile)
        low_threshold = historical_vol.quantile(low_vol_percentile)
        
        # Calculate current percentile
        historical_percentile = (historical_vol < current_vol).mean()
        
        # Determine regime
        if current_vol >= high_threshold:
            regime = 'high'
        elif current_vol <= low_threshold:
            regime = 'low'
        else:
            regime = 'normal'
        
        return {
            'regime': regime,
            'current_volatility': current_vol,
            'historical_percentile': historical_percentile,
            'high_threshold': high_threshold,
            'low_threshold': low_threshold
        } 