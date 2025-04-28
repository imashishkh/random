"""
Process Manager for Async Agent Orchestration

This module provides the ProcessManager class for orchestrating concurrent
agent execution using asyncio.TaskGroup for structured concurrency.
"""

import asyncio
import functools
import logging
import signal
import time
from typing import Dict, List, Set, Tuple, Optional, Any, Callable, Union, Type

from .base_agent import BaseAgent
from .factory import AgentFactory
from .risk import RiskAwareAgent
from ...utils.logging.logger import get_logger
from .health import AgentHealthMonitor

from .error_handling import RecoverableError, NonRecoverableError, ErrorCategory
from .shutdown_coordinator import ShutdownCoordinator
from .agent_wrapper import execute_agent_with_monitoring, create_agent_task

logger = get_logger()


class ProcessManager:
    """
    Process manager for coordinating multiple agent processes using asyncio.TaskGroup.
    
    This class implements the agent swarm orchestrator using structured concurrency,
    with robust error handling and graceful shutdown procedures.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the process manager.
        
        Args:
            config: Configuration dictionary for the process manager
        """
        self.config = config or {}
        self.active_agents: Dict[str, BaseAgent] = {}
        self.running_tasks: Set[asyncio.Task] = set()
        self.agent_configs: Dict[str, Dict[str, Any]] = {}
        
        # Initialize health monitoring
        self.health_monitor = AgentHealthMonitor()
        
        # Create shutdown coordinator
        self.shutdown_coordinator = ShutdownCoordinator()
        
        # Register the shutdown event from the coordinator
        self.shutdown_event = self.shutdown_coordinator.shutdown_event
        
        # Initialize metrics
        self.metrics: Dict[str, Any] = {
            "agent_count": 0,
            "errors": 0,
            "start_time": None,
            "agents": {}
        }
        
        # Task group context manager for Python 3.11+
        self._task_group_context = None
        
        logger.info("ProcessManager initialized")
    
    async def start(self) -> None:
        """
        Start the process manager and register signal handlers.
        
        This method initializes the health monitoring system and sets up
        signal handlers for graceful shutdown.
        """
        # Record start time
        self.metrics["start_time"] = time.time()
        
        # Register signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(
                    self.shutdown_coordinator.initiate_shutdown(s)
                )
            )
        
        # Start the health monitoring system
        await self.health_monitor.start_monitoring()
        
        logger.info("ProcessManager started")
    
    async def spawn_agent(
        self,
        agent_type: str,
        agent_id: str = None,
        **kwargs
    ) -> str:
        """
        Spawn a new agent process and add it to the managed task group.
        
        Args:
            agent_type: Type of agent to create (researcher, planner, executor, etc.)
            agent_id: Unique identifier for the agent (generated if not provided)
            **kwargs: Additional parameters for agent initialization
            
        Returns:
            The agent_id of the created agent
        """
        # Create the agent through the factory pattern
        agent = AgentFactory.create_agent(
            agent_type=agent_type,
            agent_id=agent_id,
            **kwargs
        )
        
        # Get the agent_id (might have been generated if not provided)
        agent_id = agent.agent_id
        
        # Store agent reference and config
        self.active_agents[agent_id] = agent
        self.agent_configs[agent_id] = {
            "agent_type": agent_type,
            "agent_id": agent_id,
            **kwargs
        }
        
        # Register with health monitoring
        self.health_monitor.register_agent(agent)
        
        # Register with shutdown coordinator
        self.shutdown_coordinator.register_agent(agent_id, agent)
        
        # Create and start the agent task
        task = asyncio.create_task(
            execute_agent_with_monitoring(
                agent=agent,
                shutdown_event=self.shutdown_event,
                agent_metrics_callback=self._update_agent_metrics
            ),
            name=f"agent:{agent_id}"
        )
        
        # Add task completion callback
        task.add_done_callback(
            functools.partial(self._handle_task_completion, agent_id=agent_id)
        )
        
        # Store task reference
        self.running_tasks.add(task)
        
        # Register with shutdown coordinator
        self.shutdown_coordinator.register_task(task)
        
        # Update metrics
        self.metrics["agent_count"] += 1
        self.metrics["agents"][agent_id] = {
            "type": agent_type,
            "status": "starting",
            "start_time": time.time()
        }
        
        logger.info(f"Agent {agent_id} of type {agent_type} spawned successfully")
        return agent_id
    
    async def spawn_multiple_agents(
        self,
        agent_configs: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Spawn multiple agents concurrently using TaskGroup for structured concurrency.
        
        This method uses Python 3.11+ TaskGroup to ensure structured concurrency,
        automatically cancelling all tasks if any one fails.
        
        Args:
            agent_configs: List of agent configurations, each containing at least
                          'agent_type' and optionally 'agent_id'
            
        Returns:
            List of agent IDs that were spawned
        """
        agent_ids = []
        
        # Using Python 3.11+ TaskGroup
        async with asyncio.TaskGroup() as tg:
            # Store the task group context for potential later use
            self._task_group_context = tg
            
            for config in agent_configs:
                agent_type = config.pop("agent_type")
                agent_id = config.pop("agent_id", None)
                
                # Create the agent through the factory pattern
                agent = AgentFactory.create_agent(
                    agent_type=agent_type,
                    agent_id=agent_id,
                    **config
                )
                
                # Get the agent_id (might have been generated if not provided)
                agent_id = agent.agent_id
                agent_ids.append(agent_id)
                
                # Store agent reference and config
                self.active_agents[agent_id] = agent
                self.agent_configs[agent_id] = {
                    "agent_type": agent_type,
                    "agent_id": agent_id,
                    **config
                }
                
                # Register with health monitoring
                self.health_monitor.register_agent(agent)
                
                # Register with shutdown coordinator
                self.shutdown_coordinator.register_agent(agent_id, agent)
                
                # Create task in the task group
                task = tg.create_task(
                    execute_agent_with_monitoring(
                        agent=agent,
                        shutdown_event=self.shutdown_event,
                        agent_metrics_callback=self._update_agent_metrics
                    ),
                    name=f"agent:{agent_id}"
                )
                
                # Store task reference
                self.running_tasks.add(task)
                
                # Register with shutdown coordinator
                self.shutdown_coordinator.register_task(task)
                
                # Update metrics
                self.metrics["agent_count"] += 1
                self.metrics["agents"][agent_id] = {
                    "type": agent_type,
                    "status": "starting",
                    "start_time": time.time()
                }
                
                logger.info(f"Agent {agent_id} of type {agent_type} added to task group")
        
        # At this point, all tasks have completed (or an exception was raised)
        self._task_group_context = None
        
        return agent_ids
    
    async def create_trading_agent(
        self,
        agent_type: str,
        agent_id: str = None,
        **kwargs
    ) -> RiskAwareAgent:
        """
        Create a trading agent with proper risk management integration.
        
        Args:
            agent_type: Type of agent to create
            agent_id: Unique identifier for the agent
            **kwargs: Additional parameters for agent initialization
            
        Returns:
            Initialized trading agent with risk management
            
        Raises:
            ValueError: If the created agent doesn't inherit from RiskAwareAgent
        """
        # Create the agent through the factory pattern
        agent = AgentFactory.create_agent(
            agent_type=agent_type,
            agent_id=agent_id,
            **kwargs
        )
        
        # Validate that the agent has proper risk management
        if not isinstance(agent, RiskAwareAgent):
            raise ValueError(
                f"Trading agent {agent.agent_id} of type {agent_type} must inherit from RiskAwareAgent"
            )
        
        return agent
    
    def _handle_task_completion(self, task: asyncio.Task, agent_id: str) -> None:
        """
        Handle completion of an agent task, whether successful or due to error.
        
        Args:
            task: The completed task
            agent_id: ID of the agent associated with the task
        """
        # Remove task from tracking sets
        self.running_tasks.discard(task)
        self.shutdown_coordinator.unregister_task(task)
        
        # Handle task result/exception
        if task.cancelled():
            logger.info(f"Agent {agent_id} task was cancelled")
            self._update_agent_metrics(agent_id, {"status": "cancelled"})
        elif task.exception():
            error = task.exception()
            logger.error(f"Agent {agent_id} task failed with exception: {error}")
            self._update_agent_metrics(
                agent_id, 
                {"status": "failed", "error": str(error)}
            )
        else:
            logger.info(f"Agent {agent_id} task completed successfully")
            self._update_agent_metrics(agent_id, {"status": "completed"})
            
        # Unregister agent from monitoring and shutdown coordinator
        self.health_monitor.unregister_agent(agent_id)
        self.shutdown_coordinator.unregister_agent(agent_id)
        
        # Remove agent reference
        self.active_agents.pop(agent_id, None)
        self.agent_configs.pop(agent_id, None)
    
    def _update_agent_metrics(self, agent_id: str, metrics_update: Dict[str, Any]) -> None:
        """
        Update metrics for an agent.
        
        Args:
            agent_id: ID of the agent to update
            metrics_update: Dictionary of metrics to update
        """
        if agent_id in self.metrics["agents"]:
            self.metrics["agents"][agent_id].update(metrics_update)
        
        # If this is an error, increment the global error counter
        if "error" in metrics_update:
            self.metrics["errors"] += 1
    
    async def restart_agent(self, agent_id: str) -> Optional[str]:
        """
        Restart a failed or terminated agent.
        
        Args:
            agent_id: ID of the agent to restart
            
        Returns:
            New agent ID if successful, None if agent config not found
            
        Raises:
            RuntimeError: If the agent is still running
        """
        # Check if agent is still running
        if agent_id in self.active_agents:
            raise RuntimeError(f"Cannot restart agent {agent_id} - still running")
        
        # Check if we have the agent's configuration
        if agent_id not in self.agent_configs:
            logger.warning(f"Cannot restart agent {agent_id} - configuration not found")
            return None
        
        # Get the original configuration
        config = self.agent_configs[agent_id].copy()
        
        # Extract the agent type
        agent_type = config.pop("agent_type")
        
        # Generate a new agent ID to avoid conflicts
        orig_id = config.pop("agent_id", agent_id)
        new_id = f"{orig_id}_restarted_{int(time.time())}"
        
        logger.info(f"Restarting agent {orig_id} with new ID {new_id}")
        
        # Spawn the agent with the new ID
        return await self.spawn_agent(agent_type, new_id, **config)
    
    async def shutdown(self, timeout: float = 30.0) -> bool:
        """
        Shutdown all agents gracefully within the specified timeout.
        
        Args:
            timeout: Maximum time to wait for clean shutdown in seconds
            
        Returns:
            True if shutdown was clean, False if some tasks were forced to cancel
        """
        logger.info(f"Shutting down ProcessManager with {timeout}s timeout")
        
        # Initiate shutdown if not already in progress
        if not self.shutdown_event.is_set():
            await self.shutdown_coordinator.initiate_shutdown()
        
        # Wait for shutdown to complete
        result = await self.shutdown_coordinator.wait_for_shutdown(timeout)
        
        # Stop health monitoring
        await self.health_monitor.stop_monitoring()
        
        # Update final metrics
        self.metrics["end_time"] = time.time()
        self.metrics["duration"] = self.metrics["end_time"] - self.metrics["start_time"]
        
        logger.info("ProcessManager shutdown completed")
        return result
    
    def get_agent_metrics(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get metrics for a specific agent or all agents.
        
        Args:
            agent_id: ID of the agent to get metrics for, or None for all agents
            
        Returns:
            Dictionary of agent metrics
        """
        if agent_id is not None:
            return self.metrics["agents"].get(agent_id, {})
        else:
            return self.metrics
    
    def get_agent_health(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get health status for a specific agent or all agents.
        
        Args:
            agent_id: ID of the agent to get health for, or None for all agents
            
        Returns:
            Dictionary of agent health metrics
        """
        if agent_id is not None:
            return self.health_monitor.get_agent_health(agent_id) or {}
        else:
            return self.health_monitor.get_all_health_metrics() 