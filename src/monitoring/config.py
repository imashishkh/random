"""
Configuration module for Prometheus exporters.

This module defines the configuration classes and loading functions
for the Prometheus exporters.
"""

import logging
import os
from typing import Dict, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ServerConfig(BaseModel):
    """Configuration for the Prometheus HTTP server."""
    
    enabled: bool = Field(default=True, description="Whether to enable the server")
    port: int = Field(default=9090, description="HTTP server port")
    address: str = Field(default="0.0.0.0", description="HTTP server address")
    metrics_path: str = Field(default="/metrics", description="Path for metrics endpoint")


class CollectorConfig(BaseModel):
    """Configuration for a metric collector."""
    
    enabled: bool = Field(default=True, description="Whether to enable this collector")
    interval: int = Field(default=15, description="Collection interval in seconds")
    cache_ttl: int = Field(default=30, description="Cache TTL in seconds")


class CollectorsConfig(BaseModel):
    """Configuration for all metric collectors."""
    
    agent: CollectorConfig = Field(default_factory=CollectorConfig, 
                                   description="Agent collector config")
    trade: CollectorConfig = Field(default_factory=CollectorConfig,
                                   description="Trade collector config")
    api: CollectorConfig = Field(default_factory=CollectorConfig,
                                 description="API collector config")


class MonitoringConfig(BaseModel):
    """Configuration for the Prometheus exporters."""
    
    server: ServerConfig = Field(default_factory=ServerConfig,
                                description="HTTP server config")
    collectors: CollectorsConfig = Field(default_factory=CollectorsConfig,
                                        description="Collectors config")


def load_env_bool(env_var: str, default: bool = False) -> bool:
    """
    Load a boolean value from an environment variable.
    
    Args:
        env_var: Name of the environment variable
        default: Default value if not set
        
    Returns:
        The boolean value
    """
    value = os.environ.get(env_var)
    if value is None:
        return default
    
    return value.lower() in ("true", "1", "yes", "y", "t")


def load_env_int(env_var: str, default: int) -> int:
    """
    Load an integer value from an environment variable.
    
    Args:
        env_var: Name of the environment variable
        default: Default value if not set
        
    Returns:
        The integer value
    """
    value = os.environ.get(env_var)
    if value is None:
        return default
    
    try:
        return int(value)
    except ValueError:
        logger.warning(f"Invalid value for {env_var}: {value}, using default {default}")
        return default


def load_env_str(env_var: str, default: str) -> str:
    """
    Load a string value from an environment variable.
    
    Args:
        env_var: Name of the environment variable
        default: Default value if not set
        
    Returns:
        The string value
    """
    value = os.environ.get(env_var)
    if value is None:
        return default
    
    return value


def load_config_from_env() -> MonitoringConfig:
    """
    Load configuration from environment variables.
    
    Returns:
        A MonitoringConfig object
    """
    # Server config
    server_enabled = load_env_bool("PROMETHEUS_SERVER_ENABLED", True)
    server_port = load_env_int("PROMETHEUS_SERVER_PORT", 9090)
    server_address = load_env_str("PROMETHEUS_SERVER_ADDRESS", "0.0.0.0")
    metrics_path = load_env_str("PROMETHEUS_METRICS_PATH", "/metrics")
    
    server_config = ServerConfig(
        enabled=server_enabled,
        port=server_port,
        address=server_address,
        metrics_path=metrics_path
    )
    
    # Agent collector config
    agent_enabled = load_env_bool("PROMETHEUS_AGENT_COLLECTOR_ENABLED", True)
    agent_interval = load_env_int("PROMETHEUS_AGENT_COLLECTOR_INTERVAL", 15)
    agent_cache_ttl = load_env_int("PROMETHEUS_AGENT_COLLECTOR_CACHE_TTL", 30)
    
    agent_config = CollectorConfig(
        enabled=agent_enabled,
        interval=agent_interval,
        cache_ttl=agent_cache_ttl
    )
    
    # Trade collector config
    trade_enabled = load_env_bool("PROMETHEUS_TRADE_COLLECTOR_ENABLED", True)
    trade_interval = load_env_int("PROMETHEUS_TRADE_COLLECTOR_INTERVAL", 15)
    trade_cache_ttl = load_env_int("PROMETHEUS_TRADE_COLLECTOR_CACHE_TTL", 30)
    
    trade_config = CollectorConfig(
        enabled=trade_enabled,
        interval=trade_interval,
        cache_ttl=trade_cache_ttl
    )
    
    # API collector config
    api_enabled = load_env_bool("PROMETHEUS_API_COLLECTOR_ENABLED", True)
    api_interval = load_env_int("PROMETHEUS_API_COLLECTOR_INTERVAL", 15)
    api_cache_ttl = load_env_int("PROMETHEUS_API_COLLECTOR_CACHE_TTL", 30)
    
    api_config = CollectorConfig(
        enabled=api_enabled,
        interval=api_interval,
        cache_ttl=api_cache_ttl
    )
    
    collectors_config = CollectorsConfig(
        agent=agent_config,
        trade=trade_config,
        api=api_config
    )
    
    return MonitoringConfig(
        server=server_config,
        collectors=collectors_config
    )


def load_config() -> MonitoringConfig:
    """
    Load configuration from all sources.
    
    This function will load configuration from environment variables.
    In the future, it could be extended to load from files as well.
    
    Returns:
        A MonitoringConfig object
    """
    return load_config_from_env() 