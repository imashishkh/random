"""
Metrics Calculator for Strategy Evaluation
-----------------------------------------
Calculates performance metrics for trading strategies.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Union


class MetricsCalculator:
    """
    Calculates performance metrics for trading strategies.
    
    This class calculates various performance metrics including returns,
    risk-adjusted metrics, drawdowns, and other trading statistics.
    """
    
    def __init__(self, 
                 risk_free_rate: float = 0.0,
                 trading_days_per_year: int = 252,
                 calculate_all: bool = True,
                 custom_metrics: Optional[Dict[str, callable]] = None):
        """
        Initialize the metrics calculator.
        
        Args:
            risk_free_rate: Annual risk-free rate for Sharpe ratio calculation
            trading_days_per_year: Number of trading days per year
            calculate_all: Whether to calculate all metrics or just basic ones
            custom_metrics: Dictionary of custom metric functions to include
        """
        self.risk_free_rate = risk_free_rate
        self.trading_days_per_year = trading_days_per_year
        self.calculate_all = calculate_all
        self.custom_metrics = custom_metrics or {}
        
        # Daily risk-free rate for daily returns
        self.daily_risk_free_rate = (1 + self.risk_free_rate) ** (1 / self.trading_days_per_year) - 1
    
    def calculate(self, 
                  positions: pd.DataFrame,
                  trades: Optional[pd.DataFrame] = None,
                  market_data: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """
        Calculate performance metrics.
        
        Args:
            positions: DataFrame with position values over time
            trades: DataFrame with individual trades (optional)
            market_data: Original market data (optional, for benchmark comparison)
            
        Returns:
            Dictionary of performance metrics
        """
        # Check if positions DataFrame has the necessary columns
        required_cols = ['timestamp', 'position_value']
        missing_cols = [col for col in required_cols if col not in positions.columns]
        
        if missing_cols:
            raise ValueError(f"Positions DataFrame missing columns: {missing_cols}")
        
        # Calculate daily returns
        positions = positions.sort_values('timestamp')
        positions['daily_return'] = positions['position_value'].pct_change()
        
        # Basic metrics
        metrics = {}
        
        # Total return
        initial_value = positions['position_value'].iloc[0]
        final_value = positions['position_value'].iloc[-1]
        metrics['total_return'] = (final_value / initial_value) - 1
        
        # Annualized return
        n_days = (positions['timestamp'].iloc[-1] - positions['timestamp'].iloc[0]).days
        n_years = n_days / 365
        metrics['annualized_return'] = (1 + metrics['total_return']) ** (1 / max(n_years, 1e-9)) - 1
        
        # Daily returns statistics
        daily_returns = positions['daily_return'].dropna().values
        metrics['mean_daily_return'] = np.mean(daily_returns)
        metrics['std_daily_return'] = np.std(daily_returns)
        
        # Annualized volatility
        metrics['annualized_volatility'] = metrics['std_daily_return'] * np.sqrt(self.trading_days_per_year)
        
        # Sharpe ratio
        excess_returns = daily_returns - self.daily_risk_free_rate
        metrics['sharpe_ratio'] = (np.mean(excess_returns) / np.std(daily_returns)) * np.sqrt(self.trading_days_per_year)
        
        # If we requested all metrics, calculate additional ones
        if self.calculate_all:
            # Sortino ratio (downside risk only)
            downside_returns = daily_returns[daily_returns < 0]
            if len(downside_returns) > 0:
                downside_deviation = np.std(downside_returns)
                metrics['sortino_ratio'] = (np.mean(excess_returns) / downside_deviation) * np.sqrt(self.trading_days_per_year)
            else:
                metrics['sortino_ratio'] = np.inf  # No downside risk
            
            # Maximum drawdown
            cumulative_returns = (1 + daily_returns).cumprod()
            running_max = np.maximum.accumulate(cumulative_returns)
            drawdowns = (cumulative_returns / running_max) - 1
            metrics['max_drawdown'] = np.min(drawdowns)
            
            # Calmar ratio
            if metrics['max_drawdown'] != 0:
                metrics['calmar_ratio'] = metrics['annualized_return'] / abs(metrics['max_drawdown'])
            else:
                metrics['calmar_ratio'] = np.inf  # No drawdown
            
            # Win rate (if trades data is provided)
            if trades is not None:
                if 'profit' in trades.columns:
                    winning_trades = trades[trades['profit'] > 0]
                    metrics['win_rate'] = len(winning_trades) / len(trades)
                    
                    # Average profit/loss
                    metrics['avg_profit'] = trades['profit'].mean()
                    metrics['avg_win'] = winning_trades['profit'].mean() if len(winning_trades) > 0 else 0
                    
                    losing_trades = trades[trades['profit'] <= 0]
                    metrics['avg_loss'] = losing_trades['profit'].mean() if len(losing_trades) > 0 else 0
                    
                    # Profit factor
                    total_profit = winning_trades['profit'].sum() if len(winning_trades) > 0 else 0
                    total_loss = abs(losing_trades['profit'].sum()) if len(losing_trades) > 0 else 0
                    
                    if total_loss > 0:
                        metrics['profit_factor'] = total_profit / total_loss
                    else:
                        metrics['profit_factor'] = np.inf  # No losing trades
            
            # Market correlation and beta (if market data is provided)
            if market_data is not None and 'close' in market_data.columns:
                # Align timestamps
                merged = pd.merge(
                    positions[['timestamp', 'daily_return']],
                    market_data[['timestamp', 'close']],
                    on='timestamp',
                    how='inner'
                )
                
                if len(merged) > 1:
                    merged['market_return'] = merged['close'].pct_change()
                    merged = merged.dropna()
                    
                    if len(merged) > 1:
                        strategy_returns = merged['daily_return'].values
                        market_returns = merged['market_return'].values
                        
                        # Correlation
                        metrics['market_correlation'] = np.corrcoef(strategy_returns, market_returns)[0, 1]
                        
                        # Beta
                        market_var = np.var(market_returns)
                        if market_var > 0:
                            covariance = np.cov(strategy_returns, market_returns)[0, 1]
                            metrics['beta'] = covariance / market_var
                        else:
                            metrics['beta'] = 0
                        
                        # Alpha (Jensen's alpha)
                        expected_return = self.daily_risk_free_rate + metrics['beta'] * (np.mean(market_returns) - self.daily_risk_free_rate)
                        metrics['alpha'] = np.mean(strategy_returns) - expected_return
                        metrics['annualized_alpha'] = metrics['alpha'] * self.trading_days_per_year
        
        # Calculate any custom metrics
        for name, metric_func in self.custom_metrics.items():
            try:
                metrics[name] = metric_func(positions, trades, market_data)
            except Exception as e:
                metrics[name] = f"Error: {str(e)}"
        
        return metrics
    
    def calculate_rolling(self,
                          positions: pd.DataFrame,
                          window: int = 60,
                          metrics: List[str] = None) -> pd.DataFrame:
        """
        Calculate rolling performance metrics.
        
        Args:
            positions: DataFrame with position values over time
            window: Rolling window size in days
            metrics: List of metrics to calculate (default: sharpe, volatility)
            
        Returns:
            DataFrame with rolling metrics
        """
        metrics = metrics or ['sharpe_ratio', 'annualized_volatility']
        positions = positions.sort_values('timestamp')
        
        # Calculate daily returns
        positions['daily_return'] = positions['position_value'].pct_change()
        
        # Initialize result DataFrame
        rolling_metrics = pd.DataFrame({'timestamp': positions['timestamp']})
        
        # Calculate rolling metrics
        for i in range(window, len(positions)):
            window_positions = positions.iloc[i-window:i].copy()
            window_metrics = self.calculate(window_positions)
            
            for metric in metrics:
                if metric in window_metrics:
                    if i == window:  # First window
                        rolling_metrics[metric] = np.nan
                    
                    rolling_metrics.loc[i, metric] = window_metrics[metric]
        
        return rolling_metrics 