"""
Risk Metrics Module

This module contains functions for analyzing the risk characteristics of a trading system,
including value at risk, drawdown metrics, and risk exposure calculations.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List, Tuple
from scipy import stats


def calculate_value_at_risk(returns: pd.Series, confidence_level: float = 0.95) -> float:
    """
    Calculate the Value at Risk (VaR) at the specified confidence level.
    
    Args:
        returns: Series of returns (not cumulative)
        confidence_level: Confidence level (e.g., 0.95 for 95% VaR)
        
    Returns:
        Value at Risk as a positive decimal
    """
    if len(returns) < 2:
        return 0.0
    
    # Calculate VaR using the historical method
    var = abs(np.percentile(returns, 100 * (1 - confidence_level)))
    
    return var


def calculate_conditional_value_at_risk(returns: pd.Series, confidence_level: float = 0.95) -> float:
    """
    Calculate the Conditional Value at Risk (CVaR) / Expected Shortfall at the specified confidence level.
    
    Args:
        returns: Series of returns (not cumulative)
        confidence_level: Confidence level (e.g., 0.95 for 95% CVaR)
        
    Returns:
        Conditional Value at Risk as a positive decimal
    """
    if len(returns) < 2:
        return 0.0
    
    # Calculate VaR
    var = calculate_value_at_risk(returns, confidence_level)
    
    # Calculate CVaR as the average of returns below VaR
    cvar_returns = returns[returns <= -var]
    
    if len(cvar_returns) == 0:
        return var
    
    return abs(cvar_returns.mean())


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


def calculate_drawdown_duration(equity_curve: pd.Series) -> Tuple[int, float]:
    """
    Calculate the maximum drawdown duration in days and the current drawdown duration.
    
    Args:
        equity_curve: Series of equity values over time
        
    Returns:
        Tuple of (max_drawdown_duration, current_drawdown_duration)
    """
    if len(equity_curve) < 2:
        return 0, 0.0
    
    # Calculate returns and cumulative returns
    returns = equity_curve.pct_change().dropna()
    cum_returns = (1 + returns).cumprod()
    
    # Calculate running maximum
    running_max = cum_returns.cummax()
    
    # Calculate drawdown
    drawdown = (cum_returns / running_max) - 1
    
    # Initialize variables
    in_drawdown = False
    current_duration = 0
    max_duration = 0
    drawdown_start = 0
    
    # Iterate through drawdowns to find durations
    for i, dd in enumerate(drawdown):
        if dd < 0:
            if not in_drawdown:
                in_drawdown = True
                drawdown_start = i
            current_duration = i - drawdown_start
        else:
            if in_drawdown:
                in_drawdown = False
                max_duration = max(max_duration, current_duration)
                current_duration = 0
    
    # Check if we're still in a drawdown at the end
    if in_drawdown:
        current_duration = len(drawdown) - 1 - drawdown_start
        max_duration = max(max_duration, current_duration)
    
    return max_duration, current_duration


def calculate_time_to_recovery(equity_curve: pd.Series) -> pd.Series:
    """
    Calculate the time to recovery for each drawdown.
    
    Args:
        equity_curve: Series of equity values over time
        
    Returns:
        Series of recovery times for each drawdown
    """
    if len(equity_curve) < 2:
        return pd.Series(dtype=float)
    
    # Calculate returns and cumulative returns
    returns = equity_curve.pct_change().dropna()
    cum_returns = (1 + returns).cumprod()
    
    # Calculate running maximum
    running_max = cum_returns.cummax()
    
    # Calculate drawdown
    drawdown = (cum_returns / running_max) - 1
    
    # Initialize variables
    recovery_times = []
    in_drawdown = False
    high_watermark = 0
    drawdown_start = 0
    
    # Iterate through drawdowns to find recovery times
    for i, (dd, eq) in enumerate(zip(drawdown, cum_returns)):
        if dd < 0:
            if not in_drawdown:
                in_drawdown = True
                drawdown_start = i
                high_watermark = running_max[i]
        elif in_drawdown and eq >= high_watermark:
            in_drawdown = False
            recovery_time = i - drawdown_start
            recovery_times.append((drawdown_start, i, recovery_time))
    
    # Create a series of recovery times
    if recovery_times:
        recovery_df = pd.DataFrame(recovery_times, columns=['start', 'end', 'recovery_time'])
        recovery_df.set_index('start', inplace=True)
        return recovery_df['recovery_time']
    else:
        return pd.Series(dtype=float)


def calculate_drawdown_statistics(equity_curve: pd.Series) -> Dict[str, Any]:
    """
    Calculate comprehensive drawdown statistics.
    
    Args:
        equity_curve: Series of equity values over time
        
    Returns:
        Dictionary with drawdown statistics
    """
    if len(equity_curve) < 2:
        return {
            'max_drawdown': 0.0,
            'avg_drawdown': 0.0,
            'max_drawdown_duration': 0,
            'avg_drawdown_duration': 0,
            'avg_recovery_time': 0
        }
    
    # Calculate returns and cumulative returns
    returns = equity_curve.pct_change().dropna()
    cum_returns = (1 + returns).cumprod()
    
    # Calculate running maximum
    running_max = cum_returns.cummax()
    
    # Calculate drawdown
    drawdown = (cum_returns / running_max) - 1
    
    # Calculate maximum drawdown
    max_drawdown = abs(drawdown.min())
    
    # Calculate average drawdown
    avg_drawdown = abs(drawdown[drawdown < 0].mean()) if any(drawdown < 0) else 0.0
    
    # Find drawdown periods
    drawdown_periods = []
    in_drawdown = False
    drawdown_start = 0
    high_watermark = 0
    
    for i, (dd, eq) in enumerate(zip(drawdown, cum_returns)):
        if dd < 0:
            if not in_drawdown:
                in_drawdown = True
                drawdown_start = i
                high_watermark = running_max[i]
        elif in_drawdown and eq >= high_watermark:
            in_drawdown = False
            drawdown_end = i
            drawdown_depth = abs(drawdown[drawdown_start:drawdown_end].min())
            drawdown_duration = drawdown_end - drawdown_start
            drawdown_periods.append({
                'start': drawdown_start,
                'end': drawdown_end,
                'depth': drawdown_depth,
                'duration': drawdown_duration,
                'recovery_time': drawdown_duration
            })
    
    # If still in drawdown at the end
    if in_drawdown:
        drawdown_end = len(drawdown) - 1
        drawdown_depth = abs(drawdown[drawdown_start:].min())
        drawdown_duration = drawdown_end - drawdown_start
        drawdown_periods.append({
            'start': drawdown_start,
            'end': drawdown_end,
            'depth': drawdown_depth,
            'duration': drawdown_duration,
            'recovery_time': None  # Still in drawdown, no recovery time
        })
    
    # Calculate statistics
    if drawdown_periods:
        max_drawdown_duration = max(period['duration'] for period in drawdown_periods)
        avg_drawdown_duration = sum(period['duration'] for period in drawdown_periods) / len(drawdown_periods)
        
        recovery_times = [period['recovery_time'] for period in drawdown_periods if period['recovery_time'] is not None]
        avg_recovery_time = sum(recovery_times) / len(recovery_times) if recovery_times else 0
    else:
        max_drawdown_duration = 0
        avg_drawdown_duration = 0
        avg_recovery_time = 0
    
    return {
        'max_drawdown': max_drawdown,
        'avg_drawdown': avg_drawdown,
        'max_drawdown_duration': max_drawdown_duration,
        'avg_drawdown_duration': avg_drawdown_duration,
        'avg_recovery_time': avg_recovery_time,
        'drawdown_periods': drawdown_periods
    }


def calculate_downside_deviation(returns: pd.Series, target_return: float = 0.0) -> float:
    """
    Calculate the downside deviation (semi-deviation) relative to a target return.
    
    Args:
        returns: Series of returns (not cumulative)
        target_return: Target return (usually 0 or risk-free rate)
        
    Returns:
        Downside deviation as a decimal
    """
    if len(returns) < 2:
        return 0.0
    
    # Calculate downside returns
    downside_returns = returns[returns < target_return]
    
    if len(downside_returns) == 0:
        return 0.0
    
    # Calculate downside deviation
    downside_deviation = np.sqrt(((downside_returns - target_return) ** 2).mean())
    
    return downside_deviation


def calculate_parametric_var(returns: pd.Series, confidence_level: float = 0.95) -> float:
    """
    Calculate the parametric Value at Risk assuming normal distribution.
    
    Args:
        returns: Series of returns (not cumulative)
        confidence_level: Confidence level (e.g., 0.95 for 95% VaR)
        
    Returns:
        Parametric Value at Risk as a positive decimal
    """
    if len(returns) < 2:
        return 0.0
    
    # Calculate mean and standard deviation
    mean = returns.mean()
    std_dev = returns.std()
    
    # Calculate the z-score for the given confidence level
    z_score = stats.norm.ppf(1 - confidence_level)
    
    # Calculate parametric VaR
    var = abs(mean + z_score * std_dev)
    
    return var


def calculate_cornish_fisher_var(returns: pd.Series, confidence_level: float = 0.95) -> float:
    """
    Calculate the Cornish-Fisher VaR adjustment for non-normal distributions.
    
    Args:
        returns: Series of returns (not cumulative)
        confidence_level: Confidence level (e.g., 0.95 for 95% VaR)
        
    Returns:
        Cornish-Fisher Value at Risk as a positive decimal
    """
    if len(returns) < 2:
        return 0.0
    
    # Calculate mean, standard deviation, skewness, and kurtosis
    mean = returns.mean()
    std_dev = returns.std()
    skewness = returns.skew()
    kurtosis = returns.kurtosis()  # Excess kurtosis
    
    # Calculate the z-score for the given confidence level
    z_score = stats.norm.ppf(1 - confidence_level)
    
    # Apply Cornish-Fisher adjustment
    cf_z_score = z_score + (z_score**2 - 1) * skewness / 6 + (z_score**3 - 3*z_score) * kurtosis / 24 - (2*z_score**3 - 5*z_score) * skewness**2 / 36
    
    # Calculate adjusted VaR
    var = abs(mean + cf_z_score * std_dev)
    
    return var


def calculate_rolling_var(returns: pd.Series, window: int = 252, confidence_level: float = 0.95) -> pd.Series:
    """
    Calculate the rolling Value at Risk over a specified window.
    
    Args:
        returns: Series of returns (not cumulative)
        window: Rolling window size
        confidence_level: Confidence level (e.g., 0.95 for 95% VaR)
        
    Returns:
        Series of rolling VaR values
    """
    if len(returns) < window:
        return pd.Series(index=returns.index, dtype=float)
    
    # Calculate rolling VaR
    rolling_var = returns.rolling(window=window).apply(
        lambda x: calculate_value_at_risk(x, confidence_level)
    )
    
    return rolling_var


def calculate_rolling_conditional_var(returns: pd.Series, window: int = 252, confidence_level: float = 0.95) -> pd.Series:
    """
    Calculate the rolling Conditional Value at Risk over a specified window.
    
    Args:
        returns: Series of returns (not cumulative)
        window: Rolling window size
        confidence_level: Confidence level (e.g., 0.95 for 95% CVaR)
        
    Returns:
        Series of rolling CVaR values
    """
    if len(returns) < window:
        return pd.Series(index=returns.index, dtype=float)
    
    # Calculate rolling CVaR
    rolling_cvar = returns.rolling(window=window).apply(
        lambda x: calculate_conditional_value_at_risk(x, confidence_level)
    )
    
    return rolling_cvar


def calculate_max_consecutive_losses(returns: pd.Series) -> int:
    """
    Calculate the maximum consecutive losing periods.
    
    Args:
        returns: Series of returns (not cumulative)
        
    Returns:
        Maximum number of consecutive losses
    """
    if len(returns) < 1:
        return 0
    
    # Create binary series of wins and losses
    losses = (returns < 0).astype(int)
    
    # Initialize variables
    current_streak = 0
    max_streak = 0
    
    # Count consecutive losses
    for loss in losses:
        if loss:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    
    return max_streak


def calculate_tail_risk_metrics(returns: pd.Series) -> Dict[str, float]:
    """
    Calculate various tail risk metrics.
    
    Args:
        returns: Series of returns (not cumulative)
        
    Returns:
        Dictionary with tail risk metrics
    """
    if len(returns) < 2:
        return {
            'var_95': 0.0,
            'cvar_95': 0.0,
            'var_99': 0.0,
            'cvar_99': 0.0,
            'parametric_var_95': 0.0,
            'cornish_fisher_var_95': 0.0
        }
    
    return {
        'var_95': calculate_value_at_risk(returns, 0.95),
        'cvar_95': calculate_conditional_value_at_risk(returns, 0.95),
        'var_99': calculate_value_at_risk(returns, 0.99),
        'cvar_99': calculate_conditional_value_at_risk(returns, 0.99),
        'parametric_var_95': calculate_parametric_var(returns, 0.95),
        'cornish_fisher_var_95': calculate_cornish_fisher_var(returns, 0.95)
    }


def calculate_stress_test(returns: pd.Series, stress_scenarios: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """
    Perform a stress test by calculating portfolio performance under different scenarios.
    
    Args:
        returns: Series of returns (not cumulative)
        stress_scenarios: Dictionary mapping scenario names to stress factors
        
    Returns:
        Dictionary with stress test results
    """
    if len(returns) < 2:
        return {}
    
    if stress_scenarios is None:
        # Default stress scenarios
        stress_scenarios = {
            'mild_stress': 1.5,  # 1.5x historical volatility
            'medium_stress': 2.0,  # 2x historical volatility
            'severe_stress': 3.0,  # 3x historical volatility
        }
    
    # Calculate mean and standard deviation
    mean = returns.mean()
    std_dev = returns.std()
    
    # Calculate stress test results
    stress_results = {}
    
    for scenario, stress_factor in stress_scenarios.items():
        # Calculate stressed return
        stressed_return = mean - stress_factor * std_dev
        stress_results[scenario] = stressed_return
    
    return stress_results


def calculate_risk_contribution(returns: pd.DataFrame) -> pd.Series:
    """
    Calculate the risk contribution of each asset in a portfolio.
    
    Args:
        returns: DataFrame of asset returns (columns are assets)
        
    Returns:
        Series of risk contributions as percentages
    """
    if len(returns) < 2 or returns.shape[1] < 2:
        return pd.Series(dtype=float)
    
    # Calculate the covariance matrix
    cov_matrix = returns.cov()
    
    # Assume equal weights for assets if not provided
    weights = np.ones(returns.shape[1]) / returns.shape[1]
    
    # Calculate portfolio variance
    portfolio_variance = np.dot(weights.T, np.dot(cov_matrix, weights))
    
    # Calculate individual risk contributions
    marginal_risk = np.dot(cov_matrix, weights)
    risk_contribution = weights * marginal_risk / portfolio_variance
    
    # Convert to a Series with asset names
    risk_contribution_series = pd.Series(risk_contribution, index=returns.columns)
    
    return risk_contribution_series


def generate_risk_summary(returns: pd.Series, equity_curve: pd.Series, 
                        benchmark_returns: Optional[pd.Series] = None) -> Dict[str, Any]:
    """
    Generate a comprehensive risk summary.
    
    Args:
        returns: Series of returns (not cumulative)
        equity_curve: Series of equity values over time
        benchmark_returns: Series of benchmark returns (optional)
        
    Returns:
        Dictionary with risk metrics
    """
    if len(returns) < 2:
        return {
            'max_drawdown': 0.0,
            'downside_deviation': 0.0,
            'var_95': 0.0,
            'cvar_95': 0.0
        }
    
    # Calculate basic risk metrics
    risk_summary = {
        'volatility': returns.std(),
        'annualized_volatility': returns.std() * np.sqrt(252),
        'max_drawdown': calculate_max_drawdown(equity_curve),
        'downside_deviation': calculate_downside_deviation(returns),
        'max_consecutive_losses': calculate_max_consecutive_losses(returns),
        'skewness': returns.skew(),
        'kurtosis': returns.kurtosis()
    }
    
    # Add drawdown statistics
    drawdown_stats = calculate_drawdown_statistics(equity_curve)
    risk_summary.update({
        'avg_drawdown': drawdown_stats['avg_drawdown'],
        'max_drawdown_duration': drawdown_stats['max_drawdown_duration'],
        'avg_drawdown_duration': drawdown_stats['avg_drawdown_duration'],
        'avg_recovery_time': drawdown_stats['avg_recovery_time']
    })
    
    # Add tail risk metrics
    tail_risk = calculate_tail_risk_metrics(returns)
    risk_summary.update(tail_risk)
    
    # Add benchmark relative metrics if available
    if benchmark_returns is not None and len(benchmark_returns) >= 2:
        # Align the series
        aligned_returns, aligned_benchmark = returns.align(benchmark_returns, join='inner')
        
        if len(aligned_returns) >= 2:
            # Calculate beta
            beta = aligned_returns.cov(aligned_benchmark) / aligned_benchmark.var()
            
            # Calculate tracking error
            tracking_error = (aligned_returns - aligned_benchmark).std() * np.sqrt(252)
            
            risk_summary.update({
                'beta': beta,
                'tracking_error': tracking_error
            })
    
    return risk_summary 