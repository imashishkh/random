"""
WebSocket Transport Implementation for Exchange Communications

This module provides a WebSocket-based transport implementation for
communicating with cryptocurrency exchanges in real-time.
"""
import asyncio
import json
import logging
import time
import hmac
import hashlib
import uuid
from typing import Dict, List, Set, Any, Optional, Union, Callable, Awaitable
from datetime import datetime, timedelta
from urllib.parse import urlencode

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed

from .transport.base import (
    TransportType,
    AuthType,
    ConnectionStatus,
    RequestMetadata,
    ResponseMetadata,
    Request,
    Response,
    RetryPolicy,
    BaseTransport,
    DefaultRetryPolicy
)

# Configure logger
logger = logging.getLogger(__name__)

class WebSocketTransport(BaseTransport):
    """
    WebSocket transport implementation.
    
    This class provides WebSocket transport functionality for real-time
    communication with cryptocurrency exchanges.
    """
    
    def __init__(
        self,
        exchange: str,
        base_url: str,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        extra_auth: Optional[Dict[str, Any]] = None,
        ping_interval: int = 30,
        ping_timeout: int = 10,
        close_timeout: int = 10,
        reconnect_delay: int = 5,
        max_reconnect_attempts: int = 5,
        connection_timeout: int = 30,
        buffer_size: int = 1000,
        enable_rate_limit: bool = True,
        testnet: bool = False,
        exchange_options: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the WebSocket transport.
        
        Args:
            exchange: Name of the exchange
            base_url: Base WebSocket URL for the exchange
            api_key: API key for authentication
            api_secret: API secret for authentication
            extra_auth: Extra authentication parameters
            ping_interval: Interval in seconds between ping messages
            ping_timeout: Timeout in seconds for ping responses
            close_timeout: Timeout in seconds for closing connections
            reconnect_delay: Initial delay in seconds between reconnection attempts
            max_reconnect_attempts: Maximum number of reconnection attempts
            connection_timeout: Timeout in seconds for establishing connections
            buffer_size: Maximum number of messages to buffer
            enable_rate_limit: Whether to enable rate limiting
            testnet: Whether to use the testnet
            exchange_options: Additional options for the exchange
        """
        # Initialize base class with the determined auth type
        auth_type = AuthType.API_KEY if api_key and api_secret else AuthType.NONE
        super().__init__(
            exchange=exchange,
            base_url=base_url,
            auth_type=auth_type,
            timeout=connection_timeout,
            max_retries=max_reconnect_attempts,
            retry_policy=None,  # WebSocket uses custom reconnection logic
            enable_rate_limit=enable_rate_limit
        )
        
        # Store authentication credentials
        self.api_key = api_key
        self.api_secret = api_secret
        self.extra_auth = extra_auth or {}
        self.testnet = testnet
        
        # WebSocket connection parameters
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.close_timeout = close_timeout
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        self.connection_timeout = connection_timeout
        self.buffer_size = buffer_size
        
        # Exchange options
        self.exchange_options = exchange_options or {}
        
        # Connection state
        self.reconnect_attempts = 0
        self.last_message_time = None
        
        # WebSocket connection
        self.websocket = None
        self.connection_task = None
        self.ping_task = None
        
        # Stream subscriptions
        self.subscriptions: Dict[str, Callable[[Response], None]] = {}
        self.active_streams: Set[str] = set()
        
        # Message buffer for disconnections
        self.message_buffer: List[Dict[str, Any]] = []
        
        # Authentication state
        self.listen_key = None
        self.listen_key_keep_alive_task = None
        
        # Locks
        self._connection_lock = asyncio.Lock()
    
    @property
    def transport_type(self) -> TransportType:
        """Get the transport type."""
        return TransportType.WEBSOCKET
    
    async def connect(self) -> bool:
        """
        Connect to the exchange WebSocket API.
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
        # Skip if already connected
        if self.status == ConnectionStatus.CONNECTED and self.websocket:
            logger.debug(f"Already connected to {self.exchange} WebSocket API")
            return True
        
        # Acquire lock to prevent concurrent connection attempts
        async with self._connection_lock:
            try:
                # Update status to connecting
                self._update_status(ConnectionStatus.CONNECTING)
                
                # Get appropriate URL (may involve authentication)
                url = await self._get_websocket_url()
                
                # Establish WebSocket connection with timeout
                connect_task = websockets.connect(
                    url,
                    ping_interval=self.ping_interval,
                    ping_timeout=self.ping_timeout,
                    close_timeout=self.close_timeout,
                    extra_headers=self._get_auth_headers()
                )
                
                try:
                    self.websocket = await asyncio.wait_for(
                        connect_task,
                        timeout=self.connection_timeout
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Timeout connecting to {self.exchange} WebSocket API")
                    self._update_status(ConnectionStatus.ERROR, "Connection timeout")
                    return False
                
                # Reset reconnect attempts on successful connection
                self.reconnect_attempts = 0
                
                # Update status
                self._update_status(ConnectionStatus.CONNECTED)
                self.last_message_time = time.time()
                
                # Start ping/keepalive task
                self.ping_task = asyncio.create_task(self._ping_loop())
                
                # Start listen key keep-alive task if authenticated
                if self.auth_type == AuthType.API_KEY and self.listen_key:
                    self.listen_key_keep_alive_task = asyncio.create_task(
                        self._keep_listen_key_alive()
                    )
                
                # Start message handler task
                self.connection_task = asyncio.create_task(self._message_handler())
                
                # Re-subscribe to active streams
                if self.active_streams:
                    for stream in self.active_streams:
                        await self._subscribe_to_stream(stream)
                
                logger.info(f"Connected to {self.exchange} WebSocket API")
                return True
                
            except Exception as e:
                logger.error(f"Error connecting to {self.exchange} WebSocket API: {str(e)}")
                self._update_status(ConnectionStatus.ERROR, str(e))
                return False
    
    async def disconnect(self) -> bool:
        """
        Disconnect from the exchange WebSocket API.
        
        Returns:
            bool: True if disconnection was successful, False otherwise
        """
        try:
            # Cancel ping task
            if self.ping_task and not self.ping_task.done():
                self.ping_task.cancel()
                try:
                    await self.ping_task
                except asyncio.CancelledError:
                    pass
            
            # Cancel listen key keep-alive task
            if self.listen_key_keep_alive_task and not self.listen_key_keep_alive_task.done():
                self.listen_key_keep_alive_task.cancel()
                try:
                    await self.listen_key_keep_alive_task
                except asyncio.CancelledError:
                    pass
            
            # Cancel connection task
            if self.connection_task and not self.connection_task.done():
                self.connection_task.cancel()
                try:
                    await self.connection_task
                except asyncio.CancelledError:
                    pass
            
            # Close WebSocket connection
            if self.websocket:
                await self.websocket.close(
                    code=1000,
                    reason="Client requested disconnect"
                )
                self.websocket = None
            
            # Update status
            self._update_status(ConnectionStatus.DISCONNECTED)
            
            # Clear active streams
            self.active_streams.clear()
            
            logger.info(f"Disconnected from {self.exchange} WebSocket API")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from {self.exchange} WebSocket API: {str(e)}")
            return False
    
    async def is_connected(self) -> bool:
        """
        Check if the WebSocket is connected.
        
        Returns:
            bool: True if connected, False otherwise
        """
        if self.status != ConnectionStatus.CONNECTED or not self.websocket:
            return False
        
        try:
            # Check if the WebSocket is open
            return self.websocket.open
        except Exception:
            return False
    
    async def send(self, request: Request) -> Response:
        """
        Send a request over the WebSocket connection.
        
        Args:
            request: Request to send
            
        Returns:
            Response: Response from the exchange
        """
        if not self.websocket or not await self.is_connected():
            await self.connect()
            if not self.websocket or not await self.is_connected():
                return Response(
                    data=None,
                    metadata=ResponseMetadata(
                        status_code=500,
                        error="Not connected to the WebSocket"
                    )
                )
        
        # Prepare message to send
        message = {
            "method": request.metadata.method,
            "params": request.params,
            "id": request.metadata.get("id", str(uuid.uuid4()))
        }
        
        if request.path:
            message["path"] = request.path
        
        # Add any additional data
        message.update(request.data)
        
        # Send the message
        try:
            start_time = time.time()
            await self.websocket.send(json.dumps(message))
            
            # For synchronous requests (those with an ID), we need to wait for a response
            if "id" in message:
                # Wait for response with matching ID
                response_data = await self._wait_for_response(message["id"], request.metadata.timeout)
                
                latency = time.time() - start_time
                
                # Update metrics
                self.update_metrics(latency=latency)
                
                if response_data:
                    return Response(
                        data=response_data,
                        metadata=ResponseMetadata(
                            status_code=200,
                            latency=latency
                        ),
                        raw=response_data
                    )
                else:
                    return Response(
                        data=None,
                        metadata=ResponseMetadata(
                            status_code=408,  # Request Timeout
                            error="Timed out waiting for response",
                            latency=latency
                        )
                    )
            else:
                # Asynchronous message (no response expected)
                return Response(
                    data={"success": True},
                    metadata=ResponseMetadata(
                        status_code=200,
                        latency=time.time() - start_time
                    )
                )
                
        except Exception as e:
            latency = time.time() - start_time
            self.update_metrics(latency=latency, is_error=True)
            
            return Response(
                data=None,
                metadata=ResponseMetadata(
                    status_code=500,
                    error=str(e),
                    latency=latency
                )
            )
    
    async def subscribe(self, channel: str, callback: Callable[[Response], None]) -> bool:
        """
        Subscribe to a WebSocket channel.
        
        Args:
            channel: Channel to subscribe to
            callback: Function to call with received data
            
        Returns:
            bool: True if subscription was successful, False otherwise
        """
        # Store the subscription
        self.subscriptions[channel] = callback
        
        # Only add to active streams and send subscription if connected
        if self.status == ConnectionStatus.CONNECTED and self.websocket:
            success = await self._subscribe_to_stream(channel)
            if success:
                self.active_streams.add(channel)
            return success
        else:
            # Queue for subscription when connected
            self.active_streams.add(channel)
            return True
    
    async def unsubscribe(self, channel: str) -> bool:
        """
        Unsubscribe from a WebSocket channel.
        
        Args:
            channel: Channel to unsubscribe from
            
        Returns:
            bool: True if unsubscription was successful, False otherwise
        """
        # Remove from subscriptions
        if channel in self.subscriptions:
            del self.subscriptions[channel]
        
        # Only send unsubscription if connected
        if self.status == ConnectionStatus.CONNECTED and self.websocket:
            success = await self._unsubscribe_from_stream(channel)
            if success:
                self.active_streams.discard(channel)
            return success
        else:
            # Just remove from active streams if not connected
            self.active_streams.discard(channel)
            return True
    
    async def _get_websocket_url(self) -> str:
        """
        Get the WebSocket URL, handling any exchange-specific logic.
        
        Returns:
            str: WebSocket URL
        """
        # Override with custom base URL if provided
        url = self.base_url
        
        # Handle exchange-specific URL formatting
        if self.exchange.lower() == 'binance':
            # For authenticated streams (user data), need to get a listen key
            if self.auth_type == AuthType.API_KEY and self.api_key and self.api_secret:
                if not self.listen_key:
                    await self._get_listen_key()
                
                # Check if we need to use a specific stream format
                if self.listen_key:
                    if 'stream.binance' in url:
                        # For combined streams on main API
                        return f"{url}/ws/{self.listen_key}"
                    elif 'testnet.binance' in url:
                        # For testnet
                        return f"{url}/ws/{self.listen_key}"
            
            # For public streams, use standard URL
            return f"{url}/ws"
        
        # Default case - just use the provided URL
        return url
    
    async def _get_listen_key(self) -> None:
        """
        Get a listen key for authenticated WebSocket streams.
        """
        if not self.api_key:
            logger.error("Cannot get listen key without API key")
            return
        
        try:
            # Determine the API URL based on the exchange
            if self.exchange.lower() == 'binance':
                # Extract the base domain from the WebSocket URL
                domain = self.base_url.split('/ws')[0]
                if not domain.startswith('http'):
                    # Convert ws:// to https://
                    domain = domain.replace('ws://', 'https://')
                    domain = domain.replace('wss://', 'https://')
                
                # Use appropriate endpoint based on URL
                if 'testnet.binance' in domain:
                    api_url = 'https://testnet.binance.vision/api/v3/userDataStream'
                elif 'binance.com' in domain or 'stream.binance' in domain:
                    api_url = 'https://api.binance.com/api/v3/userDataStream'
                else:
                    api_url = f"{domain}/api/v3/userDataStream"
            else:
                logger.error(f"Getting listen key not implemented for {self.exchange}")
                return
            
            # Prepare headers
            headers = {
                'X-MBX-APIKEY': self.api_key
            }
            
            # Make the request
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.listen_key = result.get('listenKey')
                        logger.info(f"Got listen key for {self.exchange}")
                    else:
                        error = await response.text()
                        logger.error(f"Failed to get listen key: {error}")
        
        except Exception as e:
            logger.error(f"Error getting listen key: {str(e)}")
    
    async def _keep_listen_key_alive(self) -> None:
        """
        Periodically extend the validity of the listen key.
        """
        if not self.listen_key or not self.api_key:
            return
        
        try:
            # Determine the API URL based on the exchange
            if self.exchange.lower() == 'binance':
                # Extract the base domain from the WebSocket URL
                domain = self.base_url.split('/ws')[0]
                if not domain.startswith('http'):
                    # Convert ws:// to https://
                    domain = domain.replace('ws://', 'https://')
                    domain = domain.replace('wss://', 'https://')
                
                # Use appropriate endpoint based on URL
                if 'testnet.binance' in domain:
                    api_url = 'https://testnet.binance.vision/api/v3/userDataStream'
                elif 'binance.com' in domain or 'stream.binance' in domain:
                    api_url = 'https://api.binance.com/api/v3/userDataStream'
                else:
                    api_url = f"{domain}/api/v3/userDataStream"
            else:
                logger.error(f"Keeping listen key alive not implemented for {self.exchange}")
                return
            
            # Prepare headers
            headers = {
                'X-MBX-APIKEY': self.api_key
            }
            
            # Keep-alive loop (every 30 minutes)
            while True:
                await asyncio.sleep(30 * 60)  # 30 minutes
                
                if not self.listen_key:
                    break
                
                try:
                    # Make the PUT request to keep listen key alive
                    async with aiohttp.ClientSession() as session:
                        params = {'listenKey': self.listen_key}
                        async with session.put(api_url, headers=headers, params=params) as response:
                            if response.status == 200:
                                logger.debug(f"Refreshed listen key for {self.exchange}")
                            else:
                                error = await response.text()
                                logger.error(f"Failed to refresh listen key: {error}")
                                
                                # Try to get a new listen key
                                await self._get_listen_key()
                                
                                # If we couldn't get a new listen key, reconnect
                                if not self.listen_key:
                                    await self.disconnect()
                                    await self.connect()
                
                except Exception as e:
                    logger.error(f"Error refreshing listen key: {str(e)}")
        
        except asyncio.CancelledError:
            logger.debug("Listen key keep-alive task cancelled")
        
        except Exception as e:
            logger.error(f"Error in listen key keep-alive loop: {str(e)}")
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """
        Get authentication headers for the WebSocket connection.
        
        Returns:
            Dict: Authentication headers
        """
        headers = {}
        
        if self.auth_type == AuthType.API_KEY and self.api_key:
            headers['X-MBX-APIKEY'] = self.api_key
        
        return headers
    
    async def _subscribe_to_stream(self, channel: str) -> bool:
        """
        Send a subscription message to the server.
        
        Args:
            channel: Channel to subscribe to
            
        Returns:
            bool: True if subscription was successful, False otherwise
        """
        try:
            # Handle exchange-specific subscription logic
            if self.exchange.lower() == 'binance':
                # Binance has different subscription formats based on API
                if '@' in channel:
                    # Standard public channel (e.g., "btcusdt@trade")
                    message = {
                        "method": "SUBSCRIBE",
                        "params": [channel],
                        "id": int(time.time() * 1000)
                    }
                else:
                    # Custom channel format or user data stream
                    # For user data streams, the channel is already defined by the listen key
                    return True
                
                # Send subscription message
                if self.websocket:
                    await self.websocket.send(json.dumps(message))
                    logger.debug(f"Sent subscription to {channel}")
                    return True
            else:
                # Generic subscription message format
                message = {
                    "op": "subscribe",
                    "channel": channel,
                    "id": str(uuid.uuid4())
                }
                
                # Send subscription message
                if self.websocket:
                    await self.websocket.send(json.dumps(message))
                    logger.debug(f"Sent subscription to {channel}")
                    return True
            
            return False
        
        except Exception as e:
            logger.error(f"Error subscribing to {channel}: {str(e)}")
            return False
    
    async def _unsubscribe_from_stream(self, channel: str) -> bool:
        """
        Send an unsubscription message to the server.
        
        Args:
            channel: Channel to unsubscribe from
            
        Returns:
            bool: True if unsubscription was successful, False otherwise
        """
        try:
            # Handle exchange-specific unsubscription logic
            if self.exchange.lower() == 'binance':
                # Binance has different unsubscription formats based on API
                if '@' in channel:
                    # Standard public channel (e.g., "btcusdt@trade")
                    message = {
                        "method": "UNSUBSCRIBE",
                        "params": [channel],
                        "id": int(time.time() * 1000)
                    }
                else:
                    # Custom channel format or user data stream
                    # For user data streams, can't unsubscribe individually
                    return True
                
                # Send unsubscription message
                if self.websocket:
                    await self.websocket.send(json.dumps(message))
                    logger.debug(f"Sent unsubscription to {channel}")
                    return True
            else:
                # Generic unsubscription message format
                message = {
                    "op": "unsubscribe",
                    "channel": channel,
                    "id": str(uuid.uuid4())
                }
                
                # Send unsubscription message
                if self.websocket:
                    await self.websocket.send(json.dumps(message))
                    logger.debug(f"Sent unsubscription to {channel}")
                    return True
            
            return False
        
        except Exception as e:
            logger.error(f"Error unsubscribing from {channel}: {str(e)}")
            return False
    
    async def _message_handler(self) -> None:
        """
        Handle incoming WebSocket messages.
        """
        if not self.websocket:
            return
        
        try:
            # Process messages until connection is closed
            async for message in self.websocket:
                self.last_message_time = time.time()
                
                try:
                    # Parse message as JSON
                    data = json.loads(message)
                    
                    # Process the message
                    await self._process_message(data)
                    
                except json.JSONDecodeError:
                    logger.warning(f"Received non-JSON message: {message}")
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}")
            
            # Connection closed
            logger.info("WebSocket connection closed")
            
            # Update status if not already disconnected
            if self.status not in [ConnectionStatus.DISCONNECTED, ConnectionStatus.ERROR]:
                self._update_status(ConnectionStatus.DISCONNECTED)
            
        except ConnectionClosed as e:
            logger.warning(f"WebSocket connection closed unexpectedly: {e.reason}")
            
            # Update status
            self._update_status(ConnectionStatus.ERROR, str(e))
            
            # Attempt to reconnect
            asyncio.create_task(self._reconnect())
            
        except asyncio.CancelledError:
            logger.debug("Message handler task cancelled")
            
        except Exception as e:
            logger.error(f"Error in message handler: {str(e)}")
            
            # Update status
            self._update_status(ConnectionStatus.ERROR, str(e))
            
            # Attempt to reconnect
            asyncio.create_task(self._reconnect())
    
    async def _process_message(self, data: Dict[str, Any]) -> None:
        """
        Process a received WebSocket message.
        
        Args:
            data: Message data
        """
        # Update performance metrics
        self.requests_count += 1
        
        # Check if this is a response to a sync request
        if 'id' in data:
            # Store the response for a waiting request
            self._store_response(data)
            return
        
        # Determine the channel/stream from the message
        channel = self._extract_channel_from_message(data)
        
        if not channel:
            logger.debug(f"Unknown message format, no channel identified: {data}")
            return
        
        # Find the corresponding callback
        callback = self.subscriptions.get(channel)
        
        if callback:
            # Create a response object
            response = Response(
                data=data,
                metadata=ResponseMetadata(
                    timestamp=time.time(),
                    status_code=200
                ),
                raw=data
            )
            
            # Call the callback
            try:
                callback(response)
            except Exception as e:
                logger.error(f"Error in callback for channel {channel}: {str(e)}")
        else:
            logger.debug(f"No callback for channel {channel}")
    
    def _extract_channel_from_message(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Extract the channel/stream name from a message.
        
        Args:
            data: Message data
            
        Returns:
            str: Channel name or None if not found
        """
        # Binance format
        if self.exchange.lower() == 'binance':
            # Public streams (combined stream format)
            if 'stream' in data:
                return data['stream']
            
            # Public streams (single stream format)
            if 'e' in data and 's' in data:
                event_type = data['e']
                symbol = data['s'].lower()
                
                # Common Binance event types
                if event_type == 'trade':
                    return f"{symbol}@trade"
                elif event_type == 'kline':
                    interval = data['k']['i']
                    return f"{symbol}@kline_{interval}"
                elif event_type == 'ticker':
                    return f"{symbol}@ticker"
                elif event_type == 'depth':
                    return f"{symbol}@depth"
                elif event_type == 'aggTrade':
                    return f"{symbol}@aggTrade"
                elif event_type == 'bookTicker':
                    return f"{symbol}@bookTicker"
            
            # User data streams
            if 'e' in data:
                event_type = data['e']
                
                # Common user data event types
                if event_type == 'outboundAccountPosition':
                    return 'user.account'
                elif event_type == 'executionReport':
                    return 'user.order'
                elif event_type == 'balanceUpdate':
                    return 'user.balance'
        
        # Generic fallback
        if 'channel' in data:
            return data['channel']
        if 'topic' in data:
            return data['topic']
        
        # No channel identified
        return None
    
    def _store_response(self, data: Dict[str, Any]) -> None:
        """
        Store a response for a synchronized request.
        
        Args:
            data: Response data
        """
        # Add to message buffer with ID as key for retrieval
        message_id = str(data.get('id'))
        
        # Store in buffer with a tuple of (timestamp, data)
        # Clear buffer if it exceeds the limit
        if len(self.message_buffer) >= self.buffer_size:
            self.message_buffer.pop(0)
        
        self.message_buffer.append((message_id, time.time(), data))
    
    async def _wait_for_response(self, message_id: str, timeout: float) -> Optional[Dict[str, Any]]:
        """
        Wait for a response to a specific request.
        
        Args:
            message_id: ID of the request
            timeout: Maximum time to wait in seconds
            
        Returns:
            Optional[Dict]: Response data or None if timed out
        """
        message_id = str(message_id)
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Check if response is in buffer
            for i, (stored_id, timestamp, data) in enumerate(self.message_buffer):
                if stored_id == message_id:
                    # Remove from buffer to avoid memory leaks
                    self.message_buffer.pop(i)
                    return data
            
            # Wait a bit before checking again
            await asyncio.sleep(0.01)
        
        # Timeout reached
        return None
    
    async def _ping_loop(self) -> None:
        """
        Send periodic ping messages to keep the connection alive.
        """
        try:
            while self.status == ConnectionStatus.CONNECTED and self.websocket:
                # Only send ping if no message received for a while
                if self.last_message_time and time.time() - self.last_message_time > self.ping_interval / 2:
                    await self._send_ping()
                
                # Wait for the next ping interval
                await asyncio.sleep(self.ping_interval)
        
        except asyncio.CancelledError:
            logger.debug("Ping loop cancelled")
        
        except Exception as e:
            logger.error(f"Error in ping loop: {str(e)}")
    
    async def _send_ping(self) -> None:
        """
        Send a ping message to the server.
        """
        if not self.websocket or not await self.is_connected():
            return
        
        try:
            # Handle exchange-specific ping formats
            if self.exchange.lower() == 'binance':
                # Binance uses standard WebSocket ping/pong
                await self.websocket.ping()
            else:
                # Generic ping format
                message = {
                    "op": "ping",
                    "id": str(uuid.uuid4())
                }
                await self.websocket.send(json.dumps(message))
            
            logger.debug("Sent ping message")
        
        except Exception as e:
            logger.error(f"Error sending ping: {str(e)}")
    
    async def _reconnect(self) -> None:
        """
        Attempt to reconnect to the WebSocket server.
        """
        # Skip if already reconnecting
        if self.status == ConnectionStatus.RECONNECTING:
            return
        
        # Update status
        self._update_status(ConnectionStatus.RECONNECTING)
        
        # Increment reconnect attempts
        self.reconnect_attempts += 1
        
        # Check if max reconnect attempts reached
        if self.reconnect_attempts > self.max_reconnect_attempts:
            logger.error(f"Max reconnect attempts ({self.max_reconnect_attempts}) reached")
            self._update_status(ConnectionStatus.ERROR, "Max reconnect attempts reached")
            return
        
        # Calculate delay with exponential backoff
        delay = self.reconnect_delay * (2 ** (self.reconnect_attempts - 1))
        logger.info(f"Reconnecting in {delay:.2f}s (attempt {self.reconnect_attempts}/{self.max_reconnect_attempts})")
        
        # Wait before reconnecting
        await asyncio.sleep(delay)
        
        # Attempt to reconnect
        success = await self.connect()
        
        if not success and self.reconnect_attempts < self.max_reconnect_attempts:
            # Try again
            asyncio.create_task(self._reconnect())
    
    def _update_status(self, status: ConnectionStatus, reason: Optional[str] = None) -> None:
        """
        Update the connection status.
        
        Args:
            status: New status
            reason: Reason for status change
        """
        self.status = status
        self.disconnect_reason = reason
        
        if status == ConnectionStatus.CONNECTED:
            self.connected_since = time.time()
        elif status == ConnectionStatus.DISCONNECTED or status == ConnectionStatus.ERROR:
            self.connected_since = None 