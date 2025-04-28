"""
Base Agent Framework

This module provides the foundational Agent class that integrates with LangChain
and includes memory capabilities, tool integration, and execution management.
"""

import time
import uuid
import abc
import asyncio
import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Union, Callable, Tuple

from langchain.schema import BaseMessage, AgentAction, AgentFinish
from langchain.schema.runnable import Runnable, RunnableConfig
from langchain.agents import AgentExecutor, BaseSingleActionAgent
from langchain.tools import BaseTool as Tool
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
from langchain.callbacks.base import BaseCallbackManager
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.tracers import LangChainTracer

from .memory.memory import AgentMemory
from .state.base import BaseState, create_empty_state, update_state_timestamp
from .health import get_health_monitor
from ..llm.client import get_llm_model
from ..utils.logging.logger import get_logger
from .shutdown_coordinator import get_shutdown_coordinator

logger = get_logger()


class AgentState(Enum):
    """Possible states of an agent during its lifecycle."""
    INITIALIZING = "initializing"
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class BaseAgentCore(abc.ABC):
    """
    Abstract base class for all trading agents.
    
    Provides the interface and basic functionality that all agents
    must implement, including lifecycle management and shutdown protocol.
    """

    def __init__(self, agent_id: str, agent_type: str):
        """
        Initialize a new agent.
        
        Args:
            agent_id: Unique identifier for this agent instance
            agent_type: Type of agent (e.g., 'execution', 'technical', 'portfolio')
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self._state = AgentState.INITIALIZING
        self._is_shutting_down = False
        self._creation_time = asyncio.get_event_loop().time()
        
        # Register with shutdown coordinator
        self._register_with_shutdown_coordinator()
        
        logger.info(f"Agent {self.agent_id} ({self.agent_type}) initialized")
    
    def _register_with_shutdown_coordinator(self) -> None:
        """Register this agent with the shutdown coordinator system."""
        try:
            # Get the shutdown coordinator and register this agent
            coordinator = get_shutdown_coordinator()
            coordinator.register_agent(
                agent_id=self.agent_id,
                agent_type=self.agent_type, 
                agent_instance=self,
                shutdown_priority=self._get_shutdown_priority(),
                dependencies=self._get_shutdown_dependencies()
            )
            logger.debug(f"Agent {self.agent_id} registered with shutdown coordinator")
        except Exception as e:
            logger.error(f"Failed to register agent {self.agent_id} with shutdown coordinator: {str(e)}")
    
    def _get_shutdown_priority(self) -> int:
        """
        Get the shutdown priority for this agent.
        
        Override this method to customize the priority (higher values are processed first).
        Default is 0 (lowest priority).
        
        Returns:
            Shutdown priority value
        """
        return 0
    
    def _get_shutdown_dependencies(self) -> List[str]:
        """
        Get the list of agent IDs this agent depends on for shutdown.
        
        Override this method to define dependencies. Dependent agents will be
        shut down before this agent.
        
        Returns:
            List of dependent agent IDs
        """
        return []
    
    @property
    def state(self) -> AgentState:
        """Get the current state of the agent."""
        return self._state
    
    @state.setter
    def state(self, value: AgentState) -> None:
        """Set the agent state."""
        if self._state != value:
            logger.debug(f"Agent {self.agent_id} state change: {self._state.value} -> {value.value}")
            self._state = value
    
    def is_running(self) -> bool:
        """Check if the agent is currently running."""
        return self.state == AgentState.RUNNING
    
    @abc.abstractmethod
    async def start(self) -> bool:
        """
        Start the agent's operation.
        
        Must be implemented by subclasses to initialize and start
        the agent's main processing loop or connection to resources.
        
        Returns:
            True if started successfully, False otherwise
        """
        pass
    
    async def prepare_shutdown(self) -> None:
        """
        Prepare for shutdown (phase 1 of shutdown protocol).
        
        This method should:
        - Finish critical operations
        - Flush data to storage if needed
        - Save state for recovery if applicable
        - Signal any dependent processes to prepare for shutdown
        
        Subclasses should override this to implement specific preparation steps.
        """
        self._is_shutting_down = True
        logger.debug(f"Agent {self.agent_id} preparing for shutdown")
    
    async def stop(self) -> bool:
        """
        Stop the agent's operation (phase 2 of shutdown protocol).
        
        This method should:
        - Stop processing new data or operations
        - Cancel any pending operations that are non-critical
        - Signal any managed resources to stop processing
        
        Subclasses must override this to implement specific stopping behavior.
        
        Returns:
            True if stopped successfully, False otherwise
        """
        if not self._is_shutting_down:
            self._is_shutting_down = True
        
        self.state = AgentState.STOPPING
        logger.info(f"Agent {self.agent_id} stopping")
        
        # Wait a moment to simulate stopping
        await asyncio.sleep(0.1)
        
        self.state = AgentState.STOPPED
        logger.info(f"Agent {self.agent_id} stopped")
        return True
    
    async def cleanup(self) -> None:
        """
        Clean up resources (phase 3 of shutdown protocol).
        
        This method should:
        - Release all acquired resources
        - Close connections
        - Terminate any background threads or tasks
        - Perform any final cleanup needed
        
        Subclasses should override this to implement specific cleanup steps.
        """
        logger.debug(f"Agent {self.agent_id} cleaning up resources")
        
        # Default implementation just logs completion
        logger.debug(f"Agent {self.agent_id} cleanup complete")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the agent.
        
        Returns:
            Dictionary with agent status information
        """
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "state": self.state.value,
            "is_shutting_down": self._is_shutting_down,
            "uptime": asyncio.get_event_loop().time() - self._creation_time
        }
    
    def __repr__(self) -> str:
        """String representation of the agent."""
        return f"{self.__class__.__name__}(id={self.agent_id}, type={self.agent_type}, state={self.state.value})"


class BaseAgent:
    """
    Base agent class that integrates with LangChain's agent framework.
    
    This class provides a unified interface for working with different types of agents,
    including memory management, tool integration, and execution handling.
    """
    
    def __init__(
        self,
        agent_id: str,
        agent_type: str = "default",
        agent_name: str = "Assistant",
        agent_role: str = "General assistant",
        agent_description: str = "A helpful AI assistant that can perform various tasks.",
        system_message: Optional[str] = None,
        tools: Optional[List[Tool]] = None,
        memory: Optional[AgentMemory] = None,
        openai_api_key: Optional[str] = None,
        model_name: str = "gpt-3.5-turbo",
        max_iterations: int = 10,
        max_execution_time: Optional[float] = None,
        verbose: bool = False,
        callback_manager: Optional[BaseCallbackManager] = None,
        enable_health_monitoring: bool = True,
        **kwargs
    ):
        """
        Initialize the base agent.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_type: Type of agent (e.g., "researcher", "planner", "executor")
            agent_name: Human-readable name for the agent
            agent_role: Role description for the agent
            agent_description: Detailed description of the agent's capabilities
            system_message: System message for the agent's LLM
            tools: List of tools available to the agent
            memory: Memory system for the agent (created if not provided)
            openai_api_key: OpenAI API key
            model_name: LLM model name
            max_iterations: Maximum number of iterations for agent execution
            max_execution_time: Maximum execution time in seconds
            verbose: Whether to print detailed execution logs
            callback_manager: Callback manager for tracing and logging
            enable_health_monitoring: Whether to enable health monitoring for this agent
            **kwargs: Additional arguments passed to specific agent implementations
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.agent_name = agent_name
        self.agent_role = agent_role
        self.agent_description = agent_description
        
        # Set up system message
        self.system_message = system_message or self._get_default_system_message()
        
        # Set up memory
        self.memory = memory or self._initialize_memory(openai_api_key)
        
        # Set up tools
        self.tools = tools or []
        
        # Set up LLM
        self.model_name = model_name
        self.llm = get_llm_model(model_name=model_name, openai_api_key=openai_api_key)
        
        # Set up execution parameters
        self.max_iterations = max_iterations
        self.max_execution_time = max_execution_time
        self.verbose = verbose
        
        # Set up callback manager
        self.callback_manager = callback_manager or self._initialize_callback_manager()
        
        # Set up state
        self.state = self._initialize_state()
        
        # Set up additional properties from kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)
        
        # Track execution metrics
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.last_execution_time = 0
        
        # Shutdown protocol integration
        self._is_shutting_down = False
        
        # Register with the shutdown coordinator
        self._register_with_shutdown_coordinator()
        
        # Enable health monitoring
        self.enable_health_monitoring = enable_health_monitoring
        if enable_health_monitoring:
            self._register_with_health_monitor()
            
        # Start heartbeat
        self.send_heartbeat()
        
        logger.info(f"Initialized {self.agent_type} agent: {self.agent_name} ({self.agent_id})")
    
    def _register_with_shutdown_coordinator(self) -> None:
        """Register this agent with the shutdown coordinator system."""
        try:
            # Get the shutdown coordinator and register this agent
            coordinator = get_shutdown_coordinator()
            coordinator.register_agent(
                agent_id=self.agent_id,
                agent_type=self.agent_type, 
                agent_instance=self,
                shutdown_priority=self._get_shutdown_priority(),
                dependencies=self._get_shutdown_dependencies()
            )
            logger.debug(f"Agent {self.agent_id} registered with shutdown coordinator")
        except Exception as e:
            logger.error(f"Failed to register agent {self.agent_id} with shutdown coordinator: {str(e)}")
    
    def _get_shutdown_priority(self) -> int:
        """
        Get the shutdown priority for this agent.
        
        Override this method to customize the priority (higher values are processed first).
        Default is 0 (lowest priority).
        
        Returns:
            Shutdown priority value
        """
        return 0
    
    def _get_shutdown_dependencies(self) -> List[str]:
        """
        Get the list of agent IDs this agent depends on for shutdown.
        
        Override this method to define dependencies. Dependent agents will be
        shut down before this agent.
        
        Returns:
            List of dependent agent IDs
        """
        return []
    
    def _initialize_memory(self, openai_api_key: Optional[str] = None) -> AgentMemory:
        """
        Initialize the agent's memory system.
        
        Args:
            openai_api_key: OpenAI API key for embeddings
            
        Returns:
            Initialized memory instance
        """
        return AgentMemory(
            agent_id=self.agent_id,
            openai_api_key=openai_api_key
        )
    
    def _initialize_callback_manager(self) -> CallbackManager:
        """
        Initialize the callback manager for tracing and logging.
        
        Returns:
            Initialized callback manager
        """
        callbacks = []
        
        # Add tracer if verbose
        if self.verbose:
            tracer = LangChainTracer()
            callbacks.append(tracer)
        
        return CallbackManager(handlers=callbacks)
    
    def _initialize_state(self) -> BaseState:
        """
        Initialize the agent's state.
        
        Returns:
            Initialized state
        """
        state = create_empty_state()
        state["agent_type"] = self.agent_type
        state["metadata"] = {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "agent_id": self.agent_id
        }
        return state
    
    def _get_default_system_message(self) -> str:
        """
        Get the default system message based on agent type and role.
        
        Returns:
            Default system message
        """
        return f"""You are {self.agent_name}, a helpful assistant with the role of {self.agent_role}.
        
{self.agent_description}

Always strive to provide accurate, helpful, and relevant information.
"""
    
    def _register_with_health_monitor(self) -> None:
        """Register this agent with the health monitoring system"""
        try:
            # Create a factory callback that can recreate this agent if needed
            def factory_callback() -> BaseAgent:
                # Create a new instance with the same parameters
                return self.__class__(
                    agent_id=self.agent_id,
                    agent_type=self.agent_type,
                    agent_name=self.agent_name,
                    agent_role=self.agent_role,
                    agent_description=self.agent_description,
                    system_message=self.system_message,
                    tools=self.tools.copy() if self.tools else None,
                    # Memory is not copied as it may contain state that should be preserved
                    openai_api_key=None,  # API key should be obtained from config or env
                    model_name=self.model_name,
                    max_iterations=self.max_iterations,
                    max_execution_time=self.max_execution_time,
                    verbose=self.verbose,
                    enable_health_monitoring=True
                )
            
            # Get the health monitor and register this agent
            health_monitor = get_health_monitor()
            health_monitor.register_agent(self, factory_callback)
            
            logger.debug(f"Agent {self.agent_id} registered with health monitoring system")
        except Exception as e:
            logger.error(f"Failed to register agent {self.agent_id} with health monitor: {str(e)}")
    
    def send_heartbeat(self) -> None:
        """Send a heartbeat to the health monitoring system"""
        if self.enable_health_monitoring:
            try:
                get_health_monitor().record_agent_heartbeat(self.agent_id)
            except Exception as e:
                logger.error(f"Failed to send heartbeat for agent {self.agent_id}: {str(e)}")
    
    def add_tool(self, tool: Tool) -> None:
        """
        Add a tool to the agent's toolset.
        
        Args:
            tool: Tool to add
        """
        self.tools.append(tool)
        logger.debug(f"Added tool '{tool.name}' to agent {self.agent_id}")
    
    def add_tools(self, tools: List[Tool]) -> None:
        """
        Add multiple tools to the agent's toolset.
        
        Args:
            tools: List of tools to add
        """
        self.tools.extend(tools)
        tool_names = [tool.name for tool in tools]
        logger.debug(f"Added tools {tool_names} to agent {self.agent_id}")
    
    def _create_agent(self) -> BaseSingleActionAgent:
        """
        Create the concrete LangChain agent implementation.
        
        This method should be overridden by subclasses to create the specific
        agent implementation based on the agent type.
        
        Returns:
            Concrete LangChain agent implementation
        """
        raise NotImplementedError("Subclasses must implement _create_agent()")
    
    def _create_executor(self) -> AgentExecutor:
        """
        Create the agent executor with the agent and tools.
        
        Returns:
            Configured AgentExecutor
        """
        agent = self._create_agent()
        
        return AgentExecutor.from_agent_and_tools(
            agent=agent,
            tools=self.tools,
            callback_manager=self.callback_manager,
            verbose=self.verbose,
            max_iterations=self.max_iterations,
            max_execution_time=self.max_execution_time
        )
    
    async def arun(self, input_text: str, **kwargs) -> str:
        """
        Run the agent asynchronously on the given input.
        
        Args:
            input_text: Input text to the agent
            **kwargs: Additional arguments passed to the executor
            
        Returns:
            Agent response
        """
        # Check if shutting down
        if self._is_shutting_down:
            logger.warning(f"Agent {self.agent_id} is shutting down, refusing new requests")
            return "Agent is shutting down and cannot process new requests."
            
        start_time = time.time()
        
        try:
            # Send heartbeat
            self.send_heartbeat()
            
            # Add input to memory
            self.memory.add_message(input_text, role="user")
            
            # Create executor
            executor = self._create_executor()
            
            # Run the executor
            result = await executor.arun(
                input=input_text,
                **kwargs
            )
            
            # Add result to memory
            self.memory.add_message(result, role="assistant")
            
            # Update statistics
            self.execution_count += 1
            self.success_count += 1
            self.last_execution_time = time.time() - start_time
            
            # Update state
            update_state_timestamp(self.state)
            
            # Report success to health monitor
            if self.enable_health_monitoring:
                response_time = time.time() - start_time
                get_health_monitor().record_agent_success(self.agent_id, response_time)
            
            return result
        except Exception as e:
            # Handle execution failure
            logger.error(f"Agent execution failed: {str(e)}")
            error_msg = f"Error: {str(e)}"
            
            self.failure_count += 1
            
            # Report failure to health monitor
            if self.enable_health_monitoring:
                get_health_monitor().record_agent_failure(self.agent_id, str(e))
            
            # Raise the exception
            raise
    
    def run(self, input_text: str, **kwargs) -> str:
        """
        Run the agent synchronously on the given input.
        
        Args:
            input_text: Input text to the agent
            **kwargs: Additional arguments passed to the executor
            
        Returns:
            Agent response
        """
        # Check if shutting down
        if self._is_shutting_down:
            logger.warning(f"Agent {self.agent_id} is shutting down, refusing new requests")
            return "Agent is shutting down and cannot process new requests."
            
        start_time = time.time()
        
        try:
            # Send heartbeat
            self.send_heartbeat()
            
            # Add input to memory
            self.memory.add_message(input_text, role="user")
            
            # Create executor
            executor = self._create_executor()
            
            # Run the executor
            result = executor.run(
                input=input_text,
                **kwargs
            )
            
            # Add result to memory
            self.memory.add_message(result, role="assistant")
            
            # Update statistics
            self.execution_count += 1
            self.success_count += 1
            self.last_execution_time = time.time() - start_time
            
            # Update state
            update_state_timestamp(self.state)
            
            # Report success to health monitor
            if self.enable_health_monitoring:
                response_time = time.time() - start_time
                get_health_monitor().record_agent_success(self.agent_id, response_time)
            
            return result
        except Exception as e:
            # Handle execution failure
            logger.error(f"Agent execution failed: {str(e)}")
            error_msg = f"Error: {str(e)}"
            
            self.failure_count += 1
            
            # Report failure to health monitor
            if self.enable_health_monitoring:
                get_health_monitor().record_agent_failure(self.agent_id, str(e))
            
            # Raise the exception
            raise
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get agent execution metrics.
        
        Returns:
            Dictionary of execution metrics
        """
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_execution_time": self.last_execution_time,
        }
    
    def reset(self) -> None:
        """
        Reset the agent's state.
        
        This is used for recovery purposes and to clear any internal state
        that might be causing issues.
        """
        # Clear memory
        self.memory = self._initialize_memory()
        
        # Reset state
        self.state = self._initialize_state()
        
        # Reset metrics
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.last_execution_time = 0
        
        # Send heartbeat after reset
        self.send_heartbeat()
        
        logger.info(f"Agent {self.agent_id} has been reset")
    
    def save(self) -> bool:
        """
        Save the agent's state to persistent storage.
        
        Returns:
            True if saved successfully, False otherwise
        """
        # This is a placeholder for subclasses to implement persistence
        logger.warning(f"Save method not implemented for agent {self.agent_id}")
        return False
        
    # Implement shutdown protocol methods for integration with the coordinator
    
    async def prepare_shutdown(self) -> None:
        """
        Prepare for shutdown (phase 1 of shutdown protocol).
        
        This method:
        - Sets the shutdown flag to prevent new requests
        - Flushes memory to persistent storage if applicable
        - Saves agent state if needed
        """
        self._is_shutting_down = True
        logger.info(f"Agent {self.agent_id} preparing for shutdown")
        
        # Try to save state if supported
        try:
            self.save()
        except Exception as e:
            logger.warning(f"Failed to save state for agent {self.agent_id} during shutdown: {str(e)}")
    
    async def stop(self) -> bool:
        """
        Stop the agent's operation (phase 2 of shutdown protocol).
        
        This method:
        - Cancels any pending operations
        - Ensures no new operations are started
        
        Returns:
            True if stopped successfully, False otherwise
        """
        logger.info(f"Agent {self.agent_id} stopping")
        
        # Additional cleanup could be performed here
        
        return True
    
    async def cleanup(self) -> None:
        """
        Clean up resources (phase 3 of shutdown protocol).
        
        This method:
        - Closes connections
        - Releases resources
        - Performs final cleanup
        """
        logger.info(f"Agent {self.agent_id} cleaning up resources")
        
        # Close any open connections or resources
        # Additional cleanup specific to this agent type 