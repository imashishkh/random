"""
Command Pattern implementation for order actions.

This module implements the Command Pattern for order operations (place, cancel, modify)
to provide a flexible, extensible architecture with support for undo/redo operations
and order action logging.
"""
from typing import Dict, Any, Optional, Tuple, List, Union, Callable
from abc import ABC, abstractmethod
import logging
import time
import random
import uuid
from datetime import datetime

from .execution.orders.model import Order, OrderStatus, OrderSide, OrderType
from ....exchange.binance_api_client import BinanceApiClient
from ....exchange.exceptions import (
    ExchangeError, RateLimitError, InsufficientFundsError, 
    InvalidOrderError, NetworkError, ServerError, TimeoutError
)
from .execution.orders.handlers import OrderHandlerFactory
from .execution.orders.exceptions import OrderExecutionError

# Configure logger
logger = logging.getLogger(__name__)


class OrderCommand(ABC):
    """
    Base class for the Command Pattern implementation of order actions.
    
    Order commands represent actions that can be performed on orders,
    such as placing, canceling, or updating orders.
    """
    
    @abstractmethod
    def execute(self) -> Dict[str, Any]:
        """
        Execute the command.
        
        Returns:
            A dictionary containing the result of the command execution
            
        Raises:
            OrderExecutionError: If the command fails to execute
        """
        pass
    
    @abstractmethod
    def undo(self) -> Dict[str, Any]:
        """
        Undo the command if possible.
        
        Returns:
            A dictionary containing the result of the undo operation
            
        Raises:
            OrderExecutionError: If the undo operation fails
        """
        pass


class PlaceOrderCommand(OrderCommand):
    """Command to place a new order."""
    
    def __init__(self, order: Order, exchange_client: Any, on_success: Optional[Callable] = None):
        """
        Initialize the place order command.
        
        Args:
            order: The order to place
            exchange_client: The exchange client to use
            on_success: Optional callback function to execute upon successful order placement
        """
        self.order = order
        self.exchange_client = exchange_client
        self.on_success = on_success
        self.response = None
        self.exchange_order_id = None
    
    def execute(self) -> Dict[str, Any]:
        """
        Execute the place order command.
        
        Returns:
            A dictionary containing the exchange response
            
        Raises:
            OrderExecutionError: If the order fails to execute
        """
        try:
            logger.info(f"Executing place order command for order {self.order.order_id}")
            
            # Get the appropriate handler for this order type
            handler = OrderHandlerFactory.create_handler(
                self.order.order_type, 
                self.exchange_client
            )
            
            # Validate the order
            handler.validate_order(self.order)
            
            # Execute the order
            self.response = handler.execute_order(self.order)
            
            # Extract the exchange order ID for potential undo operations
            self.exchange_order_id = self.response.get("exchange_order_id")
            
            # Call the success callback if provided
            if self.on_success:
                self.on_success(self.order, self.response)
            
            logger.info(f"Order {self.order.order_id} placed successfully with exchange ID {self.exchange_order_id}")
            return self.response
            
        except Exception as e:
            logger.error(f"Failed to place order {self.order.order_id}: {str(e)}", exc_info=True)
            raise OrderExecutionError(f"Failed to place order: {str(e)}")
    
    def undo(self) -> Dict[str, Any]:
        """
        Undo the place order command by canceling the order.
        
        Returns:
            A dictionary containing the cancellation response
            
        Raises:
            OrderExecutionError: If the cancellation fails
        """
        if not self.exchange_order_id:
            logger.warning(f"Cannot undo place order command for order {self.order.order_id} - no exchange order ID")
            return {"status": "NOTHING_TO_UNDO", "reason": "Order was not successfully placed"}
        
        try:
            logger.info(f"Undoing place order command for order {self.order.order_id} (exchange ID: {self.exchange_order_id})")
            
            cancel_response = self.exchange_client.cancel_order(
                symbol=self.order.symbol,
                orderId=self.exchange_order_id
            )
            
            logger.info(f"Order {self.order.order_id} canceled successfully")
            return {
                "status": "CANCELED",
                "order_id": self.order.order_id,
                "exchange_order_id": self.exchange_order_id,
                "cancel_response": cancel_response
            }
            
        except Exception as e:
            logger.error(f"Failed to cancel order {self.order.order_id}: {str(e)}", exc_info=True)
            raise OrderExecutionError(f"Failed to cancel order: {str(e)}")


class CancelOrderCommand(OrderCommand):
    """Command to cancel an existing order."""
    
    def __init__(self, order_id: str, symbol: str, exchange_client: Any, 
                 exchange_order_id: Optional[str] = None,
                 client_order_id: Optional[str] = None,
                 on_success: Optional[Callable] = None):
        """
        Initialize the cancel order command.
        
        Args:
            order_id: The internal order ID
            symbol: The trading symbol
            exchange_client: The exchange client to use
            exchange_order_id: Optional exchange order ID (if known)
            client_order_id: Optional client order ID (if known)
            on_success: Optional callback function to execute upon successful cancellation
        """
        self.order_id = order_id
        self.symbol = symbol
        self.exchange_client = exchange_client
        self.exchange_order_id = exchange_order_id
        self.client_order_id = client_order_id
        self.on_success = on_success
        self.response = None
        self.original_order = None
    
    def execute(self) -> Dict[str, Any]:
        """
        Execute the cancel order command.
        
        Returns:
            A dictionary containing the cancellation response
            
        Raises:
            OrderExecutionError: If the cancellation fails
        """
        try:
            logger.info(f"Executing cancel order command for order {self.order_id}")
            
            # Build the cancellation parameters
            params = {"symbol": self.symbol}
            
            if self.exchange_order_id:
                params["orderId"] = self.exchange_order_id
            elif self.client_order_id:
                params["origClientOrderId"] = self.client_order_id
            else:
                raise OrderExecutionError("Either exchange order ID or client order ID must be provided")
            
            # Get the original order for potential undo operations
            get_params = params.copy()
            try:
                self.original_order = self.exchange_client.get_order(**get_params)
            except Exception as e:
                logger.warning(f"Failed to get original order details: {str(e)}")
                self.original_order = None
            
            # Cancel the order
            self.response = self.exchange_client.cancel_order(**params)
            
            # Call the success callback if provided
            if self.on_success:
                self.on_success(self.order_id, self.response)
            
            logger.info(f"Order {self.order_id} canceled successfully")
            return {
                "status": "CANCELED",
                "order_id": self.order_id,
                "exchange_order_id": self.exchange_order_id or self.response.get("orderId"),
                "client_order_id": self.client_order_id or self.response.get("clientOrderId"),
                "cancel_response": self.response
            }
            
        except Exception as e:
            logger.error(f"Failed to cancel order {self.order_id}: {str(e)}", exc_info=True)
            raise OrderExecutionError(f"Failed to cancel order: {str(e)}")
    
    def undo(self) -> Dict[str, Any]:
        """
        Undo the cancellation by placing a new order with the same parameters.
        
        Returns:
            A dictionary containing the new order response
            
        Raises:
            OrderExecutionError: If the new order placement fails
        """
        if not self.original_order:
            logger.warning(f"Cannot undo cancel command for order {self.order_id} - no original order details")
            return {"status": "CANNOT_UNDO", "reason": "Original order details not available"}
        
        try:
            logger.info(f"Undoing cancel order command for order {self.order_id}")
            
            # Extract parameters from the original order
            params = {
                "symbol": self.original_order["symbol"],
                "side": self.original_order["side"],
                "type": self.original_order["type"],
            }
            
            # Add quantity
            if "origQty" in self.original_order:
                params["quantity"] = self.original_order["origQty"]
            
            # Add price for limit orders
            if "price" in self.original_order and float(self.original_order["price"]) > 0:
                params["price"] = self.original_order["price"]
            
            # Add stop price for stop orders
            if "stopPrice" in self.original_order and float(self.original_order["stopPrice"]) > 0:
                params["stopPrice"] = self.original_order["stopPrice"]
            
            # Add time in force
            if "timeInForce" in self.original_order:
                params["timeInForce"] = self.original_order["timeInForce"]
            
            # Create a new client order ID
            import time
            params["newClientOrderId"] = f"{self.order_id}_REPL_{int(time.time() * 1000)}"
            
            # Place the new order
            new_order_response = self.exchange_client.create_order(**params)
            
            logger.info(f"Order {self.order_id} replaced successfully")
            return {
                "status": "REPLACED",
                "original_order_id": self.order_id,
                "new_exchange_order_id": new_order_response.get("orderId"),
                "new_client_order_id": new_order_response.get("clientOrderId"),
                "new_order_response": new_order_response
            }
            
        except Exception as e:
            logger.error(f"Failed to replace order {self.order_id}: {str(e)}", exc_info=True)
            raise OrderExecutionError(f"Failed to replace order: {str(e)}")


class UpdateOrderCommand(OrderCommand):
    """Command to update an existing order (cancel and replace)."""
    
    def __init__(self, original_order_id: str, symbol: str, exchange_client: Any,
                 exchange_order_id: Optional[str] = None,
                 client_order_id: Optional[str] = None,
                 new_price: Optional[float] = None,
                 new_quantity: Optional[float] = None,
                 new_stop_price: Optional[float] = None,
                 on_success: Optional[Callable] = None):
        """
        Initialize the update order command.
        
        Args:
            original_order_id: The internal order ID of the order to update
            symbol: The trading symbol
            exchange_client: The exchange client to use
            exchange_order_id: Optional exchange order ID (if known)
            client_order_id: Optional client order ID (if known)
            new_price: Optional new price
            new_quantity: Optional new quantity
            new_stop_price: Optional new stop price
            on_success: Optional callback function to execute upon successful update
        """
        self.original_order_id = original_order_id
        self.symbol = symbol
        self.exchange_client = exchange_client
        self.exchange_order_id = exchange_order_id
        self.client_order_id = client_order_id
        self.new_price = new_price
        self.new_quantity = new_quantity
        self.new_stop_price = new_stop_price
        self.on_success = on_success
        self.original_order = None
        self.cancel_response = None
        self.new_order_response = None
    
    def execute(self) -> Dict[str, Any]:
        """
        Execute the update order command by canceling the existing order and placing a new one.
        
        Returns:
            A dictionary containing the new order response
            
        Raises:
            OrderExecutionError: If the update fails
        """
        try:
            logger.info(f"Executing update order command for order {self.original_order_id}")
            
            # Build the query parameters to get the original order
            get_params = {"symbol": self.symbol}
            
            if self.exchange_order_id:
                get_params["orderId"] = self.exchange_order_id
            elif self.client_order_id:
                get_params["origClientOrderId"] = self.client_order_id
            else:
                raise OrderExecutionError("Either exchange order ID or client order ID must be provided")
            
            # Get the original order details
            self.original_order = self.exchange_client.get_order(**get_params)
            
            # Cancel the original order
            cancel_params = get_params.copy()
            self.cancel_response = self.exchange_client.cancel_order(**cancel_params)
            
            # Extract parameters from the original order for the new order
            new_order_params = {
                "symbol": self.original_order["symbol"],
                "side": self.original_order["side"],
                "type": self.original_order["type"],
            }
            
            # Set quantity (use new if provided, otherwise original)
            if self.new_quantity is not None:
                new_order_params["quantity"] = self.new_quantity
            elif "origQty" in self.original_order:
                new_order_params["quantity"] = self.original_order["origQty"]
            
            # Set price (use new if provided, otherwise original)
            if self.new_price is not None:
                new_order_params["price"] = self.new_price
            elif "price" in self.original_order and float(self.original_order["price"]) > 0:
                new_order_params["price"] = self.original_order["price"]
            
            # Set stop price (use new if provided, otherwise original)
            if self.new_stop_price is not None:
                new_order_params["stopPrice"] = self.new_stop_price
            elif "stopPrice" in self.original_order and float(self.original_order["stopPrice"]) > 0:
                new_order_params["stopPrice"] = self.original_order["stopPrice"]
            
            # Add time in force
            if "timeInForce" in self.original_order:
                new_order_params["timeInForce"] = self.original_order["timeInForce"]
            
            # Create a new client order ID
            import time
            new_order_params["newClientOrderId"] = f"{self.original_order_id}_UPD_{int(time.time() * 1000)}"
            
            # Place the new order
            self.new_order_response = self.exchange_client.create_order(**new_order_params)
            
            # Call the success callback if provided
            if self.on_success:
                self.on_success(self.original_order_id, self.new_order_response)
            
            logger.info(f"Order {self.original_order_id} updated successfully")
            return {
                "status": "UPDATED",
                "original_order_id": self.original_order_id,
                "new_exchange_order_id": self.new_order_response.get("orderId"),
                "new_client_order_id": self.new_order_response.get("clientOrderId"),
                "cancel_response": self.cancel_response,
                "new_order_response": self.new_order_response
            }
            
        except Exception as e:
            logger.error(f"Failed to update order {self.original_order_id}: {str(e)}", exc_info=True)
            raise OrderExecutionError(f"Failed to update order: {str(e)}")
    
    def undo(self) -> Dict[str, Any]:
        """
        Undo the update by canceling the new order and placing another order with the original parameters.
        
        Returns:
            A dictionary containing the response
            
        Raises:
            OrderExecutionError: If the undo operation fails
        """
        if not self.original_order or not self.new_order_response:
            logger.warning(f"Cannot undo update command for order {self.original_order_id} - incomplete information")
            return {"status": "CANNOT_UNDO", "reason": "Incomplete order information"}
        
        try:
            logger.info(f"Undoing update order command for order {self.original_order_id}")
            
            # Cancel the new order
            new_order_id = self.new_order_response.get("orderId")
            if new_order_id:
                self.exchange_client.cancel_order(
                    symbol=self.symbol,
                    orderId=new_order_id
                )
            
            # Extract parameters from the original order
            orig_params = {
                "symbol": self.original_order["symbol"],
                "side": self.original_order["side"],
                "type": self.original_order["type"],
            }
            
            # Add quantity
            if "origQty" in self.original_order:
                orig_params["quantity"] = self.original_order["origQty"]
            
            # Add price for limit orders
            if "price" in self.original_order and float(self.original_order["price"]) > 0:
                orig_params["price"] = self.original_order["price"]
            
            # Add stop price for stop orders
            if "stopPrice" in self.original_order and float(self.original_order["stopPrice"]) > 0:
                orig_params["stopPrice"] = self.original_order["stopPrice"]
            
            # Add time in force
            if "timeInForce" in self.original_order:
                orig_params["timeInForce"] = self.original_order["timeInForce"]
            
            # Create a new client order ID
            import time
            orig_params["newClientOrderId"] = f"{self.original_order_id}_UNDO_{int(time.time() * 1000)}"
            
            # Place a new order with the original parameters
            restored_order_response = self.exchange_client.create_order(**orig_params)
            
            logger.info(f"Order {self.original_order_id} restored to original state")
            return {
                "status": "RESTORED",
                "original_order_id": self.original_order_id,
                "restored_exchange_order_id": restored_order_response.get("orderId"),
                "restored_client_order_id": restored_order_response.get("clientOrderId"),
                "restored_order_response": restored_order_response
            }
            
        except Exception as e:
            logger.error(f"Failed to restore order {self.original_order_id}: {str(e)}", exc_info=True)
            raise OrderExecutionError(f"Failed to restore order: {str(e)}")


class BatchOrderCommand(OrderCommand):
    """Command to execute multiple order commands as a batch."""
    
    def __init__(self, commands: List[OrderCommand], all_or_nothing: bool = False):
        """
        Initialize the batch order command.
        
        Args:
            commands: List of OrderCommand objects to execute
            all_or_nothing: If True, all commands must succeed or all will be undone
        """
        self.commands = commands
        self.all_or_nothing = all_or_nothing
        self.executed_commands = []
        self.failed_command = None
        self.results = []
    
    def execute(self) -> Dict[str, Any]:
        """
        Execute all commands in the batch.
        
        Returns:
            A dictionary containing the results of all commands
            
        Raises:
            OrderExecutionError: If a command fails and all_or_nothing is True
        """
        try:
            logger.info(f"Executing batch of {len(self.commands)} commands")
            
            for command in self.commands:
                try:
                    result = command.execute()
                    self.results.append({
                        "status": "SUCCESS",
                        "command": command.__class__.__name__,
                        "result": result
                    })
                    self.executed_commands.append(command)
                except Exception as e:
                    logger.error(f"Command {command.__class__.__name__} failed: {str(e)}")
                    self.results.append({
                        "status": "ERROR",
                        "command": command.__class__.__name__,
                        "error": str(e)
                    })
                    self.failed_command = command
                    
                    if self.all_or_nothing:
                        # Undo all previously executed commands
                        self.undo()
                        raise OrderExecutionError(f"Batch execution failed: {str(e)}")
            
            num_succeeded = sum(1 for r in self.results if r["status"] == "SUCCESS")
            logger.info(f"Batch execution completed with {num_succeeded}/{len(self.commands)} successes")
            
            return {
                "status": "COMPLETE",
                "all_succeeded": num_succeeded == len(self.commands),
                "results": self.results
            }
            
        except Exception as e:
            if not self.all_or_nothing:
                logger.error(f"Batch execution error: {str(e)}", exc_info=True)
                return {
                    "status": "PARTIAL",
                    "error": str(e),
                    "results": self.results
                }
            else:
                raise OrderExecutionError(f"Batch execution failed: {str(e)}")
    
    def undo(self) -> Dict[str, Any]:
        """
        Undo all executed commands in reverse order.
        
        Returns:
            A dictionary containing the results of all undo operations
            
        Raises:
            OrderExecutionError: If an undo operation fails
        """
        logger.info(f"Undoing batch of {len(self.executed_commands)} executed commands")
        
        undo_results = []
        
        # Undo commands in reverse order (last executed first)
        for command in reversed(self.executed_commands):
            try:
                undo_result = command.undo()
                undo_results.append({
                    "status": "SUCCESS",
                    "command": command.__class__.__name__,
                    "result": undo_result
                })
            except Exception as e:
                logger.error(f"Failed to undo command {command.__class__.__name__}: {str(e)}")
                undo_results.append({
                    "status": "ERROR",
                    "command": command.__class__.__name__,
                    "error": str(e)
                })
        
        num_succeeded = sum(1 for r in undo_results if r["status"] == "SUCCESS")
        logger.info(f"Batch undo completed with {num_succeeded}/{len(self.executed_commands)} successes")
        
        return {
            "status": "UNDO_COMPLETE",
            "all_undos_succeeded": num_succeeded == len(self.executed_commands),
            "undo_results": undo_results
        }


def retry_with_backoff(max_attempts: int = 3, 
                     base_delay: float = 1.0, 
                     max_delay: float = 60.0, 
                     retryable_exceptions: List[type] = None):
    """
    Decorator for retrying commands with exponential backoff.
    
    Args:
        max_attempts: Maximum number of attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        retryable_exceptions: List of exceptions to retry on (defaults to network-related exceptions)
    
    Returns:
        Decorator function
    """
    if retryable_exceptions is None:
        retryable_exceptions = [
            NetworkError, 
            TimeoutError, 
            ServerError, 
            RateLimitError
        ]
    
    def decorator(func):
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except tuple(retryable_exceptions) as e:
                    attempts += 1
                    if attempts >= max_attempts:
                        raise
                    
                    # Calculate delay with jitter
                    delay = min(base_delay * (2 ** (attempts - 1)), max_delay)
                    jitter = random.uniform(0, 0.1 * delay)
                    sleep_time = delay + jitter
                    
                    logger.warning(
                        f"Retrying command after error ({attempts}/{max_attempts}): "
                        f"{str(e)}. Waiting {sleep_time:.2f}s"
                    )
                    
                    time.sleep(sleep_time)
                except Exception:
                    # Don't retry other exceptions
                    raise
        return wrapper
    return decorator 