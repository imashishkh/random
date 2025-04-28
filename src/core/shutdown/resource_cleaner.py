"""
ResourceCleaner - Responsible for safely cleaning up resources during shutdown
"""
import asyncio
import enum
import logging
import time
from typing import Dict, List, Callable, Optional, Any, Set, Awaitable, Union, Tuple

logger = logging.getLogger(__name__)

class ResourceType(enum.Enum):
    """Types of resources that can be registered for cleanup"""
    DATABASE = "DATABASE"
    FILE = "FILE"
    NETWORK = "NETWORK"
    API_CONNECTION = "API_CONNECTION"
    THREAD_POOL = "THREAD_POOL"
    PROCESS = "PROCESS"
    CUSTOM = "CUSTOM"


class Resource:
    """
    Representation of a resource that needs to be cleaned up during shutdown.
    """
    def __init__(self, 
                 resource_id: str,
                 resource_type: Union[ResourceType, str],
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 cleanup_handler: Optional[Callable[["Resource"], Awaitable[bool]]] = None,
                 resource_obj: Optional[Any] = None):
        """
        Initialize a Resource object.
        
        Args:
            resource_id: Unique identifier for the resource
            resource_type: Type of resource
            name: Human-readable name for the resource
            description: Description of the resource
            cleanup_handler: Custom function to clean up this resource
            resource_obj: The actual resource object (if applicable)
        """
        self.resource_id = resource_id
        
        # Handle resource_type as either enum or string
        if isinstance(resource_type, str):
            try:
                self.resource_type = ResourceType(resource_type)
            except ValueError:
                self.resource_type = ResourceType.CUSTOM
                self.custom_type = resource_type
        else:
            self.resource_type = resource_type
            self.custom_type = None
            
        self.name = name or f"{self.resource_type.value}-{resource_id[:8]}"
        self.description = description
        self.cleanup_handler = cleanup_handler
        self.resource_obj = resource_obj
        self.is_cleaning = False
        self.is_cleaned = False
        self.cleanup_time = None
        self.error = None
        
    def get_info(self) -> Dict[str, Any]:
        """Get resource information as a dictionary.
        
        Returns:
            dict: Resource information
        """
        return {
            "resource_id": self.resource_id,
            "resource_type": self.resource_type.value,
            "custom_type": self.custom_type,
            "name": self.name,
            "description": self.description,
            "is_cleaning": self.is_cleaning,
            "is_cleaned": self.is_cleaned,
            "cleanup_time": self.cleanup_time,
            "error": str(self.error) if self.error else None
        }


class ResourceCleaner:
    """
    Responsible for safely cleaning up resources during shutdown.
    """
    def __init__(self):
        """Initialize the ResourceCleaner."""
        self._resources: Dict[str, Resource] = {}  # resource_id -> Resource
        self._resource_sources: List[Callable[[], List[Resource]]] = []
        self._type_handlers: Dict[ResourceType, Callable[[Resource], Awaitable[bool]]] = {}
        self._last_cleanup_result: Optional[Dict[str, Any]] = None
        self._resource_priorities: Dict[str, int] = {}  # resource_id -> priority (0-100, higher first)
        
    def register_resource(self, resource: Resource, priority: int = 50) -> None:
        """
        Register a resource for tracking by the resource cleaner.
        
        Args:
            resource: Resource object to register
            priority: Priority for cleanup (0-100, higher means clean first)
        """
        self._resources[resource.resource_id] = resource
        self._resource_priorities[resource.resource_id] = max(0, min(100, priority))
        logger.debug(f"Registered resource {resource.resource_id} ({resource.name}) with priority {priority}")
        
    def unregister_resource(self, resource_id: str) -> bool:
        """
        Unregister a resource from tracking.
        
        Args:
            resource_id: ID of the resource to unregister
            
        Returns:
            bool: True if the resource was found and unregistered, False otherwise
        """
        if resource_id in self._resources:
            del self._resources[resource_id]
            if resource_id in self._resource_priorities:
                del self._resource_priorities[resource_id]
            logger.debug(f"Unregistered resource {resource_id}")
            return True
        return False
        
    def register_resource_source(self, source_func: Callable[[], List[Resource]]) -> None:
        """
        Register a function that provides resources from an external source.
        
        Args:
            source_func: Function that returns a list of resources
        """
        self._resource_sources.append(source_func)
        logger.debug("Registered resource source")
        
    def unregister_resource_source(self, source_func: Callable[[], List[Resource]]) -> bool:
        """
        Unregister a previously registered resource source.
        
        Args:
            source_func: The source function to unregister
            
        Returns:
            bool: True if the source was found and unregistered, False otherwise
        """
        if source_func in self._resource_sources:
            self._resource_sources.remove(source_func)
            logger.debug("Unregistered resource source")
            return True
        return False
        
    def register_type_handler(self, resource_type: ResourceType, 
                             handler: Callable[[Resource], Awaitable[bool]]) -> None:
        """
        Register a handler for cleaning up resources of a specific type.
        
        Args:
            resource_type: Type of resource this handler can clean
            handler: Async function that cleans the resource
        """
        self._type_handlers[resource_type] = handler
        logger.debug(f"Registered cleanup handler for resource type {resource_type.value}")
        
    def unregister_type_handler(self, resource_type: ResourceType) -> bool:
        """
        Unregister a previously registered type handler.
        
        Args:
            resource_type: Type of resource handler to unregister
            
        Returns:
            bool: True if the handler was found and unregistered, False otherwise
        """
        if resource_type in self._type_handlers:
            del self._type_handlers[resource_type]
            logger.debug(f"Unregistered cleanup handler for resource type {resource_type.value}")
            return True
        return False
        
    def set_resource_priority(self, resource_id: str, priority: int) -> bool:
        """
        Set the cleanup priority for a resource.
        
        Args:
            resource_id: ID of the resource
            priority: Priority (0-100, higher means clean first)
            
        Returns:
            bool: True if the resource was found and priority set, False otherwise
        """
        if resource_id in self._resources:
            self._resource_priorities[resource_id] = max(0, min(100, priority))
            logger.debug(f"Set priority {priority} for resource {resource_id}")
            return True
        return False
        
    async def cleanup_all_resources(self) -> bool:
        """
        Clean up all registered resources.
        
        Returns:
            bool: True if all resources were successfully cleaned up, False otherwise
        """
        # First gather all resources from registered sources
        self._fetch_resources_from_sources()
        
        if not self._resources:
            logger.info("No resources to clean up")
            self._last_cleanup_result = {
                "success": True,
                "total_resources": 0,
                "cleaned_resources": 0,
                "time_taken": 0.0
            }
            return True
            
        start_time = time.time()
        logger.info(f"Starting to clean up {len(self._resources)} resources")
        
        # Sort resources by priority (higher priority first)
        sorted_resources = sorted(
            self._resources.values(),
            key=lambda r: self._resource_priorities.get(r.resource_id, 50),
            reverse=True
        )
        
        # Group resources by type for more efficient cleanup
        resource_groups: Dict[ResourceType, List[Resource]] = {}
        for res in sorted_resources:
            if res.resource_type not in resource_groups:
                resource_groups[res.resource_type] = []
            resource_groups[res.resource_type].append(res)
        
        # Clean up resources by type
        cleaned_count = 0
        for res_type, resources in resource_groups.items():
            # Clean resources of the same type in parallel
            tasks = [self._cleanup_resource(res) for res in resources]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count successes
            for i, result in enumerate(results):
                if result is True:  # Successfully cleaned
                    cleaned_count += 1
                elif isinstance(result, Exception):
                    logger.error(f"Error cleaning resource {resources[i].resource_id}: {result}")
                    resources[i].error = result
        
        total_resources = len(self._resources)
        success = cleaned_count == total_resources
        
        time_taken = time.time() - start_time
        logger.info(f"Resource cleanup completed: {cleaned_count}/{total_resources} resources cleaned "
                    f"in {time_taken:.2f} seconds")
        
        self._last_cleanup_result = {
            "success": success,
            "total_resources": total_resources,
            "cleaned_resources": cleaned_count,
            "failed_resources": total_resources - cleaned_count,
            "time_taken": time_taken
        }
        
        return success
        
    async def _cleanup_resource(self, resource: Resource) -> bool:
        """
        Clean up a single resource.
        
        Args:
            resource: Resource to clean up
            
        Returns:
            bool: True if successfully cleaned up, False otherwise
        """
        if resource.is_cleaned:
            return True
            
        resource.is_cleaning = True
        
        try:
            # First try using resource's custom handler if available
            if resource.cleanup_handler is not None:
                logger.info(f"Cleaning resource {resource.resource_id} ({resource.name}) using custom handler")
                success = await resource.cleanup_handler(resource)
            # Next try using a registered type handler if available
            elif resource.resource_type in self._type_handlers:
                logger.info(f"Cleaning resource {resource.resource_id} ({resource.name}) using type handler")
                handler = self._type_handlers[resource.resource_type]
                success = await handler(resource)
            else:
                # Default cleanup logic - just log that we can't clean this
                logger.warning(f"No handler available for resource {resource.resource_id} "
                              f"({resource.name}) of type {resource.resource_type.value}")
                # Simple simulation for demonstration
                await asyncio.sleep(0.1)
                success = True
                
            if success:
                resource.is_cleaned = True
                resource.cleanup_time = time.time()
                logger.info(f"Resource {resource.resource_id} ({resource.name}) cleaned up successfully")
            else:
                logger.error(f"Failed to clean up resource {resource.resource_id} ({resource.name})")
                
            resource.is_cleaning = False
            return success
            
        except Exception as e:
            logger.exception(f"Error cleaning up resource {resource.resource_id}: {e}")
            resource.is_cleaning = False
            resource.error = e
            return False
            
    def _fetch_resources_from_sources(self) -> None:
        """Fetch resources from all registered sources."""
        for source_func in self._resource_sources:
            try:
                resources = source_func()
                for res in resources:
                    if res.resource_id not in self._resources:
                        self._resources[res.resource_id] = res
                        # Use default priority for resources from sources
                        if res.resource_id not in self._resource_priorities:
                            self._resource_priorities[res.resource_id] = 50
                        logger.debug(f"Added resource {res.resource_id} from source")
            except Exception as e:
                logger.error(f"Error fetching resources from source: {e}")
                
    def get_resources(self) -> List[Resource]:
        """
        Get all registered resources.
        
        Returns:
            List[Resource]: All currently registered resources
        """
        return list(self._resources.values())
        
    def get_resource(self, resource_id: str) -> Optional[Resource]:
        """
        Get a specific resource by ID.
        
        Args:
            resource_id: ID of the resource to get
            
        Returns:
            Optional[Resource]: The resource if found, None otherwise
        """
        return self._resources.get(resource_id)
        
    def get_last_cleanup_result(self) -> Optional[Dict[str, Any]]:
        """
        Get the result of the last cleanup_all_resources call.
        
        Returns:
            Optional[Dict[str, Any]]: Result of the last cleanup operation, or None if not called yet
        """
        return self._last_cleanup_result
    
    # Convenience methods for creating and registering common resources
    def register_database_connection(self, conn_id: str, connection_obj: Any, 
                                     name: Optional[str] = None, priority: int = 80) -> Resource:
        """
        Register a database connection for cleanup.
        
        Args:
            conn_id: Unique identifier for the connection
            connection_obj: The database connection object
            name: Human-readable name for the connection
            priority: Cleanup priority (higher is cleaned first)
            
        Returns:
            Resource: The created and registered resource
        """
        resource = Resource(
            resource_id=conn_id,
            resource_type=ResourceType.DATABASE,
            name=name or f"Database-{conn_id[:8]}",
            description="Database connection",
            resource_obj=connection_obj
        )
        self.register_resource(resource, priority)
        return resource
        
    def register_file_handle(self, file_id: str, file_obj: Any, 
                            name: Optional[str] = None, priority: int = 70) -> Resource:
        """
        Register a file handle for cleanup.
        
        Args:
            file_id: Unique identifier for the file
            file_obj: The file object
            name: Human-readable name for the file
            priority: Cleanup priority (higher is cleaned first)
            
        Returns:
            Resource: The created and registered resource
        """
        resource = Resource(
            resource_id=file_id,
            resource_type=ResourceType.FILE,
            name=name or f"File-{file_id[:8]}",
            description="File handle",
            resource_obj=file_obj
        )
        self.register_resource(resource, priority)
        return resource
        
    def register_network_connection(self, conn_id: str, connection_obj: Any, 
                                   name: Optional[str] = None, priority: int = 75) -> Resource:
        """
        Register a network connection for cleanup.
        
        Args:
            conn_id: Unique identifier for the connection
            connection_obj: The network connection object
            name: Human-readable name for the connection
            priority: Cleanup priority (higher is cleaned first)
            
        Returns:
            Resource: The created and registered resource
        """
        resource = Resource(
            resource_id=conn_id,
            resource_type=ResourceType.NETWORK,
            name=name or f"Network-{conn_id[:8]}",
            description="Network connection",
            resource_obj=connection_obj
        )
        self.register_resource(resource, priority)
        return resource
        
    def register_api_connection(self, api_id: str, api_obj: Any, 
                               name: Optional[str] = None, priority: int = 85) -> Resource:
        """
        Register an API connection for cleanup.
        
        Args:
            api_id: Unique identifier for the API connection
            api_obj: The API connection object
            name: Human-readable name for the connection
            priority: Cleanup priority (higher is cleaned first)
            
        Returns:
            Resource: The created and registered resource
        """
        resource = Resource(
            resource_id=api_id,
            resource_type=ResourceType.API_CONNECTION,
            name=name or f"API-{api_id[:8]}",
            description="API connection",
            resource_obj=api_obj
        )
        self.register_resource(resource, priority)
        return resource
        
    def register_thread_pool(self, pool_id: str, pool_obj: Any, 
                            name: Optional[str] = None, priority: int = 60) -> Resource:
        """
        Register a thread pool for cleanup.
        
        Args:
            pool_id: Unique identifier for the thread pool
            pool_obj: The thread pool object
            name: Human-readable name for the pool
            priority: Cleanup priority (higher is cleaned first)
            
        Returns:
            Resource: The created and registered resource
        """
        resource = Resource(
            resource_id=pool_id,
            resource_type=ResourceType.THREAD_POOL,
            name=name or f"ThreadPool-{pool_id[:8]}",
            description="Thread pool",
            resource_obj=pool_obj
        )
        self.register_resource(resource, priority)
        return resource
        
    def register_process(self, process_id: str, process_obj: Any, 
                        name: Optional[str] = None, priority: int = 65) -> Resource:
        """
        Register a process for cleanup.
        
        Args:
            process_id: Unique identifier for the process
            process_obj: The process object
            name: Human-readable name for the process
            priority: Cleanup priority (higher is cleaned first)
            
        Returns:
            Resource: The created and registered resource
        """
        resource = Resource(
            resource_id=process_id,
            resource_type=ResourceType.PROCESS,
            name=name or f"Process-{process_id[:8]}",
            description="Process",
            resource_obj=process_obj
        )
        self.register_resource(resource, priority)
        return resource
        
    def register_custom_resource(self, resource_id: str, custom_type: str, resource_obj: Any,
                               name: Optional[str] = None, description: Optional[str] = None,
                               cleanup_handler: Optional[Callable[[Resource], Awaitable[bool]]] = None,
                               priority: int = 50) -> Resource:
        """
        Register a custom resource for cleanup.
        
        Args:
            resource_id: Unique identifier for the resource
            custom_type: Custom type string for the resource
            resource_obj: The resource object
            name: Human-readable name for the resource
            description: Description of the resource
            cleanup_handler: Custom function to clean up this resource
            priority: Cleanup priority (higher is cleaned first)
            
        Returns:
            Resource: The created and registered resource
        """
        resource = Resource(
            resource_id=resource_id,
            resource_type=custom_type,
            name=name or f"{custom_type}-{resource_id[:8]}",
            description=description or f"Custom resource of type {custom_type}",
            cleanup_handler=cleanup_handler,
            resource_obj=resource_obj
        )
        self.register_resource(resource, priority)
        return resource 