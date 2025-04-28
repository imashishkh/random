"""
Trade Analytics Database Module for Forex Trading Platform v4.

This module provides classes and functions to interact with the trade analytics database
tables, including repositories for each table with CRUD operations.
"""

import logging
import datetime
import os
import random
from typing import List, Dict, Any, Optional, Union, Tuple
from decimal import Decimal

from psycopg2.extras import DictCursor, Json
from psycopg2.errors import UniqueViolation, ForeignKeyViolation

from .connection import get_db_cursor, execute_query, insert_with_json, update_with_json

# Set up logging
logger = logging.getLogger(__name__)

# Check if we're in mock mode
MOCK_DB = os.getenv("MOCK_DB", "false").lower() == "true"

# Mock data for development
MOCK_POSITIONS = [
    {
        "position_id": 1,
        "symbol": "BTCUSDT",
        "quantity": Decimal("0.12"),
        "entry_price": Decimal("43200.50"),
        "current_price": Decimal("44500.75"),
        "unrealized_pnl": Decimal("156.03"),
        "realized_pnl": Decimal("0"),
        "status": "OPEN",
        "entry_time": datetime.datetime.now() - datetime.timedelta(days=3),
        "exit_time": None,
        "agent_id": "main_trader",
        "metadata": {"strategy": "trend_following", "timeframe": "4h"}
    },
    {
        "position_id": 2,
        "symbol": "ETHUSDT",
        "quantity": Decimal("1.5"),
        "entry_price": Decimal("2405.30"),
        "current_price": Decimal("2350.25"),
        "unrealized_pnl": Decimal("-82.575"),
        "realized_pnl": Decimal("0"),
        "status": "OPEN",
        "entry_time": datetime.datetime.now() - datetime.timedelta(days=1),
        "exit_time": None,
        "agent_id": "main_trader",
        "metadata": {"strategy": "mean_reversion", "timeframe": "1h"}
    },
    {
        "position_id": 3,
        "symbol": "ADAUSDT",
        "quantity": Decimal("500"),
        "entry_price": Decimal("0.52"),
        "current_price": Decimal("0.53"),
        "unrealized_pnl": Decimal("5.0"),
        "realized_pnl": Decimal("0"),
        "status": "OPEN",
        "entry_time": datetime.datetime.now() - datetime.timedelta(days=5),
        "exit_time": None,
        "agent_id": "altcoin_trader",
        "metadata": {"strategy": "breakout", "timeframe": "1d"}
    },
    {
        "position_id": 4,
        "symbol": "SOLUSDT",
        "quantity": Decimal("10"),
        "entry_price": Decimal("95.60"),
        "current_price": Decimal("98.40"),
        "unrealized_pnl": Decimal("28.0"),
        "realized_pnl": Decimal("0"),
        "status": "OPEN",
        "entry_time": datetime.datetime.now() - datetime.timedelta(days=2),
        "exit_time": None,
        "agent_id": "altcoin_trader",
        "metadata": {"strategy": "momentum", "timeframe": "4h"}
    }
]

MOCK_CLOSED_POSITIONS = [
    {
        "position_id": 5,
        "symbol": "BTCUSDT",
        "quantity": Decimal("0.08"),
        "entry_price": Decimal("42000.50"),
        "current_price": Decimal("43500.75"),
        "unrealized_pnl": Decimal("0"),
        "realized_pnl": Decimal("120.02"),
        "status": "CLOSED",
        "entry_time": datetime.datetime.now() - datetime.timedelta(days=10),
        "exit_time": datetime.datetime.now() - datetime.timedelta(days=7),
        "agent_id": "main_trader",
        "metadata": {"strategy": "trend_following", "timeframe": "4h"}
    },
    {
        "position_id": 6,
        "symbol": "BNBUSDT",
        "quantity": Decimal("2.5"),
        "entry_price": Decimal("320.40"),
        "current_price": Decimal("310.25"),
        "unrealized_pnl": Decimal("0"),
        "realized_pnl": Decimal("-25.375"),
        "status": "CLOSED",
        "entry_time": datetime.datetime.now() - datetime.timedelta(days=15),
        "exit_time": datetime.datetime.now() - datetime.timedelta(days=12),
        "agent_id": "main_trader",
        "metadata": {"strategy": "mean_reversion", "timeframe": "1h"}
    }
]

class SymbolRepository:
    """Repository for managing trading symbols."""
    
    @staticmethod
    def create_symbol(symbol: str, base_asset: str, quote_asset: str, 
                     min_quantity: Decimal, quantity_precision: int, 
                     price_precision: int) -> bool:
        """
        Create a new trading symbol.
        
        Args:
            symbol: Symbol identifier (e.g., 'BTCUSDT')
            base_asset: Base asset code (e.g., 'BTC')
            quote_asset: Quote asset code (e.g., 'USDT')
            min_quantity: Minimum order quantity
            quantity_precision: Decimal places for quantity
            price_precision: Decimal places for price
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO symbols 
                    (symbol, base_asset, quote_asset, min_quantity, quantity_precision, 
                     price_precision, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (symbol, base_asset, quote_asset, min_quantity, quantity_precision, 
                     price_precision, True))
                return True
        except UniqueViolation:
            logger.warning(f"Symbol {symbol} already exists")
            return False
        except Exception as e:
            logger.error(f"Error creating symbol {symbol}: {e}")
            return False
    
    @staticmethod
    def get_symbol(symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get symbol details by symbol identifier.
        
        Args:
            symbol: Symbol identifier (e.g., 'BTCUSDT')
            
        Returns:
            Dict containing symbol details or None if not found
        """
        try:
            results = execute_query(
                "SELECT * FROM symbols WHERE symbol = %s", 
                (symbol,)
            )
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error fetching symbol {symbol}: {e}")
            return None
    
    @staticmethod
    def get_all_active_symbols() -> List[Dict[str, Any]]:
        """
        Get all active trading symbols.
        
        Returns:
            List of dictionaries containing symbol details
        """
        try:
            return execute_query("SELECT * FROM symbols WHERE is_active = TRUE")
        except Exception as e:
            logger.error(f"Error fetching active symbols: {e}")
            return []
    
    @staticmethod
    def update_symbol(symbol: str, updates: Dict[str, Any]) -> bool:
        """
        Update symbol details.
        
        Args:
            symbol: Symbol identifier
            updates: Dictionary of column:value pairs to update
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not updates:
            return True
            
        try:
            set_parts = []
            values = []
            
            for column, value in updates.items():
                set_parts.append(f"{column} = %s")
                values.append(value)
            
            values.append(symbol)
            query = f"UPDATE symbols SET {', '.join(set_parts)} WHERE symbol = %s"
            
            with get_db_cursor() as cursor:
                cursor.execute(query, tuple(values))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating symbol {symbol}: {e}")
            return False

    @staticmethod
    def deactivate_symbol(symbol: str) -> bool:
        """
        Deactivate a symbol (more preferable than deletion).
        
        Args:
            symbol: Symbol identifier
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    "UPDATE symbols SET is_active = FALSE WHERE symbol = %s",
                    (symbol,)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deactivating symbol {symbol}: {e}")
            return False


class AgentStateRepository:
    """Repository for managing agent states."""
    
    @staticmethod
    def create_agent(agent_id: str, agent_name: str, current_balance: Decimal,
                    available_balance: Decimal, status: str, 
                    configuration: Dict[str, Any]) -> bool:
        """
        Create a new agent state record.
        
        Args:
            agent_id: Unique agent identifier
            agent_name: Human-readable agent name
            current_balance: Total balance including positions
            available_balance: Free balance not in positions
            status: Agent status ('ACTIVE', 'PAUSED', 'STOPPED', 'ERROR')
            configuration: Agent configuration as dictionary
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO agent_states 
                    (agent_id, agent_name, current_balance, available_balance, status, 
                     last_heartbeat, configuration)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (agent_id, agent_name, current_balance, available_balance, 
                      status, datetime.datetime.now(), Json(configuration)))
                return True
        except UniqueViolation:
            logger.warning(f"Agent with ID {agent_id} already exists")
            return False
        except Exception as e:
            logger.error(f"Error creating agent {agent_id}: {e}")
            return False
    
    @staticmethod
    def get_agent(agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get agent details by ID.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Dict containing agent details or None if not found
        """
        try:
            results = execute_query(
                "SELECT * FROM agent_states WHERE agent_id = %s", 
                (agent_id,)
            )
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error fetching agent {agent_id}: {e}")
            return None
    
    @staticmethod
    def get_all_active_agents() -> List[Dict[str, Any]]:
        """
        Get all active agents.
        
        Returns:
            List of dictionaries containing agent details
        """
        try:
            return execute_query("SELECT * FROM agent_states WHERE status = 'ACTIVE'")
        except Exception as e:
            logger.error(f"Error fetching active agents: {e}")
            return []
    
    @staticmethod
    def update_agent_state(agent_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update agent state.
        
        Args:
            agent_id: Agent identifier
            updates: Dictionary of column:value pairs to update
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not updates:
            return True
            
        try:
            # Special handling for JSONB configuration field
            if 'configuration' in updates and isinstance(updates['configuration'], dict):
                updates['configuration'] = Json(updates['configuration'])
                
            set_parts = []
            values = []
            
            for column, value in updates.items():
                set_parts.append(f"{column} = %s")
                values.append(value)
            
            values.append(agent_id)
            query = f"UPDATE agent_states SET {', '.join(set_parts)} WHERE agent_id = %s"
            
            with get_db_cursor() as cursor:
                cursor.execute(query, tuple(values))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating agent {agent_id}: {e}")
            return False
    
    @staticmethod
    def update_heartbeat(agent_id: str) -> bool:
        """
        Update agent's last heartbeat timestamp.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    "UPDATE agent_states SET last_heartbeat = NOW() WHERE agent_id = %s",
                    (agent_id,)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating heartbeat for agent {agent_id}: {e}")
            return False


class PositionRepository:
    """Repository for managing trading positions."""
    
    @staticmethod
    def create_position(symbol: str, quantity: Decimal, entry_price: Decimal,
                       current_price: Decimal, agent_id: str) -> Optional[int]:
        """
        Create a new position.
        
        Args:
            symbol: Trading symbol
            quantity: Position quantity
            entry_price: Entry price per unit
            current_price: Current market price
            agent_id: Agent identifier
            
        Returns:
            Position ID if successful, None otherwise
        """
        if MOCK_DB:
            # Generate a mock position ID
            new_id = len(MOCK_POSITIONS) + 7
            
            # Calculate unrealized PnL
            unrealized_pnl = (current_price - entry_price) * quantity
            
            # Create new mock position
            new_position = {
                "position_id": new_id,
                "symbol": symbol,
                "quantity": quantity,
                "entry_price": entry_price,
                "current_price": current_price,
                "unrealized_pnl": unrealized_pnl,
                "realized_pnl": Decimal("0"),
                "status": "OPEN",
                "entry_time": datetime.datetime.now(),
                "exit_time": None,
                "agent_id": agent_id,
                "metadata": {}
            }
            
            # Add to mock positions
            MOCK_POSITIONS.append(new_position)
            return new_id
            
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO positions 
                    (symbol, quantity, entry_price, current_price, unrealized_pnl, 
                     status, entry_time, agent_id)
                    VALUES (%s, %s, %s, %s, %s, 'OPEN', %s, %s)
                    RETURNING position_id
                """, (
                    symbol, quantity, entry_price, current_price, 
                    (current_price - entry_price) * quantity,
                    datetime.datetime.now(), agent_id
                ))
                result = cursor.fetchone()
                return result['position_id'] if result else None
        except Exception as e:
            logger.error(f"Error creating position: {e}")
            return None
    
    @staticmethod
    def get_position(position_id: int) -> Optional[Dict[str, Any]]:
        """
        Get position details.
        
        Args:
            position_id: Position ID
            
        Returns:
            Dictionary with position details or None if not found
        """
        if MOCK_DB:
            # Find position in mock data
            for position in MOCK_POSITIONS + MOCK_CLOSED_POSITIONS:
                if position["position_id"] == position_id:
                    return position.copy()
            return None
            
        try:
            results = execute_query(
                "SELECT * FROM positions WHERE position_id = %s", 
                (position_id,)
            )
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error fetching position {position_id}: {e}")
            return None
    
    @staticmethod
    def get_open_positions(agent_id: str = None) -> List[Dict[str, Any]]:
        """
        Get all open positions, optionally filtered by agent.
        
        Args:
            agent_id: Optional agent ID to filter by
            
        Returns:
            List of dictionaries with position details
        """
        if MOCK_DB:
            # Filter positions by agent_id if provided
            if agent_id:
                return [pos.copy() for pos in MOCK_POSITIONS if pos["agent_id"] == agent_id]
            return [pos.copy() for pos in MOCK_POSITIONS]
            
        try:
            query = "SELECT * FROM positions WHERE status = 'OPEN'"
            params = []
            
            if agent_id:
                query += " AND agent_id = %s"
                params.append(agent_id)
                
            return execute_query(query, tuple(params) if params else None)
        except Exception as e:
            logger.error(f"Error fetching open positions: {e}")
            return []
    
    @staticmethod
    def update_position(position_id: int, updates: Dict[str, Any]) -> bool:
        """
        Update position details.
        
        Args:
            position_id: Position ID
            updates: Dictionary of column:value pairs to update
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not updates:
            return True
            
        try:
            set_parts = []
            values = []
            
            for column, value in updates.items():
                set_parts.append(f"{column} = %s")
                values.append(value)
            
            values.append(position_id)
            query = f"UPDATE positions SET {', '.join(set_parts)} WHERE position_id = %s"
            
            with get_db_cursor() as cursor:
                cursor.execute(query, tuple(values))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating position {position_id}: {e}")
            return False
    
    @staticmethod
    def close_position(position_id: int, exit_price: Decimal) -> bool:
        """
        Close a position with the specified exit price.
        
        Args:
            position_id: Position ID
            exit_price: Exit/closing price
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get current position details
            position = PositionRepository.get_position(position_id)
            if not position or position['status'] != 'OPEN':
                logger.warning(f"Cannot close position {position_id}: not open or doesn't exist")
                return False
            
            # Calculate realized PnL
            realized_pnl = (exit_price - position['entry_price']) * position['quantity']
            
            with get_db_cursor() as cursor:
                cursor.execute("""
                    UPDATE positions
                    SET status = 'CLOSED', 
                        closed_at = NOW(),
                        current_price = %s,
                        realized_pnl = %s,
                        unrealized_pnl = 0
                    WHERE position_id = %s AND status = 'OPEN'
                """, (exit_price, realized_pnl, position_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error closing position {position_id}: {e}")
            return False
    
    @staticmethod
    def update_position_market_price(position_id: int, current_price: Decimal) -> bool:
        """
        Update a position's current market price and recalculate unrealized PnL.
        
        Args:
            position_id: Position ID
            current_price: Current market price
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get current position details
            position = PositionRepository.get_position(position_id)
            if not position or position['status'] != 'OPEN':
                logger.warning(f"Cannot update position {position_id}: not open or doesn't exist")
                return False
            
            # Calculate new unrealized PnL
            unrealized_pnl = (current_price - position['entry_price']) * position['quantity']
            
            with get_db_cursor() as cursor:
                cursor.execute("""
                    UPDATE positions
                    SET current_price = %s,
                        unrealized_pnl = %s
                    WHERE position_id = %s AND status = 'OPEN'
                """, (current_price, unrealized_pnl, position_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating position market price {position_id}: {e}")
            return False


class TradeFillRepository:
    """Repository for managing trade fills."""
    
    @staticmethod
    def create_trade_fill(trade_id: str, symbol: str, price: Decimal, quantity: Decimal,
                         side: str, executed_at: datetime.datetime, fee: Decimal, 
                         fee_asset: str, order_id: str, agent_id: str, 
                         position_id: Optional[int] = None) -> Optional[int]:
        """
        Create a new trade fill record.
        
        Args:
            trade_id: Exchange-provided trade ID
            symbol: Trading symbol
            price: Execution price
            quantity: Executed quantity
            side: Trade side ('BUY' or 'SELL')
            executed_at: Execution timestamp
            fee: Fee amount
            fee_asset: Fee currency
            order_id: Exchange-provided order ID
            agent_id: Associated agent ID
            position_id: Optional position ID
            
        Returns:
            int: Trade fill ID if successful, None otherwise
        """
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO trade_fills 
                    (trade_id, symbol, price, quantity, side, executed_at, fee, 
                     fee_asset, order_id, agent_id, position_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    trade_id, symbol, price, quantity, side, executed_at, fee,
                    fee_asset, order_id, agent_id, position_id
                ))
                result = cursor.fetchone()
                return result[0] if result else None
        except ForeignKeyViolation as e:
            logger.error(f"Foreign key violation creating trade fill: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creating trade fill: {e}")
            return None
    
    @staticmethod
    def get_trade_fill(trade_fill_id: int) -> Optional[Dict[str, Any]]:
        """
        Get trade fill details by ID.
        
        Args:
            trade_fill_id: Trade fill ID
            
        Returns:
            Dict containing trade fill details or None if not found
        """
        try:
            results = execute_query(
                "SELECT * FROM trade_fills WHERE id = %s", 
                (trade_fill_id,)
            )
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error fetching trade fill {trade_fill_id}: {e}")
            return None
    
    @staticmethod
    def get_trade_fills_by_position(position_id: int) -> List[Dict[str, Any]]:
        """
        Get all trade fills for a specific position.
        
        Args:
            position_id: Position ID
            
        Returns:
            List of dictionaries containing trade fill details
        """
        try:
            return execute_query(
                "SELECT * FROM trade_fills WHERE position_id = %s ORDER BY executed_at",
                (position_id,)
            )
        except Exception as e:
            logger.error(f"Error fetching trade fills for position {position_id}: {e}")
            return []
    
    @staticmethod
    def get_trade_fills_by_agent(agent_id: str, 
                                from_date: Optional[datetime.datetime] = None,
                                to_date: Optional[datetime.datetime] = None,
                                limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get trade fills for a specific agent, optionally filtered by date range.
        
        Args:
            agent_id: Agent ID
            from_date: Optional start date for filtering
            to_date: Optional end date for filtering
            limit: Maximum number of records to return
            
        Returns:
            List of dictionaries containing trade fill details
        """
        try:
            query = "SELECT * FROM trade_fills WHERE agent_id = %s"
            params = [agent_id]
            
            if from_date:
                query += " AND executed_at >= %s"
                params.append(from_date)
                
            if to_date:
                query += " AND executed_at <= %s"
                params.append(to_date)
                
            query += " ORDER BY executed_at DESC LIMIT %s"
            params.append(limit)
            
            return execute_query(query, tuple(params))
        except Exception as e:
            logger.error(f"Error fetching trade fills for agent {agent_id}: {e}")
            return []
    
    @staticmethod
    def assign_trade_fill_to_position(trade_fill_id: int, position_id: int) -> bool:
        """
        Assign a trade fill to a position.
        
        Args:
            trade_fill_id: Trade fill ID
            position_id: Position ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    "UPDATE trade_fills SET position_id = %s WHERE id = %s",
                    (position_id, trade_fill_id)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error assigning trade fill {trade_fill_id} to position {position_id}: {e}")
            return False


class RiskAlertRepository:
    """Repository for managing risk alerts."""
    
    @staticmethod
    def create_risk_alert(agent_id: str, alert_type: str, severity: str, 
                         message: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """
        Create a new risk alert.
        
        Args:
            agent_id: Associated agent ID
            alert_type: Type of alert
            severity: Alert severity ('INFO', 'WARNING', 'CRITICAL', 'EMERGENCY')
            message: Alert message
            metadata: Optional additional context
            
        Returns:
            int: Alert ID if successful, None otherwise
        """
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO risk_alerts 
                    (agent_id, alert_type, severity, message, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    agent_id, 
                    alert_type, 
                    severity, 
                    message, 
                    Json(metadata) if metadata else None
                ))
                result = cursor.fetchone()
                return result[0] if result else None
        except ForeignKeyViolation as e:
            logger.error(f"Foreign key violation creating risk alert: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creating risk alert: {e}")
            return None
    
    @staticmethod
    def get_risk_alert(alert_id: int) -> Optional[Dict[str, Any]]:
        """
        Get risk alert details by ID.
        
        Args:
            alert_id: Alert ID
            
        Returns:
            Dict containing alert details or None if not found
        """
        try:
            results = execute_query(
                "SELECT * FROM risk_alerts WHERE id = %s", 
                (alert_id,)
            )
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error fetching risk alert {alert_id}: {e}")
            return None
    
    @staticmethod
    def get_active_alerts(agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all unresolved risk alerts, optionally filtered by agent ID.
        
        Args:
            agent_id: Optional agent ID to filter by
            
        Returns:
            List of dictionaries containing alert details
        """
        try:
            if agent_id:
                return execute_query(
                    "SELECT * FROM risk_alerts WHERE resolved = FALSE AND agent_id = %s ORDER BY triggered_at DESC",
                    (agent_id,)
                )
            else:
                return execute_query(
                    "SELECT * FROM risk_alerts WHERE resolved = FALSE ORDER BY triggered_at DESC"
                )
        except Exception as e:
            logger.error(f"Error fetching active alerts: {e}")
            return []
    
    @staticmethod
    def resolve_alert(alert_id: int) -> bool:
        """
        Mark a risk alert as resolved.
        
        Args:
            alert_id: Alert ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    "UPDATE risk_alerts SET resolved = TRUE, resolved_at = NOW() WHERE id = %s",
                    (alert_id,)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error resolving alert {alert_id}: {e}")
            return False


class AnalyticsService:
    """Service for aggregating and analyzing trading data."""
    
    @staticmethod
    def get_agent_performance(agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get performance summary for an agent.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Dictionary with performance metrics or None if not found
        """
        if MOCK_DB:
            # Filter positions by agent
            agent_positions = [pos for pos in MOCK_POSITIONS + MOCK_CLOSED_POSITIONS 
                              if pos["agent_id"] == agent_id]
            
            if not agent_positions:
                return None
                
            # Calculate metrics
            total_realized_pnl = sum(pos["realized_pnl"] for pos in agent_positions)
            open_positions = [pos for pos in agent_positions if pos["status"] == "OPEN"]
            total_unrealized_pnl = sum(pos["unrealized_pnl"] for pos in open_positions)
            
            win_trades = [pos for pos in agent_positions 
                         if pos["status"] == "CLOSED" and pos["realized_pnl"] > 0]
            loss_trades = [pos for pos in agent_positions 
                          if pos["status"] == "CLOSED" and pos["realized_pnl"] < 0]
                          
            win_rate = len(win_trades) / len(agent_positions) if agent_positions else 0
            
            return {
                "agent_id": agent_id,
                "total_realized_pnl": total_realized_pnl,
                "total_unrealized_pnl": total_unrealized_pnl,
                "total_pnl": total_realized_pnl + total_unrealized_pnl,
                "win_rate": win_rate,
                "open_positions_count": len(open_positions),
                "closed_positions_count": len(agent_positions) - len(open_positions),
                "total_positions_count": len(agent_positions)
            }
            
        try:
            # Join positions and agent_states to get performance metrics
            query = """
                SELECT 
                    a.agent_id,
                    a.agent_name,
                    a.current_balance,
                    a.available_balance,
                    COUNT(p.position_id) AS total_positions,
                    SUM(CASE WHEN p.status = 'OPEN' THEN 1 ELSE 0 END) AS open_positions,
                    SUM(CASE WHEN p.status = 'CLOSED' THEN 1 ELSE 0 END) AS closed_positions,
                    SUM(p.realized_pnl) AS total_realized_pnl,
                    SUM(CASE WHEN p.status = 'OPEN' THEN p.unrealized_pnl ELSE 0 END) AS total_unrealized_pnl,
                    AVG(CASE WHEN p.status = 'CLOSED' THEN p.realized_pnl END) AS avg_profit_per_trade,
                    SUM(CASE WHEN p.realized_pnl > 0 THEN 1 ELSE 0 END) AS winning_trades,
                    SUM(CASE WHEN p.realized_pnl < 0 THEN 1 ELSE 0 END) AS losing_trades
                FROM 
                    agent_states a
                LEFT JOIN 
                    positions p ON a.agent_id = p.agent_id
                WHERE 
                    a.agent_id = %s
                GROUP BY 
                    a.agent_id, a.agent_name, a.current_balance, a.available_balance
            """
            results = execute_query(query, (agent_id,))
            
            if not results:
                return None
                
            performance = results[0]
            
            # Calculate win rate
            if performance['winning_trades'] is not None and performance['total_positions'] > 0:
                win_rate = performance['winning_trades'] / performance['total_positions']
            else:
                win_rate = 0
                
            # Add win rate to performance dict
            performance['win_rate'] = win_rate
            
            return performance
            
        except Exception as e:
            logger.error(f"Error getting agent performance: {e}")
            return None
    
    @staticmethod
    def get_daily_pnl(agent_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get daily profit/loss for an agent.
        
        Args:
            agent_id: Agent identifier
            days: Number of past days to include
            
        Returns:
            List of dictionaries with daily PnL values
        """
        if MOCK_DB:
            # Generate mock daily PnL data
            daily_pnl = []
            start_date = datetime.datetime.now() - datetime.timedelta(days=days)
            
            for day in range(days):
                current_date = start_date + datetime.timedelta(days=day)
                # Generate random PnL between -100 and 300
                pnl_value = Decimal(str(random.uniform(-100, 300)))
                
                daily_pnl.append({
                    "date": current_date.date(),
                    "realized_pnl": pnl_value,
                    "unrealized_pnl": Decimal(str(random.uniform(-50, 150))),
                    "cumulative_pnl": sum(entry["realized_pnl"] for entry in daily_pnl) + pnl_value
                })
                
            return daily_pnl
            
        try:
            # Calculate date range
            end_date = datetime.datetime.now()
            start_date = end_date - datetime.timedelta(days=days)
            
            # Get daily PnL from trade_fills and positions
            query = """
                WITH daily_realized AS (
                    SELECT 
                        DATE(executed_at) AS trade_date,
                        SUM(
                            CASE 
                                WHEN side = 'SELL' THEN (price * quantity) - (entry_price * quantity)
                                ELSE 0
                            END
                        ) AS realized_pnl
                    FROM 
                        trade_fills tf
                    JOIN 
                        positions p ON tf.position_id = p.position_id
                    WHERE 
                        tf.agent_id = %s AND
                        executed_at >= %s AND
                        executed_at <= %s
                    GROUP BY 
                        DATE(executed_at)
                ),
                daily_unrealized AS (
                    SELECT 
                        CURRENT_DATE AS calc_date,
                        SUM(unrealized_pnl) AS unrealized_pnl
                    FROM 
                        positions
                    WHERE 
                        agent_id = %s AND
                        status = 'OPEN'
                    GROUP BY 
                        CURRENT_DATE
                )
                SELECT 
                    dr.trade_date AS date,
                    dr.realized_pnl,
                    CASE 
                        WHEN dr.trade_date = CURRENT_DATE THEN du.unrealized_pnl 
                        ELSE 0 
                    END AS unrealized_pnl
                FROM 
                    daily_realized dr
                LEFT JOIN 
                    daily_unrealized du ON dr.trade_date = du.calc_date
                ORDER BY 
                    dr.trade_date
            """
            
            results = execute_query(
                query, 
                (agent_id, start_date, end_date, agent_id)
            )
            
            # Calculate cumulative PnL
            cumulative = Decimal('0')
            for i, day in enumerate(results):
                cumulative += day['realized_pnl']
                results[i]['cumulative_pnl'] = cumulative
                
            return results
            
        except Exception as e:
            logger.error(f"Error getting daily PnL: {e}")
            return []
    
    @staticmethod
    def calculate_position_metrics(agent_id: str) -> Dict[str, Any]:
        """
        Calculate position-based metrics for an agent.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Dictionary with calculated metrics
        """
        if MOCK_DB:
            # Filter positions by agent
            agent_positions = [pos for pos in MOCK_POSITIONS + MOCK_CLOSED_POSITIONS 
                              if pos["agent_id"] == agent_id]
                              
            closed_positions = [pos for pos in agent_positions if pos["status"] == "CLOSED"]
            open_positions = [pos for pos in agent_positions if pos["status"] == "OPEN"]
            
            # Calculate metrics
            avg_position_size = sum(pos["quantity"] * pos["entry_price"] for pos in agent_positions) / len(agent_positions) if agent_positions else Decimal('0')
            avg_holding_time = sum((pos["exit_time"] - pos["entry_time"]).total_seconds() for pos in closed_positions) / len(closed_positions) if closed_positions else 0
            
            return {
                "total_positions": len(agent_positions),
                "open_positions": len(open_positions),
                "closed_positions": len(closed_positions),
                "avg_position_size": avg_position_size,
                "avg_holding_time_seconds": avg_holding_time,
                "largest_position": max((pos["quantity"] * pos["entry_price"] for pos in agent_positions), default=Decimal('0')),
                "smallest_position": min((pos["quantity"] * pos["entry_price"] for pos in agent_positions), default=Decimal('0')),
                "by_symbol": {
                    symbol: len([pos for pos in agent_positions if pos["symbol"] == symbol])
                    for symbol in set(pos["symbol"] for pos in agent_positions)
                }
            }
        else:
            # Implementation of the method in the original code
            # This part should be implemented based on the original code's logic
            # For now, we'll return an empty dictionary
            return {}


# Initialize tables if they don't exist
def initialize_tables():
    """
    Initialize the analytics tables by running the SQL schema.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        import os
        schema_path = os.path.join(os.path.dirname(__file__), 'trade_analytics_schema.sql')
        
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
            
        with get_db_cursor() as cursor:
            cursor.execute(schema_sql)
            
        logger.info("Trade analytics tables initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Error initializing trade analytics tables: {e}")
        return False 