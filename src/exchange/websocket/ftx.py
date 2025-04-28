"""
FTX WebSocket client for real-time market data.

This module implements a WebSocket client for connecting to FTX
and receiving real-time market data and user notifications.
"""
import os
import json
import time
import asyncio
import logging
import hmac
import hashlib
from typing import Dict, List, Set, Any, Optional, Union, Callable, Awaitable, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlencode
import uuid

import websockets
import aiohttp

from .websocket.base import BaseWebSocketClient
from .websocket.models import (
    WebSocketMessage,
    WebSocketMessageType,
    WebSocketConnectionStatus,
    WebSocketError
)
from .websocket.handlers import (
    handle_ftx_trade,
    handle_ftx_ticker,
    handle_ftx_orderbook,
    handle_ftx_fills,
    handle_ftx_orders,
    get_ftx_handler_for_stream
)

# Configure logger
logger = logging.getLogger(__name__)

# FTX WebSocket URLs
FTX_STREAM_URL = "wss://ftx.com/ws/"
FTX_STREAM_TESTNET_URL = "wss://ftx.com/ws/"  # FTX doesn't have a separate testnet WebSocket

# API endpoints
REST_API_URL = "https://ftx.com/api"
REST_API_TESTNET_URL = "https://ftx.com/api"  # FTX doesn't have a separate testnet API

class FTXWebSocketClient(BaseWebSocketClient):
    """WebSocket client for FTX exchange."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        subaccount: Optional[str] = None,
        testnet: bool = False,
        ping_interval: int = 15,
        ping_timeout: int = 10,
        close_timeout: int = 10,
        reconnect_delay: int = 5,
        max_reconnect_attempts: int = 5,
        connection_timeout: int = 30,
        buffer_size: int = 1000
    ):
        """
        Initialize the FTX WebSocket client.
        
        Args:
            api_key: FTX API key (required for user data streams)
            api_secret: FTX API secret (required for user data streams)
            subaccount: FTX subaccount name (optional)
            testnet: Whether to use the testnet (Note: FTX doesn't have a separate testnet)
            ping_interval: Interval in seconds between ping messages
            ping_timeout: Timeout in seconds for ping responses
            close_timeout: Timeout in seconds for closing connections
            reconnect_delay: Initial delay in seconds between reconnection attempts
            max_reconnect_attempts: Maximum number of reconnection attempts
            connection_timeout: Timeout in seconds for establishing connections
            buffer_size: Maximum number of messages to buffer during disconnections
        """
        # FTX uses the same WebSocket URL for both testnet and mainnet
        ws_url = FTX_STREAM_URL
        
        # Initialize the base class
        super().__init__(
            url=ws_url,
            ping_interval=ping_interval,
            ping_timeout=ping_timeout,
            close_timeout=close_timeout,
            reconnect_delay=reconnect_delay,
            max_reconnect_attempts=max_reconnect_attempts,
            connection_timeout=connection_timeout,
            buffer_size=buffer_size
        )
        
        # Store API credentials
        self.api_key = api_key or os.environ.get('FTX_API_KEY')
        self.api_secret = api_secret or os.environ.get('FTX_API_SECRET')
        self.subaccount = subaccount or os.environ.get('FTX_SUBACCOUNT')
        self.testnet = testnet
        
        # REST API URL
        self.rest_api_url = REST_API_URL
        
        # WebSocket connection
        self.websocket = None
        self.authenticated = False
        
        # Stream management
        self.market_streams = set()
        self.user_streams = set()
        
        # Stream callbacks
        self.stream_callbacks = {}
        
        # Register message handlers
        self._register_message_handlers()
    
    def _register_message_handlers(self) -> None:
        """Register message handlers for different types of messages."""
        self.register_handler(WebSocketMessageType.TRADE, handle_ftx_trade)
        self.register_handler(WebSocketMessageType.TICKER, handle_ftx_ticker)
        self.register_handler(WebSocketMessageType.DEPTH, handle_ftx_orderbook)
        self.register_handler(WebSocketMessageType.USER_DATA, handle_ftx_fills)
        self.register_handler(WebSocketMessageType.ORDER_UPDATE, handle_ftx_orders)
    
    async def connect(self) -> bool:
        """
        Connect to the FTX WebSocket server.
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
        # Skip if already connected
        if self.is_connected:
            logger.debug("Already connected to FTX WebSocket")
            return True
        
        # Acquire lock to prevent concurrent connection attempts
        async with self._connection_lock:
            try:
                self._update_status(WebSocketConnectionStatus.CONNECTING)
                
                # Connect to the WebSocket server
                self.websocket = await websockets.connect(
                    self.url,
                    ping_interval=self.ping_interval,
                    ping_timeout=self.ping_timeout,
                    close_timeout=self.close_timeout,
                    max_size=None,  # No limit on message size
                    extra_headers=None,  # No extra headers needed for public streams
                    ssl=True
                )
                
                # Reset connection attempt counter
                self.reconnect_attempts = 0
                
                # Authenticate if API credentials are provided
                if self.api_key and self.api_secret:
                    auth_success = await self._authenticate()
                    if not auth_success:
                        logger.error("FTX WebSocket authentication failed")
                        await self.disconnect(
                            code=1000,
                            reason="Authentication failed"
                        )
                        return False
                
                # Subscribe to streams
                subscription_tasks = []
                
                # Subscribe to market streams
                for stream in self.market_streams:
                    subscription_tasks.append(self.subscribe(stream))
                
                # Subscribe to user streams if authenticated
                if self.authenticated and self.user_streams:
                    for stream in self.user_streams:
                        subscription_tasks.append(self.subscribe(stream))
                
                # Wait for subscriptions to complete
                if subscription_tasks:
                    results = await asyncio.gather(*subscription_tasks, return_exceptions=True)
                    if any(isinstance(result, Exception) for result in results):
                        logger.error("Some FTX WebSocket subscriptions failed")
                
                # Start listening for messages
                self.connection_task = asyncio.create_task(self._listen())
                
                # Update connection status
                self._update_status(WebSocketConnectionStatus.CONNECTED)
                self.connected_since = time.time()
                logger.info("Connected to FTX WebSocket")
                
                # Start ping task
                self.ping_task = asyncio.create_task(self._ping_loop())
                
                # Process any buffered messages
                if self.message_buffer:
                    await self.process_buffer()
                
                return True
                
            except Exception as e:
                logger.error(f"Failed to connect to FTX WebSocket: {str(e)}")
                self._update_status(
                    WebSocketConnectionStatus.ERROR,
                    f"Connection failed: {str(e)}"
                )
                return False
    
    async def _authenticate(self) -> bool:
        """
        Authenticate with the FTX WebSocket server.
        
        Returns:
            bool: True if authentication was successful, False otherwise
        """
        if not self.api_key or not self.api_secret:
            logger.warning("Cannot authenticate without API credentials")
            return False
        
        try:
            # Generate authentication timestamp
            ts = int(time.time() * 1000)
            
            # Generate signature
            signature_payload = f'{ts}websocket_login'
            signature = hmac.new(
                self.api_secret.encode(),
                signature_payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Create authentication message
            auth_message = {
                'op': 'login',
                'args': {
                    'key': self.api_key,
                    'sign': signature,
                    'time': ts
                }
            }
            
            # Add subaccount if provided
            if self.subaccount:
                auth_message['args']['subaccount'] = self.subaccount
            
            # Send authentication message
            await self.websocket.send(json.dumps(auth_message))
            
            # Wait for authentication response (with timeout)
            try:
                response = await asyncio.wait_for(
                    self.websocket.recv(),
                    timeout=self.connection_timeout
                )
                
                # Parse response
                response_data = json.loads(response)
                
                # Check for success
                if response_data.get('type') == 'subscribed' and response_data.get('channel') == 'fills':
                    self.authenticated = True
                    logger.info("Authenticated with FTX WebSocket")
                    return True
                else:
                    logger.error(f"FTX authentication failed: {response_data}")
                    return False
                
            except asyncio.TimeoutError:
                logger.error("Timeout waiting for FTX authentication response")
                return False
            
        except Exception as e:
            logger.error(f"Error during FTX authentication: {str(e)}")
            return False
    
    async def _listen(self) -> None:
        """Listen for messages from the WebSocket server."""
        try:
            while self.websocket and not self.websocket.closed:
                try:
                    # Wait for message with timeout
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=self.ping_interval + self.ping_timeout
                    )
                    
                    # Update last message time
                    self.last_message_time = time.time()
                    
                    # Increment message counter
                    self.messages_received += 1
                    
                    # Process message
                    await self._handle_message(message)
                    
                except asyncio.TimeoutError:
                    # No message received within timeout period
                    if self.is_connected:
                        current_time = time.time()
                        last_msg_time = self.last_message_time or 0
                        
                        if current_time - last_msg_time > self.ping_interval + self.ping_timeout:
                            logger.warning("No message received from FTX within timeout period")
                            # Try to send a ping to check connection
                            ping_success = await self.ping()
                            if not ping_success:
                                logger.error("FTX WebSocket connection appears to be dead, reconnecting")
                                await self.reconnect()
                                break
                
                except websockets.exceptions.ConnectionClosed as e:
                    logger.warning(f"FTX WebSocket connection closed: {e}")
                    if self.is_connected:
                        await self.reconnect()
                    break
                
                except Exception as e:
                    logger.error(f"Error processing FTX WebSocket message: {str(e)}")
                    self.errors_count += 1
        
        except Exception as e:
            logger.error(f"Error in FTX WebSocket listener: {str(e)}")
            if self.is_connected:
                await self.reconnect()
    
    async def _handle_message(self, message: str) -> None:
        """
        Process a raw message from the WebSocket server.
        
        Args:
            message: Raw message string
        """
        try:
            # Parse the JSON message
            data = json.loads(message)
            
            # Handle different message types
            message_type = data.get('type')
            
            if message_type == 'subscribed':
                # Subscription confirmation
                channel = data.get('channel')
                market = data.get('market', '')
                logger.debug(f"Successfully subscribed to FTX {channel} for {market}")
                return
            
            elif message_type == 'unsubscribed':
                # Unsubscription confirmation
                channel = data.get('channel')
                market = data.get('market', '')
                logger.debug(f"Successfully unsubscribed from FTX {channel} for {market}")
                return
            
            elif message_type == 'error':
                # Error message
                error_msg = data.get('msg', 'Unknown error')
                error_code = data.get('code', 0)
                logger.error(f"FTX WebSocket error: {error_msg} (code: {error_code})")
                
                error = self._handle_error(error_code, error_msg)
                
                # Create error message
                ws_message = WebSocketMessage(
                    msg_type=WebSocketMessageType.ERROR,
                    message_data={"error": error_msg, "code": error_code},
                    raw_data=data,
                    timestamp=int(time.time() * 1000),
                    event_datetime=datetime.now(),
                    stream=f"{data.get('channel', '')}/{data.get('market', '')}"
                )
                
                # Dispatch message
                await self._dispatch_message(ws_message)
                return
            
            elif message_type == 'info':
                # Information message
                info_msg = data.get('msg', '')
                logger.info(f"FTX WebSocket info: {info_msg}")
                return
            
            elif message_type == 'partial' or message_type == 'update':
                # Market data update
                channel = data.get('channel')
                market = data.get('market', '')
                
                # Create stream identifier
                stream = f"{channel}/{market}"
                
                # Process based on channel type
                if channel == 'trades':
                    # Trade data
                    await self._process_trades_message(data, stream)
                
                elif channel == 'ticker':
                    # Ticker data
                    await self._process_ticker_message(data, stream)
                
                elif channel == 'orderbook':
                    # Order book data
                    await self._process_orderbook_message(data, stream)
                
                elif channel == 'fills' and self.authenticated:
                    # User trades data (authenticated)
                    await self._process_fills_message(data, stream)
                
                elif channel == 'orders' and self.authenticated:
                    # User orders data (authenticated)
                    await self._process_orders_message(data, stream)
                
                else:
                    # Unknown or unsupported channel
                    logger.warning(f"Received message for unknown/unsupported FTX channel: {channel}")
            
            else:
                # Unknown message type
                logger.warning(f"Received unknown FTX message type: {message_type}")
        
        except json.JSONDecodeError:
            logger.error(f"Failed to parse FTX WebSocket message: {message}")
        
        except Exception as e:
            logger.error(f"Error handling FTX WebSocket message: {str(e)}")
    
    async def _process_trades_message(self, data: Dict[str, Any], stream: str) -> None:
        """
        Process a trades channel message.
        
        Args:
            data: Message data
            stream: Stream identifier
        """
        handler = get_ftx_handler_for_stream(stream)
        message = await handler(data)
        await self._dispatch_message(message)
    
    async def _process_ticker_message(self, data: Dict[str, Any], stream: str) -> None:
        """
        Process a ticker channel message.
        
        Args:
            data: Message data
            stream: Stream identifier
        """
        handler = get_ftx_handler_for_stream(stream)
        message = await handler(data)
        await self._dispatch_message(message)
    
    async def _process_orderbook_message(self, data: Dict[str, Any], stream: str) -> None:
        """
        Process an orderbook channel message.
        
        Args:
            data: Message data
            stream: Stream identifier
        """
        handler = get_ftx_handler_for_stream(stream)
        message = await handler(data)
        await self._dispatch_message(message)
    
    async def _process_fills_message(self, data: Dict[str, Any], stream: str) -> None:
        """
        Process a fills channel message (authenticated).
        
        Args:
            data: Message data
            stream: Stream identifier
        """
        handler = get_ftx_handler_for_stream(stream)
        message = await handler(data)
        await self._dispatch_message(message)
    
    async def _process_orders_message(self, data: Dict[str, Any], stream: str) -> None:
        """
        Process an orders channel message (authenticated).
        
        Args:
            data: Message data
            stream: Stream identifier
        """
        handler = get_ftx_handler_for_stream(stream)
        message = await handler(data)
        await self._dispatch_message(message)
    
    async def disconnect(self, code: int = 1000, reason: str = "Client requested disconnect") -> bool:
        """
        Disconnect from the WebSocket server.
        
        Args:
            code: WebSocket close code
            reason: Reason for disconnection
            
        Returns:
            bool: True if disconnection was successful, False otherwise
        """
        if not self.is_connected:
            logger.debug("Already disconnected from FTX WebSocket")
            return True
        
        try:
            self._update_status(WebSocketConnectionStatus.DISCONNECTED, reason)
            
            # Cancel ping task
            if self.ping_task and not self.ping_task.done():
                self.ping_task.cancel()
                try:
                    await self.ping_task
                except asyncio.CancelledError:
                    pass
            
            # Cancel connection task
            if self.connection_task and not self.connection_task.done():
                self.connection_task.cancel()
                try:
                    await self.connection_task
                except asyncio.CancelledError:
                    pass
            
            # Close the WebSocket connection
            if self.websocket and not self.websocket.closed:
                await self.websocket.close(code=code, reason=reason)
            
            logger.info(f"Disconnected from FTX WebSocket: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from FTX WebSocket: {str(e)}")
            return False
    
    async def reconnect(self) -> bool:
        """
        Reconnect to the WebSocket server.
        
        Returns:
            bool: True if reconnection was successful, False otherwise
        """
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error(f"Maximum reconnection attempts ({self.max_reconnect_attempts}) reached")
            self._update_status(
                WebSocketConnectionStatus.ERROR,
                f"Maximum reconnection attempts ({self.max_reconnect_attempts}) reached"
            )
            return False
        
        self.reconnect_attempts += 1
        self.reconnects_count += 1
        
        logger.info(f"Attempting to reconnect to FTX WebSocket (attempt {self.reconnect_attempts}/{self.max_reconnect_attempts})")
        
        self._update_status(WebSocketConnectionStatus.RECONNECTING)
        
        # Disconnect first if still connected
        if self.is_connected:
            await self.disconnect(
                code=1000,
                reason="Reconnecting"
            )
        
        # Exponential backoff for reconnect delay
        delay = self.reconnect_delay * (2 ** (self.reconnect_attempts - 1))
        logger.info(f"Waiting {delay} seconds before reconnecting")
        await asyncio.sleep(delay)
        
        # Attempt to connect
        return await self.connect()
    
    async def subscribe(self, stream: str) -> bool:
        """
        Subscribe to a WebSocket stream.
        
        Args:
            stream: Stream name in format "channel/market"
            
        Returns:
            bool: True if subscription was successful, False otherwise
        """
        if not self.is_connected:
            # If not connected, store the subscription for later
            if self._is_user_stream(stream):
                self.user_streams.add(stream)
            else:
                self.market_streams.add(stream)
            logger.debug(f"Stored subscription to FTX stream: {stream} for when connected")
            return False
        
        try:
            # Parse stream name
            parts = stream.split('/')
            if len(parts) != 2:
                logger.error(f"Invalid FTX stream format: {stream}. Expected 'channel/market'")
                return False
            
            channel, market = parts
            
            # Check if this is a user stream and we're authenticated
            if self._is_user_stream(stream) and not self.authenticated:
                logger.error(f"Cannot subscribe to FTX user stream {stream} without authentication")
                return False
            
            # Create subscription message
            subscription = {
                'op': 'subscribe',
                'channel': channel,
            }
            
            # Add market for market-specific channels
            if market and channel not in ['fills', 'orders']:
                subscription['market'] = market
            
            # Send subscription message
            await self.websocket.send(json.dumps(subscription))
            
            # Add to subscriptions set
            if self._is_user_stream(stream):
                self.user_streams.add(stream)
            else:
                self.market_streams.add(stream)
            
            logger.info(f"Subscribed to FTX stream: {stream}")
            return True
            
        except Exception as e:
            logger.error(f"Error subscribing to FTX stream {stream}: {str(e)}")
            return False
    
    async def unsubscribe(self, stream: str) -> bool:
        """
        Unsubscribe from a WebSocket stream.
        
        Args:
            stream: Stream name in format "channel/market"
            
        Returns:
            bool: True if unsubscription was successful, False otherwise
        """
        # Remove from subscription sets regardless of connection status
        if self._is_user_stream(stream):
            self.user_streams.discard(stream)
        else:
            self.market_streams.discard(stream)
        
        if not self.is_connected:
            logger.debug(f"Removed subscription to FTX stream: {stream}")
            return True
        
        try:
            # Parse stream name
            parts = stream.split('/')
            if len(parts) != 2:
                logger.error(f"Invalid FTX stream format: {stream}. Expected 'channel/market'")
                return False
            
            channel, market = parts
            
            # Create unsubscription message
            unsubscription = {
                'op': 'unsubscribe',
                'channel': channel,
            }
            
            # Add market for market-specific channels
            if market and channel not in ['fills', 'orders']:
                unsubscription['market'] = market
            
            # Send unsubscription message
            await self.websocket.send(json.dumps(unsubscription))
            
            logger.info(f"Unsubscribed from FTX stream: {stream}")
            return True
            
        except Exception as e:
            logger.error(f"Error unsubscribing from FTX stream {stream}: {str(e)}")
            return False
    
    async def send_message(self, message: Dict[str, Any]) -> bool:
        """
        Send a message to the WebSocket server.
        
        Args:
            message: Message to send
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        if not self.is_connected:
            logger.error("Cannot send message: Not connected to FTX WebSocket")
            return False
        
        try:
            await self.websocket.send(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Error sending message to FTX WebSocket: {str(e)}")
            return False
    
    async def ping(self) -> bool:
        """
        Send a ping message to the WebSocket server.
        
        Returns:
            bool: True if ping was successful, False otherwise
        """
        if not self.is_connected:
            return False
        
        try:
            # FTX doesn't have a specific ping message format
            # We just use a basic ping message
            ping_message = {
                'op': 'ping'
            }
            
            await self.websocket.send(json.dumps(ping_message))
            return True
        except Exception as e:
            logger.error(f"Error sending ping to FTX WebSocket: {str(e)}")
            return False
    
    def _is_user_stream(self, stream: str) -> bool:
        """
        Check if a stream is a user data stream.
        
        Args:
            stream: Stream name
            
        Returns:
            bool: True if the stream is a user data stream, False otherwise
        """
        user_channels = ['fills', 'orders']
        parts = stream.split('/')
        if len(parts) >= 1:
            return parts[0] in user_channels
        return False 