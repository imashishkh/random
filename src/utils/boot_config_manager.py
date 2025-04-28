"""
Boot Configuration Manager

This module provides a Boot Configuration Manager that extends the existing
ConfigManager with boot-specific functionality, including service dependency
checking and health verification.
"""

import os
import sys
import json
import time
import copy
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Callable, Tuple
from enum import Enum
from pathlib import Path
import logging

try:
    from pydantic import BaseModel, Field, validator, ConfigDict
except ImportError:
    # Add useful error message
    raise ImportError(
        "Pydantic is required for boot configuration management. "
        "Install it with: pip install pydantic"
    )

from .config_manager import ConfigManager
from .logger import get_logger
from .dependency_checker import (
    http_health_check,
    tcp_health_check,
    database_health_check,
    filesystem_health_check,
    custom_health_check
)

logger = get_logger("boot_config")

class HealthCheckType(str, Enum):
    """Type of health check to perform."""
    HTTP = "http"
    TCP = "tcp"
    DATABASE = "database"
    FILESYSTEM = "filesystem"
    CUSTOM = "custom"

class HealthCheckConfig(BaseModel):
    """Configuration for a health check."""
    type: HealthCheckType = HealthCheckType.HTTP
    endpoint: Optional[str] = None
    expected_status: int = 200
    timeout: int = 5
    headers: Dict[str, str] = Field(default_factory=dict)
    custom_check: Optional[str] = None
    
    model_config = ConfigDict(extra="ignore")

class ServiceConfig(BaseModel):
    """Configuration for a service."""
    enabled: bool = True
    critical: bool = True
    health_check: Optional[HealthCheckConfig] = None
    dependencies: List[str] = Field(default_factory=list)
    
    model_config = ConfigDict(extra="ignore")

class BootConfig(BaseModel):
    """Boot configuration."""
    startup_sequence: List[str] = Field(
        default_factory=lambda: ["database", "cache", "api", "trading_engine"]
    )
    dependency_timeout: int = 30
    retry_attempts: int = 3
    retry_backoff: float = 2.0
    initial_retry_delay: float = 1.0
    force_boot: bool = False
    health_check_timeout: int = 5
    services: Dict[str, ServiceConfig] = Field(default_factory=dict)
    exit_handlers: List[str] = Field(default_factory=list)
    
    model_config = ConfigDict(extra="ignore")

class BootConfigManager:
    """
    Extends ConfigManager with boot-specific functionality.
    
    This class provides methods for boot configuration management, service
    dependency checking, and health verification.
    """
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance of BootConfigManager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self, config_manager=None):
        """
        Initialize BootConfigManager with an existing ConfigManager instance.
        
        Args:
            config_manager: Optional ConfigManager instance, default is singleton
        """
        self.config_manager = config_manager or ConfigManager.get_instance()
        self.boot_config = self._load_boot_config()
        self.dependency_status = {}
        self.service_status = {}
        self.logger = get_logger("boot_config")
        
    def _load_boot_config(self) -> BootConfig:
        """
        Load and validate boot configuration.
        
        Returns:
            BootConfig: Validated boot configuration object
        """
        raw_config = self.config_manager.get_config("boot", {})
        try:
            return BootConfig.model_validate(raw_config)
        except Exception as e:
            self.logger.error(f"Error loading boot configuration: {str(e)}")
            # Fallback to default config
            self.logger.warning("Using default boot configuration")
            return BootConfig()
    
    def refresh_config(self):
        """Reload boot configuration from the config manager."""
        self.boot_config = self._load_boot_config()
    
    async def check_service_dependencies(self) -> Dict[str, bool]:
        """
        Check all service dependencies and return their status.
        
        Returns:
            Dict mapping service names to boolean status (True if available)
        """
        results = {}
        
        for service_name, service_config in self.boot_config.services.items():
            if not service_config.enabled:
                self.logger.info(f"Skipping disabled service: {service_name}")
                results[service_name] = True
                continue
                
            self.logger.info(f"Checking service: {service_name}")
            is_available = await self._check_service_health(service_name, service_config)
            results[service_name] = is_available
            
            if not is_available and service_config.critical and not self.boot_config.force_boot:
                self.logger.error(f"Critical service {service_name} unavailable")
        
        self.dependency_status = results
        return results
    
    async def _check_service_health(self, service_name: str, config: ServiceConfig) -> bool:
        """
        Check health of a specific service.
        
        Args:
            service_name: Name of the service to check
            config: Service configuration
            
        Returns:
            True if the service is healthy, False otherwise
        """
        if not config.health_check:
            self.logger.warning(f"No health check configured for {service_name}")
            return True
            
        health_check = config.health_check
        timeout = health_check.timeout or self.boot_config.health_check_timeout
        
        # Try with retries
        for attempt in range(self.boot_config.retry_attempts + 1):
            if attempt > 0:
                # Calculate backoff delay
                delay = self.boot_config.initial_retry_delay * (
                    self.boot_config.retry_backoff ** (attempt - 1)
                )
                self.logger.info(f"Retry {attempt}/{self.boot_config.retry_attempts} "
                                f"for {service_name} after {delay:.2f}s")
                await asyncio.sleep(delay)
            
            # Implement different health check types
            try:
                result = False
                
                if health_check.type == HealthCheckType.HTTP:
                    if not health_check.endpoint:
                        self.logger.error(f"No endpoint specified for HTTP health check: {service_name}")
                        continue
                    result = await http_health_check(
                        health_check.endpoint,
                        timeout,
                        health_check.expected_status,
                        health_check.headers
                    )
                elif health_check.type == HealthCheckType.TCP:
                    if not health_check.endpoint:
                        self.logger.error(f"No endpoint specified for TCP health check: {service_name}")
                        continue
                    # Parse host:port format
                    try:
                        host, port_str = health_check.endpoint.split(":")
                        port = int(port_str)
                        result = await tcp_health_check(host, port, timeout)
                    except ValueError:
                        self.logger.error(f"Invalid TCP endpoint format for {service_name}: "
                                         f"{health_check.endpoint}. Use host:port format.")
                        continue
                elif health_check.type == HealthCheckType.DATABASE:
                    if not health_check.endpoint:
                        self.logger.error(f"No connection string specified for DB health check: {service_name}")
                        continue
                    # Parse connection type from endpoint if specified: type://connection
                    if "://" in health_check.endpoint:
                        driver_type, conn_str = health_check.endpoint.split("://", 1)
                        result = await database_health_check(conn_str, driver_type, timeout)
                    else:
                        # Default to sqlite
                        result = await database_health_check(health_check.endpoint, "sqlite", timeout)
                elif health_check.type == HealthCheckType.FILESYSTEM:
                    if not health_check.endpoint:
                        self.logger.error(f"No path specified for filesystem health check: {service_name}")
                        continue
                    result = filesystem_health_check(health_check.endpoint)
                elif health_check.type == HealthCheckType.CUSTOM:
                    if not health_check.custom_check:
                        self.logger.error(f"No custom check function specified for {service_name}")
                        continue
                    result = await custom_health_check(
                        health_check.custom_check,
                        endpoint=health_check.endpoint,
                        timeout=timeout,
                        **health_check.headers  # Pass headers as kwargs
                    )
                else:
                    self.logger.error(f"Unknown health check type for {service_name}: {health_check.type}")
                    continue
                
                if result:
                    self.logger.info(f"Health check passed for {service_name}")
                    return True
                else:
                    self.logger.warning(f"Health check failed for {service_name}")
            except Exception as e:
                self.logger.error(f"Error during health check for {service_name}: {str(e)}")
        
        return False
    
    def validate_boot_readiness(self) -> Tuple[bool, List[str]]:
        """
        Validate that all required boot parameters are present and valid.
        
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        missing = []
        
        # Check for required services in startup sequence
        for service in self.boot_config.startup_sequence:
            if service not in self.boot_config.services:
                missing.append(f"Service '{service}' in startup_sequence has no configuration")
        
        # Validate service dependencies
        for service_name, service_config in self.boot_config.services.items():
            for dependency in service_config.dependencies:
                if dependency not in self.boot_config.services:
                    missing.append(f"Service '{service_name}' depends on undefined service '{dependency}'")
        
        # Check for circular dependencies
        if not self._check_circular_dependencies():
            missing.append("Circular dependencies detected in service configuration")
        
        return len(missing) == 0, missing
    
    def _check_circular_dependencies(self) -> bool:
        """
        Check for circular dependencies in the service configuration.
        
        Returns:
            True if no circular dependencies found, False otherwise
        """
        # Build dependency graph
        graph = {}
        for service_name, service_config in self.boot_config.services.items():
            graph[service_name] = service_config.dependencies
        
        # Check for cycles using DFS
        visited = set()
        path = set()
        
        def dfs(node):
            if node in path:
                return False  # Cycle detected
            if node in visited:
                return True  # Already checked, no cycles
            
            visited.add(node)
            path.add(node)
            
            for neighbor in graph.get(node, []):
                if not dfs(neighbor):
                    return False
            
            path.remove(node)
            return True
        
        # Check all nodes
        for node in graph:
            if node not in visited:
                if not dfs(node):
                    return False
        
        return True
    
    def log_boot_configuration(self, mask_sensitive: bool = True):
        """
        Log the boot configuration with optional masking of sensitive data.
        
        Args:
            mask_sensitive: Whether to mask sensitive data like keys and passwords
        """
        config_dict = self.boot_config.model_dump()
        
        if mask_sensitive:
            # Mask sensitive fields like API keys, passwords, etc.
            config_dict = self._mask_sensitive_data(config_dict)
        
        self.logger.info(f"Boot configuration loaded")
        self.logger.debug(f"Boot configuration details: {json.dumps(config_dict, indent=2)}")
    
    def _mask_sensitive_data(self, config_dict: Dict) -> Dict:
        """
        Recursively mask sensitive data in configuration.
        
        Args:
            config_dict: Configuration dictionary to mask
            
        Returns:
            Masked configuration dictionary
        """
        sensitive_keys = ['api_key', 'secret', 'password', 'token', 'key']
        masked_dict = config_dict.copy()
        
        for key, value in masked_dict.items():
            # Recursively process dictionaries
            if isinstance(value, dict):
                masked_dict[key] = self._mask_sensitive_data(value)
            # Recursively process lists
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                masked_dict[key] = [self._mask_sensitive_data(item) for item in value]
            # Mask sensitive string values
            elif isinstance(value, str) and any(sk in key.lower() for sk in sensitive_keys):
                masked_dict[key] = "***MASKED***"
                
        return masked_dict
    
    def get_service_boot_order(self) -> List[str]:
        """
        Get the correct boot order respecting dependencies.
        
        Returns:
            List of service names in the order they should be started
        """
        # Get all enabled services
        enabled_services = [
            service_name for service_name in self.boot_config.services
            if self.boot_config.services[service_name].enabled
        ]
        
        # Get dependency order first
        dependency_order = self._resolve_dependency_order(enabled_services)
        
        # If dependency resolution failed, return enabled services in startup sequence order
        if not dependency_order:
            return enabled_services
            
        return dependency_order
    
    def _resolve_dependency_order(self, services: List[str]) -> List[str]:
        """
        Resolve the correct order to start services based on dependencies.
        
        Args:
            services: List of service names to order
            
        Returns:
            Ordered list of service names
        """
        # Build dependency graph and in-degree count
        graph = {}
        in_degree = {}
        
        # Initialize graph and in-degree
        for service_name in services:
            if service_name in self.boot_config.services:
                deps = [d for d in self.boot_config.services[service_name].dependencies if d in services]
                graph[service_name] = deps
                in_degree[service_name] = len(deps)
            else:
                graph[service_name] = []
                in_degree[service_name] = 0
        
        # Initialize queue with services that have no dependencies
        queue = [svc for svc in services if in_degree[svc] == 0]
        result = []
        
        # Process queue
        while queue:
            # Get a service with no dependencies
            service = queue.pop(0)
            result.append(service)
            
            # For each service that depends on this one
            for dependent in services:
                if service in graph[dependent]:
                    # Reduce its in-degree
                    in_degree[dependent] -= 1
                    # If all dependencies are satisfied, add to queue
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
        
        # If result doesn't contain all services, there's a cycle
        if len(result) != len(services):
            self.logger.error("Circular dependency detected in service configuration")
            return []
            
        return result 