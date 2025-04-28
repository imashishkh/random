"""
Transaction Cost Models Module

This module contains models for simulating various transaction costs
including commissions and slippage during backtesting.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union
import random
import math

import pandas as pd
import numpy as np

# Configure logger
logger = logging.getLogger(__name__)


class CommissionModel(ABC):
    """
    Abstract base class for commission models.
    """
    
    @abstractmethod
    def calculate_commission(
        self,
        symbol: str,
        quantity: float,
        price: float,
        timestamp: Optional[pd.Timestamp] = None
    ) -> float:
        """
        Calculate commission for a trade.
        
        Args:
            symbol: Symbol string
            quantity: Trade quantity
            price: Execution price
            timestamp: Timestamp of the trade
            
        Returns:
            Commission amount
        """
        pass


class ZeroCommissionModel(CommissionModel):
    """
    Commission model with zero commission (free trades).
    """
    
    def calculate_commission(
        self,
        symbol: str,
        quantity: float,
        price: float,
        timestamp: Optional[pd.Timestamp] = None
    ) -> float:
        """
        Calculate commission for a trade (always zero).
        
        Args:
            symbol: Symbol string
            quantity: Trade quantity
            price: Execution price
            timestamp: Timestamp of the trade
            
        Returns:
            Commission amount (0.0)
        """
        return 0.0


class FixedCommissionModel(CommissionModel):
    """
    Commission model with a fixed commission per trade.
    """
    
    def __init__(self, commission_per_trade: float = 5.0):
        """
        Initialize a fixed commission model.
        
        Args:
            commission_per_trade: Fixed commission amount per trade
        """
        self.commission_per_trade = commission_per_trade
    
    def calculate_commission(
        self,
        symbol: str,
        quantity: float,
        price: float,
        timestamp: Optional[pd.Timestamp] = None
    ) -> float:
        """
        Calculate commission for a trade.
        
        Args:
            symbol: Symbol string
            quantity: Trade quantity
            price: Execution price
            timestamp: Timestamp of the trade
            
        Returns:
            Fixed commission amount
        """
        if quantity == 0:
            return 0.0
        
        return self.commission_per_trade


class PercentageCommissionModel(CommissionModel):
    """
    Commission model with a percentage of trade value.
    """
    
    def __init__(
        self,
        commission_rate: float = 0.001,  # 0.1% by default
        min_commission: float = 1.0,
        max_commission: Optional[float] = None
    ):
        """
        Initialize a percentage commission model.
        
        Args:
            commission_rate: Commission rate as a decimal
            min_commission: Minimum commission amount
            max_commission: Maximum commission amount (optional)
        """
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.max_commission = max_commission
    
    def calculate_commission(
        self,
        symbol: str,
        quantity: float,
        price: float,
        timestamp: Optional[pd.Timestamp] = None
    ) -> float:
        """
        Calculate commission for a trade.
        
        Args:
            symbol: Symbol string
            quantity: Trade quantity
            price: Execution price
            timestamp: Timestamp of the trade
            
        Returns:
            Commission amount based on percentage of trade value
        """
        if quantity == 0:
            return 0.0
        
        # Calculate trade value
        trade_value = abs(quantity) * price
        
        # Calculate percentage commission
        commission = trade_value * self.commission_rate
        
        # Apply minimum commission
        commission = max(commission, self.min_commission)
        
        # Apply maximum commission if set
        if self.max_commission is not None:
            commission = min(commission, self.max_commission)
        
        return commission


class TieredCommissionModel(CommissionModel):
    """
    Commission model with tiered rates based on trade value.
    """
    
    def __init__(
        self,
        tiers: Dict[float, float],
        min_commission: float = 1.0,
        max_commission: Optional[float] = None
    ):
        """
        Initialize a tiered commission model.
        
        Args:
            tiers: Dictionary mapping trade value thresholds to commission rates
                  e.g., {10000: 0.002, 50000: 0.001, float('inf'): 0.0005}
            min_commission: Minimum commission amount
            max_commission: Maximum commission amount (optional)
        """
        # Sort tiers by trade value (ascending)
        self.tiers = dict(sorted(tiers.items()))
        self.min_commission = min_commission
        self.max_commission = max_commission
    
    def calculate_commission(
        self,
        symbol: str,
        quantity: float,
        price: float,
        timestamp: Optional[pd.Timestamp] = None
    ) -> float:
        """
        Calculate commission for a trade using tiered rates.
        
        Args:
            symbol: Symbol string
            quantity: Trade quantity
            price: Execution price
            timestamp: Timestamp of the trade
            
        Returns:
            Commission amount based on tiered rates
        """
        if quantity == 0:
            return 0.0
        
        # Calculate trade value
        trade_value = abs(quantity) * price
        
        # Find applicable tier
        applicable_rate = None
        for threshold, rate in self.tiers.items():
            if trade_value <= threshold:
                applicable_rate = rate
                break
        
        # Use last tier if trade value exceeds all thresholds
        if applicable_rate is None and self.tiers:
            applicable_rate = list(self.tiers.values())[-1]
        
        # Calculate commission
        commission = trade_value * applicable_rate if applicable_rate is not None else 0.0
        
        # Apply minimum commission
        commission = max(commission, self.min_commission)
        
        # Apply maximum commission if set
        if self.max_commission is not None:
            commission = min(commission, self.max_commission)
        
        return commission


class SlippageModel(ABC):
    """
    Abstract base class for slippage models.
    """
    
    @abstractmethod
    def apply_slippage(
        self,
        symbol: str,
        quantity: float,
        price: float,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        timestamp: Optional[pd.Timestamp] = None
    ) -> float:
        """
        Apply slippage to a trade price.
        
        Args:
            symbol: Symbol string
            quantity: Trade quantity (positive for buy, negative for sell)
            price: Original price
            bid_price: Current bid price (optional)
            ask_price: Current ask price (optional)
            timestamp: Timestamp of the trade
            
        Returns:
            Adjusted price after slippage
        """
        pass


class ZeroSlippageModel(SlippageModel):
    """
    Slippage model with zero slippage (perfect execution).
    """
    
    def apply_slippage(
        self,
        symbol: str,
        quantity: float,
        price: float,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        timestamp: Optional[pd.Timestamp] = None
    ) -> float:
        """
        Apply slippage to a trade price (no change).
        
        Args:
            symbol: Symbol string
            quantity: Trade quantity
            price: Original price
            bid_price: Current bid price (unused)
            ask_price: Current ask price (unused)
            timestamp: Timestamp of the trade
            
        Returns:
            Original price without slippage
        """
        return price


class FixedSlippageModel(SlippageModel):
    """
    Slippage model with a fixed slippage amount.
    """
    
    def __init__(self, slippage_amount: float = 0.01):
        """
        Initialize a fixed slippage model.
        
        Args:
            slippage_amount: Fixed slippage amount in price units
        """
        self.slippage_amount = slippage_amount
    
    def apply_slippage(
        self,
        symbol: str,
        quantity: float,
        price: float,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        timestamp: Optional[pd.Timestamp] = None
    ) -> float:
        """
        Apply fixed slippage to a trade price.
        
        Args:
            symbol: Symbol string
            quantity: Trade quantity (positive for buy, negative for sell)
            price: Original price
            bid_price: Current bid price (unused)
            ask_price: Current ask price (unused)
            timestamp: Timestamp of the trade
            
        Returns:
            Adjusted price after slippage
        """
        if quantity == 0:
            return price
        
        # Buy orders have positive slippage
        if quantity > 0:
            return price + self.slippage_amount
        # Sell orders have negative slippage
        else:
            return price - self.slippage_amount


class PercentageSlippageModel(SlippageModel):
    """
    Slippage model with a percentage of price.
    """
    
    def __init__(self, slippage_rate: float = 0.001):  # 0.1% by default
        """
        Initialize a percentage slippage model.
        
        Args:
            slippage_rate: Slippage rate as a decimal
        """
        self.slippage_rate = slippage_rate
    
    def apply_slippage(
        self,
        symbol: str,
        quantity: float,
        price: float,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        timestamp: Optional[pd.Timestamp] = None
    ) -> float:
        """
        Apply percentage slippage to a trade price.
        
        Args:
            symbol: Symbol string
            quantity: Trade quantity (positive for buy, negative for sell)
            price: Original price
            bid_price: Current bid price (unused)
            ask_price: Current ask price (unused)
            timestamp: Timestamp of the trade
            
        Returns:
            Adjusted price after slippage
        """
        if quantity == 0:
            return price
        
        slippage_amount = price * self.slippage_rate
        
        # Buy orders have positive slippage
        if quantity > 0:
            return price + slippage_amount
        # Sell orders have negative slippage
        else:
            return price - slippage_amount


class VolumeBasedSlippageModel(SlippageModel):
    """
    Slippage model based on trade volume relative to market volume.
    """
    
    def __init__(
        self,
        base_rate: float = 0.0005,  # 0.05% base slippage
        volume_impact_factor: float = 0.1,
        market_volume_data: Optional[Dict[str, pd.DataFrame]] = None
    ):
        """
        Initialize a volume-based slippage model.
        
        Args:
            base_rate: Base slippage rate as a decimal
            volume_impact_factor: Factor to scale volume impact
            market_volume_data: Dictionary mapping symbols to DataFrames with volume data
        """
        self.base_rate = base_rate
        self.volume_impact_factor = volume_impact_factor
        self.market_volume_data = market_volume_data or {}
    
    def set_market_data(self, symbol: str, volume_data: pd.DataFrame) -> None:
        """
        Set market volume data for a symbol.
        
        Args:
            symbol: Symbol string
            volume_data: DataFrame with volume data
        """
        self.market_volume_data[symbol] = volume_data
    
    def get_market_volume(
        self,
        symbol: str,
        timestamp: Optional[pd.Timestamp]
    ) -> float:
        """
        Get market volume for a symbol at a specific timestamp.
        
        Args:
            symbol: Symbol string
            timestamp: Timestamp to look up
            
        Returns:
            Market volume or default value
        """
        if symbol not in self.market_volume_data or timestamp is None:
            return 1000000.0  # Default volume if data not available
        
        df = self.market_volume_data[symbol]
        
        # Find closest timestamp
        if timestamp in df.index:
            return df.loc[timestamp, 'volume']
        
        # Return default if not found
        return 1000000.0
    
    def apply_slippage(
        self,
        symbol: str,
        quantity: float,
        price: float,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        timestamp: Optional[pd.Timestamp] = None
    ) -> float:
        """
        Apply volume-based slippage to a trade price.
        
        Args:
            symbol: Symbol string
            quantity: Trade quantity (positive for buy, negative for sell)
            price: Original price
            bid_price: Current bid price (optional)
            ask_price: Current ask price (optional)
            timestamp: Timestamp of the trade
            
        Returns:
            Adjusted price after slippage
        """
        if quantity == 0:
            return price
        
        # Get market volume
        market_volume = self.get_market_volume(symbol, timestamp)
        
        # Calculate volume ratio (trade quantity relative to market volume)
        volume_ratio = abs(quantity) / market_volume
        
        # Calculate slippage rate
        slippage_rate = self.base_rate + (volume_ratio * self.volume_impact_factor)
        
        # Calculate slippage amount
        slippage_amount = price * slippage_rate
        
        # Apply slippage based on direction
        if quantity > 0:  # Buy
            return price + slippage_amount
        else:  # Sell
            return price - slippage_amount


class RandomSlippageModel(SlippageModel):
    """
    Slippage model with random slippage within a range.
    """
    
    def __init__(self, min_rate: float = 0.0, max_rate: float = 0.002):
        """
        Initialize a random slippage model.
        
        Args:
            min_rate: Minimum slippage rate as a decimal
            max_rate: Maximum slippage rate as a decimal
        """
        self.min_rate = min_rate
        self.max_rate = max_rate
    
    def apply_slippage(
        self,
        symbol: str,
        quantity: float,
        price: float,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        timestamp: Optional[pd.Timestamp] = None
    ) -> float:
        """
        Apply random slippage to a trade price.
        
        Args:
            symbol: Symbol string
            quantity: Trade quantity (positive for buy, negative for sell)
            price: Original price
            bid_price: Current bid price (unused)
            ask_price: Current ask price (unused)
            timestamp: Timestamp of the trade
            
        Returns:
            Adjusted price after slippage
        """
        if quantity == 0:
            return price
        
        # Generate random slippage rate within range
        slippage_rate = random.uniform(self.min_rate, self.max_rate)
        
        # Calculate slippage amount
        slippage_amount = price * slippage_rate
        
        # Apply slippage based on direction
        if quantity > 0:  # Buy
            return price + slippage_amount
        else:  # Sell
            return price - slippage_amount


class BidAskSlippageModel(SlippageModel):
    """
    Slippage model based on bid-ask spread.
    """
    
    def __init__(self, default_spread_pct: float = 0.001):
        """
        Initialize a bid-ask slippage model.
        
        Args:
            default_spread_pct: Default bid-ask spread as a percentage when real data is unavailable
        """
        self.default_spread_pct = default_spread_pct
    
    def apply_slippage(
        self,
        symbol: str,
        quantity: float,
        price: float,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        timestamp: Optional[pd.Timestamp] = None
    ) -> float:
        """
        Apply bid-ask slippage to a trade price.
        
        Args:
            symbol: Symbol string
            quantity: Trade quantity (positive for buy, negative for sell)
            price: Original price
            bid_price: Current bid price (optional)
            ask_price: Current ask price (optional)
            timestamp: Timestamp of the trade
            
        Returns:
            Adjusted price after slippage
        """
        if quantity == 0:
            return price
        
        # Use provided bid/ask if available
        if quantity > 0:  # Buy at ask
            if ask_price is not None:
                return ask_price
            else:
                # Estimate ask price using default spread
                return price * (1 + self.default_spread_pct / 2)
        else:  # Sell at bid
            if bid_price is not None:
                return bid_price
            else:
                # Estimate bid price using default spread
                return price * (1 - self.default_spread_pct / 2) 