"""
Shutdown Coordinator

This module provides a high-level interface for coordinating the shutdown of
trading agents in the system. It encapsulates the shutdown protocol and provides
additional functionality for monitoring and reporting shutdown progress.
"""

import asyncio
import logging
import threading
import time
from typing import Dict, List, Optional, Callable, Any, Set, Awaitable
from enum import Enum

from .shutdown_protocol import (
    get_shutdown_protocol,
    ShutdownPhase,
    ShutdownStatus,
    AgentShutdownState
)

# Configure logger
logger = logging.getLogger(__name__)


class ShutdownCoordinator:
    """
    Coordinator for gracefully shutting down agents in the system.
    
    This class provides a high-level interface for coordinating the shutdown
    of trading agents, encapsulating the shutdown protocol and providing
    additional functionality for monitoring and reporting shutdown progress.
    """
    
    def __init__(self):
        """Initialize the shutdown coordinator."""
        self._protocol = get_shutdown_protocol()
        self._shutdown_lock = threading.RLock()
        self._shutdown_initialized = False
        self._shutdown_in_progress = False
        self._shutdown_complete = False
        self._shutdown_start_time = None
        self._shutdown_end_time = None
        self._force_shutdown = False
        self._shutdown_reason = None
        self._critical_error = None
        
        # Callbacks for monitoring shutdown progress
        self._progress_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._completion_callbacks: List[Callable[[Dict[str, Any], bool], None]] = []
        
        # Progress reporting
        self._progress_reporting_interval = 1.0  # seconds
        self._progress_reporting_task = None
        
        logger.info("Shutdown coordinator initialized")
    
    def initialize_shutdown(self, 
                          reason: str = "Normal shutdown", 
                          critical_error: Optional[Exception] = None,
                          preparation_timeout: float = None,
                          stop_timeout: float = None,
                          cleanup_timeout: float = None) -> bool:
        """
        Initialize the shutdown process with custom settings.
        
        Args:
            reason: Human-readable reason for shutdown
            critical_error: Critical exception that triggered shutdown (if any)
            preparation_timeout: Custom timeout for preparation phase (seconds)
            stop_timeout: Custom timeout for stop phase (seconds)
            cleanup_timeout: Custom timeout for cleanup phase (seconds)
            
        Returns:
            True if initialization successful, False if already initialized
        """
        with self._shutdown_lock:
            if self._shutdown_initialized:
                logger.warning("Shutdown already initialized")
                return False
            
            self._shutdown_initialized = True
            self._shutdown_reason = reason
            self._critical_error = critical_error
            
            # Set custom timeouts if provided
            if any(t is not None for t in [preparation_timeout, stop_timeout, cleanup_timeout]):
                self._protocol.set_timeouts(preparation_timeout, stop_timeout, cleanup_timeout)
            
            logger.info(f"Shutdown initialized: {reason}")
            
            if critical_error:
                logger.error(f"Shutdown triggered by critical error: {str(critical_error)}")
            
            return True
    
    def register_agent(self, 
                     agent_id: str, 
                     agent_type: str, 
                     agent_instance: Any,
                     shutdown_priority: int = 0,
                     dependencies: List[str] = None) -> None:
        """
        Register an agent for shutdown tracking.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_type: Type of agent (technical, execution, etc.)
            agent_instance: Reference to the agent instance
            shutdown_priority: Priority during shutdown (higher values are processed first)
            dependencies: List of agent IDs this agent depends on
        """
        self._protocol.registry.register_agent(
            agent_id, agent_type, agent_instance, shutdown_priority, dependencies
        )
    
    def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent from shutdown tracking.
        
        Args:
            agent_id: ID of the agent to unregister
            
        Returns:
            True if unregistered, False if not found
        """
        return self._protocol.registry.unregister_agent(agent_id)
    
    def register_progress_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Register a callback for shutdown progress updates.
        
        Args:
            callback: Function to call with progress updates
        """
        with self._shutdown_lock:
            self._progress_callbacks.append(callback)
    
    def register_completion_callback(self, callback: Callable[[Dict[str, Any], bool], None]) -> None:
        """
        Register a callback for shutdown completion.
        
        Args:
            callback: Function to call when shutdown completes
                     (receives progress stats and success flag)
        """
        with self._shutdown_lock:
            self._completion_callbacks.append(callback)
    
    def set_progress_reporting_interval(self, interval: float) -> None:
        """
        Set the interval for progress reporting during shutdown.
        
        Args:
            interval: Interval in seconds (minimum 0.1)
        """
        with self._shutdown_lock:
            self._progress_reporting_interval = max(0.1, interval)
    
    async def shutdown_agent(self, agent_id: str, force: bool = False) -> bool:
        """
        Shut down a specific agent using the shutdown protocol.
        
        Args:
            agent_id: ID of the agent to shut down
            force: Whether to force shutdown even if phases fail
            
        Returns:
            True if shutdown was successful, False otherwise
        """
        return await self._protocol.shutdown_agent(agent_id, force)
    
    async def shutdown_all_agents(self, force: bool = False) -> bool:
        """
        Shut down all registered agents using the shutdown protocol.
        
        Args:
            force: Whether to force shutdown even if phases fail
            
        Returns:
            True if all shutdowns were successful, False otherwise
        """
        with self._shutdown_lock:
            if not self._shutdown_initialized:
                logger.warning("Shutdown not initialized, initializing with default settings")
                self.initialize_shutdown("Automatic shutdown")
            
            if self._shutdown_in_progress:
                logger.warning("Shutdown already in progress")
                return False
            
            self._shutdown_in_progress = True
            self._shutdown_start_time = time.time()
            self._force_shutdown = force
        
        # Start progress reporting
        await self._start_progress_reporting()
        
        # Perform the actual shutdown
        success = False
        try:
            success = await self._protocol.shutdown_all_agents(force)
            return success
        finally:
            # Cleanup and notify completion
            with self._shutdown_lock:
                self._shutdown_in_progress = False
                self._shutdown_complete = True
                self._shutdown_end_time = time.time()
            
            # Stop progress reporting
            await self._stop_progress_reporting()
            
            # Notify completion callbacks
            final_stats = self._protocol.registry.get_shutdown_progress()
            final_stats["reason"] = self._shutdown_reason
            final_stats["force_shutdown"] = self._force_shutdown
            final_stats["total_time"] = self._shutdown_end_time - self._shutdown_start_time
            
            for callback in self._completion_callbacks:
                try:
                    callback(final_stats, success)
                except Exception as e:
                    logger.error(f"Error in shutdown completion callback: {str(e)}")
    
    async def emergency_shutdown(self, reason: str = "Emergency shutdown") -> bool:
        """
        Perform an emergency shutdown with minimal timeouts.
        
        Args:
            reason: Reason for emergency shutdown
            
        Returns:
            True if shutdown was initiated, False otherwise
        """
        with self._shutdown_lock:
            if self._shutdown_in_progress:
                logger.warning("Shutdown already in progress, cannot initiate emergency shutdown")
                return False
            
            # Set minimal timeouts for emergency
            self._protocol.set_timeouts(
                preparation=3.0,  # Very short preparation time
                stop=2.0,         # Quick stop
                cleanup=1.0       # Minimal cleanup
            )
            
            self.initialize_shutdown(f"EMERGENCY: {reason}", None)
        
        # Force shutdown all agents
        return await self.shutdown_all_agents(force=True)
    
    async def wait_for_shutdown(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for shutdown to complete.
        
        Args:
            timeout: Maximum time to wait in seconds, or None to wait indefinitely
            
        Returns:
            True if shutdown completed, False if timeout was reached
        """
        return await self._protocol.wait_for_shutdown(timeout)
    
    def get_shutdown_progress(self) -> Dict[str, Any]:
        """
        Get current shutdown progress statistics.
        
        Returns:
            Dictionary with detailed shutdown statistics
        """
        with self._shutdown_lock:
            stats = self._protocol.registry.get_shutdown_progress()
            
            # Add additional context
            stats["shutdown_initialized"] = self._shutdown_initialized
            stats["shutdown_in_progress"] = self._shutdown_in_progress
            stats["shutdown_complete"] = self._shutdown_complete
            stats["force_shutdown"] = self._force_shutdown
            stats["reason"] = self._shutdown_reason
            
            # Calculate elapsed time
            if self._shutdown_start_time:
                if self._shutdown_end_time:
                    stats["elapsed_time"] = self._shutdown_end_time - self._shutdown_start_time
                else:
                    stats["elapsed_time"] = time.time() - self._shutdown_start_time
            else:
                stats["elapsed_time"] = 0
            
            return stats
    
    def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed shutdown status for a specific agent.
        
        Args:
            agent_id: ID of the agent
            
        Returns:
            Dictionary with agent shutdown status, or None if not found
        """
        agent_state = self._protocol.registry.get_agent_state(agent_id)
        if not agent_state:
            return None
        
        return {
            "agent_id": agent_state.agent_id,
            "agent_type": agent_state.agent_type,
            "current_phase": agent_state.get_current_phase().value,
            "overall_status": agent_state.overall_status.value,
            "is_complete": agent_state.is_complete(),
            "was_successful": agent_state.was_successful(),
            "execution_time": agent_state.get_execution_time(),
            "registered_at": agent_state.registered_at,
            "shutdown_priority": agent_state.shutdown_priority,
            "dependencies": agent_state.dependencies,
            "phases": {
                "preparation": {
                    "status": agent_state.preparation_status.value,
                    "start_time": agent_state.preparation_start,
                    "end_time": agent_state.preparation_end,
                    "error": agent_state.preparation_error
                },
                "stop": {
                    "status": agent_state.stop_status.value,
                    "start_time": agent_state.stop_start,
                    "end_time": agent_state.stop_end,
                    "error": agent_state.stop_error
                },
                "cleanup": {
                    "status": agent_state.cleanup_status.value,
                    "start_time": agent_state.cleanup_start,
                    "end_time": agent_state.cleanup_end,
                    "error": agent_state.cleanup_error
                }
            }
        }
    
    async def _start_progress_reporting(self) -> None:
        """Start the background task for progress reporting."""
        if self._progress_reporting_task is not None:
            return
        
        self._progress_reporting_task = asyncio.create_task(self._report_progress())
    
    async def _stop_progress_reporting(self) -> None:
        """Stop the background task for progress reporting."""
        if self._progress_reporting_task is None:
            return
        
        self._progress_reporting_task.cancel()
        try:
            await self._progress_reporting_task
        except asyncio.CancelledError:
            pass
        finally:
            self._progress_reporting_task = None
    
    async def _report_progress(self) -> None:
        """Background task for periodically reporting shutdown progress."""
        try:
            while True:
                # Get current progress
                progress = self.get_shutdown_progress()
                
                # Notify all callbacks
                for callback in self._progress_callbacks:
                    try:
                        callback(progress)
                    except Exception as e:
                        logger.error(f"Error in progress callback: {str(e)}")
                
                # Wait for next interval
                await asyncio.sleep(self._progress_reporting_interval)
        except asyncio.CancelledError:
            # Task was cancelled, exit cleanly
            pass
        except Exception as e:
            logger.error(f"Error in progress reporting task: {str(e)}")


# Singleton instance
_shutdown_coordinator_instance = None


def get_shutdown_coordinator() -> ShutdownCoordinator:
    """
    Get or create the singleton shutdown coordinator instance.
    
    Returns:
        The shutdown coordinator instance
    """
    global _shutdown_coordinator_instance
    if _shutdown_coordinator_instance is None:
        _shutdown_coordinator_instance = ShutdownCoordinator()
    return _shutdown_coordinator_instance 