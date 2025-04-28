"""
Trading system metrics collector for Prometheus.

This module provides a collector for trading system metrics like open positions,
trade counts, and profit/loss metrics.
"""

import logging
from typing import Dict, List, Any

from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily

from .collectors.base_collector import BaseCollector
from ...trading.account import Account
from ...trading.position import Position

logger = logging.getLogger(__name__)


class TradingCollector(BaseCollector):
    """
    Collector for trading system metrics.
    
    This collector gathers metrics about the trading system, including:
    - Account metrics (balance, equity, margin)
    - Position metrics (open positions, P/L)
    - Trade metrics (count, volume, P/L)
    """
    
    def __init__(self, account: Account, collection_interval: float = 30.0):
        """
        Initialize the trading collector.
        
        Args:
            account: The trading account to monitor
            collection_interval: Interval in seconds between metric collection
        """
        super().__init__(collection_interval=collection_interval)
        self.account = account
    
    def collect_metrics(self) -> List[Any]:
        """
        Collect trading system metrics.
        
        Returns:
            List of metrics for Prometheus
        """
        metrics = []
        
        # Add account metrics
        metrics.extend(self._collect_account_metrics())
        
        # Add position metrics
        metrics.extend(self._collect_position_metrics())
        
        # Add trade metrics
        metrics.extend(self._collect_trade_metrics())
        
        # Add collector's own metrics
        metrics.extend(self.get_collector_metrics())
        
        return metrics
    
    def _collect_account_metrics(self) -> List[Any]:
        """
        Collect account-related metrics.
        
        Returns:
            List of account metrics
        """
        metrics = []
        
        # Account balance
        gauge = GaugeMetricFamily(
            'forex_account_balance',
            'Current account balance',
            labels=['account_id']
        )
        gauge.add_metric([self.account.account_id], self.account.balance)
        metrics.append(gauge)
        
        # Account equity
        gauge = GaugeMetricFamily(
            'forex_account_equity',
            'Current account equity (balance + unrealized P/L)',
            labels=['account_id']
        )
        gauge.add_metric([self.account.account_id], self.account.equity)
        metrics.append(gauge)
        
        # Account margin
        gauge = GaugeMetricFamily(
            'forex_account_margin',
            'Current used margin',
            labels=['account_id']
        )
        gauge.add_metric([self.account.account_id], self.account.margin)
        metrics.append(gauge)
        
        # Free margin
        gauge = GaugeMetricFamily(
            'forex_account_free_margin',
            'Current free margin available for trading',
            labels=['account_id']
        )
        gauge.add_metric([self.account.account_id], self.account.free_margin)
        metrics.append(gauge)
        
        # Margin level
        gauge = GaugeMetricFamily(
            'forex_account_margin_level',
            'Current margin level as percentage',
            labels=['account_id']
        )
        gauge.add_metric([self.account.account_id], self.account.margin_level)
        metrics.append(gauge)
        
        return metrics
    
    def _collect_position_metrics(self) -> List[Any]:
        """
        Collect position-related metrics.
        
        Returns:
            List of position metrics
        """
        metrics = []
        
        # Count open positions
        buy_count = 0
        sell_count = 0
        total_buy_volume = 0.0
        total_sell_volume = 0.0
        
        # Position metrics by symbol and direction
        for position in self.account.positions:
            if position.is_buy:
                buy_count += 1
                total_buy_volume += position.volume
            else:
                sell_count += 1
                total_sell_volume += position.volume
        
        # Open positions count
        gauge = GaugeMetricFamily(
            'forex_open_positions',
            'Number of open positions',
            labels=['account_id', 'direction']
        )
        gauge.add_metric([self.account.account_id, 'buy'], buy_count)
        gauge.add_metric([self.account.account_id, 'sell'], sell_count)
        metrics.append(gauge)
        
        # Open positions volume
        gauge = GaugeMetricFamily(
            'forex_open_positions_volume',
            'Total volume of open positions',
            labels=['account_id', 'direction']
        )
        gauge.add_metric([self.account.account_id, 'buy'], total_buy_volume)
        gauge.add_metric([self.account.account_id, 'sell'], total_sell_volume)
        metrics.append(gauge)
        
        # Detailed position metrics by symbol
        symbols = {position.symbol for position in self.account.positions}
        
        for symbol in symbols:
            # Filter positions by symbol
            symbol_positions = [p for p in self.account.positions if p.symbol == symbol]
            
            # Skip if no positions for this symbol
            if not symbol_positions:
                continue
            
            # Count by direction
            symbol_buy_count = sum(1 for p in symbol_positions if p.is_buy)
            symbol_sell_count = sum(1 for p in symbol_positions if not p.is_buy)
            
            # Positions by symbol
            gauge = GaugeMetricFamily(
                'forex_symbol_positions',
                'Number of open positions by symbol',
                labels=['account_id', 'symbol', 'direction']
            )
            gauge.add_metric([self.account.account_id, symbol, 'buy'], symbol_buy_count)
            gauge.add_metric([self.account.account_id, symbol, 'sell'], symbol_sell_count)
            metrics.append(gauge)
            
            # Volume by symbol
            symbol_buy_volume = sum(p.volume for p in symbol_positions if p.is_buy)
            symbol_sell_volume = sum(p.volume for p in symbol_positions if not p.is_buy)
            
            gauge = GaugeMetricFamily(
                'forex_symbol_volume',
                'Total volume of open positions by symbol',
                labels=['account_id', 'symbol', 'direction']
            )
            gauge.add_metric([self.account.account_id, symbol, 'buy'], symbol_buy_volume)
            gauge.add_metric([self.account.account_id, symbol, 'sell'], symbol_sell_volume)
            metrics.append(gauge)
            
            # P/L by symbol
            symbol_buy_pl = sum(p.profit for p in symbol_positions if p.is_buy)
            symbol_sell_pl = sum(p.profit for p in symbol_positions if not p.is_buy)
            
            gauge = GaugeMetricFamily(
                'forex_symbol_profit',
                'Current unrealized profit/loss by symbol',
                labels=['account_id', 'symbol', 'direction']
            )
            gauge.add_metric([self.account.account_id, symbol, 'buy'], symbol_buy_pl)
            gauge.add_metric([self.account.account_id, symbol, 'sell'], symbol_sell_pl)
            metrics.append(gauge)
        
        return metrics
    
    def _collect_trade_metrics(self) -> List[Any]:
        """
        Collect trade-related metrics.
        
        Returns:
            List of trade metrics
        """
        metrics = []
        
        # Trade counts
        counter = CounterMetricFamily(
            'forex_trades_total',
            'Total number of trades executed',
            labels=['account_id', 'result']
        )
        
        # Get trade statistics
        profitable_trades = self.account.trade_stats.get('profitable_trades', 0)
        losing_trades = self.account.trade_stats.get('losing_trades', 0)
        
        counter.add_metric([self.account.account_id, 'profitable'], profitable_trades)
        counter.add_metric([self.account.account_id, 'losing'], losing_trades)
        metrics.append(counter)
        
        # Trade P/L
        gauge = GaugeMetricFamily(
            'forex_total_profit',
            'Total realized profit/loss from closed trades',
            labels=['account_id']
        )
        gauge.add_metric([self.account.account_id], self.account.trade_stats.get('total_profit', 0.0))
        metrics.append(gauge)
        
        # Largest profit and loss
        gauge = GaugeMetricFamily(
            'forex_largest_profit',
            'Largest profit from a single trade',
            labels=['account_id']
        )
        gauge.add_metric([self.account.account_id], self.account.trade_stats.get('largest_profit', 0.0))
        metrics.append(gauge)
        
        gauge = GaugeMetricFamily(
            'forex_largest_loss',
            'Largest loss from a single trade',
            labels=['account_id']
        )
        gauge.add_metric([self.account.account_id], self.account.trade_stats.get('largest_loss', 0.0))
        metrics.append(gauge)
        
        # Average profit and loss
        gauge = GaugeMetricFamily(
            'forex_average_profit',
            'Average profit per profitable trade',
            labels=['account_id']
        )
        gauge.add_metric([self.account.account_id], self.account.trade_stats.get('average_profit', 0.0))
        metrics.append(gauge)
        
        gauge = GaugeMetricFamily(
            'forex_average_loss',
            'Average loss per losing trade',
            labels=['account_id']
        )
        gauge.add_metric([self.account.account_id], self.account.trade_stats.get('average_loss', 0.0))
        metrics.append(gauge)
        
        # Win rate
        gauge = GaugeMetricFamily(
            'forex_win_rate',
            'Win rate as percentage',
            labels=['account_id']
        )
        gauge.add_metric([self.account.account_id], self.account.trade_stats.get('win_rate', 0.0))
        metrics.append(gauge)
        
        return metrics 