"""
Boot commands module for forex trading bot CLI.

This module provides CLI commands for boot process management,
including system boot, status checking, and dependency validation.
"""

import os
import sys
import click
import asyncio
import json
import time
from typing import Optional, Dict, List, Any, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich.theme import Theme
from rich.live import Live
from rich.traceback import install as install_rich_traceback

from ..utils.boot_config_manager import BootConfigManager
from ..utils.logger import get_logger
from ..core.boot import BootManager, Component, ComponentState

# Install rich traceback handler
install_rich_traceback()

# Create a custom theme with forex trading colors
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red",
    "success": "green",
    "progress.description": "cyan",
    "progress.percentage": "cyan",
    "progress.elapsed": "cyan",
})

# Initialize console with custom theme
console = Console(theme=custom_theme)

logger = get_logger("cli.boot")

@click.group(name="boot")
def boot_group():
    """Boot system and manage boot configuration."""
    pass

@boot_group.command(name="start")
@click.option('--config-file', type=click.Path(exists=True), 
              help='Custom boot configuration file')
@click.option('--skip-dependency-check', is_flag=True, 
              help='Skip checking service dependencies')
@click.option('--force', is_flag=True, 
              help='Force boot even if non-critical validations fail')
@click.option('--verbose', '-v', is_flag=True, 
              help='Enable verbose output')
@click.option('--quiet', '-q', is_flag=True,
              help='Minimize output, show only errors')
@click.option('--components', '-c', 
              help='Comma-separated list of specific components to start')
@click.option('--dry-run', is_flag=True,
              help='Validate configuration without starting services')
def boot_start(config_file: Optional[str], skip_dependency_check: bool, 
              force: bool, verbose: bool, quiet: bool, 
              components: Optional[str], dry_run: bool):
    """
    Boot the trading system with specified configuration.
    
    This command starts the Forex Trading Bot system, performing dependency
    checks and service initialization according to the boot configuration.
    
    Examples:
        botctl boot start
        botctl boot start --verbose
        botctl boot start --components=api,worker,data
        botctl boot start --dry-run
    """
    # Set boot start time
    start_time = time.time()

    # Resolve conflicting options
    if verbose and quiet:
        console.print("[warning]Warning: Both --verbose and --quiet specified. Using --verbose.[/warning]")
        quiet = False
    
    # Parse components if specified
    component_list = None
    if components:
        component_list = [c.strip() for c in components.split(',')]
        if not quiet:
            console.print(f"[info]Starting specific components: [/info][bold]{', '.join(component_list)}[/bold]")
    
    # Show boot header
    if not quiet:
        _display_boot_header(dry_run)
    
    # Get boot configuration manager
    boot_config_manager = BootConfigManager.get_instance()
    
    # Load config from file if provided
    if config_file:
        if not quiet:
            console.print(f"[info]Using custom configuration file: [/info][bold]{config_file}[/bold]")
    
    # Get the boot manager
    boot_manager = BootManager.get_instance(config_file)
    
    if force:
        # Override force_boot setting
        boot_config_manager.boot_config.force_boot = True
        if not quiet:
            console.print("[warning]Force boot enabled - will ignore non-critical failures[/warning]")
    
    # Display configuration in verbose mode
    if verbose and not quiet:
        console.print("[info]Boot configuration:[/info]")
        config_dict = boot_config_manager.boot_config.model_dump()
        console.print_json(json.dumps(config_dict, indent=2))
    elif not quiet:
        boot_config_manager.log_boot_configuration()
    
    # Validate boot configuration
    if not quiet:
        console.print("[info]Validating boot configuration...[/info]")
    
    is_valid, missing = boot_config_manager.validate_boot_readiness()
    if not is_valid:
        console.print("[warning]Boot configuration validation issues:[/warning]")
        for issue in missing:
            console.print(f"  [warning]- {issue}[/warning]")
        
        if not force and not dry_run:
            console.print("[error]Boot aborted due to configuration issues.[/error]")
            console.print("[info]Suggestion: Run with --dry-run to validate or --force to override[/info]")
            sys.exit(1)
        else:
            if not quiet:
                console.print("[warning]Continuing despite validation issues " + 
                          f"({'dry run mode' if dry_run else '--force enabled'})[/warning]")
    else:
        if not quiet:
            console.print("[success]Boot configuration validated successfully[/success]")
    
    # Check dependencies if not skipped
    if not skip_dependency_check and not dry_run:
        if not quiet:
            console.print("[info]Checking service dependencies...[/info]")
        
        try:
            dependency_results = asyncio.run(boot_config_manager.check_service_dependencies())
            
            failed_deps = [svc for svc, status in dependency_results.items() if not status]
            
            if failed_deps:
                console.print("[warning]Failed dependencies:[/warning]")
                critical_failures = False
                
                # Create a table for better visibility
                table = Table(show_header=True, header_style="bold")
                table.add_column("Service")
                table.add_column("Status")
                table.add_column("Impact")
                
                for svc in failed_deps:
                    is_critical = boot_config_manager.boot_config.services[svc].critical
                    status_str = "CRITICAL" if is_critical else "NON-CRITICAL"
                    status_color = "red" if is_critical else "yellow"
                    
                    table.add_row(
                        svc,
                        f"[{status_color}]UNAVAILABLE[/{status_color}]",
                        f"[{status_color}]{status_str}[/{status_color}]"
                    )
                    
                    if is_critical:
                        critical_failures = True
                
                console.print(table)
                
                if critical_failures and not force:
                    console.print("[error]Boot aborted due to critical service failures.[/error]")
                    console.print("[info]Suggestions:[/info]")
                    console.print("  [info]- Check service health with[/info] [bold]botctl boot check[/bold]")
                    console.print("  [info]- Use --force to override, but system may not function properly[/info]")
                    sys.exit(1)
                else:
                    if not quiet:
                        console.print("[warning]Continuing despite dependency failures " + 
                                  f"({('dry run mode' if dry_run else '--force enabled') if force else 'non-critical only'})[/warning]")
            else:
                if not quiet:
                    console.print("[success]All service dependencies available[/success]")
        except Exception as e:
            console.print(f"[error]Error checking dependencies: {str(e)}[/error]")
            if not force and not dry_run:
                console.print("[error]Boot aborted due to dependency check error.[/error]")
                console.print("[info]Use --force to override or --skip-dependency-check to bypass[/info]")
                sys.exit(1)
    elif skip_dependency_check and not quiet:
        console.print("[warning]Dependency check skipped (--skip-dependency-check)[/warning]")
    
    # Get boot order
    boot_order = boot_config_manager.get_service_boot_order()
    
    # Filter boot order based on selected components
    if component_list:
        boot_order = [svc for svc in boot_order if svc in component_list]
        if not boot_order:
            console.print("[error]Error: None of the specified components exist in boot configuration[/error]")
            console.print("[info]Available components: " + 
                      f"{', '.join(boot_config_manager.get_service_boot_order())}[/info]")
            sys.exit(1)
    
    if not quiet:
        console.print("[info]Boot sequence:[/info]")
        for i, service in enumerate(boot_order, 1):
            console.print(f"  [info]{i}. {service}[/info]")
    
    # Stop here if dry run mode
    if dry_run:
        end_time = time.time()
        console.print("[success]Dry run completed successfully[/success]")
        console.print(f"[info]Total time: {end_time - start_time:.2f} seconds[/info]")
        console.print("[info]No services were started. Run without --dry-run to execute boot sequence.[/info]")
        return
    
    # Start the actual boot process
    if not quiet:
        console.print("[info]Starting services...[/info]")
    
    # Set up the progress display
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
        transient=False  # Keep progress bars after completion
    ) as progress:
        # Create the main tasks
        overall_task = progress.add_task("[bold blue]Overall boot progress", total=len(boot_order) + 4)  # +4 for boot phases
        phase_task = progress.add_task("Initializing...", total=1.0)
        
        # Create a boot status listener to update our progress display
        async def boot_status_listener(event, data):
            if event == "phase_started":
                phase = data["phase"]
                progress.update(phase_task, description=f"Phase: {phase.capitalize()}", completed=0.0)
            elif event == "phase_completed":
                phase = data["phase"]
                progress.update(phase_task, description=f"[green]✓ Phase: {phase.capitalize()} completed", completed=1.0)
                progress.update(overall_task, advance=1)
            elif event == "component_state_changed":
                component = data["component"]
                state = data["state"]
                if state == ComponentState.STARTING:
                    progress.update(phase_task, description=f"Starting {component}...", completed=0.3)
                elif state == ComponentState.RUNNING:
                    progress.update(phase_task, description=f"[green]✓ {component} started", completed=1.0)
                    progress.update(overall_task, advance=1)
                elif state == ComponentState.FAILED:
                    progress.update(phase_task, description=f"[red]✗ {component} failed", completed=1.0)
                    console.print(f"[error]Error starting service {component}: {data.get('error', 'Unknown error')}[/error]")
        
        # Register the listener with the boot manager
        boot_manager.register_event_listener(boot_status_listener)
        
        try:
            # Run the actual boot process
            progress.update(phase_task, description="Starting boot sequence...", completed=0.0)
            
            # Create an event loop for the boot process
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Execute boot process with real-time progress updates
            boot_result = False
            
            try:
                # Run the boot process which will emit events for our listener
                progress.update(phase_task, description="Starting boot sequence...", completed=0.0)
                boot_result = loop.run_until_complete(boot_manager.boot())
                
                # Final update based on boot result
                if boot_result:
                    progress.update(overall_task, completed=len(boot_order) + 4)  # Mark as fully complete
                    end_time = time.time()
                    if not quiet:
                        _display_boot_complete(start_time, end_time)
                    else:
                        console.print("[success]Boot completed successfully[/success]")
                else:
                    console.print("[error]Boot failed. See errors above for details.[/error]")
                    sys.exit(1)
                
            except Exception as e:
                console.print(f"[error]Boot process failed: {str(e)}[/error]")
                if verbose:
                    console.print_exception()
                boot_result = False
            finally:
                # Unregister event listener
                boot_manager.unregister_event_listener(boot_status_listener)
                loop.close()
            
        except Exception as e:
            console.print(f"[error]Error during boot process: {str(e)}[/error]")
            if verbose:
                console.print_exception()
            sys.exit(1)

def _display_boot_header(dry_run: bool = False):
    """Display an attractive boot header with system info."""
    mode = "[yellow]DRY RUN MODE[/yellow]" if dry_run else "[green]BOOT SEQUENCE[/green]"
    
    header = Panel(
        f"[bold blue]Forex Trading Bot System[/bold blue]\n"
        f"{mode}\n"
        f"[cyan]Time: {time.strftime('%Y-%m-%d %H:%M:%S')}[/cyan]",
        border_style="blue",
        expand=False,
        title="botctl"
    )
    
    console.print(header)

def _display_boot_complete(start_time: float, end_time: float):
    """Display boot completion message with timing stats."""
    duration = end_time - start_time
    footer = Panel(
        f"[bold green]Boot completed successfully[/bold green]\n"
        f"[cyan]Total boot time: {duration:.2f} seconds[/cyan]\n"
        f"[blue]System is now ready for operation[/blue]",
        border_style="green",
        expand=False,
        title="Status"
    )
    
    console.print(footer)

@boot_group.command(name="status")
@click.option('--json', 'json_output', is_flag=True, help='Output in JSON format')
def boot_status(json_output: bool):
    """Show the current boot status including service health."""
    boot_manager = BootConfigManager.get_instance()
    
    try:
        # Check all service statuses
        status_results = asyncio.run(boot_manager.check_service_dependencies())
        
        if json_output:
            # Enhanced JSON with service details
            json_data = {
                "status": "healthy" if all(status_results.values()) else "unhealthy",
                "services": {}
            }
            
            for service, status in status_results.items():
                service_config = boot_manager.boot_config.services.get(service, {})
                json_data["services"][service] = {
                    "status": "healthy" if status else "unhealthy",
                    "critical": service_config.critical if hasattr(service_config, "critical") else True,
                    "enabled": service_config.enabled if hasattr(service_config, "enabled") else True
                }
                
            console.print_json(json.dumps(json_data, indent=2))
        else:
            all_healthy = all(status_results.values())
            status_str = "[green]✓ HEALTHY[/green]" if all_healthy else "[red]✗ UNHEALTHY[/red]"
            
            table = Table(title="Boot Status", show_header=True, header_style="bold")
            table.add_column("Service")
            table.add_column("Status")
            table.add_column("Type")
            
            for service, status in status_results.items():
                service_config = boot_manager.boot_config.services.get(service, {})
                critical = getattr(service_config, "critical", True)
                enabled = getattr(service_config, "enabled", True)
                
                service_status = "[green]✓ HEALTHY[/green]" if status else "[red]✗ UNHEALTHY[/red]"
                critical_str = "[red]CRITICAL[/red]" if critical else "[yellow]NON-CRITICAL[/yellow]"
                disabled_str = " [gray](DISABLED)[/gray]" if not enabled else ""
                
                table.add_row(f"{service}{disabled_str}", service_status, critical_str)
            
            console.print(Panel(f"Overall Status: {status_str}", border_style="blue"))
            console.print(table)
    except Exception as e:
        console.print(f"[error]Error checking service status: {str(e)}[/error]")
        if json_output:
            console.print_json(json.dumps({"status": "error", "message": str(e)}, indent=2))

@boot_group.command(name="check")
@click.argument('service', required=False)
def boot_check(service: Optional[str]):
    """
    Check health of a specific service or all services.
    
    If SERVICE is provided, checks only that service.
    Otherwise, checks all services.
    """
    boot_manager = BootConfigManager.get_instance()
    
    try:
        if service:
            # Check specific service
            if service not in boot_manager.boot_config.services:
                console.print(f"[error]Unknown service: {service}[/error]")
                return
                
            config = boot_manager.boot_config.services[service]
            console.print(f"[info]Checking service: {service}...[/info]")
            is_healthy = asyncio.run(boot_manager._check_service_health(service, config))
            
            status_str = "[green]✓ HEALTHY[/green]" if is_healthy else "[red]✗ UNHEALTHY[/red]"
            console.print(f"{service}: {status_str}")
            
            if not is_healthy:
                sys.exit(1)  # Exit with error code for scripting use
        else:
            # Check all services
            console.print("[info]Checking all services...[/info]")
            results = asyncio.run(boot_manager.check_service_dependencies())
            all_healthy = all(results.values())
            
            status_str = "[green]✓ ALL HEALTHY[/green]" if all_healthy else "[red]✗ ISSUES DETECTED[/red]"
            console.print(f"Overall Status: {status_str}")
            
            table = Table(show_header=True, header_style="bold")
            table.add_column("Service")
            table.add_column("Status")
            
            for service, status in results.items():
                service_status = "[green]✓ HEALTHY[/green]" if status else "[red]✗ UNHEALTHY[/red]"
                table.add_row(service, service_status)
            
            console.print(table)
            
            if not all_healthy:
                sys.exit(1)  # Exit with error code for scripting use
    except Exception as e:
        console.print(f"[error]Error during health check: {str(e)}[/error]")
        sys.exit(1)

@boot_group.command(name="validate")
def boot_validate():
    """Validate boot configuration without starting services."""
    boot_manager = BootConfigManager.get_instance()
    
    console.print("[info]Validating boot configuration...[/info]")
    is_valid, missing = boot_manager.validate_boot_readiness()
    
    if is_valid:
        console.print("[success]Boot configuration is valid[/success]")
        
        # Also check for warnings about service dependencies
        console.print("[info]Analyzing service dependency graph...[/info]")
        boot_order = boot_manager.get_service_boot_order()
        
        console.print("[success]Recommended boot order:[/success]")
        
        table = Table(show_header=True, header_style="bold")
        table.add_column("#")
        table.add_column("Service")
        
        for i, service in enumerate(boot_order, 1):
            table.add_row(str(i), service)
        
        console.print(table)
    else:
        console.print("[error]Boot configuration has issues:[/error]")
        for issue in missing:
            console.print(f"  [error]- {issue}[/error]")
        sys.exit(1)  # Exit with error code for scripting use

# Register commands with the CLI
def register_commands(cli):
    """Register boot commands with the CLI."""
    cli.add_command(boot_group) 