"""
Risk Management Package

This package provides components for managing risk in the trading system,
including exposure limits, circuit breakers, and monitoring.
"""

from .exposure_manager import (
    ExposureManager,
    ExposureLimitType,
    ExposureLimit,
    CircuitBreaker,
    CircuitBreakerTrigger,
    CircuitBreakerDefinition,
    CircuitBreakerConfig,
    CircuitBreakerState,
    Observer,
    ObservableSubject
)

from .exposure_limits import (
    create_default_exposure_manager,
    get_default_exposure_limits,
    get_default_circuit_breakers,
    create_circuit_breaker_for_symbol,
    create_exposure_limit_for_symbol,
    create_exposure_limit_for_strategy,
    check_volatility_for_circuit_breaker,
    check_spread_for_circuit_breaker,
    check_drawdown_for_circuit_breaker,
    check_consecutive_losses_for_circuit_breaker
)

from .exposure_dashboard import ExposureDashboard
from .market_monitor import MarketConditionMonitor

__all__ = [
    'ExposureManager',
    'ExposureLimitType',
    'ExposureLimit',
    'CircuitBreaker',
    'CircuitBreakerTrigger',
    'CircuitBreakerDefinition',
    'CircuitBreakerConfig',
    'CircuitBreakerState',
    'Observer',
    'ObservableSubject',
    'create_default_exposure_manager',
    'get_default_exposure_limits',
    'get_default_circuit_breakers',
    'create_circuit_breaker_for_symbol',
    'create_exposure_limit_for_symbol',
    'create_exposure_limit_for_strategy',
    'check_volatility_for_circuit_breaker',
    'check_spread_for_circuit_breaker',
    'check_drawdown_for_circuit_breaker',
    'check_consecutive_losses_for_circuit_breaker',
    'ExposureDashboard',
    'MarketConditionMonitor'
] 