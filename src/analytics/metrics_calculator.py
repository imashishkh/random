import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import defaultdict
import math

from .data_models import Trade, TradeDirection, PerformanceTimePeriod, TradeFilter


class MetricsCalculator:
    """Calculates trading performance metrics"""
    
    def __init__(self, trades: List[Trade]):
        self.trades = trades
        self._cache = {}  # Simple cache for expensive calculations
        
    def filter_trades(self, trade_filter: TradeFilter) -> List[Trade]:
        """Filter trades based on criteria"""
        filtered = self.trades
        
        if trade_filter.time_period:
            filtered = [t for t in filtered if 
                       t.close_time >= trade_filter.time_period.start_date and 
                       t.close_time <= trade_filter.time_period.end_date]
        
        if trade_filter.symbols:
            filtered = [t for t in filtered if t.symbol in trade_filter.symbols]
        
        if trade_filter.strategies:
            filtered = [t for t in filtered if t.strategy in trade_filter.strategies]
        
        if trade_filter.min_pnl is not None:
            filtered = [t for t in filtered if t.net_pnl >= trade_filter.min_pnl]
        
        if trade_filter.max_pnl is not None:
            filtered = [t for t in filtered if t.net_pnl <= trade_filter.max_pnl]
        
        if trade_filter.directions:
            filtered = [t for t in filtered if t.direction in trade_filter.directions]
        
        if trade_filter.tags:
            filtered = [t for t in filtered if any(tag in t.tags for tag in trade_filter.tags)]
            
        return filtered
    
    def get_trades_in_period(self, period: PerformanceTimePeriod) -> List[Trade]:
        """Get all trades in a specific time period"""
        return self.filter_trades(TradeFilter(time_period=period))
    
    def calculate_total_pnl(self, trades: Optional[List[Trade]] = None) -> float:
        """Calculate total profit/loss"""
        trades = trades or self.trades
        return sum(t.net_pnl for t in trades)
    
    def calculate_win_rate(self, trades: Optional[List[Trade]] = None) -> float:
        """Calculate win rate percentage"""
        trades = trades or self.trades
        if not trades:
            return 0.0
        winning_trades = [t for t in trades if t.is_winning]
        return len(winning_trades) / len(trades) * 100
    
    def calculate_profit_factor(self, trades: Optional[List[Trade]] = None) -> float:
        """Calculate profit factor (gross profit / gross loss)"""
        trades = trades or self.trades
        if not trades:
            return 0.0
            
        gross_profit = sum(t.net_pnl for t in trades if t.is_winning)
        gross_loss = abs(sum(t.net_pnl for t in trades if not t.is_winning))
        
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
            
        return gross_profit / gross_loss
    
    def calculate_average_trade(self, trades: Optional[List[Trade]] = None) -> float:
        """Calculate average trade profit/loss"""
        trades = trades or self.trades
        if not trades:
            return 0.0
        return self.calculate_total_pnl(trades) / len(trades)
    
    def calculate_average_win(self, trades: Optional[List[Trade]] = None) -> float:
        """Calculate average winning trade"""
        trades = trades or self.trades
        winning_trades = [t for t in trades if t.is_winning]
        if not winning_trades:
            return 0.0
        return sum(t.net_pnl for t in winning_trades) / len(winning_trades)
    
    def calculate_average_loss(self, trades: Optional[List[Trade]] = None) -> float:
        """Calculate average losing trade"""
        trades = trades or self.trades
        losing_trades = [t for t in trades if not t.is_winning]
        if not losing_trades:
            return 0.0
        return sum(t.net_pnl for t in losing_trades) / len(losing_trades)
    
    def calculate_win_loss_ratio(self, trades: Optional[List[Trade]] = None) -> float:
        """Calculate win/loss ratio (average win / average loss)"""
        avg_win = self.calculate_average_win(trades)
        avg_loss = self.calculate_average_loss(trades)
        
        if avg_loss == 0:
            return float('inf') if avg_win > 0 else 0.0
            
        return abs(avg_win / avg_loss)
    
    def calculate_max_drawdown(self, trades: Optional[List[Trade]] = None) -> Tuple[float, datetime, datetime]:
        """Calculate maximum drawdown and its period"""
        trades = trades or self.trades
        if not trades:
            return (0.0, None, None)
            
        # Sort trades by close time
        sorted_trades = sorted(trades, key=lambda t: t.close_time)
        
        # Calculate cumulative PnL
        cumulative_pnl = []
        running_total = 0
        for trade in sorted_trades:
            running_total += trade.net_pnl
            cumulative_pnl.append(running_total)
            
        # Find max drawdown
        max_drawdown = 0
        peak_idx = 0
        trough_idx = 0
        current_peak_idx = 0
        
        for i, pnl in enumerate(cumulative_pnl):
            if pnl > cumulative_pnl[current_peak_idx]:
                current_peak_idx = i
            else:
                current_drawdown = cumulative_pnl[current_peak_idx] - pnl
                if current_drawdown > max_drawdown:
                    max_drawdown = current_drawdown
                    peak_idx = current_peak_idx
                    trough_idx = i
        
        if max_drawdown == 0:
            return (0.0, None, None)
            
        return (max_drawdown, 
                sorted_trades[peak_idx].close_time, 
                sorted_trades[trough_idx].close_time)
    
    def calculate_sharpe_ratio(self, trades: Optional[List[Trade]] = None, 
                              risk_free_rate: float = 0.0, 
                              annualize: bool = True) -> float:
        """Calculate Sharpe ratio"""
        trades = trades or self.trades
        if not trades:
            return 0.0
            
        # Sort trades by close time
        sorted_trades = sorted(trades, key=lambda t: t.close_time)
        
        # Calculate daily returns
        daily_returns = defaultdict(float)
        for trade in sorted_trades:
            date_key = trade.close_time.date().isoformat()
            daily_returns[date_key] += trade.net_pnl
            
        # Convert to numpy array
        returns = list(daily_returns.values())
        
        if not returns:
            return 0.0
            
        returns_array = np.array(returns)
        
        # Calculate mean and std dev
        mean_return = np.mean(returns_array)
        std_dev = np.std(returns_array, ddof=1)  # Using sample standard deviation
        
        if std_dev == 0:
            return 0.0
            
        # Calculate Sharpe ratio
        sharpe = (mean_return - risk_free_rate) / std_dev
        
        # Annualize if requested
        if annualize:
            # Assuming 252 trading days per year
            sharpe *= math.sqrt(252)
            
        return sharpe
    
    def calculate_sortino_ratio(self, trades: Optional[List[Trade]] = None, 
                               risk_free_rate: float = 0.0, 
                               annualize: bool = True) -> float:
        """Calculate Sortino ratio (using downside deviation)"""
        trades = trades or self.trades
        if not trades:
            return 0.0
            
        # Sort trades by close time
        sorted_trades = sorted(trades, key=lambda t: t.close_time)
        
        # Calculate daily returns
        daily_returns = defaultdict(float)
        for trade in sorted_trades:
            date_key = trade.close_time.date().isoformat()
            daily_returns[date_key] += trade.net_pnl
            
        # Convert to numpy array
        returns = list(daily_returns.values())
        
        if not returns:
            return 0.0
            
        returns_array = np.array(returns)
        
        # Calculate mean return
        mean_return = np.mean(returns_array)
        
        # Calculate downside deviation
        downside_returns = returns_array[returns_array < 0]
        
        if len(downside_returns) == 0:
            return float('inf') if mean_return > risk_free_rate else 0.0
            
        downside_deviation = np.std(downside_returns, ddof=1)
        
        if downside_deviation == 0:
            return 0.0
            
        # Calculate Sortino ratio
        sortino = (mean_return - risk_free_rate) / downside_deviation
        
        # Annualize if requested
        if annualize:
            # Assuming 252 trading days per year
            sortino *= math.sqrt(252)
            
        return sortino
    
    def calculate_trades_by_symbol(self, trades: Optional[List[Trade]] = None) -> Dict[str, int]:
        """Calculate number of trades by symbol"""
        trades = trades or self.trades
        result = defaultdict(int)
        for trade in trades:
            result[trade.symbol] += 1
        return dict(result)
    
    def calculate_pnl_by_symbol(self, trades: Optional[List[Trade]] = None) -> Dict[str, float]:
        """Calculate P&L by symbol"""
        trades = trades or self.trades
        result = defaultdict(float)
        for trade in trades:
            result[trade.symbol] += trade.net_pnl
        return dict(result)
    
    def calculate_win_rate_by_symbol(self, trades: Optional[List[Trade]] = None) -> Dict[str, float]:
        """Calculate win rate by symbol"""
        trades = trades or self.trades
        trades_by_symbol = defaultdict(list)
        for trade in trades:
            trades_by_symbol[trade.symbol].append(trade)
            
        result = {}
        for symbol, symbol_trades in trades_by_symbol.items():
            winning_trades = [t for t in symbol_trades if t.is_winning]
            if symbol_trades:
                result[symbol] = len(winning_trades) / len(symbol_trades) * 100
            else:
                result[symbol] = 0.0
                
        return result
    
    def calculate_pnl_by_period(self, trades: Optional[List[Trade]] = None, 
                               period: str = 'daily') -> Dict[str, float]:
        """Calculate P&L aggregated by time period"""
        trades = trades or self.trades
        sorted_trades = sorted(trades, key=lambda t: t.close_time)
        
        result = defaultdict(float)
        for trade in sorted_trades:
            period_key = self._get_period_key(trade.close_time, period)
            result[period_key] += trade.net_pnl
            
        return dict(result)
    
    def calculate_cumulative_pnl_by_period(self, trades: Optional[List[Trade]] = None, 
                                         period: str = 'daily') -> Dict[str, float]:
        """Calculate cumulative P&L by time period"""
        trades = trades or self.trades
        pnl_by_period = self.calculate_pnl_by_period(trades, period)
        
        # Sort period keys
        period_keys = sorted(pnl_by_period.keys())
        
        result = {}
        running_total = 0
        for key in period_keys:
            running_total += pnl_by_period[key]
            result[key] = running_total
            
        return result
    
    def _get_period_key(self, dt: datetime, period: str) -> str:
        """Convert a datetime to period key string"""
        if period == 'daily':
            return dt.strftime("%Y-%m-%d")
        elif period == 'weekly':
            return f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]}"
        elif period == 'monthly':
            return dt.strftime("%Y-%m")
        elif period == 'yearly':
            return dt.strftime("%Y")
        else:
            return dt.strftime("%Y-%m-%d")
    
    def calculate_consecutive_wins_losses(self, trades: Optional[List[Trade]] = None) -> Tuple[int, int]:
        """Calculate max consecutive wins and losses"""
        trades = trades or self.trades
        if not trades:
            return (0, 0)
            
        sorted_trades = sorted(trades, key=lambda t: t.close_time)
        
        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0
        
        for trade in sorted_trades:
            if trade.is_winning:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
                
        return (max_wins, max_losses)
    
    def get_best_trades(self, trades: Optional[List[Trade]] = None, limit: int = 5) -> List[Trade]:
        """Get the best trades by P&L"""
        trades = trades or self.trades
        return sorted(trades, key=lambda t: t.net_pnl, reverse=True)[:limit]
    
    def get_worst_trades(self, trades: Optional[List[Trade]] = None, limit: int = 5) -> List[Trade]:
        """Get the worst trades by P&L"""
        trades = trades or self.trades
        return sorted(trades, key=lambda t: t.net_pnl)[:limit]
    
    def calculate_average_duration(self, trades: Optional[List[Trade]] = None) -> timedelta:
        """Calculate average trade duration"""
        trades = trades or self.trades
        if not trades:
            return timedelta(0)
            
        total_duration = sum((t.duration for t in trades), timedelta(0))
        return total_duration / len(trades)
    
    def calculate_trade_expectancy(self, trades: Optional[List[Trade]] = None) -> float:
        """Calculate trade expectancy (win_rate * avg_win - loss_rate * avg_loss)"""
        trades = trades or self.trades
        if not trades:
            return 0.0
            
        win_rate = self.calculate_win_rate(trades) / 100
        loss_rate = 1 - win_rate
        avg_win = self.calculate_average_win(trades)
        avg_loss = abs(self.calculate_average_loss(trades))
        
        return (win_rate * avg_win) - (loss_rate * avg_loss) 