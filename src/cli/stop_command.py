"""
Botctl Stop Command

This module implements the `botctl stop` command for gracefully shutting down
the Forex Trading Bot system.
"""

import os
import sys
import asyncio
import click
import logging
import time
from typing import Optional, Dict, Any
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.prompt import Confirm
from rich.table import Table

# Ensure we can import modules from the src directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import our shutdown coordinator and related components
from ..core.shutdown import (
    ShutdownCoordinator, 
    ShutdownPhase,
    PositionCloseStrategy,
    get_shutdown_coordinator,
    setup_signal_handlers
)
from ..core.position_closer import get_position_closer
from ..core.agent_terminator import get_agent_terminator
from ..core.resource_cleaner import get_resource_cleaner, register_cleanup_callback

# Import the risk manager
from ..risk.global_risk_manager import GlobalRiskManager

# Import the agent orchestrator
from ..agents.orchestrator.engine import AgentSwarmOrchestrator, get_orchestrator

# Configure console
console = Console()

# Configure logger
logger = logging.getLogger(__name__)


class StopCommand:
    """
    Implements the `botctl stop` command for gracefully shutting down
    the Forex Trading Bot system.
    """
    
    def __init__(self):
        """Initialize the stop command."""
        # Get components
        self.shutdown_coordinator = get_shutdown_coordinator()
        self.position_closer = None
        self.agent_terminator = None
        self.resource_cleaner = None
        
        # Track start time for reporting
        self.start_time = None
    
    async def initialize_components(self):
        """Initialize the components needed for shutdown."""
        # Get the risk manager if available
        try:
            # This is a placeholder - in a real implementation, we would 
            # get the actual risk manager instance
            risk_manager = None
            self.position_closer = get_position_closer(risk_manager)
        except Exception as e:
            logger.warning(f"Failed to initialize position closer: {str(e)}")
        
        # Get the agent orchestrator if available
        try:
            orchestrator = get_orchestrator()
            self.agent_terminator = get_agent_terminator(orchestrator)
        except Exception as e:
            logger.warning(f"Failed to initialize agent terminator: {str(e)}")
        
        # Get the resource cleaner
        self.resource_cleaner = get_resource_cleaner()
    
    async def execute_shutdown(self,
                              force: bool = False,
                              immediate: bool = False,
                              timeout: float = 60.0,
                              verbose: bool = False) -> int:
        """
        Execute the shutdown process.
        
        Args:
            force: Whether to force shutdown even if components fail to stop
            immediate: Whether to use immediate position closing strategy
            timeout: Maximum time to wait for shutdown to complete
            verbose: Whether to show verbose output
            
        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        # Record start time
        self.start_time = time.time()
        
        # Initialize components
        await self.initialize_components()
        
        # Set up signal handlers
        setup_signal_handlers(self.shutdown_coordinator)
        
        # Determine position closing strategy
        position_strategy = (
            PositionCloseStrategy.IMMEDIATE if immediate 
            else PositionCloseStrategy.GRADUAL
        )
        
        # Initiate shutdown
        await self.shutdown_coordinator.initiate_shutdown(
            reason="cli_command",
            force=force,
            position_strategy=position_strategy
        )
        
        # Display progress
        return await self.monitor_shutdown_progress(
            timeout=timeout,
            verbose=verbose
        )
    
    async def monitor_shutdown_progress(self, timeout: float = 60.0, verbose: bool = False) -> int:
        """
        Monitor and display the shutdown progress.
        
        Args:
            timeout: Maximum time to wait for shutdown to complete
            verbose: Whether to show verbose output
            
        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        # Create a progress display
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[bold]{task.fields[status]}"),
            TimeElapsedColumn(),
            console=console,
            expand=True
        ) as progress:
            # Add a task for overall progress
            task = progress.add_task(
                "[bold]Shutting down system...", 
                total=5,  # INITIALIZING, PREPARATION, POSITIONS, AGENTS, RESOURCES
                status="Initializing"
            )
            
            # Wait for shutdown to complete or timeout
            try:
                # Poll for status updates
                last_phase = None
                while not await self.shutdown_coordinator.wait_for_shutdown(timeout=0.5):
                    # Get current status
                    status = self.shutdown_coordinator.get_status()
                    current_phase = status.get('phase')
                    
                    # Update progress if phase changed
                    if current_phase != last_phase:
                        if current_phase == ShutdownPhase.PREPARATION.value:
                            progress.update(task, completed=1, status="Preparing for shutdown")
                        elif current_phase == ShutdownPhase.POSITIONS.value:
                            progress.update(task, completed=2, status="Closing positions")
                        elif current_phase == ShutdownPhase.AGENTS.value:
                            progress.update(task, completed=3, status="Stopping agents")
                        elif current_phase == ShutdownPhase.RESOURCES.value:
                            progress.update(task, completed=4, status="Cleaning up resources")
                        elif current_phase == ShutdownPhase.COMPLETE.value:
                            progress.update(task, completed=5, status="Shutdown complete")
                        elif current_phase == ShutdownPhase.FAILED.value:
                            progress.update(task, completed=5, status="Shutdown failed")
                        
                        last_phase = current_phase
                    
                    # Check if timeout has exceeded
                    elapsed = time.time() - self.start_time
                    if elapsed > timeout:
                        progress.update(task, status="Timeout exceeded")
                        console.print("[bold red]Shutdown timeout exceeded![/bold red]")
                        return 1
                
                # Shutdown completed
                status = self.shutdown_coordinator.get_status()
                current_phase = status.get('phase')
                
                # Update final progress
                if current_phase == ShutdownPhase.COMPLETE.value:
                    progress.update(task, completed=5, status="Shutdown complete")
                    console.print(f"[bold green]Shutdown completed successfully in {time.time() - self.start_time:.2f}s[/bold green]")
                    return 0
                else:
                    progress.update(task, completed=5, status="Shutdown failed")
                    console.print("[bold red]Shutdown failed![/bold red]")
                    
                    # Print details if verbose
                    if verbose:
                        console.print(self._format_status_table(status))
                    
                    return 1
                
            except asyncio.TimeoutError:
                console.print("[bold red]Shutdown timeout exceeded![/bold red]")
                return 1
            except Exception as e:
                console.print(f"[bold red]Error during shutdown: {str(e)}[/bold red]")
                return 1
    
    def _format_status_table(self, status: Dict[str, Any]) -> Table:
        """
        Format the shutdown status as a rich table.
        
        Args:
            status: Status information from the shutdown coordinator
            
        Returns:
            A rich table with the status information
        """
        # Create table
        table = Table(title="Shutdown Status", show_header=True)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")
        
        # Add rows
        table.add_row("Phase", status.get('phase', 'Unknown'))
        table.add_row("Elapsed Time", f"{status.get('elapsed_time', 0):.2f}s")
        table.add_row("Reason", status.get('reason', 'Unknown'))
        table.add_row("Force Mode", "Yes" if status.get('force', False) else "No")
        table.add_row("Position Strategy", status.get('position_strategy', 'Unknown'))
        
        # Add phase results if available
        phase_results = status.get('phase_results', {})
        for phase, results in phase_results.items():
            success = results.get('success', False)
            success_text = "[green]Success[/green]" if success else "[red]Failed[/red]"
            table.add_row(f"Phase {phase}", success_text)
        
        return table


def register_commands(cli):
    """
    Register the stop command with the CLI.
    
    Args:
        cli: The Click CLI group to register with
    """
    
    @cli.command(name="stop")
    @click.option('--force', is_flag=True, 
                  help='Force shutdown even if components fail to stop gracefully')
    @click.option('--immediate', is_flag=True, 
                  help='Close positions immediately using market orders')
    @click.option('--timeout', type=float, default=60.0, 
                  help='Maximum time to wait for shutdown (seconds)')
    @click.option('--no-confirm', is_flag=True, 
                  help='Skip confirmation prompt')
    @click.option('--verbose', '-v', is_flag=True, 
                  help='Show verbose output')
    @click.pass_context
    def stop(ctx, force, immediate, timeout, no_confirm, verbose):
        """
        Gracefully shut down the trading system.
        
        This command initiates a graceful shutdown of the entire trading system,
        including closing positions, stopping agents, and releasing resources.
        
        By default, it uses a gradual approach to minimize market impact when
        closing positions. Use --immediate for faster shutdown with market orders.
        
        Examples:
            botctl stop
            botctl stop --immediate
            botctl stop --force --timeout 30
        """
        # Warn about potential risks
        if immediate:
            console.print(
                Panel(
                    "[bold yellow]WARNING: Immediate position closing uses market orders![/bold yellow]\n"
                    "This may result in worse execution prices and higher fees.",
                    title="Risk Warning",
                    border_style="yellow"
                )
            )
        
        # Confirm if not skipped
        if not no_confirm:
            message = "Are you sure you want to shut down the trading system?"
            if force:
                message += " (FORCE MODE)"
            
            if not Confirm.ask(message, default=False):
                console.print("[yellow]Shutdown cancelled.[/yellow]")
                ctx.exit(0)
        
        # Print shutdown header
        console.print(
            Panel(
                f"[bold blue]Forex Trading Bot Shutdown[/bold blue]\n"
                f"Strategy: {'Immediate' if immediate else 'Gradual'} position closing\n"
                f"Force mode: {'Yes' if force else 'No'}\n"
                f"Timeout: {timeout} seconds",
                border_style="blue",
                title="botctl stop"
            )
        )
        
        try:
            # Create and run the command
            cmd = StopCommand()
            exit_code = asyncio.run(cmd.execute_shutdown(
                force=force,
                immediate=immediate,
                timeout=timeout,
                verbose=verbose
            ))
            ctx.exit(exit_code)
        except Exception as e:
            console.print(f"[bold red]Error: {str(e)}[/bold red]")
            if ctx.obj and ctx.obj.get('DEBUG', False):
                console.print_exception()
            ctx.exit(1)
    
    # Alias for immediate shutdown
    @cli.command(name="stop-immediate")
    @click.option('--timeout', type=float, default=60.0, 
                  help='Maximum time to wait for shutdown (seconds)')
    @click.option('--no-confirm', is_flag=True, 
                  help='Skip confirmation prompt')
    @click.option('--verbose', '-v', is_flag=True, 
                  help='Show verbose output')
    @click.pass_context
    def stop_immediate(ctx, timeout, no_confirm, verbose):
        """
        Shut down the trading system with immediate position closing.
        
        This is a convenience alias for 'botctl stop --immediate'.
        It closes all positions immediately using market orders.
        
        Examples:
            botctl stop-immediate
            botctl stop-immediate --no-confirm
        """
        ctx.forward(stop, immediate=True)
    
    # Alias for forced shutdown
    @cli.command(name="stop-force")
    @click.option('--immediate', is_flag=True, 
                  help='Close positions immediately using market orders')
    @click.option('--timeout', type=float, default=60.0, 
                  help='Maximum time to wait for shutdown (seconds)')
    @click.option('--no-confirm', is_flag=True, 
                  help='Skip confirmation prompt')
    @click.option('--verbose', '-v', is_flag=True, 
                  help='Show verbose output')
    @click.pass_context
    def stop_force(ctx, immediate, timeout, no_confirm, verbose):
        """
        Force shutdown of the trading system even if components fail.
        
        This is a convenience alias for 'botctl stop --force'.
        Use this only when a normal shutdown fails or is stuck.
        
        Examples:
            botctl stop-force
            botctl stop-force --immediate
        """
        ctx.forward(stop, force=True)
    
    # Alias for emergency shutdown
    @cli.command(name="stop-emergency")
    @click.option('--timeout', type=float, default=30.0, 
                  help='Maximum time to wait for shutdown (seconds)')
    @click.option('--verbose', '-v', is_flag=True, 
                  help='Show verbose output')
    @click.pass_context
    def stop_emergency(ctx, timeout, verbose):
        """
        Emergency shutdown of the trading system.
        
        This is a convenience alias for 'botctl stop --force --immediate --no-confirm'
        with a reduced default timeout. Use this in emergency situations when
        you need to shut down the system as quickly as possible.
        
        Examples:
            botctl stop-emergency
            botctl stop-emergency --timeout 15
        """
        ctx.forward(stop, force=True, immediate=True, no_confirm=True, timeout=timeout)
    
    # General alias for stop
    @cli.command(name="shutdown")
    @click.option('--force', is_flag=True, 
                  help='Force shutdown even if components fail to stop gracefully')
    @click.option('--immediate', is_flag=True, 
                  help='Close positions immediately using market orders')
    @click.option('--timeout', type=float, default=60.0, 
                  help='Maximum time to wait for shutdown (seconds)')
    @click.option('--no-confirm', is_flag=True, 
                  help='Skip confirmation prompt')
    @click.option('--verbose', '-v', is_flag=True, 
                  help='Show verbose output')
    @click.pass_context
    def shutdown(ctx, force, immediate, timeout, no_confirm, verbose):
        """
        Gracefully shut down the trading system.
        
        This is an alias for 'botctl stop' with identical functionality.
        
        Examples:
            botctl shutdown
            botctl shutdown --immediate
        """
        ctx.forward(stop) 