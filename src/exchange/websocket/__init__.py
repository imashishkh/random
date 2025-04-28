"""
WebSocket module for real-time cryptocurrency exchange data.

This module provides WebSocket clients for connecting to cryptocurrency
exchanges and processing real-time market data and user updates.
"""

__version__ = "0.1.0"

# Export main classes for easier imports
from .base import BaseWebSocketClient
from .binance import BinanceWebSocketClient
from .ftx import FTXWebSocketClient

__all__ = ["BaseWebSocketClient", "BinanceWebSocketClient", "FTXWebSocketClient"] 