"""
Backtesting Data Source Module

This module contains the data source classes for the backtesting system,
providing a unified interface for accessing historical data from various sources.
"""

import os
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union, Tuple

import pandas as pd
import numpy as np
from aiohttp import ClientSession
import asyncio

from ...data_manager.data_manager import DataManager

# Configure logger
logger = logging.getLogger(__name__)


class BacktestDataSource(ABC):
    """
    Abstract base class for all backtesting data sources.
    
    Provides a common interface for accessing historical data
    regardless of the underlying source.
    """
    
    @abstractmethod
    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        include_indicators: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Get historical market data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe for the data (e.g., '1h', '1d')
            start_date: Start date for historical data
            end_date: End date for historical data
            include_indicators: Optional list of technical indicators to include
            
        Returns:
            DataFrame with historical data
        """
        pass
    
    @abstractmethod
    async def get_multiple_symbols_data(
        self,
        symbols: List[str],
        timeframe: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        include_indicators: Optional[List[str]] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Get historical market data for multiple symbols.
        
        Args:
            symbols: List of trading pair symbols
            timeframe: Timeframe for the data (e.g., '1h', '1d')
            start_date: Start date for historical data
            end_date: End date for historical data
            include_indicators: Optional list of technical indicators to include
            
        Returns:
            Dictionary mapping symbols to their respective DataFrames
        """
        pass


class DataManagerAdapter(BacktestDataSource):
    """
    Adapter for using the application's DataManager as a backtesting data source.
    """
    
    def __init__(
        self,
        data_manager: Optional[DataManager] = None,
        default_source: str = 'ccxt'
    ):
        """
        Initialize the DataManager adapter.
        
        Args:
            data_manager: Optional DataManager instance
            default_source: Default data source type to use
        """
        self.data_manager = data_manager or DataManager()
        self.default_source = default_source
    
    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        include_indicators: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Get historical market data using the DataManager.
        
        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe for the data
            start_date: Start date for historical data
            end_date: End date for historical data
            include_indicators: Optional list of technical indicators to include
            
        Returns:
            DataFrame with historical data
        """
        # Convert string dates to datetime if needed
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        
        # Calculate the appropriate limit based on timeframe and date range
        limit = self._calculate_limit(start_date, end_date, timeframe)
        
        # Get data from data_manager
        data = await self.data_manager.get_market_data(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            since=start_date,
            source_type=self.default_source,
            preprocess=True
        )
        
        # Filter to exact date range
        if not data.empty:
            data = data[(data.index >= pd.Timestamp(start_date)) & 
                         (data.index <= pd.Timestamp(end_date))]
        
        # Add requested indicators if not already present
        if include_indicators and not data.empty:
            data = await self._add_indicators(data, include_indicators)
        
        return data
    
    async def get_multiple_symbols_data(
        self,
        symbols: List[str],
        timeframe: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        include_indicators: Optional[List[str]] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Get historical market data for multiple symbols using the DataManager.
        
        Args:
            symbols: List of trading pair symbols
            timeframe: Timeframe for the data
            start_date: Start date for historical data
            end_date: End date for historical data
            include_indicators: Optional list of technical indicators to include
            
        Returns:
            Dictionary mapping symbols to their respective DataFrames
        """
        # Convert string dates to datetime if needed
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        
        # Calculate the appropriate limit based on timeframe and date range
        limit = self._calculate_limit(start_date, end_date, timeframe)
        
        # Get data for multiple symbols
        data_dict = await self.data_manager.get_multi_symbol_data(
            symbols=symbols,
            timeframe=timeframe,
            limit=limit,
            since=start_date,
            source_type=self.default_source,
            preprocess=True
        )
        
        # Filter to exact date range for each symbol
        for symbol, data in data_dict.items():
            if not data.empty:
                data_dict[symbol] = data[(data.index >= pd.Timestamp(start_date)) & 
                                         (data.index <= pd.Timestamp(end_date))]
                
                # Add requested indicators if not already present
                if include_indicators and not data_dict[symbol].empty:
                    data_dict[symbol] = await self._add_indicators(data_dict[symbol], include_indicators)
        
        return data_dict
    
    def _calculate_limit(self, start_date: datetime, end_date: datetime, timeframe: str) -> int:
        """
        Calculate the appropriate limit for data retrieval based on date range and timeframe.
        
        Args:
            start_date: Start date
            end_date: End date
            timeframe: Timeframe string (e.g., '1h', '1d')
            
        Returns:
            Calculated limit value
        """
        # Map timeframe to timedelta
        timeframe_map = {
            '1m': timedelta(minutes=1),
            '5m': timedelta(minutes=5),
            '15m': timedelta(minutes=15),
            '30m': timedelta(minutes=30),
            '1h': timedelta(hours=1),
            '2h': timedelta(hours=2),
            '4h': timedelta(hours=4),
            '6h': timedelta(hours=6),
            '8h': timedelta(hours=8),
            '12h': timedelta(hours=12),
            '1d': timedelta(days=1),
            '3d': timedelta(days=3),
            '1w': timedelta(weeks=1),
            '1M': timedelta(days=30)
        }
        
        # Get the timedelta for this timeframe, default to 1 day if unknown
        tdelta = timeframe_map.get(timeframe, timedelta(days=1))
        
        # Calculate number of periods in the date range
        periods = (end_date - start_date) / tdelta
        
        # Add 10% margin and return as integer
        return int(periods * 1.1) + 10
    
    async def _add_indicators(self, data: pd.DataFrame, indicators: List[str]) -> pd.DataFrame:
        """
        Add technical indicators to the data if they don't already exist.
        
        Args:
            data: Price data DataFrame
            indicators: List of indicator names to add
            
        Returns:
            DataFrame with added indicators
        """
        # Check which indicators need to be added
        existing_columns = set(data.columns)
        indicators_to_add = []
        
        for indicator in indicators:
            # Handle composite indicators like 'macd' which creates multiple columns
            if indicator == 'macd' and not all(col in existing_columns for col in ['macd', 'macd_signal', 'macd_hist']):
                indicators_to_add.append('macd')
            # Handle bollinger bands
            elif indicator == 'bbands' and not all(col in existing_columns for col in ['bb_upper', 'bb_middle', 'bb_lower']):
                indicators_to_add.append('bbands')
            # Simple indicators with single column
            elif indicator not in existing_columns:
                indicators_to_add.append(indicator)
        
        if not indicators_to_add:
            return data
        
        # Get a technical preprocessor and add the indicators
        from src.data_manager.preprocessor import PreprocessorFactory
        tech_preprocessor = PreprocessorFactory().get_preprocessor('technical', indicators=indicators_to_add)
        
        # Process the data
        processed_data = tech_preprocessor.process(data)
        
        return processed_data


class CSVDataSource(BacktestDataSource):
    """
    Data source that reads historical data from CSV files.
    """
    
    def __init__(self, data_directory: str):
        """
        Initialize the CSV data source.
        
        Args:
            data_directory: Directory containing CSV files with historical data
        """
        self.data_directory = data_directory
        self._verify_directory()
    
    def _verify_directory(self):
        """Verify that the data directory exists."""
        if not os.path.exists(self.data_directory):
            logger.warning(f"Data directory {self.data_directory} does not exist, creating it")
            os.makedirs(self.data_directory)
    
    def _get_filename(self, symbol: str, timeframe: str) -> str:
        """
        Generate a standardized filename for a symbol and timeframe.
        
        Args:
            symbol: Symbol string
            timeframe: Timeframe string
            
        Returns:
            Filename string
        """
        # Replace any characters that would be invalid in a filename
        clean_symbol = symbol.replace('/', '_').replace(':', '_')
        return os.path.join(self.data_directory, f"{clean_symbol}_{timeframe}.csv")
    
    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        include_indicators: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Get historical market data from CSV file.
        
        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe for the data
            start_date: Start date for historical data
            end_date: End date for historical data
            include_indicators: Optional list of technical indicators to include
            
        Returns:
            DataFrame with historical data
        """
        filename = self._get_filename(symbol, timeframe)
        
        if not os.path.exists(filename):
            logger.warning(f"CSV file {filename} does not exist, returning empty DataFrame")
            return pd.DataFrame()
        
        # Read CSV file
        try:
            df = pd.read_csv(filename)
            
            # Check if 'timestamp' column exists
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
            elif 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'])
                df.set_index('time', inplace=True)
            elif 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                
            # Convert string dates to datetime if needed
            if isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if isinstance(end_date, str):
                end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                
            # Filter to date range
            df = df[(df.index >= pd.Timestamp(start_date)) & 
                    (df.index <= pd.Timestamp(end_date))]
            
            # Add requested indicators if not already present
            if include_indicators and not df.empty:
                from src.data_manager.preprocessor import PreprocessorFactory
                tech_preprocessor = PreprocessorFactory().get_preprocessor('technical', indicators=include_indicators)
                df = tech_preprocessor.process(df)
            
            return df
            
        except Exception as e:
            logger.error(f"Error reading CSV file {filename}: {e}")
            return pd.DataFrame()
    
    async def get_multiple_symbols_data(
        self,
        symbols: List[str],
        timeframe: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        include_indicators: Optional[List[str]] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Get historical market data for multiple symbols from CSV files.
        
        Args:
            symbols: List of trading pair symbols
            timeframe: Timeframe for the data
            start_date: Start date for historical data
            end_date: End date for historical data
            include_indicators: Optional list of technical indicators to include
            
        Returns:
            Dictionary mapping symbols to their respective DataFrames
        """
        result = {}
        
        for symbol in symbols:
            df = await self.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                include_indicators=include_indicators
            )
            result[symbol] = df
        
        return result 