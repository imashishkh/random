"""
Tests for Agent Templates

This module contains tests for the BaseAgent class and specialized agent templates.
"""

import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

from langchain.agents.tools import Tool

from ...agents.base_agent import BaseAgent
from ...agents.templates.researcher import ResearcherAgent
from ...agents.templates.planner import PlannerAgent
from ...agents.templates.executor import ExecutorAgent
from ...agents.factory import AgentFactory


class MockAgent(BaseAgent):
    """Mock agent implementation for testing BaseAgent."""
    
    def _create_agent(self):
        """Mock implementation of _create_agent."""
        return MagicMock()


class TestBaseAgent:
    """Tests for the BaseAgent class."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent for testing."""
        return MockAgent(agent_id="test_agent")
    
    def test_initialization(self):
        """Test that the base agent initializes correctly."""
        agent = MockAgent(
            agent_id="test_agent",
            agent_name="Test Agent",
            agent_type="test",
            agent_role="Testing",
            agent_description="A test agent for unit testing."
        )
        
        assert agent.agent_id == "test_agent"
        assert agent.agent_name == "Test Agent"
        assert agent.agent_type == "test"
        assert agent.agent_role == "Testing"
        assert agent.agent_description == "A test agent for unit testing."
        assert agent.tools == []
        assert agent.execution_count == 0
        assert agent.success_count == 0
        assert agent.failure_count == 0
    
    def test_add_tool(self, mock_agent):
        """Test adding a tool to the agent."""
        tool = Tool(name="test_tool", func=lambda x: x, description="Test tool")
        mock_agent.add_tool(tool)
        
        assert len(mock_agent.tools) == 1
        assert mock_agent.tools[0].name == "test_tool"
    
    def test_add_tools(self, mock_agent):
        """Test adding multiple tools to the agent."""
        tools = [
            Tool(name="tool1", func=lambda x: x, description="Tool 1"),
            Tool(name="tool2", func=lambda x: x, description="Tool 2")
        ]
        mock_agent.add_tools(tools)
        
        assert len(mock_agent.tools) == 2
        assert {tool.name for tool in mock_agent.tools} == {"tool1", "tool2"}
    
    def test_get_metrics(self, mock_agent):
        """Test getting agent metrics."""
        # Set up some execution metrics
        mock_agent.execution_count = 10
        mock_agent.success_count = 8
        mock_agent.failure_count = 2
        
        metrics = mock_agent.get_metrics()
        
        assert metrics["agent_id"] == "test_agent"
        assert metrics["execution_count"] == 10
        assert metrics["success_count"] == 8
        assert metrics["failure_count"] == 2
        assert metrics["success_rate"] == 0.8
    
    @patch.object(MockAgent, '_create_executor')
    def test_run_success(self, mock_create_executor, mock_agent):
        """Test successful agent run."""
        # Set up mock executor
        mock_executor = MagicMock()
        mock_executor.run.return_value = "Success response"
        mock_create_executor.return_value = mock_executor
        
        # Run the agent
        response = mock_agent.run("Test input")
        
        # Verify response and state updates
        assert response == "Success response"
        assert mock_agent.execution_count == 1
        assert mock_agent.success_count == 1
        assert mock_agent.failure_count == 0
    
    @patch.object(MockAgent, '_create_executor')
    def test_run_failure(self, mock_create_executor, mock_agent):
        """Test failed agent run."""
        # Set up mock executor
        mock_executor = MagicMock()
        mock_executor.run.side_effect = Exception("Test error")
        mock_create_executor.return_value = mock_executor
        
        # Run the agent and expect exception
        with pytest.raises(Exception, match="Test error"):
            mock_agent.run("Test input")
        
        # Verify state updates
        assert mock_agent.execution_count == 1
        assert mock_agent.success_count == 0
        assert mock_agent.failure_count == 1
    
    def test_reset(self, mock_agent):
        """Test resetting agent state."""
        # Set up some state
        mock_agent.execution_count = 5
        mock_agent.success_count = 4
        mock_agent.failure_count = 1
        
        # Add messages to memory
        mock_agent.memory.add_message("Test message", "user")
        
        # Reset agent
        mock_agent.reset()
        
        # Verify state reset
        assert mock_agent.execution_count == 0
        assert mock_agent.success_count == 0
        assert mock_agent.failure_count == 0


class TestResearcherAgent:
    """Tests for the ResearcherAgent template."""
    
    def test_initialization(self):
        """Test that the researcher agent initializes correctly."""
        agent = ResearcherAgent(agent_id="test_researcher")
        
        assert agent.agent_id == "test_researcher"
        assert agent.agent_type == "researcher"
        assert agent.agent_role == "Research specialist"
        assert "Research Agent" in agent.agent_name
    
    def test_system_message(self):
        """Test that the system message is set correctly."""
        agent = ResearcherAgent(agent_id="test_researcher")
        
        assert "Research Agent" in agent.system_message
        assert "gathering, analyzing, and synthesizing information" in agent.system_message
    
    @patch('langchain.tools.WikipediaQueryRun')
    @patch('langchain.tools.DuckDuckGoSearchRun')
    def test_search_tools(self, mock_duckduckgo, mock_wikipedia):
        """Test that search tools are added correctly."""
        # Mock the search tools to avoid actual API calls
        mock_duckduckgo.return_value.run = lambda x: f"DuckDuckGo results for: {x}"
        mock_wikipedia.return_value.run = lambda x: f"Wikipedia results for: {x}"
        
        # Create agent with mocked dependencies
        with patch('src.agents.templates.researcher.WikipediaQueryRun', return_value=mock_wikipedia), \
             patch('src.agents.templates.researcher.DuckDuckGoSearchRun', return_value=mock_duckduckgo):
            agent = ResearcherAgent(agent_id="test_researcher", search_tools=True)
        
        # Check that tools were added
        tool_names = [tool.name for tool in agent.tools]
        assert "Web Search" in tool_names or "Wikipedia" in tool_names


class TestPlannerAgent:
    """Tests for the PlannerAgent template."""
    
    def test_initialization(self):
        """Test that the planner agent initializes correctly."""
        agent = PlannerAgent(agent_id="test_planner")
        
        assert agent.agent_id == "test_planner"
        assert agent.agent_type == "planner"
        assert agent.agent_role == "Planning specialist"
        assert "Planning Agent" in agent.agent_name
        assert agent.planning_framework == "standard"
    
    def test_system_message(self):
        """Test that the system message is set correctly."""
        agent = PlannerAgent(agent_id="test_planner")
        
        assert "Planning Agent" in agent.system_message
        assert "strategic thinking, plan formulation, and goal decomposition" in agent.system_message
    
    def test_framework_specific_message(self):
        """Test that framework-specific guidance is included in system message."""
        # Test standard framework
        standard_agent = PlannerAgent(
            agent_id="test_standard",
            planning_framework="standard"
        )
        assert "Standard Planning specialist" in standard_agent.system_message
        
        # Test agile framework
        agile_agent = PlannerAgent(
            agent_id="test_agile",
            planning_framework="agile"
        )
        assert "Agile Planning specialist" in agile_agent.system_message
        assert "short sprints" in agile_agent.system_message
        
        # Test strategic framework
        strategic_agent = PlannerAgent(
            agent_id="test_strategic",
            planning_framework="strategic"
        )
        assert "Strategic Planning specialist" in strategic_agent.system_message
        assert "SWOT" in strategic_agent.system_message
    
    def test_planning_tools(self):
        """Test that planning tools are added correctly."""
        agent = PlannerAgent(agent_id="test_planner")
        
        tool_names = [tool.name for tool in agent.tools]
        assert "GoalDecomposition" in tool_names
        assert "CreatePlan" in tool_names
        assert "EstimateResources" in tool_names


class TestExecutorAgent:
    """Tests for the ExecutorAgent template."""
    
    def test_initialization(self):
        """Test that the executor agent initializes correctly."""
        agent = ExecutorAgent(agent_id="test_executor")
        
        assert agent.agent_id == "test_executor"
        assert agent.agent_type == "executor"
        assert agent.agent_role == "Execution specialist"
        assert "Executor Agent" in agent.agent_name
        assert agent.execution_mode == "standard"
    
    def test_system_message(self):
        """Test that the system message is set correctly."""
        agent = ExecutorAgent(agent_id="test_executor")
        
        assert "Executor Agent" in agent.system_message
        assert "implementing plans, solving problems, and taking action" in agent.system_message
    
    def test_mode_specific_message(self):
        """Test that mode-specific guidance is included in system message."""
        # Test standard mode
        standard_agent = ExecutorAgent(
            agent_id="test_standard",
            execution_mode="standard"
        )
        assert "Standard Execution specialist" in standard_agent.system_message
        
        # Test detailed mode
        detailed_agent = ExecutorAgent(
            agent_id="test_detailed",
            execution_mode="detailed"
        )
        assert "Detailed Execution specialist" in detailed_agent.system_message
        assert "Document every step" in detailed_agent.system_message
        
        # Test expedited mode
        expedited_agent = ExecutorAgent(
            agent_id="test_expedited",
            execution_mode="expedited"
        )
        assert "Expedited Execution specialist" in expedited_agent.system_message
        assert "Prioritize speed" in expedited_agent.system_message
    
    def test_execution_tools(self):
        """Test that execution tools are added correctly."""
        agent = ExecutorAgent(agent_id="test_executor")
        
        tool_names = [tool.name for tool in agent.tools]
        assert "ExecuteTask" in tool_names
        assert "TroubleshootIssue" in tool_names
        assert "TrackProgress" in tool_names


class TestAgentFactory:
    """Tests for the AgentFactory."""
    
    def test_create_researcher(self):
        """Test creating a researcher agent."""
        agent = AgentFactory.create_researcher(agent_id="factory_researcher")
        
        assert isinstance(agent, ResearcherAgent)
        assert agent.agent_id == "factory_researcher"
        assert agent.agent_type == "researcher"
    
    def test_create_planner(self):
        """Test creating a planner agent."""
        agent = AgentFactory.create_planner(
            agent_id="factory_planner",
            planning_framework="agile"
        )
        
        assert isinstance(agent, PlannerAgent)
        assert agent.agent_id == "factory_planner"
        assert agent.agent_type == "planner"
        assert agent.planning_framework == "agile"
    
    def test_create_executor(self):
        """Test creating an executor agent."""
        agent = AgentFactory.create_executor(
            agent_id="factory_executor",
            execution_mode="detailed"
        )
        
        assert isinstance(agent, ExecutorAgent)
        assert agent.agent_id == "factory_executor"
        assert agent.agent_type == "executor"
        assert agent.execution_mode == "detailed"
    
    def test_create_agent_generic(self):
        """Test creating an agent with the generic method."""
        agent = AgentFactory.create_agent(
            agent_type="planner",
            agent_id="generic_agent",
            agent_name="Generic Agent",
            verbose=True
        )
        
        assert isinstance(agent, PlannerAgent)
        assert agent.agent_id == "generic_agent"
        assert agent.agent_name == "Generic Agent"
        assert agent.verbose is True
    
    def test_invalid_agent_type(self):
        """Test that creating an invalid agent type raises an error."""
        with pytest.raises(ValueError, match="Unsupported agent type"):
            AgentFactory.create_agent(agent_type="invalid_type") 