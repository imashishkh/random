"""
Market Conditions Monitor

This module provides a service that continuously monitors market conditions
and triggers circuit breakers when unusual conditions are detected.
"""

import logging
import threading
import time
from typing import Dict, List, Any, Optional, Set
import math
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from .risk.exposure_manager import (
    ExposureManager,
    CircuitBreaker,
    CircuitBreakerTrigger,
    Observer
)
from .risk.exposure_limits import (
    check_volatility_for_circuit_breaker,
    check_spread_for_circuit_breaker,
    check_drawdown_for_circuit_breaker,
    check_consecutive_losses_for_circuit_breaker
)

logger = logging.getLogger(__name__)


class MarketDataPoint:
    """Represents a snapshot of market data for analysis."""
    
    def __init__(self, symbol: str, timestamp: datetime):
        """
        Initialize a market data point.
        
        Args:
            symbol: Trading symbol
            timestamp: Time of this data point
        """
        self.symbol = symbol
        self.timestamp = timestamp
        self.price = None
        self.bid = None
        self.ask = None
        self.spread = None
        self.volume = None
        self.volatility = None
        self.atr = None
        self.is_anomaly = False


class MarketConditionMonitor:
    """
    Service that monitors market conditions for anomalies and triggers
    circuit breakers when unusual conditions are detected.
    """
    
    def __init__(self, 
                 exposure_manager: ExposureManager,
                 market_data_service,
                 update_interval_seconds: int = 5,
                 volatility_window: int = 20,
                 atr_period: int = 14):
        """
        Initialize the market condition monitor.
        
        Args:
            exposure_manager: Exposure manager to interact with
            market_data_service: Service to retrieve market data
            update_interval_seconds: How often to check market conditions
            volatility_window: Window for calculating volatility
            atr_period: Period for ATR calculation
        """
        self.exposure_manager = exposure_manager
        self.market_data_service = market_data_service
        self.update_interval_seconds = update_interval_seconds
        self.volatility_window = volatility_window
        self.atr_period = atr_period
        
        # Monitoring state
        self._running = False
        self._monitor_thread = None
        self._lock = threading.RLock()
        
        # Market data history
        self._market_data: Dict[str, List[MarketDataPoint]] = {}
        self._max_history_points = 100  # Maximum number of data points to keep per symbol
        
        # Tracked symbols
        self._symbols: Set[str] = set()
        
        # Market metrics
        self._volatility_history: Dict[str, List[float]] = {}
        self._spread_history: Dict[str, List[float]] = {}
        self._average_volatility: Dict[str, float] = {}
        self._average_spread: Dict[str, float] = {}
        
        # Anomaly detection thresholds
        self.volatility_threshold = 3.0  # Trigger at 3x normal volatility
        self.spread_threshold = 5.0      # Trigger at 5x normal spread
        self.price_gap_threshold = 0.03  # Trigger at 3% price gap
        
        logger.info("Initialized market condition monitor")
        
    def start(self) -> None:
        """Start the monitoring service."""
        with self._lock:
            if self._running:
                return
                
            self._running = True
            self._monitor_thread = threading.Thread(target=self._monitoring_loop)
            self._monitor_thread.daemon = True
            self._monitor_thread.start()
            
            logger.info("Market condition monitor started")
            
    def stop(self) -> None:
        """Stop the monitoring service."""
        with self._lock:
            self._running = False
            
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)
            
        logger.info("Market condition monitor stopped")
        
    def add_symbol(self, symbol: str) -> None:
        """
        Add a symbol to monitor.
        
        Args:
            symbol: Trading symbol to monitor
        """
        with self._lock:
            self._symbols.add(symbol)
            
            # Initialize data structures for this symbol
            if symbol not in self._market_data:
                self._market_data[symbol] = []
                
            if symbol not in self._volatility_history:
                self._volatility_history[symbol] = []
                
            if symbol not in self._spread_history:
                self._spread_history[symbol] = []
                
            logger.info(f"Added symbol to market monitor: {symbol}")
            
    def remove_symbol(self, symbol: str) -> None:
        """
        Remove a symbol from monitoring.
        
        Args:
            symbol: Trading symbol to remove
        """
        with self._lock:
            if symbol in self._symbols:
                self._symbols.remove(symbol)
                
            logger.info(f"Removed symbol from market monitor: {symbol}")
            
    def _monitoring_loop(self) -> None:
        """Main monitoring loop that runs in a separate thread."""
        while self._running:
            try:
                self._check_market_conditions()
            except Exception as e:
                logger.error(f"Error in market condition monitor: {str(e)}", exc_info=True)
                
            time.sleep(self.update_interval_seconds)
            
    def _check_market_conditions(self) -> None:
        """Check market conditions for all tracked symbols."""
        # Get a copy of the symbols to monitor
        with self._lock:
            symbols = list(self._symbols)
            
        # Skip if no symbols to monitor
        if not symbols:
            return
            
        # Check each symbol
        for symbol in symbols:
            try:
                self._check_symbol_conditions(symbol)
            except Exception as e:
                logger.error(f"Error checking conditions for {symbol}: {str(e)}", exc_info=True)
                
    def _check_symbol_conditions(self, symbol: str) -> None:
        """
        Check market conditions for a specific symbol.
        
        Args:
            symbol: Trading symbol to check
        """
        # Get current market data
        market_data = self._fetch_market_data(symbol)
        if not market_data:
            return
            
        # Update market data history
        with self._lock:
            self._market_data[symbol].append(market_data)
            
            # Trim history if needed
            if len(self._market_data[symbol]) > self._max_history_points:
                self._market_data[symbol] = self._market_data[symbol][-self._max_history_points:]
                
            # Update volatility history
            if market_data.volatility is not None:
                self._volatility_history[symbol].append(market_data.volatility)
                
                # Trim history if needed
                if len(self._volatility_history[symbol]) > self._max_history_points:
                    self._volatility_history[symbol] = self._volatility_history[symbol][-self._max_history_points:]
                    
                # Update average volatility
                if len(self._volatility_history[symbol]) >= self.volatility_window:
                    self._average_volatility[symbol] = np.mean(self._volatility_history[symbol][-self.volatility_window:])
                    
            # Update spread history
            if market_data.spread is not None:
                self._spread_history[symbol].append(market_data.spread)
                
                # Trim history if needed
                if len(self._spread_history[symbol]) > self._max_history_points:
                    self._spread_history[symbol] = self._spread_history[symbol][-self._max_history_points:]
                    
                # Update average spread
                if len(self._spread_history[symbol]) >= self.volatility_window:
                    self._average_spread[symbol] = np.mean(self._spread_history[symbol][-self.volatility_window:])
        
        # Check for anomalies
        self._check_for_anomalies(symbol, market_data)
        
    def _fetch_market_data(self, symbol: str) -> Optional[MarketDataPoint]:
        """
        Fetch current market data for a symbol.
        
        Args:
            symbol: Trading symbol to fetch data for
            
        Returns:
            MarketDataPoint with current data, or None on error
        """
        try:
            # Fetch data from the market data service
            raw_data = self.market_data_service.get_market_data(symbol)
            if not raw_data:
                return None
                
            # Create a new data point
            data_point = MarketDataPoint(symbol, datetime.now())
            
            # Extract data from the raw data
            data_point.price = raw_data.get("price", raw_data.get("close", None))
            data_point.bid = raw_data.get("bid", None)
            data_point.ask = raw_data.get("ask", None)
            
            # Calculate spread if bid/ask are available
            if data_point.bid is not None and data_point.ask is not None:
                data_point.spread = data_point.ask - data_point.bid
                
            data_point.volume = raw_data.get("volume", None)
            
            # Calculate volatility if we have enough history
            with self._lock:
                if symbol in self._market_data and len(self._market_data[symbol]) >= 2:
                    prices = [p.price for p in self._market_data[symbol] if p.price is not None]
                    if len(prices) >= 2:
                        # Calculate returns
                        returns = [prices[i] / prices[i-1] - 1 for i in range(1, len(prices))]
                        
                        # Calculate volatility (standard deviation of returns)
                        if len(returns) > 0:
                            data_point.volatility = np.std(returns)
                            
            # Get ATR if available
            data_point.atr = raw_data.get("atr", None)
            
            return data_point
            
        except Exception as e:
            logger.error(f"Error fetching market data for {symbol}: {str(e)}", exc_info=True)
            return None
            
    def _check_for_anomalies(self, symbol: str, data: MarketDataPoint) -> None:
        """
        Check for market anomalies and trigger circuit breakers if needed.
        
        Args:
            symbol: Trading symbol to check
            data: Current market data
        """
        # Skip if we don't have enough data
        with self._lock:
            if (symbol not in self._average_volatility or 
                symbol not in self._average_spread or
                len(self._market_data[symbol]) < 2):
                return
                
            avg_volatility = self._average_volatility.get(symbol, 0.0)
            avg_spread = self._average_spread.get(symbol, 0.0)
            
            # Get previous data point
            prev_data = self._market_data[symbol][-2] if len(self._market_data[symbol]) >= 2 else None
            
        # Check for volatility spike
        if data.volatility is not None and avg_volatility > 0:
            volatility_ratio = data.volatility / avg_volatility
            
            # Check against circuit breakers
            for breaker_name, breaker in self.exposure_manager._circuit_breakers.items():
                if breaker.definition.trigger_type == CircuitBreakerTrigger.VOLATILITY_SPIKE:
                    # Check if this breaker applies to this symbol
                    if "all" in breaker.definition.applies_to or symbol in breaker.definition.applies_to:
                        # Check if volatility exceeds threshold
                        if check_volatility_for_circuit_breaker(
                            symbol, data.volatility, avg_volatility, breaker
                        ):
                            logger.warning(
                                f"Volatility circuit breaker triggered for {symbol}: "
                                f"current={data.volatility:.6f}, avg={avg_volatility:.6f}, "
                                f"ratio={volatility_ratio:.2f}"
                            )
            
        # Check for spread widening
        if data.spread is not None and avg_spread > 0:
            spread_ratio = data.spread / avg_spread
            
            # Check against circuit breakers
            for breaker_name, breaker in self.exposure_manager._circuit_breakers.items():
                if breaker.definition.trigger_type == CircuitBreakerTrigger.SPREAD_WIDENING:
                    # Check if this breaker applies to this symbol
                    if "all" in breaker.definition.applies_to or symbol in breaker.definition.applies_to:
                        # Check if spread exceeds threshold
                        if check_spread_for_circuit_breaker(
                            symbol, data.spread, avg_spread, breaker
                        ):
                            logger.warning(
                                f"Spread circuit breaker triggered for {symbol}: "
                                f"current={data.spread:.6f}, avg={avg_spread:.6f}, "
                                f"ratio={spread_ratio:.2f}"
                            )
            
        # Check for price gap
        if prev_data and prev_data.price and data.price:
            price_change_pct = abs(data.price - prev_data.price) / prev_data.price
            
            # Check for large price gaps
            if price_change_pct >= self.price_gap_threshold:
                # Check against circuit breakers
                for breaker_name, breaker in self.exposure_manager._circuit_breakers.items():
                    if breaker.definition.trigger_type == CircuitBreakerTrigger.PRICE_GAP:
                        # Check if this breaker applies to this symbol
                        if "all" in breaker.definition.applies_to or symbol in breaker.definition.applies_to:
                            # Record the event
                            if breaker.record_event(price_change_pct):
                                logger.warning(
                                    f"Price gap circuit breaker triggered for {symbol}: "
                                    f"change={price_change_pct:.2%}, "
                                    f"current={data.price}, previous={prev_data.price}"
                                )
                
    def get_market_metrics(self, symbol: str) -> Dict[str, Any]:
        """
        Get current market metrics for a symbol.
        
        Args:
            symbol: Trading symbol to get metrics for
            
        Returns:
            Dict containing market metrics
        """
        with self._lock:
            if symbol not in self._market_data or not self._market_data[symbol]:
                return {}
                
            latest = self._market_data[symbol][-1]
            
            return {
                "symbol": symbol,
                "timestamp": latest.timestamp,
                "price": latest.price,
                "spread": latest.spread,
                "volatility": latest.volatility,
                "average_volatility": self._average_volatility.get(symbol, None),
                "average_spread": self._average_spread.get(symbol, None),
                "is_anomaly": latest.is_anomaly
            }
            
    def get_all_market_metrics(self) -> Dict[str, Dict[str, Any]]:
        """
        Get current market metrics for all tracked symbols.
        
        Returns:
            Dict mapping symbols to their metrics
        """
        metrics = {}
        
        with self._lock:
            for symbol in self._symbols:
                metrics[symbol] = self.get_market_metrics(symbol)
                
        return metrics 