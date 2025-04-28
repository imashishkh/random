"""
Dependency checking system core interfaces.

This module provides the foundational classes for the dependency checking system:
- CheckStatus: Status enum for dependency check results
- CheckResult: Immutable result object for check outcomes
- DependencyCheck: Abstract base class for all specific check implementations
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Dict, Any, Union
import asyncio
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class CheckStatus(Enum):
    """Status for dependency check results."""
    SUCCESS = auto()
    WARNING = auto()
    FAILURE = auto()


@dataclass(frozen=True)
class CheckResult:
    """Immutable result of a dependency check."""
    name: str
    status: CheckStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    
    @property
    def is_successful(self) -> bool:
        """Check if the result indicates success."""
        return self.status == CheckStatus.SUCCESS
    
    @property
    def is_warning(self) -> bool:
        """Check if the result indicates a warning."""
        return self.status == CheckStatus.WARNING
    
    @property
    def is_failure(self) -> bool:
        """Check if the result indicates a failure."""
        return self.status == CheckStatus.FAILURE


class DependencyCheck(ABC):
    """
    Abstract base class for all dependency checks.
    
    Concrete implementations should override _execute_check to implement
    the specific check logic. The execute and execute_async methods handle
    retry logic and exception handling.
    """
    def __init__(
        self,
        name: str,
        description: str = "",
        dependencies: List[str] = None,
        retry_attempts: int = 3,
        retry_backoff: float = 2.0
    ):
        """
        Initialize a dependency check.
        
        Args:
            name: Unique identifier for the check
            description: Human-readable description of the check
            dependencies: List of other check names that must succeed before this check
            retry_attempts: Number of times to retry the check on failure
            retry_backoff: Maximum backoff multiplier for retries (in seconds)
        """
        self.name = name
        self.description = description
        self.dependencies = dependencies or []
        self.retry_attempts = retry_attempts
        self.retry_backoff = retry_backoff
    
    @abstractmethod
    def _execute_check(self) -> CheckResult:
        """
        Implement the actual check logic in subclasses.
        
        Returns:
            CheckResult with the outcome of the check
        """
        pass
    
    def execute(self) -> CheckResult:
        """
        Execute the check with retry logic.
        
        This method handles the retry logic and exception handling.
        
        Returns:
            CheckResult with the outcome of the check
        """
        @retry(
            stop=stop_after_attempt(self.retry_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=self.retry_backoff),
            reraise=True,
            before_sleep=lambda retry_state: logger.debug(
                f"Retrying {self.name} (attempt {retry_state.attempt_number}/{self.retry_attempts})"
            )
        )
        def _do_check():
            return self._execute_check()
        
        try:
            logger.debug(f"Executing check: {self.name}")
            return _do_check()
        except Exception as e:
            logger.exception(f"Check {self.name} failed with exception")
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message=f"Check failed after {self.retry_attempts} attempts: {str(e)}",
                details={"exception": str(e), "type": type(e).__name__}
            )
    
    async def execute_async(self) -> CheckResult:
        """
        Async version of execute for async-compatible checks.
        
        By default, this runs the synchronous check in a thread pool,
        but subclasses can override for native async implementations.
        
        Returns:
            CheckResult with the outcome of the check
        """
        try:
            # Default implementation runs synchronous check in a thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.execute)
        except Exception as e:
            logger.exception(f"Async check {self.name} failed with exception")
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAILURE,
                message=f"Async check failed: {str(e)}",
                details={"exception": str(e), "type": type(e).__name__}
            ) 