"""
Market data metrics collector for Prometheus.

This module provides a collector for market data metrics like prices,
spreads, and volatility indicators.
"""

import logging
from typing import Dict, List, Any, Set

from prometheus_client.core import GaugeMetricFamily

from .collectors.base_collector import BaseCollector
from ...market_data.market_data_service import MarketDataService

logger = logging.getLogger(__name__)


class MarketCollector(BaseCollector):
    """
    Collector for market data metrics.
    
    This collector gathers metrics about market data, including:
    - Current prices (bid/ask)
    - Spreads
    - Volatility indicators
    - Data quality metrics
    """
    
    def __init__(self, market_data_service: MarketDataService, 
                 symbols: Set[str], collection_interval: float = 10.0):
        """
        Initialize the market data collector.
        
        Args:
            market_data_service: Service for accessing market data
            symbols: Set of symbols to monitor
            collection_interval: Interval in seconds between metric collection
        """
        super().__init__(collection_interval=collection_interval)
        self.market_data_service = market_data_service
        self.symbols = symbols
    
    def collect_metrics(self) -> List[Any]:
        """
        Collect market data metrics.
        
        Returns:
            List of metrics for Prometheus
        """
        metrics = []
        
        # Current price metrics
        metrics.extend(self._collect_price_metrics())
        
        # Spread metrics
        metrics.extend(self._collect_spread_metrics())
        
        # Volatility metrics
        metrics.extend(self._collect_volatility_metrics())
        
        # Data quality metrics
        metrics.extend(self._collect_data_quality_metrics())
        
        # Add collector's own metrics
        metrics.extend(self.get_collector_metrics())
        
        return metrics
    
    def _collect_price_metrics(self) -> List[Any]:
        """
        Collect current price metrics.
        
        Returns:
            List of price metrics
        """
        metrics = []
        
        # Bid price
        bid_gauge = GaugeMetricFamily(
            'forex_bid_price',
            'Current bid price',
            labels=['symbol']
        )
        
        # Ask price
        ask_gauge = GaugeMetricFamily(
            'forex_ask_price',
            'Current ask price',
            labels=['symbol']
        )
        
        # Mid price
        mid_gauge = GaugeMetricFamily(
            'forex_mid_price',
            'Current mid price (bid+ask)/2',
            labels=['symbol']
        )
        
        # Collect prices for each symbol
        for symbol in self.symbols:
            try:
                quote = self.market_data_service.get_current_quote(symbol)
                
                if quote:
                    bid_gauge.add_metric([symbol], quote.bid)
                    ask_gauge.add_metric([symbol], quote.ask)
                    mid_price = (quote.bid + quote.ask) / 2
                    mid_gauge.add_metric([symbol], mid_price)
            except Exception as e:
                logger.error(f"Error collecting price for {symbol}: {str(e)}")
        
        metrics.append(bid_gauge)
        metrics.append(ask_gauge)
        metrics.append(mid_gauge)
        
        return metrics
    
    def _collect_spread_metrics(self) -> List[Any]:
        """
        Collect spread metrics.
        
        Returns:
            List of spread metrics
        """
        metrics = []
        
        # Raw spread in price points
        raw_spread_gauge = GaugeMetricFamily(
            'forex_raw_spread',
            'Current raw spread (ask-bid)',
            labels=['symbol']
        )
        
        # Spread in pips
        pip_spread_gauge = GaugeMetricFamily(
            'forex_pip_spread',
            'Current spread in pips',
            labels=['symbol']
        )
        
        # Collect spreads for each symbol
        for symbol in self.symbols:
            try:
                quote = self.market_data_service.get_current_quote(symbol)
                
                if quote:
                    # Raw spread
                    raw_spread = quote.ask - quote.bid
                    raw_spread_gauge.add_metric([symbol], raw_spread)
                    
                    # Pip spread (depends on the instrument precision)
                    symbol_info = self.market_data_service.get_symbol_info(symbol)
                    pip_size = 0.0001 if symbol_info.digits == 4 else 0.00001
                    pip_spread = raw_spread / pip_size
                    pip_spread_gauge.add_metric([symbol], pip_spread)
            except Exception as e:
                logger.error(f"Error collecting spread for {symbol}: {str(e)}")
        
        metrics.append(raw_spread_gauge)
        metrics.append(pip_spread_gauge)
        
        return metrics
    
    def _collect_volatility_metrics(self) -> List[Any]:
        """
        Collect volatility metrics.
        
        Returns:
            List of volatility metrics
        """
        metrics = []
        
        # Daily range
        daily_range_gauge = GaugeMetricFamily(
            'forex_daily_range',
            'Daily price range (high-low)',
            labels=['symbol']
        )
        
        # Daily range in pips
        daily_range_pips_gauge = GaugeMetricFamily(
            'forex_daily_range_pips',
            'Daily price range in pips',
            labels=['symbol']
        )
        
        # Hourly volatility
        hourly_vol_gauge = GaugeMetricFamily(
            'forex_hourly_volatility',
            'Average hourly volatility as standard deviation',
            labels=['symbol']
        )
        
        # Collect volatility metrics for each symbol
        for symbol in self.symbols:
            try:
                # Get daily high/low
                daily_data = self.market_data_service.get_daily_stats(symbol)
                
                if daily_data:
                    # Daily range
                    daily_range = daily_data.high - daily_data.low
                    daily_range_gauge.add_metric([symbol], daily_range)
                    
                    # Daily range in pips
                    symbol_info = self.market_data_service.get_symbol_info(symbol)
                    pip_size = 0.0001 if symbol_info.digits == 4 else 0.00001
                    daily_range_pips = daily_range / pip_size
                    daily_range_pips_gauge.add_metric([symbol], daily_range_pips)
                
                # Get hourly volatility
                hourly_vol = self.market_data_service.get_hourly_volatility(symbol)
                if hourly_vol is not None:
                    hourly_vol_gauge.add_metric([symbol], hourly_vol)
                
            except Exception as e:
                logger.error(f"Error collecting volatility for {symbol}: {str(e)}")
        
        metrics.append(daily_range_gauge)
        metrics.append(daily_range_pips_gauge)
        metrics.append(hourly_vol_gauge)
        
        return metrics
    
    def _collect_data_quality_metrics(self) -> List[Any]:
        """
        Collect data quality metrics.
        
        Returns:
            List of data quality metrics
        """
        metrics = []
        
        # Quote age (seconds since last update)
        quote_age_gauge = GaugeMetricFamily(
            'forex_quote_age_seconds',
            'Age of the latest quote in seconds',
            labels=['symbol']
        )
        
        # Quote update frequency (updates per minute)
        update_freq_gauge = GaugeMetricFamily(
            'forex_quote_updates_per_minute',
            'Number of quote updates per minute',
            labels=['symbol']
        )
        
        # Quote latency
        latency_gauge = GaugeMetricFamily(
            'forex_quote_latency_ms',
            'Latency of quote retrieval in milliseconds',
            labels=['symbol']
        )
        
        # Collect data quality metrics for each symbol
        for symbol in self.symbols:
            try:
                # Quote age
                quote_age = self.market_data_service.get_quote_age(symbol)
                if quote_age is not None:
                    quote_age_gauge.add_metric([symbol], quote_age)
                
                # Update frequency
                update_freq = self.market_data_service.get_update_frequency(symbol)
                if update_freq is not None:
                    update_freq_gauge.add_metric([symbol], update_freq)
                
                # Quote latency
                latency = self.market_data_service.get_quote_latency(symbol)
                if latency is not None:
                    latency_gauge.add_metric([symbol], latency)
                
            except Exception as e:
                logger.error(f"Error collecting data quality metrics for {symbol}: {str(e)}")
        
        metrics.append(quote_age_gauge)
        metrics.append(update_freq_gauge)
        metrics.append(latency_gauge)
        
        return metrics 