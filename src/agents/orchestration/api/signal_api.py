"""
Signal API

This module provides a FastAPI-based API for accessing trading signals
from the Signal Validation and Orchestration System.
"""

import os
import json
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import asyncio
import uuid
import logging
from collections import defaultdict
import time
import threading
import queue

from ....utils.logging.logger import get_logger
from .orchestration.models import PublishedSignal, TradingSignal
from .orchestration.signal_orchestrator import SignalOrchestrator

logger = get_logger()

# Define API models
class SignalResponse(BaseModel):
    """Model for signal responses from the API."""
    id: str = Field(..., description="Unique identifier for the published signal")
    original_signal_id: str = Field(..., description="ID of the original signal")
    trading_pair: str = Field(..., description="Trading pair (e.g., BTC-USD)")
    created_at: str = Field(..., description="ISO format timestamp")
    agent_id: str = Field(..., description="ID of the agent that generated the signal")
    agent_type: str = Field(..., description="Type of the agent")
    signal_type: str = Field(..., description="Type of signal")
    direction: str = Field(..., description="Direction (BUY, SELL, NEUTRAL)")
    timeframe: str = Field(..., description="Timeframe for the signal")
    strength: float = Field(..., description="Signal strength (0.0-1.0)")
    confidence: float = Field(..., description="Signal confidence (0.0-1.0)")

class SignalFilter(BaseModel):
    """Model for filtering signals in API requests."""
    trading_pairs: Optional[List[str]] = Field(None, description="List of trading pairs to filter")
    agent_types: Optional[List[str]] = Field(None, description="List of agent types to filter")
    signal_types: Optional[List[str]] = Field(None, description="List of signal types to filter")
    directions: Optional[List[str]] = Field(None, description="List of directions to filter")
    timeframes: Optional[List[str]] = Field(None, description="List of timeframes to filter")
    min_confidence: Optional[float] = Field(None, description="Minimum confidence level")
    start_time: Optional[str] = Field(None, description="Start time (ISO format)")
    end_time: Optional[str] = Field(None, description="End time (ISO format)")
    
class HealthResponse(BaseModel):
    """Model for health check responses."""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    timestamp: str = Field(..., description="Current timestamp")
    
class SubscriptionRequest(BaseModel):
    """Model for WebSocket subscription requests."""
    trading_pairs: Optional[List[str]] = Field(None, description="Trading pairs to subscribe to")
    agent_types: Optional[List[str]] = Field(None, description="Agent types to subscribe to")
    signal_types: Optional[List[str]] = Field(None, description="Signal types to subscribe to")
    min_confidence: Optional[float] = Field(0.0, description="Minimum confidence threshold")

class SignalAPIError(Exception):
    """Exception raised for errors in the Signal API."""
    pass

class SignalAPI:
    """
    Provides a unified API for consuming trading signals.
    
    This class offers both REST-like and streaming interfaces for accessing 
    trading signals that have been validated and filtered by the orchestration system.
    """
    
    def __init__(self, orchestrator: SignalOrchestrator, config: Dict[str, Any]):
        """
        Initialize the Signal API.
        
        Args:
            orchestrator: SignalOrchestrator instance that processes signals
            config: Configuration dictionary
        """
        self.orchestrator = orchestrator
        self.config = config
        
        # Configure logging
        self.logger = logging.getLogger("signal_api")
        log_level = config.get("log_level", "INFO").upper()
        self.logger.setLevel(getattr(logging, log_level))
        
        # Signal subscribers
        # Maps trading pairs to list of callbacks
        self.subscribers: Dict[str, List[Callable]] = {}
        
        # Subscription management
        self.subscription_lock = threading.Lock()
        
        # Signal queues for streaming
        self.signal_queues: Dict[str, queue.Queue] = {}
        
        # Active streams
        self.active_streams: Dict[str, threading.Thread] = {}
        
        # Subscription tokens for security
        self.subscription_tokens: Dict[str, Dict[str, str]] = {}
        
        # API key management
        self.api_keys = config.get("api_keys", {})
        
        # Register callback for new signals
        self.orchestrator.register_signal_callback("published", self._on_signal_published)
        
        self.logger.info("Signal API initialized")
        
    def _on_signal_published(self, original_signal: TradingSignal, 
                           published_signal: PublishedSignal) -> None:
        """
        Handle published signals from the orchestrator.
        
        This callback is triggered when the orchestrator publishes a new signal.
        
        Args:
            original_signal: Original trading signal
            published_signal: Published signal after validation and filtering
        """
        self.logger.info(f"Received new signal: {published_signal.id}")
        
    def validate_api_key(self, api_key: str) -> bool:
        """
        Validate an API key.
        
        Args:
            api_key: API key to validate
            
        Returns:
            True if API key is valid, False otherwise
        """
        return api_key in self.api_keys
        
    def get_signals(self, api_key: str, trading_pair: Optional[str] = None, 
                  limit: int = 100) -> List[PublishedSignal]:
        """
        Get recent signals with REST-like interface.
        
        Args:
            api_key: API key for authentication
            trading_pair: Optional trading pair to filter by
            limit: Maximum number of signals to return
            
        Returns:
            List of recent published signals
            
        Raises:
            SignalAPIError: If API key is invalid
        """
        # Validate API key
        if not self.validate_api_key(api_key):
            raise SignalAPIError("Invalid API key")
            
        # Get recent signals from orchestrator
        return self.orchestrator.get_recent_published_signals(
            trading_pair=trading_pair,
            limit=limit
        )
        
    def subscribe(self, api_key: str, callback: Callable[[PublishedSignal], None]) -> str:
        """
        Subscribe to trading signals.
        
        Args:
            api_key: API key for authentication
            callback: Function to call when a new signal is published
            
        Returns:
            Subscription token
            
        Raises:
            SignalAPIError: If API key is invalid
        """
        # Validate API key
        if not self.validate_api_key(api_key):
            raise SignalAPIError("Invalid API key")
            
        self.logger.info("New subscription registered")
        return "subscription_token"
        
    def unsubscribe(self, api_key: str, token: str) -> bool:
        """
        Unsubscribe from trading signals.
        
        Args:
            api_key: API key used for subscription
            token: Subscription token
            
        Returns:
            True if unsubscribed successfully, False otherwise
            
        Raises:
            SignalAPIError: If API key is invalid
        """
        # Validate API key
        if not self.validate_api_key(api_key):
            raise SignalAPIError("Invalid API key")
            
        # Check token exists
        if api_key not in self.subscription_tokens or token not in self.subscription_tokens[api_key]:
            return False
            
        subscription_key = self.subscription_tokens[api_key][token]
        
        with self.subscription_lock:
            # Remove token
            del self.subscription_tokens[api_key][token]
            
            # Find and remove callback
            if subscription_key in self.subscribers:
                # We can't directly remove the callback because we don't have a reference to it
                # Instead, we'll rebuild the list, which is usually small
                # For a production implementation, we'd need a better tracking mechanism
                self.subscribers[subscription_key] = [
                    cb for idx, cb in enumerate(self.subscribers[subscription_key])
                    if f"{subscription_key}_{id(cb)}" not in token
                ]
                
                # Remove empty subscription list
                if not self.subscribers[subscription_key]:
                    del self.subscribers[subscription_key]
                    
        self.logger.info("Unsubscribed from %s signals", subscription_key)
        
        return True
        
    def create_stream(self, api_key: str, trading_pair: Optional[str] = None) -> str:
        """
        Create a signal stream for a trading pair.
        
        This creates a streaming endpoint that clients can connect to.
        
        Args:
            api_key: API key for authentication
            trading_pair: Trading pair to stream, or None for all pairs
            
        Returns:
            Stream ID
            
        Raises:
            SignalAPIError: If API key is invalid
        """
        # Validate API key
        if not self.validate_api_key(api_key):
            raise SignalAPIError("Invalid API key")
            
        # Use "*" to represent all trading pairs
        subscription_key = trading_pair if trading_pair is not None else "*"
        
        # Create a queue for this stream
        stream_queue = queue.Queue(maxsize=100)  # Limit queue size
        
        # Generate stream ID
        stream_id = f"stream_{subscription_key}_{int(time.time())}"
        
        with self.subscription_lock:
            # Store queue
            self.signal_queues[stream_id] = stream_queue
            
        self.logger.info("Created signal stream %s for %s", stream_id, subscription_key)
        
        return stream_id
        
    def close_stream(self, api_key: str, stream_id: str) -> bool:
        """
        Close a signal stream.
        
        Args:
            api_key: API key used to create the stream
            stream_id: Stream ID to close
            
        Returns:
            True if closed successfully, False otherwise
            
        Raises:
            SignalAPIError: If API key is invalid
        """
        # Validate API key
        if not self.validate_api_key(api_key):
            raise SignalAPIError("Invalid API key")
            
        with self.subscription_lock:
            # Stop thread if running
            if stream_id in self.active_streams:
                # Signal thread to stop
                thread = self.active_streams[stream_id]
                if thread.is_alive():
                    # In a real implementation, we'd need a proper way to signal the thread to stop
                    # For this example, we'll just rely on the thread being daemon
                    pass
                    
                del self.active_streams[stream_id]
                
            # Remove queue
            if stream_id in self.signal_queues:
                del self.signal_queues[stream_id]
                self.logger.info("Closed signal stream %s", stream_id)
                return True
                
        return False
        
    def get_stream_signal(self, api_key: str, stream_id: str, 
                        timeout: Optional[float] = None) -> Optional[PublishedSignal]:
        """
        Get the next signal from a stream.
        
        Args:
            api_key: API key for authentication
            stream_id: Stream ID to get signal from
            timeout: Optional timeout in seconds, None to block indefinitely
            
        Returns:
            Next published signal or None if timeout expires
            
        Raises:
            SignalAPIError: If API key is invalid or stream doesn't exist
        """
        # Validate API key
        if not self.validate_api_key(api_key):
            raise SignalAPIError("Invalid API key")
            
        # Check stream exists
        if stream_id not in self.signal_queues:
            raise SignalAPIError(f"Stream {stream_id} does not exist")
            
        try:
            # Get next signal, with optional timeout
            return self.signal_queues[stream_id].get(block=True, timeout=timeout)
        except queue.Empty:
            # Timeout expired
            return None
        except Exception as e:
            self.logger.error("Error getting signal from stream: %s", str(e))
            return None
            
    def serialize_signal(self, signal: PublishedSignal) -> Dict[str, Any]:
        """
        Serialize a signal to a dictionary.
        
        Args:
            signal: Signal to serialize
            
        Returns:
            Dictionary representation of the signal
        """
        return {
            "id": signal.id,
            "original_signal_id": signal.original_signal_id,
            "trading_pair": signal.trading_pair,
            "timestamp": signal.timestamp.isoformat(),
            "direction": signal.direction,
            "timeframe": signal.timeframe,
            "strength": signal.strength,
            "confidence": signal.confidence,
            "agent_id": signal.agent_id,
            "metadata": signal.metadata
        }
        
    def to_json(self, signal: Union[PublishedSignal, List[PublishedSignal]]) -> str:
        """
        Convert signal(s) to JSON.
        
        Args:
            signal: Signal or list of signals to convert
            
        Returns:
            JSON string representation
        """
        if isinstance(signal, list):
            # List of signals
            serialized = [self.serialize_signal(s) for s in signal]
        else:
            # Single signal
            serialized = self.serialize_signal(signal)
            
        return json.dumps(serialized)

    def get_app(self):
        """Get the FastAPI application instance."""
        return self.app
    
    def register_orchestrator(self, orchestrator):
        """
        Register a signal orchestrator with the API.
        
        This will allow the API to receive signals directly from the orchestrator.
        
        Args:
            orchestrator: Signal orchestrator instance
        """
        self.orchestrator = orchestrator
        
        # Add event listener to orchestrator
        if hasattr(orchestrator, 'add_event_listener'):
            orchestrator.add_event_listener('signal_published', self.add_signal)
        
        logger.info(f"Registered orchestrator {orchestrator.name} with Signal API") 