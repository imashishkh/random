"""
Shutdown Coordinator for Forex Trading Bot

This module provides a centralized mechanism for graceful shutdown of the trading system.
It coordinates the shutdown process across multiple components, ensuring that
resources are released in the correct order and that open positions are properly handled.
"""

import asyncio
import enum
import logging
import signal
import sys
import threading
import time
import traceback
from typing import Dict, List, Callable, Any, Optional, Union, Set, Tuple

# Configure logging
logger = logging.getLogger(__name__)


class ShutdownPhase(enum.Enum):
    """Phases of the shutdown process."""
    INITIALIZING = "initializing"
    PREPARATION = "preparation"    # Preparation phase (notify components)
    POSITIONS = "positions"        # Close positions phase
    AGENTS = "agents"              # Stop agent processes
    RESOURCES = "resources"        # Resource cleanup phase
    COMPLETE = "complete"          # Shutdown complete
    FAILED = "failed"              # Shutdown failed


class PositionCloseStrategy(enum.Enum):
    """
    Strategies for closing positions during shutdown.
    """
    GRADUAL = "gradual"      # Use limit orders close to market price
    IMMEDIATE = "immediate"  # Use market orders for immediate close


# Global singleton instance
_shutdown_coordinator: Optional['ShutdownCoordinator'] = None
_shutdown_coordinator_lock = threading.Lock()


def get_shutdown_coordinator() -> 'ShutdownCoordinator':
    """
    Get or create the global shutdown coordinator instance.
    
    Returns:
        The global ShutdownCoordinator instance
    """
    global _shutdown_coordinator
    
    if _shutdown_coordinator is None:
        with _shutdown_coordinator_lock:
            if _shutdown_coordinator is None:
                logger.debug("Creating new ShutdownCoordinator instance")
                _shutdown_coordinator = ShutdownCoordinator()
    
    return _shutdown_coordinator


def setup_signal_handlers(coordinator: Optional['ShutdownCoordinator'] = None) -> None:
    """
    Set up signal handlers for the shutdown coordinator.
    
    Args:
        coordinator: The shutdown coordinator to use, or None to use the global instance
    """
    if coordinator is None:
        coordinator = get_shutdown_coordinator()
    
    # Define signal handler
    def signal_handler(sig, frame):
        signal_name = {
            signal.SIGINT: "SIGINT",
            signal.SIGTERM: "SIGTERM"
        }.get(sig, f"Signal {sig}")
        
        logger.info(f"Received {signal_name}, initiating graceful shutdown")
        
        # Create a task in the event loop to initiate shutdown
        loop = asyncio.get_event_loop()
        
        # If we're already in an event loop, schedule the shutdown
        if loop.is_running():
            asyncio.create_task(coordinator.initiate_shutdown(
                reason=f"signal_{signal_name.lower()}"
            ))
        else:
            # Otherwise, try to run it directly
            try:
                loop.run_until_complete(coordinator.initiate_shutdown(
                    reason=f"signal_{signal_name.lower()}"
                ))
            except RuntimeError:
                # Handle case where there's no running event loop
                logger.warning(f"No running event loop to process {signal_name}, immediate exit")
                sys.exit(1)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal
    
    logger.debug("Signal handlers registered for graceful shutdown")


class ShutdownCoordinator:
    """
    Coordinates the graceful shutdown of the trading system.
    
    This class manages the shutdown process across different phases, ensuring that
    components are stopped in the correct order and that resources are properly released.
    """

    def __init__(self):
        """Initialize the shutdown coordinator."""
        # State tracking
        self._shutdown_in_progress = False
        self._shutdown_complete = asyncio.Event()
        self._shutdown_phase = ShutdownPhase.INITIALIZING
        self._shutdown_start_time = 0.0
        self._shutdown_reason = None
        self._position_close_strategy = PositionCloseStrategy.GRADUAL
        self._force_mode = False
        
        # Phase callbacks and timeouts
        self._phase_callbacks: Dict[ShutdownPhase, List[Callable]] = {
            phase: [] for phase in ShutdownPhase
        }
        self._phase_timeouts: Dict[ShutdownPhase, float] = {
            ShutdownPhase.INITIALIZING: 5.0,
            ShutdownPhase.PREPARATION: 5.0,
            ShutdownPhase.POSITIONS: 30.0,
            ShutdownPhase.AGENTS: 20.0,
            ShutdownPhase.RESOURCES: 10.0,
        }
        
        # Results tracking
        self._phase_results: Dict[ShutdownPhase, Dict[str, Any]] = {}
        
        logger.debug("ShutdownCoordinator initialized")
    
    #
    # Properties
    #
    
    @property
    def current_phase(self) -> ShutdownPhase:
        """Get the current shutdown phase."""
        return self._shutdown_phase
    
    @property
    def shutdown_time(self) -> float:
        """Get the time elapsed since shutdown started."""
        if not self._shutdown_start_time:
            return 0.0
        return time.time() - self._shutdown_start_time
    
    @property
    def is_shutdown_in_progress(self) -> bool:
        """Check if shutdown is in progress."""
        return self._shutdown_in_progress
    
    @property
    def position_close_strategy(self) -> PositionCloseStrategy:
        """Get the position closing strategy."""
        return self._position_close_strategy
    
    @property
    def force_mode(self) -> bool:
        """Check if force mode is enabled."""
        return self._force_mode
    
    #
    # Registration methods
    #
    
    def register_phase_callback(self, phase: ShutdownPhase, callback: Callable) -> None:
        """
        Register a callback to be called during a specific shutdown phase.
        
        Args:
            phase: The shutdown phase to register for
            callback: The callback function to call
        """
        if not callable(callback):
            raise ValueError(f"Callback must be callable, got {type(callback)}")
        
        self._phase_callbacks[phase].append(callback)
        logger.debug(f"Registered callback for phase {phase.value}")
    
    def set_phase_timeout(self, phase: ShutdownPhase, timeout: float) -> None:
        """
        Set a timeout for a specific shutdown phase.
        
        Args:
            phase: The shutdown phase
            timeout: The timeout in seconds
        """
        if timeout <= 0:
            raise ValueError(f"Timeout must be positive, got {timeout}")
        
        self._phase_timeouts[phase] = timeout
        logger.debug(f"Set timeout for phase {phase.value} to {timeout}s")
    
    #
    # Shutdown methods
    #
    
    async def initiate_shutdown(self, 
                               reason: str = "unspecified", 
                               force: bool = False,
                               position_strategy: Optional[PositionCloseStrategy] = None) -> None:
        """
        Initiate the shutdown process.
        
        Args:
            reason: The reason for shutdown
            force: Whether to force shutdown even if components fail
            position_strategy: Strategy for closing positions
        """
        # If shutdown already in progress, just wait for it
        if self._shutdown_in_progress:
            logger.warning(f"Shutdown already in progress, ignoring new request with reason: {reason}")
            return
        
        # Set shutdown state
        self._shutdown_in_progress = True
        self._shutdown_start_time = time.time()
        self._shutdown_reason = reason
        self._force_mode = force
        
        if position_strategy is not None:
            self._position_close_strategy = position_strategy
        
        logger.info(f"Initiating shutdown: reason='{reason}', "
                    f"force={force}, "
                    f"strategy={self._position_close_strategy.value}")
        
        # Start shutdown sequence
        try:
            # Execute preparation phase
            await self._execute_phase(ShutdownPhase.PREPARATION)
            
            # Execute position closing phase
            await self._execute_phase(ShutdownPhase.POSITIONS)
            
            # Execute agent termination phase
            await self._execute_phase(ShutdownPhase.AGENTS)
            
            # Execute resource cleanup phase
            await self._execute_phase(ShutdownPhase.RESOURCES)
            
            # Mark shutdown as complete
            self._set_phase(ShutdownPhase.COMPLETE)
            logger.info(f"Shutdown completed successfully in {self.shutdown_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Shutdown failed: {str(e)}", exc_info=True)
            self._set_phase(ShutdownPhase.FAILED)
            
            # Store the error
            self._phase_results[self._shutdown_phase] = {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }
        
        finally:
            # Signal that shutdown is complete
            self._shutdown_complete.set()
    
    async def wait_for_shutdown(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for shutdown to complete.
        
        Args:
            timeout: Maximum time to wait in seconds, or None to wait indefinitely
        
        Returns:
            True if shutdown is complete, False if timeout was reached
        """
        if not self._shutdown_in_progress:
            return False
        
        try:
            await asyncio.wait_for(self._shutdown_complete.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the shutdown process.
        
        Returns:
            Dict with status information
        """
        return {
            'in_progress': self._shutdown_in_progress,
            'phase': self._shutdown_phase.value if self._shutdown_phase else None,
            'elapsed_time': self.shutdown_time,
            'reason': self._shutdown_reason,
            'force': self._force_mode,
            'position_strategy': self._position_close_strategy.value if self._position_close_strategy else None,
            'phase_results': self._phase_results
        }
    
    #
    # Internal methods
    #
    
    def _set_phase(self, phase: ShutdownPhase) -> None:
        """
        Update the current shutdown phase.
        
        Args:
            phase: The new phase
        """
        logger.info(f"Shutdown phase: {phase.value}")
        self._shutdown_phase = phase
    
    async def _execute_phase(self, phase: ShutdownPhase) -> None:
        """
        Execute a specific shutdown phase.
        
        Args:
            phase: The phase to execute
        """
        # Set the current phase
        self._set_phase(phase)
        
        # Get callbacks for this phase
        callbacks = self._phase_callbacks.get(phase, [])
        
        if not callbacks:
            logger.debug(f"No callbacks registered for phase {phase.value}")
            self._phase_results[phase] = {'success': True, 'message': 'No callbacks registered'}
            return
        
        logger.debug(f"Executing {len(callbacks)} callbacks for phase {phase.value}")
        
        # Set up results tracking
        phase_success = True
        phase_errors = []
        
        # Execute each callback with timeout
        timeout = self._phase_timeouts.get(phase, 10.0)
        
        for i, callback in enumerate(callbacks):
            try:
                # Execute the callback with timeout
                logger.debug(f"Executing callback {i+1}/{len(callbacks)} for phase {phase.value}")
                await asyncio.wait_for(callback(), timeout)
                logger.debug(f"Callback {i+1}/{len(callbacks)} for phase {phase.value} completed")
                
            except asyncio.TimeoutError:
                error_msg = f"Callback {i+1} for phase {phase.value} timed out after {timeout}s"
                logger.error(error_msg)
                phase_errors.append(error_msg)
                phase_success = False
                
                # In non-force mode, this is a failure
                if not self._force_mode:
                    break
                
            except Exception as e:
                error_msg = f"Callback {i+1} for phase {phase.value} failed: {str(e)}"
                logger.error(error_msg, exc_info=True)
                phase_errors.append(error_msg)
                phase_success = False
                
                # In non-force mode, this is a failure
                if not self._force_mode:
                    break
        
        # Store phase results
        self._phase_results[phase] = {
            'success': phase_success,
            'errors': phase_errors if phase_errors else None
        }
        
        # If phase failed and not in force mode, raise exception
        if not phase_success and not self._force_mode:
            raise RuntimeError(f"Shutdown phase {phase.value} failed: {phase_errors[0]}")
        
        # If phase failed but in force mode, log warning and continue
        elif not phase_success:
            logger.warning(f"Shutdown phase {phase.value} had errors, but continuing in force mode") 