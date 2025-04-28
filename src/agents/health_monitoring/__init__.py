"""
Health Monitoring Package

This package provides functionality for monitoring agent health,
detecting issues, and implementing automated recovery actions.
"""

# Expose key functions from submodules
from .health_monitoring.health_monitor import HealthMonitor, get_health_monitor
from .health_monitoring.health_monitor_service import HealthMonitorService
from .health_monitoring.circuit_breaker import (
    CircuitBreaker, 
    MarketAwareCircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
    CircuitBreakerError,
    get_circuit_breaker_registry
)
from .health_monitoring.watchdog import (
    AgentWatchdog,
    WatchdogCheck,
    ForexWatchdogCheck,
    WatchdogPriority,
    WatchdogAction,
    get_agent_watchdog
)
from .health_monitoring.recovery_orchestrator import (
    RecoveryOrchestrator,
    TradingRecoveryOrchestrator,
    RecoveryStrategy,
    RecoveryStatus,
    get_recovery_orchestrator,
    get_trading_recovery_orchestrator
)
from .health_monitoring.metrics_collector import (
    MetricsCollector,
    MetricType,
    MetricSeries
)
from .health_monitoring.anomaly_detector import (
    HealthAnomalyDetector,
    AnomalyPattern,
    AnomalyResult,
    get_anomaly_detector
)
from .health_monitoring.agent_health_sdk import (
    AgentHealthClient,
    HealthStatus,
    HealthCheckResult,
    get_health_client
)

# Define top-level imports for easier access
__all__ = [
    # Health monitor
    'HealthMonitor', 'get_health_monitor',
    
    # Health monitor service
    'HealthMonitorService',
    
    # Circuit breaker
    'CircuitBreaker', 'MarketAwareCircuitBreaker', 'CircuitBreakerRegistry',
    'CircuitState', 'CircuitBreakerError', 'get_circuit_breaker_registry',
    
    # Watchdog
    'AgentWatchdog', 'WatchdogCheck', 'ForexWatchdogCheck',
    'WatchdogPriority', 'WatchdogAction', 'get_agent_watchdog',
    
    # Recovery
    'RecoveryOrchestrator', 'TradingRecoveryOrchestrator',
    'RecoveryStrategy', 'RecoveryStatus',
    'get_recovery_orchestrator', 'get_trading_recovery_orchestrator',
    
    # Metrics
    'MetricsCollector', 'MetricType', 'MetricSeries',
    
    # Anomaly detection
    'HealthAnomalyDetector', 'AnomalyPattern', 'AnomalyResult',
    'get_anomaly_detector',
    
    # Agent Health SDK
    'AgentHealthClient', 'HealthStatus', 'HealthCheckResult', 'get_health_client'
]
