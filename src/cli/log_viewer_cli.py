"""
Forex Trading Dashboard - Log Viewer CLI

This module provides a command-line interface for viewing and managing logs.
It allows users to view, filter, search, and export logs with various formatting options.
"""

import os
import sys
import json
import argparse
import datetime
from typing import Dict, List, Any, Optional, Set
import re
import csv

from ..utils.logger import logger, ForexLogger

class LogViewerCLI:
    """Command-line interface for viewing and managing logs."""
    
    def __init__(self):
        """Initialize the LogViewerCLI."""
        self.logger = logger
        self.forex_logger = ForexLogger.get_instance()
    
    def run(self, args: Optional[List[str]] = None) -> int:
        """
        Run the log viewer CLI.
        
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
            description='Forex Trading Dashboard Log Viewer',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Show the most recent logs
  python -m src.cli.log_viewer_cli show
  
  # Show logs with specific level
  python -m src.cli.log_viewer_cli show --level ERROR
  
  # Search logs for a pattern
  python -m src.cli.log_viewer_cli search "API request failed"
  
  # Export logs to a file
  python -m src.cli.log_viewer_cli export logs.txt
  
  # Clear all logs
  python -m src.cli.log_viewer_cli clear
"""
        )
        
        # Create subparsers for commands
        subparsers = parser.add_subparsers(dest='command', help='Command to execute')
        
        # Show command
        show_parser = subparsers.add_parser('show', help='Show logs')
        show_parser.add_argument('--level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                              help='Filter by log level')
        show_parser.add_argument('--tag', help='Filter by tag')
        show_parser.add_argument('--from', dest='from_date', help='Show logs from date (YYYY-MM-DD)')
        show_parser.add_argument('--to', dest='to_date', help='Show logs to date (YYYY-MM-DD)')
        show_parser.add_argument('--component', help='Filter by component')
        show_parser.add_argument('--limit', type=int, default=50, help='Limit number of logs (default: 50)')
        show_parser.add_argument('--offset', type=int, default=0, help='Offset for pagination')
        show_parser.add_argument('--format', choices=['text', 'json', 'minimal'], default='text',
                              help='Output format (default: text)')
        show_parser.set_defaults(func=self._handle_show)
        
        # Search command
        search_parser = subparsers.add_parser('search', help='Search logs for a pattern')
        search_parser.add_argument('pattern', help='Search pattern')
        search_parser.add_argument('--regex', action='store_true', help='Use regular expression for search')
        search_parser.add_argument('--case-sensitive', action='store_true', help='Case sensitive search')
        search_parser.add_argument('--level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                                help='Filter by log level')
        search_parser.add_argument('--tag', help='Filter by tag')
        search_parser.add_argument('--from', dest='from_date', help='Show logs from date (YYYY-MM-DD)')
        search_parser.add_argument('--to', dest='to_date', help='Show logs to date (YYYY-MM-DD)')
        search_parser.add_argument('--component', help='Filter by component')
        search_parser.add_argument('--limit', type=int, default=50, help='Limit number of logs (default: 50)')
        search_parser.add_argument('--format', choices=['text', 'json', 'minimal'], default='text',
                                help='Output format (default: text)')
        search_parser.set_defaults(func=self._handle_search)
        
        # Export command
        export_parser = subparsers.add_parser('export', help='Export logs to a file')
        export_parser.add_argument('filename', help='Export filename')
        export_parser.add_argument('--format', choices=['text', 'json', 'csv'], default='text',
                                help='Export format (default: text)')
        export_parser.add_argument('--level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                                help='Filter by log level')
        export_parser.add_argument('--tag', help='Filter by tag')
        export_parser.add_argument('--from', dest='from_date', help='Show logs from date (YYYY-MM-DD)')
        export_parser.add_argument('--to', dest='to_date', help='Show logs to date (YYYY-MM-DD)')
        export_parser.add_argument('--component', help='Filter by component')
        export_parser.add_argument('--pattern', help='Search pattern')
        export_parser.add_argument('--regex', action='store_true', help='Use regular expression for search')
        export_parser.add_argument('--case-sensitive', action='store_true', help='Case sensitive search')
        export_parser.set_defaults(func=self._handle_export)
        
        # Clear command
        clear_parser = subparsers.add_parser('clear', help='Clear logs')
        clear_parser.add_argument('--level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                               help='Clear logs with specific level')
        clear_parser.add_argument('--tag', help='Clear logs with specific tag')
        clear_parser.add_argument('--from', dest='from_date', help='Clear logs from date (YYYY-MM-DD)')
        clear_parser.add_argument('--to', dest='to_date', help='Clear logs to date (YYYY-MM-DD)')
        clear_parser.add_argument('--component', help='Clear logs with specific component')
        clear_parser.add_argument('--confirm', action='store_true', help='Skip confirmation')
        clear_parser.set_defaults(func=self._handle_clear)
        
        # Stats command
        stats_parser = subparsers.add_parser('stats', help='Show log statistics')
        stats_parser.add_argument('--from', dest='from_date', help='Stats from date (YYYY-MM-DD)')
        stats_parser.add_argument('--to', dest='to_date', help='Stats to date (YYYY-MM-DD)')
        stats_parser.add_argument('--format', choices=['text', 'json'], default='text',
                               help='Output format (default: text)')
        stats_parser.set_defaults(func=self._handle_stats)
        
        # Tags command
        tags_parser = subparsers.add_parser('tags', help='List all log tags')
        tags_parser.set_defaults(func=self._handle_tags)
        
        # Components command
        components_parser = subparsers.add_parser('components', help='List all log components')
        components_parser.set_defaults(func=self._handle_components)
        
        # Level command
        level_parser = subparsers.add_parser('level', help='Get or set the current log level')
        level_parser.add_argument('new_level', nargs='?', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                               help='New log level to set')
        level_parser.set_defaults(func=self._handle_level)
        
        return parser
    
    def _get_filtered_logs(self, args: argparse.Namespace) -> List[Dict[str, Any]]:
        """
        Get filtered logs based on the provided arguments.
        
        Args:
            args: Parsed arguments
            
        Returns:
            List of log records
        """
        # Build filter criteria
        filters = {}
        
        if hasattr(args, 'level') and args.level:
            filters['level'] = args.level
        
        if hasattr(args, 'tag') and args.tag:
            filters['tag'] = args.tag
        
        if hasattr(args, 'from_date') and args.from_date:
            try:
                from_date = datetime.datetime.strptime(args.from_date, '%Y-%m-%d')
                filters['from_time'] = from_date.timestamp()
            except ValueError:
                print(f"Error: Invalid from date format. Use YYYY-MM-DD.")
                return []
        
        if hasattr(args, 'to_date') and args.to_date:
            try:
                to_date = datetime.datetime.strptime(args.to_date, '%Y-%m-%d')
                # Set to end of day
                to_date = to_date.replace(hour=23, minute=59, second=59)
                filters['to_time'] = to_date.timestamp()
            except ValueError:
                print(f"Error: Invalid to date format. Use YYYY-MM-DD.")
                return []
        
        if hasattr(args, 'component') and args.component:
            filters['component'] = args.component
        
        # Get logs with filters
        logs = self.forex_logger.get_logs(filters)
        
        # Apply search pattern if provided
        if hasattr(args, 'pattern') and args.pattern:
            pattern = args.pattern
            is_regex = getattr(args, 'regex', False)
            case_sensitive = getattr(args, 'case_sensitive', False)
            
            filtered_logs = []
            
            for log in logs:
                message = log.get('message', '')
                
                if is_regex:
                    # Use regular expression
                    flags = 0 if case_sensitive else re.IGNORECASE
                    if re.search(pattern, message, flags):
                        filtered_logs.append(log)
                else:
                    # Use simple string search
                    if not case_sensitive:
                        if pattern.lower() in message.lower():
                            filtered_logs.append(log)
                    else:
                        if pattern in message:
                            filtered_logs.append(log)
            
            logs = filtered_logs
        
        # Apply pagination if needed
        limit = getattr(args, 'limit', 0)
        offset = getattr(args, 'offset', 0)
        
        if offset > 0 and offset < len(logs):
            logs = logs[offset:]
        
        if limit > 0 and limit < len(logs):
            logs = logs[:limit]
        
        return logs
    
    def _format_logs(self, logs: List[Dict[str, Any]], format_type: str) -> str:
        """
        Format logs for display.
        
        Args:
            logs: List of log records
            format_type: Format type (text, json, minimal)
            
        Returns:
            Formatted logs as a string
        """
        if format_type == 'json':
            return json.dumps(logs, indent=2)
        
        elif format_type == 'minimal':
            lines = []
            for log in logs:
                level = log.get('level', '')
                time_str = datetime.datetime.fromtimestamp(log.get('created', 0)).strftime('%H:%M:%S')
                message = log.get('message', '')
                lines.append(f"{time_str} [{level[0]}] {message}")
            return "\n".join(lines)
        
        else:  # text
            lines = []
            for log in logs:
                level = log.get('level', '')
                time_str = datetime.datetime.fromtimestamp(log.get('created', 0)).strftime('%Y-%m-%d %H:%M:%S')
                message = log.get('message', '')
                component = log.get('component', '')
                tag = log.get('tag', '')
                
                line = f"{time_str} [{level}]"
                
                if component:
                    line += f" [{component}]"
                
                if tag:
                    line += f" ({tag})"
                
                line += f": {message}"
                lines.append(line)
            
            return "\n".join(lines)
    
    def _handle_show(self, args: argparse.Namespace) -> int:
        """
        Handle the 'show' command.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        try:
            logs = self._get_filtered_logs(args)
            
            if not logs:
                print("No logs found matching the criteria.")
                return 0
            
            # Format and print logs
            formatted_logs = self._format_logs(logs, args.format)
            print(formatted_logs)
            
            print(f"\nShowing {len(logs)} log entries.")
            return 0
        except Exception as e:
            self.logger.error(f"Error showing logs: {str(e)}")
            print(f"Error: {str(e)}")
            return 1
    
    def _handle_search(self, args: argparse.Namespace) -> int:
        """
        Handle the 'search' command.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        try:
            logs = self._get_filtered_logs(args)
            
            if not logs:
                print(f"No logs found matching the search pattern '{args.pattern}'.")
                return 0
            
            # Format and print logs
            formatted_logs = self._format_logs(logs, args.format)
            print(formatted_logs)
            
            print(f"\nFound {len(logs)} log entries matching '{args.pattern}'.")
            return 0
        except Exception as e:
            self.logger.error(f"Error searching logs: {str(e)}")
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
            logs = self._get_filtered_logs(args)
            
            if not logs:
                print("No logs found matching the criteria.")
                return 0
            
            # Export logs based on format
            if args.format == 'json':
                with open(args.filename, 'w') as f:
                    json.dump(logs, f, indent=2)
            
            elif args.format == 'csv':
                with open(args.filename, 'w', newline='') as f:
                    # Get all possible field names
                    fieldnames = set()
                    for log in logs:
                        fieldnames.update(log.keys())
                    
                    writer = csv.DictWriter(f, fieldnames=sorted(fieldnames))
                    writer.writeheader()
                    writer.writerows(logs)
            
            else:  # text
                with open(args.filename, 'w') as f:
                    f.write(self._format_logs(logs, 'text'))
            
            print(f"Exported {len(logs)} log entries to {args.filename}")
            self.logger.info(f"Exported {len(logs)} log entries to {args.filename}")
            return 0
        except Exception as e:
            self.logger.error(f"Error exporting logs: {str(e)}")
            print(f"Error: {str(e)}")
            return 1
    
    def _handle_clear(self, args: argparse.Namespace) -> int:
        """
        Handle the 'clear' command.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        try:
            # Build filter criteria for logs to clear
            filters = {}
            
            if args.level:
                filters['level'] = args.level
            
            if args.tag:
                filters['tag'] = args.tag
            
            if args.from_date:
                try:
                    from_date = datetime.datetime.strptime(args.from_date, '%Y-%m-%d')
                    filters['from_time'] = from_date.timestamp()
                except ValueError:
                    print(f"Error: Invalid from date format. Use YYYY-MM-DD.")
                    return 1
            
            if args.to_date:
                try:
                    to_date = datetime.datetime.strptime(args.to_date, '%Y-%m-%d')
                    # Set to end of day
                    to_date = to_date.replace(hour=23, minute=59, second=59)
                    filters['to_time'] = to_date.timestamp()
                except ValueError:
                    print(f"Error: Invalid to date format. Use YYYY-MM-DD.")
                    return 1
            
            if args.component:
                filters['component'] = args.component
            
            # Get count of logs to clear
            logs_to_clear = self._get_filtered_logs(args)
            count = len(logs_to_clear)
            
            if count == 0:
                print("No logs found matching the criteria.")
                return 0
            
            # Confirm before clearing
            if not args.confirm:
                confirm = input(f"Are you sure you want to clear {count} log entries? [y/N] ")
                if confirm.lower() not in ['y', 'yes']:
                    print("Operation cancelled.")
                    return 0
            
            # Clear logs
            self.forex_logger.clear_logs(filters)
            
            print(f"Cleared {count} log entries.")
            self.logger.info(f"Cleared {count} log entries with filters: {filters}")
            return 0
        except Exception as e:
            self.logger.error(f"Error clearing logs: {str(e)}")
            print(f"Error: {str(e)}")
            return 1
    
    def _handle_stats(self, args: argparse.Namespace) -> int:
        """
        Handle the 'stats' command.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        try:
            # Build filter criteria
            filters = {}
            
            if args.from_date:
                try:
                    from_date = datetime.datetime.strptime(args.from_date, '%Y-%m-%d')
                    filters['from_time'] = from_date.timestamp()
                except ValueError:
                    print(f"Error: Invalid from date format. Use YYYY-MM-DD.")
                    return 1
            
            if args.to_date:
                try:
                    to_date = datetime.datetime.strptime(args.to_date, '%Y-%m-%d')
                    # Set to end of day
                    to_date = to_date.replace(hour=23, minute=59, second=59)
                    filters['to_time'] = to_date.timestamp()
                except ValueError:
                    print(f"Error: Invalid to date format. Use YYYY-MM-DD.")
                    return 1
            
            # Get logs
            logs = self._get_filtered_logs(args)
            
            if not logs:
                print("No logs found matching the criteria.")
                return 0
            
            # Calculate statistics
            stats = {
                'total_logs': len(logs),
                'levels': {},
                'tags': {},
                'components': {},
                'time_period': {
                    'first_log': None,
                    'last_log': None,
                },
                'hourly_distribution': {str(h).zfill(2): 0 for h in range(24)},
            }
            
            first_timestamp = float('inf')
            last_timestamp = 0
            
            for log in logs:
                # Count by level
                level = log.get('level', 'UNKNOWN')
                stats['levels'][level] = stats['levels'].get(level, 0) + 1
                
                # Count by tag
                tag = log.get('tag', 'UNTAGGED')
                stats['tags'][tag] = stats['tags'].get(tag, 0) + 1
                
                # Count by component
                component = log.get('component', 'UNKNOWN')
                stats['components'][component] = stats['components'].get(component, 0) + 1
                
                # Track time period
                timestamp = log.get('created', 0)
                first_timestamp = min(first_timestamp, timestamp)
                last_timestamp = max(last_timestamp, timestamp)
                
                # Track hourly distribution
                hour = datetime.datetime.fromtimestamp(timestamp).hour
                hour_key = str(hour).zfill(2)
                stats['hourly_distribution'][hour_key] = stats['hourly_distribution'].get(hour_key, 0) + 1
            
            # Set time period
            if first_timestamp < float('inf'):
                stats['time_period']['first_log'] = datetime.datetime.fromtimestamp(first_timestamp).strftime('%Y-%m-%d %H:%M:%S')
            
            if last_timestamp > 0:
                stats['time_period']['last_log'] = datetime.datetime.fromtimestamp(last_timestamp).strftime('%Y-%m-%d %H:%M:%S')
            
            # Sort dictionaries for better readability
            stats['levels'] = dict(sorted(stats['levels'].items()))
            stats['tags'] = dict(sorted(stats['tags'].items(), key=lambda x: x[1], reverse=True))
            stats['components'] = dict(sorted(stats['components'].items(), key=lambda x: x[1], reverse=True))
            
            # Format and output statistics
            if args.format == 'json':
                print(json.dumps(stats, indent=2))
            else:
                print("Log Statistics:")
                print(f"Total logs: {stats['total_logs']}")
                
                if stats['time_period']['first_log']:
                    print(f"Time period: {stats['time_period']['first_log']} to {stats['time_period']['last_log']}")
                
                print("\nLog Levels:")
                for level, count in stats['levels'].items():
                    percentage = (count / stats['total_logs']) * 100
                    print(f"  {level}: {count} ({percentage:.1f}%)")
                
                print("\nTop Tags:")
                tag_items = list(stats['tags'].items())
                for tag, count in tag_items[:10]:
                    percentage = (count / stats['total_logs']) * 100
                    print(f"  {tag}: {count} ({percentage:.1f}%)")
                
                if len(tag_items) > 10:
                    print(f"  ... and {len(tag_items) - 10} more")
                
                print("\nTop Components:")
                component_items = list(stats['components'].items())
                for component, count in component_items[:10]:
                    percentage = (count / stats['total_logs']) * 100
                    print(f"  {component}: {count} ({percentage:.1f}%)")
                
                if len(component_items) > 10:
                    print(f"  ... and {len(component_items) - 10} more")
                
                print("\nHourly Distribution:")
                max_count = max(stats['hourly_distribution'].values())
                for hour, count in sorted(stats['hourly_distribution'].items()):
                    if count > 0:
                        bar_width = 50
                        bar = "#" * int((count / max_count) * bar_width)
                        print(f"  {hour}:00 - {hour}:59: {count.rjust(5)} {bar}")
            
            return 0
        except Exception as e:
            self.logger.error(f"Error generating log statistics: {str(e)}")
            print(f"Error: {str(e)}")
            return 1
    
    def _handle_tags(self, args: argparse.Namespace) -> int:
        """
        Handle the 'tags' command.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        try:
            # Get all logs
            logs = self._get_filtered_logs(args)
            
            # Extract unique tags
            tags: Set[str] = set()
            for log in logs:
                tag = log.get('tag')
                if tag:
                    tags.add(tag)
            
            # Sort tags
            sorted_tags = sorted(tags)
            
            if not sorted_tags:
                print("No tags found in logs.")
                return 0
            
            print("Available log tags:")
            for tag in sorted_tags:
                print(f"  {tag}")
            
            print(f"\nTotal: {len(sorted_tags)} unique tags")
            return 0
        except Exception as e:
            self.logger.error(f"Error listing tags: {str(e)}")
            print(f"Error: {str(e)}")
            return 1
    
    def _handle_components(self, args: argparse.Namespace) -> int:
        """
        Handle the 'components' command.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        try:
            # Get all logs
            logs = self._get_filtered_logs(args)
            
            # Extract unique components
            components: Set[str] = set()
            for log in logs:
                component = log.get('component')
                if component:
                    components.add(component)
            
            # Sort components
            sorted_components = sorted(components)
            
            if not sorted_components:
                print("No components found in logs.")
                return 0
            
            print("Available log components:")
            for component in sorted_components:
                print(f"  {component}")
            
            print(f"\nTotal: {len(sorted_components)} unique components")
            return 0
        except Exception as e:
            self.logger.error(f"Error listing components: {str(e)}")
            print(f"Error: {str(e)}")
            return 1
    
    def _handle_level(self, args: argparse.Namespace) -> int:
        """
        Handle the 'level' command.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        try:
            if args.new_level:
                # Set new log level
                self.forex_logger.set_level(args.new_level)
                print(f"Log level set to {args.new_level}")
                self.logger.info(f"Log level changed to {args.new_level}")
            else:
                # Show current log level
                current_level = self.forex_logger.get_level()
                print(f"Current log level: {current_level}")
            
            return 0
        except Exception as e:
            self.logger.error(f"Error handling log level: {str(e)}")
            print(f"Error: {str(e)}")
            return 1


def main() -> int:
    """
    Main entry point for the log viewer CLI.
    
    Returns:
        Exit code
    """
    cli = LogViewerCLI()
    return cli.run()


if __name__ == "__main__":
    sys.exit(main()) 