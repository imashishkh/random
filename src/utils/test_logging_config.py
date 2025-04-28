#!/usr/bin/env python3
"""
Forex Trading Dashboard - Logging and Configuration Test Script

This script demonstrates the integration between the configuration manager and
the logging system for the Forex Trading Dashboard.
"""

import os
import time
import sys
from pprint import pprint

# Add the project directory to the path to allow imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import configuration and logging modules
from .config_manager import config_manager
from .logger import logger, info, debug, warning, error, critical, get_logs

def main():
    """Test the configuration management and logging integration."""
    print("\n===== Testing Configuration Management and Logging Integration =====\n")

    # Initialize the configuration manager
    print("Initializing configuration manager...")
    config_manager.initialize()

    # Display current logging configuration
    print("\nCurrent logging configuration:")
    logging_config = config_manager.get_config('logging')
    pprint(logging_config)

    # Log messages at different levels
    print("\nLogging messages at different levels...")
    debug("This is a debug message", component="TestScript", tags=["test", "debug"])
    info("This is an info message", component="TestScript", tags=["test", "info"])
    warning("This is a warning message", component="TestScript", tags=["test", "warning"])
    error("This is an error message", component="TestScript", tags=["test", "error"])
    critical("This is a critical message", component="TestScript", tags=["test", "critical"])

    # Log messages with extra data
    print("\nLogging messages with extra data...")
    info(
        "Processing forex data",
        component="DataProcessor",
        tags=["forex", "data"],
        extra={
            "currency_pair": "EUR/USD",
            "timeframe": "1h",
            "records_processed": 1000
        }
    )

    # Show in-memory logs
    print("\nIn-memory logs:")
    memory_logs = get_logs()
    print(f"Total logs in memory: {len(memory_logs)}")
    
    if memory_logs:
        print("Latest log entry:")
        pprint(memory_logs[-1])

    # Demonstrate filtering logs
    print("\nFiltered logs (component=TestScript):")
    filtered_logs = get_logs(component="TestScript")
    print(f"Total matching logs: {len(filtered_logs)}")

    print("\nFiltered logs (level=ERROR):")
    filtered_logs = get_logs(level="ERROR")
    print(f"Total matching logs: {len(filtered_logs)}")

    # Change logging configuration at runtime
    print("\nChanging logging level to DEBUG...")
    config_manager.set_config('logging.level', 'DEBUG')
    
    # Log a debug message after changing the level
    debug("This debug message should now appear", component="TestScript", tags=["test", "debug"])
    
    # Change other logging settings
    print("\nChanging log format...")
    config_manager.set_config('logging.console_format', 
                            '%(asctime)s [%(levelname)s] <%(message)s>')
    
    # Log another message to show the format change
    info("This message should use the new format", component="TestScript")
    
    # Persist configuration changes
    print("\nPersisting configuration changes...")
    config_manager.set_config('logging.level', 'INFO', persist=True)
    
    # Test environment-specific configuration
    print("\nSwitching to development environment...")
    config_manager.set_environment('development')
    info("Switched to development environment", component="TestScript")
    
    print("\nSwitching to production environment...")
    config_manager.set_environment('production')
    info("Switched to production environment", component="TestScript")
    
    # Reset to default environment
    config_manager.set_environment('development')
    
    print("\n===== Test Complete =====\n")

if __name__ == "__main__":
    main() 