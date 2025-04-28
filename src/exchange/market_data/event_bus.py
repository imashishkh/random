"""
Event Bus module for market data events.

This module implements the Observer Pattern for distributing market events
to interested components.
"""
import asyncio
import logging
import time
from collections import defaultdict
from typing import Dict, Set, Any, Callable, Awaitable, Optional, List

logger = logging.getLogger(__name__)

class MarketEventBus:
    """
    Event bus for market data events.
    
    Implements the Observer Pattern for distributing market events
    to interested components.
    """
    
    _instance = None  # Singleton instance
    
    @classmethod
    def get_instance(cls, *args, **kwargs):
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls(*args, **kwargs)
        return cls._instance
    
    def __init__(self, max_queue_size: int = 1000):
        """
        Initialize the event bus.
        
        Args:
            max_queue_size: Maximum number of events to buffer
        """
        self.subscribers = defaultdict(set)  # topic -> set of callbacks
        self.priorities = {}  # callback -> priority
        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.running = False
        self.processor_task = None
        
        # Performance metrics
        self.events_processed = 0
        self.events_dropped = 0
        self.processing_times = []  # Rolling window of last 100 processing times
        
        logger.info("Market event bus initialized")
    
    def subscribe(self, topic: str, callback: Callable, priority: int = 0) -> 'Subscription':
        """
        Subscribe to a topic.
        
        Args:
            topic: Event topic to subscribe to
            callback: Async function to call when an event occurs
            priority: Priority level (higher = processed first)
            
        Returns:
            Subscription object for easy unsubscription
        """
        self.subscribers[topic].add(callback)
        self.priorities[callback] = priority
        logger.debug(f"Subscribed to topic: {topic} with priority {priority}")
        
        # Return a subscription object for easy unsubscription
        return Subscription(self, topic, callback)
    
    def unsubscribe(self, topic: str, callback: Callable) -> None:
        """
        Unsubscribe from a topic.
        
        Args:
            topic: Event topic to unsubscribe from
            callback: Callback to remove
        """
        if topic in self.subscribers and callback in self.subscribers[topic]:
            self.subscribers[topic].remove(callback)
            logger.debug(f"Unsubscribed from topic: {topic}")
            
            # Clean up priorities if no longer needed
            if callback in self.priorities:
                del self.priorities[callback]
            
            # Clean up topic if no subscribers left
            if not self.subscribers[topic]:
                del self.subscribers[topic]
    
    async def publish(self, topic: str, data: Any) -> bool:
        """
        Publish an event to a topic.
        
        Args:
            topic: Event topic
            data: Event data
            
        Returns:
            bool: True if event was queued, False if dropped
        """
        try:
            # Create event with timestamp
            event = {
                "topic": topic,
                "data": data,
                "timestamp": time.time()
            }
            
            # Try to put event in queue with a timeout
            try:
                await asyncio.wait_for(
                    self.queue.put(event),
                    timeout=0.1  # 100ms timeout
                )
                return True
            except asyncio.TimeoutError:
                # Queue is full, increment dropped counter
                self.events_dropped += 1
                logger.warning(f"Event queue full, dropped event for topic: {topic}")
                return False
            
        except Exception as e:
            logger.error(f"Error publishing event: {str(e)}")
            return False
    
    async def start(self) -> None:
        """Start the event processing loop."""
        if self.running:
            logger.warning("Event bus already running")
            return
        
        self.running = True
        self.processor_task = asyncio.create_task(self._process_events())
        logger.info("Event bus started")
    
    async def stop(self) -> None:
        """Stop the event processing loop."""
        if not self.running:
            logger.warning("Event bus not running")
            return
        
        self.running = False
        if self.processor_task:
            self.processor_task.cancel()
            try:
                await self.processor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Event bus stopped")
    
    async def _process_events(self) -> None:
        """Process events from the queue."""
        while self.running:
            try:
                # Get event from queue
                event = await self.queue.get()
                
                # Extract topic and data
                topic = event["topic"]
                data = event["data"]
                timestamp = event["timestamp"]
                
                # Start processing timing
                start_time = time.time()
                
                # Get callbacks for this topic, including wildcard subscribers
                callbacks = set()
                
                # Add exact topic subscribers
                callbacks.update(self.subscribers.get(topic, set()))
                
                # Add wildcard subscribers
                if ".*" in topic:
                    base_topic = topic.split(".*")[0]
                    wildcard_topic = f"{base_topic}.*"
                    callbacks.update(self.subscribers.get(wildcard_topic, set()))
                
                # Sort by priority (higher first)
                sorted_callbacks = sorted(
                    callbacks,
                    key=lambda cb: self.priorities.get(cb, 0),
                    reverse=True
                )
                
                # Execute callbacks
                for callback in sorted_callbacks:
                    try:
                        await callback(topic, data)
                    except Exception as e:
                        logger.error(f"Error in event handler for {topic}: {str(e)}")
                
                # Record processing time
                processing_time = time.time() - start_time
                self.processing_times.append(processing_time)
                
                # Keep only the last 100 processing times
                if len(self.processing_times) > 100:
                    self.processing_times.pop(0)
                
                # Increment processed counter
                self.events_processed += 1
                
                # Mark task as done
                self.queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing event: {str(e)}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics.
        
        Returns:
            Dict with performance metrics
        """
        avg_processing_time = (
            sum(self.processing_times) / len(self.processing_times)
            if self.processing_times else 0
        )
        
        return {
            "events_processed": self.events_processed,
            "events_dropped": self.events_dropped,
            "queue_size": self.queue.qsize(),
            "queue_full": self.queue.full(),
            "avg_processing_time": avg_processing_time,
            "subscriber_count": sum(len(subs) for subs in self.subscribers.values())
        }


class Subscription:
    """Subscription object for managing event subscriptions."""
    
    def __init__(self, bus: MarketEventBus, topic: str, callback: Callable):
        """
        Initialize a subscription.
        
        Args:
            bus: Event bus
            topic: Topic subscribed to
            callback: Callback function
        """
        self.bus = bus
        self.topic = topic
        self.callback = callback
    
    def unsubscribe(self) -> None:
        """Unsubscribe from the topic."""
        self.bus.unsubscribe(self.topic, self.callback) 