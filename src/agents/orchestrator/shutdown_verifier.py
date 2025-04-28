"""
Shutdown Verifier for Orchestrator Shutdown

This module provides verification mechanisms to ensure components are properly
shut down during the orchestrator shutdown process.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from .orchestrator.shutdown_reporter import ShutdownReporter

# Configure logger
logger = logging.getLogger(__name__)

class VerificationStatus(Enum):
    """Status of verification checks."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


@dataclass
class VerificationCheck:
    """A verification check to be performed during shutdown."""
    check_id: str
    check_name: str
    verify_func: Callable
    is_async: bool
    description: str
    timeout: float
    required: bool = True
    dependencies: List[str] = field(default_factory=list)
    max_attempts: int = 1
    retry_delay: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: VerificationStatus = VerificationStatus.PENDING
    error_message: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    attempts: int = 0


class VerificationResult:
    """Result of a verification check."""
    
    def __init__(self, 
                name: str, 
                status: VerificationStatus, 
                details: Optional[str] = None, 
                duration: Optional[float] = None):
        """
        Initialize a verification result.
        
        Args:
            name: Name of the verification check
            status: Status of the verification check
            details: Additional details about the result
            duration: Duration of the verification check in seconds
        """
        self.name = name
        self.status = status
        self.details = details
        self.duration = duration
        self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the verification result to a dictionary.
        
        Returns:
            Dictionary representation of the verification result
        """
        return {
            "name": self.name,
            "status": self.status.value,
            "details": self.details,
            "duration": self.duration,
            "timestamp": self.timestamp
        }


class VerificationError(Exception):
    """Exception raised when a verification check fails."""
    pass


class ShutdownVerifier:
    """
    Verifies that the system has been properly shut down.
    
    Runs a series of validation checks to ensure all resources
    have been properly cleaned up, processes terminated, and
    the system is in a consistent state after shutdown.
    """
    
    def __init__(self, reporter: Optional[ShutdownReporter] = None):
        """
        Initialize the shutdown verifier.
        
        Args:
            reporter: Optional reporter to update with verification status
        """
        self._reporter = reporter
        self._verification_checks = {}  # name -> check_function
        self._check_results = {}  # name -> {status, details, duration}
        self._pending_checks = []  # list of check names not yet run
    
    def register_check(self, 
                      name: str, 
                      check_function: Callable[[], Union[bool, Dict[str, Any], Tuple[bool, str]]]) -> None:
        """
        Register a verification check.
        
        Args:
            name: Name of the check
            check_function: Function to run for verification
                The function can return:
                - A boolean (True if check passed, False if failed)
                - A tuple of (bool, str) with success status and details
                - A dict with keys 'success' and optionally 'details'
        """
        self._verification_checks[name] = check_function
        self._pending_checks.append(name)
        logger.debug(f"Registered verification check: {name}")
    
    def unregister_check(self, name: str) -> bool:
        """
        Unregister a verification check.
        
        Args:
            name: Name of the check to unregister
            
        Returns:
            True if the check was unregistered, False if it wasn't registered
        """
        if name in self._verification_checks:
            del self._verification_checks[name]
            if name in self._pending_checks:
                self._pending_checks.remove(name)
            if name in self._check_results:
                del self._check_results[name]
            logger.debug(f"Unregistered verification check: {name}")
            return True
        return False
    
    async def run_check(self, name: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Run a specific verification check.
        
        Args:
            name: Name of the check to run
            timeout: Maximum time (in seconds) to allow for the check
            
        Returns:
            Result of the check containing status, details, and duration
            
        Raises:
            KeyError: If the check isn't registered
            VerificationError: If the check fails
            asyncio.TimeoutError: If the check times out
        """
        if name not in self._verification_checks:
            raise KeyError(f"Verification check '{name}' is not registered")
        
        check_function = self._verification_checks[name]
        
        # Update reporter if available
        if self._reporter:
            await self._reporter.update_verification_status(name, "in_progress")
        
        start_time = time.time()
        details = None
        status = "failed"  # Default to failed, will update if successful
        
        try:
            # Run the check with timeout if specified
            if asyncio.iscoroutinefunction(check_function):
                # For async functions
                if timeout:
                    check_result = await asyncio.wait_for(check_function(), timeout=timeout)
                else:
                    check_result = await check_function()
            else:
                # For sync functions
                loop = asyncio.get_event_loop()
                if timeout:
                    check_result = await asyncio.wait_for(
                        loop.run_in_executor(None, check_function),
                        timeout=timeout
                    )
                else:
                    check_result = await loop.run_in_executor(None, check_function)
            
            # Process the result based on its type
            if isinstance(check_result, bool):
                success = check_result
                details = None
            elif isinstance(check_result, tuple) and len(check_result) == 2:
                success, details = check_result
            elif isinstance(check_result, dict):
                success = check_result.get('success', False)
                details = check_result.get('details')
            else:
                success = bool(check_result)
                details = None
            
            # Update status based on success
            status = "successful" if success else "failed"
            
            # If verification failed, raise an exception
            if not success:
                error_msg = f"Verification check '{name}' failed"
                if details:
                    error_msg += f": {details}"
                raise VerificationError(error_msg)
            
            # Update pending checks list
            if name in self._pending_checks:
                self._pending_checks.remove(name)
            
        except asyncio.TimeoutError:
            status = "timed_out"
            details = f"Check timed out after {timeout} seconds"
            raise
        except VerificationError:
            # Re-raise verification errors
            raise
        except Exception as e:
            status = "failed"
            details = f"Error during check: {str(e)}"
            logger.exception(f"Error in verification check '{name}'")
            raise VerificationError(f"Error in verification check '{name}': {str(e)}") from e
        finally:
            end_time = time.time()
            duration = end_time - start_time
            
            # Store the result
            self._check_results[name] = {
                "status": status,
                "details": details,
                "duration": duration
            }
            
            # Update reporter if available
            if self._reporter:
                await self._reporter.update_verification_status(
                    name,
                    status,
                    details=details,
                    duration=duration
                )
            
            logger.debug(f"Verification check '{name}': {status} ({duration:.2f}s)")
            if details:
                logger.debug(f"  Details: {details}")
        
        return self._check_results[name]
    
    async def run_all_checks(self, 
                           timeout_per_check: Optional[float] = None, 
                           fail_fast: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Run all registered verification checks.
        
        Args:
            timeout_per_check: Maximum time (in seconds) per check
            fail_fast: Whether to stop on first failure
            
        Returns:
            Dictionary of check results
        """
        logger.info(f"Running {len(self._verification_checks)} verification checks")
        
        # Reset pending checks list
        self._pending_checks = list(self._verification_checks.keys())
        
        for name in list(self._verification_checks.keys()):
            try:
                await self.run_check(name, timeout=timeout_per_check)
            except (VerificationError, asyncio.TimeoutError):
                if fail_fast:
                    logger.warning(f"Verification failed at check '{name}', stopping due to fail_fast")
                    break
            except Exception as e:
                logger.error(f"Unexpected error in verification check '{name}': {e}")
                if fail_fast:
                    break
        
        return self._check_results
    
    async def get_verification_summary(self) -> Dict[str, Any]:
        """
        Get a summary of verification results.
        
        Returns:
            Dictionary with verification summary information
        """
        # Count status occurrences
        status_counts = {}
        failed_checks = []
        total_duration = 0.0
        
        for name, result in self._check_results.items():
            status = result["status"]
            
            # Count statuses
            if status not in status_counts:
                status_counts[status] = 0
            status_counts[status] += 1
            
            # Track failed checks
            if status in ["failed", "timed_out"]:
                failed_checks.append({
                    "name": name,
                    "status": status,
                    "details": result["details"],
                    "duration": result["duration"]
                })
            
            # Sum up duration
            total_duration += result["duration"]
        
        # Check if all checks passed
        all_passed = (
            len(self._check_results) > 0 and
            len(self._check_results) == len(self._verification_checks) and
            len(failed_checks) == 0
        )
        
        summary = {
            "total_checks": len(self._verification_checks),
            "completed_checks": len(self._check_results),
            "pending_checks": len(self._pending_checks),
            "status_counts": status_counts,
            "all_passed": all_passed,
            "failed_checks": failed_checks,
            "total_duration": total_duration
        }
        
        # Update reporter if available
        if self._reporter:
            await self._reporter.update_verification_summary(summary)
        
        return summary
    
    def get_check_names(self) -> List[str]:
        """
        Get the names of all registered verification checks.
        
        Returns:
            List of check names
        """
        return list(self._verification_checks.keys())
    
    def get_pending_checks(self) -> List[str]:
        """
        Get the names of all pending verification checks.
        
        Returns:
            List of pending check names
        """
        return self._pending_checks.copy()
    
    def all_checks_passed(self) -> bool:
        """
        Check if all verification checks have passed.
        
        Returns:
            True if all checks have been run and passed, False otherwise
        """
        return (
            len(self._check_results) == len(self._verification_checks) and
            all(result["status"] == "successful" for result in self._check_results.values())
        )

    # Common verification functions
    
    @staticmethod
    async def verify_no_tasks(task_group) -> bool:
        """
        Verify that a task group has no running tasks.
        
        Args:
            task_group: Task group to verify
            
        Returns:
            True if no tasks are running, False otherwise
        """
        if hasattr(task_group, "get_tasks") and callable(task_group.get_tasks):
            tasks = await task_group.get_tasks()
            return len(tasks) == 0
        
        # For simpler task groups
        for task in getattr(task_group, "_tasks", []):
            if not task.done() and not task.cancelled():
                return False
        
        return True
    
    @staticmethod
    async def verify_no_connections(connection_manager) -> bool:
        """
        Verify that a connection manager has no active connections.
        
        Args:
            connection_manager: Connection manager to verify
            
        Returns:
            True if no connections are active, False otherwise
        """
        if hasattr(connection_manager, "get_active_connections") and callable(connection_manager.get_active_connections):
            connections = await connection_manager.get_active_connections()
            return len(connections) == 0
        
        # For simpler connection managers
        return len(getattr(connection_manager, "_connections", [])) == 0
    
    @staticmethod
    async def verify_agent_inactive(agent_metadata) -> bool:
        """
        Verify that an agent is inactive.
        
        Args:
            agent_metadata: Agent metadata to verify
            
        Returns:
            True if agent is stopped or failed, False otherwise
        """
        from src.agents.orchestrator.engine import AgentStatus
        
        # Check if agent is stopped or failed
        return agent_metadata.status in (AgentStatus.STOPPED, AgentStatus.FAILED) 