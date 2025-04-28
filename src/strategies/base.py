from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
import numpy as np
from enum import Enum


class SignalType(Enum):
    """Enum representing different types of trading signals."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    EXIT = "EXIT"


class Signal:
    """Class representing a trading signal with metadata."""
    
    def __init__(
        self,
        signal_type: SignalType,
        symbol: str,
        price: float,
        timestamp: pd.Timestamp,
        strength: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.signal_type = signal_type
        self.symbol = symbol
        self.price = price
        self.timestamp = timestamp
        self.strength = strength  # Signal confidence/strength (0.0 to 1.0)
        self.metadata = metadata or {}
    
    def __repr__(self) -> str:
        return (
            f"Signal({self.signal_type.value}, {self.symbol}, "
            f"price={self.price:.2f}, strength={self.strength:.2f}, "
            f"timestamp={self.timestamp})"
        )


class Strategy(ABC):
    """Abstract base class for all trading strategies."""
    
    def __init__(self, name: str, params: Dict[str, Any] = None):
        self.name = name
        self.params = params or {}
        self.is_initialized = False
    
    @abstractmethod
    def initialize(self) -> None:
        """Initialize the strategy with any necessary setup."""
        pass
    
    @abstractmethod
    def analyze(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze market data and produce analysis results.
        
        Args:
            data: DataFrame containing market data (OHLCV, etc.)
            
        Returns:
            Dictionary containing analysis results
        """
        pass
    
    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """
        Generate trading signals based on market data.
        
        Args:
            data: DataFrame containing market data (OHLCV, etc.)
            
        Returns:
            List of Signal objects
        """
        pass
    
    def update_params(self, new_params: Dict[str, Any]) -> None:
        """Update strategy parameters."""
        self.params.update(new_params)
    
    @property
    def description(self) -> str:
        """Return a description of the strategy."""
        return f"{self.name} Strategy"
    
    @abstractmethod
    def get_required_indicators(self) -> List[str]:
        """Return a list of indicator names required by this strategy."""
        pass
    
    @abstractmethod
    def get_required_timeframes(self) -> List[str]:
        """Return a list of timeframes required by this strategy."""
        pass 