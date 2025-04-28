"""
Configuration Manager for the Performance Monitoring System.

This module provides utilities for loading, validating, and accessing configuration
settings for the trade performance monitoring system.
"""

import os
import json
import logging
import jsonschema
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ConfigManager:
    """
    Manages configuration for the trade performance monitoring system.
    
    This class is responsible for loading configuration from files,
    validating it against a schema, and providing access to the configuration.
    """
    
    def __init__(self, config_path: Optional[str] = None, schema_path: Optional[str] = None):
        """
        Initialize the configuration manager.
        
        Args:
            config_path: Path to the configuration file (optional)
            schema_path: Path to the schema file (optional)
        """
        self.config_path = config_path
        
        # Default schema path if not provided
        if schema_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            schema_path = os.path.join(current_dir, "schema.json")
        
        self.schema_path = schema_path
        self.config = {}
        self.schema = {}
        
        # Load schema
        self._load_schema()
        
        # Load configuration
        if config_path:
            self.load_config(config_path)
        else:
            self._load_default_config()
    
    def _load_schema(self) -> None:
        """Load the schema from file."""
        try:
            with open(self.schema_path, 'r') as f:
                self.schema = json.load(f)
            logger.debug(f"Loaded schema from {self.schema_path}")
        except Exception as e:
            logger.error(f"Error loading schema: {e}")
            raise
    
    def _load_default_config(self) -> None:
        """Load the default configuration."""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            default_config_path = os.path.join(current_dir, "default_config.json")
            
            if os.path.exists(default_config_path):
                self.load_config(default_config_path)
                logger.info(f"Loaded default configuration from {default_config_path}")
            else:
                logger.warning(f"Default configuration file not found: {default_config_path}")
                # Initialize with minimal configuration
                self.config = {
                    "exchanges": ["binance"],
                    "pairs": ["BTC/USDT"]
                }
        except Exception as e:
            logger.error(f"Error loading default configuration: {e}")
            # Initialize with minimal configuration
            self.config = {
                "exchanges": ["binance"],
                "pairs": ["BTC/USDT"]
            }
    
    def load_config(self, config_path: str) -> None:
        """
        Load configuration from file and validate it.
        
        Args:
            config_path: Path to the configuration file
        
        Raises:
            FileNotFoundError: If the configuration file does not exist
            jsonschema.exceptions.ValidationError: If the configuration is invalid
        """
        if not os.path.exists(config_path):
            logger.error(f"Configuration file not found: {config_path}")
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Validate against schema
            self.validate_config(config)
            
            # Store the validated configuration
            self.config = config
            self.config_path = config_path
            
            logger.info(f"Loaded configuration from {config_path}")
        
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing configuration file: {e}")
            raise
        
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            raise
    
    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate configuration against schema.
        
        Args:
            config: Configuration dictionary to validate
        
        Raises:
            jsonschema.exceptions.ValidationError: If the configuration is invalid
        """
        try:
            jsonschema.validate(instance=config, schema=self.schema)
            logger.debug("Configuration validation successful")
        except jsonschema.exceptions.ValidationError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get the complete configuration.
        
        Returns:
            The complete configuration dictionary
        """
        return self.config
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key.
        
        Args:
            key: Configuration key (supports dot notation for nested keys)
            default: Default value to return if key is not found
        
        Returns:
            Configuration value or default if key not found
        """
        # Handle nested keys with dot notation
        if "." in key:
            parts = key.split(".")
            value = self.config
            
            for part in parts:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return default
            
            return value
        
        # Simple key lookup
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value.
        
        Args:
            key: Configuration key (supports dot notation for nested keys)
            value: Value to set
        """
        # Handle nested keys with dot notation
        if "." in key:
            parts = key.split(".")
            config = self.config
            
            # Navigate to the correct nested dictionary
            for part in parts[:-1]:
                if part not in config:
                    config[part] = {}
                config = config[part]
            
            # Set the value
            config[parts[-1]] = value
        
        # Simple key setting
        else:
            self.config[key] = value
    
    def save_config(self, output_path: Optional[str] = None) -> None:
        """
        Save configuration to file.
        
        Args:
            output_path: Path to save the configuration (optional, uses current path if not provided)
        """
        if output_path is None:
            output_path = self.config_path
        
        if output_path is None:
            logger.error("No output path specified for configuration save")
            return
        
        try:
            # Validate before saving
            self.validate_config(self.config)
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Save configuration to file
            with open(output_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            logger.info(f"Saved configuration to {output_path}")
        
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            raise 