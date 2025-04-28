"""
Example demonstrating how to use the base repository pattern with the unit of work pattern.

This script provides a simple example of creating a concrete repository that
inherits from BaseRepository and using it with the DatabaseUnitOfWork class.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional

from .base_repository import BaseRepository
from .models import Symbol, Trade
from .unit_of_work import DatabaseUnitOfWork
from .exceptions import EntityNotFoundError, RepositoryError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SymbolRepository(BaseRepository[Symbol]):
    """
    Repository for Symbol entities.
    
    This extends the BaseRepository class to provide specific functionality
    for Symbol entities.
    """
    
    def __init__(self):
        """Initialize the repository."""
        super().__init__('symbols', Symbol)
    
    def map_to_entity(self, row: Dict[str, Any]) -> Symbol:
        """
        Map a database row to a Symbol entity.
        
        Args:
            row: Database row as a dictionary
            
        Returns:
            Symbol entity
        """
        # Handle any custom mapping or conversions here
        return Symbol(
            id=row.get('id'),
            name=row.get('name'),
            type=row.get('type'),
            description=row.get('description'),
            active=row.get('active', True),
            metadata=row.get('metadata', {}),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )
    
    def map_to_db_dict(self, entity: Symbol) -> Dict[str, Any]:
        """
        Map a Symbol entity to a dictionary for database operations.
        
        Args:
            entity: Symbol entity
            
        Returns:
            Dictionary for database operations
        """
        return {
            'id': entity.id,
            'name': entity.name,
            'type': entity.type,
            'description': entity.description,
            'active': entity.active,
            'metadata': entity.metadata,
            'created_at': entity.created_at,
            'updated_at': entity.updated_at
        }
    
    def get_by_name(self, name: str) -> Optional[Symbol]:
        """
        Get a symbol by its name.
        
        Args:
            name: Symbol name
            
        Returns:
            Symbol if found, None otherwise
        """
        # Use the execute_query method to execute a custom query
        try:
            query = "SELECT * FROM symbols WHERE name = %s"
            results = self.execute_query(query, [name])
            if results:
                return self.map_to_entity(results[0])
            return None
        except Exception as e:
            logger.error(f"Error getting symbol by name: {e}")
            raise
    
    def get_active_symbols(self) -> List[Symbol]:
        """
        Get all active symbols.
        
        Returns:
            List of active symbols
        """
        try:
            query = "SELECT * FROM symbols WHERE active = %s"
            results = self.execute_query(query, [True])
            return [self.map_to_entity(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting active symbols: {e}")
            raise


class TradeRepository(BaseRepository[Trade]):
    """
    Repository for Trade entities.
    
    This extends the BaseRepository class to provide specific functionality
    for Trade entities.
    """
    
    def __init__(self):
        """Initialize the repository."""
        super().__init__('trades', Trade)
    
    def map_to_entity(self, row: Dict[str, Any]) -> Trade:
        """
        Map a database row to a Trade entity.
        
        Args:
            row: Database row as a dictionary
            
        Returns:
            Trade entity
        """
        # Handle any custom mapping or conversions here
        return Trade(
            id=row.get('id'),
            symbol_id=row.get('symbol_id'),
            open_time=row.get('open_time'),
            open_price=row.get('open_price'),
            close_time=row.get('close_time'),
            close_price=row.get('close_price'),
            volume=row.get('volume', Decimal('0.01')),
            direction=row.get('direction', 'buy'),
            pnl=row.get('pnl'),
            pips=row.get('pips'),
            status=row.get('status', 'open'),
            take_profit=row.get('take_profit'),
            stop_loss=row.get('stop_loss'),
            commission=row.get('commission'),
            swap=row.get('swap'),
            tags=row.get('tags', []),
            notes=row.get('notes'),
            metadata=row.get('metadata', {}),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )
    
    def map_to_db_dict(self, entity: Trade) -> Dict[str, Any]:
        """
        Map a Trade entity to a dictionary for database operations.
        
        Args:
            entity: Trade entity
            
        Returns:
            Dictionary for database operations
        """
        return {
            'id': entity.id,
            'symbol_id': entity.symbol_id,
            'open_time': entity.open_time,
            'open_price': entity.open_price,
            'close_time': entity.close_time,
            'close_price': entity.close_price,
            'volume': entity.volume,
            'direction': entity.direction,
            'pnl': entity.pnl,
            'pips': entity.pips,
            'status': entity.status,
            'take_profit': entity.take_profit,
            'stop_loss': entity.stop_loss,
            'commission': entity.commission,
            'swap': entity.swap,
            'tags': entity.tags,
            'notes': entity.notes,
            'metadata': entity.metadata,
            'created_at': entity.created_at,
            'updated_at': entity.updated_at
        }
    
    def get_open_trades(self) -> List[Trade]:
        """
        Get all open trades.
        
        Returns:
            List of open trades
        """
        try:
            query = "SELECT * FROM trades WHERE status = %s"
            results = self.execute_query(query, ['open'])
            return [self.map_to_entity(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting open trades: {e}")
            raise
    
    def close_trade(self, trade_id: int, close_price: Decimal, close_time: Optional[datetime] = None) -> Optional[Trade]:
        """
        Close an open trade.
        
        Args:
            trade_id: ID of the trade to close
            close_price: Closing price
            close_time: Closing time (defaults to current time)
            
        Returns:
            Updated trade if successful, None otherwise
        """
        try:
            # Get the trade
            trade = self.get_by_id(trade_id)
            
            # Check if the trade can be closed
            if trade.status != 'open':
                logger.warning(f"Cannot close trade {trade_id} because it is not open")
                return None
            
            # Set closing details
            close_time = close_time or datetime.now()
            trade.close_time = close_time
            trade.close_price = close_price
            trade.status = 'closed'
            
            # Calculate PnL and pips
            trade.pnl = trade.calculate_pnl()
            trade.pips = trade.calculate_pips()
            
            # Update the trade
            return self.update(trade)
            
        except EntityNotFoundError:
            logger.warning(f"Trade with ID {trade_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error closing trade: {e}")
            raise


def create_example_unit_of_work():
    """
    Create an example unit of work with repositories.
    
    Returns:
        Unit of work instance
    """
    # Create repositories
    symbol_repo = SymbolRepository()
    trade_repo = TradeRepository()
    
    # Create unit of work with these repositories
    uow = DatabaseUnitOfWork({
        'symbols': symbol_repo,
        'trades': trade_repo
    })
    
    return uow


def example_usage():
    """Example of using the repository pattern with unit of work."""
    # Create a unit of work
    uow = create_example_unit_of_work()
    
    try:
        # Use the unit of work to manage a transaction
        with uow:
            # Create a new symbol
            new_symbol = Symbol(
                name="EURUSD",
                type="forex",
                description="Euro vs US Dollar",
                active=True
            )
            
            # Save the symbol using the repository
            created_symbol = uow.symbols.create(new_symbol)
            logger.info(f"Created symbol: {created_symbol.name} with ID: {created_symbol.id}")
            
            # Create a new trade
            new_trade = Trade(
                symbol_id=created_symbol.id,
                open_time=datetime.now(),
                open_price=Decimal('1.0750'),
                volume=Decimal('0.01'),
                direction='buy',
                status='open'
            )
            
            # Save the trade
            created_trade = uow.trades.create(new_trade)
            logger.info(f"Created trade with ID: {created_trade.id}")
            
            # Update the trade
            created_trade.stop_loss = Decimal('1.0700')
            created_trade.take_profit = Decimal('1.0800')
            updated_trade = uow.trades.update(created_trade)
            logger.info(f"Updated trade with SL: {updated_trade.stop_loss} and TP: {updated_trade.take_profit}")
            
            # Close the trade
            closed_trade = uow.trades.close_trade(
                created_trade.id,
                Decimal('1.0780')
            )
            if closed_trade:
                logger.info(f"Closed trade with PnL: {closed_trade.pnl}")
            
            # Get open trades
            open_trades = uow.trades.get_open_trades()
            logger.info(f"Open trades count: {len(open_trades)}")
            
            # Get active symbols
            active_symbols = uow.symbols.get_active_symbols()
            logger.info(f"Active symbols count: {len(active_symbols)}")
            
            # Explicitly commit the transaction
            # Note: The context manager will commit automatically if no exceptions occur
            uow.commit()
    
    except Exception as e:
        logger.error(f"Error in example: {e}")
        # The context manager will roll back automatically on exception
    
    
if __name__ == "__main__":
    example_usage() 