"""
Health Monitoring Registry

This module provides factory functions to access the health monitoring system
components. It uses the singleton pattern to ensure there's only one instance
of each component in the application.
"""

import logging
from typing import Optional, Dict, Any

from .health_monitoring.health_monitor_service import HealthMonitorService
from .health_monitoring.circuit_breaker import CircuitBreakerRegistry, CircuitBreaker
from .health_monitoring.anomaly_detector import HealthAnomalyDetector
from .health_monitoring.agent_health_sdk import AgentHealthClient, get_health_client
from ...utils.logging.logger import get_logger

# Singleton instances
_health_monitor_service: Optional[HealthMonitorService] = None
_circuit_breaker_registry: Optional[CircuitBreakerRegistry] = None
_anomaly_detector: Optional[HealthAnomalyDetector] = None
_logger = get_logger()

def get_health_monitor_service(
    heartbeat_timeout_seconds: float = 60.0,
    health_check_interval_seconds: float = 300.0,
    recovery_enabled: bool = True,
    early_warning_enabled: bool = True,
    early_warning_severity_threshold: float = 0.7,
    **kwargs
) -> HealthMonitorService:
    """
    Get or create the singleton HealthMonitorService instance.
    
    Args:
        heartbeat_timeout_seconds: Time in seconds after which an agent is considered
            unresponsive if no heartbeat is received
        health_check_interval_seconds: Interval in seconds between health checks
        recovery_enabled: Whether automatic recovery is enabled
        early_warning_enabled: Whether early warning through anomaly detection is enabled
        early_warning_severity_threshold: Threshold for early warning severity (0.0-1.0)
        **kwargs: Additional arguments for HealthMonitorService
        
    Returns:
        The HealthMonitorService instance
    """
    global _health_monitor_service
    
    if _health_monitor_service is None:
        _logger.info("Creating new HealthMonitorService instance")
        _health_monitor_service = HealthMonitorService(
            heartbeat_timeout_seconds=heartbeat_timeout_seconds,
            health_check_interval_seconds=health_check_interval_seconds,
            recovery_enabled=recovery_enabled,
            early_warning_enabled=early_warning_enabled,
            early_warning_severity_threshold=early_warning_severity_threshold,
            **kwargs
        )
        
    return _health_monitor_service


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """
    Get or create the singleton CircuitBreakerRegistry instance.
    
    Returns:
        The CircuitBreakerRegistry instance
    """
    global _circuit_breaker_registry
    
    if _circuit_breaker_registry is None:
        _logger.info("Creating new CircuitBreakerRegistry instance")
        _circuit_breaker_registry = CircuitBreakerRegistry()
        
    return _circuit_breaker_registry


def get_circuit_breaker(
    circuit_id: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    half_open_timeout: float = 30.0
) -> CircuitBreaker:
    """
    Get or create a CircuitBreaker instance with the specified ID.
    
    Args:
        circuit_id: Unique identifier for the circuit
        failure_threshold: Number of failures before the circuit opens
        recovery_timeout: Time in seconds before attempting recovery
        half_open_timeout: Time in seconds to wait in half-open state
        
    Returns:
        The CircuitBreaker instance
    """
    registry = get_circuit_breaker_registry()
    return registry.get_or_create(
        circuit_id=circuit_id,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        half_open_timeout=half_open_timeout
    )


def get_anomaly_detector(
    check_interval_seconds: float = 60.0,
    history_window_size: int = 100,
    **kwargs
) -> HealthAnomalyDetector:
    """
    Get or create the singleton HealthAnomalyDetector instance.
    
    Args:
        check_interval_seconds: Interval in seconds between anomaly checks
        history_window_size: Size of history window for anomaly detection
        **kwargs: Additional arguments for HealthAnomalyDetector
        
    Returns:
        The HealthAnomalyDetector instance
    """
    global _anomaly_detector
    
    if _anomaly_detector is None:
        _logger.info("Creating new HealthAnomalyDetector instance")
        _anomaly_detector = HealthAnomalyDetector.get_instance(
            check_interval_seconds=check_interval_seconds,
            history_window_size=history_window_size,
            **kwargs
        )
        
    return _anomaly_detector 