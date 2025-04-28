"""
Example Integration of AdvancedRateLimiter with BinanceApiClient

This module demonstrates how to integrate the advanced rate limiter
into the existing BinanceApiClient class.
"""

from typing import Dict, Any, Optional, Tuple
import time
import requests

from .rate_limiting.advanced_limiter import (
    AdvancedRateLimiter,
    ConnectionType,
    RequestPriority,
    rate_limited
)


class EnhancedBinanceApiClient:
    """
    Example of integrating the advanced rate limiter with BinanceApiClient.
    
    This is a simplified version that shows the integration pattern.
    """
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """Initialize the client with optional API credentials."""
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_url = "https://api.binance.com"
        
        # Get the singleton rate limiter instance
        self.rate_limiter = AdvancedRateLimiter()
        
        # Start the async queue processor if using async methods
        # import asyncio
        # asyncio.create_task(self.rate_limiter.start_queue_processor())
    
    def make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        authenticated: bool = False,
        priority: RequestPriority = RequestPriority.NORMAL
    ) -> Dict[str, Any]:
        """
        Make a request to the Binance API with rate limiting.
        
        This method explicitly calls the rate limiter's pre_request and
        post_request methods to handle rate limiting.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: URL parameters
            data: Request body
            headers: HTTP headers
            authenticated: Whether to sign the request
            priority: Request priority
            
        Returns:
            Response data
        """
        # Prepare the request
        url = f"{self.api_url}{endpoint}"
        request_headers = {'Content-Type': 'application/json'}
        
        if self.api_key and authenticated:
            request_headers['X-MBX-APIKEY'] = self.api_key
            
        if headers:
            request_headers.update(headers)
            
        # Apply rate limiting before making the request
        self.rate_limiter.pre_request(
            endpoint=endpoint,
            method=method,
            options=params,
            connection_type=ConnectionType.REST,
            priority=priority
        )
        
        # Make the request
        try:
            if method == 'GET':
                response = requests.get(url, params=params, headers=request_headers)
            elif method == 'POST':
                response = requests.post(url, json=data, params=params, headers=request_headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            # Process the response
            response.raise_for_status()
            
            # Update rate limits from headers
            self.rate_limiter.post_request(response.headers)
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            # Handle the error
            if hasattr(e.response, 'headers'):
                self.rate_limiter.post_request(e.response.headers)
                
            raise
    
    # Example of using the rate_limited decorator
    @rate_limited(priority=RequestPriority.NORMAL, custom_endpoint="/api/v3/ping")
    def ping(self) -> Dict[str, Any]:
        """
        Test connectivity to the API.
        
        This method uses the rate_limited decorator to handle rate limiting.
        
        Returns:
            Empty object on success
        """
        url = f"{self.api_url}/api/v3/ping"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    
    def get_exchange_info(self) -> Dict[str, Any]:
        """
        Get exchange information.
        
        Uses the explicit rate limiting approach.
        
        Returns:
            Exchange information
        """
        return self.make_request(
            method='GET',
            endpoint='/api/v3/exchangeInfo',
            priority=RequestPriority.NORMAL
        )
    
    def get_order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """
        Get order book for a symbol.
        
        Uses the explicit rate limiting approach with a higher priority.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            limit: Number of entries to return
            
        Returns:
            Order book data
        """
        params = {'symbol': symbol, 'limit': limit}
        
        # Order book requests get higher priority
        return self.make_request(
            method='GET',
            endpoint='/api/v3/depth',
            params=params,
            priority=RequestPriority.HIGH
        )
    
    def place_order(
        self,
        symbol: str,
        side: str,
        type: str,
        quantity: float,
        price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Place a new order.
        
        Uses the explicit rate limiting approach with critical priority.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            side: Order side (BUY or SELL)
            type: Order type (LIMIT, MARKET, etc.)
            quantity: Order quantity
            price: Order price (required for limit orders)
            
        Returns:
            Order information
        """
        params = {
            'symbol': symbol,
            'side': side,
            'type': type,
            'quantity': quantity,
            'timestamp': int(time.time() * 1000)
        }
        
        if price and type == 'LIMIT':
            params['price'] = price
            params['timeInForce'] = 'GTC'
            
        # Order placement gets critical priority
        return self.make_request(
            method='POST',
            endpoint='/api/v3/order',
            params=params,
            authenticated=True,
            priority=RequestPriority.CRITICAL
        )
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current rate limit status.
        
        Returns:
            Rate limit status information
        """
        return self.rate_limiter.get_status()


# Example usage:
if __name__ == "__main__":
    # Create client instance
    client = EnhancedBinanceApiClient()
    
    # Test connectivity
    ping_result = client.ping()
    print("Ping result:", ping_result)
    
    # Get exchange info
    exchange_info = client.get_exchange_info()
    print(f"Got exchange info with {len(exchange_info.get('symbols', []))} symbols")
    
    # Get order book
    order_book = client.get_order_book("BTCUSDT", limit=10)
    print(f"Got order book with {len(order_book.get('bids', []))} bids")
    
    # Check rate limit status
    status = client.get_rate_limit_status()
    print("Rate limit status:", status) 