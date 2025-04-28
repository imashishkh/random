"""
Binance WebSocket client for real-time market data.

This module implements a WebSocket client for connecting to Binance
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
import random

import websockets
from binance import AsyncClient
from binance.streams import BinanceSocketManager
import aiohttp

from .websocket.base import BaseWebSocketClient
from .websocket.models import (
    WebSocketMessage,
    WebSocketMessageType,
    WebSocketConnectionStatus,
    WebSocketError
)
from .websocket.handlers import (
    handle_binance_trade,
    handle_binance_kline,
    handle_binance_ticker,
    handle_binance_depth,
    handle_binance_book_ticker,
    handle_binance_account_update,
    handle_binance_order_update,
    get_binance_handler_for_stream
)

# Configure logger
logger = logging.getLogger(__name__)

# Binance WebSocket URLs
BINANCE_STREAM_URL = "wss://stream.binance.com:9443"
BINANCE_STREAM_TESTNET_URL = "wss://testnet.binance.vision/ws"

# API endpoints for user data stream
REST_API_URL = "https://api.binance.com"
REST_API_TESTNET_URL = "https://testnet.binance.vision"
LISTEN_KEY_ENDPOINT = "/api/v3/userDataStream"

class BinanceWebSocketClient(BaseWebSocketClient):
    """WebSocket client for Binance exchange."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = False,
        ping_interval: int = 30,
        ping_timeout: int = 10,
        close_timeout: int = 10,
        reconnect_delay: int = 5,
        max_reconnect_attempts: int = 5,
        connection_timeout: int = 30,
        buffer_size: int = 1000
    ):
        """
        Initialize the Binance WebSocket client.
        
        Args:
            api_key: Binance API key (required for user data streams)
            api_secret: Binance API secret (required for user data streams)
            testnet: Whether to use the testnet
            ping_interval: Interval in seconds between ping messages
            ping_timeout: Timeout in seconds for ping responses
            close_timeout: Timeout in seconds for closing connections
            reconnect_delay: Initial delay in seconds between reconnection attempts
            max_reconnect_attempts: Maximum number of reconnection attempts
            connection_timeout: Timeout in seconds for establishing connections
            buffer_size: Maximum number of messages to buffer during disconnections
        """
        # Determine the WebSocket URL based on testnet flag
        ws_url = BINANCE_STREAM_TESTNET_URL if testnet else BINANCE_STREAM_URL
        
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
        self.api_key = api_key or os.environ.get('BINANCE_API_KEY')
        self.api_secret = api_secret or os.environ.get('BINANCE_API_SECRET')
        self.testnet = testnet
        
        # REST API URL for listen key management
        self.rest_api_url = REST_API_TESTNET_URL if testnet else REST_API_URL
        
        # Stream management
        self.combined_stream = False
        self.stream_id = None
        self.listen_key = None
        self.listen_key_keep_alive_task = None
        
        # Binance client instances
        self.binance_client = None
        self.socket_manager = None
        
        # Stream callbacks
        self.stream_callbacks = {}
        
        # Stream types (for subscription management)
        self.market_streams = set()
        self.user_streams = set()
        
        # Register message handlers
        self._register_message_handlers()
    
    def _register_message_handlers(self) -> None:
        """Register message handlers for different types of messages."""
        self.register_handler(WebSocketMessageType.TRADE, handle_binance_trade)
        self.register_handler(WebSocketMessageType.KLINE, handle_binance_kline)
        self.register_handler(WebSocketMessageType.TICKER, handle_binance_ticker)
        self.register_handler(WebSocketMessageType.DEPTH, handle_binance_depth)
        self.register_handler(WebSocketMessageType.BOOK_TICKER, handle_binance_book_ticker)
        self.register_handler(WebSocketMessageType.ACCOUNT_UPDATE, handle_binance_account_update)
        self.register_handler(WebSocketMessageType.ORDER_UPDATE, handle_binance_order_update)
    
    async def connect(self) -> bool:
        """
        Connect to the Binance WebSocket server.
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
        # Skip if already connected
        if self.is_connected:
            logger.debug("Already connected to Binance WebSocket")
            return True
        
        # Acquire lock to prevent concurrent connection attempts
        async with self._connection_lock:
            try:
                self._update_status(WebSocketConnectionStatus.CONNECTING)
                
                # Initialize Binance client
                self.binance_client = await AsyncClient.create(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    testnet=self.testnet
                )
                
                # Initialize Socket Manager
                self.socket_manager = BinanceSocketManager(self.binance_client)
                
                # Reset connection attempt counter
                self.reconnect_attempts = 0
                
                # Start connection tasks
                tasks = []
                
                # Connect to market streams if any
                if self.market_streams:
                    tasks.append(self._connect_market_streams())
                
                # Connect to user streams if credentials are available
                if self.api_key and self.api_secret and self.user_streams:
                    tasks.append(self._connect_user_stream())
                
                # Wait for all streams to connect
                if tasks:
                    await asyncio.gather(*tasks)
                    
                    # Update connection status
                    self._update_status(WebSocketConnectionStatus.CONNECTED)
                    self.connected_since = time.time()
                    logger.info("Connected to Binance WebSocket")
                    
                    # Start ping/keepalive task
                    self.ping_task = asyncio.create_task(self._ping_loop())
                    
                    # Process any buffered messages
                    if self.message_buffer:
                        await self.process_buffer()
                    
                    return True
                else:
                    logger.warning("No streams to connect to")
                    self._update_status(WebSocketConnectionStatus.DISCONNECTED)
                    return False
                
            except Exception as e:
                logger.error(f"Error connecting to Binance WebSocket: {str(e)}")
                self._update_status(WebSocketConnectionStatus.ERROR, str(e))
                return False
    
    async def _connect_market_streams(self) -> None:
        """Connect to market data streams."""
        try:
            # Combine streams for efficiency if multiple market streams
            if len(self.market_streams) > 1:
                self.combined_stream = True
                streams = list(self.market_streams)
                logger.debug(f"Connecting to combined market streams: {streams}")
                
                # Create a multiplexed socket with all market streams
                self.multiplex_socket = self.socket_manager.multiplex_socket(streams)
                self.connection_task = asyncio.create_task(self._listen_to_multiplex_socket())
            
            # Single stream
            elif len(self.market_streams) == 1:
                stream = next(iter(self.market_streams))
                logger.debug(f"Connecting to market stream: {stream}")
                
                # Parse stream to determine type and create appropriate socket
                if "@kline_" in stream:
                    symbol, interval = stream.split("@kline_")
                    self.connection_task = asyncio.create_task(
                        self._listen_to_socket(
                            self.socket_manager.kline_socket(symbol, interval)
                        )
                    )
                elif "@trade" in stream:
                    symbol = stream.split("@trade")[0]
                    self.connection_task = asyncio.create_task(
                        self._listen_to_socket(
                            self.socket_manager.trade_socket(symbol)
                        )
                    )
                elif "@ticker" in stream:
                    symbol = stream.split("@ticker")[0]
                    self.connection_task = asyncio.create_task(
                        self._listen_to_socket(
                            self.socket_manager.symbol_ticker_socket(symbol)
                        )
                    )
                elif "@depth" in stream:
                    parts = stream.split("@depth")
                    symbol = parts[0]
                    depth = "20" if len(parts) == 1 else parts[1]
                    self.connection_task = asyncio.create_task(
                        self._listen_to_socket(
                            self.socket_manager.depth_socket(symbol, depth)
                        )
                    )
                elif "@bookTicker" in stream:
                    symbol = stream.split("@bookTicker")[0]
                    self.connection_task = asyncio.create_task(
                        self._listen_to_socket(
                            self.socket_manager.symbol_book_ticker_socket(symbol)
                        )
                    )
                else:
                    logger.warning(f"Unknown stream type: {stream}")
            
        except Exception as e:
            logger.error(f"Error connecting to market streams: {str(e)}")
            raise
    
    async def _connect_user_stream(self) -> None:
        """Connect to user data stream."""
        try:
            # Get or refresh listen key
            await self._get_listen_key()
            
            if not self.listen_key:
                logger.error("Failed to get listen key")
                return
            
            logger.debug(f"Connecting to user data stream with listen key: {self.listen_key[:5]}...")
            
            # Create user socket
            user_socket = self.socket_manager.user_socket(self.listen_key)
            
            # Start listening task
            self.user_socket_task = asyncio.create_task(self._listen_to_socket(user_socket, is_user_socket=True))
            
            # Start keep-alive task for listen key
            self.listen_key_keep_alive_task = asyncio.create_task(self._keep_listen_key_alive())
            
        except Exception as e:
            logger.error(f"Error connecting to user data stream: {str(e)}")
            raise
    
    async def _listen_to_socket(self, socket, is_user_socket: bool = False) -> None:
        """
        Listen for messages on a socket.
        
        Args:
            socket: Binance socket to listen on
            is_user_socket: Whether this is a user data stream socket
        """
        async with socket as sock:
            while True:
                try:
                    msg = await sock.recv()
                    
                    # Update last message time
                    self.last_message_time = time.time()
                    
                    # Process the message
                    await self._handle_message(msg)
                    
                except websockets.exceptions.ConnectionClosed:
                    logger.warning(f"Connection closed for {'user' if is_user_socket else 'market'} socket")
                    break
                except Exception as e:
                    logger.error(f"Error in socket listener: {str(e)}")
                    # Attempt to reconnect
                    await asyncio.sleep(1)
    
    async def _listen_to_multiplex_socket(self) -> None:
        """Listen for messages on a multiplexed socket."""
        async with self.multiplex_socket as socket:
            while True:
                try:
                    msg = await socket.recv()
                    
                    # Update last message time
                    self.last_message_time = time.time()
                    
                    # Process the message
                    await self._handle_message(msg)
                    
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("Multiplexed socket connection closed")
                    break
                except Exception as e:
                    logger.error(f"Error in multiplexed socket listener: {str(e)}")
                    # Attempt to reconnect
                    await asyncio.sleep(1)
    
    async def _handle_message(self, message: Any) -> None:
        """
        Process a raw message from the WebSocket server.
        
        Args:
            message: Raw message data
        """
        try:
            # Increment message counter
            self.messages_received += 1
            
            # Parse the message
            if isinstance(message, str):
                message = json.loads(message)
            
            # Determine message type and get appropriate handler
            stream = message.get("stream", "")
            handler = get_binance_handler_for_stream(stream)
            
            # Process the message with the handler
            ws_message = await handler(message)
            
            # Dispatch the processed message
            await self._dispatch_message(ws_message)
            
            # Increment processed counter
            self.messages_processed += 1
            
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            self.errors_count += 1
    
    async def _get_listen_key(self) -> None:
        """
        Obtain a listen key for user data stream.
        
        A listen key is required for subscribing to user-specific updates
        like account or order updates.
        """
        if not self.api_key:
            raise WebSocketError("API key is required for user data stream")
        
        try:
            # Prepare the API call
            url = f"{self.rest_api_url}{LISTEN_KEY_ENDPOINT}"
            headers = {"X-MBX-APIKEY": self.api_key}
            
            # Make the POST request to get a listen key
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.listen_key = data.get("listenKey")
                        logger.info("Obtained listenKey for user data stream", 
                                   listen_key_length=len(self.listen_key) if self.listen_key else 0)
                    else:
                        error_text = await response.text()
                        logger.error("Failed to get listenKey", 
                                     status=response.status, 
                                     response=error_text)
                        raise WebSocketError(f"Failed to get listenKey: {error_text}")
        except Exception as e:
            logger.error("Error getting listenKey", error=str(e))
            raise WebSocketError(f"Error getting listenKey: {str(e)}")
    
    async def _keep_listen_key_alive(self) -> None:
        """
        Keep the user data stream listen key alive by sending periodic PUT requests.
        
        Binance requires the listen key to be kept alive by calling the keep-alive
        endpoint every 30 minutes. We use a shorter interval (20 minutes) to ensure
        the key remains valid.
        """
        if not self.api_key or not self.listen_key:
            logger.warning("Cannot keep listen key alive without API key and listen key")
            return
        
        keep_alive_interval = 20 * 60  # 20 minutes in seconds
        max_retries = 5
        retry_delay_base = 30  # Base delay in seconds for exponential backoff
        
        logger.info("Starting listen key keep-alive task")
        
        while self.is_connected and self._connection_status != WebSocketConnectionStatus.CLOSING:
            try:
                # Prepare the API call
                url = f"{self.rest_api_url}{LISTEN_KEY_ENDPOINT}"
                headers = {"X-MBX-APIKEY": self.api_key}
                params = {"listenKey": self.listen_key}
                
                # Make the PUT request to keep the listen key alive
                retry_count = 0
                success = False
                
                while not success and retry_count < max_retries:
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.put(url, headers=headers, params=params) as response:
                                if response.status == 200:
                                    logger.debug("Successfully renewed listenKey")
                                    success = True
                                else:
                                    error_text = await response.text()
                                    retry_count += 1
                                    retry_delay = retry_delay_base * (2 ** retry_count) + random.uniform(0, 1)  # Exponential backoff with jitter
                                    logger.warning("Failed to renew listenKey, will retry", 
                                                 status=response.status, 
                                                 response=error_text,
                                                 retry_count=retry_count,
                                                 retry_delay=retry_delay)
                                    
                                    # If we're running out of retries, try to get a new listen key
                                    if retry_count >= max_retries - 1:
                                        logger.warning("Maximum retries reached, attempting to get a new listenKey")
                                        await self._get_listen_key()
                                        # Update params with the new listen key
                                        params = {"listenKey": self.listen_key}
                                    
                                    await asyncio.sleep(retry_delay)
                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        retry_count += 1
                        retry_delay = retry_delay_base * (2 ** retry_count) + random.uniform(0, 1)
                        logger.warning("Error during listenKey renewal", 
                                     error=str(e),
                                     retry_count=retry_count,
                                     retry_delay=retry_delay)
                        await asyncio.sleep(retry_delay)
                
                if not success:
                    logger.error("Failed to renew listenKey after multiple attempts")
                    # Attempt to reconnect the WebSocket since the listen key might be invalid
                    asyncio.create_task(self.reconnect())
                
                # Sleep until the next keep-alive time
                await asyncio.sleep(keep_alive_interval)
                
            except asyncio.CancelledError:
                logger.info("Listen key keep-alive task cancelled")
                break
            except Exception as e:
                logger.error("Error in listen key keep-alive task", error=str(e))
                # Sleep before retrying to avoid rapid failure loops
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
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
            logger.debug("Already disconnected from Binance WebSocket")
            return True
        
        try:
            self._update_status(WebSocketConnectionStatus.DISCONNECTED, reason)
            
            # Cancel ping task if running
            if self.ping_task and not self.ping_task.done():
                self.ping_task.cancel()
                try:
                    await self.ping_task
                except asyncio.CancelledError:
                    pass
            
            # Cancel listen key keep-alive task if running
            if self.listen_key_keep_alive_task and not self.listen_key_keep_alive_task.done():
                self.listen_key_keep_alive_task.cancel()
                try:
                    await self.listen_key_keep_alive_task
                except asyncio.CancelledError:
                    pass
            
            # Close the socket manager connections
            if self.socket_manager:
                await self.socket_manager.close()
            
            # Close the Binance client
            if self.binance_client:
                await self.binance_client.close_connection()
            
            # Clear connection-related attributes
            self.connected_since = None
            self.socket_manager = None
            self.binance_client = None
            self.connection_task = None
            
            logger.info("Disconnected from Binance WebSocket")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from Binance WebSocket: {str(e)}")
            return False
    
    async def reconnect(self) -> bool:
        """
        Attempt to reconnect to the WebSocket server with exponential backoff.
        
        Returns:
            bool: True if reconnection was successful, False otherwise
        """
        if self._connection_status == WebSocketConnectionStatus.CONNECTING:
            logger.debug("Reconnection already in progress")
            return False
            
        async with self._connection_lock:
            logger.info("Attempting to reconnect")
            self._update_status(WebSocketConnectionStatus.CONNECTING)
            
            # Disconnect if still connected
            if self.is_connected:
                await self.disconnect(code=1006, reason="Reconnecting")
                
            # Apply exponential backoff for reconnect attempts
            delay = min(
                self.reconnect_delay * (2 ** self.reconnect_attempts),
                300  # Max delay of 5 minutes
            )
            
            # Add jitter to prevent thundering herd issues
            jitter = random.uniform(0, 1)
            total_delay = delay + jitter
            
            logger.info(f"Reconnecting in {total_delay:.2f} seconds (attempt {self.reconnect_attempts + 1})")
            await asyncio.sleep(total_delay)
            
            # Increment the reconnect counter
            self.reconnect_attempts += 1
            
            # If we exceed the maximum reconnect attempts, give up
            if self.reconnect_attempts > self.max_reconnect_attempts:
                self._update_status(
                    WebSocketConnectionStatus.ERROR,
                    f"Maximum reconnection attempts ({self.max_reconnect_attempts}) exceeded"
                )
                logger.error("Maximum reconnection attempts exceeded")
                return False
                
            try:
                # For user data streams, we may need a new listen key
                if self.user_streams and not self.listen_key:
                    await self._get_listen_key()
                    
                # Try to connect again
                return await self.connect()
            except Exception as e:
                logger.error(f"Error during reconnection: {str(e)}")
                self._update_status(WebSocketConnectionStatus.ERROR, str(e))
                return False
    
    async def subscribe(self, stream: str) -> bool:
        """
        Subscribe to a WebSocket stream.
        
        Args:
            stream: Stream name (e.g., "btcusdt@trade", "btcusdt@kline_1m")
            
        Returns:
            bool: True if subscription was successful, False otherwise
        """
        # Skip if already subscribed
        if stream in self.subscriptions:
            logger.debug(f"Already subscribed to {stream}")
            return True
        
        try:
            # Determine if this is a market or user stream
            if self._is_user_stream(stream):
                self.user_streams.add(stream)
            else:
                self.market_streams.add(stream)
            
            # Add to subscriptions set
            self.subscriptions.add(stream)
            
            # If already connected, need to reconnect to apply new subscription
            was_connected = self.is_connected
            if was_connected:
                await self.disconnect(reason="Updating subscriptions")
            
            # Connect with new subscription
            result = await self.connect()
            
            if result:
                logger.info(f"Subscribed to {stream}")
                return True
            else:
                # Remove from subscriptions if connection failed
                self.subscriptions.remove(stream)
                if self._is_user_stream(stream):
                    self.user_streams.remove(stream)
                else:
                    self.market_streams.remove(stream)
                logger.error(f"Failed to subscribe to {stream}")
                return False
                
        except Exception as e:
            logger.error(f"Error subscribing to {stream}: {str(e)}")
            return False
    
    async def unsubscribe(self, stream: str) -> bool:
        """
        Unsubscribe from a WebSocket stream.
        
        Args:
            stream: Stream name
            
        Returns:
            bool: True if unsubscription was successful, False otherwise
        """
        # Skip if not subscribed
        if stream not in self.subscriptions:
            logger.debug(f"Not subscribed to {stream}")
            return True
        
        try:
            # Remove from subscriptions set
            self.subscriptions.remove(stream)
            
            # Remove from specific stream set
            if self._is_user_stream(stream):
                self.user_streams.remove(stream)
            else:
                self.market_streams.remove(stream)
            
            # If connected, need to reconnect to apply unsubscription
            was_connected = self.is_connected
            if was_connected:
                await self.disconnect(reason="Updating subscriptions")
                
                # Only reconnect if there are remaining subscriptions
                if self.subscriptions:
                    result = await self.connect()
                    
                    if result:
                        logger.info(f"Unsubscribed from {stream}")
                        return True
                    else:
                        # Add back to subscriptions if reconnection failed
                        self.subscriptions.add(stream)
                        if self._is_user_stream(stream):
                            self.user_streams.add(stream)
                        else:
                            self.market_streams.add(stream)
                        logger.error(f"Failed to apply unsubscription from {stream}")
                        return False
                else:
                    logger.info(f"Unsubscribed from {stream}, no remaining subscriptions")
                    return True
            else:
                logger.info(f"Unsubscribed from {stream} (not connected)")
                return True
                
        except Exception as e:
            logger.error(f"Error unsubscribing from {stream}: {str(e)}")
            return False
    
    async def send_message(self, message: Dict[str, Any]) -> bool:
        """
        Send a message to the WebSocket server.
        
        Args:
            message: Message to send
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        # Binance WebSocket API doesn't support sending arbitrary messages
        # So this is mainly for compatibility with the base class
        logger.warning("Binance WebSocket API doesn't support sending arbitrary messages")
        return False
    
    async def ping(self) -> bool:
        """
        Send a ping to the WebSocket server.
        
        Returns:
            bool: True if ping was successful, False otherwise
        """
        # For Binance, we don't need to ping the WebSocket directly
        # as the underlying websocket library handles that
        # This is mainly for compatibility with the base class
        return self.is_connected
    
    def _is_user_stream(self, stream: str) -> bool:
        """
        Check if a stream is a user data stream.
        
        Args:
            stream: Stream name
            
        Returns:
            bool: True if the stream is a user data stream, False otherwise
        """
        return stream in {
            "account", "balance", "order", "trade", "userData"
        }