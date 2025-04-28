"""
Exposure Limits and Circuit Breakers Implementation

This module provides the implementation of exposure limits and circuit breakers
for the trading system, including default configurations and helper functions.
"""

from typing import Dict, List, Any, Set, Optional
import logging
from datetime import datetime, timedelta

from .risk.exposure_manager import (
    ExposureManager,
    ExposureLimitType,
    ExposureLimit,
    CircuitBreaker,
    CircuitBreakerTrigger,
    CircuitBreakerDefinition,
    CircuitBreakerConfig
)

logger = logging.getLogger(__name__)


def create_default_exposure_manager(account_balance: float) -> ExposureManager:
    """
    Create an ExposureManager with default exposure limits.
    
    Args:
        account_balance: Current account balance
        
    Returns:
        Configured ExposureManager
    """
    manager = ExposureManager(account_balance)
    
    # Add default exposure limits
    default_limits = get_default_exposure_limits()
    for limit in default_limits:
        manager.add_exposure_limit(limit)
        
    # Add default circuit breakers
    default_breakers = get_default_circuit_breakers()
    for breaker in default_breakers:
        manager.add_circuit_breaker(breaker)
        
    logger.info(f"Created default exposure manager with {len(default_limits)} limits and {len(default_breakers)} circuit breakers")
    
    return manager


def get_default_exposure_limits() -> List[ExposureLimit]:
    """
    Get a list of default exposure limits for the trading system.
    
    Returns:
        List of default ExposureLimit objects
    """
    limits = [
        # Portfolio-wide limit (50% max exposure)
        ExposureLimit(
            limit_type=ExposureLimitType.PORTFOLIO,
            identifier="total",
            max_exposure=0.50,  # 50% max total exposure
            warning_threshold=0.80,  # Warn at 80% of limit (40% exposure)
            hard_limit=True
        ),
        
        # Sector limits
        ExposureLimit(
            limit_type=ExposureLimitType.SECTOR,
            identifier="crypto",
            max_exposure=0.30,  # 30% max exposure to crypto
            warning_threshold=0.80,
            hard_limit=True
        ),
        ExposureLimit(
            limit_type=ExposureLimitType.SECTOR,
            identifier="forex",
            max_exposure=0.40,  # 40% max exposure to forex
            warning_threshold=0.80,
            hard_limit=True
        ),
        
        # Default strategy limit
        ExposureLimit(
            limit_type=ExposureLimitType.STRATEGY,
            identifier="default",
            max_exposure=0.20,  # 20% max exposure to a single strategy
            warning_threshold=0.80,
            hard_limit=True
        ),
        
        # Default asset limit
        ExposureLimit(
            limit_type=ExposureLimitType.ASSET,
            identifier="default",
            max_exposure=0.10,  # 10% max exposure to a single asset
            warning_threshold=0.80,
            hard_limit=True
        ),
        
        # Special asset limits for major pairs
        ExposureLimit(
            limit_type=ExposureLimitType.ASSET,
            identifier="BTC/USDT",
            max_exposure=0.15,  # 15% max exposure to BTC/USDT
            warning_threshold=0.80,
            hard_limit=True
        ),
        ExposureLimit(
            limit_type=ExposureLimitType.ASSET,
            identifier="ETH/USDT",
            max_exposure=0.10,  # 10% max exposure to ETH/USDT
            warning_threshold=0.80,
            hard_limit=True
        ),
        ExposureLimit(
            limit_type=ExposureLimitType.ASSET,
            identifier="EUR/USD",
            max_exposure=0.15,  # 15% max exposure to EUR/USD
            warning_threshold=0.80,
            hard_limit=True
        )
    ]
    
    return limits


def get_default_circuit_breakers() -> List[CircuitBreaker]:
    """
    Get a list of default circuit breakers for the trading system.
    
    Returns:
        List of default CircuitBreaker objects
    """
    breakers = [
        # Volatility circuit breaker
        CircuitBreaker(
            name="volatility_breaker",
            definition=CircuitBreakerDefinition(
                name="High Volatility Circuit Breaker",
                trigger_type=CircuitBreakerTrigger.VOLATILITY_SPIKE,
                applies_to=["all"],  # Applies to all symbols
                threshold=3.0,  # Trigger when volatility is 3x normal
                cooldown_period_seconds=1800,  # 30 minutes
                action="reduce_position_sizes",
                description="Pauses trading during abnormally high volatility"
            ),
            config=CircuitBreakerConfig(
                failure_threshold=3,
                reset_timeout_seconds=1800,  # 30 minutes
                recovery_success_threshold=5
            )
        ),
        
        # Spread widening circuit breaker
        CircuitBreaker(
            name="spread_breaker",
            definition=CircuitBreakerDefinition(
                name="Wide Spread Circuit Breaker",
                trigger_type=CircuitBreakerTrigger.SPREAD_WIDENING,
                applies_to=["all"],  # Applies to all symbols
                threshold=5.0,  # Trigger when spread is 5x normal
                cooldown_period_seconds=900,  # 15 minutes
                action="pause_trading",
                description="Pauses trading when spreads widen abnormally"
            ),
            config=CircuitBreakerConfig(
                failure_threshold=2,
                reset_timeout_seconds=900,  # 15 minutes
                recovery_success_threshold=3
            )
        ),
        
        # Consecutive losses circuit breaker
        CircuitBreaker(
            name="consecutive_loss_breaker",
            definition=CircuitBreakerDefinition(
                name="Consecutive Loss Circuit Breaker",
                trigger_type=CircuitBreakerTrigger.CONSECUTIVE_LOSSES,
                applies_to=["all"],  # Applies to all symbols
                threshold=5.0,  # Trigger after 5 consecutive losses
                cooldown_period_seconds=3600,  # 1 hour
                action="reduce_risk_per_trade",
                description="Reduces risk after consecutive losses"
            ),
            config=CircuitBreakerConfig(
                failure_threshold=5,
                reset_timeout_seconds=3600,  # 1 hour
                recovery_success_threshold=2
            )
        ),
        
        # Drawdown circuit breaker
        CircuitBreaker(
            name="drawdown_breaker",
            definition=CircuitBreakerDefinition(
                name="Drawdown Circuit Breaker",
                trigger_type=CircuitBreakerTrigger.DRAWDOWN_THRESHOLD,
                applies_to=["all"],  # Applies to all symbols
                threshold=0.05,  # Trigger at 5% daily drawdown
                cooldown_period_seconds=86400,  # 24 hours
                action="pause_trading",
                description="Pauses trading after significant drawdown"
            ),
            config=CircuitBreakerConfig(
                failure_threshold=1,  # Trigger immediately at threshold
                reset_timeout_seconds=86400,  # 24 hours
                recovery_success_threshold=1
            )
        ),
        
        # API failures circuit breaker
        CircuitBreaker(
            name="api_failure_breaker",
            definition=CircuitBreakerDefinition(
                name="API Failure Circuit Breaker",
                trigger_type=CircuitBreakerTrigger.API_FAILURES,
                applies_to=["all"],  # Applies to all symbols
                threshold=3.0,  # Trigger after 3 API failures
                cooldown_period_seconds=300,  # 5 minutes
                action="pause_trading",
                description="Pauses trading when API connectivity issues occur"
            ),
            config=CircuitBreakerConfig(
                failure_threshold=3,
                reset_timeout_seconds=300,  # 5 minutes
                recovery_success_threshold=3
            )
        )
    ]
    
    return breakers


def create_circuit_breaker_for_symbol(symbol: str,
                                    trigger_type: CircuitBreakerTrigger,
                                    threshold: float,
                                    cooldown_period_seconds: int = 600) -> CircuitBreaker:
    """
    Create a circuit breaker for a specific symbol.
    
    Args:
        symbol: Trading symbol to apply to
        trigger_type: Type of trigger for this circuit breaker
        threshold: Threshold value for triggering
        cooldown_period_seconds: Cooldown period after triggering
        
    Returns:
        Configured CircuitBreaker
    """
    name = f"{symbol.lower().replace('/', '_')}_{trigger_type.value}_breaker"
    
    definition = CircuitBreakerDefinition(
        name=f"{symbol} {trigger_type.value.replace('_', ' ').title()} Circuit Breaker",
        trigger_type=trigger_type,
        applies_to=[symbol],
        threshold=threshold,
        cooldown_period_seconds=cooldown_period_seconds,
        action="pause_trading",
        description=f"Pauses {symbol} trading when {trigger_type.value.replace('_', ' ')} threshold is exceeded"
    )
    
    config = CircuitBreakerConfig(
        failure_threshold=3,
        reset_timeout_seconds=cooldown_period_seconds,
        recovery_success_threshold=2
    )
    
    return CircuitBreaker(name=name, definition=definition, config=config)


def create_exposure_limit_for_symbol(symbol: str, max_exposure: float, hard_limit: bool = True) -> ExposureLimit:
    """
    Create an exposure limit for a specific symbol.
    
    Args:
        symbol: Trading symbol to apply to
        max_exposure: Maximum exposure as decimal (e.g., 0.10 for 10%)
        hard_limit: Whether this is a hard limit or soft warning
        
    Returns:
        Configured ExposureLimit
    """
    return ExposureLimit(
        limit_type=ExposureLimitType.ASSET,
        identifier=symbol,
        max_exposure=max_exposure,
        warning_threshold=0.80,
        hard_limit=hard_limit
    )


def create_exposure_limit_for_strategy(strategy: str, max_exposure: float, hard_limit: bool = True) -> ExposureLimit:
    """
    Create an exposure limit for a specific strategy.
    
    Args:
        strategy: Strategy name to apply to
        max_exposure: Maximum exposure as decimal (e.g., 0.15 for 15%)
        hard_limit: Whether this is a hard limit or soft warning
        
    Returns:
        Configured ExposureLimit
    """
    return ExposureLimit(
        limit_type=ExposureLimitType.STRATEGY,
        identifier=strategy,
        max_exposure=max_exposure,
        warning_threshold=0.80,
        hard_limit=hard_limit
    )


def check_volatility_for_circuit_breaker(symbol: str, 
                                       current_volatility: float,
                                       average_volatility: float,
                                       circuit_breaker: CircuitBreaker) -> bool:
    """
    Check if volatility has exceeded the circuit breaker threshold.
    
    Args:
        symbol: Trading symbol to check
        current_volatility: Current volatility value
        average_volatility: Average volatility for comparison
        circuit_breaker: Circuit breaker to check against
        
    Returns:
        True if circuit breaker triggered, False otherwise
    """
    if circuit_breaker.definition.trigger_type != CircuitBreakerTrigger.VOLATILITY_SPIKE:
        return False
        
    # Calculate ratio of current to average
    if average_volatility > 0:
        volatility_ratio = current_volatility / average_volatility
    else:
        volatility_ratio = 1.0
        
    # Check if the ratio exceeds the threshold
    if volatility_ratio >= circuit_breaker.definition.threshold:
        # Record the event and check if the breaker triggered
        return circuit_breaker.record_event(volatility_ratio)
        
    return False


def check_spread_for_circuit_breaker(symbol: str,
                                   current_spread: float,
                                   average_spread: float,
                                   circuit_breaker: CircuitBreaker) -> bool:
    """
    Check if spread has exceeded the circuit breaker threshold.
    
    Args:
        symbol: Trading symbol to check
        current_spread: Current spread value
        average_spread: Average spread for comparison
        circuit_breaker: Circuit breaker to check against
        
    Returns:
        True if circuit breaker triggered, False otherwise
    """
    if circuit_breaker.definition.trigger_type != CircuitBreakerTrigger.SPREAD_WIDENING:
        return False
        
    # Calculate ratio of current to average
    if average_spread > 0:
        spread_ratio = current_spread / average_spread
    else:
        spread_ratio = 1.0
        
    # Check if the ratio exceeds the threshold
    if spread_ratio >= circuit_breaker.definition.threshold:
        # Record the event and check if the breaker triggered
        return circuit_breaker.record_event(spread_ratio)
        
    return False


def check_drawdown_for_circuit_breaker(current_drawdown: float,
                                     circuit_breaker: CircuitBreaker) -> bool:
    """
    Check if drawdown has exceeded the circuit breaker threshold.
    
    Args:
        current_drawdown: Current drawdown as a decimal (e.g., 0.05 for 5%)
        circuit_breaker: Circuit breaker to check against
        
    Returns:
        True if circuit breaker triggered, False otherwise
    """
    if circuit_breaker.definition.trigger_type != CircuitBreakerTrigger.DRAWDOWN_THRESHOLD:
        return False
        
    # Check if the drawdown exceeds the threshold
    if current_drawdown >= circuit_breaker.definition.threshold:
        # Record the event and check if the breaker triggered
        return circuit_breaker.record_event(current_drawdown)
        
    return False


def check_consecutive_losses_for_circuit_breaker(consecutive_losses: int,
                                               circuit_breaker: CircuitBreaker) -> bool:
    """
    Check if consecutive losses have exceeded the circuit breaker threshold.
    
    Args:
        consecutive_losses: Number of consecutive losing trades
        circuit_breaker: Circuit breaker to check against
        
    Returns:
        True if circuit breaker triggered, False otherwise
    """
    if circuit_breaker.definition.trigger_type != CircuitBreakerTrigger.CONSECUTIVE_LOSSES:
        return False
        
    # Check if the consecutive losses exceed the threshold
    if consecutive_losses >= circuit_breaker.definition.threshold:
        # Record the event and check if the breaker triggered
        return circuit_breaker.record_event(float(consecutive_losses))
        
    return False 