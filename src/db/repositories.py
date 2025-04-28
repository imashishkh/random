"""
Entity-specific repositories that inherit from BaseRepository.
Each repository specializes in CRUD operations for a specific entity type.
"""
from typing import List, Optional, Dict, Any, Union, TypeVar, Type, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from .repository import BaseRepository, UnitOfWork
from .models import (
    Symbol, Trade, TradeMetric, TradingSession, TradeTag, 
    PriceData, TradingStrategy
)

logger = logging.getLogger(__name__)

T = TypeVar('T')

class SymbolRepository(BaseRepository[Symbol]):
    """Repository for Symbol entities."""
    
    def __init__(self):
        super().__init__('symbols', Symbol)
        
    def get_by_name(self, name: str) -> Optional[Symbol]:
        """Get a symbol by its name."""
        return self.get_by_column('name', name)
        
    def get_active_symbols(self) -> List[Symbol]:
        """Get all active symbols."""
        return self.get_by_filter({'active': True})
        
    def get_symbols_by_type(self, symbol_type: str) -> List[Symbol]:
        """Get all symbols of a specific type."""
        return self.get_by_filter({'type': symbol_type})


class TradeRepository(BaseRepository[Trade]):
    """Repository for Trade entities."""
    
    def __init__(self):
        super().__init__('trades', Trade)
        
    def get_open_trades(self) -> List[Trade]:
        """Get all currently open trades."""
        return self.get_by_filter({'status': 'open'})
        
    def get_trades_by_symbol(self, symbol_id: int) -> List[Trade]:
        """Get all trades for a specific symbol."""
        return self.get_by_column('symbol_id', symbol_id)
        
    def get_trades_by_date_range(self, start_date: datetime, end_date: datetime) -> List[Trade]:
        """Get all trades within a specific date range."""
        query = """
            SELECT * FROM trades
            WHERE open_time >= %s AND open_time <= %s
            ORDER BY open_time DESC
        """
        params = (start_date, end_date)
        
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [self._from_db_dict(row) for row in rows]
                
    def get_trades_with_tag(self, tag: str) -> List[Trade]:
        """Get all trades with a specific tag."""
        query = """
            SELECT * FROM trades
            WHERE tags @> %s::text[]
            ORDER BY open_time DESC
        """
        params = ([tag],)
        
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [self._from_db_dict(row) for row in rows]
                
    def get_profitable_trades(self) -> List[Trade]:
        """Get all profitable trades."""
        return self.get_by_filter({'status': 'closed', 'pnl > 0': None})
        
    def get_losing_trades(self) -> List[Trade]:
        """Get all losing trades."""
        return self.get_by_filter({'status': 'closed', 'pnl < 0': None})
        
    def close_trade(self, trade_id: int, close_price: Decimal, close_time: datetime = None) -> Optional[Trade]:
        """Close an open trade with the specified closing price and time."""
        trade = self.get_by_id(trade_id)
        if not trade or trade.status != 'open':
            return None
            
        if close_time is None:
            close_time = datetime.now()
            
        trade.close_time = close_time
        trade.close_price = close_price
        trade.status = 'closed'
        
        # Calculate PnL and pips
        trade.pnl = trade.calculate_pnl()
        trade.pips = trade.calculate_pips()
        
        # Update the trade
        return self.update(trade)


class TradeMetricRepository(BaseRepository[TradeMetric]):
    """Repository for TradeMetric entities."""
    
    def __init__(self):
        super().__init__('trade_metrics', TradeMetric)
        
    def get_metrics_by_type(self, metric_type: str) -> List[TradeMetric]:
        """Get metrics by their type (daily, weekly, monthly, etc.)."""
        return self.get_by_column('metric_type', metric_type)
        
    def get_metrics_by_date_range(self, start_date: datetime, end_date: datetime) -> List[TradeMetric]:
        """Get metrics within a date range."""
        query = """
            SELECT * FROM trade_metrics
            WHERE date >= %s AND date <= %s
            ORDER BY date ASC
        """
        params = (start_date, end_date)
        
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [self._from_db_dict(row) for row in rows]
                
    def get_latest_metric(self, metric_type: str, symbol_id: Optional[int] = None) -> Optional[TradeMetric]:
        """Get the most recent metric of a specific type."""
        filter_dict = {'metric_type': metric_type}
        if symbol_id is not None:
            filter_dict['symbol_id'] = symbol_id
            
        query = """
            SELECT * FROM trade_metrics
            WHERE metric_type = %s
        """
        params = [metric_type]
        
        if symbol_id is not None:
            query += " AND symbol_id = %s"
            params.append(symbol_id)
            
        query += " ORDER BY date DESC LIMIT 1"
        
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                return self._from_db_dict(row) if row else None


class TradingSessionRepository(BaseRepository[TradingSession]):
    """Repository for TradingSession entities."""
    
    def __init__(self):
        super().__init__('trading_sessions', TradingSession)
        
    def get_active_sessions(self) -> List[TradingSession]:
        """Get all active trading sessions."""
        return self.get_by_column('status', 'active')
        
    def get_completed_sessions(self) -> List[TradingSession]:
        """Get all completed trading sessions."""
        return self.get_by_column('status', 'completed')
        
    def get_sessions_by_date_range(self, start_date: datetime, end_date: datetime) -> List[TradingSession]:
        """Get trading sessions within a date range."""
        query = """
            SELECT * FROM trading_sessions
            WHERE start_time >= %s AND start_time <= %s
            ORDER BY start_time DESC
        """
        params = (start_date, end_date)
        
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [self._from_db_dict(row) for row in rows]


class TradeTagRepository(BaseRepository[TradeTag]):
    """Repository for TradeTag entities."""
    
    def __init__(self):
        super().__init__('trade_tags', TradeTag)
        
    def get_by_name(self, name: str) -> Optional[TradeTag]:
        """Get a tag by its name."""
        return self.get_by_column('name', name)
        
    def get_system_tags(self) -> List[TradeTag]:
        """Get all system-defined tags."""
        return self.get_by_column('is_system', True)


class PriceDataRepository(BaseRepository[PriceData]):
    """Repository for PriceData entities."""
    
    def __init__(self):
        super().__init__('price_data', PriceData)
        
    def get_by_symbol_and_timeframe(self, symbol_id: int, timeframe: str, 
                                    start_time: datetime, end_time: datetime) -> List[PriceData]:
        """Get price data for a specific symbol and timeframe within a date range."""
        query = """
            SELECT * FROM price_data
            WHERE symbol_id = %s 
            AND timeframe = %s
            AND timestamp >= %s 
            AND timestamp <= %s
            ORDER BY timestamp ASC
        """
        params = (symbol_id, timeframe, start_time, end_time)
        
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [self._from_db_dict(row) for row in rows]
                
    def get_latest_price(self, symbol_id: int, timeframe: str) -> Optional[PriceData]:
        """Get the most recent price data for a specific symbol and timeframe."""
        query = """
            SELECT * FROM price_data
            WHERE symbol_id = %s 
            AND timeframe = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """
        params = (symbol_id, timeframe)
        
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                return self._from_db_dict(row) if row else None
                
    def get_ohlc_data(self, symbol_id: int, timeframe: str, limit: int = 100) -> List[PriceData]:
        """Get OHLC data for a specific symbol and timeframe, limited to a number of records."""
        query = """
            SELECT * FROM price_data
            WHERE symbol_id = %s 
            AND timeframe = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """
        params = (symbol_id, timeframe, limit)
        
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                # Return in ascending order for charting
                return [self._from_db_dict(row) for row in reversed(rows)]
                
    def bulk_insert_price_data(self, price_data_list: List[PriceData]) -> None:
        """Insert multiple price data points efficiently."""
        if not price_data_list:
            return
            
        # Use bulk_create method from BaseRepository
        self.bulk_create(price_data_list)


class TradingStrategyRepository(BaseRepository[TradingStrategy]):
    """Repository for TradingStrategy entities."""
    
    def __init__(self):
        super().__init__('trading_strategies', TradingStrategy)
        
    def get_active_strategies(self) -> List[TradingStrategy]:
        """Get all active trading strategies."""
        return self.get_by_column('is_active', True)
        
    def get_by_name(self, name: str) -> Optional[TradingStrategy]:
        """Get a strategy by its name."""
        return self.get_by_column('name', name)
        
    def get_profitable_strategies(self) -> List[TradingStrategy]:
        """Get all strategies with positive PnL."""
        return self.get_by_filter({'net_pnl > 0': None})
        
    def get_high_win_rate_strategies(self, min_win_rate: float = 0.6, min_trades: int = 10) -> List[TradingStrategy]:
        """Get strategies with high win rates and a minimum number of trades."""
        query = """
            SELECT * FROM trading_strategies
            WHERE win_rate >= %s AND total_trades >= %s
            ORDER BY win_rate DESC
        """
        params = (min_win_rate, min_trades)
        
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [self._from_db_dict(row) for row in rows] 