"""
Performance Metrics Module

This module contains functions for analyzing the overall performance of a trading system,
including return metrics, risk-adjusted performance metrics, and comparison benchmarks.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List, Tuple
from scipy import stats


def calculate_total_return(equity_curve: pd.Series) -> float:
    """
    Calculate the total return of the equity curve.
    
    Args:
        equity_curve: Series of equity values over time
        
    Returns:
        Total return as a decimal
    """
    if len(equity_curve) < 2:
        return 0.0
    
    return (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1.0


def calculate_annual_return(equity_curve: pd.Series, trading_days_per_year: int = 252) -> float:
    """
    Calculate the annualized return of the equity curve.
    
    Args:
        equity_curve: Series of equity values over time, indexed by datetime
        trading_days_per_year: Number of trading days in a year
        
    Returns:
        Annualized return as a decimal
    """
    if len(equity_curve) < 2:
        return 0.0
    
    # Calculate total return
    total_return = calculate_total_return(equity_curve)
    
    # Calculate number of years
    if isinstance(equity_curve.index, pd.DatetimeIndex):
        start_date = equity_curve.index[0]
        end_date = equity_curve.index[-1]
        days = (end_date - start_date).days
        years = days / 365.25
    else:
        # If not a datetime index, assume each data point is a day
        years = len(equity_curve) / trading_days_per_year
    
    if years == 0:
        return total_return
    
    # Calculate annualized return
    return (1 + total_return) ** (1 / years) - 1


def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0, 
                          trading_days_per_year: int = 252) -> float:
    """
    Calculate the Sharpe ratio of a returns series.
    
    Args:
        returns: Series of returns (not cumulative)
        risk_free_rate: Annual risk-free rate as a decimal
        trading_days_per_year: Number of trading days in a year
        
    Returns:
        Sharpe ratio
    """
    if len(returns) < 2:
        return 0.0
    
    # Convert annual risk-free rate to daily
    daily_risk_free = (1 + risk_free_rate) ** (1 / trading_days_per_year) - 1
    
    # Calculate excess returns
    excess_returns = returns - daily_risk_free
    
    # Calculate standard deviation of returns
    std_dev = returns.std()
    
    if std_dev == 0:
        return 0.0
    
    # Calculate daily Sharpe ratio
    daily_sharpe = excess_returns.mean() / std_dev
    
    # Annualize Sharpe ratio
    annual_sharpe = daily_sharpe * np.sqrt(trading_days_per_year)
    
    return annual_sharpe


def calculate_sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0,
                           trading_days_per_year: int = 252, target_return: float = 0.0) -> float:
    """
    Calculate the Sortino ratio of a returns series.
    
    Args:
        returns: Series of returns (not cumulative)
        risk_free_rate: Annual risk-free rate as a decimal
        trading_days_per_year: Number of trading days in a year
        target_return: Target return (usually 0 or risk-free rate)
        
    Returns:
        Sortino ratio
    """
    if len(returns) < 2:
        return 0.0
    
    # Convert annual risk-free rate to daily
    daily_risk_free = (1 + risk_free_rate) ** (1 / trading_days_per_year) - 1
    
    # Calculate excess returns
    excess_returns = returns - daily_risk_free
    
    # Calculate downside returns
    downside_returns = returns[returns < target_return]
    
    if len(downside_returns) == 0:
        return float('inf') if excess_returns.mean() > 0 else 0.0
    
    # Calculate downside deviation
    downside_deviation = np.sqrt(((downside_returns - target_return) ** 2).mean())
    
    if downside_deviation == 0:
        return float('inf') if excess_returns.mean() > 0 else 0.0
    
    # Calculate daily Sortino ratio
    daily_sortino = excess_returns.mean() / downside_deviation
    
    # Annualize Sortino ratio
    annual_sortino = daily_sortino * np.sqrt(trading_days_per_year)
    
    return annual_sortino


def calculate_calmar_ratio(equity_curve: pd.Series, trading_days_per_year: int = 252) -> float:
    """
    Calculate the Calmar ratio (annualized return / maximum drawdown).
    
    Args:
        equity_curve: Series of equity values over time, indexed by datetime
        trading_days_per_year: Number of trading days in a year
        
    Returns:
        Calmar ratio
    """
    if len(equity_curve) < 2:
        return 0.0
    
    # Calculate annualized return
    annual_return = calculate_annual_return(equity_curve, trading_days_per_year)
    
    # Calculate maximum drawdown
    # Convert equity curve to returns
    returns = equity_curve.pct_change().dropna()
    
    # Calculate cumulative returns
    cum_returns = (1 + returns).cumprod()
    
    # Calculate running maximum
    running_max = cum_returns.cummax()
    
    # Calculate drawdown
    drawdown = (cum_returns / running_max) - 1
    
    # Calculate maximum drawdown
    max_drawdown = abs(drawdown.min())
    
    if max_drawdown == 0:
        return float('inf') if annual_return > 0 else 0.0
    
    # Calculate Calmar ratio
    return annual_return / max_drawdown


def calculate_information_ratio(returns: pd.Series, benchmark_returns: pd.Series, 
                               trading_days_per_year: int = 252) -> float:
    """
    Calculate the Information ratio.
    
    Args:
        returns: Series of returns (not cumulative)
        benchmark_returns: Series of benchmark returns
        trading_days_per_year: Number of trading days in a year
        
    Returns:
        Information ratio
    """
    if len(returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    
    # Align the series
    returns, benchmark_returns = returns.align(benchmark_returns, join='inner')
    
    if len(returns) < 2:
        return 0.0
    
    # Calculate tracking error
    tracking_diff = returns - benchmark_returns
    tracking_error = tracking_diff.std()
    
    if tracking_error == 0:
        return 0.0
    
    # Calculate daily information ratio
    daily_ir = tracking_diff.mean() / tracking_error
    
    # Annualize Information ratio
    annual_ir = daily_ir * np.sqrt(trading_days_per_year)
    
    return annual_ir


def calculate_treynor_ratio(returns: pd.Series, benchmark_returns: pd.Series, 
                           risk_free_rate: float = 0.0, trading_days_per_year: int = 252) -> float:
    """
    Calculate the Treynor ratio.
    
    Args:
        returns: Series of returns (not cumulative)
        benchmark_returns: Series of benchmark returns
        risk_free_rate: Annual risk-free rate as a decimal
        trading_days_per_year: Number of trading days in a year
        
    Returns:
        Treynor ratio
    """
    if len(returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    
    # Align the series
    returns, benchmark_returns = returns.align(benchmark_returns, join='inner')
    
    if len(returns) < 2:
        return 0.0
    
    # Convert annual risk-free rate to daily
    daily_risk_free = (1 + risk_free_rate) ** (1 / trading_days_per_year) - 1
    
    # Calculate excess returns
    excess_returns = returns - daily_risk_free
    
    # Calculate beta using covariance and variance
    beta = returns.cov(benchmark_returns) / benchmark_returns.var()
    
    if beta == 0:
        return float('inf') if excess_returns.mean() > 0 else 0.0
    
    # Calculate daily Treynor ratio
    daily_treynor = excess_returns.mean() / beta
    
    # Annualize Treynor ratio
    annual_treynor = daily_treynor * trading_days_per_year
    
    return annual_treynor


def calculate_alpha(returns: pd.Series, benchmark_returns: pd.Series, 
                   risk_free_rate: float = 0.0, trading_days_per_year: int = 252) -> float:
    """
    Calculate Jensen's Alpha.
    
    Args:
        returns: Series of returns (not cumulative)
        benchmark_returns: Series of benchmark returns
        risk_free_rate: Annual risk-free rate as a decimal
        trading_days_per_year: Number of trading days in a year
        
    Returns:
        Jensen's Alpha (annualized)
    """
    if len(returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    
    # Align the series
    returns, benchmark_returns = returns.align(benchmark_returns, join='inner')
    
    if len(returns) < 2:
        return 0.0
    
    # Convert annual risk-free rate to daily
    daily_risk_free = (1 + risk_free_rate) ** (1 / trading_days_per_year) - 1
    
    # Calculate beta using covariance and variance
    beta = returns.cov(benchmark_returns) / benchmark_returns.var()
    
    # Calculate daily alpha
    daily_alpha = returns.mean() - (daily_risk_free + beta * (benchmark_returns.mean() - daily_risk_free))
    
    # Annualize alpha
    annual_alpha = daily_alpha * trading_days_per_year
    
    return annual_alpha


def calculate_beta(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """
    Calculate beta (sensitivity to market movements).
    
    Args:
        returns: Series of returns (not cumulative)
        benchmark_returns: Series of benchmark returns
        
    Returns:
        Beta value
    """
    if len(returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    
    # Align the series
    returns, benchmark_returns = returns.align(benchmark_returns, join='inner')
    
    if len(returns) < 2:
        return 0.0
    
    # Calculate beta using covariance and variance
    beta = returns.cov(benchmark_returns) / benchmark_returns.var()
    
    return beta


def calculate_r_squared(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """
    Calculate R-squared (coefficient of determination).
    
    Args:
        returns: Series of returns (not cumulative)
        benchmark_returns: Series of benchmark returns
        
    Returns:
        R-squared value
    """
    if len(returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    
    # Align the series
    returns, benchmark_returns = returns.align(benchmark_returns, join='inner')
    
    if len(returns) < 2:
        return 0.0
    
    # Calculate R-squared using correlation
    correlation = returns.corr(benchmark_returns)
    r_squared = correlation ** 2
    
    return r_squared


def calculate_volatility(returns: pd.Series, trading_days_per_year: int = 252) -> float:
    """
    Calculate the annualized volatility (standard deviation of returns).
    
    Args:
        returns: Series of returns (not cumulative)
        trading_days_per_year: Number of trading days in a year
        
    Returns:
        Annualized volatility as a decimal
    """
    if len(returns) < 2:
        return 0.0
    
    # Calculate daily volatility
    daily_volatility = returns.std()
    
    # Annualize volatility
    annual_volatility = daily_volatility * np.sqrt(trading_days_per_year)
    
    return annual_volatility


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """
    Calculate the maximum drawdown of an equity curve.
    
    Args:
        equity_curve: Series of equity values over time
        
    Returns:
        Maximum drawdown as a decimal
    """
    if len(equity_curve) < 2:
        return 0.0
    
    # Calculate returns
    returns = equity_curve.pct_change().dropna()
    
    # Calculate cumulative returns
    cum_returns = (1 + returns).cumprod()
    
    # Calculate running maximum
    running_max = cum_returns.cummax()
    
    # Calculate drawdown
    drawdown = (cum_returns / running_max) - 1
    
    # Calculate maximum drawdown
    max_drawdown = abs(drawdown.min())
    
    return max_drawdown


def calculate_skewness(returns: pd.Series) -> float:
    """
    Calculate the skewness of returns.
    
    Args:
        returns: Series of returns (not cumulative)
        
    Returns:
        Skewness value
    """
    if len(returns) < 2:
        return 0.0
    
    return float(returns.skew())


def calculate_kurtosis(returns: pd.Series) -> float:
    """
    Calculate the excess kurtosis of returns.
    
    Args:
        returns: Series of returns (not cumulative)
        
    Returns:
        Excess kurtosis value
    """
    if len(returns) < 2:
        return 0.0
    
    return float(returns.kurtosis())


def calculate_monthly_returns(equity_curve: pd.Series) -> pd.Series:
    """
    Calculate monthly returns from an equity curve.
    
    Args:
        equity_curve: Series of equity values over time, indexed by datetime
        
    Returns:
        Series of monthly returns
    """
    if len(equity_curve) < 2 or not isinstance(equity_curve.index, pd.DatetimeIndex):
        return pd.Series(dtype=float)
    
    # Resample to month-end
    monthly_equity = equity_curve.resample('M').last()
    
    # Calculate monthly returns
    monthly_returns = monthly_equity.pct_change().dropna()
    
    return monthly_returns


def calculate_annual_returns(equity_curve: pd.Series) -> pd.Series:
    """
    Calculate annual returns from an equity curve.
    
    Args:
        equity_curve: Series of equity values over time, indexed by datetime
        
    Returns:
        Series of annual returns
    """
    if len(equity_curve) < 2 or not isinstance(equity_curve.index, pd.DatetimeIndex):
        return pd.Series(dtype=float)
    
    # Resample to year-end
    annual_equity = equity_curve.resample('Y').last()
    
    # Calculate annual returns
    annual_returns = annual_equity.pct_change().dropna()
    
    return annual_returns


def calculate_gain_to_pain_ratio(returns: pd.Series) -> float:
    """
    Calculate the gain-to-pain ratio (sum of returns / sum of absolute negative returns).
    
    Args:
        returns: Series of returns (not cumulative)
        
    Returns:
        Gain-to-pain ratio
    """
    if len(returns) < 2:
        return 0.0
    
    # Calculate sum of returns
    sum_returns = returns.sum()
    
    # Calculate sum of absolute negative returns
    sum_abs_negative = abs(returns[returns < 0].sum())
    
    if sum_abs_negative == 0:
        return float('inf') if sum_returns > 0 else 0.0
    
    return sum_returns / sum_abs_negative


def calculate_upside_capture_ratio(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """
    Calculate the upside capture ratio relative to a benchmark.
    
    Args:
        returns: Series of returns (not cumulative)
        benchmark_returns: Series of benchmark returns
        
    Returns:
        Upside capture ratio
    """
    if len(returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    
    # Align the series
    returns, benchmark_returns = returns.align(benchmark_returns, join='inner')
    
    if len(returns) < 2:
        return 0.0
    
    # Filter for periods when benchmark is positive
    mask = benchmark_returns > 0
    upside_returns = returns[mask]
    upside_benchmark = benchmark_returns[mask]
    
    if len(upside_returns) == 0 or upside_benchmark.mean() == 0:
        return 0.0
    
    # Calculate upside capture ratio
    return upside_returns.mean() / upside_benchmark.mean()


def calculate_downside_capture_ratio(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """
    Calculate the downside capture ratio relative to a benchmark.
    
    Args:
        returns: Series of returns (not cumulative)
        benchmark_returns: Series of benchmark returns
        
    Returns:
        Downside capture ratio (lower is better)
    """
    if len(returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    
    # Align the series
    returns, benchmark_returns = returns.align(benchmark_returns, join='inner')
    
    if len(returns) < 2:
        return 0.0
    
    # Filter for periods when benchmark is negative
    mask = benchmark_returns < 0
    downside_returns = returns[mask]
    downside_benchmark = benchmark_returns[mask]
    
    if len(downside_returns) == 0 or downside_benchmark.mean() == 0:
        return 0.0
    
    # Calculate downside capture ratio
    return downside_returns.mean() / downside_benchmark.mean()


def calculate_batting_average(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """
    Calculate the batting average (frequency of outperforming the benchmark).
    
    Args:
        returns: Series of returns (not cumulative)
        benchmark_returns: Series of benchmark returns
        
    Returns:
        Batting average as a decimal (0 to 1)
    """
    if len(returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    
    # Align the series
    returns, benchmark_returns = returns.align(benchmark_returns, join='inner')
    
    if len(returns) == 0:
        return 0.0
    
    # Calculate how many times returns are better than benchmark
    outperformance_count = (returns > benchmark_returns).sum()
    
    return outperformance_count / len(returns)


def generate_performance_summary(equity_curve: pd.Series, benchmark_equity: Optional[pd.Series] = None, 
                               risk_free_rate: float = 0.0, trading_days_per_year: int = 252) -> Dict[str, Any]:
    """
    Generate a comprehensive performance summary.
    
    Args:
        equity_curve: Series of equity values over time, indexed by datetime
        benchmark_equity: Series of benchmark equity values over time
        risk_free_rate: Annual risk-free rate as a decimal
        trading_days_per_year: Number of trading days in a year
        
    Returns:
        Dictionary with performance metrics
    """
    if len(equity_curve) < 2:
        return {
            'total_return': 0.0,
            'annual_return': 0.0,
            'volatility': 0.0,
            'max_drawdown': 0.0
        }
    
    # Calculate returns from equity
    returns = equity_curve.pct_change().dropna()
    
    # Initialize summary
    summary = {
        'total_return': calculate_total_return(equity_curve),
        'annual_return': calculate_annual_return(equity_curve, trading_days_per_year),
        'volatility': calculate_volatility(returns, trading_days_per_year),
        'sharpe_ratio': calculate_sharpe_ratio(returns, risk_free_rate, trading_days_per_year),
        'sortino_ratio': calculate_sortino_ratio(returns, risk_free_rate, trading_days_per_year),
        'max_drawdown': calculate_max_drawdown(equity_curve),
        'calmar_ratio': calculate_calmar_ratio(equity_curve, trading_days_per_year),
        'skewness': calculate_skewness(returns),
        'kurtosis': calculate_kurtosis(returns),
        'gain_to_pain_ratio': calculate_gain_to_pain_ratio(returns)
    }
    
    # Add benchmark metrics if benchmark is provided
    if benchmark_equity is not None and len(benchmark_equity) >= 2:
        benchmark_returns = benchmark_equity.pct_change().dropna()
        
        # Align the series for benchmark metrics
        aligned_returns, aligned_benchmark = returns.align(benchmark_returns, join='inner')
        
        if len(aligned_returns) >= 2:
            summary.update({
                'benchmark_total_return': calculate_total_return(benchmark_equity),
                'benchmark_annual_return': calculate_annual_return(benchmark_equity, trading_days_per_year),
                'benchmark_volatility': calculate_volatility(benchmark_returns, trading_days_per_year),
                'benchmark_max_drawdown': calculate_max_drawdown(benchmark_equity),
                'alpha': calculate_alpha(aligned_returns, aligned_benchmark, risk_free_rate, trading_days_per_year),
                'beta': calculate_beta(aligned_returns, aligned_benchmark),
                'r_squared': calculate_r_squared(aligned_returns, aligned_benchmark),
                'information_ratio': calculate_information_ratio(aligned_returns, aligned_benchmark, trading_days_per_year),
                'treynor_ratio': calculate_treynor_ratio(aligned_returns, aligned_benchmark, risk_free_rate, trading_days_per_year),
                'upside_capture': calculate_upside_capture_ratio(aligned_returns, aligned_benchmark),
                'downside_capture': calculate_downside_capture_ratio(aligned_returns, aligned_benchmark),
                'batting_average': calculate_batting_average(aligned_returns, aligned_benchmark)
            })
    
    return summary 