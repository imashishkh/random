"""
Agent Terminator for Graceful Shutdown

This module provides a bridge between the shutdown coordinator and the
agent orchestrator to safely terminate agents during shutdown.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable, Set

# Import our new shutdown coordinator
from .shutdown import ShutdownPhase, ShutdownCoordinator, get_shutdown_coordinator

# Import the agent orchestrator
from ..agents.orchestrator.engine import AgentSwarmOrchestrator, get_orchestrator, AgentStatus

# Configure logger
logger = logging.getLogger(__name__)


class AgentTerminator:
    """
    Handles the graceful termination of agents during system shutdown.
    
    This class bridges the shutdown coordinator with the agent orchestrator
    to ensure all agents are safely terminated before shutdown.
    """
    
    def __init__(self, orchestrator: Optional[AgentSwarmOrchestrator] = None):
        """
        Initialize the agent terminator.
        
        Args:
            orchestrator: The agent swarm orchestrator to use, or None to get the default
        """
        # Get or use the provided orchestrator
        self.orchestrator = orchestrator or get_orchestrator()
        
        # Get the shutdown coordinator
        self.shutdown_coordinator = get_shutdown_coordinator()
        
        # Track agents that were terminated
        self.terminated_agents = []
        
        # Agent termination timeout
        self.termination_timeout = 15.0  # seconds
        
        # Register with shutdown coordinator
        self.register_with_coordinator()
    
    def register_with_coordinator(self) -> None:
        """Register callbacks with the shutdown coordinator."""
        self.shutdown_coordinator.register_phase_callback(
            ShutdownPhase.AGENTS,
            self.terminate_agents
        )
    
    async def terminate_agents(self) -> None:
        """
        Terminate all agents during shutdown.
        
        This method is called by the shutdown coordinator during the AGENTS phase.
        """
        logger.info("Starting agent termination process")
        
        # Check if we have an orchestrator
        if not self.orchestrator:
            logger.warning("No agent orchestrator available, skipping agent termination")
            return
        
        # Get all active agents
        try:
            agents = await self.orchestrator.get_all_agents()
            
            if not agents:
                logger.info("No agents to terminate")
                return
            
            logger.info(f"Found {len(agents)} agents to terminate")
            
            # First, ask all agents to stop accepting new work
            await self._prepare_agents_for_shutdown(agents)
            
            # Then terminate each agent
            termination_tasks = []
            for agent in agents:
                # Skip agents that are already stopped or failed
                if agent.status in (AgentStatus.STOPPED, AgentStatus.FAILED):
                    logger.debug(f"Skipping already stopped agent: {agent.id} ({agent.status.value})")
                    continue
                
                # Add to termination tasks
                task = asyncio.create_task(self._terminate_agent(agent.id))
                termination_tasks.append(task)
            
            # Wait for all termination tasks with timeout
            if termination_tasks:
                done, pending = await asyncio.wait(
                    termination_tasks,
                    timeout=self.termination_timeout
                )
                
                # Force terminate any pending tasks
                for task in pending:
                    logger.warning(f"Force cancelling agent termination task that exceeded timeout")
                    task.cancel()
                
                # Process results
                for task in done:
                    try:
                        agent_id, success = await task
                        if success:
                            self.terminated_agents.append(agent_id)
                    except Exception as e:
                        logger.error(f"Error processing agent termination result: {str(e)}")
            
            # If force shutdown, use orchestrator's shutdown method
            if self.shutdown_coordinator.force_shutdown:
                logger.info("Executing orchestrator shutdown with force flag")
                await self.orchestrator.shutdown()
            
            logger.info(f"Agent termination complete. Terminated {len(self.terminated_agents)} agents")
            
        except Exception as e:
            logger.error(f"Error during agent termination: {str(e)}", exc_info=True)
    
    async def _prepare_agents_for_shutdown(self, agents) -> None:
        """
        Prepare agents for shutdown by stopping them from accepting new work.
        
        Args:
            agents: List of agent metadata objects
        """
        logger.info("Preparing agents for shutdown")
        
        prepare_tasks = []
        for agent in agents:
            # Skip agents that are already stopped or failed
            if agent.status in (AgentStatus.STOPPED, AgentStatus.FAILED):
                continue
            
            # Update status to STOPPING to prevent new operations
            try:
                await self.orchestrator.update_agent_status(agent.id, AgentStatus.STOPPING)
                logger.debug(f"Agent {agent.id} prepared for shutdown")
            except Exception as e:
                logger.error(f"Error preparing agent {agent.id} for shutdown: {str(e)}")
    
    async def _terminate_agent(self, agent_id: str) -> tuple:
        """
        Terminate a single agent.
        
        Args:
            agent_id: The ID of the agent to terminate
            
        Returns:
            Tuple of (agent_id, success)
        """
        logger.info(f"Terminating agent: {agent_id}")
        
        try:
            # Use the orchestrator's terminate_agent method
            # This method already implements graceful termination
            force = self.shutdown_coordinator.force_shutdown
            success = await self.orchestrator.terminate_agent(
                agent_id=agent_id,
                timeout=self.termination_timeout / 2,  # Use half the overall timeout
                force=force
            )
            
            if success:
                logger.info(f"Successfully terminated agent: {agent_id}")
            else:
                logger.warning(f"Failed to terminate agent: {agent_id}")
            
            return agent_id, success
            
        except Exception as e:
            logger.error(f"Error terminating agent {agent_id}: {str(e)}")
            return agent_id, False
    
    def get_termination_results(self) -> Dict[str, Any]:
        """
        Get the results of the agent termination process.
        
        Returns:
            Results including terminated agents and status
        """
        return {
            "terminated_agents": self.terminated_agents,
            "total_terminated": len(self.terminated_agents),
        }


# Singleton instance
_agent_terminator_instance = None


def get_agent_terminator(orchestrator: Optional[AgentSwarmOrchestrator] = None) -> AgentTerminator:
    """
    Get or create the singleton agent terminator instance.
    
    Args:
        orchestrator: The agent swarm orchestrator to use
        
    Returns:
        The agent terminator instance
    """
    global _agent_terminator_instance
    if _agent_terminator_instance is None:
        _agent_terminator_instance = AgentTerminator(orchestrator=orchestrator)
    return _agent_terminator_instance 