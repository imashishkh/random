"""
Repository implementation for Position entities.

This module provides repository operations for Position entities, including CRUD operations
and specialized queries for position management.
"""

import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from decimal import Decimal
import psycopg2
from psycopg2 import sql

from .base_repository import BaseRepository
from .exceptions import EntityNotFoundError, QueryError, RepositoryError
from .models.position import Position  # Import the model (to be created)

logger = logging.getLogger(__name__)


class PositionRepository(BaseRepository[Position]):
    """
    Repository for Position entities.
    
    This extends the BaseRepository class to provide specific functionality
    for Position entities.
    """
    
    def __init__(self):
        """Initialize the repository."""
        super().__init__('positions', Position)
    
    def map_to_entity(self, row: Dict[str, Any]) -> Position:
        """
        Map a database row to a Position entity.
        
        Args:
            row: Database row as a dictionary
            
        Returns:
            Position entity
        """
        return Position(
            id=row.get('id'),
            symbol=row.get('symbol'),
            quantity=row.get('quantity'),
            entry_price=row.get('entry_price'),
            current_price=row.get('current_price'),
            unrealized_pnl=row.get('unrealized_pnl'),
            realized_pnl=row.get('realized_pnl'),
            agent_id=row.get('agent_id'),
            status=row.get('status'),
            opened_at=row.get('opened_at'),
            closed_at=row.get('closed_at'),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )
    
    def map_to_db_dict(self, entity: Position) -> Dict[str, Any]:
        """
        Map a Position entity to a dictionary for database operations.
        
        Args:
            entity: Position entity
            
        Returns:
            Dictionary for database operations
        """
        return {
            'id': entity.id,
            'symbol': entity.symbol,
            'quantity': entity.quantity,
            'entry_price': entity.entry_price,
            'current_price': entity.current_price,
            'unrealized_pnl': entity.unrealized_pnl,
            'realized_pnl': entity.realized_pnl,
            'agent_id': entity.agent_id,
            'status': entity.status,
            'opened_at': entity.opened_at,
            'closed_at': entity.closed_at,
            'created_at': entity.created_at,
            'updated_at': entity.updated_at
        }
    
    def get_open_positions(self, agent_id: Optional[str] = None) -> List[Position]:
        """
        Get all open positions, optionally filtered by agent ID.
        
        Args:
            agent_id: Optional agent ID filter
            
        Returns:
            List of open Position entities
        """
        try:
            if agent_id:
                query = sql.SQL("SELECT * FROM {} WHERE status = 'OPEN' AND agent_id = %s").format(
                    sql.Identifier(self.table_name)
                )
                results = self.execute_query(query, [agent_id])
            else:
                query = sql.SQL("SELECT * FROM {} WHERE status = 'OPEN'").format(
                    sql.Identifier(self.table_name)
                )
                results = self.execute_query(query, [])
            
            return [self.map_to_entity(row) for row in results]
        except Exception as e:
            logger.error(f"Error fetching open positions: {e}")
            raise QueryError(f"Error fetching open positions: {e}")
    
    def get_closed_positions(self, agent_id: Optional[str] = None,
                           from_date: Optional[datetime] = None,
                           to_date: Optional[datetime] = None,
                           limit: int = 100) -> List[Position]:
        """
        Get closed positions, optionally filtered by agent ID and date range.
        
        Args:
            agent_id: Optional agent ID filter
            from_date: Optional start date for filtering
            to_date: Optional end date for filtering
            limit: Maximum number of records to return
            
        Returns:
            List of closed Position entities
        """
        try:
            query_parts = [sql.SQL("SELECT * FROM {} WHERE status = 'CLOSED'").format(
                sql.Identifier(self.table_name)
            )]
            params = []
            
            if agent_id:
                query_parts.append(sql.SQL("AND agent_id = %s"))
                params.append(agent_id)
            
            if from_date:
                query_parts.append(sql.SQL("AND closed_at >= %s"))
                params.append(from_date)
                
            if to_date:
                query_parts.append(sql.SQL("AND closed_at <= %s"))
                params.append(to_date)
                
            query_parts.append(sql.SQL("ORDER BY closed_at DESC LIMIT %s"))
            params.append(limit)
            
            query = sql.SQL(" ").join(query_parts)
            results = self.execute_query(query, params)
            return [self.map_to_entity(row) for row in results]
        except Exception as e:
            logger.error(f"Error fetching closed positions: {e}")
            raise QueryError(f"Error fetching closed positions: {e}")
    
    def get_by_symbol(self, symbol: str, status: Optional[str] = None) -> List[Position]:
        """
        Get positions for a specific symbol, optionally filtered by status.
        
        Args:
            symbol: Trading symbol
            status: Optional position status filter ('OPEN', 'CLOSED')
            
        Returns:
            List of Position entities
        """
        try:
            if status:
                query = sql.SQL("SELECT * FROM {} WHERE symbol = %s AND status = %s").format(
                    sql.Identifier(self.table_name)
                )
                results = self.execute_query(query, [symbol, status])
            else:
                query = sql.SQL("SELECT * FROM {} WHERE symbol = %s").format(
                    sql.Identifier(self.table_name)
                )
                results = self.execute_query(query, [symbol])
            
            return [self.map_to_entity(row) for row in results]
        except Exception as e:
            logger.error(f"Error fetching positions for symbol {symbol}: {e}")
            raise QueryError(f"Error fetching positions for symbol: {e}")
    
    def close_position(self, position_id: int, exit_price: Decimal) -> Position:
        """
        Close a position with the specified exit price.
        
        Args:
            position_id: Position ID
            exit_price: Exit/closing price
            
        Returns:
            Updated Position entity
        """
        try:
            # Get the current position
            position = self.get_by_id(position_id)
            
            # Check if position can be closed
            if position.status != 'OPEN':
                logger.warning(f"Cannot close position {position_id}: not open or doesn't exist")
                raise RepositoryError(f"Cannot close position {position_id}: not in OPEN status")
            
            # Calculate realized PnL
            realized_pnl = (exit_price - position.entry_price) * position.quantity
            
            # Update position properties
            position.status = 'CLOSED'
            position.closed_at = datetime.now()
            position.current_price = exit_price
            position.realized_pnl = realized_pnl
            position.unrealized_pnl = Decimal('0')
            position.updated_at = datetime.now()
            
            # Save and return updated position
            return self.update(position)
        except EntityNotFoundError:
            logger.error(f"Position with ID {position_id} not found")
            raise
        except Exception as e:
            logger.error(f"Error closing position {position_id}: {e}")
            raise QueryError(f"Error closing position: {e}")
    
    def update_market_price(self, position_id: int, current_price: Decimal) -> Position:
        """
        Update a position's current market price and recalculate unrealized PnL.
        
        Args:
            position_id: Position ID
            current_price: Current market price
            
        Returns:
            Updated Position entity
        """
        try:
            # Get the current position
            position = self.get_by_id(position_id)
            
            # Check if position can be updated
            if position.status != 'OPEN':
                logger.warning(f"Cannot update position {position_id}: not open")
                raise RepositoryError(f"Cannot update position {position_id}: not in OPEN status")
            
            # Calculate new unrealized PnL
            unrealized_pnl = (current_price - position.entry_price) * position.quantity
            
            # Update position properties
            position.current_price = current_price
            position.unrealized_pnl = unrealized_pnl
            position.updated_at = datetime.now()
            
            # Save and return updated position
            return self.update(position)
        except EntityNotFoundError:
            logger.error(f"Position with ID {position_id} not found")
            raise
        except Exception as e:
            logger.error(f"Error updating position market price {position_id}: {e}")
            raise QueryError(f"Error updating position market price: {e}")
    
    def update_all_positions_price(self, symbol: str, current_price: Decimal) -> int:
        """
        Update current market price and unrealized PnL for all open positions of a symbol.
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            
        Returns:
            Number of positions updated
        """
        try:
            query = sql.SQL("""
                UPDATE {}
                SET 
                    current_price = %s,
                    unrealized_pnl = ((%s - entry_price) * quantity),
                    updated_at = NOW()
                WHERE symbol = %s AND status = 'OPEN'
                RETURNING id
            """).format(sql.Identifier(self.table_name))
            
            results = self.execute_query(query, [current_price, current_price, symbol])
            return len(results)
        except Exception as e:
            logger.error(f"Error updating positions for symbol {symbol} with price {current_price}: {e}")
            raise QueryError(f"Error batch updating positions: {e}")
    
    def get_position_value(self, position_id: int) -> Decimal:
        """
        Calculate the current notional value of a position.
        
        Args:
            position_id: Position ID
            
        Returns:
            Decimal: Position notional value (quantity * current_price)
        """
        try:
            position = self.get_by_id(position_id)
            return position.quantity * position.current_price
        except Exception as e:
            logger.error(f"Error calculating position value for position {position_id}: {e}")
            raise QueryError(f"Error calculating position value: {e}")
    
    def get_agent_exposure(self, agent_id: str) -> Dict[str, Any]:
        """
        Calculate total exposure and metrics for an agent across all open positions.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Dictionary with exposure metrics
        """
        try:
            query = sql.SQL("""
                SELECT 
                    COUNT(*) as position_count,
                    SUM(quantity * current_price) as total_exposure,
                    SUM(unrealized_pnl) as total_unrealized_pnl,
                    COUNT(DISTINCT symbol) as symbol_count,
                    MAX(quantity * current_price) as largest_position_value
                FROM {}
                WHERE agent_id = %s AND status = 'OPEN'
            """).format(sql.Identifier(self.table_name))
            
            results = self.execute_query(query, [agent_id])
            return results[0] if results else {}
        except Exception as e:
            logger.error(f"Error calculating agent exposure for agent {agent_id}: {e}")
            raise QueryError(f"Error calculating agent exposure: {e}") 