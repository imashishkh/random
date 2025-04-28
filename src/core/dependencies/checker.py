"""
Dependency checker orchestrator.

This module provides the main DependencyChecker class that:
- Manages the registration of individual checks
- Resolves dependencies using a directed acyclic graph
- Executes checks in the correct order
- Provides reporting and visualization of results
"""
import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List, Set, Optional, Union, Callable, Any
import logging
import networkx as nx
from rich.console import Console
from rich.progress import Progress, TaskID
from rich.table import Table
from rich.panel import Panel

from .base import DependencyCheck, CheckResult, CheckStatus

logger = logging.getLogger(__name__)


@dataclass
class CheckSummary:
    """Summary of dependency check results."""
    total: int
    successful: int
    warnings: int
    failures: int
    duration: float
    
    @property
    def success_rate(self) -> float:
        """Calculate the percentage of successful checks."""
        return self.successful / self.total if self.total > 0 else 0.0


class DependencyChecker:
    """
    Main orchestrator for dependency checks.
    
    This class manages the registration, ordering, and execution of
    dependency checks. It uses a directed acyclic graph (DAG) to 
    represent and resolve dependencies between checks.
    """
    def __init__(self, config: dict = None):
        """
        Initialize a dependency checker.
        
        Args:
            config: Optional configuration dictionary
        """
        self.checks: Dict[str, DependencyCheck] = {}
        self.results: Dict[str, CheckResult] = {}
        self.config = config or {}
        self.console = Console()
        self._dependency_graph = nx.DiGraph()
    
    def register_check(self, check: DependencyCheck) -> None:
        """
        Register a new dependency check.
        
        Args:
            check: The dependency check to register
            
        Raises:
            ValueError: If a check with the same name is already registered
                        or if a dependency doesn't exist
        """
        if check.name in self.checks:
            raise ValueError(f"Check with name '{check.name}' already registered")
        
        self.checks[check.name] = check
        self._dependency_graph.add_node(check.name)
        
        # Add dependency edges to the graph
        for dep in check.dependencies:
            if dep not in self.checks:
                raise ValueError(f"Dependency '{dep}' not found for check '{check.name}'")
            self._dependency_graph.add_edge(dep, check.name)
    
    def validate_graph(self) -> bool:
        """
        Validate the dependency graph is a DAG with no cycles.
        
        Returns:
            True if the graph is valid, False otherwise
        """
        try:
            cycles = list(nx.simple_cycles(self._dependency_graph))
            if cycles:
                cycle_str = ", ".join([" -> ".join(cycle) for cycle in cycles])
                logger.error(f"Dependency cycle detected: {cycle_str}")
                self.console.print(f"[red]Dependency cycle detected: {cycle_str}[/red]")
                return False
            return True
        except nx.NetworkXNoCycle:
            return True
    
    def get_execution_order(self) -> List[str]:
        """
        Get the topologically sorted execution order of checks.
        
        Returns:
            List of check names in dependency order
            
        Raises:
            ValueError: If the dependency graph has cycles
        """
        if not self.validate_graph():
            raise ValueError("Cannot determine execution order with cyclic dependencies")
        
        try:
            # Get topological sort (dependencies first)
            return list(nx.topological_sort(self._dependency_graph))
        except nx.NetworkXUnfeasible:
            raise ValueError("Dependency graph has cycles, cannot determine execution order")
    
    def run_checks(self, verbose: bool = False) -> CheckSummary:
        """
        Run all dependency checks in the correct order.
        
        Args:
            verbose: Whether to print detailed progress information
            
        Returns:
            Summary of check results
        """
        if not self.checks:
            logger.warning("No dependency checks registered")
            self.console.print("[yellow]Warning: No dependency checks registered[/yellow]")
            return CheckSummary(0, 0, 0, 0, 0.0)
        
        start_time = time.time()
        execution_order = self.get_execution_order()
        
        with Progress() as progress:
            task = progress.add_task("[green]Running dependency checks...", total=len(execution_order))
            
            for check_name in execution_order:
                check = self.checks[check_name]
                
                # Skip checks whose dependencies failed
                dependencies_ok = True
                for dep in check.dependencies:
                    if dep in self.results and self.results[dep].is_failure:
                        dependencies_ok = False
                        self.results[check_name] = CheckResult(
                            name=check_name,
                            status=CheckStatus.FAILURE,
                            message=f"Skipped due to failed dependency: {dep}",
                            details={"failed_dependency": dep}
                        )
                        break
                
                if dependencies_ok:
                    if verbose:
                        self.console.print(f"Running check: [blue]{check_name}[/blue]")
                    result = check.execute()
                    self.results[check_name] = result
                    
                    if result.is_failure and verbose:
                        self.console.print(f"[red]✗ {check_name}: {result.message}[/red]")
                    elif result.is_warning and verbose:
                        self.console.print(f"[yellow]⚠ {check_name}: {result.message}[/yellow]")
                    elif verbose:
                        self.console.print(f"[green]✓ {check_name}[/green]")
                
                progress.update(task, advance=1)
        
        # Calculate summary
        duration = time.time() - start_time
        successful = sum(1 for r in self.results.values() if r.is_successful)
        warnings = sum(1 for r in self.results.values() if r.is_warning)
        failures = sum(1 for r in self.results.values() if r.is_failure)
        
        return CheckSummary(
            total=len(self.results),
            successful=successful,
            warnings=warnings,
            failures=failures,
            duration=duration
        )
    
    async def run_checks_async(self, verbose: bool = False) -> CheckSummary:
        """
        Run checks asynchronously where possible.
        
        This method groups checks by dependency level and executes
        independent checks in parallel for better performance.
        
        Args:
            verbose: Whether to print detailed progress information
            
        Returns:
            Summary of check results
        """
        if not self.checks:
            logger.warning("No dependency checks registered")
            self.console.print("[yellow]Warning: No dependency checks registered[/yellow]")
            return CheckSummary(0, 0, 0, 0, 0.0)
        
        start_time = time.time()
        execution_order = self.get_execution_order()
        
        # Group checks by their dependency level for parallel execution
        levels: Dict[int, List[str]] = {}
        for node in execution_order:
            # Calculate node's level (longest path from any root)
            # For nodes with no incoming edges, this will be 0
            incoming_paths = dict(nx.shortest_path_length(self._dependency_graph.reverse(), target=node))
            level = max(incoming_paths.values()) if incoming_paths else 0
            if level not in levels:
                levels[level] = []
            levels[level].append(node)
        
        with Progress() as progress:
            task = progress.add_task("[green]Running dependency checks...", total=len(execution_order))
            
            # Process each level in order, but checks within a level in parallel
            for level in sorted(levels.keys()):
                if verbose:
                    self.console.print(f"Running level {level} checks...")
                
                checks_at_level = levels[level]
                
                # Filter out checks with failed dependencies
                valid_checks = []
                for check_name in checks_at_level:
                    dependencies_ok = True
                    for dep in self.checks[check_name].dependencies:
                        if dep in self.results and self.results[dep].is_failure:
                            dependencies_ok = False
                            self.results[check_name] = CheckResult(
                                name=check_name,
                                status=CheckStatus.FAILURE,
                                message=f"Skipped due to failed dependency: {dep}",
                                details={"failed_dependency": dep}
                            )
                            progress.update(task, advance=1)
                            if verbose:
                                self.console.print(f"[red]✗ {check_name}: Skipped due to failed dependency: {dep}[/red]")
                            break
                    
                    if dependencies_ok:
                        valid_checks.append(check_name)
                
                # Run valid checks in parallel
                if valid_checks:
                    if verbose:
                        self.console.print(f"Running {len(valid_checks)} checks in parallel")
                    
                    tasks = [self.checks[name].execute_async() for name in valid_checks]
                    results = await asyncio.gather(*tasks)
                    
                    for name, result in zip(valid_checks, results):
                        self.results[name] = result
                        
                        if verbose:
                            if result.is_failure:
                                self.console.print(f"[red]✗ {name}: {result.message}[/red]")
                            elif result.is_warning:
                                self.console.print(f"[yellow]⚠ {name}: {result.message}[/yellow]")
                            else:
                                self.console.print(f"[green]✓ {name}[/green]")
                        
                        progress.update(task, advance=1)
        
        # Calculate summary
        duration = time.time() - start_time
        successful = sum(1 for r in self.results.values() if r.is_successful)
        warnings = sum(1 for r in self.results.values() if r.is_warning)
        failures = sum(1 for r in self.results.values() if r.is_failure)
        
        logger.info(f"Dependency checks completed in {duration:.2f}s: "
                  f"{successful}/{len(self.results)} passed, "
                  f"{warnings} warnings, {failures} failures")
        
        return CheckSummary(
            total=len(self.results),
            successful=successful,
            warnings=warnings,
            failures=failures,
            duration=duration
        )
    
    def print_report(self) -> None:
        """
        Print a detailed report of all check results.
        
        This method uses rich tables and panels for a visually appealing report.
        """
        self.console.print("\n[bold]Dependency Check Report[/bold]")
        
        if not self.results:
            self.console.print("[yellow]No checks were executed[/yellow]")
            return
        
        # Create summary table
        summary = Table(title="Dependency Check Summary")
        summary.add_column("Status", style="bold")
        summary.add_column("Count")
        summary.add_column("Percentage", style="dim")
        
        successful = sum(1 for r in self.results.values() if r.is_successful)
        warnings = sum(1 for r in self.results.values() if r.is_warning)
        failures = sum(1 for r in self.results.values() if r.is_failure)
        total = len(self.results)
        
        success_rate = successful / total if total > 0 else 0
        warning_rate = warnings / total if total > 0 else 0
        failure_rate = failures / total if total > 0 else 0
        
        summary.add_row("✅ SUCCESS", str(successful), f"{success_rate:.1%}")
        summary.add_row("⚠️ WARNING", str(warnings), f"{warning_rate:.1%}")
        summary.add_row("❌ FAILURE", str(failures), f"{failure_rate:.1%}")
        summary.add_row("TOTAL", str(total), "100%")
        
        self.console.print(summary)
        
        # Print successful checks if any
        successful_checks = [r for r in self.results.values() if r.is_successful]
        if successful_checks:
            self.console.print(f"\n[green]Successful Checks ({len(successful_checks)})[/green]")
            for result in successful_checks:
                self.console.print(f"[green]✓ {result.name}[/green]: {result.message}")
        
        # Print warnings if any
        warnings = [r for r in self.results.values() if r.is_warning]
        if warnings:
            self.console.print(f"\n[yellow]Warnings ({len(warnings)})[/yellow]")
            for result in warnings:
                self.console.print(f"[yellow]⚠ {result.name}[/yellow]: {result.message}")
                if result.details:
                    for key, value in result.details.items():
                        self.console.print(f"  - {key}: {value}")
        
        # Print failures in detail
        failures = [r for r in self.results.values() if r.is_failure]
        if failures:
            self.console.print(f"\n[red]Failures ({len(failures)})[/red]")
            for result in failures:
                self.console.print(f"[red]✗ {result.name}[/red]: {result.message}")
                if result.details:
                    for key, value in result.details.items():
                        self.console.print(f"  - {key}: {value}")
        
        # Print dependency graph information if verbose
        self.console.print(f"\n[bold]Dependency Structure:[/bold] {len(self._dependency_graph.edges)} dependencies between {len(self._dependency_graph.nodes)} checks")
        
        # Print execution time if available
        successful_result = CheckSummary(
            total=total,
            successful=successful,
            warnings=warnings,
            failures=failures,
            duration=0.0
        )
        self.console.print(f"\n[bold]Summary:[/bold] {successful_result.success_rate:.1%} success rate ({successful}/{total})") 