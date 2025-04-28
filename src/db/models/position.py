"""
Position entity model for position data.

This model represents a trading position in the system and maps to the positions table
in the database.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal


@dataclass
class Position:
    """
    Position entity representing a trading position.
    
    Maps to the positions table in the database.
    """
    # Trading pair (e.g., "BTCUSDT")
    symbol: str
    
    # Position size
    quantity: Decimal
    
    # Entry price
    entry_price: Decimal
    
    # Current market price
    current_price: Decimal
    
    # Reference to agent
    agent_id: str
    
    # Primary key
    id: Optional[int] = None
    
    # Unrealized profit/loss
    unrealized_pnl: Decimal = Decimal('0')
    
    # Realized profit/loss (for closed positions)
    realized_pnl: Decimal = Decimal('0')
    
    # Position status ('OPEN', 'CLOSED')
    status: str = 'OPEN'
    
    # Opening timestamp
    opened_at: Optional[datetime] = None
    
    # Closing timestamp
    closed_at: Optional[datetime] = None
    
    # Creation timestamp
    created_at: Optional[datetime] = None
    
    # Last update timestamp
    updated_at: Optional[datetime] = None
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def position_value(self) -> Decimal:
        """Calculate the current notional value of the position."""
        return self.quantity * self.current_price
    
    @property
    def is_open(self) -> bool:
        """Check if the position is open."""
        return self.status == 'OPEN'
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate the duration of the position in seconds."""
        if not self.opened_at:
            return None
            
        end_time = self.closed_at if self.closed_at else datetime.now()
        return (end_time - self.opened_at).total_seconds()
    
    @property
    def pnl(self) -> Decimal:
        """Get the appropriate PnL value based on position status."""
        return self.unrealized_pnl if self.is_open else self.realized_pnl
    
    @property
    def pnl_percentage(self) -> Decimal:
        """Calculate the PnL as a percentage of the initial position value."""
        initial_value = self.quantity * self.entry_price
        if initial_value == 0:
            return Decimal('0')
            
        return (self.pnl / initial_value) * Decimal('100')
    
    def update_unrealized_pnl(self) -> None:
        """Recalculate the unrealized PnL based on current price."""
        if self.is_open:
            self.unrealized_pnl = (self.current_price - self.entry_price) * self.quantity 