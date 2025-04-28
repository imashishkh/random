from typing import List, Dict, Optional, Union, Any
from datetime import datetime, timedelta
import os
import logging

from .data_models import Trade, PerformanceTimePeriod, TradeFilter, TradeDirection
from .metrics_calculator import MetricsCalculator
from .data_fetcher import create_data_fetcher, DataFetcherBase
from .visualization import VisualizationManager


class TradingPerformanceAnalytics:
    """Main class for trading performance analytics"""
    
    def __init__(self, data_source: Union[str, DataFetcherBase], **kwargs):
        """Initialize with either a data source type or a DataFetcher instance"""
        self.logger = logging.getLogger(__name__)
        
        # Set up data fetcher
        if isinstance(data_source, str):
            self.data_fetcher = create_data_fetcher(data_source, **kwargs)
        else:
            self.data_fetcher = data_source
            
        # Initialize with empty trade list
        self.trades = []
        
        # Create calculator and visualization manager
        self.calculator = MetricsCalculator(self.trades)
        self.visualizer = VisualizationManager(self.calculator)
        
        # Load initial data
        self.refresh_data()
    
    def refresh_data(self) -> None:
        """Refresh trade data from the source"""
        try:
            self.trades = self.data_fetcher.fetch_trades()
            self.calculator = MetricsCalculator(self.trades)
            self.visualizer = VisualizationManager(self.calculator)
            self.logger.info(f"Loaded {len(self.trades)} trades")
        except Exception as e:
            self.logger.error(f"Error refreshing data: {str(e)}")
    
    def update_data(self) -> None:
        """Update with new trades from the source"""
        try:
            new_trades = self.data_fetcher.update_trades()
            if new_trades:
                self.trades.extend(new_trades)
                self.calculator = MetricsCalculator(self.trades)
                self.logger.info(f"Added {len(new_trades)} new trades")
        except Exception as e:
            self.logger.error(f"Error updating data: {str(e)}")
    
    def filter_trades(self, **kwargs) -> List[Trade]:
        """Filter trades based on criteria"""
        # Create a TradeFilter from kwargs
        filter_args = {}
        
        if 'start_date' in kwargs or 'end_date' in kwargs:
            start_date = kwargs.get('start_date')
            end_date = kwargs.get('end_date', datetime.now())
            filter_args['time_period'] = PerformanceTimePeriod(start_date, end_date, "Custom")
            
        if 'symbols' in kwargs:
            filter_args['symbols'] = kwargs['symbols']
            
        if 'strategies' in kwargs:
            filter_args['strategies'] = kwargs['strategies']
            
        if 'min_pnl' in kwargs:
            filter_args['min_pnl'] = kwargs['min_pnl']
            
        if 'max_pnl' in kwargs:
            filter_args['max_pnl'] = kwargs['max_pnl']
            
        if 'directions' in kwargs:
            filter_args['directions'] = kwargs['directions']
            
        if 'tags' in kwargs:
            filter_args['tags'] = kwargs['tags']
            
        trade_filter = TradeFilter(**filter_args)
        return self.calculator.filter_trades(trade_filter)
    
    def get_trades_for_period(self, period_type: str) -> List[Trade]:
        """Get trades for a specific time period"""
        now = datetime.now()
        
        if period_type == 'today':
            start_date = datetime(now.year, now.month, now.day)
            time_period = PerformanceTimePeriod(start_date, now, "Today")
        elif period_type == 'yesterday':
            yesterday = now - timedelta(days=1)
            start_date = datetime(yesterday.year, yesterday.month, yesterday.day)
            end_date = datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59)
            time_period = PerformanceTimePeriod(start_date, end_date, "Yesterday")
        elif period_type == 'this_week':
            # Start of week (Monday)
            days_since_monday = now.weekday()
            start_date = now - timedelta(days=days_since_monday)
            start_date = datetime(start_date.year, start_date.month, start_date.day)
            time_period = PerformanceTimePeriod(start_date, now, "This Week")
        elif period_type == 'last_week':
            # Previous week (Monday to Sunday)
            days_since_monday = now.weekday()
            end_of_last_week = now - timedelta(days=days_since_monday + 1)
            end_of_last_week = datetime(end_of_last_week.year, end_of_last_week.month, end_of_last_week.day, 23, 59, 59)
            start_of_last_week = end_of_last_week - timedelta(days=6)
            start_of_last_week = datetime(start_of_last_week.year, start_of_last_week.month, start_of_last_week.day)
            time_period = PerformanceTimePeriod(start_of_last_week, end_of_last_week, "Last Week")
        elif period_type == 'this_month':
            start_date = datetime(now.year, now.month, 1)
            time_period = PerformanceTimePeriod(start_date, now, "This Month")
        elif period_type == 'last_month':
            if now.month == 1:
                last_month = 12
                last_month_year = now.year - 1
            else:
                last_month = now.month - 1
                last_month_year = now.year
                
            start_date = datetime(last_month_year, last_month, 1)
            
            # End of last month
            if last_month == 12:
                end_date = datetime(last_month_year, last_month, 31, 23, 59, 59)
            else:
                end_date = datetime(now.year, now.month, 1) - timedelta(days=1)
                end_date = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)
                
            time_period = PerformanceTimePeriod(start_date, end_date, "Last Month")
        elif period_type == 'this_year':
            start_date = datetime(now.year, 1, 1)
            time_period = PerformanceTimePeriod(start_date, now, "This Year")
        elif period_type == 'last_year':
            start_date = datetime(now.year - 1, 1, 1)
            end_date = datetime(now.year - 1, 12, 31, 23, 59, 59)
            time_period = PerformanceTimePeriod(start_date, end_date, "Last Year")
        elif period_type == 'last_7_days':
            start_date = now - timedelta(days=7)
            time_period = PerformanceTimePeriod(start_date, now, "Last 7 Days")
        elif period_type == 'last_30_days':
            start_date = now - timedelta(days=30)
            time_period = PerformanceTimePeriod(start_date, now, "Last 30 Days")
        elif period_type == 'last_90_days':
            start_date = now - timedelta(days=90)
            time_period = PerformanceTimePeriod(start_date, now, "Last 90 Days")
        elif period_type == 'all_time':
            # Using a far past date as the start
            start_date = datetime(1970, 1, 1)
            time_period = PerformanceTimePeriod(start_date, now, "All Time")
        else:
            raise ValueError(f"Unknown period type: {period_type}")
            
        return self.calculator.get_trades_in_period(time_period)
    
    def display_dashboard(self, period_type: str = 'all_time', **kwargs) -> None:
        """Display the full performance dashboard for a specific time period"""
        trades = self.get_trades_for_period(period_type)
        
        # Apply additional filters if provided
        if kwargs:
            trade_filter = TradeFilter(**kwargs)
            trades = self.calculator.filter_trades(trade_filter)
            
        self.visualizer.display_full_dashboard(trades)
    
    def display_summary(self, period_type: str = 'all_time', **kwargs) -> None:
        """Display just the performance summary for a specific time period"""
        trades = self.get_trades_for_period(period_type)
        
        # Apply additional filters if provided
        if kwargs:
            trade_filter = TradeFilter(**kwargs)
            trades = self.calculator.filter_trades(trade_filter)
            
        summary = self.visualizer.create_performance_summary(trades)
        self.visualizer.console.print(summary)
    
    def display_pnl_chart(self, period_type: str = 'all_time', 
                         period: str = 'daily', 
                         show_cumulative: bool = True,
                         **kwargs) -> None:
        """Display P&L chart for a specific time period"""
        trades = self.get_trades_for_period(period_type)
        
        # Apply additional filters if provided
        if kwargs:
            trade_filter = TradeFilter(**kwargs)
            trades = self.calculator.filter_trades(trade_filter)
            
        self.visualizer.create_pnl_chart(trades, period, show_cumulative)
    
    def display_trade_table(self, period_type: str = 'all_time', 
                           limit: int = 10, 
                           **kwargs) -> None:
        """Display trade table for a specific time period"""
        trades = self.get_trades_for_period(period_type)
        
        # Apply additional filters if provided
        if kwargs:
            trade_filter = TradeFilter(**kwargs)
            trades = self.calculator.filter_trades(trade_filter)
            
        table = self.visualizer.create_trade_table(trades, limit)
        self.visualizer.console.print(table)
    
    def display_symbol_performance(self, period_type: str = 'all_time', **kwargs) -> None:
        """Display performance by symbol for a specific time period"""
        trades = self.get_trades_for_period(period_type)
        
        # Apply additional filters if provided
        if kwargs:
            trade_filter = TradeFilter(**kwargs)
            trades = self.calculator.filter_trades(trade_filter)
            
        table = self.visualizer.create_symbol_performance_table(trades)
        self.visualizer.console.print(table)
    
    def display_risk_metrics(self, period_type: str = 'all_time', **kwargs) -> None:
        """Display risk metrics for a specific time period"""
        trades = self.get_trades_for_period(period_type)
        
        # Apply additional filters if provided
        if kwargs:
            trade_filter = TradeFilter(**kwargs)
            trades = self.calculator.filter_trades(trade_filter)
            
        panel = self.visualizer.create_risk_metrics_panel(trades)
        self.visualizer.console.print(panel)
    
    def get_performance_metrics(self, period_type: str = 'all_time', **kwargs) -> Dict[str, Any]:
        """Get all performance metrics as a dictionary for a specific time period"""
        trades = self.get_trades_for_period(period_type)
        
        # Apply additional filters if provided
        if kwargs:
            trade_filter = TradeFilter(**kwargs)
            trades = self.calculator.filter_trades(trade_filter)
            
        if not trades:
            return {"error": "No trades found for the specified period"}
            
        # Calculate all metrics
        metrics = {
            "total_trades": len(trades),
            "winning_trades": len([t for t in trades if t.is_winning]),
            "losing_trades": len([t for t in trades if not t.is_winning]),
            "total_pnl": self.calculator.calculate_total_pnl(trades),
            "win_rate": self.calculator.calculate_win_rate(trades),
            "profit_factor": self.calculator.calculate_profit_factor(trades),
            "average_trade": self.calculator.calculate_average_trade(trades),
            "average_win": self.calculator.calculate_average_win(trades),
            "average_loss": self.calculator.calculate_average_loss(trades),
            "win_loss_ratio": self.calculator.calculate_win_loss_ratio(trades),
            "sharpe_ratio": self.calculator.calculate_sharpe_ratio(trades),
            "sortino_ratio": self.calculator.calculate_sortino_ratio(trades),
            "trade_expectancy": self.calculator.calculate_trade_expectancy(trades),
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "average_duration": str(self.calculator.calculate_average_duration(trades)),
            "symbols": {},
        }
        
        # Add max drawdown
        max_dd, dd_start, dd_end = self.calculator.calculate_max_drawdown(trades)
        metrics["max_drawdown"] = max_dd
        metrics["drawdown_start"] = dd_start.isoformat() if dd_start else None
        metrics["drawdown_end"] = dd_end.isoformat() if dd_end else None
        
        # Add consecutive wins/losses
        max_wins, max_losses = self.calculator.calculate_consecutive_wins_losses(trades)
        metrics["max_consecutive_wins"] = max_wins
        metrics["max_consecutive_losses"] = max_losses
        
        # Add symbol metrics
        trades_by_symbol = {}
        for trade in trades:
            if trade.symbol not in trades_by_symbol:
                trades_by_symbol[trade.symbol] = []
            trades_by_symbol[trade.symbol].append(trade)
            
        for symbol, symbol_trades in trades_by_symbol.items():
            metrics["symbols"][symbol] = {
                "trades": len(symbol_trades),
                "pnl": sum(t.pnl for t in symbol_trades),
                "win_rate": len([t for t in symbol_trades if t.is_winning]) / len(symbol_trades) * 100
            }
            
        return metrics 