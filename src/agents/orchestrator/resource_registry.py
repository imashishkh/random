import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

class ResourceCleanupRegistry:
    """
    Registry for tracking resources that need to be cleaned up during orchestrator shutdown.
    
    Resources are organized by category and priority, with cleanup functions registered
    for each resource. During shutdown, resources are cleaned up in priority order.
    """
    
    def __init__(self):
        """Initialize the resource cleanup registry."""
        # Structure to hold registered resources and their cleanup functions
        # {category: {priority: [(resource_id, cleanup_fn, kwargs)]}}
        self.resources: Dict[str, Dict[int, List[Tuple[str, Callable, Dict[str, Any]]]]] = {}
        
        # Track cleanup results
        self.cleanup_success: Dict[str, bool] = {}
        self.cleanup_errors: Dict[str, Exception] = {}
        
        # Default priorities by category
        self.default_priorities = {
            "agent": 10,
            "database": 20,
            "file": 30,
            "network": 40,
            "memory": 50,
            "misc": 90
        }
    
    def register_resource(self, 
                         resource_id: str,
                         cleanup_fn: Callable,
                         category: str = "misc",
                         priority: Optional[int] = None,
                         **kwargs) -> None:
        """
        Register a resource for cleanup during shutdown.
        
        Args:
            resource_id: Unique identifier for the resource
            cleanup_fn: Function to call for cleanup. Should take resource_id as first arg.
            category: Resource category (agent, database, file, network, memory, misc)
            priority: Priority within category (lower numbers are cleaned up earlier)
            **kwargs: Additional arguments to pass to the cleanup function
        """
        # Determine priority if not specified
        if priority is None:
            priority = self.default_priorities.get(category, 100)
        
        # Initialize category dict if needed
        if category not in self.resources:
            self.resources[category] = {}
        
        # Initialize priority list if needed
        if priority not in self.resources[category]:
            self.resources[category][priority] = []
        
        # Register the resource
        self.resources[category][priority].append((resource_id, cleanup_fn, kwargs))
        logger.debug(f"Registered resource for cleanup: {resource_id} ({category}, priority {priority})")
    
    def unregister_resource(self, resource_id: str) -> bool:
        """
        Remove a resource from the registry.
        
        Args:
            resource_id: Identifier of the resource to remove
            
        Returns:
            bool: True if resource was found and removed, False otherwise
        """
        for category in self.resources:
            for priority in self.resources[category]:
                resource_list = self.resources[category][priority]
                for i, (rid, _, _) in enumerate(resource_list):
                    if rid == resource_id:
                        resource_list.pop(i)
                        logger.debug(f"Unregistered resource: {resource_id}")
                        return True
        
        logger.warning(f"Resource not found for unregistration: {resource_id}")
        return False
    
    def cleanup_resource(self, resource_id: str, 
                        cleanup_fn: Callable, 
                        kwargs: Dict[str, Any]) -> bool:
        """
        Clean up a specific resource.
        
        Args:
            resource_id: Resource identifier
            cleanup_fn: Function to call for cleanup
            kwargs: Additional arguments for the cleanup function
            
        Returns:
            bool: True if cleanup succeeded, False otherwise
        """
        try:
            logger.info(f"Cleaning up resource: {resource_id}")
            cleanup_fn(resource_id, **kwargs)
            self.cleanup_success[resource_id] = True
            logger.debug(f"Successfully cleaned up resource: {resource_id}")
            return True
        except Exception as e:
            self.cleanup_errors[resource_id] = e
            logger.error(f"Error cleaning up resource {resource_id}: {str(e)}")
            return False
    
    def cleanup_category(self, category: str, 
                        timeout: Optional[float] = None) -> Tuple[int, int]:
        """
        Clean up all resources in a specific category.
        
        Args:
            category: Category to clean up
            timeout: Maximum time in seconds for cleanup (None for no timeout)
            
        Returns:
            Tuple of (successful_cleanups, failed_cleanups)
        """
        if category not in self.resources:
            logger.debug(f"No resources registered for category: {category}")
            return (0, 0)
        
        logger.info(f"Cleaning up resources in category: {category}")
        
        successful = 0
        failed = 0
        start_time = time.time()
        
        # Process priorities in ascending order (lowest first)
        priorities = sorted(self.resources[category].keys())
        
        for priority in priorities:
            # Check timeout if specified
            if timeout is not None and time.time() - start_time > timeout:
                logger.warning(f"Timeout reached while cleaning up {category} resources")
                break
            
            resources = self.resources[category][priority]
            for resource_id, cleanup_fn, kwargs in resources:
                if self.cleanup_resource(resource_id, cleanup_fn, kwargs):
                    successful += 1
                else:
                    failed += 1
        
        logger.info(f"Cleaned up {successful} resources in {category} (failed: {failed})")
        return (successful, failed)
    
    def cleanup_all(self, 
                   timeout: Optional[float] = None,
                   categories_order: Optional[List[str]] = None) -> Dict[str, int]:
        """
        Clean up all registered resources across all categories.
        
        Args:
            timeout: Maximum time in seconds for cleanup (None for no timeout)
            categories_order: Custom order for processing categories
            
        Returns:
            Dict with cleanup stats
        """
        logger.info("Starting cleanup of all registered resources")
        
        # Determine categories order
        if categories_order is None:
            # Default order: agents first, databases next, etc.
            categories_order = [
                "agent", "database", "network", "file", "memory", "misc"
            ]
        
        # Add any categories that aren't in the provided order
        all_categories = set(self.resources.keys())
        for category in all_categories:
            if category not in categories_order:
                categories_order.append(category)
        
        start_time = time.time()
        total_successful = 0
        total_failed = 0
        category_stats = {}
        
        # Process categories in specified order
        for category in categories_order:
            if category not in self.resources:
                continue
                
            # Check timeout if specified
            if timeout is not None and time.time() - start_time > timeout:
                logger.warning("Timeout reached during resource cleanup")
                break
            
            # Calculate remaining time for this category if timeout specified
            remaining_time = None
            if timeout is not None:
                remaining_time = timeout - (time.time() - start_time)
                if remaining_time <= 0:
                    break
            
            # Clean up this category
            successful, failed = self.cleanup_category(category, remaining_time)
            total_successful += successful
            total_failed += failed
            category_stats[category] = {"successful": successful, "failed": failed}
        
        cleanup_time = time.time() - start_time
        
        logger.info(
            f"Resource cleanup completed in {cleanup_time:.2f}s: "
            f"{total_successful} successful, {total_failed} failed"
        )
        
        return {
            "total_resources": total_successful + total_failed,
            "successful": total_successful,
            "failed": total_failed,
            "errors": len(self.cleanup_errors),
            "time": cleanup_time,
            "categories": category_stats
        }
    
    def get_cleanup_report(self) -> Dict:
        """
        Get a report of resource cleanup results.
        
        Returns:
            Dict with cleanup stats and errors
        """
        total = len(self.cleanup_success) + len(self.cleanup_errors)
        successful = sum(1 for success in self.cleanup_success.values() if success)
        
        return {
            "total_resources": total,
            "successful": successful,
            "failed": total - successful,
            "error_count": len(self.cleanup_errors),
            "error_details": {
                resource_id: str(error) 
                for resource_id, error in self.cleanup_errors.items()
            }
        } 