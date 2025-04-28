"""
Portfolio Model Module

This module contains the portfolio and position classes for tracking
trading activity during backtesting.
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Union, Set

import pandas as pd
import numpy as np

# Configure logger
logger = logging.getLogger(__name__)


class Position:
    """
    Represents a trading position in a specific symbol.
    """
    
    def __init__(
        self,
        symbol: str,
        initial_quantity: float = 0.0,
        initial_price: float = 0.0,
        current_price: float = 0.0,
        timestamp: Optional[pd.Timestamp] = None
    ):
        """
        Initialize a position.
        
        Args:
            symbol: Symbol string
            initial_quantity: Initial position quantity
            initial_price: Initial position price
            current_price: Current market price
            timestamp: Timestamp when position was created
        """
        self.symbol = symbol
        self.quantity = initial_quantity
        self.initial_price = initial_price
        self.current_price = current_price or initial_price
        self.timestamp = timestamp or pd.Timestamp.now()
        
        # Position tracking
        self.cost_basis = initial_quantity * initial_price
        self.realized_pnl = 0.0
        self.trades = []
        
        # Performance tracking
        self.high_value = self.market_value
        self.low_value = self.market_value
    
    @property
    def market_value(self) -> float:
        """Calculate current market value of the position."""
        return self.quantity * self.current_price
    
    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized profit/loss."""
        if self.quantity == 0:
            return 0.0
        return self.market_value - self.cost_basis
    
    @property
    def unrealized_pnl_pct(self) -> float:
        """Calculate unrealized profit/loss as a percentage."""
        if self.cost_basis == 0:
            return 0.0
        return self.unrealized_pnl / abs(self.cost_basis)
    
    @property
    def total_pnl(self) -> float:
        """Calculate total profit/loss (realized + unrealized)."""
        return self.realized_pnl + self.unrealized_pnl
    
    def update_price(self, price: float, timestamp: pd.Timestamp = None) -> None:
        """
        Update the current price of the position.
        
        Args:
            price: New price
            timestamp: Timestamp of the update
        """
        self.current_price = price
        
        # Update high and low values
        self.high_value = max(self.high_value, self.market_value)
        self.low_value = min(self.low_value, self.market_value)
    
    def add(
        self,
        quantity: float,
        price: float,
        timestamp: pd.Timestamp = None,
        commission: float = 0.0
    ) -> float:
        """
        Add to the position.
        
        Args:
            quantity: Quantity to add (positive for buy, negative for sell)
            price: Execution price
            timestamp: Timestamp of the trade
            commission: Commission paid
            
        Returns:
            Realized profit/loss from the trade
        """
        timestamp = timestamp or pd.Timestamp.now()
        
        # Calculate absolute quantity
        abs_quantity = abs(quantity)
        
        # Calculate trade value
        trade_value = abs_quantity * price
        
        # Record trade
        self.trades.append({
            'timestamp': timestamp,
            'quantity': quantity,
            'price': price,
            'value': trade_value,
            'commission': commission
        })
        
        # Update position based on whether we're adding or reducing
        realized_pnl = 0.0
        
        if self.quantity * quantity > 0 or self.quantity == 0:
            # Adding to position (same direction or new position)
            old_value = self.cost_basis
            self.quantity += quantity
            self.cost_basis += quantity * price
            
            # If we're opening a new position, set initial price
            if old_value == 0:
                self.initial_price = price
                self.timestamp = timestamp
        else:
            # Reducing or closing position (opposite direction)
            if abs_quantity <= abs(self.quantity):
                # Partial close
                close_ratio = abs_quantity / abs(self.quantity)
                realized_pnl = (price - self.initial_price) * quantity
                
                # Update cost basis and quantity
                self.cost_basis += quantity * price
                self.quantity += quantity
            else:
                # Full close and reverse
                realized_pnl = (price - self.initial_price) * -self.quantity
                
                # Calculate remaining quantity after closing
                remaining_quantity = quantity + self.quantity
                
                # Reset position with new direction
                self.initial_price = price
                self.timestamp = timestamp
                self.quantity = remaining_quantity
                self.cost_basis = remaining_quantity * price
        
        # Update realized P&L
        self.realized_pnl += realized_pnl - commission
        
        # Update price
        self.update_price(price, timestamp)
        
        return realized_pnl - commission


class Portfolio:
    """
    Represents a trading portfolio with multiple positions.
    """
    
    def __init__(self, initial_capital: float = 100000.0):
        """
        Initialize a portfolio.
        
        Args:
            initial_capital: Initial capital
        """
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        
        # Performance tracking
        self.starting_value = initial_capital
        self.current_value = initial_capital
        self.high_value = initial_capital
        self.low_value = initial_capital
        self.last_value = initial_capital
        
        # Transaction history
        self.transactions = []
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get a position by symbol.
        
        Args:
            symbol: Symbol string
            
        Returns:
            Position object or None if not found
        """
        return self.positions.get(symbol)
    
    def update_price(
        self, 
        symbol: str, 
        price: float, 
        timestamp: pd.Timestamp = None
    ) -> None:
        """
        Update the price of a position.
        
        Args:
            symbol: Symbol string
            price: New price
            timestamp: Timestamp of the update
        """
        position = self.get_position(symbol)
        if position:
            position.update_price(price, timestamp)
        else:
            # Create a new position with zero quantity
            self.positions[symbol] = Position(
                symbol=symbol,
                initial_quantity=0.0,
                initial_price=price,
                current_price=price,
                timestamp=timestamp
            )
        
        # Update portfolio value
        self.update_value(timestamp)
    
    def update_value(self, timestamp: pd.Timestamp = None) -> float:
        """
        Update the portfolio value.
        
        Args:
            timestamp: Timestamp of the update
            
        Returns:
            Updated portfolio value
        """
        timestamp = timestamp or pd.Timestamp.now()
        
        # Calculate portfolio value (cash + positions)
        position_value = sum(position.market_value for position in self.positions.values())
        self.current_value = self.cash + position_value
        
        # Update high and low values
        self.high_value = max(self.high_value, self.current_value)
        self.low_value = min(self.low_value, self.current_value)
        
        return self.current_value
    
    def execute_trade(
        self,
        symbol: str,
        quantity: float,
        price: float,
        timestamp: pd.Timestamp = None,
        commission: float = 0.0
    ) -> float:
        """
        Execute a trade.
        
        Args:
            symbol: Symbol string
            quantity: Quantity to trade (positive for buy, negative for sell)
            price: Execution price
            timestamp: Timestamp of the trade
            commission: Commission paid
            
        Returns:
            Realized profit/loss from the trade
        """
        timestamp = timestamp or pd.Timestamp.now()
        
        # Check if we have enough cash for a buy
        trade_value = abs(quantity) * price
        trade_cost = trade_value + commission
        
        if quantity > 0 and trade_cost > self.cash:
            logger.warning(
                f"Insufficient cash for trade: {trade_cost:.2f} > {self.cash:.2f}. "
                f"Adjusting quantity."
            )
            # Adjust quantity to match available cash
            quantity = (self.cash - commission) / price
            quantity = max(0, quantity)  # Ensure non-negative
            
            if quantity <= 0:
                logger.warning("Cannot execute trade with zero quantity")
                return 0.0
            
            # Recalculate trade value
            trade_value = quantity * price
            trade_cost = trade_value + commission
        
        # Get or create position
        position = self.get_position(symbol)
        if not position:
            position = Position(
                symbol=symbol,
                initial_quantity=0.0,
                initial_price=price,
                current_price=price,
                timestamp=timestamp
            )
            self.positions[symbol] = position
        
        # Execute trade
        realized_pnl = position.add(quantity, price, timestamp, commission)
        
        # Update cash
        if quantity > 0:
            # Buy - decrease cash
            self.cash -= trade_cost
        else:
            # Sell - increase cash
            self.cash += trade_value - commission
        
        # Record transaction
        self.transactions.append({
            'timestamp': timestamp,
            'symbol': symbol,
            'quantity': quantity,
            'price': price,
            'value': trade_value,
            'commission': commission,
            'realized_pnl': realized_pnl,
            'cash': self.cash
        })
        
        # Remove position if quantity is zero
        if position.quantity == 0:
            del self.positions[symbol]
        
        # Update portfolio value
        self.update_value(timestamp)
        
        return realized_pnl
    
    def get_daily_return(self) -> float:
        """
        Calculate the daily return.
        
        Returns:
            Daily return as a decimal
        """
        if self.last_value == 0:
            return 0.0
        
        daily_return = (self.current_value / self.last_value) - 1
        self.last_value = self.current_value
        
        return daily_return
    
    def get_total_return(self) -> float:
        """
        Calculate the total return since inception.
        
        Returns:
            Total return as a decimal
        """
        if self.initial_capital == 0:
            return 0.0
        
        return (self.current_value / self.initial_capital) - 1
    
    def get_equity_value(self) -> float:
        """
        Calculate the total equity value (excluding cash).
        
        Returns:
            Equity value
        """
        return sum(position.market_value for position in self.positions.values())
    
    def get_exposure(self) -> float:
        """
        Calculate the exposure ratio (equity value / portfolio value).
        
        Returns:
            Exposure ratio
        """
        if self.current_value == 0:
            return 0.0
        
        return self.get_equity_value() / self.current_value
    
    def get_exposure_by_asset(self) -> Dict[str, float]:
        """
        Calculate exposure by asset.
        
        Returns:
            Dictionary mapping symbols to exposure ratios
        """
        exposures = {}
        
        if self.current_value == 0:
            return exposures
        
        for symbol, position in self.positions.items():
            exposures[symbol] = position.market_value / self.current_value
        
        return exposures
    
    def reset(self, capital: Optional[float] = None) -> None:
        """
        Reset the portfolio to initial state.
        
        Args:
            capital: Optional new initial capital
        """
        self.initial_capital = capital if capital is not None else self.initial_capital
        self.cash = self.initial_capital
        self.positions = {}
        
        # Reset performance tracking
        self.starting_value = self.initial_capital
        self.current_value = self.initial_capital
        self.high_value = self.initial_capital
        self.low_value = self.initial_capital
        self.last_value = self.initial_capital
        
        # Clear transaction history
        self.transactions = []
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the portfolio.
        
        Returns:
            Dictionary with portfolio summary
        """
        position_summaries = []
        
        for symbol, position in self.positions.items():
            position_summaries.append({
                'symbol': symbol,
                'quantity': position.quantity,
                'market_value': position.market_value,
                'cost_basis': position.cost_basis,
                'unrealized_pnl': position.unrealized_pnl,
                'unrealized_pnl_pct': position.unrealized_pnl_pct
            })
        
        return {
            'cash': self.cash,
            'equity': self.get_equity_value(),
            'total_value': self.current_value,
            'total_return': self.get_total_return(),
            'exposure': self.get_exposure(),
            'positions': position_summaries
        }
    
    def get_holdings(self) -> Dict[str, float]:
        """
        Get current holdings as quantities.
        
        Returns:
            Dictionary mapping symbols to quantities
        """
        return {
            symbol: position.quantity
            for symbol, position in self.positions.items()
        }
    
    def get_weights(self) -> Dict[str, float]:
        """
        Get current portfolio weights.
        
        Returns:
            Dictionary mapping symbols to weights
        """
        weights = {}
        
        if self.current_value == 0:
            return weights
        
        # Add positions
        for symbol, position in self.positions.items():
            weights[symbol] = position.market_value / self.current_value
        
        # Add cash
        weights['cash'] = self.cash / self.current_value
        
        return weights 