"""
Simple test script for the PNL commands module.
"""

import sys
import click
from rich.console import Console

# Import directly from the current directory
from pnl_commands import pnl_group

console = Console()

if __name__ == "__main__":
    console.print("[bold blue]Testing PNL command group[/bold blue]")
    
    # Test the help output for the command group
    ctx = click.Context(pnl_group)
    help_text = pnl_group.get_help(ctx)
    console.print("[bold]PNL Group Help:[/bold]")
    console.print(help_text)
    
    # Test individual commands by name
    console.print("\n[bold]Available Commands:[/bold]")
    for cmd_name in pnl_group.list_commands(ctx):
        console.print(f"- {cmd_name}")
    
    console.print("[bold green]Test complete![/bold green]") 