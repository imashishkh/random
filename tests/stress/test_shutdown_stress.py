"""
Stress tests for the graceful shutdown functionality.

This module contains stress tests for the shutdown functionality, simulating
high load and verifying system stability under stress.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import time
import logging
import random
import signal
import os

from src.core.shutdown import (
    ShutdownCoordinator,
    ShutdownPhase,
    PositionCloseStrategy,
    get_shutdown_coordinator,
    setup_signal_handlers
)
from src.core.position_closer import PositionCloser, get_position_closer
from src.core.agent_terminator import AgentTerminator, get_agent_terminator
from src.core.resource_cleaner import ResourceCleaner, get_resource_cleaner, register_cleanup_callback

# Mark all tests as asyncio to support async tests
pytestmark = pytest.mark.asyncio


class TestShutdownStress:
    """Stress tests for the shutdown functionality."""

    @pytest.fixture
    async def high_load_environment(self, num_agents=50, num_positions=20, num_resources=30):
        """
        Set up a high-load environment with many agents, positions, and resources.
        
        Args:
            num_agents: Number of agents to simulate
            num_positions: Number of trading positions to simulate
            num_resources: Number of resources to simulate
            
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
        
        # Configure many mock agents
        agents = {}
        for i in range(num_agents):
            agent = MagicMock()
            agent.agent_id = f"agent{i}"
            agent.agent_type = f"type{i % 5}"  # 5 different agent types
            agent.prepare_shutdown = AsyncMock()
            
            # Some agents take longer to stop
            if i % 5 == 0:
                async def slow_stop():
                    await asyncio.sleep(0.05)  # Slow but not too slow for tests
                    return True
                agent.stop = AsyncMock(side_effect=slow_stop)
            else:
                agent.stop = AsyncMock(return_value=True)
                
            agent.cleanup = AsyncMock()
            agents[f"agent{i}"] = agent
        
        mock_orchestrator.get_all_agents.return_value = agents
        
        # Configure many mock positions
        mock_positions = []
        for i in range(num_positions):
            position = {
                'symbol': f'PAIR{i}',
                'positionAmt': str(random.uniform(0.1, 10.0)),
                'entryPrice': str(random.uniform(100, 50000)),
                'markPrice': str(random.uniform(100, 50000))
            }
            mock_positions.append(position)
        
        # Make position fetching take time to simulate real API call
        async def slow_fetch_positions():
            await asyncio.sleep(0.02)  # Small delay
            return mock_positions
        
        mock_risk_manager.fetch_binance_position_risk = AsyncMock(
            side_effect=[slow_fetch_positions(), []]  # First call returns positions, second call empty
        )
        
        # Configure emergency shutdown to succeed
        mock_risk_manager.emergency_shutdown = MagicMock(
            return_value={
                'success': True,
                'closed_positions': [{'success': True} for _ in range(num_positions)]
            }
        )
        
        # Create position closer
        position_closer = get_position_closer(mock_risk_manager)
        
        # Create agent terminator
        agent_terminator = get_agent_terminator(mock_orchestrator)
        
        # Create resource cleaner
        resource_cleaner = get_resource_cleaner()
        
        # Register many resource cleanup callbacks
        resource_types = ["db", "file", "network", "cache", "socket"]
        cleanup_callbacks = {}
        
        for i in range(num_resources):
            resource_type = resource_types[i % len(resource_types)]
            resource_key = f"{resource_type}_resource_{i}"
            
            # Some resources take longer to clean up
            if i % 7 == 0:
                async def slow_cleanup():
                    await asyncio.sleep(0.05)  # Slow but not too slow for tests
                
                callback = AsyncMock(side_effect=slow_cleanup)
            else:
                callback = AsyncMock()
                
            register_cleanup_callback(resource_type, resource_key, callback)
            cleanup_callbacks[f"{resource_type}.{resource_key}"] = callback
        
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
            "cleanup_callbacks": cleanup_callbacks,
            "num_agents": num_agents,
            "num_positions": num_positions,
            "num_resources": num_resources
        }

    async def test_shutdown_many_agents(self):
        """Test shutting down a large number of agents."""
        # Set up environment with many agents
        env = await self.high_load_environment(num_agents=100, num_positions=5, num_resources=5)
        coordinator = env["coordinator"]
        
        # Track performance
        start_time = time.time()
        
        # Initiate and execute shutdown
        await coordinator.initiate_shutdown(reason="test_many_agents")
        result = await coordinator.shutdown_all_agents()
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Verify shutdown was successful
        assert result is True
        
        # Verify shutdown completed in a reasonable time
        # This would depend on the actual implementation, but let's set a generous upper bound
        assert duration < 2.0  # Should complete in under 2 seconds
        
        # Log performance metrics
        print(f"\nShutdown of {env['num_agents']} agents completed in {duration:.2f} seconds")
        
        # Verify all agents were shut down
        for agent in env["agents"].values():
            agent.prepare_shutdown.assert_called_once()
            agent.stop.assert_called_once()
            agent.cleanup.assert_called_once()

    async def test_shutdown_many_positions(self):
        """Test shutting down with a large number of positions to close."""
        # Set up environment with many positions
        env = await self.high_load_environment(num_agents=5, num_positions=100, num_resources=5)
        coordinator = env["coordinator"]
        
        # Track performance
        start_time = time.time()
        
        # Initiate and execute shutdown
        await coordinator.initiate_shutdown(
            reason="test_many_positions",
            position_strategy=PositionCloseStrategy.IMMEDIATE
        )
        result = await coordinator.shutdown_all_agents()
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Verify shutdown was successful
        assert result is True
        
        # Verify shutdown completed in a reasonable time
        assert duration < 2.0  # Should complete in under 2 seconds
        
        # Log performance metrics
        print(f"\nShutdown with {env['num_positions']} positions completed in {duration:.2f} seconds")
        
        # Verify emergency shutdown was called
        env["mock_risk_manager"].emergency_shutdown.assert_called()

    async def test_shutdown_many_resources(self):
        """Test shutting down with a large number of resources to clean up."""
        # Set up environment with many resources
        env = await self.high_load_environment(num_agents=5, num_positions=5, num_resources=100)
        coordinator = env["coordinator"]
        
        # Track performance
        start_time = time.time()
        
        # Initiate and execute shutdown
        await coordinator.initiate_shutdown(reason="test_many_resources")
        result = await coordinator.shutdown_all_agents()
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Verify shutdown was successful
        assert result is True
        
        # Verify shutdown completed in a reasonable time
        assert duration < 2.0  # Should complete in under 2 seconds
        
        # Log performance metrics
        print(f"\nShutdown with {env['num_resources']} resources completed in {duration:.2f} seconds")
        
        # Verify all resources were cleaned up
        for callback in env["cleanup_callbacks"].values():
            callback.assert_called_once()

    async def test_shutdown_full_system_load(self):
        """Test shutting down a full system under load with many agents, positions, and resources."""
        # Set up environment with many of everything
        env = await self.high_load_environment(num_agents=50, num_positions=50, num_resources=50)
        coordinator = env["coordinator"]
        
        # Track performance
        start_time = time.time()
        
        # Initiate and execute shutdown
        await coordinator.initiate_shutdown(
            reason="test_full_system",
            position_strategy=PositionCloseStrategy.IMMEDIATE
        )
        result = await coordinator.shutdown_all_agents()
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Verify shutdown was successful
        assert result is True
        
        # Verify shutdown completed in a reasonable time
        assert duration < 3.0  # Should complete in under 3 seconds
        
        # Log performance metrics
        print(f"\nFull system shutdown completed in {duration:.2f} seconds")
        print(f"  Agents: {env['num_agents']}")
        print(f"  Positions: {env['num_positions']}")
        print(f"  Resources: {env['num_resources']}")
        
        # Verify all components were properly shut down
        for agent in env["agents"].values():
            agent.prepare_shutdown.assert_called_once()
            agent.stop.assert_called_once()
            agent.cleanup.assert_called_once()
        
        env["mock_risk_manager"].emergency_shutdown.assert_called()
        
        for callback in env["cleanup_callbacks"].values():
            callback.assert_called_once()

    async def test_concurrent_shutdowns(self):
        """Test multiple concurrent shutdown attempts."""
        # Set up environment
        env = await self.high_load_environment()
        coordinator = env["coordinator"]
        
        # Start multiple shutdown tasks concurrently
        shutdown_task1 = asyncio.create_task(
            coordinator.initiate_shutdown(reason="concurrent_test_1")
        )
        
        # Small delay to ensure the first one starts
        await asyncio.sleep(0.01)
        
        # Start a second shutdown
        shutdown_task2 = asyncio.create_task(
            coordinator.initiate_shutdown(reason="concurrent_test_2")
        )
        
        # Wait for both to complete
        await asyncio.gather(shutdown_task1, shutdown_task2, return_exceptions=True)
        
        # Only one shutdown should succeed (the first one)
        # The second one should be ignored or return immediately
        
        # Execute the shutdown
        result = await coordinator.shutdown_all_agents()
        
        # Verify shutdown was successful
        assert result is True
        
        # Verify reason is from the first shutdown
        status = coordinator.get_status()
        assert status["reason"] == "concurrent_test_1"

    async def test_signal_handler(self):
        """Test signal handler triggers shutdown."""
        # Set up environment
        env = await self.high_load_environment()
        coordinator = env["coordinator"]
        
        # Set up signal handler
        setup_signal_handlers(coordinator)
        
        # Create a task to monitor shutdown status
        shutdown_detected = asyncio.Event()
        
        async def monitor_shutdown():
            while True:
                await asyncio.sleep(0.05)
                status = coordinator.get_status()
                if status["phase"] != ShutdownPhase.INITIALIZING.value:
                    shutdown_detected.set()
                    break
        
        monitor_task = asyncio.create_task(monitor_shutdown())
        
        # Allow time for monitor to start
        await asyncio.sleep(0.1)
        
        # Override initiate_shutdown to not actually execute but record call
        original_initiate_shutdown = coordinator.initiate_shutdown
        coordinator.initiate_shutdown = AsyncMock()
        
        # Send SIGTERM signal (this requires care in tests)
        # Note: This part is tricky in tests and may need to be mocked
        # depending on the test environment
        
        # Mock approach - directly call the handler that would be registered
        # Find the signal handler for SIGTERM
        # This simulates what would happen when SIGTERM is received
        for signum, handler in signal.Signals:
            if signum == signal.SIGTERM:
                handler(signal.SIGTERM, None)
                break
        
        # Wait for shutdown to be detected or timeout
        try:
            await asyncio.wait_for(shutdown_detected.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            # If we get here, the signal handler didn't trigger shutdown
            # This is a legitimate test failure
            assert False, "Signal handler did not trigger shutdown"
        
        # Verify initiate_shutdown was called
        coordinator.initiate_shutdown.assert_called()
        
        # Restore original method
        coordinator.initiate_shutdown = original_initiate_shutdown
        
        # Cancel monitor task
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

    async def test_memory_usage(self):
        """Test memory usage during shutdown of a large system."""
        try:
            import psutil
            process = psutil.Process(os.getpid())
        except ImportError:
            pytest.skip("psutil not available, skipping memory usage test")
            return
        
        # Record starting memory
        start_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Set up a large environment
        env = await self.high_load_environment(num_agents=100, num_positions=100, num_resources=100)
        coordinator = env["coordinator"]
        
        # Initiate and execute shutdown
        await coordinator.initiate_shutdown(reason="test_memory")
        result = await coordinator.shutdown_all_agents()
        
        # Record ending memory
        end_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Calculate memory increase
        memory_increase = end_memory - start_memory
        
        # Log memory usage
        print(f"\nMemory usage:")
        print(f"  Start: {start_memory:.2f} MB")
        print(f"  End: {end_memory:.2f} MB")
        print(f"  Increase: {memory_increase:.2f} MB")
        
        # Verify memory usage is reasonable
        # The actual threshold would depend on the implementation
        # but let's set a generous limit for the test
        assert memory_increase < 100.0  # MB 