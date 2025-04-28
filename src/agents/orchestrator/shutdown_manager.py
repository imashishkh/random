"""
Orchestrator Shutdown Manager

This module provides a comprehensive manager for orchestrator shutdown,
coordinating state persistence, resource cleanup, verification, and reporting.
"""

import asyncio
import logging
import os
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from .resource_cleanup_registry import ResourceCleanupRegistry, CleanupStatus
from .shutdown_verifier import ShutdownVerifier
from .shutdown_reporter import ShutdownReporter, ShutdownStatus, PhaseStatus

# Configure logger
logger = logging.getLogger(__name__)

class ShutdownPhase(Enum):
    """Enum representing different phases of the orchestrator shutdown process"""
    
    STATE_PERSISTENCE = "state_persistence"
    AGENT_TERMINATION = "agent_termination"
    RESOURCE_CLEANUP = "resource_cleanup"
    VERIFICATION = "verification"
    REPORTING = "reporting"

class OrchestratorShutdownManager:
    """
    Manages the orchestrated shutdown process for AgentSwarmOrchestrator.
    
    This class handles the sequencing and execution of various shutdown phases,
    including state persistence, agent termination, resource cleanup, and verification.
    It coordinates between ResourceCleanupRegistry, ShutdownVerifier, and ShutdownReporter.
    """
    
    def __init__(self, 
                verbose: bool = False,
                report_dir: Optional[str] = None,
                state_dir: Optional[str] = None):
        """
        Initialize the orchestrator shutdown manager.
        
        Args:
            verbose: Whether to log detailed information during shutdown
            report_dir: Directory to save shutdown reports (None for no saving)
            state_dir: Directory to save state files (None for default location)
        """
        # Helper components
        self._cleanup_registry = ResourceCleanupRegistry()
        self._reporter = ShutdownReporter(verbose=verbose)
        self._verifier = ShutdownVerifier(reporter=self._reporter)
        
        # Connect the registry to the reporter
        # self._cleanup_registry.set_reporter(self._reporter)
        
        # State directory
        self._state_dir = state_dir or os.path.join(os.getcwd(), 'data', 'state')
        os.makedirs(self._state_dir, exist_ok=True)
        
        # Phase callbacks
        self._phase_callbacks: Dict[ShutdownPhase, List[Callable]] = {
            phase: [] for phase in ShutdownPhase
        }
        
        # Default timeouts for each phase
        self._phase_timeouts: Dict[ShutdownPhase, float] = {
            ShutdownPhase.STATE_PERSISTENCE: 10.0,
            ShutdownPhase.AGENT_TERMINATION: 30.0,
            ShutdownPhase.RESOURCE_CLEANUP: 20.0,
            ShutdownPhase.VERIFICATION: 15.0,
            ShutdownPhase.REPORTING: 5.0
        }
        
        # Shutdown state
        self._shutdown_in_progress = False
        self._current_phase: Optional[ShutdownPhase] = None
        self._shutdown_start_time = 0.0
        self._force_mode = False
        self._reason = "unknown"
        
        # Event for shutdown completion
        self._shutdown_complete = asyncio.Event()
        
        # Error tracking
        self._errors: List[Dict[str, Any]] = []
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        logger.debug("OrchestratorShutdownManager initialized")
    
    @property
    def cleanup_registry(self) -> ResourceCleanupRegistry:
        """Get the resource cleanup registry."""
        return self._cleanup_registry
    
    @property
    def verifier(self) -> ShutdownVerifier:
        """Get the shutdown verifier."""
        return self._verifier
    
    @property
    def reporter(self) -> ShutdownReporter:
        """Get the shutdown reporter."""
        return self._reporter
    
    @property
    def is_shutdown_in_progress(self) -> bool:
        """Check if shutdown is in progress."""
        return self._shutdown_in_progress
    
    @property
    def current_phase(self) -> Optional[ShutdownPhase]:
        """Get the current shutdown phase."""
        return self._current_phase
    
    @property
    def shutdown_time(self) -> float:
        """Get the time elapsed since shutdown started."""
        if not self._shutdown_start_time:
            return 0.0
        return time.time() - self._shutdown_start_time
    
    def register_phase_callback(self, 
                              phase: ShutdownPhase, 
                              callback: Callable) -> None:
        """
        Register a callback for a specific shutdown phase.
        
        Args:
            phase: The shutdown phase to register for
            callback: Callback function to be called during the phase
        """
        self._phase_callbacks[phase].append(callback)
        logger.debug(f"Registered callback for phase {phase.value}")
    
    def set_phase_timeout(self, phase: ShutdownPhase, timeout: float) -> None:
        """
        Set the timeout for a specific shutdown phase.
        
        Args:
            phase: The shutdown phase to set timeout for
            timeout: Timeout in seconds
        """
        self._phase_timeouts[phase] = max(1.0, timeout)
        logger.debug(f"Set {phase.value} phase timeout to {timeout}s")
    
    async def shutdown(self, 
                     reason: str = "requested",
                     force: bool = False,
                     timeout: Optional[float] = None) -> bool:
        """
        Execute the orchestrator shutdown process.
        
        Args:
            reason: Reason for shutdown
            force: If True, force shutdown even if phases fail
            timeout: Total timeout for shutdown (None for phase-specific timeouts)
            
        Returns:
            True if shutdown was successful, False otherwise
        """
        async with self._lock:
            if self._shutdown_in_progress:
                logger.warning("Shutdown already in progress")
                await self.wait_for_shutdown(timeout)
                return not self._force_mode
            
            # Initialize shutdown state
            self._shutdown_in_progress = True
            self._shutdown_start_time = time.time()
            self._force_mode = force
            self._reason = reason
            self._errors = []
            self._current_phase = None
            
            # Reset completion event
            self._shutdown_complete.clear()
        
        # Start shutdown in reporter
        await self._reporter.start_shutdown(message=reason)
        
        logger.info(
            f"Starting orchestrator shutdown: reason='{reason}', "
            f"force={force}, timeout={timeout or 'default'}"
        )
        
        # Execute shutdown phases
        success = await self._execute_shutdown_phases(timeout)
        
        # Complete shutdown in reporter
        status = ShutdownStatus.COMPLETED if success else ShutdownStatus.FAILED
        await self._reporter.end_shutdown(status, details=f"Shutdown {'succeeded' if success else 'failed'}")
        
        # Log final report
        await self._reporter.log_final_report()
        
        # Signal completion
        self._shutdown_complete.set()
        
        logger.info(
            f"Orchestrator shutdown complete: success={success}, "
            f"time={self.shutdown_time:.2f}s"
        )
        
        return success
    
    async def wait_for_shutdown(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for shutdown to complete.
        
        Args:
            timeout: Maximum time to wait in seconds, or None to wait indefinitely
            
        Returns:
            True if shutdown completed, False if timeout occurred
        """
        if not self._shutdown_in_progress:
            return True
        
        try:
            await asyncio.wait_for(self._shutdown_complete.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False
    
    async def _execute_shutdown_phases(self, total_timeout: Optional[float] = None) -> bool:
        """
        Execute all shutdown phases in sequence.
        
        Args:
            total_timeout: Maximum time for all phases combined
            
        Returns:
            True if all phases completed successfully, False otherwise
        """
        # Track overall success
        all_phases_successful = True
        start_time = time.time()
        
        # Calculate time remaining if total_timeout is set
        time_remaining = lambda: (
            total_timeout - (time.time() - start_time) 
            if total_timeout is not None else None
        )
        
        # Execute each phase in sequence
        for phase in ShutdownPhase:
            # Skip if out of time
            if total_timeout is not None and time_remaining() <= 0:
                logger.warning(f"Total shutdown timeout reached, skipping remaining phases")
                all_phases_successful = False
                break
            
            # Set current phase
            self._current_phase = phase
            
            # Start phase in reporter
            await self._reporter.start_phase(phase.value, 
                                          details=f"Starting {phase.value} phase of shutdown")
            
            # Calculate phase timeout
            phase_timeout = min(
                time_remaining() or float('inf'),
                self._phase_timeouts[phase]
            )
            
            # Execute phase
            phase_status = PhaseStatus.COMPLETED
            phase_details = None
            try:
                phase_success = await self._execute_phase(phase, phase_timeout)
                
                if not phase_success:
                    logger.warning(f"Phase {phase.value} failed or timed out")
                    phase_status = PhaseStatus.FAILED
                    phase_details = f"Phase {phase.value} failed or timed out"
                    
                    all_phases_successful = False
                    
                    # Break if forced mode off and critical phase failed
                    critical_phases = {
                        ShutdownPhase.STATE_PERSISTENCE,
                        ShutdownPhase.AGENT_TERMINATION
                    }
                    if not self._force_mode and phase in critical_phases:
                        logger.error(
                            f"Critical phase {phase.value} failed, aborting shutdown"
                        )
                        break
            except asyncio.TimeoutError:
                logger.error(f"Phase {phase.value} timed out after {phase_timeout}s")
                phase_status = PhaseStatus.TIMED_OUT
                phase_details = f"Phase timed out after {phase_timeout}s"
                all_phases_successful = False
                
                if not self._force_mode:
                    break
            except Exception as e:
                logger.error(f"Error in shutdown phase {phase.value}: {str(e)}", exc_info=True)
                phase_status = PhaseStatus.FAILED
                phase_details = f"Error: {str(e)}"
                
                all_phases_successful = False
                
                # Break if forced mode off
                if not self._force_mode:
                    break
            finally:
                # End phase in reporter
                await self._reporter.end_phase(phase.value, phase_status, details=phase_details)
        
        # Clear current phase
        self._current_phase = None
        
        return all_phases_successful
    
    async def _execute_phase(self, phase: ShutdownPhase, timeout: float) -> bool:
        """
        Execute a specific shutdown phase.
        
        Args:
            phase: The phase to execute
            timeout: Maximum time to spend on this phase
            
        Returns:
            True if phase completed successfully, False otherwise
        """
        logger.info(f"Executing shutdown phase: {phase.value} (timeout: {timeout:.1f}s)")
        
        if phase == ShutdownPhase.STATE_PERSISTENCE:
            return await self._execute_state_persistence_phase(timeout)
        elif phase == ShutdownPhase.AGENT_TERMINATION:
            return await self._execute_agent_termination_phase(timeout)
        elif phase == ShutdownPhase.RESOURCE_CLEANUP:
            return await self._execute_resource_cleanup_phase(timeout)
        elif phase == ShutdownPhase.VERIFICATION:
            return await self._execute_verification_phase(timeout)
        elif phase == ShutdownPhase.REPORTING:
            return await self._execute_reporting_phase(timeout)
        else:
            logger.warning(f"Unknown phase: {phase.value}")
            return False
    
    async def _execute_state_persistence_phase(self, timeout: float) -> bool:
        """
        Execute the state persistence phase.
        
        Args:
            timeout: Maximum time for this phase
            
        Returns:
            True if successful, False otherwise
        """
        logger.info("Executing state persistence phase")
        
        # Get callbacks for this phase
        callbacks = self._phase_callbacks.get(ShutdownPhase.STATE_PERSISTENCE, [])
        
        # No callbacks means nothing to do in this phase
        if not callbacks:
            logger.debug("No callbacks registered for state persistence phase")
            return True
        
        # Execute callbacks with timeout
        return await self._execute_phase_callbacks(callbacks, timeout)
    
    async def _execute_agent_termination_phase(self, timeout: float) -> bool:
        """
        Execute the agent termination phase.
        
        Args:
            timeout: Maximum time for this phase
            
        Returns:
            True if successful, False otherwise
        """
        logger.info("Executing agent termination phase")
        
        # Get callbacks for this phase
        callbacks = self._phase_callbacks.get(ShutdownPhase.AGENT_TERMINATION, [])
        
        # No callbacks means nothing to do in this phase
        if not callbacks:
            logger.debug("No callbacks registered for agent termination phase")
            return True
        
        # Execute callbacks with timeout
        return await self._execute_phase_callbacks(callbacks, timeout)
    
    async def _execute_resource_cleanup_phase(self, timeout: float) -> bool:
        """
        Execute the resource cleanup phase.
        
        Args:
            timeout: Maximum time for this phase
            
        Returns:
            True if successful, False otherwise
        """
        logger.info("Executing resource cleanup phase")
        
        # Execute custom callbacks first
        callbacks = self._phase_callbacks.get(ShutdownPhase.RESOURCE_CLEANUP, [])
        if callbacks:
            success = await self._execute_phase_callbacks(callbacks, timeout * 0.3)
            if not success and not self._force_mode:
                return False
        
        # Calculate remaining time
        remaining_time = max(0.1, timeout - (callbacks and timeout * 0.3 or 0))
        
        # Clean up resources using the registry
        try:
            cleanup_results = await self._cleanup_registry.cleanup_all_resources()
            cleanup_summary = await self._cleanup_registry.get_cleanup_summary()
            
            # Update the reporter with cleanup results
            await self._reporter.update_cleanup_summary(cleanup_summary)
            
            # Check for failures
            if not cleanup_summary.get('all_successful', False) and not self._force_mode:
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error during resource cleanup: {str(e)}", exc_info=True)
            return False
    
    async def _execute_verification_phase(self, timeout: float) -> bool:
        """
        Execute the verification phase.
        
        Args:
            timeout: Maximum time for this phase
            
        Returns:
            True if successful, False otherwise
        """
        logger.info("Executing verification phase")
        
        # Execute custom callbacks first
        callbacks = self._phase_callbacks.get(ShutdownPhase.VERIFICATION, [])
        if callbacks:
            success = await self._execute_phase_callbacks(callbacks, timeout * 0.3)
            if not success and not self._force_mode:
                return False
        
        # Calculate remaining time
        remaining_time = max(0.1, timeout - (callbacks and timeout * 0.3 or 0))
        
        # Run verification checks
        try:
            await self._verifier.run_all_checks(
                timeout_per_check=min(remaining_time / 10, 5.0),
                fail_fast=not self._force_mode
            )
            
            verification_summary = await self._verifier.get_verification_summary()
            
            # Check for failures
            all_passed = verification_summary.get('all_passed', False)
            return all_passed or self._force_mode
        except Exception as e:
            logger.error(f"Error during verification: {str(e)}", exc_info=True)
            return False
    
    async def _execute_reporting_phase(self, timeout: float) -> bool:
        """
        Execute the reporting phase.
        
        Args:
            timeout: Maximum time for this phase
            
        Returns:
            True if successful, False otherwise
        """
        logger.info("Executing reporting phase")
        
        # Get shutdown status from reporter
        try:
            status = await self._reporter.get_shutdown_status()
            logger.debug(f"Shutdown status: {status['status']}")
            
            # Execute custom callbacks
            callbacks = self._phase_callbacks.get(ShutdownPhase.REPORTING, [])
            if callbacks:
                await self._execute_phase_callbacks(callbacks, timeout)
            
            return True
        except Exception as e:
            logger.error(f"Error during reporting phase: {str(e)}", exc_info=True)
            return False
    
    async def _execute_phase_callbacks(self, 
                                     callbacks: List[Callable], 
                                     timeout: float) -> bool:
        """
        Execute a list of callbacks with timeout.
        
        Args:
            callbacks: List of callback functions
            timeout: Maximum time for all callbacks
            
        Returns:
            True if all callbacks succeeded, False otherwise
        """
        # Create tasks for all callbacks
        tasks = []
        for i, callback in enumerate(callbacks):
            if asyncio.iscoroutinefunction(callback):
                # Async function
                task = asyncio.create_task(self._safely_execute_callback(callback))
            else:
                # Sync function
                loop = asyncio.get_event_loop()
                task = asyncio.create_task(
                    self._safely_execute_callback(
                        lambda cb=callback: loop.run_in_executor(None, cb)
                    )
                )
            
            tasks.append(task)
        
        # Wait for all tasks with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            
            # Process results
            success_count = 0
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Callback failed: {str(result)}")
                elif result is False:
                    logger.warning("Callback returned False")
                else:
                    success_count += 1
            
            success = success_count == len(callbacks)
            logger.info(
                f"Completed {success_count}/{len(callbacks)} "
                f"successful callbacks"
            )
            
            return success
            
        except asyncio.TimeoutError:
            # Cancel pending tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            
            logger.warning(f"Callbacks timed out after {timeout:.1f}s")
            
            # Wait for cancellations to complete
            try:
                await asyncio.wait(tasks, timeout=1.0)
            except Exception:
                pass
            
            return False
    
    async def _safely_execute_callback(self, callback: Callable) -> bool:
        """
        Safely execute a callback function with error handling.
        
        Args:
            callback: The callback to execute
            
        Returns:
            Result of the callback (True for success)
        """
        try:
            # Execute callback
            result = await callback()
            
            # Handle different return types
            if result is None:
                # Treat None as success
                return True
            elif isinstance(result, bool):
                return result
            elif isinstance(result, dict) and "success" in result:
                return result["success"]
            else:
                # Any other return value is assumed to be success
                return True
                
        except Exception as e:
            logger.error(
                f"Error executing callback: {str(e)}",
                exc_info=True
            )
            return False
    
    # Convenience methods for registering resources and verification checks
    
    def register_resource(self, 
                         resource_id: str,
                         resource_type: str,
                         cleanup_func: Callable,
                         is_async: bool = False,
                         timeout: float = 30.0,
                         description: Optional[str] = None) -> None:
        """
        Register a resource for cleanup.
        
        Args:
            resource_id: Unique identifier for the resource
            resource_type: Type of resource
            cleanup_func: Function to call for cleanup
            is_async: Whether the cleanup function is asynchronous
            timeout: Maximum time to wait for cleanup
            description: Description of the resource
        """
        asyncio.create_task(
            self._cleanup_registry.register_resource(
                resource_id=resource_id,
                resource_type=resource_type,
                cleanup_func=cleanup_func,
                is_async=is_async,
                timeout=timeout,
                description=description or f"Resource {resource_id} ({resource_type})"
            )
        )
    
    def register_verification_check(self, 
                                  name: str, 
                                  check_function: Callable) -> None:
        """
        Register a verification check.
        
        Args:
            name: Name of the verification check
            check_function: Function to run for verification
        """
        self._verifier.register_check(name, check_function)

    def get_cleanup_registry(self) -> ResourceCleanupRegistry:
        """
        Get the resource cleanup registry.
        
        Returns:
            The resource cleanup registry
        """
        return self._cleanup_registry
    
    def get_verifier(self) -> ShutdownVerifier:
        """
        Get the shutdown verifier.
        
        Returns:
            The shutdown verifier
        """
        return self._verifier
    
    def get_reporter(self) -> ShutdownReporter:
        """
        Get the shutdown reporter.
        
        Returns:
            The shutdown reporter
        """
        return self._reporter 