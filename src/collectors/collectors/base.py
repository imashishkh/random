"""
Base collector module.

This module contains the BaseCollector abstract class which defines
the interface and common functionality for all data collectors.
"""

import abc
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from ..binance.client import BinanceClient
from ..binance.websocket import BinanceWebSocketClient


logger = logging.getLogger(__name__)


class BaseCollector(abc.ABC):
    """
    Abstract base class for all data collectors.
    
    Defines the common interface and functionality for collecting
    different types of market data.
    """
    
    def __init__(
        self,
        client: BinanceClient,
        websocket_client: Optional[BinanceWebSocketClient] = None,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        **kwargs
    ):
        """
        Initialize the base collector.
        
        Args:
            client: Binance REST API client
            websocket_client: Optional Binance WebSocket client
            symbols: List of symbols to collect data for
            timeframes: List of timeframes to collect data for (if applicable)
            **kwargs: Additional configuration options
        """
        self.client = client
        self.websocket_client = websocket_client
        self.symbols = symbols or ["BTCUSDT"]  # Default to BTC/USDT
        self.timeframes = timeframes or ["1h"]  # Default to 1-hour timeframe
        self.config = kwargs
        self._is_running = False
        self.last_run_time = None
        self.stats = {
            'collected': 0,
            'errors': 0,
            'last_error': None,
            'last_success_time': None,
        }
    
    @abc.abstractmethod
    async def collect(self, symbol: str, **kwargs) -> Any:
        """
        Collect data for a specific symbol.
        
        This method must be implemented by all concrete collector classes.
        
        Args:
            symbol: The trading pair symbol to collect data for
            **kwargs: Additional collection parameters
            
        Returns:
            Collected data in a format specific to the collector type
        """
        pass
    
    @abc.abstractmethod
    async def store(self, data: Any, **kwargs) -> bool:
        """
        Store the collected data.
        
        This method must be implemented by all concrete collector classes.
        
        Args:
            data: The data to store
            **kwargs: Additional storage parameters
            
        Returns:
            True if storage was successful, False otherwise
        """
        pass
    
    async def run(self, symbol: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Run the data collection process for one or all symbols.
        
        Args:
            symbol: Optional symbol to collect data for (if None, collect for all symbols)
            **kwargs: Additional run parameters
            
        Returns:
            Statistics about the collection run
        """
        self._is_running = True
        self.last_run_time = datetime.now()
        symbols_to_collect = [symbol] if symbol else self.symbols
        
        results = {}
        
        for sym in symbols_to_collect:
            try:
                logger.info(f"Collecting data for {sym}")
                data = await self.collect(sym, **kwargs)
                success = await self.store(data, symbol=sym, **kwargs)
                
                if success:
                    self.stats['collected'] += 1
                    self.stats['last_success_time'] = datetime.now()
                    results[sym] = {'success': True, 'data_points': len(data) if hasattr(data, '__len__') else 1}
                else:
                    self.stats['errors'] += 1
                    results[sym] = {'success': False, 'reason': 'Storage failed'}
                    
            except Exception as e:
                logger.error(f"Error collecting data for {sym}: {str(e)}")
                self.stats['errors'] += 1
                self.stats['last_error'] = str(e)
                results[sym] = {'success': False, 'reason': str(e)}
        
        self._is_running = False
        return {
            'results': results,
            'stats': self.stats,
            'run_time': datetime.now() - self.last_run_time
        }
    
    @property
    def is_running(self) -> bool:
        """
        Check if the collector is currently running.
        
        Returns:
            True if the collector is running, False otherwise
        """
        return self._is_running
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get collection statistics.
        
        Returns:
            Dictionary with collection statistics
        """
        return {
            **self.stats,
            'is_running': self._is_running,
            'last_run_time': self.last_run_time,
        } 