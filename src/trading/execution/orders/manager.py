"""
Order Management System (OMS) for handling the lifecycle of orders.
"""
from typing import Dict, List, Optional, Callable, Any, Set, Union, Tuple
from datetime import datetime
import logging
import uuid
import threading
import json
import os
from enum import Enum
from collections import defaultdict
import time
from threading import Lock

from .execution.orders.model import (
    Order, OrderStatus, OrderValidationResult, OrderSide, OrderType
)
from .execution.messaging.queue import (
    MessageType, Message, MessageBus, LocalQueue
)
from .execution.orders.handlers import OrderHandlerFactory
from .execution.orders.commands import (
    PlaceOrderCommand,
    CancelOrderCommand,
    UpdateOrderCommand,
    BatchOrderCommand
)
from .execution.orders.tracking import OrderTrackerFactory, OrderTracker, OrderUpdate
from .execution.orders.exceptions import (
    OrderValidationError, OrderExecutionError, UnsupportedOrderTypeError
)

# Setup logger
logger = logging.getLogger(__name__)


class OrderEvent(Enum):
    """Events that can occur in an order's lifecycle."""
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    ROUTED = "ROUTED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"
    ERROR = "ERROR"


class OrderManager:
    """
    Manages order operations and tracking.
    
    Provides a high-level interface for order placement, modification,
    cancellation, and tracking. Coordinates between exchange clients,
    order handlers, and websocket tracking.
    """
    
    def __init__(self, exchange_client: Any, ws_client: Optional[Any] = None):
        """
        Initialize the order manager.
        
        Args:
            exchange_client: The exchange client to use for order execution
            ws_client: Optional websocket client for real-time order updates
        """
        self.exchange_client = exchange_client
        self.ws_client = ws_client
        self.order_handler_factory = OrderHandlerFactory()
        
        # For tracking active orders and their status
        self.active_orders: Dict[str, Dict[str, Any]] = {}
        self.order_lock = Lock()
        
        # Track order history
        self.order_history: List[Dict[str, Any]] = []
        
        # Callbacks
        self.order_update_callbacks: List[Callable] = []
        
        # Initialize websocket handlers if available
        if self.ws_client:
            self._setup_websocket_handlers()
    
    def _setup_websocket_handlers(self):
        """Configure WebSocket handlers for order updates."""
        try:
            # Set up user data stream if not already started
            if not hasattr(self.ws_client, 'user_stream_id'):
                listen_key = self.exchange_client.start_user_data_stream()
                self.ws_client.user_stream_id = listen_key
                self.ws_client.start_user_data_stream(listen_key, self._handle_user_data)
                logger.info(f"Started user data stream with listen key: {listen_key}")
            else:
                logger.info("User data stream already started")
        except Exception as e:
            logger.error(f"Failed to setup WebSocket handlers: {str(e)}", exc_info=True)
    
    def _handle_user_data(self, msg: Dict[str, Any]):
        """
        Process user data WebSocket messages.
        
        Args:
            msg: The WebSocket message
        """
        try:
            event_type = msg.get("e")
            
            if event_type == "executionReport":
                self._process_order_update(msg)
            elif event_type == "outboundAccountPosition":
                self._process_account_update(msg)
            elif event_type == "balanceUpdate":
                self._process_balance_update(msg)
            else:
                logger.debug(f"Received unhandled user data message: {event_type}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {str(e)}", exc_info=True)
    
    def _process_order_update(self, msg: Dict[str, Any]):
        """
        Process order update messages from WebSocket.
        
        Args:
            msg: The order update message
        """
        try:
            client_order_id = msg.get("c")
            exchange_order_id = msg.get("i")
            order_status = msg.get("X")
            symbol = msg.get("s")
            
            if not client_order_id or not exchange_order_id:
                logger.warning(f"Received order update with missing IDs: {msg}")
                return
            
            # Find our internal order ID
            internal_order_id = None
            with self.order_lock:
                for order_id, order_data in self.active_orders.items():
                    if (order_data.get("client_order_id") == client_order_id or 
                        order_data.get("exchange_order_id") == exchange_order_id):
                        internal_order_id = order_id
                        break
            
            if not internal_order_id:
                logger.warning(f"Received update for unknown order: {client_order_id}")
                return
            
            # Update order status
            with self.order_lock:
                if internal_order_id in self.active_orders:
                    self.active_orders[internal_order_id].update({
                        "exchange_status": order_status,
                        "last_update_time": time.time(),
                        "last_update_data": msg
                    })
                    
                    # If order is in a final state, move to history
                    if order_status in ["FILLED", "CANCELED", "REJECTED", "EXPIRED"]:
                        order_data = self.active_orders.pop(internal_order_id)
                        self.order_history.append({
                            "order_id": internal_order_id,
                            "final_status": order_status,
                            "final_update_time": time.time(),
                            "data": order_data
                        })
            
            # Notify callbacks
            for callback in self.order_update_callbacks:
                try:
                    callback(internal_order_id, order_status, msg)
                except Exception as e:
                    logger.error(f"Error in order update callback: {str(e)}", exc_info=True)
            
            logger.info(f"Order {internal_order_id} updated: {order_status}")
            
        except Exception as e:
            logger.error(f"Error processing order update: {str(e)}", exc_info=True)
    
    def _process_account_update(self, msg: Dict[str, Any]):
        """
        Process account update messages from WebSocket.
        
        Args:
            msg: The account update message
        """
        # Account updates can be used to track balances, positions, etc.
        logger.debug(f"Account update received: {msg}")
    
    def _process_balance_update(self, msg: Dict[str, Any]):
        """
        Process balance update messages from WebSocket.
        
        Args:
            msg: The balance update message
        """
        # Balance updates can be used to track account balance changes
        logger.debug(f"Balance update received: {msg}")
    
    def add_order_update_callback(self, callback: Callable):
        """
        Add a callback function to be called on order updates.
        
        Args:
            callback: Function to call with (order_id, status, data)
        """
        self.order_update_callbacks.append(callback)
    
    def remove_order_update_callback(self, callback: Callable):
        """
        Remove a previously added callback function.
        
        Args:
            callback: The callback function to remove
        """
        if callback in self.order_update_callbacks:
            self.order_update_callbacks.remove(callback)
    
    def place_order(self, order: Order) -> Dict[str, Any]:
        """
        Place a new order.
        
        Args:
            order: The order to place
            
        Returns:
            Dictionary with the placement result
            
        Raises:
            OrderExecutionError: If order placement fails
        """
        try:
            logger.info(f"Placing order: {order.order_id}, type: {order.order_type}")
            
            # Create and execute the place order command
            command = PlaceOrderCommand(
                order=order,
                exchange_client=self.exchange_client,
                on_success=self._on_order_placed
            )
            
            result = command.execute()
            
            # For easy lookup by client_order_id and exchange_order_id 
            with self.order_lock:
                self.active_orders[order.order_id] = {
                    "order": order,
                    "status": OrderStatus.WORKING,
                    "client_order_id": result.get("client_order_id"),
                    "exchange_order_id": result.get("exchange_order_id"),
                    "placement_response": result,
                    "placement_time": time.time()
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to place order {order.order_id}: {str(e)}", exc_info=True)
            raise OrderExecutionError(f"Order placement failed: {str(e)}")
    
    def _on_order_placed(self, order: Order, response: Dict[str, Any]):
        """
        Callback for successful order placement.
        
        Args:
            order: The placed order
            response: The exchange response
        """
        logger.info(f"Order placed successfully: {order.order_id}")
        
        # Additional logic can be added here (e.g., analytics, notifications)
    
    def cancel_order(self, 
                    order_id: str, 
                    symbol: str, 
                    exchange_order_id: Optional[str] = None,
                    client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Cancel an existing order.
        
        Args:
            order_id: The internal order ID
            symbol: The trading symbol
            exchange_order_id: Optional exchange order ID (if known)
            client_order_id: Optional client order ID (if known)
            
        Returns:
            Dictionary with the cancellation result
            
        Raises:
            OrderExecutionError: If order cancellation fails
        """
        try:
            logger.info(f"Cancelling order: {order_id}")
            
            # If we don't have exchange_order_id or client_order_id, try to find them
            if not exchange_order_id and not client_order_id:
                with self.order_lock:
                    if order_id in self.active_orders:
                        exchange_order_id = self.active_orders[order_id].get("exchange_order_id")
                        client_order_id = self.active_orders[order_id].get("client_order_id")
            
            if not exchange_order_id and not client_order_id:
                raise OrderExecutionError(f"Cannot cancel order {order_id}: no exchange or client order ID available")
            
            # Create and execute the cancel order command
            command = CancelOrderCommand(
                order_id=order_id,
                symbol=symbol,
                exchange_client=self.exchange_client,
                exchange_order_id=exchange_order_id,
                client_order_id=client_order_id,
                on_success=self._on_order_cancelled
            )
            
            result = command.execute()
            
            # Update order status
            with self.order_lock:
                if order_id in self.active_orders:
                    self.active_orders[order_id].update({
                        "status": OrderStatus.CANCELLED,
                        "cancellation_response": result,
                        "cancellation_time": time.time()
                    })
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {str(e)}", exc_info=True)
            raise OrderExecutionError(f"Order cancellation failed: {str(e)}")
    
    def _on_order_cancelled(self, order_id: str, response: Dict[str, Any]):
        """
        Callback for successful order cancellation.
        
        Args:
            order_id: The cancelled order ID
            response: The exchange response
        """
        logger.info(f"Order cancelled successfully: {order_id}")
        
        # Additional logic can be added here (e.g., analytics, notifications)
    
    def update_order(self,
                   order_id: str,
                   symbol: str,
                   new_price: Optional[float] = None,
                   new_quantity: Optional[float] = None,
                   new_stop_price: Optional[float] = None,
                   exchange_order_id: Optional[str] = None,
                   client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Update an existing order (cancel and replace).
        
        Args:
            order_id: The internal order ID
            symbol: The trading symbol
            new_price: Optional new price
            new_quantity: Optional new quantity
            new_stop_price: Optional new stop price
            exchange_order_id: Optional exchange order ID (if known)
            client_order_id: Optional client order ID (if known)
            
        Returns:
            Dictionary with the update result
            
        Raises:
            OrderExecutionError: If order update fails
        """
        try:
            logger.info(f"Updating order: {order_id}")
            
            if not any([new_price, new_quantity, new_stop_price]):
                raise OrderExecutionError("At least one parameter (price, quantity, stop_price) must be updated")
            
            # If we don't have exchange_order_id or client_order_id, try to find them
            if not exchange_order_id and not client_order_id:
                with self.order_lock:
                    if order_id in self.active_orders:
                        exchange_order_id = self.active_orders[order_id].get("exchange_order_id")
                        client_order_id = self.active_orders[order_id].get("client_order_id")
            
            if not exchange_order_id and not client_order_id:
                raise OrderExecutionError(f"Cannot update order {order_id}: no exchange or client order ID available")
            
            # Create and execute the update order command
            command = UpdateOrderCommand(
                original_order_id=order_id,
                symbol=symbol,
                exchange_client=self.exchange_client,
                exchange_order_id=exchange_order_id,
                client_order_id=client_order_id,
                new_price=new_price,
                new_quantity=new_quantity,
                new_stop_price=new_stop_price,
                on_success=self._on_order_updated
            )
            
            result = command.execute()
            
            # Update order tracking - remove old order and add new one
            with self.order_lock:
                if order_id in self.active_orders:
                    old_order_data = self.active_orders.pop(order_id)
                    
                    # Move the old order to history
                    self.order_history.append({
                        "order_id": order_id,
                        "final_status": "REPLACED",
                        "final_update_time": time.time(),
                        "data": old_order_data,
                        "replacement_order_id": result.get("new_exchange_order_id")
                    })
                    
                    # Create a new entry for the updated order
                    new_order_id = f"{order_id}_updated_{int(time.time())}"
                    self.active_orders[new_order_id] = {
                        "original_order_id": order_id,
                        "status": OrderStatus.WORKING,
                        "client_order_id": result.get("new_client_order_id"),
                        "exchange_order_id": result.get("new_exchange_order_id"),
                        "update_response": result,
                        "update_time": time.time()
                    }
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to update order {order_id}: {str(e)}", exc_info=True)
            raise OrderExecutionError(f"Order update failed: {str(e)}")
    
    def _on_order_updated(self, order_id: str, response: Dict[str, Any]):
        """
        Callback for successful order update.
        
        Args:
            order_id: The updated order ID
            response: The exchange response
        """
        logger.info(f"Order updated successfully: {order_id}")
        
        # Additional logic can be added here (e.g., analytics, notifications)
    
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """
        Get the current status of an order.
        
        Args:
            order_id: The internal order ID
            
        Returns:
            Dictionary with order status information
            
        Raises:
            OrderExecutionError: If order status query fails
        """
        # First check our local tracking
        with self.order_lock:
            if order_id in self.active_orders:
                return {
                    "order_id": order_id,
                    "status": self.active_orders[order_id].get("status"),
                    "exchange_status": self.active_orders[order_id].get("exchange_status"),
                    "exchange_order_id": self.active_orders[order_id].get("exchange_order_id"),
                    "client_order_id": self.active_orders[order_id].get("client_order_id"),
                    "is_active": True,
                    "data": self.active_orders[order_id]
                }
            
            # Check order history
            for history_entry in self.order_history:
                if history_entry.get("order_id") == order_id:
                    return {
                        "order_id": order_id,
                        "status": history_entry.get("final_status"),
                        "is_active": False,
                        "completion_time": history_entry.get("final_update_time"),
                        "data": history_entry.get("data")
                    }
        
        # If we don't have it locally, try to query the exchange
        try:
            # We need to have exchange_order_id or client_order_id to query
            exchange_order_id = None
            client_order_id = None
            symbol = None
            
            # Check if we have this information in our history
            for history_entry in self.order_history:
                if history_entry.get("order_id") == order_id:
                    data = history_entry.get("data", {})
                    exchange_order_id = data.get("exchange_order_id")
                    client_order_id = data.get("client_order_id")
                    order = data.get("order")
                    if order:
                        symbol = order.symbol
                    break
            
            if not symbol or (not exchange_order_id and not client_order_id):
                raise OrderExecutionError(f"Cannot query order {order_id}: insufficient information")
            
            # Build query parameters
            params = {"symbol": symbol}
            if exchange_order_id:
                params["orderId"] = exchange_order_id
            elif client_order_id:
                params["origClientOrderId"] = client_order_id
            
            # Query the exchange
            exchange_response = self.exchange_client.get_order(**params)
            
            return {
                "order_id": order_id,
                "exchange_status": exchange_response.get("status"),
                "exchange_order_id": exchange_response.get("orderId"),
                "client_order_id": exchange_response.get("clientOrderId"),
                "is_active": exchange_response.get("status") not in ["FILLED", "CANCELED", "REJECTED", "EXPIRED"],
                "exchange_data": exchange_response
            }
            
        except Exception as e:
            logger.error(f"Failed to query order status for {order_id}: {str(e)}", exc_info=True)
            raise OrderExecutionError(f"Order status query failed: {str(e)}")
    
    def get_active_orders(self) -> List[Dict[str, Any]]:
        """
        Get all currently active orders.
        
        Returns:
            List of dictionaries with active order information
        """
        active_orders = []
        
        with self.order_lock:
            for order_id, order_data in self.active_orders.items():
                active_orders.append({
                    "order_id": order_id,
                    "status": order_data.get("status"),
                    "exchange_status": order_data.get("exchange_status"),
                    "exchange_order_id": order_data.get("exchange_order_id"),
                    "client_order_id": order_data.get("client_order_id"),
                    "placement_time": order_data.get("placement_time"),
                    "last_update_time": order_data.get("last_update_time")
                })
        
        return active_orders
    
    def get_order_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get historical orders.
        
        Args:
            limit: Maximum number of historical orders to return
            
        Returns:
            List of dictionaries with historical order information
        """
        history = []
        
        for entry in self.order_history[-limit:]:
            history.append({
                "order_id": entry.get("order_id"),
                "final_status": entry.get("final_status"),
                "completion_time": entry.get("final_update_time"),
                "replacement_order_id": entry.get("replacement_order_id")
            })
        
        return history
    
    def sync_with_exchange(self):
        """
        Synchronize local order tracking with exchange state.
        
        This is useful after system restarts or connection issues.
        
        Returns:
            Dictionary with synchronization results
        """
        try:
            logger.info("Synchronizing order status with exchange")
            
            # Get all open orders from the exchange
            open_orders = self.exchange_client.get_open_orders()
            
            exchange_orders = {}
            for order in open_orders:
                exchange_order_id = order.get("orderId")
                client_order_id = order.get("clientOrderId")
                if exchange_order_id:
                    exchange_orders[str(exchange_order_id)] = order
                if client_order_id:
                    exchange_orders[client_order_id] = order
            
            # Update our local tracking
            updated_count = 0
            missing_count = 0
            extra_count = 0
            
            with self.order_lock:
                # Check each locally active order
                for order_id, order_data in list(self.active_orders.items()):
                    exchange_order_id = order_data.get("exchange_order_id")
                    client_order_id = order_data.get("client_order_id")
                    
                    # Check if we can find this order on the exchange
                    found = False
                    if exchange_order_id and str(exchange_order_id) in exchange_orders:
                        found = True
                        exchange_order = exchange_orders[str(exchange_order_id)]
                    elif client_order_id and client_order_id in exchange_orders:
                        found = True
                        exchange_order = exchange_orders[client_order_id]
                    
                    if found:
                        # Update local status
                        order_data.update({
                            "exchange_status": exchange_order.get("status"),
                            "last_update_time": time.time(),
                            "last_update_data": exchange_order
                        })
                        updated_count += 1
                        
                        # If order is in a final state, move to history
                        if exchange_order.get("status") in ["FILLED", "CANCELED", "REJECTED", "EXPIRED"]:
                            self.order_history.append({
                                "order_id": order_id,
                                "final_status": exchange_order.get("status"),
                                "final_update_time": time.time(),
                                "data": self.active_orders.pop(order_id)
                            })
                    else:
                        # Order not found on exchange, might have been filled or cancelled
                        missing_count += 1
                        
                        # Try to get specific order details
                        try:
                            params = {"symbol": order_data.get("order").symbol}
                            if exchange_order_id:
                                params["orderId"] = exchange_order_id
                            elif client_order_id:
                                params["origClientOrderId"] = client_order_id
                            
                            specific_order = self.exchange_client.get_order(**params)
                            
                            # Update with specific status
                            order_data.update({
                                "exchange_status": specific_order.get("status"),
                                "last_update_time": time.time(),
                                "last_update_data": specific_order
                            })
                            
                            # If order is in a final state, move to history
                            if specific_order.get("status") in ["FILLED", "CANCELED", "REJECTED", "EXPIRED"]:
                                self.order_history.append({
                                    "order_id": order_id,
                                    "final_status": specific_order.get("status"),
                                    "final_update_time": time.time(),
                                    "data": self.active_orders.pop(order_id)
                                })
                        except Exception as e:
                            logger.warning(f"Could not get specific order details for {order_id}: {str(e)}")
                            # Assume the order is no longer active
                            self.order_history.append({
                                "order_id": order_id,
                                "final_status": "UNKNOWN",
                                "final_update_time": time.time(),
                                "data": self.active_orders.pop(order_id),
                                "error": str(e)
                            })
                
                # Check for orders on the exchange that we're not tracking
                for exchange_order in open_orders:
                    exchange_order_id = exchange_order.get("orderId")
                    client_order_id = exchange_order.get("clientOrderId")
                    
                    # Check if we're already tracking this order
                    found = False
                    for order_data in self.active_orders.values():
                        if (str(order_data.get("exchange_order_id")) == str(exchange_order_id) or
                            order_data.get("client_order_id") == client_order_id):
                            found = True
                            break
                    
                    if not found:
                        # Create a new entry for this unknown order
                        new_order_id = f"synced_{exchange_order_id}_{int(time.time())}"
                        self.active_orders[new_order_id] = {
                            "status": OrderStatus.WORKING,
                            "exchange_status": exchange_order.get("status"),
                            "exchange_order_id": exchange_order_id,
                            "client_order_id": client_order_id,
                            "sync_time": time.time(),
                            "exchange_data": exchange_order
                        }
                        extra_count += 1
            
            logger.info(f"Sync complete: Updated {updated_count}, Missing {missing_count}, Extra {extra_count}")
            
            return {
                "status": "COMPLETE",
                "updated_count": updated_count,
                "missing_count": missing_count,
                "extra_count": extra_count
            }
            
        except Exception as e:
            logger.error(f"Failed to sync with exchange: {str(e)}", exc_info=True)
            raise OrderExecutionError(f"Exchange synchronization failed: {str(e)}")
    
    def close(self):
        """
        Close the order manager and release resources.
        """
        try:
            # Keep the websocket connection alive if needed
            if self.ws_client and hasattr(self.ws_client, 'user_stream_id'):
                try:
                    # Extend the user data stream to prevent it from expiring
                    self.exchange_client.keep_alive_user_data_stream(self.ws_client.user_stream_id)
                except Exception as e:
                    logger.warning(f"Failed to keep alive user data stream: {str(e)}")
        except Exception as e:
            logger.error(f"Error during order manager shutdown: {str(e)}", exc_info=True)


# Basic order validators

def symbol_validator(order: Order) -> OrderValidationResult:
    """
    Basic validator to check if symbol is valid.
    
    Args:
        order: Order to validate
        
    Returns:
        Validation result
    """
    # In a real system, this would check against a list of valid symbols
    # Here, we'll just check that it's not empty
    if not order.symbol or len(order.symbol) < 2:
        return OrderValidationResult(
            is_valid=False,
            order_id=order.order_id,
            reason="Invalid symbol"
        )
    
    return OrderValidationResult(
        is_valid=True,
        order_id=order.order_id
    )


def price_validator(order: Order) -> OrderValidationResult:
    """
    Basic validator to check price.
    
    Args:
        order: Order to validate
        
    Returns:
        Validation result
    """
    # For limit and stop orders, price must be > 0
    if order.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] and (order.price is None or order.price <= 0):
        return OrderValidationResult(
            is_valid=False,
            order_id=order.order_id,
            reason=f"Invalid price for {order.order_type.value} order: {order.price}"
        )
    
    # For stop orders, stop price must be > 0
    if order.order_type in [OrderType.STOP, OrderType.STOP_LIMIT, OrderType.TRAILING_STOP] and (order.stop_price is None or order.stop_price <= 0):
        return OrderValidationResult(
            is_valid=False,
            order_id=order.order_id,
            reason=f"Invalid stop price for {order.order_type.value} order: {order.stop_price}"
        )
    
    return OrderValidationResult(
        is_valid=True,
        order_id=order.order_id
    )


def quantity_validator(order: Order) -> OrderValidationResult:
    """
    Basic validator to check quantity.
    
    Args:
        order: Order to validate
        
    Returns:
        Validation result
    """
    # Quantity must be > 0
    if order.quantity <= 0:
        return OrderValidationResult(
            is_valid=False,
            order_id=order.order_id,
            reason=f"Invalid quantity: {order.quantity}"
        )
    
    return OrderValidationResult(
        is_valid=True,
        order_id=order.order_id
    )


# Export classes
__all__ = [
    "OrderEvent",
    "OrderManager",
    "symbol_validator",
    "price_validator",
    "quantity_validator"
] 