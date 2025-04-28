"""
Signal API Client

This module provides a client for consuming signals from the Signal API.
"""

import json
import aiohttp
import asyncio
import websockets
from typing import Dict, List, Any, Optional, Callable, Union, Awaitable
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class SignalClient:
    """
    Client for consuming signals from the Signal API.
    
    Provides methods for:
    - Retrieving recent signals
    - Filtering signals
    - Subscribing to real-time signal updates
    - Retrieving statistics
    """
    
    def __init__(self, base_url: str, websocket_url: Optional[str] = None):
        """
        Initialize the Signal API client.
        
        Args:
            base_url: Base URL for the Signal API (e.g., 'http://localhost:8000')
            websocket_url: WebSocket URL for real-time updates (if different from base_url)
        """
        self.base_url = base_url.rstrip('/')
        
        # Set WebSocket URL (default: replace http:// with ws:// in base_url)
        if websocket_url:
            self.websocket_url = websocket_url
        else:
            self.websocket_url = self.base_url.replace('http://', 'ws://').replace('https://', 'wss://') + '/ws'
        
        # Set up HTTP session
        self._session = None
        
        # Set up WebSocket
        self.websocket = None
        self.websocket_task = None
        self._signal_handlers = []
        
        logger.info(f"Signal client initialized for {self.base_url}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def get_signals(self, 
                         trading_pair: Optional[str] = None,
                         direction: Optional[str] = None,
                         timeframe: Optional[str] = None,
                         min_confidence: float = 0.0,
                         limit: int = 50,
                         offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get recent signals with optional filtering.
        
        Args:
            trading_pair: Trading pair to filter by
            direction: Direction to filter by
            timeframe: Timeframe to filter by
            min_confidence: Minimum confidence threshold
            limit: Maximum number of signals to return
            offset: Offset for pagination
            
        Returns:
            List of signals
        """
        session = await self._get_session()
        
        # Build query parameters
        params = {
            'limit': limit,
            'offset': offset,
            'min_confidence': min_confidence
        }
        
        if trading_pair:
            params['trading_pair'] = trading_pair
        if direction:
            params['direction'] = direction
        if timeframe:
            params['timeframe'] = timeframe
        
        # Make request
        async with session.get(f'{self.base_url}/signals', params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                error_text = await response.text()
                logger.error(f"Error getting signals: {response.status} - {error_text}")
                response.raise_for_status()
    
    async def filter_signals(self,
                           trading_pairs: Optional[List[str]] = None,
                           agent_types: Optional[List[str]] = None,
                           signal_types: Optional[List[str]] = None,
                           directions: Optional[List[str]] = None,
                           timeframes: Optional[List[str]] = None,
                           min_confidence: Optional[float] = None,
                           start_time: Optional[Union[str, datetime]] = None,
                           end_time: Optional[Union[str, datetime]] = None,
                           limit: int = 50,
                           offset: int = 0) -> List[Dict[str, Any]]:
        """
        Filter signals with complex criteria.
        
        Args:
            trading_pairs: List of trading pairs to filter by
            agent_types: List of agent types to filter by
            signal_types: List of signal types to filter by
            directions: List of directions to filter by
            timeframes: List of timeframes to filter by
            min_confidence: Minimum confidence threshold
            start_time: Start time (ISO format string or datetime)
            end_time: End time (ISO format string or datetime)
            limit: Maximum number of signals to return
            offset: Offset for pagination
            
        Returns:
            List of signals
        """
        session = await self._get_session()
        
        # Build request data
        data = {}
        if trading_pairs:
            data['trading_pairs'] = trading_pairs
        if agent_types:
            data['agent_types'] = agent_types
        if signal_types:
            data['signal_types'] = signal_types
        if directions:
            data['directions'] = directions
        if timeframes:
            data['timeframes'] = timeframes
        if min_confidence is not None:
            data['min_confidence'] = min_confidence
        
        # Convert datetime objects to ISO format strings
        if start_time:
            if isinstance(start_time, datetime):
                data['start_time'] = start_time.isoformat()
            else:
                data['start_time'] = start_time
        
        if end_time:
            if isinstance(end_time, datetime):
                data['end_time'] = end_time.isoformat()
            else:
                data['end_time'] = end_time
        
        # Make request
        async with session.post(
            f'{self.base_url}/signals/filter',
            params={'limit': limit, 'offset': offset},
            json=data
        ) as response:
            if response.status == 200:
                return await response.json()
            else:
                error_text = await response.text()
                logger.error(f"Error filtering signals: {response.status} - {error_text}")
                response.raise_for_status()
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the signal system.
        
        Returns:
            Dictionary of statistics
        """
        session = await self._get_session()
        
        # Make request
        async with session.get(f'{self.base_url}/stats') as response:
            if response.status == 200:
                return await response.json()
            else:
                error_text = await response.text()
                logger.error(f"Error getting stats: {response.status} - {error_text}")
                response.raise_for_status()
    
    def add_signal_handler(self, handler: Callable[[Dict[str, Any]], Union[None, Awaitable[None]]]):
        """
        Add a handler for real-time signal updates.
        
        The handler will be called with the signal data when a new signal is received.
        
        Args:
            handler: Function or coroutine function to call when a new signal is received
        """
        self._signal_handlers.append(handler)
    
    async def _handle_signal(self, signal: Dict[str, Any]):
        """
        Handle a signal from the WebSocket connection.
        
        Args:
            signal: Signal data
        """
        for handler in self._signal_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(signal)
                else:
                    handler(signal)
            except Exception as e:
                logger.error(f"Error in signal handler: {e}")
    
    async def _websocket_listener(self):
        """Listen for messages on the WebSocket connection."""
        while True:
            try:
                async with websockets.connect(self.websocket_url) as websocket:
                    self.websocket = websocket
                    
                    # Send initial subscription
                    await websocket.send(json.dumps({
                        "trading_pairs": None,
                        "agent_types": None,
                        "signal_types": None,
                        "min_confidence": 0.0
                    }))
                    
                    # Receive confirmation
                    response = await websocket.recv()
                    response_data = json.loads(response)
                    
                    if response_data.get("type") == "subscription_success":
                        logger.info("WebSocket subscription successful")
                    else:
                        logger.warning(f"Unexpected response to subscription: {response_data}")
                    
                    # Listen for messages
                    while True:
                        message = await websocket.recv()
                        data = json.loads(message)
                        
                        if data.get("type") == "signal":
                            await self._handle_signal(data.get("data", {}))
                        else:
                            logger.debug(f"Received non-signal message: {data}")
            
            except (websockets.ConnectionClosed, ConnectionRefusedError) as e:
                logger.warning(f"WebSocket connection closed: {e}. Reconnecting in 5 seconds...")
                await asyncio.sleep(5)
                continue
            
            except Exception as e:
                logger.error(f"Error in WebSocket listener: {e}. Reconnecting in 5 seconds...")
                await asyncio.sleep(5)
                continue
    
    async def subscribe(self,
                       trading_pairs: Optional[List[str]] = None,
                       agent_types: Optional[List[str]] = None,
                       signal_types: Optional[List[str]] = None,
                       min_confidence: float = 0.0):
        """
        Subscribe to real-time signal updates.
        
        Args:
            trading_pairs: List of trading pairs to subscribe to
            agent_types: List of agent types to subscribe to
            signal_types: List of signal types to subscribe to
            min_confidence: Minimum confidence threshold
        """
        # Start WebSocket listener if not already running
        if self.websocket_task is None:
            self.websocket_task = asyncio.create_task(self._websocket_listener())
        
        # Send subscription request once WebSocket is connected
        while self.websocket is None:
            await asyncio.sleep(0.1)
        
        # Send subscription request
        subscription = {
            "type": "subscription",
            "data": {
                "trading_pairs": trading_pairs,
                "agent_types": agent_types,
                "signal_types": signal_types,
                "min_confidence": min_confidence
            }
        }
        
        await self.websocket.send(json.dumps(subscription))
    
    async def close(self):
        """Close the client and clean up resources."""
        # Cancel WebSocket task
        if self.websocket_task:
            self.websocket_task.cancel()
            try:
                await self.websocket_task
            except asyncio.CancelledError:
                pass
            self.websocket_task = None
        
        # Close HTTP session
        if self._session and not self._session.closed:
            await self._session.close()
        
        logger.info("Signal client closed") 