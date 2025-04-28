"""
Market Conditions Provider Module

This module contains functionality for analyzing market data and determining
current market conditions for trading decision-making.
"""

import logging
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta

from .models import MarketConditions

class MarketConditionsProvider:
    """
    Provides market condition analysis for trading pairs.
    
    This class analyzes market data to determine:
    - Market regime (trending, ranging, volatile)
    - Volatility levels
    - Trend strength
    - Volume and liquidity metrics
    """
    
    def __init__(self, config: Dict[str, Any], price_data_provider: Any):
        """
        Initialize the market conditions provider.
        
        Args:
            config: Configuration dictionary
            price_data_provider: Object that provides price data for analysis
        """
        self.config = config
        self.price_data_provider = price_data_provider
        
        # Configure logging
        self.logger = logging.getLogger("market_conditions")
        self._configure_logging()
        
        # Caching for analyzed conditions
        self.condition_cache: Dict[str, Tuple[MarketConditions, datetime]] = {}
        
        # Cache expiry in seconds
        self.cache_expiry_seconds = config.get("cache_expiry_seconds", 300)  # 5 minutes by default
        
        # Regime classification parameters
        self.regime_settings = {
            "trend_threshold": config.get("trend_threshold", 0.6),
            "volatility_threshold": config.get("volatility_threshold", 0.7),
            "lookback_periods": config.get("regime_lookback_periods", 20)
        }
        
        self.logger.info("Market conditions provider initialized")
        
    def _configure_logging(self) -> None:
        """Configure logging for this provider."""
        log_level = self.config.get("log_level", "INFO").upper()
        self.logger.setLevel(getattr(logging, log_level))
        
    def get_market_conditions(self, trading_pair: str, 
                            timeframe: str = "1h") -> Optional[MarketConditions]:
        """
        Get current market conditions for a trading pair.
        
        Args:
            trading_pair: The trading pair to analyze
            timeframe: Timeframe for analysis (e.g., "1h", "4h", "1d")
            
        Returns:
            MarketConditions object or None if data unavailable
        """
        # Check cache first
        cache_key = f"{trading_pair}_{timeframe}"
        if cache_key in self.condition_cache:
            conditions, timestamp = self.condition_cache[cache_key]
            age = (datetime.now() - timestamp).total_seconds()
            
            # Return cached conditions if not expired
            if age < self.cache_expiry_seconds:
                return conditions
                
        # Get price data
        try:
            price_data = self._get_price_data(trading_pair, timeframe)
            if price_data is None or len(price_data) < self.regime_settings["lookback_periods"]:
                self.logger.warning("Insufficient price data for %s on %s timeframe", 
                                  trading_pair, timeframe)
                return None
                
            # Analyze market conditions
            conditions = self._analyze_market_conditions(trading_pair, price_data, timeframe)
            
            # Cache results
            self.condition_cache[cache_key] = (conditions, datetime.now())
            
            return conditions
            
        except Exception as e:
            self.logger.error("Error analyzing market conditions for %s: %s", 
                            trading_pair, str(e), exc_info=True)
            return None
            
    def _get_price_data(self, trading_pair: str, timeframe: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get price data from the data provider.
        
        Args:
            trading_pair: Trading pair to get data for
            timeframe: Timeframe for data
            
        Returns:
            List of price data points or None if unavailable
        """
        try:
            # Lookback periods plus buffer for calculations
            lookback = self.regime_settings["lookback_periods"] * 2
            
            # Delegate to price data provider
            return self.price_data_provider.get_price_data(
                trading_pair=trading_pair, 
                timeframe=timeframe,
                limit=lookback
            )
        except Exception as e:
            self.logger.error("Error fetching price data: %s", str(e))
            return None
            
    def _analyze_market_conditions(self, trading_pair: str, 
                                 price_data: List[Dict[str, Any]],
                                 timeframe: str) -> MarketConditions:
        """
        Analyze market conditions from price data.
        
        Args:
            trading_pair: Trading pair being analyzed
            price_data: List of price data points
            timeframe: Timeframe of the data
            
        Returns:
            MarketConditions object with analysis results
        """
        # Extract OHLCV data
        closes = np.array([p["close"] for p in price_data])
        highs = np.array([p["high"] for p in price_data])
        lows = np.array([p["low"] for p in price_data])
        volumes = np.array([p["volume"] for p in price_data])
        
        # Calculate volatility (normalized ATR)
        atr = self._calculate_atr(highs, lows, closes)
        normalized_atr = atr / closes[-1]
        
        # Calculate trend strength
        trend_strength = self._calculate_trend_strength(closes)
        
        # Determine market regime
        regime = self._determine_market_regime(trend_strength, normalized_atr)
        
        # Calculate volume profile
        volume_metric = self._calculate_volume_metric(volumes)
        
        # Calculate liquidity estimate
        liquidity = self._estimate_liquidity(highs, lows, volumes)
        
        # Create and return market conditions
        return MarketConditions(
            trading_pair=trading_pair,
            timestamp=datetime.now(),
            regime=regime,
            volatility=normalized_atr,
            trend_strength=trend_strength,
            volume=volume_metric,
            liquidity=liquidity
        )
        
    def _calculate_atr(self, highs: np.ndarray, lows: np.ndarray, 
                      closes: np.ndarray) -> float:
        """
        Calculate Average True Range (ATR).
        
        Args:
            highs: Array of high prices
            lows: Array of low prices
            closes: Array of close prices
            
        Returns:
            ATR value
        """
        # Need at least 2 bars for ATR calculation
        if len(closes) < 2:
            return 0.0
            
        # Calculate true ranges
        prev_closes = np.roll(closes, 1)
        prev_closes[0] = closes[0]
        
        ranges1 = highs - lows  # Current high - current low
        ranges2 = np.abs(highs - prev_closes)  # Current high - previous close
        ranges3 = np.abs(lows - prev_closes)  # Current low - previous close
        
        true_ranges = np.maximum(ranges1, np.maximum(ranges2, ranges3))
        
        # Use simple moving average for ATR
        atr_periods = min(14, len(true_ranges))
        atr = np.mean(true_ranges[-atr_periods:])
        
        return atr
        
    def _calculate_trend_strength(self, closes: np.ndarray) -> float:
        """
        Calculate trend strength using linear regression R-squared.
        
        Args:
            closes: Array of close prices
            
        Returns:
            Trend strength value (0-1)
        """
        # Use only recent prices for trend calculation
        lookback = min(self.regime_settings["lookback_periods"], len(closes))
        recent_prices = closes[-lookback:]
        
        # Create x-axis (time)
        x = np.arange(len(recent_prices))
        
        # Calculate linear regression
        try:
            slope, intercept = np.polyfit(x, recent_prices, 1)
            
            # Calculate R-squared
            y_hat = x * slope + intercept
            y_bar = np.mean(recent_prices)
            
            ssreg = np.sum((y_hat - y_bar) ** 2)
            sstot = np.sum((recent_prices - y_bar) ** 2)
            
            r_squared = ssreg / sstot if sstot > 0 else 0
            
            # Direction-aware trend strength
            trend_strength = r_squared * (1 if slope > 0 else -1)
            
            return trend_strength
            
        except Exception:
            # Handle numerical issues
            return 0.0
            
    def _determine_market_regime(self, trend_strength: float, volatility: float) -> str:
        """
        Determine market regime based on trend strength and volatility.
        
        Args:
            trend_strength: Calculated trend strength
            volatility: Calculated volatility
            
        Returns:
            Market regime string
        """
        # Get thresholds from settings
        trend_threshold = self.regime_settings["trend_threshold"]
        volatility_threshold = self.regime_settings["volatility_threshold"]
        
        # Determine regime
        abs_trend = abs(trend_strength)
        
        if volatility > volatility_threshold:
            regime = "volatile"
        elif abs_trend > trend_threshold:
            regime = "trending"
        else:
            regime = "ranging"
            
        return regime
        
    def _calculate_volume_metric(self, volumes: np.ndarray) -> float:
        """
        Calculate volume metric compared to recent average.
        
        Args:
            volumes: Array of volume data
            
        Returns:
            Volume metric (ratio of recent to average)
        """
        if len(volumes) < 10:
            return 1.0
            
        # Recent volume (average of last 3 periods)
        recent_volume = np.mean(volumes[-3:])
        
        # Historical volume (average of previous periods)
        hist_lookback = min(20, len(volumes) - 3)
        if hist_lookback <= 0:
            return 1.0
            
        hist_volume = np.mean(volumes[-hist_lookback-3:-3])
        
        # Avoid division by zero
        if hist_volume == 0:
            return 1.0
            
        # Return ratio of recent to historical
        return recent_volume / hist_volume
        
    def _estimate_liquidity(self, highs: np.ndarray, lows: np.ndarray, 
                          volumes: np.ndarray) -> float:
        """
        Estimate market liquidity using price range and volume.
        
        Args:
            highs: Array of high prices
            lows: Array of low prices
            volumes: Array of volumes
            
        Returns:
            Liquidity estimate (0-1 scale)
        """
        if len(highs) < 5:
            return 0.5  # Default for insufficient data
            
        # Calculate price ranges
        price_ranges = highs - lows
        
        # Calculate volume-to-range ratio
        # Higher ratio means more volume per price movement, indicating higher liquidity
        volume_range_ratios = volumes[-5:] / (price_ranges[-5:] + 0.00001)  # Avoid div by zero
        
        # Normalize to 0-1 scale using a sigmoid-like function
        # This scales the raw values to something more manageable
        mean_ratio = np.mean(volume_range_ratios)
        liquidity = 1 / (1 + np.exp(-0.1 * (mean_ratio - 50)))
        
        return liquidity 