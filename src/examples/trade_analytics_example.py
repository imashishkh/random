"""
Example usage of the Trade Analytics data access layer.

This script demonstrates how to use the repositories and Unit of Work pattern
to interact with trade analytics data.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
import uuid

from ..db.models.trade_fill import TradeFill
from ..db.models.position import Position
from ..db.repositories.trade_analytics_unit_of_work import TradeAnalyticsUnitOfWork
from ..db.exceptions import EntityNotFoundError, QueryError, RepositoryError

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_trade_fill_example():
    """Example of creating a trade fill."""
    logger.info("Running trade fill creation example...")
    
    # Create a trade fill instance
    trade_fill = TradeFill(
        trade_id=f"t-{str(uuid.uuid4())[:8]}",
        symbol="BTCUSDT",
        price=Decimal("45000.00"),
        quantity=Decimal("0.1"),
        side="BUY",
        executed_at=datetime.now(),
        fee=Decimal("2.25"),
        fee_asset="USDT",
        order_id=f"o-{str(uuid.uuid4())[:8]}",
        agent_id=f"agent-{str(uuid.uuid4())[:8]}"
    )
    
    # Use Unit of Work to create the trade fill
    try:
        with TradeAnalyticsUnitOfWork() as uow:
            created_fill = uow.trade_fills.create(trade_fill)
            logger.info(f"Created trade fill with ID: {created_fill.id}")
            
            # The transaction is automatically committed when exiting the context
            # without exceptions
    except Exception as e:
        logger.error(f"Error creating trade fill: {e}")
        
    return trade_fill


def create_position_example(agent_id: str, symbol: str):
    """
    Example of creating a position.
    
    Args:
        agent_id: Agent ID
        symbol: Trading symbol
    """
    logger.info("Running position creation example...")
    
    # Create a position instance
    position = Position(
        symbol=symbol,
        quantity=Decimal("0.5"),
        entry_price=Decimal("45000.00"),
        current_price=Decimal("45100.00"),
        agent_id=agent_id,
        opened_at=datetime.now()
    )
    
    # Calculate initial unrealized PnL
    position.update_unrealized_pnl()
    
    # Use Unit of Work to create the position
    try:
        with TradeAnalyticsUnitOfWork() as uow:
            created_position = uow.positions.create(position)
            logger.info(f"Created position with ID: {created_position.id}")
            logger.info(f"Initial unrealized PnL: {created_position.unrealized_pnl}")
            
            # The transaction is automatically committed when exiting the context
            # without exceptions
            return created_position
    except Exception as e:
        logger.error(f"Error creating position: {e}")
        return None


def associate_trade_fill_with_position(trade_fill_id: int, position_id: int):
    """
    Example of associating a trade fill with a position.
    
    Args:
        trade_fill_id: Trade fill ID
        position_id: Position ID
    """
    logger.info(f"Associating trade fill {trade_fill_id} with position {position_id}...")
    
    try:
        with TradeAnalyticsUnitOfWork() as uow:
            # Get the trade fill
            trade_fill = uow.trade_fills.get_by_id(trade_fill_id)
            
            # Get the position
            position = uow.positions.get_by_id(position_id)
            
            # Associate the trade fill with the position
            trade_fill.position_id = position.id
            
            # Update the trade fill
            updated_fill = uow.trade_fills.update(trade_fill)
            logger.info(f"Associated trade fill {updated_fill.id} with position {position.id}")
            
    except EntityNotFoundError as e:
        logger.error(f"Entity not found: {e}")
    except Exception as e:
        logger.error(f"Error associating trade fill with position: {e}")


def close_position_example(position_id: int, exit_price: Decimal):
    """
    Example of closing a position.
    
    Args:
        position_id: Position ID
        exit_price: Exit/closing price
    """
    logger.info(f"Closing position {position_id} at price {exit_price}...")
    
    try:
        with TradeAnalyticsUnitOfWork() as uow:
            # Close the position
            closed_position = uow.positions.close_position(position_id, exit_price)
            
            logger.info(f"Closed position {closed_position.id}")
            logger.info(f"Realized PnL: {closed_position.realized_pnl}")
            logger.info(f"PnL percentage: {closed_position.pnl_percentage}%")
            logger.info(f"Position duration: {closed_position.duration} seconds")
            
    except EntityNotFoundError as e:
        logger.error(f"Position not found: {e}")
    except Exception as e:
        logger.error(f"Error closing position: {e}")


def update_position_price_example(position_id: int, new_price: Decimal):
    """
    Example of updating a position's current price.
    
    Args:
        position_id: Position ID
        new_price: New current price
    """
    logger.info(f"Updating position {position_id} with new price {new_price}...")
    
    try:
        with TradeAnalyticsUnitOfWork() as uow:
            # Update the position's market price
            updated_position = uow.positions.update_market_price(position_id, new_price)
            
            logger.info(f"Updated position {updated_position.id}")
            logger.info(f"New unrealized PnL: {updated_position.unrealized_pnl}")
            logger.info(f"PnL percentage: {updated_position.pnl_percentage}%")
            
    except EntityNotFoundError as e:
        logger.error(f"Position not found: {e}")
    except Exception as e:
        logger.error(f"Error updating position price: {e}")


def query_examples(agent_id: str, symbol: str):
    """
    Examples of various queries using the repositories.
    
    Args:
        agent_id: Agent ID for filtering
        symbol: Symbol for filtering
    """
    logger.info("Running query examples...")
    
    try:
        with TradeAnalyticsUnitOfWork() as uow:
            # Get open positions for an agent
            open_positions = uow.positions.get_open_positions(agent_id)
            logger.info(f"Found {len(open_positions)} open positions for agent {agent_id}")
            
            # Get trade fills for a symbol in the last day
            yesterday = datetime.now() - timedelta(days=1)
            trade_fills = uow.trade_fills.get_by_symbol(
                symbol, from_date=yesterday, limit=10
            )
            logger.info(f"Found {len(trade_fills)} trade fills for symbol {symbol} in the last day")
            
            # Get position statistics for an agent
            stats = uow.positions.get_agent_exposure(agent_id)
            if stats:
                logger.info(f"Agent exposure statistics:")
                for key, value in stats.items():
                    logger.info(f"  {key}: {value}")
            
    except Exception as e:
        logger.error(f"Error in query examples: {e}")


def main():
    """Main function to run the examples."""
    logger.info("Starting Trade Analytics Example...")
    
    # Generate a random agent ID and symbol for the examples
    agent_id = f"agent-{str(uuid.uuid4())[:8]}"
    symbol = "BTCUSDT"
    
    # Create a trade fill
    trade_fill = create_trade_fill_example()
    
    # Create a position
    position = create_position_example(agent_id, symbol)
    
    if trade_fill is not None and position is not None and trade_fill.id and position.id:
        # Associate the trade fill with the position
        associate_trade_fill_with_position(trade_fill.id, position.id)
        
        # Update the position price after some time (simulating market movement)
        new_price = Decimal("45500.00")
        update_position_price_example(position.id, new_price)
        
        # Run some query examples
        query_examples(agent_id, symbol)
        
        # Close the position
        exit_price = Decimal("46000.00")
        close_position_example(position.id, exit_price)
    
    logger.info("Finished Trade Analytics Example")


if __name__ == "__main__":
    main() 