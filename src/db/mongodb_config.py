"""
MongoDB configuration for Forex Trading application.

This module provides configuration settings for MongoDB connection
and database parameters. Settings can be loaded from environment variables,
configuration files, or set with defaults.
"""

import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path
import json

# Set up logging
logger = logging.getLogger(__name__)

# Default MongoDB connection parameters
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 27017
DEFAULT_DB_NAME = "forex_trading"
DEFAULT_USERNAME = None
DEFAULT_PASSWORD = None
DEFAULT_AUTH_SOURCE = "admin"
DEFAULT_AUTH_MECHANISM = "SCRAM-SHA-256"

# Connection pool settings
DEFAULT_MIN_POOL_SIZE = 5
DEFAULT_MAX_POOL_SIZE = 10
DEFAULT_MAX_IDLE_TIME_MS = 10000  # 10 seconds
DEFAULT_CONNECT_TIMEOUT_MS = 5000  # 5 seconds
DEFAULT_SERVER_SELECTION_TIMEOUT_MS = 5000  # 5 seconds

# Collection names
COLLECTIONS = {
    "TRADES": "trades",
    "ACCOUNTS": "accounts",
    "STRATEGIES": "strategies",
    "JOURNAL_ENTRIES": "journal_entries"
}

def load_config_from_env() -> Dict[str, Any]:
    """
    Load MongoDB configuration from environment variables.
    
    Returns:
        Dict[str, Any]: MongoDB configuration
    """
    return {
        "host": os.environ.get("MONGODB_HOST", DEFAULT_HOST),
        "port": int(os.environ.get("MONGODB_PORT", DEFAULT_PORT)),
        "db_name": os.environ.get("MONGODB_DB_NAME", DEFAULT_DB_NAME),
        "username": os.environ.get("MONGODB_USERNAME", DEFAULT_USERNAME),
        "password": os.environ.get("MONGODB_PASSWORD", DEFAULT_PASSWORD),
        "auth_source": os.environ.get("MONGODB_AUTH_SOURCE", DEFAULT_AUTH_SOURCE),
        "auth_mechanism": os.environ.get("MONGODB_AUTH_MECHANISM", DEFAULT_AUTH_MECHANISM),
        "min_pool_size": int(os.environ.get("MONGODB_MIN_POOL_SIZE", DEFAULT_MIN_POOL_SIZE)),
        "max_pool_size": int(os.environ.get("MONGODB_MAX_POOL_SIZE", DEFAULT_MAX_POOL_SIZE)),
        "max_idle_time_ms": int(os.environ.get("MONGODB_MAX_IDLE_TIME_MS", DEFAULT_MAX_IDLE_TIME_MS)),
        "connect_timeout_ms": int(os.environ.get("MONGODB_CONNECT_TIMEOUT_MS", DEFAULT_CONNECT_TIMEOUT_MS)),
        "server_selection_timeout_ms": int(os.environ.get("MONGODB_SERVER_SELECTION_TIMEOUT_MS", DEFAULT_SERVER_SELECTION_TIMEOUT_MS)),
    }

def load_config_from_file(config_file: str = None) -> Dict[str, Any]:
    """
    Load MongoDB configuration from a JSON file.
    
    Args:
        config_file (str, optional): Path to the configuration file. 
                                     If None, looks for 'mongodb_config.json' in standard locations.
    
    Returns:
        Dict[str, Any]: MongoDB configuration
    """
    # Default config file locations to check
    default_locations = [
        Path(os.getcwd()) / 'config' / 'mongodb_config.json',
        Path(os.getcwd()) / 'mongodb_config.json',
        Path.home() / '.forex_trading' / 'mongodb_config.json'
    ]
    
    # If config_file is specified, try to load it
    if config_file:
        file_path = Path(config_file)
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load configuration from {config_file}: {str(e)}")
    
    # Try default locations
    for location in default_locations:
        if location.exists():
            try:
                with open(location, 'r') as f:
                    logger.info(f"Loading MongoDB configuration from {location}")
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load configuration from {location}: {str(e)}")
    
    # If no config file is found, return an empty dict
    logger.warning("No MongoDB configuration file found, using environment variables or defaults")
    return {}

def get_mongodb_config(config_file: Optional[str] = None) -> Dict[str, Any]:
    """
    Get MongoDB configuration using environment variables and/or configuration file.
    Environment variables take precedence over configuration file.
    
    Args:
        config_file (Optional[str]): Path to configuration file
        
    Returns:
        Dict[str, Any]: MongoDB configuration
    """
    # Start with defaults from configuration file
    config = load_config_from_file(config_file)
    
    # Override with environment variables if present
    env_config = load_config_from_env()
    config.update({k: v for k, v in env_config.items() if v is not None})
    
    # Ensure required fields have defaults
    for key, default in {
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "db_name": DEFAULT_DB_NAME,
        "min_pool_size": DEFAULT_MIN_POOL_SIZE,
        "max_pool_size": DEFAULT_MAX_POOL_SIZE
    }.items():
        if key not in config or config[key] is None:
            config[key] = default
    
    return config

def save_config_to_file(config: Dict[str, Any], file_path: str) -> bool:
    """
    Save MongoDB configuration to a JSON file.
    
    Args:
        config (Dict[str, Any]): MongoDB configuration
        file_path (str): Path to save the configuration file
        
    Returns:
        bool: True if file was saved successfully, False otherwise
    """
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        
        # Remove password if present for security
        if "password" in config:
            secure_config = config.copy()
            secure_config["password"] = "********" if config["password"] else None
        else:
            secure_config = config
            
        # Save to file
        with open(file_path, 'w') as f:
            json.dump(secure_config, f, indent=4)
            
        logger.info(f"MongoDB configuration saved to {file_path}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to save MongoDB configuration to {file_path}: {str(e)}")
        return False

# Singleton configuration instance
_mongodb_config = None

def get_config(config_file: Optional[str] = None, force_reload: bool = False) -> Dict[str, Any]:
    """
    Get the MongoDB configuration, caching the result for repeated calls.
    
    Args:
        config_file (Optional[str]): Path to configuration file
        force_reload (bool): Force reload the configuration even if cached
        
    Returns:
        Dict[str, Any]: MongoDB configuration
    """
    global _mongodb_config
    
    if _mongodb_config is None or force_reload:
        _mongodb_config = get_mongodb_config(config_file)
        
    return _mongodb_config 