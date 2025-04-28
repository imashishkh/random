"""
Performance Metrics Module

This module contains functions for calculating performance metrics from backtest results.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Union, List, Tuple
from scipy import stats


def calculate_returns(equity_curve: pd.Series) -> pd.Series:
    """
    Calculate returns from an equity curve.
    
    Args:
        equity_curve: Series of portfolio/strategy equity values
        
    Returns:
        Series of returns
    """
    return equity_curve.pct_change().fillna(0)


def calculate_log_returns(equity_curve: pd.Series) -> pd.Series:
    """
    Calculate logarithmic returns from an equity curve.
    
    Args:
        equity_curve: Series of portfolio/strategy equity values
        
    Returns:
        Series of log returns
    """
    return np.log(equity_curve / equity_curve.shift(1)).fillna(0)


def calculate_total_return(equity_curve: pd.Series) -> float:
    """
    Calculate total return from an equity curve.
    
    Args:
        equity_curve: Series of portfolio/strategy equity values
        
    Returns:
        Total return as a percentage
    """
    if len(equity_curve) < 2 or equity_curve.iloc[0] == 0:
        return 0.0
    
    return (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1


def calculate_annualized_return(equity_curve: pd.Series) -> float:
    """
    Calculate annualized return from an equity curve.
    
    Args:
        equity_curve: Series of portfolio/strategy equity values (with datetime index)
        
    Returns:
        Annualized return as a percentage
    """
    if len(equity_curve) < 2 or equity_curve.iloc[0] == 0:
        return 0.0
    
    # Calculate total return
    total_return = calculate_total_return(equity_curve)
    
    # Calculate years elapsed
    start_date = equity_curve.index[0]
    end_date = equity_curve.index[-1]
    years = (end_date - start_date).days / 365.25
    
    if years < 0.01:  # Avoid division by very small numbers
        years = 0.01
    
    # Calculate annualized return
    return ((1 + total_return) ** (1 / years)) - 1


def calculate_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """
    Calculate Sharpe ratio from a series of returns.
    
    Args:
        returns: Series of strategy returns
        risk_free_rate: Annualized risk-free rate
        periods_per_year: Number of periods in a year (252 for daily, 12 for monthly, etc.)
        
    Returns:
        Sharpe ratio
    """
    if len(returns) < 2:
        return 0.0
    
    # Convert annualized risk-free rate to per-period rate
    rf_per_period = (1 + risk_free_rate) ** (1 / periods_per_year) - 1
    
    # Calculate excess returns
    excess_returns = returns - rf_per_period
    
    # Calculate annualized Sharpe ratio
    return np.sqrt(periods_per_year) * np.mean(excess_returns) / np.std(excess_returns, ddof=1)


def calculate_sortino_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
    target_return: float = 0.0
) -> float:
    """
    Calculate Sortino ratio from a series of returns.
    
    Args:
        returns: Series of strategy returns
        risk_free_rate: Annualized risk-free rate
        periods_per_year: Number of periods in a year (252 for daily, 12 for monthly, etc.)
        target_return: Minimum acceptable return
        
    Returns:
        Sortino ratio
    """
    if len(returns) < 2:
        return 0.0
    
    # Convert annualized risk-free rate to per-period rate
    rf_per_period = (1 + risk_free_rate) ** (1 / periods_per_year) - 1
    
    # Calculate excess returns
    excess_returns = returns - rf_per_period
    
    # Calculate downside returns (negative returns)
    downside_returns = excess_returns[excess_returns < target_return]
    
    if len(downside_returns) == 0 or np.std(downside_returns, ddof=1) == 0:
        return float('inf') if np.mean(excess_returns) > 0 else 0.0
    
    # Calculate downside deviation
    downside_deviation = np.std(downside_returns, ddof=1)
    
    # Calculate annualized Sortino ratio
    return np.sqrt(periods_per_year) * np.mean(excess_returns) / downside_deviation


def calculate_calmar_ratio(
    equity_curve: pd.Series,
    periods_per_year: int = 252
) -> float:
    """
    Calculate Calmar ratio (return / maximum drawdown).
    
    Args:
        equity_curve: Series of portfolio/strategy equity values
        periods_per_year: Number of periods in a year (252 for daily, 12 for monthly, etc.)
        
    Returns:
        Calmar ratio
    """
    if len(equity_curve) < 2:
        return 0.0
    
    # Calculate annualized return
    ann_return = calculate_annualized_return(equity_curve)
    
    # Calculate maximum drawdown
    max_dd = calculate_max_drawdown(equity_curve)
    
    if max_dd == 0:
        return float('inf') if ann_return > 0 else 0.0
    
    return ann_return / max_dd


def calculate_volatility(returns: pd.Series, periods_per_year: int = 252) -> float:
    """
    Calculate annualized volatility from a series of returns.
    
    Args:
        returns: Series of strategy returns
        periods_per_year: Number of periods in a year (252 for daily, 12 for monthly, etc.)
        
    Returns:
        Annualized volatility
    """
    if len(returns) < 2:
        return 0.0
    
    return np.std(returns, ddof=1) * np.sqrt(periods_per_year)


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """
    Calculate maximum drawdown from an equity curve.
    
    Args:
        equity_curve: Series of portfolio/strategy equity values
        
    Returns:
        Maximum drawdown as a positive percentage
    """
    if len(equity_curve) < 2:
        return 0.0
    
    # Calculate running maximum
    running_max = equity_curve.cummax()
    
    # Calculate drawdown
    drawdown = (equity_curve - running_max) / running_max
    
    # Return maximum drawdown as positive percentage
    return abs(drawdown.min())


def calculate_drawdowns(equity_curve: pd.Series) -> pd.DataFrame:
    """
    Calculate all drawdown periods from an equity curve.
    
    Args:
        equity_curve: Series of portfolio/strategy equity values
        
    Returns:
        DataFrame with drawdown periods, depths, and durations
    """
    if len(equity_curve) < 2:
        return pd.DataFrame(columns=['start', 'end', 'depth', 'duration'])
    
    # Calculate running maximum
    running_max = equity_curve.cummax()
    
    # Calculate drawdown
    drawdown = (equity_curve - running_max) / running_max
    
    # Find drawdown periods
    is_drawdown = drawdown < 0
    
    # Identify drawdown period start and end points
    # Convert to numpy for faster processing
    is_dd_np = is_drawdown.values
    
    # Find start indices
    starts = np.where(~is_dd_np[:-1] & is_dd_np[1:])[0] + 1
    
    # Handle case where series starts in drawdown
    if is_dd_np[0]:
        starts = np.insert(starts, 0, 0)
    
    # Find end indices
    ends = np.where(is_dd_np[:-1] & ~is_dd_np[1:])[0] + 1
    
    # Handle case where series ends in drawdown
    if is_dd_np[-1]:
        ends = np.append(ends, len(is_dd_np) - 1)
    
    # Ensure starts and ends have the same length
    min_len = min(len(starts), len(ends))
    starts = starts[:min_len]
    ends = ends[:min_len]
    
    if len(starts) == 0:
        return pd.DataFrame(columns=['start', 'end', 'depth', 'duration'])
    
    # Convert indices to timestamps
    start_dates = equity_curve.index[starts]
    end_dates = equity_curve.index[ends]
    
    # Calculate drawdown depths and durations
    depths = []
    durations = []
    
    for i in range(len(starts)):
        # Depth is the maximum drawdown during the period
        period_drawdown = drawdown.iloc[starts[i]:ends[i]+1]
        depth = abs(period_drawdown.min())
        depths.append(depth)
        
        # Duration is the length of the drawdown period in days
        duration = (end_dates[i] - start_dates[i]).days
        durations.append(duration)
    
    # Create DataFrame
    drawdown_df = pd.DataFrame({
        'start': start_dates,
        'end': end_dates,
        'depth': depths,
        'duration': durations
    })
    
    # Sort by depth (largest first)
    drawdown_df = drawdown_df.sort_values('depth', ascending=False).reset_index(drop=True)
    
    return drawdown_df


def calculate_win_rate(trades: pd.DataFrame) -> float:
    """
    Calculate win rate from a DataFrame of trades.
    
    Args:
        trades: DataFrame with trade results, must have a 'pnl' column
        
    Returns:
        Win rate as a percentage
    """
    if len(trades) == 0 or 'pnl' not in trades.columns:
        return 0.0
    
    winning_trades = (trades['pnl'] > 0).sum()
    total_trades = len(trades)
    
    return winning_trades / total_trades if total_trades > 0 else 0.0


def calculate_profit_factor(trades: pd.DataFrame) -> float:
    """
    Calculate profit factor from a DataFrame of trades.
    
    Args:
        trades: DataFrame with trade results, must have a 'pnl' column
        
    Returns:
        Profit factor (gross profit / gross loss)
    """
    if len(trades) == 0 or 'pnl' not in trades.columns:
        return 0.0
    
    gross_profit = trades.loc[trades['pnl'] > 0, 'pnl'].sum()
    gross_loss = abs(trades.loc[trades['pnl'] < 0, 'pnl'].sum())
    
    return gross_profit / gross_loss if gross_loss != 0 else float('inf')


def calculate_expectancy(trades: pd.DataFrame) -> float:
    """
    Calculate expectancy (average trade P&L) from a DataFrame of trades.
    
    Args:
        trades: DataFrame with trade results, must have a 'pnl' column
        
    Returns:
        Expectancy value
    """
    if len(trades) == 0 or 'pnl' not in trades.columns:
        return 0.0
    
    return trades['pnl'].mean()


def calculate_avg_win_loss_ratio(trades: pd.DataFrame) -> float:
    """
    Calculate average win/loss ratio from a DataFrame of trades.
    
    Args:
        trades: DataFrame with trade results, must have a 'pnl' column
        
    Returns:
        Average win/loss ratio
    """
    if len(trades) == 0 or 'pnl' not in trades.columns:
        return 0.0
    
    avg_win = trades.loc[trades['pnl'] > 0, 'pnl'].mean() if any(trades['pnl'] > 0) else 0
    avg_loss = abs(trades.loc[trades['pnl'] < 0, 'pnl'].mean()) if any(trades['pnl'] < 0) else 0
    
    return avg_win / avg_loss if avg_loss != 0 else float('inf')


def calculate_max_consecutive_wins(trades: pd.DataFrame) -> int:
    """
    Calculate maximum consecutive winning trades.
    
    Args:
        trades: DataFrame with trade results, must have a 'pnl' column
        
    Returns:
        Maximum number of consecutive winning trades
    """
    if len(trades) == 0 or 'pnl' not in trades.columns:
        return 0
    
    # Create array of win/loss results
    wins = (trades['pnl'] > 0).astype(int).values
    
    # Count consecutive wins
    max_consec = 0
    current_consec = 0
    
    for win in wins:
        if win == 1:
            current_consec += 1
            max_consec = max(max_consec, current_consec)
        else:
            current_consec = 0
    
    return max_consec


def calculate_max_consecutive_losses(trades: pd.DataFrame) -> int:
    """
    Calculate maximum consecutive losing trades.
    
    Args:
        trades: DataFrame with trade results, must have a 'pnl' column
        
    Returns:
        Maximum number of consecutive losing trades
    """
    if len(trades) == 0 or 'pnl' not in trades.columns:
        return 0
    
    # Create array of win/loss results
    losses = (trades['pnl'] < 0).astype(int).values
    
    # Count consecutive losses
    max_consec = 0
    current_consec = 0
    
    for loss in losses:
        if loss == 1:
            current_consec += 1
            max_consec = max(max_consec, current_consec)
        else:
            current_consec = 0
    
    return max_consec


def calculate_largest_win(trades: pd.DataFrame) -> float:
    """
    Calculate largest winning trade.
    
    Args:
        trades: DataFrame with trade results, must have a 'pnl' column
        
    Returns:
        Largest winning trade amount
    """
    if len(trades) == 0 or 'pnl' not in trades.columns:
        return 0.0
    
    return trades['pnl'].max() if any(trades['pnl'] > 0) else 0.0


def calculate_largest_loss(trades: pd.DataFrame) -> float:
    """
    Calculate largest losing trade.
    
    Args:
        trades: DataFrame with trade results, must have a 'pnl' column
        
    Returns:
        Largest losing trade amount (as a positive number)
    """
    if len(trades) == 0 or 'pnl' not in trades.columns:
        return 0.0
    
    return abs(trades['pnl'].min()) if any(trades['pnl'] < 0) else 0.0


def calculate_average_trade_duration(trades: pd.DataFrame) -> float:
    """
    Calculate average trade duration in days.
    
    Args:
        trades: DataFrame with trade results, must have 'entry_time' and 'exit_time' columns
        
    Returns:
        Average trade duration in days
    """
    if (len(trades) == 0 or 
        'entry_time' not in trades.columns or 
        'exit_time' not in trades.columns):
        return 0.0
    
    # Calculate duration for each trade
    durations = (trades['exit_time'] - trades['entry_time']).dt.total_seconds() / 86400  # Convert to days
    
    return durations.mean()


def calculate_equity_curve(trades: pd.DataFrame, initial_capital: float = 10000.0) -> pd.Series:
    """
    Calculate equity curve from a DataFrame of trades.
    
    Args:
        trades: DataFrame with trade results, must have 'pnl' and 'exit_time' columns
        initial_capital: Initial capital amount
        
    Returns:
        Series of equity values indexed by time
    """
    if (len(trades) == 0 or 
        'pnl' not in trades.columns or 
        'exit_time' not in trades.columns):
        return pd.Series([initial_capital], index=[pd.Timestamp.now()])
    
    # Sort trades by exit time
    sorted_trades = trades.sort_values('exit_time')
    
    # Calculate cumulative P&L
    cumulative_pnl = sorted_trades['pnl'].cumsum()
    
    # Create equity curve
    equity = initial_capital + cumulative_pnl
    
    # Index by exit time
    equity.index = sorted_trades['exit_time']
    
    return equity


def calculate_cagr(equity_curve: pd.Series) -> float:
    """
    Calculate Compound Annual Growth Rate (CAGR).
    
    Args:
        equity_curve: Series of portfolio/strategy equity values (with datetime index)
        
    Returns:
        CAGR as a percentage
    """
    return calculate_annualized_return(equity_curve)


def calculate_monthly_returns(equity_curve: pd.Series) -> pd.Series:
    """
    Calculate monthly returns from an equity curve.
    
    Args:
        equity_curve: Series of portfolio/strategy equity values (with datetime index)
        
    Returns:
        Series of monthly returns
    """
    if len(equity_curve) < 2:
        return pd.Series()
    
    # Resample to month-end and calculate returns
    monthly = equity_curve.resample('M').last()
    monthly_returns = monthly.pct_change().dropna()
    
    return monthly_returns


def calculate_annual_returns(equity_curve: pd.Series) -> pd.Series:
    """
    Calculate annual returns from an equity curve.
    
    Args:
        equity_curve: Series of portfolio/strategy equity values (with datetime index)
        
    Returns:
        Series of annual returns
    """
    if len(equity_curve) < 2:
        return pd.Series()
    
    # Resample to year-end and calculate returns
    annual = equity_curve.resample('A').last()
    annual_returns = annual.pct_change().dropna()
    
    return annual_returns


def calculate_skewness(returns: pd.Series) -> float:
    """
    Calculate skewness of returns distribution.
    
    Args:
        returns: Series of returns
        
    Returns:
        Skewness value
    """
    if len(returns) < 2:
        return 0.0
    
    return stats.skew(returns.dropna())


def calculate_kurtosis(returns: pd.Series) -> float:
    """
    Calculate excess kurtosis of returns distribution.
    
    Args:
        returns: Series of returns
        
    Returns:
        Excess kurtosis value
    """
    if len(returns) < 2:
        return 0.0
    
    return stats.kurtosis(returns.dropna())


def calculate_var(returns: pd.Series, alpha: float = 0.05) -> float:
    """
    Calculate Value at Risk (VaR).
    
    Args:
        returns: Series of returns
        alpha: Significance level (default: 0.05 for 95% VaR)
        
    Returns:
        VaR value (positive number representing loss)
    """
    if len(returns) < 2:
        return 0.0
    
    # Calculate VaR as a quantile of the returns distribution
    return abs(returns.quantile(alpha))


def calculate_cvar(returns: pd.Series, alpha: float = 0.05) -> float:
    """
    Calculate Conditional Value at Risk (CVaR) / Expected Shortfall.
    
    Args:
        returns: Series of returns
        alpha: Significance level (default: 0.05 for 95% CVaR)
        
    Returns:
        CVaR value (positive number representing expected loss)
    """
    if len(returns) < 2:
        return 0.0
    
    # Sort returns
    sorted_returns = returns.sort_values()
    
    # Calculate CVaR as the mean of returns below VaR
    var_cutoff = int(len(sorted_returns) * alpha)
    cvar_returns = sorted_returns.iloc[:var_cutoff]
    
    return abs(cvar_returns.mean())


def calculate_downside_deviation(returns: pd.Series, min_acceptable_return: float = 0.0) -> float:
    """
    Calculate downside deviation.
    
    Args:
        returns: Series of returns
        min_acceptable_return: Minimum acceptable return
        
    Returns:
        Downside deviation
    """
    if len(returns) < 2:
        return 0.0
    
    # Calculate returns below the minimum acceptable return
    downside_returns = returns[returns < min_acceptable_return]
    
    if len(downside_returns) == 0:
        return 0.0
    
    # Calculate squared deviations
    downside_squared = (downside_returns - min_acceptable_return) ** 2
    
    # Calculate downside deviation
    return np.sqrt(downside_squared.sum() / len(returns))


def calculate_beta(
    returns: pd.Series,
    benchmark_returns: pd.Series
) -> float:
    """
    Calculate beta (systematic risk) against a benchmark.
    
    Args:
        returns: Series of strategy returns
        benchmark_returns: Series of benchmark returns
        
    Returns:
        Beta coefficient
    """
    if len(returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    
    # Align series
    aligned_returns = pd.DataFrame({
        'returns': returns,
        'benchmark': benchmark_returns
    }).dropna()
    
    if len(aligned_returns) < 2:
        return 0.0
    
    # Calculate covariance and variance
    covariance = np.cov(aligned_returns['returns'], aligned_returns['benchmark'])[0, 1]
    benchmark_variance = np.var(aligned_returns['benchmark'], ddof=1)
    
    if benchmark_variance == 0:
        return 0.0
    
    return covariance / benchmark_variance


def calculate_alpha(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """
    Calculate alpha (excess return) against a benchmark.
    
    Args:
        returns: Series of strategy returns
        benchmark_returns: Series of benchmark returns
        risk_free_rate: Annualized risk-free rate
        periods_per_year: Number of periods in a year (252 for daily, 12 for monthly, etc.)
        
    Returns:
        Annualized alpha
    """
    if len(returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    
    # Align series
    aligned_data = pd.DataFrame({
        'returns': returns,
        'benchmark': benchmark_returns
    }).dropna()
    
    if len(aligned_data) < 2:
        return 0.0
    
    # Convert annualized risk-free rate to per-period rate
    rf_per_period = (1 + risk_free_rate) ** (1 / periods_per_year) - 1
    
    # Calculate beta
    beta = calculate_beta(aligned_data['returns'], aligned_data['benchmark'])
    
    # Calculate annualized alpha using CAPM formula
    mean_excess_return = aligned_data['returns'].mean() - rf_per_period
    mean_excess_benchmark = aligned_data['benchmark'].mean() - rf_per_period
    
    periodic_alpha = mean_excess_return - (beta * mean_excess_benchmark)
    
    # Annualize alpha
    return periodic_alpha * periods_per_year


def calculate_information_ratio(
    returns: pd.Series,
    benchmark_returns: pd.Series
) -> float:
    """
    Calculate information ratio.
    
    Args:
        returns: Series of strategy returns
        benchmark_returns: Series of benchmark returns
        
    Returns:
        Information ratio
    """
    if len(returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    
    # Align series
    aligned_data = pd.DataFrame({
        'returns': returns,
        'benchmark': benchmark_returns
    }).dropna()
    
    if len(aligned_data) < 2:
        return 0.0
    
    # Calculate tracking error
    excess_returns = aligned_data['returns'] - aligned_data['benchmark']
    tracking_error = excess_returns.std(ddof=1)
    
    if tracking_error == 0:
        return 0.0
    
    # Calculate information ratio
    return excess_returns.mean() / tracking_error


def calculate_treynor_ratio(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """
    Calculate Treynor ratio.
    
    Args:
        returns: Series of strategy returns
        benchmark_returns: Series of benchmark returns
        risk_free_rate: Annualized risk-free rate
        periods_per_year: Number of periods in a year (252 for daily, 12 for monthly, etc.)
        
    Returns:
        Treynor ratio
    """
    if len(returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    
    # Align series
    aligned_data = pd.DataFrame({
        'returns': returns,
        'benchmark': benchmark_returns
    }).dropna()
    
    if len(aligned_data) < 2:
        return 0.0
    
    # Convert annualized risk-free rate to per-period rate
    rf_per_period = (1 + risk_free_rate) ** (1 / periods_per_year) - 1
    
    # Calculate beta
    beta = calculate_beta(aligned_data['returns'], aligned_data['benchmark'])
    
    if beta == 0:
        return 0.0
    
    # Calculate average excess return
    excess_return = aligned_data['returns'].mean() - rf_per_period
    
    # Calculate annualized Treynor ratio
    return excess_return * periods_per_year / beta


def generate_performance_summary(
    equity_curve: pd.Series,
    trades: pd.DataFrame,
    benchmark_returns: Optional[pd.Series] = None,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252
) -> Dict[str, Any]:
    """
    Generate a comprehensive performance summary.
    
    Args:
        equity_curve: Series of portfolio/strategy equity values
        trades: DataFrame with trade results
        benchmark_returns: Series of benchmark returns (optional)
        risk_free_rate: Annualized risk-free rate
        periods_per_year: Number of periods in a year (252 for daily, 12 for monthly, etc.)
        
    Returns:
        Dictionary with performance metrics
    """
    # Calculate returns
    returns = calculate_returns(equity_curve)
    
    # Initialize performance summary
    summary = {
        'total_return': calculate_total_return(equity_curve),
        'cagr': calculate_cagr(equity_curve),
        'sharpe_ratio': calculate_sharpe_ratio(returns, risk_free_rate, periods_per_year),
        'sortino_ratio': calculate_sortino_ratio(returns, risk_free_rate, periods_per_year),
        'max_drawdown': calculate_max_drawdown(equity_curve),
        'calmar_ratio': calculate_calmar_ratio(equity_curve, periods_per_year),
        'volatility': calculate_volatility(returns, periods_per_year),
        'skewness': calculate_skewness(returns),
        'kurtosis': calculate_kurtosis(returns),
        'var': calculate_var(returns),
        'cvar': calculate_cvar(returns),
        'win_rate': calculate_win_rate(trades),
        'profit_factor': calculate_profit_factor(trades),
        'expectancy': calculate_expectancy(trades),
        'avg_win_loss_ratio': calculate_avg_win_loss_ratio(trades),
        'max_consecutive_wins': calculate_max_consecutive_wins(trades),
        'max_consecutive_losses': calculate_max_consecutive_losses(trades),
        'largest_win': calculate_largest_win(trades),
        'largest_loss': calculate_largest_loss(trades),
        'avg_trade_duration': calculate_average_trade_duration(trades)
    }
    
    # Add benchmark-related metrics if benchmark is provided
    if benchmark_returns is not None:
        summary.update({
            'beta': calculate_beta(returns, benchmark_returns),
            'alpha': calculate_alpha(returns, benchmark_returns, risk_free_rate, periods_per_year),
            'information_ratio': calculate_information_ratio(returns, benchmark_returns),
            'treynor_ratio': calculate_treynor_ratio(returns, benchmark_returns, risk_free_rate, periods_per_year)
        })
    
    return summary 