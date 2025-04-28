"""
Forex Trading Dashboard - Log Viewer CLI

This module provides a command-line interface for viewing and filtering logs
from the Forex Trading Dashboard.
"""

import argparse
import sys
import os
import json
import re
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
from tabulate import tabulate
from colorama import init, Fore, Style

# Initialize colorama for cross-platform colored terminal output
init()

# Import the logger
from .logger import forex_logger, ForexLogRecord
from .config_manager import config_manager

# Set up color mapping for log levels
LEVEL_COLORS = {
    "DEBUG": Fore.CYAN,
    "INFO": Fore.GREEN,
    "WARNING": Fore.YELLOW,
    "ERROR": Fore.RED,
    "CRITICAL": Fore.MAGENTA + Style.BRIGHT
}

def format_timestamp(timestamp: float) -> str:
    """
    Format a timestamp to a human-readable string.
    
    Args:
        timestamp: UNIX timestamp
        
    Returns:
        Formatted timestamp string
    """
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def parse_timeframe(timeframe: str) -> Optional[float]:
    """
    Parse a timeframe string to a timestamp.
    
    Args:
        timeframe: String like '1h', '2d', '30m' for hours, days, minutes
        
    Returns:
        Timestamp representing the start time for the timeframe
    """
    if not timeframe:
        return None
        
    pattern = re.compile(r'(\d+)([hdmsy])')
    match = pattern.match(timeframe)
    
    if not match:
        return None
        
    value, unit = match.groups()
    value = int(value)
    
    now = datetime.now()
    
    if unit == 'm':
        start_time = now - timedelta(minutes=value)
    elif unit == 'h':
        start_time = now - timedelta(hours=value)
    elif unit == 'd':
        start_time = now - timedelta(days=value)
    elif unit == 'w':
        start_time = now - timedelta(weeks=value)
    elif unit == 'y':
        start_time = now - timedelta(days=value*365)
    else:
        return None
        
    return start_time.timestamp()

def filter_logs(logs: List[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    """
    Filter logs based on command line arguments.
    
    Args:
        logs: List of log records
        args: Command line arguments
        
    Returns:
        Filtered list of log records
    """
    filtered_logs = logs.copy()
    
    # Filter by log level
    if args.level:
        level = args.level.upper()
        filtered_logs = [log for log in filtered_logs if log['level'] == level]
    
    # Filter by minimum log level
    if args.min_level:
        levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        min_idx = levels.index(args.min_level.upper())
        filtered_logs = [log for log in filtered_logs if levels.index(log['level']) >= min_idx]
    
    # Filter by time range
    if args.since:
        since_time = parse_timeframe(args.since)
        if since_time:
            filtered_logs = [log for log in filtered_logs if log['created'] >= since_time]
    
    # Filter by component
    if args.component:
        filtered_logs = [log for log in filtered_logs if 
                         log.get('component', '').lower() == args.component.lower()]
    
    # Filter by tag
    if args.tag:
        filtered_logs = [log for log in filtered_logs if 
                         args.tag.lower() in [t.lower() for t in log.get('tags', [])]]
    
    # Search text in message
    if args.search:
        search_term = args.search.lower()
        filtered_logs = [log for log in filtered_logs if 
                         search_term in log['message'].lower() or
                         search_term in json.dumps(log.get('extra', {})).lower()]
    
    # Limit the number of logs
    if args.limit and len(filtered_logs) > args.limit:
        filtered_logs = filtered_logs[-args.limit:]
    
    return filtered_logs

def print_logs_table(logs: List[Dict[str, Any]], args: argparse.Namespace):
    """
    Print logs as a formatted table.
    
    Args:
        logs: List of log records
        args: Command line arguments
    """
    if not logs:
        print("No logs found matching the criteria.")
        return
    
    # Prepare table data
    table_data = []
    
    for log in logs:
        time_str = format_timestamp(log['created'])
        level = log['level']
        component = log.get('component', '')
        message = log['message']
        
        # Truncate message if it's too long
        if args.truncate and len(message) > args.truncate:
            message = message[:args.truncate] + "..."
        
        # Add color to level
        colored_level = f"{LEVEL_COLORS.get(level, '')}{level}{Style.RESET_ALL}"
        
        # Create row
        row = [time_str, colored_level, component, message]
        
        # Add extra info if requested
        if args.extra and log.get('extra'):
            extra_str = json.dumps(log['extra'], indent=2)
            row.append(extra_str)
            
        table_data.append(row)
    
    # Define headers
    headers = ["Timestamp", "Level", "Component", "Message"]
    if args.extra:
        headers.append("Extra Info")
    
    # Print table
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    print(f"\nTotal logs: {len(logs)}")

def print_logs_json(logs: List[Dict[str, Any]], args: argparse.Namespace):
    """
    Print logs as JSON.
    
    Args:
        logs: List of log records
        args: Command line arguments
    """
    if not logs:
        print("[]")
        return
        
    # Convert timestamp to string for better readability
    for log in logs:
        log['created'] = format_timestamp(log['created'])
    
    print(json.dumps(logs, indent=args.json_indent))

def main():
    """
    Main entry point for the log viewer CLI.
    """
    parser = argparse.ArgumentParser(description="Forex Trading Dashboard Log Viewer")
    
    parser.add_argument("-l", "--level", help="Filter by exact log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    parser.add_argument("-m", "--min-level", help="Filter by minimum log level")
    parser.add_argument("-s", "--since", help="Show logs since time frame (e.g., 1h, 2d, 30m)")
    parser.add_argument("-c", "--component", help="Filter by component name")
    parser.add_argument("-t", "--tag", help="Filter by tag")
    parser.add_argument("-S", "--search", help="Search text in log messages")
    parser.add_argument("-n", "--limit", type=int, default=100, help="Limit number of logs (default: 100)")
    parser.add_argument("-f", "--follow", action="store_true", help="Follow log output")
    parser.add_argument("-j", "--json", action="store_true", help="Output as JSON")
    parser.add_argument("--json-indent", type=int, default=2, help="JSON indentation level")
    parser.add_argument("-e", "--extra", action="store_true", help="Show extra information")
    parser.add_argument("--truncate", type=int, default=0, help="Truncate message to specified length")
    parser.add_argument("--clear", action="store_true", help="Clear in-memory logs after viewing")
    
    args = parser.parse_args()
    
    # Use follow mode
    if args.follow:
        try:
            last_displayed_log_idx = -1
            while True:
                # Get all logs
                logs = forex_logger.get_logs()
                
                # Check if there are new logs
                if logs and len(logs) > last_displayed_log_idx + 1:
                    # Filter new logs
                    new_logs = logs[last_displayed_log_idx + 1:]
                    filtered_logs = filter_logs(new_logs, args)
                    
                    # Display new logs
                    if filtered_logs:
                        if args.json:
                            print_logs_json(filtered_logs, args)
                        else:
                            print_logs_table(filtered_logs, args)
                    
                    # Update last displayed log index
                    last_displayed_log_idx = len(logs) - 1
                
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nLog viewing stopped.")
    else:
        # Get logs
        logs = forex_logger.get_logs()
        
        # Filter logs
        filtered_logs = filter_logs(logs, args)
        
        # Display logs
        if args.json:
            print_logs_json(filtered_logs, args)
        else:
            print_logs_table(filtered_logs, args)
        
        # Clear logs if requested
        if args.clear:
            forex_logger.clear_logs()
            print("In-memory logs cleared.")

if __name__ == "__main__":
    main() 