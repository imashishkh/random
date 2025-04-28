"""
Market data utility functions.

This module contains utility functions for the market data module,
including normalizing data formats and generating cache keys.
"""

from typing import Dict, List, Any, Optional
import time
import hashlib
import json

# Cache TTL values (in seconds)
CACHE_TTL_TICKER = 10
CACHE_TTL_ORDERBOOK = 5
CACHE_TTL_OHLCV = {
    '1m': 60,  # 1 minute
    '5m': 300,  # 5 minutes
    '15m': 900,  # 15 minutes
    '30m': 1800,  # 30 minutes
    '1h': 3600,  # 1 hour
    '2h': 7200,  # 2 hours
    '4h': 14400,  # 4 hours
    '12h': 43200,  # 12 hours
    '1d': 86400,  # 1 day
    '3d': 259200,  # 3 days
    '1w': 604800,  # 1 week
}
CACHE_TTL_MARKETS = 3600
CACHE_TTL_EXCHANGE_INFO = 3600

# Timeframe constants
TIMEFRAME_1M = '1m'
TIMEFRAME_5M = '5m'
TIMEFRAME_15M = '15m'
TIMEFRAME_30M = '30m'
TIMEFRAME_1H = '1h'
TIMEFRAME_4H = '4h'
TIMEFRAME_1D = '1d'
TIMEFRAME_1W = '1w'

# Supported timeframes
BINANCE_TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M']

def normalize_symbol(symbol: str) -> str:
    """
    Normalize a trading pair symbol to a standard format.
    
    Args:
        symbol: Trading pair symbol (e.g., 'BTC/USDT', 'BTCUSDT', 'btc_usdt')
        
    Returns:
        Normalized symbol string (e.g., 'BTC/USDT')
    """
    # Remove any whitespace
    symbol = symbol.strip()
    
    # If already in ccxt format (contains '/'), return as is
    if '/' in symbol:
        return symbol.upper()
    
    # Handle underscore format (e.g., 'btc_usdt')
    if '_' in symbol:
        base, quote = symbol.split('_', 1)
        return f"{base.upper()}/{quote.upper()}"
    
    # Handle direct format (e.g., 'BTCUSDT')
    # Common quote currencies in order of matching priority
    quote_currencies = ['USDT', 'BUSD', 'USDC', 'BTC', 'ETH', 'BNB', 'USD', 'EUR']
    
    symbol = symbol.upper()
    for quote in quote_currencies:
        if symbol.endswith(quote):
            base = symbol[:-len(quote)]
            return f"{base}/{quote}"
    
    # If we can't determine the format, return as is with a warning
    # Default to assuming last 4 characters are the quote currency
    if len(symbol) > 4:
        base = symbol[:-4]
        quote = symbol[-4:]
        return f"{base}/{quote}"
    
    # Fallback - just return the original symbol
    return symbol

def normalize_ticker(ticker: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize ticker data to a standard format.
    
    Args:
        ticker: Raw ticker data from the exchange
        
    Returns:
        Normalized ticker dictionary
    """
    # Extract the common fields we want to normalize
    return {
        'symbol': ticker['symbol'],
        'timestamp': ticker['timestamp'],
        'datetime': ticker['datetime'],
        'high': ticker['high'],
        'low': ticker['low'],
        'bid': ticker['bid'],
        'ask': ticker['ask'],
        'last': ticker['last'],
        'open': ticker['open'],
        'close': ticker['close'],
        'baseVolume': ticker['baseVolume'],
        'quoteVolume': ticker['quoteVolume'],
        'change': ticker.get('change', None),
        'percentage': ticker.get('percentage', None),
        'average': ticker.get('average', None),
        'vwap': ticker.get('vwap', None),
        'raw': ticker  # Include the raw data for reference
    }

def normalize_order_book(order_book: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize order book data to a standard format.
    
    Args:
        order_book: Raw order book data from the exchange
        
    Returns:
        Normalized order book dictionary
    """
    return {
        'symbol': order_book.get('symbol', ''),
        'timestamp': order_book['timestamp'],
        'datetime': order_book.get('datetime', ''),
        'nonce': order_book.get('nonce', None),
        'bids': [[price, amount] for price, amount in order_book['bids']],
        'asks': [[price, amount] for price, amount in order_book['asks']],
        'raw': order_book  # Include the raw data for reference
    }

def normalize_ohlcv(ohlcv_data: List[List[Any]]) -> List[Dict[str, Any]]:
    """
    Normalize OHLCV (candle) data to a standard format.
    
    Args:
        ohlcv_data: Raw OHLCV data from the exchange
        
    Returns:
        List of normalized OHLCV dictionaries
    """
    normalized_data = []
    
    for candle in ohlcv_data:
        # CCXT OHLCV format: [timestamp, open, high, low, close, volume]
        timestamp, open_price, high, low, close, volume = candle
        
        normalized_data.append({
            'timestamp': timestamp,
            'datetime': time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(timestamp / 1000)),
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })
    
    return normalized_data

def normalize_markets(markets: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize markets data to a standard format.
    
    Args:
        markets: Raw markets data from the exchange
        
    Returns:
        Dictionary of normalized market data
    """
    normalized_markets = {}
    
    for symbol, market in markets.items():
        normalized_markets[symbol] = {
            'symbol': market['symbol'],
            'base': market['base'],
            'quote': market['quote'],
            'active': market.get('active', True),
            'precision': {
                'price': market.get('precision', {}).get('price', None),
                'amount': market.get('precision', {}).get('amount', None),
            },
            'limits': {
                'amount': {
                    'min': market.get('limits', {}).get('amount', {}).get('min', None),
                    'max': market.get('limits', {}).get('amount', {}).get('max', None),
                },
                'price': {
                    'min': market.get('limits', {}).get('price', {}).get('min', None),
                    'max': market.get('limits', {}).get('price', {}).get('max', None),
                },
                'cost': {
                    'min': market.get('limits', {}).get('cost', {}).get('min', None),
                    'max': market.get('limits', {}).get('cost', {}).get('max', None),
                },
            },
            'info': market.get('info', {}),
        }
    
    return normalized_markets

def get_cache_key(exchange: str, symbol: str, data_type: str, params: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate a unique cache key for market data.
    
    Args:
        exchange: Exchange name (e.g., 'binance')
        symbol: Trading pair symbol (e.g., 'BTC/USDT')
        data_type: Type of data (e.g., 'ticker', 'orderbook', 'ohlcv')
        params: Additional parameters to include in the key
        
    Returns:
        Cache key string
    """
    key_parts = [exchange.lower(), symbol.upper(), data_type.lower()]
    
    # Add params if provided
    if params:
        # Sort params to ensure consistent key generation
        sorted_params = sorted(params.items())
        for k, v in sorted_params:
            key_parts.append(f"{k}:{v}")
    
    # Join with underscores and create a hash for long keys
    key = '_'.join(str(part) for part in key_parts)
    
    # If key is too long, hash it
    if len(key) > 200:
        key_hash = hashlib.md5(key.encode()).hexdigest()
        key = f"{exchange.lower()}_{symbol.upper()}_{data_type.lower()}_{key_hash}"
    
    return key 