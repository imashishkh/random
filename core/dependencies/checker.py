"""
Dependency Checker Module

This module provides functionality for checking and managing dependencies
in the forex trading system. It allows for dependency resolution and running
checks in the correct order based on their dependencies.
"""

import asyncio
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass

class CheckStatus(Enum):
    """Enum representing the status of a dependency check."""
    SUCCESS = auto()
    WARNING = auto()
    FAILURE = auto()
    SKIPPED = auto()


@dataclass
class CheckResult:
    """Result of a dependency check."""
    status: CheckStatus
    message: str = ""
    details: Optional[Dict[str, Any]] = None
    
    @property
    def is_successful(self) -> bool:
        """Return True if the check is successful."""
        return self.status == CheckStatus.SUCCESS


class DependencyCheck:
    """Base class for dependency checks."""
    
    def __init__(self, check_id: str, dependencies: List[str] = None):
        """
        Initialize a dependency check.
        
        Args:
            check_id: Unique identifier for this check
            dependencies: List of check IDs that this check depends on
        """
        self.check_id = check_id
        self.dependencies = dependencies or []
    
    def run(self) -> CheckResult:
        """
        Run the dependency check.
        
        Returns:
            CheckResult: Result of the check
        """
        raise NotImplementedError("Subclasses must implement run()")
    
    async def run_async(self) -> CheckResult:
        """
        Run the dependency check asynchronously.
        
        Returns:
            CheckResult: Result of the check
        """
        # Default implementation calls the synchronous run method
        return self.run()


class DependencyChecker:
    """
    Class responsible for managing and running dependency checks.
    Ensures checks are run in the correct order based on their dependencies.
    """
    
    def __init__(self):
        """Initialize the dependency checker."""
        self._checks: Dict[str, DependencyCheck] = {}
    
    def register_check(self, check: DependencyCheck) -> None:
        """
        Register a dependency check.
        
        Args:
            check: The check to register
        """
        self._checks[check.check_id] = check
    
    def resolve_dependencies(self) -> List[DependencyCheck]:
        """
        Resolve dependencies between checks and return them in the correct order.
        
        Returns:
            List of checks in dependency order
        """
        # Topological sort to resolve dependencies
        visited: Set[str] = set()
        temp_marked: Set[str] = set()
        ordered: List[DependencyCheck] = []
        
        def visit(check_id: str):
            if check_id in temp_marked:
                # We have a circular dependency
                raise ValueError(f"Circular dependency detected involving {check_id}")
            
            if check_id not in visited and check_id in self._checks:
                temp_marked.add(check_id)
                check = self._checks[check_id]
                
                # Visit dependencies first
                for dep_id in check.dependencies:
                    if dep_id in self._checks:
                        visit(dep_id)
                
                temp_marked.remove(check_id)
                visited.add(check_id)
                ordered.append(check)
        
        # Visit all nodes
        for check_id in list(self._checks.keys()):
            if check_id not in visited:
                visit(check_id)
        
        return ordered
    
    def run_checks(self) -> Dict[str, CheckResult]:
        """
        Run all dependency checks in the correct order.
        
        Returns:
            Dict mapping check IDs to their results
        """
        ordered_checks = self.resolve_dependencies()
        results: Dict[str, CheckResult] = {}
        
        for check in ordered_checks:
            # Skip checks with failed dependencies
            skip = False
            for dep_id in check.dependencies:
                if dep_id in results and results[dep_id].status == CheckStatus.FAILURE:
                    results[check.check_id] = CheckResult(
                        CheckStatus.SKIPPED,
                        f"Skipped because dependency {dep_id} failed"
                    )
                    skip = True
                    break
            
            if not skip:
                results[check.check_id] = check.run()
        
        return results
    
    async def run_checks_async(self, parallelize: bool = True) -> Dict[str, CheckResult]:
        """
        Run all dependency checks asynchronously.
        
        Args:
            parallelize: If True, run checks with satisfied dependencies in parallel
            
        Returns:
            Dict mapping check IDs to their results
        """
        ordered_checks = self.resolve_dependencies()
        results: Dict[str, CheckResult] = {}
        
        if not parallelize:
            # Sequential execution
            for check in ordered_checks:
                # Skip checks with failed dependencies
                skip = False
                for dep_id in check.dependencies:
                    if dep_id in results and results[dep_id].status == CheckStatus.FAILURE:
                        results[check.check_id] = CheckResult(
                            CheckStatus.SKIPPED,
                            f"Skipped because dependency {dep_id} failed"
                        )
                        skip = True
                        break
                
                if not skip:
                    results[check.check_id] = await check.run_async()
        else:
            # Parallel execution where possible
            # Track which checks have been processed
            processed: Set[str] = set()
            
            while len(processed) < len(ordered_checks):
                # Find checks whose dependencies are all processed
                ready_checks = []
                for check in ordered_checks:
                    if check.check_id in processed:
                        continue
                    
                    deps_satisfied = True
                    skip = False
                    
                    for dep_id in check.dependencies:
                        if dep_id not in processed:
                            deps_satisfied = False
                            break
                        if dep_id in results and results[dep_id].status == CheckStatus.FAILURE:
                            results[check.check_id] = CheckResult(
                                CheckStatus.SKIPPED,
                                f"Skipped because dependency {dep_id} failed"
                            )
                            skip = True
                            break
                    
                    if deps_satisfied and not skip:
                        ready_checks.append(check)
                    elif skip:
                        processed.add(check.check_id)
                
                if not ready_checks:
                    raise ValueError("Dependency resolution error - no progress made in an iteration")
                
                # Run all ready checks in parallel
                tasks = [check.run_async() for check in ready_checks]
                check_results = await asyncio.gather(*tasks)
                
                # Store results
                for check, result in zip(ready_checks, check_results):
                    results[check.check_id] = result
                    processed.add(check.check_id)
        
        return results 