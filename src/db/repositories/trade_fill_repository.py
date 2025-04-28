"""
Repository implementation for TradeFill entities.

This module provides repository operations for TradeFill entities, including CRUD operations
and specialized queries.
"""

import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from decimal import Decimal
import psycopg2
from psycopg2 import sql

from .base_repository import BaseRepository
from .exceptions import EntityNotFoundError, QueryError, RepositoryError
from .models.trade_fill import TradeFill  # Import the model (to be created)

logger = logging.getLogger(__name__)


class TradeFillRepository(BaseRepository[TradeFill]):
    """
    Repository for TradeFill entities.
    
    This extends the BaseRepository class to provide specific functionality
    for TradeFill entities.
    """
    
    def __init__(self):
        """Initialize the repository."""
        super().__init__('trade_fills', TradeFill)
    
    def map_to_entity(self, row: Dict[str, Any]) -> TradeFill:
        """
        Map a database row to a TradeFill entity.
        
        Args:
            row: Database row as a dictionary
            
        Returns:
            TradeFill entity
        """
        return TradeFill(
            id=row.get('id'),
            trade_id=row.get('trade_id'),
            symbol=row.get('symbol'),
            price=row.get('price'),
            quantity=row.get('quantity'),
            side=row.get('side'),
            executed_at=row.get('executed_at'),
            fee=row.get('fee'),
            fee_asset=row.get('fee_asset'),
            order_id=row.get('order_id'),
            agent_id=row.get('agent_id'),
            position_id=row.get('position_id'),
            created_at=row.get('created_at')
        )
    
    def map_to_db_dict(self, entity: TradeFill) -> Dict[str, Any]:
        """
        Map a TradeFill entity to a dictionary for database operations.
        
        Args:
            entity: TradeFill entity
            
        Returns:
            Dictionary for database operations
        """
        return {
            'id': entity.id,
            'trade_id': entity.trade_id,
            'symbol': entity.symbol,
            'price': entity.price,
            'quantity': entity.quantity,
            'side': entity.side,
            'executed_at': entity.executed_at,
            'fee': entity.fee,
            'fee_asset': entity.fee_asset,
            'order_id': entity.order_id,
            'agent_id': entity.agent_id,
            'position_id': entity.position_id,
            'created_at': entity.created_at
        }
    
    def get_by_trade_id(self, trade_id: str) -> Optional[TradeFill]:
        """
        Get a trade fill by its trade_id.
        
        Args:
            trade_id: The exchange-provided trade ID
            
        Returns:
            TradeFill entity if found, None otherwise
        """
        try:
            query = sql.SQL("SELECT * FROM {} WHERE trade_id = %s").format(
                sql.Identifier(self.table_name)
            )
            results = self.execute_query(query, [trade_id])
            if not results:
                return None
            return self.map_to_entity(results[0])
        except Exception as e:
            logger.error(f"Error fetching trade fill by trade_id {trade_id}: {e}")
            raise QueryError(f"Error fetching trade fill by trade_id: {e}")
    
    def get_by_position_id(self, position_id: int) -> List[TradeFill]:
        """
        Get all trade fills for a specific position.
        
        Args:
            position_id: Position ID
            
        Returns:
            List of TradeFill entities
        """
        try:
            query = sql.SQL("SELECT * FROM {} WHERE position_id = %s ORDER BY executed_at").format(
                sql.Identifier(self.table_name)
            )
            results = self.execute_query(query, [position_id])
            return [self.map_to_entity(row) for row in results]
        except Exception as e:
            logger.error(f"Error fetching trade fills for position {position_id}: {e}")
            raise QueryError(f"Error fetching trade fills for position: {e}")
    
    def get_by_agent_id(self, agent_id: str, 
                        from_date: Optional[datetime] = None,
                        to_date: Optional[datetime] = None,
                        limit: int = 100) -> List[TradeFill]:
        """
        Get trade fills for a specific agent, optionally filtered by date range.
        
        Args:
            agent_id: Agent ID
            from_date: Optional start date for filtering
            to_date: Optional end date for filtering
            limit: Maximum number of records to return
            
        Returns:
            List of TradeFill entities
        """
        try:
            query_parts = [sql.SQL("SELECT * FROM {} WHERE agent_id = %s").format(
                sql.Identifier(self.table_name)
            )]
            params = [agent_id]
            
            if from_date:
                query_parts.append(sql.SQL("AND executed_at >= %s"))
                params.append(from_date)
                
            if to_date:
                query_parts.append(sql.SQL("AND executed_at <= %s"))
                params.append(to_date)
                
            query_parts.append(sql.SQL("ORDER BY executed_at DESC LIMIT %s"))
            params.append(limit)
            
            query = sql.SQL(" ").join(query_parts)
            results = self.execute_query(query, params)
            return [self.map_to_entity(row) for row in results]
        except Exception as e:
            logger.error(f"Error fetching trade fills for agent {agent_id}: {e}")
            raise QueryError(f"Error fetching trade fills for agent: {e}")
    
    def get_by_symbol(self, symbol: str, 
                      from_date: Optional[datetime] = None,
                      to_date: Optional[datetime] = None,
                      limit: int = 100) -> List[TradeFill]:
        """
        Get trade fills for a specific symbol, optionally filtered by date range.
        
        Args:
            symbol: Trading symbol
            from_date: Optional start date for filtering
            to_date: Optional end date for filtering
            limit: Maximum number of records to return
            
        Returns:
            List of TradeFill entities
        """
        try:
            query_parts = [sql.SQL("SELECT * FROM {} WHERE symbol = %s").format(
                sql.Identifier(self.table_name)
            )]
            params = [symbol]
            
            if from_date:
                query_parts.append(sql.SQL("AND executed_at >= %s"))
                params.append(from_date)
                
            if to_date:
                query_parts.append(sql.SQL("AND executed_at <= %s"))
                params.append(to_date)
                
            query_parts.append(sql.SQL("ORDER BY executed_at DESC LIMIT %s"))
            params.append(limit)
            
            query = sql.SQL(" ").join(query_parts)
            results = self.execute_query(query, params)
            return [self.map_to_entity(row) for row in results]
        except Exception as e:
            logger.error(f"Error fetching trade fills for symbol {symbol}: {e}")
            raise QueryError(f"Error fetching trade fills for symbol: {e}")
    
    def assign_to_position(self, trade_fill_id: int, position_id: int) -> bool:
        """
        Assign a trade fill to a position.
        
        Args:
            trade_fill_id: Trade fill ID
            position_id: Position ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            query = sql.SQL("UPDATE {} SET position_id = %s WHERE id = %s").format(
                sql.Identifier(self.table_name)
            )
            results = self.execute_query(query, [position_id, trade_fill_id])
            return True
        except Exception as e:
            logger.error(f"Error assigning trade fill {trade_fill_id} to position {position_id}: {e}")
            raise QueryError(f"Error assigning trade fill to position: {e}")
    
    def get_statistics_by_agent(self, agent_id: str, 
                               from_date: Optional[datetime] = None,
                               to_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Get trade statistics for a specific agent, optionally filtered by date range.
        
        Args:
            agent_id: Agent ID
            from_date: Optional start date for filtering
            to_date: Optional end date for filtering
            
        Returns:
            Dictionary containing trade statistics
        """
        try:
            query_parts = [sql.SQL("""
                SELECT 
                    COUNT(*) as total_fills,
                    SUM(CASE WHEN side = 'BUY' THEN 1 ELSE 0 END) as buy_count,
                    SUM(CASE WHEN side = 'SELL' THEN 1 ELSE 0 END) as sell_count,
                    SUM(quantity) as total_quantity,
                    SUM(price * quantity) as total_value,
                    SUM(fee) as total_fees,
                    COUNT(DISTINCT symbol) as symbol_count,
                    COUNT(DISTINCT position_id) as position_count
                FROM {}
                WHERE agent_id = %s
            """).format(sql.Identifier(self.table_name))]
            
            params = [agent_id]
            
            if from_date:
                query_parts.append(sql.SQL("AND executed_at >= %s"))
                params.append(from_date)
                
            if to_date:
                query_parts.append(sql.SQL("AND executed_at <= %s"))
                params.append(to_date)
            
            query = sql.SQL(" ").join(query_parts)
            results = self.execute_query(query, params)
            return results[0] if results else {}
        except Exception as e:
            logger.error(f"Error fetching trade statistics for agent {agent_id}: {e}")
            raise QueryError(f"Error fetching trade statistics for agent: {e}") 