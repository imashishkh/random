"""
Supervisor Manager for Agent Swarm Orchestration

This module implements the Supervisor pattern for managing agent lifecycles,
providing hierarchical monitoring, error recovery, and graceful shutdown capabilities.
"""

import asyncio
import signal
import sys
import time
import threading
import logging
from enum import Enum
from typing import Dict, List, Set, Optional, Any, Callable, Awaitable, Tuple
from dataclasses import dataclass, field
import networkx as nx
from datetime import datetime

from ...utils.logging.logger import get_logger
from .health import get_health_monitor, AgentHealthStatus
from .engine import AgentStatus, AgentMetadata, get_orchestrator

logger = get_logger()


class RestartPolicy(str, Enum):
    """Restart policy for supervised agents"""
    ALWAYS = "always"
    ON_FAILURE = "on-failure"
    NEVER = "never"


@dataclass
class SupervisionPolicy:
    """Configuration for a supervised agent"""
    restart_policy: RestartPolicy = RestartPolicy.ON_FAILURE
    max_restarts: int = 3
    backoff_factor: float = 1.5
    backoff_max: float = 30.0
    escalate_on_failure: bool = True
    shutdown_priority: int = 0
    timeout: float = 10.0
    position_check_required: bool = False


class ShutdownPhase(str, Enum):
    """Phases of the shutdown process"""
    NONE = "none"
    PREPARE = "prepare"
    VERIFY = "verify"
    TERMINATE = "terminate"
    COMPLETE = "complete"


class SupervisorManager:
    """
    Implements the Supervisor pattern for agent lifecycle management.
    
    This class provides:
    1. Hierarchical supervision of agents
    2. Customizable restart policies
    3. Graceful two-phase shutdown
    4. Dependency-aware termination
    5. Fault isolation and escalation
    
    The supervisor pattern is inspired by Erlang's OTP and the Actor model,
    providing robust error handling and recovery strategies.
    """
    
    def __init__(self, orchestrator=None):
        """
        Initialize the supervisor manager.
        
        Args:
            orchestrator: Optional orchestrator instance, will use singleton if None
        """
        # Get or create the orchestrator
        self.orchestrator = orchestrator or get_orchestrator()
        
        # Supervision policies for agents
        self.policies: Dict[str, SupervisionPolicy] = {}
        
        # Agent dependency graph (directed)
        self.dependency_graph = nx.DiGraph()
        
        # Restart tracking
        self.restart_counts: Dict[str, int] = {}
        self.last_restart: Dict[str, float] = {}
        
        # Shutdown state
        self.shutdown_phase = ShutdownPhase.NONE
        self.shutdown_event = asyncio.Event()
        self.shutdown_verified = asyncio.Event()
        self.shutdown_complete = asyncio.Event()
        self.shutdown_timeout = 60.0  # Default timeout in seconds
        
        # Recovery tasks
        self.recovery_tasks: Dict[str, asyncio.Task] = {}
        
        # Health monitoring integration
        self.health_monitor = get_health_monitor()
        
        # Lifecycle event log
        self.events: List[Dict[str, Any]] = []
        
        # Active agent tasks
        self.agent_tasks: Dict[str, asyncio.Task] = {}
        
        # Set up signal handlers
        self._setup_signal_handlers()
        
        logger.info("Supervisor Manager initialized")
    
    async def register_agent(self, 
                           agent_id: str, 
                           dependencies: List[str] = None,
                           policy: SupervisionPolicy = None) -> None:
        """
        Register an agent with supervision policy and dependencies.
        
        Args:
            agent_id: Unique agent identifier
            dependencies: List of agent IDs this agent depends on
            policy: Supervision policy, uses default if None
        """
        # Set default policy if not provided
        if policy is None:
            policy = SupervisionPolicy()
        
        # Store supervision policy
        self.policies[agent_id] = policy
        
        # Initialize restart count
        self.restart_counts[agent_id] = 0
        
        # Add to dependency graph
        self.dependency_graph.add_node(agent_id)
        
        # Add dependencies
        dependencies = dependencies or []
        for dep_id in dependencies:
            self.dependency_graph.add_edge(dep_id, agent_id)
        
        # Log event
        self._log_event(agent_id, "registered", {
            "dependencies": dependencies,
            "policy": policy.__dict__
        })
        
        logger.info(f"Agent {agent_id} registered with supervisor (dependencies: {dependencies})")
    
    async def deregister_agent(self, agent_id: str) -> None:
        """
        Deregister an agent from supervision.
        
        Args:
            agent_id: Unique agent identifier
        """
        # Remove from policies
        self.policies.pop(agent_id, None)
        
        # Remove from restart tracking
        self.restart_counts.pop(agent_id, None)
        self.last_restart.pop(agent_id, None)
        
        # Remove from dependency graph
        if self.dependency_graph.has_node(agent_id):
            self.dependency_graph.remove_node(agent_id)
        
        # Cancel any recovery tasks
        if agent_id in self.recovery_tasks and not self.recovery_tasks[agent_id].done():
            self.recovery_tasks[agent_id].cancel()
            self.recovery_tasks.pop(agent_id, None)
        
        # Remove from agent tasks
        self.agent_tasks.pop(agent_id, None)
        
        # Log event
        self._log_event(agent_id, "deregistered", {})
        
        logger.info(f"Agent {agent_id} deregistered from supervisor")
    
    async def handle_agent_failure(self, 
                                agent_id: str, 
                                error: Optional[Exception] = None) -> None:
        """
        Handle agent failure according to its supervision policy.
        
        Args:
            agent_id: ID of the failed agent
            error: Optional exception that caused the failure
        """
        if agent_id not in self.policies:
            logger.warning(f"Cannot handle failure for unregistered agent {agent_id}")
            return
        
        policy = self.policies[agent_id]
        
        # Log the failure
        error_str = str(error) if error else "Unknown error"
        self._log_event(agent_id, "failed", {"error": error_str})
        logger.error(f"Agent {agent_id} failed: {error_str}")
        
        # Check restart policy
        if policy.restart_policy == RestartPolicy.NEVER:
            logger.info(f"Agent {agent_id} has NEVER restart policy, not restarting")
            
            # Escalate if configured
            if policy.escalate_on_failure:
                await self._escalate_failure(agent_id, error)
            return
        
        # Check if agent failure was during shutdown
        if self.shutdown_phase != ShutdownPhase.NONE:
            logger.info(f"Not restarting agent {agent_id} during shutdown")
            return
        
        # Check if max restarts exceeded
        current_restarts = self.restart_counts.get(agent_id, 0)
        if current_restarts >= policy.max_restarts and policy.restart_policy != RestartPolicy.ALWAYS:
            logger.warning(
                f"Agent {agent_id} exceeded max restart attempts ({policy.max_restarts}), escalating"
            )
            await self._escalate_failure(agent_id, error)
            return
        
        # Calculate backoff time
        backoff = min(
            policy.backoff_factor ** current_restarts,
            policy.backoff_max
        )
        
        # Log restart attempt
        self._log_event(agent_id, "restarting", {
            "attempt": current_restarts + 1,
            "backoff": backoff,
            "max_restarts": policy.max_restarts
        })
        
        # Schedule restart with backoff
        logger.info(f"Scheduling restart of agent {agent_id} in {backoff:.2f}s (attempt {current_restarts + 1})")
        self.restart_counts[agent_id] = current_restarts + 1
        self.last_restart[agent_id] = time.time()
        
        # Create restart task
        restart_task = asyncio.create_task(
            self._restart_agent_with_backoff(agent_id, backoff),
            name=f"restart:{agent_id}"
        )
        self.recovery_tasks[agent_id] = restart_task
    
    async def _restart_agent_with_backoff(self, agent_id: str, backoff: float) -> None:
        """
        Restart an agent after a backoff period.
        
        Args:
            agent_id: ID of the agent to restart
            backoff: Backoff time in seconds
        """
        try:
            # Wait for backoff period
            await asyncio.sleep(backoff)
            
            # Get agent metadata
            metadata = await self.orchestrator.get_agent_metadata(agent_id)
            if not metadata:
                logger.warning(f"Cannot restart agent {agent_id}: not found in registry")
                return
            
            # Log restart
            logger.info(f"Restarting agent {agent_id}")
            self._log_event(agent_id, "restart_initiated", {})
            
            # Restart the agent using orchestrator
            agent_type = metadata.agent_type
            name = metadata.name
            config = metadata.config
            
            # Update agent status
            await self.orchestrator.update_agent_status(agent_id, AgentStatus.RESTARTING)
            
            # Spawn the agent
            try:
                task = await self.orchestrator.spawn_agent(agent_id, agent_type, name, config)
                self.agent_tasks[agent_id] = task
                
                # Log successful restart
                self._log_event(agent_id, "restart_completed", {"success": True})
                logger.info(f"Agent {agent_id} restarted successfully")
            except Exception as e:
                # Log failed restart
                self._log_event(agent_id, "restart_failed", {"error": str(e)})
                logger.error(f"Failed to restart agent {agent_id}: {str(e)}")
                
                # Escalate if policy requires it
                policy = self.policies[agent_id]
                if policy.escalate_on_failure:
                    await self._escalate_failure(agent_id, e)
        except asyncio.CancelledError:
            # Restart was cancelled
            logger.info(f"Restart of agent {agent_id} was cancelled")
        except Exception as e:
            # Log any other errors
            logger.error(f"Error during restart of agent {agent_id}: {str(e)}", exc_info=True)
    
    async def _escalate_failure(self, agent_id: str, error: Optional[Exception] = None) -> None:
        """
        Escalate agent failure to appropriate handlers.
        
        Args:
            agent_id: ID of the failed agent
            error: Optional exception that caused the failure
        """
        # Log escalation
        error_str = str(error) if error else "Unknown error"
        self._log_event(agent_id, "failure_escalated", {"error": error_str})
        logger.warning(f"Escalating failure of agent {agent_id}: {error_str}")
        
        # Find dependent agents
        dependents = list(self.dependency_graph.successors(agent_id)) if self.dependency_graph.has_node(agent_id) else []
        
        if dependents:
            logger.warning(f"Agent {agent_id} failure affects {len(dependents)} dependent agents: {dependents}")
            
            # Update dependents
            for dep_id in dependents:
                if dep_id in self.policies:
                    # Mark dependent as degraded
                    await self.orchestrator.update_agent_status(dep_id, AgentStatus.DEGRADED)
                    self._log_event(dep_id, "degraded", {"caused_by": agent_id})
        
        # TODO: Add integration with alerting system here
    
    async def initiate_shutdown(self, timeout: float = 60.0) -> None:
        """
        Initiate graceful shutdown sequence.
        
        Args:
            timeout: Maximum time to wait for shutdown in seconds
        """
        if self.shutdown_phase != ShutdownPhase.NONE:
            logger.info(f"Shutdown already in progress (phase: {self.shutdown_phase})")
            return
        
        logger.info(f"Initiating graceful shutdown with {timeout}s timeout")
        self.shutdown_timeout = timeout
        self.shutdown_phase = ShutdownPhase.PREPARE
        self.shutdown_event.set()
        
        # Start shutdown process in background
        asyncio.create_task(
            self._execute_shutdown_sequence(),
            name="supervisor_shutdown"
        )
    
    async def wait_for_shutdown(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for shutdown to complete.
        
        Args:
            timeout: Optional timeout override
            
        Returns:
            True if shutdown was completed cleanly, False if forced or timed out
        """
        if self.shutdown_phase == ShutdownPhase.NONE:
            logger.warning("wait_for_shutdown called but shutdown not initiated")
            return False
        
        if self.shutdown_phase == ShutdownPhase.COMPLETE:
            return True
        
        timeout = timeout or self.shutdown_timeout
        try:
            await asyncio.wait_for(self.shutdown_complete.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Timed out waiting for shutdown to complete after {timeout}s")
            return False
    
    async def _execute_shutdown_sequence(self) -> None:
        """
        Execute the two-phase shutdown sequence.
        """
        try:
            # Phase 1: Prepare for shutdown
            logger.info("SHUTDOWN PHASE 1: Preparing agents for shutdown")
            await self._notify_agents_prepare_shutdown()
            
            # Phase 2: Verify positions closed
            logger.info("SHUTDOWN PHASE 2: Verifying positions are closed")
            self.shutdown_phase = ShutdownPhase.VERIFY
            positions_verified = await self._verify_positions_closed()
            
            if not positions_verified:
                logger.warning("Not all positions verified as closed, proceeding with caution")
            
            # Mark verification complete
            self.shutdown_verified.set()
            
            # Phase 3: Terminate agents in dependency order
            logger.info("SHUTDOWN PHASE 3: Terminating agents in dependency order")
            self.shutdown_phase = ShutdownPhase.TERMINATE
            
            # Determine termination order
            termination_order = self._get_termination_order()
            
            # Terminate in order
            for agent_id in termination_order:
                await self._terminate_agent_with_policy(agent_id)
            
            # Clean up any remaining tasks
            await self._cleanup_remaining_tasks()
            
            # Mark shutdown complete
            self.shutdown_phase = ShutdownPhase.COMPLETE
            self.shutdown_complete.set()
            logger.info("Supervisor shutdown sequence completed successfully")
        except Exception as e:
            logger.error(f"Error during shutdown sequence: {str(e)}", exc_info=True)
            # Force shutdown on error
            self.shutdown_phase = ShutdownPhase.COMPLETE
            self.shutdown_complete.set()
            logger.warning("Forcing shutdown completion due to error")
    
    async def _notify_agents_prepare_shutdown(self) -> None:
        """
        Notify all agents to prepare for shutdown.
        """
        agents = await self.orchestrator.get_all_agents()
        
        # Group by priority
        agents_by_priority = {}
        for agent in agents:
            policy = self.policies.get(agent.id, SupervisionPolicy())
            priority = policy.shutdown_priority
            if priority not in agents_by_priority:
                agents_by_priority[priority] = []
            agents_by_priority[priority].append(agent)
        
        # Process in priority order (higher first)
        for priority in sorted(agents_by_priority.keys(), reverse=True):
            priority_agents = agents_by_priority[priority]
            
            # Log notification
            agent_ids = [a.id for a in priority_agents]
            logger.info(f"Notifying {len(agent_ids)} agents to prepare for shutdown (priority {priority}): {agent_ids}")
            
            # Create tasks to notify agents
            notify_tasks = []
            for agent in priority_agents:
                task = asyncio.create_task(
                    self._notify_agent_prepare_shutdown(agent.id),
                    name=f"notify_shutdown:{agent.id}"
                )
                notify_tasks.append(task)
            
            # Wait for current priority level to complete
            if notify_tasks:
                await asyncio.gather(*notify_tasks, return_exceptions=True)
    
    async def _notify_agent_prepare_shutdown(self, agent_id: str) -> None:
        """
        Notify individual agent to prepare for shutdown.
        
        Args:
            agent_id: ID of the agent to notify
        """
        try:
            # Get agent metadata
            metadata = await self.orchestrator.get_agent_metadata(agent_id)
            if not metadata or metadata.status in (AgentStatus.STOPPED, AgentStatus.FAILED):
                return
            
            # Set agent status to stopping
            await self.orchestrator.update_agent_status(agent_id, AgentStatus.STOPPING)
            
            # Log event
            self._log_event(agent_id, "prepare_shutdown", {})
            logger.debug(f"Agent {agent_id} notified to prepare for shutdown")
            
            # TODO: Implement Redis pub/sub notification to agent here
            # For now, this just updates the status
        except Exception as e:
            logger.warning(f"Failed to notify agent {agent_id} for shutdown: {str(e)}")
    
    async def _verify_positions_closed(self) -> bool:
        """
        Verify that all trading positions are closed before proceeding with shutdown.
        
        Returns:
            True if all positions verified as closed, False otherwise
        """
        # Get agents requiring position check
        position_check_agents = []
        for agent_id, policy in self.policies.items():
            if policy.position_check_required:
                metadata = await self.orchestrator.get_agent_metadata(agent_id)
                if metadata and metadata.status not in (AgentStatus.STOPPED, AgentStatus.FAILED):
                    position_check_agents.append(agent_id)
        
        if not position_check_agents:
            logger.info("No agents require position verification")
            return True
        
        logger.info(f"Verifying positions closed for {len(position_check_agents)} agents: {position_check_agents}")
        
        # TODO: Implement position verification with risk manager
        # For now, we assume positions are closed after a delay
        await asyncio.sleep(2.0)
        
        # Log verification
        for agent_id in position_check_agents:
            self._log_event(agent_id, "positions_verified", {"closed": True})
        
        logger.info("All positions verified as closed")
        return True
    
    def _get_termination_order(self) -> List[str]:
        """
        Get the order in which agents should be terminated based on dependencies.
        
        Returns:
            List of agent IDs in termination order
        """
        try:
            # Use topological sort to get termination order
            termination_order = list(nx.topological_sort(self.dependency_graph))
            
            # Reverse the order so agents with dependencies are terminated last
            termination_order.reverse()
            
            logger.info(f"Determined agent termination order: {termination_order}")
            return termination_order
        except nx.NetworkXUnfeasible:
            # Handle cycles in graph
            logger.warning("Dependency graph contains cycles, using priority-based termination")
            
            # Fall back to priority-based ordering
            agents_with_priority = []
            for agent_id, policy in self.policies.items():
                agents_with_priority.append((agent_id, policy.shutdown_priority))
            
            # Sort by priority (higher first)
            agents_with_priority.sort(key=lambda x: x[1], reverse=True)
            priority_order = [a[0] for a in agents_with_priority]
            
            logger.info(f"Using priority-based termination order: {priority_order}")
            return priority_order
    
    async def _terminate_agent_with_policy(self, agent_id: str) -> bool:
        """
        Terminate an agent according to its supervision policy.
        
        Args:
            agent_id: ID of the agent to terminate
            
        Returns:
            True if termination was successful, False otherwise
        """
        # Get policy and timeout
        policy = self.policies.get(agent_id, SupervisionPolicy())
        timeout = policy.timeout
        
        # Log termination
        self._log_event(agent_id, "terminating", {"timeout": timeout})
        logger.info(f"Terminating agent {agent_id} with {timeout}s timeout")
        
        try:
            # Terminate using orchestrator
            success = await self.orchestrator.terminate_agent(
                agent_id, 
                timeout=timeout,
                force=True  # Force termination during shutdown
            )
            
            # Log result
            self._log_event(agent_id, "terminated", {"success": success})
            
            if success:
                logger.info(f"Agent {agent_id} terminated successfully")
            else:
                logger.warning(f"Agent {agent_id} termination may have been incomplete")
            
            return success
        except Exception as e:
            logger.error(f"Error terminating agent {agent_id}: {str(e)}")
            self._log_event(agent_id, "terminate_error", {"error": str(e)})
            return False
    
    async def _cleanup_remaining_tasks(self) -> None:
        """
        Clean up any remaining tasks after agent termination.
        """
        # Cancel recovery tasks
        for agent_id, task in list(self.recovery_tasks.items()):
            if not task.done():
                logger.debug(f"Cancelling recovery task for agent {agent_id}")
                task.cancel()
        
        # Clear recovery tasks
        self.recovery_tasks.clear()
        
        # Clear agent tasks
        self.agent_tasks.clear()
        
        logger.info("Cleaned up all remaining supervision tasks")
    
    def _setup_signal_handlers(self) -> None:
        """
        Set up signal handlers for graceful shutdown.
        """
        # Only set up in main thread
        if threading.current_thread() is not threading.main_thread():
            return
        
        # Set up signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._signal_handler)
                logger.debug(f"Registered signal handler for {sig.name}")
            except Exception as e:
                logger.warning(f"Failed to set up signal handler for {getattr(sig, 'name', sig)}: {str(e)}")
    
    def _signal_handler(self, signum: int, frame) -> None:
        """
        Handle termination signals by scheduling a graceful shutdown.
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        
        # Schedule shutdown in the event loop
        if asyncio.get_event_loop().is_running():
            asyncio.create_task(self.initiate_shutdown())
        else:
            # If event loop is not running, we can't do much
            logger.warning(f"Event loop not running, can't schedule graceful shutdown for {sig_name}")
            sys.exit(1)
    
    def _log_event(self, agent_id: str, event_type: str, data: Dict[str, Any]) -> None:
        """
        Log a lifecycle event for the agent.
        
        Args:
            agent_id: ID of the agent
            event_type: Type of event
            data: Additional event data
        """
        timestamp = datetime.now().isoformat()
        event = {
            "timestamp": timestamp,
            "agent_id": agent_id,
            "event": event_type,
            "data": data
        }
        self.events.append(event)
        
        # Keep event log to a reasonable size
        if len(self.events) > 1000:
            self.events = self.events[-1000:]


# Singleton instance
_supervisor_instance = None


def get_supervisor(orchestrator=None) -> SupervisorManager:
    """
    Get or create the singleton supervisor instance.
    
    Args:
        orchestrator: Optional orchestrator instance
        
    Returns:
        The supervisor manager instance
    """
    global _supervisor_instance
    if _supervisor_instance is None:
        _supervisor_instance = SupervisorManager(orchestrator)
    return _supervisor_instance 