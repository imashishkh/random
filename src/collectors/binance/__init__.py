"""
Binance API client for cryptocurrency data collection.

This package provides functionality for interacting with the Binance API,
including REST API requests and WebSocket streams.
"""

from .client import BinanceClient
from .websocket import BinanceWebSocketClient
from .constants import (
    INTERVALS,
    REST_API_URL,
    TESTNET_API_URL,
    WS_API_URL,
    WS_API_COMBINED_URL,
    STREAM_TYPES,
)
from .exceptions import (
    BinanceAPIException,
    BinanceOrderException,
    BinanceRateLimitException,
    BinanceRequestException,
    BinanceResponseException,
    BinanceTimeoutException,
    BinanceWebSocketException,
)
from .models import (
    BookTicker,
    OHLCV,
    OrderBook,
    OrderBookEntry,
    Ticker,
    Trade,
)

__all__ = [
    # Clients
    "BinanceClient",
    "BinanceWebSocketClient",
    
    # Constants
    "INTERVALS",
    "REST_API_URL",
    "TESTNET_API_URL",
    "WS_API_URL",
    "WS_API_COMBINED_URL",
    "STREAM_TYPES",
    
    # Exceptions
    "BinanceAPIException",
    "BinanceOrderException",
    "BinanceRateLimitException",
    "BinanceRequestException",
    "BinanceResponseException",
    "BinanceTimeoutException",
    "BinanceWebSocketException",
    
    # Models
    "BookTicker",
    "OHLCV",
    "OrderBook",
    "OrderBookEntry",
    "Ticker",
    "Trade",
] 