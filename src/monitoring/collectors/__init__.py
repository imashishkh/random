"""
Collectors package for Prometheus metrics.

This package contains specialized collectors for different metric domains:
- AgentCollector: Metrics related to the agent swarm orchestrator
- TradeCollector: Metrics related to trading analytics and performance
- ApiCollector: Metrics related to API usage and performance
- SystemCollector: Metrics related to system resources (CPU, memory, disk, network)
- NetworkCollector: Metrics related to network connectivity to external services
- ApplicationCollector: Metrics related to application-specific metrics
- DatabaseCollector: Metrics related to database performance (PostgreSQL, MongoDB, Redis)
"""

from .agent_collector import AgentCollector
from .trade_collector import TradeCollector
from .api_collector import ApiCollector
from .base_collector import BaseCollector
from .system_collector import SystemCollector
from .network_collector import NetworkCollector
from .application_collector import ApplicationCollector
from .database_collector import DatabaseCollector

__all__ = [
    'AgentCollector', 
    'TradeCollector', 
    'ApiCollector', 
    'BaseCollector',
    'SystemCollector',
    'NetworkCollector',
    'ApplicationCollector',
    'DatabaseCollector'
] 