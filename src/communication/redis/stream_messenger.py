"""
Redis Stream Messenger

This module implements reliable messaging using Redis Streams for
communications between the orchestrator and agents that require
persistence, acknowledgment, and delivery guarantees.
"""

import asyncio
import threading
import logging
from typing import Dict, Any, Callable, Optional, List, Union, Awaitable, Tuple
from datetime import datetime, timedelta
import json
import time
import uuid

from ...utils.logging.logger import get_logger
from .redis.connection_manager import RedisConnectionManager
from .redis.message_schema import Message, MessageType

logger = get_logger()

class StreamMessenger:
    """
    Handles reliable messaging via Redis Streams with acknowledgments and persistence.
    
    This class is responsible for:
    - Adding messages to streams
    - Creating and managing consumer groups
    - Processing new messages and pending messages
    - Handling message acknowledgments
    - Managing error conditions and retries
    
    Streams are used for critical messages where delivery guarantees are important,
    such as commands and their results.
    """
    
    def __init__(
        self, 
        connection_manager: RedisConnectionManager,
        consumer_name: str,
        group_prefix: str = "group",
        consumer_timeout: int = 100,  # ms
        max_retry_count: int = 3,
        retry_delay: int = 5,  # seconds
        cleanup_interval: int = 3600,  # seconds
        max_stream_length: int = 1000
    ):
        """
        Initialize the Stream messenger.
        
        Args:
            connection_manager: Redis connection manager instance
            consumer_name: Unique name for this consumer
            group_prefix: Prefix for consumer group names
            consumer_timeout: Timeout for blocking reads in milliseconds
            max_retry_count: Maximum number of retries for messages
            retry_delay: Delay between retries in seconds
            cleanup_interval: Interval for cleaning up acknowledged messages
            max_stream_length: Maximum number of messages in a stream
        """
        self.connection_manager = connection_manager
        self.redis = connection_manager.get_connection()
        self.consumer_name = consumer_name
        self.group_prefix = group_prefix
        self.consumer_timeout = consumer_timeout
        self.max_retry_count = max_retry_count
        self.retry_delay = retry_delay
        self.cleanup_interval = cleanup_interval
        self.max_stream_length = max_stream_length
        
        self.stream_handlers: Dict[str, List[Callable[[Message], Awaitable[bool]]]] = {}
        self.running = False
        self.consumer_threads: Dict[str, threading.Thread] = {}
        self.last_cleanup_time = time.time()
        
        logger.info(f"StreamMessenger initialized with consumer name: {consumer_name}")
    
    def _create_consumer_group(self, stream: str, group: str) -> bool:
        """
        Create a consumer group for a stream if it doesn't exist.
        
        Args:
            stream: Stream name
            group: Consumer group name
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Try to create the group
            self.redis.xgroup_create(stream, group, id='0', mkstream=True)
            logger.info(f"Created consumer group {group} for stream {stream}")
            return True
        except Exception as e:
            # Group already exists
            if hasattr(e, "__str__") and 'BUSYGROUP' in str(e):
                logger.debug(f"Consumer group {group} already exists for stream {stream}")
                return True
            logger.error(f"Failed to create consumer group: {str(e)}")
            return False
    
    def add_message(self, stream: str, message: Message) -> Optional[str]:
        """
        Add a message to a stream.
        
        Args:
            stream: The stream name
            message: The message to add
            
        Returns:
            The message ID if successful, None otherwise
        """
        try:
            # Serialize message to JSON
            message_json = message.to_json()
            
            # Flatten the dict for Redis streams (which expects simple key-value pairs)
            flattened_dict = {
                "message_data": message_json
            }
            
            # Add to stream with trimming to maintain max length
            message_id = self.redis.xadd(
                stream, 
                flattened_dict, 
                maxlen=self.max_stream_length
            )
            
            logger.debug(f"Added message {message.message_id} to stream {stream} with ID {message_id}")
            return message_id
        except Exception as e:
            logger.error(f"Failed to add message to stream {stream}: {str(e)}")
            return None
    
    def register_stream_handler(
        self, 
        stream: str, 
        handler: Callable[[Message], Awaitable[bool]],
        group: Optional[str] = None
    ) -> None:
        """
        Register a handler for messages from a stream.
        
        Args:
            stream: The stream name
            handler: Async callback function that processes messages and returns success flag
            group: Optional consumer group name (default: {group_prefix}:{consumer_name})
        """
        if stream not in self.stream_handlers:
            self.stream_handlers[stream] = []
        
        self.stream_handlers[stream].append(handler)
        
        # Default group name if not provided
        if group is None:
            group = f"{self.group_prefix}:{self.consumer_name}"
        
        # Ensure consumer group exists
        self._create_consumer_group(stream, group)
        
        logger.info(f"Registered handler for stream {stream} with group {group}")
    
    def start_consumers(self) -> None:
        """
        Start consumer threads for all registered streams.
        
        This method creates and starts a background thread for each stream
        that has registered handlers.
        """
        if self.running:
            logger.warning("Stream consumers are already running")
            return
        
        self.running = True
        
        # Start a consumer thread for each stream
        for stream in self.stream_handlers:
            group = f"{self.group_prefix}:{self.consumer_name}"
            
            # Create and start the thread
            thread = threading.Thread(
                target=self._consumer_loop,
                args=(stream, group),
                daemon=True,
                name=f"stream-consumer-{stream}"
            )
            self.consumer_threads[stream] = thread
            thread.start()
            
            logger.info(f"Started consumer thread for stream {stream}")
    
    def stop_consumers(self) -> None:
        """
        Stop all consumer threads.
        
        This method signals all consumer threads to stop and waits for them to terminate.
        """
        self.running = False
        
        # Wait for threads to terminate
        for stream, thread in self.consumer_threads.items():
            if thread.is_alive():
                thread.join(timeout=1.0)
                logger.info(f"Stopped consumer for stream {stream}")
        
        self.consumer_threads.clear()
    
    def _consumer_loop(self, stream: str, group: str) -> None:
        """
        Consumer loop for a stream.
        
        This method runs in a background thread and processes messages from a stream.
        
        Args:
            stream: Stream name
            group: Consumer group name
        """
        try:
            while self.running:
                # Check for pending messages (unacknowledged)
                self._process_pending_messages(stream, group)
                
                # Check for new messages
                self._process_new_messages(stream, group)
                
                # Periodic cleanup of acknowledged messages
                self._perform_periodic_cleanup(stream)
                
                # Small sleep to prevent tight loop
                time.sleep(0.1)
        except Exception as e:
            logger.error(f"Error in consumer loop for {stream}: {str(e)}", exc_info=True)
            if self.running:
                # Try to restart the consumer
                logger.info(f"Attempting to restart consumer for {stream}")
                new_thread = threading.Thread(
                    target=self._consumer_loop,
                    args=(stream, group),
                    daemon=True,
                    name=f"stream-consumer-{stream}"
                )
                self.consumer_threads[stream] = new_thread
                new_thread.start()
    
    def _process_pending_messages(self, stream: str, group: str) -> None:
        """
        Process pending (unacknowledged) messages.
        
        This method checks for messages that have been delivered but not acknowledged
        and attempts to reprocess them if they're due for a retry.
        
        Args:
            stream: Stream name
            group: Consumer group name
        """
        try:
            # Get pending messages for this consumer
            pending = self.redis.xpending_range(
                name=stream,
                groupname=group,
                min='-',
                max='+',
                count=10,
                consumername=self.consumer_name
            )
            
            for p in pending:
                message_id = p['message_id']
                delivery_count = p['times_delivered']
                
                # Skip if max retries exceeded
                if delivery_count > self.max_retry_count:
                    logger.warning(f"Message {message_id} in {stream} exceeded max retry count, skipping")
                    # Could implement dead-letter queue here
                    self.redis.xack(stream, group, message_id)
                    continue
                
                # Process the message if it's been idle long enough (retry delay)
                result = self.redis.xclaim(
                    name=stream,
                    groupname=group,
                    consumername=self.consumer_name,
                    min_idle_time=self.retry_delay * 1000,  # Convert to milliseconds
                    message_ids=[message_id]
                )
                
                if result:
                    self._handle_stream_message(stream, group, result[0])
        except Exception as e:
            logger.error(f"Error processing pending messages for {stream}: {str(e)}", exc_info=True)
    
    def _process_new_messages(self, stream: str, group: str) -> None:
        """
        Process new messages from the stream.
        
        This method checks for new messages that haven't been processed yet.
        
        Args:
            stream: Stream name
            group: Consumer group name
        """
        try:
            # Read new messages
            result = self.redis.xreadgroup(
                groupname=group,
                consumername=self.consumer_name,
                streams={stream: '>'},
                count=10,
                block=self.consumer_timeout
            )
            
            if result:
                for stream_data in result:
                    stream_name = stream_data[0]
                    messages = stream_data[1]
                    
                    for message in messages:
                        self._handle_stream_message(stream_name, group, message)
        except Exception as e:
            logger.error(f"Error processing new messages for {stream}: {str(e)}", exc_info=True)
    
    def _handle_stream_message(self, stream: str, group: str, message: Tuple) -> None:
        """
        Handle a message from a stream.
        
        This method processes a message by deserializing it and passing it to
        the registered handlers. If all handlers process the message successfully,
        it is acknowledged.
        
        Args:
            stream: Stream name
            group: Consumer group name
            message: Message tuple from Redis (id, fields)
        """
        try:
            # Unpack the message - careful about the types, as they might be bytes
            message_id, message_data = message
            
            # Convert message_id to string if it's bytes
            if isinstance(message_id, bytes):
                message_id = message_id.decode('utf-8')
            
            # Extract the message JSON
            message_json = None
            for key, value in message_data.items():
                # Find the message_data field
                key_str = key if isinstance(key, str) else key.decode('utf-8')
                if key_str == 'message_data':
                    message_json = value if isinstance(value, str) else value.decode('utf-8')
                    break
            
            if not message_json:
                logger.warning(f"Received malformed message without message_data field in {stream}")
                # Acknowledge to avoid reprocessing invalid messages
                self.redis.xack(stream, group, message_id)
                return
                
            # Parse the message
            message_obj = Message.from_json(message_json)
            
            # Process with handlers
            processed = False
            
            # Get the event loop or create one
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # No event loop in this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            for handler in self.stream_handlers.get(stream, []):
                try:
                    # Execute the handler
                    success = loop.run_until_complete(handler(message_obj))
                    
                    if success:
                        processed = True
                    else:
                        logger.warning(f"Handler failed to process message {message_id} in {stream}")
                except Exception as e:
                    logger.error(f"Error in stream message handler: {str(e)}", exc_info=True)
            
            # Acknowledge if processed successfully
            if processed:
                self.redis.xack(stream, group, message_id)
                logger.debug(f"Acknowledged message {message_id} in stream {stream}")
            
        except Exception as e:
            logger.error(f"Error handling stream message: {str(e)}", exc_info=True)
    
    def _perform_periodic_cleanup(self, stream: str) -> None:
        """
        Periodically clean up old messages.
        
        This method trims the stream to the maximum length and performs
        other cleanup operations at regular intervals.
        
        Args:
            stream: Stream name
        """
        current_time = time.time()
        if current_time - self.last_cleanup_time > self.cleanup_interval:
            try:
                # Trim the stream to max length
                self.redis.xtrim(stream, maxlen=self.max_stream_length)
                logger.debug(f"Trimmed stream {stream} to {self.max_stream_length} messages")
                
                # Update last cleanup time
                self.last_cleanup_time = current_time
            except Exception as e:
                logger.error(f"Error during stream cleanup: {str(e)}", exc_info=True)
    
    def read_stream(self, stream: str, count: int = 10, block: int = 1000) -> List[Tuple[str, Dict]]:
        """
        Read messages from a stream without using consumer groups.
        
        This is a simple read operation that doesn't involve acknowledgment.
        Useful for monitoring or debugging.
        
        Args:
            stream: Stream name
            count: Maximum number of messages to read
            block: Blocking timeout in milliseconds
            
        Returns:
            List of message tuples (id, fields)
        """
        try:
            result = self.redis.xread(
                streams={stream: '0'},
                count=count,
                block=block
            )
            
            if result:
                for stream_data in result:
                    stream_name = stream_data[0]
                    messages = stream_data[1]
                    return messages
                    
            return []
        except Exception as e:
            logger.error(f"Error reading from stream {stream}: {str(e)}")
            return [] 