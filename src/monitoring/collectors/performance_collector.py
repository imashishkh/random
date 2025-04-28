"""
Performance Collector module.

This module contains the PerformanceCollector class which is responsible for
monitoring trade execution metrics such as slippage, latency, fill rates,
and other performance indicators.
"""

import logging
import time
from typing import Dict, List, Optional, Tuple
import statistics
from datetime import datetime, timedelta
from enum import Enum
import math

from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, HistogramMetricFamily

from .base_collector import BaseCollector

logger = logging.getLogger(__name__)

class OrderStatus(Enum):
    """Order status enumeration for tracking trade lifecycle."""
    CREATED = "created"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    PARTIAL = "partial"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELED = "canceled"
    EXPIRED = "expired"
    FAILED = "failed"


class PerformanceCollector(BaseCollector):
    """
    Collector for trade execution performance metrics.
    
    Collects metrics related to trade execution quality including latency,
    slippage, fill rates, rejection rates, and other performance indicators.
    """
    
    def __init__(
        self,
        exchanges: Optional[List[str]] = None,
        pairs: Optional[List[str]] = None,
        latency_buckets: List[float] = [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
        slippage_buckets: List[float] = [0.0, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        collection_interval: int = 15,
        max_trade_history: int = 1000
    ):
        """
        Initialize the PerformanceCollector.
        
        Args:
            exchanges: List of exchanges to monitor (default: ["binance", "kucoin", "okx", "bybit"])
            pairs: List of trading pairs to monitor (default: ["BTC/USDT", "ETH/USDT", "XRP/USDT"])
            latency_buckets: Histogram buckets for latency in seconds
            slippage_buckets: Histogram buckets for slippage in percentage terms
            collection_interval: How often to collect metrics in seconds (default: 15)
            max_trade_history: Maximum number of trades to keep in history (default: 1000)
        """
        super().__init__(collection_interval=collection_interval)
        
        self.exchanges = exchanges or ["binance", "kucoin", "okx", "bybit"]
        self.pairs = pairs or ["BTC/USDT", "ETH/USDT", "XRP/USDT"]
        self.latency_buckets = latency_buckets
        self.slippage_buckets = slippage_buckets
        self.max_trade_history = max_trade_history
        
        # Store order lifecycle times for latency calculations
        # {order_id: {status: timestamp, ...}}
        self.order_times: Dict[str, Dict[str, datetime]] = {}
        
        # Store price information for slippage calculations
        # {order_id: {intended_price: float, executed_price: float, side: str, ...}}
        self.order_prices: Dict[str, Dict[str, float]] = {}
        
        # Store trade history for calculating various metrics
        # {exchange: {pair: [trade_record, ...], ...}, ...}
        self.trade_history: Dict[str, Dict[str, List[Dict]]] = {}
        
        # Initialize trade history structure
        for exchange in self.exchanges:
            self.trade_history[exchange] = {}
            for pair in self.pairs:
                self.trade_history[exchange][pair] = []
        
        # Track performance counters
        self.total_orders: Dict[str, Dict[str, int]] = {}
        self.fill_counts: Dict[str, Dict[str, int]] = {}
        self.reject_counts: Dict[str, Dict[str, int]] = {}
        self.cancel_counts: Dict[str, Dict[str, int]] = {}
        self.timeout_counts: Dict[str, Dict[str, int]] = {}
        
        # Initialize performance counters
        for exchange in self.exchanges:
            self.total_orders[exchange] = {pair: 0 for pair in self.pairs}
            self.fill_counts[exchange] = {pair: 0 for pair in self.pairs}
            self.reject_counts[exchange] = {pair: 0 for pair in self.pairs}
            self.cancel_counts[exchange] = {pair: 0 for pair in self.pairs}
            self.timeout_counts[exchange] = {pair: 0 for pair in self.pairs}
        
        logger.info(f"Initialized PerformanceCollector for {len(self.exchanges)} exchanges and {len(self.pairs)} pairs")
    
    def collect_metrics(self):
        """Collect all trade execution performance metrics."""
        try:
            metrics = []
            
            # Latency metrics
            latency = HistogramMetricFamily(
                'trade_execution_latency_seconds',
                'Trade execution latency in seconds',
                labels=['exchange', 'pair', 'phase']
            )
            
            # Slippage metrics
            slippage = HistogramMetricFamily(
                'trade_execution_slippage_percent',
                'Price slippage from intended price in percentage terms',
                labels=['exchange', 'pair', 'side']
            )
            
            # Fill rate metrics
            fill_rate = GaugeMetricFamily(
                'trade_fill_rate_percent',
                'Percentage of orders that were filled successfully',
                labels=['exchange', 'pair']
            )
            
            # Rejection rate metrics
            reject_rate = GaugeMetricFamily(
                'trade_rejection_rate_percent',
                'Percentage of orders that were rejected',
                labels=['exchange', 'pair']
            )
            
            # Cancellation rate metrics
            cancel_rate = GaugeMetricFamily(
                'trade_cancellation_rate_percent',
                'Percentage of orders that were cancelled',
                labels=['exchange', 'pair']
            )
            
            # Timeout rate metrics
            timeout_rate = GaugeMetricFamily(
                'trade_timeout_rate_percent',
                'Percentage of orders that timed out',
                labels=['exchange', 'pair']
            )
            
            # Order count metrics
            order_counts = CounterMetricFamily(
                'trade_orders_total',
                'Total number of orders placed',
                labels=['exchange', 'pair', 'status']
            )
            
            # Collect the metrics
            self._collect_latency_metrics(latency)
            self._collect_slippage_metrics(slippage)
            self._collect_fill_rate_metrics(fill_rate)
            self._collect_reject_rate_metrics(reject_rate)
            self._collect_cancel_rate_metrics(cancel_rate)
            self._collect_timeout_rate_metrics(timeout_rate)
            self._collect_order_count_metrics(order_counts)
            
            metrics.extend([latency, slippage, fill_rate, reject_rate, cancel_rate, timeout_rate, order_counts])
            
            return metrics
        except Exception as e:
            logger.error(f"Error collecting performance metrics: {str(e)}")
            return []
    
    def _collect_latency_metrics(self, latency_metric):
        """
        Collect trade execution latency metrics.
        
        Args:
            latency_metric: The Prometheus metric to populate
        """
        for exchange in self.exchanges:
            for pair in self.pairs:
                # Calculate latency values for different phases
                created_to_sent = []
                sent_to_ack = []
                ack_to_fill = []
                total_latency = []
                
                # Extract latency data from trade history
                for trade in self.trade_history[exchange][pair]:
                    if 'latency' in trade:
                        if 'created_to_sent' in trade['latency']:
                            created_to_sent.append(trade['latency']['created_to_sent'])
                        if 'sent_to_acknowledged' in trade['latency']:
                            sent_to_ack.append(trade['latency']['sent_to_acknowledged'])
                        if 'acknowledged_to_filled' in trade['latency']:
                            ack_to_fill.append(trade['latency']['acknowledged_to_filled'])
                        if 'total' in trade['latency']:
                            total_latency.append(trade['latency']['total'])
                
                # Add metrics to the histogram
                if created_to_sent:
                    latency_metric.add_metric(
                        [exchange, pair, 'created_to_sent'],
                        self.latency_buckets,
                        self._calculate_histogram_buckets(created_to_sent, self.latency_buckets)
                    )
                
                if sent_to_ack:
                    latency_metric.add_metric(
                        [exchange, pair, 'sent_to_acknowledged'],
                        self.latency_buckets,
                        self._calculate_histogram_buckets(sent_to_ack, self.latency_buckets)
                    )
                
                if ack_to_fill:
                    latency_metric.add_metric(
                        [exchange, pair, 'acknowledged_to_filled'],
                        self.latency_buckets,
                        self._calculate_histogram_buckets(ack_to_fill, self.latency_buckets)
                    )
                
                if total_latency:
                    latency_metric.add_metric(
                        [exchange, pair, 'total'],
                        self.latency_buckets,
                        self._calculate_histogram_buckets(total_latency, self.latency_buckets)
                    )
    
    def _collect_slippage_metrics(self, slippage_metric):
        """
        Collect trade execution slippage metrics.
        
        Args:
            slippage_metric: The Prometheus metric to populate
        """
        for exchange in self.exchanges:
            for pair in self.pairs:
                # Extract buy and sell slippage values
                buy_slippage = []
                sell_slippage = []
                
                for trade in self.trade_history[exchange][pair]:
                    if 'slippage_percent' in trade:
                        if trade.get('side') == 'buy':
                            buy_slippage.append(abs(trade['slippage_percent']))
                        elif trade.get('side') == 'sell':
                            sell_slippage.append(abs(trade['slippage_percent']))
                
                # Add metrics to the histogram
                if buy_slippage:
                    slippage_metric.add_metric(
                        [exchange, pair, 'buy'],
                        self.slippage_buckets,
                        self._calculate_histogram_buckets(buy_slippage, self.slippage_buckets)
                    )
                
                if sell_slippage:
                    slippage_metric.add_metric(
                        [exchange, pair, 'sell'],
                        self.slippage_buckets,
                        self._calculate_histogram_buckets(sell_slippage, self.slippage_buckets)
                    )
    
    def _collect_fill_rate_metrics(self, fill_rate_metric):
        """
        Collect trade fill rate metrics.
        
        Args:
            fill_rate_metric: The Prometheus metric to populate
        """
        for exchange in self.exchanges:
            for pair in self.pairs:
                total = self.total_orders[exchange][pair]
                filled = self.fill_counts[exchange][pair]
                
                if total > 0:
                    rate = (filled / total) * 100
                    fill_rate_metric.add_metric([exchange, pair], rate)
                else:
                    fill_rate_metric.add_metric([exchange, pair], 0)
    
    def _collect_reject_rate_metrics(self, reject_rate_metric):
        """
        Collect trade rejection rate metrics.
        
        Args:
            reject_rate_metric: The Prometheus metric to populate
        """
        for exchange in self.exchanges:
            for pair in self.pairs:
                total = self.total_orders[exchange][pair]
                rejected = self.reject_counts[exchange][pair]
                
                if total > 0:
                    rate = (rejected / total) * 100
                    reject_rate_metric.add_metric([exchange, pair], rate)
                else:
                    reject_rate_metric.add_metric([exchange, pair], 0)
    
    def _collect_cancel_rate_metrics(self, cancel_rate_metric):
        """
        Collect trade cancellation rate metrics.
        
        Args:
            cancel_rate_metric: The Prometheus metric to populate
        """
        for exchange in self.exchanges:
            for pair in self.pairs:
                total = self.total_orders[exchange][pair]
                cancelled = self.cancel_counts[exchange][pair]
                
                if total > 0:
                    rate = (cancelled / total) * 100
                    cancel_rate_metric.add_metric([exchange, pair], rate)
                else:
                    cancel_rate_metric.add_metric([exchange, pair], 0)
    
    def _collect_timeout_rate_metrics(self, timeout_rate_metric):
        """
        Collect trade timeout rate metrics.
        
        Args:
            timeout_rate_metric: The Prometheus metric to populate
        """
        for exchange in self.exchanges:
            for pair in self.pairs:
                total = self.total_orders[exchange][pair]
                timeouts = self.timeout_counts[exchange][pair]
                
                if total > 0:
                    rate = (timeouts / total) * 100
                    timeout_rate_metric.add_metric([exchange, pair], rate)
                else:
                    timeout_rate_metric.add_metric([exchange, pair], 0)
    
    def _collect_order_count_metrics(self, order_counts_metric):
        """
        Collect order count metrics.
        
        Args:
            order_counts_metric: The Prometheus metric to populate
        """
        for exchange in self.exchanges:
            for pair in self.pairs:
                # Total orders
                order_counts_metric.add_metric(
                    [exchange, pair, 'total'],
                    self.total_orders[exchange][pair]
                )
                
                # Filled orders
                order_counts_metric.add_metric(
                    [exchange, pair, 'filled'],
                    self.fill_counts[exchange][pair]
                )
                
                # Rejected orders
                order_counts_metric.add_metric(
                    [exchange, pair, 'rejected'],
                    self.reject_counts[exchange][pair]
                )
                
                # Cancelled orders
                order_counts_metric.add_metric(
                    [exchange, pair, 'cancelled'],
                    self.cancel_counts[exchange][pair]
                )
                
                # Timeout orders
                order_counts_metric.add_metric(
                    [exchange, pair, 'timeout'],
                    self.timeout_counts[exchange][pair]
                )
    
    def _calculate_histogram_buckets(self, values, buckets):
        """
        Calculate histogram bucket values for a list of measurements.
        
        Args:
            values: List of measurement values
            buckets: List of bucket boundaries
            
        Returns:
            List of cumulative counts for each bucket + sum of all values
        """
        # Initialize bucket counters
        bucket_counts = [0] * (len(buckets) + 1)
        
        # Count values in each bucket
        for value in values:
            for i, bucket in enumerate(buckets):
                if value <= bucket:
                    bucket_counts[i] += 1
        
        # Last bucket is +Inf, so it contains all values
        bucket_counts[-1] = len(values)
        
        # Return bucket counts and sum of all values
        return bucket_counts + [sum(values)]
    
    def record_order_status(
        self,
        order_id: str,
        exchange: str,
        pair: str,
        status: OrderStatus,
        timestamp: Optional[datetime] = None
    ):
        """
        Record an order status update.
        
        Args:
            order_id: Unique identifier for the order
            exchange: The exchange the order was placed on
            pair: The trading pair for the order
            status: The new status of the order
            timestamp: When the status change occurred (default: current time)
        """
        if exchange not in self.exchanges:
            logger.warning(f"Ignoring order status update for unknown exchange: {exchange}")
            return
        
        if pair not in self.pairs:
            logger.warning(f"Ignoring order status update for unknown pair: {pair}")
            return
        
        if timestamp is None:
            timestamp = datetime.now()
        
        # Create order entry if it doesn't exist
        if order_id not in self.order_times:
            self.order_times[order_id] = {}
            
            # If this is the first status update and it's not CREATED,
            # assume the order was created now (may be slightly inaccurate)
            if status != OrderStatus.CREATED:
                self.order_times[order_id][OrderStatus.CREATED.value] = timestamp
        
        # Record the time for this status
        self.order_times[order_id][status.value] = timestamp
        
        # Update counters based on terminal states
        if status in [OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELED, OrderStatus.EXPIRED, OrderStatus.FAILED]:
            self._process_completed_order(order_id, exchange, pair, status)
    
    def record_order_price_info(
        self,
        order_id: str,
        intended_price: float,
        side: str,
        executed_price: Optional[float] = None
    ):
        """
        Record price information for an order to calculate slippage.
        
        Args:
            order_id: Unique identifier for the order
            intended_price: The price the order was intended to execute at
            side: The order side ('buy' or 'sell')
            executed_price: The actual execution price (if known, otherwise can be set later)
        """
        # Create price entry if it doesn't exist
        if order_id not in self.order_prices:
            self.order_prices[order_id] = {}
        
        self.order_prices[order_id]['intended_price'] = intended_price
        self.order_prices[order_id]['side'] = side
        
        if executed_price is not None:
            self.order_prices[order_id]['executed_price'] = executed_price
    
    def set_executed_price(self, order_id: str, executed_price: float):
        """
        Set the final executed price for an order.
        
        Args:
            order_id: Unique identifier for the order
            executed_price: The actual price the order executed at
        """
        if order_id not in self.order_prices:
            logger.warning(f"Cannot set executed price for unknown order: {order_id}")
            return
        
        self.order_prices[order_id]['executed_price'] = executed_price
    
    def _process_completed_order(self, order_id: str, exchange: str, pair: str, status: OrderStatus):
        """
        Process a completed order to update metrics and trade history.
        
        Args:
            order_id: Unique identifier for the order
            exchange: The exchange the order was placed on
            pair: The trading pair for the order
            status: The final status of the order
        """
        # Increment total order count
        self.total_orders[exchange][pair] += 1
        
        # Update status-specific counters
        if status == OrderStatus.FILLED:
            self.fill_counts[exchange][pair] += 1
        elif status == OrderStatus.REJECTED:
            self.reject_counts[exchange][pair] += 1
        elif status == OrderStatus.CANCELED:
            self.cancel_counts[exchange][pair] += 1
        elif status in [OrderStatus.EXPIRED, OrderStatus.FAILED]:
            self.timeout_counts[exchange][pair] += 1
        
        # Calculate latency metrics if we have the timestamps
        latency = {}
        order_times = self.order_times.get(order_id, {})
        
        # Created to sent latency
        if OrderStatus.CREATED.value in order_times and OrderStatus.SENT.value in order_times:
            created_time = order_times[OrderStatus.CREATED.value]
            sent_time = order_times[OrderStatus.SENT.value]
            latency['created_to_sent'] = (sent_time - created_time).total_seconds()
        
        # Sent to acknowledged latency
        if OrderStatus.SENT.value in order_times and OrderStatus.ACKNOWLEDGED.value in order_times:
            sent_time = order_times[OrderStatus.SENT.value]
            ack_time = order_times[OrderStatus.ACKNOWLEDGED.value]
            latency['sent_to_acknowledged'] = (ack_time - sent_time).total_seconds()
        
        # Acknowledged to filled latency (only for filled orders)
        if status == OrderStatus.FILLED and OrderStatus.ACKNOWLEDGED.value in order_times:
            ack_time = order_times[OrderStatus.ACKNOWLEDGED.value]
            filled_time = order_times[OrderStatus.FILLED.value]
            latency['acknowledged_to_filled'] = (filled_time - ack_time).total_seconds()
        
        # Total latency
        if OrderStatus.CREATED.value in order_times and status.value in order_times:
            created_time = order_times[OrderStatus.CREATED.value]
            final_time = order_times[status.value]
            latency['total'] = (final_time - created_time).total_seconds()
        
        # Calculate slippage if we have price information
        slippage_percent = None
        price_info = self.order_prices.get(order_id, {})
        
        if status == OrderStatus.FILLED and 'intended_price' in price_info and 'executed_price' in price_info:
            intended_price = price_info['intended_price']
            executed_price = price_info['executed_price']
            side = price_info.get('side')
            
            if intended_price > 0:
                # Calculate slippage (negative = better price, positive = worse price)
                if side == 'buy':
                    # For buys, executed > intended is bad (paying more than expected)
                    slippage_percent = ((executed_price - intended_price) / intended_price) * 100
                elif side == 'sell':
                    # For sells, executed < intended is bad (receiving less than expected)
                    slippage_percent = ((intended_price - executed_price) / intended_price) * 100
        
        # Create the trade record
        trade_record = {
            'order_id': order_id,
            'exchange': exchange,
            'pair': pair,
            'status': status.value,
            'timestamp': datetime.now(),
            'latency': latency
        }
        
        # Add slippage if calculated
        if status == OrderStatus.FILLED and price_info.get('side') and slippage_percent is not None:
            trade_record['side'] = price_info['side']
            trade_record['intended_price'] = price_info['intended_price']
            trade_record['executed_price'] = price_info['executed_price']
            trade_record['slippage_percent'] = slippage_percent
        
        # Add to trade history
        self.trade_history[exchange][pair].append(trade_record)
        
        # Limit trade history size
        if len(self.trade_history[exchange][pair]) > self.max_trade_history:
            self.trade_history[exchange][pair] = self.trade_history[exchange][pair][-self.max_trade_history:]
        
        # Clean up the order data
        if order_id in self.order_times:
            del self.order_times[order_id]
        if order_id in self.order_prices:
            del self.order_prices[order_id]
    
    def get_trade_metrics_summary(self, exchange: str, pair: str) -> Dict[str, float]:
        """
        Get a summary of trade execution metrics for a specific exchange and pair.
        
        Args:
            exchange: Name of the exchange
            pair: Trading pair
            
        Returns:
            Dictionary with summary metrics
        """
        if exchange not in self.exchanges or pair not in self.pairs:
            return {}
        
        total = self.total_orders[exchange][pair]
        if total == 0:
            return {
                "total_orders": 0,
                "fill_rate": 0.0,
                "reject_rate": 0.0,
                "cancel_rate": 0.0,
                "timeout_rate": 0.0,
                "avg_latency": 0.0,
                "avg_slippage": 0.0
            }
        
        # Calculate rates
        fill_rate = (self.fill_counts[exchange][pair] / total) * 100
        reject_rate = (self.reject_counts[exchange][pair] / total) * 100
        cancel_rate = (self.cancel_counts[exchange][pair] / total) * 100
        timeout_rate = (self.timeout_counts[exchange][pair] / total) * 100
        
        # Calculate average latency
        total_latencies = [
            trade.get('latency', {}).get('total', 0)
            for trade in self.trade_history[exchange][pair]
            if 'latency' in trade and 'total' in trade['latency']
        ]
        
        avg_latency = statistics.mean(total_latencies) if total_latencies else 0.0
        
        # Calculate average slippage
        slippages = [
            abs(trade.get('slippage_percent', 0))
            for trade in self.trade_history[exchange][pair]
            if 'slippage_percent' in trade
        ]
        
        avg_slippage = statistics.mean(slippages) if slippages else 0.0
        
        return {
            "total_orders": total,
            "filled_orders": self.fill_counts[exchange][pair],
            "rejected_orders": self.reject_counts[exchange][pair],
            "cancelled_orders": self.cancel_counts[exchange][pair],
            "timeout_orders": self.timeout_counts[exchange][pair],
            "fill_rate": fill_rate,
            "reject_rate": reject_rate,
            "cancel_rate": cancel_rate,
            "timeout_rate": timeout_rate,
            "avg_latency": avg_latency,
            "avg_slippage": avg_slippage
        }
    
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
        self.trade_history[exchange] = {}
        self.total_orders[exchange] = {}
        self.fill_counts[exchange] = {}
        self.reject_counts[exchange] = {}
        self.cancel_counts[exchange] = {}
        self.timeout_counts[exchange] = {}
        
        for pair in self.pairs:
            self.trade_history[exchange][pair] = []
            self.total_orders[exchange][pair] = 0
            self.fill_counts[exchange][pair] = 0
            self.reject_counts[exchange][pair] = 0
            self.cancel_counts[exchange][pair] = 0
            self.timeout_counts[exchange][pair] = 0
        
        logger.info(f"Added exchange {exchange} to performance monitoring")
    
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
            self.trade_history[exchange][pair] = []
            self.total_orders[exchange][pair] = 0
            self.fill_counts[exchange][pair] = 0
            self.reject_counts[exchange][pair] = 0
            self.cancel_counts[exchange][pair] = 0
            self.timeout_counts[exchange][pair] = 0
        
        logger.info(f"Added pair {pair} to performance monitoring")
    
    def reset_metrics(self, exchange: Optional[str] = None, pair: Optional[str] = None):
        """
        Reset metrics for a specific exchange/pair or all metrics.
        
        Args:
            exchange: Name of the exchange to reset (or None for all)
            pair: Trading pair to reset (or None for all)
        """
        if exchange is None:
            # Reset all metrics
            for ex in self.exchanges:
                for pr in self.pairs:
                    self._reset_pair_metrics(ex, pr)
            logger.info("Reset all performance metrics")
        elif pair is None:
            # Reset all metrics for a specific exchange
            if exchange in self.exchanges:
                for pr in self.pairs:
                    self._reset_pair_metrics(exchange, pr)
                logger.info(f"Reset all performance metrics for exchange {exchange}")
            else:
                logger.warning(f"Cannot reset metrics for unknown exchange: {exchange}")
        else:
            # Reset metrics for a specific exchange and pair
            if exchange in self.exchanges and pair in self.pairs:
                self._reset_pair_metrics(exchange, pair)
                logger.info(f"Reset performance metrics for {exchange} {pair}")
            else:
                logger.warning(f"Cannot reset metrics for unknown exchange/pair: {exchange}/{pair}")
    
    def _reset_pair_metrics(self, exchange: str, pair: str):
        """
        Reset metrics for a specific exchange and pair.
        
        Args:
            exchange: Name of the exchange
            pair: Trading pair
        """
        self.trade_history[exchange][pair] = []
        self.total_orders[exchange][pair] = 0
        self.fill_counts[exchange][pair] = 0
        self.reject_counts[exchange][pair] = 0
        self.cancel_counts[exchange][pair] = 0
        self.timeout_counts[exchange][pair] = 0 