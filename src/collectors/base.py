"""
Base collector module.

This module defines the abstract base class for all data collectors.
Collectors are responsible for fetching data from various sources and
providing a unified interface for data access.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import pandas as pd


logger = logging.getLogger(__name__)


class DataType(str, Enum):
    """Supported data types for collection."""
    
    OHLCV = "ohlcv"
    TRADES = "trades"
    ORDERBOOK = "orderbook"
    TICKER = "ticker"
    

class CollectorState(str, Enum):
    """Collector state enum."""
    
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class BaseCollector(ABC):
    """
    Abstract base class for all data collectors.
    
    This class defines the interface that all collectors must implement.
    It provides common functionality such as logging, error handling,
    and state management.
    """
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the collector.
        
        Args:
            name: Collector name
            config: Configuration dictionary
        """
        self.name = name
        self.config = config or {}
        self.running = False
        self.last_error = None
        self.last_update_time = None
        self._tasks = []
        
    async def __aenter__(self):
        """Support for async context manager."""
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources when exiting context manager."""
        await self.stop()
        
    @abstractmethod
    async def start(self):
        """
        Start the collector.
        
        This method should initialize connections, set up resources,
        and prepare the collector for data collection.
        """
        self.running = True
        logger.info(f"Starting collector: {self.name}")
        
    @abstractmethod
    async def stop(self):
        """
        Stop the collector.
        
        This method should clean up resources, close connections,
        and ensure the collector is properly shut down.
        """
        self.running = False
        logger.info(f"Stopping collector: {self.name}")
        
        # Cancel any running tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
                
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks = []
            
    @abstractmethod
    async def collect(self, *args, **kwargs) -> Any:
        """
        Collect data from the source.
        
        This is the main method for collecting data and should be
        implemented by each specific collector.
        
        Returns:
            The collected data
        """
        pass
    
    async def fetch_periodic(self, interval: float, callback=None):
        """
        Schedule periodic data collection.
        
        Args:
            interval: Collection interval in seconds
            callback: Optional callback function to process collected data
        """
        while self.running:
            try:
                start_time = datetime.now()
                
                # Collect data
                data = await self.collect()
                
                # Process data if callback provided
                if callback and data is not None:
                    callback(data)
                    
                # Update status
                self.last_update_time = datetime.now()
                
                # Calculate sleep time to maintain consistent interval
                elapsed = (datetime.now() - start_time).total_seconds()
                sleep_time = max(0, interval - elapsed)
                
                # Sleep until next collection
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                # Handle cancellation
                logger.info(f"Periodic collection cancelled for {self.name}")
                break
            except Exception as e:
                # Log error and continue
                self.last_error = str(e)
                logger.exception(f"Error in periodic collection for {self.name}: {e}")
                await asyncio.sleep(interval)  # Sleep before retry
    
    def schedule_task(self, coro):
        """
        Schedule a new task and track it.
        
        Args:
            coro: Coroutine to schedule
            
        Returns:
            The scheduled task
        """
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        
        # Set up task cleanup
        def _on_task_done(t):
            if t in self._tasks:
                self._tasks.remove(t)
                
        task.add_done_callback(_on_task_done)
        return task
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the collector.
        
        Returns:
            Status dictionary
        """
        return {
            "name": self.name,
            "running": self.running,
            "last_update": self.last_update_time.isoformat() if self.last_update_time else None,
            "last_error": self.last_error,
            "active_tasks": len(self._tasks)
        }


class DataSink(ABC):
    """
    Abstract base class for data sinks.
    
    A data sink is responsible for storing collected data,
    whether in memory, a database, or other storage.
    """
    
    @abstractmethod
    async def store(self, data: Any) -> bool:
        """
        Store the collected data.
        
        Args:
            data: Data to store
            
        Returns:
            Success status
        """
        pass
    
    @abstractmethod
    async def retrieve(self, *args, **kwargs) -> Any:
        """
        Retrieve stored data.
        
        Returns:
            Retrieved data
        """
        pass


class MemoryDataSink(DataSink):
    """
    In-memory implementation of a data sink.
    
    Stores data in memory, useful for testing or short-lived applications.
    """
    
    def __init__(self, max_items: Optional[int] = None):
        """
        Initialize the memory sink.
        
        Args:
            max_items: Maximum number of items to store
        """
        self.data = []
        self.max_items = max_items
        
    async def store(self, data: Any) -> bool:
        """
        Store data in memory.
        
        Args:
            data: Data to store
            
        Returns:
            Success status
        """
        self.data.append(data)
        
        # If max_items is set, trim the data
        if self.max_items and len(self.data) > self.max_items:
            self.data = self.data[-self.max_items:]
            
        return True
        
    async def retrieve(self, start: int = 0, end: Optional[int] = None) -> List[Any]:
        """
        Retrieve stored data.
        
        Args:
            start: Start index
            end: End index
            
        Returns:
            List of data items
        """
        return self.data[start:end]


class DataFrameSink(DataSink):
    """
    DataFrame-based implementation of a data sink.
    
    Stores data in a pandas DataFrame, suitable for time series data.
    """
    
    def __init__(self, index_col: Optional[str] = None, max_rows: Optional[int] = None):
        """
        Initialize the DataFrame sink.
        
        Args:
            index_col: Column to use as index
            max_rows: Maximum number of rows to store
        """
        self.df = pd.DataFrame()
        self.index_col = index_col
        self.max_rows = max_rows
        
    async def store(self, data: Union[Dict, pd.DataFrame]) -> bool:
        """
        Store data in the DataFrame.
        
        Args:
            data: Data to store (dict or DataFrame)
            
        Returns:
            Success status
        """
        if isinstance(data, dict):
            # Convert single row dict to DataFrame
            new_df = pd.DataFrame([data])
        elif isinstance(data, pd.DataFrame):
            new_df = data
        else:
            raise ValueError(f"Unsupported data type: {type(data)}")
            
        # Set index if specified
        if self.index_col and self.index_col in new_df.columns:
            new_df = new_df.set_index(self.index_col)
            
        # Append to existing data
        if self.df.empty:
            self.df = new_df
        else:
            self.df = pd.concat([self.df, new_df])
            
        # Trim if needed
        if self.max_rows and len(self.df) > self.max_rows:
            self.df = self.df.iloc[-self.max_rows:]
            
        return True
        
    async def retrieve(self, *args, **kwargs) -> pd.DataFrame:
        """
        Retrieve the DataFrame.
        
        Args can include filtering options like:
        - start_time: Filter rows after this time
        - end_time: Filter rows before this time
        - columns: List of columns to return
        
        Returns:
            DataFrame with requested data
        """
        result = self.df.copy()
        
        # Apply time filters if provided
        if 'start_time' in kwargs and self.index_col:
            result = result[result.index >= kwargs['start_time']]
            
        if 'end_time' in kwargs and self.index_col:
            result = result[result.index <= kwargs['end_time']]
            
        # Select columns if specified
        if 'columns' in kwargs:
            result = result[kwargs['columns']]
            
        return result 