"""
Position management functionality.

This module provides functions for managing and tracking trading positions,
including position creation, updates, and position-related calculations.
"""
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

from .models import Position, PositionSide, PositionStatus
from ..exchange.base import BaseExchange

# Configure logger
logger = logging.getLogger(__name__)


class PositionManager:
    """Position manager for tracking and managing trading positions."""
    
    def __init__(self, exchange: BaseExchange):
        """
        Initialize the position manager.
        
        Args:
            exchange: The exchange client
        """
        self.exchange = exchange
        self.exchange_name = exchange.exchange_name.lower()
        
        logger.info(f"Initialized position manager for {self.exchange_name}")
    
    def open_position(self, 
                    symbol: str, 
                    side: Union[PositionSide, str],
                    amount: float,
                    entry_price: float,
                    leverage: float = 1.0,
                    margin_type: str = "isolated",
                    stop_loss: Optional[float] = None,
                    take_profit: Optional[float] = None) -> Position:
        """
        Open a new position.
        
        Args:
            symbol: Trading pair symbol
            side: Position side (LONG, SHORT)
            amount: Position size/amount
            entry_price: Entry price
            leverage: Leverage multiplier
            margin_type: Margin type (isolated, cross)
            stop_loss: Stop loss price
            take_profit: Take profit price
            
        Returns:
            Position model representing the opened position
        """
        try:
            # Convert string side to enum if needed
            if isinstance(side, str):
                side = PositionSide(side.lower())
            
            # Validate parameters
            if amount <= 0:
                raise ValueError(f"Position amount must be positive, got {amount}")
            
            if entry_price <= 0:
                raise ValueError(f"Entry price must be positive, got {entry_price}")
            
            if leverage < 1.0:
                raise ValueError(f"Leverage must be at least 1.0, got {leverage}")
            
            # Calculate liquidation price (simplified)
            liquidation_price = None
            if leverage > 1.0:
                # This is a very simplified calculation - actual liquidation price
                # would depend on position size, account balance, funding rates, etc.
                if side == PositionSide.LONG:
                    liquidation_price = entry_price * (1 - (1 / leverage))
                else:  # SHORT
                    liquidation_price = entry_price * (1 + (1 / leverage))
            
            # Create position object
            position = Position(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                amount=amount,
                leverage=leverage,
                liquidation_price=liquidation_price,
                margin_type=margin_type,
                status=PositionStatus.OPEN,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                open_time=datetime.utcnow(),
                stop_loss=stop_loss,
                take_profit=take_profit,
                exchange=self.exchange_name
            )
            
            # TODO: Store position in database
            # This is a placeholder - actual implementation would save to a database
            logger.info(f"Opened {side.value} position for {amount} {symbol} at {entry_price}")
            
            return position
        
        except Exception as e:
            logger.error(f"Error opening position: {str(e)}")
            raise
    
    def close_position(self, 
                     position: Position,
                     exit_price: float,
                     amount: Optional[float] = None) -> Position:
        """
        Close a position fully or partially.
        
        Args:
            position: Position to close
            exit_price: Exit price
            amount: Amount to close (if None, closes entire position)
            
        Returns:
            Updated Position model
        """
        try:
            # Validate parameters
            if exit_price <= 0:
                raise ValueError(f"Exit price must be positive, got {exit_price}")
            
            closing_amount = amount if amount is not None else position.amount
            
            if closing_amount <= 0 or closing_amount > position.amount:
                raise ValueError(f"Invalid closing amount: {closing_amount}")
            
            # Calculate realized PNL
            price_diff = exit_price - position.entry_price
            if position.side == PositionSide.SHORT:
                price_diff = -price_diff
            
            # PnL = (exit_price - entry_price) * amount * side_multiplier
            realized_pnl = price_diff * closing_amount
            
            # Update position
            position.realized_pnl += realized_pnl
            
            # Full close
            if closing_amount == position.amount or amount is None:
                position.status = PositionStatus.CLOSED
                position.close_time = datetime.utcnow()
                position.amount = 0
                position.unrealized_pnl = 0
            # Partial close
            else:
                position.status = PositionStatus.PARTIALLY_CLOSED
                position.amount -= closing_amount
                
                # Recalculate unrealized PNL for remaining position
                current_price = exit_price  # Using exit price as current price
                remaining_price_diff = current_price - position.entry_price
                if position.side == PositionSide.SHORT:
                    remaining_price_diff = -remaining_price_diff
                
                position.unrealized_pnl = remaining_price_diff * position.amount
            
            # TODO: Update position in database
            # This is a placeholder - actual implementation would update the database
            
            if position.status == PositionStatus.CLOSED:
                logger.info(f"Closed {position.side.value} position for {position.symbol} at {exit_price} with PNL: {realized_pnl}")
            else:
                logger.info(f"Partially closed {position.side.value} position for {position.symbol}, {closing_amount} at {exit_price} with PNL: {realized_pnl}")
            
            return position
        
        except Exception as e:
            logger.error(f"Error closing position: {str(e)}")
            raise
    
    def update_position_price(self,
                            position: Position,
                            current_price: float) -> Position:
        """
        Update position with current market price.
        
        Args:
            position: Position to update
            current_price: Current market price
            
        Returns:
            Updated Position model
        """
        try:
            # Validate parameters
            if current_price <= 0:
                raise ValueError(f"Current price must be positive, got {current_price}")
            
            if position.status == PositionStatus.CLOSED:
                # No need to update closed positions
                return position
            
            # Calculate unrealized PNL
            price_diff = current_price - position.entry_price
            if position.side == PositionSide.SHORT:
                price_diff = -price_diff
            
            position.unrealized_pnl = price_diff * position.amount
            
            # Check stop loss / take profit (spot trading)
            if position.stop_loss and position.status == PositionStatus.OPEN:
                if (position.side == PositionSide.LONG and current_price <= position.stop_loss) or \
                   (position.side == PositionSide.SHORT and current_price >= position.stop_loss):
                    # Stop loss hit, close position
                    logger.info(f"Stop loss triggered for {position.symbol} at {current_price}")
                    return self.close_position(position, position.stop_loss)
            
            if position.take_profit and position.status == PositionStatus.OPEN:
                if (position.side == PositionSide.LONG and current_price >= position.take_profit) or \
                   (position.side == PositionSide.SHORT and current_price <= position.take_profit):
                    # Take profit hit, close position
                    logger.info(f"Take profit triggered for {position.symbol} at {current_price}")
                    return self.close_position(position, position.take_profit)
            
            # TODO: Update position in database
            # This is a placeholder - actual implementation would update the database
            
            return position
        
        except Exception as e:
            logger.error(f"Error updating position price: {str(e)}")
            raise
    
    def get_position_value(self, position: Position, current_price: Optional[float] = None) -> float:
        """
        Calculate the current value of a position.
        
        Args:
            position: Position to value
            current_price: Current market price (if None, uses entry price)
            
        Returns:
            Current position value
        """
        try:
            if position.status == PositionStatus.CLOSED or position.amount <= 0:
                return 0.0
            
            price = current_price if current_price is not None else position.entry_price
            
            # Position value = amount * price
            position_value = position.amount * price
            
            return position_value
        
        except Exception as e:
            logger.error(f"Error calculating position value: {str(e)}")
            raise
    
    def get_position_margin(self, position: Position) -> float:
        """
        Calculate the margin used by a position.
        
        Args:
            position: Position to calculate margin for
            
        Returns:
            Margin amount used by the position
        """
        try:
            if position.status == PositionStatus.CLOSED or position.amount <= 0:
                return 0.0
            
            # For spot trading with no leverage
            if position.leverage <= 1.0:
                return position.amount * position.entry_price
            
            # For leveraged trading
            # Margin = position value / leverage
            position_value = position.amount * position.entry_price
            margin = position_value / position.leverage
            
            return margin
        
        except Exception as e:
            logger.error(f"Error calculating position margin: {str(e)}")
            raise 