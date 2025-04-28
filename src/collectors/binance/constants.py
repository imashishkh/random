"""
Binance API constants.

This module contains constants for Binance API endpoints and configurations.
"""

# Base URLs
REST_API_URL = "https://api.binance.com"
TESTNET_API_URL = "https://testnet.binance.vision"
WS_API_URL = "wss://stream.binance.com:9443/ws"
WS_API_COMBINED_URL = "wss://stream.binance.com:9443/stream"

# REST API endpoints
# Public endpoints
PING = "/api/v3/ping"
SERVER_TIME = "/api/v3/time"
EXCHANGE_INFO = "/api/v3/exchangeInfo"
DEPTH = "/api/v3/depth"
TRADES = "/api/v3/trades"
HISTORICAL_TRADES = "/api/v3/historicalTrades"
AGG_TRADES = "/api/v3/aggTrades"
KLINES = "/api/v3/klines"
AVG_PRICE = "/api/v3/avgPrice"
TICKER_24HR = "/api/v3/ticker/24hr"
TICKER_PRICE = "/api/v3/ticker/price"
TICKER_BOOK = "/api/v3/ticker/bookTicker"

# Authenticated endpoints
ACCOUNT = "/api/v3/account"
MY_TRADES = "/api/v3/myTrades"
USER_DATA_STREAM = "/api/v3/userDataStream"

# Timeframes (intervals)
INTERVALS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
    "1M": 2592000,
}

# Rate limit settings
DEFAULT_WEIGHT_LIMIT = 1200  # per minute
DEFAULT_ORDERS_LIMIT = 10    # per second
DEFAULT_RAW_REQUESTS_LIMIT = 6000  # per 5 minutes

# WebSocket stream types
STREAM_TYPES = {
    "TRADE": "@trade",
    "KLINE": "@kline_",
    "DEPTH": "@depth",
    "BOOK_TICKER": "@bookTicker",
    "AGG_TRADE": "@aggTrade",
    "MINI_TICKER": "@miniTicker",
    "TICKER": "@ticker",
}

# Error codes and messages
ERROR_CODES = {
    429: "Rate limit exceeded",
    418: "IP banned for rate limit violation",
    403: "WAF (Web Application Firewall) Limit",
    400: "Bad request",
    401: "Unauthorized",
    404: "Not found",
    500: "Internal server error",
    503: "Service unavailable",
}

# Specific Binance error codes
BINANCE_ERROR_CODES = {
    -1000: "UNKNOWN",
    -1001: "DISCONNECTED",
    -1002: "UNAUTHORIZED",
    -1003: "TOO_MANY_REQUESTS",
    -1004: "SERVER_BUSY",
    -1005: "UNEXPECTED_RESP",
    -1006: "TIMEOUT",
    -1007: "INVALID_RESPONSE",
    -1010: "ERROR_MSG_RECEIVED",
    -1013: "INVALID_ORDER_COMPOSITION",
    -1014: "UNSUPPORTED_ORDER_COMBINATION",
    -1015: "TOO_MANY_ORDERS",
    -1016: "SERVICE_SHUTTING_DOWN",
    -1020: "UNSUPPORTED_OPERATION",
    -1021: "INVALID_TIMESTAMP",
    -1022: "INVALID_SIGNATURE",
    -1100: "ILLEGAL_CHARS",
    -1101: "TOO_MANY_PARAMETERS",
    -1102: "MANDATORY_PARAM_EMPTY_OR_MALFORMED",
    -1103: "UNKNOWN_PARAM",
    -1104: "UNREAD_PARAMETERS",
    -1105: "PARAM_EMPTY",
    -1106: "PARAM_NOT_REQUIRED",
    -1111: "BAD_PRECISION",
    -1112: "NO_DEPTH",
    -1114: "TIF_NOT_REQUIRED",
    -1115: "INVALID_TIF",
    -1116: "INVALID_ORDER_TYPE",
    -1117: "INVALID_SIDE",
    -1118: "EMPTY_NEW_CL_ORD_ID",
    -1119: "EMPTY_ORG_CL_ORD_ID",
    -1120: "BAD_INTERVAL",
    -1121: "BAD_SYMBOL",
    -1122: "INVALID_LISTEN_KEY",
    -1125: "INVALID_LIST_INTERVAL",
    -1127: "LOOKUP_INTERVAL_INVALID",
    -1131: "BAD_RECV_WINDOW",
    -2010: "NEW_ORDER_REJECTED",
    -2011: "CANCEL_REJECTED",
    -2013: "NO_SUCH_ORDER",
    -2014: "BAD_API_KEY_FMT",
    -2015: "INVALID_API_KEY",
}

# Retry-able errors
RETRY_ERRORS = [
    -1001,  # DISCONNECTED
    -1003,  # TOO_MANY_REQUESTS
    -1004,  # SERVER_BUSY
    -1006,  # TIMEOUT
    -1007,  # INVALID_RESPONSE
    -1016,  # SERVICE_SHUTTING_DOWN
    -1021,  # INVALID_TIMESTAMP (can happen if time is not synced)
]

# Retry-able HTTP status codes
RETRY_HTTP_CODES = [
    429,  # Too many requests
    500,  # Internal server error
    502,  # Bad gateway
    503,  # Service unavailable
    504,  # Gateway timeout
]

# Websocket connection settings
WS_PING_INTERVAL = 30  # seconds
WS_TIMEOUT = 10        # seconds
WS_RECONNECT_DELAY = 5 # seconds 