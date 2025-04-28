"""
Unit tests for the resource cleaner module.

This module tests the functionality of the resource cleaner, which is responsible
for cleaning up resources during the shutdown process.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
import time

from src.core.resource_cleaner import (
    ResourceCleaner,
    get_resource_cleaner,
    register_cleanup_callback
)

# Mark all tests as asyncio to support async tests
pytestmark = pytest.mark.asyncio


class TestResourceCleaner:
    """Test class for the ResourceCleaner."""

    @pytest.fixture
    def cleaner(self):
        """Fixture to create a fresh ResourceCleaner for each test."""
        # Reset the singleton instance for each test
        ResourceCleaner._instance = None
        cleaner = ResourceCleaner()
        return cleaner

    async def test_singleton_pattern(self):
        """Test that ResourceCleaner follows the singleton pattern."""
        cleaner1 = get_resource_cleaner()
        cleaner2 = get_resource_cleaner()
        
        # Both instances should be the same object
        assert cleaner1 is cleaner2
        
        # The singleton instance should be of type ResourceCleaner
        assert isinstance(cleaner1, ResourceCleaner)

    async def test_register_cleanup_callback(self, cleaner):
        """Test registering a cleanup callback."""
        # Create a mock callback
        callback = AsyncMock()
        
        # Register the callback
        resource_type = "test_resource"
        resource_key = "test_key"
        register_cleanup_callback(resource_type, resource_key, callback)
        
        # Verify callback was registered
        assert resource_type in cleaner._resources
        assert resource_key in cleaner._resources[resource_type]
        assert cleaner._resources[resource_type][resource_key] == callback

    async def test_cleanup_resources(self, cleaner):
        """Test cleaning up resources."""
        # Create mock callbacks
        callback1 = AsyncMock()
        callback2 = AsyncMock()
        callback3 = AsyncMock()
        
        # Register callbacks
        register_cleanup_callback("db", "connection1", callback1)
        register_cleanup_callback("file", "handle1", callback2)
        register_cleanup_callback("network", "socket1", callback3)
        
        # Clean up resources
        success = await cleaner.cleanup_resources()
        
        # Verify all callbacks were called
        assert success is True
        callback1.assert_called_once()
        callback2.assert_called_once()
        callback3.assert_called_once()

    async def test_cleanup_specific_resource_type(self, cleaner):
        """Test cleaning up a specific resource type."""
        # Create mock callbacks
        callback1 = AsyncMock()
        callback2 = AsyncMock()
        callback3 = AsyncMock()
        
        # Register callbacks
        register_cleanup_callback("db", "connection1", callback1)
        register_cleanup_callback("file", "handle1", callback2)
        register_cleanup_callback("network", "socket1", callback3)
        
        # Clean up only db resources
        success = await cleaner.cleanup_resource_type("db")
        
        # Verify only db callback was called
        assert success is True
        callback1.assert_called_once()
        callback2.assert_not_called()
        callback3.assert_not_called()

    async def test_cleanup_priority(self, cleaner):
        """Test that resources are cleaned up in priority order."""
        # Create order tracking list
        cleanup_order = []
        
        # Create callbacks that record their order
        async def callback1():
            cleanup_order.append("db")
        
        async def callback2():
            cleanup_order.append("file")
        
        async def callback3():
            cleanup_order.append("network")
        
        # Register callbacks with priorities
        register_cleanup_callback("db", "connection1", AsyncMock(side_effect=callback1), priority=10)
        register_cleanup_callback("file", "handle1", AsyncMock(side_effect=callback2), priority=30)
        register_cleanup_callback("network", "socket1", AsyncMock(side_effect=callback3), priority=20)
        
        # Clean up resources
        await cleaner.cleanup_resources()
        
        # Verify cleanup order based on priority (higher first)
        assert cleanup_order == ["file", "network", "db"]

    async def test_handle_cleanup_failure(self, cleaner):
        """Test handling failures during cleanup."""
        # Create callbacks with one that fails
        callback1 = AsyncMock()
        callback2 = AsyncMock(side_effect=Exception("Test error"))
        callback3 = AsyncMock()
        
        # Register callbacks
        register_cleanup_callback("db", "connection1", callback1)
        register_cleanup_callback("file", "handle1", callback2)
        register_cleanup_callback("network", "socket1", callback3)
        
        # Clean up resources with force=False
        success = await cleaner.cleanup_resources(force=False)
        
        # Verify the operation failed due to callback2
        assert success is False
        callback1.assert_called_once()
        callback2.assert_called_once()
        
        # callback3 might or might not be called depending on execution order
        
        # Reset mocks
        callback1.reset_mock()
        callback2.reset_mock()
        callback3.reset_mock()
        
        # Clean up with force=True
        success = await cleaner.cleanup_resources(force=True)
        
        # Verify the operation succeeded despite the failure
        assert success is True
        
        # callback1 and callback3 should be called
        # callback2 will be called again but will fail again

    async def test_cleanup_with_timeout(self, cleaner):
        """Test cleanup with a timeout."""
        # Create a callback that hangs
        async def hang_forever():
            await asyncio.sleep(10)  # Long delay
        
        hanging_callback = AsyncMock(side_effect=hang_forever)
        normal_callback = AsyncMock()
        
        # Register callbacks
        register_cleanup_callback("db", "connection1", hanging_callback)
        register_cleanup_callback("network", "socket1", normal_callback)
        
        # Clean up with a short timeout
        success = await cleaner.cleanup_resources(timeout=0.1)
        
        # Verify operation completed despite the hanging callback
        hanging_callback.assert_called_once()
        normal_callback.assert_called_once()

    async def test_no_registered_resources(self, cleaner):
        """Test behavior when no resources are registered."""
        # Clean up with no resources registered
        success = await cleaner.cleanup_resources()
        
        # Verify the operation succeeds
        assert success is True

    async def test_unregister_callback(self, cleaner):
        """Test unregistering a cleanup callback."""
        # Create a mock callback
        callback = AsyncMock()
        
        # Register the callback
        resource_type = "test_resource"
        resource_key = "test_key"
        register_cleanup_callback(resource_type, resource_key, callback)
        
        # Verify callback was registered
        assert resource_type in cleaner._resources
        assert resource_key in cleaner._resources[resource_type]
        
        # Unregister the callback
        cleaner.unregister_cleanup_callback(resource_type, resource_key)
        
        # Verify callback was unregistered
        assert resource_key not in cleaner._resources[resource_type]

    async def test_cleanup_dependencies(self, cleaner):
        """Test cleaning up resources with dependencies."""
        # Create order tracking list
        cleanup_order = []
        
        # Create callbacks
        async def callback1():
            cleanup_order.append("db")
        
        async def callback2():
            cleanup_order.append("cache")
        
        async def callback3():
            cleanup_order.append("api")
        
        # Register callbacks with dependencies
        # api depends on cache, cache depends on db
        register_cleanup_callback("db", "connection", AsyncMock(side_effect=callback1), dependencies=[])
        register_cleanup_callback("cache", "redis", AsyncMock(side_effect=callback2), dependencies=["db.connection"])
        register_cleanup_callback("api", "server", AsyncMock(side_effect=callback3), dependencies=["cache.redis"])
        
        # Clean up resources
        await cleaner.cleanup_resources()
        
        # Verify correct cleanup order based on dependencies
        assert cleanup_order == ["api", "cache", "db"]

    async def test_concurrent_cleanup(self, cleaner):
        """Test concurrent cleanup of independent resources."""
        # Create callbacks with sleep to simulate work
        async def slow_callback1():
            await asyncio.sleep(0.1)
            return True
        
        async def slow_callback2():
            await asyncio.sleep(0.1)
            return True
        
        # Register independent callbacks
        register_cleanup_callback("db", "connection1", AsyncMock(side_effect=slow_callback1))
        register_cleanup_callback("db", "connection2", AsyncMock(side_effect=slow_callback2))
        
        # Time how long cleanup takes
        start_time = time.time()
        await cleaner.cleanup_resources(concurrent=True)
        end_time = time.time()
        
        # With concurrent=True, both should be cleaned up in parallel
        # so total time should be ~0.1s, not ~0.2s
        assert end_time - start_time < 0.15  # Allow some overhead

    async def test_sequential_cleanup(self, cleaner):
        """Test sequential cleanup of resources."""
        # Create callbacks with sleep to simulate work
        async def slow_callback1():
            await asyncio.sleep(0.1)
            return True
        
        async def slow_callback2():
            await asyncio.sleep(0.1)
            return True
        
        # Register independent callbacks
        register_cleanup_callback("db", "connection1", AsyncMock(side_effect=slow_callback1))
        register_cleanup_callback("db", "connection2", AsyncMock(side_effect=slow_callback2))
        
        # Time how long cleanup takes
        start_time = time.time()
        await cleaner.cleanup_resources(concurrent=False)
        end_time = time.time()
        
        # With concurrent=False, they should be cleaned up sequentially
        # so total time should be ~0.2s, not ~0.1s
        assert end_time - start_time >= 0.2  # Sequential execution 