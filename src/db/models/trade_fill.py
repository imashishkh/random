"""
TradeFill entity model for trade fill data.

This model represents a trade execution in the system and maps to the trade_fills table
in the database.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from decimal import Decimal


@dataclass
class TradeFill:
    """
    TradeFill entity representing a single trade execution.
    
    Maps to the trade_fills table in the database.
    """
    # Exchange-provided trade ID
    trade_id: str
    
    # Trading pair (e.g., "BTCUSDT")
    symbol: str
    
    # Execution price
    price: Decimal
    
    # Executed quantity
    quantity: Decimal
    
    # Trade side ('BUY' or 'SELL')
    side: str
    
    # Execution timestamp
    executed_at: datetime
    
    # Fee amount
    fee: Decimal
    
    # Fee currency
    fee_asset: str
    
    # Exchange-provided order ID
    order_id: str
    
    # Reference to agent
    agent_id: str
    
    # Primary key
    id: Optional[int] = None
    
    # Reference to position (can be NULL initially)
    position_id: Optional[int] = None
    
    # Creation timestamp
    created_at: Optional[datetime] = None
    
    @property
    def trade_value(self) -> Decimal:
        """Calculate the notional value of this trade fill."""
        return self.price * self.quantity
    
    @property
    def net_value(self) -> Decimal:
        """Calculate the net value after fees."""
        return self.trade_value - self.fee 