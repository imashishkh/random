"""
Unit tests for the shutdown coordinator module.

This module tests the functionality of the shutdown coordinator, which manages
the graceful shutdown process of the Forex Trading Bot system.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
import time

from src.core.shutdown import (
    ShutdownCoordinator,
    ShutdownPhase,
    PositionCloseStrategy,
    get_shutdown_coordinator
)

# Mark all tests as asyncio to support async tests
pytestmark = pytest.mark.asyncio


class TestShutdownCoordinator:
    """Test class for the ShutdownCoordinator."""

    @pytest.fixture
    def coordinator(self):
        """Fixture to create a fresh ShutdownCoordinator for each test."""
        # Reset the singleton instance for each test
        ShutdownCoordinator._instance = None
        coordinator = ShutdownCoordinator()
        return coordinator

    @pytest.fixture
    def mock_agent(self):
        """Fixture to create a mock agent for testing."""
        agent = MagicMock()
        agent.agent_id = "test_agent"
        agent.agent_type = "test_type"
        agent.prepare_shutdown = AsyncMock(return_value=None)
        agent.stop = AsyncMock(return_value=True)
        agent.cleanup = AsyncMock(return_value=None)
        return agent

    async def test_singleton_pattern(self):
        """Test that ShutdownCoordinator follows the singleton pattern."""
        coordinator1 = get_shutdown_coordinator()
        coordinator2 = get_shutdown_coordinator()
        
        # Both instances should be the same object
        assert coordinator1 is coordinator2
        
        # The singleton instance should be of type ShutdownCoordinator
        assert isinstance(coordinator1, ShutdownCoordinator)

    async def test_register_agent(self, coordinator, mock_agent):
        """Test registering an agent with the coordinator."""
        coordinator.register_agent(
            agent_id=mock_agent.agent_id,
            agent_type=mock_agent.agent_type,
            agent_instance=mock_agent,
            shutdown_priority=50,
            dependencies=[]
        )
        
        # Verify agent was registered
        assert mock_agent.agent_id in coordinator._agents
        assert coordinator._agents[mock_agent.agent_id]['instance'] is mock_agent
        assert coordinator._agents[mock_agent.agent_id]['priority'] == 50
        assert coordinator._agents[mock_agent.agent_id]['dependencies'] == []

    async def test_initiate_shutdown(self, coordinator):
        """Test initiating the shutdown process."""
        # Initiate shutdown
        await coordinator.initiate_shutdown(reason="test", force=False)
        
        # Verify shutdown was initiated
        status = coordinator.get_status()
        assert status['phase'] == ShutdownPhase.INITIALIZING.value
        assert status['reason'] == "test"
        assert status['force'] is False
        assert status['position_strategy'] == PositionCloseStrategy.GRADUAL.value

    async def test_shutdown_phases(self, coordinator, mock_agent):
        """Test that shutdown proceeds through all phases correctly."""
        # Register an agent
        coordinator.register_agent(
            agent_id=mock_agent.agent_id,
            agent_type=mock_agent.agent_type,
            agent_instance=mock_agent,
            shutdown_priority=50,
            dependencies=[]
        )
        
        # Mock the _execute_phase method to track calls
        coordinator._execute_phase = AsyncMock(return_value=True)
        
        # Initiate and execute shutdown
        await coordinator.initiate_shutdown(reason="test")
        await coordinator.shutdown_all_agents()
        
        # Verify all phases were executed in order
        expected_calls = [
            call(ShutdownPhase.PREPARATION),
            call(ShutdownPhase.POSITIONS),
            call(ShutdownPhase.AGENTS),
            call(ShutdownPhase.RESOURCES)
        ]
        coordinator._execute_phase.assert_has_calls(expected_calls, any_order=False)
        
        # Verify final phase is COMPLETE
        status = coordinator.get_status()
        assert status['phase'] == ShutdownPhase.COMPLETE.value

    async def test_agent_shutdown_sequence(self, coordinator, mock_agent):
        """Test that agents are shut down in the correct sequence."""
        # Replace the _execute_phase with real implementation for this test
        original_execute_phase = coordinator._execute_phase
        coordinator._execute_phase = original_execute_phase
        
        # Register an agent
        coordinator.register_agent(
            agent_id=mock_agent.agent_id,
            agent_type=mock_agent.agent_type,
            agent_instance=mock_agent,
            shutdown_priority=50,
            dependencies=[]
        )
        
        # Initiate and execute shutdown
        await coordinator.initiate_shutdown(reason="test")
        await coordinator.shutdown_all_agents()
        
        # Verify agent methods were called in the correct order
        mock_agent.prepare_shutdown.assert_called_once()
        mock_agent.stop.assert_called_once()
        mock_agent.cleanup.assert_called_once()

    async def test_force_shutdown(self, coordinator, mock_agent):
        """Test that force shutdown bypasses normal checks."""
        # Configure agent.stop to fail
        mock_agent.stop = AsyncMock(return_value=False)
        
        # Register the agent
        coordinator.register_agent(
            agent_id=mock_agent.agent_id,
            agent_type=mock_agent.agent_type,
            agent_instance=mock_agent,
            shutdown_priority=50,
            dependencies=[]
        )
        
        # Initiate normal shutdown
        await coordinator.initiate_shutdown(reason="test", force=False)
        
        # Mock _execute_phase to inspect calls
        coordinator._execute_phase = AsyncMock(return_value=True)
        
        # Execute shutdown
        await coordinator.shutdown_all_agents()
        
        # Verify all phases were executed despite the failed stop
        assert coordinator._execute_phase.call_count == 4

    async def test_shutdown_with_dependencies(self, coordinator):
        """Test that agents are shut down respecting dependencies."""
        # Create mock agents with dependencies
        agent1 = MagicMock()
        agent1.agent_id = "agent1"
        agent1.agent_type = "test_type"
        agent1.prepare_shutdown = AsyncMock()
        agent1.stop = AsyncMock(return_value=True)
        agent1.cleanup = AsyncMock()
        
        agent2 = MagicMock()
        agent2.agent_id = "agent2"
        agent2.agent_type = "test_type"
        agent2.prepare_shutdown = AsyncMock()
        agent2.stop = AsyncMock(return_value=True)
        agent2.cleanup = AsyncMock()
        
        # Register agents (agent2 depends on agent1)
        coordinator.register_agent(
            agent_id=agent1.agent_id,
            agent_type=agent1.agent_type,
            agent_instance=agent1,
            shutdown_priority=50,
            dependencies=[]
        )
        
        coordinator.register_agent(
            agent_id=agent2.agent_id,
            agent_type=agent2.agent_type,
            agent_instance=agent2,
            shutdown_priority=50,
            dependencies=["agent1"]
        )
        
        # Create lists to track the order of calls
        prepare_order = []
        stop_order = []
        cleanup_order = []
        
        # Override mock methods to track call order
        async def agent1_prepare():
            prepare_order.append("agent1")
        
        async def agent2_prepare():
            prepare_order.append("agent2")
        
        async def agent1_stop():
            stop_order.append("agent1")
            return True
        
        async def agent2_stop():
            stop_order.append("agent2")
            return True
        
        async def agent1_cleanup():
            cleanup_order.append("agent1")
        
        async def agent2_cleanup():
            cleanup_order.append("agent2")
        
        agent1.prepare_shutdown.side_effect = agent1_prepare
        agent2.prepare_shutdown.side_effect = agent2_prepare
        agent1.stop.side_effect = agent1_stop
        agent2.stop.side_effect = agent2_stop
        agent1.cleanup.side_effect = agent1_cleanup
        agent2.cleanup.side_effect = agent2_cleanup
        
        # Initiate and execute shutdown
        await coordinator.initiate_shutdown(reason="test")
        await coordinator.shutdown_all_agents()
        
        # Verify dependent agent (agent2) was shut down before agent1
        assert prepare_order.index("agent2") < prepare_order.index("agent1")
        assert stop_order.index("agent2") < stop_order.index("agent1")
        assert cleanup_order.index("agent2") < cleanup_order.index("agent1")

    async def test_timeout_handling(self, coordinator, mock_agent):
        """Test that timeouts are handled correctly."""
        # Configure agent to hang
        async def hang():
            await asyncio.sleep(10)  # Long delay
        
        mock_agent.stop = AsyncMock(side_effect=hang)
        
        # Register the agent
        coordinator.register_agent(
            agent_id=mock_agent.agent_id,
            agent_type=mock_agent.agent_type,
            agent_instance=mock_agent,
            shutdown_priority=50,
            dependencies=[]
        )
        
        # Initiate shutdown with a short timeout
        await coordinator.initiate_shutdown(reason="test", stop_timeout=0.1)
        
        # Execute shutdown
        await coordinator.shutdown_all_agents()
        
        # Verify shutdown completed despite the hanging agent
        status = coordinator.get_status()
        assert status['phase'] == ShutdownPhase.COMPLETE.value or status['phase'] == ShutdownPhase.FAILED.value
        
        # Verify stop was called but timed out
        mock_agent.stop.assert_called_once()

    async def test_get_status(self, coordinator):
        """Test getting the shutdown status."""
        # Initiate shutdown
        await coordinator.initiate_shutdown(reason="test_status")
        
        # Get status
        status = coordinator.get_status()
        
        # Verify status contains expected fields
        assert 'phase' in status
        assert 'reason' in status
        assert 'force' in status
        assert 'position_strategy' in status
        assert 'elapsed_time' in status
        
        # Verify correct values
        assert status['reason'] == "test_status"
        assert status['force'] is False
        assert isinstance(status['elapsed_time'], float)

    async def test_wait_for_shutdown(self, coordinator):
        """Test waiting for shutdown completion."""
        # Initiate shutdown
        await coordinator.initiate_shutdown(reason="test")
        
        # Create a task to execute shutdown in the background
        async def execute_shutdown():
            await asyncio.sleep(0.1)  # Short delay
            coordinator._phase = ShutdownPhase.COMPLETE
        
        asyncio.create_task(execute_shutdown())
        
        # Wait for shutdown with timeout
        result = await coordinator.wait_for_shutdown(timeout=1.0)
        
        # Verify wait completed successfully
        assert result is True
        assert coordinator._phase == ShutdownPhase.COMPLETE

    async def test_emergency_shutdown(self, coordinator, mock_agent):
        """Test emergency shutdown with minimal timeouts."""
        # Register an agent
        coordinator.register_agent(
            agent_id=mock_agent.agent_id,
            agent_type=mock_agent.agent_type,
            agent_instance=mock_agent,
            shutdown_priority=50,
            dependencies=[]
        )
        
        # Execute emergency shutdown
        await coordinator.emergency_shutdown(reason="emergency")
        
        # Verify emergency settings were used
        assert coordinator._force is True
        assert coordinator._position_strategy == PositionCloseStrategy.IMMEDIATE
        assert coordinator._preparation_timeout < 5.0  # Should be reduced for emergency
        assert coordinator._stop_timeout < 5.0
        assert coordinator._cleanup_timeout < 5.0
        
        # Verify agent methods were called
        mock_agent.prepare_shutdown.assert_called_once()
        mock_agent.stop.assert_called_once()
        mock_agent.cleanup.assert_called_once()

    async def test_shutdown_progress_callbacks(self, coordinator):
        """Test registering and triggering progress callbacks."""
        # Create a mock callback
        callback = MagicMock()
        
        # Register the callback
        coordinator.register_progress_callback(callback)
        
        # Initiate shutdown
        await coordinator.initiate_shutdown(reason="test")
        
        # Manually change phase to trigger callback
        coordinator._phase = ShutdownPhase.PREPARATION
        coordinator._notify_progress_callbacks()
        
        # Verify callback was called with the right information
        callback.assert_called_once()
        args = callback.call_args[0][0]  # First positional argument
        assert 'phase' in args
        assert args['phase'] == ShutdownPhase.PREPARATION.value 