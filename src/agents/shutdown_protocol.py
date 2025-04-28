"""
Agent Shutdown Protocol

This module implements a three-phase protocol for gracefully shutting down
trading agents:

1. Preparation: Agents prepare for shutdown (flush data, save state)
2. Stop: Agents stop processing new data or making decisions
3. Cleanup: Agents clean up resources and terminate connections

The protocol includes a registry to track the status of each agent during
the shutdown process, with configurable timeouts for each phase.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

# Configure logger
logger = logging.getLogger(__name__)


class ShutdownPhase(Enum):
    """Phases of the agent shutdown protocol."""
    PREPARATION = "preparation"
    STOP = "stop"
    CLEANUP = "cleanup"
    COMPLETE = "complete"  # All phases finished
    NOT_STARTED = "not_started"  # Shutdown not yet initiated


class ShutdownStatus(Enum):
    """Status of a shutdown phase for an agent."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AgentShutdownState:
    """
    Tracks the shutdown state of an individual agent.
    """
    agent_id: str
    agent_type: str
    agent_instance: Any
    registered_at: float = field(default_factory=time.time)
    shutdown_priority: int = 0
    dependencies: List[str] = field(default_factory=list)
    
    # Overall status tracking
    overall_status: ShutdownStatus = ShutdownStatus.NOT_STARTED
    
    # Preparation phase
    preparation_status: ShutdownStatus = ShutdownStatus.NOT_STARTED
    preparation_start: Optional[float] = None
    preparation_end: Optional[float] = None
    preparation_error: Optional[Exception] = None
    
    # Stop phase
    stop_status: ShutdownStatus = ShutdownStatus.NOT_STARTED
    stop_start: Optional[float] = None
    stop_end: Optional[float] = None
    stop_error: Optional[Exception] = None
    
    # Cleanup phase
    cleanup_status: ShutdownStatus = ShutdownStatus.NOT_STARTED
    cleanup_start: Optional[float] = None
    cleanup_end: Optional[float] = None
    cleanup_error: Optional[Exception] = None
    
    def is_complete(self) -> bool:
        """Check if all shutdown phases are complete (successful or not)."""
        return (self.preparation_status in (ShutdownStatus.COMPLETED, ShutdownStatus.FAILED, ShutdownStatus.TIMED_OUT, ShutdownStatus.SKIPPED) and
                self.stop_status in (ShutdownStatus.COMPLETED, ShutdownStatus.FAILED, ShutdownStatus.TIMED_OUT, ShutdownStatus.SKIPPED) and
                self.cleanup_status in (ShutdownStatus.COMPLETED, ShutdownStatus.FAILED, ShutdownStatus.TIMED_OUT, ShutdownStatus.SKIPPED))
    
    def was_successful(self) -> bool:
        """Check if all shutdown phases completed successfully."""
        return (self.preparation_status == ShutdownStatus.COMPLETED and
                self.stop_status == ShutdownStatus.COMPLETED and
                self.cleanup_status == ShutdownStatus.COMPLETED)
    
    def get_execution_time(self) -> float:
        """Get the total execution time of all phases."""
        total_time = 0.0
        
        # Preparation phase time
        if self.preparation_start and self.preparation_end:
            total_time += self.preparation_end - self.preparation_start
        
        # Stop phase time
        if self.stop_start and self.stop_end:
            total_time += self.stop_end - self.stop_start
        
        # Cleanup phase time
        if self.cleanup_start and self.cleanup_end:
            total_time += self.cleanup_end - self.cleanup_start
        
        return total_time
    
    def get_current_phase(self) -> ShutdownPhase:
        """Get the current or most recently completed phase."""
        if self.is_complete():
            return ShutdownPhase.COMPLETE
        elif self.cleanup_status == ShutdownStatus.IN_PROGRESS:
            return ShutdownPhase.CLEANUP
        elif self.stop_status == ShutdownStatus.IN_PROGRESS:
            return ShutdownPhase.STOP
        elif self.preparation_status == ShutdownStatus.IN_PROGRESS:
            return ShutdownPhase.PREPARATION
        else:
            return ShutdownPhase.NOT_STARTED
    
    def update_overall_status(self) -> None:
        """Update the overall status based on phase statuses."""
        if self.is_complete():
            if self.was_successful():
                self.overall_status = ShutdownStatus.COMPLETED
            elif (ShutdownStatus.FAILED in 
                 (self.preparation_status, self.stop_status, self.cleanup_status)):
                self.overall_status = ShutdownStatus.FAILED
            elif (ShutdownStatus.TIMED_OUT in 
                 (self.preparation_status, self.stop_status, self.cleanup_status)):
                self.overall_status = ShutdownStatus.TIMED_OUT
            else:
                # Must include some skipped phases
                self.overall_status = ShutdownStatus.COMPLETED
        elif (self.preparation_status == ShutdownStatus.IN_PROGRESS or
              self.stop_status == ShutdownStatus.IN_PROGRESS or
              self.cleanup_status == ShutdownStatus.IN_PROGRESS):
            self.overall_status = ShutdownStatus.IN_PROGRESS
        else:
            self.overall_status = ShutdownStatus.NOT_STARTED


class AgentShutdownRegistry:
    """
    Registry for tracking agents during shutdown.
    
    Manages agent state, dependencies, and provides progress information
    during the shutdown process.
    """
    
    def __init__(self):
        """Initialize the agent registry."""
        self._agents: Dict[str, AgentShutdownState] = {}
        self._lock = asyncio.Lock()
        self._shutdown_complete_event = asyncio.Event()
    
    async def register_agent(self, 
                           agent_id: str, 
                           agent_type: str, 
                           agent_instance: Any,
                           shutdown_priority: int = 0,
                           dependencies: Optional[List[str]] = None) -> None:
        """
        Register an agent for shutdown tracking.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_type: Type of agent (technical, execution, etc.)
            agent_instance: Reference to the agent instance
            shutdown_priority: Priority during shutdown (higher values first)
            dependencies: List of agent IDs this agent depends on
        """
        async with self._lock:
            if agent_id in self._agents:
                logger.warning(f"Agent {agent_id} already registered, updating")
            
            deps = dependencies if dependencies else []
            self._agents[agent_id] = AgentShutdownState(
                agent_id=agent_id,
                agent_type=agent_type,
                agent_instance=agent_instance,
                shutdown_priority=shutdown_priority,
                dependencies=deps,
                registered_at=time.time()
            )
            
            logger.info(f"Agent registered: {agent_id} (type: {agent_type}, priority: {shutdown_priority})")
    
    def register_agent(self, 
                     agent_id: str, 
                     agent_type: str, 
                     agent_instance: Any,
                     shutdown_priority: int = 0,
                     dependencies: Optional[List[str]] = None) -> None:
        """
        Synchronous version of register_agent.
        """
        if agent_id in self._agents:
            logger.warning(f"Agent {agent_id} already registered, updating")
        
        deps = dependencies if dependencies else []
        self._agents[agent_id] = AgentShutdownState(
            agent_id=agent_id,
            agent_type=agent_type,
            agent_instance=agent_instance,
            shutdown_priority=shutdown_priority,
            dependencies=deps,
            registered_at=time.time()
        )
        
        logger.info(f"Agent registered: {agent_id} (type: {agent_type}, priority: {shutdown_priority})")
    
    async def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent.
        
        Args:
            agent_id: ID of the agent to unregister
            
        Returns:
            True if agent was unregistered, False if not found
        """
        async with self._lock:
            if agent_id not in self._agents:
                logger.warning(f"Agent {agent_id} not found, cannot unregister")
                return False
            
            del self._agents[agent_id]
            logger.info(f"Agent unregistered: {agent_id}")
            return True
    
    def unregister_agent(self, agent_id: str) -> bool:
        """
        Synchronous version of unregister_agent.
        """
        if agent_id not in self._agents:
            logger.warning(f"Agent {agent_id} not found, cannot unregister")
            return False
        
        del self._agents[agent_id]
        logger.info(f"Agent unregistered: {agent_id}")
        return True
    
    async def get_agent_state(self, agent_id: str) -> Optional[AgentShutdownState]:
        """
        Get the shutdown state for a specific agent.
        
        Args:
            agent_id: ID of the agent
            
        Returns:
            Agent state object or None if not found
        """
        async with self._lock:
            return self._agents.get(agent_id)
    
    def get_agent_state(self, agent_id: str) -> Optional[AgentShutdownState]:
        """
        Synchronous version of get_agent_state.
        """
        return self._agents.get(agent_id)
    
    async def get_all_agent_states(self) -> Dict[str, AgentShutdownState]:
        """
        Get shutdown states for all registered agents.
        
        Returns:
            Dictionary mapping agent IDs to their states
        """
        async with self._lock:
            return self._agents.copy()
    
    def get_all_agent_states(self) -> Dict[str, AgentShutdownState]:
        """
        Synchronous version of get_all_agent_states.
        """
        return self._agents.copy()
    
    async def set_phase_started(self, agent_id: str, phase: ShutdownPhase) -> bool:
        """
        Mark a shutdown phase as started for an agent.
        
        Args:
            agent_id: ID of the agent
            phase: Phase that started
            
        Returns:
            True if updated, False if agent not found
        """
        async with self._lock:
            agent_state = self._agents.get(agent_id)
            if not agent_state:
                logger.warning(f"Agent {agent_id} not found, cannot update phase {phase.value}")
                return False
            
            if phase == ShutdownPhase.PREPARATION:
                agent_state.preparation_status = ShutdownStatus.IN_PROGRESS
                agent_state.preparation_start = time.time()
            elif phase == ShutdownPhase.STOP:
                agent_state.stop_status = ShutdownStatus.IN_PROGRESS
                agent_state.stop_start = time.time()
            elif phase == ShutdownPhase.CLEANUP:
                agent_state.cleanup_status = ShutdownStatus.IN_PROGRESS
                agent_state.cleanup_start = time.time()
            
            agent_state.update_overall_status()
            return True
    
    async def set_phase_completed(self, agent_id: str, phase: ShutdownPhase) -> bool:
        """
        Mark a shutdown phase as completed for an agent.
        
        Args:
            agent_id: ID of the agent
            phase: Phase that completed
            
        Returns:
            True if updated, False if agent not found
        """
        async with self._lock:
            agent_state = self._agents.get(agent_id)
            if not agent_state:
                logger.warning(f"Agent {agent_id} not found, cannot update phase {phase.value}")
                return False
            
            if phase == ShutdownPhase.PREPARATION:
                agent_state.preparation_status = ShutdownStatus.COMPLETED
                agent_state.preparation_end = time.time()
            elif phase == ShutdownPhase.STOP:
                agent_state.stop_status = ShutdownStatus.COMPLETED
                agent_state.stop_end = time.time()
            elif phase == ShutdownPhase.CLEANUP:
                agent_state.cleanup_status = ShutdownStatus.COMPLETED
                agent_state.cleanup_end = time.time()
            
            agent_state.update_overall_status()
            
            # Check if all agents are complete
            await self._check_all_complete()
            
            return True
    
    async def set_phase_failed(self, 
                             agent_id: str, 
                             phase: ShutdownPhase, 
                             error: Optional[Exception] = None) -> bool:
        """
        Mark a shutdown phase as failed for an agent.
        
        Args:
            agent_id: ID of the agent
            phase: Phase that failed
            error: Optional exception that caused the failure
            
        Returns:
            True if updated, False if agent not found
        """
        async with self._lock:
            agent_state = self._agents.get(agent_id)
            if not agent_state:
                logger.warning(f"Agent {agent_id} not found, cannot update phase {phase.value}")
                return False
            
            if phase == ShutdownPhase.PREPARATION:
                agent_state.preparation_status = ShutdownStatus.FAILED
                agent_state.preparation_end = time.time()
                agent_state.preparation_error = error
            elif phase == ShutdownPhase.STOP:
                agent_state.stop_status = ShutdownStatus.FAILED
                agent_state.stop_end = time.time()
                agent_state.stop_error = error
            elif phase == ShutdownPhase.CLEANUP:
                agent_state.cleanup_status = ShutdownStatus.FAILED
                agent_state.cleanup_end = time.time()
                agent_state.cleanup_error = error
            
            agent_state.update_overall_status()
            
            # Check if all agents are complete
            await self._check_all_complete()
            
            return True
    
    async def set_phase_timed_out(self, agent_id: str, phase: ShutdownPhase) -> bool:
        """
        Mark a shutdown phase as timed out for an agent.
        
        Args:
            agent_id: ID of the agent
            phase: Phase that timed out
            
        Returns:
            True if updated, False if agent not found
        """
        async with self._lock:
            agent_state = self._agents.get(agent_id)
            if not agent_state:
                logger.warning(f"Agent {agent_id} not found, cannot update phase {phase.value}")
                return False
            
            if phase == ShutdownPhase.PREPARATION:
                agent_state.preparation_status = ShutdownStatus.TIMED_OUT
                agent_state.preparation_end = time.time()
            elif phase == ShutdownPhase.STOP:
                agent_state.stop_status = ShutdownStatus.TIMED_OUT
                agent_state.stop_end = time.time()
            elif phase == ShutdownPhase.CLEANUP:
                agent_state.cleanup_status = ShutdownStatus.TIMED_OUT
                agent_state.cleanup_end = time.time()
            
            agent_state.update_overall_status()
            
            # Check if all agents are complete
            await self._check_all_complete()
            
            return True
    
    async def set_phase_skipped(self, agent_id: str, phase: ShutdownPhase) -> bool:
        """
        Mark a shutdown phase as skipped for an agent.
        
        Args:
            agent_id: ID of the agent
            phase: Phase that was skipped
            
        Returns:
            True if updated, False if agent not found
        """
        async with self._lock:
            agent_state = self._agents.get(agent_id)
            if not agent_state:
                logger.warning(f"Agent {agent_id} not found, cannot update phase {phase.value}")
                return False
            
            if phase == ShutdownPhase.PREPARATION:
                agent_state.preparation_status = ShutdownStatus.SKIPPED
                agent_state.preparation_start = time.time()
                agent_state.preparation_end = time.time()
            elif phase == ShutdownPhase.STOP:
                agent_state.stop_status = ShutdownStatus.SKIPPED
                agent_state.stop_start = time.time()
                agent_state.stop_end = time.time()
            elif phase == ShutdownPhase.CLEANUP:
                agent_state.cleanup_status = ShutdownStatus.SKIPPED
                agent_state.cleanup_start = time.time()
                agent_state.cleanup_end = time.time()
            
            agent_state.update_overall_status()
            
            # Check if all agents are complete
            await self._check_all_complete()
            
            return True
    
    async def _check_all_complete(self) -> bool:
        """
        Check if all agents have completed the shutdown process and
        set the completion event if so.
        
        Returns:
            True if all agents are complete, False otherwise
        """
        all_complete = True
        for agent_state in self._agents.values():
            if not agent_state.is_complete():
                all_complete = False
                break
        
        if all_complete and self._agents:
            self._shutdown_complete_event.set()
        
        return all_complete
    
    async def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for all agents to complete the shutdown process.
        
        Args:
            timeout: Maximum time to wait in seconds, or None to wait indefinitely
            
        Returns:
            True if all agents completed, False if timeout was reached
        """
        try:
            await asyncio.wait_for(self._shutdown_complete_event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False
    
    def get_shutdown_progress(self) -> Dict[str, Any]:
        """
        Get current shutdown progress statistics.
        
        Returns:
            Dictionary with detailed shutdown statistics
        """
        total_agents = len(self._agents)
        completed_agents = sum(1 for agent in self._agents.values() if agent.is_complete())
        successful_agents = sum(1 for agent in self._agents.values() if agent.was_successful())
        
        # Count by phase status
        preparation_counts = {status.value: 0 for status in ShutdownStatus}
        stop_counts = {status.value: 0 for status in ShutdownStatus}
        cleanup_counts = {status.value: 0 for status in ShutdownStatus}
        
        for agent in self._agents.values():
            preparation_counts[agent.preparation_status.value] += 1
            stop_counts[agent.stop_status.value] += 1
            cleanup_counts[agent.cleanup_status.value] += 1
        
        # Count by agent type
        type_counts = {}
        for agent in self._agents.values():
            agent_type = agent.agent_type
            if agent_type not in type_counts:
                type_counts[agent_type] = {
                    "total": 0,
                    "completed": 0,
                    "successful": 0
                }
            
            type_counts[agent_type]["total"] += 1
            if agent.is_complete():
                type_counts[agent_type]["completed"] += 1
            if agent.was_successful():
                type_counts[agent_type]["successful"] += 1
        
        return {
            "total_agents": total_agents,
            "completed_agents": completed_agents,
            "successful_agents": successful_agents,
            "percent_complete": (completed_agents / total_agents * 100) if total_agents > 0 else 100,
            "percent_successful": (successful_agents / total_agents * 100) if total_agents > 0 else 100,
            "phases": {
                "preparation": preparation_counts,
                "stop": stop_counts,
                "cleanup": cleanup_counts
            },
            "agent_types": type_counts
        }
    
    def get_agents_by_priority(self) -> List[AgentShutdownState]:
        """
        Get all registered agents sorted by shutdown priority (highest first).
        
        Returns:
            List of agent state objects sorted by priority
        """
        return sorted(
            self._agents.values(),
            key=lambda a: a.shutdown_priority,
            reverse=True
        )
    
    def get_dependency_order(self) -> List[str]:
        """
        Get agents ordered by dependencies (dependencies first).
        
        Returns:
            List of agent IDs ordered by dependencies
        """
        # Simple topological sort
        result = []
        visited = set()
        temp_visited = set()
        
        def visit(agent_id):
            if agent_id in temp_visited:
                # Circular dependency detected
                logger.warning(f"Circular dependency detected involving agent {agent_id}")
                return
            if agent_id in visited:
                return
            
            temp_visited.add(agent_id)
            
            # Visit dependencies first
            agent = self._agents.get(agent_id)
            if agent:
                for dep_id in agent.dependencies:
                    if dep_id in self._agents:
                        visit(dep_id)
            
            temp_visited.remove(agent_id)
            visited.add(agent_id)
            result.append(agent_id)
        
        # Visit each agent
        for agent_id in self._agents:
            if agent_id not in visited:
                visit(agent_id)
        
        # Return in reverse order (dependencies first)
        return result[::-1]


class AgentShutdownProtocol:
    """
    Implements the three-phase agent shutdown protocol.
    
    Manages the orchestration of the shutdown process across multiple agents,
    respecting dependencies and priorities.
    """
    
    def __init__(self):
        """Initialize the shutdown protocol."""
        self.registry = AgentShutdownRegistry()
        
        # Default timeouts for each phase (in seconds)
        self._preparation_timeout = 10.0
        self._stop_timeout = 10.0
        self._cleanup_timeout = 5.0
        
        # Shutdown flags
        self._shutdown_in_progress = False
        self._shutdown_lock = asyncio.Lock()
    
    def set_timeouts(self, 
                    preparation: Optional[float] = None,
                    stop: Optional[float] = None,
                    cleanup: Optional[float] = None) -> None:
        """
        Set custom timeouts for shutdown phases.
        
        Args:
            preparation: Timeout for preparation phase (seconds)
            stop: Timeout for stop phase (seconds)
            cleanup: Timeout for cleanup phase (seconds)
        """
        if preparation is not None:
            self._preparation_timeout = max(0.1, preparation)
        
        if stop is not None:
            self._stop_timeout = max(0.1, stop)
        
        if cleanup is not None:
            self._cleanup_timeout = max(0.1, cleanup)
        
        logger.debug(f"Timeouts set: preparation={self._preparation_timeout}s, "
                    f"stop={self._stop_timeout}s, cleanup={self._cleanup_timeout}s")
    
    async def shutdown_agent(self, agent_id: str, force: bool = False) -> bool:
        """
        Shut down a specific agent using the three-phase protocol.
        
        Args:
            agent_id: ID of the agent to shut down
            force: Whether to force shutdown even if phases fail
            
        Returns:
            True if shutdown was successful, False otherwise
        """
        agent_state = await self.registry.get_agent_state(agent_id)
        if not agent_state:
            logger.error(f"Agent {agent_id} not found, cannot shut down")
            return False
        
        logger.info(f"Starting shutdown for agent {agent_id} (type: {agent_state.agent_type})")
        
        # Execute three-phase shutdown protocol
        prep_success = await self._execute_preparation_phase(agent_state)
        if not prep_success and not force:
            logger.error(f"Preparation phase failed for agent {agent_id}, aborting shutdown")
            return False
        
        stop_success = await self._execute_stop_phase(agent_state)
        if not stop_success and not force:
            logger.error(f"Stop phase failed for agent {agent_id}, aborting shutdown")
            return False
        
        cleanup_success = await self._execute_cleanup_phase(agent_state)
        if not cleanup_success and not force:
            logger.error(f"Cleanup phase failed for agent {agent_id}, shutdown incomplete")
            return False
        
        agent_state.update_overall_status()
        
        if agent_state.was_successful():
            logger.info(f"Agent {agent_id} shutdown completed successfully")
            return True
        else:
            log_fn = logger.warning if force else logger.error
            log_fn(f"Agent {agent_id} shutdown completed with issues: "
                  f"preparation={agent_state.preparation_status.value}, "
                  f"stop={agent_state.stop_status.value}, "
                  f"cleanup={agent_state.cleanup_status.value}")
            return force
    
    async def shutdown_all_agents(self, force: bool = False) -> bool:
        """
        Shut down all registered agents using the three-phase protocol.
        
        Args:
            force: Whether to force shutdown even if phases fail
            
        Returns:
            True if all shutdowns were successful, False otherwise
        """
        async with self._shutdown_lock:
            if self._shutdown_in_progress:
                logger.warning("Shutdown already in progress")
                return False
            
            self._shutdown_in_progress = True
        
        try:
            logger.info("Starting shutdown for all agents")
            
            # Get agents considering dependencies and priorities
            ordered_agents = await self._get_shutdown_order()
            
            # Skip shutdown if no agents registered
            if not ordered_agents:
                logger.info("No agents registered, shutdown complete")
                return True
            
            logger.info(f"Shutting down {len(ordered_agents)} agents in optimal order")
            
            # Execute each phase for all agents before moving to next phase
            overall_success = True
            
            # Phase 1: Preparation
            logger.info("Starting PREPARATION phase for all agents")
            for agent_state in ordered_agents:
                success = await self._execute_preparation_phase(agent_state)
                if not success and not force:
                    overall_success = False
                    logger.error(f"Preparation failed for agent {agent_state.agent_id}, "
                                f"but continuing with remaining agents")
            
            # Phase 2: Stop
            logger.info("Starting STOP phase for all agents")
            for agent_state in ordered_agents:
                success = await self._execute_stop_phase(agent_state)
                if not success and not force:
                    overall_success = False
                    logger.error(f"Stop failed for agent {agent_state.agent_id}, "
                                f"but continuing with remaining agents")
            
            # Phase 3: Cleanup
            logger.info("Starting CLEANUP phase for all agents")
            for agent_state in ordered_agents:
                success = await self._execute_cleanup_phase(agent_state)
                if not success and not force:
                    overall_success = False
                    logger.error(f"Cleanup failed for agent {agent_state.agent_id}, "
                                f"but continuing with remaining agents")
            
            # Log summary
            stats = self.registry.get_shutdown_progress()
            logger.info(f"Shutdown complete: {stats['completed_agents']}/{stats['total_agents']} "
                       f"agents processed, {stats['successful_agents']} successful")
            
            return overall_success or force
        finally:
            async with self._shutdown_lock:
                self._shutdown_in_progress = False
    
    async def _get_shutdown_order(self) -> List[AgentShutdownState]:
        """
        Determine the optimal order for shutting down agents.
        
        Returns:
            List of agent states in optimal shutdown order
        """
        # First sort by dependency order
        dependency_order = self.registry.get_dependency_order()
        
        # Then sort by priority within same dependency level
        priority_groups: Dict[int, List[AgentShutdownState]] = {}
        
        for agent_id in dependency_order:
            agent = await self.registry.get_agent_state(agent_id)
            if agent:
                if agent.shutdown_priority not in priority_groups:
                    priority_groups[agent.shutdown_priority] = []
                priority_groups[agent.shutdown_priority].append(agent)
        
        # Flatten priority groups, highest priority first
        result = []
        for priority in sorted(priority_groups.keys(), reverse=True):
            result.extend(priority_groups[priority])
        
        return result
    
    async def _execute_preparation_phase(self, agent_state: AgentShutdownState) -> bool:
        """
        Execute the preparation phase for an agent.
        
        Args:
            agent_state: Agent state to execute preparation for
            
        Returns:
            True if preparation was successful, False otherwise
        """
        agent_id = agent_state.agent_id
        agent = agent_state.agent_instance
        
        # Skip if already completed
        if agent_state.preparation_status != ShutdownStatus.NOT_STARTED:
            logger.debug(f"Preparation already executed for agent {agent_id}, skipping")
            return agent_state.preparation_status == ShutdownStatus.COMPLETED
        
        # Skip if agent doesn't support prepare
        if not hasattr(agent, 'prepare_shutdown') or not callable(getattr(agent, 'prepare_shutdown')):
            logger.debug(f"Agent {agent_id} doesn't support prepare_shutdown, skipping")
            await self.registry.set_phase_skipped(agent_id, ShutdownPhase.PREPARATION)
            return True
        
        # Start preparation
        logger.debug(f"Starting preparation for agent {agent_id}")
        await self.registry.set_phase_started(agent_id, ShutdownPhase.PREPARATION)
        
        try:
            # Execute with timeout
            prepare_fn = getattr(agent, 'prepare_shutdown')
            
            try:
                await asyncio.wait_for(
                    self._safe_execute_phase(prepare_fn),
                    timeout=self._preparation_timeout
                )
                
                # Mark as successful
                await self.registry.set_phase_completed(agent_id, ShutdownPhase.PREPARATION)
                logger.debug(f"Preparation completed for agent {agent_id}")
                return True
                
            except asyncio.TimeoutError:
                logger.warning(f"Preparation timed out for agent {agent_id} "
                              f"after {self._preparation_timeout} seconds")
                await self.registry.set_phase_timed_out(agent_id, ShutdownPhase.PREPARATION)
                return False
                
        except Exception as e:
            logger.error(f"Preparation failed for agent {agent_id}: {str(e)}")
            await self.registry.set_phase_failed(agent_id, ShutdownPhase.PREPARATION, e)
            return False
    
    async def _execute_stop_phase(self, agent_state: AgentShutdownState) -> bool:
        """
        Execute the stop phase for an agent.
        
        Args:
            agent_state: Agent state to execute stop for
            
        Returns:
            True if stop was successful, False otherwise
        """
        agent_id = agent_state.agent_id
        agent = agent_state.agent_instance
        
        # Skip if already completed
        if agent_state.stop_status != ShutdownStatus.NOT_STARTED:
            logger.debug(f"Stop already executed for agent {agent_id}, skipping")
            return agent_state.stop_status == ShutdownStatus.COMPLETED
        
        # Skip if agent doesn't support stop
        if not hasattr(agent, 'stop') or not callable(getattr(agent, 'stop')):
            logger.debug(f"Agent {agent_id} doesn't support stop, skipping")
            await self.registry.set_phase_skipped(agent_id, ShutdownPhase.STOP)
            return True
        
        # Start stop
        logger.debug(f"Starting stop for agent {agent_id}")
        await self.registry.set_phase_started(agent_id, ShutdownPhase.STOP)
        
        try:
            # Execute with timeout
            stop_fn = getattr(agent, 'stop')
            
            try:
                await asyncio.wait_for(
                    self._safe_execute_phase(stop_fn),
                    timeout=self._stop_timeout
                )
                
                # Mark as successful
                await self.registry.set_phase_completed(agent_id, ShutdownPhase.STOP)
                logger.debug(f"Stop completed for agent {agent_id}")
                return True
                
            except asyncio.TimeoutError:
                logger.warning(f"Stop timed out for agent {agent_id} "
                              f"after {self._stop_timeout} seconds")
                await self.registry.set_phase_timed_out(agent_id, ShutdownPhase.STOP)
                return False
                
        except Exception as e:
            logger.error(f"Stop failed for agent {agent_id}: {str(e)}")
            await self.registry.set_phase_failed(agent_id, ShutdownPhase.STOP, e)
            return False
    
    async def _execute_cleanup_phase(self, agent_state: AgentShutdownState) -> bool:
        """
        Execute the cleanup phase for an agent.
        
        Args:
            agent_state: Agent state to execute cleanup for
            
        Returns:
            True if cleanup was successful, False otherwise
        """
        agent_id = agent_state.agent_id
        agent = agent_state.agent_instance
        
        # Skip if already completed
        if agent_state.cleanup_status != ShutdownStatus.NOT_STARTED:
            logger.debug(f"Cleanup already executed for agent {agent_id}, skipping")
            return agent_state.cleanup_status == ShutdownStatus.COMPLETED
        
        # Skip if agent doesn't support cleanup
        if not hasattr(agent, 'cleanup') or not callable(getattr(agent, 'cleanup')):
            logger.debug(f"Agent {agent_id} doesn't support cleanup, skipping")
            await self.registry.set_phase_skipped(agent_id, ShutdownPhase.CLEANUP)
            return True
        
        # Start cleanup
        logger.debug(f"Starting cleanup for agent {agent_id}")
        await self.registry.set_phase_started(agent_id, ShutdownPhase.CLEANUP)
        
        try:
            # Execute with timeout
            cleanup_fn = getattr(agent, 'cleanup')
            
            try:
                await asyncio.wait_for(
                    self._safe_execute_phase(cleanup_fn),
                    timeout=self._cleanup_timeout
                )
                
                # Mark as successful
                await self.registry.set_phase_completed(agent_id, ShutdownPhase.CLEANUP)
                logger.debug(f"Cleanup completed for agent {agent_id}")
                return True
                
            except asyncio.TimeoutError:
                logger.warning(f"Cleanup timed out for agent {agent_id} "
                              f"after {self._cleanup_timeout} seconds")
                await self.registry.set_phase_timed_out(agent_id, ShutdownPhase.CLEANUP)
                return False
                
        except Exception as e:
            logger.error(f"Cleanup failed for agent {agent_id}: {str(e)}")
            await self.registry.set_phase_failed(agent_id, ShutdownPhase.CLEANUP, e)
            return False
    
    async def _safe_execute_phase(self, phase_fn) -> None:
        """
        Safely execute a phase function that could be sync or async.
        
        Args:
            phase_fn: The phase function to execute
        """
        try:
            if asyncio.iscoroutinefunction(phase_fn):
                await phase_fn()
            else:
                # Run sync function in executor to avoid blocking
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, phase_fn)
        except Exception as e:
            # Re-raise to be caught by the phase executor
            raise
    
    async def wait_for_shutdown(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for all agents to complete the shutdown process.
        
        Args:
            timeout: Maximum time to wait in seconds, or None to wait indefinitely
            
        Returns:
            True if all agents completed, False if timeout was reached
        """
        return await self.registry.wait_for_completion(timeout)


# Singleton instance
_shutdown_protocol_instance = None


def get_shutdown_protocol() -> AgentShutdownProtocol:
    """
    Get or create the singleton shutdown protocol instance.
    
    Returns:
        The shutdown protocol instance
    """
    global _shutdown_protocol_instance
    if _shutdown_protocol_instance is None:
        _shutdown_protocol_instance = AgentShutdownProtocol()
    return _shutdown_protocol_instance 