"""
Binance API Client

Enhanced Binance API client implementation with Singleton pattern,
improved security, rate limiting, and error handling.
"""

import os
import time
import hmac
import hashlib
import urllib.parse
import base64
from typing import Dict, List, Any, Optional, Tuple, Union, Callable
import threading
from datetime import datetime
import random
import json

import ccxt
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError
)

from ..utils import ThreadSafeSingleton
from ..utils.logging import get_structured_logger
from .rate_limiter import RateLimiter
from .exceptions import (
    ExchangeError, AuthenticationError, RateLimitError,
    InsufficientFundsError, InvalidOrderError, CircuitBreakerError,
    NetworkError, ServerError, TimeoutError, ExchangeOperationError,
    SymbolNotFoundError, ExchangeMaintenanceError, WebSocketError
)

# Configure logger
logger = get_structured_logger(__name__)

# Check if we're in mock mode
MOCK_API = os.getenv("MOCK_API", "false").lower() == "true"

# Mock data for development
MOCK_BALANCES = [
    {"asset": "BTC", "free": "0.5", "locked": "0.1"},
    {"asset": "ETH", "free": "5.0", "locked": "0.0"},
    {"asset": "USDT", "free": "10000.0", "locked": "5000.0"},
    {"asset": "BNB", "free": "10.0", "locked": "2.0"},
    {"asset": "SOL", "free": "50.0", "locked": "0.0"},
    {"asset": "ADA", "free": "1000.0", "locked": "0.0"},
    {"asset": "DOT", "free": "100.0", "locked": "0.0"},
    {"asset": "DOGE", "free": "10000.0", "locked": "0.0"}
]

MOCK_TICKER_PRICES = [
    {"symbol": "BTCUSDT", "price": "45000.50"},
    {"symbol": "ETHUSDT", "price": "2500.75"},
    {"symbol": "BNBUSDT", "price": "320.40"},
    {"symbol": "SOLUSDT", "price": "98.60"},
    {"symbol": "ADAUSDT", "price": "0.53"},
    {"symbol": "DOTUSDT", "price": "15.80"},
    {"symbol": "DOGEUSDT", "price": "0.15"}
]

# Binance API endpoints
BINANCE_API_URL = "https://api.binance.com"
BINANCE_API_TESTNET_URL = "https://testnet.binance.vision"
BINANCE_DATA_API_URL = "https://data-api.binance.vision"

# Default rate limits
DEFAULT_RATE_LIMITS = {
    "general": {"limit": 1200, "interval": 60},  # 1200 requests per minute
    "orders": {"limit": 50, "interval": 10},     # 50 orders per 10 seconds
    "trading": {"limit": 100000, "interval": 3600}  # 100,000 per hour
}


class CircuitBreaker:
    """
    Circuit breaker implementation to prevent cascading failures.
    
    Opens the circuit after a specified number of failures, preventing
    further requests for a cooling-off period.
    """
    
    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"      # Circuit breaker triggered, requests blocked
    HALF_OPEN = "half_open"  # Testing if service is back, limited requests
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        timeout_factor: float = 2.0,
        max_timeout: float = 300.0
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit.
            recovery_timeout: Initial time in seconds to wait before retrying.
            timeout_factor: Factor to multiply timeout by on consecutive failures.
            max_timeout: Maximum timeout value in seconds.
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.timeout_factor = timeout_factor
        self.max_timeout = max_timeout
        
        self.state = self.CLOSED
        self.failures = 0
        self.last_failure_time = 0
        self.current_timeout = recovery_timeout
        self.lock = threading.RLock()
    
    def record_success(self) -> None:
        """Record a successful operation."""
        with self.lock:
            self.failures = 0
            self.state = self.CLOSED
            self.current_timeout = self.recovery_timeout
    
    def record_failure(self) -> None:
        """Record a failed operation."""
        with self.lock:
            self.failures += 1
            self.last_failure_time = time.time()
            
            if self.state == self.CLOSED and self.failures >= self.failure_threshold:
                self.state = self.OPEN
                logger.warning("Circuit breaker opened", failures=self.failures)
            elif self.state == self.HALF_OPEN:
                self.state = self.OPEN
                self.current_timeout = min(self.current_timeout * self.timeout_factor, self.max_timeout)
                logger.warning("Circuit breaker reopened", 
                               timeout=self.current_timeout)
    
    def allow_request(self) -> bool:
        """
        Check if a request is allowed based on the circuit state.
        
        Returns:
            True if request is allowed, False otherwise.
        """
        with self.lock:
            if self.state == self.CLOSED:
                return True
            
            if self.state == self.OPEN:
                # Check if recovery timeout has elapsed
                elapsed = time.time() - self.last_failure_time
                if elapsed >= self.current_timeout:
                    self.state = self.HALF_OPEN
                    logger.info("Circuit breaker half-open", elapsed=elapsed)
                    return True
                
                # Calculate time remaining until retry
                retry_after = self.current_timeout - elapsed
                raise CircuitBreakerError(
                    f"Circuit breaker open for {self.current_timeout} seconds",
                    category=self.__class__.__name__,
                    retry_after=retry_after
                )
            
            # HALF_OPEN state - allow the request to test service
            return True


class BinanceApiClient(metaclass=ThreadSafeSingleton):
    """
    Enhanced Binance API client with improved security, rate limiting, 
    and reliability.
    
    Implements the Singleton pattern to ensure only one client instance
    exists.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        use_ed25519: bool = False,
        testnet: bool = False,
        timeout: int = 30000,
        enable_rate_limit: bool = True,
        max_retries: int = 3,
    ):
        """
        Initialize the Binance API client.
        
        Args:
            api_key: Binance API key (defaults to BINANCE_API_KEY env var)
            api_secret: Binance API secret (defaults to BINANCE_API_SECRET env var)
            use_ed25519: Whether to use Ed25519 for signing (newer, more secure)
            testnet: Whether to use the testnet
            timeout: Request timeout in milliseconds
            enable_rate_limit: Whether to enable rate limiting
            max_retries: Maximum number of retries for API calls
        """
        # Load API credentials from environment if not provided
        self.api_key = api_key or os.environ.get('BINANCE_API_KEY')
        self.api_secret = api_secret or os.environ.get('BINANCE_API_SECRET')
        
        # Use Ed25519 or HmacSHA256 based on flag
        self.use_ed25519 = use_ed25519
        self.testnet = testnet
        self.timeout = timeout
        self.enable_rate_limit = enable_rate_limit
        self.max_retries = max_retries
        
        # API URLs
        self.api_url = BINANCE_API_TESTNET_URL if testnet else BINANCE_API_URL
        self.data_api_url = BINANCE_DATA_API_URL
        
        # Initialize clients
        self.ccxt_client = None
        self.session = requests.Session()
        
        # Set up rate limiter
        self.rate_limiter = RateLimiter()
        self._setup_rate_limits()
        
        # Set up circuit breakers for different API endpoints
        self.circuit_breakers = {
            "market": CircuitBreaker(),
            "account": CircuitBreaker(),
            "trade": CircuitBreaker(),
        }
        
        # Initialize CCXT client
        self._init_ccxt_client()
        
        logger.info("Initialized Binance API client", 
                    testnet=testnet, 
                    ed25519=use_ed25519,
                    has_credentials=bool(self.api_key and self.api_secret))
    
    def _setup_rate_limits(self) -> None:
        """Set up default rate limits."""
        for endpoint, config in DEFAULT_RATE_LIMITS.items():
            self.rate_limiter.set_limit(endpoint, config["limit"], config["interval"])
    
    def _init_ccxt_client(self) -> None:
        """Initialize the CCXT client with configuration."""
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
                        'public': f"{BINANCE_API_TESTNET_URL}/api/v3",
                        'private': f"{BINANCE_API_TESTNET_URL}/api/v3",
                    }
                }
            
            # Initialize ccxt Binance client
            self.ccxt_client = ccxt.binance(options)
            
            # Load markets to cache available symbols
            self.ccxt_client.load_markets()
            
        except Exception as e:
            logger.error("Failed to initialize CCXT client", error=str(e))
            raise ExchangeOperationError(f"Failed to initialize client: {str(e)}")
    
    def _sign_request_sha256(self, data: Dict[str, Any]) -> str:
        """
        Sign request data using HMAC-SHA256.
        
        Args:
            data: Request parameters to sign.
            
        Returns:
            Signature as a hexadecimal string.
        """
        # Convert data to query string
        query_string = urllib.parse.urlencode(data)
        
        # Create signature using HMAC-SHA256
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def _sign_request_ed25519(self, data: Dict[str, Any]) -> str:
        """
        Sign request data using Ed25519.
        
        This is Binance's newer, more secure signing method.
        
        Args:
            data: Request parameters to sign.
            
        Returns:
            Signature as a base64 string.
        """
        try:
            import nacl.signing
            import nacl.encoding
            
            # Convert data to query string
            query_string = urllib.parse.urlencode(data)
            
            # Decode the API secret from base64
            signing_key = base64.b64decode(self.api_secret)
            
            # Create the signing key
            key = nacl.signing.SigningKey(signing_key)
            
            # Sign the query string
            signature = key.sign(query_string.encode('utf-8')).signature
            
            # Encode the signature as base64
            return base64.b64encode(signature).decode('utf-8')
            
        except ImportError:
            logger.error("Ed25519 signing requires PyNaCl library. Falling back to SHA256.")
            return self._sign_request_sha256(data)
    
    def sign_request(self, data: Dict[str, Any]) -> str:
        """
        Sign request data using the configured signing method.
        
        Args:
            data: Request parameters to sign.
            
        Returns:
            Signature string.
        """
        if self.use_ed25519:
            return self._sign_request_ed25519(data)
        else:
            return self._sign_request_sha256(data)
    
    def _get_request_headers(self) -> Dict[str, str]:
        """
        Get headers for API requests.
        
        Returns:
            Dictionary of request headers.
        """
        headers = {
            'User-Agent': 'BinanceApiClient/1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        
        if self.api_key:
            if self.use_ed25519:
                headers['X-MBX-APIKEY'] = self.api_key
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
            else:
                headers['X-MBX-APIKEY'] = self.api_key
        
        return headers
    
    def _endpoint_to_category(self, endpoint: str) -> str:
        """
        Map an endpoint to a circuit breaker category.
        
        Args:
            endpoint: API endpoint.
            
        Returns:
            Circuit breaker category.
        """
        if '/api/v3/order' in endpoint or '/api/v3/allOrders' in endpoint:
            return "trade"
        elif '/api/v3/account' in endpoint or '/api/v3/myTrades' in endpoint:
            return "account"
        else:
            return "market"
    
    def _map_error_code(self, status_code: int, error_code: Optional[int] = None, error_msg: str = "") -> ExchangeError:
        """
        Map HTTP status codes and Binance API error codes to appropriate exceptions.
        
        Args:
            status_code: HTTP status code
            error_code: Binance API error code (optional)
            error_msg: Error message from API response
            
        Returns:
            Appropriate exception derived from ExchangeError
        """
        # Check for specific Binance error codes first
        if error_code is not None:
            # Binance specific error code mapping
            # Ref: https://binance-docs.github.io/apidocs/spot/en/#error-codes
            binance_errors = {
                # Server errors
                -1000: ("Unknown error", ServerError),
                -1001: ("Disconnected from server", NetworkError),
                -1002: ("Unauthorized", AuthenticationError),
                -1003: ("Too many requests (rate limit)", RateLimitError),
                -1004: ("Server busy", ServerError),
                -1005: ("Unexpected server response", ServerError),
                -1006: ("Async request in progress", ServerError),
                -1007: ("Timeout waiting for response", TimeoutError),
                -1010: ("Error in processing request", ServerError),
                -1013: ("Invalid order size/price", InvalidOrderError),
                -1014: ("Unsupported order combination", InvalidOrderError),
                -1015: ("Too many orders (rate limit)", RateLimitError),
                -1016: ("Service shutting down", ServerError),
                -1020: ("Unsupported operation", InvalidOrderError),
                -1021: ("Timestamp for this request outside the recvWindow", ExchangeError),
                -1022: ("Invalid signature", AuthenticationError),
                -1100: ("Illegal parameter combination", ExchangeError),
                -1101: ("Too many parameters sent", ExchangeError),
                -1102: ("Required parameter not sent", ExchangeError),
                -1103: ("Invalid parameter format/value", ExchangeError),
                -1104: ("Parameter not required", ExchangeError),
                -1105: ("Parameter empty", ExchangeError),
                -1106: ("Parameter not required and should not be sent", ExchangeError),
                -1111: ("Invalid precision", ExchangeError),
                -1112: ("Withdrawal amount too large", ExchangeError),
                -1114: ("TIF does not match order type", InvalidOrderError),
                -1115: ("Invalid order type", InvalidOrderError),
                -1116: ("Invalid order side", InvalidOrderError),
                -1117: ("New client order ID was empty", InvalidOrderError),
                -1118: ("Invalid interval", ExchangeError),
                -1119: ("Invalid function call", ExchangeError),
                -1120: ("Invalid API key format", AuthenticationError),
                -1121: ("Invalid signature format", AuthenticationError),
                -1125: ("User account invalid", AuthenticationError),
                -1127: ("Client order ID already exists", InvalidOrderError),
                -1130: ("Invalid data sent", ExchangeError),
                -1131: ("Invalid BAM API key format", AuthenticationError),
                -2010: ("Insufficient balance", InsufficientFundsError),
                -2011: ("Order would trigger immediately as a taker", InvalidOrderError),
                -2013: ("Order does not exist", InvalidOrderError),
                -2014: ("Invalid API key permissions", AuthenticationError),
                -2015: ("Rejected MBX key", AuthenticationError),
                -2016: ("No trading window", ExchangeError),
                -3000: ("Internal server error", ServerError),
                -3001: ("Asset not available for API trading", ExchangeError),
                -3002: ("Exchange not available due to maintenance", ExchangeMaintenanceError),
                -3003: ("Account not available due to maintenance", ExchangeMaintenanceError),
                -3004: ("Asset not available due to maintenance", ExchangeMaintenanceError),
                -3005: ("Refresh rate limit exceeded", RateLimitError),
                -3006: ("IP banned due to repeated rate limit violations", RateLimitError),
                -3007: ("Long execution time, try again later", ServerError),
                -3008: ("Mandatory parameter not sent", ExchangeError),
                -3009: ("Forbidden duplicate parameter sent", ExchangeError),
                -3010: ("Request path contains invalid parameters", ExchangeError),
                -3011: ("Alternative symbol does not exist", SymbolNotFoundError),
                -3014: ("Token is not active", ExchangeError),
                -3015: ("Symbol does not exist", SymbolNotFoundError),
                -3016: ("Request body contains invalid JSON", ExchangeError),
                -3017: ("Market order amount exceeds allowed limit", InvalidOrderError),
                -3018: ("Market order price exceeds allowed limit", InvalidOrderError),
                -3019: ("Contract is currently restricted from trading", InvalidOrderError),
                -3020: ("Order cancel conditions not met", InvalidOrderError),
                -3021: ("Order would immediately trigger", InvalidOrderError),
                -3022: ("Contract is currently in settlement", ExchangeError),
                -3041: ("Symbol not found or trading not available", SymbolNotFoundError),
                -4000: ("Invalid operation in transfer", ExchangeError),
                -4001: ("Invalid operation type in transfer", ExchangeError),
                -4002: ("Invalid transfer type", ExchangeError),
                -4003: ("Invalid client type", ExchangeError),
                -4004: ("Invalid or not authorized target account", ExchangeError),
                -4005: ("Invalid parent account", ExchangeError),
                -4006: ("User does not exist", AuthenticationError),
                -4007: ("Operation type not supported", ExchangeError),
                -4008: ("Transfer amount <= 0", ExchangeError),
                -4009: ("Transfer would breach max available balance", InsufficientFundsError),
                -4010: ("Your input request exceeded the maximum size", ExchangeError),
                -4011: ("Asset does not exist", ExchangeError),
                -4012: ("Account does not exist", ExchangeError),
                -4013: ("Timeout transferring between accounts", TimeoutError),
                -4014: ("Invalid account status", ExchangeError),
                -4015: ("Transfer incomplete", ExchangeError),
                -4016: ("Transfer would breach sub-account transfer limit", ExchangeError),
                -4017: ("This asset cannot be transferred", ExchangeError),
                -9000: ("System error", ServerError),
                -11001: ("Isolated margin account does not exist", ExchangeError),
                -11002: ("Margin account already existing", ExchangeError),
                -11003: ("Incorrect margin account for transfer", ExchangeError),
                -11004: ("Account in liquidation", ExchangeError),
                -11005: ("Repay transaction would breach max LTV", ExchangeError),
                -11006: ("Invalid trade direction", ExchangeError),
                -11007: ("Not eligible for margin trading", ExchangeError),
                -11008: ("Unable to transfer into margin account due to max transfer limit", ExchangeError),
                -11009: ("Unable to transfer out due to loan", ExchangeError),
                -11010: ("Isolated margin account conversion not eligible", ExchangeError),
                -11011: ("Asset in isolated margin account", ExchangeError),
                -11012: ("Asset locked in cross margin account", ExchangeError),
                -11013: ("Interest payment in progress", ExchangeError),
                -11014: ("Pending repayment in progress", ExchangeError),
                -11015: ("Negative account balance", InsufficientFundsError),
                -11016: ("Unable to adjust cross margin due to funds", InsufficientFundsError),
                -11017: ("Unable to create isolated margin account", ExchangeError),
                -11018: ("Isolated margin account limit reached", ExchangeError),
                -11019: ("Isolated margin account not eligible for this asset", ExchangeError),
                -11020: ("Loan not found", ExchangeError),
                -11021: ("Repay amount exceeds loan", ExchangeError),
                -11022: ("Insufficient wallet balance", InsufficientFundsError),
                -11023: ("Interest cannot be prepaid", ExchangeError),
                -11024: ("Exceeds maximum borrow amount", ExchangeError),
                -11025: ("Collateral cannot be removed", ExchangeError),
                -11026: ("Exceeds maximum number of borrowable assets", ExchangeError),
                -11027: ("Collateral assets cannot be traded", ExchangeError),
                -11028: ("Account or symbol not enabled for margin", ExchangeError),
                -11029: ("Margin balance insufficient", InsufficientFundsError),
                -11030: ("Maintenance margin level too high", ExchangeError),
                -11031: ("Margin is not sufficient", InsufficientFundsError),
                -11032: ("LTV would breach max LTV", ExchangeError),
                -11033: ("Order amount exceeds current available", InsufficientFundsError),
                -11034: ("Order quantity exceeds available quantity", InsufficientFundsError),
                -11035: ("Order would breach position closure threshold", ExchangeError),
                -11036: ("Account would breach maximum positions", ExchangeError),
                -11037: ("Unsupported order combination", InvalidOrderError),
                -11038: ("Account not eligible for this margin trade", ExchangeError),
                -11039: ("Disable margin trading not allowed", ExchangeError),
                -11040: ("This operation requires margin auto-repay enabled", ExchangeError),
                -11041: ("Margin trading not enabled", ExchangeError),
                -11042: ("Cannot transfer to disabled margin account", ExchangeError),
                -11043: ("Unable to transfer from or to margin account", ExchangeError),
                -11044: ("Insufficient margin account balance", InsufficientFundsError),
                -11045: ("Negative margin account balance", InsufficientFundsError),
            }
            
            error_info = binance_errors.get(error_code)
            if error_info:
                error_description, error_class = error_info
                message = f"{error_description}: {error_msg}" if error_msg else error_description
                return error_class(message, code=error_code)
        
        # If no specific Binance error code match, use HTTP status code
        if status_code >= 500:
            return ServerError(f"Server error: HTTP {status_code}: {error_msg}")
        elif status_code == 429:
            return RateLimitError(f"Rate limit exceeded: {error_msg}")
        elif status_code == 418:
            return RateLimitError(f"IP has been auto-banned for violation: {error_msg}")
        elif status_code == 403:
            return AuthenticationError(f"Forbidden: {error_msg}")
        elif status_code == 401:
            return AuthenticationError(f"Unauthorized: {error_msg}")
        elif status_code == 404:
            return ExchangeError(f"Endpoint not found: {error_msg}")
        elif status_code == 400:
            # Try to determine if it's a more specific error
            lower_error_msg = error_msg.lower() if error_msg else ""
            if "insufficient" in lower_error_msg and "balance" in lower_error_msg:
                return InsufficientFundsError(f"Insufficient balance: {error_msg}")
            elif "order" in lower_error_msg:
                return InvalidOrderError(f"Invalid order: {error_msg}")
            else:
                return ExchangeError(f"Bad request: {error_msg}")
        
        # Default to generic exchange error
        return ExchangeError(f"HTTP {status_code}: {error_msg}")
    
    def _handle_response(self, response: requests.Response, endpoint: str) -> Dict[str, Any]:
        """
        Handle API response.
        
        Args:
            response: Response object.
            endpoint: API endpoint.
            
        Returns:
            Response data as dictionary.
            
        Raises:
            Exception: If the response contains an error.
        """
        # Update rate limit info from headers
        self.rate_limiter.post_request(endpoint, response.headers)
        
        # Record success in circuit breaker
        category = self._endpoint_to_category(endpoint)
        
        # Handle response
        if response.status_code == 200:
            self.circuit_breakers[category].record_success()
            return response.json()
        
        # Handle error responses
        error_info = response.json() if response.content else {"error": "Unknown error"}
        error_code = error_info.get("code", None)
        error_msg = error_info.get("msg", str(response.content))
        
        logger.error("Binance API error", 
                     endpoint=endpoint,
                     status_code=response.status_code,
                     error_code=error_code,
                     error_message=error_msg)
        
        # Record failure in circuit breaker
        self.circuit_breakers[category].record_failure()
        
        # Map to appropriate exception
        exception = self._map_error_code(response.status_code, error_code, error_msg)
        
        # Add details to exception
        exception.details.update({
            'endpoint': endpoint,
            'status_code': response.status_code,
            'error_code': error_code,
            'headers': dict(response.headers)
        })
        
        raise exception
    
    @retry(
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    def make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        authenticated: bool = False,
        rate_limit_category: str = "general",
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the Binance API.
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.).
            endpoint: API endpoint.
            params: URL parameters.
            data: Request body data.
            headers: Additional headers.
            timeout: Request timeout in seconds.
            authenticated: Whether the request needs authentication.
            rate_limit_category: Rate limit category for this request.
            
        Returns:
            Response data as dictionary.
            
        Raises:
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limits are exceeded.
            NetworkError: If a network error occurs.
            ServerError: If the server returns an error.
            TimeoutError: If the request times out.
            ExchangeError: For other exchange-related errors.
        """
        # Default parameters
        params = params or {}
        headers = headers or {}
        timeout = timeout or (self.timeout / 1000)  # Convert to seconds
        
        # Add timestamp for authenticated requests
        if authenticated:
            if not self.api_key or not self.api_secret:
                raise AuthenticationError("API key and secret required for authenticated requests")
            
            params['timestamp'] = int(time.time() * 1000)
            
            # Add recvWindow parameter
            if 'recvWindow' not in params:
                params['recvWindow'] = 5000
            
            # Sign the request
            params['signature'] = self.sign_request(params)
        
        # Check circuit breaker
        category = self._endpoint_to_category(endpoint)
        try:
            if not self.circuit_breakers[category].allow_request():
                # This should never be reached - allow_request raises if not allowed
                pass
        except CircuitBreakerError as e:
            # Pass through CircuitBreakerError
            raise
        
        # Apply rate limiting
        try:
            wait_time = self.rate_limiter.pre_request(rate_limit_category)
            if wait_time > 0:
                logger.info("Rate limited request", 
                            wait_time=wait_time, 
                            category=rate_limit_category)
        except Exception as e:
            logger.warning("Rate limiter error", error=str(e))
            # Continue anyway, Binance will enforce rate limits
        
        # Full URL
        url = f"{self.api_url}{endpoint}"
        
        # Use data API for market data if not authenticated
        if not authenticated and endpoint.startswith('/api/v3/klines'):
            url = f"{self.data_api_url}{endpoint}"
        
        # Prepare headers
        request_headers = self._get_request_headers()
        request_headers.update(headers)
        
        try:
            # Make the request
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=data if method != 'GET' else None,
                headers=request_headers,
                timeout=timeout
            )
            
            # Handle the response
            return self._handle_response(response, endpoint)
            
        except requests.ConnectionError as e:
            # Record failure in circuit breaker
            self.circuit_breakers[category].record_failure()
            
            # Log error and raise NetworkError
            logger.error("Connection error", 
                         endpoint=endpoint,
                         error=str(e))
            raise NetworkError(f"Connection error: {str(e)}")
            
        except requests.Timeout as e:
            # Record failure in circuit breaker
            self.circuit_breakers[category].record_failure()
            
            # Log error and raise TimeoutError
            logger.error("Request timed out", 
                         endpoint=endpoint,
                         timeout=timeout,
                         error=str(e))
            raise TimeoutError(f"Request timed out: {str(e)}")
            
        except requests.RequestException as e:
            # Record failure in circuit breaker
            self.circuit_breakers[category].record_failure()
            
            # Log error and raise NetworkError
            logger.error("Request failed", 
                         endpoint=endpoint,
                         error=str(e),
                         error_type=type(e).__name__)
            raise NetworkError(f"Request failed: {str(e)}")
            
        except ExchangeError:
            # Pass through existing exchange errors
            raise
            
        except Exception as e:
            # Catch all other exceptions
            logger.error("Unexpected error", 
                         endpoint=endpoint,
                         error=str(e),
                         error_type=type(e).__name__)
            raise ExchangeOperationError(f"Unexpected error: {str(e)}")
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test the connection to Binance.
        
        Returns:
            Tuple of (success, message).
        """
        try:
            result = self.make_request('GET', '/api/v3/ping')
            server_time = self.make_request('GET', '/api/v3/time')
            
            if 'serverTime' in server_time:
                time_diff = abs(server_time['serverTime'] - int(time.time() * 1000))
                return True, f"Connected to Binance. Server time sync: {time_diff}ms difference"
            
            return True, "Connected to Binance."
        except ExchangeError as e:
            return False, f"Connection test failed: {str(e)}"
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"
    
    def get_exchange_info(self) -> Dict[str, Any]:
        """
        Get exchange information.
        
        Returns:
            Exchange information as a dictionary.
        """
        return self.make_request('GET', '/api/v3/exchangeInfo')
    
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get ticker for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT').
            
        Returns:
            Ticker data.
        """
        return self.make_request('GET', '/api/v3/ticker/24hr', params={'symbol': symbol})
    
    def get_account_info(self) -> Dict[str, Any]:
        """
        Get account information.
        
        Returns:
            Account information as a dictionary.
        """
        return self.make_request('GET', '/api/v3/account', authenticated=True, rate_limit_category="account")
    
    def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        time_in_force: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a new order.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT').
            side: Order side ('BUY' or 'SELL').
            order_type: Order type ('LIMIT', 'MARKET', etc.).
            quantity: Order quantity.
            price: Order price (required for limit orders).
            time_in_force: Time in force ('GTC', 'IOC', 'FOK').
            **kwargs: Additional parameters.
            
        Returns:
            Order information.
        """
        # Prepare parameters
        params = {
            'symbol': symbol,
            'side': side,
            'type': order_type,
        }
        
        # Add optional parameters if provided
        if quantity is not None:
            params['quantity'] = quantity
        
        if price is not None:
            params['price'] = price
        
        if time_in_force is not None:
            params['timeInForce'] = time_in_force
        
        # Add any additional parameters
        params.update(kwargs)
        
        # Make the request
        return self.make_request(
            'POST', 
            '/api/v3/order', 
            params=params, 
            authenticated=True,
            rate_limit_category="orders"
        )
    
    def cancel_order(self, symbol: str, order_id: Optional[int] = None, 
                      client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Cancel an order.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT').
            order_id: Order ID.
            client_order_id: Client order ID.
            
        Returns:
            Cancellation information.
        """
        # Prepare parameters
        params = {'symbol': symbol}
        
        # Add either order_id or client_order_id
        if order_id is not None:
            params['orderId'] = order_id
        elif client_order_id is not None:
            params['origClientOrderId'] = client_order_id
        else:
            raise InvalidOrderError("Either order_id or client_order_id must be provided")
        
        # Make the request
        return self.make_request(
            'DELETE', 
            '/api/v3/order', 
            params=params, 
            authenticated=True,
            rate_limit_category="orders"
        )
    
    def create_virtual_subaccount(
        self,
        subaccount_name: str,
        email: Optional[str] = None,
        recv_window: int = 5000
    ) -> Dict[str, Any]:
        """
        Create a Binance virtual sub-account.
        
        This endpoint requires a master account with appropriate permissions.
        
        Args:
            subaccount_name: Name for the sub-account. This will be used in the
                             subAccountString parameter.
            email: Email for the sub-account (optional).
            recv_window: The number of milliseconds the request is valid for.
            
        Returns:
            Sub-account creation response.
            
        Raises:
            AuthenticationError: If API key lacks permission or is not a master account.
            ExchangeError: For other Binance API errors.
        """
        # Prepare parameters
        params = {
            'subAccountString': subaccount_name,
            'recvWindow': recv_window
        }
        
        # Add email if provided
        if email is not None:
            params['email'] = email
            
        # Add additional KYC info if needed in future
        # These fields are based on Binance documentation but may not be
        # required for all account types
        
        # Make the request to the sub-account creation endpoint
        # Note: This uses /sapi/ endpoints which are different from regular /api/ endpoints
        logger.info("Creating Binance virtual sub-account", 
                   subaccount_name=subaccount_name,
                   has_email=bool(email))
                   
        try:
            return self.make_request(
                'POST',
                '/sapi/v1/sub-account/virtualSubAccount',
                params=params,
                authenticated=True,
                rate_limit_category="account"
            )
        except ExchangeError as e:
            logger.error("Failed to create virtual sub-account", 
                         error=str(e),
                         error_code=getattr(e, 'code', None))
            raise
    
    def create_subaccount_api_key(
        self,
        subaccount_id: str,
        label: str,
        permissions: List[str] = None,
        ip_restrict: bool = True,
        ip_list: Optional[str] = None,
        key_type: str = "Ed25519",
        recv_window: int = 5000
    ) -> Dict[str, Any]:
        """
        Create a new API key for a subaccount.
        
        Args:
            subaccount_id: The ID of the subaccount (UUID)
            label: Label for the API key
            permissions: List of permissions (e.g., ['SPOT', 'MARGIN', 'FUTURES'])
            ip_restrict: Whether to restrict by IP
            ip_list: Comma-separated list of IPs (required if ip_restrict is True)
            key_type: API key type (HMAC or Ed25519)
            recv_window: The receive window in milliseconds
            
        Returns:
            Response containing the new API key information
        """
        if permissions is None:
            permissions = ["SPOT"]
            
        params = {
            "subAccountId": subaccount_id,
            "label": label,
            "permissions": permissions,
            "ipRestrict": ip_restrict,
            "recvWindow": recv_window,
            "keyType": key_type
        }
        
        if ip_restrict and not ip_list:
            raise ValueError("IP list is required when IP restriction is enabled")
            
        if ip_restrict:
            params["ipList"] = ip_list
            
        return self.make_request(
            method="POST",
            endpoint="/sapi/v1/broker/subAccountApi",
            params=params,
            authenticated=True
        )
    
    def get_balance(self) -> Dict[str, Any]:
        """
        Get account balance information.
        
        Returns:
            Dictionary with balance data including all assets in the account
        """
        if MOCK_API:
            logger.info("Using mock Binance API for balance data")
            return {
                'balances': MOCK_BALANCES,
                'timestamp': int(time.time() * 1000),
                'datetime': datetime.utcnow().isoformat()
            }
            
        try:
            # Use account info endpoint to get all balances
            account_info = self.get_account_info()
            
            # Extract and process balances
            balances = account_info.get('balances', [])
            
            # Filter out zero balances for cleaner output
            non_zero_balances = []
            for balance in balances:
                free = float(balance.get('free', 0))
                locked = float(balance.get('locked', 0))
                if free > 0 or locked > 0:
                    non_zero_balances.append(balance)
            
            # Create a formatted response
            return {
                'balances': balances,  # Keep all balances for completeness
                'timestamp': int(time.time() * 1000),
                'datetime': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error fetching balance: {str(e)}")
            raise ExchangeOperationError(f"Failed to get balance: {str(e)}")
    
    def get_ticker_prices(self) -> List[Dict[str, Any]]:
        """
        Get current prices for all trading pairs.
        
        Returns:
            List of dictionaries with symbol and price information
        """
        if MOCK_API:
            logger.info("Using mock Binance API for ticker prices")
            return MOCK_TICKER_PRICES
            
        try:
            # Call the ticker/price endpoint
            endpoint = "/api/v3/ticker/price"
            result = self.make_request(
                method="GET",
                endpoint=endpoint,
                authenticated=False,
                rate_limit_category="market"
            )
            
            # Result is a list of dictionaries with symbol and price
            return result
        except Exception as e:
            logger.error(f"Error fetching ticker prices: {str(e)}")
            raise ExchangeOperationError(f"Failed to get ticker prices: {str(e)}")

    def get_24h_ticker_info(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Get 24-hour ticker information for specific symbols or all symbols.
        
        Provides price change, percent change, weighted average price, volume, etc.
        
        Args:
            symbols: Optional list of symbol pairs (e.g., ['BTCUSDT', 'ETHUSDT'])
                    If None, retrieves data for all trading pairs
                    
        Returns:
            List of dictionaries with 24h ticker information
        """
        if MOCK_API:
            logger.info("Using mock Binance API for 24h ticker info")
            # Create mock 24h data based on MOCK_TICKER_PRICES
            mock_24h_data = []
            for ticker in MOCK_TICKER_PRICES:
                symbol = ticker['symbol']
                price = float(ticker['price'])
                # Generate random values for mock data
                percent_change = random.uniform(-5.0, 5.0)
                price_change = price * percent_change / 100
                
                mock_24h_data.append({
                    'symbol': symbol,
                    'priceChange': str(price_change),
                    'priceChangePercent': str(percent_change),
                    'weightedAvgPrice': str(price * random.uniform(0.98, 1.02)),
                    'prevClosePrice': str(price - price_change),
                    'lastPrice': ticker['price'],
                    'volume': str(random.uniform(1000, 100000)),
                    'quoteVolume': str(random.uniform(10000, 10000000))
                })
            return mock_24h_data
        
        try:
            endpoint = "/api/v3/ticker/24hr"
            params = {}
            
            # If specific symbols are provided, add them to the request params
            # Binance allows requesting multiple symbols in a single call
            if symbols:
                # For multiple symbols, we need to convert the list to JSON string
                if len(symbols) > 1:
                    params['symbols'] = json.dumps(symbols)
                # For a single symbol, use the 'symbol' parameter
                elif len(symbols) == 1:
                    params['symbol'] = symbols[0]
            
            result = self.make_request(
                method="GET",
                endpoint=endpoint,
                params=params,
                authenticated=False,
                rate_limit_category="market"
            )
            
            # If a single symbol was requested with 'symbol' parameter,
            # the result is a dictionary, so we wrap it in a list
            if symbols and len(symbols) == 1 and isinstance(result, dict):
                result = [result]
            
            # Return the list of 24h ticker data
            return result
        except Exception as e:
            logger.error(f"Error fetching 24h ticker info: {str(e)}")
            raise ExchangeOperationError(f"Failed to get 24h ticker info: {str(e)}")

# Export as BinanceAPIClient for backward compatibility
BinanceAPIClient = BinanceApiClient 