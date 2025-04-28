"""
Unified Exchange Client Interface

This module provides a high-level client interface that abstracts away
the differences between REST and WebSocket transport methods, providing
a consistent API for exchange operations with intelligent transport selection
and automatic failover capabilities.
"""
from typing import Dict, List, Optional, Any, Union, Callable, Type, Tuple
from enum import Enum
import logging
import time
import asyncio
from dataclasses import dataclass

from .transport.base import BaseTransport, TransportType, Request, Response
from .transport.rest import RestTransport
from .transport.websocket import WebSocketTransport
from .auth.provider import AuthProvider
from .rate_limiting.limiter import RateLimiter
import src.exchange.exceptions as exc
from .client import MarketOperation, ExchangeClient, TransportType as ClientTransportType


# Configure logger
logger = logging.getLogger(__name__)


class TransportPreference(Enum):
    """Preference for transport selection."""
    AUTO = "auto"  # Automatically select the best transport
    REST_PREFERRED = "rest_preferred"  # Prefer REST but fallback to WebSocket
    WEBSOCKET_PREFERRED = "websocket_preferred"  # Prefer WebSocket but fallback to REST
    REST_ONLY = "rest_only"  # Only use REST
    WEBSOCKET_ONLY = "websocket_only"  # Only use WebSocket


class OperationCategory(Enum):
    """Categories of market operations."""
    MARKET_DATA = "market_data"
    ACCOUNT = "account"
    TRADING = "trading"
    SUBSCRIPTION = "subscription"


# Mapping of operations to their categories
OPERATION_CATEGORIES = {
    # Market data
    MarketOperation.GET_TICKER: OperationCategory.MARKET_DATA,
    MarketOperation.GET_ORDER_BOOK: OperationCategory.MARKET_DATA,
    MarketOperation.GET_RECENT_TRADES: OperationCategory.MARKET_DATA,
    MarketOperation.GET_KLINES: OperationCategory.MARKET_DATA,
    MarketOperation.GET_24H_STATS: OperationCategory.MARKET_DATA,
    
    # Trading
    MarketOperation.CREATE_ORDER: OperationCategory.TRADING,
    MarketOperation.CANCEL_ORDER: OperationCategory.TRADING,
    MarketOperation.GET_ORDER: OperationCategory.TRADING,
    MarketOperation.GET_OPEN_ORDERS: OperationCategory.TRADING,
    MarketOperation.GET_ORDER_HISTORY: OperationCategory.TRADING,
    
    # Account
    MarketOperation.GET_ACCOUNT_INFO: OperationCategory.ACCOUNT,
    MarketOperation.GET_BALANCES: OperationCategory.ACCOUNT,
    MarketOperation.GET_DEPOSIT_HISTORY: OperationCategory.ACCOUNT,
    MarketOperation.GET_WITHDRAWAL_HISTORY: OperationCategory.ACCOUNT,
    MarketOperation.GET_DEPOSIT_ADDRESS: OperationCategory.ACCOUNT,
    MarketOperation.CREATE_WITHDRAWAL: OperationCategory.ACCOUNT,
}


# Default transport preferences by operation category
DEFAULT_TRANSPORT_PREFERENCES = {
    OperationCategory.MARKET_DATA: TransportPreference.WEBSOCKET_PREFERRED,
    OperationCategory.ACCOUNT: TransportPreference.REST_PREFERRED,
    OperationCategory.TRADING: TransportPreference.REST_PREFERRED,
    OperationCategory.SUBSCRIPTION: TransportPreference.WEBSOCKET_ONLY,
}


@dataclass
class TransportMetrics:
    """Metrics for transport performance tracking."""
    success_count: int = 0
    error_count: int = 0
    total_latency: float = 0.0
    avg_latency: float = 0.0
    last_success_time: Optional[float] = None
    last_error_time: Optional[float] = None
    consecutive_errors: int = 0

    def record_success(self, latency: float) -> None:
        """Record a successful operation."""
        self.success_count += 1
        self.total_latency += latency
        self.avg_latency = self.total_latency / self.success_count
        self.last_success_time = time.time()
        self.consecutive_errors = 0

    def record_error(self) -> None:
        """Record a failed operation."""
        self.error_count += 1
        self.last_error_time = time.time()
        self.consecutive_errors += 1


class TransportManager:
    """
    Manages transport connections and selects optimal transport for operations.
    
    This class is responsible for maintaining transport connections,
    monitoring their health, and selecting the appropriate transport
    for different types of operations based on preferences and metrics.
    """
    
    def __init__(
        self,
        exchange_id: str,
        base_url: str,
        ws_url: Optional[str] = None,
        auth_provider: Optional[AuthProvider] = None,
        rate_limiter: Optional[RateLimiter] = None,
        transport_preferences: Optional[Dict[OperationCategory, TransportPreference]] = None
    ):
        """
        Initialize the transport manager.
        
        Args:
            exchange_id: Unique identifier for the exchange
            base_url: Base URL for REST API
            ws_url: WebSocket URL (if different from base_url)
            auth_provider: Authentication provider
            rate_limiter: Rate limiter
            transport_preferences: Mapping of operation categories to transport preferences
        """
        self.exchange_id = exchange_id
        self.base_url = base_url
        self.ws_url = ws_url or base_url.replace('https://', 'wss://')
        self.auth_provider = auth_provider
        self.rate_limiter = rate_limiter
        
        # Set transport preferences (use defaults if not provided)
        self.transport_preferences = transport_preferences or DEFAULT_TRANSPORT_PREFERENCES.copy()
        
        # Initialize transports (but don't connect yet)
        self._transports = {
            ClientTransportType.REST: None,
            ClientTransportType.WEBSOCKET: None
        }
        
        # Initialize metrics for each transport
        self._metrics = {
            ClientTransportType.REST: TransportMetrics(),
            ClientTransportType.WEBSOCKET: TransportMetrics()
        }
        
        # Transport availability
        self._available = {
            ClientTransportType.REST: True,
            ClientTransportType.WEBSOCKET: True
        }
        
        # Initialize operation-specific metrics
        self._operation_metrics = {}
        for operation in MarketOperation:
            self._operation_metrics[operation] = {
                ClientTransportType.REST: TransportMetrics(),
                ClientTransportType.WEBSOCKET: TransportMetrics()
            }
        
        logger.info(f"Initialized TransportManager for {exchange_id}")
    
    def get_transport(self, transport_type: ClientTransportType) -> ExchangeClient:
        """
        Get or create a transport instance for the specified type.
        
        Args:
            transport_type: Type of transport to get
            
        Returns:
            Transport instance
            
        Raises:
            ValueError: If transport type is not supported
        """
        if self._transports[transport_type] is None:
            if transport_type == ClientTransportType.REST:
                self._transports[transport_type] = ExchangeClient(
                    exchange_id=self.exchange_id,
                    base_url=self.base_url,
                    auth_provider=self.auth_provider,
                    rate_limiter=self.rate_limiter
                )
            elif transport_type == ClientTransportType.WEBSOCKET:
                self._transports[transport_type] = ExchangeClient(
                    exchange_id=self.exchange_id,
                    base_url=self.base_url,
                    ws_url=self.ws_url,
                    auth_provider=self.auth_provider,
                    rate_limiter=self.rate_limiter
                )
            else:
                raise ValueError(f"Unsupported transport type: {transport_type}")
                
        return self._transports[transport_type]
    
    def select_transport(
        self, 
        operation: MarketOperation,
        override_preference: Optional[TransportPreference] = None
    ) -> Tuple[ClientTransportType, ExchangeClient]:
        """
        Select the optimal transport for an operation.
        
        Args:
            operation: Market operation to perform
            override_preference: Override the default transport preference
            
        Returns:
            Tuple of (selected transport type, transport instance)
            
        Raises:
            exc.NoAvailableTransportError: If no suitable transport is available
        """
        # Get operation category
        category = OPERATION_CATEGORIES.get(operation, OperationCategory.MARKET_DATA)
        
        # Get preference (use override if provided)
        preference = override_preference or self.transport_preferences.get(
            category, TransportPreference.AUTO
        )
        
        # Handle strict preferences first
        if preference == TransportPreference.REST_ONLY:
            if not self._available[ClientTransportType.REST]:
                raise exc.NoAvailableTransportError(
                    f"REST transport required but not available for operation {operation}"
                )
            return ClientTransportType.REST, self.get_transport(ClientTransportType.REST)
            
        if preference == TransportPreference.WEBSOCKET_ONLY:
            if not self._available[ClientTransportType.WEBSOCKET]:
                raise exc.NoAvailableTransportError(
                    f"WebSocket transport required but not available for operation {operation}"
                )
            return ClientTransportType.WEBSOCKET, self.get_transport(ClientTransportType.WEBSOCKET)
        
        # Handle preferences with fallbacks
        primary, secondary = self._get_primary_secondary_transports(preference)
        
        # Check if primary is available
        if self._available[primary]:
            return primary, self.get_transport(primary)
        
        # Fall back to secondary if primary not available
        if self._available[secondary]:
            logger.warning(
                f"Primary transport {primary} not available for {operation}. "
                f"Falling back to {secondary}."
            )
            return secondary, self.get_transport(secondary)
        
        # No transports available
        raise exc.NoAvailableTransportError(
            f"No transport available for operation {operation}"
        )
    
    def _get_primary_secondary_transports(
        self, 
        preference: TransportPreference
    ) -> Tuple[ClientTransportType, ClientTransportType]:
        """
        Get primary and secondary transport types based on preference.
        
        Args:
            preference: Transport preference
            
        Returns:
            Tuple of (primary, secondary) transport types
        """
        if preference == TransportPreference.REST_PREFERRED:
            return ClientTransportType.REST, ClientTransportType.WEBSOCKET
        elif preference == TransportPreference.WEBSOCKET_PREFERRED:
            return ClientTransportType.WEBSOCKET, ClientTransportType.REST
        elif preference == TransportPreference.AUTO:
            # For AUTO, make a decision based on metrics
            # For simplicity, we'll just use WebSocket if it has better latency
            rest_metrics = self._metrics[ClientTransportType.REST]
            ws_metrics = self._metrics[ClientTransportType.WEBSOCKET]
            
            # If WebSocket has better average latency and enough successful operations, use it
            if (ws_metrics.success_count > 10 and 
                ws_metrics.avg_latency < rest_metrics.avg_latency and
                ws_metrics.consecutive_errors < 3):
                return ClientTransportType.WEBSOCKET, ClientTransportType.REST
            
            # Otherwise default to REST
            return ClientTransportType.REST, ClientTransportType.WEBSOCKET
        
        # Default to REST preferred
        return ClientTransportType.REST, ClientTransportType.WEBSOCKET
    
    def update_metrics(
        self, 
        transport_type: ClientTransportType, 
        operation: MarketOperation,
        success: bool, 
        latency: float
    ) -> None:
        """
        Update transport metrics after an operation.
        
        Args:
            transport_type: Type of transport used
            operation: Operation performed
            success: Whether the operation was successful
            latency: Operation latency in seconds
        """
        # Update general transport metrics
        transport_metrics = self._metrics[transport_type]
        
        # Update operation-specific metrics
        operation_metrics = self._operation_metrics[operation][transport_type]
        
        if success:
            transport_metrics.record_success(latency)
            operation_metrics.record_success(latency)
            
            # Reset availability if it was marked unavailable
            if not self._available[transport_type]:
                logger.info(
                    f"Transport {transport_type} is now available again"
                )
                self._available[transport_type] = True
        else:
            transport_metrics.record_error()
            operation_metrics.record_error()
            
            # Check if we should mark this transport as unavailable
            if transport_metrics.consecutive_errors >= 3:
                logger.warning(
                    f"Marking transport {transport_type} as unavailable due to "
                    f"{transport_metrics.consecutive_errors} consecutive errors"
                )
                self._available[transport_type] = False
    
    def close(self) -> None:
        """Close all transport connections."""
        for transport in self._transports.values():
            if transport is not None:
                transport.close()


class UnifiedClient:
    """
    Unified client interface for cryptocurrency exchanges.
    
    This high-level client provides a consistent interface for interacting
    with cryptocurrency exchanges, automatically selecting the optimal
    transport method (REST or WebSocket) based on the operation type
    and current system conditions.
    """
    
    def __init__(
        self, 
        exchange_id: str,
        base_url: str,
        ws_url: Optional[str] = None,
        auth_provider: Optional[AuthProvider] = None,
        rate_limiter: Optional[RateLimiter] = None,
        transport_preferences: Optional[Dict[OperationCategory, TransportPreference]] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 30.0
    ):
        """
        Initialize the unified client.
        
        Args:
            exchange_id: Unique identifier for the exchange
            base_url: Base URL for REST API
            ws_url: WebSocket URL (if different from base_url)
            auth_provider: Authentication provider
            rate_limiter: Rate limiter
            transport_preferences: Mapping of operation categories to transport preferences
            max_retries: Maximum number of retries for operations
            retry_delay: Base delay between retries (in seconds)
            timeout: Default timeout for operations (in seconds)
        """
        self.exchange_id = exchange_id
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        
        # Initialize transport manager
        self.transport_manager = TransportManager(
            exchange_id=exchange_id,
            base_url=base_url,
            ws_url=ws_url,
            auth_provider=auth_provider,
            rate_limiter=rate_limiter,
            transport_preferences=transport_preferences
        )
        
        # Subscription handlers for WebSocket
        self._subscription_handlers = {}
        
        logger.info(f"Initialized UnifiedClient for {exchange_id}")
    
    def execute(
        self,
        operation: MarketOperation,
        params: Dict[str, Any] = None,
        transport_preference: Optional[TransportPreference] = None,
        max_retries: Optional[int] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Execute a market operation with automatic transport selection and failover.
        
        Args:
            operation: Market operation to perform
            params: Operation-specific parameters
            transport_preference: Override default transport preference
            max_retries: Override default max retries
            timeout: Override default timeout
            
        Returns:
            Operation result as a dictionary
            
        Raises:
            exc.ExchangeError: If the operation fails after all retries
        """
        params = params or {}
        max_retries = max_retries if max_retries is not None else self.max_retries
        retry_count = 0
        last_error = None
        tried_transports = set()
        
        start_time = time.time()
        
        # Retry loop
        while retry_count <= max_retries:
            try:
                # Select transport (excluding ones we've already tried if possible)
                transport_type, transport = self._select_transport(
                    operation, transport_preference, tried_transports
                )
                
                # Keep track of which transports we've tried
                tried_transports.add(transport_type)
                
                # Execute the operation
                operation_start = time.time()
                result = transport.execute(
                    operation=operation,
                    params=params,
                    transport_type=self._client_to_internal_transport_type(transport_type)
                )
                operation_latency = time.time() - operation_start
                
                # Update metrics
                self.transport_manager.update_metrics(
                    transport_type=transport_type,
                    operation=operation,
                    success=True,
                    latency=operation_latency
                )
                
                # Log success
                total_latency = time.time() - start_time
                logger.debug(
                    f"Operation {operation} succeeded using {transport_type} "
                    f"transport after {retry_count} retries. "
                    f"Latency: {operation_latency:.3f}s, Total: {total_latency:.3f}s"
                )
                
                return result
                
            except Exception as e:
                last_error = e
                
                # Update metrics
                self.transport_manager.update_metrics(
                    transport_type=transport_type,
                    operation=operation,
                    success=False,
                    latency=0.0
                )
                
                # Log error
                logger.warning(
                    f"Operation {operation} failed using {transport_type} transport: {str(e)}. "
                    f"Retry {retry_count}/{max_retries}"
                )
                
                # Increment retry counter
                retry_count += 1
                
                # If we have more retries, wait before trying again
                if retry_count <= max_retries:
                    # Exponential backoff
                    delay = self.retry_delay * (2 ** (retry_count - 1))
                    time.sleep(delay)
        
        # If we get here, all retries failed
        error_msg = f"Operation {operation} failed after {max_retries} retries"
        logger.error(f"{error_msg}. Last error: {str(last_error)}")
        
        # Raise an appropriate exception
        if isinstance(last_error, exc.ExchangeError):
            raise last_error
        else:
            raise exc.ExchangeError(f"{error_msg}: {str(last_error)}")
    
    def _select_transport(
        self,
        operation: MarketOperation,
        transport_preference: Optional[TransportPreference],
        tried_transports: set
    ) -> Tuple[ClientTransportType, ExchangeClient]:
        """
        Select a transport, avoiding ones we've already tried if possible.
        
        Args:
            operation: Market operation to perform
            transport_preference: Override default transport preference
            tried_transports: Set of transport types already tried
            
        Returns:
            Tuple of (selected transport type, transport instance)
            
        Raises:
            exc.NoAvailableTransportError: If no suitable transport is available
        """
        # If we've tried all transports, just use the default selection
        if len(tried_transports) >= len(ClientTransportType):
            return self.transport_manager.select_transport(operation, transport_preference)
        
        # Try to get a transport we haven't tried yet
        try:
            # First, try to get primary transport
            transport_type, transport = self.transport_manager.select_transport(
                operation, transport_preference
            )
            
            # If we've already tried this one, try to get the other type
            if transport_type in tried_transports:
                other_type = (
                    ClientTransportType.WEBSOCKET 
                    if transport_type == ClientTransportType.REST 
                    else ClientTransportType.REST
                )
                
                # Only use the other type if it's available
                if self.transport_manager._available[other_type]:
                    transport_type = other_type
                    transport = self.transport_manager.get_transport(other_type)
            
            return transport_type, transport
            
        except exc.NoAvailableTransportError:
            # If no transport is available, re-raise
            raise
    
    def _client_to_internal_transport_type(
        self, 
        transport_type: ClientTransportType
    ) -> Union[str, int]:
        """
        Convert client transport type to the internal format used by ExchangeClient.
        
        Args:
            transport_type: Client transport type
            
        Returns:
            Internal transport type
        """
        if transport_type == ClientTransportType.REST:
            return "REST"
        elif transport_type == ClientTransportType.WEBSOCKET:
            return "WEBSOCKET"
        else:
            raise ValueError(f"Unsupported transport type: {transport_type}")
    
    # Higher-level operation methods
    
    def get_ticker(self, symbol: str, **kwargs) -> Dict[str, Any]:
        """
        Get ticker information for a symbol.
        
        Args:
            symbol: Symbol to get ticker for (e.g., 'BTC/USDT')
            **kwargs: Additional parameters
            
        Returns:
            Ticker information
        """
        return self.execute(
            operation=MarketOperation.GET_TICKER,
            params={"symbol": symbol, **kwargs}
        )
    
    def get_order_book(self, symbol: str, limit: int = 100, **kwargs) -> Dict[str, Any]:
        """
        Get order book for a symbol.
        
        Args:
            symbol: Symbol to get order book for (e.g., 'BTC/USDT')
            limit: Number of levels to retrieve
            **kwargs: Additional parameters
            
        Returns:
            Order book information
        """
        return self.execute(
            operation=MarketOperation.GET_ORDER_BOOK,
            params={"symbol": symbol, "limit": limit, **kwargs}
        )
    
    def get_recent_trades(self, symbol: str, limit: int = 100, **kwargs) -> Dict[str, Any]:
        """
        Get recent trades for a symbol.
        
        Args:
            symbol: Symbol to get trades for (e.g., 'BTC/USDT')
            limit: Number of trades to retrieve
            **kwargs: Additional parameters
            
        Returns:
            Recent trades information
        """
        return self.execute(
            operation=MarketOperation.GET_RECENT_TRADES,
            params={"symbol": symbol, "limit": limit, **kwargs}
        )
    
    def get_klines(
        self, 
        symbol: str, 
        interval: str, 
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get candlestick data for a symbol.
        
        Args:
            symbol: Symbol to get klines for (e.g., 'BTC/USDT')
            interval: Kline interval (e.g., '1m', '1h', '1d')
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            limit: Number of klines to retrieve
            **kwargs: Additional parameters
            
        Returns:
            Kline information
        """
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            **kwargs
        }
        
        if start_time is not None:
            params["startTime"] = start_time
            
        if end_time is not None:
            params["endTime"] = end_time
            
        return self.execute(
            operation=MarketOperation.GET_KLINES,
            params=params
        )
    
    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a new order.
        
        Args:
            symbol: Symbol to create order for (e.g., 'BTC/USDT')
            order_type: Order type (e.g., 'limit', 'market')
            side: Order side (e.g., 'buy', 'sell')
            amount: Order amount
            price: Order price (required for limit orders)
            **kwargs: Additional parameters
            
        Returns:
            Order information
        """
        params = {
            "symbol": symbol,
            "type": order_type,
            "side": side,
            "amount": amount,
            **kwargs
        }
        
        if price is not None:
            params["price"] = price
            
        return self.execute(
            operation=MarketOperation.CREATE_ORDER,
            params=params,
            # Always use REST for orders unless explicitly overridden
            transport_preference=TransportPreference.REST_PREFERRED
        )
    
    def cancel_order(self, order_id: str, symbol: str, **kwargs) -> Dict[str, Any]:
        """
        Cancel an existing order.
        
        Args:
            order_id: Order ID to cancel
            symbol: Symbol the order was created for
            **kwargs: Additional parameters
            
        Returns:
            Cancellation information
        """
        return self.execute(
            operation=MarketOperation.CANCEL_ORDER,
            params={"orderId": order_id, "symbol": symbol, **kwargs},
            # Always use REST for orders unless explicitly overridden
            transport_preference=TransportPreference.REST_PREFERRED
        )
    
    def get_order(self, order_id: str, symbol: str, **kwargs) -> Dict[str, Any]:
        """
        Get information about an order.
        
        Args:
            order_id: Order ID to get information for
            symbol: Symbol the order was created for
            **kwargs: Additional parameters
            
        Returns:
            Order information
        """
        return self.execute(
            operation=MarketOperation.GET_ORDER,
            params={"orderId": order_id, "symbol": symbol, **kwargs}
        )
    
    def get_account_info(self, **kwargs) -> Dict[str, Any]:
        """
        Get account information.
        
        Args:
            **kwargs: Additional parameters
            
        Returns:
            Account information
        """
        return self.execute(
            operation=MarketOperation.GET_ACCOUNT_INFO,
            params=kwargs
        )
    
    def get_balances(self, **kwargs) -> Dict[str, Any]:
        """
        Get account balances.
        
        Args:
            **kwargs: Additional parameters
            
        Returns:
            Balance information
        """
        return self.execute(
            operation=MarketOperation.GET_BALANCES,
            params=kwargs
        )
    
    def subscribe_ticker(self, symbol: str, callback: Callable) -> str:
        """
        Subscribe to ticker updates for a symbol.
        
        Args:
            symbol: Symbol to subscribe to (e.g., 'BTC/USDT')
            callback: Function to call when updates are received
            
        Returns:
            Subscription ID
        """
        # Get WebSocket transport
        transport_type, transport = self.transport_manager.select_transport(
            operation=MarketOperation.GET_TICKER,
            override_preference=TransportPreference.WEBSOCKET_ONLY
        )
        
        # Subscribe to the channel
        return transport.subscribe(
            channel=f"ticker.{symbol}",
            handler=callback
        )
    
    def subscribe_order_book(self, symbol: str, callback: Callable) -> str:
        """
        Subscribe to order book updates for a symbol.
        
        Args:
            symbol: Symbol to subscribe to (e.g., 'BTC/USDT')
            callback: Function to call when updates are received
            
        Returns:
            Subscription ID
        """
        # Get WebSocket transport
        transport_type, transport = self.transport_manager.select_transport(
            operation=MarketOperation.GET_ORDER_BOOK,
            override_preference=TransportPreference.WEBSOCKET_ONLY
        )
        
        # Subscribe to the channel
        return transport.subscribe(
            channel=f"orderbook.{symbol}",
            handler=callback
        )
    
    def subscribe_trades(self, symbol: str, callback: Callable) -> str:
        """
        Subscribe to trade updates for a symbol.
        
        Args:
            symbol: Symbol to subscribe to (e.g., 'BTC/USDT')
            callback: Function to call when updates are received
            
        Returns:
            Subscription ID
        """
        # Get WebSocket transport
        transport_type, transport = self.transport_manager.select_transport(
            operation=MarketOperation.GET_RECENT_TRADES,
            override_preference=TransportPreference.WEBSOCKET_ONLY
        )
        
        # Subscribe to the channel
        return transport.subscribe(
            channel=f"trades.{symbol}",
            handler=callback
        )
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from a WebSocket channel.
        
        Args:
            subscription_id: Subscription ID to unsubscribe
            
        Returns:
            True if successful, False otherwise
        """
        # Try with WebSocket transport
        try:
            transport_type, transport = self.transport_manager.select_transport(
                operation=MarketOperation.GET_TICKER,  # Any operation will do
                override_preference=TransportPreference.WEBSOCKET_ONLY
            )
            return transport.unsubscribe(subscription_id)
        except exc.NoAvailableTransportError:
            logger.error("Cannot unsubscribe: WebSocket transport not available")
            return False
    
    def close(self) -> None:
        """Close all connections and clean up resources."""
        self.transport_manager.close()
    
    def __enter__(self):
        """Enable context manager support."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources when exiting context."""
        self.close()


class UnifiedClientFactory:
    """
    Factory for creating exchange-specific unified client instances.
    
    This factory handles the creation and configuration of unified clients
    for different exchanges, applying exchange-specific settings and
    operation mappings as needed.
    """
    
    _registered_exchanges: Dict[str, Dict[str, Any]] = {}
    
    @classmethod
    def register_exchange(
        cls,
        exchange_id: str,
        base_url: str,
        ws_url: Optional[str] = None,
        transport_preferences: Optional[Dict[OperationCategory, TransportPreference]] = None,
        operation_mappings: Optional[Dict[MarketOperation, Dict[str, Any]]] = None
    ) -> None:
        """
        Register an exchange with the factory.
        
        Args:
            exchange_id: Unique identifier for the exchange
            base_url: Base URL for REST API
            ws_url: WebSocket URL (if different from base_url)
            transport_preferences: Mapping of operation categories to transport preferences
            operation_mappings: Exchange-specific operation mappings
        """
        cls._registered_exchanges[exchange_id] = {
            "base_url": base_url,
            "ws_url": ws_url,
            "transport_preferences": transport_preferences,
            "operation_mappings": operation_mappings
        }
        
        logger.info(f"Registered exchange {exchange_id} with UnifiedClientFactory")
    
    @classmethod
    def create(
        cls,
        exchange_id: str,
        auth_provider: Optional[AuthProvider] = None,
        rate_limiter: Optional[RateLimiter] = None,
        **kwargs
    ) -> UnifiedClient:
        """
        Create a unified client for the specified exchange.
        
        Args:
            exchange_id: Unique identifier for the exchange
            auth_provider: Authentication provider
            rate_limiter: Rate limiter
            **kwargs: Additional client configuration
            
        Returns:
            Configured UnifiedClient instance
            
        Raises:
            ValueError: If the exchange is not registered
        """
        if exchange_id not in cls._registered_exchanges:
            raise ValueError(f"Exchange {exchange_id} not registered with UnifiedClientFactory")
        
        # Get exchange configuration
        config = cls._registered_exchanges[exchange_id]
        
        # Create client
        client = UnifiedClient(
            exchange_id=exchange_id,
            base_url=config["base_url"],
            ws_url=config["ws_url"],
            auth_provider=auth_provider,
            rate_limiter=rate_limiter,
            transport_preferences=config["transport_preferences"],
            **kwargs
        )
        
        # Apply operation mappings if provided
        if config["operation_mappings"]:
            # Assuming each transport has an _operation_mappings attribute
            for transport_type in [ClientTransportType.REST, ClientTransportType.WEBSOCKET]:
                transport = client.transport_manager.get_transport(transport_type)
                transport._operation_mappings.update(config["operation_mappings"])
        
        logger.info(f"Created unified client for exchange {exchange_id}")
        return client 