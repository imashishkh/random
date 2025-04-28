"""
High-performance message queue architecture for order execution system communication.
"""
from enum import Enum
from typing import Dict, Any, Optional, List, Callable, Union, Type
import logging
import json
import threading
import time
import uuid
from datetime import datetime
from queue import Queue, Empty

# Configure logger
logger = logging.getLogger(__name__)

class MessageType(Enum):
    """Enumeration of available message types for system communication."""
    ORDER_NEW = "order.new"
    ORDER_CANCEL = "order.cancel"
    ORDER_UPDATE = "order.update"
    ORDER_STATUS = "order.status"
    EXECUTION_REPORT = "execution.report"
    MARKET_DATA = "market.data"
    HEARTBEAT = "system.heartbeat"
    ERROR = "system.error"
    COMMAND = "system.command"


class Message:
    """Base message class for queue communication."""
    
    def __init__(self, 
                 message_type: MessageType, 
                 payload: Dict[str, Any],
                 message_id: Optional[str] = None,
                 correlation_id: Optional[str] = None,
                 source: Optional[str] = None,
                 timestamp: Optional[float] = None,
                 headers: Optional[Dict[str, Any]] = None):
        """
        Initialize a new message.
        
        Args:
            message_type: Type of message (from MessageType enum)
            payload: Message payload as a dictionary
            message_id: Unique ID for this message (generated if not provided)
            correlation_id: ID for correlating related messages
            source: Component that generated the message
            timestamp: Message creation time (generated if not provided)
            headers: Additional message headers
        """
        self.message_type = message_type
        self.payload = payload
        self.message_id = message_id or str(uuid.uuid4())
        self.correlation_id = correlation_id
        self.source = source
        self.timestamp = timestamp or time.time()
        self.headers = headers or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the message to a dictionary for serialization."""
        return {
            "message_type": self.message_type.value,
            "payload": self.payload,
            "message_id": self.message_id,
            "correlation_id": self.correlation_id,
            "source": self.source,
            "timestamp": self.timestamp,
            "headers": self.headers
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create a message from a dictionary representation."""
        return cls(
            message_type=MessageType(data["message_type"]),
            payload=data["payload"],
            message_id=data["message_id"],
            correlation_id=data.get("correlation_id"),
            source=data.get("source"),
            timestamp=data.get("timestamp"),
            headers=data.get("headers", {})
        )
    
    def to_json(self) -> str:
        """Convert the message to a JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Message':
        """Create a message from a JSON string."""
        return cls.from_dict(json.loads(json_str))


class MessageSerializer:
    """Utility class for serializing and deserializing messages."""
    
    @staticmethod
    def serialize(message: Message) -> bytes:
        """Serialize a message to bytes for transmission."""
        return message.to_json().encode('utf-8')
    
    @staticmethod
    def deserialize(data: bytes) -> Message:
        """Deserialize a message from bytes."""
        return Message.from_json(data.decode('utf-8'))


class MessageFilter:
    """Filter for subscribing to specific message types or with specific properties."""
    
    def __init__(self, 
                 message_types: Optional[List[MessageType]] = None,
                 source: Optional[str] = None,
                 correlation_id: Optional[str] = None,
                 header_filters: Optional[Dict[str, Any]] = None,
                 payload_filters: Optional[Dict[str, Any]] = None):
        """
        Initialize a message filter.
        
        Args:
            message_types: Types of messages to filter for
            source: Source to filter for
            correlation_id: Correlation ID to filter for
            header_filters: Values that must be present in message headers
            payload_filters: Values that must be present in message payload
        """
        self.message_types = message_types
        self.source = source
        self.correlation_id = correlation_id
        self.header_filters = header_filters
        self.payload_filters = payload_filters
    
    def matches(self, message: Message) -> bool:
        """Check if a message matches this filter."""
        if self.message_types and message.message_type not in self.message_types:
            return False
        
        if self.source and message.source != self.source:
            return False
        
        if self.correlation_id and message.correlation_id != self.correlation_id:
            return False
        
        if self.header_filters:
            for key, value in self.header_filters.items():
                if key not in message.headers or message.headers[key] != value:
                    return False
        
        if self.payload_filters:
            for key, value in self.payload_filters.items():
                if key not in message.payload or message.payload[key] != value:
                    return False
        
        return True


class MessageBus:
    """
    Central message bus for publishing and subscribing to messages.
    Implements a publish-subscribe pattern.
    """
    
    def __init__(self):
        """Initialize the message bus."""
        self.subscribers: List[tuple[MessageFilter, Callable[[Message], None]]] = []
        self.lock = threading.Lock()
        self._running = False
        self._queue = Queue()
        self._worker_thread = None
        self.latency_tracking = False
        self.latency_stats = {
            "count": 0,
            "total_latency": 0,
            "max_latency": 0,
            "min_latency": float("inf")
        }
    
    def start(self):
        """Start the message bus processing thread."""
        with self.lock:
            if self._running:
                return
            
            self._running = True
            self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
            self._worker_thread.start()
            logger.info("Message bus started")
    
    def stop(self):
        """Stop the message bus processing thread."""
        with self.lock:
            self._running = False
            
            if self._worker_thread:
                self._worker_thread.join(timeout=1.0)
                if self._worker_thread.is_alive():
                    logger.warning("Message bus worker thread did not terminate cleanly")
                self._worker_thread = None
            
            logger.info("Message bus stopped")
    
    def _process_queue(self):
        """Worker thread to process messages from the queue."""
        while self._running:
            try:
                message, enqueue_time = self._queue.get(timeout=0.1)
                
                if self.latency_tracking:
                    now = time.time()
                    latency = now - enqueue_time
                    with self.lock:
                        self.latency_stats["count"] += 1
                        self.latency_stats["total_latency"] += latency
                        self.latency_stats["max_latency"] = max(self.latency_stats["max_latency"], latency)
                        self.latency_stats["min_latency"] = min(self.latency_stats["min_latency"], latency)
                
                self._dispatch_message(message)
                self._queue.task_done()
            except Empty:
                pass
            except Exception as e:
                logger.error(f"Error processing message queue: {e}")
    
    def _dispatch_message(self, message: Message):
        """Dispatch a message to all matching subscribers."""
        matching_subscribers = [
            subscriber for message_filter, subscriber in self.subscribers
            if message_filter.matches(message)
        ]
        
        for subscriber in matching_subscribers:
            try:
                subscriber(message)
            except Exception as e:
                logger.error(f"Error in subscriber processing message {message.message_id}: {e}")
    
    def publish(self, message: Message):
        """
        Publish a message to the bus.
        
        Args:
            message: Message to publish
        """
        if not self._running:
            logger.warning("Attempted to publish message to stopped message bus")
            return
        
        self._queue.put((message, time.time()))
    
    def subscribe(self, message_filter: MessageFilter, subscriber: Callable[[Message], None]):
        """
        Subscribe to messages matching a filter.
        
        Args:
            message_filter: Filter for messages to subscribe to
            subscriber: Callback function to receive matching messages
        """
        with self.lock:
            self.subscribers.append((message_filter, subscriber))
    
    def unsubscribe(self, subscriber: Callable[[Message], None]):
        """
        Unsubscribe a subscriber from all message filters.
        
        Args:
            subscriber: Subscriber to remove
        """
        with self.lock:
            self.subscribers = [
                (message_filter, sub) for message_filter, sub in self.subscribers
                if sub != subscriber
            ]
    
    def enable_latency_tracking(self, enabled: bool = True):
        """
        Enable or disable latency tracking.
        
        Args:
            enabled: Whether to enable latency tracking
        """
        self.latency_tracking = enabled
        
        if enabled:
            # Reset stats
            with self.lock:
                self.latency_stats = {
                    "count": 0,
                    "total_latency": 0,
                    "max_latency": 0,
                    "min_latency": float("inf")
                }
    
    def get_latency_stats(self) -> Dict[str, Any]:
        """Get current latency statistics."""
        with self.lock:
            stats = self.latency_stats.copy()
            
            if stats["count"] > 0:
                stats["average_latency"] = stats["total_latency"] / stats["count"]
                
                if stats["min_latency"] == float("inf"):
                    stats["min_latency"] = 0
            else:
                stats["average_latency"] = 0
                stats["min_latency"] = 0
            
            return stats


class LocalQueue:
    """
    A high-performance local queue for intra-process communication.
    Optimized for low-latency single-process use cases.
    """
    
    def __init__(self, name: str, max_size: int = 10000):
        """
        Initialize a local queue.
        
        Args:
            name: Name of the queue
            max_size: Maximum queue size
        """
        self.name = name
        self.queue = Queue(maxsize=max_size)
        self.subscribers: List[Callable[[Message], None]] = []
        self.lock = threading.Lock()
        self._running = False
        self._worker_thread = None
    
    def start(self):
        """Start the queue processing thread."""
        with self.lock:
            if self._running:
                return
            
            self._running = True
            self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
            self._worker_thread.start()
            logger.info(f"Local queue '{self.name}' started")
    
    def stop(self):
        """Stop the queue processing thread."""
        with self.lock:
            self._running = False
            
            if self._worker_thread:
                self._worker_thread.join(timeout=1.0)
                if self._worker_thread.is_alive():
                    logger.warning(f"Local queue '{self.name}' worker thread did not terminate cleanly")
                self._worker_thread = None
            
            logger.info(f"Local queue '{self.name}' stopped")
    
    def _process_queue(self):
        """Worker thread to process messages from the queue."""
        while self._running:
            try:
                message = self.queue.get(timeout=0.1)
                
                with self.lock:
                    for subscriber in self.subscribers:
                        try:
                            subscriber(message)
                        except Exception as e:
                            logger.error(f"Error in subscriber processing message from '{self.name}': {e}")
                
                self.queue.task_done()
            except Empty:
                pass
            except Exception as e:
                logger.error(f"Error processing queue '{self.name}': {e}")
    
    def publish(self, message: Message):
        """
        Publish a message to the queue.
        
        Args:
            message: Message to publish
        """
        if not self._running:
            logger.warning(f"Attempted to publish message to stopped queue '{self.name}'")
            return
        
        try:
            self.queue.put(message, block=False)
        except Exception:
            logger.warning(f"Queue '{self.name}' is full, dropping message")
    
    def subscribe(self, subscriber: Callable[[Message], None]):
        """
        Subscribe to messages from this queue.
        
        Args:
            subscriber: Callback function to receive messages
        """
        with self.lock:
            self.subscribers.append(subscriber)
    
    def unsubscribe(self, subscriber: Callable[[Message], None]):
        """
        Unsubscribe from this queue.
        
        Args:
            subscriber: Subscriber to remove
        """
        with self.lock:
            self.subscribers = [sub for sub in self.subscribers if sub != subscriber]


class MessageQueueFactory:
    """Factory for creating and managing message queues and buses."""
    
    def __init__(self):
        """Initialize the message queue factory."""
        self.buses: Dict[str, MessageBus] = {}
        self.local_queues: Dict[str, LocalQueue] = {}
        self.lock = threading.Lock()
    
    def get_or_create_bus(self, name: str) -> MessageBus:
        """
        Get or create a message bus.
        
        Args:
            name: Name of the bus
            
        Returns:
            The message bus
        """
        with self.lock:
            if name not in self.buses:
                self.buses[name] = MessageBus()
                self.buses[name].start()
            
            return self.buses[name]
    
    def get_or_create_local_queue(self, name: str, max_size: int = 10000) -> LocalQueue:
        """
        Get or create a local queue.
        
        Args:
            name: Name of the queue
            max_size: Maximum queue size
            
        Returns:
            The local queue
        """
        with self.lock:
            if name not in self.local_queues:
                self.local_queues[name] = LocalQueue(name, max_size)
                self.local_queues[name].start()
            
            return self.local_queues[name]
    
    def shutdown(self):
        """Shutdown all message buses and queues."""
        with self.lock:
            for bus in self.buses.values():
                bus.stop()
            
            for queue in self.local_queues.values():
                queue.stop()
            
            self.buses.clear()
            self.local_queues.clear()


# Create a global factory instance
factory = MessageQueueFactory()

# Export the classes
__all__ = [
    "MessageType",
    "Message",
    "MessageSerializer",
    "MessageFilter",
    "MessageBus",
    "LocalQueue",
    "MessageQueueFactory",
    "factory"
] 