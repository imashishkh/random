"""
Financial analytics metrics calculations.

This module provides functions for calculating various financial metrics
such as Sharpe ratio, Sortino ratio, drawdown, and other risk/performance measures.
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime, timedelta

def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.02/252, annualization_factor: int = 252) -> Optional[float]:
    """
    Calculate the Sharpe ratio.
    
    Args:
        returns: Daily returns series
        risk_free_rate: Risk-free rate (default: 2% annual converted to daily)
        annualization_factor: Annualization factor (default: 252 trading days)
        
    Returns:
        Sharpe ratio or None if there's insufficient data
    """
    if len(returns) < 2:
        return None
        
    excess_returns = returns - risk_free_rate
    
    # Handle case where all returns are identical
    if returns.std() == 0:
        return None
        
    return float(excess_returns.mean() / excess_returns.std() * np.sqrt(annualization_factor))

def calculate_sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.02/252, target_return: float = 0, annualization_factor: int = 252) -> Optional[float]:
    """
    Calculate the Sortino ratio, which only penalizes downside volatility.
    
    Args:
        returns: Daily returns series
        risk_free_rate: Risk-free rate (default: 2% annual converted to daily)
        target_return: Minimum acceptable return (default: 0)
        annualization_factor: Annualization factor (default: 252 trading days)
        
    Returns:
        Sortino ratio or None if there's insufficient data
    """
    if len(returns) < 2:
        return None
        
    excess_returns = returns - risk_free_rate
    downside_returns = excess_returns[excess_returns < target_return]
    
    if len(downside_returns) < 1:
        return float('inf')  # No downside returns
        
    downside_deviation = np.sqrt(np.mean(downside_returns**2)) * np.sqrt(annualization_factor)
    
    if downside_deviation == 0:
        return float('inf')  # No downside deviation
        
    return float(excess_returns.mean() * annualization_factor / downside_deviation)

def calculate_max_drawdown(returns: pd.Series) -> float:
    """
    Calculate the maximum drawdown from a series of returns.
    
    Args:
        returns: Series of returns
        
    Returns:
        Maximum drawdown as a percentage (0-1)
    """
    if len(returns) < 2:
        return 0.0
    
    # Calculate cumulative returns
    cumulative = (1 + returns).cumprod()
    
    # Calculate running maximum
    running_max = cumulative.cummax()
    
    # Calculate drawdown
    drawdown = (cumulative / running_max) - 1
    
    # Get maximum drawdown
    max_dd = drawdown.min()
    
    return float(abs(max_dd))

def calculate_win_loss_ratio(trades_df: pd.DataFrame, pnl_column: str = 'pnl') -> Optional[float]:
    """
    Calculate the win/loss ratio from a DataFrame of trades.
    
    Args:
        trades_df: DataFrame of trades
        pnl_column: Name of the column containing P&L values
        
    Returns:
        Win/loss ratio or None if there are no trades
    """
    if trades_df.empty:
        return None
    
    wins = len(trades_df[trades_df[pnl_column] > 0])
    losses = len(trades_df[trades_df[pnl_column] < 0])
    
    if losses == 0:
        return float('inf') if wins > 0 else 0.0
    
    return float(wins / losses)

def calculate_profit_factor(trades_df: pd.DataFrame, pnl_column: str = 'pnl') -> Optional[float]:
    """
    Calculate the profit factor from a DataFrame of trades.
    
    Profit factor is the ratio of gross profits to gross losses.
    
    Args:
        trades_df: DataFrame of trades
        pnl_column: Name of the column containing P&L values
        
    Returns:
        Profit factor or None if there are no trades
    """
    if trades_df.empty:
        return None
    
    gross_profit = trades_df[trades_df[pnl_column] > 0][pnl_column].sum()
    gross_loss = abs(trades_df[trades_df[pnl_column] < 0][pnl_column].sum())
    
    if gross_loss == 0:
        return float('inf') if gross_profit > 0 else 0.0
    
    return float(gross_profit / gross_loss)

def calculate_average_trade(trades_df: pd.DataFrame, pnl_column: str = 'pnl') -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Calculate average trade metrics from a DataFrame of trades.
    
    Args:
        trades_df: DataFrame of trades
        pnl_column: Name of the column containing P&L values
        
    Returns:
        Tuple of (average trade P&L, average winning trade, average losing trade)
    """
    if trades_df.empty:
        return None, None, None
    
    avg_trade = float(trades_df[pnl_column].mean()) if len(trades_df) > 0 else 0.0
    
    winning_trades = trades_df[trades_df[pnl_column] > 0]
    losing_trades = trades_df[trades_df[pnl_column] < 0]
    
    avg_win = float(winning_trades[pnl_column].mean()) if len(winning_trades) > 0 else None
    avg_loss = float(losing_trades[pnl_column].mean()) if len(losing_trades) > 0 else None
    
    return avg_trade, avg_win, avg_loss

def calculate_trade_expectancy(trades_df: pd.DataFrame, pnl_column: str = 'pnl') -> Optional[float]:
    """
    Calculate trade expectancy from a DataFrame of trades.
    
    Expectancy = (Win Rate × Average Win) - (Loss Rate × Average Loss)
    
    Args:
        trades_df: DataFrame of trades
        pnl_column: Name of the column containing P&L values
        
    Returns:
        Trade expectancy or None if there are no trades
    """
    if trades_df.empty:
        return None
    
    total_trades = len(trades_df)
    winning_trades = trades_df[trades_df[pnl_column] > 0]
    losing_trades = trades_df[trades_df[pnl_column] < 0]
    
    win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
    loss_rate = len(losing_trades) / total_trades if total_trades > 0 else 0
    
    avg_win = winning_trades[pnl_column].mean() if len(winning_trades) > 0 else 0
    avg_loss = abs(losing_trades[pnl_column].mean()) if len(losing_trades) > 0 else 0
    
    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    
    return float(expectancy)

def calculate_daily_returns(trades_df: pd.DataFrame, pnl_column: str = 'pnl', timestamp_column: str = 'close_time') -> pd.Series:
    """
    Calculate daily returns from a DataFrame of trades.
    
    Args:
        trades_df: DataFrame of trades
        pnl_column: Name of the column containing P&L values
        timestamp_column: Name of the column containing timestamp
        
    Returns:
        Series of daily returns
    """
    if trades_df.empty:
        return pd.Series()
    
    # Ensure timestamp column is datetime
    trades_df = trades_df.copy()
    if not pd.api.types.is_datetime64_dtype(trades_df[timestamp_column]):
        trades_df[timestamp_column] = pd.to_datetime(trades_df[timestamp_column])
    
    # Group by date and sum P&L
    daily_pnl = trades_df.groupby(trades_df[timestamp_column].dt.date)[pnl_column].sum()
    
    return daily_pnl

def detect_anomalies(trades_df: pd.DataFrame, pnl_column: str = 'pnl', window: int = 20, z_threshold: float = 3.0) -> pd.Series:
    """
    Detect anomalous trades using Z-score.
    
    Args:
        trades_df: DataFrame of trades
        pnl_column: Name of the column containing P&L values
        window: Rolling window size for Z-score calculation
        z_threshold: Z-score threshold for anomaly detection
        
    Returns:
        Boolean series indicating anomalies
    """
    if len(trades_df) < window:
        return pd.Series([False] * len(trades_df), index=trades_df.index)
    
    # Calculate rolling mean and std
    rolling_mean = trades_df[pnl_column].rolling(window=window).mean()
    rolling_std = trades_df[pnl_column].rolling(window=window).std()
    
    # Calculate Z-scores
    z_scores = (trades_df[pnl_column] - rolling_mean) / rolling_std
    
    # Identify anomalies
    return abs(z_scores) > z_threshold

def calculate_volatility(returns: pd.Series, annualization_factor: int = 252) -> Optional[float]:
    """
    Calculate the annualized volatility of returns.
    
    Args:
        returns: Series of returns
        annualization_factor: Annualization factor (default: 252 trading days)
        
    Returns:
        Annualized volatility or None if there's insufficient data
    """
    if len(returns) < 2:
        return None
    
    return float(returns.std() * np.sqrt(annualization_factor))

def calculate_var(returns: pd.Series, confidence_level: float = 0.95) -> Optional[float]:
    """
    Calculate Value at Risk (VaR) using historical method.
    
    Args:
        returns: Series of returns
        confidence_level: Confidence level for VaR (default: 0.95)
        
    Returns:
        Value at Risk or None if there's insufficient data
    """
    if len(returns) < 10:  # Arbitrary threshold for statistical significance
        return None
    
    # Sort returns in ascending order
    sorted_returns = sorted(returns)
    
    # Calculate the index of the VaR percentile
    index = int(np.ceil((1 - confidence_level) * len(sorted_returns))) - 1
    index = max(0, index)  # Ensure index is not negative
    
    # Get the VaR value
    var = abs(sorted_returns[index])
    
    return float(var)

def calculate_beta(returns: pd.Series, market_returns: pd.Series) -> Optional[float]:
    """
    Calculate beta (systematic risk) relative to a market index.
    
    Args:
        returns: Series of returns
        market_returns: Series of market returns
        
    Returns:
        Beta coefficient or None if there's insufficient data
    """
    if len(returns) < 2 or len(market_returns) < 2:
        return None
    
    # Ensure both series have the same length
    min_length = min(len(returns), len(market_returns))
    returns = returns[-min_length:]
    market_returns = market_returns[-min_length:]
    
    # Calculate covariance and variance
    covariance = returns.cov(market_returns)
    variance = market_returns.var()
    
    if variance == 0:
        return None
    
    beta = covariance / variance
    
    return float(beta)

def calculate_calmar_ratio(returns: pd.Series, period_years: float = 3.0) -> Optional[float]:
    """
    Calculate Calmar ratio (annualized return / maximum drawdown).
    
    Args:
        returns: Series of returns
        period_years: Period in years to calculate the ratio for
        
    Returns:
        Calmar ratio or None if there's insufficient data
    """
    if len(returns) < 252:  # At least a year of data
        return None
    
    # Calculate annualized return
    total_return = (1 + returns).prod() - 1
    annualized_return = (1 + total_return) ** (1 / period_years) - 1
    
    # Calculate maximum drawdown
    max_dd = calculate_max_drawdown(returns)
    
    if max_dd == 0:
        return float('inf') if annualized_return > 0 else float('-inf')
    
    calmar_ratio = annualized_return / max_dd
    
    return float(calmar_ratio) 