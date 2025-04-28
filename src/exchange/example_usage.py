"""
Example usage of the UnifiedClient interface.

This file demonstrates common usage patterns for the UnifiedClient interface,
showing how it simplifies interactions with cryptocurrency exchanges by
abstracting away the differences between REST and WebSocket transports.
"""
import asyncio
import logging
from typing import Dict, Any
import time

from .unified_client import (
    UnifiedClient, 
    UnifiedClientFactory,
    TransportPreference,
    OperationCategory
)
from .auth.provider import ApiKeyAuthProvider
from .rate_limiting.limiter import RateLimiter
from .client import MarketOperation


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def demo_direct_client_creation():
    """Demonstrate creating a client directly."""
    # Create an authentication provider
    auth_provider = ApiKeyAuthProvider(
        api_key="your_api_key",
        api_secret="your_api_secret"
    )
    
    # Create a rate limiter
    rate_limiter = RateLimiter(
        max_requests_per_second=10,
        max_request_weight_per_minute=1200
    )
    
    # Create a unified client
    client = UnifiedClient(
        exchange_id="binance",
        base_url="https://api.binance.com",
        ws_url="wss://stream.binance.com:9443/ws",
        auth_provider=auth_provider,
        rate_limiter=rate_limiter,
        # Override default transport preferences if needed
        transport_preferences={
            # Always use WebSocket for market data
            OperationCategory.MARKET_DATA: TransportPreference.WEBSOCKET_ONLY,
        },
        # Configure retry behavior
        max_retries=3,
        retry_delay=1.0,
        timeout=30.0
    )
    
    return client


def demo_factory_creation():
    """Demonstrate creating a client using the factory pattern."""
    # First, register exchanges with the factory
    UnifiedClientFactory.register_exchange(
        exchange_id="binance",
        base_url="https://api.binance.com",
        ws_url="wss://stream.binance.com:9443/ws",
        # Default preferences for operations
        transport_preferences={
            OperationCategory.MARKET_DATA: TransportPreference.WEBSOCKET_PREFERRED,
            OperationCategory.TRADING: TransportPreference.REST_ONLY,
        }
    )
    
    # Register another exchange
    UnifiedClientFactory.register_exchange(
        exchange_id="kucoin",
        base_url="https://api.kucoin.com",
        ws_url="wss://ws-api.kucoin.com"
    )
    
    # Create authentication provider
    auth_provider = ApiKeyAuthProvider(
        api_key="your_api_key",
        api_secret="your_api_secret"
    )
    
    # Create a rate limiter
    rate_limiter = RateLimiter(
        max_requests_per_second=10,
        max_request_weight_per_minute=1200
    )
    
    # Create clients for different exchanges using the factory
    binance_client = UnifiedClientFactory.create(
        exchange_id="binance",
        auth_provider=auth_provider,
        rate_limiter=rate_limiter
    )
    
    kucoin_client = UnifiedClientFactory.create(
        exchange_id="kucoin",
        auth_provider=auth_provider,
        rate_limiter=rate_limiter
    )
    
    return binance_client, kucoin_client


def demo_market_data():
    """Demonstrate fetching market data."""
    client = demo_direct_client_creation()
    
    try:
        # Get ticker information
        # The UnifiedClient automatically selects the appropriate transport
        ticker = client.get_ticker(symbol="BTC/USDT")
        logger.info(f"BTC/USDT Ticker: {ticker}")
        
        # Get order book
        order_book = client.get_order_book(symbol="ETH/USDT", limit=10)
        logger.info(f"ETH/USDT Order Book (10 levels): {order_book}")
        
        # Get recent trades
        trades = client.get_recent_trades(symbol="BTC/USDT", limit=5)
        logger.info(f"BTC/USDT Recent Trades (5): {trades}")
        
        # Get klines (candlestick data)
        klines = client.get_klines(
            symbol="BTC/USDT",
            interval="1h",
            limit=24  # Last 24 hours
        )
        logger.info(f"BTC/USDT Hourly Klines (24): {len(klines)} candles")
        
        # Force usage of REST for a specific request
        ticker_rest = client.execute(
            operation=MarketOperation.GET_TICKER,
            params={"symbol": "BTC/USDT"},
            transport_preference=TransportPreference.REST_ONLY
        )
        logger.info(f"BTC/USDT Ticker (REST): {ticker_rest}")
        
    finally:
        # Clean up resources
        client.close()


def demo_trading():
    """Demonstrate trading operations."""
    client = demo_direct_client_creation()
    
    try:
        # Get account information
        account_info = client.get_account_info()
        logger.info(f"Account Info: {account_info}")
        
        # Get balances
        balances = client.get_balances()
        logger.info(f"Balances: {balances}")
        
        # Create a limit order
        order = client.create_order(
            symbol="BTC/USDT",
            order_type="limit",
            side="buy",
            amount=0.01,  # 0.01 BTC
            price=50000.0,  # $50,000 per BTC
            # Additional parameters
            time_in_force="GTC"  # Good Till Cancelled
        )
        logger.info(f"Created Order: {order}")
        
        # Get order status
        order_status = client.get_order(
            order_id=order["id"],
            symbol="BTC/USDT"
        )
        logger.info(f"Order Status: {order_status}")
        
        # Cancel the order
        cancel_result = client.cancel_order(
            order_id=order["id"],
            symbol="BTC/USDT"
        )
        logger.info(f"Cancel Result: {cancel_result}")
        
    finally:
        # Clean up resources
        client.close()


def demo_websocket_subscriptions():
    """Demonstrate WebSocket subscriptions for real-time data."""
    client = demo_direct_client_creation()
    
    # Define callback functions for different data types
    def on_ticker_update(data: Dict[str, Any]):
        logger.info(f"Ticker Update: {data}")
    
    def on_orderbook_update(data: Dict[str, Any]):
        logger.info(f"Order Book Update: {data}")
    
    def on_trades_update(data: Dict[str, Any]):
        logger.info(f"Trades Update: {data}")
    
    try:
        # Subscribe to ticker updates
        ticker_sub_id = client.subscribe_ticker(
            symbol="BTC/USDT",
            callback=on_ticker_update
        )
        logger.info(f"Subscribed to BTC/USDT ticker with ID: {ticker_sub_id}")
        
        # Subscribe to order book updates
        orderbook_sub_id = client.subscribe_order_book(
            symbol="BTC/USDT",
            callback=on_orderbook_update
        )
        logger.info(f"Subscribed to BTC/USDT order book with ID: {orderbook_sub_id}")
        
        # Subscribe to trade updates
        trades_sub_id = client.subscribe_trades(
            symbol="BTC/USDT",
            callback=on_trades_update
        )
        logger.info(f"Subscribed to BTC/USDT trades with ID: {trades_sub_id}")
        
        # Keep the subscriptions active for a while
        logger.info("Listening for updates for 30 seconds...")
        time.sleep(30)
        
        # Unsubscribe from one channel
        client.unsubscribe(ticker_sub_id)
        logger.info(f"Unsubscribed from ticker updates")
        
        # Keep listening on the remaining channels
        logger.info("Continuing to listen for order book and trade updates for 30 more seconds...")
        time.sleep(30)
        
    finally:
        # Clean up resources (this will automatically unsubscribe from all channels)
        client.close()


def demo_error_handling_and_failover():
    """Demonstrate error handling and transport failover."""
    client = demo_direct_client_creation()
    
    try:
        # Simulate a scenario where the first attempt fails but retry succeeds
        logger.info("Demonstrating automatic retry and failover...")
        
        # This would normally be handled internally, but for demonstration:
        # 1. First attempt with REST fails
        # 2. Second attempt with WebSocket succeeds
        
        # In practice, the UnifiedClient handles this automatically:
        result = client.get_ticker(symbol="BTC/USDT")
        logger.info(f"Operation succeeded after potential failover: {result}")
        
        # You can also manually override the transport preference:
        try:
            # Force WebSocket for an operation that might fail with WebSocket
            result = client.execute(
                operation=MarketOperation.GET_TICKER,
                params={"symbol": "BTC/USDT"},
                transport_preference=TransportPreference.WEBSOCKET_ONLY
            )
            logger.info(f"WebSocket operation succeeded: {result}")
        except Exception as e:
            logger.error(f"WebSocket operation failed: {str(e)}")
            # Fall back to REST manually
            result = client.execute(
                operation=MarketOperation.GET_TICKER,
                params={"symbol": "BTC/USDT"},
                transport_preference=TransportPreference.REST_ONLY
            )
            logger.info(f"Fallback to REST succeeded: {result}")
        
    finally:
        # Clean up resources
        client.close()


def main():
    """Run the demonstration."""
    logger.info("Starting UnifiedClient demonstration")
    
    # Demonstrate client creation methods
    logger.info("\n--- Demonstrating Client Creation ---")
    direct_client = demo_direct_client_creation()
    direct_client.close()
    
    binance_client, kucoin_client = demo_factory_creation()
    binance_client.close()
    kucoin_client.close()
    
    # Demonstrate market data operations
    logger.info("\n--- Demonstrating Market Data Operations ---")
    demo_market_data()
    
    # Demonstrate trading operations
    logger.info("\n--- Demonstrating Trading Operations ---")
    demo_trading()
    
    # Demonstrate WebSocket subscriptions
    logger.info("\n--- Demonstrating WebSocket Subscriptions ---")
    demo_websocket_subscriptions()
    
    # Demonstrate error handling and failover
    logger.info("\n--- Demonstrating Error Handling and Failover ---")
    demo_error_handling_and_failover()
    
    logger.info("Demonstration completed")


if __name__ == "__main__":
    main() 