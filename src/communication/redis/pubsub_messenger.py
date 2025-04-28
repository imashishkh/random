"""
Redis Pub/Sub Messenger

This module implements real-time messaging using Redis Pub/Sub for
non-critical communications between the orchestrator and agents.
"""

import asyncio
import threading
import logging
from typing import Dict, Any, Callable, Optional, List, Union
from datetime import datetime
import time

from ...utils.logging.logger import get_logger
from .redis.connection_manager import RedisConnectionManager
from .redis.message_schema import Message, MessageType

logger = get_logger()

class PubSubMessenger:
    """
    Handles Pub/Sub messaging for real-time, non-critical communications.
    
    This class is responsible for:
    - Subscribing to Redis channels
    - Publishing messages to channels
    - Routing incoming messages to appropriate handlers
    - Managing the background listener thread
    
    Pub/Sub is used for messages where delivery guarantees are not critical,
    such as status updates and heartbeats.
    """
    
    def __init__(self, connection_manager: RedisConnectionManager):
        """
        Initialize the Pub/Sub messenger.
        
        Args:
            connection_manager: Redis connection manager instance
        """
        self.connection_manager = connection_manager
        self.redis = connection_manager.get_connection()
        self.pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
        self.running = False
        self.subscription_handlers: Dict[str, List[Callable[[Message], None]]] = {}
        self.listener_thread = None
        
        logger.info("PubSubMessenger initialized")
    
    def start_listener(self) -> None:
        """
        Start the Pub/Sub listener thread.
        
        The listener thread runs in the background and processes incoming messages.
        """
        if self.running:
            logger.warning("Pub/Sub listener is already running")
            return
            
        self.running = True
        self.listener_thread = threading.Thread(
            target=self._listener_loop,
            daemon=True,
            name="redis-pubsub-listener"
        )
        self.listener_thread.start()
        logger.info("Started Pub/Sub listener thread")
    
    def stop_listener(self) -> None:
        """
        Stop the Pub/Sub listener thread.
        
        This method will unsubscribe from all channels and terminate the listener thread.
        """
        self.running = False
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join(timeout=1.0)
            logger.info("Stopped Pub/Sub listener thread")
        
        # Unsubscribe from all channels
        self.pubsub.unsubscribe()
        logger.info("Unsubscribed from all Pub/Sub channels")
    
    def subscribe(self, channel: str, handler: Callable[[Message], None]) -> None:
        """
        Subscribe to a channel with a message handler.
        
        Args:
            channel: The channel name to subscribe to
            handler: Callback function that processes messages
        """
        # Register the handler
        if channel not in self.subscription_handlers:
            self.subscription_handlers[channel] = []
        self.subscription_handlers[channel].append(handler)
        
        # Subscribe to the channel
        self.pubsub.subscribe(channel)
        logger.info(f"Subscribed to channel: {channel}")
    
    def unsubscribe(self, channel: str, handler: Optional[Callable] = None) -> None:
        """
        Unsubscribe from a channel.
        
        Args:
            channel: The channel to unsubscribe from
            handler: Optional specific handler to remove (if None, removes all)
        """
        if handler is None:
            # Remove all handlers for this channel
            self.subscription_handlers.pop(channel, None)
        else:
            # Remove specific handler
            if channel in self.subscription_handlers:
                try:
                    self.subscription_handlers[channel].remove(handler)
                except ValueError:
                    logger.warning(f"Handler not found for channel: {channel}")
                
                # If no handlers left, remove the channel
                if not self.subscription_handlers[channel]:
                    self.subscription_handlers.pop(channel)
        
        # Unsubscribe if no handlers left
        if channel not in self.subscription_handlers:
            self.pubsub.unsubscribe(channel)
            logger.info(f"Unsubscribed from channel: {channel}")
    
    def publish(self, channel: str, message: Message) -> bool:
        """
        Publish a message to a channel.
        
        Args:
            channel: The channel to publish to
            message: The message to publish
            
        Returns:
            True if published successfully, False otherwise
        """
        try:
            # Serialize message to JSON
            message_json = message.to_json()
            
            # Publish to channel
            self.redis.publish(channel, message_json)
            logger.debug(f"Published message to channel {channel}: {message.message_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish message to {channel}: {str(e)}")
            return False
    
    def _listener_loop(self) -> None:
        """
        Listen for messages in a background thread.
        
        This method runs in a separate thread and processes incoming messages.
        """
        try:
            while self.running:
                message = self.pubsub.get_message(timeout=0.1)
                if message and message['type'] == 'message':
                    self._process_message(message)
                
                # Small sleep to prevent tight loop
                time.sleep(0.01)
        except Exception as e:
            logger.error(f"Error in Pub/Sub listener: {str(e)}", exc_info=True)
            self.running = False
            
            # Attempt to restart the listener if unintentional shutdown
            if self.running:
                logger.info("Attempting to restart Pub/Sub listener...")
                self.start_listener()
    
    def _process_message(self, redis_message: Dict[str, Any]) -> None:
        """
        Process a message received from Redis Pub/Sub.
        
        Args:
            redis_message: Message data from Redis
        """
        try:
            # Extract channel and message data
            channel = redis_message['channel']
            data = redis_message['data']
            
            # Parse the message
            message = Message.from_json(data)
            
            # Check expiry
            if message.expires_at and message.expires_at < datetime.utcnow():
                logger.debug(f"Discarded expired message: {message.message_id}")
                return
                
            # Route to appropriate handlers
            if channel in self.subscription_handlers:
                for handler in self.subscription_handlers[channel]:
                    try:
                        handler(message)
                    except Exception as e:
                        logger.error(f"Error in message handler: {str(e)}", exc_info=True)
        except Exception as e:
            logger.error(f"Error processing Pub/Sub message: {str(e)}", exc_info=True) 