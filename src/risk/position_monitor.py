"""
Position monitoring system for real-time tracking and risk management.

This module provides classes and functions for monitoring trading positions,
calculating risk metrics, and implementing risk management controls.
"""

import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Union, Set
from enum import Enum

import pandas as pd
import numpy as np
from pydantic import BaseModel, Field, validator

from ..account.models import PositionSide, PositionStatus

# Configure logger
logger = logging.getLogger(__name__)


class PositionType(str, Enum):
    """Types of positions that can be tracked."""
    SPOT = "spot"
    MARGIN = "margin"
    FUTURES = "futures"
    OPTION = "option"


class Position(BaseModel):
    """
    Comprehensive position tracking model with risk metrics.
    
    This class represents a trading position with detailed tracking of
    entry/exit information, P&L calculations, and risk metrics.
    """
    # Core position data
    position_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    side: PositionSide
    entry_price: float
    current_price: float
    quantity: float
    leverage: float = 1.0
    position_type: PositionType = PositionType.SPOT
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    
    # Status tracking
    status: PositionStatus = PositionStatus.OPEN
    is_hedged: bool = False
    
    # Risk management
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop: Optional[float] = None
    max_drawdown: float = 0.0
    
    # P&L tracking
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    fees: float = 0.0
    
    # Additional metadata
    strategy_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    notes: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Advanced exit management
    partial_exit_points: Dict[float, float] = Field(default_factory=dict)  # price: percentage
    exit_orders: List[Dict[str, Any]] = Field(default_factory=list)
    
    class Config:
        validate_assignment = True
    
    def __init__(self, **data):
        """Initialize position and calculate initial metrics."""
        super().__init__(**data)
        self.calculate_unrealized_pnl()
    
    def update_price(self, price: float, timestamp: Optional[datetime] = None) -> None:
        """
        Update the current price and recalculate metrics.
        
        Args:
            price: New current price
            timestamp: Timestamp of the update (defaults to current time)
        """
        prev_price = self.current_price
        self.current_price = price
        self.updated_at = timestamp or datetime.utcnow()
        
        # Calculate unrealized P&L
        self.calculate_unrealized_pnl()
        
        # Track max drawdown
        if self.unrealized_pnl < 0:
            drawdown_pct = abs(self.unrealized_pnl) / (self.entry_price * self.quantity)
            self.max_drawdown = max(self.max_drawdown, drawdown_pct)
        
        # Check if stop loss or take profit has been triggered
        self._check_exits(prev_price, price)
        
        logger.debug(f"Updated price for {self.symbol} position: {price}, PnL: {self.unrealized_pnl}")
    
    def _check_exits(self, prev_price: float, current_price: float) -> None:
        """
        Check if any exit conditions have been triggered.
        
        Args:
            prev_price: Previous price before update
            current_price: New current price
        """
        if self.status != PositionStatus.OPEN:
            return
        
        # Check stop loss
        if self.stop_loss:
            if (self.side == PositionSide.LONG and current_price <= self.stop_loss) or \
               (self.side == PositionSide.SHORT and current_price >= self.stop_loss):
                self.status = PositionStatus.CLOSED
                self.closed_at = datetime.utcnow()
                logger.info(f"Stop loss triggered for {self.symbol} at {current_price}")
                return
        
        # Check take profit
        if self.take_profit:
            if (self.side == PositionSide.LONG and current_price >= self.take_profit) or \
               (self.side == PositionSide.SHORT and current_price <= self.take_profit):
                self.status = PositionStatus.CLOSED
                self.closed_at = datetime.utcnow()
                logger.info(f"Take profit triggered for {self.symbol} at {current_price}")
                return
        
        # Check trailing stop if set
        if self.trailing_stop and self.side == PositionSide.LONG and prev_price > current_price:
            # For long positions, trailing stop activates on price decrease
            trailing_level = current_price * (1 - self.trailing_stop)
            if current_price <= trailing_level:
                self.status = PositionStatus.CLOSED
                self.closed_at = datetime.utcnow()
                logger.info(f"Trailing stop triggered for {self.symbol} at {current_price}")
        elif self.trailing_stop and self.side == PositionSide.SHORT and prev_price < current_price:
            # For short positions, trailing stop activates on price increase
            trailing_level = current_price * (1 + self.trailing_stop)
            if current_price >= trailing_level:
                self.status = PositionStatus.CLOSED
                self.closed_at = datetime.utcnow()
                logger.info(f"Trailing stop triggered for {self.symbol} at {current_price}")
        
        # Check partial exit points
        for price_level, exit_percentage in self.partial_exit_points.items():
            if (self.side == PositionSide.LONG and prev_price < price_level <= current_price) or \
               (self.side == PositionSide.SHORT and prev_price > price_level >= current_price):
                # Partial exit triggered
                exit_quantity = self.quantity * (exit_percentage / 100)
                self._execute_partial_exit(price_level, exit_quantity)
                logger.info(f"Partial exit ({exit_percentage}%) triggered for {self.symbol} at {price_level}")
    
    def _execute_partial_exit(self, price: float, quantity: float) -> None:
        """
        Execute a partial exit at the given price and quantity.
        
        Args:
            price: Exit price
            quantity: Quantity to exit
        """
        if quantity >= self.quantity:
            # Full close if quantity equals or exceeds remaining
            self.close_position(price)
            return
        
        # Calculate realized P&L for this exit
        price_diff = price - self.entry_price if self.side == PositionSide.LONG else self.entry_price - price
        realized_pnl = price_diff * quantity
        
        # Update position
        self.realized_pnl += realized_pnl
        self.quantity -= quantity
        
        # Record the exit
        self.exit_orders.append({
            "timestamp": datetime.utcnow(),
            "price": price,
            "quantity": quantity,
            "pnl": realized_pnl,
            "type": "partial_exit"
        })
        
        logger.info(f"Executed partial exit: {quantity} {self.symbol} at {price}, PnL: {realized_pnl}")
    
    def close_position(self, exit_price: float, timestamp: Optional[datetime] = None) -> float:
        """
        Close the position and calculate final P&L.
        
        Args:
            exit_price: Exit price
            timestamp: Timestamp of the close (defaults to current time)
            
        Returns:
            Realized P&L from closing the position
        """
        if self.status == PositionStatus.CLOSED:
            logger.warning(f"Position {self.position_id} already closed")
            return 0.0
        
        # Calculate realized P&L
        price_diff = exit_price - self.entry_price if self.side == PositionSide.LONG else self.entry_price - exit_price
        realized_pnl = price_diff * self.quantity
        
        # Update position
        self.realized_pnl += realized_pnl
        self.current_price = exit_price
        self.status = PositionStatus.CLOSED
        self.closed_at = timestamp or datetime.utcnow()
        self.unrealized_pnl = 0.0
        
        # Record the exit
        self.exit_orders.append({
            "timestamp": self.closed_at,
            "price": exit_price,
            "quantity": self.quantity,
            "pnl": realized_pnl,
            "type": "full_exit"
        })
        
        logger.info(f"Closed position: {self.quantity} {self.symbol} at {exit_price}, PnL: {realized_pnl}")
        return realized_pnl
    
    def calculate_unrealized_pnl(self) -> float:
        """
        Calculate and update the unrealized P&L for the position.
        
        Returns:
            Current unrealized P&L
        """
        if self.status == PositionStatus.CLOSED:
            self.unrealized_pnl = 0.0
            return 0.0
        
        price_diff = self.current_price - self.entry_price if self.side == PositionSide.LONG else self.entry_price - self.current_price
        self.unrealized_pnl = price_diff * self.quantity
        return self.unrealized_pnl
    
    def update_stop_loss(self, price: float) -> None:
        """
        Update the stop loss price.
        
        Args:
            price: New stop loss price
        """
        # Validate stop loss makes sense for position direction
        if self.side == PositionSide.LONG and price >= self.entry_price:
            logger.warning(f"Invalid stop loss {price} for long position with entry {self.entry_price}")
            return
        if self.side == PositionSide.SHORT and price <= self.entry_price:
            logger.warning(f"Invalid stop loss {price} for short position with entry {self.entry_price}")
            return
        
        self.stop_loss = price
        logger.info(f"Updated stop loss for {self.symbol} to {price}")
    
    def update_take_profit(self, price: float) -> None:
        """
        Update the take profit price.
        
        Args:
            price: New take profit price
        """
        # Validate take profit makes sense for position direction
        if self.side == PositionSide.LONG and price <= self.entry_price:
            logger.warning(f"Invalid take profit {price} for long position with entry {self.entry_price}")
            return
        if self.side == PositionSide.SHORT and price >= self.entry_price:
            logger.warning(f"Invalid take profit {price} for short position with entry {self.entry_price}")
            return
        
        self.take_profit = price
        logger.info(f"Updated take profit for {self.symbol} to {price}")
    
    def set_trailing_stop(self, percentage: float) -> None:
        """
        Set a trailing stop loss as a percentage from the current price.
        
        Args:
            percentage: Trailing stop percentage (0.01 = 1%)
        """
        if percentage <= 0 or percentage >= 1:
            logger.warning(f"Invalid trailing stop percentage: {percentage}, must be between 0 and 1")
            return
        
        self.trailing_stop = percentage
        logger.info(f"Set trailing stop for {self.symbol} to {percentage * 100}%")
    
    def add_partial_exit(self, price: float, percentage: float) -> None:
        """
        Add a partial exit point at a specific price level.
        
        Args:
            price: Price level to trigger partial exit
            percentage: Percentage of position to exit (1-100)
        """
        if percentage <= 0 or percentage > 100:
            logger.warning(f"Invalid exit percentage: {percentage}, must be between 0 and 100")
            return
        
        # Validate price makes sense for position direction
        if self.side == PositionSide.LONG and price <= self.entry_price:
            logger.warning(f"Invalid partial exit price {price} for long position with entry {self.entry_price}")
            return
        if self.side == PositionSide.SHORT and price >= self.entry_price:
            logger.warning(f"Invalid partial exit price {price} for short position with entry {self.entry_price}")
            return
        
        self.partial_exit_points[price] = percentage
        logger.info(f"Added partial exit for {self.symbol}: {percentage}% at {price}")
    
    def get_risk_metrics(self) -> Dict[str, Any]:
        """
        Calculate risk metrics for the position.
        
        Returns:
            Dictionary of risk metrics
        """
        position_value = self.quantity * self.current_price
        
        # Calculate risk to stop loss if set
        risk_to_stop = 0.0
        if self.stop_loss:
            price_to_stop = abs(self.current_price - self.stop_loss)
            risk_to_stop = (price_to_stop / self.current_price) * position_value
        
        # Calculate reward to take profit if set
        reward_to_tp = 0.0
        if self.take_profit:
            price_to_tp = abs(self.current_price - self.take_profit)
            reward_to_tp = (price_to_tp / self.current_price) * position_value
        
        # Calculate risk-reward ratio
        risk_reward_ratio = reward_to_tp / risk_to_stop if risk_to_stop > 0 else 0.0
        
        return {
            "position_value": position_value,
            "entry_value": self.quantity * self.entry_price,
            "risk_to_stop": risk_to_stop,
            "reward_to_tp": reward_to_tp,
            "risk_reward_ratio": risk_reward_ratio,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": (self.unrealized_pnl / (self.entry_price * self.quantity)) if self.quantity > 0 else 0,
            "realized_pnl": self.realized_pnl,
            "max_drawdown": self.max_drawdown,
            "time_in_position": (datetime.utcnow() - self.created_at).total_seconds() / 3600  # hours
        } 

class PositionMonitor:
    """
    Position monitoring system for tracking multiple positions and managing risk.
    
    This class manages a collection of positions, updates them in real-time,
    calculates portfolio-level risk metrics, and implements risk controls.
    """
    
    def __init__(
        self, 
        max_portfolio_risk_percent: float = 5.0,
        max_asset_risk_percent: float = 2.0,
        max_correlated_risk_percent: float = 4.0,
        max_leverage: float = 10.0,
        position_reconciliation_interval: int = 300,  # 5 minutes
        use_circuit_breakers: bool = True,
        circuit_breaker_levels: Optional[Dict[str, float]] = None,
        position_db_client = None
    ):
        """
        Initialize the position monitor.
        
        Args:
            max_portfolio_risk_percent: Maximum portfolio-wide risk percentage
            max_asset_risk_percent: Maximum risk percentage for a single asset
            max_correlated_risk_percent: Maximum risk for correlated assets
            max_leverage: Maximum allowed leverage
            position_reconciliation_interval: Seconds between position reconciliations
            use_circuit_breakers: Whether to use circuit breakers
            circuit_breaker_levels: Custom circuit breaker levels
            position_db_client: Database client for position storage
        """
        # Initialize position storage
        self.positions: Dict[str, Position] = {}
        self.positions_by_symbol: Dict[str, List[Position]] = {}
        self.position_db_client = position_db_client
        
        # Risk limits
        self.max_portfolio_risk_percent = max_portfolio_risk_percent
        self.max_asset_risk_percent = max_asset_risk_percent
        self.max_correlated_risk_percent = max_correlated_risk_percent
        self.max_leverage = max_leverage
        
        # Reconciliation settings
        self.position_reconciliation_interval = position_reconciliation_interval
        self.last_reconciliation_time = 0
        
        # Circuit breaker settings
        self.use_circuit_breakers = use_circuit_breakers
        self.circuit_breaker_levels = circuit_breaker_levels or {
            "l1_volatility_multiple": 1.5,  # Level 1: Reduce sizes when volatility is 1.5x normal
            "l2_volatility_multiple": 2.5,  # Level 2: Pause new entries at 2.5x volatility
            "l3_volatility_multiple": 4.0,  # Level 3: Close positions at 4.0x volatility
            "correlation_deviation_threshold": 3.0  # Significant correlation shift (std devs)
        }
        self.circuit_breaker_status = {
            "level": 0,  # 0=normal, 1-3=breaker levels
            "triggered_at": None,
            "reason": None,
            "affected_symbols": []
        }
        
        # Volatility tracking
        self.normal_volatility: Dict[str, float] = {}
        self.current_volatility: Dict[str, float] = {}
        
        # Correlation tracking
        self.normal_correlations: Dict[str, Dict[str, float]] = {}
        self.current_correlations: Dict[str, Dict[str, float]] = {}
        
        # Alerts storage
        self.alerts: List[Dict[str, Any]] = []
        
        logger.info("Initialized position monitoring system")
    
    async def add_position(self, position: Position) -> bool:
        """
        Add a position to the monitoring system.
        
        Args:
            position: Position object to add
            
        Returns:
            True if position was added successfully
        """
        # Check if we already have this position
        if position.position_id in self.positions:
            logger.warning(f"Position {position.position_id} already exists")
            return False
        
        # Validate position against risk limits
        if not self._validate_position_risk(position):
            logger.warning(f"Position {position.position_id} exceeds risk limits")
            return False
        
        # Add to internal storage
        self.positions[position.position_id] = position
        
        # Add to symbol lookup
        if position.symbol not in self.positions_by_symbol:
            self.positions_by_symbol[position.symbol] = []
        self.positions_by_symbol[position.symbol].append(position)
        
        # Persist to database if client available
        if self.position_db_client:
            try:
                await self.position_db_client.save_position(position.dict())
                logger.debug(f"Persisted position {position.position_id} to database")
            except Exception as e:
                logger.error(f"Failed to persist position {position.position_id}: {str(e)}")
        
        logger.info(f"Added position {position.position_id} ({position.symbol}) to monitoring")
        return True
    
    def _validate_position_risk(self, position: Position) -> bool:
        """
        Validate a position against risk limits.
        
        Args:
            position: Position to validate
            
        Returns:
            True if position is within risk limits
        """
        # Check leverage limit
        if position.leverage > self.max_leverage:
            logger.warning(f"Position {position.symbol} exceeds leverage limit: {position.leverage} > {self.max_leverage}")
            return False
        
        # Skip further checks if position has no stop loss
        if not position.stop_loss:
            logger.warning(f"Position {position.symbol} has no stop loss set")
            return True
        
        # Calculate position risk
        risk_metrics = position.get_risk_metrics()
        position_risk_percent = (risk_metrics["risk_to_stop"] / self._get_portfolio_value()) * 100
        
        # Check single position risk limit
        if position_risk_percent > self.max_asset_risk_percent:
            logger.warning(f"Position {position.symbol} exceeds asset risk limit: {position_risk_percent:.2f}% > {self.max_asset_risk_percent:.2f}%")
            return False
        
        # Check portfolio-wide risk limit
        current_portfolio_risk = self._calculate_portfolio_risk_percent()
        if current_portfolio_risk + position_risk_percent > self.max_portfolio_risk_percent:
            logger.warning(f"Position {position.symbol} would exceed portfolio risk limit: {current_portfolio_risk:.2f}% + {position_risk_percent:.2f}% > {self.max_portfolio_risk_percent:.2f}%")
            return False
        
        # Check correlated asset risk
        correlated_symbols = self._get_correlated_symbols(position.symbol)
        correlated_risk = sum(
            self._calculate_symbol_risk_percent(symbol)
            for symbol in correlated_symbols
        )
        if correlated_risk + position_risk_percent > self.max_correlated_risk_percent:
            logger.warning(f"Position {position.symbol} would exceed correlated risk limit: {correlated_risk:.2f}% + {position_risk_percent:.2f}% > {self.max_correlated_risk_percent:.2f}%")
            return False
        
        return True
    
    def _get_correlated_symbols(self, symbol: str) -> List[str]:
        """
        Get symbols correlated with the given symbol.
        
        Args:
            symbol: Symbol to check correlations for
            
        Returns:
            List of correlated symbols
        """
        # Simple implementation - in a real system, this would use a correlation matrix
        # For now, assume pairs with same base or quote currency are correlated
        correlated = []
        
        if "/" in symbol:
            base, quote = symbol.split("/")
            
            for other_symbol in self.positions_by_symbol:
                if other_symbol == symbol:
                    continue
                    
                if "/" in other_symbol:
                    other_base, other_quote = other_symbol.split("/")
                    if base == other_base or quote == other_quote:
                        correlated.append(other_symbol)
        
        return correlated
    
    def _calculate_symbol_risk_percent(self, symbol: str) -> float:
        """
        Calculate the risk percentage for a symbol.
        
        Args:
            symbol: Symbol to calculate risk for
            
        Returns:
            Risk percentage for the symbol
        """
        if symbol not in self.positions_by_symbol:
            return 0.0
        
        portfolio_value = self._get_portfolio_value()
        if portfolio_value == 0.0:
            return 0.0
        
        total_risk = sum(
            position.get_risk_metrics()["risk_to_stop"]
            for position in self.positions_by_symbol[symbol]
            if position.status == PositionStatus.OPEN
        )
        
        return (total_risk / portfolio_value) * 100
    
    def _calculate_portfolio_risk_percent(self) -> float:
        """
        Calculate the total portfolio risk percentage.
        
        Returns:
            Portfolio risk percentage
        """
        portfolio_value = self._get_portfolio_value()
        if portfolio_value == 0.0:
            return 0.0
        
        total_risk = sum(
            position.get_risk_metrics()["risk_to_stop"]
            for position in self.positions.values()
            if position.status == PositionStatus.OPEN and position.stop_loss is not None
        )
        
        return (total_risk / portfolio_value) * 100
    
    def _get_portfolio_value(self) -> float:
        """
        Calculate the total portfolio value.
        
        Returns:
            Total portfolio value
        """
        return sum(
            position.quantity * position.current_price
            for position in self.positions.values()
            if position.status == PositionStatus.OPEN
        )
    
    async def update_prices(self, symbol: str, price: float, timestamp: Optional[datetime] = None) -> None:
        """
        Update prices for all positions of a given symbol.
        
        Args:
            symbol: Symbol to update
            price: New price
            timestamp: Timestamp of the update
        """
        if symbol not in self.positions_by_symbol:
            return
        
        for position in self.positions_by_symbol[symbol]:
            if position.status == PositionStatus.OPEN:
                position.update_price(price, timestamp)
                
                # Persist updated position to database if client available
                if self.position_db_client:
                    try:
                        await self.position_db_client.update_position(position.dict())
                    except Exception as e:
                        logger.error(f"Failed to update position {position.position_id} in database: {str(e)}")
    
    async def handle_trade_update(self, trade_data: Dict[str, Any]) -> None:
        """
        Handle a trade update from the WebSocket stream.
        
        Args:
            trade_data: Trade data from WebSocket
        """
        symbol = trade_data.get("symbol")
        price = trade_data.get("price")
        
        if not symbol or not price:
            logger.warning("Received trade update with missing symbol or price")
            return
        
        # Update prices for affected positions
        await self.update_prices(symbol, price)
        
        # Update volatility metrics
        self._update_volatility(symbol, price)
        
        # Check circuit breakers
        if self.use_circuit_breakers:
            await self._check_circuit_breakers()
    
    def _update_volatility(self, symbol: str, price: float) -> None:
        """
        Update volatility metrics for a symbol.
        
        Args:
            symbol: Symbol to update
            price: Current price
        """
        # This is a simplified implementation - a real system would use
        # a proper volatility calculation (e.g., standard deviation of returns)
        # For now, we'll just store the price
        
        # In a real implementation, this would collect price data points
        # and calculate rolling volatility metrics
        pass
    
    async def _check_circuit_breakers(self) -> None:
        """
        Check if any circuit breakers should be triggered.
        
        A real implementation would have more sophisticated circuit breaker logic
        based on volatility spikes, correlation breakdowns, etc.
        """
        # This is a simplified implementation - a real system would have
        # more sophisticated circuit breaker triggers
        
        # In this simplified version, we won't actually implement circuit breaker checks,
        # but a real system would:
        # 1. Compare current volatility to historical volatility for each symbol
        # 2. Check for correlation breakdowns between related symbols
        # 3. Monitor liquidity conditions
        # 4. Trigger appropriate circuit breaker levels
        pass
    
    async def reconcile_positions(self, exchange_positions: List[Dict[str, Any]]) -> None:
        """
        Reconcile internal position tracking with exchange positions.
        
        Args:
            exchange_positions: Positions from exchange API
        """
        logger.info("Starting position reconciliation")
        
        # Skip if we've reconciled recently
        current_time = time.time()
        if current_time - self.last_reconciliation_time < self.position_reconciliation_interval:
            logger.debug("Skipping reconciliation, last one was too recent")
            return
        
        self.last_reconciliation_time = current_time
        
        # Track which positions were found on the exchange
        found_position_ids = set()
        
        # Update existing positions and add new ones
        for exchange_position in exchange_positions:
            symbol = exchange_position.get("symbol")
            position_id = exchange_position.get("position_id")
            
            if not symbol or not position_id:
                logger.warning(f"Skipping exchange position with missing symbol or ID: {exchange_position}")
                continue
            
            # If we already know this position, update it
            if position_id in self.positions:
                # Mark as found
                found_position_ids.add(position_id)
                
                # Update position details (simplified - real implementation would be more detailed)
                position = self.positions[position_id]
                
                # Update price and quantity if different
                if "current_price" in exchange_position and exchange_position["current_price"] != position.current_price:
                    position.update_price(exchange_position["current_price"])
                
                if "quantity" in exchange_position and exchange_position["quantity"] != position.quantity:
                    # This is a simplified update - real implementation would handle partial fills
                    position.quantity = exchange_position["quantity"]
                    logger.info(f"Updated position {position_id} quantity to {position.quantity}")
            else:
                # This is a new position we're not tracking - create it
                try:
                    # Convert exchange position format to our Position model
                    # This is a simplified conversion - real implementation would be more detailed
                    new_position = Position(
                        position_id=position_id,
                        symbol=symbol,
                        side=exchange_position.get("side"),
                        entry_price=exchange_position.get("entry_price"),
                        current_price=exchange_position.get("current_price"),
                        quantity=exchange_position.get("quantity"),
                        leverage=exchange_position.get("leverage", 1.0),
                        status=exchange_position.get("status", PositionStatus.OPEN),
                        stop_loss=exchange_position.get("stop_loss"),
                        take_profit=exchange_position.get("take_profit")
                    )
                    
                    # Add to our tracking
                    await self.add_position(new_position)
                    found_position_ids.add(position_id)
                except Exception as e:
                    logger.error(f"Failed to create position from exchange data: {str(e)}")
        
        # Check for positions we're tracking that no longer exist on exchange
        for position_id, position in list(self.positions.items()):
            if position.status == PositionStatus.OPEN and position_id not in found_position_ids:
                logger.warning(f"Position {position_id} not found on exchange, marking as closed")
                position.status = PositionStatus.CLOSED
                position.closed_at = datetime.utcnow()
                
                # Persist to database if client available
                if self.position_db_client:
                    try:
                        await self.position_db_client.update_position(position.dict())
                    except Exception as e:
                        logger.error(f"Failed to update position {position_id} in database: {str(e)}")
        
        logger.info("Completed position reconciliation")
    
    async def rebalance_portfolio(self) -> None:
        """
        Rebalance the portfolio based on current risk parameters.
        
        This would include:
        1. Checking if overall portfolio risk is within limits
        2. Adjusting position sizes if needed
        3. Checking for overexposure to correlated assets
        """
        # This is a placeholder - a real implementation would include
        # portfolio rebalancing logic based on risk parameters
        logger.info("Portfolio rebalancing not implemented")
    
    def get_portfolio_risk_metrics(self) -> Dict[str, Any]:
        """
        Calculate comprehensive risk metrics for the portfolio.
        
        Returns:
            Dictionary of risk metrics
        """
        # Calculate basic metrics
        open_positions = [p for p in self.positions.values() if p.status == PositionStatus.OPEN]
        total_positions = len(open_positions)
        portfolio_value = self._get_portfolio_value()
        
        # Calculate P&L
        total_unrealized_pnl = sum(p.unrealized_pnl for p in open_positions)
        total_realized_pnl = sum(p.realized_pnl for p in self.positions.values())
        total_pnl = total_unrealized_pnl + total_realized_pnl
        
        # Calculate exposure by symbol
        exposure_by_symbol = {}
        for symbol, positions in self.positions_by_symbol.items():
            active_positions = [p for p in positions if p.status == PositionStatus.OPEN]
            if active_positions:
                long_positions = [p for p in active_positions if p.side == PositionSide.LONG]
                short_positions = [p for p in active_positions if p.side == PositionSide.SHORT]
                
                long_exposure = sum(p.quantity * p.current_price for p in long_positions)
                short_exposure = sum(p.quantity * p.current_price for p in short_positions)
                net_exposure = long_exposure - short_exposure
                
                exposure_by_symbol[symbol] = {
                    "long": long_exposure,
                    "short": short_exposure,
                    "net": net_exposure,
                    "percentage": (net_exposure / portfolio_value * 100) if portfolio_value > 0 else 0
                }
        
        # Calculate risk metrics
        total_risk_amount = sum(
            p.get_risk_metrics()["risk_to_stop"] for p in open_positions if p.stop_loss is not None
        )
        total_risk_percent = (total_risk_amount / portfolio_value * 100) if portfolio_value > 0 else 0
        
        # Calculate max drawdown
        max_drawdown = max([p.max_drawdown for p in self.positions.values()], default=0.0)
        
        return {
            "total_positions": total_positions,
            "portfolio_value": portfolio_value,
            "total_unrealized_pnl": total_unrealized_pnl,
            "total_realized_pnl": total_realized_pnl,
            "total_pnl": total_pnl,
            "exposure_by_symbol": exposure_by_symbol,
            "total_risk_amount": total_risk_amount,
            "total_risk_percent": total_risk_percent,
            "max_drawdown": max_drawdown,
            "circuit_breaker_status": self.circuit_breaker_status,
            "alerts": self.alerts[-10:]  # Last 10 alerts
        } 