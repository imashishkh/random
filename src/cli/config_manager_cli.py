"""
Forex Trading Dashboard - Configuration Manager CLI

This module provides a command-line interface for managing the application configuration.
It allows users to view, modify, export, and import configuration settings.
"""

import os
import sys
import json
import argparse
from typing import Dict, List, Any, Optional
import datetime

from ..utils.config_manager import ConfigManager
from ..utils.logger import logger

class ConfigManagerCLI:
    """Command-line interface for the configuration manager."""
    
    def __init__(self):
        """Initialize the ConfigManagerCLI."""
        self.config_manager = ConfigManager.get_instance()
        self.logger = logger
    
    def run(self, args: Optional[List[str]] = None) -> int:
        """
        Run the configuration manager CLI.
        
        Args:
            args: Command line arguments (if None, sys.argv is used)
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        parser = self._create_parser()
        
        if args is None:
            args = sys.argv[1:]
        
        # Parse arguments
        parsed_args = parser.parse_args(args)
        
        # Execute the selected command
        if hasattr(parsed_args, 'func'):
            try:
                return parsed_args.func(parsed_args)
            except Exception as e:
                self.logger.error(f"Error executing command: {str(e)}", exc_info=True)
                return 1
        else:
            parser.print_help()
            return 0
    
    def _create_parser(self) -> argparse.ArgumentParser:
        """
        Create the argument parser for the CLI.
        
        Returns:
            Configured argument parser
        """
        # Create main parser
        parser = argparse.ArgumentParser(
            description='Forex Trading Dashboard Configuration Manager',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Show all configuration settings
  python -m src.cli.config_manager_cli show
  
  # Show a specific configuration setting
  python -m src.cli.config_manager_cli show api.base_url
  
  # Set a configuration value
  python -m src.cli.config_manager_cli set api.base_url "https://api.example.com"
  
  # Export configuration to a file
  python -m src.cli.config_manager_cli export config_backup.json
  
  # Import configuration from a file
  python -m src.cli.config_manager_cli import config_backup.json
"""
        )
        
        # Create subparsers for commands
        subparsers = parser.add_subparsers(dest='command', help='Command to execute')
        
        # Show command
        show_parser = subparsers.add_parser('show', help='Show configuration settings')
        show_parser.add_argument('key', nargs='?', help='Specific configuration key to show (e.g., "api.base_url")')
        show_parser.add_argument('--format', choices=['text', 'json'], default='text', 
                              help='Output format (default: text)')
        show_parser.set_defaults(func=self._handle_show)
        
        # Set command
        set_parser = subparsers.add_parser('set', help='Set a configuration value')
        set_parser.add_argument('key', help='Configuration key (e.g., "api.base_url")')
        set_parser.add_argument('value', help='New value')
        set_parser.add_argument('--no-save', action='store_true', 
                             help='Do not save to file immediately')
        set_parser.set_defaults(func=self._handle_set)
        
        # Delete command
        delete_parser = subparsers.add_parser('delete', help='Delete a configuration value')
        delete_parser.add_argument('key', help='Configuration key to delete')
        delete_parser.add_argument('--no-save', action='store_true', 
                                help='Do not save to file immediately')
        delete_parser.set_defaults(func=self._handle_delete)
        
        # Reset command
        reset_parser = subparsers.add_parser('reset', help='Reset configuration to defaults')
        reset_parser.add_argument('key', nargs='?', help='Specific key to reset (if not specified, resets all)')
        reset_parser.set_defaults(func=self._handle_reset)
        
        # Export command
        export_parser = subparsers.add_parser('export', help='Export configuration to a file')
        export_parser.add_argument('filename', help='Export filename')
        export_parser.add_argument('--format', choices=['json', 'ini', 'env'], default='json',
                                help='Export format (default: json)')
        export_parser.set_defaults(func=self._handle_export)
        
        # Import command
        import_parser = subparsers.add_parser('import', help='Import configuration from a file')
        import_parser.add_argument('filename', help='Import filename')
        import_parser.add_argument('--merge', action='store_true', 
                                help='Merge with existing configuration (default is to replace)')
        import_parser.set_defaults(func=self._handle_import)
        
        return parser
    
    def _handle_show(self, args: argparse.Namespace) -> int:
        """
        Handle the 'show' command.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        try:
            if args.key:
                # Show specific key
                value = self.config_manager.get(args.key)
                
                if value is None:
                    print(f"Configuration key '{args.key}' not found.")
                    return 1
                
                if args.format == 'json':
                    print(json.dumps(value, indent=2))
                else:
                    self._print_config_value(args.key, value)
            else:
                # Show all config
                config = self.config_manager.get_all()
                
                if args.format == 'json':
                    print(json.dumps(config, indent=2))
                else:
                    print("Configuration Settings:")
                    self._print_config_recursive(config)
            
            return 0
        except Exception as e:
            self.logger.error(f"Error showing configuration: {str(e)}")
            print(f"Error: {str(e)}")
            return 1
    
    def _print_config_recursive(self, config: Dict[str, Any], prefix: str = "") -> None:
        """
        Recursively print configuration in a readable format.
        
        Args:
            config: Configuration dictionary
            prefix: Key prefix for nested config
        """
        for key, value in sorted(config.items()):
            full_key = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict):
                print(f"{full_key}:")
                self._print_config_recursive(value, full_key)
            else:
                self._print_config_value(full_key, value)
    
    def _print_config_value(self, key: str, value: Any) -> None:
        """
        Print a configuration key-value pair in a readable format.
        
        Args:
            key: Configuration key
            value: Configuration value
        """
        # Format value based on type
        if isinstance(value, bool):
            formatted_value = str(value).lower()
        elif isinstance(value, (int, float)):
            formatted_value = str(value)
        elif isinstance(value, str):
            formatted_value = f'"{value}"'
        elif value is None:
            formatted_value = "null"
        else:
            formatted_value = str(value)
        
        print(f"  {key} = {formatted_value}")
    
    def _handle_set(self, args: argparse.Namespace) -> int:
        """
        Handle the 'set' command.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        try:
            # Try to convert the string value to appropriate types
            value = self._parse_value(args.value)
            
            # Set the configuration value
            self.config_manager.set(args.key, value)
            
            # Save to file unless --no-save is specified
            if not args.no_save:
                self.config_manager.save()
                self.logger.info(f"Set '{args.key}' to '{value}' and saved to file")
            else:
                self.logger.info(f"Set '{args.key}' to '{value}' (not saved to file)")
            
            print(f"Successfully set '{args.key}' to '{value}'")
            return 0
        except Exception as e:
            self.logger.error(f"Error setting configuration value: {str(e)}")
            print(f"Error: {str(e)}")
            return 1
    
    def _parse_value(self, value_str: str) -> Any:
        """
        Parse a string value into an appropriate type.
        
        Args:
            value_str: String value to parse
            
        Returns:
            Parsed value in appropriate type
        """
        # Try to parse as JSON first
        try:
            return json.loads(value_str)
        except json.JSONDecodeError:
            pass
        
        # Check for boolean values
        if value_str.lower() == 'true':
            return True
        elif value_str.lower() == 'false':
            return False
        elif value_str.lower() == 'null':
            return None
        
        # Check if it's a number
        try:
            if '.' in value_str:
                return float(value_str)
            else:
                return int(value_str)
        except ValueError:
            pass
        
        # If nothing else matches, return as string
        return value_str
    
    def _handle_delete(self, args: argparse.Namespace) -> int:
        """
        Handle the 'delete' command.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        try:
            # Check if the key exists
            if not self.config_manager.has(args.key):
                print(f"Configuration key '{args.key}' not found.")
                return 1
            
            # Delete the configuration value
            self.config_manager.delete(args.key)
            
            # Save to file unless --no-save is specified
            if not args.no_save:
                self.config_manager.save()
                self.logger.info(f"Deleted '{args.key}' and saved to file")
            else:
                self.logger.info(f"Deleted '{args.key}' (not saved to file)")
            
            print(f"Successfully deleted '{args.key}'")
            return 0
        except Exception as e:
            self.logger.error(f"Error deleting configuration value: {str(e)}")
            print(f"Error: {str(e)}")
            return 1
    
    def _handle_reset(self, args: argparse.Namespace) -> int:
        """
        Handle the 'reset' command.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        try:
            if args.key:
                # Reset specific key to default
                default_value = self.config_manager.get_default(args.key)
                
                if default_value is None:
                    print(f"Default value for key '{args.key}' not found.")
                    return 1
                
                self.config_manager.set(args.key, default_value)
                self.logger.info(f"Reset '{args.key}' to default value: {default_value}")
                print(f"Successfully reset '{args.key}' to default value: {default_value}")
            else:
                # Reset all configuration
                self.config_manager.reset_to_defaults()
                self.logger.info("Reset all configuration to defaults")
                print("Successfully reset all configuration to defaults")
            
            # Save the changes
            self.config_manager.save()
            return 0
        except Exception as e:
            self.logger.error(f"Error resetting configuration: {str(e)}")
            print(f"Error: {str(e)}")
            return 1
    
    def _handle_export(self, args: argparse.Namespace) -> int:
        """
        Handle the 'export' command.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        try:
            # Get configuration
            config = self.config_manager.get_all()
            
            # Export based on format
            if args.format == 'json':
                with open(args.filename, 'w') as f:
                    json.dump(config, f, indent=2)
            elif args.format == 'ini':
                content = self._config_to_ini(config)
                with open(args.filename, 'w') as f:
                    f.write(content)
            elif args.format == 'env':
                content = self._config_to_env(config)
                with open(args.filename, 'w') as f:
                    f.write(content)
            
            self.logger.info(f"Exported configuration to {args.filename} in {args.format} format")
            print(f"Successfully exported configuration to {args.filename}")
            return 0
        except Exception as e:
            self.logger.error(f"Error exporting configuration: {str(e)}")
            print(f"Error: {str(e)}")
            return 1
    
    def _config_to_ini(self, config: Dict[str, Any]) -> str:
        """
        Convert configuration to INI format.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            INI formatted string
        """
        ini_sections = {}
        
        # Helper function to process nested dictionaries
        def process_section(section_dict, section_prefix=""):
            for key, value in section_dict.items():
                if isinstance(value, dict):
                    # Create a new section
                    section_name = f"{section_prefix}.{key}" if section_prefix else key
                    process_section(value, section_name)
                else:
                    # Add key-value pair to the section
                    section_name = section_prefix if section_prefix else "DEFAULT"
                    
                    if section_name not in ini_sections:
                        ini_sections[section_name] = []
                    
                    # Format value based on type
                    if isinstance(value, bool):
                        formatted_value = str(value).lower()
                    elif isinstance(value, (int, float)):
                        formatted_value = str(value)
                    elif isinstance(value, str):
                        formatted_value = value
                    elif value is None:
                        formatted_value = ""
                    else:
                        formatted_value = str(value)
                    
                    ini_sections[section_name].append(f"{key} = {formatted_value}")
        
        # Process the configuration
        process_section(config)
        
        # Create the INI content
        lines = ["; Forex Trading Dashboard Configuration",
                f"; Exported on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                ""]
        
        for section, entries in sorted(ini_sections.items()):
            if section != "DEFAULT":
                lines.append(f"[{section}]")
            
            for entry in sorted(entries):
                lines.append(entry)
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _config_to_env(self, config: Dict[str, Any]) -> str:
        """
        Convert configuration to environment variables format.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Environment variables formatted string
        """
        env_vars = []
        
        # Helper function to process nested dictionaries
        def process_section(section_dict, prefix=""):
            for key, value in section_dict.items():
                env_key = f"{prefix}_{key}" if prefix else key
                env_key = env_key.upper().replace('.', '_')
                
                if isinstance(value, dict):
                    process_section(value, env_key)
                else:
                    # Format value based on type
                    if isinstance(value, bool):
                        formatted_value = str(value).lower()
                    elif isinstance(value, (int, float)):
                        formatted_value = str(value)
                    elif isinstance(value, str):
                        # Escape quotes in strings
                        formatted_value = f'"{value.replace('"', '\\"')}"'
                    elif value is None:
                        formatted_value = '""'
                    else:
                        formatted_value = f'"{str(value)}"'
                    
                    env_vars.append(f"FOREX_{env_key}={formatted_value}")
        
        # Process the configuration
        process_section(config)
        
        # Create the env content
        lines = ["# Forex Trading Dashboard Environment Variables",
                f"# Exported on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                ""]
        
        lines.extend(sorted(env_vars))
        
        return "\n".join(lines)
    
    def _handle_import(self, args: argparse.Namespace) -> int:
        """
        Handle the 'import' command.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        try:
            # Check if file exists
            if not os.path.isfile(args.filename):
                print(f"Import file '{args.filename}' not found.")
                return 1
            
            # Import configuration
            with open(args.filename, 'r') as f:
                imported_config = json.load(f)
            
            # Update configuration
            if args.merge:
                # Merge with existing configuration
                current_config = self.config_manager.get_all()
                merged_config = self.config_manager.deep_merge(current_config, imported_config)
                self.config_manager.set_all(merged_config)
                self.logger.info(f"Merged configuration from {args.filename}")
                print(f"Successfully merged configuration from {args.filename}")
            else:
                # Replace existing configuration
                self.config_manager.set_all(imported_config)
                self.logger.info(f"Imported configuration from {args.filename}")
                print(f"Successfully imported configuration from {args.filename}")
            
            # Save the changes
            self.config_manager.save()
            return 0
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON format in {args.filename}")
            print(f"Error: Invalid JSON format in {args.filename}")
            return 1
        except Exception as e:
            self.logger.error(f"Error importing configuration: {str(e)}")
            print(f"Error: {str(e)}")
            return 1


def main() -> int:
    """
    Main entry point for the configuration manager CLI.
    
    Returns:
        Exit code
    """
    cli = ConfigManagerCLI()
    return cli.run()


if __name__ == "__main__":
    sys.exit(main()) 