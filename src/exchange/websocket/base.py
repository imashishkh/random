"""
Base WebSocket client module for cryptocurrency exchanges.

This module defines the abstract base class for WebSocket clients
that connect to cryptocurrency exchanges for real-time data.
"""
import abc
import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Set, Any, Optional, Callable, Awaitable, Union, Tuple
from enum import Enum

from .models import (
    WebSocketConnectionStatus,
    WebSocketMessageType,
    WebSocketMessage,
    WebSocketError
)

# Configure logger
logger = logging.getLogger(__name__)

class BaseWebSocketClient(abc.ABC):
    """Abstract base class for WebSocket clients."""
    
    def __init__(
        self,
        url: str,
        ping_interval: int = 30,
        ping_timeout: int = 10,
        close_timeout: int = 10,
        reconnect_delay: int = 5,
        max_reconnect_attempts: int = 5,
        connection_timeout: int = 30,
        buffer_size: int = 1000
    ):
        """
        Initialize the base WebSocket client.
        
        Args:
            url: WebSocket server URL
            ping_interval: Interval in seconds between ping messages
            ping_timeout: Timeout in seconds for ping responses
            close_timeout: Timeout in seconds for closing connections
            reconnect_delay: Initial delay in seconds between reconnection attempts
            max_reconnect_attempts: Maximum number of reconnection attempts
            connection_timeout: Timeout in seconds for establishing connections
            buffer_size: Maximum number of messages to buffer during disconnections
        """
        self.url = url
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.close_timeout = close_timeout
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        self.connection_timeout = connection_timeout
        self.buffer_size = buffer_size
        
        # Connection state
        self.status = WebSocketConnectionStatus.DISCONNECTED
        self.connected_since = None
        self.disconnect_reason = None
        self.reconnect_attempts = 0
        self.last_message_time = None
        
        # WebSocket connection
        self.websocket = None
        self.connection_task = None
        self.ping_task = None
        
        # Stream subscriptions
        self.subscriptions = set()
        
        # Message handlers
        self.message_handlers = {}
        self.default_message_handler = None
        
        # Message buffer for disconnections
        self.message_buffer = []
        
        # Performance metrics
        self.messages_received = 0
        self.messages_processed = 0
        self.errors_count = 0
        self.reconnects_count = 0
        self.last_latency = 0
        
        # Locks
        self._connection_lock = asyncio.Lock()
    
    @property
    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return self.status == WebSocketConnectionStatus.CONNECTED
    
    @property
    def connection_time(self) -> Optional[int]:
        """Get the connection duration in seconds."""
        if self.connected_since is None:
            return None
        return int(time.time() - self.connected_since)
    
    @abc.abstractmethod
    async def connect(self) -> bool:
        """
        Connect to the WebSocket server.
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def disconnect(self, code: int = 1000, reason: str = "Client requested disconnect") -> bool:
        """
        Disconnect from the WebSocket server.
        
        Args:
            code: WebSocket close code
            reason: Reason for disconnection
            
        Returns:
            bool: True if disconnection was successful, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def reconnect(self) -> bool:
        """
        Reconnect to the WebSocket server.
        
        Returns:
            bool: True if reconnection was successful, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def subscribe(self, stream: str) -> bool:
        """
        Subscribe to a WebSocket stream.
        
        Args:
            stream: Stream name or identifier
            
        Returns:
            bool: True if subscription was successful, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def unsubscribe(self, stream: str) -> bool:
        """
        Unsubscribe from a WebSocket stream.
        
        Args:
            stream: Stream name or identifier
            
        Returns:
            bool: True if unsubscription was successful, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def send_message(self, message: Dict[str, Any]) -> bool:
        """
        Send a message to the WebSocket server.
        
        Args:
            message: Message to send
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def _handle_message(self, message: str) -> None:
        """
        Process a raw message from the WebSocket server.
        
        Args:
            message: Raw message string
        """
        pass
    
    def register_handler(self, message_type: Union[str, WebSocketMessageType], handler: Callable[[WebSocketMessage], Awaitable[None]]) -> None:
        """
        Register a handler for a specific message type.
        
        Args:
            message_type: Type of message to handle
            handler: Async function to handle the message
        """
        if isinstance(message_type, str):
            message_type = WebSocketMessageType(message_type)
        
        self.message_handlers[message_type] = handler
        logger.debug(f"Registered handler for message type: {message_type}")
    
    def register_default_handler(self, handler: Callable[[WebSocketMessage], Awaitable[None]]) -> None:
        """
        Register a default handler for messages without a specific handler.
        
        Args:
            handler: Async function to handle messages
        """
        self.default_message_handler = handler
        logger.debug("Registered default message handler")
    
    async def _dispatch_message(self, message: WebSocketMessage) -> None:
        """
        Dispatch a message to the appropriate handler.
        
        Args:
            message: WebSocket message to dispatch
        """
        try:
            self.messages_processed += 1
            
            # Find and call the appropriate handler
            handler = self.message_handlers.get(message.msg_type)
            
            if handler:
                await handler(message)
            elif self.default_message_handler:
                await self.default_message_handler(message)
            else:
                logger.debug(f"No handler for message type: {message.msg_type}")
        
        except Exception as e:
            self.errors_count += 1
            logger.error(f"Error dispatching message: {str(e)}")
    
    def add_to_buffer(self, message: WebSocketMessage) -> None:
        """
        Add a message to the buffer for later processing.
        
        Args:
            message: WebSocket message to buffer
        """
        # Ensure buffer doesn't exceed max size
        if len(self.message_buffer) >= self.buffer_size:
            # Remove oldest message
            self.message_buffer.pop(0)
        
        self.message_buffer.append(message)
    
    async def process_buffer(self) -> None:
        """Process all messages in the buffer."""
        logger.info(f"Processing {len(self.message_buffer)} buffered messages")
        
        while self.message_buffer:
            message = self.message_buffer.pop(0)
            await self._dispatch_message(message)
    
    def clear_buffer(self) -> None:
        """Clear the message buffer."""
        buffer_size = len(self.message_buffer)
        self.message_buffer = []
        logger.debug(f"Cleared {buffer_size} messages from buffer")
    
    def get_subscription_status(self) -> Dict[str, bool]:
        """
        Get the status of all subscriptions.
        
        Returns:
            Dict mapping subscription names to their active status
        """
        return {subscription: self.is_connected for subscription in self.subscriptions}
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics.
        
        Returns:
            Dict with performance metrics
        """
        return {
            "status": self.status,
            "connected_since": self.connected_since,
            "connection_time": self.connection_time,
            "messages_received": self.messages_received,
            "messages_processed": self.messages_processed,
            "errors_count": self.errors_count,
            "reconnects_count": self.reconnects_count,
            "last_message_time": self.last_message_time,
            "last_latency": self.last_latency,
            "subscriptions_count": len(self.subscriptions),
            "buffer_size": len(self.message_buffer),
        }
    
    async def ping(self) -> bool:
        """
        Send a ping message to check connection health.
        
        Returns:
            bool: True if ping was successful, False otherwise
        """
        try:
            start_time = time.time()
            
            if not self.is_connected or self.websocket is None:
                return False
            
            await self.websocket.ping()
            
            # Wait for pong with timeout
            ping_waiter = asyncio.create_task(self.websocket.pong())
            try:
                await asyncio.wait_for(ping_waiter, self.ping_timeout)
                self.last_latency = time.time() - start_time
                return True
            except asyncio.TimeoutError:
                logger.warning("Ping timeout, connection may be unhealthy")
                return False
        
        except Exception as e:
            logger.error(f"Error during ping: {str(e)}")
            return False
    
    async def _ping_loop(self) -> None:
        """Periodically send ping messages to keep the connection alive."""
        while self.is_connected:
            try:
                await asyncio.sleep(self.ping_interval)
                
                if not await self.ping():
                    logger.warning("Failed to ping server, attempting reconnect")
                    await self.reconnect()
            
            except asyncio.CancelledError:
                break
            
            except Exception as e:
                logger.error(f"Error in ping loop: {str(e)}")
    
    def _update_status(self, status: WebSocketConnectionStatus, reason: Optional[str] = None) -> None:
        """
        Update the connection status.
        
        Args:
            status: New connection status
            reason: Reason for the status change
        """
        old_status = self.status
        self.status = status
        
        if status == WebSocketConnectionStatus.CONNECTED:
            self.connected_since = time.time()
            self.disconnect_reason = None
        elif status == WebSocketConnectionStatus.DISCONNECTED:
            self.connected_since = None
            self.disconnect_reason = reason
        
        logger.info(f"WebSocket status changed: {old_status} -> {status}" + (f" ({reason})" if reason else ""))
    
    def _handle_error(self, code: int, message: str) -> WebSocketError:
        """
        Handle an error condition.
        
        Args:
            code: Error code
            message: Error message
            
        Returns:
            WebSocketError object
        """
        self.errors_count += 1
        logger.error(f"WebSocket error [{code}]: {message}")
        
        error = WebSocketError(
            code=code,
            message=message,
            timestamp=int(time.time() * 1000),
            datetime=datetime.now()
        )
        
        return error
    
    def __str__(self) -> str:
        """String representation of the client."""
        return f"{self.__class__.__name__}(status={self.status}, subscriptions={len(self.subscriptions)})" 