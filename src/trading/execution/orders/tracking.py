import json
import logging
import threading
import time
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

import websocket

from .models.order import Order, OrderStatus
from .execution.orders.exceptions import ConnectionError, WebSocketError

logger = logging.getLogger(__name__)

@dataclass
class OrderUpdate:
    """Contains information about an order update from the exchange."""
    order_id: str
    exchange_order_id: str
    symbol: str
    status: Optional[str] = None
    filled_quantity: Optional[float] = None
    remaining_quantity: Optional[float] = None
    avg_price: Optional[float] = None
    last_price: Optional[float] = None
    transaction_time: Optional[int] = None
    raw_data: Optional[Dict[str, Any]] = None


class OrderTracker(ABC):
    """
    Abstract base class for order trackers.
    
    Order trackers monitor order status through websocket connections or
    periodic polling, depending on exchange capabilities.
    """
    
    def __init__(self, exchange_client: Any):
        """
        Initialize OrderTracker.
        
        Args:
            exchange_client: The exchange API client
        """
        self.exchange_client = exchange_client
        self.tracking_orders: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._lock = threading.RLock()
        self._worker_thread: Optional[threading.Thread] = None
    
    @abstractmethod
    def _process_message(self, message: Dict[str, Any]) -> Optional[OrderUpdate]:
        """
        Process a message from the websocket.
        
        Args:
            message: The raw message from the websocket
            
        Returns:
            OrderUpdate if the message is relevant, None otherwise
        """
        pass
    
    @abstractmethod
    def _start_tracking(self) -> None:
        """Start tracking orders."""
        pass
    
    @abstractmethod
    def _stop_tracking(self) -> None:
        """Stop tracking orders."""
        pass
    
    def start(self) -> None:
        """Start the order tracker."""
        with self._lock:
            if self._running:
                return
            
            self._running = True
            
            # Start the worker thread
            self._worker_thread = threading.Thread(
                target=self._tracking_worker,
                daemon=True,
                name="OrderTracker"
            )
            self._worker_thread.start()
            
            logger.info("OrderTracker started")
    
    def stop(self) -> None:
        """Stop the order tracker."""
        with self._lock:
            if not self._running:
                return
            
            self._running = False
            
            # Stop tracking
            self._stop_tracking()
            
            # Wait for worker thread to terminate
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=5.0)
            
            logger.info("OrderTracker stopped")
    
    def register_order(self, order_id: str, exchange_order_id: str, symbol: str, 
                     callback: Callable[[OrderUpdate], None]) -> None:
        """
        Register an order for tracking.
        
        Args:
            order_id: Client order ID
            exchange_order_id: Exchange order ID
            symbol: Trading symbol
            callback: Function to call with order updates
        """
        with self._lock:
            self.tracking_orders[order_id] = {
                "order_id": order_id,
                "exchange_order_id": exchange_order_id,
                "symbol": symbol,
                "callback": callback,
                "registered_at": time.time()
            }
            
            logger.debug(f"Registered order {order_id} for tracking")
    
    def unregister_order(self, order_id: str) -> None:
        """
        Unregister an order from tracking.
        
        Args:
            order_id: Client order ID
        """
        with self._lock:
            if order_id in self.tracking_orders:
                del self.tracking_orders[order_id]
                logger.debug(f"Unregistered order {order_id} from tracking")
    
    def _tracking_worker(self) -> None:
        """Worker thread function for tracking orders."""
        try:
            self._start_tracking()
            
            # Keep thread alive while running
            while self._running:
                time.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Error in order tracking worker: {str(e)}", exc_info=True)
        finally:
            self._stop_tracking()
    
    def process_update(self, update: OrderUpdate) -> None:
        """
        Process an order update.
        
        Args:
            update: The order update
        """
        with self._lock:
            # Find matching orders
            found = False
            for order_info in list(self.tracking_orders.values()):
                if (update.exchange_order_id == order_info["exchange_order_id"] or 
                    update.order_id == order_info["order_id"]):
                    # Call the callback
                    try:
                        order_info["callback"](update)
                        found = True
                    except Exception as e:
                        logger.error(f"Error in order update callback: {str(e)}", exc_info=True)
            
            if not found:
                logger.debug(f"Received update for non-tracked order: {update.order_id}/{update.exchange_order_id}")


class BinanceOrderTracker(OrderTracker):
    """
    Binance-specific implementation of OrderTracker.
    
    Uses Binance's User Data Stream to monitor order status.
    """
    
    def __init__(self, exchange_client: Any):
        """
        Initialize BinanceOrderTracker.
        
        Args:
            exchange_client: The Binance API client
        """
        super().__init__(exchange_client)
        self._listen_key: Optional[str] = None
        self._renewal_thread: Optional[threading.Thread] = None
        self._renewal_interval = 30 * 60  # 30 minutes in seconds
    
    def _start_tracking(self) -> None:
        """Start tracking orders via Binance's user data stream."""
        try:
            # Get listen key
            self._listen_key = self.exchange_client.start_user_data_stream()
            
            # Start websocket connection
            self.exchange_client.user_socket(
                self._listen_key,
                callback=self._on_message
            )
            
            # Start listen key renewal thread
            self._renewal_thread = threading.Thread(
                target=self._renew_listen_key_worker,
                daemon=True,
                name="ListenKeyRenewal"
            )
            self._renewal_thread.start()
            
            logger.info("Binance order tracking started")
            
        except Exception as e:
            logger.error(f"Error starting Binance order tracking: {str(e)}", exc_info=True)
            self._listen_key = None
    
    def _stop_tracking(self) -> None:
        """Stop tracking orders."""
        try:
            # Close listen key
            if self._listen_key:
                self.exchange_client.close_user_data_stream(self._listen_key)
                self._listen_key = None
            
            logger.info("Binance order tracking stopped")
            
        except Exception as e:
            logger.error(f"Error stopping Binance order tracking: {str(e)}", exc_info=True)
    
    def _renew_listen_key_worker(self) -> None:
        """Worker thread to periodically renew the listen key."""
        try:
            while self._running and self._listen_key:
                # Sleep for the renewal interval
                for _ in range(self._renewal_interval * 10):
                    if not self._running or not self._listen_key:
                        break
                    time.sleep(0.1)
                
                # Renew listen key if still running
                if self._running and self._listen_key:
                    self.exchange_client.keep_alive_user_data_stream(self._listen_key)
                    logger.debug("Renewed Binance listen key")
            
        except Exception as e:
            logger.error(f"Error in listen key renewal thread: {str(e)}", exc_info=True)
    
    def _on_message(self, message: Dict[str, Any]) -> None:
        """
        Handle a message from the websocket.
        
        Args:
            message: The raw message from the websocket
        """
        try:
            update = self._process_message(message)
            if update:
                self.process_update(update)
        except Exception as e:
            logger.error(f"Error processing websocket message: {str(e)}", exc_info=True)
    
    def _process_message(self, message: Dict[str, Any]) -> Optional[OrderUpdate]:
        """
        Process a message from the websocket.
        
        Args:
            message: The raw message from the websocket
            
        Returns:
            OrderUpdate if the message is about an order, None otherwise
        """
        try:
            event_type = message.get("e")
            
            # Handle order execution report
            if event_type == "executionReport":
                client_order_id = message.get("c")
                if not client_order_id:
                    return None
                
                # Parse order update
                return OrderUpdate(
                    order_id=client_order_id,
                    exchange_order_id=message.get("i", ""),
                    symbol=message.get("s", ""),
                    status=message.get("X"),  # Order execution status (NEW, FILLED, etc)
                    filled_quantity=float(message.get("z", 0)),  # Cumulative filled qty
                    remaining_quantity=float(message.get("q", 0)) - float(message.get("z", 0)),
                    avg_price=float(message.get("L", 0)) if float(message.get("z", 0)) > 0 else None,
                    last_price=float(message.get("L", 0)),
                    transaction_time=message.get("T"),
                    raw_data=message
                )
                
            return None
            
        except Exception as e:
            logger.error(f"Error processing websocket message: {str(e)}", exc_info=True)
            return None


class PollingOrderTracker(OrderTracker):
    """
    Fallback implementation that uses periodic API polling.
    
    This is for exchanges that don't support websocket order updates.
    """
    
    def __init__(self, exchange_client: Any, poll_interval: float = 5.0):
        """
        Initialize PollingOrderTracker.
        
        Args:
            exchange_client: The exchange API client
            poll_interval: How often to poll for updates (seconds)
        """
        super().__init__(exchange_client)
        self.poll_interval = poll_interval
        self._polling_thread: Optional[threading.Thread] = None
    
    def _start_tracking(self) -> None:
        """Start tracking orders via polling."""
        self._polling_thread = threading.Thread(
            target=self._polling_worker,
            daemon=True,
            name="OrderPolling"
        )
        self._polling_thread.start()
        
        logger.info(f"Polling order tracking started (interval: {self.poll_interval}s)")
    
    def _stop_tracking(self) -> None:
        """Stop tracking orders."""
        # No special actions needed, the polling thread will exit when self._running is False
        logger.info("Polling order tracking stopped")
    
    def _polling_worker(self) -> None:
        """Worker thread to periodically poll for order updates."""
        try:
            while self._running:
                self._poll_orders()
                
                # Sleep for the poll interval
                for _ in range(int(self.poll_interval * 10)):
                    if not self._running:
                        break
                    time.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Error in polling thread: {str(e)}", exc_info=True)
    
    def _poll_orders(self) -> None:
        """Poll for updates to all tracked orders."""
        with self._lock:
            # Copy the order list to avoid modification during iteration
            order_infos = list(self.tracking_orders.values())
        
        for order_info in order_infos:
            try:
                # Skip if we're not running anymore
                if not self._running:
                    break
                
                # Get order details from exchange
                result = self.exchange_client.get_order(
                    symbol=order_info["symbol"],
                    order_id=order_info["exchange_order_id"]
                )
                
                # Create update and process it
                update = self._process_message(result)
                if update:
                    self.process_update(update)
                
            except Exception as e:
                logger.error(f"Error polling order {order_info['order_id']}: {str(e)}", exc_info=True)
    
    def _process_message(self, message: Dict[str, Any]) -> Optional[OrderUpdate]:
        """
        Process an order response from the API.
        
        Args:
            message: The order data from the API
            
        Returns:
            OrderUpdate object
        """
        try:
            if not message:
                return None
                
            client_order_id = message.get("clientOrderId")
            if not client_order_id:
                return None
            
            # Parse order update
            return OrderUpdate(
                order_id=client_order_id,
                exchange_order_id=str(message.get("orderId", "")),
                symbol=message.get("symbol", ""),
                status=message.get("status"),  
                filled_quantity=float(message.get("executedQty", 0)),
                remaining_quantity=float(message.get("origQty", 0)) - float(message.get("executedQty", 0)),
                avg_price=float(message.get("price", 0)) if float(message.get("executedQty", 0)) > 0 else None,
                transaction_time=message.get("time"),
                raw_data=message
            )
            
        except Exception as e:
            logger.error(f"Error processing API response: {str(e)}", exc_info=True)
            return None


class OrderTrackerFactory:
    """Factory for creating OrderTrackers based on exchange."""
    
    @staticmethod
    def create_tracker(exchange_name: str, exchange_client: Any) -> OrderTracker:
        """
        Create an OrderTracker for the specified exchange.
        
        Args:
            exchange_name: Name of the exchange
            exchange_client: The exchange API client
            
        Returns:
            An OrderTracker instance
        """
        exchange_name = exchange_name.lower()
        
        if exchange_name == "binance":
            return BinanceOrderTracker(exchange_client)
        else:
            # Fallback to polling for unsupported exchanges
            logger.warning(f"No specific OrderTracker for {exchange_name}, using polling fallback")
            return PollingOrderTracker(exchange_client) 