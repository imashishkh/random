"""
Resource Cleanup Registry for Orchestrator Shutdown

This module provides a registry for tracking and cleaning up resources
during orchestrator shutdown in a controlled, orderly manner.
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from functools import partial
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

# Configure logger
logger = logging.getLogger(__name__)

class ResourceType(Enum):
    """Types of resources that can be registered for cleanup."""
    DATABASE_CONNECTION = "database_connection"
    FILE_HANDLE = "file_handle"
    NETWORK_CONNECTION = "network_connection"
    THREAD_POOL = "thread_pool"
    PROCESS = "process"
    MEMORY_CACHE = "memory_cache"
    TEMP_FILE = "temp_file"
    LOCK = "lock"
    EVENT_LISTENER = "event_listener"
    API_CLIENT = "api_client"
    CUSTOM = "custom"


class CleanupPriority(Enum):
    """Priority levels for cleanup operations."""
    CRITICAL = 0  # Must be cleaned up first (e.g., open transactions)
    HIGH = 1      # Should be cleaned up early (e.g., network connections)
    MEDIUM = 2    # Standard priority (e.g., file handles)
    LOW = 3       # Can be cleaned up later (e.g., caches)
    FINAL = 4     # Should be cleaned up last (e.g., logging)


@dataclass
class ResourceCleanupTask:
    """Data class for a resource cleanup task."""
    resource_id: str
    resource_type: ResourceType
    cleanup_func: Callable
    is_async: bool
    priority: CleanupPriority
    timeout: float
    description: Optional[str] = None
    dependencies: List[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        """Initialize default values for optional fields."""
        if self.dependencies is None:
            self.dependencies = []
        if self.metadata is None:
            self.metadata = {}
    
    @property
    def priority_value(self) -> int:
        """Get the numeric priority value for sorting."""
        return self.priority.value


class ResourceCleanupRegistry:
    """
    Registry for tracking and cleaning up resources during shutdown.
    
    This class provides a centralized way to register resources that need
    cleanup during orchestrator shutdown. It handles dependencies between
    resources, prioritization of cleanup tasks, and parallel execution
    where possible.
    """
    
    def __init__(self, max_workers: int = 5):
        """
        Initialize the resource cleanup registry.
        
        Args:
            max_workers: Maximum number of worker threads for parallel cleanup
        """
        self._resources: Dict[str, ResourceCleanupTask] = {}
        self._cleaned_resources: Set[str] = set()
        self._failed_resources: Set[str] = set()
        self._cleaning_resources: Set[str] = set()
        self._resource_errors: Dict[str, str] = {}
        self._max_workers = max_workers
        self._thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        self._cleanup_in_progress = False
        self._cleanup_complete = False
        self._lock = asyncio.Lock()
        
        # Statistics
        self._cleanup_start_time: Optional[float] = None
        self._cleanup_end_time: Optional[float] = None
        self._resource_cleanup_times: Dict[str, float] = {}
    
    def register_resource(self,
                         resource_id: str,
                         cleanup_func: Callable,
                         resource_type: Union[ResourceType, str],
                         is_async: bool = False,
                         priority: Union[CleanupPriority, str, int] = CleanupPriority.MEDIUM,
                         timeout: float = 30.0,
                         description: Optional[str] = None,
                         dependencies: Optional[List[str]] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Register a resource for cleanup during shutdown.
        
        Args:
            resource_id: Unique identifier for the resource
            cleanup_func: Function to call to clean up the resource
            resource_type: Type of resource (enum or string)
            is_async: Whether the cleanup function is asynchronous
            priority: Priority for cleanup (enum, string name, or int value)
            timeout: Maximum time in seconds to wait for cleanup
            description: Human-readable description of the resource
            dependencies: List of resource IDs that must be cleaned up before this one
            metadata: Additional information about the resource
            
        Raises:
            ValueError: If resource_id already exists
        """
        if resource_id in self._resources:
            raise ValueError(f"Resource {resource_id} is already registered")
        
        # Convert string resource type to enum
        if isinstance(resource_type, str):
            try:
                resource_type = ResourceType[resource_type.upper()]
            except KeyError:
                resource_type = ResourceType.CUSTOM
        
        # Convert priority to enum
        if isinstance(priority, str):
            try:
                priority = CleanupPriority[priority.upper()]
            except KeyError:
                priority = CleanupPriority.MEDIUM
        elif isinstance(priority, int):
            priority_values = {p.value: p for p in CleanupPriority}
            priority = priority_values.get(priority, CleanupPriority.MEDIUM)
        
        # Create the cleanup task
        task = ResourceCleanupTask(
            resource_id=resource_id,
            resource_type=resource_type,
            cleanup_func=cleanup_func,
            is_async=is_async,
            priority=priority,
            timeout=timeout,
            description=description,
            dependencies=dependencies or [],
            metadata=metadata or {}
        )
        
        # Store the task
        self._resources[resource_id] = task
        logger.debug(f"Registered resource for cleanup: {resource_id} ({resource_type.value})")
    
    def unregister_resource(self, resource_id: str) -> bool:
        """
        Remove a resource from the registry.
        
        Args:
            resource_id: ID of the resource to unregister
            
        Returns:
            True if the resource was unregistered, False if not found
        """
        if resource_id in self._resources:
            del self._resources[resource_id]
            logger.debug(f"Unregistered resource: {resource_id}")
            return True
        return False
    
    def is_resource_registered(self, resource_id: str) -> bool:
        """
        Check if a resource is registered.
        
        Args:
            resource_id: ID of the resource to check
            
        Returns:
            True if the resource is registered
        """
        return resource_id in self._resources
    
    def get_resource_info(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a registered resource.
        
        Args:
            resource_id: ID of the resource
            
        Returns:
            Dictionary with resource information, or None if not found
        """
        task = self._resources.get(resource_id)
        if not task:
            return None
        
        return {
            "id": task.resource_id,
            "type": task.resource_type.value,
            "priority": task.priority.name,
            "priority_value": task.priority_value,
            "is_async": task.is_async,
            "timeout": task.timeout,
            "description": task.description,
            "dependencies": task.dependencies,
            "metadata": task.metadata,
            "is_cleaned": resource_id in self._cleaned_resources,
            "is_failed": resource_id in self._failed_resources,
            "is_cleaning": resource_id in self._cleaning_resources,
            "error": self._resource_errors.get(resource_id)
        }
    
    def mark_resource_cleaned(self, resource_id: str) -> None:
        """
        Mark a resource as already cleaned up.
        
        Args:
            resource_id: ID of the resource to mark as cleaned
            
        Raises:
            ValueError: If the resource is not registered
        """
        if resource_id not in self._resources:
            raise ValueError(f"Resource {resource_id} is not registered")
        
        self._cleaned_resources.add(resource_id)
        logger.debug(f"Marked resource as cleaned: {resource_id}")
    
    async def cleanup_resource(self, resource_id: str) -> bool:
        """
        Clean up a specific resource.
        
        Args:
            resource_id: ID of the resource to clean up
            
        Returns:
            True if cleanup was successful
            
        Raises:
            ValueError: If the resource is not registered
        """
        task = self._resources.get(resource_id)
        if not task:
            raise ValueError(f"Resource {resource_id} is not registered")
        
        # Check if already cleaned
        if resource_id in self._cleaned_resources:
            logger.debug(f"Resource {resource_id} already cleaned up")
            return True
        
        # Check if already failed
        if resource_id in self._failed_resources:
            logger.debug(f"Resource {resource_id} previously failed cleanup")
            return False
        
        # Check dependencies
        for dep_id in task.dependencies:
            if dep_id not in self._cleaned_resources:
                logger.warning(f"Cannot clean up {resource_id}: dependency {dep_id} not cleaned")
                return False
        
        # Mark as being cleaned
        self._cleaning_resources.add(resource_id)
        
        # Record start time
        start_time = time.time()
        
        try:
            # Call the cleanup function
            if task.is_async:
                # Run async function
                await asyncio.wait_for(task.cleanup_func(), timeout=task.timeout)
            else:
                # Run synchronous function in thread pool
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    self._thread_pool, 
                    partial(asyncio.wait_for, asyncio.to_thread(task.cleanup_func), task.timeout)
                )
            
            # Mark as cleaned
            self._cleaned_resources.add(resource_id)
            
            # Record cleanup time
            end_time = time.time()
            self._resource_cleanup_times[resource_id] = end_time - start_time
            
            logger.info(f"Successfully cleaned up resource: {resource_id} ({task.resource_type.value}) in {end_time - start_time:.2f}s")
            return True
            
        except asyncio.TimeoutError:
            error_msg = f"Cleanup timed out after {task.timeout}s"
            self._resource_errors[resource_id] = error_msg
            self._failed_resources.add(resource_id)
            logger.error(f"Timeout cleaning up resource {resource_id}: {error_msg}")
            return False
            
        except Exception as e:
            error_msg = f"Cleanup failed: {str(e)}"
            self._resource_errors[resource_id] = error_msg
            self._failed_resources.add(resource_id)
            logger.error(f"Error cleaning up resource {resource_id}: {error_msg}")
            return False
            
        finally:
            # Remove from cleaning set
            self._cleaning_resources.discard(resource_id)
    
    def get_resource_cleanup_status(self) -> Dict[str, Any]:
        """
        Get the current status of resource cleanup.
        
        Returns:
            Dictionary with cleanup status information
        """
        resource_types = {}
        priority_levels = {}
        
        # Count resources by type and priority
        for resource_id, task in self._resources.items():
            # Count by type
            res_type = task.resource_type.value
            if res_type not in resource_types:
                resource_types[res_type] = {
                    "total": 0,
                    "cleaned": 0,
                    "failed": 0,
                    "pending": 0
                }
            
            resource_types[res_type]["total"] += 1
            
            if resource_id in self._cleaned_resources:
                resource_types[res_type]["cleaned"] += 1
            elif resource_id in self._failed_resources:
                resource_types[res_type]["failed"] += 1
            else:
                resource_types[res_type]["pending"] += 1
            
            # Count by priority
            priority_name = task.priority.name
            if priority_name not in priority_levels:
                priority_levels[priority_name] = {
                    "total": 0,
                    "cleaned": 0,
                    "failed": 0,
                    "pending": 0
                }
            
            priority_levels[priority_name]["total"] += 1
            
            if resource_id in self._cleaned_resources:
                priority_levels[priority_name]["cleaned"] += 1
            elif resource_id in self._failed_resources:
                priority_levels[priority_name]["failed"] += 1
            else:
                priority_levels[priority_name]["pending"] += 1
        
        # Calculate overall stats
        total_resources = len(self._resources)
        cleaned_resources = len(self._cleaned_resources)
        failed_resources = len(self._failed_resources)
        pending_resources = total_resources - cleaned_resources - failed_resources
        
        # Calculate cleanup duration
        cleanup_duration = None
        if self._cleanup_start_time is not None:
            if self._cleanup_end_time is not None:
                cleanup_duration = self._cleanup_end_time - self._cleanup_start_time
            else:
                cleanup_duration = time.time() - self._cleanup_start_time
        
        return {
            "total": total_resources,
            "cleaned": cleaned_resources,
            "failed": failed_resources,
            "pending": pending_resources,
            "in_progress": len(self._cleaning_resources),
            "by_type": resource_types,
            "by_priority": priority_levels,
            "cleanup_in_progress": self._cleanup_in_progress,
            "cleanup_complete": self._cleanup_complete,
            "cleanup_start_time": self._cleanup_start_time,
            "cleanup_end_time": self._cleanup_end_time,
            "cleanup_duration": cleanup_duration,
            "failed_resources": list(self._failed_resources),
            "errors": self._resource_errors
        }
    
    async def cleanup_all_resources(self, 
                                  force: bool = False, 
                                  parallel: bool = True) -> Dict[str, Any]:
        """
        Clean up all registered resources.
        
        Args:
            force: Whether to continue despite errors
            parallel: Whether to clean up resources in parallel where possible
            
        Returns:
            Dictionary with results of the cleanup operation
        """
        async with self._lock:
            if self._cleanup_complete:
                logger.warning("Cleanup already completed")
                return self.get_resource_cleanup_status()
            
            if self._cleanup_in_progress:
                logger.warning("Cleanup already in progress")
                return self.get_resource_cleanup_status()
            
            self._cleanup_in_progress = True
            self._cleanup_start_time = time.time()
        
        try:
            # Get all resources
            resources = list(self._resources.values())
            
            # Sort by priority (lower values first)
            resources.sort(key=lambda x: x.priority_value)
            
            # Group resources by priority level
            priority_groups: Dict[int, List[ResourceCleanupTask]] = {}
            for task in resources:
                if task.priority_value not in priority_groups:
                    priority_groups[task.priority_value] = []
                priority_groups[task.priority_value].append(task)
            
            # Process each priority group
            priority_levels = sorted(priority_groups.keys())
            
            for priority_level in priority_levels:
                group = priority_groups[priority_level]
                
                # Build dependency graph for this group
                dependency_graph: Dict[str, Set[str]] = {}
                for task in group:
                    # Only include dependencies within this group
                    group_deps = [
                        dep for dep in task.dependencies 
                        if dep in [t.resource_id for t in group]
                    ]
                    dependency_graph[task.resource_id] = set(group_deps)
                
                # Determine cleanup order for this group
                cleanup_order = self._topological_sort(dependency_graph)
                
                # Process resources in order
                if parallel:
                    # Group resources that can be processed in parallel
                    while cleanup_order:
                        # Find resources with no pending dependencies
                        parallel_batch = []
                        
                        for resource_id in list(cleanup_order):
                            # Skip if already cleaned or failed
                            if (resource_id in self._cleaned_resources or 
                                resource_id in self._failed_resources):
                                cleanup_order.remove(resource_id)
                                continue
                            
                            # Check if all dependencies are satisfied
                            deps = dependency_graph[resource_id]
                            if all(dep in self._cleaned_resources for dep in deps):
                                parallel_batch.append(resource_id)
                                cleanup_order.remove(resource_id)
                        
                        if not parallel_batch:
                            # Check for circular dependencies
                            if cleanup_order:
                                logger.error(f"Possible circular dependency detected in resources: {cleanup_order}")
                                if force:
                                    # Try to clean up remaining resources one by one
                                    for resource_id in cleanup_order:
                                        await self.cleanup_resource(resource_id)
                                    cleanup_order = []
                                else:
                                    break
                            break
                        
                        # Clean up resources in parallel
                        cleanup_tasks = [self.cleanup_resource(rid) for rid in parallel_batch]
                        await asyncio.gather(*cleanup_tasks)
                else:
                    # Process resources sequentially
                    for resource_id in cleanup_order:
                        # Skip if already cleaned or failed
                        if (resource_id in self._cleaned_resources or 
                            resource_id in self._failed_resources):
                            continue
                        
                        # Clean up the resource
                        success = await self.cleanup_resource(resource_id)
                        
                        # Stop on failure unless force is True
                        if not success and not force:
                            break
                
                # Check if cleanup should continue
                if (not force and self._failed_resources and 
                    self._cleanup_in_progress):
                    logger.warning("Aborting cleanup due to failures")
                    break
            
            return self.get_resource_cleanup_status()
            
        finally:
            self._cleanup_in_progress = False
            self._cleanup_complete = True
            self._cleanup_end_time = time.time()
            
            # Shut down thread pool
            self._thread_pool.shutdown(wait=True)
    
    async def cleanup_resources_by_type(self, 
                                     resource_type: Union[ResourceType, str],
                                     force: bool = False,
                                     parallel: bool = True) -> Dict[str, Any]:
        """
        Clean up all resources of a specific type.
        
        Args:
            resource_type: Type of resources to clean up
            force: Whether to continue despite errors
            parallel: Whether to clean up in parallel
            
        Returns:
            Dictionary with results of the cleanup operation
        """
        # Convert string to enum if needed
        if isinstance(resource_type, str):
            try:
                resource_type = ResourceType[resource_type.upper()]
            except KeyError:
                resource_type = ResourceType.CUSTOM
        
        # Find resources of the specified type
        resource_ids = [
            task.resource_id 
            for task in self._resources.values() 
            if task.resource_type == resource_type
        ]
        
        if not resource_ids:
            logger.info(f"No resources of type {resource_type.value} to clean up")
            return {"cleaned": 0, "failed": 0, "total": 0}
        
        # Clean up resources
        if parallel:
            tasks = [self.cleanup_resource(rid) for rid in resource_ids]
            results = await asyncio.gather(*tasks, return_exceptions=force)
            
            success_count = sum(1 for r in results if r is True)
            fail_count = sum(1 for r in results if r is False or isinstance(r, Exception))
            
            return {
                "cleaned": success_count,
                "failed": fail_count,
                "total": len(resource_ids)
            }
        else:
            success_count = 0
            fail_count = 0
            
            for rid in resource_ids:
                try:
                    if await self.cleanup_resource(rid):
                        success_count += 1
                    else:
                        fail_count += 1
                        if not force:
                            break
                except Exception:
                    fail_count += 1
                    if not force:
                        break
            
            return {
                "cleaned": success_count,
                "failed": fail_count,
                "total": len(resource_ids)
            }
    
    async def cleanup_resources_by_priority(self,
                                         priority: Union[CleanupPriority, str, int],
                                         force: bool = False,
                                         parallel: bool = True) -> Dict[str, Any]:
        """
        Clean up all resources at a specific priority level.
        
        Args:
            priority: Priority level of resources to clean up
            force: Whether to continue despite errors
            parallel: Whether to clean up in parallel
            
        Returns:
            Dictionary with results of the cleanup operation
        """
        # Convert to enum if needed
        if isinstance(priority, str):
            try:
                priority = CleanupPriority[priority.upper()]
            except KeyError:
                priority = CleanupPriority.MEDIUM
        elif isinstance(priority, int):
            priority_values = {p.value: p for p in CleanupPriority}
            priority = priority_values.get(priority, CleanupPriority.MEDIUM)
        
        # Find resources at the specified priority
        resource_ids = [
            task.resource_id 
            for task in self._resources.values() 
            if task.priority == priority
        ]
        
        if not resource_ids:
            logger.info(f"No resources with priority {priority.name} to clean up")
            return {"cleaned": 0, "failed": 0, "total": 0}
        
        # Clean up resources (implementation similar to cleanup_resources_by_type)
        if parallel:
            tasks = [self.cleanup_resource(rid) for rid in resource_ids]
            results = await asyncio.gather(*tasks, return_exceptions=force)
            
            success_count = sum(1 for r in results if r is True)
            fail_count = sum(1 for r in results if r is False or isinstance(r, Exception))
            
            return {
                "cleaned": success_count,
                "failed": fail_count,
                "total": len(resource_ids)
            }
        else:
            success_count = 0
            fail_count = 0
            
            for rid in resource_ids:
                try:
                    if await self.cleanup_resource(rid):
                        success_count += 1
                    else:
                        fail_count += 1
                        if not force:
                            break
                except Exception:
                    fail_count += 1
                    if not force:
                        break
            
            return {
                "cleaned": success_count,
                "failed": fail_count,
                "total": len(resource_ids)
            }
    
    def get_registered_resources(self) -> List[Dict[str, Any]]:
        """
        Get a list of all registered resources and their status.
        
        Returns:
            List of dictionaries with resource information
        """
        return [self.get_resource_info(rid) for rid in self._resources]
    
    def _topological_sort(self, graph: Dict[str, Set[str]]) -> List[str]:
        """
        Perform topological sort on a dependency graph.
        
        Args:
            graph: Dictionary mapping resource IDs to sets of dependency IDs
            
        Returns:
            List of resource IDs in dependency order (dependencies first)
        """
        # Track temporary and permanent marks for cycle detection
        temp_marks: Set[str] = set()
        perm_marks: Set[str] = set()
        result: List[str] = []
        
        def visit(node: str) -> None:
            """Visit a node in the graph."""
            # Check for cycles
            if node in temp_marks:
                logger.warning(f"Circular dependency detected involving {node}")
                return
            
            # Skip if already processed
            if node in perm_marks:
                return
            
            # Mark temporarily
            temp_marks.add(node)
            
            # Visit dependencies
            for dep in graph.get(node, set()):
                visit(dep)
            
            # Mark permanently and add to result
            perm_marks.add(node)
            temp_marks.remove(node)
            result.append(node)
        
        # Visit all nodes
        for node in graph:
            if node not in perm_marks:
                visit(node)
        
        # Return reversed result (dependencies first)
        return list(reversed(result)) 