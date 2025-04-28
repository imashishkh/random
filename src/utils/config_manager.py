"""
Forex Trading Dashboard - Configuration Management System

This module provides a configuration management system for the Forex Trading
Dashboard, allowing centralized configuration with support for different
environments, user-specific settings, and runtime configuration changes.
"""

import os
import json
import yaml
import threading
from typing import Dict, Any, List, Optional, Union, Callable
from pathlib import Path
import copy

# Define default configuration paths
DEFAULT_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config')
DEFAULT_CONFIG_FILE = os.path.join(DEFAULT_CONFIG_DIR, 'config.yaml')
USER_CONFIG_FILE = os.path.join(DEFAULT_CONFIG_DIR, 'user_config.yaml')

class ConfigManager:
    """
    Configuration manager for the Forex Trading Dashboard.
    
    Provides methods for loading, accessing, and modifying configuration settings.
    Supports environment-specific configuration and user overrides.
    """
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance of ConfigManager."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.initialize()
        return cls._instance
    
    def __init__(self):
        """Initialize the configuration manager with default settings."""
        # Initialize the configuration dictionaries
        self._default_config: Dict[str, Any] = {}
        self._user_config: Dict[str, Any] = {}
        self._runtime_config: Dict[str, Any] = {}
        self._env_config: Dict[str, Any] = {}
        
        # Combined configuration (computed property)
        self._config: Dict[str, Any] = {}
        
        # Configuration change callbacks
        self._callbacks: Dict[str, List[Callable[[str, Any], None]]] = {}
        
        # Thread lock for thread safety
        self._lock = threading.RLock()
        
        # Environment
        self._environment = os.environ.get('FOREX_ENV', 'development')
        
        # Flag to track if initialization is complete
        self._initialized = False
    
    def initialize(self, config_dir: Optional[str] = None, 
                  config_file: Optional[str] = None,
                  user_config_file: Optional[str] = None,
                  environment: Optional[str] = None) -> None:
        """
        Initialize the configuration system.
        
        Args:
            config_dir: Configuration directory
            config_file: Default configuration file
            user_config_file: User configuration file
            environment: Environment name
        """
        with self._lock:
            # Set environment
            if environment:
                self._environment = environment
            
            # Determine file paths
            config_dir = config_dir or DEFAULT_CONFIG_DIR
            config_file = config_file or DEFAULT_CONFIG_FILE
            user_config_file = user_config_file or USER_CONFIG_FILE
            
            # Ensure config directory exists
            os.makedirs(config_dir, exist_ok=True)
            
            # Load default configuration
            if os.path.exists(config_file):
                self._default_config = self._load_yaml_file(config_file)
            else:
                # Create default configuration if it doesn't exist
                self._default_config = self._create_default_config()
                self._save_yaml_file(config_file, self._default_config)
            
            # Load user configuration if it exists
            if os.path.exists(user_config_file):
                self._user_config = self._load_yaml_file(user_config_file)
            
            # Load environment configuration if it exists
            env_config_file = os.path.join(config_dir, f'config.{self._environment}.yaml')
            if os.path.exists(env_config_file):
                self._env_config = self._load_yaml_file(env_config_file)
            
            # Merge configurations
            self._update_config()
            
            # Mark as initialized
            self._initialized = True
    
    def _load_yaml_file(self, file_path: str) -> Dict[str, Any]:
        """
        Load configuration from a YAML file.
        
        Args:
            file_path: Path to the YAML file
            
        Returns:
            Dictionary containing the configuration
        """
        try:
            with open(file_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            # Return empty dict if file can't be loaded
            return {}
    
    def _load_json_file(self, file_path: str) -> Dict[str, Any]:
        """
        Load configuration from a JSON file.
        
        Args:
            file_path: Path to the JSON file
            
        Returns:
            Dictionary containing the configuration
        """
        try:
            with open(file_path, 'r') as f:
                return json.load(f) or {}
        except Exception as e:
            # Return empty dict if file can't be loaded
            return {}
    
    def _save_yaml_file(self, file_path: str, data: Dict[str, Any]) -> None:
        """
        Save configuration to a YAML file.
        
        Args:
            file_path: Path to the YAML file
            data: Dictionary containing the configuration
        """
        try:
            with open(file_path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False)
        except Exception as e:
            # Handle save error
            pass
    
    def _save_json_file(self, file_path: str, data: Dict[str, Any]) -> None:
        """
        Save configuration to a JSON file.
        
        Args:
            file_path: Path to the JSON file
            data: Dictionary containing the configuration
        """
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            # Handle save error
            pass
    
    def _create_default_config(self) -> Dict[str, Any]:
        """
        Create default configuration.
        
        Returns:
            Dictionary containing default configuration
        """
        return {
            'general': {
                'app_name': 'Forex Trading Dashboard',
                'version': '1.0.0',
                'timezone': 'UTC',
            },
            'api': {
                'base_url': 'https://api.example.com',
                'timeout': 30,
                'retry_count': 3,
                'api_key': '',
            },
            'database': {
                'type': 'sqlite',
                'path': 'data/forex.db',
                'host': 'localhost',
                'port': 5432,
                'user': '',
                'password': '',
                'database': 'forex',
            },
            'logging': {
                'level': 'INFO',
                'console_enabled': True,
                'file_enabled': True,
                'json_enabled': True,
                'log_directory': 'logs',
                'log_filename': 'forex.log',
                'json_filename': 'forex.json.log',
                'max_file_size_mb': 10,
                'backup_count': 5,
                'max_memory_logs': 1000,
                'console_format': '%(asctime)s - %(levelname)s - %(message)s',
                'file_format': '%(asctime)s - %(levelname)s - %(message)s',
            },
            'trading': {
                'default_leverage': 50,
                'default_lot_size': 0.01,
                'max_open_positions': 10,
                'risk_per_trade': 0.01,  # 1% of account
                'default_stop_loss_pips': 50,
                'default_take_profit_pips': 100,
                'enable_trailing_stop': False,
                'trailing_stop_pips': 20,
            },
            'ui': {
                'theme': 'dark',
                'refresh_interval': 5,  # seconds
                'chart_timeframe': '1h',
                'default_currency_pair': 'EUR/USD',
                'favorite_pairs': ['EUR/USD', 'GBP/USD', 'USD/JPY', 'AUD/USD'],
                'table_page_size': 25,
            },
            'notifications': {
                'enabled': True,
                'email': {
                    'enabled': False,
                    'smtp_server': 'smtp.example.com',
                    'smtp_port': 587,
                    'smtp_user': '',
                    'smtp_password': '',
                    'from_address': '',
                    'to_address': '',
                },
                'desktop': {
                    'enabled': True,
                    'trade_opened': True,
                    'trade_closed': True,
                    'price_alert': True,
                },
            },
            'security': {
                'enable_2fa': False,
                'session_timeout_minutes': 30,
                'max_login_attempts': 5,
                'password_expiry_days': 90,
            },
        }
    
    def _update_config(self) -> None:
        """
        Update the combined configuration by merging all configuration sources.
        The precedence order is:
        1. Runtime configuration (highest)
        2. User configuration
        3. Environment configuration
        4. Default configuration (lowest)
        """
        with self._lock:
            # Start with default configuration
            result = copy.deepcopy(self._default_config)
            
            # Merge environment configuration
            self._deep_merge(result, self._env_config)
            
            # Merge user configuration
            self._deep_merge(result, self._user_config)
            
            # Merge runtime configuration
            self._deep_merge(result, self._runtime_config)
            
            # Update combined configuration
            self._config = result
    
    def _deep_merge(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """
        Recursively merge source dictionary into target dictionary.
        
        Args:
            target: Target dictionary
            source: Source dictionary to merge from
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                # Recursively merge dictionaries
                self._deep_merge(target[key], value)
            else:
                # Replace or add value
                target[key] = copy.deepcopy(value)
    
    def get_config(self, section: Optional[str] = None, default: Any = None) -> Any:
        """
        Get configuration value for a section.
        
        Args:
            section: Configuration section or key path (dot-separated)
            default: Default value to return if section doesn't exist
            
        Returns:
            Configuration value or default
        """
        with self._lock:
            # Initialize if needed
            if not self._initialized:
                self.initialize()
            
            # Return full configuration if no section specified
            if not section:
                return copy.deepcopy(self._config)
            
            # Handle dot notation for nested keys
            if '.' in section:
                parts = section.split('.')
                current = self._config
                for part in parts:
                    if part not in current:
                        return default
                    current = current[part]
                return copy.deepcopy(current)
            
            # Return section or default
            return copy.deepcopy(self._config.get(section, default))
    
    def set_config(self, section: str, value: Any, persist: bool = False) -> None:
        """
        Set configuration value for a section.
        
        Args:
            section: Configuration section or key path (dot-separated)
            value: Configuration value
            persist: Whether to persist the change to user configuration file
        """
        with self._lock:
            # Initialize if needed
            if not self._initialized:
                self.initialize()
            
            # Handle dot notation for nested keys
            if '.' in section:
                # Create nested structure in runtime config
                parts = section.split('.')
                current = self._runtime_config
                for i, part in enumerate(parts[:-1]):
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                
                # Set value
                current[parts[-1]] = value
                
                # Update user config if persist is True
                if persist:
                    current = self._user_config
                    for i, part in enumerate(parts[:-1]):
                        if part not in current:
                            current[part] = {}
                        current = current[part]
                    current[parts[-1]] = value
            else:
                # Set value in runtime config
                self._runtime_config[section] = value
                
                # Update user config if persist is True
                if persist:
                    self._user_config[section] = value
            
            # Update combined configuration
            self._update_config()
            
            # Persist to user config file if required
            if persist:
                self._save_yaml_file(USER_CONFIG_FILE, self._user_config)
            
            # Trigger callbacks
            self._trigger_callbacks(section, value)
    
    def reset_config(self, section: Optional[str] = None) -> None:
        """
        Reset configuration to default values.
        
        Args:
            section: Configuration section to reset (or None for all)
        """
        with self._lock:
            # Initialize if needed
            if not self._initialized:
                self.initialize()
            
            if section:
                # Handle dot notation for nested keys
                if '.' in section:
                    parts = section.split('.')
                    
                    # Remove from runtime config
                    current = self._runtime_config
                    for i, part in enumerate(parts[:-1]):
                        if part not in current:
                            break
                        current = current[part]
                    if parts[-1] in current:
                        del current[parts[-1]]
                    
                    # Remove from user config
                    current = self._user_config
                    for i, part in enumerate(parts[:-1]):
                        if part not in current:
                            break
                        current = current[part]
                    if parts[-1] in current:
                        del current[parts[-1]]
                else:
                    # Remove section from runtime config
                    if section in self._runtime_config:
                        del self._runtime_config[section]
                    
                    # Remove section from user config
                    if section in self._user_config:
                        del self._user_config[section]
            else:
                # Reset all configuration
                self._runtime_config = {}
                self._user_config = {}
            
            # Update combined configuration
            self._update_config()
            
            # Persist changes to user config file
            self._save_yaml_file(USER_CONFIG_FILE, self._user_config)
            
            # Trigger callbacks
            if section:
                self._trigger_callbacks(section, self.get_config(section))
            else:
                # Trigger callbacks for all sections
                for section in self._callbacks.keys():
                    self._trigger_callbacks(section, self.get_config(section))
    
    def register_callback(self, section: str, callback: Callable[[str, Any], None]) -> None:
        """
        Register a callback function to be called when a configuration section changes.
        
        Args:
            section: Configuration section or key path (dot-separated)
            callback: Callback function that takes section and value arguments
        """
        with self._lock:
            if section not in self._callbacks:
                self._callbacks[section] = []
            self._callbacks[section].append(callback)
    
    def unregister_callback(self, section: str, callback: Callable[[str, Any], None]) -> None:
        """
        Unregister a callback function.
        
        Args:
            section: Configuration section or key path (dot-separated)
            callback: Callback function to unregister
        """
        with self._lock:
            if section in self._callbacks:
                self._callbacks[section] = [cb for cb in self._callbacks[section] if cb != callback]
                if not self._callbacks[section]:
                    del self._callbacks[section]
    
    def _trigger_callbacks(self, section: str, value: Any) -> None:
        """
        Trigger callbacks for a section.
        
        Args:
            section: Configuration section or key path (dot-separated)
            value: New value for the section
        """
        # Create a copy of the callbacks to avoid issues with callbacks modifying the list
        callbacks = []
        
        with self._lock:
            # Find exact match callbacks
            if section in self._callbacks:
                callbacks.extend(self._callbacks[section])
            
            # Find parent section callbacks for dot notation
            if '.' in section:
                parts = section.split('.')
                for i in range(len(parts)):
                    parent = '.'.join(parts[:i+1])
                    if parent in self._callbacks:
                        callbacks.extend(self._callbacks[parent])
        
        # Call callbacks outside the lock to avoid deadlocks
        for callback in callbacks:
            try:
                callback(section, value)
            except Exception:
                # Ignore callback errors
                pass
    
    def get_environment(self) -> str:
        """
        Get the current environment.
        
        Returns:
            Current environment name
        """
        return self._environment
    
    def set_environment(self, environment: str) -> None:
        """
        Set the current environment and reload configuration.
        
        Args:
            environment: Environment name
        """
        with self._lock:
            if environment != self._environment:
                self._environment = environment
                
                # Reload environment configuration
                env_config_file = os.path.join(DEFAULT_CONFIG_DIR, f'config.{environment}.yaml')
                if os.path.exists(env_config_file):
                    self._env_config = self._load_yaml_file(env_config_file)
                else:
                    self._env_config = {}
                
                # Update combined configuration
                self._update_config()
                
                # Trigger callbacks for all sections
                for section in self._callbacks.keys():
                    self._trigger_callbacks(section, self.get_config(section))

# Create a singleton instance
config_manager = ConfigManager() 