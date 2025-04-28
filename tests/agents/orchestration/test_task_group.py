"""
Unit tests for the TaskGroup module.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.orchestration.task_group import (
    TaskGroup, 
    TaskGroupManager, 
    TaskGroupStatus
)


@pytest.fixture
def mock_process_manager():
    """Create a mock process manager for testing."""
    process_manager = MagicMock()
    process_manager.register_agent = AsyncMock()
    process_manager.start_agent = AsyncMock()
    process_manager.stop_agent = AsyncMock()
    process_manager.is_agent_running = AsyncMock(return_value=True)
    return process_manager


@pytest.fixture
def task_group(mock_process_manager):
    """Create a TaskGroup instance for testing."""
    return TaskGroup(
        group_id="test-group",
        name="Test Group",
        description="Test group description",
        process_manager=mock_process_manager
    )


@pytest.fixture
def task_group_manager(mock_process_manager):
    """Create a TaskGroupManager instance for testing."""
    return TaskGroupManager(process_manager=mock_process_manager)


class TestTaskGroup:
    """Tests for the TaskGroup class."""

    def test_initialization(self, task_group):
        """Test that a TaskGroup initializes correctly."""
        assert task_group.group_id == "test-group"
        assert task_group.name == "Test Group"
        assert task_group.description == "Test group description"
        assert task_group.status == TaskGroupStatus.PENDING
        assert isinstance(task_group.agent_configs, list)
        assert len(task_group.agent_configs) == 0
        assert isinstance(task_group.registered_agents, list)
        assert len(task_group.registered_agents) == 0

    def test_add_agent_config(self, task_group):
        """Test adding agent configurations to a TaskGroup."""
        # Add a single agent config
        config = {
            "agent_type": "test_agent",
            "agent_id": "test-agent-1",
            "agent_name": "Test Agent 1",
            "config": {"param1": "value1"}
        }
        task_group.add_agent_config(config)
        
        # Verify it was added
        assert len(task_group.agent_configs) == 1
        assert task_group.agent_configs[0] == config
        
        # Add another config
        config2 = {
            "agent_type": "test_agent",
            "agent_id": "test-agent-2",
            "agent_name": "Test Agent 2",
            "config": {"param1": "value2"}
        }
        task_group.add_agent_config(config2)
        
        # Verify both configs are present
        assert len(task_group.agent_configs) == 2
        assert task_group.agent_configs[1] == config2

    @pytest.mark.asyncio
    async def test_register_agents(self, task_group, mock_process_manager):
        """Test registering agents with the process manager."""
        # Add agent configs
        task_group.add_agent_config({
            "agent_type": "test_agent",
            "agent_id": "test-agent-1",
            "agent_name": "Test Agent 1",
            "config": {"param1": "value1"}
        })
        task_group.add_agent_config({
            "agent_type": "test_agent",
            "agent_id": "test-agent-2",
            "agent_name": "Test Agent 2",
            "config": {"param1": "value2"}
        })
        
        # Mock the agent factory
        mock_agent = MagicMock()
        mock_agent.agent_id = "test-agent-1"
        
        with patch("src.agents.factory.AgentFactory.create_agent", return_value=mock_agent):
            # Register the agents
            await task_group.register_agents()
            
            # Verify process manager was called
            assert mock_process_manager.register_agent.call_count == 2
            
            # Verify agents were registered
            assert len(task_group.registered_agents) == 2

    @pytest.mark.asyncio
    async def test_start(self, task_group, mock_process_manager):
        """Test starting a TaskGroup."""
        # Add agent configs and register them
        task_group.add_agent_config({
            "agent_type": "test_agent",
            "agent_id": "test-agent-1"
        })
        
        mock_agent = MagicMock()
        mock_agent.agent_id = "test-agent-1"
        task_group.registered_agents = [mock_agent]
        
        # Start the task group
        await task_group.start()
        
        # Verify the process manager was called to start the agent
        mock_process_manager.start_agent.assert_called_once_with("test-agent-1")
        
        # Verify the task group status changed
        assert task_group.status == TaskGroupStatus.RUNNING

    @pytest.mark.asyncio
    async def test_check_completion(self, task_group, mock_process_manager):
        """Test checking completion status of a TaskGroup."""
        # Add agent configs and register them
        task_group.add_agent_config({
            "agent_type": "test_agent",
            "agent_id": "test-agent-1"
        })
        
        mock_agent = MagicMock()
        mock_agent.agent_id = "test-agent-1"
        task_group.registered_agents = [mock_agent]
        task_group.status = TaskGroupStatus.RUNNING
        
        # Mock that the agent is not running
        mock_process_manager.is_agent_running.return_value = False
        
        # Check completion
        completed = await task_group.check_completion()
        
        # Verify agent status was checked
        mock_process_manager.is_agent_running.assert_called_once_with("test-agent-1")
        
        # Verify the task group was marked as completed
        assert completed is True
        assert task_group.status == TaskGroupStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cancel(self, task_group, mock_process_manager):
        """Test cancelling a TaskGroup."""
        # Add agent configs and register them
        task_group.add_agent_config({
            "agent_type": "test_agent",
            "agent_id": "test-agent-1"
        })
        
        mock_agent = MagicMock()
        mock_agent.agent_id = "test-agent-1"
        task_group.registered_agents = [mock_agent]
        task_group.status = TaskGroupStatus.RUNNING
        
        # Cancel the task group
        await task_group.cancel(reason="Test cancellation")
        
        # Verify the process manager was called to stop the agent
        mock_process_manager.stop_agent.assert_called_once_with("test-agent-1")
        
        # Verify the task group status changed
        assert task_group.status == TaskGroupStatus.CANCELLED
        
        # Verify metadata was updated
        assert task_group.metadata["cancel_reason"] == "Test cancellation"

    def test_get_metrics(self, task_group):
        """Test getting metrics from a TaskGroup."""
        # Set up the task group with some history
        task_group.status_history = [
            {"status": TaskGroupStatus.PENDING, "timestamp": 1000},
            {"status": TaskGroupStatus.STARTING, "timestamp": 1100},
            {"status": TaskGroupStatus.RUNNING, "timestamp": 1200},
            {"status": TaskGroupStatus.COMPLETED, "timestamp": 1500},
        ]
        task_group.add_agent_config({"agent_id": "agent1"})
        task_group.add_agent_config({"agent_id": "agent2"})
        task_group.status = TaskGroupStatus.COMPLETED
        
        # Get metrics
        metrics = task_group.get_metrics()
        
        # Verify metrics
        assert metrics["group_id"] == "test-group"
        assert metrics["name"] == "Test Group"
        assert metrics["status"] == TaskGroupStatus.COMPLETED.name
        assert metrics["agent_count"] == 2
        assert metrics["duration"] == 500  # 1500 - 1000
        assert isinstance(metrics["status_history"], list)
        assert len(metrics["status_history"]) == 4


class TestTaskGroupManager:
    """Tests for the TaskGroupManager class."""

    def test_initialization(self, task_group_manager):
        """Test that a TaskGroupManager initializes correctly."""
        assert isinstance(task_group_manager.task_groups, dict)
        assert len(task_group_manager.task_groups) == 0
        assert isinstance(task_group_manager.group_dependencies, dict)
        assert len(task_group_manager.group_dependencies) == 0

    def test_create_task_group(self, task_group_manager):
        """Test creating a task group."""
        # Create a task group
        group = task_group_manager.create_task_group(
            group_id="test-group",
            name="Test Group",
            description="Test description",
            depends_on=["other-group"]
        )
        
        # Verify it was created and stored
        assert isinstance(group, TaskGroup)
        assert group.group_id == "test-group"
        assert group.name == "Test Group"
        assert group.description == "Test description"
        assert "test-group" in task_group_manager.task_groups
        assert task_group_manager.task_groups["test-group"] == group
        
        # Verify dependencies were stored
        assert "test-group" in task_group_manager.group_dependencies
        assert task_group_manager.group_dependencies["test-group"] == ["other-group"]

    def test_get_independent_groups(self, task_group_manager):
        """Test getting independent groups with no dependencies."""
        # Create groups with and without dependencies
        group1 = task_group_manager.create_task_group(
            group_id="group1",
            name="Group 1"
        )
        group2 = task_group_manager.create_task_group(
            group_id="group2",
            name="Group 2",
            depends_on=["group1"]
        )
        group3 = task_group_manager.create_task_group(
            group_id="group3",
            name="Group 3"
        )
        
        # Get independent groups
        independent_groups = task_group_manager.get_independent_groups()
        
        # Verify only the groups with no dependencies are returned
        assert len(independent_groups) == 2
        assert "group1" in independent_groups
        assert "group3" in independent_groups
        assert "group2" not in independent_groups

    def test_get_dependency_status(self, task_group_manager):
        """Test getting dependency status for a group."""
        # Create groups with dependencies
        group1 = task_group_manager.create_task_group(
            group_id="group1",
            name="Group 1"
        )
        group2 = task_group_manager.create_task_group(
            group_id="group2",
            name="Group 2"
        )
        group3 = task_group_manager.create_task_group(
            group_id="group3",
            name="Group 3",
            depends_on=["group1", "group2"]
        )
        
        # Set group statuses
        group1.status = TaskGroupStatus.COMPLETED
        group2.status = TaskGroupStatus.RUNNING
        
        # Check dependency status
        status = task_group_manager.get_dependency_status("group3")
        
        # Verify the status shows the correct dependencies
        assert status["all_completed"] is False
        assert status["completed"] == ["group1"]
        assert status["pending"] == ["group2"]

    @pytest.mark.asyncio
    async def test_start_all_independent_groups(self, task_group_manager):
        """Test starting all independent groups."""
        # Create groups with and without dependencies
        group1 = task_group_manager.create_task_group(
            group_id="group1",
            name="Group 1"
        )
        group2 = task_group_manager.create_task_group(
            group_id="group2",
            name="Group 2",
            depends_on=["group1"]
        )
        
        # Mock the start method
        group1.start = AsyncMock()
        group2.start = AsyncMock()
        
        # Start independent groups
        started = await task_group_manager.start_all_independent_groups()
        
        # Verify only independent group was started
        assert started == ["group1"]
        group1.start.assert_called_once()
        group2.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_group_with_dependencies(self, task_group_manager):
        """Test starting a group with dependencies."""
        # Create groups with dependencies
        group1 = task_group_manager.create_task_group(
            group_id="group1",
            name="Group 1"
        )
        group2 = task_group_manager.create_task_group(
            group_id="group2",
            name="Group 2",
            depends_on=["group1"]
        )
        
        # Set first group as completed
        group1.status = TaskGroupStatus.COMPLETED
        
        # Mock the start method
        group2.start = AsyncMock()
        
        # Try to start the dependent group
        started = await task_group_manager.start_group("group2")
        
        # Verify it was started because dependency is satisfied
        assert started is True
        group2.start.assert_called_once()
        
        # Reset and try with incomplete dependency
        group2.start.reset_mock()
        group1.status = TaskGroupStatus.RUNNING
        
        # Try to start the dependent group
        started = await task_group_manager.start_group("group2")
        
        # Verify it was not started because dependency is not satisfied
        assert started is False
        group2.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_and_start_dependent_groups(self, task_group_manager):
        """Test checking and starting dependent groups."""
        # Create groups with dependencies
        group1 = task_group_manager.create_task_group(
            group_id="group1",
            name="Group 1"
        )
        group2 = task_group_manager.create_task_group(
            group_id="group2",
            name="Group 2",
            depends_on=["group1"]
        )
        group3 = task_group_manager.create_task_group(
            group_id="group3",
            name="Group 3",
            depends_on=["group2"]
        )
        
        # Mock methods
        group1.check_completion = AsyncMock(return_value=True)
        group2.check_completion = AsyncMock(return_value=False)
        group3.check_completion = AsyncMock(return_value=False)
        
        group1.start = AsyncMock()
        group2.start = AsyncMock()
        group3.start = AsyncMock()
        
        # Set first group as completed
        group1.status = TaskGroupStatus.COMPLETED
        
        # Check and start dependents
        started = await task_group_manager.check_and_start_dependent_groups()
        
        # Verify only group2 was started
        assert started == ["group2"]
        group1.start.assert_not_called()
        group2.start.assert_called_once()
        group3.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_all_groups(self, task_group_manager):
        """Test cancelling all groups."""
        # Create groups
        group1 = task_group_manager.create_task_group(
            group_id="group1",
            name="Group 1"
        )
        group2 = task_group_manager.create_task_group(
            group_id="group2",
            name="Group 2"
        )
        
        # Mock cancel method
        group1.cancel = AsyncMock()
        group2.cancel = AsyncMock()
        
        # Cancel all groups
        await task_group_manager.cancel_all_groups(reason="Test cancellation")
        
        # Verify all groups were cancelled
        group1.cancel.assert_called_once_with(reason="Test cancellation")
        group2.cancel.assert_called_once_with(reason="Test cancellation")

    @pytest.mark.asyncio
    async def test_wait_for_all_groups(self, task_group_manager):
        """Test waiting for all groups to complete."""
        # Create groups
        group1 = task_group_manager.create_task_group(
            group_id="group1",
            name="Group 1"
        )
        group2 = task_group_manager.create_task_group(
            group_id="group2",
            name="Group 2",
            depends_on=["group1"]
        )
        
        # Mock methods
        task_group_manager.check_and_start_dependent_groups = AsyncMock(
            side_effect=[["group2"], []]
        )
        
        group1.check_completion = AsyncMock(
            side_effect=[False, True, True]
        )
        group2.check_completion = AsyncMock(
            side_effect=[False, True]
        )
        
        group1.status = TaskGroupStatus.RUNNING
        group2.status = TaskGroupStatus.PENDING
        
        # Create a mock sleep to avoid actual sleeping
        with patch("asyncio.sleep", AsyncMock()):
            # Wait for all groups
            await task_group_manager.wait_for_all_groups(check_interval=0.1)
            
            # Verify methods were called appropriately
            assert group1.check_completion.call_count >= 2
            assert group2.check_completion.call_count >= 1
            assert task_group_manager.check_and_start_dependent_groups.call_count >= 1

    def test_get_all_metrics(self, task_group_manager):
        """Test getting metrics for all groups."""
        # Create groups
        group1 = task_group_manager.create_task_group(
            group_id="group1",
            name="Group 1"
        )
        group2 = task_group_manager.create_task_group(
            group_id="group2",
            name="Group 2",
            depends_on=["group1"]
        )
        
        # Mock get_metrics
        group1.get_metrics = MagicMock(return_value={"name": "Group 1", "status": "COMPLETED"})
        group2.get_metrics = MagicMock(return_value={"name": "Group 2", "status": "RUNNING"})
        
        # Get metrics
        metrics = task_group_manager.get_all_metrics()
        
        # Verify metrics structure
        assert isinstance(metrics, dict)
        assert "total_groups" in metrics
        assert metrics["total_groups"] == 2
        assert "groups" in metrics
        assert len(metrics["groups"]) == 2
        assert "group1" in metrics["groups"]
        assert "group2" in metrics["groups"]
        assert metrics["groups"]["group1"]["name"] == "Group 1"
        assert metrics["groups"]["group2"]["status"] == "RUNNING"
        assert "dependencies" in metrics
        assert "group2" in metrics["dependencies"]
        assert metrics["dependencies"]["group2"] == ["group1"] 