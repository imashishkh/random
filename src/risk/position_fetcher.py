"""
Position Data Fetcher for Binance API

This module implements a specialized fetcher for position data from the
Binance Futures API, with proper caching, error handling, and data normalization.
"""

import os
import time
import logging
import asyncio
from typing import Dict, List, Any, Optional, Union
from datetime import datetime

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log
)

from ..exchange.binance_api_client import BinanceApiClient
from ..utils import ThreadSafeSingleton
from ..utils.logging import get_structured_logger
from ..exchange.exceptions import (
    ExchangeError, RateLimitError, NetworkError, 
    ServerError, TimeoutError, CircuitBreakerError
)

# Configure logger
logger = get_structured_logger(__name__)


class PositionDataFetcher(metaclass=ThreadSafeSingleton):
    """
    A specialized class for fetching position data from Binance Futures API.
    
    Features:
    - Implements Singleton pattern to ensure only one instance exists
    - Caches responses to reduce API calls
    - Handles connection failures gracefully with retries
    - Normalizes position data into a standardized format
    - Supports both sync and async fetching methods
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = False,
        cache_ttl_seconds: int = 5
    ):
        """
        Initialize the Position Data Fetcher.
        
        Args:
            api_key: Binance API key (defaults to BINANCE_API_KEY env var)
            api_secret: Binance API secret (defaults to BINANCE_API_SECRET env var)
            testnet: Whether to use the testnet
            cache_ttl_seconds: How long to cache position data before refetching
        """
        # Load API credentials from environment if not provided
        self.api_key = api_key or os.environ.get('BINANCE_API_KEY')
        self.api_secret = api_secret or os.environ.get('BINANCE_API_SECRET')
        self.testnet = testnet
        
        # Initialize Binance API client
        self.client = BinanceApiClient(
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=self.testnet
        )
        
        # Cache settings
        self.cache_ttl = cache_ttl_seconds
        self._cached_positions = []
        self._last_fetch_time = 0
        
        logger.info("Initialized Position Data Fetcher", 
                   testnet=testnet, 
                   cache_ttl=cache_ttl_seconds)
    
    def _should_use_cache(self) -> bool:
        """
        Determine if cache should be used based on TTL.
        
        Returns:
            True if cache is valid, False if a refresh is needed
        """
        if not self._cached_positions:
            return False
            
        return (time.time() - self._last_fetch_time) < self.cache_ttl
    
    @retry(
        retry=retry_if_exception_type((NetworkError, TimeoutError, ServerError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def fetch_positions(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch position data with retry logic for resilience.
        
        Args:
            force_refresh: Whether to bypass cache and fetch fresh data
            
        Returns:
            List of standardized position dictionaries
            
        Raises:
            ExchangeError: If there's a persistent problem fetching positions
        """
        if not force_refresh and self._should_use_cache():
            logger.debug("Using cached position data")
            return self._cached_positions
        
        try:
            # Use the v2 position risk endpoint for better performance and data
            response = self.client.make_request(
                method="GET",
                endpoint="/fapi/v2/positionRisk",
                authenticated=True,
                rate_limit_category="trading"
            )
            
            # Transform and cache the response
            self._cached_positions = self._transform_position_data(response)
            self._last_fetch_time = time.time()
            
            logger.info(f"Successfully fetched position data", 
                       position_count=len(self._cached_positions))
            
            return self._cached_positions
            
        except CircuitBreakerError as e:
            logger.error("Circuit breaker triggered when fetching positions", error=str(e))
            if self._cached_positions:
                logger.warning("Returning stale cached positions due to circuit breaker")
                return self._cached_positions
            raise ExchangeError("Unable to fetch positions: circuit breaker open") from e
            
        except RateLimitError as e:
            logger.warning("Rate limit exceeded when fetching positions", error=str(e))
            if self._cached_positions:
                logger.warning("Returning stale cached positions due to rate limit")
                return self._cached_positions
            raise
            
        except (NetworkError, TimeoutError, ServerError) as e:
            # These will be retried by the retry decorator
            logger.warning(f"Temporary error fetching position data: {str(e)}")
            raise
            
        except Exception as e:
            logger.error(f"Unexpected error fetching position data: {str(e)}")
            if self._cached_positions:
                logger.warning("Returning stale cached positions due to error")
                return self._cached_positions
            raise ExchangeError(f"Failed to fetch positions: {str(e)}") from e
    
    async def fetch_positions_async(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Async implementation of position fetching with caching.
        
        Args:
            force_refresh: Whether to bypass cache and fetch fresh data
            
        Returns:
            List of standardized position dictionaries
            
        Raises:
            ExchangeError: If there's a persistent problem fetching positions
        """
        if not force_refresh and self._should_use_cache():
            logger.debug("Using cached position data")
            return self._cached_positions
        
        # Run the synchronous method in an executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.fetch_positions, force_refresh)
    
    def _transform_position_data(self, positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform raw API response into standardized format for risk analysis.
        
        Args:
            positions: Raw position data from Binance API
            
        Returns:
            Standardized position data
        """
        normalized = []
        
        for pos in positions:
            # Skip positions with zero amount
            if float(pos.get('positionAmt', 0)) == 0:
                continue
                
            # Extract and calculate position metrics
            position_amount = float(pos.get('positionAmt', 0))
            entry_price = float(pos.get('entryPrice', 0))
            mark_price = float(pos.get('markPrice', 0))
            notional_value = abs(position_amount * mark_price)
            
            # Create standardized position object
            normalized.append({
                'symbol': pos.get('symbol', ''),
                'position_amount': position_amount,
                'entry_price': entry_price,
                'mark_price': mark_price,
                'unreal_pnl': float(pos.get('unRealizedProfit', 0)),
                'liquidation_price': float(pos.get('liquidationPrice', 0)),
                'leverage': float(pos.get('leverage', 1)),
                'notional_value': notional_value,
                'margin_type': pos.get('marginType', ''),
                'isolated_margin': float(pos.get('isolatedMargin', 0)),
                'is_auto_add_margin': pos.get('isAutoAddMargin', 'false') == 'true',
                'position_side': pos.get('positionSide', 'BOTH'),
                'break_even_price': float(pos.get('breakEvenPrice', 0)),
                'timestamp': int(time.time() * 1000),
                'raw': pos  # Keep the raw data for reference
            })
        
        return normalized
    
    def get_position_by_symbol(self, symbol: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get position data for a specific symbol.
        
        Args:
            symbol: The trading pair symbol (e.g., "BTCUSDT")
            force_refresh: Whether to bypass cache and fetch fresh data
            
        Returns:
            Position data dictionary or None if no position exists
        """
        positions = self.fetch_positions(force_refresh=force_refresh)
        
        for position in positions:
            if position['symbol'] == symbol:
                return position
                
        return None
    
    def get_total_exposure(self, force_refresh: bool = False) -> float:
        """
        Calculate total notional exposure across all positions.
        
        Args:
            force_refresh: Whether to bypass cache and fetch fresh data
            
        Returns:
            Total notional value of all positions
        """
        positions = self.fetch_positions(force_refresh=force_refresh)
        return sum(position['notional_value'] for position in positions)
    
    def get_exposure_by_symbol(self, symbol: str, force_refresh: bool = False) -> float:
        """
        Get notional exposure for a specific symbol.
        
        Args:
            symbol: The trading pair symbol (e.g., "BTCUSDT")
            force_refresh: Whether to bypass cache and fetch fresh data
            
        Returns:
            Notional value of the position or 0 if no position exists
        """
        position = self.get_position_by_symbol(symbol, force_refresh=force_refresh)
        return position['notional_value'] if position else 0
    
    def get_pnl_by_symbol(self, symbol: str, force_refresh: bool = False) -> float:
        """
        Get unrealized PnL for a specific symbol.
        
        Args:
            symbol: The trading pair symbol (e.g., "BTCUSDT")
            force_refresh: Whether to bypass cache and fetch fresh data
            
        Returns:
            Unrealized PnL of the position or 0 if no position exists
        """
        position = self.get_position_by_symbol(symbol, force_refresh=force_refresh)
        return position['unreal_pnl'] if position else 0


# Simple test function
def test_position_fetcher():
    """Test the PositionDataFetcher with a simple example."""
    fetcher = PositionDataFetcher()
    try:
        positions = fetcher.fetch_positions()
        
        print(f"\nFound {len(positions)} active positions:")
        for pos in positions:
            print(f"{pos['symbol']}: {pos['position_amount']} contracts at ${pos['entry_price']:.2f}, "
                  f"Mark Price: ${pos['mark_price']:.2f}, "
                  f"PnL: ${pos['unreal_pnl']:.2f}, "
                  f"Liq. Price: ${pos['liquidation_price']:.2f}")
        
        total_exposure = fetcher.get_total_exposure()
        print(f"\nTotal exposure: ${total_exposure:.2f}")
        
    except Exception as e:
        print(f"Error testing position fetcher: {str(e)}")


if __name__ == "__main__":
    # Run the test when the script is executed directly
    test_position_fetcher() 