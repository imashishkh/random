"""
Tests for the agent orchestration module.

This module tests the LangGraph orchestration utilities, builder pattern,
and workflow execution for different agent scenarios.
"""

import os
import pytest
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock

from langchain.tools import BaseTool
from langgraph.graph import StateGraph

from ...agents.base_agent import BaseAgent
from ...agents.orchestration import (
    GraphState,
    create_empty_graph_state,
    WorkflowBuilder,
    create_research_planning_execution_workflow,
    create_question_answering_workflow
)


class TestOrchestration:
    """Test suite for agent orchestration utilities."""
    
    def test_create_empty_graph_state(self):
        """Test creating an empty graph state."""
        state = create_empty_graph_state()
        
        # Check required fields
        assert "messages" in state
        assert "context" in state
        assert "artifacts" in state
        assert "workflow_id" in state
        assert "created_at" in state
        assert "updated_at" in state
        assert "status" in state
        assert "is_complete" in state
        
        # Check default values
        assert state["messages"] == []
        assert state["context"] == {}
        assert state["artifacts"] == []
        assert state["status"] == "initialized"
        assert state["is_complete"] is False
        
        # Check custom ID
        custom_id = "test-workflow-123"
        state_with_id = create_empty_graph_state(workflow_id=custom_id)
        assert state_with_id["workflow_id"] == custom_id
    
    def test_workflow_builder_initialization(self):
        """Test initializing the workflow builder."""
        builder = WorkflowBuilder(name="test_workflow")
        
        # Check builder properties
        assert builder.name == "test_workflow"
        assert builder.checkpoint_dir is None
        assert builder.graph is not None
        
        # Check with checkpoint dir
        builder_with_checkpoints = WorkflowBuilder(
            name="test_with_checkpoints",
            checkpoint_dir="./test_checkpoints"
        )
        assert builder_with_checkpoints.checkpoint_dir == "./test_checkpoints"
    
    @patch("src.agents.orchestration.BaseAgent")
    def test_add_agent_node(self, mock_agent):
        """Test adding an agent node to the workflow."""
        # Setup mock agent
        mock_agent.run.return_value = "Agent response"
        
        # Create builder and add agent node
        builder = WorkflowBuilder()
        builder.add_agent_node("test_agent", mock_agent)
        
        # Verify node was added to graph
        assert "test_agent" in builder.graph.nodes
    
    @patch("src.agents.orchestration.ToolNode")
    def test_add_tool_node(self, mock_tool_node):
        """Test adding a tool node to the workflow."""
        # Setup mock tools
        mock_tools = [MagicMock(spec=BaseTool)]
        mock_tool_node.return_value = lambda x: x  # Simple identity function
        
        # Create builder and add tool node
        builder = WorkflowBuilder()
        builder.add_tool_node("tools", mock_tools)
        
        # Verify node was added to graph
        assert "tools" in builder.graph.nodes
    
    def test_add_processing_node(self):
        """Test adding a processing node to the workflow."""
        # Create a test processing function
        def test_processor(state: GraphState) -> GraphState:
            state["status"] = "processed"
            return state
        
        # Create builder and add processing node
        builder = WorkflowBuilder()
        builder.add_processing_node("processor", test_processor)
        
        # Verify node was added to graph
        assert "processor" in builder.graph.nodes
    
    def test_add_human_intervention_node(self):
        """Test adding a human intervention node."""
        # Create builder and add human node
        builder = WorkflowBuilder()
        builder.add_human_intervention_node("human")
        
        # Verify node was added to graph
        assert "human" in builder.graph.nodes
    
    def test_add_edge(self):
        """Test adding a direct edge between nodes."""
        # Create builder and add two nodes with an edge
        builder = WorkflowBuilder()
        
        # Add two processing nodes
        def node1(state: GraphState) -> GraphState:
            return state
            
        def node2(state: GraphState) -> GraphState:
            return state
            
        builder.add_processing_node("node1", node1)
        builder.add_processing_node("node2", node2)
        
        # Add edge
        builder.add_edge("node1", "node2")
        
        # Verify edge exists in graph
        assert builder.graph.edges
    
    def test_add_conditional_edge(self):
        """Test adding a conditional edge between nodes."""
        # Create builder and add two nodes with a conditional edge
        builder = WorkflowBuilder()
        
        # Add two processing nodes
        def node1(state: GraphState) -> GraphState:
            return state
            
        def node2(state: GraphState) -> GraphState:
            return state
            
        builder.add_processing_node("node1", node1)
        builder.add_processing_node("node2", node2)
        
        # Add conditional edge
        def condition(state: GraphState) -> bool:
            return True
            
        builder.add_conditional_edge("node1", "node2", condition)
        
        # Verify conditional edge exists in graph
        assert builder.graph.conditional_edges
    
    def test_set_entry_point(self):
        """Test setting the entry point for the workflow."""
        builder = WorkflowBuilder()
        
        # Add a node
        def node1(state: GraphState) -> GraphState:
            return state
            
        builder.add_processing_node("node1", node1)
        
        # Set entry point
        builder.set_entry_point("node1")
        
        # Check it was set
        assert builder.graph.entry_point == "node1"
    
    def test_build(self):
        """Test building the workflow graph."""
        builder = WorkflowBuilder()
        
        # Add a node and set entry point
        def node1(state: GraphState) -> GraphState:
            return state
            
        builder.add_processing_node("node1", node1)
        builder.set_entry_point("node1")
        
        # Build graph
        compiled = builder.build(debug=True)
        
        # Check result is a StateGraph
        assert isinstance(compiled, StateGraph)
    
    @patch("src.agents.factory.AgentFactory")
    def test_create_research_planning_execution_workflow(self, mock_factory):
        """Test creating the research-planning-execution workflow."""
        # Mock agent factory and agents
        mock_researcher = MagicMock(spec=BaseAgent)
        mock_planner = MagicMock(spec=BaseAgent)
        mock_executor = MagicMock(spec=BaseAgent)
        
        mock_factory.create_researcher.return_value = mock_researcher
        mock_factory.create_planner.return_value = mock_planner
        mock_factory.create_executor.return_value = mock_executor
        
        # Create workflow
        with patch("src.agents.orchestration.AgentFactory", mock_factory):
            workflow = create_research_planning_execution_workflow()
        
        # Check result is a StateGraph
        assert isinstance(workflow, StateGraph)
    
    @patch("src.agents.factory.AgentFactory")
    def test_create_question_answering_workflow(self, mock_factory):
        """Test creating the question-answering workflow."""
        # Mock agent factory and agents
        mock_researcher = MagicMock(spec=BaseAgent)
        mock_agent = MagicMock(spec=BaseAgent)
        
        mock_factory.create_researcher.return_value = mock_researcher
        mock_factory.create_agent.return_value = mock_agent
        
        # Create workflow
        with patch("src.agents.orchestration.AgentFactory", mock_factory):
            workflow = create_question_answering_workflow()
        
        # Check result is a StateGraph
        assert isinstance(workflow, StateGraph) 