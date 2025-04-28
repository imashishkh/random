"""
Trade metrics collector for Prometheus.

This module collects metrics related to forex trading performance,
including trade volume, profit/loss, execution time, and order book depth.
"""

import logging
import time
from typing import Dict, List, Optional, Any

from prometheus_client import Counter, Gauge, Histogram

from .base_collector import BaseCollector

logger = logging.getLogger(__name__)


class TradeCollector(BaseCollector):
    """
    Collector for trade-related metrics.
    
    Collects the following metrics:
    - Trade volume by currency pair
    - Profit/loss metrics by currency pair
    - Trade execution latency
    - Order book depth by currency pair and side
    """
    
    def __init__(
        self,
        trade_service=None,
        market_data_service=None,
        registry=None,
        collection_interval: int = 15,
        cache_ttl: int = 30,
    ):
        """
        Initialize the trade metrics collector.
        
        Args:
            trade_service: The trade analytics service to monitor
            market_data_service: Service for accessing market data like order books
            registry: Prometheus registry to use
            collection_interval: How often to collect metrics, in seconds
            cache_ttl: How long to cache expensive operations, in seconds
        """
        self.trade_service = trade_service
        self.market_data_service = market_data_service
        
        super().__init__(
            registry=registry,
            collection_interval=collection_interval,
            cache_ttl=cache_ttl,
            name="TradeCollector"
        )
    
    def _initialize_metrics(self) -> None:
        """Initialize all trade-related metrics."""
        # Gauge for trade volume by currency pair
        self._metrics['trade_volume'] = Gauge(
            'forex_trade_volume_total',
            'Total trade volume by currency pair',
            ['currency_pair', 'side'],
            registry=self.registry
        )
        
        # Gauge for profit/loss metrics
        self._metrics['profit_loss'] = Gauge(
            'forex_trade_profit_dollars',
            'Profit or loss in USD',
            ['currency_pair', 'time_window'],
            registry=self.registry
        )
        
        # Histogram for trade execution latency
        self._metrics['execution_time'] = Histogram(
            'forex_trade_execution_seconds',
            'Time to execute a trade',
            ['currency_pair', 'order_type'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1.0],
            registry=self.registry
        )
        
        # Gauge for order book depth
        self._metrics['orderbook_depth'] = Gauge(
            'forex_orderbook_depth_total',
            'Order book depth by currency pair and side',
            ['currency_pair', 'side', 'price_level'],
            registry=self.registry
        )
        
        # Counter for trades completed
        self._metrics['trades_completed'] = Counter(
            'forex_trades_completed_total',
            'Number of completed trades',
            ['currency_pair', 'side', 'order_type'],
            registry=self.registry
        )
        
        # Gauge for price spread
        self._metrics['price_spread'] = Gauge(
            'forex_price_spread',
            'Spread between bid and ask prices',
            ['currency_pair'],
            registry=self.registry
        )
        
        # Gauge for volatility metrics
        self._metrics['volatility'] = Gauge(
            'forex_price_volatility',
            'Price volatility measure',
            ['currency_pair', 'time_window'],
            registry=self.registry
        )
    
    def _collect_metrics(self) -> None:
        """Collect current trade metrics."""
        if not self.trade_service:
            logger.warning("Trade service not available, skipping collection")
            return
        
        try:
            # Get volume data
            volumes = self._cached_operation(
                'trade_volumes',
                self._get_trade_volumes
            )
            
            # Update volume gauges
            self._update_volume_gauges(volumes)
            
            # Get profit/loss data
            pnl = self._cached_operation(
                'profit_loss',
                self._get_profit_loss
            )
            
            # Update profit/loss gauges
            self._update_pnl_gauges(pnl)
            
            # Get order book data
            if self.market_data_service:
                orderbook = self._cached_operation(
                    'orderbook',
                    self._get_orderbook_data
                )
                
                # Update order book gauges
                self._update_orderbook_gauges(orderbook)
                
                # Update price spread gauges
                self._update_spread_gauges(orderbook)
            
            # Get volatility data
            volatility = self._cached_operation(
                'volatility',
                self._get_volatility_data
            )
            
            # Update volatility gauges
            self._update_volatility_gauges(volatility)
            
        except Exception as e:
            logger.error(f"Error collecting trade metrics: {e}")
    
    def _get_trade_volumes(self) -> Dict[str, Dict[str, float]]:
        """
        Get the current trade volumes by currency pair and side.
        
        Returns:
            Dictionary mapping currency pairs to sides to volumes
        """
        try:
            # This is a placeholder. In a real implementation,
            # this would query the trade analytics service.
            return {
                'EUR/USD': {'buy': 1250000, 'sell': 1150000},
                'GBP/USD': {'buy': 850000, 'sell': 800000},
                'USD/JPY': {'buy': 1500000, 'sell': 1450000},
                'USD/CAD': {'buy': 750000, 'sell': 700000},
                'AUD/USD': {'buy': 600000, 'sell': 580000},
            }
        except Exception as e:
            logger.error(f"Error getting trade volumes: {e}")
            return {}
    
    def _update_volume_gauges(self, volumes: Dict[str, Dict[str, float]]) -> None:
        """
        Update the trade volume gauges with current values.
        
        Args:
            volumes: Dictionary mapping currency pairs to sides to volumes
        """
        for currency_pair, sides in volumes.items():
            for side, volume in sides.items():
                self._metrics['trade_volume'].labels(
                    currency_pair=currency_pair,
                    side=side
                ).set(volume)
    
    def _get_profit_loss(self) -> Dict[str, Dict[str, float]]:
        """
        Get the current profit/loss data by currency pair and time window.
        
        Returns:
            Dictionary mapping currency pairs to time windows to PnL values
        """
        try:
            # This is a placeholder. In a real implementation,
            # this would query the trade analytics service.
            return {
                'EUR/USD': {'daily': 15000, 'weekly': 65000, 'monthly': 250000},
                'GBP/USD': {'daily': 8000, 'weekly': 35000, 'monthly': 120000},
                'USD/JPY': {'daily': 12000, 'weekly': 48000, 'monthly': 180000},
                'USD/CAD': {'daily': 5000, 'weekly': 22000, 'monthly': 85000},
                'AUD/USD': {'daily': 3000, 'weekly': 15000, 'monthly': 60000},
            }
        except Exception as e:
            logger.error(f"Error getting profit/loss data: {e}")
            return {}
    
    def _update_pnl_gauges(self, pnl: Dict[str, Dict[str, float]]) -> None:
        """
        Update the profit/loss gauges with current values.
        
        Args:
            pnl: Dictionary mapping currency pairs to time windows to PnL values
        """
        for currency_pair, windows in pnl.items():
            for time_window, value in windows.items():
                self._metrics['profit_loss'].labels(
                    currency_pair=currency_pair,
                    time_window=time_window
                ).set(value)
    
    def _get_orderbook_data(self) -> Dict[str, Dict[str, List[Dict[str, float]]]]:
        """
        Get the current order book data by currency pair.
        
        Returns:
            Dictionary mapping currency pairs to sides to lists of price levels
        """
        try:
            # This is a placeholder. In a real implementation,
            # this would query the market data service.
            return {
                'EUR/USD': {
                    'bid': [
                        {'price': 1.0500, 'volume': 1000000},
                        {'price': 1.0499, 'volume': 1500000},
                        {'price': 1.0498, 'volume': 2000000},
                    ],
                    'ask': [
                        {'price': 1.0501, 'volume': 800000},
                        {'price': 1.0502, 'volume': 1200000},
                        {'price': 1.0503, 'volume': 1800000},
                    ]
                },
                'GBP/USD': {
                    'bid': [
                        {'price': 1.2600, 'volume': 800000},
                        {'price': 1.2599, 'volume': 1200000},
                        {'price': 1.2598, 'volume': 1600000},
                    ],
                    'ask': [
                        {'price': 1.2601, 'volume': 600000},
                        {'price': 1.2602, 'volume': 900000},
                        {'price': 1.2603, 'volume': 1400000},
                    ]
                },
                'USD/JPY': {
                    'bid': [
                        {'price': 150.00, 'volume': 1200000},
                        {'price': 149.99, 'volume': 1800000},
                        {'price': 149.98, 'volume': 2400000},
                    ],
                    'ask': [
                        {'price': 150.01, 'volume': 1000000},
                        {'price': 150.02, 'volume': 1500000},
                        {'price': 150.03, 'volume': 2100000},
                    ]
                }
            }
        except Exception as e:
            logger.error(f"Error getting order book data: {e}")
            return {}
    
    def _update_orderbook_gauges(
        self,
        orderbook: Dict[str, Dict[str, List[Dict[str, float]]]]
    ) -> None:
        """
        Update the order book depth gauges with current values.
        
        Args:
            orderbook: Dictionary mapping currency pairs to sides to price levels
        """
        for currency_pair, sides in orderbook.items():
            for side, levels in sides.items():
                for i, level in enumerate(levels):
                    price_level = i + 1  # 1-based indexing for price levels
                    self._metrics['orderbook_depth'].labels(
                        currency_pair=currency_pair,
                        side=side,
                        price_level=str(price_level)
                    ).set(level['volume'])
    
    def _update_spread_gauges(
        self,
        orderbook: Dict[str, Dict[str, List[Dict[str, float]]]]
    ) -> None:
        """
        Update the price spread gauges with current values.
        
        Args:
            orderbook: Dictionary mapping currency pairs to sides to price levels
        """
        for currency_pair, sides in orderbook.items():
            if 'bid' in sides and 'ask' in sides and sides['bid'] and sides['ask']:
                # Get best bid and ask prices
                best_bid = sides['bid'][0]['price']
                best_ask = sides['ask'][0]['price']
                
                # Calculate spread
                spread = best_ask - best_bid
                
                # Update gauge
                self._metrics['price_spread'].labels(
                    currency_pair=currency_pair
                ).set(spread)
    
    def _get_volatility_data(self) -> Dict[str, Dict[str, float]]:
        """
        Get the current volatility data by currency pair and time window.
        
        Returns:
            Dictionary mapping currency pairs to time windows to volatility values
        """
        try:
            # This is a placeholder. In a real implementation,
            # this would calculate or query for volatility data.
            return {
                'EUR/USD': {'hourly': 0.0005, 'daily': 0.0025, 'weekly': 0.0080},
                'GBP/USD': {'hourly': 0.0007, 'daily': 0.0035, 'weekly': 0.0100},
                'USD/JPY': {'hourly': 0.0015, 'daily': 0.0060, 'weekly': 0.0180},
                'USD/CAD': {'hourly': 0.0004, 'daily': 0.0020, 'weekly': 0.0070},
                'AUD/USD': {'hourly': 0.0006, 'daily': 0.0030, 'weekly': 0.0090},
            }
        except Exception as e:
            logger.error(f"Error getting volatility data: {e}")
            return {}
    
    def _update_volatility_gauges(self, volatility: Dict[str, Dict[str, float]]) -> None:
        """
        Update the volatility gauges with current values.
        
        Args:
            volatility: Dictionary mapping currency pairs to time windows to values
        """
        for currency_pair, windows in volatility.items():
            for time_window, value in windows.items():
                self._metrics['volatility'].labels(
                    currency_pair=currency_pair,
                    time_window=time_window
                ).set(value)
    
    # Additional methods for recording trade-specific events
    
    def record_trade_execution_time(
        self,
        currency_pair: str,
        order_type: str,
        seconds: float
    ) -> None:
        """
        Record the time taken to execute a trade.
        
        Args:
            currency_pair: The currency pair traded
            order_type: Type of the order (market, limit, etc.)
            seconds: Time taken in seconds
        """
        self._metrics['execution_time'].labels(
            currency_pair=currency_pair,
            order_type=order_type
        ).observe(seconds)
    
    def record_trade_completed(
        self,
        currency_pair: str,
        side: str,
        order_type: str
    ) -> None:
        """
        Record a completed trade.
        
        Args:
            currency_pair: The currency pair traded
            side: Trade side (buy/sell)
            order_type: Type of the order
        """
        self._metrics['trades_completed'].labels(
            currency_pair=currency_pair,
            side=side,
            order_type=order_type
        ).inc() 