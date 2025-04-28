"""
Core system model definitions.

This module contains the core model classes and enums used throughout 
the Forex Trading Bot system, specifically for system-wide operations
like shutdown management.
"""

from enum import Enum, auto
from typing import Dict, Any, List, Optional

class ShutdownPhase(Enum):
    """
    Phases of the system shutdown process.
    
    The shutdown process occurs in the following sequence:
    1. PENDING - Initial state, not yet started
    2. POSITIONS - Closing trading positions 
    3. SERVICES - Stopping services (API, workers, etc.)
    4. CONNECTIONS - Closing connections (databases, message queues, etc.)
    5. RESOURCES - Releasing resources (memory, file handles, etc.)
    6. COMPLETE - Shutdown process has completed
    7. FAILED - Shutdown process has failed
    """
    PENDING = auto()
    POSITIONS = auto()
    SERVICES = auto()
    CONNECTIONS = auto()
    RESOURCES = auto()
    COMPLETE = auto()
    FAILED = auto()
    
    def __str__(self) -> str:
        """Return the phase name in title case for display."""
        return self.name.title()

class PositionCloseStrategy(Enum):
    """
    Strategy for closing positions during shutdown.
    
    - GRACEFUL: Wait for positions to close at good price levels with timeout
    - IMMEDIATE: Close positions at market price immediately
    - KEEP_OPEN: Don't close positions, just record their state
    """
    GRACEFUL = auto()
    IMMEDIATE = auto()
    KEEP_OPEN = auto()
    
    def __str__(self) -> str:
        """Return the strategy name in title case for display."""
        return self.name.replace('_', ' ').title()

class ShutdownStatus:
    """
    Represents the current status of the shutdown process.
    
    This class encapsulates all information about the current state
    of the shutdown process, including the phase, time elapsed,
    the reason for shutdown, and any results from phase execution.
    """
    
    def __init__(self, phase: ShutdownPhase = ShutdownPhase.PENDING,
                 elapsed_seconds: float = 0.0, 
                 reason: str = "User initiated",
                 phase_results: Dict[ShutdownPhase, Any] = None):
        """
        Initialize a new shutdown status object.
        
        Args:
            phase: Current shutdown phase
            elapsed_seconds: Time elapsed since shutdown started
            reason: Reason for shutdown
            phase_results: Results from each completed phase
        """
        self.phase = phase
        self.elapsed_seconds = elapsed_seconds
        self.reason = reason
        self.phase_results = phase_results or {}
    
    @property
    def is_complete(self) -> bool:
        """Return True if shutdown is complete."""
        return self.phase == ShutdownPhase.COMPLETE
    
    @property
    def is_failed(self) -> bool:
        """Return True if shutdown has failed."""
        return self.phase == ShutdownPhase.FAILED
    
    @property
    def phase_name(self) -> str:
        """Return the current phase name for display."""
        return str(self.phase)
    
    def format_elapsed_time(self) -> str:
        """Format elapsed time for display."""
        minutes, seconds = divmod(int(self.elapsed_seconds), 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert status to a dictionary for serialization."""
        return {
            "phase": self.phase.name,
            "elapsed_seconds": self.elapsed_seconds,
            "reason": self.reason,
            "phase_results": {
                phase.name: result for phase, result in self.phase_results.items()
            },
            "is_complete": self.is_complete,
            "is_failed": self.is_failed
        } 