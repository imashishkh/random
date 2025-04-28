"""
Analytics service for calculating trading performance metrics.

This module provides functions to analyze trading performance,
calculate risk metrics, and generate various distribution analyses.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
import pandas as pd
import numpy as np
from functools import lru_cache

from ..api.schemas.analytics import (
    PerformanceMetric,
    PerformanceMetricsResponse,
    PnLOverTimeResponse,
    DistributionItem,
    TradeDistributionResponse,
    RiskAnalysisResponse
)
from .trade_service import TradeService
from ..database.models.trade import Trade
from ..utils.date_utils import parse_timeframe

logger = logging.getLogger(__name__)

class AnalyticsService:
    """Service for generating trading analytics and performance metrics."""
    
    def __init__(self, trade_service: TradeService):
        """
        Initialize the analytics service.
        
        Args:
            trade_service: Service for retrieving trade data
        """
        self.trade_service = trade_service
        self._cache = {}
        self._cache_timestamps = {}
    
    def _get_cache_key(self, method_name: str, agent_id: Optional[str], 
                      symbol: Optional[str], start_date: Optional[datetime], 
                      end_date: Optional[datetime]) -> str:
        """Generate a cache key based on query parameters."""
        return f"{method_name}:{agent_id}:{symbol}:{start_date}:{end_date}"
    
    def _get_date_range(self, start_date: Optional[datetime], end_date: Optional[datetime], 
                       timeframe: Optional[str]) -> Tuple[datetime, datetime]:
        """
        Determine the date range for analysis.
        
        Args:
            start_date: Explicit start date
            end_date: Explicit end date
            timeframe: Predefined timeframe (day, week, month, quarter, year)
            
        Returns:
            Tuple containing start and end dates
        """
        if timeframe:
            return parse_timeframe(timeframe)
        
        # If no timeframe provided, use explicit dates or defaults
        end = end_date or datetime.now()
        
        # Default to last 30 days if no start date provided
        if not start_date:
            start = end - timedelta(days=30)
        else:
            start = start_date
            
        return start, end
    
    def _prepare_trade_dataframe(self, trades: List[Trade]) -> pd.DataFrame:
        """Convert trade list to DataFrame for analysis."""
        if not trades:
            return pd.DataFrame()
        
        # Convert trades to dict for DataFrame creation
        trade_dicts = []
        for trade in trades:
            trade_dict = {
                "id": trade.id,
                "agent_id": trade.agent_id,
                "symbol": trade.symbol,
                "direction": trade.direction,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "entry_time": trade.entry_time,
                "exit_time": trade.exit_time,
                "position_size": trade.position_size,
                "profit_loss": trade.profit_loss,
                "status": trade.status,
                # Add other relevant fields
            }
            trade_dicts.append(trade_dict)
        
        df = pd.DataFrame(trade_dicts)
        
        # Add calculated columns
        if not df.empty:
            df["is_win"] = df["profit_loss"] > 0
            df["trade_duration"] = (df["exit_time"] - df["entry_time"]).dt.total_seconds() / 3600  # in hours
            df["entry_hour"] = df["entry_time"].dt.hour
            df["entry_day_of_week"] = df["entry_time"].dt.day_name()
            
        return df
    
    def clear_cache(self, agent_id: Optional[str] = None, 
                   symbol: Optional[str] = None) -> None:
        """
        Clear analytics cache.
        
        Args:
            agent_id: Clear cache for specific agent
            symbol: Clear cache for specific symbol
        """
        # If no parameters specified, clear all cache
        if not agent_id and not symbol:
            self._cache = {}
            self._cache_timestamps = {}
            return
            
        # Clear specific cache entries
        keys_to_remove = []
        for key in self._cache.keys():
            if (agent_id and agent_id in key) or (symbol and symbol in key):
                keys_to_remove.append(key)
                
        for key in keys_to_remove:
            if key in self._cache:
                del self._cache[key]
            if key in self._cache_timestamps:
                del self._cache_timestamps[key]
    
    def get_performance_metrics(self, agent_id: Optional[str] = None, 
                              symbol: Optional[str] = None,
                              start_date: Optional[datetime] = None, 
                              end_date: Optional[datetime] = None,
                              timeframe: Optional[str] = None,
                              use_cache: bool = True) -> PerformanceMetricsResponse:
        """
        Calculate trading performance metrics.
        
        Args:
            agent_id: Optional agent ID to filter trades
            symbol: Optional symbol to filter trades
            start_date: Start date for analysis
            end_date: End date for analysis
            timeframe: Predefined timeframe
            use_cache: Whether to use cached results
            
        Returns:
            PerformanceMetricsResponse containing the calculated metrics
        """
        # Get date range based on inputs
        start, end = self._get_date_range(start_date, end_date, timeframe)
        
        # Check cache
        cache_key = self._get_cache_key("performance", agent_id, symbol, start, end)
        if use_cache and cache_key in self._cache:
            cached_result = self._cache[cache_key]
            cached_result.cached = True
            cached_result.cache_time = self._cache_timestamps.get(cache_key)
            return cached_result
        
        try:
            # Get trades
            trades = self.trade_service.get_trades(
                agent_id=agent_id,
                symbol=symbol,
                start_date=start,
                end_date=end,
                status="closed"  # Only include completed trades
            )
            
            if not trades:
                logger.warning(f"No trades found for the given parameters: agent_id={agent_id}, symbol={symbol}")
                return PerformanceMetricsResponse(
                    total_trades=0,
                    win_rate=PerformanceMetric(value=0, unit="%"),
                    profit_factor=PerformanceMetric(value=0, unit=""),
                    average_profit=PerformanceMetric(value=0, unit="$"),
                    average_loss=PerformanceMetric(value=0, unit="$"),
                    risk_reward_ratio=PerformanceMetric(value=0, unit=""),
                    sharpe_ratio=PerformanceMetric(value=0, unit=""),
                    sortino_ratio=PerformanceMetric(value=0, unit=""),
                    max_drawdown=PerformanceMetric(value=0, unit="%"),
                    recovery_factor=PerformanceMetric(value=0, unit=""),
                    profit_per_day=PerformanceMetric(value=0, unit="$"),
                    net_profit=PerformanceMetric(value=0, unit="$"),
                    annualized_return=PerformanceMetric(value=0, unit="%")
                )
            
            # Convert to DataFrame for analysis
            df = self._prepare_trade_dataframe(trades)
            
            # Calculate metrics
            total_trades = len(trades)
            winning_trades = df[df["profit_loss"] > 0]
            losing_trades = df[df["profit_loss"] <= 0]
            
            win_count = len(winning_trades)
            win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
            
            gross_profit = winning_trades["profit_loss"].sum() if not winning_trades.empty else 0
            gross_loss = abs(losing_trades["profit_loss"].sum()) if not losing_trades.empty else 0
            
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
            
            avg_profit = winning_trades["profit_loss"].mean() if not winning_trades.empty else 0
            avg_loss = abs(losing_trades["profit_loss"].mean()) if not losing_trades.empty else 0
            
            risk_reward = avg_profit / avg_loss if avg_loss > 0 else float('inf') if avg_profit > 0 else 0
            
            # Calculate Sharpe ratio (assuming daily returns)
            daily_returns = df.groupby(df["exit_time"].dt.date)["profit_loss"].sum()
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if len(daily_returns) > 1 and daily_returns.std() > 0 else 0
            
            # Calculate Sortino ratio (downside deviation)
            downside_returns = daily_returns[daily_returns < 0]
            sortino = (daily_returns.mean() / downside_returns.std()) * np.sqrt(252) if not downside_returns.empty and downside_returns.std() > 0 else sharpe
            
            # Calculate drawdown
            cumulative_returns = df.sort_values("exit_time")["profit_loss"].cumsum()
            running_max = cumulative_returns.cummax()
            drawdown = (cumulative_returns - running_max) / running_max * 100 if not running_max.empty and running_max.max() > 0 else pd.Series([0])
            max_drawdown = abs(drawdown.min())
            
            # Calculate recovery factor
            net_profit = df["profit_loss"].sum()
            recovery_factor = net_profit / (max_drawdown / 100 * net_profit) if max_drawdown > 0 and net_profit > 0 else 0
            
            # Calculate profit per day
            date_range = (end - start).days or 1  # Avoid division by zero
            profit_per_day = net_profit / date_range
            
            # Calculate annualized return
            annualized_return = (net_profit / date_range) * 365 / 100000 * 100  # Assuming $100k account
            
            # Calculate average trade duration
            avg_duration = df["trade_duration"].mean() if "trade_duration" in df.columns else None
            
            # Calculate expectancy
            expectancy = (win_rate/100 * avg_profit) - ((100-win_rate)/100 * avg_loss) if total_trades > 0 else 0
            
            # Create response
            response = PerformanceMetricsResponse(
                total_trades=total_trades,
                win_rate=PerformanceMetric(value=round(win_rate, 2), unit="%"),
                profit_factor=PerformanceMetric(value=round(profit_factor, 2), unit=""),
                average_profit=PerformanceMetric(value=round(avg_profit, 2), unit="$"),
                average_loss=PerformanceMetric(value=round(avg_loss, 2), unit="$"),
                risk_reward_ratio=PerformanceMetric(value=round(risk_reward, 2), unit=""),
                sharpe_ratio=PerformanceMetric(value=round(sharpe, 2), unit=""),
                sortino_ratio=PerformanceMetric(value=round(sortino, 2), unit=""),
                max_drawdown=PerformanceMetric(value=round(max_drawdown, 2), unit="%"),
                recovery_factor=PerformanceMetric(value=round(recovery_factor, 2), unit=""),
                profit_per_day=PerformanceMetric(value=round(profit_per_day, 2), unit="$"),
                net_profit=PerformanceMetric(value=round(net_profit, 2), unit="$"),
                annualized_return=PerformanceMetric(value=round(annualized_return, 2), unit="%"),
                expectancy=PerformanceMetric(value=round(expectancy, 2), unit="$"),
                average_trade_duration=PerformanceMetric(value=round(avg_duration, 2), unit="hours") if avg_duration is not None else None
            )
            
            # Cache the result
            if use_cache:
                self._cache[cache_key] = response
                self._cache_timestamps[cache_key] = datetime.now()
            
            return response
            
        except Exception as e:
            logger.error(f"Error calculating performance metrics: {str(e)}", exc_info=True)
            raise
    
    def get_pnl_over_time(self, interval: str = "day",
                        agent_id: Optional[str] = None, 
                        symbol: Optional[str] = None,
                        start_date: Optional[datetime] = None, 
                        end_date: Optional[datetime] = None,
                        timeframe: Optional[str] = None,
                        use_cache: bool = True) -> List[PnLOverTimeResponse]:
        """
        Get profit and loss data over time.
        
        Args:
            interval: Time interval for grouping (day, week, month)
            agent_id: Optional agent ID to filter trades
            symbol: Optional symbol to filter trades
            start_date: Start date for analysis
            end_date: End date for analysis
            timeframe: Predefined timeframe
            use_cache: Whether to use cached results
            
        Returns:
            List of PnLOverTimeResponse objects for each interval
        """
        # Get date range based on inputs
        start, end = self._get_date_range(start_date, end_date, timeframe)
        
        # Check cache
        cache_key = self._get_cache_key(f"pnl_{interval}", agent_id, symbol, start, end)
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            # Get trades
            trades = self.trade_service.get_trades(
                agent_id=agent_id,
                symbol=symbol,
                start_date=start,
                end_date=end,
                status="closed"  # Only include completed trades
            )
            
            if not trades:
                logger.warning(f"No trades found for the given parameters: agent_id={agent_id}, symbol={symbol}")
                return []
            
            # Convert to DataFrame for analysis
            df = self._prepare_trade_dataframe(trades)
            
            # Set the time grouping based on interval
            if interval == "day":
                df["interval"] = df["exit_time"].dt.date
            elif interval == "week":
                df["interval"] = df["exit_time"].dt.to_period('W').dt.start_time
            elif interval == "month":
                df["interval"] = df["exit_time"].dt.to_period('M').dt.start_time
            else:
                logger.warning(f"Invalid interval: {interval}. Using day as default.")
                df["interval"] = df["exit_time"].dt.date
            
            # Group by interval
            grouped = df.groupby("interval").agg({
                "profit_loss": "sum",
                "id": "count",
                "is_win": ["sum", "count"]
            }).reset_index()
            
            # Rename columns
            grouped.columns = ["date", "profit_loss", "trade_count", "win_count", "total_count"]
            
            # Calculate win rate and cumulative P&L
            grouped["win_rate"] = (grouped["win_count"] / grouped["total_count"]) * 100
            grouped["cumulative_profit_loss"] = grouped["profit_loss"].cumsum()
            
            # Convert to response objects
            result = []
            for _, row in grouped.iterrows():
                response = PnLOverTimeResponse(
                    date=row["date"],
                    profit_loss=float(row["profit_loss"]),
                    cumulative_profit_loss=float(row["cumulative_profit_loss"]),
                    trade_count=int(row["trade_count"]),
                    win_count=int(row["win_count"]),
                    loss_count=int(row["total_count"] - row["win_count"]),
                    win_rate=float(row["win_rate"])
                )
                result.append(response)
            
            # Cache the result
            if use_cache:
                self._cache[cache_key] = result
                self._cache_timestamps[cache_key] = datetime.now()
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating PnL over time: {str(e)}", exc_info=True)
            raise
    
    def get_trade_distribution(self, agent_id: Optional[str] = None, 
                             symbol: Optional[str] = None,
                             start_date: Optional[datetime] = None, 
                             end_date: Optional[datetime] = None,
                             timeframe: Optional[str] = None,
                             use_cache: bool = True) -> TradeDistributionResponse:
        """
        Analyze trade distribution by various parameters.
        
        Args:
            agent_id: Optional agent ID to filter trades
            symbol: Optional symbol to filter trades
            start_date: Start date for analysis
            end_date: End date for analysis
            timeframe: Predefined timeframe
            use_cache: Whether to use cached results
            
        Returns:
            TradeDistributionResponse with various distribution breakdowns
        """
        # Get date range based on inputs
        start, end = self._get_date_range(start_date, end_date, timeframe)
        
        # Check cache
        cache_key = self._get_cache_key("distribution", agent_id, symbol, start, end)
        if use_cache and cache_key in self._cache:
            cached_result = self._cache[cache_key]
            cached_result.cached = True
            cached_result.cache_time = self._cache_timestamps.get(cache_key)
            return cached_result
        
        try:
            # Get trades
            trades = self.trade_service.get_trades(
                agent_id=agent_id,
                symbol=symbol,
                start_date=start,
                end_date=end,
                status="closed"  # Only include completed trades
            )
            
            if not trades:
                logger.warning(f"No trades found for the given parameters: agent_id={agent_id}, symbol={symbol}")
                return TradeDistributionResponse(
                    by_symbol=[],
                    by_direction=[],
                    by_time_of_day=[],
                    by_day_of_week=[]
                )
            
            # Convert to DataFrame for analysis
            df = self._prepare_trade_dataframe(trades)
            total_trades = len(df)
            
            # Distribution by symbol
            by_symbol = self._get_distribution_by_category(df, "symbol", total_trades)
            
            # Distribution by direction
            by_direction = self._get_distribution_by_category(df, "direction", total_trades)
            
            # Distribution by time of day
            df["hour_of_day"] = df["entry_time"].dt.hour
            by_time_of_day = self._get_distribution_by_category(df, "hour_of_day", total_trades)
            
            # Distribution by day of week
            df["day_of_week"] = df["entry_time"].dt.day_name()
            by_day_of_week = self._get_distribution_by_category(df, "day_of_week", total_trades)
            
            # Optional: Distribution by trade duration
            by_trade_duration = None
            if "trade_duration" in df.columns:
                # Create duration bins
                bins = [0, 1, 4, 24, 72, float('inf')]  # hours
                labels = ["< 1h", "1-4h", "4-24h", "1-3d", "> 3d"]
                df["duration_category"] = pd.cut(df["trade_duration"], bins=bins, labels=labels)
                by_trade_duration = self._get_distribution_by_category(df, "duration_category", total_trades)
            
            # Create response
            response = TradeDistributionResponse(
                by_symbol=by_symbol,
                by_direction=by_direction,
                by_time_of_day=by_time_of_day,
                by_day_of_week=by_day_of_week,
                by_trade_duration=by_trade_duration
            )
            
            # Cache the result
            if use_cache:
                self._cache[cache_key] = response
                self._cache_timestamps[cache_key] = datetime.now()
            
            return response
            
        except Exception as e:
            logger.error(f"Error analyzing trade distribution: {str(e)}", exc_info=True)
            raise
    
    def _get_distribution_by_category(self, df: pd.DataFrame, category: str, total_trades: int) -> List[DistributionItem]:
        """
        Helper method to get distribution analysis by a specific category.
        
        Args:
            df: DataFrame with trade data
            category: Column name to group by
            total_trades: Total number of trades
            
        Returns:
            List of DistributionItem objects
        """
        result = []
        
        if df.empty:
            return result
            
        # Group by the category
        grouped = df.groupby(category).agg({
            "id": "count",
            "profit_loss": "sum",
            "is_win": ["sum", "count"]
        }).reset_index()
        
        # Rename columns
        grouped.columns = [category, "count", "profit_loss", "win_count", "total_count"]
        
        # Calculate percentages and win rates
        grouped["percentage"] = (grouped["count"] / total_trades) * 100
        grouped["win_rate"] = (grouped["win_count"] / grouped["total_count"]) * 100
        
        # Calculate average profit and loss
        for idx, group_value in enumerate(grouped[category]):
            category_df = df[df[category] == group_value]
            wins = category_df[category_df["profit_loss"] > 0]
            losses = category_df[category_df["profit_loss"] <= 0]
            
            avg_profit = wins["profit_loss"].mean() if not wins.empty else 0
            avg_loss = abs(losses["profit_loss"].mean()) if not losses.empty else 0
            
            grouped.at[idx, "avg_profit"] = avg_profit
            grouped.at[idx, "avg_loss"] = avg_loss
        
        # Convert to response objects
        for _, row in grouped.iterrows():
            item = DistributionItem(
                category=str(row[category]),
                count=int(row["count"]),
                percentage=float(row["percentage"]),
                profit_loss=float(row["profit_loss"]),
                win_rate=float(row["win_rate"]),
                average_profit=float(row["avg_profit"]) if "avg_profit" in grouped.columns else None,
                average_loss=float(row["avg_loss"]) if "avg_loss" in grouped.columns else None
            )
            result.append(item)
        
        # Sort by count (descending)
        result.sort(key=lambda x: x.count, reverse=True)
        
        return result
    
    def get_risk_analysis(self, agent_id: Optional[str] = None, 
                         symbol: Optional[str] = None,
                         start_date: Optional[datetime] = None, 
                         end_date: Optional[datetime] = None,
                         timeframe: Optional[str] = None,
                         confidence_level: float = 0.95,
                         use_cache: bool = True) -> RiskAnalysisResponse:
        """
        Calculate risk metrics for the trading activity.
        
        Args:
            agent_id: Optional agent ID to filter trades
            symbol: Optional symbol to filter trades
            start_date: Start date for analysis
            end_date: End date for analysis
            timeframe: Predefined timeframe
            confidence_level: Confidence level for VaR calculation
            use_cache: Whether to use cached results
            
        Returns:
            RiskAnalysisResponse with various risk metrics
        """
        # Get date range based on inputs
        start, end = self._get_date_range(start_date, end_date, timeframe)
        
        # Check cache
        cache_key = self._get_cache_key(f"risk_{confidence_level}", agent_id, symbol, start, end)
        if use_cache and cache_key in self._cache:
            cached_result = self._cache[cache_key]
            cached_result.cached = True
            cached_result.cache_time = self._cache_timestamps.get(cache_key)
            return cached_result
        
        try:
            # Get trades
            trades = self.trade_service.get_trades(
                agent_id=agent_id,
                symbol=symbol,
                start_date=start,
                end_date=end,
                status="closed"  # Only include completed trades
            )
            
            if not trades:
                logger.warning(f"No trades found for the given parameters: agent_id={agent_id}, symbol={symbol}")
                return RiskAnalysisResponse(
                    max_drawdown=PerformanceMetric(value=0, unit="%"),
                    max_drawdown_amount=PerformanceMetric(value=0, unit="$"),
                    drawdown_duration=PerformanceMetric(value=0, unit="days"),
                    value_at_risk=PerformanceMetric(value=0, unit="$"),
                    conditional_value_at_risk=PerformanceMetric(value=0, unit="$"),
                    max_consecutive_losses=0,
                    max_consecutive_wins=0,
                    risk_reward_ratio=PerformanceMetric(value=0, unit="")
                )
            
            # Convert to DataFrame for analysis
            df = self._prepare_trade_dataframe(trades)
            
            # Calculate drawdown
            cumulative_pnl = df.sort_values("exit_time")["profit_loss"].cumsum()
            running_max = cumulative_pnl.cummax()
            drawdown = (cumulative_pnl - running_max)
            drawdown_pct = drawdown / running_max * 100 if not running_max.empty and running_max.max() > 0 else pd.Series([0])
            
            max_drawdown_pct = abs(drawdown_pct.min())
            max_drawdown_amount = abs(drawdown.min())
            
            # Calculate drawdown duration
            # This is a simplification - real drawdown duration would track each drawdown period
            drawdown_periods = (drawdown < 0).astype(int).diff().fillna(0)
            start_indices = drawdown_periods[drawdown_periods == 1].index
            end_indices = drawdown_periods[drawdown_periods == -1].index
            
            if len(start_indices) > 0 and len(end_indices) > 0:
                # Make sure we have matching start and end points
                if start_indices[0] > end_indices[0]:
                    end_indices = end_indices[1:]
                if len(start_indices) > len(end_indices):
                    start_indices = start_indices[:len(end_indices)]
                
                drawdown_durations = [(df.iloc[end - 1]["exit_time"] - df.iloc[start]["exit_time"]).days 
                                     for start, end in zip(start_indices, end_indices)]
                avg_drawdown_duration = sum(drawdown_durations) / len(drawdown_durations) if drawdown_durations else 0
            else:
                avg_drawdown_duration = 0
            
            # Calculate Value at Risk (VaR)
            daily_returns = df.groupby(df["exit_time"].dt.date)["profit_loss"].sum()
            var = np.percentile(daily_returns, (1 - confidence_level) * 100)
            var = abs(var) if var < 0 else 0  # VaR is typically reported as a positive number
            
            # Calculate Conditional VaR (CVaR) / Expected Shortfall
            cvar_threshold = daily_returns.quantile(1 - confidence_level)
            cvar = daily_returns[daily_returns <= cvar_threshold].mean()
            cvar = abs(cvar) if not pd.isna(cvar) and cvar < 0 else 0
            
            # Calculate consecutive wins/losses
            df = df.sort_values("exit_time")
            is_win = df["profit_loss"] > 0
            
            # Count consecutive occurrences
            consecutive_wins = 0
            consecutive_losses = 0
            current_streak = 0
            current_type = None
            
            for win in is_win:
                if current_type is None:
                    current_type = win
                    current_streak = 1
                elif current_type == win:
                    current_streak += 1
                else:
                    if current_type:  # True = win
                        consecutive_wins = max(consecutive_wins, current_streak)
                    else:
                        consecutive_losses = max(consecutive_losses, current_streak)
                    current_type = win
                    current_streak = 1
            
            # Check final streak
            if current_type is not None:
                if current_type:
                    consecutive_wins = max(consecutive_wins, current_streak)
                else:
                    consecutive_losses = max(consecutive_losses, current_streak)
            
            # Calculate risk/reward ratio
            winning_trades = df[df["profit_loss"] > 0]
            losing_trades = df[df["profit_loss"] <= 0]
            
            avg_profit = winning_trades["profit_loss"].mean() if not winning_trades.empty else 0
            avg_loss = abs(losing_trades["profit_loss"].mean()) if not losing_trades.empty else 0
            
            risk_reward = avg_profit / avg_loss if avg_loss > 0 else float('inf') if avg_profit > 0 else 0
            
            # Calculate additional advanced metrics
            # Downside deviation
            benchmark_return = 0  # Could be risk-free rate if available
            downside_returns = daily_returns[daily_returns < benchmark_return]
            downside_deviation = downside_returns.std() if not downside_returns.empty else 0
            
            # Ulcer Index - measure of drawdown severity
            squared_drawdowns = np.square(drawdown_pct.clip(upper=0))
            ulcer_index = np.sqrt(squared_drawdowns.mean())
            
            # Calmar ratio - return to max drawdown ratio
            annualized_return = (daily_returns.mean() * 252) if not daily_returns.empty else 0
            calmar_ratio = annualized_return / max_drawdown_pct if max_drawdown_pct > 0 else float('inf') if annualized_return > 0 else 0
            
            # Create response
            response = RiskAnalysisResponse(
                max_drawdown=PerformanceMetric(value=round(max_drawdown_pct, 2), unit="%"),
                max_drawdown_amount=PerformanceMetric(value=round(max_drawdown_amount, 2), unit="$"),
                drawdown_duration=PerformanceMetric(value=round(avg_drawdown_duration, 1), unit="days"),
                value_at_risk=PerformanceMetric(value=round(var, 2), unit="$"),
                conditional_value_at_risk=PerformanceMetric(value=round(cvar, 2), unit="$"),
                max_consecutive_losses=consecutive_losses,
                max_consecutive_wins=consecutive_wins,
                risk_reward_ratio=PerformanceMetric(value=round(risk_reward, 2), unit=""),
                downside_deviation=PerformanceMetric(value=round(downside_deviation, 2), unit="$"),
                ulcer_index=PerformanceMetric(value=round(ulcer_index, 2), unit=""),
                calmar_ratio=PerformanceMetric(value=round(calmar_ratio, 2), unit="")
            )
            
            # Cache the result
            if use_cache:
                self._cache[cache_key] = response
                self._cache_timestamps[cache_key] = datetime.now()
            
            return response
            
        except Exception as e:
            logger.error(f"Error calculating risk metrics: {str(e)}", exc_info=True)
            raise 