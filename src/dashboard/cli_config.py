"""
CLI Configuration Management Module

This module provides CLI commands for managing configuration and
integrates with the dashboard for displaying configuration options.
"""

import os
import sys
import argparse
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union

from ..utils.config_manager import ConfigManager, ConfigValidationError
from ..utils.logging.log_manager import get_log_manager
from ..utils.notification_manager import (
    get_notification_manager, 
    NotificationLevel,
    NotificationChannel
)

class ConfigCLI:
    """CLI interface for configuration management."""
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize the ConfigCLI.
        
        Args:
            config_dir: Directory for configuration files.
        """
        self.config_manager = ConfigManager.get_instance(config_dir=config_dir)
        self.log_manager = get_log_manager()
        self.logger = self.log_manager.get_logger(__name__)
        self.notification_manager = get_notification_manager()
    
    def run(self, args: List[str]) -> int:
        """
        Run the configuration CLI with the given arguments.
        
        Args:
            args: Command line arguments.
            
        Returns:
            Exit code (0 for success, non-zero for failure).
        """
        parser = argparse.ArgumentParser(description="Configuration Management CLI")
        subparsers = parser.add_subparsers(dest="command", help="Command to run")
        
        # Get command
        get_parser = subparsers.add_parser("get", help="Get configuration value(s)")
        get_parser.add_argument("path", nargs="?", help="Configuration path (e.g., 'app.name')")
        
        # Set command
        set_parser = subparsers.add_parser("set", help="Set configuration value")
        set_parser.add_argument("path", help="Configuration path (e.g., 'app.name')")
        set_parser.add_argument("value", help="Value to set")
        set_parser.add_argument("--type", choices=["string", "number", "boolean", "json"], 
                               default="string", help="Value type")
        set_parser.add_argument("--no-validate", action="store_true", 
                               help="Skip validation")
        
        # List command
        list_parser = subparsers.add_parser("list", help="List configuration sections")
        list_parser.add_argument("section", nargs="?", help="Configuration section")
        list_parser.add_argument("--schema", action="store_true", 
                                help="Show schema information")
        
        # Export command
        export_parser = subparsers.add_parser("export", help="Export configuration")
        export_parser.add_argument("file", help="Export file path")
        export_parser.add_argument("--include-schema", action="store_true", 
                                  help="Include schema in export")
        
        # Import command
        import_parser = subparsers.add_parser("import", help="Import configuration")
        import_parser.add_argument("file", help="Import file path")
        import_parser.add_argument("--no-validate", action="store_true", 
                                  help="Skip validation")
        
        # Backup command
        backup_parser = subparsers.add_parser("backup", help="Backup configuration")
        backup_parser.add_argument("name", nargs="?", help="Backup name")
        
        # Restore command
        restore_parser = subparsers.add_parser("restore", help="Restore configuration")
        restore_parser.add_argument("backup_id", help="Backup name or path")
        
        # List backups command
        backups_parser = subparsers.add_parser("backups", help="List available backups")
        
        # Template commands
        templates_parser = subparsers.add_parser("templates", help="Template commands")
        template_subparsers = templates_parser.add_subparsers(dest="template_command", 
                                                             help="Template command")
        
        # List templates
        template_list_parser = template_subparsers.add_parser("list", 
                                                             help="List available templates")
        
        # Save template
        template_save_parser = template_subparsers.add_parser("save", 
                                                             help="Save current config as template")
        template_save_parser.add_argument("name", help="Template name")
        
        # Apply template
        template_apply_parser = template_subparsers.add_parser("apply", 
                                                              help="Apply a template")
        template_apply_parser.add_argument("name", help="Template name")
        template_apply_parser.add_argument("--no-validate", action="store_true", 
                                          help="Skip validation")
        
        # Reset command
        reset_parser = subparsers.add_parser("reset", help="Reset configuration to defaults")
        reset_parser.add_argument("--confirm", action="store_true", 
                                 help="Confirm reset without prompting")
        
        # Validate command
        validate_parser = subparsers.add_parser("validate", help="Validate configuration")
        
        # Parse args
        parsed_args = parser.parse_args(args)
        
        if not parsed_args.command:
            parser.print_help()
            return 1
        
        # Dispatch command
        try:
            if parsed_args.command == "get":
                return self._cmd_get(parsed_args)
            elif parsed_args.command == "set":
                return self._cmd_set(parsed_args)
            elif parsed_args.command == "list":
                return self._cmd_list(parsed_args)
            elif parsed_args.command == "export":
                return self._cmd_export(parsed_args)
            elif parsed_args.command == "import":
                return self._cmd_import(parsed_args)
            elif parsed_args.command == "backup":
                return self._cmd_backup(parsed_args)
            elif parsed_args.command == "restore":
                return self._cmd_restore(parsed_args)
            elif parsed_args.command == "backups":
                return self._cmd_list_backups(parsed_args)
            elif parsed_args.command == "templates":
                return self._cmd_templates(parsed_args)
            elif parsed_args.command == "reset":
                return self._cmd_reset(parsed_args)
            elif parsed_args.command == "validate":
                return self._cmd_validate(parsed_args)
            else:
                print(f"Unknown command: {parsed_args.command}")
                return 1
        except Exception as e:
            print(f"Error: {e}")
            self.logger.error(f"Error in config CLI: {e}", exc_info=True)
            self.notification_manager.notify_error(
                title="Configuration Error",
                message=str(e),
                source="config_cli",
                exception=e
            )
            return 1
    
    def _cmd_get(self, args: argparse.Namespace) -> int:
        """
        Handle the 'get' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        if args.path:
            # Get a specific value
            value = self.config_manager.get(args.path)
            
            if value is None:
                print(f"Configuration path not found: {args.path}")
                return 1
            
            if isinstance(value, (dict, list)):
                print(json.dumps(value, indent=2))
            else:
                print(value)
        else:
            # Get all configuration
            config = self.config_manager.config
            print(json.dumps(config, indent=2))
        
        return 0
    
    def _cmd_set(self, args: argparse.Namespace) -> int:
        """
        Handle the 'set' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        # Parse value based on type
        if args.type == "number":
            try:
                if "." in args.value:
                    value = float(args.value)
                else:
                    value = int(args.value)
            except ValueError:
                print(f"Invalid number: {args.value}")
                return 1
        elif args.type == "boolean":
            value_lower = args.value.lower()
            if value_lower in ("true", "yes", "1", "y"):
                value = True
            elif value_lower in ("false", "no", "0", "n"):
                value = False
            else:
                print(f"Invalid boolean value: {args.value}")
                return 1
        elif args.type == "json":
            try:
                value = json.loads(args.value)
            except json.JSONDecodeError:
                print(f"Invalid JSON: {args.value}")
                return 1
        else:
            # String type
            value = args.value
        
        # Set the value
        try:
            self.config_manager.set(args.path, value, validate=not args.no_validate)
            self.config_manager.save()
            
            print(f"Set {args.path} = {value}")
            
            # Notify about config change
            self.notification_manager.notify_info(
                title="Configuration Changed",
                message=f"Configuration value changed: {args.path}",
                source="config_cli",
                metadata={
                    "path": args.path,
                    "value": str(value)
                }
            )
            
            return 0
        except ConfigValidationError as e:
            print(f"Validation error: {e}")
            return 1
    
    def _cmd_list(self, args: argparse.Namespace) -> int:
        """
        Handle the 'list' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        config = self.config_manager.config
        schema = self.config_manager.schema
        
        if args.section:
            # List a specific section
            parts = args.section.split('.')
            
            # Navigate to the section in config
            section_config = config
            section_schema = schema
            
            for part in parts:
                if part in section_config:
                    section_config = section_config[part]
                else:
                    print(f"Section not found: {args.section}")
                    return 1
                
                if part in section_schema:
                    section_schema = section_schema.get(part, {}).get("properties", {})
                else:
                    section_schema = {}
            
            # Print the section
            if isinstance(section_config, dict):
                # Print as table
                max_key_len = max([len(k) for k in section_config.keys()], default=10)
                
                print(f"\n{args.section} Configuration:")
                print(f"{'-'*80}")
                
                for key, value in sorted(section_config.items()):
                    key_str = key.ljust(max_key_len)
                    
                    # Get schema info for this key
                    if args.schema and key in section_schema:
                        schema_info = section_schema[key]
                        
                        value_type = schema_info.get("type", "unknown")
                        default = schema_info.get("default", "")
                        doc = schema_info.get("doc", "")
                        
                        if isinstance(value, (dict, list)):
                            value_str = f"<{value_type}>"
                        else:
                            value_str = str(value)
                        
                        print(f"{key_str} = {value_str}")
                        
                        if doc:
                            print(f"{' ' * (max_key_len + 3)}{doc}")
                        
                        if default != "":
                            print(f"{' ' * (max_key_len + 3)}Default: {default}")
                        
                        if "enum" in schema_info:
                            print(f"{' ' * (max_key_len + 3)}Allowed values: {schema_info['enum']}")
                        
                        print()
                    else:
                        # Simple key-value format without schema info
                        if isinstance(value, (dict, list)):
                            value_str = json.dumps(value)
                        else:
                            value_str = str(value)
                        
                        print(f"{key_str} = {value_str}")
            else:
                # Just print the value
                if isinstance(section_config, (dict, list)):
                    print(json.dumps(section_config, indent=2))
                else:
                    print(section_config)
        else:
            # List all top-level sections
            print("\nConfiguration Sections:")
            print(f"{'-'*80}")
            
            for section, value in sorted(config.items()):
                if isinstance(value, dict):
                    keys_count = len(value)
                    print(f"{section} ({keys_count} settings)")
                else:
                    print(f"{section} = {value}")
            
            print("\nUse 'config list <section>' to see settings in a section")
        
        return 0
    
    def _cmd_export(self, args: argparse.Namespace) -> int:
        """
        Handle the 'export' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        try:
            success = self.config_manager.export_config(
                args.file,
                include_schema=args.include_schema
            )
            
            if success:
                print(f"Configuration exported to {args.file}")
                return 0
            else:
                print("Failed to export configuration")
                return 1
        except Exception as e:
            print(f"Export error: {e}")
            return 1
    
    def _cmd_import(self, args: argparse.Namespace) -> int:
        """
        Handle the 'import' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        try:
            success = self.config_manager.import_config(
                args.file,
                validate=not args.no_validate
            )
            
            if success:
                print(f"Configuration imported from {args.file}")
                
                # Notify about config import
                self.notification_manager.notify_info(
                    title="Configuration Imported",
                    message=f"Configuration imported from {args.file}",
                    source="config_cli"
                )
                
                return 0
            else:
                print("Failed to import configuration")
                return 1
        except Exception as e:
            print(f"Import error: {e}")
            return 1
    
    def _cmd_backup(self, args: argparse.Namespace) -> int:
        """
        Handle the 'backup' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        try:
            backup_file = self.config_manager.create_backup(args.name)
            print(f"Configuration backed up to {backup_file}")
            return 0
        except Exception as e:
            print(f"Backup error: {e}")
            return 1
    
    def _cmd_restore(self, args: argparse.Namespace) -> int:
        """
        Handle the 'restore' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        try:
            success = self.config_manager.restore_backup(args.backup_id)
            
            if success:
                print(f"Configuration restored from {args.backup_id}")
                
                # Notify about config restore
                self.notification_manager.notify_info(
                    title="Configuration Restored",
                    message=f"Configuration restored from backup: {args.backup_id}",
                    source="config_cli"
                )
                
                return 0
            else:
                print("Failed to restore configuration")
                return 1
        except Exception as e:
            print(f"Restore error: {e}")
            return 1
    
    def _cmd_list_backups(self, args: argparse.Namespace) -> int:
        """
        Handle the 'backups' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        try:
            backups = self.config_manager.list_backups()
            
            if not backups:
                print("No backups found")
                return 0
            
            print("\nAvailable Backups:")
            print(f"{'-'*80}")
            
            for i, backup in enumerate(backups):
                name = backup['name']
                created_at = backup['created_at']
                path = backup['path']
                
                print(f"{i+1}. {name}")
                print(f"   Created: {created_at}")
                print(f"   Path: {path}")
                print()
            
            return 0
        except Exception as e:
            print(f"Error listing backups: {e}")
            return 1
    
    def _cmd_templates(self, args: argparse.Namespace) -> int:
        """
        Handle the 'templates' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        if not args.template_command:
            print("Missing template command. Use 'list', 'save', or 'apply'.")
            return 1
        
        if args.template_command == "list":
            # List templates
            templates = self.config_manager.list_templates()
            
            if not templates:
                print("No templates found")
                return 0
            
            print("\nAvailable Templates:")
            print(f"{'-'*80}")
            
            for i, template in enumerate(templates):
                print(f"{i+1}. {template}")
            
            return 0
            
        elif args.template_command == "save":
            # Save template
            try:
                success = self.config_manager.save_template(args.name)
                
                if success:
                    print(f"Template saved: {args.name}")
                    return 0
                else:
                    print(f"Failed to save template: {args.name}")
                    return 1
            except Exception as e:
                print(f"Error saving template: {e}")
                return 1
                
        elif args.template_command == "apply":
            # Apply template
            try:
                success = self.config_manager.apply_template(
                    args.name,
                    validate=not args.no_validate
                )
                
                if success:
                    print(f"Template applied: {args.name}")
                    
                    # Notify about template application
                    self.notification_manager.notify_info(
                        title="Configuration Template Applied",
                        message=f"Configuration template applied: {args.name}",
                        source="config_cli"
                    )
                    
                    return 0
                else:
                    print(f"Failed to apply template: {args.name}")
                    return 1
            except Exception as e:
                print(f"Error applying template: {e}")
                return 1
        
        else:
            print(f"Unknown template command: {args.template_command}")
            return 1
    
    def _cmd_reset(self, args: argparse.Namespace) -> int:
        """
        Handle the 'reset' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        if not args.confirm:
            response = input("Reset configuration to defaults? This cannot be undone. [y/N] ")
            if response.lower() not in ("y", "yes"):
                print("Reset cancelled")
                return 0
        
        try:
            success = self.config_manager.reset_to_defaults()
            
            if success:
                print("Configuration reset to defaults")
                
                # Notify about config reset
                self.notification_manager.notify_warning(
                    title="Configuration Reset",
                    message="Configuration has been reset to defaults",
                    source="config_cli"
                )
                
                return 0
            else:
                print("Failed to reset configuration")
                return 1
        except Exception as e:
            print(f"Reset error: {e}")
            return 1
    
    def _cmd_validate(self, args: argparse.Namespace) -> int:
        """
        Handle the 'validate' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        try:
            self.config_manager._validate_config()
            print("Configuration is valid")
            return 0
        except ConfigValidationError as e:
            print(f"Validation error: {e}")
            return 1


class LogCLI:
    """CLI interface for log management."""
    
    def __init__(self, log_dir: Optional[str] = None):
        """
        Initialize the LogCLI.
        
        Args:
            log_dir: Directory for log files.
        """
        self.log_manager = get_log_manager(log_dir=log_dir)
        self.logger = self.log_manager.get_logger(__name__)
        self.notification_manager = get_notification_manager()
    
    def run(self, args: List[str]) -> int:
        """
        Run the log CLI with the given arguments.
        
        Args:
            args: Command line arguments.
            
        Returns:
            Exit code (0 for success, non-zero for failure).
        """
        parser = argparse.ArgumentParser(description="Log Management CLI")
        subparsers = parser.add_subparsers(dest="command", help="Command to run")
        
        # Get logs command
        get_parser = subparsers.add_parser("get", help="Get logs")
        get_parser.add_argument("--level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                               help="Filter by log level")
        get_parser.add_argument("--start", help="Start time (YYYY-MM-DD HH:MM:SS)")
        get_parser.add_argument("--end", help="End time (YYYY-MM-DD HH:MM:SS)")
        get_parser.add_argument("--logger", help="Filter by logger name")
        get_parser.add_argument("--search", help="Search text")
        get_parser.add_argument("--limit", type=int, default=100, help="Maximum number of logs")
        get_parser.add_argument("--tail", action="store_true", help="Show most recent logs")
        
        # Export logs command
        export_parser = subparsers.add_parser("export", help="Export logs")
        export_parser.add_argument("file", help="Export file path")
        export_parser.add_argument("--level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                                  help="Filter by log level")
        export_parser.add_argument("--start", help="Start time (YYYY-MM-DD HH:MM:SS)")
        export_parser.add_argument("--end", help="End time (YYYY-MM-DD HH:MM:SS)")
        export_parser.add_argument("--logger", help="Filter by logger name")
        export_parser.add_argument("--search", help="Search text")
        export_parser.add_argument("--format", choices=["json", "csv", "txt"], default="json",
                                  help="Export format")
        
        # Set level command
        level_parser = subparsers.add_parser("level", help="Set log level")
        level_parser.add_argument("level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                                 help="Log level")
        
        # Cleanup command
        cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old logs")
        
        # Stats command
        stats_parser = subparsers.add_parser("stats", help="Show log statistics")
        stats_parser.add_argument("--days", type=int, default=1, help="Number of days")
        
        # Parse args
        parsed_args = parser.parse_args(args)
        
        if not parsed_args.command:
            parser.print_help()
            return 1
        
        # Dispatch command
        try:
            if parsed_args.command == "get":
                return self._cmd_get_logs(parsed_args)
            elif parsed_args.command == "export":
                return self._cmd_export_logs(parsed_args)
            elif parsed_args.command == "level":
                return self._cmd_set_level(parsed_args)
            elif parsed_args.command == "cleanup":
                return self._cmd_cleanup(parsed_args)
            elif parsed_args.command == "stats":
                return self._cmd_stats(parsed_args)
            else:
                print(f"Unknown command: {parsed_args.command}")
                return 1
        except Exception as e:
            print(f"Error: {e}")
            self.logger.error(f"Error in log CLI: {e}", exc_info=True)
            self.notification_manager.notify_error(
                title="Log Error",
                message=str(e),
                source="log_cli",
                exception=e
            )
            return 1
    
    def _cmd_get_logs(self, args: argparse.Namespace) -> int:
        """
        Handle the 'get' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        # Parse time arguments
        start_time = None
        end_time = None
        
        if args.start:
            try:
                start_time = datetime.strptime(args.start, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                print(f"Invalid start time format: {args.start}")
                print("Expected format: YYYY-MM-DD HH:MM:SS")
                return 1
        
        if args.end:
            try:
                end_time = datetime.strptime(args.end, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                print(f"Invalid end time format: {args.end}")
                print("Expected format: YYYY-MM-DD HH:MM:SS")
                return 1
        
        # Convert level to list if provided
        levels = [args.level] if args.level else None
        
        # Convert logger to list if provided
        logger_names = [args.logger] if args.logger else None
        
        try:
            # Get logs
            logs = self.log_manager.get_logs(
                start_time=start_time,
                end_time=end_time,
                levels=levels,
                logger_names=logger_names,
                search_text=args.search,
                limit=args.limit,
                order_by="desc" if args.tail else "asc"
            )
            
            if not logs:
                print("No logs found matching the criteria")
                return 0
            
            # Print logs
            for log in logs:
                timestamp = log.get("timestamp", "")
                level = log.get("level", "UNKNOWN")
                logger_name = log.get("logger", "")
                message = log.get("message", "")
                
                # Color mapping
                level_colors = {
                    "DEBUG": "\033[36m",  # Cyan
                    "INFO": "\033[32m",   # Green
                    "WARNING": "\033[33m", # Yellow
                    "ERROR": "\033[31m",  # Red
                    "CRITICAL": "\033[35m" # Magenta
                }
                
                reset_color = "\033[0m"
                level_color = level_colors.get(level, "\033[0m")
                
                # Format and print
                print(f"{timestamp} {level_color}[{level}]{reset_color} {logger_name}: {message}")
            
            return 0
        except Exception as e:
            print(f"Error getting logs: {e}")
            return 1
    
    def _cmd_export_logs(self, args: argparse.Namespace) -> int:
        """
        Handle the 'export' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        # Parse time arguments
        start_time = None
        end_time = None
        
        if args.start:
            try:
                start_time = datetime.strptime(args.start, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                print(f"Invalid start time format: {args.start}")
                print("Expected format: YYYY-MM-DD HH:MM:SS")
                return 1
        
        if args.end:
            try:
                end_time = datetime.strptime(args.end, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                print(f"Invalid end time format: {args.end}")
                print("Expected format: YYYY-MM-DD HH:MM:SS")
                return 1
        
        # Convert level to list if provided
        levels = [args.level] if args.level else None
        
        # Convert logger to list if provided
        logger_names = [args.logger] if args.logger else None
        
        try:
            # Export logs
            success = self.log_manager.export_logs(
                export_path=args.file,
                start_time=start_time,
                end_time=end_time,
                levels=levels,
                logger_names=logger_names,
                search_text=args.search,
                format=args.format
            )
            
            if success:
                print(f"Logs exported to {args.file}")
                return 0
            else:
                print("Failed to export logs")
                return 1
        except Exception as e:
            print(f"Error exporting logs: {e}")
            return 1
    
    def _cmd_set_level(self, args: argparse.Namespace) -> int:
        """
        Handle the 'level' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        try:
            self.log_manager.set_level(args.level)
            print(f"Log level set to {args.level}")
            return 0
        except Exception as e:
            print(f"Error setting log level: {e}")
            return 1
    
    def _cmd_cleanup(self, args: argparse.Namespace) -> int:
        """
        Handle the 'cleanup' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        try:
            deleted_count = self.log_manager.cleanup_old_logs()
            print(f"Cleaned up {deleted_count} old log files")
            return 0
        except Exception as e:
            print(f"Error cleaning up logs: {e}")
            return 1
    
    def _cmd_stats(self, args: argparse.Namespace) -> int:
        """
        Handle the 'stats' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        try:
            # Calculate time range
            end_time = datetime.now()
            start_time = end_time - timedelta(days=args.days)
            
            # Get stats
            stats = self.log_manager.get_log_stats(
                start_time=start_time,
                end_time=end_time
            )
            
            # Print stats
            print(f"\nLog Statistics for the Last {args.days} Day(s):")
            print(f"{'-'*80}")
            
            print(f"Total Logs: {stats['total_logs']}")
            print(f"Time Range: {stats['start_time']} to {stats['end_time']}")
            print()
            
            # Print by level
            print("Logs by Level:")
            for level_stat in stats['by_level']:
                level = level_stat['level']
                count = level_stat['count']
                
                # Color mapping
                level_colors = {
                    "DEBUG": "\033[36m",  # Cyan
                    "INFO": "\033[32m",   # Green
                    "WARNING": "\033[33m", # Yellow
                    "ERROR": "\033[31m",  # Red
                    "CRITICAL": "\033[35m" # Magenta
                }
                
                reset_color = "\033[0m"
                level_color = level_colors.get(level, "\033[0m")
                
                print(f"  {level_color}{level}{reset_color}: {count}")
            
            print()
            
            # Print top errors
            if stats['top_errors']:
                print("Top Errors:")
                for i, error in enumerate(stats['top_errors']):
                    print(f"  {i+1}. {error['message']} ({error['count']} occurrences)")
                print()
            
            # Print top loggers
            if stats['top_loggers']:
                print("Top Loggers:")
                for i, logger in enumerate(stats['top_loggers']):
                    print(f"  {i+1}. {logger['logger']}: {logger['count']} logs")
                print()
            
            return 0
        except Exception as e:
            print(f"Error getting log stats: {e}")
            return 1


def config_command(args: List[str]) -> int:
    """
    Entry point for the 'config' CLI command.
    
    Args:
        args: Command line arguments.
        
    Returns:
        Exit code.
    """
    cli = ConfigCLI()
    return cli.run(args)


def log_command(args: List[str]) -> int:
    """
    Entry point for the 'log' CLI command.
    
    Args:
        args: Command line arguments.
        
    Returns:
        Exit code.
    """
    cli = LogCLI()
    return cli.run(args) 