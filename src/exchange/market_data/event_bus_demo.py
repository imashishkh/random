"""
Demonstration of the MarketEventBus.

This script demonstrates the basic functionality of the MarketEventBus,
including publishing events and subscribing to topics.
"""
import asyncio
import logging
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Import locally to avoid dependency issues
from event_bus import MarketEventBus

# Sample event handlers
async def trade_handler(topic, data):
    """Handle trade events."""
    logging.info(f"Trade handler received: {topic} - {data}")
    await asyncio.sleep(0.01)  # Simulate processing

async def orderbook_handler(topic, data):
    """Handle orderbook events."""
    logging.info(f"Orderbook handler received: {topic} - {data}")
    await asyncio.sleep(0.02)  # Simulate processing

async def high_priority_handler(topic, data):
    """High-priority handler for all events."""
    logging.info(f"HIGH PRIORITY handler received: {topic}")
    await asyncio.sleep(0.005)  # Simulate processing

async def simulate_market_data():
    """Simulate publishing market data events."""
    bus = MarketEventBus()
    
    # Generate some trade events
    for i in range(5):
        symbol = "BTCUSDT"
        trade_data = {
            "symbol": symbol,
            "price": 50000.0 + (i * 10),
            "quantity": 1.0 + (i * 0.1),
            "timestamp": int(time.time() * 1000)
        }
        
        await bus.publish(f"trade.{symbol}", trade_data)
        logging.info(f"Published trade #{i+1} for {symbol}")
        
        await asyncio.sleep(0.1)
    
    # Generate some orderbook events
    for i in range(3):
        symbol = "ETHUSDT"
        orderbook_data = {
            "symbol": symbol,
            "bids": [[3000.0 - i, 2.0]],
            "asks": [[3005.0 + i, 1.5]],
            "timestamp": int(time.time() * 1000)
        }
        
        await bus.publish(f"orderbook.{symbol}", orderbook_data)
        logging.info(f"Published orderbook #{i+1} for {symbol}")
        
        await asyncio.sleep(0.2)
    
    # Wait for all events to be processed
    await bus.queue.join()
    
    # Get and log metrics
    metrics = bus.get_metrics()
    logging.info(f"Event bus metrics: {metrics}")

async def main():
    """Run the demonstration."""
    # Create event bus
    bus = MarketEventBus()
    
    # Start the event bus
    await bus.start()
    
    try:
        # Subscribe to events
        bus.subscribe("trade.BTCUSDT", trade_handler)
        bus.subscribe("orderbook.ETHUSDT", orderbook_handler)
        
        # Subscribe with high priority
        bus.subscribe("trade.BTCUSDT", high_priority_handler, priority=10)
        
        # Run the simulation
        await simulate_market_data()
        
        # Demonstrate unsubscription
        logging.info("Unsubscribing trade handler and running again")
        bus.unsubscribe("trade.BTCUSDT", trade_handler)
        
        # Run the simulation again
        await simulate_market_data()
        
    finally:
        # Stop the event bus
        await bus.stop()
    
    logging.info("Demonstration completed successfully")

if __name__ == "__main__":
    asyncio.run(main()) 