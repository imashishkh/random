"""
Real-time stream processor for technical indicator calculations.
"""

import logging
import time
import json
import asyncio
from typing import Dict, Any, List, Callable, Optional, Set
import pandas as pd
import numpy as np
from collections import defaultdict, deque

from .calculator import IndicatorCalculator
from ..cache.redis_client import RedisClient

# Set up logging
logger = logging.getLogger(__name__)

class IndicatorStreamProcessor:
    """
    Stream processor for real-time technical indicator calculations.
    
    This processor maintains a sliding window of market data for
    different symbols and timeframes, and recalculates indicators
    when new data arrives. It is designed to be memory-efficient
    and performant for real-time trading scenarios.
    """
    
    def __init__(self, 
                 calculator: IndicatorCalculator,
                 redis_client: Optional[RedisClient] = None,
                 max_window_size: int = 1000):
        """
        Initialize the stream processor.
        
        Args:
            calculator: The indicator calculator instance
            redis_client: Redis client for pub/sub and data sharing
            max_window_size: Maximum data points to keep in sliding window
        """
        self.calculator = calculator
        self.redis_client = redis_client
        self.max_window_size = max_window_size
        
        # Data storage: symbol -> timeframe -> data
        self.data_windows: Dict[str, Dict[str, pd.DataFrame]] = defaultdict(dict)
        
        # Indicator subscriptions: symbol -> timeframe -> set of indicators
        self.subscriptions: Dict[str, Dict[str, Set[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(set))
        
        # Callbacks for indicator updates: (symbol, timeframe, indicator) -> callback
        self.callbacks: Dict[tuple, List[Callable]] = defaultdict(list)
        
        # Running flag
        self.running = False
        
        logger.info(f"Initialized IndicatorStreamProcessor")
    
    def subscribe(self, 
                 symbol: str, 
                 timeframe: str, 
                 indicator_name: str,
                 params: Dict[str, Any] = None,
                 callback: Optional[Callable] = None) -> None:
        """
        Subscribe to indicator updates for a symbol and timeframe.
        
        Args:
            symbol: Market symbol (e.g., 'BTC/USD')
            timeframe: Timeframe (e.g., '1m', '1h')
            indicator_name: Indicator name to calculate
            params: Indicator parameters
            callback: Optional callback function when indicator updates
        """
        params = params or {}
        
        # Create subscription key
        subscription = {
            'name': indicator_name.upper(),
            'params': params
        }
        
        # Add to subscriptions
        self.subscriptions[symbol][timeframe].add(frozenset(subscription.items()))
        
        # Register callback if provided
        if callback:
            key = (symbol, timeframe, indicator_name)
            self.callbacks[key].append(callback)
        
        logger.debug(f"Subscribed to {indicator_name} for {symbol} {timeframe}")
    
    def unsubscribe(self, 
                   symbol: str, 
                   timeframe: str, 
                   indicator_name: str = None,
                   callback: Optional[Callable] = None) -> None:
        """
        Unsubscribe from indicator updates.
        
        Args:
            symbol: Market symbol
            timeframe: Timeframe
            indicator_name: Indicator name (None to unsubscribe from all)
            callback: Specific callback to remove (None to remove all)
        """
        if indicator_name is None:
            # Remove all subscriptions for symbol/timeframe
            if symbol in self.subscriptions:
                if timeframe in self.subscriptions[symbol]:
                    del self.subscriptions[symbol][timeframe]
                
                if not self.subscriptions[symbol]:
                    del self.subscriptions[symbol]
        else:
            # Remove specific indicator subscription
            if symbol in self.subscriptions and timeframe in self.subscriptions[symbol]:
                # Convert subscriptions to a list to modify during iteration
                subs_to_remove = []
                for sub in self.subscriptions[symbol][timeframe]:
                    sub_dict = dict(sub)
                    if sub_dict.get('name') == indicator_name.upper():
                        subs_to_remove.append(sub)
                
                for sub in subs_to_remove:
                    self.subscriptions[symbol][timeframe].remove(sub)
        
        # Remove callbacks
        if callback is not None:
            if indicator_name is not None:
                key = (symbol, timeframe, indicator_name)
                if key in self.callbacks and callback in self.callbacks[key]:
                    self.callbacks[key].remove(callback)
            else:
                # Remove all callbacks for this symbol/timeframe
                keys_to_check = [(s, t, i) for s, t, i in self.callbacks.keys() 
                                if s == symbol and t == timeframe]
                for key in keys_to_check:
                    if callback in self.callbacks[key]:
                        self.callbacks[key].remove(callback)
        elif indicator_name is not None:
            # Remove all callbacks for this indicator
            key = (symbol, timeframe, indicator_name)
            if key in self.callbacks:
                del self.callbacks[key]
        else:
            # Remove all callbacks for this symbol/timeframe
            keys_to_remove = [(s, t, i) for s, t, i in self.callbacks.keys() 
                            if s == symbol and t == timeframe]
            for key in keys_to_remove:
                del self.callbacks[key]
        
        logger.debug(f"Unsubscribed from {indicator_name or 'all'} for {symbol} {timeframe}")
    
    def process_market_data(self, 
                           symbol: str, 
                           timeframe: str, 
                           data: pd.DataFrame) -> Dict[str, Any]:
        """
        Process new market data and recalculate indicators.
        
        Args:
            symbol: Market symbol
            timeframe: Timeframe
            data: New market data to process
            
        Returns:
            Dictionary of calculated indicators
        """
        if not data.empty:
            # Update data window
            self._update_data_window(symbol, timeframe, data)
            
            # Get subscribed indicators
            subscriptions = self.subscriptions.get(symbol, {}).get(timeframe, set())
            if not subscriptions:
                logger.debug(f"No subscriptions for {symbol} {timeframe}")
                return {}
            
            # Prepare indicator configs for batch calculation
            indicator_configs = []
            for sub in subscriptions:
                sub_dict = dict(sub)
                indicator_configs.append({
                    'name': sub_dict.get('name'),
                    'params': sub_dict.get('params', {})
                })
            
            # Calculate all indicators in batch
            try:
                start_time = time.time()
                results = self.calculator.batch_calculate(
                    indicator_configs,
                    self.data_windows[symbol][timeframe],
                    use_cache=True,
                    refresh_cache=True  # Force refresh for streaming data
                )
                calculation_time = time.time() - start_time
                
                logger.debug(f"Calculated {len(results)} indicators for {symbol} {timeframe} in {calculation_time:.2f}s")
                
                # Invoke callbacks
                for indicator_name, result in results.items():
                    key = (symbol, timeframe, indicator_name)
                    for callback in self.callbacks.get(key, []):
                        try:
                            callback(symbol, timeframe, indicator_name, result)
                        except Exception as e:
                            logger.exception(f"Error in callback for {key}: {e}")
                
                # Publish to Redis if available
                if self.redis_client and results:
                    try:
                        # We can't directly publish pandas objects, so we'll publish
                        # a notification that new data is available
                        notification = {
                            'symbol': symbol,
                            'timeframe': timeframe,
                            'timestamp': time.time(),
                            'indicators': list(results.keys())
                        }
                        channel = f"indicators:{symbol}:{timeframe}"
                        self.redis_client.publish(channel, json.dumps(notification))
                        
                    except Exception as e:
                        logger.warning(f"Error publishing to Redis: {e}")
                
                return results
                
            except Exception as e:
                logger.exception(f"Error calculating indicators for {symbol} {timeframe}: {e}")
                return {}
        else:
            logger.warning(f"Empty data received for {symbol} {timeframe}")
            return {}
    
    def _update_data_window(self, symbol: str, timeframe: str, new_data: pd.DataFrame) -> None:
        """
        Update the sliding window of market data.
        
        Args:
            symbol: Market symbol
            timeframe: Timeframe
            new_data: New data to add to window
        """
        # Ensure data is properly indexed by timestamp
        if not isinstance(new_data.index, pd.DatetimeIndex):
            if 'timestamp' in new_data.columns:
                new_data = new_data.set_index('timestamp')
            else:
                logger.warning(f"Data for {symbol} {timeframe} missing timestamp index")
                return
        
        # Sort by timestamp
        new_data = new_data.sort_index()
        
        # If we already have data for this symbol/timeframe
        if symbol in self.data_windows and timeframe in self.data_windows[symbol]:
            existing_data = self.data_windows[symbol][timeframe]
            
            # Concatenate and remove duplicates
            combined = pd.concat([existing_data, new_data])
            combined = combined[~combined.index.duplicated(keep='last')]
            
            # Sort by timestamp and limit window size
            combined = combined.sort_index()
            if len(combined) > self.max_window_size:
                combined = combined.iloc[-self.max_window_size:]
            
            self.data_windows[symbol][timeframe] = combined
            
        else:
            # First data for this symbol/timeframe
            if len(new_data) > self.max_window_size:
                new_data = new_data.iloc[-self.max_window_size:]
            
            self.data_windows[symbol][timeframe] = new_data
        
        logger.debug(f"Updated data window for {symbol} {timeframe}: {len(self.data_windows[symbol][timeframe])} points")
    
    async def start_processing(self) -> None:
        """
        Start the stream processor in a background task.
        
        This method is intended to be called in an event loop.
        """
        if self.running:
            logger.warning("Stream processor already running")
            return
        
        self.running = True
        logger.info("Starting indicator stream processor")
        
        # In a real implementation, this would listen to a stream of market data
        # For this demo, we'll just keep the processor alive
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Stream processor task cancelled")
            self.running = False
    
    def stop_processing(self) -> None:
        """Stop the stream processor."""
        self.running = False
        logger.info("Stopping indicator stream processor") 