"""
Unit tests for the agent terminator module.

This module tests the functionality of the agent terminator, which is responsible
for gracefully shutting down trading agents.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import time

from src.core.agent_terminator import (
    AgentTerminator,
    get_agent_terminator,
    ShutdownPhase
)

# Mark all tests as asyncio to support async tests
pytestmark = pytest.mark.asyncio


class TestAgentTerminator:
    """Test class for the AgentTerminator."""

    @pytest.fixture
    def orchestrator_mock(self):
        """Fixture to create a mock orchestrator for testing."""
        orchestrator = MagicMock()
        orchestrator.get_all_agents = MagicMock(return_value={})
        return orchestrator

    @pytest.fixture
    def terminator(self, orchestrator_mock):
        """Fixture to create an AgentTerminator instance for testing."""
        return AgentTerminator(orchestrator_mock)

    @pytest.fixture
    def agents_mock(self):
        """Fixture to create mock agents for testing."""
        agent1 = MagicMock()
        agent1.agent_id = "agent1"
        agent1.agent_type = "type1"
        agent1.get_state = MagicMock(return_value="running")
        agent1.prepare_shutdown = AsyncMock()
        agent1.stop = AsyncMock(return_value=True)
        agent1.cleanup = AsyncMock()
        
        agent2 = MagicMock()
        agent2.agent_id = "agent2"
        agent2.agent_type = "type2"
        agent2.get_state = MagicMock(return_value="running")
        agent2.prepare_shutdown = AsyncMock()
        agent2.stop = AsyncMock(return_value=True)
        agent2.cleanup = AsyncMock()
        
        return {"agent1": agent1, "agent2": agent2}

    async def test_factory_function(self, orchestrator_mock):
        """Test that the factory function returns an AgentTerminator instance."""
        terminator = get_agent_terminator(orchestrator_mock)
        assert isinstance(terminator, AgentTerminator)

    async def test_prepare_agents_for_shutdown(self, terminator, orchestrator_mock, agents_mock):
        """Test preparing agents for shutdown."""
        # Configure orchestrator to return mock agents
        orchestrator_mock.get_all_agents.return_value = agents_mock
        
        # Call prepare method
        success = await terminator.prepare_agents_for_shutdown()
        
        # Verify all agents were prepared
        assert success is True
        for agent in agents_mock.values():
            agent.prepare_shutdown.assert_called_once()

    async def test_stop_agents(self, terminator, orchestrator_mock, agents_mock):
        """Test stopping agents."""
        # Configure orchestrator to return mock agents
        orchestrator_mock.get_all_agents.return_value = agents_mock
        
        # Call stop method
        success = await terminator.stop_agents()
        
        # Verify all agents were stopped
        assert success is True
        for agent in agents_mock.values():
            agent.stop.assert_called_once()

    async def test_cleanup_agents(self, terminator, orchestrator_mock, agents_mock):
        """Test cleaning up agents."""
        # Configure orchestrator to return mock agents
        orchestrator_mock.get_all_agents.return_value = agents_mock
        
        # Call cleanup method
        success = await terminator.cleanup_agents()
        
        # Verify all agents were cleaned up
        assert success is True
        for agent in agents_mock.values():
            agent.cleanup.assert_called_once()

    async def test_handle_agent_failure(self, terminator, orchestrator_mock, agents_mock):
        """Test handling agent failure during shutdown."""
        # Configure agent1 to fail during stop
        agent1 = agents_mock["agent1"]
        agent1.stop = AsyncMock(return_value=False)
        
        # Configure orchestrator to return mock agents
        orchestrator_mock.get_all_agents.return_value = agents_mock
        
        # Call stop method without force
        success = await terminator.stop_agents(force=False)
        
        # Verify the operation failed due to agent1
        assert success is False
        agent1.stop.assert_called_once()
        
        # Now try with force=True
        agent1.stop.reset_mock()
        success = await terminator.stop_agents(force=True)
        
        # Verify operation succeeded despite agent1 failure
        assert success is True
        agent1.stop.assert_called_once()

    async def test_stop_with_timeout(self, terminator, orchestrator_mock, agents_mock):
        """Test stopping agents with a timeout."""
        # Configure agent1 to hang during stop
        agent1 = agents_mock["agent1"]
        
        async def hang_forever():
            await asyncio.sleep(10)  # Long delay
            return True
        
        agent1.stop = AsyncMock(side_effect=hang_forever)
        
        # Configure orchestrator to return mock agents
        orchestrator_mock.get_all_agents.return_value = agents_mock
        
        # Call stop method with a short timeout
        success = await terminator.stop_agents(timeout=0.1)
        
        # Verify operation completed despite the hanging agent
        agent1.stop.assert_called_once()
        
        # Agent2 should still be stopped
        agents_mock["agent2"].stop.assert_called_once()

    async def test_execute_phase(self, terminator, orchestrator_mock, agents_mock):
        """Test executing a specific shutdown phase."""
        # Configure orchestrator to return mock agents
        orchestrator_mock.get_all_agents.return_value = agents_mock
        
        # Test PREPARATION phase
        success = await terminator.execute_phase(ShutdownPhase.PREPARATION)
        assert success is True
        for agent in agents_mock.values():
            agent.prepare_shutdown.assert_called_once()
        
        # Reset mocks
        for agent in agents_mock.values():
            agent.prepare_shutdown.reset_mock()
            agent.stop.reset_mock()
            agent.cleanup.reset_mock()
        
        # Test AGENTS phase
        success = await terminator.execute_phase(ShutdownPhase.AGENTS)
        assert success is True
        for agent in agents_mock.values():
            agent.stop.assert_called_once()
        
        # Reset mocks
        for agent in agents_mock.values():
            agent.prepare_shutdown.reset_mock()
            agent.stop.reset_mock()
            agent.cleanup.reset_mock()
        
        # Test RESOURCES phase (cleanup)
        success = await terminator.execute_phase(ShutdownPhase.RESOURCES)
        assert success is True
        for agent in agents_mock.values():
            agent.cleanup.assert_called_once()

    async def test_no_agents(self, terminator, orchestrator_mock):
        """Test behavior when no agents are registered."""
        # Configure orchestrator to return empty agent dict
        orchestrator_mock.get_all_agents.return_value = {}
        
        # Call methods and verify they succeed
        assert await terminator.prepare_agents_for_shutdown() is True
        assert await terminator.stop_agents() is True
        assert await terminator.cleanup_agents() is True

    async def test_exception_handling(self, terminator, orchestrator_mock, agents_mock):
        """Test handling exceptions from agent methods."""
        # Configure agent1 to raise an exception during stop
        agent1 = agents_mock["agent1"]
        agent1.stop = AsyncMock(side_effect=Exception("Test error"))
        
        # Configure orchestrator to return mock agents
        orchestrator_mock.get_all_agents.return_value = agents_mock
        
        # Call stop method and verify it handles the exception
        success = await terminator.stop_agents()
        
        # Should return False due to the exception
        assert success is False
        
        # Agent2 should still be stopped
        agents_mock["agent2"].stop.assert_called_once()

    async def test_shutdown_in_priority_order(self, terminator, orchestrator_mock):
        """Test that agents are shut down in priority order."""
        # Create agents with priorities
        agent1 = MagicMock()
        agent1.agent_id = "agent1"
        agent1.agent_type = "type1"
        agent1.get_state = MagicMock(return_value="running")
        agent1.get_shutdown_priority = MagicMock(return_value=10)  # Higher priority
        agent1.prepare_shutdown = AsyncMock()
        agent1.stop = AsyncMock(return_value=True)
        agent1.cleanup = AsyncMock()
        
        agent2 = MagicMock()
        agent2.agent_id = "agent2"
        agent2.agent_type = "type2"
        agent2.get_state = MagicMock(return_value="running")
        agent2.get_shutdown_priority = MagicMock(return_value=5)  # Lower priority
        agent2.prepare_shutdown = AsyncMock()
        agent2.stop = AsyncMock(return_value=True)
        agent2.cleanup = AsyncMock()
        
        agents = {"agent1": agent1, "agent2": agent2}
        
        # Track order of calls
        stop_order = []
        
        async def agent1_stop():
            stop_order.append("agent1")
            return True
        
        async def agent2_stop():
            stop_order.append("agent2")
            return True
        
        agent1.stop = AsyncMock(side_effect=agent1_stop)
        agent2.stop = AsyncMock(side_effect=agent2_stop)
        
        # Configure orchestrator to return agents
        orchestrator_mock.get_all_agents.return_value = agents
        
        # Call stop method
        success = await terminator.stop_agents()
        
        # Verify success
        assert success is True
        
        # Verify higher priority agent (agent1) was stopped first
        assert stop_order == ["agent1", "agent2"] 