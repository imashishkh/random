"""
Unit tests for the ProcessManager module.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import signal
import os

from src.agents.orchestration.process_manager import (
    ProcessManager,
    ShutdownCoordinator,
    HealthMonitor,
    ProcessStatus
)


@pytest.fixture
def mock_shutdown_coordinator():
    """Create a mock shutdown coordinator."""
    coordinator = MagicMock()
    coordinator.shutdown_requested = False
    coordinator.add_shutdown_task = MagicMock()
    coordinator.trigger_shutdown = AsyncMock()
    return coordinator


@pytest.fixture
def mock_health_monitor():
    """Create a mock health monitor."""
    monitor = MagicMock()
    monitor.start_monitoring = AsyncMock()
    monitor.stop_monitoring = AsyncMock()
    monitor.update_heartbeat = AsyncMock()
    monitor.check_health = AsyncMock(return_value=True)
    return monitor


@pytest.fixture
def process_manager(mock_shutdown_coordinator, mock_health_monitor):
    """Create a ProcessManager instance for testing."""
    with patch("src.agents.orchestration.process_manager.ShutdownCoordinator", 
               return_value=mock_shutdown_coordinator):
        with patch("src.agents.orchestration.process_manager.HealthMonitor", 
                   return_value=mock_health_monitor):
            manager = ProcessManager()
            manager._task_pool = {}  # Initialize directly for testing
            return manager


class TestShutdownCoordinator:
    """Tests for the ShutdownCoordinator class."""

    def test_initialization(self):
        """Test that a ShutdownCoordinator initializes correctly."""
        coordinator = ShutdownCoordinator()
        assert coordinator.shutdown_requested is False
        assert isinstance(coordinator.shutdown_tasks, list)
        assert len(coordinator.shutdown_tasks) == 0

    def test_add_shutdown_task(self):
        """Test adding a shutdown task."""
        coordinator = ShutdownCoordinator()
        
        # Create a mock task
        task = MagicMock()
        
        # Add the task
        coordinator.add_shutdown_task(task)
        
        # Verify the task was added
        assert len(coordinator.shutdown_tasks) == 1
        assert coordinator.shutdown_tasks[0] == task

    @pytest.mark.asyncio
    async def test_trigger_shutdown(self):
        """Test triggering a shutdown."""
        coordinator = ShutdownCoordinator()
        
        # Create mock tasks
        task1 = AsyncMock()
        task2 = AsyncMock()
        
        # Add the tasks
        coordinator.add_shutdown_task(task1)
        coordinator.add_shutdown_task(task2)
        
        # Trigger shutdown
        await coordinator.trigger_shutdown()
        
        # Verify tasks were called
        task1.assert_called_once()
        task2.assert_called_once()
        
        # Verify shutdown_requested was set
        assert coordinator.shutdown_requested is True

    def test_register_signal_handlers(self):
        """Test registering signal handlers."""
        coordinator = ShutdownCoordinator()
        
        # Mock signal.signal to verify it's called
        with patch("signal.signal") as mock_signal:
            coordinator.register_signal_handlers()
            
            # Verify signal.signal was called for each expected signal
            assert mock_signal.call_count >= 2  # SIGINT and SIGTERM at minimum


class TestHealthMonitor:
    """Tests for the HealthMonitor class."""

    def test_initialization(self):
        """Test that a HealthMonitor initializes correctly."""
        monitor = HealthMonitor()
        assert isinstance(monitor.agent_heartbeats, dict)
        assert len(monitor.agent_heartbeats) == 0
        assert monitor.monitoring_task is None
        assert isinstance(monitor.health_check_interval, (int, float))
        assert monitor.health_check_interval > 0

    @pytest.mark.asyncio
    async def test_start_monitoring(self):
        """Test starting health monitoring."""
        monitor = HealthMonitor()
        
        # Mock create_task to avoid actually creating a task
        with patch("asyncio.create_task") as mock_create_task:
            await monitor.start_monitoring()
            
            # Verify create_task was called
            mock_create_task.assert_called_once()
            
            # Verify the monitoring task was set
            assert monitor.monitoring_task is not None

    @pytest.mark.asyncio
    async def test_stop_monitoring(self):
        """Test stopping health monitoring."""
        monitor = HealthMonitor()
        
        # Create a mock task
        mock_task = MagicMock()
        mock_task.cancel = MagicMock()
        monitor.monitoring_task = mock_task
        
        # Stop monitoring
        await monitor.stop_monitoring()
        
        # Verify the task was cancelled
        mock_task.cancel.assert_called_once()
        
        # Verify the monitoring task was cleared
        assert monitor.monitoring_task is None

    def test_update_heartbeat(self):
        """Test updating an agent's heartbeat."""
        monitor = HealthMonitor()
        
        # Update heartbeat for an agent
        monitor.update_heartbeat("agent-1")
        
        # Verify the agent was added to heartbeats
        assert "agent-1" in monitor.agent_heartbeats
        
        # Verify the timestamp is recent
        assert monitor.agent_heartbeats["agent-1"] > 0

    @pytest.mark.asyncio
    async def test_check_health(self):
        """Test checking agent health."""
        monitor = HealthMonitor()
        
        # Add some heartbeats
        current_time = asyncio.get_event_loop().time()
        monitor.agent_heartbeats = {
            "healthy-agent": current_time,  # Just updated
            "unhealthy-agent": current_time - 300  # Updated 5 minutes ago (should be unhealthy)
        }
        
        # Check health for the healthy agent
        healthy = await monitor.check_health("healthy-agent")
        
        # Verify the agent is healthy
        assert healthy is True
        
        # Check health for the unhealthy agent
        unhealthy = await monitor.check_health("unhealthy-agent")
        
        # Verify the agent is unhealthy
        assert unhealthy is False
        
        # Check health for a non-existent agent
        non_existent = await monitor.check_health("non-existent-agent")
        
        # Verify the agent is considered unhealthy
        assert non_existent is False


class TestProcessManager:
    """Tests for the ProcessManager class."""

    def test_initialization(self, process_manager, mock_shutdown_coordinator, mock_health_monitor):
        """Test that a ProcessManager initializes correctly."""
        assert process_manager.shutdown_coordinator == mock_shutdown_coordinator
        assert process_manager.health_monitor == mock_health_monitor
        assert isinstance(process_manager._task_pool, dict)
        assert len(process_manager._task_pool) == 0

    @pytest.mark.asyncio
    async def test_register_agent(self, process_manager):
        """Test registering an agent."""
        # Create a mock agent
        mock_agent = MagicMock()
        mock_agent.agent_id = "test-agent"
        mock_agent.run = AsyncMock()
        
        # Register the agent
        await process_manager.register_agent(mock_agent)
        
        # Verify the agent was registered
        assert "test-agent" in process_manager._task_pool
        assert process_manager._task_pool["test-agent"]["agent"] == mock_agent
        assert process_manager._task_pool["test-agent"]["status"] == ProcessStatus.REGISTERED

    @pytest.mark.asyncio
    async def test_start_agent(self, process_manager, mock_health_monitor):
        """Test starting an agent."""
        # Create and register a mock agent
        mock_agent = MagicMock()
        mock_agent.agent_id = "test-agent"
        mock_agent.run = AsyncMock()
        
        process_manager._task_pool["test-agent"] = {
            "agent": mock_agent,
            "status": ProcessStatus.REGISTERED,
            "task": None
        }
        
        # Mock create_task to avoid actually creating a task
        with patch("asyncio.create_task") as mock_create_task:
            # Start the agent
            await process_manager.start_agent("test-agent")
            
            # Verify create_task was called
            mock_create_task.assert_called_once()
            
            # Verify the agent's status was updated
            assert process_manager._task_pool["test-agent"]["status"] == ProcessStatus.RUNNING
            
            # Verify health monitor was called
            mock_health_monitor.update_heartbeat.assert_called_once_with("test-agent")

    @pytest.mark.asyncio
    async def test_stop_agent(self, process_manager):
        """Test stopping an agent."""
        # Create a mock task
        mock_task = MagicMock()
        mock_task.cancel = MagicMock()
        
        # Register and start a mock agent
        process_manager._task_pool["test-agent"] = {
            "agent": MagicMock(),
            "status": ProcessStatus.RUNNING,
            "task": mock_task
        }
        
        # Stop the agent
        await process_manager.stop_agent("test-agent")
        
        # Verify the task was cancelled
        mock_task.cancel.assert_called_once()
        
        # Verify the agent's status was updated
        assert process_manager._task_pool["test-agent"]["status"] == ProcessStatus.STOPPED

    @pytest.mark.asyncio
    async def test_restart_agent(self, process_manager):
        """Test restarting an agent."""
        # Create and register a mock agent
        mock_agent = MagicMock()
        mock_agent.agent_id = "test-agent"
        mock_agent.run = AsyncMock()
        
        # Create a mock task
        mock_task = MagicMock()
        mock_task.cancel = MagicMock()
        
        process_manager._task_pool["test-agent"] = {
            "agent": mock_agent,
            "status": ProcessStatus.RUNNING,
            "task": mock_task
        }
        
        # Mock stop_agent and start_agent
        process_manager.stop_agent = AsyncMock()
        process_manager.start_agent = AsyncMock()
        
        # Restart the agent
        await process_manager.restart_agent("test-agent")
        
        # Verify stop_agent and start_agent were called
        process_manager.stop_agent.assert_called_once_with("test-agent")
        process_manager.start_agent.assert_called_once_with("test-agent")

    @pytest.mark.asyncio
    async def test_is_agent_running(self, process_manager, mock_health_monitor):
        """Test checking if an agent is running."""
        # Setup test cases
        process_manager._task_pool = {
            "running-agent": {
                "status": ProcessStatus.RUNNING,
                "task": MagicMock()
            },
            "stopped-agent": {
                "status": ProcessStatus.STOPPED,
                "task": None
            },
            "unknown-status": {
                "status": "invalid-status",
                "task": None
            }
        }
        
        # Check running agent
        is_running = await process_manager.is_agent_running("running-agent")
        assert is_running is True
        
        # Check stopped agent
        is_running = await process_manager.is_agent_running("stopped-agent")
        assert is_running is False
        
        # Check agent with unknown status
        is_running = await process_manager.is_agent_running("unknown-status")
        assert is_running is False
        
        # Check non-existent agent
        is_running = await process_manager.is_agent_running("non-existent-agent")
        assert is_running is False

    @pytest.mark.asyncio
    async def test_get_agent_status(self, process_manager):
        """Test getting an agent's status."""
        # Setup test cases
        process_manager._task_pool = {
            "running-agent": {
                "status": ProcessStatus.RUNNING,
                "task": MagicMock()
            },
            "stopped-agent": {
                "status": ProcessStatus.STOPPED,
                "task": None
            }
        }
        
        # Check running agent
        status = await process_manager.get_agent_status("running-agent")
        assert status == ProcessStatus.RUNNING
        
        # Check stopped agent
        status = await process_manager.get_agent_status("stopped-agent")
        assert status == ProcessStatus.STOPPED
        
        # Check non-existent agent
        status = await process_manager.get_agent_status("non-existent-agent")
        assert status == ProcessStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_get_all_agents(self, process_manager):
        """Test getting all agents."""
        # Setup test cases
        process_manager._task_pool = {
            "agent-1": {
                "agent": MagicMock(agent_id="agent-1"),
                "status": ProcessStatus.RUNNING,
                "task": MagicMock()
            },
            "agent-2": {
                "agent": MagicMock(agent_id="agent-2"),
                "status": ProcessStatus.STOPPED,
                "task": None
            }
        }
        
        # Get all agents
        agents = await process_manager.get_all_agents()
        
        # Verify the agents were returned
        assert len(agents) == 2
        assert agents[0].agent_id == "agent-1"
        assert agents[1].agent_id == "agent-2"

    @pytest.mark.asyncio
    async def test_shutdown(self, process_manager, mock_shutdown_coordinator):
        """Test shutting down the process manager."""
        # Setup test cases
        mock_task_1 = MagicMock()
        mock_task_1.cancel = MagicMock()
        
        mock_task_2 = MagicMock()
        mock_task_2.cancel = MagicMock()
        
        process_manager._task_pool = {
            "agent-1": {
                "agent": MagicMock(agent_id="agent-1"),
                "status": ProcessStatus.RUNNING,
                "task": mock_task_1
            },
            "agent-2": {
                "agent": MagicMock(agent_id="agent-2"),
                "status": ProcessStatus.RUNNING,
                "task": mock_task_2
            }
        }
        
        # Mock health_monitor
        process_manager.health_monitor.stop_monitoring = AsyncMock()
        
        # Shutdown the process manager
        await process_manager.shutdown()
        
        # Verify all tasks were cancelled
        mock_task_1.cancel.assert_called_once()
        mock_task_2.cancel.assert_called_once()
        
        # Verify shutdown coordinator was triggered
        mock_shutdown_coordinator.trigger_shutdown.assert_called_once()
        
        # Verify health monitor was stopped
        process_manager.health_monitor.stop_monitoring.assert_called_once()
        
        # Verify all agents were marked as stopped
        for agent_id, agent_data in process_manager._task_pool.items():
            assert agent_data["status"] == ProcessStatus.STOPPED

    @pytest.mark.asyncio
    async def test_monitor_task(self, process_manager):
        """Test the _monitor_task method."""
        # Create a mock agent and task
        mock_agent = MagicMock()
        mock_agent.agent_id = "test-agent"
        mock_agent.run = AsyncMock()
        
        # Setup the state for the test
        process_manager._task_pool["test-agent"] = {
            "agent": mock_agent,
            "status": ProcessStatus.RUNNING,
            "task": None,
            "metadata": {}
        }
        
        # Mock health_monitor
        process_manager.health_monitor.update_heartbeat = AsyncMock()
        
        # Call _monitor_task directly
        await process_manager._monitor_task("test-agent", mock_agent)
        
        # Verify the agent's run method was called
        mock_agent.run.assert_called_once()
        
        # Verify heartbeat was updated
        process_manager.health_monitor.update_heartbeat.assert_called_with("test-agent")

    @pytest.mark.asyncio
    async def test_monitor_task_with_exception(self, process_manager):
        """Test the _monitor_task method when the agent raises an exception."""
        # Create a mock agent that raises an exception
        mock_agent = MagicMock()
        mock_agent.agent_id = "test-agent"
        mock_agent.run = AsyncMock(side_effect=Exception("Test exception"))
        
        # Setup the state for the test
        process_manager._task_pool["test-agent"] = {
            "agent": mock_agent,
            "status": ProcessStatus.RUNNING,
            "task": None,
            "metadata": {}
        }
        
        # Mock health_monitor
        process_manager.health_monitor.update_heartbeat = AsyncMock()
        
        # Mock logging to verify it's called
        with patch("logging.error") as mock_logging:
            # Call _monitor_task directly
            await process_manager._monitor_task("test-agent", mock_agent)
            
            # Verify logging.error was called
            mock_logging.assert_called_once()
            
            # Verify the agent's status was updated to ERROR
            assert process_manager._task_pool["test-agent"]["status"] == ProcessStatus.ERROR
            
            # Verify metadata contains error information
            assert "error" in process_manager._task_pool["test-agent"]["metadata"]
            assert "Test exception" in process_manager._task_pool["test-agent"]["metadata"]["error"] 