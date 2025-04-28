"""
Example demonstrating the usage of Order model and Order Management System.
"""
import sys
import os
import time
import logging
import json
import uuid
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from .execution.orders.model import (
    Order, OrderSide, OrderType, OrderStatus, OrderTimeInForce, OrderExecution
)
from .execution.orders.manager import (
    OrderManager, OrderEvent, symbol_validator, price_validator, quantity_validator
)
from .execution.messaging.queue import (
    MessageBus, MessageType, Message, MessageQueueFactory
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def order_event_handler(order, **kwargs):
    """Example order event handler."""
    logger.info(f"Order Event: {order.order_id} - {order.status.value}")
    if kwargs:
        logger.info(f"Event details: {json.dumps(kwargs, default=str)}")


def simulate_execution(order_manager, order_id):
    """Simulate an execution for the order."""
    order = order_manager.get_order(order_id)
    if not order:
        logger.error(f"Order {order_id} not found")
        return False

    # Create an execution
    execution = OrderExecution(
        execution_id=str(uuid.uuid4()),
        order_id=order.order_id,
        quantity=order.quantity,  # Fully executed
        price=order.price if order.price else 1.12345,  # Use limit price or market price
        timestamp=datetime.now(),
        venue="SIM_EXCHANGE"
    )

    # Process the execution
    order_manager.process_execution(order_id, execution.to_dict())
    logger.info(f"Executed order {order_id} at price {execution.price}")
    return True


def message_handler(message):
    """Handle messages from the message bus."""
    logger.info(f"Received message: {message.message_type.value}")
    logger.info(f"Message data: {json.dumps(message.data, default=str)}")


def main():
    """Run the order example."""
    # Create message bus and order manager
    queue_factory = MessageQueueFactory()
    message_bus = queue_factory.create_message_bus("example_bus")
    message_bus.start()

    # Create a temporary directory for order storage
    import tempfile
    temp_dir = tempfile.mkdtemp()
    logger.info(f"Using temporary storage directory: {temp_dir}")
    
    # Create order manager
    order_manager = OrderManager(
        message_bus=message_bus,
        storage_dir=temp_dir
    )
    
    # Register validators
    order_manager.register_validator(symbol_validator)
    order_manager.register_validator(price_validator)
    order_manager.register_validator(quantity_validator)
    
    # Register event handlers
    order_manager.register_event_handler(OrderEvent.CREATED, order_event_handler)
    order_manager.register_event_handler(OrderEvent.VALIDATED, order_event_handler)
    order_manager.register_event_handler(OrderEvent.ROUTED, order_event_handler)
    order_manager.register_event_handler(OrderEvent.FILLED, order_event_handler)
    
    # Subscribe to order messages
    message_bus.subscribe(
        message_types=[MessageType.ORDER_UPDATE],
        callback=message_handler
    )
    
    # Create a market order
    market_order_id, success, error = order_manager.create_market_order(
        symbol="EURUSD",
        side=OrderSide.BUY,
        quantity=10000.0,
        account_id="demo_account",
        client_order_id="market_order_1",
        strategy_id="example_strategy"
    )
    
    if not success:
        logger.error(f"Failed to create market order: {error}")
        return
    
    logger.info(f"Created market order with ID: {market_order_id}")
    
    # Create a limit order
    limit_order_id, success, error = order_manager.create_limit_order(
        symbol="GBPUSD",
        side=OrderSide.SELL,
        quantity=5000.0,
        price=1.25,
        account_id="demo_account",
        client_order_id="limit_order_1",
        strategy_id="example_strategy"
    )
    
    if not success:
        logger.error(f"Failed to create limit order: {error}")
        return
    
    logger.info(f"Created limit order with ID: {limit_order_id}")
    
    # Wait a moment for processing
    time.sleep(1)
    
    # Check active orders
    active_orders = order_manager.get_active_orders()
    logger.info(f"Active orders: {len(active_orders)}")
    for order in active_orders:
        logger.info(f"  {order}")
    
    # Simulate execution for the market order
    logger.info("Simulating execution for market order...")
    simulate_execution(order_manager, market_order_id)
    
    # Wait a moment for processing
    time.sleep(1)
    
    # Check order status
    market_order = order_manager.get_order(market_order_id)
    logger.info(f"Market order status: {market_order.status.value}")
    logger.info(f"Market order filled quantity: {market_order.filled_quantity}")
    logger.info(f"Market order average fill price: {market_order.average_fill_price}")
    
    # Cancel the limit order
    logger.info("Canceling limit order...")
    success, error = order_manager.cancel_order(limit_order_id)
    
    if not success:
        logger.error(f"Failed to cancel limit order: {error}")
    else:
        logger.info("Limit order canceled successfully")
    
    # Wait a moment for processing
    time.sleep(1)
    
    # Check order status
    limit_order = order_manager.get_order(limit_order_id)
    logger.info(f"Limit order status: {limit_order.status.value}")
    
    # Get orders by account
    account_orders = order_manager.get_orders_by_account("demo_account")
    logger.info(f"Orders for account 'demo_account': {len(account_orders)}")
    
    # Get orders by strategy
    strategy_orders = order_manager.get_orders_by_strategy("example_strategy")
    logger.info(f"Orders for strategy 'example_strategy': {len(strategy_orders)}")
    
    # Send a message to the message bus (simulating an external order)
    new_order = Order(
        symbol="USDJPY",
        side=OrderSide.BUY,
        quantity=15000.0,
        order_type=OrderType.LIMIT,
        price=108.50,
        account_id="demo_account",
        client_order_id="external_order_1",
        strategy_id="api_strategy"
    )
    
    message_bus.publish(
        Message(
            message_type=MessageType.ORDER_NEW,
            source="external_client",
            data={"order": new_order.to_dict()}
        )
    )
    
    logger.info("Published external order to message bus")
    
    # Wait a moment for processing
    time.sleep(1)
    
    # Check if the external order was received and processed
    external_order = order_manager.get_order_by_client_id("external_order_1")
    if external_order:
        logger.info(f"External order received and processed: {external_order}")
        logger.info(f"External order status: {external_order.status.value}")
    else:
        logger.error("External order not found")
    
    # Clean up
    message_bus.stop()
    logger.info("Example completed")


if __name__ == "__main__":
    main() 