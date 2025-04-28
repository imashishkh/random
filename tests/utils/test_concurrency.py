"""
Tests for concurrency utilities.
"""

import asyncio
import unittest
from unittest.mock import patch
import logging

from src.utils.concurrency import WaitGroup


class TestWaitGroup(unittest.TestCase):
    """Test cases for the WaitGroup class."""
    
    def setUp(self):
        """Set up test cases."""
        # Configure logging for tests
        logging.basicConfig(level=logging.DEBUG)
    
    def test_init(self):
        """Test initialization of WaitGroup."""
        wg = WaitGroup("test")
        self.assertEqual(wg.count, 0)
        self.assertTrue(wg.complete)
        self.assertEqual(len(wg.completed_tasks), 0)
    
    async def _example_task(self, delay: float, fail: bool = False):
        """Example task that sleeps then optionally fails."""
        await asyncio.sleep(delay)
        if fail:
            raise ValueError("Task failed")
        return delay
    
    async def async_test_add_and_wait(self):
        """Test adding tasks and waiting for completion."""
        wg = WaitGroup("test_add_wait")
        
        # Create tasks
        task1 = asyncio.create_task(self._example_task(0.1))
        task2 = asyncio.create_task(self._example_task(0.2))
        
        # Add tasks to wait group
        await wg.add(task1)
        await wg.add(task2)
        
        self.assertEqual(wg.count, 2)
        self.assertFalse(wg.complete)
        
        # Wait for completion
        result = await wg.wait()
        
        self.assertTrue(result)
        self.assertEqual(wg.count, 0)
        self.assertTrue(wg.complete)
        self.assertEqual(len(wg.completed_tasks), 2)
        
        # Check task results
        self.assertEqual(task1.result(), 0.1)
        self.assertEqual(task2.result(), 0.2)
    
    async def async_test_timeout(self):
        """Test timeout functionality."""
        wg = WaitGroup("test_timeout")
        
        # Create a long-running task
        task = asyncio.create_task(self._example_task(1.0))
        await wg.add(task)
        
        # Wait with a short timeout
        result = await wg.wait(0.1)
        
        self.assertFalse(result)
        self.assertEqual(wg.count, 1)
        self.assertFalse(wg.complete)
        
        # Wait for the task to actually complete (for cleanup)
        await task
    
    async def async_test_with_failures(self):
        """Test handling of failed tasks."""
        wg = WaitGroup("test_failures")
        
        # Create tasks, one that fails
        task1 = asyncio.create_task(self._example_task(0.1))
        task2 = asyncio.create_task(self._example_task(0.2, fail=True))
        
        await wg.add(task1)
        await wg.add(task2)
        
        # Wait for completion (should still complete despite the failure)
        result = await wg.wait()
        
        self.assertTrue(result)
        self.assertEqual(wg.count, 0)
        self.assertTrue(wg.complete)
        
        # Check results
        results = wg.get_results()
        self.assertEqual(results["total"], 2)
        self.assertEqual(results["succeeded"], 1)
        self.assertEqual(results["failed"], 1)
        self.assertEqual(results["pending"], 0)
        self.assertEqual(len(results["exceptions"]), 1)
        self.assertTrue("Task failed" in results["exceptions"][0])
    
    def test_add_and_wait(self):
        """Run the async test for adding and waiting."""
        asyncio.run(self.async_test_add_and_wait())
    
    def test_timeout(self):
        """Run the async test for timeout."""
        asyncio.run(self.async_test_timeout())
    
    def test_with_failures(self):
        """Run the async test for handling failures."""
        asyncio.run(self.async_test_with_failures())


if __name__ == "__main__":
    unittest.main() 