"""
OHLCV (candlestick) data collector.

This module contains the OHLCVCollector class for collecting historical
and real-time price data from Binance.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from ..binance.constants import TIMEFRAMES
from ..binance.client import BinanceClient
from ..binance.websocket import BinanceWebSocketClient
from .base import BaseCollector


logger = logging.getLogger(__name__)


class OHLCVCollector(BaseCollector):
    """
    Collector for OHLCV (Open, High, Low, Close, Volume) candlestick data.
    
    Supports both historical data collection via REST API and
    real-time updates via WebSocket.
    """
    
    def __init__(
        self,
        client: BinanceClient,
        websocket_client: Optional[BinanceWebSocketClient] = None,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        limit: int = 1000,
        data_dir: Optional[str] = None,
        realtime: bool = False,
        **kwargs
    ):
        """
        Initialize the OHLCV collector.
        
        Args:
            client: Binance REST API client
            websocket_client: Optional Binance WebSocket client (required for realtime mode)
            symbols: List of symbols to collect data for
            timeframes: List of timeframes to collect data for
            limit: Maximum number of candles to request per API call
            data_dir: Directory to store the collected data
            realtime: Whether to collect real-time data via WebSocket
            **kwargs: Additional configuration options
        """
        super().__init__(client, websocket_client, symbols, timeframes, **kwargs)
        
        self.limit = min(limit, 1000)  # Binance has a max limit of 1000
        self.data_dir = data_dir or "data/ohlcv"
        self.realtime = realtime
        
        if self.realtime and not websocket_client:
            raise ValueError("WebSocket client is required for realtime mode")
        
        # Ensure data directory exists
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Keep track of the latest data for each symbol and timeframe
        self.latest_data = {}
        self.websocket_callbacks = {}
    
    async def collect(
        self, 
        symbol: str, 
        timeframe: Optional[str] = None, 
        start_time: Optional[Union[datetime, int]] = None,
        end_time: Optional[Union[datetime, int]] = None,
        **kwargs
    ) -> pd.DataFrame:
        """
        Collect OHLCV data for a specific symbol and timeframe.
        
        Args:
            symbol: Trading pair symbol
            timeframe: Candlestick timeframe (e.g. '1h', '15m')
            start_time: Start time for historical data
            end_time: End time for historical data (default: now)
            **kwargs: Additional collection parameters
            
        Returns:
            DataFrame with OHLCV data
        """
        timeframe = timeframe or self.timeframes[0]
        
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Invalid timeframe: {timeframe}")
        
        if self.realtime:
            return await self._collect_realtime(symbol, timeframe)
        else:
            return await self._collect_historical(symbol, timeframe, start_time, end_time)
    
    async def _collect_historical(
        self, 
        symbol: str, 
        timeframe: str,
        start_time: Optional[Union[datetime, int]] = None,
        end_time: Optional[Union[datetime, int]] = None
    ) -> pd.DataFrame:
        """
        Collect historical OHLCV data using REST API.
        
        Args:
            symbol: Trading pair symbol
            timeframe: Candlestick timeframe
            start_time: Start time for historical data
            end_time: End time for historical data
            
        Returns:
            DataFrame with historical OHLCV data
        """
        # Convert datetime to milliseconds timestamp if needed
        if start_time and isinstance(start_time, datetime):
            start_time = int(start_time.timestamp() * 1000)
        
        if end_time and isinstance(end_time, datetime):
            end_time = int(end_time.timestamp() * 1000)
        
        logger.info(f"Collecting historical OHLCV for {symbol} on {timeframe} timeframe")
        klines = await self.client.get_klines(
            symbol=symbol,
            interval=timeframe,
            limit=self.limit,
            startTime=start_time,
            endTime=end_time
        )
        
        # Convert to DataFrame
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        # Convert types
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
        
        for col in ['open', 'high', 'low', 'close', 'volume', 'quote_asset_volume',
                   'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume']:
            df[col] = pd.to_numeric(df[col])
        
        # Set timestamp as index
        df.set_index('timestamp', inplace=True)
        
        # Store the latest data for this symbol and timeframe
        key = f"{symbol}_{timeframe}"
        self.latest_data[key] = df
        
        return df
    
    async def _collect_realtime(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """
        Set up realtime data collection via WebSocket.
        
        Args:
            symbol: Trading pair symbol
            timeframe: Candlestick timeframe
            
        Returns:
            DataFrame with the most recent data (if available) or empty DataFrame
        """
        if not self.websocket_client:
            raise RuntimeError("WebSocket client is not available")
        
        key = f"{symbol}_{timeframe}"
        symbol_lower = symbol.lower()
        
        # Set up WebSocket callback if not already done
        if key not in self.websocket_callbacks:
            logger.info(f"Setting up realtime OHLCV collection for {symbol} on {timeframe} timeframe")
            
            # Define callback for WebSocket updates
            async def on_kline_update(msg):
                if msg['e'] == 'kline':
                    k = msg['k']
                    
                    # Only process completed candles
                    if k['x']:  # Candle is closed/completed
                        # Create a DataFrame with this single candle
                        candle_data = {
                            'timestamp': [pd.to_datetime(k['t'], unit='ms')],
                            'open': [float(k['o'])],
                            'high': [float(k['h'])],
                            'low': [float(k['l'])],
                            'close': [float(k['c'])],
                            'volume': [float(k['v'])],
                            'close_time': [pd.to_datetime(k['T'], unit='ms')],
                            'quote_asset_volume': [float(k['q'])],
                            'number_of_trades': [int(k['n'])],
                            'taker_buy_base_asset_volume': [float(k['V'])],
                            'taker_buy_quote_asset_volume': [float(k['Q'])],
                            'ignore': [0]
                        }
                        
                        df = pd.DataFrame(candle_data)
                        df.set_index('timestamp', inplace=True)
                        
                        # Update our latest data
                        if key in self.latest_data:
                            # Append the new candle to the existing data
                            self.latest_data[key] = pd.concat([self.latest_data[key], df])
                            # Keep only the most recent candles (limit to avoid memory issues)
                            self.latest_data[key] = self.latest_data[key].iloc[-self.limit:]
                        else:
                            self.latest_data[key] = df
                        
                        # Save the updated data
                        await self.store(self.latest_data[key], symbol=symbol, timeframe=timeframe)
            
            # Subscribe to kline/candlestick WebSocket stream
            stream_name = f"{symbol_lower}@kline_{timeframe}"
            await self.websocket_client.subscribe(stream_name, on_kline_update)
            
            # Store the callback for later management
            self.websocket_callbacks[key] = on_kline_update
            
            # Load the most recent historical data to fill in until we get realtime updates
            try:
                # Get a small batch of recent data to start with
                await self._collect_historical(symbol, timeframe)
            except Exception as e:
                logger.error(f"Error getting initial historical data: {str(e)}")
                # Create empty DataFrame if we can't get historical data
                self.latest_data[key] = pd.DataFrame(columns=[
                    'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                ])
        
        # Return the latest data we have for this symbol and timeframe
        return self.latest_data.get(key, pd.DataFrame())
    
    async def store(
        self, 
        data: pd.DataFrame, 
        symbol: str,
        timeframe: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        Store the collected OHLCV data to CSV file.
        
        Args:
            data: DataFrame with OHLCV data
            symbol: Trading pair symbol
            timeframe: Candlestick timeframe
            **kwargs: Additional storage parameters
            
        Returns:
            True if storage was successful, False otherwise
        """
        if data.empty:
            logger.warning("No data to store")
            return False
        
        timeframe = timeframe or self.timeframes[0]
        
        # Create directory for this symbol if it doesn't exist
        symbol_dir = os.path.join(self.data_dir, symbol)
        os.makedirs(symbol_dir, exist_ok=True)
        
        # Save to CSV file
        filename = os.path.join(symbol_dir, f"{timeframe}.csv")
        try:
            # Check if file exists and append or create new
            if os.path.exists(filename):
                # Read existing data
                existing_data = pd.read_csv(filename, index_col='timestamp', parse_dates=True)
                
                # Combine with new data, remove duplicates
                combined = pd.concat([existing_data, data])
                combined = combined[~combined.index.duplicated(keep='last')]
                
                # Sort by timestamp
                combined.sort_index(inplace=True)
                
                # Save back to file
                combined.to_csv(filename)
            else:
                # Create new file
                data.to_csv(filename)
            
            logger.info(f"Stored OHLCV data for {symbol} ({timeframe}) to {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing data for {symbol}: {str(e)}")
            return False
    
    async def cleanup(self):
        """
        Clean up resources, especially WebSocket subscriptions.
        """
        if self.realtime and self.websocket_client:
            # Unsubscribe from all WebSocket streams
            for key in self.websocket_callbacks:
                symbol, timeframe = key.split('_')
                symbol_lower = symbol.lower()
                stream_name = f"{symbol_lower}@kline_{timeframe}"
                
                try:
                    await self.websocket_client.unsubscribe(stream_name)
                except Exception as e:
                    logger.error(f"Error unsubscribing from {stream_name}: {str(e)}")
            
            # Clear callbacks
            self.websocket_callbacks = {} 