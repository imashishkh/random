"""
Binance exchange implementation using ccxt.
"""
import os
import time
import logging
import functools
from typing import Dict, List, Any, Optional, Tuple, Callable, Union
from datetime import datetime
import ccxt
import uuid

from .base import BaseExchange
from .market_data import (
    normalize_symbol, normalize_ohlcv, normalize_order_book, 
    normalize_ticker, normalize_markets, get_cache_key,
    BINANCE_TIMEFRAMES, CACHE_TTL_TICKER, CACHE_TTL_ORDERBOOK, 
    CACHE_TTL_OHLCV, CACHE_TTL_MARKETS, CACHE_TTL_EXCHANGE_INFO,
    TIMEFRAME_1H  # Default timeframe
)
from ..cache.redis_client import get_cache, set_cache

# Configure logger
logger = logging.getLogger(__name__)

def retry(max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 10.0):
    """
    Retry decorator with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay in seconds between retries
        max_delay: Maximum delay in seconds between retries
    
    Returns:
        Decorator function
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except (ccxt.NetworkError, ccxt.RequestTimeout) as e:
                    last_exception = e
                    if attempt < max_attempts:
                        # Calculate delay with exponential backoff
                        delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                        logger.warning(f"Attempt {attempt} failed with {str(e)}, retrying in {delay:.2f} seconds...")
                        time.sleep(delay)
                    else:
                        logger.error(f"All {max_attempts} attempts failed. Last error: {str(e)}")
                except Exception as e:
                    # Don't retry other exceptions
                    raise e
            
            # If we've exhausted all retries, raise the last exception
            if last_exception:
                raise last_exception
        return wrapper
    return decorator

class BinanceClient(BaseExchange):
    """Binance exchange client implementation."""
    
    def __init__(self, 
                 api_key: Optional[str] = None, 
                 api_secret: Optional[str] = None,
                 testnet: bool = False,
                 timeout: int = 30000,
                 enable_rate_limit: bool = True,
                 max_retries: int = 3):
        """
        Initialize the Binance client.
        
        Args:
            api_key: Binance API key (defaults to BINANCE_API_KEY env var)
            api_secret: Binance API secret (defaults to BINANCE_API_SECRET env var)
            testnet: Whether to use the testnet
            timeout: Request timeout in milliseconds
            enable_rate_limit: Whether to enable rate limiting
            max_retries: Maximum number of retries for API calls
        """
        # Load API credentials from environment if not provided
        self.api_key = api_key or os.environ.get('BINANCE_API_KEY')
        self.api_secret = api_secret or os.environ.get('BINANCE_API_SECRET')
        self.testnet = testnet
        self.max_retries = max_retries
        
        # Initialize base class
        super().__init__(
            api_key=self.api_key,
            api_secret=self.api_secret,
            timeout=timeout,
            enable_rate_limit=enable_rate_limit
        )
        
        # Initialize the client
        self.initialize()
    
    def _get_exchange_name(self) -> str:
        """Return the name of the exchange."""
        return "Binance"
    
    def initialize(self) -> None:
        """Initialize the Binance client with configured parameters."""
        try:
            # Define ccxt client options
            options = {
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'timeout': self.timeout,
                'enableRateLimit': self.enable_rate_limit,
                'options': {
                    'defaultType': 'spot',
                    'adjustForTimeDifference': True,
                    'recvWindow': 5000
                }
            }
            
            # Use testnet if specified
            if self.testnet:
                options['urls'] = {
                    'api': {
                        'public': 'https://testnet.binance.vision/api/v3',
                        'private': 'https://testnet.binance.vision/api/v3',
                    }
                }
            
            # Initialize ccxt Binance client
            self.client = ccxt.binance(options)
            
            # Load markets to cache available symbols
            self.client.load_markets()
            
            logger.info(f"Initialized Binance client: {'testnet' if self.testnet else 'mainnet'}")
        except Exception as e:
            logger.error(f"Failed to initialize Binance client: {str(e)}")
            raise
    
    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test the connection to Binance.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            # Use a simple API call to test connectivity
            result = self.client.fetch_time()
            time_diff = abs(result - int(time.time() * 1000))
            
            # Check if time difference is reasonable (less than 10 seconds)
            if time_diff < 10000:
                return True, f"Connected to Binance. Server time sync: {time_diff}ms difference"
            else:
                return False, f"Connected to Binance but time sync issue detected: {time_diff}ms difference"
        
        except ccxt.AuthenticationError as e:
            logger.error(f"Binance authentication error: {str(e)}")
            return False, f"Authentication error: {str(e)}"
        
        except (ccxt.NetworkError, ccxt.RequestTimeout) as e:
            logger.error(f"Binance network error: {str(e)}")
            raise  # This will be retried by the decorator
        
        except ccxt.ExchangeError as e:
            logger.error(f"Binance exchange error: {str(e)}")
            return False, f"Exchange error: {str(e)}"
        
        except Exception as e:
            logger.error(f"Binance test connection failed with unexpected error: {str(e)}")
            return False, f"Unexpected error: {str(e)}"
    
    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def get_markets(self) -> Dict[str, Any]:
        """
        Get the markets available on Binance.
        
        Returns:
            Dictionary of market data
        """
        try:
            # Check cache first
            cache_key = get_cache_key("binance", "ALL", "markets")
            cached_data = get_cache(cache_key)
            
            if cached_data:
                logger.debug("Retrieved markets from cache")
                return cached_data
            
            # Fetch from API if not in cache
            markets = self.client.markets
            
            # Normalize the data
            normalized_markets = normalize_markets(markets)
            
            # Cache the normalized data
            set_cache(cache_key, normalized_markets, CACHE_TTL_MARKETS)
            
            return normalized_markets
        except Exception as e:
            return self.handle_error(e)
    
    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get the ticker for a specific symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            
        Returns:
            Dictionary with ticker data
        """
        try:
            # Normalize the symbol
            symbol = normalize_symbol(symbol)
            
            # Check cache first
            cache_key = get_cache_key("binance", symbol, "ticker")
            cached_data = get_cache(cache_key)
            
            if cached_data:
                logger.debug(f"Retrieved ticker for {symbol} from cache")
                return cached_data
            
            # Fetch from API if not in cache
            ticker = self.client.fetch_ticker(symbol)
            
            # Normalize the data
            normalized_ticker = normalize_ticker(ticker)
            
            # Cache the normalized data
            set_cache(cache_key, normalized_ticker, CACHE_TTL_TICKER)
            
            return normalized_ticker
        except Exception as e:
            return self.handle_error(e)
    
    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def get_tickers(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """
        Get tickers for multiple symbols.
        
        Args:
            symbols: List of symbol strings (e.g., ['BTC/USDT', 'ETH/USDT'])
                    If None, get tickers for all available symbols
            
        Returns:
            Dictionary of symbol to ticker data
        """
        try:
            # If symbols are provided, normalize them
            normalized_symbols = [normalize_symbol(s) for s in symbols] if symbols else None
            
            # Check cache first for 'all tickers' request
            cache_key = get_cache_key("binance", "ALL", "tickers")
            cached_data = get_cache(cache_key)
            
            if cached_data and not symbols:
                logger.debug("Retrieved all tickers from cache")
                return cached_data
            
            # Fetch from API if not in cache
            tickers = self.client.fetch_tickers(normalized_symbols)
            
            # Normalize each ticker
            normalized_tickers = {}
            for symbol, ticker in tickers.items():
                normalized_tickers[symbol] = normalize_ticker(ticker)
            
            # Cache the normalized data (only if fetching all tickers)
            if not symbols:
                set_cache(cache_key, normalized_tickers, CACHE_TTL_TICKER)
            
            # If specific symbols were requested, filter the results
            if symbols:
                return {s: normalized_tickers[s] for s in normalized_symbols if s in normalized_tickers}
            
            return normalized_tickers
        except Exception as e:
            logger.error(f"Error fetching tickers: {str(e)}")
            return self.handle_error(e)
    
    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def get_order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """
        Get the order book for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            limit: Number of entries to return (max: 5000 for Binance)
            
        Returns:
            Dictionary with order book data
        """
        try:
            # Normalize the symbol
            symbol = normalize_symbol(symbol)
            
            # Check cache first
            cache_key = get_cache_key("binance", symbol, "orderbook", {"limit": limit})
            cached_data = get_cache(cache_key)
            
            if cached_data:
                logger.debug(f"Retrieved order book for {symbol} from cache")
                return cached_data
            
            # Fetch from API if not in cache
            order_book = self.client.fetch_order_book(symbol, limit)
            
            # Normalize the data
            normalized_order_book = normalize_order_book(order_book)
            
            # Cache the normalized data
            set_cache(cache_key, normalized_order_book, CACHE_TTL_ORDERBOOK)
            
            return normalized_order_book
        except Exception as e:
            logger.error(f"Error fetching order book for {symbol}: {str(e)}")
            return self.handle_error(e)
    
    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def get_historical_ohlcv(
        self, 
        symbol: str, 
        timeframe: str = TIMEFRAME_1H, 
        since: Optional[int] = None, 
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLCV (candle) data.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            timeframe: Timeframe string (e.g., '1m', '1h', '1d')
            since: Timestamp in milliseconds to fetch data from
            limit: Number of candles to return
            
        Returns:
            List of candle dictionaries
        """
        try:
            # Validate timeframe
            if timeframe not in BINANCE_TIMEFRAMES:
                raise ValueError(f"Invalid timeframe: {timeframe}. Supported timeframes: {', '.join(BINANCE_TIMEFRAMES)}")
            
            # Normalize the symbol
            symbol = normalize_symbol(symbol)
            
            # Build cache parameters
            cache_params = {"timeframe": timeframe}
            if since:
                cache_params["since"] = since
            if limit:
                cache_params["limit"] = limit
            
            # Check cache first
            cache_key = get_cache_key("binance", symbol, "ohlcv", cache_params)
            cached_data = get_cache(cache_key)
            
            if cached_data:
                logger.debug(f"Retrieved OHLCV data for {symbol} from cache")
                return cached_data
            
            # Fetch from API if not in cache
            ohlcv_data = self.client.fetch_ohlcv(symbol, timeframe, since, limit)
            
            # Normalize the data
            normalized_ohlcv_data = normalize_ohlcv(ohlcv_data)
            
            # Get the appropriate TTL for this timeframe
            ttl = CACHE_TTL_OHLCV.get(timeframe, 300)  # Default to 5 minutes if timeframe not found
            
            # Cache the normalized data
            set_cache(cache_key, normalized_ohlcv_data, ttl)
            
            return normalized_ohlcv_data
        except Exception as e:
            logger.error(f"Error fetching OHLCV data for {symbol}: {str(e)}")
            return self.handle_error(e)
    
    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def get_symbols(self) -> List[str]:
        """
        Get all available trading symbols.
        
        Returns:
            List of symbol strings
        """
        try:
            # Check cache first
            cache_key = get_cache_key("binance", "ALL", "symbols")
            cached_data = get_cache(cache_key)
            
            if cached_data:
                logger.debug("Retrieved symbols from cache")
                return cached_data
            
            # Fetch from API if not in cache
            markets = self.client.markets
            symbols = list(markets.keys())
            
            # Cache the data
            set_cache(cache_key, symbols, CACHE_TTL_MARKETS)
            
            return symbols
        except Exception as e:
            logger.error(f"Error fetching symbols: {str(e)}")
            return self.handle_error(e)
    
    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def get_exchange_info(self) -> Dict[str, Any]:
        """
        Get exchange information from Binance.
        
        Returns:
            Dictionary with exchange information
        """
        try:
            # Check cache first
            cache_key = get_cache_key("binance", "ALL", "exchange_info")
            cached_data = get_cache(cache_key)
            
            if cached_data:
                logger.debug("Retrieved exchange info from cache")
                return cached_data
            
            # Fetch from API if not in cache
            exchange_info = self.client.fetch_status()
            
            # Add additional exchange information
            if hasattr(self.client, 'sapiGetSystem'):
                # This is a Binance-specific endpoint
                try:
                    system_status = self.client.sapiGetSystem({'status': {}})
                    exchange_info['systemStatus'] = system_status
                except Exception as e:
                    logger.warning(f"Error fetching system status: {str(e)}")
            
            # Add exchange load and rate limits if available
            try:
                if hasattr(self.client, 'dapiGetExchangeInfo'):
                    exchange_load = self.client.dapiGetExchangeInfo()
                    exchange_info['exchangeInfo'] = exchange_load
            except Exception as e:
                logger.warning(f"Error fetching exchange load information: {str(e)}")
            
            # Cache the data
            set_cache(cache_key, exchange_info, CACHE_TTL_EXCHANGE_INFO)
            
            return exchange_info
        except Exception as e:
            logger.error(f"Error fetching exchange info: {str(e)}")
            return self.handle_error(e)
    
    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get detailed information for a specific symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            
        Returns:
            Dictionary with symbol information
        """
        try:
            # Normalize the symbol
            symbol = normalize_symbol(symbol)
            
            # Check cache first
            cache_key = get_cache_key("binance", symbol, "symbol_info")
            cached_data = get_cache(cache_key)
            
            if cached_data:
                logger.debug(f"Retrieved symbol info for {symbol} from cache")
                return cached_data
            
            # Fetch from API if not in cache
            markets = self.get_markets()
            
            if symbol not in markets:
                raise ValueError(f"Symbol not found: {symbol}")
            
            symbol_info = markets[symbol]
            
            # Cache the data
            set_cache(cache_key, symbol_info, CACHE_TTL_MARKETS)
            
            return symbol_info
        except Exception as e:
            logger.error(f"Error fetching symbol info for {symbol}: {str(e)}")
            return self.handle_error(e)
    
    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def get_balance(self) -> Dict[str, Any]:
        """
        Get account balance information.
        
        Returns:
            Dictionary with balance data
        """
        try:
            return self.client.fetch_balance()
        except Exception as e:
            return self.handle_error(e)
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current rate limit status.
        
        Returns:
            Dictionary with rate limit information
        """
        # Note: ccxt handles rate limits internally but doesn't expose the current status
        # Return a general status based on client's enableRateLimit setting
        return {
            "enabled": self.enable_rate_limit,
            "message": "Rate limiting is managed internally by ccxt"
        }
    
    # ======= Order Management Methods =======
    
    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def create_market_order(self, symbol: str, side: str, amount: float, params: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Create a market order.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            side: Order side ('buy' or 'sell')
            amount: Order amount
            params: Additional parameters for the order
            
        Returns:
            Dictionary with order information
        """
        try:
            # Normalize the symbol
            symbol = normalize_symbol(symbol)
            
            # Validate parameters
            if side.lower() not in ['buy', 'sell']:
                raise ValueError(f"Invalid side: {side}. Must be 'buy' or 'sell'.")
            
            if amount <= 0:
                raise ValueError(f"Invalid amount: {amount}. Must be > 0.")
            
            # Create a unique client order ID for tracking
            client_order_id = self.generate_client_order_id()
            order_params = {'clientOrderId': client_order_id, **params}
            
            # Place the market order
            order = self.client.create_order(
                symbol=symbol,
                type='market',
                side=side.lower(),
                amount=amount,
                params=order_params
            )
            
            logger.info(f"Created market {side} order for {amount} {symbol}")
            return order
        except Exception as e:
            logger.error(f"Error creating market order: {str(e)}")
            return self.handle_error(e)

    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def create_limit_order(self, symbol: str, side: str, amount: float, price: float, params: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Create a limit order.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            side: Order side ('buy' or 'sell')
            amount: Order amount
            price: Limit price
            params: Additional parameters for the order
            
        Returns:
            Dictionary with order information
        """
        try:
            # Normalize the symbol
            symbol = normalize_symbol(symbol)
            
            # Validate parameters
            if side.lower() not in ['buy', 'sell']:
                raise ValueError(f"Invalid side: {side}. Must be 'buy' or 'sell'.")
            
            if amount <= 0:
                raise ValueError(f"Invalid amount: {amount}. Must be > 0.")
            
            if price <= 0:
                raise ValueError(f"Invalid price: {price}. Must be > 0.")
            
            # Create a unique client order ID for tracking
            client_order_id = self.generate_client_order_id()
            order_params = {'clientOrderId': client_order_id, **params}
            
            # Place the limit order
            order = self.client.create_order(
                symbol=symbol,
                type='limit',
                side=side.lower(),
                amount=amount,
                price=price,
                params=order_params
            )
            
            logger.info(f"Created limit {side} order for {amount} {symbol} at {price}")
            return order
        except Exception as e:
            logger.error(f"Error creating limit order: {str(e)}")
            return self.handle_error(e)

    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def create_stop_loss_order(self, symbol: str, side: str, amount: float, 
                             stop_price: float, price: Optional[float] = None, 
                             params: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Create a stop-loss order.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            side: Order side ('buy' or 'sell')
            amount: Order amount
            stop_price: Trigger price
            price: Limit price (if None, creates a stop-market order)
            params: Additional parameters for the order
            
        Returns:
            Dictionary with order information
        """
        try:
            # Normalize the symbol
            symbol = normalize_symbol(symbol)
            
            # Validate parameters
            if side.lower() not in ['buy', 'sell']:
                raise ValueError(f"Invalid side: {side}. Must be 'buy' or 'sell'.")
            
            if amount <= 0:
                raise ValueError(f"Invalid amount: {amount}. Must be > 0.")
            
            if stop_price <= 0:
                raise ValueError(f"Invalid stop price: {stop_price}. Must be > 0.")
            
            # Create a unique client order ID for tracking
            client_order_id = self.generate_client_order_id()
            
            # Determine order type and parameters
            if price is not None:
                if price <= 0:
                    raise ValueError(f"Invalid price: {price}. Must be > 0.")
                
                # Stop-limit order
                order_type = 'STOP_LOSS_LIMIT'
                order_params = {
                    'clientOrderId': client_order_id,
                    'stopPrice': stop_price,
                    'timeInForce': 'GTC',  # Good Till Cancelled
                    **params
                }
                
                logger.info(f"Creating stop-limit {side} order for {amount} {symbol} at {price} (stop: {stop_price})")
            else:
                # Stop-market order
                order_type = 'STOP_LOSS'
                order_params = {
                    'clientOrderId': client_order_id,
                    'stopPrice': stop_price,
                    **params
                }
                price = None  # Ensure price is None for stop-market
                
                logger.info(f"Creating stop-market {side} order for {amount} {symbol} (stop: {stop_price})")
            
            # Place the stop order
            order = self.client.create_order(
                symbol=symbol,
                type=order_type,
                side=side.lower(),
                amount=amount,
                price=price,
                params=order_params
            )
            
            return order
        except Exception as e:
            logger.error(f"Error creating stop-loss order: {str(e)}")
            return self.handle_error(e)

    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def create_take_profit_order(self, symbol: str, side: str, amount: float, 
                               stop_price: float, price: Optional[float] = None, 
                               params: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Create a take-profit order.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            side: Order side ('buy' or 'sell')
            amount: Order amount
            stop_price: Trigger price
            price: Limit price (if None, creates a take-profit-market order)
            params: Additional parameters for the order
            
        Returns:
            Dictionary with order information
        """
        try:
            # Normalize the symbol
            symbol = normalize_symbol(symbol)
            
            # Validate parameters
            if side.lower() not in ['buy', 'sell']:
                raise ValueError(f"Invalid side: {side}. Must be 'buy' or 'sell'.")
            
            if amount <= 0:
                raise ValueError(f"Invalid amount: {amount}. Must be > 0.")
            
            if stop_price <= 0:
                raise ValueError(f"Invalid stop price: {stop_price}. Must be > 0.")
            
            # Create a unique client order ID for tracking
            client_order_id = self.generate_client_order_id()
            
            # Determine order type and parameters
            if price is not None:
                if price <= 0:
                    raise ValueError(f"Invalid price: {price}. Must be > 0.")
                
                # Take-profit-limit order
                order_type = 'TAKE_PROFIT_LIMIT'
                order_params = {
                    'clientOrderId': client_order_id,
                    'stopPrice': stop_price,
                    'timeInForce': 'GTC',  # Good Till Cancelled
                    **params
                }
                
                logger.info(f"Creating take-profit-limit {side} order for {amount} {symbol} at {price} (stop: {stop_price})")
            else:
                # Take-profit-market order
                order_type = 'TAKE_PROFIT'
                order_params = {
                    'clientOrderId': client_order_id,
                    'stopPrice': stop_price,
                    **params
                }
                price = None  # Ensure price is None for take-profit-market
                
                logger.info(f"Creating take-profit-market {side} order for {amount} {symbol} (stop: {stop_price})")
            
            # Place the take-profit order
            order = self.client.create_order(
                symbol=symbol,
                type=order_type,
                side=side.lower(),
                amount=amount,
                price=price,
                params=order_params
            )
            
            return order
        except Exception as e:
            logger.error(f"Error creating take-profit order: {str(e)}")
            return self.handle_error(e)

    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def create_trailing_stop_order(self, symbol: str, side: str, amount: float, 
                                 activation_price: float, callback_rate: float,
                                 params: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Create a trailing stop order.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            side: Order side ('buy' or 'sell')
            amount: Order amount
            activation_price: Price at which the trailing stop will be activated
            callback_rate: Percentage distance from the highest/lowest price (0.1 to 5 percent)
            params: Additional parameters for the order
            
        Returns:
            Dictionary with order information
        """
        try:
            # Normalize the symbol
            symbol = normalize_symbol(symbol)
            
            # Validate parameters
            if side.lower() not in ['buy', 'sell']:
                raise ValueError(f"Invalid side: {side}. Must be 'buy' or 'sell'.")
            
            if amount <= 0:
                raise ValueError(f"Invalid amount: {amount}. Must be > 0.")
            
            if activation_price <= 0:
                raise ValueError(f"Invalid activation price: {activation_price}. Must be > 0.")
            
            if callback_rate < 0.1 or callback_rate > 5:
                raise ValueError(f"Invalid callback rate: {callback_rate}. Must be between 0.1 and 5 percent.")
            
            # Create a unique client order ID for tracking
            client_order_id = self.generate_client_order_id()
            
            # Set up parameters for trailing stop
            order_params = {
                'clientOrderId': client_order_id,
                'activationPrice': activation_price,
                'callbackRate': callback_rate,
                **params
            }
            
            # Place trailing stop order
            order = self.client.create_order(
                symbol=symbol,
                type='TRAILING_STOP_MARKET',
                side=side.lower(),
                amount=amount,
                params=order_params
            )
            
            logger.info(f"Created trailing stop {side} order for {amount} {symbol} (activation: {activation_price}, callback: {callback_rate}%)")
            return order
        except Exception as e:
            logger.error(f"Error creating trailing stop order: {str(e)}")
            return self.handle_error(e)

    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def create_oco_order(self, symbol: str, side: str, amount: float, price: float, 
                       stop_price: float, stop_limit_price: Optional[float] = None, 
                       params: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Create an OCO (One-Cancels-the-Other) order.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            side: Order side ('buy' or 'sell')
            amount: Order amount
            price: Limit order price
            stop_price: Stop trigger price
            stop_limit_price: Stop-limit order price (if None, stop_price is used)
            params: Additional parameters for the order
            
        Returns:
            Dictionary with order information
        """
        try:
            # Normalize the symbol
            symbol = normalize_symbol(symbol)
            
            # Validate parameters
            if side.lower() not in ['buy', 'sell']:
                raise ValueError(f"Invalid side: {side}. Must be 'buy' or 'sell'.")
            
            if amount <= 0:
                raise ValueError(f"Invalid amount: {amount}. Must be > 0.")
            
            if price <= 0:
                raise ValueError(f"Invalid price: {price}. Must be > 0.")
            
            if stop_price <= 0:
                raise ValueError(f"Invalid stop price: {stop_price}. Must be > 0.")
            
            # Use stop_price as stop_limit_price if not provided
            if stop_limit_price is None:
                stop_limit_price = stop_price
            elif stop_limit_price <= 0:
                raise ValueError(f"Invalid stop limit price: {stop_limit_price}. Must be > 0.")
            
            # Create a unique client order ID for tracking
            client_order_id = self.generate_client_order_id()
            
            # Prepare OCO order parameters
            oco_params = {
                'clientOrderId': client_order_id,
                'stopPrice': stop_price,
                'stopLimitPrice': stop_limit_price,
                'stopLimitTimeInForce': 'GTC',  # Good Till Cancelled
                **params
            }
            
            # Check if the Binance exchange instance supports OCO orders directly
            if hasattr(self.client, 'create_order_oco'):
                # Use direct OCO order creation if available
                order = self.client.create_order_oco(
                    symbol=symbol,
                    side=side.lower(),
                    amount=amount,
                    price=price,
                    stopPrice=stop_price,
                    stopLimitPrice=stop_limit_price,
                    params=oco_params
                )
            else:
                # If not directly supported through ccxt, use Binance-specific endpoint
                if hasattr(self.client, 'privatePostOrderOco'):
                    # Format according to Binance API requirements
                    oco_request = {
                        'symbol': self.client.market_id(symbol),
                        'side': side.upper(),
                        'quantity': str(amount),
                        'price': str(price),
                        'stopPrice': str(stop_price),
                        'stopLimitPrice': str(stop_limit_price),
                        'stopLimitTimeInForce': 'GTC',
                        'newClientOrderId': client_order_id
                    }
                    # Merge any additional parameters
                    oco_request.update(params)
                    
                    # Make the API call
                    order = self.client.privatePostOrderOco(oco_request)
                else:
                    raise NotImplementedError("OCO orders are not supported for this exchange")
            
            logger.info(f"Created OCO {side} order for {amount} {symbol} (price: {price}, stop: {stop_price})")
            return order
        except Exception as e:
            logger.error(f"Error creating OCO order: {str(e)}")
            return self.handle_error(e)

    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def cancel_order(self, order_id: str, symbol: str, params: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Cancel an existing order.
        
        Args:
            order_id: Order ID to cancel
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            params: Additional parameters for the cancellation
            
        Returns:
            Dictionary with cancellation information
        """
        try:
            # Normalize the symbol
            symbol = normalize_symbol(symbol)
            
            # Cancel the order
            result = self.client.cancel_order(order_id, symbol, params)
            
            logger.info(f"Cancelled order {order_id} for {symbol}")
            return result
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {str(e)}")
            return self.handle_error(e)

    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def cancel_all_orders(self, symbol: Optional[str] = None, params: Dict[str, Any] = {}) -> List[Dict[str, Any]]:
        """
        Cancel all open orders, optionally for a specific symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT'), if None cancels for all symbols
            params: Additional parameters for the cancellation
            
        Returns:
            List of dictionaries with cancellation information
        """
        try:
            # Normalize the symbol if provided
            normalized_symbol = normalize_symbol(symbol) if symbol else None
            
            # Cancel all orders
            result = self.client.cancel_all_orders(normalized_symbol, params)
            
            if symbol:
                logger.info(f"Cancelled all orders for {symbol}")
            else:
                logger.info("Cancelled all orders across all symbols")
                
            return result
        except Exception as e:
            symbol_info = f" for {symbol}" if symbol else ""
            logger.error(f"Error cancelling all orders{symbol_info}: {str(e)}")
            return self.handle_error(e)

    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def amend_order(self, order_id: str, symbol: str, amount: Optional[float] = None, 
                   price: Optional[float] = None, params: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Amend an existing order.
        
        Args:
            order_id: ID of the order to amend
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            amount: New order amount (if None, keeps the original)
            price: New order price (if None, keeps the original)
            params: Additional parameters for the amendment
            
        Returns:
            Dictionary with order information
        """
        try:
            # Normalize the symbol
            symbol = normalize_symbol(symbol)
            
            # Validate parameters
            if amount is not None and amount <= 0:
                raise ValueError(f"Invalid amount: {amount}. Must be > 0.")
            
            if price is not None and price <= 0:
                raise ValueError(f"Invalid price: {price}. Must be > 0.")
            
            # Get current order to see what values to keep
            current_order = self.get_order(order_id, symbol)
            
            if current_order.get('status') not in ['open', 'pending']:
                raise ValueError(f"Cannot amend order {order_id} with status {current_order.get('status')}. Only open or pending orders can be amended.")
            
            # Set values for amendment
            update_amount = amount if amount is not None else current_order.get('amount')
            update_price = price if price is not None else current_order.get('price')
            
            # Amend the order using ccxt
            if hasattr(self.client, 'edit_order'):
                order = self.client.edit_order(
                    id=order_id,
                    symbol=symbol,
                    type=current_order.get('type'),
                    side=current_order.get('side'),
                    amount=update_amount,
                    price=update_price,
                    params=params
                )
                
                logger.info(f"Amended order {order_id} for {symbol} (amount: {update_amount}, price: {update_price})")
                return order
            else:
                # If direct amendment is not supported, cancel and replace
                logger.warning(f"Direct order amendment not supported. Cancelling and replacing order {order_id}")
                
                # Cancel existing order
                self.cancel_order(order_id, symbol)
                
                # Create new order with updated parameters
                new_order = self.client.create_order(
                    symbol=symbol,
                    type=current_order.get('type'),
                    side=current_order.get('side'),
                    amount=update_amount,
                    price=update_price,
                    params=params
                )
                
                logger.info(f"Replaced order {order_id} with new order {new_order.get('id')} for {symbol}")
                return new_order
        except Exception as e:
            logger.error(f"Error amending order {order_id}: {str(e)}")
            return self.handle_error(e)

    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def get_order(self, order_id: str, symbol: str, params: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Get information about a specific order.
        
        Args:
            order_id: Order ID to query
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            params: Additional parameters for the query
            
        Returns:
            Dictionary with order information
        """
        try:
            # Normalize the symbol
            symbol = normalize_symbol(symbol)
            
            # Get the order
            order = self.client.fetch_order(order_id, symbol, params)
            
            return order
        except Exception as e:
            logger.error(f"Error fetching order {order_id}: {str(e)}")
            return self.handle_error(e)

    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def get_open_orders(self, symbol: Optional[str] = None, params: Dict[str, Any] = {}) -> List[Dict[str, Any]]:
        """
        Get all open orders, optionally for a specific symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT'), if None gets for all symbols
            params: Additional parameters for the query
            
        Returns:
            List of dictionaries with order information
        """
        try:
            # Normalize the symbol if provided
            normalized_symbol = normalize_symbol(symbol) if symbol else None
            
            # Get open orders
            orders = self.client.fetch_open_orders(normalized_symbol, params=params)
            
            return orders
        except Exception as e:
            symbol_info = f" for {symbol}" if symbol else ""
            logger.error(f"Error fetching open orders{symbol_info}: {str(e)}")
            return self.handle_error(e)

    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def get_closed_orders(self, symbol: Optional[str] = None, since: Optional[int] = None, 
                        limit: Optional[int] = None, params: Dict[str, Any] = {}) -> List[Dict[str, Any]]:
        """
        Get closed orders, optionally for a specific symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT'), if None gets for all symbols
            since: Timestamp in milliseconds to fetch orders from
            limit: Maximum number of orders to return
            params: Additional parameters for the query
            
        Returns:
            List of dictionaries with order information
        """
        try:
            # Normalize the symbol if provided
            normalized_symbol = normalize_symbol(symbol) if symbol else None
            
            # Get closed orders
            orders = self.client.fetch_closed_orders(normalized_symbol, since, limit, params)
            
            return orders
        except Exception as e:
            symbol_info = f" for {symbol}" if symbol else ""
            logger.error(f"Error fetching closed orders{symbol_info}: {str(e)}")
            return self.handle_error(e)

    @retry(max_attempts=3, base_delay=1.0, max_delay=10.0)
    def create_batch_orders(self, orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create multiple orders in a batch.
        
        Args:
            orders: List of order specifications, each containing:
                    - symbol: Trading pair symbol (e.g., 'BTC/USDT')
                    - type: Order type ('market', 'limit', etc.)
                    - side: Order side ('buy' or 'sell')
                    - amount: Order amount
                    - price: Order price (for limit orders)
                    - params: Additional parameters (optional)
            
        Returns:
            Dictionary with order results and any errors
        """
        try:
            # Validate orders
            if not orders:
                raise ValueError("No orders provided for batch creation")
            
            results = []
            errors = []
            
            # Process each order
            for i, order_spec in enumerate(orders):
                try:
                    # Extract order details
                    symbol = order_spec.get('symbol')
                    if not symbol:
                        raise ValueError(f"Missing symbol for order at index {i}")
                        
                    # Normalize the symbol
                    symbol = normalize_symbol(symbol)
                    
                    order_type = order_spec.get('type')
                    if not order_type:
                        raise ValueError(f"Missing order type for order at index {i}")
                        
                    side = order_spec.get('side')
                    if not side or side.lower() not in ['buy', 'sell']:
                        raise ValueError(f"Invalid or missing side for order at index {i}")
                        
                    amount = order_spec.get('amount')
                    if not amount or amount <= 0:
                        raise ValueError(f"Invalid or missing amount for order at index {i}")
                        
                    price = order_spec.get('price')
                    if order_type.lower() == 'limit' and (not price or price <= 0):
                        raise ValueError(f"Invalid or missing price for limit order at index {i}")
                        
                    params = order_spec.get('params', {})
                    
                    # Create a unique client order ID for tracking
                    client_order_id = self.generate_client_order_id()
                    order_params = {'clientOrderId': client_order_id, **params}
                    
                    # Create the order
                    order = self.client.create_order(
                        symbol=symbol,
                        type=order_type,
                        side=side.lower(),
                        amount=amount,
                        price=price,
                        params=order_params
                    )
                    
                    logger.info(f"Created {order_type} {side} order for {amount} {symbol}")
                    results.append(order)
                    
                except Exception as e:
                    logger.error(f"Error creating order at index {i}: {str(e)}")
                    errors.append({
                        'index': i,
                        'error': str(e),
                        'order_spec': order_spec
                    })
                    continue
            
            # Return results and any errors
            return {
                'orders': results,
                'errors': errors,
                'success_count': len(results),
                'error_count': len(errors),
                'total_orders': len(orders)
            }
        except Exception as e:
            logger.error(f"Error creating batch orders: {str(e)}")
            return self.handle_error(e)

    def generate_client_order_id(self) -> str:
        """
        Generate a unique client order ID for tracking.
        
        Returns:
            String client order ID
        """
        return f"bot_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}" 