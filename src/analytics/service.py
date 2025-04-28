"""
Analytics service for retrieving and processing trade data.

This module provides the AnalyticsService class that serves as the central
component for retrieving and processing analytics data from the database.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Union
from fastapi import Depends
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc, asc
import json
import asyncio
import aioredis

from ..database import get_db
from ..models.trade import Trade
from ..models.agent import Agent
from ..models.user import User
from .metrics import (
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_max_drawdown,
    calculate_win_loss_ratio,
    calculate_profit_factor,
    calculate_average_trade,
    calculate_trade_expectancy,
    calculate_daily_returns,
    detect_anomalies,
    calculate_volatility,
    calculate_var,
    calculate_beta,
    calculate_calmar_ratio
)
from ..config import settings

logger = logging.getLogger(__name__)

class AnalyticsService:
    """Service for retrieving and analyzing trade data."""
    
    def __init__(self, db: Session = None, redis_url: str = None):
        """
        Initialize the AnalyticsService.
        
        Args:
            db: Database session
            redis_url: Redis URL for caching
        """
        self.db = db
        self.redis_url = redis_url or settings.REDIS_URL
        self.cache_ttl = settings.ANALYTICS_CACHE_TTL
        self._redis = None
    
    async def get_redis(self):
        """Get Redis connection."""
        if self._redis is None:
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return self._redis
    
    async def _get_cache(self, key: str) -> Optional[Dict]:
        """
        Get data from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached data or None
        """
        try:
            redis = await self.get_redis()
            data = await redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Error getting cache: {e}")
        
        return None
    
    async def _set_cache(self, key: str, data: Dict, ttl: int = None) -> bool:
        """
        Set data in cache.
        
        Args:
            key: Cache key
            data: Data to cache
            ttl: Time to live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            redis = await self.get_redis()
            await redis.set(
                key,
                json.dumps(data),
                ex=ttl or self.cache_ttl
            )
            return True
        except Exception as e:
            logger.warning(f"Error setting cache: {e}")
            return False
    
    async def get_performance_metrics(
        self,
        agent_id: Optional[int] = None,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get performance metrics for a specific agent, symbol, and time period.
        
        Args:
            agent_id: Agent ID to filter by
            symbol: Symbol to filter by
            start_date: Start date for filtering
            end_date: End date for filtering
            use_cache: Whether to use cache
            
        Returns:
            Dictionary containing performance metrics
        """
        # Generate cache key
        cache_key = f"perf_metrics:{agent_id or 'all'}:{symbol or 'all'}:{start_date.strftime('%Y%m%d') if start_date else 'all'}:{end_date.strftime('%Y%m%d') if end_date else 'all'}"
        
        # Check cache
        if use_cache:
            cached_data = await self._get_cache(cache_key)
            if cached_data:
                return cached_data
        
        # Get trade data
        trades_df = await self.get_trades_dataframe(
            agent_id=agent_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if trades_df.empty:
            return {
                "total_trades": 0,
                "profitable_trades": 0,
                "losing_trades": 0,
                "win_rate": None,
                "profit_factor": None,
                "sharpe_ratio": None,
                "sortino_ratio": None,
                "max_drawdown": None,
                "total_pnl": 0,
                "avg_trade": None,
                "avg_win": None,
                "avg_loss": None,
                "expectancy": None,
                "volatility": None,
                "value_at_risk": None,
                "calmar_ratio": None
            }
        
        # Calculate daily returns
        daily_returns = calculate_daily_returns(trades_df)
        
        # Calculate performance metrics
        total_trades = len(trades_df)
        profitable_trades = len(trades_df[trades_df['pnl'] > 0])
        losing_trades = len(trades_df[trades_df['pnl'] < 0])
        win_rate = profitable_trades / total_trades if total_trades > 0 else 0
        
        metrics = {
            "total_trades": total_trades,
            "profitable_trades": profitable_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 4),
            "profit_factor": calculate_profit_factor(trades_df),
            "sharpe_ratio": calculate_sharpe_ratio(daily_returns) if not daily_returns.empty else None,
            "sortino_ratio": calculate_sortino_ratio(daily_returns) if not daily_returns.empty else None,
            "max_drawdown": calculate_max_drawdown(daily_returns) if not daily_returns.empty else None,
            "total_pnl": float(trades_df['pnl'].sum()),
            "avg_trade": None,
            "avg_win": None,
            "avg_loss": None,
            "expectancy": calculate_trade_expectancy(trades_df),
            "volatility": calculate_volatility(daily_returns) if not daily_returns.empty else None,
            "value_at_risk": calculate_var(daily_returns) if not daily_returns.empty else None,
            "calmar_ratio": calculate_calmar_ratio(daily_returns) if not daily_returns.empty and len(daily_returns) >= 252 else None
        }
        
        # Get average trade metrics
        avg_trade, avg_win, avg_loss = calculate_average_trade(trades_df)
        metrics["avg_trade"] = avg_trade
        metrics["avg_win"] = avg_win
        metrics["avg_loss"] = avg_loss
        
        # Cache the results
        if use_cache:
            await self._set_cache(cache_key, metrics)
        
        return metrics
    
    async def get_trades_dataframe(
        self,
        agent_id: Optional[int] = None,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = None,
        offset: int = None,
        include_pending: bool = False,
        sort_by: str = "close_time",
        sort_direction: str = "desc"
    ) -> pd.DataFrame:
        """
        Get trades as a pandas DataFrame.
        
        Args:
            agent_id: Agent ID to filter by
            symbol: Symbol to filter by
            start_date: Start date for filtering
            end_date: End date for filtering
            limit: Maximum number of trades to return
            offset: Offset for pagination
            include_pending: Whether to include pending trades
            sort_by: Column to sort by
            sort_direction: Sort direction ('asc' or 'desc')
            
        Returns:
            DataFrame containing trades
        """
        # Build query filter
        filters = []
        
        if not include_pending:
            filters.append(Trade.status == 'closed')
        
        if agent_id:
            filters.append(Trade.agent_id == agent_id)
        
        if symbol:
            filters.append(Trade.symbol == symbol)
        
        if start_date:
            filters.append(Trade.close_time >= start_date)
        
        if end_date:
            filters.append(Trade.close_time <= end_date)
        
        # Build query
        query = self.db.query(Trade)
        
        if filters:
            query = query.filter(and_(*filters))
        
        # Sort
        if sort_direction.lower() == 'asc':
            query = query.order_by(asc(getattr(Trade, sort_by)))
        else:
            query = query.order_by(desc(getattr(Trade, sort_by)))
        
        # Paginate
        if limit:
            query = query.limit(limit)
        
        if offset:
            query = query.offset(offset)
        
        # Execute query and convert to DataFrame
        trades = query.all()
        
        if not trades:
            return pd.DataFrame()
        
        # Convert to dictionary records
        records = [trade.__dict__ for trade in trades]
        
        # Remove SQLAlchemy instance state
        for record in records:
            record.pop('_sa_instance_state', None)
        
        # Convert to DataFrame
        df = pd.DataFrame.from_records(records)
        
        return df
    
    async def get_pnl_over_time(
        self,
        agent_id: Optional[int] = None,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = 'day',
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get P&L over time for a specific agent, symbol, and time period.
        
        Args:
            agent_id: Agent ID to filter by
            symbol: Symbol to filter by
            start_date: Start date for filtering
            end_date: End date for filtering
            interval: Time interval for aggregation ('day', 'week', 'month')
            use_cache: Whether to use cache
            
        Returns:
            List of dictionaries containing date and P&L
        """
        # Generate cache key
        cache_key = f"pnl_time:{agent_id or 'all'}:{symbol or 'all'}:{start_date.strftime('%Y%m%d') if start_date else 'all'}:{end_date.strftime('%Y%m%d') if end_date else 'all'}:{interval}"
        
        # Check cache
        if use_cache:
            cached_data = await self._get_cache(cache_key)
            if cached_data:
                return cached_data
        
        # Get trade data
        trades_df = await self.get_trades_dataframe(
            agent_id=agent_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if trades_df.empty:
            return []
        
        # Ensure timestamp column is datetime
        if not pd.api.types.is_datetime64_dtype(trades_df['close_time']):
            trades_df['close_time'] = pd.to_datetime(trades_df['close_time'])
        
        # Group by interval
        if interval == 'day':
            grouped = trades_df.groupby(trades_df['close_time'].dt.date)['pnl'].sum()
        elif interval == 'week':
            trades_df['week'] = trades_df['close_time'].dt.to_period('W').dt.start_time
            grouped = trades_df.groupby(trades_df['week'])['pnl'].sum()
        elif interval == 'month':
            trades_df['month'] = trades_df['close_time'].dt.to_period('M').dt.start_time
            grouped = trades_df.groupby(trades_df['month'])['pnl'].sum()
        else:
            # Default to day
            grouped = trades_df.groupby(trades_df['close_time'].dt.date)['pnl'].sum()
        
        # Convert to list of dictionaries
        result = [{"date": str(date), "pnl": float(pnl)} for date, pnl in grouped.items()]
        
        # Add cumulative P&L
        cumulative_pnl = 0
        for entry in result:
            cumulative_pnl += entry['pnl']
            entry['cumulative_pnl'] = cumulative_pnl
        
        # Cache the results
        if use_cache:
            await self._set_cache(cache_key, result)
        
        return result
    
    async def get_trade_distribution(
        self,
        agent_id: Optional[int] = None,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get trade distribution metrics.
        
        Args:
            agent_id: Agent ID to filter by
            symbol: Symbol to filter by
            start_date: Start date for filtering
            end_date: End date for filtering
            use_cache: Whether to use cache
            
        Returns:
            Dictionary containing trade distribution metrics
        """
        # Generate cache key
        cache_key = f"trade_dist:{agent_id or 'all'}:{symbol or 'all'}:{start_date.strftime('%Y%m%d') if start_date else 'all'}:{end_date.strftime('%Y%m%d') if end_date else 'all'}"
        
        # Check cache
        if use_cache:
            cached_data = await self._get_cache(cache_key)
            if cached_data:
                return cached_data
        
        # Get trade data
        trades_df = await self.get_trades_dataframe(
            agent_id=agent_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if trades_df.empty:
            return {
                "by_symbol": [],
                "by_direction": [],
                "by_day_of_week": [],
                "by_hour_of_day": [],
                "pnl_distribution": {}
            }
        
        # Distribution by symbol
        symbol_dist = trades_df.groupby('symbol').agg({
            'id': 'count',
            'pnl': 'sum'
        }).reset_index()
        
        symbol_dist = symbol_dist.rename(columns={'id': 'count'})
        
        # Distribution by direction
        direction_dist = trades_df.groupby('direction').agg({
            'id': 'count',
            'pnl': 'sum'
        }).reset_index()
        
        direction_dist = direction_dist.rename(columns={'id': 'count'})
        
        # Ensure timestamp column is datetime
        if not pd.api.types.is_datetime64_dtype(trades_df['close_time']):
            trades_df['close_time'] = pd.to_datetime(trades_df['close_time'])
        
        # Distribution by day of week
        trades_df['day_of_week'] = trades_df['close_time'].dt.day_name()
        day_of_week_dist = trades_df.groupby('day_of_week').agg({
            'id': 'count',
            'pnl': 'sum'
        }).reset_index()
        
        day_of_week_dist = day_of_week_dist.rename(columns={'id': 'count'})
        
        # Distribution by hour of day
        trades_df['hour_of_day'] = trades_df['close_time'].dt.hour
        hour_of_day_dist = trades_df.groupby('hour_of_day').agg({
            'id': 'count',
            'pnl': 'sum'
        }).reset_index()
        
        hour_of_day_dist = hour_of_day_dist.rename(columns={'id': 'count'})
        
        # P&L distribution
        pnl_values = trades_df['pnl'].values
        pnl_distribution = {
            'min': float(np.min(pnl_values)),
            'max': float(np.max(pnl_values)),
            'mean': float(np.mean(pnl_values)),
            'median': float(np.median(pnl_values)),
            'std': float(np.std(pnl_values)),
            'percentiles': {
                '10': float(np.percentile(pnl_values, 10)),
                '25': float(np.percentile(pnl_values, 25)),
                '50': float(np.percentile(pnl_values, 50)),
                '75': float(np.percentile(pnl_values, 75)),
                '90': float(np.percentile(pnl_values, 90))
            }
        }
        
        # Convert DataFrames to lists of dictionaries
        result = {
            "by_symbol": symbol_dist.to_dict(orient='records'),
            "by_direction": direction_dist.to_dict(orient='records'),
            "by_day_of_week": day_of_week_dist.to_dict(orient='records'),
            "by_hour_of_day": hour_of_day_dist.to_dict(orient='records'),
            "pnl_distribution": pnl_distribution
        }
        
        # Cache the results
        if use_cache:
            await self._set_cache(cache_key, result)
        
        return result
    
    async def get_risk_analysis(
        self,
        agent_id: Optional[int] = None,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get risk analysis metrics.
        
        Args:
            agent_id: Agent ID to filter by
            symbol: Symbol to filter by
            start_date: Start date for filtering
            end_date: End date for filtering
            use_cache: Whether to use cache
            
        Returns:
            Dictionary containing risk analysis metrics
        """
        # Generate cache key
        cache_key = f"risk_analysis:{agent_id or 'all'}:{symbol or 'all'}:{start_date.strftime('%Y%m%d') if start_date else 'all'}:{end_date.strftime('%Y%m%d') if end_date else 'all'}"
        
        # Check cache
        if use_cache:
            cached_data = await self._get_cache(cache_key)
            if cached_data:
                return cached_data
        
        # Get trade data
        trades_df = await self.get_trades_dataframe(
            agent_id=agent_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if trades_df.empty:
            return {
                "max_drawdown": None,
                "value_at_risk": None,
                "consecutive_losses": {
                    "max": 0,
                    "current": 0
                },
                "risk_reward_ratio": None,
                "risk_per_trade": None,
                "daily_volatility": None,
                "anomalies": []
            }
        
        # Calculate daily returns
        daily_returns = calculate_daily_returns(trades_df)
        
        # Consecutive losses
        if not trades_df.empty:
            trades_df = trades_df.sort_values('close_time')
            trades_df['is_loss'] = trades_df['pnl'] < 0
            
            # Calculate streak of consecutive losses
            trades_df['streak'] = (trades_df['is_loss'] != trades_df['is_loss'].shift()).cumsum()
            
            # Calculate streak lengths for losses
            loss_streaks = trades_df[trades_df['is_loss']].groupby('streak').size()
            
            max_consecutive_losses = int(loss_streaks.max()) if not loss_streaks.empty else 0
            
            # Calculate current streak
            current_streak = 0
            for is_loss in trades_df['is_loss'].iloc[::-1]:
                if is_loss:
                    current_streak += 1
                else:
                    break
        else:
            max_consecutive_losses = 0
            current_streak = 0
        
        # Risk reward ratio
        if not trades_df.empty:
            avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean()
            avg_loss = abs(trades_df[trades_df['pnl'] < 0]['pnl'].mean())
            
            risk_reward_ratio = float(avg_win / avg_loss) if avg_loss > 0 else float('inf')
        else:
            risk_reward_ratio = None
        
        # Risk per trade
        if not trades_df.empty:
            avg_risk = trades_df['risk_amount'].mean() if 'risk_amount' in trades_df.columns else None
        else:
            avg_risk = None
        
        # Detect anomalies
        anomalies = None
        if not trades_df.empty:
            anomaly_mask = detect_anomalies(trades_df)
            anomaly_trades = trades_df[anomaly_mask]
            
            anomalies = []
            for _, trade in anomaly_trades.iterrows():
                anomalies.append({
                    "trade_id": int(trade['id']),
                    "symbol": trade['symbol'],
                    "pnl": float(trade['pnl']),
                    "date": str(trade['close_time']),
                    "z_score": float((trade['pnl'] - trades_df['pnl'].mean()) / trades_df['pnl'].std())
                })
        
        # Compile results
        result = {
            "max_drawdown": calculate_max_drawdown(daily_returns) if not daily_returns.empty else None,
            "value_at_risk": calculate_var(daily_returns) if not daily_returns.empty else None,
            "consecutive_losses": {
                "max": max_consecutive_losses,
                "current": current_streak
            },
            "risk_reward_ratio": risk_reward_ratio,
            "risk_per_trade": avg_risk,
            "daily_volatility": calculate_volatility(daily_returns, 1) if not daily_returns.empty else None,
            "anomalies": anomalies or []
        }
        
        # Cache the results
        if use_cache:
            await self._set_cache(cache_key, result)
        
        return result
    
    async def invalidate_cache(self, agent_id: Optional[int] = None, symbol: Optional[str] = None):
        """
        Invalidate cache for a specific agent and/or symbol.
        
        Args:
            agent_id: Agent ID to invalidate cache for
            symbol: Symbol to invalidate cache for
        """
        try:
            redis = await self.get_redis()
            
            # Generate pattern
            pattern = f"*:{agent_id or '*'}:{symbol or '*'}:*"
            
            # Get matching keys
            keys = await redis.keys(pattern)
            
            # Delete keys
            if keys:
                await redis.delete(*keys)
            
            logger.info(f"Invalidated {len(keys)} cache keys for agent_id={agent_id}, symbol={symbol}")
            
            return True
        except Exception as e:
            logger.warning(f"Error invalidating cache: {e}")
            return False 