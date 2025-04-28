"""
Concurrency utilities for managing async operations.

This module provides utilities for managing concurrent operations, especially for 
coordinating multiple async tasks during operations like graceful shutdown.
"""

import asyncio
import logging
from typing import Set, Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class WaitGroup:
    """
    Implementation of the Wait Group pattern for tracking concurrent task completion.
    
    This class provides a way to track multiple concurrent tasks and wait for all of them
    to complete before proceeding, similar to Go's sync.WaitGroup.
    """
    
    def __init__(self, name: str = "default"):
        """
        Initialize a new wait group.
        
        Args:
            name: A name for the wait group for logging purposes
        """
        self._name = name
        self._count = 0
        self._tasks: Set[asyncio.Task] = set()
        self._completed_tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._complete_event = asyncio.Event()
        self._complete_event.set()  # Initially set as there are no tasks
        
        logger.debug(f"WaitGroup '{name}' initialized")
    
    @property
    def count(self) -> int:
        """Get the current number of active tasks."""
        return self._count
    
    @property
    def complete(self) -> bool:
        """Check if all tasks are complete."""
        return self._complete_event.is_set()
    
    @property
    def completed_tasks(self) -> List[asyncio.Task]:
        """Get a list of completed tasks."""
        return self._completed_tasks.copy()
    
    async def add(self, task: asyncio.Task) -> None:
        """
        Add a task to the wait group.
        
        Args:
            task: The asyncio Task to track
        """
        async with self._lock:
            self._count += 1
            self._tasks.add(task)
            self._complete_event.clear()
            
            # Add a done callback to the task to automatically mark it done
            task.add_done_callback(self._task_done_callback)
            
            logger.debug(f"Task added to WaitGroup '{self._name}', count: {self._count}")
    
    def _task_done_callback(self, task: asyncio.Task) -> None:
        """
        Callback for when a task completes.
        
        Args:
            task: The completed task
        """
        asyncio.create_task(self._mark_done(task))
    
    async def _mark_done(self, task: asyncio.Task) -> None:
        """
        Mark a task as done and update the wait group.
        
        Args:
            task: The task that has completed
        """
        async with self._lock:
            # Only process if task is still in our set
            if task in self._tasks:
                self._tasks.remove(task)
                self._completed_tasks.append(task)
                self._count -= 1
                
                # Check if all tasks are now complete
                if self._count == 0:
                    self._complete_event.set()
                    logger.debug(f"All tasks in WaitGroup '{self._name}' are complete")
                else:
                    logger.debug(f"Task completed in WaitGroup '{self._name}', {self._count} remaining")
    
    async def wait(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for all tasks in the wait group to complete.
        
        Args:
            timeout: Maximum time to wait in seconds, or None to wait indefinitely
            
        Returns:
            True if all tasks completed, False if timeout occurred
        """
        try:
            await asyncio.wait_for(self._complete_event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            remaining = self._count
            logger.warning(f"Timeout waiting for WaitGroup '{self._name}', {remaining} tasks still pending")
            return False
    
    def get_results(self) -> Dict[str, Any]:
        """
        Get a summary of results from completed tasks.
        
        Returns:
            Dictionary with summary statistics
        """
        succeeded = 0
        failed = 0
        exceptions = []
        
        for task in self._completed_tasks:
            if task.done():
                if task.exception() is None:
                    succeeded += 1
                else:
                    failed += 1
                    exceptions.append(str(task.exception()))
        
        return {
            "name": self._name,
            "total": len(self._completed_tasks),
            "succeeded": succeeded,
            "failed": failed,
            "pending": self._count,
            "exceptions": exceptions
        } 