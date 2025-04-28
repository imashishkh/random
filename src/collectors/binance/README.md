# Binance Data Collector

This module provides a comprehensive implementation of Binance API clients and data collectors for both historical and real-time market data.

## Features

- REST API client with authentication, rate limiting, and error handling
- WebSocket client for real-time data streams
- Specialized collectors for different data types (OHLCV, trades, order book, etc.)
- Monitoring and health checks for connection and data integrity
- Configurable data storage procedures
- Comprehensive error handling and retry mechanisms

## Components

### 1. REST API Client (`client.py`)

The `BinanceClient` class provides access to Binance REST API endpoints with:

- Authentication for private endpoints
- Rate limit handling
- Automatic retries for transient errors
- Error handling with detailed exceptions

```python
from src.collectors.binance.client import BinanceClient

async with BinanceClient(api_key="your_api_key", api_secret="your_api_secret") as client:
    # Get server time
    server_time = await client.get_server_time()
    
    # Get historical klines (candlestick data)
    klines = await client.get_klines(
        symbol="BTCUSDT",
        interval="1h",
        limit=100
    )
    
    # Get account information (authenticated)
    account = await client.get_account()
```

### 2. WebSocket Client (`websocket.py`)

The `BinanceWebSocketClient` class manages WebSocket connections for real-time data:

- Subscription management
- Automatic reconnection
- Message handling and callback routing

```python
import asyncio
from src.collectors.binance.websocket import BinanceWebSocketClient

# Define a message handler
async def on_message(msg):
    print(f"Received message: {msg}")

# Create and use the client
client = BinanceWebSocketClient(on_message=on_message)
await client.connect()

# Subscribe to a stream
await client.add_stream("btcusdt@trade")

# Add a specific callback for a stream
client.add_callback("btcusdt@trade", lambda msg: print(f"Trade: {msg['p']} {msg['q']}"))

# Keep running for a while
await asyncio.sleep(60)

# Unsubscribe and disconnect
await client.remove_stream("btcusdt@trade")
await client.disconnect()
```

### 3. Main Collector (`collector.py`)

The `BinanceCollector` class combines REST and WebSocket functionality:

- Unified interface for different data types
- Data normalization to pandas DataFrames
- WebSocket subscription management
- Configurable storage options

```python
import asyncio
from src.collectors.binance.collector import BinanceCollector

# Create collector
collector = BinanceCollector(
    symbols=["BTCUSDT", "ETHUSDT"],
    timeframes=["1h", "4h"],
    api_key="your_api_key",
    api_secret="your_api_secret"
)

# Start the collector
await collector.start()

try:
    # Collect OHLCV data
    klines = await collector.collect("kline", "BTCUSDT", timeframe="1h", limit=10)
    print(f"BTCUSDT 1h klines:\n{klines}")
    
    # Collect trades
    trades = await collector.collect("trade", "BTCUSDT", limit=5)
    print(f"BTCUSDT trades:\n{trades}")
    
    # Subscribe to WebSocket for real-time updates
    await collector.subscribe_ws("trade", "btcusdt", callback=lambda msg: print(f"Trade: {msg}"))
    
    # Wait for some real-time data
    await asyncio.sleep(30)
    
finally:
    # Clean up
    await collector.stop()
```

### 4. Specialized OHLCV Collector (`collectors/ohlcv.py`)

The `OHLCVCollector` class provides specialized functionality for collecting and storing candlestick data:

- Historical data collection with automatic pagination
- Real-time updates via WebSocket
- CSV storage with automatic deduplication

```python
import asyncio
from src.collectors.binance.client import BinanceClient
from src.collectors.binance.websocket import BinanceWebSocketClient
from src.collectors.collectors.ohlcv import OHLCVCollector

# Create clients
client = BinanceClient()
ws_client = BinanceWebSocketClient()

# Create OHLCV collector
collector = OHLCVCollector(
    client=client,
    websocket_client=ws_client,
    symbols=["BTCUSDT"],
    timeframes=["1h", "4h"],
    data_dir="data/ohlcv",
    realtime=True
)

# Start collectors
await client.__aenter__()
await ws_client.connect()

try:
    # Collect historical data
    btc_1h = await collector.collect("BTCUSDT", "1h", limit=100)
    print(f"Collected {len(btc_1h)} candles for BTCUSDT 1h")
    
    # Run continuous collection (collects and stores data)
    run_stats = await collector.run("BTCUSDT")
    print(f"Run stats: {run_stats}")
    
    # Wait for some real-time updates
    await asyncio.sleep(60)
    
finally:
    # Clean up
    await collector.cleanup()
    await ws_client.disconnect()
    await client.__aexit__(None, None, None)
```

### 5. Monitoring (`monitoring.py`)

The `BinanceMonitor` class provides monitoring capabilities:

- Connection health checks
- Data completeness verification
- Performance metrics tracking
- Real-time alerts for issues

```python
import asyncio
from src.collectors.binance.collector import BinanceCollector
from src.collectors.binance.monitoring import BinanceMonitor

# Create collector and monitor
collector = BinanceCollector(symbols=["BTCUSDT"])
monitor = BinanceMonitor("BTCUSDT-Collector")

# Start both
await collector.start()
await monitor.start_monitoring()

try:
    # Perform some collection operations
    for i in range(5):
        try:
            data = await collector.collect("kline", "BTCUSDT", timeframe="1h")
            monitor.record_request(success=True, data_points=len(data))
        except Exception as e:
            monitor.record_request(success=False, error=str(e))
        
        # Get health status
        status = monitor.get_status_report()
        print(f"Health status: {status['connection_status']}")
        
        await asyncio.sleep(10)
        
finally:
    # Clean up
    await monitor.stop_monitoring()
    await collector.stop()
```

## Constants and Configuration

All API URLs, endpoints, timeframes, error codes, and other constants are defined in `constants.py` for centralized management and easy updates when the Binance API changes.

## Error Handling

The implementation includes comprehensive error handling with:

- Specific error classes for different types of errors
- Automatic retries for transient errors
- Rate limiting with backoff
- Detailed logging of error conditions

## Data Storage

The collectors support various storage options:

- In-memory for temporary use
- CSV files for simple persistence
- Can be extended to use databases or other storage backends

## Testing

The module includes comprehensive tests with mock API responses to verify functionality without making actual API calls to Binance. Run the tests with:

```
pytest src/collectors/binance/tests/
```

## Monitoring and Health Checks

The monitoring system provides:

- Real-time connection health monitoring
- Data completeness verification
- Performance metrics and alerts
- Detailed status reporting for operational visibility

## Usage Guidelines

1. Always use the collectors within an async context or event loop
2. Use API rate limiting to avoid getting banned by Binance
3. Handle API key security properly (don't hardcode keys)
4. Monitor collector health for production deployments
5. Consider using the test module for development to avoid API rate limit issues 