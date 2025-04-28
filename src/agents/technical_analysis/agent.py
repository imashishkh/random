"""
Technical Analysis Agent Framework

This module provides a comprehensive framework for performing technical analysis on financial data,
generating trading signals, and evaluating strategies through backtesting.
"""

import uuid
from typing import Dict, List, Any, Optional, Union, Tuple
import pandas as pd
import numpy as np
from datetime import datetime

from .base_agent import BaseAgent
from ...indicators.factory import IndicatorFactory


class TechnicalAnalysisAgent:
    """
    Base class for technical analysis agents.
    
    This class provides core functionality for computing technical indicators,
    generating trading signals, and evaluating strategies through backtesting.
    It serves as the foundation for specialized analysis agents.
    """
    
    def __init__(self, name: str = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the technical analysis agent.
        
        Args:
            name: Optional name for the agent instance
            config: Configuration dictionary with parameters for indicators and signal generation
        """
        self.name = name or f"TA-Agent-{uuid.uuid4().hex[:8]}"
        self.config = config or {}
        self.indicators = {}
        self.signals = []
        self.backtest_results = None
        
        # Initialize library availability
        self._check_library_availability()

    def _check_library_availability(self) -> None:
        """Check for availability of TA-Lib and Pandas TA libraries"""
        # Check for TA-Lib
        try:
            import talib
            self.talib_available = True
        except ImportError:
            self.talib_available = False
            
        # Check for Pandas TA
        try:
            import pandas_ta
            self.pandas_ta_available = True
        except ImportError:
            self.pandas_ta_available = False
            
        if not (self.talib_available or self.pandas_ta_available):
            raise ImportError("Neither TA-Lib nor Pandas TA is available. At least one is required.")
    
    def compute_indicator(self, indicator_type: str, data: pd.DataFrame, params: Optional[Dict[str, Any]] = None) -> pd.Series:
        """
        Compute a single technical indicator.
        
        Args:
            indicator_type: Type of indicator to compute (e.g., 'RSI', 'MACD')
            data: Market data as a pandas DataFrame with OHLCV columns
            params: Parameters for the indicator calculation
            
        Returns:
            Computed indicator values as a pandas Series
        """
        params = params or {}
        
        # Use the existing IndicatorFactory to compute the indicator
        calculator = IndicatorFactory.get(indicator_type)
        result = calculator(data, **params)
        
        # Store the result
        self.indicators[indicator_type] = result
        
        return result
    
    def compute_indicators(self, data: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        Compute all configured indicators.
        
        This method should be implemented by subclasses to compute specific
        indicators relevant to their analysis type.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            
        Returns:
            Dictionary mapping indicator names to computed values
        """
        raise NotImplementedError("Subclasses must implement compute_indicators()")
    
    def generate_signals(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Generate trading signals based on computed indicators.
        
        This method should be implemented by subclasses to generate signals
        based on their specific analysis approach.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            
        Returns:
            List of signal dictionaries with type, timestamp, indicator, and confidence
        """
        raise NotImplementedError("Subclasses must implement generate_signals()")
    
    def get_confidence_level(self, signal: Dict[str, Any], data: pd.DataFrame) -> float:
        """
        Calculate confidence level for a trading signal.
        
        This method should be implemented by subclasses to determine the confidence
        level of a signal based on multiple factors.
        
        Args:
            signal: Signal dictionary with metadata
            data: Market data as a pandas DataFrame
            
        Returns:
            Confidence level between 0 and 1
        """
        raise NotImplementedError("Subclasses must implement get_confidence_level()")
    
    def backtest(self, data: pd.DataFrame, start_date: Optional[str] = None, 
                end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Run backtest on historical data and evaluate performance.
        
        Args:
            data: Market data as a pandas DataFrame with OHLCV columns
            start_date: Start date for the backtest in 'YYYY-MM-DD' format
            end_date: End date for the backtest in 'YYYY-MM-DD' format
            
        Returns:
            Dictionary with backtest results including signals, win rate, and profit metrics
        """
        # Filter data based on date range if provided
        if start_date and end_date:
            if 'timestamp' in data.columns:
                date_col = 'timestamp'
            elif data.index.name == 'timestamp' or isinstance(data.index, pd.DatetimeIndex):
                date_col = data.index
            else:
                raise ValueError("Data must have a 'timestamp' column or datetime index")
                
            if isinstance(date_col, str):
                data = data[(data[date_col] >= start_date) & (data[date_col] <= end_date)]
        
        # Generate signals
        signals = self.generate_signals(data)
        
        # Evaluate each signal
        results = []
        for signal in signals:
            signal_time = signal['timestamp']
            
            # Find the index of the signal time
            if isinstance(data.index, pd.DatetimeIndex):
                if isinstance(signal_time, str):
                    signal_time = pd.to_datetime(signal_time)
                try:
                    signal_idx = data.index.get_indexer([signal_time], method='nearest')[0]
                except:
                    # If exact match fails, find the closest date
                    signal_idx = data.index.get_indexer([signal_time], method='nearest')[0]
            else:
                signal_idx = data.index.get_loc(signal_time)
            
            # Skip signals near the end of the data where we can't evaluate
            evaluation_periods = self.config.get('evaluation_periods', 10)
            if signal_idx + evaluation_periods >= len(data):
                continue
                
            # Get entry and exit prices
            entry_price = data['close'].iloc[signal_idx]
            exit_price = data['close'].iloc[signal_idx + evaluation_periods]
            
            # Calculate profit/loss
            if signal['type'].lower() == 'buy':
                profit_pct = (exit_price - entry_price) / entry_price * 100
            else:  # sell signal
                profit_pct = (entry_price - exit_price) / entry_price * 100
                
            # Record result
            result = signal.copy()
            result['entry_price'] = entry_price
            result['exit_price'] = exit_price
            result['profit_pct'] = profit_pct
            result['profitable'] = profit_pct > 0
            results.append(result)
        
        # Calculate overall statistics
        if results:
            win_rate = sum(1 for r in results if r['profitable']) / len(results)
            avg_profit = sum(r['profit_pct'] for r in results) / len(results)
            
            self.backtest_results = {
                'signals': results,
                'win_rate': win_rate,
                'avg_profit': avg_profit,
                'total_signals': len(results),
                'profitable_signals': sum(1 for r in results if r['profitable']),
                'unprofitable_signals': sum(1 for r in results if not r['profitable'])
            }
            
            return self.backtest_results
        
        # Empty results case
        self.backtest_results = {
            'signals': [],
            'win_rate': 0,
            'avg_profit': 0,
            'total_signals': 0,
            'profitable_signals': 0,
            'unprofitable_signals': 0
        }
        
        return self.backtest_results
    
    def _get_index_from_timestamp(self, timestamp, data):
        """Utility method to find the index position from a timestamp"""
        if isinstance(data.index, pd.DatetimeIndex):
            if isinstance(timestamp, str):
                timestamp = pd.to_datetime(timestamp)
            return data.index.get_indexer([timestamp], method='nearest')[0]
        else:
            return data.index.get_loc(timestamp)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the agent to a dictionary representation.
        
        Returns:
            Dictionary representation of the agent
        """
        return {
            'name': self.name,
            'type': self.__class__.__name__,
            'config': self.config,
            'backtest_results': self.backtest_results
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TechnicalAnalysisAgent':
        """
        Create an agent instance from a dictionary representation.
        
        Args:
            data: Dictionary representation of the agent
            
        Returns:
            New agent instance
        """
        agent = cls(name=data.get('name'), config=data.get('config', {}))
        agent.backtest_results = data.get('backtest_results')
        return agent 