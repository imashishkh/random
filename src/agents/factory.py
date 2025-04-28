"""
Agent Factory

This module provides factory functions for creating different types of agents,
simplifying the instantiation of agent templates with common configurations.
"""

import uuid
from typing import Any, Dict, List, Optional, Union

from langchain.agents.tools import Tool

from .base_agent import BaseAgent
from .templates.researcher import ResearcherAgent
from .templates.planner import PlannerAgent
from .templates.executor import ExecutorAgent
from .templates.coordinator import CoordinatorAgent
from ..utils.logging.logger import get_logger

logger = get_logger()


class AgentFactory:
    """
    Factory class for creating different types of agents.
    
    Simplifies the instantiation of agent templates with common configurations
    and provides a consistent interface for agent creation.
    """
    
    @staticmethod
    def create_agent(
        agent_type: str,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        agent_description: Optional[str] = None,
        system_message: Optional[str] = None,
        tools: Optional[List[Tool]] = None,
        openai_api_key: Optional[str] = None,
        model_name: str = "gpt-3.5-turbo",
        verbose: bool = False,
        **kwargs
    ) -> BaseAgent:
        """
        Create an agent of the specified type.
        
        Args:
            agent_type: Type of agent to create ("researcher", "planner", "executor", "coordinator")
            agent_id: Unique identifier for the agent (generated if not provided)
            agent_name: Human-readable name for the agent
            agent_description: Detailed description of the agent's capabilities
            system_message: System message for the agent
            tools: List of tools available to the agent
            openai_api_key: OpenAI API key
            model_name: LLM model name
            verbose: Whether to print detailed execution logs
            **kwargs: Additional arguments for specific agent types
            
        Returns:
            Instantiated agent of the specified type
            
        Raises:
            ValueError: If an unsupported agent type is specified
        """
        # Generate agent ID if not provided
        if agent_id is None:
            agent_id = str(uuid.uuid4())
        
        # Create agent based on type
        if agent_type.lower() == "researcher":
            agent = ResearcherAgent(
                agent_id=agent_id,
                agent_name=agent_name or "Research Agent",
                agent_description=agent_description or "Specialized in gathering and analyzing information.",
                system_message=system_message,
                tools=tools,
                openai_api_key=openai_api_key,
                model_name=model_name,
                verbose=verbose,
                **kwargs
            )
        elif agent_type.lower() == "planner":
            agent = PlannerAgent(
                agent_id=agent_id,
                agent_name=agent_name or "Planning Agent",
                agent_description=agent_description or "Specialized in strategic planning and goal decomposition.",
                system_message=system_message,
                tools=tools,
                openai_api_key=openai_api_key,
                model_name=model_name,
                verbose=verbose,
                **kwargs
            )
        elif agent_type.lower() == "executor":
            agent = ExecutorAgent(
                agent_id=agent_id,
                agent_name=agent_name or "Executor Agent",
                agent_description=agent_description or "Specialized in implementing plans and solving problems.",
                system_message=system_message,
                tools=tools,
                openai_api_key=openai_api_key,
                model_name=model_name,
                verbose=verbose,
                **kwargs
            )
        elif agent_type.lower() == "coordinator":
            agent = CoordinatorAgent(
                agent_id=agent_id,
                agent_name=agent_name or "Coordinator Agent",
                agent_description=agent_description or "Specialized in task allocation and agent orchestration.",
                system_message=system_message,
                tools=tools,
                openai_api_key=openai_api_key,
                model_name=model_name,
                verbose=verbose,
                **kwargs
            )
        else:
            raise ValueError(f"Unsupported agent type: {agent_type}")
        
        logger.info(f"Created {agent_type} agent: {agent.agent_name} ({agent.agent_id})")
        return agent
    
    @staticmethod
    def create_researcher(
        agent_id: Optional[str] = None,
        agent_name: str = "Research Agent",
        search_tools: bool = True,
        **kwargs
    ) -> ResearcherAgent:
        """
        Create a researcher agent.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_name: Human-readable name for the agent
            search_tools: Whether to include default search tools
            **kwargs: Additional arguments for agent creation
            
        Returns:
            Instantiated researcher agent
        """
        return AgentFactory.create_agent(
            agent_type="researcher",
            agent_id=agent_id,
            agent_name=agent_name,
            search_tools=search_tools,
            **kwargs
        )
    
    @staticmethod
    def create_planner(
        agent_id: Optional[str] = None,
        agent_name: str = "Planning Agent",
        planning_framework: str = "standard",
        **kwargs
    ) -> PlannerAgent:
        """
        Create a planner agent.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_name: Human-readable name for the agent
            planning_framework: Planning approach to use ("standard", "agile", "strategic")
            **kwargs: Additional arguments for agent creation
            
        Returns:
            Instantiated planner agent
        """
        return AgentFactory.create_agent(
            agent_type="planner",
            agent_id=agent_id,
            agent_name=agent_name,
            planning_framework=planning_framework,
            **kwargs
        )
    
    @staticmethod
    def create_executor(
        agent_id: Optional[str] = None,
        agent_name: str = "Executor Agent",
        execution_mode: str = "standard",
        include_system_tools: bool = True,
        **kwargs
    ) -> ExecutorAgent:
        """
        Create an executor agent.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_name: Human-readable name for the agent
            execution_mode: Execution approach ("standard", "detailed", "expedited")
            include_system_tools: Whether to include default system tools
            **kwargs: Additional arguments for agent creation
            
        Returns:
            Instantiated executor agent
        """
        return AgentFactory.create_agent(
            agent_type="executor",
            agent_id=agent_id,
            agent_name=agent_name,
            execution_mode=execution_mode,
            include_system_tools=include_system_tools,
            **kwargs
        )
        
    @staticmethod
    def create_coordinator(
        agent_id: Optional[str] = None,
        agent_name: str = "Coordinator Agent",
        coordination_strategy: str = "adaptive",
        **kwargs
    ) -> CoordinatorAgent:
        """
        Create a coordinator agent.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_name: Human-readable name for the agent
            coordination_strategy: Strategy for coordination ("adaptive", "sequential", "parallel")
            **kwargs: Additional arguments for agent creation
            
        Returns:
            Instantiated coordinator agent
        """
        return AgentFactory.create_agent(
            agent_type="coordinator",
            agent_id=agent_id,
            agent_name=agent_name,
            coordination_strategy=coordination_strategy,
            **kwargs
        ) 