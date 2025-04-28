"""
Basic usage examples for the Binance API client.

This script demonstrates how to use both the REST API and WebSocket clients
to fetch and stream data from Binance.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from ..client import BinanceClient
from ..websocket import BinanceWebSocketClient
from ..models import Trade, OHLCV, OrderBook, Ticker


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_rest_api():
    """Test REST API functionality."""
    logger.info("Testing Binance REST API client...")
    
    # Initialize client
    client = BinanceClient()
    
    try:
        # Get server time
        server_time = await client.get_server_time()
        logger.info(f"Server time: {server_time} (ms)")
        
        # Get exchange info for a specific symbol
        symbol = "BTCUSDT"
        exchange_info = await client.get_exchange_info(symbol=symbol)
        logger.info(f"Exchange info for {symbol}: {exchange_info['symbols'][0]['status']}")
        
        # Get recent trades
        trades = await client.get_recent_trades(symbol=symbol, limit=5)
        logger.info(f"Recent trades for {symbol}:")
        for trade in trades:
            logger.info(f"  {trade.time} - Price: {trade.price}, Quantity: {trade.quantity}")
        
        # Get order book
        order_book = await client.get_order_book(symbol=symbol, limit=5)
        logger.info(f"Order book for {symbol}:")
        logger.info(f"  Top bid: {order_book.bids[0].price} - {order_book.bids[0].quantity}")
        logger.info(f"  Top ask: {order_book.asks[0].price} - {order_book.asks[0].quantity}")
        
        # Get candlestick data
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)
        klines = await client.get_klines(
            symbol=symbol,
            interval="5m",
            start_time=start_time,
            end_time=end_time,
            limit=10
        )
        logger.info(f"Candlestick data for {symbol} (5m):")
        for kline in klines:
            logger.info(f"  {kline.open_time} - Open: {kline.open_price}, Close: {kline.close_price}")
            
        # Get ticker
        ticker = await client.get_ticker(symbol=symbol)
        logger.info(f"24h ticker for {symbol}:")
        logger.info(f"  Price change: {ticker.price_change} ({ticker.price_change_percent}%)")
        logger.info(f"  Volume: {ticker.volume}")
        
        # Get latest price
        price = await client.get_ticker_price(symbol=symbol)
        logger.info(f"Latest price for {symbol}: {price}")
        
    except Exception as e:
        logger.error(f"Error in REST API test: {e}")
    finally:
        await client.close_session()


async def trade_callback(trade: Trade):
    """Callback for trade data."""
    logger.info(f"Trade: {trade.symbol} - Price: {trade.price}, Quantity: {trade.quantity}")


async def kline_callback(kline: OHLCV):
    """Callback for kline data."""
    logger.info(f"Kline: {kline.symbol} - Time: {kline.open_time}, Close: {kline.close_price}")


async def book_callback(order_book: OrderBook):
    """Callback for order book data."""
    logger.info(f"OrderBook: {order_book.symbol} - Bid: {order_book.bids[0].price}, Ask: {order_book.asks[0].price}")


async def ticker_callback(ticker: Ticker):
    """Callback for ticker data."""
    logger.info(f"Ticker: {ticker.symbol} - Price: {ticker.last_price}, 24h Change: {ticker.price_change_percent}%")


async def test_websocket():
    """Test WebSocket API functionality."""
    logger.info("Testing Binance WebSocket client...")
    
    # Initialize client
    ws_client = BinanceWebSocketClient()
    
    try:
        symbol = "btcusdt"
        
        # Subscribe to trade stream
        await ws_client.subscribe(symbol, "TRADE", trade_callback)
        logger.info(f"Subscribed to {symbol} trade stream")
        
        # Subscribe to kline stream
        await ws_client.subscribe_kline(symbol, "1m", kline_callback)
        logger.info(f"Subscribed to {symbol} 1m kline stream")
        
        # Subscribe to multiple streams with a single connection
        streams = [
            {"symbol": "ethusdt", "type": "TRADE"},
            {"symbol": "ethusdt", "type": "KLINE", "interval": "1m"}
        ]
        await ws_client.subscribe_multiple(streams, ticker_callback)
        logger.info(f"Subscribed to multiple streams")
        
        # Keep the connection alive for a while
        logger.info("Listening for WebSocket messages...")
        await asyncio.sleep(30)
        
    except Exception as e:
        logger.error(f"Error in WebSocket test: {e}")
    finally:
        await ws_client.close()


async def main():
    """Main function to run examples."""
    # Test REST API
    await test_rest_api()
    
    # Test WebSocket API
    await test_websocket()


if __name__ == "__main__":
    asyncio.run(main()) 