"""
Exposure Management and Circuit Breaker System

This module implements a hierarchical risk management system that enforces
exposure limits at various levels of the trading system and implements
circuit breakers to automatically reduce risk during unusual market conditions.
"""

import logging
import threading
import time
from typing import Dict, List, Optional, Any, Callable, Set
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Possible states for the circuit breaker."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Breaker triggered, preventing operations
    HALF_OPEN = "half_open"  # Testing if system can return to normal


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""
    failure_threshold: int = 5  # Number of failures to trigger
    reset_timeout_seconds: int = 300  # Time before trying to recover
    recovery_success_threshold: int = 3  # Successes needed to fully restore


class ExposureLimitType(Enum):
    """Types of exposure limits in the system."""
    ASSET = "asset"  # Limits for individual trading pairs/assets
    SECTOR = "sector"  # Limits for sectors (crypto, forex, etc.)
    STRATEGY = "strategy"  # Limits for individual strategies
    PORTFOLIO = "portfolio"  # Overall portfolio exposure limits


@dataclass
class ExposureLimit:
    """Definition of an exposure limit."""
    limit_type: ExposureLimitType
    identifier: str  # Asset, sector, or strategy ID
    max_exposure: float  # Maximum exposure as decimal (0.10 = 10%)
    warning_threshold: float = 0.80  # When to start warning (80% of limit)
    hard_limit: bool = True  # If True, blocks trades; if False, just warns


class CircuitBreakerTrigger(Enum):
    """Events that can trigger a circuit breaker."""
    VOLATILITY_SPIKE = "volatility_spike"
    SPREAD_WIDENING = "spread_widening"
    PRICE_GAP = "price_gap"
    LIQUIDITY_DROP = "liquidity_drop"
    RAPID_PRICE_CHANGE = "rapid_price_change"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    DRAWDOWN_THRESHOLD = "drawdown_threshold"
    API_FAILURES = "api_failures"
    SYSTEM_PERFORMANCE = "system_performance"


@dataclass
class CircuitBreakerDefinition:
    """Definition of a circuit breaker."""
    name: str
    trigger_type: CircuitBreakerTrigger
    applies_to: List[str]  # List of assets, sectors, or "all"
    threshold: float  # Trigger threshold value
    cooldown_period_seconds: int = 300  # Cooling off period after triggering
    action: str = "pause_trading"  # What to do when triggered
    description: str = ""  # Human-readable description


class Observer:
    """Observer interface for the Observer pattern."""
    
    def update(self, subject: Any, data: Dict[str, Any] = None) -> None:
        """
        Update the observer with new data from the subject.
        
        Args:
            subject: The subject that triggered the update
            data: Optional data related to the update
        """
        pass


class ObservableSubject:
    """Observable subject interface for the Observer pattern."""
    
    def __init__(self):
        """Initialize the observable subject."""
        self._observers: List[Observer] = []
        
    def attach(self, observer: Observer) -> None:
        """
        Attach an observer to this subject.
        
        Args:
            observer: The observer to attach
        """
        if observer not in self._observers:
            self._observers.append(observer)
            
    def detach(self, observer: Observer) -> None:
        """
        Detach an observer from this subject.
        
        Args:
            observer: The observer to detach
        """
        if observer in self._observers:
            self._observers.remove(observer)
            
    def notify(self, data: Dict[str, Any] = None) -> None:
        """
        Notify all observers of a change.
        
        Args:
            data: Optional data related to the notification
        """
        for observer in self._observers:
            observer.update(self, data)


class CircuitBreaker(ObservableSubject):
    """
    Circuit breaker implementation to prevent cascading failures and 
    reduce risk during unusual market conditions.
    """
    
    def __init__(self, 
                 name: str, 
                 definition: CircuitBreakerDefinition, 
                 config: Optional[CircuitBreakerConfig] = None):
        """
        Initialize the circuit breaker.
        
        Args:
            name: Name of this circuit breaker
            definition: Definition of this circuit breaker
            config: Configuration for this circuit breaker
        """
        super().__init__()
        self.name = name
        self.definition = definition
        self.config = config or CircuitBreakerConfig()
        
        # State variables
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._last_trigger_time = None
        self._lock = threading.RLock()
        
        logger.info(f"Initialized circuit breaker '{name}' of type '{definition.trigger_type.value}'")
        
    def record_event(self, value: float, timestamp: Optional[datetime] = None) -> bool:
        """
        Record an event and check if the circuit breaker should trigger.
        
        Args:
            value: The value to check against the threshold
            timestamp: Optional timestamp for the event
            
        Returns:
            True if the circuit breaker was triggered, False otherwise
        """
        with self._lock:
            # If breaker is already open, don't re-trigger
            if self._state == CircuitBreakerState.OPEN:
                return True
                
            # Check if the value exceeds the threshold
            triggered = value >= self.definition.threshold
            
            if triggered:
                return self._trigger(timestamp or datetime.now())
            
            return False
            
    def record_failure(self, timestamp: Optional[datetime] = None) -> bool:
        """
        Record a failure and potentially trigger the circuit breaker.
        
        Args:
            timestamp: Optional timestamp for the failure
            
        Returns:
            True if the circuit breaker was triggered, False otherwise
        """
        with self._lock:
            # Record the failure
            self._failure_count += 1
            self._last_failure_time = timestamp or datetime.now()
            
            # Check if we've hit the threshold
            if self._failure_count >= self.config.failure_threshold:
                return self._trigger(self._last_failure_time)
                
            return False
            
    def record_success(self) -> None:
        """Record a successful operation."""
        with self._lock:
            # Reset failure count
            self._failure_count = 0
            
            # If in HALF_OPEN state, increment success counter
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._success_count += 1
                
                # Check if we've had enough successes to close the circuit
                if self._success_count >= self.config.recovery_success_threshold:
                    self._close()
        
    def _trigger(self, timestamp: datetime) -> bool:
        """
        Trigger the circuit breaker.
        
        Args:
            timestamp: When the trigger occurred
            
        Returns:
            True if triggered, False if already triggered
        """
        # If already open, don't re-trigger
        if self._state == CircuitBreakerState.OPEN:
            return False
            
        # Trigger the circuit breaker
        self._state = CircuitBreakerState.OPEN
        self._last_trigger_time = timestamp
        
        logger.warning(
            f"Circuit breaker '{self.name}' triggered at {timestamp} "
            f"after {self._failure_count} failures"
        )
        
        # Notify observers
        self.notify({
            "event": "triggered", 
            "name": self.name,
            "trigger_type": self.definition.trigger_type.value,
            "timestamp": timestamp,
            "applies_to": self.definition.applies_to,
            "action": self.definition.action
        })
        
        return True
    
    def _close(self) -> None:
        """Close the circuit breaker."""
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_trigger_time = None
        
        logger.info(f"Circuit breaker '{self.name}' closed")
        
        # Notify observers
        self.notify({
            "event": "closed", 
            "name": self.name,
            "trigger_type": self.definition.trigger_type.value,
            "timestamp": datetime.now(),
            "applies_to": self.definition.applies_to
        })
        
    def check_status(self) -> CircuitBreakerState:
        """
        Check the current status of the circuit breaker.
        
        Returns:
            Current state of the circuit breaker
        """
        with self._lock:
            # If closed, return immediately
            if self._state == CircuitBreakerState.CLOSED:
                return CircuitBreakerState.CLOSED
                
            # If open, check if enough time has passed to try recovery
            if self._state == CircuitBreakerState.OPEN:
                if self._last_trigger_time:
                    cooldown = max(
                        self.config.reset_timeout_seconds,
                        self.definition.cooldown_period_seconds
                    )
                    elapsed = (datetime.now() - self._last_trigger_time).total_seconds()
                    
                    if elapsed >= cooldown:
                        # Transition to half-open state
                        self._state = CircuitBreakerState.HALF_OPEN
                        self._success_count = 0
                        
                        logger.info(
                            f"Circuit breaker '{self.name}' transitioned to half-open state "
                            f"after {elapsed:.1f} seconds"
                        )
                        
                        # Notify observers
                        self.notify({
                            "event": "half_open", 
                            "name": self.name,
                            "trigger_type": self.definition.trigger_type.value,
                            "timestamp": datetime.now(),
                            "applies_to": self.definition.applies_to
                        })
                
            return self._state
            
    def is_open(self) -> bool:
        """
        Check if the circuit breaker is open.
        
        Returns:
            True if open (blocking operations), False otherwise
        """
        state = self.check_status()
        return state == CircuitBreakerState.OPEN
        
    def can_attempt_operation(self) -> bool:
        """
        Check if an operation can be attempted.
        
        Returns:
            True if the operation is allowed, False otherwise
        """
        state = self.check_status()
        return state == CircuitBreakerState.CLOSED or state == CircuitBreakerState.HALF_OPEN
        
    def reset(self) -> None:
        """Reset the circuit breaker to its initial state."""
        with self._lock:
            self._close()


class ExposureManager(ObservableSubject):
    """
    Manages exposure limits and circuit breakers for a trading system.
    
    Implements the Observer pattern to notify interested components
    when limits are reached or circuit breakers are triggered.
    """
    
    def __init__(self, account_balance: float, circuit_breaker_observer: Optional[Observer] = None):
        """
        Initialize the exposure manager.
        
        Args:
            account_balance: Current account balance
            circuit_breaker_observer: Optional observer for circuit breaker events
        """
        super().__init__()
        self.account_balance = account_balance
        
        # Exposure tracking
        self._asset_exposure: Dict[str, float] = {}  # symbol -> exposure
        self._sector_exposure: Dict[str, float] = {}  # sector -> exposure
        self._strategy_exposure: Dict[str, float] = {}  # strategy -> exposure
        self._total_exposure: float = 0.0
        
        # Symbol metadata
        self._symbol_sectors: Dict[str, str] = {}  # symbol -> sector
        self._symbol_strategies: Dict[str, Set[str]] = {}  # symbol -> set of strategies
        
        # Exposure limits
        self._exposure_limits: List[ExposureLimit] = []
        
        # Circuit breakers
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Lock for thread safety
        self._lock = threading.RLock()
        
        # Add circuit breaker observer if provided
        if circuit_breaker_observer:
            self.attach(circuit_breaker_observer)
            
        logger.info(f"Initialized exposure manager with account balance: {account_balance}")
        
    def set_account_balance(self, balance: float) -> None:
        """
        Update the account balance.
        
        Args:
            balance: New account balance
        """
        with self._lock:
            self.account_balance = balance
            
    def add_exposure_limit(self, limit: ExposureLimit) -> None:
        """
        Add an exposure limit.
        
        Args:
            limit: The limit to add
        """
        with self._lock:
            self._exposure_limits.append(limit)
            logger.info(
                f"Added {limit.limit_type.value} exposure limit for {limit.identifier}: "
                f"{limit.max_exposure:.1%} (hard_limit={limit.hard_limit})"
            )
            
    def remove_exposure_limit(self, limit_type: ExposureLimitType, identifier: str) -> bool:
        """
        Remove an exposure limit.
        
        Args:
            limit_type: Type of limit to remove
            identifier: Identifier of the limit to remove
            
        Returns:
            True if a limit was removed, False otherwise
        """
        with self._lock:
            for i, limit in enumerate(self._exposure_limits):
                if limit.limit_type == limit_type and limit.identifier == identifier:
                    del self._exposure_limits[i]
                    logger.info(f"Removed {limit_type.value} exposure limit for {identifier}")
                    return True
            
            return False
            
    def add_circuit_breaker(self, breaker: CircuitBreaker) -> None:
        """
        Add a circuit breaker.
        
        Args:
            breaker: The circuit breaker to add
        """
        with self._lock:
            self._circuit_breakers[breaker.name] = breaker
            # Attach self as an observer to the circuit breaker
            breaker.attach(self)
            logger.info(f"Added circuit breaker: {breaker.name}")
            
    def remove_circuit_breaker(self, name: str) -> bool:
        """
        Remove a circuit breaker.
        
        Args:
            name: Name of the circuit breaker to remove
            
        Returns:
            True if a circuit breaker was removed, False otherwise
        """
        with self._lock:
            if name in self._circuit_breakers:
                breaker = self._circuit_breakers[name]
                # Detach self as an observer
                breaker.detach(self)
                del self._circuit_breakers[name]
                logger.info(f"Removed circuit breaker: {name}")
                return True
            
            return False
            
    def set_symbol_sector(self, symbol: str, sector: str) -> None:
        """
        Set the sector for a symbol.
        
        Args:
            symbol: The symbol to set the sector for
            sector: The sector to set
        """
        with self._lock:
            self._symbol_sectors[symbol] = sector
            
    def add_symbol_strategy(self, symbol: str, strategy: str) -> None:
        """
        Add a strategy for a symbol.
        
        Args:
            symbol: The symbol to add the strategy for
            strategy: The strategy to add
        """
        with self._lock:
            if symbol not in self._symbol_strategies:
                self._symbol_strategies[symbol] = set()
            
            self._symbol_strategies[symbol].add(strategy)
            
    def remove_symbol_strategy(self, symbol: str, strategy: str) -> bool:
        """
        Remove a strategy for a symbol.
        
        Args:
            symbol: The symbol to remove the strategy for
            strategy: The strategy to remove
            
        Returns:
            True if the strategy was removed, False otherwise
        """
        with self._lock:
            if symbol in self._symbol_strategies and strategy in self._symbol_strategies[symbol]:
                self._symbol_strategies[symbol].remove(strategy)
                return True
            
            return False
            
    def get_asset_exposure(self, symbol: str) -> float:
        """
        Get the current exposure for an asset.
        
        Args:
            symbol: The symbol to get exposure for
            
        Returns:
            Current exposure in account currency
        """
        with self._lock:
            return self._asset_exposure.get(symbol, 0.0)
            
    def get_asset_exposure_percent(self, symbol: str) -> float:
        """
        Get the current exposure for an asset as a percentage of account balance.
        
        Args:
            symbol: The symbol to get exposure for
            
        Returns:
            Current exposure as a percentage (0.0-1.0)
        """
        with self._lock:
            exposure = self._asset_exposure.get(symbol, 0.0)
            return exposure / self.account_balance if self.account_balance > 0 else 0.0
            
    def get_sector_exposure(self, sector: str) -> float:
        """
        Get the current exposure for a sector.
        
        Args:
            sector: The sector to get exposure for
            
        Returns:
            Current exposure in account currency
        """
        with self._lock:
            return self._sector_exposure.get(sector, 0.0)
            
    def get_sector_exposure_percent(self, sector: str) -> float:
        """
        Get the current exposure for a sector as a percentage of account balance.
        
        Args:
            sector: The sector to get exposure for
            
        Returns:
            Current exposure as a percentage (0.0-1.0)
        """
        with self._lock:
            exposure = self._sector_exposure.get(sector, 0.0)
            return exposure / self.account_balance if self.account_balance > 0 else 0.0
            
    def get_strategy_exposure(self, strategy: str) -> float:
        """
        Get the current exposure for a strategy.
        
        Args:
            strategy: The strategy to get exposure for
            
        Returns:
            Current exposure in account currency
        """
        with self._lock:
            return self._strategy_exposure.get(strategy, 0.0)
            
    def get_strategy_exposure_percent(self, strategy: str) -> float:
        """
        Get the current exposure for a strategy as a percentage of account balance.
        
        Args:
            strategy: The strategy to get exposure for
            
        Returns:
            Current exposure as a percentage (0.0-1.0)
        """
        with self._lock:
            exposure = self._strategy_exposure.get(strategy, 0.0)
            return exposure / self.account_balance if self.account_balance > 0 else 0.0
            
    def get_total_exposure(self) -> float:
        """
        Get the total current exposure.
        
        Returns:
            Total exposure in account currency
        """
        with self._lock:
            return self._total_exposure
            
    def get_total_exposure_percent(self) -> float:
        """
        Get the total current exposure as a percentage of account balance.
        
        Returns:
            Total exposure as a percentage (0.0-1.0)
        """
        with self._lock:
            return self._total_exposure / self.account_balance if self.account_balance > 0 else 0.0
            
    def update_position(self, 
                       symbol: str, 
                       new_exposure: float, 
                       strategy: Optional[str] = None) -> Dict[str, Any]:
        """
        Update exposure tracking for a position.
        
        Args:
            symbol: Symbol for the position
            new_exposure: New exposure value in account currency
            strategy: Optional strategy associated with this position
            
        Returns:
            Dict containing validation results and warnings
        """
        with self._lock:
            # Get old exposure if it exists
            old_exposure = self._asset_exposure.get(symbol, 0.0)
            
            # Calculate exposure delta
            delta = new_exposure - old_exposure
            
            # Get sector for this symbol
            sector = self._symbol_sectors.get(symbol)
            
            # Check exposure limits before updating
            result = self._check_exposure_limits(symbol, delta, strategy)
            
            # Check circuit breakers
            if self._check_circuit_breakers(symbol):
                result["circuit_breaker_active"] = True
                
            # If any hard limits are violated, return without updating
            if result["hard_limit_violated"]:
                return result
                
            # Update asset exposure
            self._asset_exposure[symbol] = new_exposure
            
            # Update sector exposure
            if sector:
                old_sector_exposure = self._sector_exposure.get(sector, 0.0)
                self._sector_exposure[sector] = old_sector_exposure + delta
                
            # Update strategy exposure
            if strategy:
                old_strategy_exposure = self._strategy_exposure.get(strategy, 0.0)
                self._strategy_exposure[strategy] = old_strategy_exposure + delta
                
            # Update total exposure
            self._total_exposure += delta
            
            logger.debug(
                f"Updated position for {symbol}: exposure={new_exposure:.2f}, "
                f"delta={delta:.2f}, strategy={strategy}, sector={sector}"
            )
            
            return result
            
    def remove_position(self, 
                       symbol: str, 
                       strategy: Optional[str] = None) -> None:
        """
        Remove a position from exposure tracking.
        
        Args:
            symbol: Symbol for the position to remove
            strategy: Optional strategy associated with this position
        """
        with self._lock:
            if symbol in self._asset_exposure:
                # Get exposure
                exposure = self._asset_exposure[symbol]
                
                # Update sector exposure
                sector = self._symbol_sectors.get(symbol)
                if sector and sector in self._sector_exposure:
                    self._sector_exposure[sector] -= exposure
                    
                # Update strategy exposure
                if strategy and strategy in self._strategy_exposure:
                    self._strategy_exposure[strategy] -= exposure
                    
                # Update total exposure
                self._total_exposure -= exposure
                
                # Remove from asset exposure
                del self._asset_exposure[symbol]
                
                logger.debug(f"Removed position for {symbol}: exposure={exposure:.2f}")
                
    def _check_exposure_limits(self, 
                             symbol: str, 
                             delta: float, 
                             strategy: Optional[str] = None) -> Dict[str, Any]:
        """
        Check if adding a position would violate exposure limits.
        
        Args:
            symbol: Symbol for the position
            delta: Exposure change in account currency
            strategy: Optional strategy associated with this position
            
        Returns:
            Dict containing validation results and warnings
        """
        # Initialize result
        result = {
            "allowed": True,
            "warnings": [],
            "soft_limit_warnings": [],
            "hard_limit_violated": False,
            "exposure_violations": []
        }
        
        # Skip checks for exposure reduction
        if delta <= 0:
            return result
            
        # Check each exposure limit
        for limit in self._exposure_limits:
            # Check based on limit type
            if limit.limit_type == ExposureLimitType.ASSET and limit.identifier == symbol:
                # Asset-specific limit
                current = self._asset_exposure.get(symbol, 0.0)
                new_exposure = current + delta
                limit_value = limit.max_exposure * self.account_balance
                
                if new_exposure > limit_value:
                    violation = {
                        "type": "asset",
                        "identifier": symbol,
                        "current": current,
                        "new": new_exposure,
                        "limit": limit_value,
                        "percent": new_exposure / self.account_balance,
                        "limit_percent": limit.max_exposure
                    }
                    
                    result["exposure_violations"].append(violation)
                    
                    if limit.hard_limit:
                        result["allowed"] = False
                        result["hard_limit_violated"] = True
                        result["warnings"].append(
                            f"Asset exposure for {symbol} would exceed hard limit of {limit.max_exposure:.1%}"
                        )
                    else:
                        result["soft_limit_warnings"].append(
                            f"Asset exposure for {symbol} would exceed soft limit of {limit.max_exposure:.1%}"
                        )
                        
            elif limit.limit_type == ExposureLimitType.SECTOR:
                # Sector limit
                sector = self._symbol_sectors.get(symbol)
                if sector and sector == limit.identifier:
                    current = self._sector_exposure.get(sector, 0.0)
                    new_exposure = current + delta
                    limit_value = limit.max_exposure * self.account_balance
                    
                    if new_exposure > limit_value:
                        violation = {
                            "type": "sector",
                            "identifier": sector,
                            "current": current,
                            "new": new_exposure,
                            "limit": limit_value,
                            "percent": new_exposure / self.account_balance,
                            "limit_percent": limit.max_exposure
                        }
                        
                        result["exposure_violations"].append(violation)
                        
                        if limit.hard_limit:
                            result["allowed"] = False
                            result["hard_limit_violated"] = True
                            result["warnings"].append(
                                f"Sector exposure for {sector} would exceed hard limit of {limit.max_exposure:.1%}"
                            )
                        else:
                            result["soft_limit_warnings"].append(
                                f"Sector exposure for {sector} would exceed soft limit of {limit.max_exposure:.1%}"
                            )
                            
            elif limit.limit_type == ExposureLimitType.STRATEGY and strategy == limit.identifier:
                # Strategy limit
                current = self._strategy_exposure.get(strategy, 0.0)
                new_exposure = current + delta
                limit_value = limit.max_exposure * self.account_balance
                
                if new_exposure > limit_value:
                    violation = {
                        "type": "strategy",
                        "identifier": strategy,
                        "current": current,
                        "new": new_exposure,
                        "limit": limit_value,
                        "percent": new_exposure / self.account_balance,
                        "limit_percent": limit.max_exposure
                    }
                    
                    result["exposure_violations"].append(violation)
                    
                    if limit.hard_limit:
                        result["allowed"] = False
                        result["hard_limit_violated"] = True
                        result["warnings"].append(
                            f"Strategy exposure for {strategy} would exceed hard limit of {limit.max_exposure:.1%}"
                        )
                    else:
                        result["soft_limit_warnings"].append(
                            f"Strategy exposure for {strategy} would exceed soft limit of {limit.max_exposure:.1%}"
                        )
                        
            elif limit.limit_type == ExposureLimitType.PORTFOLIO:
                # Portfolio-wide limit
                new_exposure = self._total_exposure + delta
                limit_value = limit.max_exposure * self.account_balance
                
                if new_exposure > limit_value:
                    violation = {
                        "type": "portfolio",
                        "current": self._total_exposure,
                        "new": new_exposure,
                        "limit": limit_value,
                        "percent": new_exposure / self.account_balance,
                        "limit_percent": limit.max_exposure
                    }
                    
                    result["exposure_violations"].append(violation)
                    
                    if limit.hard_limit:
                        result["allowed"] = False
                        result["hard_limit_violated"] = True
                        result["warnings"].append(
                            f"Total portfolio exposure would exceed hard limit of {limit.max_exposure:.1%}"
                        )
                    else:
                        result["soft_limit_warnings"].append(
                            f"Total portfolio exposure would exceed soft limit of {limit.max_exposure:.1%}"
                        )
        
        return result
        
    def _check_circuit_breakers(self, symbol: str) -> bool:
        """
        Check if any circuit breakers are active for a symbol.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            True if a circuit breaker is active, False otherwise
        """
        # Check each circuit breaker
        for name, breaker in self._circuit_breakers.items():
            if breaker.is_open():
                # Check if this breaker applies to this symbol
                applies_to = breaker.definition.applies_to
                
                if "all" in applies_to or symbol in applies_to:
                    # Get sector for this symbol
                    sector = self._symbol_sectors.get(symbol)
                    if sector and sector in applies_to:
                        return True
                        
                    # Check if any of the symbol's strategies are affected
                    if symbol in self._symbol_strategies:
                        for strategy in self._symbol_strategies[symbol]:
                            if strategy in applies_to:
                                return True
                                
        return False
        
    def get_exposure_summary(self) -> Dict[str, Any]:
        """
        Get a summary of current exposure levels.
        
        Returns:
            Dict containing exposure summary information
        """
        with self._lock:
            return {
                "total_exposure": self._total_exposure,
                "total_exposure_percent": self.get_total_exposure_percent(),
                "asset_exposure": dict(self._asset_exposure),
                "asset_exposure_percent": {
                    symbol: self.get_asset_exposure_percent(symbol)
                    for symbol in self._asset_exposure
                },
                "sector_exposure": dict(self._sector_exposure),
                "sector_exposure_percent": {
                    sector: self.get_sector_exposure_percent(sector)
                    for sector in self._sector_exposure
                },
                "strategy_exposure": dict(self._strategy_exposure),
                "strategy_exposure_percent": {
                    strategy: self.get_strategy_exposure_percent(strategy)
                    for strategy in self._strategy_exposure
                }
            }
            
    def get_active_circuit_breakers(self) -> Dict[str, Any]:
        """
        Get information about currently active circuit breakers.
        
        Returns:
            Dict containing active circuit breaker information
        """
        active_breakers = {}
        
        for name, breaker in self._circuit_breakers.items():
            state = breaker.check_status()
            
            if state != CircuitBreakerState.CLOSED:
                active_breakers[name] = {
                    "state": state.value,
                    "trigger_type": breaker.definition.trigger_type.value,
                    "applies_to": breaker.definition.applies_to,
                    "action": breaker.definition.action,
                    "last_trigger_time": breaker._last_trigger_time,
                    "description": breaker.definition.description
                }
                
        return active_breakers
        
    def update(self, subject: Any, data: Dict[str, Any] = None) -> None:
        """
        Update method for the Observer pattern.
        
        Triggered when a circuit breaker changes state.
        
        Args:
            subject: The subject that changed (a CircuitBreaker)
            data: Data about the change
        """
        if isinstance(subject, CircuitBreaker) and data:
            # Forward notification to observers of the ExposureManager
            self.notify(data)
            
            # Log the event
            event_type = data.get("event")
            breaker_name = data.get("name")
            
            if event_type == "triggered":
                logger.warning(f"Circuit breaker triggered: {breaker_name}")
            elif event_type == "closed":
                logger.info(f"Circuit breaker closed: {breaker_name}")
            elif event_type == "half_open":
                logger.info(f"Circuit breaker half-open: {breaker_name}") 