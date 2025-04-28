"""
ShutdownCoordinator - Main module for coordinating the graceful shutdown process
"""
import asyncio
import enum
import logging
import time
from typing import Dict, List, Callable, Optional, Any, Awaitable, Union, Tuple

from .position_closer import PositionCloser, PositionCloseStrategy
from .agent_terminator import AgentTerminator
from .resource_cleaner import ResourceCleaner

logger = logging.getLogger(__name__)

class ShutdownPhase(enum.Enum):
    """Enum representing the different phases of shutdown"""
    IDLE = "IDLE"  # No shutdown in progress
    INITIALIZING = "INITIALIZING"  # Starting shutdown
    PREPARING = "PREPARING"  # Setting up shutdown
    CLOSING_POSITIONS = "CLOSING_POSITIONS"  # Closing open trading positions
    STOPPING_AGENTS = "STOPPING_AGENTS"  # Terminating trading agents
    CLEANING_RESOURCES = "CLEANING_RESOURCES"  # Cleaning up resources
    COMPLETE = "COMPLETE"  # Shutdown complete
    FAILED = "FAILED"  # Shutdown failed


class ShutdownCoordinator:
    """
    Coordinates the entire shutdown process, managing state transitions
    and ensuring all components are properly shut down.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        """Singleton pattern to ensure only one ShutdownCoordinator exists"""
        if cls._instance is None:
            cls._instance = super(ShutdownCoordinator, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, position_closer: Optional[PositionCloser] = None,
                 agent_terminator: Optional[AgentTerminator] = None,
                 resource_cleaner: Optional[ResourceCleaner] = None):
        """Initialize the ShutdownCoordinator.
        
        Args:
            position_closer: Custom PositionCloser instance (or None for default)
            agent_terminator: Custom AgentTerminator instance (or None for default)
            resource_cleaner: Custom ResourceCleaner instance (or None for default)
        """
        # Skip initialization if already initialized (singleton pattern)
        if self._initialized:
            return
            
        self._position_closer = position_closer or PositionCloser()
        self._agent_terminator = agent_terminator or AgentTerminator()
        self._resource_cleaner = resource_cleaner or ResourceCleaner()

        # Shutdown state
        self._phase = ShutdownPhase.IDLE
        self._reason = None
        self._start_time = None
        self._end_time = None
        self._error = None
        self._progress_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._shutdown_complete_event = asyncio.Event()
        
        # Timeouts for different phases (in seconds)
        self._position_close_timeout = 60.0
        self._agent_termination_timeout = 30.0
        self._resource_cleanup_timeout = 30.0
        
        # Lock to ensure only one shutdown can occur at a time
        self._shutdown_lock = asyncio.Lock()
        
        # Mark as initialized
        self._initialized = True
        logger.debug("ShutdownCoordinator initialized")

    async def shutdown(self, reason: str = "Unspecified", 
                      position_strategy: str = PositionCloseStrategy.GRADUAL,
                      force_after_timeout: bool = True) -> bool:
        """
        Perform a graceful shutdown of all systems.
        
        Args:
            reason: Reason for shutdown, for logging purposes
            position_strategy: Strategy for closing positions (IMMEDIATE, GRADUAL, NONE)
            force_after_timeout: Whether to force shutdown if a phase times out
            
        Returns:
            bool: True if shutdown completed successfully, False otherwise
        """
        async with self._shutdown_lock:
            # Check if shutdown is already in progress
            if self._phase != ShutdownPhase.IDLE and self._phase != ShutdownPhase.COMPLETE:
                logger.warning(f"Shutdown already in progress in phase {self._phase}. Ignoring request.")
                return False
                
            if self._phase == ShutdownPhase.COMPLETE:
                logger.info("System is already shut down. Ignoring request.")
                return True
                
            # Start shutdown process
            self._start_time = time.time()
            self._reason = reason
            self._error = None
            self._shutdown_complete_event.clear()
            
            logger.info(f"Starting graceful shutdown. Reason: {reason}")
            
            try:
                # Phase 1: Initialization
                await self._transition_to(ShutdownPhase.INITIALIZING)
                # Perform initialization checks
                
                # Phase 2: Preparation
                await self._transition_to(ShutdownPhase.PREPARING)
                # Prepare for shutdown, cache necessary state, etc.
                
                # Phase 3: Close Positions
                await self._transition_to(ShutdownPhase.CLOSING_POSITIONS)
                positions_closed = await asyncio.wait_for(
                    self._position_closer.close_all_positions(strategy=position_strategy),
                    timeout=self._position_close_timeout
                )
                
                if not positions_closed and force_after_timeout:
                    logger.warning("Forcing position closure after timeout")
                    # Force close positions if needed
                
                # Phase 4: Stop Agents
                await self._transition_to(ShutdownPhase.STOPPING_AGENTS)
                agents_stopped = await asyncio.wait_for(
                    self._agent_terminator.terminate_all_agents(),
                    timeout=self._agent_termination_timeout
                )
                
                if not agents_stopped and force_after_timeout:
                    logger.warning("Forcing agent termination after timeout")
                    # Force agent termination if needed
                
                # Phase 5: Clean Resources
                await self._transition_to(ShutdownPhase.CLEANING_RESOURCES)
                resources_cleaned = await asyncio.wait_for(
                    self._resource_cleaner.cleanup_all_resources(),
                    timeout=self._resource_cleanup_timeout
                )
                
                if not resources_cleaned and force_after_timeout:
                    logger.warning("Forcing resource cleanup after timeout")
                    # Force resource cleanup if needed
                
                # Phase 6: Complete
                await self._transition_to(ShutdownPhase.COMPLETE)
                self._end_time = time.time()
                elapsed = self._end_time - self._start_time
                logger.info(f"Shutdown completed successfully in {elapsed:.2f} seconds")
                self._shutdown_complete_event.set()
                return True
                
            except asyncio.TimeoutError as e:
                logger.error(f"Shutdown timed out during {self._phase}")
                self._error = e
                await self._transition_to(ShutdownPhase.FAILED)
                
                if force_after_timeout:
                    logger.warning("Forcing completion after timeout")
                    # Force completion if needed
                    await self._transition_to(ShutdownPhase.COMPLETE)
                    self._end_time = time.time()
                    self._shutdown_complete_event.set()
                    return False
                return False
                
            except Exception as e:
                logger.exception(f"Error during shutdown phase {self._phase}: {e}")
                self._error = e
                await self._transition_to(ShutdownPhase.FAILED)
                return False

    async def emergency_shutdown(self, reason: str = "Emergency", max_wait_time: float = 5.0) -> bool:
        """
        Perform an expedited shutdown when normal shutdown is too slow.
        
        Args:
            reason: Reason for emergency shutdown
            max_wait_time: Maximum time to wait for each phase in seconds
            
        Returns:
            bool: True if shutdown completed, False if still had to abort
        """
        logger.warning(f"EMERGENCY SHUTDOWN INITIATED: {reason}")
        
        # Store original timeouts and set temporary ones
        original_timeouts = (
            self._position_close_timeout,
            self._agent_termination_timeout,
            self._resource_cleanup_timeout
        )
        
        try:
            # Set emergency timeouts
            self._position_close_timeout = max_wait_time
            self._agent_termination_timeout = max_wait_time
            self._resource_cleanup_timeout = max_wait_time
            
            # Use IMMEDIATE position strategy for faster shutdown
            return await self.shutdown(
                reason=f"EMERGENCY: {reason}", 
                position_strategy=PositionCloseStrategy.IMMEDIATE,
                force_after_timeout=True
            )
            
        finally:
            # Restore original timeouts
            (
                self._position_close_timeout,
                self._agent_termination_timeout,
                self._resource_cleanup_timeout
            ) = original_timeouts

    async def _transition_to(self, new_phase: ShutdownPhase) -> None:
        """
        Transition to a new shutdown phase and notify all progress callbacks.
        
        Args:
            new_phase: The phase to transition to
        """
        old_phase = self._phase
        self._phase = new_phase
        
        logger.info(f"Shutdown phase transition: {old_phase} -> {new_phase}")
        
        # Notify all progress callbacks of the transition
        status = self.get_status()
        for callback in self._progress_callbacks:
            try:
                callback(status)
            except Exception as e:
                logger.error(f"Error in shutdown progress callback: {e}")

    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the shutdown process.
        
        Returns:
            dict: Status information including phase, elapsed time, etc.
        """
        current_time = time.time()
        elapsed_time = 0.0
        
        if self._start_time is not None:
            if self._end_time is not None:
                elapsed_time = self._end_time - self._start_time
            else:
                elapsed_time = current_time - self._start_time
                
        return {
            "phase": self._phase.value,
            "reason": self._reason,
            "start_time": self._start_time,
            "end_time": self._end_time,
            "elapsed_time": elapsed_time,
            "error": str(self._error) if self._error else None,
            "position_close_timeout": self._position_close_timeout,
            "agent_termination_timeout": self._agent_termination_timeout,
            "resource_cleanup_timeout": self._resource_cleanup_timeout
        }
        
    def register_progress_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Register a callback to be notified of shutdown progress.
        
        Args:
            callback: Function to call with status updates
        """
        self._progress_callbacks.append(callback)
        
    def unregister_progress_callback(self, callback: Callable[[Dict[str, Any]], None]) -> bool:
        """
        Unregister a previously registered progress callback.
        
        Args:
            callback: The callback to remove
            
        Returns:
            bool: True if the callback was found and removed, False otherwise
        """
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)
            return True
        return False
        
    def is_shutdown_complete(self) -> bool:
        """Check if shutdown is complete.
        
        Returns:
            bool: True if shutdown is complete, False otherwise
        """
        return self._phase == ShutdownPhase.COMPLETE
        
    def is_shutdown_in_progress(self) -> bool:
        """Check if shutdown is currently in progress.
        
        Returns:
            bool: True if shutdown is in progress, False otherwise
        """
        return (self._phase != ShutdownPhase.IDLE and 
                self._phase != ShutdownPhase.COMPLETE and
                self._phase != ShutdownPhase.FAILED)
                
    async def wait_for_shutdown_complete(self, timeout: Optional[float] = None) -> bool:
        """Wait for shutdown to complete.
        
        Args:
            timeout: Maximum time to wait in seconds, or None to wait indefinitely
            
        Returns:
            bool: True if shutdown completed, False if it timed out or failed
        """
        if self._phase == ShutdownPhase.COMPLETE:
            return True
            
        try:
            await asyncio.wait_for(self._shutdown_complete_event.wait(), timeout=timeout)
            return self._phase == ShutdownPhase.COMPLETE
        except asyncio.TimeoutError:
            return False
            
    # Timeout configuration methods
    def set_position_close_timeout(self, timeout_seconds: float) -> None:
        """Set timeout for position closing phase.
        
        Args:
            timeout_seconds: Timeout in seconds
        """
        self._position_close_timeout = float(timeout_seconds)
        
    def set_agent_termination_timeout(self, timeout_seconds: float) -> None:
        """Set timeout for agent termination phase.
        
        Args:
            timeout_seconds: Timeout in seconds
        """
        self._agent_termination_timeout = float(timeout_seconds)
        
    def set_resource_cleanup_timeout(self, timeout_seconds: float) -> None:
        """Set timeout for resource cleanup phase.
        
        Args:
            timeout_seconds: Timeout in seconds
        """
        self._resource_cleanup_timeout = float(timeout_seconds)

    # Access to component objects (for advanced configuration)
    def get_position_closer(self) -> PositionCloser:
        """Get the PositionCloser instance.
        
        Returns:
            PositionCloser: The position closer instance
        """
        return self._position_closer
        
    def get_agent_terminator(self) -> AgentTerminator:
        """Get the AgentTerminator instance.
        
        Returns:
            AgentTerminator: The agent terminator instance
        """
        return self._agent_terminator
        
    def get_resource_cleaner(self) -> ResourceCleaner:
        """Get the ResourceCleaner instance.
        
        Returns:
            ResourceCleaner: The resource cleaner instance
        """
        return self._resource_cleaner


# Singleton instance accessor
def get_shutdown_coordinator() -> ShutdownCoordinator:
    """Get the global ShutdownCoordinator instance.
    
    Returns:
        ShutdownCoordinator: The singleton instance
    """
    return ShutdownCoordinator()

# Signal handler setup
def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown on common termination signals."""
    import signal
    import threading
    
    def signal_handler(signum, frame):
        signal_name = signal.Signals(signum).name
        reason = f"Received signal {signal_name} ({signum})"
        logger.info(f"Signal handler: {reason}")
        
        # Create background task to initiate shutdown
        # (can't use asyncio directly in signal handler)
        coordinator = get_shutdown_coordinator()
        
        def start_shutdown():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(coordinator.shutdown(reason=reason))
            loop.close()
            
        # Start shutdown in separate thread
        threading.Thread(target=start_shutdown).start()
    
    # Register for common termination signals
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal_handler)
        
    logger.info("Signal handlers installed for graceful shutdown") 