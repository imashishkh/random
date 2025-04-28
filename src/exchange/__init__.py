"""
Exchange module for handling cryptocurrency exchange integrations.
"""

__version__ = "0.1.0"

# Import for easy access
from .binance import BinanceClient
from .binance_api_client import BinanceApiClient
from .rate_limiter import RateLimiter
from .exceptions import (
    ExchangeError, AuthenticationError, RateLimitError,
    InsufficientFundsError, InvalidOrderError, CircuitBreakerError,
    NetworkError, ServerError, TimeoutError, ExchangeOperationError,
    SymbolNotFoundError, ExchangeMaintenanceError, WebSocketError
)
from .websocket import BinanceWebSocketClient, FTXWebSocketClient

# Export for convenience
__all__ = [
    "BinanceClient",
    "BinanceApiClient",
    "BinanceWebSocketClient",
    "FTXWebSocketClient",
    "RateLimiter",
    "ExchangeError",
    "AuthenticationError",
    "RateLimitError",
    "InsufficientFundsError",
    "InvalidOrderError",
    "CircuitBreakerError",
    "NetworkError",
    "ServerError",
    "TimeoutError",
    "ExchangeOperationError",
    "SymbolNotFoundError",
    "ExchangeMaintenanceError",
    "WebSocketError"
] 