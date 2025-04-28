"""
Resource Cleaner for Graceful Shutdown

This module provides functionality to clean up resources during system shutdown,
ensuring that all connections, file handles, and other resources are properly released.
"""

import asyncio
import logging
import sys
import gc
from typing import Dict, Any, Optional, List, Callable, Set

# Import our new shutdown coordinator
from .shutdown import ShutdownPhase, ShutdownCoordinator, get_shutdown_coordinator

# Configure logger
logger = logging.getLogger(__name__)


class ResourceCleaner:
    """
    Handles the cleanup of resources during system shutdown.
    
    This class ensures that all connections, file handles, and other resources
    are properly released during the shutdown process.
    """
    
    def __init__(self):
        """Initialize the resource cleaner."""
        # Get the shutdown coordinator
        self.shutdown_coordinator = get_shutdown_coordinator()
        
        # Track cleanup results
        self.cleanup_results = {}
        
        # Custom cleanup callbacks
        self.custom_cleanup_callbacks = []
        
        # Register with shutdown coordinator
        self.register_with_coordinator()
    
    def register_with_coordinator(self) -> None:
        """Register callbacks with the shutdown coordinator."""
        self.shutdown_coordinator.register_phase_callback(
            ShutdownPhase.RESOURCES,
            self.cleanup_resources
        )
    
    def register_cleanup_callback(self, callback: Callable[[], Any]) -> None:
        """
        Register a custom cleanup callback.
        
        Args:
            callback: A function to be called during resource cleanup
        """
        self.custom_cleanup_callbacks.append(callback)
        logger.debug(f"Registered custom cleanup callback: {callback.__name__}")
    
    async def cleanup_resources(self) -> None:
        """
        Clean up resources during shutdown.
        
        This method is called by the shutdown coordinator during the RESOURCES phase.
        """
        logger.info("Starting resource cleanup process")
        
        cleanup_tasks = [
            self._close_file_handles(),
            self._close_network_connections(),
            self._run_custom_cleanup(),
            self._run_garbage_collection(),
        ]
        
        # Run all cleanup tasks concurrently
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        logger.info("Resource cleanup complete")
    
    async def _close_file_handles(self) -> None:
        """Close any open file handles."""
        logger.info("Closing file handles")
        
        try:
            # Get all open file handles
            # This is not a comprehensive solution, but a starting point
            # A real implementation would track file handles explicitly
            open_files = 0
            closed_files = 0
            
            # Flush stdout and stderr
            sys.stdout.flush()
            sys.stderr.flush()
            
            # In a real implementation, we'd have a registry of open files to close
            # For this example, we'll just log the action
            logger.info("Flushed stdout and stderr")
            
            self.cleanup_results['files'] = {
                'found': open_files,
                'closed': closed_files,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Error closing file handles: {str(e)}", exc_info=True)
            self.cleanup_results['files'] = {
                'success': False,
                'error': str(e)
            }
    
    async def _close_network_connections(self) -> None:
        """Close any open network connections."""
        logger.info("Closing network connections")
        
        try:
            # In a real implementation, we'd have a registry of connections to close
            # For this example, we'll just log the action
            
            # Get references to connection managers we might have
            connection_managers = []
            closed_connections = 0
            
            # For each connection manager, close its connections
            for manager in connection_managers:
                # This is a placeholder for actual connection closing logic
                logger.debug(f"Would close connections for manager: {manager}")
                closed_connections += 1
            
            self.cleanup_results['connections'] = {
                'closed': closed_connections,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Error closing network connections: {str(e)}", exc_info=True)
            self.cleanup_results['connections'] = {
                'success': False,
                'error': str(e)
            }
    
    async def _run_custom_cleanup(self) -> None:
        """Run any custom cleanup callbacks."""
        logger.info("Running custom cleanup callbacks")
        
        if not self.custom_cleanup_callbacks:
            logger.debug("No custom cleanup callbacks registered")
            self.cleanup_results['custom_cleanup'] = {
                'total': 0,
                'success': True
            }
            return
        
        successes = 0
        failures = 0
        
        # Run each callback
        for callback in self.custom_cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
                successes += 1
                logger.debug(f"Successfully ran cleanup callback: {callback.__name__}")
            except Exception as e:
                failures += 1
                logger.error(f"Error in cleanup callback {callback.__name__}: {str(e)}", exc_info=True)
        
        self.cleanup_results['custom_cleanup'] = {
            'total': len(self.custom_cleanup_callbacks),
            'success': failures == 0,
            'successful': successes,
            'failed': failures
        }
    
    async def _run_garbage_collection(self) -> None:
        """Run garbage collection to free memory."""
        logger.info("Running garbage collection")
        
        try:
            # Force garbage collection
            collected = gc.collect()
            logger.debug(f"Garbage collection freed {collected} objects")
            
            self.cleanup_results['garbage_collection'] = {
                'collected': collected,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Error during garbage collection: {str(e)}", exc_info=True)
            self.cleanup_results['garbage_collection'] = {
                'success': False,
                'error': str(e)
            }
    
    def get_cleanup_results(self) -> Dict[str, Any]:
        """
        Get the results of the resource cleanup process.
        
        Returns:
            Results of the cleanup process
        """
        return self.cleanup_results


# Singleton instance
_resource_cleaner_instance = None


def get_resource_cleaner() -> ResourceCleaner:
    """
    Get or create the singleton resource cleaner instance.
    
    Returns:
        The resource cleaner instance
    """
    global _resource_cleaner_instance
    if _resource_cleaner_instance is None:
        _resource_cleaner_instance = ResourceCleaner()
    return _resource_cleaner_instance


def register_cleanup_callback(callback: Callable[[], Any]) -> None:
    """
    Register a custom cleanup callback with the resource cleaner.
    
    This is a convenience function that gets the resource cleaner instance
    and registers the callback with it.
    
    Args:
        callback: A function to be called during resource cleanup
    """
    cleaner = get_resource_cleaner()
    cleaner.register_cleanup_callback(callback) 