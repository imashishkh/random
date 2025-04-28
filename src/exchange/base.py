"""
Base exchange module defining interfaces and common functionality for exchanges.
"""
import abc
import logging
from typing import Dict, Any, Optional, List, Tuple

# Configure logger
logger = logging.getLogger(__name__)

class BaseExchange(abc.ABC):
    """Abstract base class for cryptocurrency exchanges."""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, 
                 timeout: int = 30000, enable_rate_limit: bool = True):
        """
        Initialize the base exchange.
        
        Args:
            api_key: API key for the exchange
            api_secret: API secret for the exchange
            timeout: Request timeout in milliseconds
            enable_rate_limit: Whether to enable rate limiting
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self.enable_rate_limit = enable_rate_limit
        self.client = None
        self.exchange_name = self._get_exchange_name()
        
        logger.info(f"Initialized base exchange: {self.exchange_name}")
    
    @abc.abstractmethod
    def _get_exchange_name(self) -> str:
        """Return the name of the exchange."""
        pass
    
    @abc.abstractmethod
    def initialize(self) -> None:
        """Initialize the exchange client with configured parameters."""
        pass
    
    @abc.abstractmethod
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test the connection to the exchange.
        
        Returns:
            Tuple of (success, message)
        """
        pass
    
    @abc.abstractmethod
    def get_markets(self) -> Dict[str, Any]:
        """
        Get the markets available on the exchange.
        
        Returns:
            Dictionary of market data
        """
        pass
    
    @abc.abstractmethod
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get the ticker for a specific symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            
        Returns:
            Dictionary with ticker data
        """
        pass
    
    def handle_error(self, error: Exception) -> Dict[str, Any]:
        """
        Handle errors from the exchange API.
        
        Args:
            error: The exception that occurred
            
        Returns:
            Dictionary with error information
        """
        logger.error(f"Exchange error ({self.exchange_name}): {str(error)}")
        
        error_info = {
            "success": False,
            "error": str(error),
            "error_type": error.__class__.__name__,
            "exchange": self.exchange_name
        }
        
        return error_info
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get the health status of the exchange connection.
        
        Returns:
            Dictionary with health status information
        """
        try:
            success, message = self.test_connection()
            return {
                "name": self.exchange_name,
                "status": "online" if success else "offline",
                "message": message,
                "has_credentials": bool(self.api_key and self.api_secret)
            }
        except Exception as e:
            logger.error(f"Failed to get health status for {self.exchange_name}: {str(e)}")
            return {
                "name": self.exchange_name,
                "status": "error",
                "message": str(e),
                "has_credentials": bool(self.api_key and self.api_secret)
            } 