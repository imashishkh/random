"""
Forex Trading Dashboard CLI - Configuration Commands

This module provides CLI commands for viewing and modifying system configuration settings.
"""

import os
import json
import click
from typing import Dict, Any, Optional

from ..utils.config_manager import ConfigManager
from ..utils.logger import get_logger

# Initialize logger
logger = get_logger("cli.config")

# Get config manager instance
config_manager = ConfigManager.get_instance()


def print_config(config_data: Dict[str, Any], section: Optional[str] = None, prefix: str = "") -> None:
    """
    Print configuration data in a hierarchical format.
    
    Args:
        config_data: Configuration data to print
        section: Optional section name to filter
        prefix: String prefix for recursive calls (used for indentation)
    """
    for key, value in sorted(config_data.items()):
        # Skip sections that don't match the filter
        if section and not key.startswith(section):
            continue
        
        # Format the key-value pair based on the type
        if isinstance(value, dict):
            click.echo(f"{prefix}{key}:")
            print_config(value, None, prefix + "  ")
        elif isinstance(value, (list, tuple)):
            click.echo(f"{prefix}{key}: {json.dumps(value)}")
        elif isinstance(value, bool):
            click.echo(f"{prefix}{key}: {str(value).lower()}")
        else:
            click.echo(f"{prefix}{key}: {value}")


@click.group(name="config")
def config_group():
    """View and modify configuration settings."""
    pass


@config_group.command(name="view")
@click.option("--section", "-s", help="Show only specific configuration section")
@click.option("--json", "json_format", is_flag=True, help="Output in JSON format")
def view_config(section: Optional[str], json_format: bool):
    """View the current configuration settings."""
    try:
        if section:
            # Get specific section
            config_data = config_manager.get(section, {})
            if not config_data and "." not in section:
                # Try with wildcard for sections like "logging.*"
                all_config = config_manager.get_all()
                filtered_config = {}
                for key, value in all_config.items():
                    if key.startswith(section + "."):
                        sub_key = key[len(section) + 1:]
                        filtered_config[sub_key] = value
                config_data = filtered_config
        else:
            # Get all configuration
            config_data = config_manager.get_all()
        
        # Output based on format
        if json_format:
            click.echo(json.dumps(config_data, indent=2))
        else:
            if not config_data:
                click.echo("No configuration settings found.")
            else:
                print_config(config_data, None)
    
    except Exception as e:
        logger.error(f"Error viewing configuration: {str(e)}", exc_info=True)
        click.echo(f"Error: {str(e)}", err=True)


@config_group.command(name="set")
@click.argument("key", type=str)
@click.argument("value", type=str)
def set_config(key: str, value: str):
    """
    Set a configuration value.
    
    Examples:
        config set logging.level DEBUG
        config set api.timeout 30
    """
    try:
        # Convert value to appropriate type
        try:
            # Try to parse as JSON for complex types
            parsed_value = json.loads(value.lower())
        except json.JSONDecodeError:
            # Handle common literal types
            if value.lower() == "true":
                parsed_value = True
            elif value.lower() == "false":
                parsed_value = False
            elif value.isdigit():
                parsed_value = int(value)
            elif value.replace(".", "", 1).isdigit() and value.count(".") == 1:
                parsed_value = float(value)
            else:
                parsed_value = value
        
        # Set the value
        config_manager.set(key, parsed_value)
        config_manager.save()
        
        # Log and confirm
        logger.info(f"Configuration updated: {key} = {parsed_value}")
        click.echo(f"Configuration updated: {key} = {parsed_value}")
    
    except Exception as e:
        logger.error(f"Error setting configuration: {str(e)}", exc_info=True)
        click.echo(f"Error: {str(e)}", err=True)


@config_group.command(name="reset")
@click.argument("key", type=str, required=False)
@click.option("--all", "reset_all", is_flag=True, help="Reset all configuration to defaults")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def reset_config(key: Optional[str], reset_all: bool, confirm: bool):
    """
    Reset configuration to default values.
    
    Examples:
        config reset logging.level
        config reset --all
    """
    try:
        if reset_all:
            # Reset all configuration
            if not confirm:
                if not click.confirm("Are you sure you want to reset all configuration to defaults?"):
                    click.echo("Operation cancelled.")
                    return
            
            config_manager.reset_all()
            config_manager.save()
            
            logger.info("All configuration reset to defaults")
            click.echo("All configuration reset to defaults.")
        
        elif key:
            # Reset specific key
            config_manager.reset(key)
            config_manager.save()
            
            logger.info(f"Configuration reset: {key}")
            click.echo(f"Configuration reset: {key}")
        
        else:
            click.echo("Please specify a key to reset or use --all to reset everything.")
    
    except Exception as e:
        logger.error(f"Error resetting configuration: {str(e)}", exc_info=True)
        click.echo(f"Error: {str(e)}", err=True)


@config_group.command(name="export")
@click.argument("filename", type=click.Path())
def export_config(filename: str):
    """
    Export configuration to a file.
    
    Example:
        config export backup.json
    """
    try:
        # Ensure directory exists
        directory = os.path.dirname(os.path.abspath(filename))
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        
        # Export configuration
        config_manager.export_to_file(filename)
        
        logger.info(f"Configuration exported to {filename}")
        click.echo(f"Configuration exported to {filename}")
    
    except Exception as e:
        logger.error(f"Error exporting configuration: {str(e)}", exc_info=True)
        click.echo(f"Error: {str(e)}", err=True)


@config_group.command(name="import")
@click.argument("filename", type=click.Path(exists=True))
@click.option("--merge", is_flag=True, help="Merge with existing configuration")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def import_config(filename: str, merge: bool, confirm: bool):
    """
    Import configuration from a file.
    
    Example:
        config import backup.json
        config import backup.json --merge
    """
    try:
        # Confirm if not using --confirm
        if not confirm:
            action = "merge with" if merge else "replace"
            if not click.confirm(f"Are you sure you want to {action} existing configuration?"):
                click.echo("Operation cancelled.")
                return
        
        # Import configuration
        config_manager.import_from_file(filename, merge=merge)
        config_manager.save()
        
        logger.info(f"Configuration imported from {filename}")
        click.echo(f"Configuration imported from {filename}")
    
    except Exception as e:
        logger.error(f"Error importing configuration: {str(e)}", exc_info=True)
        click.echo(f"Error: {str(e)}", err=True)


# Function to register commands with the CLI
def register_commands(cli):
    """Register configuration commands with the CLI."""
    cli.add_command(config_group) 