"""
Agent Swarm Orchestrator Engine

This module provides the core implementation of the Agent Swarm Orchestrator,
which manages the lifecycle, health monitoring, and communication of trading agents.
"""

import os
import yaml
import json
import uuid
import asyncio
import logging
import signal
import time
import threading
import sys
from datetime import datetime
from dataclasses import dataclass, field, asdict, replace
from enum import Enum
from typing import Dict, List, Any, Optional, Set, Callable, Awaitable, Union, Tuple

# Import existing health monitor
from .health import get_health_monitor, AgentHealthStatus
from ...utils.logging.logger import get_logger

logger = get_logger()


class AgentStatus(Enum):
    """Status of an agent in the swarm"""
    PENDING = "pending"
    INITIALIZING = "initializing"
    RUNNING = "running"
    DEGRADED = "degraded"
    RESTARTING = "restarting"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class AgentMetadata:
    """
    Immutable agent metadata for thread-safe registry operations.
    
    Using a frozen dataclass ensures that the metadata cannot be modified
    after creation, preventing race conditions in async operations.
    """
    id: str
    name: str
    agent_type: str
    status: AgentStatus
    config: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: Optional[datetime] = None
    task_handle: Optional[asyncio.Task] = None
    health_check_interval: int = 30  # seconds
    restart_attempts: int = 0
    
    # Factory methods for state transitions
    def with_status(self, new_status: AgentStatus) -> 'AgentMetadata':
        """Create a new instance with updated status."""
        return replace(self, status=new_status, updated_at=datetime.now())
    
    def with_heartbeat(self) -> 'AgentMetadata':
        """Create a new instance with updated heartbeat timestamp."""
        return replace(self, last_heartbeat=datetime.now(), updated_at=datetime.now())
    
    def with_task_handle(self, task: asyncio.Task) -> 'AgentMetadata':
        """Create a new instance with updated task handle."""
        return replace(self, task_handle=task, updated_at=datetime.now())
    
    def with_restart_attempt(self) -> 'AgentMetadata':
        """Create a new instance with incremented restart counter."""
        return replace(self, restart_attempts=self.restart_attempts+1, updated_at=datetime.now())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, handling non-serializable fields."""
        data = asdict(self)
        # Remove non-serializable fields
        data.pop('task_handle', None)
        # Convert enums to strings
        data['status'] = self.status.value
        # Convert datetime objects to ISO format strings
        for key in ['created_at', 'updated_at', 'last_heartbeat']:
            if data[key]:
                data[key] = data[key].isoformat()
        return data


class AgentSwarmOrchestrator:
    """
    Orchestrator for managing a swarm of trading agents.
    
    This class provides functionality to manage the lifecycle of multiple
    trading agents, including spawning, monitoring, and terminating agents.
    It also provides health monitoring and automatic restart capabilities.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the agent swarm orchestrator.
        
        Args:
            config_path: Path to configuration file (YAML or JSON)
        """
        # Initialize agent registry with thread-safe lock
        self._registry: Dict[str, AgentMetadata] = {}
        self._registry_lock = asyncio.Lock()
        
        # Load configuration
        self._config = self._load_config(config_path)
        
        # Configure logging
        self._configure_logging()
        
        # Event callbacks for registry state changes
        self._event_callbacks: Dict[str, List[Callable[[str, Any], Awaitable[None]]]] = {
            "agent_registered": [],
            "agent_deregistered": [],
            "agent_status_changed": [],
            "agent_heartbeat": [],
            "agent_error": []
        }
        
        # Flag to track if the orchestrator is running
        self.running = False
        
        # Integrate with existing health monitoring
        self.health_monitor = get_health_monitor()
        
        # Task groups for managing agent tasks
        self._task_groups: Dict[str, Set[asyncio.Task]] = {}
        
        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        logger.info("Agent Swarm Orchestrator initialized")
    
    async def register_agent(self, 
                           agent_id: str, 
                           agent_type: str, 
                           name: str, 
                           config: Dict[str, Any]) -> AgentMetadata:
        """
        Register a new agent with the orchestrator.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_type: Type of agent (technical, execution, etc.)
            name: Human-readable name
            config: Agent-specific configuration
            
        Returns:
            The newly created agent metadata
            
        Raises:
            ValueError: If agent_id already exists
        """
        async with self._registry_lock:
            if agent_id in self._registry:
                raise ValueError(f"Agent with ID '{agent_id}' already exists")
            
            # Validate configuration against schema
            self._validate_agent_config(agent_type, config)
            
            # Create agent metadata
            metadata = AgentMetadata(
                id=agent_id,
                name=name,
                agent_type=agent_type,
                status=AgentStatus.PENDING,
                config=config,
            )
            
            # Add to registry
            self._registry[agent_id] = metadata
            
            # Log and notify
            logger.info(f"Agent registered: {agent_id} ({agent_type})")
            await self._notify_event("agent_registered", agent_id, metadata)
            
            return metadata
    
    async def deregister_agent(self, agent_id: str) -> None:
        """
        Remove an agent from the registry.
        
        Args:
            agent_id: ID of the agent to remove
            
        Raises:
            KeyError: If agent_id does not exist
        """
        async with self._registry_lock:
            if agent_id not in self._registry:
                raise KeyError(f"Agent with ID '{agent_id}' not found")
            
            metadata = self._registry.pop(agent_id)
            
            # Log and notify
            logger.info(f"Agent deregistered: {agent_id}")
            await self._notify_event("agent_deregistered", agent_id, metadata)
    
    async def update_agent_status(self, 
                                agent_id: str, 
                                status: AgentStatus) -> AgentMetadata:
        """
        Update the status of an agent.
        
        Args:
            agent_id: ID of the agent to update
            status: New status
            
        Returns:
            Updated agent metadata
            
        Raises:
            KeyError: If agent_id does not exist
        """
        async with self._registry_lock:
            if agent_id not in self._registry:
                raise KeyError(f"Agent with ID '{agent_id}' not found")
            
            # Get current metadata and create updated version
            current = self._registry[agent_id]
            updated = current.with_status(status)
            
            # Store updated metadata
            self._registry[agent_id] = updated
            
            # Log state change
            logger.info(f"Agent status changed: {agent_id} from {current.status.value} to {status.value}")
            
            # Notify observers
            await self._notify_event("agent_status_changed", agent_id, updated)
            
            return updated
    
    async def record_agent_heartbeat(self, agent_id: str) -> Optional[AgentMetadata]:
        """
        Record a heartbeat from an agent.
        
        Args:
            agent_id: ID of the agent
            
        Returns:
            Updated agent metadata or None if agent not found
        """
        async with self._registry_lock:
            if agent_id not in self._registry:
                logger.warning(f"Heartbeat received for unknown agent: {agent_id}")
                return None
            
            current = self._registry[agent_id]
            updated = current.with_heartbeat()
            
            # Update registry
            self._registry[agent_id] = updated
            
            # Notify observers
            await self._notify_event("agent_heartbeat", agent_id, updated)
            
            return updated
    
    async def get_agent_metadata(self, agent_id: str) -> Optional[AgentMetadata]:
        """
        Get metadata for a specific agent.
        
        Args:
            agent_id: ID of the agent
            
        Returns:
            Agent metadata or None if not found
        """
        async with self._registry_lock:
            return self._registry.get(agent_id)
    
    async def get_agents_by_status(self, status: AgentStatus) -> List[AgentMetadata]:
        """
        Get all agents with a specific status.
        
        Args:
            status: Status to filter by
            
        Returns:
            List of agent metadata matching the status
        """
        async with self._registry_lock:
            return [agent for agent in self._registry.values() if agent.status == status]
    
    async def get_agents_by_type(self, agent_type: str) -> List[AgentMetadata]:
        """
        Get all agents of a specific type.
        
        Args:
            agent_type: Type to filter by
            
        Returns:
            List of agent metadata matching the type
        """
        async with self._registry_lock:
            return [agent for agent in self._registry.values() if agent.agent_type == agent_type]
    
    async def get_all_agents(self) -> List[AgentMetadata]:
        """
        Get all registered agents.
        
        Returns:
            List of all agent metadata
        """
        async with self._registry_lock:
            return list(self._registry.values())
    
    async def on_event(self, event_name: str, callback: Callable[[str, Any], Awaitable[None]]) -> None:
        """
        Register a callback for a specific event.
        
        Args:
            event_name: Name of the event to listen for
            callback: Async function to call when the event occurs
        """
        if event_name not in self._event_callbacks:
            raise ValueError(f"Unknown event: {event_name}")
        
        self._event_callbacks[event_name].append(callback)
        logger.debug(f"Registered callback for event: {event_name}")
    
    async def _notify_event(self, event_name: str, agent_id: str, data: Any) -> None:
        """
        Notify all registered callbacks about an event.
        
        Args:
            event_name: Name of the event
            agent_id: ID of the agent related to the event
            data: Event data
        """
        callbacks = self._event_callbacks.get(event_name, [])
        for callback in callbacks:
            try:
                await callback(agent_id, data)
            except Exception as e:
                logger.error(f"Error in event callback ({event_name}): {str(e)}")
    
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """
        Load configuration from file with environment variable overrides.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Configuration dictionary
        """
        config = {}
        
        # Default configuration
        default_config = {
            "log_level": "INFO",
            "agent_types": {
                "technical_analysis": {"schema": {}},
                "execution": {"schema": {}},
                "coordinator": {"schema": {}},
                "researcher": {"schema": {}}
            },
            "health_check": {
                "interval": 30,  # seconds
                "heartbeat_timeout": 90,  # seconds
                "max_restart_attempts": 3
            }
        }
        
        # Load from file if provided
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                        config = yaml.safe_load(f)
                    elif config_path.endswith('.json'):
                        config = json.load(f)
                    else:
                        raise ValueError(f"Unsupported config file format: {config_path}")
            except Exception as e:
                raise ValueError(f"Error loading configuration from {config_path}: {str(e)}")
        
        # Start with defaults and update with file config
        merged_config = {**default_config, **config}
        
        # Override with environment variables
        log_level = os.environ.get('ORCHESTRATOR_LOG_LEVEL')
        if log_level:
            merged_config['log_level'] = log_level
        
        # Override health check settings from environment
        health_check_interval = os.environ.get('ORCHESTRATOR_HEALTH_CHECK_INTERVAL')
        if health_check_interval:
            merged_config['health_check']['interval'] = int(health_check_interval)
        
        heartbeat_timeout = os.environ.get('ORCHESTRATOR_HEARTBEAT_TIMEOUT')
        if heartbeat_timeout:
            merged_config['health_check']['heartbeat_timeout'] = int(heartbeat_timeout)
        
        max_restart_attempts = os.environ.get('ORCHESTRATOR_MAX_RESTART_ATTEMPTS')
        if max_restart_attempts:
            merged_config['health_check']['max_restart_attempts'] = int(max_restart_attempts)
        
        return merged_config
    
    def _validate_agent_config(self, agent_type: str, config: Dict[str, Any]) -> None:
        """
        Validate agent configuration against schema.
        
        Args:
            agent_type: Type of agent
            config: Configuration to validate
            
        Raises:
            ValueError: If validation fails
        """
        # In a real implementation, this would use JSON Schema validation
        # For now, we'll just check that the agent type is known
        if agent_type not in self._config.get('agent_types', {}):
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        # TODO: Implement full schema validation
        return
    
    def _configure_logging(self) -> None:
        """Configure logging based on configuration."""
        log_level = self._config.get('log_level', 'INFO')
        numeric_level = getattr(logging, log_level.upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError(f'Invalid log level: {log_level}')
        logger.setLevel(numeric_level)
        logger.info(f"Log level set to {log_level}")
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert orchestrator state to a dictionary for serialization.
        
        Returns:
            Dictionary representation of the orchestrator state
        """
        agent_data = {}
        for agent_id, metadata in self._registry.items():
            agent_data[agent_id] = metadata.to_dict()
        
        return {
            "agent_count": len(self._registry),
            "agents": agent_data,
            "running": self.running,
            "config": self._config
        }
    
    async def save_state(self, file_path: str) -> None:
        """
        Save orchestrator state to a file.
        
        Args:
            file_path: Path to save state to
        """
        state = self.to_dict()
        try:
            with open(file_path, 'w') as f:
                json.dump(state, f, indent=2)
            logger.info(f"Orchestrator state saved to {file_path}")
        except Exception as e:
            logger.error(f"Failed to save orchestrator state: {str(e)}")
    
    async def load_state(self, file_path: str) -> None:
        """
        Load orchestrator state from a file.
        
        Args:
            file_path: Path to load state from
        """
        if not os.path.exists(file_path):
            logger.warning(f"State file not found: {file_path}")
            return
        
        try:
            with open(file_path, 'r') as f:
                state = json.load(f)
            
            async with self._registry_lock:
                # Clear existing registry
                self._registry.clear()
                
                # Restore agents (without task handles)
                for agent_id, data in state.get('agents', {}).items():
                    # Convert string status back to enum
                    status_str = data.pop('status', 'PENDING')
                    status = AgentStatus(status_str)
                    
                    # Convert ISO format strings back to datetime objects
                    for key in ['created_at', 'updated_at', 'last_heartbeat']:
                        if data.get(key):
                            data[key] = datetime.fromisoformat(data[key])
                        else:
                            data[key] = None
                    
                    # Create metadata
                    metadata = AgentMetadata(
                        id=agent_id,
                        status=status,
                        **{k: v for k, v in data.items() if k not in ['id', 'status']}
                    )
                    
                    self._registry[agent_id] = metadata
            
            logger.info(f"Loaded {len(self._registry)} agents from {file_path}")
        except Exception as e:
            logger.error(f"Failed to load orchestrator state: {str(e)}")
    
    async def spawn_agent(self, 
                         agent_id: str, 
                         agent_type: str, 
                         name: str, 
                         config: Dict[str, Any],
                         agent_factory: Optional[Callable] = None) -> asyncio.Task:
        """
        Spawn a new agent as an asyncio task.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_type: Type of agent (researcher, executor, etc.)
            name: Human-readable name
            config: Agent-specific configuration
            agent_factory: Optional factory function to create the agent instance
            
        Returns:
            The created asyncio Task for the agent
            
        Raises:
            ValueError: If agent_id already exists
            RuntimeError: If agent creation fails
        """
        # First register the agent to get metadata
        metadata = await self.register_agent(
            agent_id=agent_id,
            agent_type=agent_type,
            name=name,
            config=config
        )
        
        # Update agent status to initializing
        metadata = await self.update_agent_status(
            agent_id=agent_id,
            status=AgentStatus.INITIALIZING
        )
        
        # Create a task group for this agent if it doesn't exist
        if agent_id not in self._task_groups:
            self._task_groups[agent_id] = set()
        
        try:
            # Create the main agent task
            task = asyncio.create_task(
                self._run_agent_lifecycle(
                    agent_id=agent_id,
                    agent_type=agent_type,
                    config=config,
                    agent_factory=agent_factory
                ),
                name=f"agent:{agent_id}"
            )
            
            # Store task in task group
            self._task_groups[agent_id].add(task)
            
            # Update metadata with task handle
            async with self._registry_lock:
                metadata = self._registry[agent_id]
                self._registry[agent_id] = metadata.with_task_handle(task)
            
            # Add done callback to handle task completion
            task.add_done_callback(
                lambda t, aid=agent_id: asyncio.create_task(
                    self._handle_agent_task_done(aid, t)
                )
            )
            
            logger.info(f"Agent spawned: {agent_id} ({agent_type})")
            return task
            
        except Exception as e:
            logger.error(f"Failed to spawn agent {agent_id}: {str(e)}", exc_info=True)
            await self.update_agent_status(agent_id, AgentStatus.FAILED)
            await self._notify_event("agent_error", agent_id, {"error": str(e), "phase": "spawn"})
            raise RuntimeError(f"Failed to spawn agent {agent_id}: {str(e)}") from e
    
    async def _run_agent_lifecycle(self,
                                  agent_id: str,
                                  agent_type: str,
                                  config: Dict[str, Any],
                                  agent_factory: Optional[Callable] = None) -> None:
        """
        Run the agent lifecycle from initialization to termination.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_type: Type of agent
            config: Agent-specific configuration
            agent_factory: Optional factory function to create the agent instance
        """
        try:
            # Import agent factory if not provided
            if agent_factory is None:
                from src.agents.factory import AgentFactory
                agent_factory = AgentFactory.create_agent
            
            # Create agent instance
            agent = await agent_factory(
                agent_id=agent_id,
                agent_type=agent_type,
                **config
            )
            
            # Mark agent as running
            await self.update_agent_status(agent_id, AgentStatus.RUNNING)
            
            # Set up periodic heartbeat
            heartbeat_task = asyncio.create_task(
                self._agent_heartbeat_loop(agent_id),
                name=f"heartbeat:{agent_id}"
            )
            
            # Add to task group
            self._task_groups[agent_id].add(heartbeat_task)
            
            # Run the agent's main task
            logger.info(f"Agent {agent_id} starting main execution")
            await agent.run()
            
            # If we reach here without exceptions, agent completed normally
            logger.info(f"Agent {agent_id} completed successfully")
            await self.update_agent_status(agent_id, AgentStatus.STOPPED)
            
        except asyncio.CancelledError:
            # Handle task cancellation (normal termination)
            logger.info(f"Agent {agent_id} task cancelled")
            await self.update_agent_status(agent_id, AgentStatus.STOPPING)
            
        except Exception as e:
            # Handle agent execution error
            error_msg = f"Agent {agent_id} failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            await self.update_agent_status(agent_id, AgentStatus.FAILED)
            await self._notify_event("agent_error", agent_id, {"error": str(e), "phase": "execution"})
            
            # Attempt automatic restart if configured
            max_restarts = self._config.get("health_check", {}).get("max_restart_attempts", 3)
            async with self._registry_lock:
                metadata = self._registry.get(agent_id)
                if metadata and metadata.restart_attempts < max_restarts:
                    logger.info(f"Attempting to restart agent {agent_id} (attempt {metadata.restart_attempts + 1}/{max_restarts})")
                    # Schedule restart with exponential backoff
                    backoff_time = 2 ** metadata.restart_attempts
                    restart_task = asyncio.create_task(
                        self._schedule_agent_restart(agent_id, backoff_time),
                        name=f"restart:{agent_id}"
                    )
                    self._task_groups[agent_id].add(restart_task)
    
    async def _agent_heartbeat_loop(self, agent_id: str) -> None:
        """
        Periodically record agent heartbeats.
        
        Args:
            agent_id: Agent ID to record heartbeats for
        """
        try:
            # Get heartbeat interval from config
            interval = self._config.get("health_check", {}).get("interval", 30)
            
            while True:
                # Record heartbeat
                await self.record_agent_heartbeat(agent_id)
                
                # Sleep until next heartbeat
                await asyncio.sleep(interval)
                
        except asyncio.CancelledError:
            # Normal cancellation during shutdown
            pass
        except Exception as e:
            logger.error(f"Error in heartbeat loop for agent {agent_id}: {str(e)}", exc_info=True)
    
    async def _schedule_agent_restart(self, agent_id: str, delay: float) -> None:
        """
        Schedule an agent restart after a delay.
        
        Args:
            agent_id: Agent ID to restart
            delay: Delay in seconds before restarting
        """
        try:
            # Wait for the backoff period
            await asyncio.sleep(delay)
            
            # Update restart counter and agent status
            async with self._registry_lock:
                if agent_id not in self._registry:
                    logger.warning(f"Cannot restart agent {agent_id}: agent no longer registered")
                    return
                
                metadata = self._registry[agent_id]
                updated_metadata = metadata.with_restart_attempt()
                self._registry[agent_id] = updated_metadata
            
            await self.update_agent_status(agent_id, AgentStatus.RESTARTING)
            
            # Get agent configuration
            metadata = await self.get_agent_metadata(agent_id)
            if not metadata:
                logger.warning(f"Cannot restart agent {agent_id}: metadata not found")
                return
            
            # Spawn a new agent task
            await self.spawn_agent(
                agent_id=agent_id,
                agent_type=metadata.agent_type,
                name=metadata.name,
                config=metadata.config
            )
            
        except asyncio.CancelledError:
            # Normal cancellation during shutdown
            pass
        except Exception as e:
            logger.error(f"Failed to restart agent {agent_id}: {str(e)}", exc_info=True)
            await self.update_agent_status(agent_id, AgentStatus.FAILED)
    
    async def _handle_agent_task_done(self, agent_id: str, task: asyncio.Task) -> None:
        """
        Handle agent task completion.
        
        Args:
            agent_id: Agent ID of the completed task
            task: The completed task
        """
        try:
            # Remove task from task group
            if agent_id in self._task_groups:
                self._task_groups[agent_id].discard(task)
            
            # Process task result/exception
            if task.cancelled():
                logger.info(f"Agent {agent_id} task was cancelled")
            else:
                exception = task.exception()
                if exception:
                    logger.error(f"Agent {agent_id} task failed with exception: {str(exception)}")
                else:
                    logger.info(f"Agent {agent_id} task completed successfully")
            
        except Exception as e:
            logger.error(f"Error handling task completion for agent {agent_id}: {str(e)}", exc_info=True)
    
    async def terminate_agent(self, agent_id: str, timeout: float = 5.0, force: bool = False) -> bool:
        """
        Terminate an agent by cancelling its tasks.
        
        Args:
            agent_id: ID of the agent to terminate
            timeout: Timeout in seconds to wait for graceful termination
            force: If True, forcefully terminate even if timeout occurs
            
        Returns:
            True if termination was successful, False otherwise
            
        Raises:
            KeyError: If agent_id does not exist
        """
        # Check if agent exists
        metadata = await self.get_agent_metadata(agent_id)
        if not metadata:
            raise KeyError(f"Agent with ID '{agent_id}' not found")
        
        if metadata.status in (AgentStatus.STOPPED, AgentStatus.FAILED):
            logger.info(f"Agent {agent_id} already terminated (status: {metadata.status.value})")
            return True
        
        # Update agent status to stopping
        await self.update_agent_status(agent_id, AgentStatus.STOPPING)
        
        # Cancel all tasks in the agent's task group
        tasks = set()
        if agent_id in self._task_groups:
            tasks = self._task_groups[agent_id].copy()
        
        if not tasks:
            logger.warning(f"No tasks found for agent {agent_id}")
            await self.update_agent_status(agent_id, AgentStatus.STOPPED)
            return True
        
        # Cancel all tasks
        for task in tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        try:
            await asyncio.wait(tasks, timeout=timeout)
        except Exception as e:
            logger.error(f"Error waiting for agent {agent_id} tasks to cancel: {str(e)}", exc_info=True)
        
        # Check if all tasks completed
        pending_tasks = [t for t in tasks if not t.done()]
        
        if pending_tasks and force:
            logger.warning(f"Force terminating {len(pending_tasks)} tasks for agent {agent_id}")
            # We can't do much more to force termination in asyncio,
            # but we can mark the agent as stopped
        
        # Clean up task group
        if agent_id in self._task_groups:
            self._task_groups[agent_id].clear()
        
        # Mark agent as stopped
        await self.update_agent_status(agent_id, AgentStatus.STOPPED)
        
        success = len(pending_tasks) == 0 or force
        logger.info(f"Agent {agent_id} termination {'successful' if success else 'failed'}")
        return success
    
    async def run_swarm(self, agent_configs: List[Dict[str, Any]]) -> Dict[str, asyncio.Task]:
        """
        Run a swarm of agents concurrently.
        
        Args:
            agent_configs: List of agent configurations with keys:
                - agent_id: Unique identifier for the agent
                - agent_type: Type of agent
                - name: Human-readable name
                - config: Agent-specific configuration
                
        Returns:
            Dictionary mapping agent IDs to their tasks
        """
        self.running = True
        tasks = {}
        
        # Use asyncio.TaskGroup in Python 3.11+, gather for earlier versions
        if sys.version_info >= (3, 11):
            async with asyncio.TaskGroup() as tg:
                for config in agent_configs:
                    agent_id = config.get('agent_id')
                    if not agent_id:
                        logger.error("Missing agent_id in config")
                        continue
                    
                    task = await self.spawn_agent(
                        agent_id=agent_id,
                        agent_type=config.get('agent_type', 'generic'),
                        name=config.get('name', f"Agent-{agent_id}"),
                        config=config.get('config', {})
                    )
                    tasks[agent_id] = task
        else:
            # For Python 3.10 and below
            spawn_tasks = []
            for config in agent_configs:
                agent_id = config.get('agent_id')
                if not agent_id:
                    logger.error("Missing agent_id in config")
                    continue
                
                spawn_coro = self.spawn_agent(
                    agent_id=agent_id,
                    agent_type=config.get('agent_type', 'generic'),
                    name=config.get('name', f"Agent-{agent_id}"),
                    config=config.get('config', {})
                )
                spawn_tasks.append(spawn_coro)
            
            # Wait for all agents to spawn
            if spawn_tasks:
                results = await asyncio.gather(*spawn_tasks, return_exceptions=True)
                
                # Process results
                for i, result in enumerate(results):
                    agent_id = agent_configs[i].get('agent_id')
                    if isinstance(result, Exception):
                        logger.error(f"Failed to spawn agent {agent_id}: {str(result)}")
                    else:
                        tasks[agent_id] = result
        
        return tasks
    
    async def shutdown(self, 
                     reason: str = "requested", 
                     force: bool = False, 
                     timeout: Optional[float] = None) -> bool:
        """
        Gracefully shut down the orchestrator and all managed resources.
        
        This method implements a comprehensive shutdown process:
        1. Persists orchestrator state
        2. Terminates all managed agents
        3. Cleans up resources
        4. Verifies shutdown completion
        5. Generates status report
        
        Args:
            reason: Reason for shutdown
            force: If True, forcefully shutdown even if phases fail
            timeout: Maximum time to wait for shutdown (None for default timeouts)
            
        Returns:
            True if shutdown was successful, False otherwise
        """
        # Import components (here to avoid circular imports)
        from .shutdown_manager import OrchestratorShutdownManager, ShutdownPhase
        from .resource_cleanup import ResourceCleanupRegistry
        from .shutdown_verifier import ShutdownVerifier
        
        if not self.running:
            logger.info("Orchestrator already shut down")
            return True
        
        logger.info(f"Initiating orchestrator shutdown: reason='{reason}', force={force}")
        
        # Create shutdown manager
        shutdown_manager = OrchestratorShutdownManager(
            report_dir=os.path.join(
                os.getcwd(), 'data', 'reports', 'shutdown'
            ),
            state_dir=os.path.join(
                os.getcwd(), 'data', 'state'
            )
        )
        
        # Register state persistence
        shutdown_manager.register_phase_callback(
            ShutdownPhase.STATE_PERSISTENCE,
            self._persist_state_for_shutdown
        )
        
        # Register agent termination
        shutdown_manager.register_phase_callback(
            ShutdownPhase.AGENT_TERMINATION,
            self._terminate_all_agents_for_shutdown
        )
        
        # Register resource cleanup
        shutdown_manager.register_phase_callback(
            ShutdownPhase.RESOURCE_CLEANUP,
            self._cleanup_resources_for_shutdown
        )
        
        # Register verification
        shutdown_manager.register_phase_callback(
            ShutdownPhase.VERIFICATION,
            self._verify_shutdown_completion
        )
        
        # Set running to false to prevent new operations
        self.running = False
        
        # Execute shutdown process
        success = await shutdown_manager.shutdown(
            reason=reason,
            force=force,
            timeout=timeout
        )
        
        logger.info(f"Orchestrator shutdown {'succeeded' if success else 'failed'}")
        
        return success
        
    async def _persist_state_for_shutdown(self) -> bool:
        """
        Persist orchestrator state before shutdown.
        
        Returns:
            True if state was successfully persisted, False otherwise
        """
        try:
            logger.info("Persisting orchestrator state before shutdown")
            
            # Create state directory if needed
            state_dir = os.path.join(os.getcwd(), 'data', 'state')
            os.makedirs(state_dir, exist_ok=True)
            
            # Generate timestamp for filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            state_file = os.path.join(state_dir, f'orchestrator_state_{timestamp}.json')
            
            # Save state to temporary file first for atomic write
            temp_file = f"{state_file}.temp"
            await self.save_state(temp_file)
            
            # Rename for atomic operation
            os.rename(temp_file, state_file)
            
            logger.info(f"Orchestrator state saved to {state_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to persist orchestrator state: {str(e)}", exc_info=True)
            return False
    
    async def _terminate_all_agents_for_shutdown(self) -> bool:
        """
        Terminate all agents during shutdown.
        
        Returns:
            True if all agents were terminated successfully, False otherwise
        """
        try:
            # Get all active agents
            agents = await self.get_all_agents()
            
            if not agents:
                logger.info("No agents to terminate")
                return True
            
            logger.info(f"Terminating {len(agents)} agents for shutdown")
            
            # Track success status
            success_count = 0
            
            # Terminate all agents
            terminate_tasks = []
            for agent in agents:
                if agent.status not in (AgentStatus.STOPPED, AgentStatus.FAILED):
                    task = asyncio.create_task(
                        self.terminate_agent(
                            agent.id, 
                            force=True, 
                            timeout=10.0
                        ),
                        name=f"terminate_{agent.id}"
                    )
                    terminate_tasks.append((agent.id, task))
                else:
                    success_count += 1
            
            # Wait for all terminations
            if terminate_tasks:
                for agent_id, task in terminate_tasks:
                    try:
                        result = await task
                        if result:
                            success_count += 1
                        else:
                            logger.warning(f"Agent {agent_id} termination failed")
                    except Exception as e:
                        logger.error(f"Error terminating agent {agent_id}: {str(e)}")
            
            # Report results
            success_rate = success_count / len(agents) if agents else 1.0
            logger.info(
                f"Agent termination completed: {success_count}/{len(agents)} successful "
                f"({success_rate:.1%})"
            )
            
            # Consider successful if all agents terminated or if at least 90% did
            return success_count == len(agents) or success_rate >= 0.9
            
        except Exception as e:
            logger.error(f"Error during agent termination: {str(e)}", exc_info=True)
            return False
    
    async def _cleanup_resources_for_shutdown(self) -> bool:
        """
        Clean up resources during shutdown.
        
        Returns:
            True if all resources were cleaned up successfully, False otherwise
        """
        try:
            from .resource_cleanup import ResourceCleanupRegistry
            
            # Create resource registry
            cleanup_registry = ResourceCleanupRegistry()
            
            # Register task groups
            for agent_id, task_group in list(self._task_groups.items()):
                await cleanup_registry.register(
                    resource_type="task_group",
                    resource=task_group,
                    cleanup_fn=self._cleanup_task_group,
                    priority=10  # High priority
                )
            
            # Register event callbacks
            await cleanup_registry.register(
                resource_type="event_callbacks",
                resource=self._event_callbacks,
                cleanup_fn=self._cleanup_event_callbacks,
                priority=5  # Medium priority
            )
            
            # Register registry
            await cleanup_registry.register(
                resource_type="registry",
                resource=self._registry,
                cleanup_fn=self._cleanup_registry,
                priority=1  # Low priority (cleanup last)
            )
            
            # Perform cleanup
            cleanup_results = await cleanup_registry.cleanup_all(timeout=20.0)
            
            # Get summary
            summary = cleanup_registry.get_cleanup_summary()
            
            # Log results
            logger.info(
                f"Resource cleanup completed: "
                f"{summary['successful']}/{summary['total_resources']} successful "
                f"({summary['success_rate']:.1%})"
            )
            
            # Consider successful if all resources cleaned up or if at least 90% did
            return summary['success_rate'] >= 0.9
            
        except Exception as e:
            logger.error(f"Error during resource cleanup: {str(e)}", exc_info=True)
            return False
    
    async def _verify_shutdown_completion(self) -> bool:
        """
        Verify that shutdown is complete.
        
        Returns:
            True if shutdown is verified as complete, False otherwise
        """
        try:
            from .shutdown_verifier import ShutdownVerifier
            
            # Create verifier
            verifier = ShutdownVerifier()
            
            # Register verifications
            await verifier.register_verification(
                component_id="orchestrator",
                verification_type="system",
                verification_fn=self._verify_orchestrator_stopped
            )
            
            await verifier.register_verification(
                component_id="agents",
                verification_type="process",
                verification_fn=self._verify_all_agents_stopped
            )
            
            await verifier.register_verification(
                component_id="tasks",
                verification_type="resource",
                verification_fn=self._verify_no_running_tasks
            )
            
            # Perform verification
            verification_results = await verifier.verify_all_components(
                timeout=10.0,
                retry_count=3
            )
            
            # Get summary
            summary = verifier.get_verification_summary()
            
            # Log results
            logger.info(
                f"Shutdown verification completed: "
                f"{summary['verified_components']}/{summary['total_components']} verified "
                f"({summary['verification_rate']:.1%})"
            )
            
            # Consider successful if all components verified
            return summary['verification_rate'] == 1.0
            
        except Exception as e:
            logger.error(f"Error during shutdown verification: {str(e)}", exc_info=True)
            return False
    
    # Resource cleanup handlers
    
    async def _cleanup_task_group(self, task_group: Set[asyncio.Task]) -> bool:
        """
        Clean up a task group.
        
        Args:
            task_group: Set of tasks to clean up
            
        Returns:
            True if cleanup was successful, False otherwise
        """
        try:
            # Copy to avoid modification during iteration
            tasks = list(task_group)
            
            # Cancel any tasks that are still running
            for task in tasks:
                if not task.done() and not task.cancelled():
                    task.cancel()
            
            # Wait for tasks to complete
            if tasks:
                try:
                    await asyncio.wait(tasks, timeout=2.0)
                except Exception:
                    pass
            
            # Clear the task group
            task_group.clear()
            
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up task group: {str(e)}")
            return False
    
    async def _cleanup_event_callbacks(self, callbacks: Dict[str, List[Callable]]) -> bool:
        """
        Clean up event callbacks.
        
        Args:
            callbacks: Dictionary of event callbacks
            
        Returns:
            True if cleanup was successful, False otherwise
        """
        try:
            for event_type in callbacks:
                callbacks[event_type].clear()
            
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up event callbacks: {str(e)}")
            return False
    
    async def _cleanup_registry(self, registry: Dict[str, Any]) -> bool:
        """
        Clean up agent registry.
        
        Args:
            registry: Agent registry to clean up
            
        Returns:
            True if cleanup was successful, False otherwise
        """
        try:
            # Under lock to avoid concurrent access
            async with self._registry_lock:
                registry.clear()
            
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up registry: {str(e)}")
            return False
    
    # Verification handlers
    
    async def _verify_orchestrator_stopped(self) -> bool:
        """
        Verify that orchestrator is stopped.
        
        Returns:
            True if orchestrator is stopped, False otherwise
        """
        return not self.running
    
    async def _verify_all_agents_stopped(self) -> bool:
        """
        Verify that all agents are stopped.
        
        Returns:
            True if all agents are stopped, False otherwise
        """
        async with self._registry_lock:
            for agent_id, metadata in self._registry.items():
                if metadata.status not in (AgentStatus.STOPPED, AgentStatus.FAILED):
                    logger.warning(f"Agent {agent_id} still active: {metadata.status.value}")
                    return False
        
        return True
    
    async def _verify_no_running_tasks(self) -> bool:
        """
        Verify that no tasks are running.
        
        Returns:
            True if no tasks are running, False otherwise
        """
        for agent_id, task_group in self._task_groups.items():
            active_tasks = [t for t in task_group if not t.done() and not t.cancelled()]
            if active_tasks:
                logger.warning(f"Agent {agent_id} still has {len(active_tasks)} active tasks")
                return False
        
        return True
    
    def _setup_signal_handlers(self) -> None:
        """
        Set up signal handlers for graceful shutdown.
        """
        # Only set up in main thread
        if threading.current_thread() is not threading.main_thread():
            return
        
        # Set up signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                # Remove any existing handlers
                signal.signal(sig, signal.SIG_DFL)
                
                # Add our handler
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
        logger.info(f"Received {sig_name}, scheduling graceful shutdown...")
        
        # Schedule shutdown in the event loop
        if asyncio.get_event_loop().is_running():
            asyncio.create_task(self.shutdown())
        else:
            # If event loop is not running, we can't do much
            logger.warning(f"Event loop not running, can't schedule graceful shutdown for {sig_name}")
            sys.exit(1)


# Singleton instance
_orchestrator_instance = None


def get_orchestrator(config_path: Optional[str] = None) -> AgentSwarmOrchestrator:
    """
    Get or create the singleton orchestrator instance.
    
    Args:
        config_path: Optional path to configuration file
        
    Returns:
        The orchestrator instance
    """
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = AgentSwarmOrchestrator(config_path=config_path)
    return _orchestrator_instance 