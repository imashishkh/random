import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)


class ResourceCleanupPriority(Enum):
    """Priority levels for resource cleanup."""
    CRITICAL = 0  # Must be cleaned up first (e.g., locks, security-sensitive)
    HIGH = 1      # Important resources that should be cleaned up early
    MEDIUM = 2    # Standard priority for most resources
    LOW = 3       # Resources that can be cleaned up later
    FINAL = 4     # Last resources to be cleaned up (e.g., logging)


class ResourceCleanupStatus(Enum):
    """Status of a resource cleanup operation."""
    PENDING = "pending"           # Not yet started
    IN_PROGRESS = "in_progress"   # Currently being cleaned up
    SUCCEEDED = "succeeded"       # Successfully cleaned up
    FAILED = "failed"             # Failed to clean up
    PARTIAL = "partial"           # Partially cleaned up
    SKIPPED = "skipped"           # Cleanup was skipped
    TIMEOUT = "timeout"           # Cleanup timed out


@dataclass
class ResourceCleanupTask:
    """A task for cleaning up a resource."""
    resource_id: str
    resource_type: str
    cleanup_func: Union[Callable[[], Any], Callable[[], Awaitable[Any]]]
    is_async: bool
    description: str
    priority: ResourceCleanupPriority
    timeout: float = 30.0  # Default timeout in seconds
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: ResourceCleanupStatus = ResourceCleanupStatus.PENDING
    error_message: Optional[str] = None
    cleanup_time: Optional[float] = None
    result: Any = None


class CleanupStatus(Enum):
    """Status of a resource cleanup operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESSFUL = "successful"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


class CleanupResult:
    """Result of a resource cleanup operation."""
    
    def __init__(self, 
                 resource_id: str, 
                 resource_type: str,
                 status: CleanupStatus, 
                 details: Optional[str] = None, 
                 duration: Optional[float] = None):
        """
        Initialize a cleanup result.
        
        Args:
            resource_id: Identifier for the resource
            resource_type: Type of resource
            status: Status of the cleanup operation
            details: Additional details about the result
            duration: Duration of the cleanup operation in seconds
        """
        self.resource_id = resource_id
        self.resource_type = resource_type
        self.status = status
        self.details = details
        self.duration = duration
        self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the cleanup result to a dictionary.
        
        Returns:
            Dictionary representation of the cleanup result
        """
        return {
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "status": self.status.value,
            "details": self.details,
            "duration": self.duration,
            "timestamp": self.timestamp
        }


class ResourceCleanupRegistry:
    """
    Registry for managing resource cleanup during shutdown.
    
    This class allows registration of cleanup functions for various resources,
    and handles executing those functions in the appropriate order during
    shutdown. It manages dependencies between resources and prioritizes cleanup
    operations.
    """
    
    def __init__(self):
        """Initialize the resource cleanup registry."""
        self._lock = asyncio.Lock()
        self._resources: Dict[str, ResourceCleanupTask] = {}
        self._cleanup_order: List[str] = []
        self._cleanup_in_progress = False
        self._reporter = None  # Will be set later
        self._cleanup_handlers = {}
        self._cleanup_results = {}

    def set_reporter(self, reporter):
        """
        Set the shutdown reporter.
        
        Args:
            reporter: A reporter to use for reporting cleanup status
        """
        self._reporter = reporter
    
    async def register_resource(self,
                              resource_id: str,
                              resource_type: str,
                              cleanup_func: Union[Callable[[], Any], Callable[[], Awaitable[Any]]],
                              is_async: bool,
                              description: str,
                              priority: ResourceCleanupPriority = ResourceCleanupPriority.MEDIUM,
                              timeout: float = 30.0,
                              dependencies: Optional[List[str]] = None,
                              metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Register a resource for cleanup.
        
        Args:
            resource_id: Unique identifier for the resource
            resource_type: Type of resource (e.g., 'database', 'file', 'socket')
            cleanup_func: Function to call to clean up the resource
            is_async: Whether the cleanup function is async
            description: Human-readable description of the resource
            priority: Priority for cleanup (lower values are cleaned up first)
            timeout: Maximum time to wait for cleanup in seconds
            dependencies: IDs of resources that must be cleaned up before this one
            metadata: Additional information about the resource
        """
        async with self._lock:
            if resource_id in self._resources:
                logger.warning(f"Resource {resource_id} already registered for cleanup")
                return
            
            task = ResourceCleanupTask(
                resource_id=resource_id,
                resource_type=resource_type,
                cleanup_func=cleanup_func,
                is_async=is_async,
                description=description,
                priority=priority,
                timeout=timeout,
                dependencies=dependencies or [],
                metadata=metadata or {},
                status=ResourceCleanupStatus.PENDING
            )
            
            self._resources[resource_id] = task
            logger.debug(f"Registered resource for cleanup: {resource_id} ({resource_type})")
            
            # If we have a reporter, update it
            if self._reporter:
                await self._reporter.update_resource_status(
                    resource_id=resource_id,
                    status="registered",
                    resource_type=resource_type,
                    metadata={
                        "description": description,
                        "priority": priority.name,
                        "dependencies": dependencies or []
                    }
                )
    
    async def unregister_resource(self, resource_id: str) -> bool:
        """
        Unregister a resource from cleanup.
        
        Args:
            resource_id: ID of the resource to unregister
            
        Returns:
            True if the resource was unregistered, False if it wasn't registered
        """
        async with self._lock:
            if resource_id not in self._resources:
                logger.warning(f"Resource {resource_id} not registered for cleanup")
                return False
            
            # Check if cleanup is in progress
            if self._cleanup_in_progress:
                logger.warning(f"Cannot unregister resource {resource_id} during cleanup")
                return False
            
            # Check if any resources depend on this one
            dependent_resources = []
            for rid, task in self._resources.items():
                if resource_id in task.dependencies:
                    dependent_resources.append(rid)
            
            if dependent_resources:
                deps_str = ", ".join(dependent_resources)
                logger.warning(f"Cannot unregister resource {resource_id} as it is a dependency for: {deps_str}")
                return False
            
            # Remove the resource
            resource = self._resources.pop(resource_id)
            logger.debug(f"Unregistered resource from cleanup: {resource_id} ({resource.resource_type})")
            
            # If we have a reporter, update it
            if self._reporter:
                await self._reporter.update_resource_status(
                    resource_id=resource_id,
                    status="unregistered",
                    resource_type=resource.resource_type
                )
            
            return True
    
    async def get_resource_info(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a registered resource.
        
        Args:
            resource_id: ID of the resource
            
        Returns:
            Dictionary with resource information, or None if not found
        """
        async with self._lock:
            if resource_id not in self._resources:
                return None
            
            task = self._resources[resource_id]
            return {
                "resource_id": task.resource_id,
                "resource_type": task.resource_type,
                "description": task.description,
                "priority": task.priority.name,
                "timeout": task.timeout,
                "dependencies": task.dependencies.copy(),
                "status": task.status.value,
                "metadata": task.metadata.copy(),
                "error_message": task.error_message,
                "cleanup_time": task.cleanup_time
            }
    
    async def get_resources(self) -> List[Dict[str, Any]]:
        """
        Get information about all registered resources.
        
        Returns:
            List of dictionaries with resource information
        """
        async with self._lock:
            resources = []
            for resource_id in self._resources:
                info = await self.get_resource_info(resource_id)
                if info:
                    resources.append(info)
            return resources
    
    async def _compute_cleanup_order(self) -> List[str]:
        """
        Compute the order in which resources should be cleaned up.
        
        Returns:
            List of resource IDs in the order they should be cleaned up
        
        Raises:
            ValueError: If there is a circular dependency
        """
        # First, group resources by priority
        resources_by_priority: Dict[ResourceCleanupPriority, List[str]] = {
            priority: [] for priority in ResourceCleanupPriority
        }
        
        for resource_id, task in self._resources.items():
            if task.status == ResourceCleanupStatus.PENDING:
                resources_by_priority[task.priority].append(resource_id)
        
        # For each priority level, create a topological sort
        cleanup_order = []
        
        for priority in ResourceCleanupPriority:
            # Get resources at this priority level
            resources = resources_by_priority[priority]
            if not resources:
                continue
            
            # Create a graph of dependencies (only within this priority level)
            graph = {res: [] for res in resources}
            in_degree = {res: 0 for res in resources}
            
            for res in resources:
                task = self._resources[res]
                for dep in task.dependencies:
                    # Only consider dependencies within this priority level and that are still pending
                    if (dep in resources and 
                        dep in self._resources and 
                        self._resources[dep].status == ResourceCleanupStatus.PENDING):
                        graph[dep].append(res)
                        in_degree[res] += 1
            
            # Perform topological sort for this priority level
            queue = [res for res in resources if in_degree[res] == 0]
            level_order = []
            
            while queue:
                node = queue.pop(0)
                level_order.append(node)
                
                for neighbor in graph.get(node, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)
            
            # Check if we have a circular dependency
            if len(level_order) != len(resources):
                remaining = [res for res in resources if res not in level_order]
                raise ValueError(f"Circular dependency detected among resources: {', '.join(remaining)}")
            
            # Add this level's order to the overall order
            cleanup_order.extend(level_order)
        
        return cleanup_order
    
    async def _cleanup_resource(self, resource_id: str) -> Tuple[ResourceCleanupStatus, Optional[str], Any]:
        """
        Clean up a single resource.
        
        Args:
            resource_id: ID of the resource to clean up
            
        Returns:
            Tuple of (status, error_message, result)
        """
        if resource_id not in self._resources:
            return ResourceCleanupStatus.FAILED, f"Resource {resource_id} not found", None
        
        task = self._resources[resource_id]
        
        # Check if any dependencies haven't been cleaned up
        for dep_id in task.dependencies:
            if dep_id in self._resources:
                dep_task = self._resources[dep_id]
                if dep_task.status not in [ResourceCleanupStatus.SUCCEEDED, ResourceCleanupStatus.PARTIAL]:
                    return ResourceCleanupStatus.SKIPPED, f"Dependency {dep_id} not cleaned up", None
        
        # Mark as in progress
        task.status = ResourceCleanupStatus.IN_PROGRESS
        if self._reporter:
            await self._reporter.update_resource_status(
                resource_id=resource_id,
                status="cleaning",
                resource_type=task.resource_type
            )
        
        logger.debug(f"Cleaning up resource: {resource_id} ({task.resource_type})")
        
        # Create a task to run with timeout
        start_time = time.time()
        result = None
        error_message = None
        status = ResourceCleanupStatus.SUCCEEDED
        
        try:
            if task.is_async:
                # Run the async cleanup function with timeout
                coro = task.cleanup_func()
                try:
                    result = await asyncio.wait_for(coro, timeout=task.timeout)
                except asyncio.TimeoutError:
                    error_message = f"Cleanup timed out after {task.timeout} seconds"
                    status = ResourceCleanupStatus.TIMEOUT
            else:
                # Run the sync cleanup function in a thread with timeout
                loop = asyncio.get_running_loop()
                try:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, task.cleanup_func),
                        timeout=task.timeout
                    )
                except asyncio.TimeoutError:
                    error_message = f"Cleanup timed out after {task.timeout} seconds"
                    status = ResourceCleanupStatus.TIMEOUT
        except Exception as e:
            error_message = str(e)
            status = ResourceCleanupStatus.FAILED
            logger.exception(f"Error cleaning up resource {resource_id}: {str(e)}")
        
        cleanup_time = time.time() - start_time
        
        # Update task status
        task.status = status
        task.error_message = error_message
        task.cleanup_time = cleanup_time
        task.result = result
        
        # Update reporter
        if self._reporter:
            status_str = status.value
            metadata = {
                "cleanup_time": cleanup_time,
                "error_message": error_message
            }
            await self._reporter.update_resource_status(
                resource_id=resource_id,
                status=status_str,
                resource_type=task.resource_type,
                metadata=metadata
            )
        
        # Log result
        if status == ResourceCleanupStatus.SUCCEEDED:
            logger.info(f"Successfully cleaned up resource {resource_id} in {cleanup_time:.2f}s")
        elif status == ResourceCleanupStatus.TIMEOUT:
            logger.warning(f"Resource cleanup timed out for {resource_id} after {task.timeout}s")
        elif status == ResourceCleanupStatus.FAILED:
            logger.error(f"Failed to clean up resource {resource_id}: {error_message}")
        
        return status, error_message, result
    
    async def cleanup_resources(self, 
                              resource_ids: Optional[List[str]] = None,
                              ignore_dependencies: bool = False) -> Dict[str, ResourceCleanupStatus]:
        """
        Clean up specified resources or all resources.
        
        Args:
            resource_ids: List of resource IDs to clean up, or None for all
            ignore_dependencies: Whether to ignore dependencies and clean up resources directly
            
        Returns:
            Dictionary mapping resource IDs to their cleanup status
        """
        async with self._lock:
            self._cleanup_in_progress = True
            
            # Determine resources to clean up
            if resource_ids is None:
                # Clean up all resources
                to_cleanup = list(self._resources.keys())
            else:
                # Clean up specified resources
                to_cleanup = [rid for rid in resource_ids if rid in self._resources]
            
            results = {}
            
            if ignore_dependencies:
                # Clean up resources directly, ignoring dependencies
                for resource_id in to_cleanup:
                    status, _, _ = await self._cleanup_resource(resource_id)
                    results[resource_id] = status
            else:
                # Clean up resources in dependency order
                try:
                    # Compute cleanup order considering dependencies
                    self._cleanup_order = await self._compute_cleanup_order()
                    
                    # Filter to only the resources we want to clean up
                    cleanup_order = [rid for rid in self._cleanup_order if rid in to_cleanup]
                    
                    # Clean up resources in order
                    for resource_id in cleanup_order:
                        status, _, _ = await self._cleanup_resource(resource_id)
                        results[resource_id] = status
                except ValueError as e:
                    # Circular dependency detected
                    logger.error(f"Error computing cleanup order: {str(e)}")
                    for resource_id in to_cleanup:
                        if resource_id not in results:
                            self._resources[resource_id].status = ResourceCleanupStatus.FAILED
                            self._resources[resource_id].error_message = str(e)
                            results[resource_id] = ResourceCleanupStatus.FAILED
            
            self._cleanup_in_progress = False
            return results
    
    async def cleanup_all_resources(self) -> Dict[str, ResourceCleanupStatus]:
        """
        Clean up all registered resources.
        
        Returns:
            Dictionary mapping resource IDs to their cleanup status
        """
        return await self.cleanup_resources()
    
    async def cleanup_resources_by_type(self, resource_type: str) -> Dict[str, ResourceCleanupStatus]:
        """
        Clean up all resources of a specific type.
        
        Args:
            resource_type: Type of resources to clean up
            
        Returns:
            Dictionary mapping resource IDs to their cleanup status
        """
        async with self._lock:
            resource_ids = [
                rid for rid, task in self._resources.items()
                if task.resource_type == resource_type
            ]
            
            return await self.cleanup_resources(resource_ids=resource_ids)
    
    async def cleanup_resources_by_priority(self, priority: ResourceCleanupPriority) -> Dict[str, ResourceCleanupStatus]:
        """
        Clean up all resources with a specific priority.
        
        Args:
            priority: Priority level of resources to clean up
            
        Returns:
            Dictionary mapping resource IDs to their cleanup status
        """
        async with self._lock:
            resource_ids = [
                rid for rid, task in self._resources.items()
                if task.priority == priority
            ]
            
            return await self.cleanup_resources(resource_ids=resource_ids)
    
    async def get_cleanup_status(self) -> Dict[str, Any]:
        """
        Get the current status of resource cleanup.
        
        Returns:
            Dictionary with cleanup status information
        """
        async with self._lock:
            status_counts = {status.value: 0 for status in ResourceCleanupStatus}
            type_counts = {}
            priority_counts = {priority.name: 0 for priority in ResourceCleanupPriority}
            
            for task in self._resources.values():
                status_counts[task.status.value] += 1
                
                if task.resource_type not in type_counts:
                    type_counts[task.resource_type] = 0
                type_counts[task.resource_type] += 1
                
                priority_counts[task.priority.name] += 1
            
            return {
                "total_resources": len(self._resources),
                "cleanup_in_progress": self._cleanup_in_progress,
                "status_counts": status_counts,
                "type_counts": type_counts,
                "priority_counts": priority_counts
            }
    
    async def get_failed_resources(self) -> List[Dict[str, Any]]:
        """
        Get information about resources that failed to clean up.
        
        Returns:
            List of dictionaries with information about failed resources
        """
        async with self._lock:
            failed_resources = []
            for resource_id, task in self._resources.items():
                if task.status in [ResourceCleanupStatus.FAILED, ResourceCleanupStatus.TIMEOUT]:
                    info = await self.get_resource_info(resource_id)
                    if info:
                        failed_resources.append(info)
            return failed_resources

    async def cleanup_resource(self, resource_id: str) -> CleanupResult:
        """
        Clean up a specific resource.
        
        Args:
            resource_id: ID of the resource to clean up
            
        Returns:
            CleanupResult with the result of the operation
            
        Raises:
            ValueError: If the resource is not registered
        """
        # Get handler info
        handler_info = None
        async with self._lock:
            if resource_id not in self._cleanup_handlers:
                raise ValueError(f"Resource '{resource_id}' not registered for cleanup")
            
            handler_info = self._cleanup_handlers[resource_id]
            
            # Update status to in progress
            resource_type = handler_info["resource_type"]
            self._cleanup_results[resource_id] = CleanupResult(
                resource_id=resource_id,
                resource_type=resource_type,
                status=CleanupStatus.IN_PROGRESS
            )
            
            # Notify reporter if available
            if self._reporter:
                await self._reporter.update_resource_cleanup_status(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    status=CleanupStatus.IN_PROGRESS.value
                )
        
        # Run the cleanup
        cleanup_func = handler_info["func"]
        is_async = handler_info["is_async"]
        timeout = handler_info["timeout"]
        metadata = handler_info["metadata"]
        
        start_time = time.time()
        result = None
        details = None
        
        try:
            if is_async:
                if timeout:
                    try:
                        result = await asyncio.wait_for(cleanup_func(), timeout=timeout)
                    except asyncio.TimeoutError:
                        status = CleanupStatus.TIMEOUT
                        details = f"Cleanup timed out after {timeout} seconds"
                else:
                    result = await cleanup_func()
            else:
                if timeout:
                    # For non-async functions, run in executor with timeout
                    loop = asyncio.get_event_loop()
                    try:
                        result = await asyncio.wait_for(
                            loop.run_in_executor(None, cleanup_func),
                            timeout=timeout
                        )
                    except asyncio.TimeoutError:
                        status = CleanupStatus.TIMEOUT
                        details = f"Cleanup timed out after {timeout} seconds"
                else:
                    # Run non-async function in executor
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, cleanup_func)
            
            # Only set status if not already set (e.g., by timeout)
            if "status" not in locals():
                if isinstance(result, tuple) and len(result) >= 2:
                    # Assuming result is (success: bool, details: str)
                    status = CleanupStatus.SUCCESSFUL if result[0] else CleanupStatus.FAILED
                    details = result[1] if len(result) >= 2 else None
                elif isinstance(result, bool):
                    # Assuming result is success: bool
                    status = CleanupStatus.SUCCESSFUL if result else CleanupStatus.FAILED
                else:
                    # Assuming result is truthy/falsy
                    status = CleanupStatus.SUCCESSFUL if result else CleanupStatus.FAILED
        
        except Exception as e:
            status = CleanupStatus.FAILED
            details = f"Exception during cleanup: {str(e)}"
            logger.exception(f"Error cleaning up resource '{resource_id}'")
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Create and store result
        cleanup_result = CleanupResult(
            resource_id=resource_id,
            resource_type=handler_info["resource_type"],
            status=status,
            details=details,
            duration=duration
        )
        
        async with self._lock:
            self._cleanup_results[resource_id] = cleanup_result
            
            # Notify reporter if available
            if self._reporter:
                await self._reporter.update_resource_cleanup_status(
                    resource_id=resource_id,
                    resource_type=handler_info["resource_type"],
                    status=status.value,
                    details=details,
                    duration=duration
                )
            
            logger.info(f"Resource cleanup for '{resource_id}' completed with status: {status.value}")
            if details:
                logger.info(f"  Details: {details}")
        
        return cleanup_result
    
    async def cleanup_all_resources(self, resource_types: Optional[List[str]] = None) -> Dict[str, CleanupResult]:
        """
        Clean up all registered resources.
        
        Args:
            resource_types: Optional list of resource types to clean up.
                           If provided, only resources of these types will be cleaned up.
        
        Returns:
            Dictionary of cleanup results by resource ID
        """
        # Get list of resources to clean up
        resource_ids = []
        async with self._lock:
            if resource_types:
                # Filter by resource type
                resource_ids = [
                    rid for rid, info in self._cleanup_handlers.items()
                    if info["resource_type"] in resource_types
                ]
            else:
                resource_ids = list(self._cleanup_handlers.keys())
        
        # Clean up each resource
        results = {}
        for resource_id in resource_ids:
            try:
                result = await self.cleanup_resource(resource_id)
                results[resource_id] = result
            except Exception as e:
                logger.exception(f"Error cleaning up resource '{resource_id}'")
                
                # Get resource type
                resource_type = "unknown"
                async with self._lock:
                    if resource_id in self._cleanup_handlers:
                        resource_type = self._cleanup_handlers[resource_id]["resource_type"]
                
                # Create failed result
                result = CleanupResult(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    status=CleanupStatus.FAILED,
                    details=f"Exception before execution: {str(e)}"
                )
                
                # Store result
                async with self._lock:
                    self._cleanup_results[resource_id] = result
                    
                    # Notify reporter if available
                    if self._reporter:
                        await self._reporter.update_resource_cleanup_status(
                            resource_id=resource_id,
                            resource_type=resource_type,
                            status=CleanupStatus.FAILED.value,
                            details=f"Exception before execution: {str(e)}"
                        )
                
                results[resource_id] = result
        
        # Generate and report summary if reporter available
        async with self._lock:
            if self._reporter:
                summary = await self.get_cleanup_summary()
                await self._reporter.update_cleanup_summary(summary)
        
        return results
    
    async def get_cleanup_results(self) -> Dict[str, CleanupResult]:
        """
        Get the results of all cleanup operations.
        
        Returns:
            Dictionary of cleanup results by resource ID
        """
        async with self._lock:
            return dict(self._cleanup_results)
    
    async def all_cleanups_successful(self) -> bool:
        """
        Check if all cleanup operations were successful.
        
        Returns:
            True if all cleanups were successful, False otherwise
        """
        async with self._lock:
            for result in self._cleanup_results.values():
                if result.status not in [CleanupStatus.SUCCESSFUL, CleanupStatus.SKIPPED]:
                    return False
            
            return True
    
    async def get_cleanup_summary(self) -> Dict[str, Any]:
        """
        Get a summary of cleanup results.
        
        Returns:
            Dictionary with cleanup summary information
        """
        async with self._lock:
            # Count statuses
            status_counts = {status: 0 for status in CleanupStatus}
            for result in self._cleanup_results.values():
                status_counts[result.status] += 1
            
            # Count by resource type
            resource_type_counts = {}
            for result in self._cleanup_results.values():
                if result.resource_type not in resource_type_counts:
                    resource_type_counts[result.resource_type] = 0
                resource_type_counts[result.resource_type] += 1
            
            # Calculate total duration
            total_duration = sum(
                result.duration for result in self._cleanup_results.values() 
                if result.duration is not None
            )
            
            # List resources with issues
            failed_resources = [
                {
                    "resource_id": result.resource_id,
                    "resource_type": result.resource_type,
                    "status": result.status.value,
                    "details": result.details
                }
                for result in self._cleanup_results.values()
                if result.status in [CleanupStatus.FAILED, CleanupStatus.TIMEOUT]
            ]
            
            # Build summary
            return {
                "total_resources": len(self._cleanup_results),
                "status_counts": {status.value: count for status, count in status_counts.items()},
                "resource_type_counts": resource_type_counts,
                "all_successful": all(
                    result.status in [CleanupStatus.SUCCESSFUL, CleanupStatus.SKIPPED]
                    for result in self._cleanup_results.values()
                ),
                "total_duration": total_duration,
                "failed_resources": failed_resources
            } 