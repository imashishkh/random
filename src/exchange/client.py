from enum import Enum
from typing import Dict, List, Optional, Any, Union, Callable, Type

from .transport.base import BaseTransport
from .transport.rest import RestTransport
from .transport.websocket import WebSocketTransport
from .auth.provider import AuthProvider
from .rate_limiting.limiter import RateLimiter
import src.exchange.exceptions as exc


class TransportType(Enum):
    """Available transport types for exchange communication."""
    REST = "REST"
    WEBSOCKET = "WEBSOCKET"


class MarketOperation(Enum):
    """Market operations available on exchanges."""
    # Market data operations
    GET_TICKER = "GET_TICKER"
    GET_ORDER_BOOK = "GET_ORDER_BOOK"
    GET_RECENT_TRADES = "GET_RECENT_TRADES"
    GET_KLINES = "GET_KLINES"
    GET_24H_STATS = "GET_24H_STATS"
    
    # Trading operations
    CREATE_ORDER = "CREATE_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    GET_ORDER = "GET_ORDER"
    GET_OPEN_ORDERS = "GET_OPEN_ORDERS"
    GET_ORDER_HISTORY = "GET_ORDER_HISTORY"
    
    # Account operations
    GET_ACCOUNT_INFO = "GET_ACCOUNT_INFO"
    GET_BALANCES = "GET_BALANCES"
    GET_DEPOSIT_HISTORY = "GET_DEPOSIT_HISTORY"
    GET_WITHDRAWAL_HISTORY = "GET_WITHDRAWAL_HISTORY"
    GET_DEPOSIT_ADDRESS = "GET_DEPOSIT_ADDRESS"
    CREATE_WITHDRAWAL = "CREATE_WITHDRAWAL"


class ExchangeClient:
    """
    Unified client for interacting with cryptocurrency exchanges.
    
    This client provides a consistent interface for performing operations
    across different exchanges using either REST or WebSocket transport methods.
    """
    
    def __init__(
        self, 
        exchange_id: str,
        base_url: str,
        ws_url: Optional[str] = None,
        auth_provider: Optional[AuthProvider] = None,
        rate_limiter: Optional[RateLimiter] = None
    ):
        """
        Initialize a new exchange client.
        
        Args:
            exchange_id: Unique identifier for the exchange
            base_url: Base URL for REST API
            ws_url: WebSocket URL (if different from base_url)
            auth_provider: Authentication provider (optional, can be set later)
            rate_limiter: Rate limiter (optional, can be set later)
        """
        self.exchange_id = exchange_id
        self.base_url = base_url
        self.ws_url = ws_url or base_url.replace('https://', 'wss://')
        self.auth_provider = auth_provider
        self.rate_limiter = rate_limiter
        
        # Transport instances
        self._transports: Dict[TransportType, BaseTransport] = {}
        
        # Subscription handlers for WebSocket
        self._subscription_handlers: Dict[str, List[Callable]] = {}
        
        # Operation mappings (exchange-specific)
        self._operation_mappings: Dict[MarketOperation, Dict[str, Any]] = {}
        
    def _get_transport(self, transport_type: TransportType) -> BaseTransport:
        """
        Get or create a transport instance for the specified type.
        
        Args:
            transport_type: Type of transport to get
            
        Returns:
            Transport instance
            
        Raises:
            ValueError: If transport type is not supported
        """
        if transport_type not in self._transports:
            if transport_type == TransportType.REST:
                self._transports[transport_type] = RestTransport(
                    exchange_id=self.exchange_id,
                    base_url=self.base_url,
                    auth_provider=self.auth_provider,
                    rate_limiter=self.rate_limiter
                )
            elif transport_type == TransportType.WEBSOCKET:
                self._transports[transport_type] = WebSocketTransport(
                    exchange_id=self.exchange_id,
                    ws_url=self.ws_url,
                    auth_provider=self.auth_provider,
                    rate_limiter=self.rate_limiter
                )
            else:
                raise ValueError(f"Unsupported transport type: {transport_type}")
                
        return self._transports[transport_type]
    
    def create_request(
        self, 
        operation: MarketOperation,
        params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Create a normalized request for the specified operation.
        
        Args:
            operation: Market operation to perform
            params: Operation-specific parameters
            
        Returns:
            Normalized request dictionary
        """
        params = params or {}
        
        if operation not in self._operation_mappings:
            raise exc.UnsupportedOperationError(
                f"Operation {operation} not supported for exchange {self.exchange_id}"
            )
            
        operation_config = self._operation_mappings[operation]
        
        # Apply default parameters
        request_params = operation_config.get('defaults', {}).copy()
        request_params.update(params)
        
        # Build the normalized request
        request = {
            'operation': operation,
            'endpoint': operation_config['endpoint'],
            'method': operation_config.get('method', 'GET'),
            'params': request_params,
            'requires_auth': operation_config.get('requires_auth', False),
            'weight': operation_config.get('weight', 1),
            'rate_limit_type': operation_config.get('rate_limit_type', 'REQUEST_WEIGHT')
        }
        
        return request
    
    def execute(
        self,
        operation: MarketOperation,
        params: Dict[str, Any] = None,
        transport_type: TransportType = TransportType.REST
    ) -> Any:
        """
        Execute a market operation using the specified transport.
        
        Args:
            operation: Market operation to perform
            params: Operation-specific parameters
            transport_type: Transport type to use (default: REST)
            
        Returns:
            Operation result
        """
        # Create normalized request
        request = self.create_request(operation, params)
        
        # Get appropriate transport
        transport = self._get_transport(transport_type)
        
        # Execute the request
        return transport.execute_request(request)
    
    def subscribe(
        self,
        channel: str,
        handler: Callable,
        params: Dict[str, Any] = None
    ) -> str:
        """
        Subscribe to a WebSocket channel.
        
        Args:
            channel: Channel name to subscribe to
            handler: Callback function for incoming messages
            params: Subscription parameters
            
        Returns:
            Subscription ID
        """
        ws_transport = self._get_transport(TransportType.WEBSOCKET)
        
        if not isinstance(ws_transport, WebSocketTransport):
            raise TypeError("WebSocket transport required for subscriptions")
            
        # Register the handler
        if channel not in self._subscription_handlers:
            self._subscription_handlers[channel] = []
        self._subscription_handlers[channel].append(handler)
        
        # Subscribe to the channel
        subscription_id = ws_transport.subscribe(channel, handler, params)
        return subscription_id
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from a WebSocket channel.
        
        Args:
            subscription_id: Subscription ID to unsubscribe
            
        Returns:
            True if successful, False otherwise
        """
        if TransportType.WEBSOCKET not in self._transports:
            return False
            
        ws_transport = self._transports[TransportType.WEBSOCKET]
        return ws_transport.unsubscribe(subscription_id)
    
    def close(self) -> None:
        """Close all transport connections."""
        for transport in self._transports.values():
            transport.close()
            
    def __enter__(self):
        """Enable context manager support."""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources when exiting context."""
        self.close()


class ExchangeClientFactory:
    """Factory for creating exchange-specific client instances."""
    
    _registered_clients: Dict[str, Type[ExchangeClient]] = {}
    
    @classmethod
    def register(cls, exchange_id: str, client_class: Type[ExchangeClient]) -> None:
        """
        Register an exchange-specific client class.
        
        Args:
            exchange_id: Exchange identifier
            client_class: Exchange client class
        """
        cls._registered_clients[exchange_id] = client_class
        
    @classmethod
    def create(
        cls, 
        exchange_id: str,
        *args, 
        **kwargs
    ) -> ExchangeClient:
        """
        Create an exchange client instance.
        
        Args:
            exchange_id: Exchange identifier
            *args: Positional arguments for client constructor
            **kwargs: Keyword arguments for client constructor
            
        Returns:
            Exchange client instance
            
        Raises:
            ValueError: If exchange is not supported
        """
        if exchange_id not in cls._registered_clients:
            # Fall back to generic client if no specific implementation
            return ExchangeClient(exchange_id=exchange_id, *args, **kwargs)
            
        client_class = cls._registered_clients[exchange_id]
        return client_class(exchange_id=exchange_id, *args, **kwargs) 