#!/usr/bin/env python3
"""
Forex Trading Dashboard - Setup Script

This script performs initial setup tasks for the Forex Trading Dashboard,
including initializing configurations and setting up logging.
"""

import os
import sys
import argparse
from pathlib import Path

# Add the project directory to the path to allow imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_dir)

# Import the configuration manager and logger
from .config_manager import config_manager
from .logger import logger, info, warning, error

def setup_config_directories():
    """Create necessary configuration directories."""
    # Define directories
    config_dir = os.path.join(project_dir, 'config')
    data_dir = os.path.join(project_dir, 'data')
    logs_dir = os.path.join(project_dir, 'logs')
    
    # Create directories
    for directory in [config_dir, data_dir, logs_dir]:
        os.makedirs(directory, exist_ok=True)
        info(f"Created directory: {directory}", component="Setup")
    
    return config_dir

def setup_environments(config_dir, environments=None):
    """
    Create environment-specific configuration files if they don't exist.
    
    Args:
        config_dir: Configuration directory
        environments: List of environments to create
    """
    if environments is None:
        environments = ['development', 'testing', 'production']
    
    # Initialize configuration manager
    config_manager.initialize()
    
    # Get the default configuration
    default_config = config_manager.get_config()
    
    # Create environment-specific configuration files if they don't exist
    for env in environments:
        env_config_file = os.path.join(config_dir, f'config.{env}.yaml')
        
        if not os.path.exists(env_config_file):
            info(f"Creating environment configuration: {env}", component="Setup")
            
            # Create an empty environment config file
            with open(env_config_file, 'w') as f:
                f.write(f"# Forex Trading Dashboard - {env.capitalize()} Environment Configuration\n\n")
                f.write(f"# This configuration file contains {env}-specific settings\n")
                f.write("# that override the default configuration.\n\n")
                
                # Add some environment-specific settings as examples
                if env == 'development':
                    f.write("logging:\n")
                    f.write("  level: DEBUG\n")
                    f.write("  console_enabled: true\n\n")
                    f.write("development:\n")
                    f.write("  enable_mocks: true\n")
                    f.write("  hot_reload: true\n")
                elif env == 'testing':
                    f.write("logging:\n")
                    f.write("  level: DEBUG\n")
                    f.write("  console_enabled: true\n\n")
                    f.write("database:\n")
                    f.write("  type: sqlite\n")
                    f.write("  path: data/forex_test.db\n")
                elif env == 'production':
                    f.write("logging:\n")
                    f.write("  level: WARNING\n")
                    f.write("  console_enabled: false\n")
                    f.write("  file_enabled: true\n")
                    f.write("  json_enabled: true\n")
            
            info(f"Created environment configuration: {env_config_file}", component="Setup")
        else:
            info(f"Environment configuration already exists: {env}", component="Setup")

def main():
    """Run the setup script."""
    parser = argparse.ArgumentParser(description="Set up the Forex Trading Dashboard")
    parser.add_argument("--env", default="development", 
                       help="Environment (development, testing, production)")
    parser.add_argument("--setup-all-envs", action="store_true",
                       help="Set up configuration for all environments")
    args = parser.parse_args()
    
    print("Starting Forex Trading Dashboard setup...")
    
    # Initialize configuration manager
    config_manager.initialize()
    
    # Set up directories
    config_dir = setup_config_directories()
    
    # Set up environments
    if args.setup_all_envs:
        setup_environments(config_dir)
    else:
        setup_environments(config_dir, [args.env])
    
    # Set the environment
    config_manager.set_environment(args.env)
    
    # Log success
    info(f"Setup complete. Environment: {args.env}", component="Setup")
    print(f"\nSetup complete. Environment: {args.env}")
    print(f"Configuration directory: {config_dir}")

if __name__ == "__main__":
    main() 