"""
Agent Swarm Orchestrator

This module provides functionality for managing multiple trading agents with
health monitoring, configuration management, and lifecycle control.
"""

from .engine import (
    AgentSwarmOrchestrator, 
    AgentMetadata, 
    AgentStatus, 
    get_orchestrator
)

from .supervisor import (
    SupervisorManager,
    SupervisionPolicy,
    RestartPolicy,
    get_supervisor
)

# Import shutdown-related classes
from .resource_cleanup_registry import (
    ResourceCleanupRegistry,
    CleanupStatus,
    CleanupResult
)
from .shutdown_verifier import (
    ShutdownVerifier,
    VerificationError
)
from .shutdown_reporter import (
    ShutdownReporter,
    ShutdownStatus,
    PhaseStatus
)
from .shutdown_manager import (
    OrchestratorShutdownManager,
    ShutdownPhase
)

__all__ = [
    # Agent orchestration
    'AgentSwarmOrchestrator',
    'AgentMetadata',
    'AgentStatus',
    'get_orchestrator',
    
    # Supervision
    'SupervisorManager',
    'SupervisionPolicy',
    'RestartPolicy',
    'get_supervisor',
    
    # Shutdown system
    'ResourceCleanupRegistry',
    'CleanupStatus',
    'CleanupResult',
    'ShutdownVerifier',
    'VerificationError',
    'ShutdownReporter',
    'ShutdownStatus',
    'PhaseStatus',
    'OrchestratorShutdownManager',
    'ShutdownPhase',
]
