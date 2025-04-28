"""
Market Data Collector module.

This module contains the MarketDataCollector class which is responsible for
collecting metrics related to market data feeds including data quality, 
latency, and availability metrics from various data providers.
"""

import logging
import time
from typing import Dict, List, Optional, Any

from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, HistogramMetricFamily

from .base_collector import BaseCollector

logger = logging.getLogger(__name__)

class MarketDataCollector(BaseCollector):
    """
    Collector for market data feed metrics.
    
    Collects metrics related to market data quality, latency, and availability
    from different market data providers.
    """
    
    def __init__(
        self, 
        data_providers: List[str] = None,
        collection_interval: int = 30
    ):
        """
        Initialize the MarketDataCollector.
        
        Args:
            data_providers: List of market data provider names to monitor
            collection_interval: How often to collect metrics in seconds (default: 30)
        """
        super().__init__(collection_interval=collection_interval)
        self.data_providers = data_providers or ["binance", "kucoin", "okx", "bybit"]
        self.provider_stats: Dict[str, Dict[str, Any]] = {
            provider: {
                "last_update_time": None,
                "update_count": 0,
                "error_count": 0,
                "latencies": [],
            }
            for provider in self.data_providers
        }
        
        # Initialize metric values
        self._last_data_update_time = {}
        self._data_update_count = {}
        self._data_error_count = {}
        
        logger.info(f"Initialized MarketDataCollector for providers: {self.data_providers}")
        
    def collect_metrics(self):
        """Collect all market data related metrics."""
        try:
            metrics = []
            
            # Create data freshness metric
            freshness = GaugeMetricFamily(
                'market_data_freshness_seconds',
                'Time since the last market data update in seconds',
                labels=['provider', 'data_type']
            )
            
            # Create data update counter metric
            updates = CounterMetricFamily(
                'market_data_updates_total',
                'Total number of market data updates',
                labels=['provider', 'data_type']
            )
            
            # Create data error counter metric
            errors = CounterMetricFamily(
                'market_data_errors_total',
                'Total number of market data errors',
                labels=['provider', 'data_type', 'error_type']
            )
            
            # Create data latency histogram metric
            latency = HistogramMetricFamily(
                'market_data_latency_seconds',
                'Market data feed latency in seconds',
                labels=['provider', 'data_type']
            )
            
            # Create symbols count metric
            symbols = GaugeMetricFamily(
                'market_data_available_symbols',
                'Number of symbols available from the data provider',
                labels=['provider']
            )
            
            # Create market coverage metric
            coverage = GaugeMetricFamily(
                'market_data_coverage_percent',
                'Percentage of required symbols covered by the data provider',
                labels=['provider']
            )

            # Collect actual metrics
            self._collect_freshness_metrics(freshness)
            self._collect_update_metrics(updates)
            self._collect_error_metrics(errors)
            self._collect_latency_metrics(latency)
            self._collect_symbols_metrics(symbols)
            self._collect_coverage_metrics(coverage)
            
            metrics.extend([freshness, updates, errors, latency, symbols, coverage])
            
            return metrics
        except Exception as e:
            logger.error(f"Error collecting market data metrics: {str(e)}")
            return []
    
    def _collect_freshness_metrics(self, freshness_metric):
        """
        Collect freshness metrics for market data feeds.
        
        Args:
            freshness_metric: The Prometheus metric to populate
        """
        current_time = time.time()
        for provider in self.data_providers:
            for data_type in ["tickers", "orderbooks", "trades"]:
                last_update = self._last_data_update_time.get(f"{provider}_{data_type}")
                if last_update is not None:
                    freshness = current_time - last_update
                    freshness_metric.add_metric([provider, data_type], freshness)
    
    def _collect_update_metrics(self, updates_metric):
        """
        Collect update count metrics for market data feeds.
        
        Args:
            updates_metric: The Prometheus metric to populate
        """
        for provider in self.data_providers:
            for data_type in ["tickers", "orderbooks", "trades"]:
                count = self._data_update_count.get(f"{provider}_{data_type}", 0)
                updates_metric.add_metric([provider, data_type], count)
    
    def _collect_error_metrics(self, errors_metric):
        """
        Collect error metrics for market data feeds.
        
        Args:
            errors_metric: The Prometheus metric to populate
        """
        for provider in self.data_providers:
            for data_type in ["tickers", "orderbooks", "trades"]:
                for error_type in ["connection", "timeout", "data_format", "rate_limit"]:
                    count = self._data_error_count.get(f"{provider}_{data_type}_{error_type}", 0)
                    errors_metric.add_metric([provider, data_type, error_type], count)
    
    def _collect_latency_metrics(self, latency_metric):
        """
        Collect latency metrics for market data feeds.
        
        Args:
            latency_metric: The Prometheus metric to populate
        """
        for provider in self.data_providers:
            for data_type in ["tickers", "orderbooks", "trades"]:
                # We would have actual latency data in a real implementation
                # Here we just add sample buckets and sum values
                latency_metric.add_metric(
                    [provider, data_type],
                    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
                    sum_value=0.0,  # Replace with actual sum
                    count_value=0   # Replace with actual count
                )
    
    def _collect_symbols_metrics(self, symbols_metric):
        """
        Collect metrics for the number of available symbols per provider.
        
        Args:
            symbols_metric: The Prometheus metric to populate
        """
        # In a real implementation, these would be actual counts
        sample_counts = {
            "binance": 350,
            "kucoin": 420,
            "okx": 380,
            "bybit": 310
        }
        
        for provider in self.data_providers:
            count = sample_counts.get(provider, 0)
            symbols_metric.add_metric([provider], count)
    
    def _collect_coverage_metrics(self, coverage_metric):
        """
        Collect metrics for the coverage of required symbols.
        
        Args:
            coverage_metric: The Prometheus metric to populate
        """
        # In a real implementation, these would be calculated values
        sample_coverage = {
            "binance": 98.5,
            "kucoin": 92.0,
            "okx": 95.5,
            "bybit": 90.0
        }
        
        for provider in self.data_providers:
            coverage = sample_coverage.get(provider, 0)
            coverage_metric.add_metric([provider], coverage)
    
    def record_update(self, provider: str, data_type: str, latency: float = None):
        """
        Record a successful market data update.
        
        Args:
            provider: The name of the data provider
            data_type: The type of data (tickers, orderbooks, trades)
            latency: The observed latency in seconds
        """
        if provider not in self.data_providers:
            logger.warning(f"Unknown provider {provider} in record_update")
            return
            
        key = f"{provider}_{data_type}"
        current_time = time.time()
        
        # Update last update time
        self._last_data_update_time[key] = current_time
        
        # Increment update count
        self._data_update_count[key] = self._data_update_count.get(key, 0) + 1
        
        # Store latency
        if latency is not None:
            self.provider_stats[provider]["latencies"].append(latency)
            # Keep only the last 100 latency measurements
            if len(self.provider_stats[provider]["latencies"]) > 100:
                self.provider_stats[provider]["latencies"] = self.provider_stats[provider]["latencies"][-100:]
    
    def record_error(self, provider: str, data_type: str, error_type: str):
        """
        Record a market data error.
        
        Args:
            provider: The name of the data provider
            data_type: The type of data (tickers, orderbooks, trades)
            error_type: The type of error encountered
        """
        if provider not in self.data_providers:
            logger.warning(f"Unknown provider {provider} in record_error")
            return
            
        key = f"{provider}_{data_type}_{error_type}"
        
        # Increment error count
        self._data_error_count[key] = self._data_error_count.get(key, 0) + 1
        
        # Update provider stats
        self.provider_stats[provider]["error_count"] += 1 