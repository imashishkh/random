"""
Tests for the ShutdownCoordinator class.
"""
import asyncio
import pytest
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from .shutdown.coordinator import (
    ShutdownCoordinator, 
    ShutdownPhase,
    get_shutdown_coordinator
)
from .shutdown.position_closer import PositionCloseStrategy

# Disable logging during tests
logging.disable(logging.CRITICAL)

@pytest.fixture
def coordinator():
    """Fixture to create a fresh ShutdownCoordinator with mocked components."""
    # Reset the singleton instance for each test
    ShutdownCoordinator._instance = None
    
    # Create mocks for components
    position_closer_mock = MagicMock()
    position_closer_mock.close_all_positions = AsyncMock(return_value=True)
    
    agent_terminator_mock = MagicMock()
    agent_terminator_mock.terminate_all_agents = AsyncMock(return_value=True)
    
    resource_cleaner_mock = MagicMock()
    resource_cleaner_mock.cleanup_all_resources = AsyncMock(return_value=True)
    
    # Create coordinator with mocked components
    coordinator = ShutdownCoordinator(
        position_closer=position_closer_mock,
        agent_terminator=agent_terminator_mock,
        resource_cleaner=resource_cleaner_mock
    )
    
    return coordinator


class TestShutdownCoordinator:
    """Tests for the ShutdownCoordinator class."""
    
    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """Test that the ShutdownCoordinator follows the singleton pattern."""
        # Get two instances
        coordinator1 = ShutdownCoordinator()
        coordinator2 = ShutdownCoordinator()
        
        # They should be the same object
        assert coordinator1 is coordinator2
        
        # The factory function should also return the same instance
        coordinator3 = get_shutdown_coordinator()
        assert coordinator1 is coordinator3
    
    @pytest.mark.asyncio
    async def test_successful_shutdown(self, coordinator):
        """Test a successful shutdown process with all phases completing."""
        # Initiate shutdown
        success = await coordinator.shutdown(reason="Test shutdown")
        
        # Check the result
        assert success is True
        assert coordinator._phase == ShutdownPhase.COMPLETE
        assert coordinator.is_shutdown_complete() is True
        
        # Check that each component's method was called
        coordinator._position_closer.close_all_positions.assert_called_once()
        coordinator._agent_terminator.terminate_all_agents.assert_called_once()
        coordinator._resource_cleaner.cleanup_all_resources.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_shutdown_with_position_failure(self, coordinator):
        """Test a shutdown process where position closing fails."""
        # Make position closing fail
        coordinator._position_closer.close_all_positions.return_value = False
        
        # Initiate shutdown with force_after_timeout=True (default)
        success = await coordinator.shutdown(reason="Test shutdown")
        
        # Check the result - should still complete since force_after_timeout=True
        assert success is True
        assert coordinator._phase == ShutdownPhase.COMPLETE
        
        # Check that each component's method was called
        coordinator._position_closer.close_all_positions.assert_called_once()
        coordinator._agent_terminator.terminate_all_agents.assert_called_once()
        coordinator._resource_cleaner.cleanup_all_resources.assert_called_once()
        
        # Try again with force_after_timeout=False
        ShutdownCoordinator._instance = None  # Reset for new test
        coordinator = get_shutdown_coordinator()
        coordinator._position_closer = MagicMock()
        coordinator._position_closer.close_all_positions = AsyncMock(return_value=False)
        coordinator._agent_terminator = MagicMock()
        coordinator._agent_terminator.terminate_all_agents = AsyncMock(return_value=True)
        coordinator._resource_cleaner = MagicMock()
        coordinator._resource_cleaner.cleanup_all_resources = AsyncMock(return_value=True)
        
        # Initiate shutdown with force_after_timeout=False
        success = await coordinator.shutdown(reason="Test shutdown", force_after_timeout=False)
        
        # Should still proceed to other phases even though positions failed to close
        assert success is True
        coordinator._agent_terminator.terminate_all_agents.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_emergency_shutdown(self, coordinator):
        """Test an emergency shutdown."""
        # Store original timeouts
        original_timeouts = (
            coordinator._position_close_timeout,
            coordinator._agent_termination_timeout,
            coordinator._resource_cleanup_timeout
        )
        
        # Perform an emergency shutdown
        max_wait_time = 1.0
        success = await coordinator.emergency_shutdown(
            reason="Test emergency",
            max_wait_time=max_wait_time
        )
        
        # Check the result
        assert success is True
        
        # Verify that the timeouts were restored after shutdown
        assert coordinator._position_close_timeout == original_timeouts[0]
        assert coordinator._agent_termination_timeout == original_timeouts[1]
        assert coordinator._resource_cleanup_timeout == original_timeouts[2]
        
        # Check that close_all_positions was called with IMMEDIATE strategy
        coordinator._position_closer.close_all_positions.assert_called_once()
        args, kwargs = coordinator._position_closer.close_all_positions.call_args
        assert kwargs["strategy"] == PositionCloseStrategy.IMMEDIATE.value
    
    @pytest.mark.asyncio
    async def test_concurrent_shutdown_attempts(self, coordinator):
        """Test attempting multiple concurrent shutdowns."""
        # Make position closing take some time
        async def slow_close(*args, **kwargs):
            await asyncio.sleep(0.1)
            return True
        coordinator._position_closer.close_all_positions.side_effect = slow_close
        
        # Start a shutdown
        task1 = asyncio.create_task(coordinator.shutdown(reason="First shutdown"))
        
        # Try to start another shutdown before the first one completes
        task2 = asyncio.create_task(coordinator.shutdown(reason="Second shutdown"))
        
        # Wait for both to complete
        result1 = await task1
        result2 = await task2
        
        # First one should succeed, second should be rejected
        assert result1 is True
        assert result2 is False
        
        # Position closing should only be called once
        coordinator._position_closer.close_all_positions.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_progress_callbacks(self, coordinator):
        """Test that progress callbacks are called."""
        # Create a mock callback
        callback_mock = MagicMock()
        
        # Register the callback
        coordinator.register_progress_callback(callback_mock)
        
        # Perform a shutdown
        await coordinator.shutdown(reason="Test shutdown")
        
        # Check that the callback was called for each phase transition
        assert callback_mock.call_count >= 6  # At least once for each phase
        
        # Unregister the callback
        result = coordinator.unregister_progress_callback(callback_mock)
        assert result is True
        
        # Reset the callback and do another shutdown
        callback_mock.reset_mock()
        
        # Reset coordinator for new test
        ShutdownCoordinator._instance = None
        coordinator = get_shutdown_coordinator()
        
        # Perform a shutdown without the callback
        await coordinator.shutdown(reason="Test shutdown")
        
        # Check that the callback was not called
        callback_mock.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_timeout_configuration(self, coordinator):
        """Test setting timeouts."""
        # Set timeouts
        coordinator.set_position_close_timeout(10.0)
        coordinator.set_agent_termination_timeout(20.0)
        coordinator.set_resource_cleanup_timeout(30.0)
        
        # Check that they were set correctly
        assert coordinator._position_close_timeout == 10.0
        assert coordinator._agent_termination_timeout == 20.0
        assert coordinator._resource_cleanup_timeout == 30.0
        
        # Get the status and check that it includes the timeouts
        status = coordinator.get_status()
        assert status["position_close_timeout"] == 10.0
        assert status["agent_termination_timeout"] == 20.0
        assert status["resource_cleanup_timeout"] == 30.0
    
    @pytest.mark.asyncio
    async def test_wait_for_shutdown_complete(self, coordinator):
        """Test waiting for shutdown to complete."""
        # Start a shutdown in the background
        async def delayed_shutdown():
            await asyncio.sleep(0.1)
            return await coordinator.shutdown(reason="Test shutdown")
            
        shutdown_task = asyncio.create_task(delayed_shutdown())
        
        # Initially shutdown is not complete
        assert coordinator.is_shutdown_complete() is False
        
        # Wait for shutdown to complete with a timeout
        result = await coordinator.wait_for_shutdown_complete(timeout=0.5)
        assert result is True
        assert coordinator.is_shutdown_complete() is True
        
        # Clean up
        await shutdown_task 