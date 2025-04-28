"""
Test script to demonstrate order handlers and commands.
"""

import logging
import time
from typing import Dict, Any
from unittest.mock import MagicMock

from .models.orders import Order, OrderType, OrderSide
from .execution.orders.handlers import (
    OrderHandlerFactory,
    MarketOrderHandler,
    LimitOrderHandler,
    StopLossOrderHandler,
    TakeProfitOrderHandler
)
from .execution.orders.commands import (
    PlaceOrderCommand,
    CancelOrderCommand,
    UpdateOrderCommand,
    BatchOrderCommand
)
from .execution.orders.manager import OrderManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MockExchangeClient:
    """Mock exchange client for testing."""
    
    def __init__(self):
        self.orders = {}
        self.order_id_counter = 1000
        
    def create_order(self, **kwargs):
        """Mock create order method."""
        exchange_order_id = self.order_id_counter
        self.order_id_counter += 1
        
        order_data = {
            "symbol": kwargs.get("symbol"),
            "side": kwargs.get("side"),
            "type": kwargs.get("type"),
            "orderId": exchange_order_id,
            "clientOrderId": kwargs.get("newClientOrderId", f"test{exchange_order_id}"),
            "price": kwargs.get("price"),
            "origQty": kwargs.get("quantity"),
            "executedQty": "0",
            "status": "NEW",
            "timeInForce": kwargs.get("timeInForce", "GTC"),
            "createTime": int(time.time() * 1000),
        }
        
        if kwargs.get("type") in ["STOP_LOSS", "STOP_LOSS_LIMIT", "TAKE_PROFIT", "TAKE_PROFIT_LIMIT"]:
            order_data["stopPrice"] = kwargs.get("stopPrice")
        
        self.orders[exchange_order_id] = order_data
        
        logger.info(f"Created mock order: {order_data}")
        return order_data
    
    def cancel_order(self, **kwargs):
        """Mock cancel order method."""
        symbol = kwargs.get("symbol")
        order_id = kwargs.get("orderId")
        client_order_id = kwargs.get("origClientOrderId")
        
        # Find the order
        target_order = None
        if order_id and order_id in self.orders:
            target_order = self.orders[order_id]
        elif client_order_id:
            for order in self.orders.values():
                if order["clientOrderId"] == client_order_id:
                    target_order = order
                    break
        
        if not target_order:
            raise Exception(f"Order not found: {order_id or client_order_id}")
        
        # Update order status
        target_order["status"] = "CANCELED"
        
        logger.info(f"Cancelled mock order: {target_order}")
        return {
            "symbol": target_order["symbol"],
            "origClientOrderId": target_order["clientOrderId"],
            "orderId": target_order["orderId"],
            "status": "CANCELED"
        }
    
    def get_order(self, **kwargs):
        """Mock get order method."""
        symbol = kwargs.get("symbol")
        order_id = kwargs.get("orderId")
        client_order_id = kwargs.get("origClientOrderId")
        
        # Find the order
        target_order = None
        if order_id and order_id in self.orders:
            target_order = self.orders[order_id]
        elif client_order_id:
            for order in self.orders.values():
                if order["clientOrderId"] == client_order_id:
                    target_order = order
                    break
        
        if not target_order:
            raise Exception(f"Order not found: {order_id or client_order_id}")
        
        logger.info(f"Retrieved mock order: {target_order}")
        return target_order
    
    def get_open_orders(self, symbol=None):
        """Mock get open orders method."""
        open_orders = []
        for order in self.orders.values():
            if order["status"] == "NEW":
                if not symbol or order["symbol"] == symbol:
                    open_orders.append(order)
        
        logger.info(f"Retrieved {len(open_orders)} open orders")
        return open_orders
    
    def start_user_data_stream(self):
        """Mock start user data stream method."""
        return "mock_listen_key"
    
    def keep_alive_user_data_stream(self, listen_key):
        """Mock keep alive user data stream method."""
        logger.info(f"Extended listen key: {listen_key}")
        return True


class MockWebSocketClient:
    """Mock WebSocket client for testing."""
    
    def __init__(self):
        self.callbacks = {}
    
    def start_user_data_stream(self, listen_key, callback):
        """Mock start user data stream method."""
        self.callbacks[listen_key] = callback
        logger.info(f"Started user data stream with key: {listen_key}")
        return True


def run_test():
    """Run the order handlers and commands test."""
    logger.info("Starting order handlers and commands test")
    
    # Create mock exchange client and websocket client
    exchange_client = MockExchangeClient()
    ws_client = MockWebSocketClient()
    
    # Create order manager
    order_manager = OrderManager(exchange_client, ws_client)
    
    # Create test orders
    test_orders = [
        Order(
            order_id="market_buy_1",
            symbol="BTCUSDT",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            quantity=0.01,
            price=None
        ),
        Order(
            order_id="limit_sell_1",
            symbol="BTCUSDT",
            order_type=OrderType.LIMIT,
            side=OrderSide.SELL,
            quantity=0.01,
            price=50000.0
        ),
        Order(
            order_id="stop_loss_1",
            symbol="BTCUSDT",
            order_type=OrderType.STOP_LOSS,
            side=OrderSide.SELL,
            quantity=0.01,
            price=None,
            stop_price=45000.0
        ),
        Order(
            order_id="take_profit_1",
            symbol="BTCUSDT",
            order_type=OrderType.TAKE_PROFIT,
            side=OrderSide.SELL,
            quantity=0.01,
            price=None,
            stop_price=55000.0
        )
    ]
    
    # Place orders
    placed_orders = []
    for order in test_orders:
        try:
            logger.info(f"Placing order: {order.order_id}")
            result = order_manager.place_order(order)
            placed_orders.append(order)
            logger.info(f"Order placed successfully: {result}")
        except Exception as e:
            logger.error(f"Failed to place order {order.order_id}: {str(e)}")
    
    # Get active orders
    active_orders = order_manager.get_active_orders()
    logger.info(f"Active orders: {active_orders}")
    
    # Cancel one order
    if placed_orders:
        try:
            order_to_cancel = placed_orders[0]
            logger.info(f"Cancelling order: {order_to_cancel.order_id}")
            result = order_manager.cancel_order(
                order_id=order_to_cancel.order_id,
                symbol=order_to_cancel.symbol
            )
            logger.info(f"Order cancelled successfully: {result}")
        except Exception as e:
            logger.error(f"Failed to cancel order: {str(e)}")
    
    # Update one order
    if len(placed_orders) > 1:
        try:
            order_to_update = placed_orders[1]
            logger.info(f"Updating order: {order_to_update.order_id}")
            result = order_manager.update_order(
                order_id=order_to_update.order_id,
                symbol=order_to_update.symbol,
                new_price=51000.0,
                new_quantity=0.02
            )
            logger.info(f"Order updated successfully: {result}")
        except Exception as e:
            logger.error(f"Failed to update order: {str(e)}")
    
    # Get order status for all orders
    for order in placed_orders:
        try:
            status = order_manager.get_order_status(order.order_id)
            logger.info(f"Order status for {order.order_id}: {status}")
        except Exception as e:
            logger.error(f"Failed to get order status for {order.order_id}: {str(e)}")
    
    # Simulate an order update from websocket
    if placed_orders and len(placed_orders) > 2:
        order_to_update = placed_orders[2]
        order_data = None
        for order_id, data in exchange_client.orders.items():
            if data.get("clientOrderId", "").endswith(order_to_update.order_id):
                order_data = data
                break
        
        if order_data:
            # Create a simulated order fill update
            ws_update = {
                "e": "executionReport",
                "s": order_to_update.symbol,
                "c": order_data["clientOrderId"],
                "i": order_data["orderId"],
                "X": "FILLED",
                "x": "TRADE",
                "q": str(order_to_update.quantity),
                "p": "46000.00",  # Fill price
                "z": str(order_to_update.quantity)  # Total filled
            }
            
            # Send the update
            logger.info(f"Simulating WebSocket order update: {ws_update}")
            if hasattr(ws_client, 'user_stream_id'):
                callback = ws_client.callbacks.get(ws_client.user_stream_id)
                if callback:
                    callback(ws_update)
    
    # Get active orders after update
    active_orders = order_manager.get_active_orders()
    logger.info(f"Active orders after update: {active_orders}")
    
    # Get order history
    order_history = order_manager.get_order_history()
    logger.info(f"Order history: {order_history}")
    
    # Sync with exchange
    try:
        sync_result = order_manager.sync_with_exchange()
        logger.info(f"Sync result: {sync_result}")
    except Exception as e:
        logger.error(f"Failed to sync with exchange: {str(e)}")
    
    # Close order manager
    order_manager.close()
    logger.info("Test completed successfully")


if __name__ == "__main__":
    run_test() 