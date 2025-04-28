"""
Shutdown Module - Handles graceful shutdown of the Forex Trading Bot

This module ensures that all components of the trading system are properly
shut down when the application exits, including closing open positions,
terminating trading agents, and cleaning up resources.
"""

from .coordinator import (
    ShutdownCoordinator, 
    ShutdownPhase, 
    get_shutdown_coordinator,
    setup_signal_handlers
)
from .position_closer import PositionCloser, PositionCloseStrategy, Position
from .agent_terminator import AgentTerminator, Agent
from .resource_cleaner import ResourceCleaner, ResourceType, Resource

# Expose the main functionality at the module level
shutdown = get_shutdown_coordinator().shutdown
emergency_shutdown = get_shutdown_coordinator().emergency_shutdown

__all__ = [
    # Main functions
    "shutdown",
    "emergency_shutdown",
    "setup_signal_handlers",
    
    # Classes
    "ShutdownCoordinator",
    "ShutdownPhase", 
    "PositionCloser", 
    "PositionCloseStrategy",
    "Position",
    "AgentTerminator",
    "Agent",
    "ResourceCleaner",
    "ResourceType",
    "Resource",
    
    # Factory functions
    "get_shutdown_coordinator",
] 