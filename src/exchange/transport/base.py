"""
Base Transport Interface for Exchange Communications

This module defines the abstract base classes and interfaces for all
exchange communication transport methods (REST, WebSocket, etc.).
"""
import abc
import enum
import logging
import time
from typing import Dict, List, Any, Optional, Union, Callable, Tuple, TypeVar, Generic, Protocol
from dataclasses import dataclass, field
from datetime import datetime

T = TypeVar('T')  # Generic type for responses

# Configure logger
logger = logging.getLogger(__name__)

class TransportType(enum.Enum):
    """Enum defining the types of transport available."""
    REST = "rest"
    WEBSOCKET = "websocket"
    # Future transport types can be added here

class AuthType(enum.Enum):
    """Enum defining authentication types."""
    API_KEY = "api_key"
    JWT = "jwt"
    SESSION = "session"
    NONE = "none"

class ConnectionStatus(enum.Enum):
    """Enum defining connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECONNECTING = "reconnecting"

@dataclass
class RequestMetadata:
    """Metadata for a request."""
    timestamp: float = field(default_factory=time.time)
    endpoint: str = ""
    method: str = "GET"
    weight: int = 1
    priority: int = 1
    retry_count: int = 0
    max_retries: int = 3
    timeout: float = 30.0
    auth_required: bool = False
    rate_limited: bool = True

@dataclass
class ResponseMetadata:
    """Metadata for a response."""
    timestamp: float = field(default_factory=time.time)
    status_code: int = 200
    error: Optional[str] = None
    rate_limit_info: Dict[str, Any] = field(default_factory=dict)
    latency: float = 0.0

@dataclass
class Request:
    """Generic request object for all transport types."""
    path: str
    params: Dict[str, Any] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, Any] = field(default_factory=dict)
    metadata: RequestMetadata = field(default_factory=RequestMetadata)

@dataclass
class Response(Generic[T]):
    """Generic response object for all transport types."""
    data: T
    metadata: ResponseMetadata = field(default_factory=ResponseMetadata)
    raw: Any = None  # Raw response from the transport

class RetryPolicy(Protocol):
    """Protocol defining a retry policy."""
    
    def should_retry(self, response: Response, attempt: int) -> bool:
        """
        Determine if a request should be retried.
        
        Args:
            response: The response received
            attempt: The current attempt number
            
        Returns:
            Whether to retry the request
        """
        ...
    
    def get_delay(self, response: Response, attempt: int) -> float:
        """
        Get the delay before retrying a request.
        
        Args:
            response: The response received
            attempt: The current attempt number
            
        Returns:
            Delay in seconds
        """
        ...

class BaseTransport(abc.ABC):
    """
    Abstract base class for all transport methods.
    
    This class defines the interface that all transport implementations
    must follow, providing a consistent way to interact with different
    exchange communication methods.
    """
    
    def __init__(
        self,
        exchange: str,
        base_url: str,
        auth_type: AuthType = AuthType.NONE,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_policy: Optional[RetryPolicy] = None,
        enable_rate_limit: bool = True
    ):
        """
        Initialize the base transport.
        
        Args:
            exchange: Name of the exchange
            base_url: Base URL for the exchange API
            auth_type: Type of authentication to use
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            retry_policy: Policy for determining when to retry requests
            enable_rate_limit: Whether to enable rate limiting
        """
        self.exchange = exchange
        self.base_url = base_url
        self.auth_type = auth_type
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_policy = retry_policy
        self.enable_rate_limit = enable_rate_limit
        
        # Connection state
        self.status = ConnectionStatus.DISCONNECTED
        self.connected_since = None
        self.disconnect_reason = None
        
        # Performance metrics
        self.requests_count = 0
        self.errors_count = 0
        self.retries_count = 0
        self.avg_latency = 0.0
        
        logger.info(f"Initialized {self.__class__.__name__} for {exchange}")
    
    @property
    @abc.abstractmethod
    def transport_type(self) -> TransportType:
        """Get the transport type."""
        pass
    
    @abc.abstractmethod
    async def connect(self) -> bool:
        """
        Connect to the exchange API.
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def disconnect(self) -> bool:
        """
        Disconnect from the exchange API.
        
        Returns:
            bool: True if disconnection was successful, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def is_connected(self) -> bool:
        """
        Check if the transport is connected.
        
        Returns:
            bool: True if connected, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def send(self, request: Request) -> Response:
        """
        Send a request to the exchange API.
        
        Args:
            request: Request to send
            
        Returns:
            Response: Response from the exchange
        """
        pass
    
    @abc.abstractmethod
    async def subscribe(self, channel: str, callback: Callable[[Response], None]) -> bool:
        """
        Subscribe to a real-time data channel.
        
        Args:
            channel: Channel to subscribe to
            callback: Function to call with received data
            
        Returns:
            bool: True if subscription was successful, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def unsubscribe(self, channel: str) -> bool:
        """
        Unsubscribe from a real-time data channel.
        
        Args:
            channel: Channel to unsubscribe from
            
        Returns:
            bool: True if unsubscription was successful, False otherwise
        """
        pass
    
    def update_metrics(self, latency: float, is_error: bool = False, is_retry: bool = False) -> None:
        """
        Update performance metrics.
        
        Args:
            latency: Request latency in seconds
            is_error: Whether the request resulted in an error
            is_retry: Whether the request was a retry
        """
        self.requests_count += 1
        
        if is_error:
            self.errors_count += 1
        
        if is_retry:
            self.retries_count += 1
        
        # Update average latency
        self.avg_latency = (self.avg_latency * (self.requests_count - 1) + latency) / self.requests_count
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics.
        
        Returns:
            Dict: Dictionary of metrics
        """
        return {
            "requests_count": self.requests_count,
            "errors_count": self.errors_count,
            "errors_rate": self.errors_count / max(self.requests_count, 1) * 100,
            "retries_count": self.retries_count, 
            "avg_latency": self.avg_latency,
            "status": self.status.value,
            "uptime": time.time() - self.connected_since if self.connected_since else 0
        }

class DefaultRetryPolicy(RetryPolicy):
    """Default implementation of a retry policy."""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0):
        """
        Initialize the default retry policy.
        
        Args:
            max_retries: Maximum number of retries
            base_delay: Base delay between retries in seconds
            max_delay: Maximum delay between retries in seconds
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
    
    def should_retry(self, response: Response, attempt: int) -> bool:
        """
        Determine if a request should be retried.
        
        Args:
            response: The response received
            attempt: The current attempt number
            
        Returns:
            Whether to retry the request
        """
        # Don't retry if reached max attempts
        if attempt >= self.max_retries:
            return False
        
        # Retry network errors and rate limit errors
        if response.metadata.error:
            if "timeout" in response.metadata.error.lower():
                return True
            if "network" in response.metadata.error.lower():
                return True
            if "rate limit" in response.metadata.error.lower():
                return True
            if "too many requests" in response.metadata.error.lower():
                return True
        
        # Retry server errors (5xx)
        if response.metadata.status_code >= 500:
            return True
        
        # Retry rate limit errors (429)
        if response.metadata.status_code == 429:
            return True
        
        return False
    
    def get_delay(self, response: Response, attempt: int) -> float:
        """
        Get the delay before retrying a request.
        
        Args:
            response: The response received
            attempt: The current attempt number
            
        Returns:
            Delay in seconds
        """
        # Exponential backoff
        delay = self.base_delay * (2 ** (attempt - 1))
        
        # Check for explicit rate limit delay
        if response.metadata.status_code == 429:
            rate_limit_info = response.metadata.rate_limit_info
            if rate_limit_info and "retry_after" in rate_limit_info:
                delay = float(rate_limit_info["retry_after"])
        
        # Cap at max delay
        return min(delay, self.max_delay) 