"""
Tests for the Coordinator Agent

This module contains tests for the CoordinatorAgent template and its capabilities
for task coordination, agent orchestration, and workflow management.
"""

import os
import pytest
import json
from unittest.mock import patch, MagicMock, Mock

from langchain.agents.tools import Tool

from ...agents.templates.coordinator import CoordinatorAgent
from ...agents.factory import AgentFactory
from ...agents.orchestration import create_coordinator_workflow


class TestCoordinatorAgent:
    """Tests for the CoordinatorAgent template."""
    
    def test_initialization(self):
        """Test initializing a coordinator agent."""
        agent = CoordinatorAgent(agent_id="test_coordinator")
        
        assert agent.agent_id == "test_coordinator"
        assert agent.agent_type == "coordinator"
        assert agent.coordination_strategy == "adaptive"
        assert hasattr(agent, "managed_agents")
        assert hasattr(agent, "active_workflows")
    
    def test_coordination_tools(self):
        """Test that coordinator agent has the required coordination tools."""
        agent = CoordinatorAgent(agent_id="test_coordinator")
        
        # Check for coordination-specific tools
        tool_names = [tool.name for tool in agent.tools]
        assert "TaskAnalysis" in tool_names
        assert "AgentSelection" in tool_names
        assert "WorkflowCreation" in tool_names
        assert "TaskAllocation" in tool_names
    
    @patch("src.agents.templates.coordinator.CoordinatorAgent.llm")
    def test_analyze_task(self, mock_llm):
        """Test the _analyze_task method."""
        # Setup the mock
        mock_response = json.dumps({
            "overall_goal": "Test goal",
            "subtasks": [
                {
                    "id": "subtask-1",
                    "description": "Research task",
                    "agent_type": "researcher",
                    "dependencies": [],
                    "complexity": "medium",
                    "estimated_time": "30 minutes"
                },
                {
                    "id": "subtask-2",
                    "description": "Planning task",
                    "agent_type": "planner",
                    "dependencies": ["subtask-1"],
                    "complexity": "high",
                    "estimated_time": "1 hour"
                }
            ]
        })
        mock_llm.invoke = Mock(return_value=mock_response)
        
        # Create agent and call method
        agent = CoordinatorAgent(agent_id="test_coordinator")
        result = agent._analyze_task("Test complex task")
        
        # Verify the result
        assert result == mock_response
        mock_llm.invoke.assert_called_once()
        assert "Test complex task" in mock_llm.invoke.call_args[0][0]
    
    @patch("src.agents.templates.coordinator.CoordinatorAgent.llm")
    def test_select_agent_for_task(self, mock_llm):
        """Test the _select_agent_for_task method."""
        # Setup the mock
        mock_response = json.dumps({
            "recommended_agent_type": "researcher",
            "confidence": 90,
            "justification": "This is a research-heavy task requiring information gathering.",
            "alternative_agents": [
                {
                    "agent_type": "planner",
                    "suitability": 60
                }
            ]
        })
        mock_llm.invoke = Mock(return_value=mock_response)
        
        # Create agent and call method
        agent = CoordinatorAgent(agent_id="test_coordinator")
        result = agent._select_agent_for_task("Need to gather information about topic X")
        
        # Verify the result
        assert result == mock_response
        mock_llm.invoke.assert_called_once()
        assert "Need to gather information" in mock_llm.invoke.call_args[0][0]
    
    @patch("src.agents.templates.coordinator.CoordinatorAgent.llm")
    def test_create_workflow(self, mock_llm):
        """Test the _create_workflow method."""
        # Setup the mock
        mock_response = json.dumps({
            "workflow_name": "Research and Planning Workflow",
            "entry_point": "researcher",
            "agents": [
                {
                    "name": "Research Agent",
                    "agent_type": "researcher",
                    "role": "Information gathering",
                    "inputs": ["Initial task"],
                    "outputs": ["Research findings"]
                },
                {
                    "name": "Planning Agent",
                    "agent_type": "planner",
                    "role": "Strategic planning",
                    "inputs": ["Research findings"],
                    "outputs": ["Action plan"]
                }
            ],
            "connections": [
                {
                    "from": "researcher",
                    "to": "planner",
                    "data_passed": "Research findings"
                }
            ]
        })
        mock_llm.invoke = Mock(return_value=mock_response)
        
        # Create agent and call method
        agent = CoordinatorAgent(agent_id="test_coordinator")
        result = agent._create_workflow("Need a workflow for research and planning")
        
        # Verify the result
        assert result == mock_response
        mock_llm.invoke.assert_called_once()
        assert "Need a workflow" in mock_llm.invoke.call_args[0][0]
    
    @patch("src.agents.factory.AgentFactory")
    def test_create_agent_for_task(self, mock_factory):
        """Test creating an agent for a specific task."""
        # Setup mocks
        mock_researcher = MagicMock()
        mock_factory.create_researcher.return_value = mock_researcher
        
        # Create coordinator and call method
        agent = CoordinatorAgent(
            agent_id="test_coordinator",
            agent_factory=mock_factory
        )
        result = agent.create_agent_for_task(
            agent_type="researcher",
            task_description="Research XYZ topic",
            agent_id="research-xyz"
        )
        
        # Verify the result
        assert result == mock_researcher
        mock_factory.create_researcher.assert_called_once_with(
            agent_id="research-xyz",
            agent_name="Researcher Agent for Research XYZ topic...",
        )
        
        # Check that the agent was tracked
        assert "research-xyz" in agent.managed_agents
        assert agent.managed_agents["research-xyz"] == mock_researcher
    
    @patch("src.agents.orchestration.WorkflowBuilder")
    def test_create_workflow_for_task(self, mock_workflow_builder):
        """Test creating a workflow for a complex task."""
        # Setup mock
        mock_builder = MagicMock()
        mock_workflow_builder.return_value = mock_builder
        
        # Create coordinator and call method
        agent = CoordinatorAgent(agent_id="test_coordinator")
        workflow_id, builder = agent.create_workflow_for_task(
            task_description="Complex task XYZ"
        )
        
        # Verify the result
        assert isinstance(workflow_id, str)
        assert builder == mock_builder
        assert workflow_id in agent.active_workflows
        assert agent.active_workflows[workflow_id] == mock_builder
    
    @patch("src.agents.templates.coordinator.CoordinatorAgent._analyze_task")
    @patch("src.agents.templates.coordinator.CoordinatorAgent.create_agent_for_task")
    @patch("src.agents.templates.coordinator.CoordinatorAgent.create_workflow_for_task")
    @patch("src.agents.templates.coordinator.CoordinatorAgent.execute_workflow")
    def test_run_with_coordination(self, mock_execute, mock_create_workflow, 
                                  mock_create_agent, mock_analyze):
        """Test the run_with_coordination method."""
        # Setup mocks
        mock_analysis = json.dumps({
            "overall_goal": "Test goal",
            "subtasks": [
                {
                    "id": "subtask-1",
                    "description": "Research task",
                    "agent_type": "researcher",
                    "dependencies": [],
                    "complexity": "medium"
                },
                {
                    "id": "subtask-2",
                    "description": "Planning task",
                    "agent_type": "planner",
                    "dependencies": ["subtask-1"],
                    "complexity": "high"
                }
            ]
        })
        mock_analyze.return_value = mock_analysis
        
        mock_agent1 = MagicMock()
        mock_agent2 = MagicMock()
        mock_create_agent.side_effect = [mock_agent1, mock_agent2]
        
        mock_builder = MagicMock()
        mock_create_workflow.return_value = ("workflow-1", mock_builder)
        
        mock_result = {
            "messages": [
                {"role": "user", "content": "Initial input"},
                {"role": "ai", "content": "Final result"}
            ]
        }
        mock_execute.return_value = mock_result
        
        # Create coordinator and call method
        agent = CoordinatorAgent(agent_id="test_coordinator")
        result = agent.run_with_coordination("Test complex task")
        
        # Verify the result
        assert result == "Final result"
        mock_analyze.assert_called_once_with("Test complex task")
        assert mock_create_agent.call_count == 2
        mock_create_workflow.assert_called_once()
        mock_execute.assert_called_once_with("workflow-1", "Test complex task")
    
    @patch("src.agents.factory.AgentFactory")
    def test_factory_create_coordinator(self, mock_factory):
        """Test creating a coordinator agent via the factory."""
        # Setup mock
        mock_coordinator = MagicMock()
        mock_factory.create_agent.return_value = mock_coordinator
        
        # Call the factory method
        with patch("src.agents.factory.AgentFactory", mock_factory):
            agent = AgentFactory.create_coordinator(
                agent_id="factory_coordinator",
                coordination_strategy="sequential"
            )
        
        # Verify the result
        assert agent == mock_coordinator
        mock_factory.create_agent.assert_called_once_with(
            agent_type="coordinator",
            agent_id="factory_coordinator",
            agent_name="Coordinator Agent",
            coordination_strategy="sequential"
        )
    
    @patch("src.agents.orchestration.AgentFactory")
    @patch("src.agents.orchestration.WorkflowBuilder")
    def test_create_coordinator_workflow(self, mock_builder_class, mock_factory):
        """Test creating a coordinator workflow."""
        # Setup mocks
        mock_coordinator = MagicMock()
        mock_researcher = MagicMock()
        mock_planner = MagicMock()
        mock_executor = MagicMock()
        
        mock_factory.create_coordinator.return_value = mock_coordinator
        mock_factory.create_researcher.return_value = mock_researcher
        mock_factory.create_planner.return_value = mock_planner
        mock_factory.create_executor.return_value = mock_executor
        
        mock_builder = MagicMock()
        mock_graph = MagicMock()
        mock_builder.build.return_value = mock_graph
        mock_builder_class.return_value = mock_builder
        
        # Call the utility function
        with patch("src.agents.orchestration.WorkflowBuilder", mock_builder_class):
            with patch("src.agents.orchestration.AgentFactory", mock_factory):
                result = create_coordinator_workflow(
                    coordination_strategy="sequential"
                )
        
        # Verify the result
        assert result == mock_graph
        mock_factory.create_coordinator.assert_called_once()
        mock_factory.create_researcher.assert_called_once()
        mock_factory.create_planner.assert_called_once()
        mock_factory.create_executor.assert_called_once()
        
        # Verify builder usage
        assert mock_builder.add_agent_node.call_count == 4
        assert mock_builder.set_entry_point.call_args[0][0] == "coordinator"
        assert mock_builder.build.call_count == 1 