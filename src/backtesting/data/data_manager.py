"""
Backtesting Data Manager Module

This module contains the BacktestDataManager class which coordinates
data fetching and caching for backtesting operations.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union, Tuple, Set

import pandas as pd
import numpy as np
import h5py
import pyarrow as pa
import pyarrow.parquet as pq
from functools import lru_cache

from .data_source import BacktestDataSource, DataManagerAdapter, CSVDataSource

# Configure logger
logger = logging.getLogger(__name__)


class BacktestDataManager:
    """
    Manages historical data for backtesting.
    
    This class coordinates data fetching, caching, and storage for backtesting,
    providing efficient access to historical market data.
    """
    
    def __init__(
        self,
        data_sources: Optional[List[BacktestDataSource]] = None,
        cache_directory: Optional[str] = None,
        use_cache: bool = True,
        cache_format: str = 'parquet'
    ):
        """
        Initialize the BacktestDataManager.
        
        Args:
            data_sources: Optional list of data sources
            cache_directory: Directory for caching data (default: 'data/cache')
            use_cache: Whether to use caching
            cache_format: Cache format ('parquet' or 'hdf5')
        """
        self.data_sources = data_sources or [DataManagerAdapter()]
        self.use_cache = use_cache
        self.cache_format = cache_format
        
        # Set up cache directory
        self.cache_directory = cache_directory or os.path.join('data', 'cache')
        self._ensure_directory(self.cache_directory)
        
        # Dictionary to track loaded data
        self.loaded_data: Dict[str, pd.DataFrame] = {}
    
    def _ensure_directory(self, directory: str) -> None:
        """
        Ensure that a directory exists.
        
        Args:
            directory: Directory path
        """
        if not os.path.exists(directory):
            logger.info(f"Creating directory: {directory}")
            os.makedirs(directory, exist_ok=True)
    
    def _get_cache_path(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime
    ) -> str:
        """
        Generate a standardized cache file path.
        
        Args:
            symbol: Symbol string
            timeframe: Timeframe string
            start_date: Start date
            end_date: End date
            
        Returns:
            Cache file path
        """
        # Clean symbol for use in filename
        clean_symbol = symbol.replace('/', '_').replace(':', '_')
        
        # Format dates
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        
        # Generate filename
        filename = f"{clean_symbol}_{timeframe}_{start_str}_{end_str}"
        
        # Add extension based on cache format
        if self.cache_format == 'parquet':
            filename += ".parquet"
        else:
            filename += ".h5"
        
        return os.path.join(self.cache_directory, filename)
    
    def _save_to_cache(
        self,
        data: pd.DataFrame,
        path: str
    ) -> bool:
        """
        Save data to cache.
        
        Args:
            data: Data to cache
            path: Cache file path
            
        Returns:
            True if successful, False otherwise
        """
        if data.empty:
            return False
            
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            # Save based on format
            if self.cache_format == 'parquet':
                table = pa.Table.from_pandas(data.reset_index())
                pq.write_table(table, path, compression='snappy')
            else:
                data.to_hdf(path, key='data', mode='w', format='table')
            
            logger.debug(f"Cached data to {path}")
            return True
        except Exception as e:
            logger.error(f"Error caching data to {path}: {e}")
            return False
    
    def _load_from_cache(
        self,
        path: str
    ) -> Optional[pd.DataFrame]:
        """
        Load data from cache.
        
        Args:
            path: Cache file path
            
        Returns:
            Cached data or None if not found
        """
        if not os.path.exists(path):
            return None
            
        try:
            # Load based on format
            if self.cache_format == 'parquet':
                table = pq.read_table(path)
                df = table.to_pandas()
                # Convert the index column back to datetime index
                if 'index' in df.columns:
                    df['index'] = pd.to_datetime(df['index'])
                    df.set_index('index', inplace=True)
                elif 'timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
            else:
                df = pd.read_hdf(path, key='data')
            
            logger.debug(f"Loaded cached data from {path}")
            return df
        except Exception as e:
            logger.error(f"Error loading cached data from {path}: {e}")
            return None
    
    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        include_indicators: Optional[List[str]] = None,
        use_cache: Optional[bool] = None
    ) -> pd.DataFrame:
        """
        Get historical market data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe for the data
            start_date: Start date for historical data
            end_date: End date for historical data
            include_indicators: Optional list of indicators to include
            use_cache: Whether to use cache (overrides instance setting)
            
        Returns:
            DataFrame with historical data
        """
        # Convert string dates to datetime if needed
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        
        # Check if we should use cache
        use_cache_flag = self.use_cache if use_cache is None else use_cache
        
        # Generate cache key
        cache_path = self._get_cache_path(symbol, timeframe, start_date, end_date)
        
        # Try to load from cache if enabled
        if use_cache_flag:
            cached_data = self._load_from_cache(cache_path)
            if cached_data is not None:
                # Add indicators if needed
                if include_indicators:
                    from src.data_manager.preprocessor import PreprocessorFactory
                    tech_preprocessor = PreprocessorFactory().get_preprocessor(
                        'technical', indicators=include_indicators)
                    cached_data = tech_preprocessor.process(cached_data)
                return cached_data
        
        # If not cached or cache disabled, try to fetch from data sources
        data = None
        
        for source in self.data_sources:
            try:
                data = await source.get_historical_data(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date,
                    include_indicators=include_indicators
                )
                
                if not data.empty:
                    logger.debug(
                        f"Got historical data for {symbol} ({timeframe}) "
                        f"from {source.__class__.__name__}"
                    )
                    
                    # Cache data if enabled
                    if use_cache_flag:
                        self._save_to_cache(data, cache_path)
                    
                    return data
            except Exception as e:
                logger.warning(
                    f"Error getting historical data from {source.__class__.__name__}: {e}"
                )
        
        # If we got here, all sources failed
        logger.error(
            f"Failed to get historical data for {symbol} ({timeframe}) "
            f"from all sources"
        )
        return pd.DataFrame()
    
    async def get_multiple_symbols_data(
        self,
        symbols: List[str],
        timeframe: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        include_indicators: Optional[List[str]] = None,
        use_cache: Optional[bool] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Get historical market data for multiple symbols.
        
        Args:
            symbols: List of trading pair symbols
            timeframe: Timeframe for the data
            start_date: Start date for historical data
            end_date: End date for historical data
            include_indicators: Optional list of indicators to include
            use_cache: Whether to use cache (overrides instance setting)
            
        Returns:
            Dictionary mapping symbols to their respective DataFrames
        """
        import asyncio
        
        # Create tasks for each symbol
        tasks = [
            self.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                include_indicators=include_indicators,
                use_cache=use_cache
            )
            for symbol in symbols
        ]
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks)
        
        # Create dictionary of results
        return {symbol: result for symbol, result in zip(symbols, results)}
    
    async def get_synchronous_data(
        self,
        symbols: List[str],
        timeframe: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        include_indicators: Optional[List[str]] = None,
        use_cache: Optional[bool] = None
    ) -> pd.DataFrame:
        """
        Get synchronized historical data for multiple symbols.
        
        This method ensures that data for all symbols have the same timestamps
        by resampling and aligning the data.
        
        Args:
            symbols: List of trading pair symbols
            timeframe: Timeframe for the data
            start_date: Start date for historical data
            end_date: End date for historical data
            include_indicators: Optional list of indicators to include
            use_cache: Whether to use cache (overrides instance setting)
            
        Returns:
            DataFrame with synchronized data for all symbols
        """
        # Get data for each symbol
        symbol_data = await self.get_multiple_symbols_data(
            symbols=symbols,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            include_indicators=include_indicators,
            use_cache=use_cache
        )
        
        # Check if we have data for all symbols
        if not all(not data.empty for data in symbol_data.values()):
            missing_symbols = [s for s, data in symbol_data.items() if data.empty]
            logger.warning(f"Missing data for symbols: {missing_symbols}")
        
        # Create a synchronized DataFrame
        all_data = {}
        
        for symbol, data in symbol_data.items():
            if data.empty:
                continue
                
            # Create multi-level column names
            columns = {
                col: f"{symbol}_{col}" 
                for col in data.columns
            }
            
            # Rename columns and add to all_data
            renamed_data = data.rename(columns=columns)
            all_data[symbol] = renamed_data
        
        if not all_data:
            logger.error("No data available for synchronization")
            return pd.DataFrame()
        
        # Combine all DataFrames
        combined_data = pd.concat(all_data.values(), axis=1)
        
        return combined_data
    
    def clear_cache(self, pattern: Optional[str] = None) -> int:
        """
        Clear cached data.
        
        Args:
            pattern: Optional glob pattern to match cache files
            
        Returns:
            Number of files cleared
        """
        import glob
        
        if pattern:
            # Append extension if not provided
            if not pattern.endswith('.parquet') and not pattern.endswith('.h5'):
                if self.cache_format == 'parquet':
                    pattern += '*.parquet'
                else:
                    pattern += '*.h5'
            
            # Get files matching pattern
            files = glob.glob(os.path.join(self.cache_directory, pattern))
        else:
            # Get all cache files
            if self.cache_format == 'parquet':
                files = glob.glob(os.path.join(self.cache_directory, '*.parquet'))
            else:
                files = glob.glob(os.path.join(self.cache_directory, '*.h5'))
        
        # Delete files
        count = 0
        for file in files:
            try:
                os.remove(file)
                count += 1
            except Exception as e:
                logger.error(f"Error deleting cache file {file}: {e}")
        
        logger.info(f"Cleared {count} cache files")
        return count 