"""
Redis Communication Facade

This module provides a unified interface for Redis-based communication,
abstracting the details of PubSub and Streams and providing a simple API
for sending/receiving messages between the orchestrator and agents.
"""

import asyncio
import uuid
from typing import Dict, Any, Callable, Optional, List, Union, Awaitable
from datetime import datetime, timedelta
import json

from ...utils.logging.logger import get_logger
from .redis.connection_manager import RedisConnectionManager
from .redis.pubsub_messenger import PubSubMessenger
from .redis.stream_messenger import StreamMessenger
from .redis.message_schema import (
    Message, MessageType, MessagePriority, 
    CommandMessage, StatusMessage, ResultMessage, HeartbeatMessage
)

logger = get_logger()

class CommunicationFacade:
    """
    Provides a unified API for communication between the orchestrator and agents.
    
    This facade abstracts the underlying messaging mechanisms (PubSub vs. Streams)
    and provides a simple interface for sending and receiving messages.
    
    PubSub is used for:
    - Low-priority, non-critical messages (heartbeats, status updates)
    - Real-time notifications that don't require guaranteed delivery
    
    Streams are used for:
    - Critical messages that require guaranteed delivery (commands, results)
    - Messages that need acknowledgment and persistence
    """
    
    def __init__(
        self,
        connection_manager: RedisConnectionManager,
        component_id: str,
        component_type: str,
        pub_channels: List[str] = None,
        sub_channels: List[str] = None,
        stream_names: List[str] = None,
        max_stream_length: int = 1000,
        heartbeat_interval: int = 30  # seconds
    ):
        """
        Initialize the communication facade.
        
        Args:
            connection_manager: Redis connection manager instance
            component_id: Unique ID for this component
            component_type: Type of component (e.g., 'orchestrator', 'agent')
            pub_channels: Channels to publish to
            sub_channels: Channels to subscribe to
            stream_names: Names of streams to use
            max_stream_length: Maximum length of streams
            heartbeat_interval: Interval for sending heartbeats in seconds
        """
        self.connection_manager = connection_manager
        self.component_id = component_id
        self.component_type = component_type
        
        # Default channels if none provided
        self.pub_channels = pub_channels or [f"{component_type}.{component_id}.out"]
        self.sub_channels = sub_channels or [f"{component_type}.{component_id}.in"]
        
        # Default streams if none provided
        self.stream_names = stream_names or [
            f"stream.{component_type}.{component_id}.in",
            f"stream.{component_type}.{component_id}.out"
        ]
        
        # Initialize the messengers
        self.pubsub = PubSubMessenger(connection_manager)
        self.streams = StreamMessenger(
            connection_manager,
            consumer_name=component_id,
            max_stream_length=max_stream_length
        )
        
        # Track registered message handlers
        self.message_handlers: Dict[MessageType, List[Callable[[Message], Awaitable[bool]]]] = {}
        
        # Track message IDs we've sent, for correlation
        self.sent_messages: Dict[str, Dict[str, Any]] = {}
        
        # Heartbeat configuration
        self.heartbeat_interval = heartbeat_interval
        self.last_heartbeat_time = datetime.now()
        self.heartbeat_task = None
        
        logger.info(f"Communication facade initialized for {component_type} {component_id}")
    
    async def start(self) -> None:
        """
        Start the communication facade.
        
        This method starts the PubSub and Streams components and sets up
        message handling.
        """
        # Start PubSub
        for channel in self.sub_channels:
            self.pubsub.subscribe(channel, self._handle_pubsub_message)
        
        self.pubsub.start_listener()
        
        # Start Streams
        for stream in self.stream_names:
            self.streams.register_stream_handler(stream, self._handle_stream_message)
        
        self.streams.start_consumers()
        
        # Start heartbeat task
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        logger.info(f"Communication facade started for {self.component_type} {self.component_id}")
    
    async def stop(self) -> None:
        """
        Stop the communication facade.
        
        This method stops the PubSub and Streams components and cancels
        any background tasks.
        """
        # Stop PubSub
        self.pubsub.stop_listener()
        
        # Stop Streams
        self.streams.stop_consumers()
        
        # Cancel heartbeat task
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"Communication facade stopped for {self.component_type} {self.component_id}")
    
    async def send_message(
        self,
        message: Message,
        recipient_id: Optional[str] = None,
        priority: Optional[MessagePriority] = None
    ) -> str:
        """
        Send a message using the appropriate channel or stream.
        
        This method determines whether to use PubSub or Streams based on
        message priority and whether acknowledgment is required.
        
        Args:
            message: The message to send
            recipient_id: Optional recipient ID (overrides message.recipient_id)
            priority: Optional priority (overrides message.priority)
            
        Returns:
            The message ID
        """
        # Override recipient and priority if provided
        if recipient_id:
            message.recipient_id = recipient_id
        
        if priority:
            message.priority = priority
        
        # Use streams for critical messages and those requiring acknowledgment
        if message.priority == MessagePriority.CRITICAL or message.requires_ack:
            # Determine the appropriate stream
            stream = None
            for s in self.stream_names:
                if "out" in s:  # Outgoing stream
                    stream = s
                    break
            
            if not stream:
                stream = self.stream_names[0]
            
            # Add message to stream
            message_id = self.streams.add_message(stream, message)
            
            # Track the message
            if message_id:
                self.sent_messages[message.message_id] = {
                    "timestamp": datetime.now(),
                    "stream": stream,
                    "message": message,
                    "redis_id": message_id,
                    "acknowledged": False
                }
            
            return message.message_id
        else:
            # Use PubSub for non-critical messages
            channel = None
            for c in self.pub_channels:
                if "out" in c:  # Outgoing channel
                    channel = c
                    break
            
            if not channel:
                channel = self.pub_channels[0]
            
            # Publish message
            self.pubsub.publish(channel, message.to_json())
            
            # Track the message
            self.sent_messages[message.message_id] = {
                "timestamp": datetime.now(),
                "channel": channel,
                "message": message,
                "acknowledged": False
            }
            
            return message.message_id
    
    async def send_command(
        self,
        command: str,
        recipient_id: str,
        parameters: Dict[str, Any] = None,
        requires_ack: bool = True,
        priority: MessagePriority = MessagePriority.HIGH,
        expires_at: Optional[datetime] = None
    ) -> str:
        """
        Send a command to another component.
        
        Args:
            command: Command name
            recipient_id: Recipient component ID
            parameters: Command parameters
            requires_ack: Whether acknowledgment is required
            priority: Message priority
            expires_at: Optional expiry time
            
        Returns:
            The message ID
        """
        message = CommandMessage(
            message_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            sender_id=self.component_id,
            recipient_id=recipient_id,
            priority=priority,
            requires_ack=requires_ack,
            expires_at=expires_at.isoformat() if expires_at else None,
            command=command,
            parameters=parameters or {}
        )
        
        return await self.send_message(message)
    
    async def send_status(
        self,
        status: str,
        recipient_id: Optional[str] = None,
        details: Dict[str, Any] = None,
        priority: MessagePriority = MessagePriority.NORMAL
    ) -> str:
        """
        Send a status update.
        
        Args:
            status: Status string
            recipient_id: Optional recipient (broadcast if None)
            details: Additional status details
            priority: Message priority
            
        Returns:
            The message ID
        """
        message = StatusMessage(
            message_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            sender_id=self.component_id,
            recipient_id=recipient_id,
            priority=priority,
            requires_ack=False,
            expires_at=None,
            status=status,
            details=details or {}
        )
        
        return await self.send_message(message)
    
    async def send_result(
        self,
        command_id: str,
        recipient_id: str,
        success: bool,
        data: Dict[str, Any] = None,
        error: Optional[str] = None,
        priority: MessagePriority = MessagePriority.HIGH
    ) -> str:
        """
        Send a command result.
        
        Args:
            command_id: ID of the command this is a result for
            recipient_id: Component ID that sent the command
            success: Whether the command was successful
            data: Result data
            error: Error message (if not successful)
            priority: Message priority
            
        Returns:
            The message ID
        """
        message = ResultMessage(
            message_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            sender_id=self.component_id,
            recipient_id=recipient_id,
            priority=priority,
            requires_ack=True,
            expires_at=None,
            command_id=command_id,
            success=success,
            data=data or {},
            error=error
        )
        
        return await self.send_message(message)
    
    async def send_heartbeat(
        self,
        recipient_id: Optional[str] = None,
        status: str = "active",
        metrics: Dict[str, Any] = None
    ) -> str:
        """
        Send a heartbeat message.
        
        Args:
            recipient_id: Optional recipient (broadcast if None)
            status: Component status
            metrics: Optional metrics/stats
            
        Returns:
            The message ID
        """
        message = HeartbeatMessage(
            message_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            sender_id=self.component_id,
            recipient_id=recipient_id,
            priority=MessagePriority.LOW,
            requires_ack=False,
            expires_at=None,
            status=status,
            metrics=metrics or {}
        )
        
        self.last_heartbeat_time = datetime.now()
        return await self.send_message(message)
    
    def register_message_handler(
        self,
        message_type: MessageType,
        handler: Callable[[Message], Awaitable[bool]]
    ) -> None:
        """
        Register a handler for a specific message type.
        
        Args:
            message_type: Type of message to handle
            handler: Async callback function that processes messages
        """
        if message_type not in self.message_handlers:
            self.message_handlers[message_type] = []
        
        self.message_handlers[message_type].append(handler)
        logger.info(f"Registered handler for message type {message_type}")
    
    async def _handle_pubsub_message(self, channel: str, message: str) -> None:
        """
        Handle a message received via PubSub.
        
        Args:
            channel: Channel the message was received on
            message: Message data as JSON string
        """
        try:
            # Parse the message
            message_obj = Message.from_json(message)
            
            # Check if this message is for us
            if message_obj.recipient_id and message_obj.recipient_id != self.component_id:
                # Not for us, ignore
                return
            
            # Process the message
            await self._route_message(message_obj)
        except Exception as e:
            logger.error(f"Error handling PubSub message: {str(e)}", exc_info=True)
    
    async def _handle_stream_message(self, message: Message) -> bool:
        """
        Handle a message received via a Stream.
        
        Args:
            message: Message object
            
        Returns:
            True if processed successfully, False otherwise
        """
        try:
            # Check if this message is for us
            if message.recipient_id and message.recipient_id != self.component_id:
                # Not for us, acknowledge but don't process
                return True
            
            # Process the message
            return await self._route_message(message)
        except Exception as e:
            logger.error(f"Error handling Stream message: {str(e)}", exc_info=True)
            return False
    
    async def _route_message(self, message: Message) -> bool:
        """
        Route a message to the appropriate handlers.
        
        Args:
            message: Message to route
            
        Returns:
            True if processed successfully, False otherwise
        """
        try:
            # Get handlers for this message type
            handlers = self.message_handlers.get(message.message_type, [])
            
            if not handlers:
                logger.warning(f"No handlers for message type {message.message_type}")
                return False
            
            # Process with handlers
            success = False
            for handler in handlers:
                try:
                    # Execute the handler
                    result = await handler(message)
                    if result:
                        success = True
                except Exception as e:
                    logger.error(f"Error in message handler: {str(e)}", exc_info=True)
            
            return success
        except Exception as e:
            logger.error(f"Error routing message: {str(e)}", exc_info=True)
            return False
    
    async def _heartbeat_loop(self) -> None:
        """
        Background task that sends periodic heartbeats.
        """
        try:
            while True:
                # Send heartbeat if interval has elapsed
                time_since_last = (datetime.now() - self.last_heartbeat_time).total_seconds()
                if time_since_last >= self.heartbeat_interval:
                    await self.send_heartbeat()
                
                # Wait before checking again
                await asyncio.sleep(min(5, self.heartbeat_interval / 2))
        except asyncio.CancelledError:
            logger.info("Heartbeat task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in heartbeat loop: {str(e)}", exc_info=True)
    
    def get_message_status(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a sent message.
        
        Args:
            message_id: Message ID
            
        Returns:
            Message status information or None if not found
        """
        return self.sent_messages.get(message_id) 