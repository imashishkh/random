"""
Unit of Work implementation for trade analytics operations.

This module provides a specialized Unit of Work for working with trade analytics
repositories in a consistent transaction context.
"""

import logging
from typing import Dict, Any, Optional

from .unit_of_work import DatabaseUnitOfWork
from .repositories.trade_fill_repository import TradeFillRepository
from .repositories.position_repository import PositionRepository
from .repositories.agent_state_repository import AgentStateRepository 
from .repositories.risk_alert_repository import RiskAlertRepository
from .repositories.symbol_repository import SymbolRepository

logger = logging.getLogger(__name__)


class TradeAnalyticsUnitOfWork(DatabaseUnitOfWork):
    """
    Unit of Work implementation for trade analytics operations.
    
    This class coordinates repository operations for trade analytics, ensuring
    that operations across repositories (like creating a position and associating
    trade fills) happen within a single transaction.
    """
    
    def __init__(self):
        """Initialize with trade analytics repositories."""
        # Create repositories
        repositories = {
            'trade_fills': TradeFillRepository(),
            'positions': PositionRepository(),
            'agent_states': AgentStateRepository(),
            'risk_alerts': RiskAlertRepository(),
            'symbols': SymbolRepository()
        }
        
        super().__init__(repositories)
    
    @property
    def trade_fills(self) -> TradeFillRepository:
        """Get the trade fills repository."""
        return self.repositories['trade_fills']
    
    @property
    def positions(self) -> PositionRepository:
        """Get the positions repository."""
        return self.repositories['positions']
    
    @property
    def agent_states(self) -> AgentStateRepository:
        """Get the agent states repository."""
        return self.repositories['agent_states']
    
    @property
    def risk_alerts(self) -> RiskAlertRepository:
        """Get the risk alerts repository."""
        return self.repositories['risk_alerts']
    
    @property
    def symbols(self) -> SymbolRepository:
        """Get the symbols repository."""
        return self.repositories['symbols'] 