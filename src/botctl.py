#!/usr/bin/env python
"""
Forex Trading Bot CLI - Main Entry Point

This is the main entry point for the 'botctl' command-line tool,
which provides a set of commands for managing the Forex Trading Bot system.
"""

import os
import sys
import click
import logging
from rich.console import Console
from rich.logging import RichHandler

# Ensure we can import modules from the src directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import CLI modules
from .cli.bot_cli import cli

# Set up rich console for pretty output
console = Console()

# Configure logging with rich formatting
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)

def main():
    """Main entry point for the CLI."""
    try:
        cli()
    except Exception as e:
        console.print(f"[bold red]ERROR:[/bold red] {str(e)}", style="bold red")
        if "--debug" in sys.argv:
            console.print_exception()
        sys.exit(1)

if __name__ == '__main__':
    main() 