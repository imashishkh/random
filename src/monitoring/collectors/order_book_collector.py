"""
Order Book Collector module.

This module contains the OrderBookCollector class which is responsible for
collecting metrics related to order book data quality, depth, and spread
across multiple trading pairs and exchanges.
"""

import logging
import time
from typing import Dict, List, Optional, Tuple
import statistics
from datetime import datetime, timedelta

from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, HistogramMetricFamily

from .base_collector import BaseCollector

logger = logging.getLogger(__name__)

class OrderBookCollector(BaseCollector):
    """
    Collector for order book metrics.
    
    Collects metrics related to order book quality, depth, and spread
    for multiple trading pairs across different exchanges.
    """
    
    def __init__(
        self,
        exchanges: Optional[List[str]] = None,
        pairs: Optional[List[str]] = None,
        depth_levels: List[int] = [5, 10, 20, 50, 100],
        collection_interval: int = 15
    ):
        """
        Initialize the OrderBookCollector.
        
        Args:
            exchanges: List of exchanges to monitor (default: ["binance", "kucoin", "okx", "bybit"])
            pairs: List of trading pairs to monitor (default: ["BTC/USDT", "ETH/USDT", "XRP/USDT"])
            depth_levels: Order book depth levels to track (default: [5, 10, 20, 50, 100])
            collection_interval: How often to collect metrics in seconds (default: 15)
        """
        super().__init__(collection_interval=collection_interval)
        
        self.exchanges = exchanges or ["binance", "kucoin", "okx", "bybit"]
        self.pairs = pairs or ["BTC/USDT", "ETH/USDT", "XRP/USDT"]
        self.depth_levels = depth_levels
        
        # Track order book updates
        self.last_update_time: Dict[str, Dict[str, datetime]] = {}
        for exchange in self.exchanges:
            self.last_update_time[exchange] = {}
            for pair in self.pairs:
                self.last_update_time[exchange][pair] = datetime.now() - timedelta(hours=1)
        
        # Track order book depth
        self.order_book_depths: Dict[str, Dict[str, Dict[str, float]]] = {}
        for exchange in self.exchanges:
            self.order_book_depths[exchange] = {}
            for pair in self.pairs:
                self.order_book_depths[exchange][pair] = {
                    "bids": {level: 0.0 for level in self.depth_levels},
                    "asks": {level: 0.0 for level in self.depth_levels}
                }
        
        # Track spread information
        self.spreads: Dict[str, Dict[str, List[float]]] = {}
        for exchange in self.exchanges:
            self.spreads[exchange] = {}
            for pair in self.pairs:
                self.spreads[exchange][pair] = []
        
        # Track data quality metrics
        self.update_counts: Dict[str, Dict[str, int]] = {}
        self.error_counts: Dict[str, Dict[str, int]] = {}
        for exchange in self.exchanges:
            self.update_counts[exchange] = {pair: 0 for pair in self.pairs}
            self.error_counts[exchange] = {pair: 0 for pair in self.pairs}
        
        logger.info(f"Initialized OrderBookCollector for {len(self.exchanges)} exchanges and {len(self.pairs)} pairs")
    
    def collect_metrics(self):
        """Collect all order book related metrics."""
        try:
            metrics = []
            
            # Freshness metrics
            freshness = GaugeMetricFamily(
                'orderbook_freshness_seconds',
                'Time since last order book update in seconds',
                labels=['exchange', 'pair']
            )
            
            # Spread metrics
            spread = GaugeMetricFamily(
                'orderbook_spread_percentage',
                'Bid-ask spread as a percentage of mid price',
                labels=['exchange', 'pair']
            )
            
            # Depth metrics
            depth = GaugeMetricFamily(
                'orderbook_depth_volume',
                'Volume available at a specific depth level',
                labels=['exchange', 'pair', 'side', 'level']
            )
            
            # Imbalance metrics
            imbalance = GaugeMetricFamily(
                'orderbook_imbalance_ratio',
                'Ratio of bid volume to ask volume at a specific depth level',
                labels=['exchange', 'pair', 'level']
            )
            
            # Update count metrics
            updates = CounterMetricFamily(
                'orderbook_updates_total',
                'Total number of order book updates received',
                labels=['exchange', 'pair']
            )
            
            # Error count metrics
            errors = CounterMetricFamily(
                'orderbook_errors_total',
                'Total number of order book errors encountered',
                labels=['exchange', 'pair']
            )
            
            # Collect the metrics
            self._collect_freshness_metrics(freshness)
            self._collect_spread_metrics(spread)
            self._collect_depth_metrics(depth)
            self._collect_imbalance_metrics(imbalance)
            self._collect_update_metrics(updates)
            self._collect_error_metrics(errors)
            
            metrics.extend([freshness, spread, depth, imbalance, updates, errors])
            
            return metrics
        except Exception as e:
            logger.error(f"Error collecting order book metrics: {str(e)}")
            return []
    
    def _collect_freshness_metrics(self, freshness_metric):
        """
        Collect order book update freshness metrics.
        
        Args:
            freshness_metric: The Prometheus metric to populate
        """
        now = datetime.now()
        
        for exchange in self.exchanges:
            for pair in self.pairs:
                last_update = self.last_update_time[exchange][pair]
                freshness_seconds = (now - last_update).total_seconds()
                freshness_metric.add_metric([exchange, pair], freshness_seconds)
    
    def _collect_spread_metrics(self, spread_metric):
        """
        Collect order book spread metrics.
        
        Args:
            spread_metric: The Prometheus metric to populate
        """
        for exchange in self.exchanges:
            for pair in self.pairs:
                spread_values = self.spreads[exchange][pair]
                if spread_values:
                    # Use the most recent spread value
                    spread_percentage = spread_values[-1]
                    spread_metric.add_metric([exchange, pair], spread_percentage)
    
    def _collect_depth_metrics(self, depth_metric):
        """
        Collect order book depth metrics.
        
        Args:
            depth_metric: The Prometheus metric to populate
        """
        for exchange in self.exchanges:
            for pair in self.pairs:
                for side in ["bids", "asks"]:
                    for level in self.depth_levels:
                        volume = self.order_book_depths[exchange][pair][side].get(level, 0.0)
                        depth_metric.add_metric(
                            [exchange, pair, side, str(level)], 
                            volume
                        )
    
    def _collect_imbalance_metrics(self, imbalance_metric):
        """
        Collect order book imbalance metrics.
        
        Args:
            imbalance_metric: The Prometheus metric to populate
        """
        for exchange in self.exchanges:
            for pair in self.pairs:
                for level in self.depth_levels:
                    bid_volume = self.order_book_depths[exchange][pair]["bids"].get(level, 0.0)
                    ask_volume = self.order_book_depths[exchange][pair]["asks"].get(level, 0.0)
                    
                    # Calculate imbalance ratio (bid volume / ask volume)
                    if ask_volume > 0:
                        imbalance_ratio = bid_volume / ask_volume
                    else:
                        imbalance_ratio = 0.0 if bid_volume == 0 else float('inf')
                    
                    # Cap extreme values
                    if imbalance_ratio > 1000:
                        imbalance_ratio = 1000.0
                    
                    imbalance_metric.add_metric(
                        [exchange, pair, str(level)],
                        imbalance_ratio
                    )
    
    def _collect_update_metrics(self, updates_metric):
        """
        Collect order book update count metrics.
        
        Args:
            updates_metric: The Prometheus metric to populate
        """
        for exchange in self.exchanges:
            for pair in self.pairs:
                updates_metric.add_metric(
                    [exchange, pair],
                    self.update_counts[exchange][pair]
                )
    
    def _collect_error_metrics(self, errors_metric):
        """
        Collect order book error count metrics.
        
        Args:
            errors_metric: The Prometheus metric to populate
        """
        for exchange in self.exchanges:
            for pair in self.pairs:
                errors_metric.add_metric(
                    [exchange, pair],
                    self.error_counts[exchange][pair]
                )
    
    def record_orderbook_update(
        self, 
        exchange: str, 
        pair: str, 
        bids: List[Tuple[float, float]], 
        asks: List[Tuple[float, float]]
    ):
        """
        Record an order book update from an exchange.
        
        Args:
            exchange: Name of the exchange
            pair: Trading pair
            bids: List of (price, volume) tuples for bids
            asks: List of (price, volume) tuples for asks
        """
        if exchange not in self.exchanges:
            logger.warning(f"Ignoring update for unknown exchange: {exchange}")
            return
        
        if pair not in self.pairs:
            logger.warning(f"Ignoring update for unknown pair: {pair}")
            return
        
        try:
            # Update last update time
            self.last_update_time[exchange][pair] = datetime.now()
            
            # Increment update counter
            self.update_counts[exchange][pair] += 1
            
            # Process depth information
            self._process_depth_data(exchange, pair, bids, asks)
            
            # Calculate and record spread
            if bids and asks:
                best_bid = bids[0][0]  # Highest bid price
                best_ask = asks[0][0]  # Lowest ask price
                
                if best_bid > 0 and best_ask > 0 and best_ask > best_bid:
                    mid_price = (best_bid + best_ask) / 2
                    spread_value = (best_ask - best_bid) / mid_price * 100  # Spread as percentage
                    
                    # Keep only the last 100 spread values
                    self.spreads[exchange][pair].append(spread_value)
                    if len(self.spreads[exchange][pair]) > 100:
                        self.spreads[exchange][pair] = self.spreads[exchange][pair][-100:]
                else:
                    # Invalid order book state (crossed book, etc.)
                    self.record_orderbook_error(exchange, pair, "Invalid order book (crossed or negative prices)")
            else:
                self.record_orderbook_error(exchange, pair, "Empty order book")
        
        except Exception as e:
            logger.error(f"Error processing order book update for {exchange} {pair}: {str(e)}")
            self.record_orderbook_error(exchange, pair, str(e))
    
    def _process_depth_data(
        self, 
        exchange: str, 
        pair: str, 
        bids: List[Tuple[float, float]], 
        asks: List[Tuple[float, float]]
    ):
        """
        Process order book depth data for different levels.
        
        Args:
            exchange: Name of the exchange
            pair: Trading pair
            bids: List of (price, volume) tuples for bids
            asks: List of (price, volume) tuples for asks
        """
        # Clear previous depth data
        for level in self.depth_levels:
            self.order_book_depths[exchange][pair]["bids"][level] = 0.0
            self.order_book_depths[exchange][pair]["asks"][level] = 0.0
        
        # Calculate cumulative volume for bids at different depth levels
        for level in self.depth_levels:
            # Process only up to the available depth
            level_bids = bids[:min(level, len(bids))]
            level_asks = asks[:min(level, len(asks))]
            
            bid_volume = sum(volume for _, volume in level_bids)
            ask_volume = sum(volume for _, volume in level_asks)
            
            self.order_book_depths[exchange][pair]["bids"][level] = bid_volume
            self.order_book_depths[exchange][pair]["asks"][level] = ask_volume
    
    def record_orderbook_error(self, exchange: str, pair: str, error_message: str):
        """
        Record an error in order book processing.
        
        Args:
            exchange: Name of the exchange
            pair: Trading pair
            error_message: Description of the error
        """
        if exchange not in self.exchanges:
            logger.warning(f"Ignoring error for unknown exchange: {exchange}")
            return
        
        if pair not in self.pairs:
            logger.warning(f"Ignoring error for unknown pair: {pair}")
            return
        
        # Increment error counter
        self.error_counts[exchange][pair] += 1
        
        # Log the error
        logger.error(f"Order book error for {exchange} {pair}: {error_message}")
    
    def add_exchange(self, exchange: str):
        """
        Add a new exchange to monitor.
        
        Args:
            exchange: Name of the exchange to add
        """
        if exchange in self.exchanges:
            logger.warning(f"Exchange {exchange} is already being monitored")
            return
        
        self.exchanges.append(exchange)
        
        # Initialize data structures for the new exchange
        self.last_update_time[exchange] = {}
        self.order_book_depths[exchange] = {}
        self.spreads[exchange] = {}
        self.update_counts[exchange] = {}
        self.error_counts[exchange] = {}
        
        for pair in self.pairs:
            self.last_update_time[exchange][pair] = datetime.now() - timedelta(hours=1)
            self.order_book_depths[exchange][pair] = {
                "bids": {level: 0.0 for level in self.depth_levels},
                "asks": {level: 0.0 for level in self.depth_levels}
            }
            self.spreads[exchange][pair] = []
            self.update_counts[exchange][pair] = 0
            self.error_counts[exchange][pair] = 0
        
        logger.info(f"Added exchange {exchange} to order book monitoring")
    
    def add_pair(self, pair: str):
        """
        Add a new trading pair to monitor.
        
        Args:
            pair: Trading pair to add (e.g., "BTC/USDT")
        """
        if pair in self.pairs:
            logger.warning(f"Pair {pair} is already being monitored")
            return
        
        self.pairs.append(pair)
        
        # Initialize data structures for the new pair
        for exchange in self.exchanges:
            self.last_update_time[exchange][pair] = datetime.now() - timedelta(hours=1)
            self.order_book_depths[exchange][pair] = {
                "bids": {level: 0.0 for level in self.depth_levels},
                "asks": {level: 0.0 for level in self.depth_levels}
            }
            self.spreads[exchange][pair] = []
            self.update_counts[exchange][pair] = 0
            self.error_counts[exchange][pair] = 0
        
        logger.info(f"Added pair {pair} to order book monitoring")
    
    def get_spread_statistics(self, exchange: str, pair: str) -> Dict[str, float]:
        """
        Get spread statistics for a specific exchange and pair.
        
        Args:
            exchange: Name of the exchange
            pair: Trading pair
            
        Returns:
            Dictionary with spread statistics including mean, median, min, max
        """
        if exchange not in self.exchanges or pair not in self.pairs:
            return {}
        
        spread_values = self.spreads[exchange][pair]
        if not spread_values:
            return {
                "mean": 0.0,
                "median": 0.0,
                "min": 0.0,
                "max": 0.0,
                "count": 0
            }
        
        return {
            "mean": statistics.mean(spread_values),
            "median": statistics.median(spread_values),
            "min": min(spread_values),
            "max": max(spread_values),
            "count": len(spread_values)
        } 