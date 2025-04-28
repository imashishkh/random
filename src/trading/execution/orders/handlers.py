"""
Order Type Handlers for executing different types of orders.

This module implements the Strategy Pattern for order type handling,
providing specialized execution logic for different order types.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple
import logging
import time
from datetime import datetime, timedelta
import uuid

from .execution.orders.model import Order, OrderStatus, OrderType, OrderSide
from .execution.orders.commands import (
    OrderCommand, PlaceOrderCommand, CancelOrderCommand, 
    ModifyOrderCommand, CompositeOrderCommand, retry_with_backoff
)
from ....exchange.binance_api_client import BinanceApiClient
from ....exchange.exceptions import ExchangeError
from .models.order import TimeInForce
from .execution.orders.exceptions import (
    OrderValidationError, OrderExecutionError, UnsupportedOrderTypeError
)

# Configure logger
logger = logging.getLogger(__name__)


class OrderHandler(ABC):
    """
    Abstract base class for all order type handlers.
    Each order type (market, limit, etc.) will have its own handler.
    """
    
    @property
    @abstractmethod
    def supported_order_types(self) -> List[OrderType]:
        """Return a list of order types supported by this handler."""
        pass
    
    @abstractmethod
    def validate_order(self, order: Order) -> None:
        """
        Validate the order parameters.
        
        Args:
            order: The order to validate
            
        Raises:
            OrderValidationError: If the order is invalid
        """
        pass
    
    @abstractmethod
    def prepare_order_params(self, order: Order) -> Dict[str, Any]:
        """
        Prepare the order parameters for the exchange API.
        
        Args:
            order: The order to prepare parameters for
            
        Returns:
            A dictionary of parameters to send to the exchange
        """
        pass
    
    @abstractmethod
    def process_response(self, order: Order, response: Dict[str, Any]) -> None:
        """
        Process the exchange API response.
        
        Args:
            order: The original order
            response: The exchange response
            
        Raises:
            OrderExecutionError: If the exchange rejected the order
        """
        pass
    
    def supports_order_type(self, order_type: OrderType) -> bool:
        """
        Check if this handler supports the given order type.
        
        Args:
            order_type: The order type to check
            
        Returns:
            True if supported, False otherwise
        """
        return order_type in self.supported_order_types
    
    def handle_order(self, order: Order, api_client: Any) -> Order:
        """
        Handle the order end-to-end: validate, prepare, submit, process.
        
        Args:
            order: The order to handle
            api_client: The exchange API client
            
        Returns:
            The updated order with exchange information
            
        Raises:
            OrderValidationError: If the order is invalid
            OrderExecutionError: If the order execution fails
        """
        # Validate the order parameters
        self.validate_order(order)
        
        # Prepare parameters for the exchange API
        params = self.prepare_order_params(order)
        
        # Submit order to exchange
        try:
            # Log the order submission
            logger.info(f"Submitting {order.type.name} order: {order.order_id} - "
                       f"{order.side.name} {order.quantity} {order.symbol} @ {order.price}")
            
            # Call the appropriate API method based on order type
            response = self._call_exchange_api(order, params, api_client)
            
            # Process the exchange response
            self.process_response(order, response)
            
            # Log success
            logger.info(f"Order {order.order_id} submitted successfully. "
                       f"Exchange order ID: {order.metadata.get('exchange_order_id')}")
            
            return order
            
        except Exception as e:
            # Log the error and raise
            logger.error(f"Failed to execute order {order.order_id}: {str(e)}", exc_info=True)
            order.update_status(OrderStatus.REJECTED)
            order.metadata["error"] = str(e)
            raise OrderExecutionError(f"Failed to execute order {order.order_id}: {str(e)}")
    
    def _call_exchange_api(self, order: Order, params: Dict[str, Any], 
                          api_client: Any) -> Dict[str, Any]:
        """
        Call the appropriate exchange API method based on order type.
        
        Args:
            order: The order to submit
            params: The parameters to send
            api_client: The exchange API client
            
        Returns:
            The exchange response
        """
        # This method would be overridden in specific exchange implementations
        # or implemented in the parent handler based on the exchange client
        raise NotImplementedError("Exchange API call not implemented")


class MarketOrderHandler(OrderHandler):
    """Handler for market orders."""
    
    @property
    def supported_order_types(self) -> List[OrderType]:
        return [OrderType.MARKET]
    
    def validate_order(self, order: Order) -> None:
        """
        Validate market order parameters.
        
        Args:
            order: The order to validate
            
        Raises:
            OrderValidationError: If the order is invalid
        """
        if order.type != OrderType.MARKET:
            raise OrderValidationError(f"Expected MARKET order, got {order.type.name}")
        
        if not order.symbol:
            raise OrderValidationError("Symbol is required")
        
        if not order.quantity:
            raise OrderValidationError("Quantity is required")
        
        if not order.side:
            raise OrderValidationError("Side is required")
    
    def prepare_order_params(self, order: Order) -> Dict[str, Any]:
        """
        Prepare market order parameters.
        
        Args:
            order: The order to prepare parameters for
            
        Returns:
            Parameters for a market order
        """
        params = {
            "symbol": order.symbol,
            "side": order.side.name,
            "type": "MARKET",
            "quantity": order.quantity,
            "newClientOrderId": order.client_order_id or order.order_id
        }
        
        # Add optional parameters if present
        if order.reduce_only:
            params["reduceOnly"] = "true"
        
        return params
    
    def process_response(self, order: Order, response: Dict[str, Any]) -> None:
        """
        Process market order response.
        
        Args:
            order: The original order
            response: The exchange response
        """
        # Update order with exchange information
        if "orderId" in response:
            order.metadata["exchange_order_id"] = response["orderId"]
        
        if "clientOrderId" in response:
            order.client_order_id = response["clientOrderId"]
        
        # Market orders are typically filled immediately
        if response.get("status") == "FILLED":
            order.update_status(OrderStatus.FILLED)
            order.filled_quantity = float(response.get("executedQty", 0))
            
            # Calculate average fill price
            if "cummulativeQuoteQty" in response and order.filled_quantity > 0:
                order.avg_fill_price = float(response["cummulativeQuoteQty"]) / order.filled_quantity
            
        elif response.get("status") == "PARTIALLY_FILLED":
            order.update_status(OrderStatus.PARTIALLY_FILLED)
            order.filled_quantity = float(response.get("executedQty", 0))
            
            if "cummulativeQuoteQty" in response and order.filled_quantity > 0:
                order.avg_fill_price = float(response["cummulativeQuoteQty"]) / order.filled_quantity
                
        else:
            # If not filled or partially filled, it's active
            order.update_status(OrderStatus.NEW)
            
        # Store original response for reference
        order.metadata["exchange_response"] = response


class LimitOrderHandler(OrderHandler):
    """Handler for limit orders."""
    
    @property
    def supported_order_types(self) -> List[OrderType]:
        return [OrderType.LIMIT]
    
    def validate_order(self, order: Order) -> None:
        """
        Validate limit order parameters.
        
        Args:
            order: The order to validate
            
        Raises:
            OrderValidationError: If the order is invalid
        """
        if order.type != OrderType.LIMIT:
            raise OrderValidationError(f"Expected LIMIT order, got {order.type.name}")
        
        if not order.symbol:
            raise OrderValidationError("Symbol is required")
        
        if not order.quantity:
            raise OrderValidationError("Quantity is required")
        
        if not order.side:
            raise OrderValidationError("Side is required")
        
        if not order.price:
            raise OrderValidationError("Price is required for limit orders")
        
        if not order.time_in_force:
            raise OrderValidationError("Time in force is required for limit orders")
    
    def prepare_order_params(self, order: Order) -> Dict[str, Any]:
        """
        Prepare limit order parameters.
        
        Args:
            order: The order to prepare parameters for
            
        Returns:
            Parameters for a limit order
        """
        params = {
            "symbol": order.symbol,
            "side": order.side.name,
            "type": "LIMIT",
            "quantity": order.quantity,
            "price": order.price,
            "timeInForce": order.time_in_force.name,
            "newClientOrderId": order.client_order_id or order.order_id
        }
        
        # Add optional parameters if present
        if order.reduce_only:
            params["reduceOnly"] = "true"
        
        if order.post_only:
            params["postOnly"] = "true"
        
        return params
    
    def process_response(self, order: Order, response: Dict[str, Any]) -> None:
        """
        Process limit order response.
        
        Args:
            order: The original order
            response: The exchange response
        """
        # Update order with exchange information
        if "orderId" in response:
            order.metadata["exchange_order_id"] = response["orderId"]
        
        if "clientOrderId" in response:
            order.client_order_id = response["clientOrderId"]
        
        # Update status based on response
        if response.get("status") == "FILLED":
            order.update_status(OrderStatus.FILLED)
            order.filled_quantity = float(response.get("executedQty", 0))
            
            # Calculate average fill price
            if "cummulativeQuoteQty" in response and order.filled_quantity > 0:
                order.avg_fill_price = float(response["cummulativeQuoteQty"]) / order.filled_quantity
            
        elif response.get("status") == "PARTIALLY_FILLED":
            order.update_status(OrderStatus.PARTIALLY_FILLED)
            order.filled_quantity = float(response.get("executedQty", 0))
            
            if "cummulativeQuoteQty" in response and order.filled_quantity > 0:
                order.avg_fill_price = float(response["cummulativeQuoteQty"]) / order.filled_quantity
                
        else:
            # If not filled or partially filled, it's active
            order.update_status(OrderStatus.NEW)
            
        # Store original response for reference
        order.metadata["exchange_response"] = response


class StopLossOrderHandler(OrderHandler):
    """Handler for stop loss orders."""
    
    @property
    def supported_order_types(self) -> List[OrderType]:
        return [OrderType.STOP, OrderType.STOP_MARKET]
    
    def validate_order(self, order: Order) -> None:
        """
        Validate stop loss order parameters.
        
        Args:
            order: The order to validate
            
        Raises:
            OrderValidationError: If the order is invalid
        """
        if order.type not in [OrderType.STOP, OrderType.STOP_MARKET]:
            raise OrderValidationError(f"Expected STOP or STOP_MARKET order, got {order.type.name}")
        
        if not order.symbol:
            raise OrderValidationError("Symbol is required")
        
        if not order.quantity:
            raise OrderValidationError("Quantity is required")
        
        if not order.side:
            raise OrderValidationError("Side is required")
        
        if not order.stop_price:
            raise OrderValidationError("Stop price is required for stop orders")
        
        # For STOP (limit) orders, price is required
        if order.type == OrderType.STOP and not order.price:
            raise OrderValidationError("Price is required for STOP (limit) orders")
    
    def prepare_order_params(self, order: Order) -> Dict[str, Any]:
        """
        Prepare stop loss order parameters.
        
        Args:
            order: The order to prepare parameters for
            
        Returns:
            Parameters for a stop loss order
        """
        # Binance uses STOP_LOSS for market stops and STOP_LOSS_LIMIT for limit stops
        if order.type == OrderType.STOP_MARKET:
            order_type = "STOP_LOSS"
            params = {
                "symbol": order.symbol,
                "side": order.side.name,
                "type": order_type,
                "quantity": order.quantity,
                "stopPrice": order.stop_price,
                "newClientOrderId": order.client_order_id or order.order_id
            }
        else:  # STOP (limit)
            order_type = "STOP_LOSS_LIMIT"
            params = {
                "symbol": order.symbol,
                "side": order.side.name,
                "type": order_type,
                "timeInForce": order.time_in_force.name if order.time_in_force else TimeInForce.GTC.name,
                "quantity": order.quantity,
                "price": order.price,
                "stopPrice": order.stop_price,
                "newClientOrderId": order.client_order_id or order.order_id
            }
        
        # Add optional parameters if present
        if order.reduce_only:
            params["reduceOnly"] = "true"
        
        return params
    
    def process_response(self, order: Order, response: Dict[str, Any]) -> None:
        """
        Process stop loss order response.
        
        Args:
            order: The original order
            response: The exchange response
        """
        # Update order with exchange information
        if "orderId" in response:
            order.metadata["exchange_order_id"] = response["orderId"]
        
        if "clientOrderId" in response:
            order.client_order_id = response["clientOrderId"]
        
        # Stop orders start in a NEW state
        order.update_status(OrderStatus.NEW)
            
        # Store original response for reference
        order.metadata["exchange_response"] = response


class TakeProfitOrderHandler(OrderHandler):
    """Handler for take profit orders."""
    
    @property
    def supported_order_types(self) -> List[OrderType]:
        return [OrderType.TAKE_PROFIT, OrderType.TAKE_PROFIT_MARKET]
    
    def validate_order(self, order: Order) -> None:
        """
        Validate take profit order parameters.
        
        Args:
            order: The order to validate
            
        Raises:
            OrderValidationError: If the order is invalid
        """
        if order.type not in [OrderType.TAKE_PROFIT, OrderType.TAKE_PROFIT_MARKET]:
            raise OrderValidationError(
                f"Expected TAKE_PROFIT or TAKE_PROFIT_MARKET order, got {order.type.name}"
            )
        
        if not order.symbol:
            raise OrderValidationError("Symbol is required")
        
        if not order.quantity:
            raise OrderValidationError("Quantity is required")
        
        if not order.side:
            raise OrderValidationError("Side is required")
        
        if not order.stop_price:
            raise OrderValidationError("Stop price is required for take profit orders")
        
        # For TAKE_PROFIT (limit) orders, price is required
        if order.type == OrderType.TAKE_PROFIT and not order.price:
            raise OrderValidationError("Price is required for TAKE_PROFIT (limit) orders")
    
    def prepare_order_params(self, order: Order) -> Dict[str, Any]:
        """
        Prepare take profit order parameters.
        
        Args:
            order: The order to prepare parameters for
            
        Returns:
            Parameters for a take profit order
        """
        # Binance uses TAKE_PROFIT for market stops and TAKE_PROFIT_LIMIT for limit stops
        if order.type == OrderType.TAKE_PROFIT_MARKET:
            order_type = "TAKE_PROFIT"
            params = {
                "symbol": order.symbol,
                "side": order.side.name,
                "type": order_type,
                "quantity": order.quantity,
                "stopPrice": order.stop_price,
                "newClientOrderId": order.client_order_id or order.order_id
            }
        else:  # TAKE_PROFIT (limit)
            order_type = "TAKE_PROFIT_LIMIT"
            params = {
                "symbol": order.symbol,
                "side": order.side.name,
                "type": order_type,
                "timeInForce": order.time_in_force.name if order.time_in_force else TimeInForce.GTC.name,
                "quantity": order.quantity,
                "price": order.price,
                "stopPrice": order.stop_price,
                "newClientOrderId": order.client_order_id or order.order_id
            }
        
        # Add optional parameters if present
        if order.reduce_only:
            params["reduceOnly"] = "true"
        
        return params
    
    def process_response(self, order: Order, response: Dict[str, Any]) -> None:
        """
        Process take profit order response.
        
        Args:
            order: The original order
            response: The exchange response
        """
        # Update order with exchange information
        if "orderId" in response:
            order.metadata["exchange_order_id"] = response["orderId"]
        
        if "clientOrderId" in response:
            order.client_order_id = response["clientOrderId"]
        
        # Take profit orders start in a NEW state
        order.update_status(OrderStatus.NEW)
            
        # Store original response for reference
        order.metadata["exchange_response"] = response


class OrderHandlerFactory:
    """Factory for creating order handlers."""
    
    def __init__(self):
        self._handlers: Dict[OrderType, OrderHandler] = {}
        
        # Register default handlers
        self.register_handler(MarketOrderHandler())
        self.register_handler(LimitOrderHandler())
        self.register_handler(StopLossOrderHandler())
        self.register_handler(TakeProfitOrderHandler())
    
    def register_handler(self, handler: OrderHandler) -> None:
        """
        Register a handler for specific order types.
        
        Args:
            handler: The handler to register
        """
        for order_type in handler.supported_order_types:
            self._handlers[order_type] = handler
    
    def get_handler(self, order_type: OrderType) -> OrderHandler:
        """
        Get the appropriate handler for an order type.
        
        Args:
            order_type: The order type
            
        Returns:
            The appropriate handler for the order type
            
        Raises:
            UnsupportedOrderTypeError: If no handler is found for the order type
        """
        handler = self._handlers.get(order_type)
        if not handler:
            raise UnsupportedOrderTypeError(f"No handler found for order type {order_type.name}")
        
        return handler
    
    def get_handler_for_order(self, order: Order) -> OrderHandler:
        """
        Get the appropriate handler for an order.
        
        Args:
            order: The order
            
        Returns:
            The appropriate handler for the order
            
        Raises:
            UnsupportedOrderTypeError: If no handler is found for the order type
        """
        return self.get_handler(order.type) 