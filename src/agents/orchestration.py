"""
Agent Orchestration with LangGraph

This module provides utilities for building and managing agent workflows using LangGraph.
It includes a StateGraph builder, workflow node definitions, and orchestration utilities.
"""

import uuid
import time
from typing import Any, Dict, List, Optional, Callable, TypedDict, Annotated, Union, cast, Tuple

from langchain.schema import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain.schema.runnable import Runnable, RunnableConfig, RunnablePassthrough
from langchain.prompts import PromptTemplate
from langchain.agents import AgentExecutor
from langchain.tools import BaseTool

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint import JsonCheckpointManager
from langgraph.prebuilt import ToolNode

from .base_agent import BaseAgent
from .factory import AgentFactory
from .state.base import BaseState, create_empty_state, update_state_timestamp
from ..utils.logging.logger import get_logger

logger = get_logger()


class GraphState(TypedDict, total=False):
    """
    State representation for agent workflows using LangGraph.
    
    This is the core state structure passed between nodes in the workflow graph.
    """
    # Conversation messages using LangGraph's add_messages annotation 
    messages: Annotated[List[Dict[str, Any]], add_messages]
    
    # Current active agent in the workflow
    current_agent: str
    
    # Shared context between agents
    context: Dict[str, Any]
    
    # Artifacts produced during the workflow
    artifacts: List[Dict[str, Any]]
    
    # Human feedback for intervention points
    human_feedback: Optional[str]
    
    # Workflow metadata
    workflow_id: str
    created_at: float
    updated_at: float
    
    # Error tracking
    errors: List[Dict[str, Any]]
    
    # Status information
    status: str
    is_complete: bool


def create_empty_graph_state(workflow_id: Optional[str] = None) -> GraphState:
    """
    Create an empty GraphState with default values.
    
    Args:
        workflow_id: Optional workflow identifier (generated if not provided)
        
    Returns:
        A new GraphState instance
    """
    current_time = time.time()
    return {
        "messages": [],
        "current_agent": "",
        "context": {},
        "artifacts": [],
        "human_feedback": None,
        "workflow_id": workflow_id or str(uuid.uuid4()),
        "created_at": current_time,
        "updated_at": current_time,
        "errors": [],
        "status": "initialized",
        "is_complete": False
    }


class WorkflowBuilder:
    """
    Builder utility for constructing agent workflows with LangGraph.
    
    Simplifies the creation of StateGraph instances with agents, tools, and conditional routing.
    """
    
    def __init__(
        self,
        name: str = "agent_workflow",
        checkpoint_dir: Optional[str] = None,
        state: Optional[GraphState] = None
    ):
        """
        Initialize the workflow builder.
        
        Args:
            name: Workflow name for identification
            checkpoint_dir: Directory for saving checkpoints (None for no checkpointing)
            state: Initial workflow state (created if not provided)
        """
        self.name = name
        self.checkpoint_dir = checkpoint_dir
        self.initial_state = state or create_empty_graph_state()
        
        # Initialize the graph
        self.graph = StateGraph(GraphState)
        
        # Configure checkpointing if directory provided
        if checkpoint_dir:
            checkpoint_manager = JsonCheckpointManager(checkpoint_dir)
            self.graph.set_checkpoint_manager(checkpoint_manager)
        
        logger.info(f"Initialized workflow builder: {name}")
    
    def add_agent_node(
        self,
        name: str,
        agent: BaseAgent,
        description: Optional[str] = None
    ) -> 'WorkflowBuilder':
        """
        Add an agent as a node in the workflow.
        
        Args:
            name: Node name
            agent: Agent instance to add
            description: Node description for documentation
            
        Returns:
            Self for method chaining
        """
        # Define the node function to update state with agent output
        def agent_node(state: GraphState) -> GraphState:
            # Update the current agent
            state["current_agent"] = name
            
            # If we have conversation messages, extract the most recent as input
            # Otherwise, create a default input from context
            if state.get("messages", []):
                last_msg = state["messages"][-1]
                if isinstance(last_msg, dict):
                    input_text = last_msg.get("content", "")
                else:
                    input_text = str(last_msg)
            else:
                # Create input from context
                input_text = f"Task: {state.get('context', {}).get('task', 'No task specified')}"
            
            try:
                # Run the agent
                result = agent.run(input_text)
                
                # Add the agent's response to the state
                state["messages"] = state.get("messages", []) + [{
                    "role": "ai",
                    "content": result,
                    "agent": name
                }]
                
                # Update state timestamp
                state["updated_at"] = time.time()
                
            except Exception as e:
                # Log and record any errors
                logger.error(f"Error in agent node {name}: {str(e)}")
                state["errors"] = state.get("errors", []) + [{
                    "node": name,
                    "error": str(e),
                    "timestamp": time.time()
                }]
            
            return state
        
        # Add the node to the graph
        self.graph.add_node(name, agent_node)
        logger.debug(f"Added agent node: {name}")
        
        return self
    
    def add_tool_node(
        self,
        name: str,
        tools: List[BaseTool],
        description: Optional[str] = None
    ) -> 'WorkflowBuilder':
        """
        Add a tool execution node to the workflow.
        
        Args:
            name: Node name
            tools: List of tools available at this node
            description: Node description for documentation
            
        Returns:
            Self for method chaining
        """
        # Create a ToolNode from LangGraph
        tool_node = ToolNode(tools)
        
        # Add the node to the graph
        self.graph.add_node(name, tool_node)
        logger.debug(f"Added tool node: {name} with {len(tools)} tools")
        
        return self
    
    def add_human_intervention_node(
        self,
        name: str = "human_intervention",
        description: Optional[str] = None
    ) -> 'WorkflowBuilder':
        """
        Add a human intervention point to the workflow.
        
        Args:
            name: Node name
            description: Node description for documentation
            
        Returns:
            Self for method chaining
        """
        # Define the node function
        def human_intervention_node(state: GraphState) -> GraphState:
            # This would typically connect to a UI or API to get human feedback
            # For now, we'll just log that human intervention would be needed here
            logger.info(f"Human intervention needed at node {name}")
            logger.info(f"Current state context: {state.get('context', {})}")
            
            # In a real implementation, this would wait for human input
            # For now, we'll just add a placeholder and continue
            if not state.get("human_feedback"):
                state["human_feedback"] = "Awaiting human feedback"
            
            return state
        
        # Add the node to the graph
        self.graph.add_node(name, human_intervention_node)
        logger.debug(f"Added human intervention node: {name}")
        
        return self
    
    def add_processing_node(
        self,
        name: str,
        process_func: Callable[[GraphState], GraphState],
        description: Optional[str] = None
    ) -> 'WorkflowBuilder':
        """
        Add a custom processing node to the workflow.
        
        Args:
            name: Node name
            process_func: Function to process the state
            description: Node description for documentation
            
        Returns:
            Self for method chaining
        """
        # Add the node to the graph
        self.graph.add_node(name, process_func)
        logger.debug(f"Added processing node: {name}")
        
        return self
    
    def add_conditional_edge(
        self,
        source: str,
        target: str,
        condition: Callable[[GraphState], bool],
        description: Optional[str] = None
    ) -> 'WorkflowBuilder':
        """
        Add a conditional edge between nodes.
        
        Args:
            source: Source node name
            target: Target node name
            condition: Condition function that returns True if edge should be followed
            description: Edge description for documentation
            
        Returns:
            Self for method chaining
        """
        # Add the conditional edge
        self.graph.add_conditional_edge(source, target, condition)
        logger.debug(f"Added conditional edge: {source} -> {target}")
        
        return self
    
    def add_edge(
        self,
        source: str,
        target: str,
        description: Optional[str] = None
    ) -> 'WorkflowBuilder':
        """
        Add a direct edge between nodes.
        
        Args:
            source: Source node name
            target: Target node name or END
            description: Edge description for documentation
            
        Returns:
            Self for method chaining
        """
        # Add the edge
        self.graph.add_edge(source, target)
        logger.debug(f"Added edge: {source} -> {target}")
        
        return self
    
    def set_entry_point(
        self,
        node_name: str
    ) -> 'WorkflowBuilder':
        """
        Set the entry point for the workflow.
        
        Args:
            node_name: Name of the entry node
            
        Returns:
            Self for method chaining
        """
        # Set the entry point
        self.graph.set_entry_point(node_name)
        logger.debug(f"Set entry point: {node_name}")
        
        return self
    
    def build(
        self,
        debug: bool = False
    ) -> StateGraph:
        """
        Build the workflow graph.
        
        Args:
            debug: Whether to compile with debug mode enabled
            
        Returns:
            Compiled StateGraph ready for execution
        """
        # Compile the graph
        compiled = self.graph.compile(debug=debug)
        logger.info(f"Built workflow graph: {self.name}")
        
        return compiled
    
    def visualize(
        self,
        output_path: Optional[str] = None
    ) -> None:
        """
        Generate a visualization of the workflow graph.
        
        Args:
            output_path: Path to save the visualization (default: {name}_graph.png)
        """
        if output_path is None:
            output_path = f"{self.name}_graph"
        
        # Create the visualization
        self.graph.to_dot().render(output_path, format="png")
        logger.info(f"Generated workflow visualization: {output_path}.png")


# Utility functions for common workflow patterns

def create_research_planning_execution_workflow(
    openai_api_key: Optional[str] = None,
    model_name: str = "gpt-3.5-turbo",
    tools: Optional[List[BaseTool]] = None,
    checkpoint_dir: Optional[str] = None
) -> StateGraph:
    """
    Create a standard research-planning-execution workflow.
    
    Args:
        openai_api_key: OpenAI API key
        model_name: LLM model name
        tools: List of tools to make available to the agents
        checkpoint_dir: Directory for checkpointing
        
    Returns:
        Compiled workflow graph
    """
    # Create the builder
    builder = WorkflowBuilder(
        name="research_planning_execution",
        checkpoint_dir=checkpoint_dir
    )
    
    # Create the agents
    researcher = AgentFactory.create_researcher(
        agent_name="Research Agent",
        openai_api_key=openai_api_key,
        model_name=model_name,
        search_tools=True
    )
    
    planner = AgentFactory.create_planner(
        agent_name="Planning Agent",
        openai_api_key=openai_api_key,
        model_name=model_name,
        planning_framework="standard"
    )
    
    executor = AgentFactory.create_executor(
        agent_name="Execution Agent",
        openai_api_key=openai_api_key,
        model_name=model_name,
        execution_mode="standard",
        include_system_tools=True
    )
    
    # Add agents as nodes
    builder.add_agent_node("researcher", researcher)
    builder.add_agent_node("planner", planner)
    builder.add_agent_node("executor", executor)
    
    # Add tool node if tools provided
    if tools:
        builder.add_tool_node("tools", tools)
    
    # Add human intervention
    builder.add_human_intervention_node("human_review")
    
    # Add a processing node for final results
    def finalize_results(state: GraphState) -> GraphState:
        """Process the final results before completing the workflow."""
        state["status"] = "completed"
        state["is_complete"] = True
        state["updated_at"] = time.time()
        return state
    
    builder.add_processing_node("finalize", finalize_results)
    
    # Add conditional routing
    def needs_research(state: GraphState) -> bool:
        """Check if additional research is needed."""
        # Extract the last message
        if not state.get("messages"):
            return False
        
        last_message = state["messages"][-1]
        if isinstance(last_message, dict):
            content = last_message.get("content", "").lower()
        else:
            content = str(last_message).lower()
        
        # Check if the message suggests research is needed
        research_indicators = [
            "need more information",
            "need to research",
            "further research",
            "need data",
            "insufficient information"
        ]
        
        return any(indicator in content for indicator in research_indicators)
    
    def needs_planning(state: GraphState) -> bool:
        """Check if planning is needed."""
        # Similar to needs_research but for planning indicators
        if not state.get("messages"):
            return False
        
        last_message = state["messages"][-1]
        if isinstance(last_message, dict):
            content = last_message.get("content", "").lower()
        else:
            content = str(last_message).lower()
        
        planning_indicators = [
            "need a plan",
            "should plan",
            "create a strategy",
            "develop a plan",
            "step by step approach"
        ]
        
        return any(indicator in content for indicator in planning_indicators)
    
    def needs_execution(state: GraphState) -> bool:
        """Check if execution is needed."""
        # Default route to execution
        return True
    
    def needs_human_review(state: GraphState) -> bool:
        """Check if human review is needed."""
        # Extract the last message
        if not state.get("messages"):
            return False
        
        last_message = state["messages"][-1]
        if isinstance(last_message, dict):
            content = last_message.get("content", "").lower()
        else:
            content = str(last_message).lower()
        
        # Check if the message suggests human review is needed
        review_indicators = [
            "human review",
            "need confirmation",
            "please verify",
            "request feedback",
            "unsafe to proceed"
        ]
        
        return any(indicator in content for indicator in review_indicators)
    
    # Add edges with conditions
    builder.add_conditional_edge("researcher", "planner", needs_planning)
    builder.add_conditional_edge("researcher", "executor", needs_execution)
    
    builder.add_conditional_edge("planner", "researcher", needs_research)
    builder.add_conditional_edge("planner", "executor", needs_execution)
    
    builder.add_conditional_edge("executor", "researcher", needs_research)
    builder.add_conditional_edge("executor", "planner", needs_planning)
    builder.add_conditional_edge("executor", "human_review", needs_human_review)
    builder.add_edge("executor", "finalize")
    
    builder.add_edge("human_review", "executor")
    builder.add_edge("finalize", END)
    
    # Set entry point
    builder.set_entry_point("researcher")
    
    # Build and return the graph
    return builder.build()


# Additional workflow examples

def create_question_answering_workflow(
    openai_api_key: Optional[str] = None,
    model_name: str = "gpt-3.5-turbo",
    checkpoint_dir: Optional[str] = None
) -> StateGraph:
    """
    Create a question-answering workflow optimized for informational queries.
    
    Args:
        openai_api_key: OpenAI API key
        model_name: LLM model name
        checkpoint_dir: Directory for checkpointing
        
    Returns:
        Compiled workflow graph
    """
    # Create the builder
    builder = WorkflowBuilder(
        name="question_answering",
        checkpoint_dir=checkpoint_dir
    )
    
    # Create researcher for information gathering
    researcher = AgentFactory.create_researcher(
        agent_name="Research Agent",
        openai_api_key=openai_api_key,
        model_name=model_name,
        search_tools=True
    )
    
    # Create a synthesizer agent to format final answers
    synthesizer = AgentFactory.create_agent(
        agent_type="executor",  # Reuse executor type but customize
        agent_name="Answer Synthesizer",
        agent_description="Specialized in synthesizing information into clear, concise answers.",
        openai_api_key=openai_api_key,
        model_name=model_name
    )
    
    # Add nodes
    builder.add_agent_node("researcher", researcher)
    builder.add_agent_node("synthesizer", synthesizer)
    
    # Add processing node for flagging insufficient information
    def check_information_complete(state: GraphState) -> GraphState:
        """Check if sufficient information has been gathered."""
        # This would analyze the state to determine if research is complete
        # For now, just pass through
        return state
    
    builder.add_processing_node("check_complete", check_information_complete)
    
    # Add conditional routing
    def needs_more_research(state: GraphState) -> bool:
        """Determine if more research is needed."""
        # Logic to determine if research is complete
        if not state.get("messages"):
            return True
        
        # Simple heuristic - if we've gone back to research 3 times, consider it complete
        research_count = sum(
            1 for msg in state.get("messages", [])
            if isinstance(msg, dict) and msg.get("agent") == "researcher"
        )
        
        return research_count < 3
    
    # Add edges
    builder.add_conditional_edge("check_complete", "researcher", needs_more_research)
    builder.add_conditional_edge("check_complete", "synthesizer", lambda s: not needs_more_research(s))
    builder.add_edge("researcher", "check_complete")
    builder.add_edge("synthesizer", END)
    
    # Set entry point
    builder.set_entry_point("researcher")
    
    # Build and return the graph
    return builder.build()


def create_coordinator_workflow(
    openai_api_key: Optional[str] = None,
    model_name: str = "gpt-3.5-turbo",
    coordination_strategy: str = "adaptive",
    tools: Optional[List[BaseTool]] = None,
    checkpoint_dir: Optional[str] = None
) -> StateGraph:
    """
    Create a workflow with a coordinator agent as the central component.
    
    This workflow uses a coordinator agent to dynamically analyze tasks,
    allocate them to appropriate specialized agents, and manage the workflow.
    
    Args:
        openai_api_key: OpenAI API key
        model_name: LLM model name
        coordination_strategy: Strategy for coordination ("adaptive", "sequential", "parallel")
        tools: List of tools to make available to the agents
        checkpoint_dir: Directory for checkpointing
        
    Returns:
        Compiled workflow graph
    """
    # Create the builder
    builder = WorkflowBuilder(
        name="coordinator_workflow",
        checkpoint_dir=checkpoint_dir
    )
    
    # Create the coordinator agent
    coordinator = AgentFactory.create_coordinator(
        agent_name="Coordinator Agent",
        openai_api_key=openai_api_key,
        model_name=model_name,
        coordination_strategy=coordination_strategy
    )
    
    # Create specialized agents for the coordinator to use
    researcher = AgentFactory.create_researcher(
        agent_name="Research Agent",
        openai_api_key=openai_api_key,
        model_name=model_name,
        search_tools=True
    )
    
    planner = AgentFactory.create_planner(
        agent_name="Planning Agent",
        openai_api_key=openai_api_key,
        model_name=model_name,
        planning_framework="standard"
    )
    
    executor = AgentFactory.create_executor(
        agent_name="Execution Agent",
        openai_api_key=openai_api_key,
        model_name=model_name,
        execution_mode="standard",
        include_system_tools=True
    )
    
    # Add the coordinator as the central node
    builder.add_agent_node("coordinator", coordinator)
    
    # Add specialized agents
    builder.add_agent_node("researcher", researcher)
    builder.add_agent_node("planner", planner)
    builder.add_agent_node("executor", executor)
    
    # Add tool node if tools provided
    if tools:
        builder.add_tool_node("tools", tools)
    
    # Add human intervention
    builder.add_human_intervention_node("human_review")
    
    # Add a processing node for final results
    def finalize_results(state: GraphState) -> GraphState:
        """Process the final results before completing the workflow."""
        state["status"] = "completed"
        state["is_complete"] = True
        state["updated_at"] = time.time()
        return state
    
    builder.add_processing_node("finalize", finalize_results)
    
    # Define conditional routing
    def needs_research(state: GraphState) -> bool:
        """Check if research is needed based on coordinator's decision."""
        # Get coordination decision from state
        if not state.get("context") or not state["context"].get("coordination"):
            return False
        
        coordination = state["context"]["coordination"]
        return coordination.get("next_agent") == "researcher"
    
    def needs_planning(state: GraphState) -> bool:
        """Check if planning is needed based on coordinator's decision."""
        # Get coordination decision from state
        if not state.get("context") or not state["context"].get("coordination"):
            return False
        
        coordination = state["context"]["coordination"]
        return coordination.get("next_agent") == "planner"
    
    def needs_execution(state: GraphState) -> bool:
        """Check if execution is needed based on coordinator's decision."""
        # Get coordination decision from state
        if not state.get("context") or not state["context"].get("coordination"):
            return False
        
        coordination = state["context"]["coordination"]
        return coordination.get("next_agent") == "executor"
    
    def needs_human_review(state: GraphState) -> bool:
        """Check if human review is needed based on coordinator's decision."""
        # Get coordination decision from state
        if not state.get("context") or not state["context"].get("coordination"):
            return False
        
        coordination = state["context"]["coordination"]
        return coordination.get("next_agent") == "human_review"
    
    def is_task_complete(state: GraphState) -> bool:
        """Check if the task is complete based on coordinator's decision."""
        # Get coordination decision from state
        if not state.get("context") or not state["context"].get("coordination"):
            return False
        
        coordination = state["context"]["coordination"]
        return coordination.get("task_complete", False)
    
    # Add edges from coordinator to other agents
    builder.add_conditional_edge("coordinator", "researcher", needs_research)
    builder.add_conditional_edge("coordinator", "planner", needs_planning)
    builder.add_conditional_edge("coordinator", "executor", needs_execution)
    builder.add_conditional_edge("coordinator", "human_review", needs_human_review)
    builder.add_conditional_edge("coordinator", "finalize", is_task_complete)
    
    # Add edges from specialized agents back to coordinator
    builder.add_edge("researcher", "coordinator")
    builder.add_edge("planner", "coordinator")
    builder.add_edge("executor", "coordinator")
    builder.add_edge("human_review", "coordinator")
    
    # Add edges from tools to coordinator
    if tools:
        builder.add_edge("tools", "coordinator")
    
    # Connect finalize to END
    builder.add_edge("finalize", END)
    
    # Set entry point as the coordinator
    builder.set_entry_point("coordinator")
    
    # Build and return the graph
    return builder.build() 