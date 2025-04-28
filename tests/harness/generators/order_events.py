"""
Order Event Models

This module defines data classes for order lifecycle events like cancellations and modifications.
These are used by the burst order scenario generators to simulate realistic order behaviors.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .base import OrderData


@dataclass
class OrderCancellation:
    """Order cancellation event."""
    order_id: str
    symbol: str
    timestamp: datetime
    original_order: OrderData
    cancellation_id: str = None
    
    def __post_init__(self):
        if self.cancellation_id is None:
            self.cancellation_id = str(uuid.uuid4())


@dataclass
class OrderModification:
    """Order modification event."""
    order_id: str
    symbol: str
    timestamp: datetime
    original_order: OrderData
    new_price: Optional[float] = None
    new_size: Optional[float] = None
    modification_id: str = None
    
    def __post_init__(self):
        if self.modification_id is None:
            self.modification_id = str(uuid.uuid4()) 