"""
Data provider for technical analysis agents.

This module provides a standardized interface for accessing and managing
market data required for technical analysis.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime, timedelta
import os
import json


class DataProvider:
    """
    Data provider for technical analysis.
    
    This class handles fetching, preprocessing, and managing market data
    for use with technical analysis agents.
    """
    
    def __init__(self, symbol: str, timeframe: str, source: str = 'api'):
        """
        Initialize the data provider.
        
        Args:
            symbol: Trading symbol (e.g., 'EUR/USD')
            timeframe: Data timeframe (e.g., '1h', '4h', '1d')
            source: Data source type ('api', 'csv', 'database')
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self.source = source
        self.data = None
        self.last_update = None
        
    def fetch_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None,
                  limit: Optional[int] = None) -> pd.DataFrame:
        """
        Fetch market data from the configured source.
        
        Args:
            start_date: Start date for data in 'YYYY-MM-DD' format
            end_date: End date for data in 'YYYY-MM-DD' format
            limit: Maximum number of data points to fetch
            
        Returns:
            DataFrame containing market data with OHLCV columns
        """
        if self.source == 'api':
            return self._fetch_from_api(start_date, end_date, limit)
        elif self.source == 'csv':
            return self._fetch_from_csv(start_date, end_date, limit)
        elif self.source == 'database':
            return self._fetch_from_database(start_date, end_date, limit)
        else:
            raise ValueError(f"Unsupported data source: {self.source}")
    
    def _fetch_from_api(self, start_date: Optional[str], end_date: Optional[str],
                       limit: Optional[int]) -> pd.DataFrame:
        """
        Fetch data from an API source.
        
        This method should be extended to connect to specific API providers.
        For now, it returns sample data for testing purposes.
        
        Args:
            start_date: Start date for data
            end_date: End date for data
            limit: Maximum number of data points
            
        Returns:
            DataFrame with OHLCV data
        """
        # In a real implementation, this would connect to an exchange API
        # For now, generate sample data for testing
        
        # Calculate date range
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        end = pd.to_datetime(end_date)
        
        if start_date is None:
            if limit:
                # Calculate start date based on limit and timeframe
                if self.timeframe.endswith('m'):
                    minutes = int(self.timeframe[:-1])
                    start = end - timedelta(minutes=minutes * limit)
                elif self.timeframe.endswith('h'):
                    hours = int(self.timeframe[:-1])
                    start = end - timedelta(hours=hours * limit)
                elif self.timeframe.endswith('d'):
                    days = int(self.timeframe[:-1])
                    start = end - timedelta(days=days * limit)
                else:
                    # Default to 100 days
                    start = end - timedelta(days=100)
            else:
                # Default to 100 data points
                start = end - timedelta(days=100)
        else:
            start = pd.to_datetime(start_date)
        
        # Generate dates
        if self.timeframe.endswith('m'):
            minutes = int(self.timeframe[:-1])
            freq = f'{minutes}min'
        elif self.timeframe.endswith('h'):
            hours = int(self.timeframe[:-1])
            freq = f'{hours}H'
        elif self.timeframe.endswith('d'):
            days = int(self.timeframe[:-1])
            freq = f'{days}D'
        else:
            freq = '1D'
            
        dates = pd.date_range(start=start, end=end, freq=freq)
        
        # Generate sample data
        np.random.seed(42)  # For reproducibility
        
        # Start with a base price
        base_price = 100.0
        
        # Generate price movements with some trend and volatility
        price_changes = np.random.normal(0.0001, 0.001, len(dates))
        # Add some trend
        trend = np.linspace(0, 0.001, len(dates))
        price_changes = price_changes + trend
        
        # Calculate prices
        closes = base_price * (1 + np.cumsum(price_changes))
        
        # Generate OHLC data with realistic relationships
        volatility = 0.0015
        opens = closes - np.random.normal(0, volatility, len(dates))
        highs = np.maximum(opens, closes) + np.abs(np.random.normal(0, volatility, len(dates)))
        lows = np.minimum(opens, closes) - np.abs(np.random.normal(0, volatility, len(dates)))
        
        # Generate volume with some relationship to price changes
        volume_base = 1000000
        volume = volume_base + volume_base * np.abs(price_changes) * 10000
        
        # Create DataFrame
        df = pd.DataFrame({
            'timestamp': dates,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volume
        })
        
        # Set timestamp as index
        df.set_index('timestamp', inplace=True)
        
        # Apply limit if specified
        if limit and len(df) > limit:
            df = df.iloc[-limit:]
        
        self.data = df
        self.last_update = datetime.now()
        
        return df
    
    def _fetch_from_csv(self, start_date: Optional[str], end_date: Optional[str],
                      limit: Optional[int]) -> pd.DataFrame:
        """
        Fetch data from a CSV file.
        
        Args:
            start_date: Start date for data
            end_date: End date for data
            limit: Maximum number of data points
            
        Returns:
            DataFrame with OHLCV data
        """
        # Construct expected filename based on symbol and timeframe
        filename = f"{self.symbol.replace('/', '')}__{self.timeframe}.csv"
        data_dir = os.environ.get('DATA_DIR', 'data')
        filepath = os.path.join(data_dir, filename)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"CSV file not found: {filepath}")
        
        # Load data
        df = pd.read_csv(filepath)
        
        # Ensure timestamp column exists and convert to datetime
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
        
        # Filter by date range if specified
        if start_date:
            df = df[df.index >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df.index <= pd.to_datetime(end_date)]
        
        # Apply limit if specified
        if limit and len(df) > limit:
            df = df.iloc[-limit:]
        
        self.data = df
        self.last_update = datetime.now()
        
        return df
    
    def _fetch_from_database(self, start_date: Optional[str], end_date: Optional[str],
                           limit: Optional[int]) -> pd.DataFrame:
        """
        Fetch data from a database.
        
        This is a placeholder method that should be implemented based on
        the specific database used in the project.
        
        Args:
            start_date: Start date for data
            end_date: End date for data
            limit: Maximum number of data points
            
        Returns:
            DataFrame with OHLCV data
        """
        # In a real implementation, this would query a database
        # For now, we'll fall back to the API implementation
        return self._fetch_from_api(start_date, end_date, limit)
    
    def get_data(self) -> pd.DataFrame:
        """
        Get the current data, fetching it if not already loaded.
        
        Returns:
            DataFrame with OHLCV data
        """
        if self.data is None:
            self.fetch_data()
        return self.data
    
    def get_latest_data(self, limit: int = 1) -> pd.DataFrame:
        """
        Get the most recent data points.
        
        Args:
            limit: Number of recent data points to return
            
        Returns:
            DataFrame with the most recent OHLCV data
        """
        data = self.get_data()
        return data.iloc[-limit:]
    
    def update_data(self) -> pd.DataFrame:
        """
        Update the data to include the latest available data points.
        
        Returns:
            Updated DataFrame with OHLCV data
        """
        # In a real implementation, this would fetch only new data
        # and append it to the existing data
        
        # For now, we'll re-fetch all data
        last_timestamp = None
        if self.data is not None and not self.data.empty:
            last_timestamp = self.data.index[-1]
            
        # Fetch new data
        new_data = self.fetch_data()
        
        # If we had existing data, ensure we don't have duplicates
        if last_timestamp and not new_data.empty:
            new_data = new_data[new_data.index > last_timestamp]
            if not new_data.empty:
                self.data = pd.concat([self.data, new_data])
        else:
            self.data = new_data
            
        self.last_update = datetime.now()
        return self.data
    
    def save_data(self, filepath: Optional[str] = None) -> None:
        """
        Save the current data to a CSV file.
        
        Args:
            filepath: Path to save the file (defaults to symbol_timeframe.csv)
        """
        if self.data is None or self.data.empty:
            raise ValueError("No data to save")
            
        if filepath is None:
            # Construct default filename
            data_dir = os.environ.get('DATA_DIR', 'data')
            os.makedirs(data_dir, exist_ok=True)
            filepath = os.path.join(data_dir, f"{self.symbol.replace('/', '')}__{self.timeframe}.csv")
            
        # Save to CSV
        self.data.reset_index().to_csv(filepath, index=False)
    
    def get_timestamp(self, index: int) -> Union[pd.Timestamp, datetime]:
        """
        Get the timestamp for a specific index in the data.
        
        Args:
            index: Index position
            
        Returns:
            Timestamp at the specified index
        """
        data = self.get_data()
        return data.index[index] 