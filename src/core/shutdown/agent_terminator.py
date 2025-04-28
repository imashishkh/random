"""
AgentTerminator - Responsible for safely terminating trading agents during shutdown
"""
import asyncio
import logging
import time
from typing import Dict, List, Callable, Optional, Any, Set, Awaitable, Union

logger = logging.getLogger(__name__)

class Agent:
    """
    Simplified representation of a trading agent for demonstration.
    In a real system, this would likely be a more complex class from another module.
    """
    def __init__(self, agent_id: str, agent_type: str, name: Optional[str] = None):
        """
        Initialize an Agent object.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_type: Type of agent (e.g., "Trend", "Scalping", "Arbitrage")
            name: Human-readable name for the agent
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.name = name or f"{agent_type}-{agent_id[:8]}"
        self.is_active = True
        self.is_stopping = False
        self.stop_time = None
        
    def get_info(self) -> Dict[str, Any]:
        """Get agent information as a dictionary.
        
        Returns:
            dict: Agent information
        """
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "name": self.name,
            "is_active": self.is_active,
            "is_stopping": self.is_stopping,
            "stop_time": self.stop_time
        }


class AgentTerminator:
    """
    Responsible for safely terminating trading agents during shutdown.
    """
    def __init__(self):
        """Initialize the AgentTerminator."""
        self._agents: Dict[str, Agent] = {}  # agent_id -> Agent
        self._agent_stop_handlers: Dict[str, Callable[[Agent], Awaitable[bool]]] = {}
        self._agent_sources: List[Callable[[], List[Agent]]] = []
        self._last_termination_result: Optional[Dict[str, Any]] = None
        self._agent_priorities: Dict[str, int] = {}  # agent_id -> priority (0-100, higher first)
        
    def register_agent(self, agent: Agent, priority: int = 50) -> None:
        """
        Register an agent for tracking by the agent terminator.
        
        Args:
            agent: Agent object to register
            priority: Priority for shutdown (0-100, higher means stop first)
        """
        self._agents[agent.agent_id] = agent
        self._agent_priorities[agent.agent_id] = max(0, min(100, priority))
        logger.debug(f"Registered agent {agent.agent_id} ({agent.name}) with priority {priority}")
        
    def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent from tracking.
        
        Args:
            agent_id: ID of the agent to unregister
            
        Returns:
            bool: True if the agent was found and unregistered, False otherwise
        """
        if agent_id in self._agents:
            del self._agents[agent_id]
            if agent_id in self._agent_priorities:
                del self._agent_priorities[agent_id]
            if agent_id in self._agent_stop_handlers:
                del self._agent_stop_handlers[agent_id]
            logger.debug(f"Unregistered agent {agent_id}")
            return True
        return False
        
    def register_agent_source(self, source_func: Callable[[], List[Agent]]) -> None:
        """
        Register a function that provides agents from an external source.
        
        Args:
            source_func: Function that returns a list of agents
        """
        self._agent_sources.append(source_func)
        logger.debug("Registered agent source")
        
    def unregister_agent_source(self, source_func: Callable[[], List[Agent]]) -> bool:
        """
        Unregister a previously registered agent source.
        
        Args:
            source_func: The source function to unregister
            
        Returns:
            bool: True if the source was found and unregistered, False otherwise
        """
        if source_func in self._agent_sources:
            self._agent_sources.remove(source_func)
            logger.debug("Unregistered agent source")
            return True
        return False
        
    def register_stop_handler(self, agent_type: str, 
                             handler: Callable[[Agent], Awaitable[bool]]) -> None:
        """
        Register a handler for stopping agents of a specific type.
        
        Args:
            agent_type: Type of agent this handler can stop
            handler: Async function that stops the agent
        """
        self._agent_stop_handlers[agent_type] = handler
        logger.debug(f"Registered stop handler for agent type {agent_type}")
        
    def unregister_stop_handler(self, agent_type: str) -> bool:
        """
        Unregister a previously registered stop handler.
        
        Args:
            agent_type: Type of agent handler to unregister
            
        Returns:
            bool: True if the handler was found and unregistered, False otherwise
        """
        if agent_type in self._agent_stop_handlers:
            del self._agent_stop_handlers[agent_type]
            logger.debug(f"Unregistered stop handler for agent type {agent_type}")
            return True
        return False
        
    def set_agent_priority(self, agent_id: str, priority: int) -> bool:
        """
        Set the shutdown priority for an agent.
        
        Args:
            agent_id: ID of the agent
            priority: Priority (0-100, higher means stop first)
            
        Returns:
            bool: True if the agent was found and priority set, False otherwise
        """
        if agent_id in self._agents:
            self._agent_priorities[agent_id] = max(0, min(100, priority))
            logger.debug(f"Set priority {priority} for agent {agent_id}")
            return True
        return False
        
    async def terminate_all_agents(self) -> bool:
        """
        Terminate all registered agents.
        
        Returns:
            bool: True if all agents were successfully terminated, False otherwise
        """
        # First gather all agents from registered sources
        self._fetch_agents_from_sources()
        
        if not self._agents:
            logger.info("No agents to terminate")
            self._last_termination_result = {
                "success": True,
                "total_agents": 0,
                "terminated_agents": 0,
                "time_taken": 0.0
            }
            return True
            
        start_time = time.time()
        logger.info(f"Starting to terminate {len(self._agents)} agents")
        
        # Sort agents by priority (higher priority first)
        sorted_agents = sorted(
            self._agents.values(),
            key=lambda a: self._agent_priorities.get(a.agent_id, 50),
            reverse=True
        )
        
        # Terminate agents in order
        terminated_count = 0
        for agent in sorted_agents:
            success = await self._terminate_agent(agent)
            if success:
                terminated_count += 1
        
        total_agents = len(self._agents)
        success = terminated_count == total_agents
        
        time_taken = time.time() - start_time
        logger.info(f"Agent termination completed: {terminated_count}/{total_agents} agents terminated "
                    f"in {time_taken:.2f} seconds")
        
        self._last_termination_result = {
            "success": success,
            "total_agents": total_agents,
            "terminated_agents": terminated_count,
            "failed_agents": total_agents - terminated_count,
            "time_taken": time_taken
        }
        
        return success
        
    async def _terminate_agent(self, agent: Agent) -> bool:
        """
        Terminate a single agent.
        
        Args:
            agent: Agent to terminate
            
        Returns:
            bool: True if successfully terminated, False otherwise
        """
        if not agent.is_active:
            return True
            
        agent.is_stopping = True
        
        try:
            # Check if we have a custom handler for this agent type
            if agent.agent_type in self._agent_stop_handlers:
                logger.info(f"Terminating agent {agent.agent_id} ({agent.name}) using custom handler")
                handler = self._agent_stop_handlers[agent.agent_type]
                success = await handler(agent)
            else:
                # Default termination logic
                logger.info(f"Terminating agent {agent.agent_id} ({agent.name}) using default handler")
                # Simulate agent termination
                await asyncio.sleep(0.2)
                success = True
                
            if success:
                agent.is_active = False
                agent.stop_time = time.time()
                logger.info(f"Agent {agent.agent_id} ({agent.name}) terminated successfully")
            else:
                logger.error(f"Failed to terminate agent {agent.agent_id} ({agent.name})")
                
            agent.is_stopping = False
            return success
            
        except Exception as e:
            logger.exception(f"Error terminating agent {agent.agent_id}: {e}")
            agent.is_stopping = False
            return False
            
    def _fetch_agents_from_sources(self) -> None:
        """Fetch agents from all registered sources."""
        for source_func in self._agent_sources:
            try:
                agents = source_func()
                for agent in agents:
                    if agent.agent_id not in self._agents:
                        self._agents[agent.agent_id] = agent
                        # Use default priority for agents from sources
                        if agent.agent_id not in self._agent_priorities:
                            self._agent_priorities[agent.agent_id] = 50
                        logger.debug(f"Added agent {agent.agent_id} from source")
            except Exception as e:
                logger.error(f"Error fetching agents from source: {e}")
                
    def get_agents(self) -> List[Agent]:
        """
        Get all registered agents.
        
        Returns:
            List[Agent]: All currently registered agents
        """
        return list(self._agents.values())
        
    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """
        Get a specific agent by ID.
        
        Args:
            agent_id: ID of the agent to get
            
        Returns:
            Optional[Agent]: The agent if found, None otherwise
        """
        return self._agents.get(agent_id)
        
    def get_last_termination_result(self) -> Optional[Dict[str, Any]]:
        """
        Get the result of the last terminate_all_agents call.
        
        Returns:
            Optional[Dict[str, Any]]: Result of the last termination operation, or None if not called yet
        """
        return self._last_termination_result 