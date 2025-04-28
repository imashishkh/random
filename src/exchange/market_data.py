"""
Market data handling module for cryptocurrency exchanges.

This module contains utility functions for processing, transforming, and normalizing
market data retrieved from various exchange APIs.
"""
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
import time

# Configure logger
logger = logging.getLogger(__name__)

# ===== Timeframe constants =====
TIMEFRAME_1M = "1m"   # 1 minute
TIMEFRAME_3M = "3m"   # 3 minutes
TIMEFRAME_5M = "5m"   # 5 minutes
TIMEFRAME_15M = "15m" # 15 minutes
TIMEFRAME_30M = "30m" # 30 minutes
TIMEFRAME_1H = "1h"   # 1 hour
TIMEFRAME_2H = "2h"   # 2 hours
TIMEFRAME_4H = "4h"   # 4 hours
TIMEFRAME_6H = "6h"   # 6 hours
TIMEFRAME_8H = "8h"   # 8 hours
TIMEFRAME_12H = "12h" # 12 hours
TIMEFRAME_1D = "1d"   # 1 day
TIMEFRAME_3D = "3d"   # 3 days
TIMEFRAME_1W = "1w"   # 1 week
TIMEFRAME_1M_CAPITAL = "1M" # 1 month

# Binance specific timeframes
BINANCE_TIMEFRAMES = [
    TIMEFRAME_1M, TIMEFRAME_3M, TIMEFRAME_5M, TIMEFRAME_15M, TIMEFRAME_30M,
    TIMEFRAME_1H, TIMEFRAME_2H, TIMEFRAME_4H, TIMEFRAME_6H, TIMEFRAME_8H, 
    TIMEFRAME_12H, TIMEFRAME_1D, TIMEFRAME_3D, TIMEFRAME_1W, TIMEFRAME_1M_CAPITAL
]

# Cache TTL for different market data types (in seconds)
CACHE_TTL_TICKER = 5  # 5 seconds for ticker data
CACHE_TTL_ORDERBOOK = 5  # 5 seconds for order book data
CACHE_TTL_OHLCV = {
    TIMEFRAME_1M: 60,         # 1 minute
    TIMEFRAME_3M: 180,        # 3 minutes
    TIMEFRAME_5M: 300,        # 5 minutes
    TIMEFRAME_15M: 900,       # 15 minutes
    TIMEFRAME_30M: 1800,      # 30 minutes
    TIMEFRAME_1H: 3600,       # 1 hour
    TIMEFRAME_2H: 7200,       # 2 hours
    TIMEFRAME_4H: 14400,      # 4 hours
    TIMEFRAME_6H: 21600,      # 6 hours
    TIMEFRAME_8H: 28800,      # 8 hours
    TIMEFRAME_12H: 43200,     # 12 hours
    TIMEFRAME_1D: 86400,      # 1 day
    TIMEFRAME_3D: 259200,     # 3 days
    TIMEFRAME_1W: 604800,     # 1 week
    TIMEFRAME_1M_CAPITAL: 2592000,  # 1 month (30 days)
}
CACHE_TTL_MARKETS = 3600  # 1 hour for markets data
CACHE_TTL_EXCHANGE_INFO = 3600  # 1 hour for exchange information

def normalize_symbol(symbol: str) -> str:
    """
    Normalize a trading symbol to a standard format.
    
    Args:
        symbol: Trading pair symbol (e.g., 'btcusdt', 'BTC-USDT', 'BTC/USDT')
        
    Returns:
        Normalized symbol in the format 'BTC/USDT'
    """
    # Remove any spaces
    symbol = symbol.strip().upper()
    
    # Handle different separators
    if '/' in symbol:
        return symbol
    elif '-' in symbol:
        return symbol.replace('-', '/')
    elif '_' in symbol:
        return symbol.replace('_', '/')
    else:
        # For symbols without separators (e.g., 'BTCUSDT'), try to identify base/quote
        # This is a simple approach and might not work for all symbols
        common_quote_currencies = ['USDT', 'USD', 'BTC', 'ETH', 'BNB']
        for quote in common_quote_currencies:
            if symbol.endswith(quote):
                base = symbol[:-len(quote)]
                return f"{base}/{quote}"
        
        # If we can't identify the format, return as is
        return symbol

def normalize_ohlcv(ohlcv_data: List[List[Any]]) -> List[Dict[str, Any]]:
    """
    Normalize OHLCV (candle) data to a standardized format.
    
    Args:
        ohlcv_data: Raw OHLCV data from an exchange
        
    Returns:
        List of dictionaries with normalized OHLCV data
    """
    normalized_data = []
    
    for candle in ohlcv_data:
        # CCXT standard format: [timestamp, open, high, low, close, volume]
        if len(candle) >= 6:
            normalized_candle = {
                'timestamp': candle[0],
                'datetime': datetime.fromtimestamp(candle[0] / 1000.0).isoformat(),
                'open': float(candle[1]),
                'high': float(candle[2]),
                'low': float(candle[3]),
                'close': float(candle[4]),
                'volume': float(candle[5])
            }
            
            normalized_data.append(normalized_candle)
    
    return normalized_data

def normalize_order_book(order_book: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize order book data to a standardized format.
    
    Args:
        order_book: Raw order book data from an exchange
        
    Returns:
        Dictionary with normalized order book data
    """
    if not order_book or 'bids' not in order_book or 'asks' not in order_book:
        return {'bids': [], 'asks': [], 'timestamp': int(time.time() * 1000)}
    
    normalized_bids = []
    for bid in order_book.get('bids', []):
        if len(bid) >= 2:
            # Format: [price, amount]
            normalized_bids.append([float(bid[0]), float(bid[1])])
    
    normalized_asks = []
    for ask in order_book.get('asks', []):
        if len(ask) >= 2:
            # Format: [price, amount]
            normalized_asks.append([float(ask[0]), float(ask[1])])
    
    # Sort bids in descending order (highest price first)
    normalized_bids.sort(key=lambda x: x[0], reverse=True)
    
    # Sort asks in ascending order (lowest price first)
    normalized_asks.sort(key=lambda x: x[0])
    
    return {
        'bids': normalized_bids,
        'asks': normalized_asks,
        'timestamp': order_book.get('timestamp', int(time.time() * 1000)),
        'datetime': datetime.fromtimestamp(
            order_book.get('timestamp', int(time.time() * 1000)) / 1000.0
        ).isoformat() if order_book.get('timestamp') else datetime.now().isoformat(),
        'nonce': order_book.get('nonce')
    }

def normalize_ticker(ticker: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize ticker data to a standardized format.
    
    Args:
        ticker: Raw ticker data from an exchange
        
    Returns:
        Dictionary with normalized ticker data
    """
    if not ticker:
        return {}
    
    # Extract relevant fields, providing defaults for missing ones
    normalized_ticker = {
        'symbol': ticker.get('symbol', ''),
        'timestamp': ticker.get('timestamp', int(time.time() * 1000)),
        'datetime': ticker.get('datetime', datetime.now().isoformat()),
        'high': float(ticker.get('high', 0)) if ticker.get('high') is not None else None,
        'low': float(ticker.get('low', 0)) if ticker.get('low') is not None else None,
        'bid': float(ticker.get('bid', 0)) if ticker.get('bid') is not None else None,
        'ask': float(ticker.get('ask', 0)) if ticker.get('ask') is not None else None,
        'last': float(ticker.get('last', 0)) if ticker.get('last') is not None else None,
        'close': float(ticker.get('close', ticker.get('last', 0))) if ticker.get('close') or ticker.get('last') else None,
        'baseVolume': float(ticker.get('baseVolume', 0)) if ticker.get('baseVolume') is not None else None,
        'quoteVolume': float(ticker.get('quoteVolume', 0)) if ticker.get('quoteVolume') is not None else None,
        'info': ticker.get('info', {})
    }
    
    # Calculate percentage change if available
    if ticker.get('open') is not None and ticker.get('close') is not None:
        open_price = float(ticker['open'])
        close_price = float(ticker['close'])
        
        if open_price > 0:
            percentage_change = ((close_price - open_price) / open_price) * 100
            normalized_ticker['percentage'] = round(percentage_change, 2)
    
    return normalized_ticker

def normalize_markets(markets: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Normalize market data to a standardized format.
    
    Args:
        markets: Raw market data from an exchange
        
    Returns:
        Dictionary with normalized market data
    """
    normalized_markets = {}
    
    for symbol, market in markets.items():
        # Skip non-spot markets if the 'spot' field exists and is False
        if 'spot' in market and market['spot'] is False:
            continue

        normalized_market = {
            'id': market.get('id', ''),
            'symbol': market.get('symbol', ''),
            'base': market.get('base', ''),
            'quote': market.get('quote', ''),
            'baseId': market.get('baseId', ''),
            'quoteId': market.get('quoteId', ''),
            'active': market.get('active', False),
            'precision': {
                'price': market.get('precision', {}).get('price', 0),
                'amount': market.get('precision', {}).get('amount', 0),
                'cost': market.get('precision', {}).get('cost', 0)
            },
            'limits': {
                'amount': {
                    'min': market.get('limits', {}).get('amount', {}).get('min', 0),
                    'max': market.get('limits', {}).get('amount', {}).get('max', None)
                },
                'price': {
                    'min': market.get('limits', {}).get('price', {}).get('min', 0),
                    'max': market.get('limits', {}).get('price', {}).get('max', None)
                },
                'cost': {
                    'min': market.get('limits', {}).get('cost', {}).get('min', 0),
                    'max': market.get('limits', {}).get('cost', {}).get('max', None)
                }
            },
            'info': market.get('info', {})
        }
        
        normalized_markets[symbol] = normalized_market
    
    return normalized_markets

def get_timeframe_duration_seconds(timeframe: str) -> int:
    """
    Get the duration of a timeframe in seconds.
    
    Args:
        timeframe: Timeframe string (e.g., '1m', '1h', '1d')
        
    Returns:
        Duration in seconds
    """
    unit = timeframe[-1].lower()
    value = int(timeframe[:-1])
    
    if unit == 'm':
        return value * 60
    elif unit == 'h':
        return value * 60 * 60
    elif unit == 'd':
        return value * 24 * 60 * 60
    elif unit == 'w':
        return value * 7 * 24 * 60 * 60
    elif unit == 'M':
        return value * 30 * 24 * 60 * 60  # Approximation
    else:
        raise ValueError(f"Unsupported timeframe unit: {unit}")

def get_cache_key(exchange: str, symbol: str, endpoint: str, params: dict = None) -> str:
    """
    Generate a cache key for market data.
    
    Args:
        exchange: Exchange name
        symbol: Trading pair symbol
        endpoint: API endpoint or data type
        params: Additional parameters
        
    Returns:
        Cache key string
    """
    # Normalize symbol
    normalized_symbol = normalize_symbol(symbol)
    
    # Base cache key
    cache_key = f"market:{exchange.lower()}:{normalized_symbol}:{endpoint}"
    
    # Add parameters to the cache key if provided
    if params:
        # Sort parameters by key to ensure consistent cache keys
        sorted_params = sorted(params.items())
        param_str = "_".join([f"{k}={v}" for k, v in sorted_params])
        cache_key = f"{cache_key}:{param_str}"
    
    return cache_key 