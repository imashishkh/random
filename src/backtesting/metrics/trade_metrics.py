"""
Trade Metrics Module

This module contains functions for analyzing trade-level data and generating statistics
about trade performance, timing, and patterns.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta


def calculate_win_rate(trades: pd.DataFrame) -> float:
    """
    Calculate the win rate (percentage of profitable trades).
    
    Args:
        trades: DataFrame containing trade data with at least a 'pnl' column
        
    Returns:
        Win rate as a decimal (0 to 1)
    """
    if len(trades) == 0:
        return 0.0
    
    # Count profitable trades
    profitable_trades = (trades['pnl'] > 0).sum()
    
    # Calculate win rate
    return profitable_trades / len(trades)


def calculate_profit_factor(trades: pd.DataFrame) -> float:
    """
    Calculate the profit factor (gross profits divided by gross losses).
    
    Args:
        trades: DataFrame containing trade data with at least a 'pnl' column
        
    Returns:
        Profit factor
    """
    if len(trades) == 0:
        return 0.0
    
    # Calculate gross profits and losses
    gross_profits = trades.loc[trades['pnl'] > 0, 'pnl'].sum()
    gross_losses = abs(trades.loc[trades['pnl'] < 0, 'pnl'].sum())
    
    if gross_losses == 0:
        return float('inf') if gross_profits > 0 else 0.0
    
    return gross_profits / gross_losses


def calculate_average_profit_per_trade(trades: pd.DataFrame) -> float:
    """
    Calculate the average profit per trade.
    
    Args:
        trades: DataFrame containing trade data with at least a 'pnl' column
        
    Returns:
        Average profit per trade
    """
    if len(trades) == 0:
        return 0.0
    
    return trades['pnl'].mean()


def calculate_average_win_loss_ratio(trades: pd.DataFrame) -> float:
    """
    Calculate the ratio of average winning trade to average losing trade.
    
    Args:
        trades: DataFrame containing trade data with at least a 'pnl' column
        
    Returns:
        Average win/loss ratio
    """
    if len(trades) == 0:
        return 0.0
    
    # Calculate average win and loss
    avg_win = trades.loc[trades['pnl'] > 0, 'pnl'].mean()
    avg_loss = abs(trades.loc[trades['pnl'] < 0, 'pnl'].mean())
    
    if np.isnan(avg_win):
        avg_win = 0
    if np.isnan(avg_loss) or avg_loss == 0:
        return 0.0 if avg_win == 0 else float('inf')
    
    return avg_win / avg_loss


def calculate_expectancy(trades: pd.DataFrame) -> float:
    """
    Calculate the expectancy (expected return per trade).
    
    Args:
        trades: DataFrame containing trade data with at least a 'pnl' column
        
    Returns:
        Expectancy
    """
    if len(trades) == 0:
        return 0.0
    
    win_rate = calculate_win_rate(trades)
    avg_win = trades.loc[trades['pnl'] > 0, 'pnl'].mean()
    avg_loss = abs(trades.loc[trades['pnl'] < 0, 'pnl'].mean())
    
    if np.isnan(avg_win):
        avg_win = 0
    if np.isnan(avg_loss):
        avg_loss = 0
    
    return (win_rate * avg_win) - ((1 - win_rate) * avg_loss)


def calculate_largest_winning_trade(trades: pd.DataFrame) -> float:
    """
    Find the largest winning trade.
    
    Args:
        trades: DataFrame containing trade data with at least a 'pnl' column
        
    Returns:
        Value of the largest winning trade
    """
    if len(trades) == 0 or trades.loc[trades['pnl'] > 0].empty:
        return 0.0
    
    return trades['pnl'].max()


def calculate_largest_losing_trade(trades: pd.DataFrame) -> float:
    """
    Find the largest losing trade.
    
    Args:
        trades: DataFrame containing trade data with at least a 'pnl' column
        
    Returns:
        Absolute value of the largest losing trade
    """
    if len(trades) == 0 or trades.loc[trades['pnl'] < 0].empty:
        return 0.0
    
    return abs(trades['pnl'].min())


def calculate_average_holding_time(trades: pd.DataFrame) -> float:
    """
    Calculate the average holding time for trades in days.
    
    Args:
        trades: DataFrame containing trade data with 'entry_time' and 'exit_time' columns
        
    Returns:
        Average holding time in days
    """
    if len(trades) == 0 or 'entry_time' not in trades.columns or 'exit_time' not in trades.columns:
        return 0.0
    
    # Calculate holding time for each trade
    holding_times = (trades['exit_time'] - trades['entry_time']).dt.total_seconds() / (60 * 60 * 24)  # Convert to days
    
    return holding_times.mean()


def calculate_max_consecutive_wins(trades: pd.DataFrame) -> int:
    """
    Calculate the maximum number of consecutive winning trades.
    
    Args:
        trades: DataFrame containing trade data with at least a 'pnl' column
        
    Returns:
        Maximum number of consecutive winning trades
    """
    if len(trades) == 0:
        return 0
    
    # Create a list of trade results (1 for win, 0 for loss)
    results = (trades['pnl'] > 0).astype(int).values
    
    # Use a simple algorithm to find max consecutive ones
    max_consecutive = 0
    current_consecutive = 0
    
    for result in results:
        if result == 1:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0
    
    return max_consecutive


def calculate_max_consecutive_losses(trades: pd.DataFrame) -> int:
    """
    Calculate the maximum number of consecutive losing trades.
    
    Args:
        trades: DataFrame containing trade data with at least a 'pnl' column
        
    Returns:
        Maximum number of consecutive losing trades
    """
    if len(trades) == 0:
        return 0
    
    # Create a list of trade results (1 for loss, 0 for win)
    results = (trades['pnl'] <= 0).astype(int).values
    
    # Use a simple algorithm to find max consecutive ones
    max_consecutive = 0
    current_consecutive = 0
    
    for result in results:
        if result == 1:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0
    
    return max_consecutive


def calculate_max_drawdown_in_trades(trades: pd.DataFrame) -> float:
    """
    Calculate the maximum drawdown in account value across trades.
    
    Args:
        trades: DataFrame containing trade data with at least a 'pnl' column and
               'cumulative_pnl' column or one will be calculated
        
    Returns:
        Maximum drawdown as a decimal
    """
    if len(trades) == 0:
        return 0.0
    
    # If cumulative_pnl doesn't exist, calculate it
    if 'cumulative_pnl' not in trades.columns:
        trades = trades.copy()
        trades['cumulative_pnl'] = trades['pnl'].cumsum()
    
    # Calculate maximum drawdown
    cumulative_pnl = trades['cumulative_pnl'].values
    
    max_dd = 0
    peak = cumulative_pnl[0]
    
    for value in cumulative_pnl:
        if value > peak:
            peak = value
        dd = (peak - value) / (peak + 1e-10)  # Avoid division by zero
        max_dd = max(max_dd, dd)
    
    return max_dd


def calculate_average_mae(trades: pd.DataFrame) -> float:
    """
    Calculate the average Maximum Adverse Excursion (MAE).
    
    Args:
        trades: DataFrame containing trade data with at least a 'mae' column
        
    Returns:
        Average MAE
    """
    if len(trades) == 0 or 'mae' not in trades.columns:
        return 0.0
    
    return trades['mae'].mean()


def calculate_average_mfe(trades: pd.DataFrame) -> float:
    """
    Calculate the average Maximum Favorable Excursion (MFE).
    
    Args:
        trades: DataFrame containing trade data with at least a 'mfe' column
        
    Returns:
        Average MFE
    """
    if len(trades) == 0 or 'mfe' not in trades.columns:
        return 0.0
    
    return trades['mfe'].mean()


def calculate_trades_per_day(trades: pd.DataFrame) -> float:
    """
    Calculate the average number of trades per day.
    
    Args:
        trades: DataFrame containing trade data with 'entry_time' column
        
    Returns:
        Trades per day
    """
    if len(trades) == 0 or 'entry_time' not in trades.columns:
        return 0.0
    
    # Calculate date range
    start_date = trades['entry_time'].min()
    end_date = trades['entry_time'].max()
    
    # Calculate number of days
    days = (end_date - start_date).days + 1
    
    if days == 0:
        return len(trades)
    
    return len(trades) / days


def calculate_trade_pnl_distribution(trades: pd.DataFrame, bins: int = 10) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate the distribution of trade P&Ls.
    
    Args:
        trades: DataFrame containing trade data with at least a 'pnl' column
        bins: Number of bins for the histogram
        
    Returns:
        Tuple of (bin edges, histogram values)
    """
    if len(trades) == 0:
        return np.array([]), np.array([])
    
    return np.histogram(trades['pnl'], bins=bins)


def calculate_time_between_trades(trades: pd.DataFrame) -> float:
    """
    Calculate the average time between trades in hours.
    
    Args:
        trades: DataFrame containing trade data with 'entry_time' column
        
    Returns:
        Average time between trades in hours
    """
    if len(trades) <= 1 or 'entry_time' not in trades.columns:
        return 0.0
    
    # Sort trades by entry time
    sorted_trades = trades.sort_values('entry_time')
    
    # Calculate time differences
    time_diffs = sorted_trades['entry_time'].diff().dropna()
    
    # Convert to hours
    time_diffs_hours = time_diffs.dt.total_seconds() / 3600
    
    return time_diffs_hours.mean()


def calculate_win_rate_by_day_of_week(trades: pd.DataFrame) -> Dict[str, float]:
    """
    Calculate the win rate broken down by day of the week.
    
    Args:
        trades: DataFrame containing trade data with 'entry_time' and 'pnl' columns
        
    Returns:
        Dictionary with day of week as key and win rate as value
    """
    if len(trades) == 0 or 'entry_time' not in trades.columns:
        return {}
    
    # Add day of week column
    trades = trades.copy()
    trades['day_of_week'] = trades['entry_time'].dt.day_name()
    
    # Calculate win rate for each day
    result = {}
    for day in trades['day_of_week'].unique():
        day_trades = trades[trades['day_of_week'] == day]
        result[day] = calculate_win_rate(day_trades)
    
    return result


def calculate_profit_by_hour(trades: pd.DataFrame) -> Dict[int, float]:
    """
    Calculate the total profit broken down by hour of day.
    
    Args:
        trades: DataFrame containing trade data with 'entry_time' and 'pnl' columns
        
    Returns:
        Dictionary with hour as key and total profit as value
    """
    if len(trades) == 0 or 'entry_time' not in trades.columns:
        return {}
    
    # Add hour column
    trades = trades.copy()
    trades['hour'] = trades['entry_time'].dt.hour
    
    # Calculate total profit for each hour
    result = {}
    for hour in range(24):
        hour_trades = trades[trades['hour'] == hour]
        if not hour_trades.empty:
            result[hour] = hour_trades['pnl'].sum()
        else:
            result[hour] = 0.0
    
    return result


def calculate_risk_reward_ratio(trades: pd.DataFrame) -> float:
    """
    Calculate the average risk-reward ratio based on take profit and stop loss levels.
    
    Args:
        trades: DataFrame containing trade data with 'take_profit' and 'stop_loss' columns
               relative to entry price, or 'mfe' and 'mae' columns
        
    Returns:
        Average risk-reward ratio
    """
    if len(trades) == 0:
        # Check for take_profit and stop_loss columns
        if 'take_profit' in trades.columns and 'stop_loss' in trades.columns:
            tp_values = trades['take_profit'].abs()
            sl_values = trades['stop_loss'].abs()
            
            if sl_values.mean() == 0:
                return float('inf')
            
            return tp_values.mean() / sl_values.mean()
            
        # Alternatively, use MFE and MAE if available
        elif 'mfe' in trades.columns and 'mae' in trades.columns:
            if trades['mae'].mean() == 0:
                return float('inf')
                
            return trades['mfe'].mean() / trades['mae'].mean()
            
    return 0.0


def calculate_recovery_factor(trades: pd.DataFrame) -> float:
    """
    Calculate the recovery factor (net profit divided by maximum drawdown).
    
    Args:
        trades: DataFrame containing trade data with at least a 'pnl' column
        
    Returns:
        Recovery factor
    """
    if len(trades) == 0:
        return 0.0
    
    net_profit = trades['pnl'].sum()
    max_dd = calculate_max_drawdown_in_trades(trades)
    
    if max_dd == 0:
        return 0.0 if net_profit <= 0 else float('inf')
    
    return net_profit / max_dd


def calculate_payoff_ratio(trades: pd.DataFrame) -> float:
    """
    Calculate the payoff ratio (average profit / average loss).
    
    Args:
        trades: DataFrame containing trade data with at least a 'pnl' column
        
    Returns:
        Payoff ratio
    """
    # This is the same as average_win_loss_ratio
    return calculate_average_win_loss_ratio(trades)


def calculate_profit_per_day(trades: pd.DataFrame) -> float:
    """
    Calculate the average profit per trading day.
    
    Args:
        trades: DataFrame containing trade data with 'entry_time' and 'pnl' columns
        
    Returns:
        Average profit per day
    """
    if len(trades) == 0 or 'entry_time' not in trades.columns:
        return 0.0
    
    # Get total profit
    total_profit = trades['pnl'].sum()
    
    # Calculate unique trading days
    unique_days = trades['entry_time'].dt.date.nunique()
    
    if unique_days == 0:
        return total_profit
    
    return total_profit / unique_days


def generate_trade_summary(trades: pd.DataFrame) -> Dict[str, Any]:
    """
    Generate a comprehensive summary of trade metrics.
    
    Args:
        trades: DataFrame containing trade data
        
    Returns:
        Dictionary with trade metrics
    """
    if len(trades) == 0:
        return {
            'total_trades': 0,
            'win_rate': 0.0,
            'profit_factor': 0.0,
            'expectancy': 0.0
        }
    
    # Generate summary
    summary = {
        'total_trades': len(trades),
        'win_rate': calculate_win_rate(trades),
        'profit_factor': calculate_profit_factor(trades),
        'average_profit_per_trade': calculate_average_profit_per_trade(trades),
        'average_win_loss_ratio': calculate_average_win_loss_ratio(trades),
        'expectancy': calculate_expectancy(trades),
        'largest_winning_trade': calculate_largest_winning_trade(trades),
        'largest_losing_trade': calculate_largest_losing_trade(trades),
        'max_consecutive_wins': calculate_max_consecutive_wins(trades),
        'max_consecutive_losses': calculate_max_consecutive_losses(trades),
        'max_drawdown': calculate_max_drawdown_in_trades(trades),
        'recovery_factor': calculate_recovery_factor(trades),
        'total_profit': trades['pnl'].sum()
    }
    
    # Add time-based metrics if time columns are available
    if 'entry_time' in trades.columns:
        summary.update({
            'trades_per_day': calculate_trades_per_day(trades),
            'profit_per_day': calculate_profit_per_day(trades),
            'win_rate_by_day': calculate_win_rate_by_day_of_week(trades),
            'profit_by_hour': calculate_profit_by_hour(trades)
        })
        
        if 'exit_time' in trades.columns:
            summary['average_holding_time'] = calculate_average_holding_time(trades)
            summary['time_between_trades'] = calculate_time_between_trades(trades)
    
    # Add MAE/MFE metrics if available
    if 'mae' in trades.columns:
        summary['average_mae'] = calculate_average_mae(trades)
    
    if 'mfe' in trades.columns:
        summary['average_mfe'] = calculate_average_mfe(trades)
    
    # Add risk-reward ratio if possible
    if ('take_profit' in trades.columns and 'stop_loss' in trades.columns) or \
       ('mfe' in trades.columns and 'mae' in trades.columns):
        summary['risk_reward_ratio'] = calculate_risk_reward_ratio(trades)
    
    return summary 