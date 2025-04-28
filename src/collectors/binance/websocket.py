"""
Binance WebSocket client for subscribing to real-time data streams.

This module provides a WebSocket client for connecting to Binance's WebSocket API
and handling subscriptions to various data streams.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Union

import websockets
from websockets.exceptions import ConnectionClosed

from .binance.constants import (
    WS_API_URL,
    WS_PING_INTERVAL,
    WS_RECONNECT_DELAY,
    WS_TIMEOUT
)

logger = logging.getLogger(__name__)


class BinanceWebSocketClient:
    """
    WebSocket client for Binance API.
    
    Handles connection, subscription management, and message processing
    for Binance WebSocket streams.
    """
    
    def __init__(
        self,
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None,
        base_url: str = WS_API_URL,
        ping_interval: int = WS_PING_INTERVAL,
        timeout: int = WS_TIMEOUT,
        reconnect_delay: int = WS_RECONNECT_DELAY
    ):
        """
        Initialize the WebSocket client.
        
        Args:
            on_message: Callback function for all messages
            base_url: Base WebSocket URL
            ping_interval: Interval for sending ping frames in seconds
            timeout: Connection timeout in seconds
            reconnect_delay: Delay before reconnecting in seconds
        """
        self.base_url = base_url
        self.ping_interval = ping_interval
        self.timeout = timeout
        self.reconnect_delay = reconnect_delay
        
        # Global message handler
        self.on_message = on_message
        
        # Stream-specific callbacks
        self.callbacks: Dict[str, List[Callable]] = {}
        
        # Active subscriptions
        self.subscriptions: Set[str] = set()
        
        # Connection objects
        self.connection = None
        self.task = None
        self.running = False
        self.last_recv_time = 0
        
    async def connect(self) -> bool:
        """
        Establish WebSocket connection and start message handling.
        
        Returns:
            Success status
        """
        if self.running:
            return True
            
        try:
            # Create a single connection for combined streams
            self.connection = await websockets.connect(
                f"{self.base_url}/stream",
                ping_interval=self.ping_interval,
                close_timeout=self.timeout
            )
            
            # Start message handling task
            self.task = asyncio.create_task(self._handle_messages())
            self.running = True
            
            # Resubscribe to active streams
            if self.subscriptions:
                await self._subscribe(list(self.subscriptions))
                
            logger.info("Connected to Binance WebSocket API")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Binance WebSocket: {str(e)}")
            self.running = False
            return False
            
    async def disconnect(self) -> bool:
        """
        Close WebSocket connection.
        
        Returns:
            Success status
        """
        if not self.running:
            return True
            
        try:
            # Cancel message handling task
            if self.task:
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
                self.task = None
                
            # Close connection
            if self.connection:
                await self.connection.close()
                self.connection = None
                
            self.running = False
            logger.info("Disconnected from Binance WebSocket API")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from Binance WebSocket: {str(e)}")
            return False
            
    async def add_stream(self, stream: str) -> bool:
        """
        Subscribe to a stream.
        
        Args:
            stream: Stream name (e.g., 'btcusdt@trade')
            
        Returns:
            Success status
        """
        if stream in self.subscriptions:
            return True
            
        self.subscriptions.add(stream)
        
        if self.running:
            return await self._subscribe([stream])
        return True
        
    async def remove_stream(self, stream: str) -> bool:
        """
        Unsubscribe from a stream.
        
        Args:
            stream: Stream name (e.g., 'btcusdt@trade')
            
        Returns:
            Success status
        """
        if stream not in self.subscriptions:
            return True
            
        self.subscriptions.remove(stream)
        
        if self.running:
            return await self._unsubscribe([stream])
        return True
        
    def add_callback(self, stream: str, callback: Callable) -> None:
        """
        Add a callback for a specific stream.
        
        Args:
            stream: Stream name
            callback: Callback function
        """
        if stream not in self.callbacks:
            self.callbacks[stream] = []
            
        self.callbacks[stream].append(callback)
        
    def remove_callback(self, stream: str, callback: Callable) -> bool:
        """
        Remove a callback for a specific stream.
        
        Args:
            stream: Stream name
            callback: Callback function to remove
            
        Returns:
            Success status
        """
        if stream not in self.callbacks:
            return False
            
        try:
            self.callbacks[stream].remove(callback)
            return True
        except ValueError:
            return False
            
    async def _subscribe(self, streams: List[str]) -> bool:
        """
        Send subscription request.
        
        Args:
            streams: List of stream names
            
        Returns:
            Success status
        """
        if not self.connection:
            return False
            
        try:
            request = {
                "method": "SUBSCRIBE",
                "params": streams,
                "id": int(asyncio.get_event_loop().time() * 1000)
            }
            
            await self.connection.send(json.dumps(request))
            logger.debug(f"Subscribed to streams: {streams}")
            return True
            
        except Exception as e:
            logger.error(f"Error subscribing to streams: {str(e)}")
            return False
            
    async def _unsubscribe(self, streams: List[str]) -> bool:
        """
        Send unsubscription request.
        
        Args:
            streams: List of stream names
            
        Returns:
            Success status
        """
        if not self.connection:
            return False
            
        try:
            request = {
                "method": "UNSUBSCRIBE",
                "params": streams,
                "id": int(asyncio.get_event_loop().time() * 1000)
            }
            
            await self.connection.send(json.dumps(request))
            logger.debug(f"Unsubscribed from streams: {streams}")
            return True
            
        except Exception as e:
            logger.error(f"Error unsubscribing from streams: {str(e)}")
            return False
            
    async def _handle_messages(self) -> None:
        """
        Process incoming WebSocket messages.
        """
        while True:
            try:
                if not self.connection:
                    break
                    
                # Receive message
                message = await self.connection.recv()
                self.last_recv_time = asyncio.get_event_loop().time()
                
                # Parse message
                data = json.loads(message)
                
                # Handle subscription response
                if isinstance(data, dict) and "result" in data:
                    logger.debug(f"Subscription response: {data}")
                    continue
                    
                # Get stream name and data
                stream_name = None
                stream_data = data
                
                if isinstance(data, dict) and "stream" in data:
                    stream_name = data["stream"]
                    stream_data = data["data"]
                    
                # Process message
                await self._process_message(stream_name, stream_data)
                
            except asyncio.CancelledError:
                # Task was cancelled, exit cleanly
                break
                
            except ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {str(e)}")
                await self._handle_reconnect()
                break
                
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {str(e)}")
                
    async def _process_message(self, stream_name: Optional[str], data: Any) -> None:
        """
        Process a message and call appropriate callbacks.
        
        Args:
            stream_name: Stream name
            data: Message data
        """
        # Call global message handler
        if self.on_message:
            try:
                await asyncio.ensure_future(self._call_handler(self.on_message, data))
            except Exception as e:
                logger.error(f"Error in global message handler: {str(e)}")
                
        # Call stream-specific callbacks
        if stream_name and stream_name in self.callbacks:
            for callback in self.callbacks[stream_name]:
                try:
                    await asyncio.ensure_future(self._call_handler(callback, data))
                except Exception as e:
                    logger.error(f"Error in stream callback for {stream_name}: {str(e)}")
                    
    async def _call_handler(self, handler: Callable, data: Any) -> None:
        """
        Call message handler, supporting both sync and async callbacks.
        
        Args:
            handler: Callback function
            data: Message data
        """
        if asyncio.iscoroutinefunction(handler):
            await handler(data)
        else:
            handler(data)
            
    async def _handle_reconnect(self) -> None:
        """
        Handle reconnection logic.
        """
        self.connection = None
        self.running = False
        
        # Wait before reconnecting
        logger.info(f"Reconnecting in {self.reconnect_delay} seconds...")
        await asyncio.sleep(self.reconnect_delay)
        
        # Attempt to reconnect
        reconnect_attempts = 0
        max_attempts = 5
        
        while reconnect_attempts < max_attempts:
            reconnect_attempts += 1
            
            try:
                logger.info(f"Attempting to reconnect (attempt {reconnect_attempts}/{max_attempts})...")
                success = await self.connect()
                
                if success:
                    logger.info("Successfully reconnected")
                    return
                    
            except Exception as e:
                logger.error(f"Failed to reconnect: {str(e)}")
                
            # Exponential backoff
            delay = self.reconnect_delay * (2 ** (reconnect_attempts - 1))
            await asyncio.sleep(delay)
            
        logger.error(f"Failed to reconnect after {max_attempts} attempts")


# Example usage
async def example_usage():
    """Example of using the BinanceWebSocketClient."""
    # Create client with a message handler
    client = BinanceWebSocketClient(
        on_message=lambda msg: print(f"Received message: {msg}")
    )
    
    try:
        # Connect to WebSocket
        await client.connect()
        
        # Subscribe to streams
        await client.add_stream("btcusdt@trade")
        
        # Add a specific callback for the stream
        client.add_callback("btcusdt@trade", lambda msg: print(f"Trade: {msg['p']} {msg['q']}"))
        
        # Wait for messages
        await asyncio.sleep(30)
        
    finally:
        # Clean up
        await client.disconnect()
        

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_usage()) 