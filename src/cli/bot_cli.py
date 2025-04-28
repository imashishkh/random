"""
Forex Trading Bot CLI

Main entry point for the 'botctl' command-line interface.
"""

import os
import sys
import click
import logging
from rich.console import Console
from rich.logging import RichHandler

# Import CLI command modules
from .wizard_command import register_commands as register_wizard_commands
from .config_commands import register_commands as register_config_commands
from .boot_commands import register_commands as register_boot_commands
from .pnl_commands import register_commands as register_pnl_commands
from .stop_command import register_commands as register_stop_commands
from .boot_commands import boot_start, boot_status

# Set up rich console for pretty output
console = Console()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    datefmt='[%X]',
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)
logger = logging.getLogger('bot_cli')

@click.group()
@click.version_option(version="0.1.0")
@click.option('--debug', is_flag=True, help='Enable debug mode with detailed error traces')
@click.pass_context
def cli(ctx, debug):
    """
    Forex Trading Bot Control CLI.
    
    This is the main command-line interface for controlling and managing
    the Forex Trading Bot system.
    
    Examples:
        botctl start             Start the trading system
        botctl stop              Gracefully shut down the system
        botctl status            Check system status
        botctl config list       List configuration settings
        botctl boot validate     Validate boot configuration
        botctl pnl wallet        Display wallet balances
        botctl pnl profit        Show profit metrics
    """
    # Store debug flag in context
    ctx.ensure_object(dict)
    ctx.obj['DEBUG'] = debug
    
    # Set logging level based on debug flag
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")

# Add a direct 'start' command at the root level for convenience
@cli.command(name="start")
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
def start(config_file, skip_dependency_check, force, verbose, quiet, components, dry_run):
    """
    Start the trading system.
    
    This command is a shorthand for 'botctl boot start'.
    
    Examples:
        botctl start
        botctl start --verbose
        botctl start --components=api,worker,data
        botctl start --dry-run
    """
    # Call the boot_start function directly
    boot_start(config_file, skip_dependency_check, force, verbose, quiet, components, dry_run)

# Add a direct 'status' command at the root level for convenience
@cli.command(name="status")
@click.option('--json', 'json_output', is_flag=True, help='Output in JSON format')
def status(json_output):
    """
    Show system status.
    
    This command is a shorthand for 'botctl boot status'.
    """
    # Call the boot_status function directly
    boot_status(json_output)

# Register command subgroups
def register_all_commands():
    """Register all command subgroups with the CLI."""
    register_wizard_commands(cli)
    register_config_commands(cli)
    register_boot_commands(cli)
    register_pnl_commands(cli)
    register_stop_commands(cli)  # Register our new stop command

# Register all commands
register_all_commands()

def main():
    """Main entry point for the CLI."""
    try:
        cli()
    except Exception as e:
        logger.error(f"CLI error: {str(e)}", exc_info=True)
        console.print(f"[bold red]Error:[/bold red] {str(e)}", style="bold red")
        sys.exit(1)

if __name__ == '__main__':
    main() 