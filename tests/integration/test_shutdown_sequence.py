"""
Integration tests for the graceful shutdown sequence.

This module tests the complete shutdown sequence, ensuring all components
(shutdown coordinator, position closer, agent terminator, resource cleaner)
work together properly.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import time
import logging

from src.core.shutdown import (
    ShutdownCoordinator,
    ShutdownPhase,
    PositionCloseStrategy,
    get_shutdown_coordinator
)
from src.core.position_closer import PositionCloser, get_position_closer
from src.core.agent_terminator import AgentTerminator, get_agent_terminator
from src.core.resource_cleaner import ResourceCleaner, get_resource_cleaner, register_cleanup_callback

# Mark all tests as asyncio to support async tests
pytestmark = pytest.mark.asyncio


class TestShutdownSequence:
    """Integration tests for the shutdown sequence."""

    @pytest.fixture
    async def shutdown_environment(self):
        """
        Set up a complete shutdown environment with all components.
        
        Returns:
            dict: Dictionary containing all mocked components and configuration.
        """
        # Reset all singleton instances
        ShutdownCoordinator._instance = None
        ResourceCleaner._instance = None
        
        # Create coordinator
        coordinator = get_shutdown_coordinator()
        
        # Create mocks
        mock_risk_manager = MagicMock()
        mock_orchestrator = MagicMock()
        
        # Configure mock agents
        agent1 = MagicMock()
        agent1.agent_id = "agent1"
        agent1.agent_type = "trader"
        agent1.prepare_shutdown = AsyncMock()
        agent1.stop = AsyncMock(return_value=True)
        agent1.cleanup = AsyncMock()
        
        agent2 = MagicMock()
        agent2.agent_id = "agent2"
        agent2.agent_type = "analyzer"
        agent2.prepare_shutdown = AsyncMock()
        agent2.stop = AsyncMock(return_value=True)
        agent2.cleanup = AsyncMock()
        
        agents = {"agent1": agent1, "agent2": agent2}
        mock_orchestrator.get_all_agents.return_value = agents
        
        # Configure mock positions
        mock_positions = [
            {
                'symbol': 'BTCUSDT',
                'positionAmt': '1.5',
                'entryPrice': '50000',
                'markPrice': '50500'
            },
            {
                'symbol': 'ETHUSDT',
                'positionAmt': '-5.0',
                'entryPrice': '3000',
                'markPrice': '3100'
            }
        ]
        
        mock_risk_manager.fetch_binance_position_risk = AsyncMock(
            side_effect=[mock_positions, []]  # First call returns positions, second call empty
        )
        
        mock_risk_manager.emergency_shutdown = MagicMock(
            return_value={
                'success': True,
                'closed_positions': [
                    {'symbol': 'BTCUSDT', 'positionAmt': '1.5', 'success': True},
                    {'symbol': 'ETHUSDT', 'positionAmt': '-5.0', 'success': True}
                ]
            }
        )
        
        # Create position closer
        position_closer = get_position_closer(mock_risk_manager)
        
        # Create agent terminator
        agent_terminator = get_agent_terminator(mock_orchestrator)
        
        # Create resource cleaner
        resource_cleaner = get_resource_cleaner()
        
        # Register mock resource cleanup callbacks
        db_cleanup = AsyncMock()
        file_cleanup = AsyncMock()
        network_cleanup = AsyncMock()
        
        register_cleanup_callback("db", "connection", db_cleanup)
        register_cleanup_callback("file", "handle", file_cleanup)
        register_cleanup_callback("network", "socket", network_cleanup)
        
        # Configure coordinator with components
        coordinator._position_closer = position_closer
        coordinator._agent_terminator = agent_terminator
        coordinator._resource_cleaner = resource_cleaner
        
        # Return the environment
        return {
            "coordinator": coordinator,
            "position_closer": position_closer,
            "agent_terminator": agent_terminator,
            "resource_cleaner": resource_cleaner,
            "mock_risk_manager": mock_risk_manager,
            "mock_orchestrator": mock_orchestrator,
            "agents": agents,
            "cleanup_callbacks": {
                "db": db_cleanup,
                "file": file_cleanup,
                "network": network_cleanup
            }
        }

    async def test_complete_shutdown_sequence(self, shutdown_environment):
        """Test a complete shutdown sequence with all phases executing successfully."""
        coordinator = shutdown_environment["coordinator"]
        agents = shutdown_environment["agents"]
        callbacks = shutdown_environment["cleanup_callbacks"]
        
        # Initiate shutdown
        await coordinator.initiate_shutdown(
            reason="test_shutdown",
            force=False,
            position_strategy=PositionCloseStrategy.IMMEDIATE
        )
        
        # Execute shutdown
        result = await coordinator.shutdown_all_agents()
        
        # Verify result is successful
        assert result is True
        
        # Verify all phases were executed
        status = coordinator.get_status()
        assert status["phase"] == ShutdownPhase.COMPLETE.value
        
        # Verify agents were prepared, stopped, and cleaned up
        for agent in agents.values():
            agent.prepare_shutdown.assert_called_once()
            agent.stop.assert_called_once()
            agent.cleanup.assert_called_once()
        
        # Verify resource cleanup callbacks were called
        for callback in callbacks.values():
            callback.assert_called_once()

    async def test_shutdown_with_failing_agent(self, shutdown_environment):
        """Test shutdown when an agent fails to stop."""
        coordinator = shutdown_environment["coordinator"]
        agents = shutdown_environment["agents"]
        callbacks = shutdown_environment["cleanup_callbacks"]
        
        # Configure agent1 to fail during stop
        agents["agent1"].stop = AsyncMock(return_value=False)
        
        # Initiate shutdown without force
        await coordinator.initiate_shutdown(
            reason="test_failing_agent",
            force=False,
            position_strategy=PositionCloseStrategy.IMMEDIATE
        )
        
        # Execute shutdown
        result = await coordinator.shutdown_all_agents()
        
        # Verify result is failure
        assert result is False
        
        # Verify phase is FAILED
        status = coordinator.get_status()
        assert status["phase"] == ShutdownPhase.FAILED.value
        
        # Verify agent1 was attempted to stop
        agents["agent1"].stop.assert_called_once()
        
        # Reset for next test
        agents["agent1"].stop.reset_mock()
        
        # Now try with force=True
        await coordinator.initiate_shutdown(
            reason="test_failing_agent_force",
            force=True,
            position_strategy=PositionCloseStrategy.IMMEDIATE
        )
        
        # Execute shutdown
        result = await coordinator.shutdown_all_agents()
        
        # Verify result is success despite agent failure
        assert result is True
        
        # Verify all phases were executed despite failures
        status = coordinator.get_status()
        assert status["phase"] == ShutdownPhase.COMPLETE.value
        
        # Verify agent1 was attempted to stop again
        agents["agent1"].stop.assert_called_once()
        
        # Verify resource cleanup callbacks were called
        for callback in callbacks.values():
            callback.assert_called_once()

    async def test_emergency_shutdown(self, shutdown_environment):
        """Test emergency shutdown with minimal timeouts."""
        coordinator = shutdown_environment["coordinator"]
        agents = shutdown_environment["agents"]
        callbacks = shutdown_environment["cleanup_callbacks"]
        
        # Track start time
        start_time = time.time()
        
        # Execute emergency shutdown
        await coordinator.emergency_shutdown(reason="emergency_test")
        
        # Track end time
        end_time = time.time()
        
        # Verify shutdown was quick
        assert end_time - start_time < 0.5  # Should be very fast in tests
        
        # Verify emergency settings were used
        assert coordinator._force is True
        assert coordinator._position_strategy == PositionCloseStrategy.IMMEDIATE
        
        # Verify all agents were shut down
        for agent in agents.values():
            agent.prepare_shutdown.assert_called_once()
            agent.stop.assert_called_once()
            agent.cleanup.assert_called_once()
        
        # Verify resource cleanup callbacks were called
        for callback in callbacks.values():
            callback.assert_called_once()

    async def test_shutdown_sequence_order(self, shutdown_environment):
        """Test that shutdown phases execute in the correct order."""
        coordinator = shutdown_environment["coordinator"]
        
        # Create a list to track phase execution order
        execution_order = []
        
        # Override execute_phase to track order
        original_execute_phase = coordinator._execute_phase
        
        async def track_execute_phase(phase):
            execution_order.append(phase)
            return await original_execute_phase(phase)
        
        coordinator._execute_phase = track_execute_phase
        
        # Initiate and execute shutdown
        await coordinator.initiate_shutdown(reason="test_order")
        await coordinator.shutdown_all_agents()
        
        # Verify phases were executed in the correct order
        expected_order = [
            ShutdownPhase.PREPARATION,
            ShutdownPhase.POSITIONS,
            ShutdownPhase.AGENTS,
            ShutdownPhase.RESOURCES
        ]
        
        assert execution_order == expected_order

    async def test_cancellation_handling(self, shutdown_environment):
        """Test handling of cancellation during shutdown."""
        coordinator = shutdown_environment["coordinator"]
        
        # Create a task to execute shutdown
        shutdown_task = asyncio.create_task(
            coordinator.initiate_shutdown(reason="test_cancellation")
        )
        
        # Allow the task to start
        await asyncio.sleep(0.1)
        
        # Cancel the task
        shutdown_task.cancel()
        
        # Wait for cancellation to take effect
        try:
            await shutdown_task
        except asyncio.CancelledError:
            pass
        
        # Verify the phase is INITIALIZING or FAILED (not left in an intermediate state)
        status = coordinator.get_status()
        assert status["phase"] in [
            ShutdownPhase.INITIALIZING.value,
            ShutdownPhase.FAILED.value
        ]

    async def test_progress_callbacks(self, shutdown_environment):
        """Test progress callbacks during shutdown."""
        coordinator = shutdown_environment["coordinator"]
        
        # Create a mock callback
        callback = MagicMock()
        phase_sequence = []
        
        def record_phase(status):
            phase_sequence.append(status["phase"])
            return None
        
        callback.side_effect = record_phase
        
        # Register the callback
        coordinator.register_progress_callback(callback)
        
        # Initiate and execute shutdown
        await coordinator.initiate_shutdown(reason="test_callbacks")
        await coordinator.shutdown_all_agents()
        
        # Verify the callback was called for each phase
        assert callback.call_count >= 5  # At least once per phase including INITIALIZING
        
        # Verify the phases were reported in the correct order
        # Phase sequence should contain each phase in order
        # (may include duplicate reports for the same phase)
        assert ShutdownPhase.INITIALIZING.value in phase_sequence
        assert ShutdownPhase.PREPARATION.value in phase_sequence
        assert ShutdownPhase.POSITIONS.value in phase_sequence
        assert ShutdownPhase.AGENTS.value in phase_sequence
        assert ShutdownPhase.RESOURCES.value in phase_sequence
        assert ShutdownPhase.COMPLETE.value in phase_sequence
        
        # Verify INITIALIZING comes before PREPARATION
        init_idx = phase_sequence.index(ShutdownPhase.INITIALIZING.value)
        prep_idx = phase_sequence.index(ShutdownPhase.PREPARATION.value)
        assert init_idx < prep_idx
        
        # Verify COMPLETE is the last reported phase
        assert phase_sequence[-1] == ShutdownPhase.COMPLETE.value

    async def test_shutdown_under_load(self, shutdown_environment):
        """Test shutdown while the system is under load."""
        coordinator = shutdown_environment["coordinator"]
        mock_orchestrator = shutdown_environment["mock_orchestrator"]
        agents = shutdown_environment["agents"]
        
        # Create "busy" background tasks for agents
        busy_tasks = []
        
        # Mock agents to be busy with background tasks
        for agent in agents.values():
            # Add an is_busy property that returns True
            agent.is_busy = True
            agent.get_active_tasks = MagicMock(return_value=2)  # 2 active tasks
            
            # Make stop take longer to simulate work
            original_stop = agent.stop
            
            async def busy_stop():
                # Simulate busy work
                await asyncio.sleep(0.1)
                return await original_stop()
            
            agent.stop = AsyncMock(side_effect=busy_stop)
        
        # Initiate shutdown
        await coordinator.initiate_shutdown(
            reason="test_under_load",
            force=False,
            position_strategy=PositionCloseStrategy.IMMEDIATE
        )
        
        # Execute shutdown
        result = await coordinator.shutdown_all_agents()
        
        # Verify result is successful
        assert result is True
        
        # Verify all phases were executed
        status = coordinator.get_status()
        assert status["phase"] == ShutdownPhase.COMPLETE.value
        
        # Verify agents were prepared, stopped, and cleaned up
        for agent in agents.values():
            agent.prepare_shutdown.assert_called_once()
            agent.stop.assert_called_once()
            agent.cleanup.assert_called_once()

    async def test_shutdown_with_resource_dependencies(self, shutdown_environment):
        """Test shutdown with resources that have dependencies on each other."""
        coordinator = shutdown_environment["coordinator"]
        resource_cleaner = shutdown_environment["resource_cleaner"]
        
        # Create a list to track cleanup order
        cleanup_order = []
        
        # Create callbacks that record their execution order
        async def db_callback():
            cleanup_order.append("db")
            await asyncio.sleep(0.01)  # Small delay to ensure deterministic behavior
        
        async def cache_callback():
            cleanup_order.append("cache")
            await asyncio.sleep(0.01)
        
        async def api_callback():
            cleanup_order.append("api")
            await asyncio.sleep(0.01)
        
        # Register callbacks with dependencies
        # db should be cleaned up after cache, which should be cleaned up after api
        resource_cleaner._resources = {}  # Clear existing callbacks
        register_cleanup_callback("db", "connection", AsyncMock(side_effect=db_callback), dependencies=[])
        register_cleanup_callback("cache", "redis", AsyncMock(side_effect=cache_callback), dependencies=["db.connection"])
        register_cleanup_callback("api", "server", AsyncMock(side_effect=api_callback), dependencies=["cache.redis"])
        
        # Initiate and execute shutdown
        await coordinator.initiate_shutdown(reason="test_resource_dependencies")
        await coordinator.shutdown_all_agents()
        
        # Verify resources were cleaned up in the correct order
        # dependencies determine reverse order: api -> cache -> db
        assert cleanup_order == ["api", "cache", "db"] 