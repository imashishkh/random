"""
Circuit Breaker Implementation for Risk Management

This module provides circuit breaker functionality for the trading system,
allowing automatic suspension of trading during extreme market conditions
to prevent losses and manage risk.
"""

import logging
import time
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
from datetime import datetime
import pandas as pd
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)


class CircuitBreakerTrigger(str, Enum):
    """Reason codes for circuit breaker activation."""
    VOLATILITY = "volatility"
    PRICE_CHANGE = "price_change"
    DRAWDOWN = "drawdown"
    LOSS_RATE = "loss_rate"
    POSITION_LIMIT = "position_limit"
    MANUAL = "manual"
    API_ERROR = "api_error"
    SYSTEM_ERROR = "system_error"


class CircuitBreakerScope(str, Enum):
    """Scope of circuit breaker application."""
    GLOBAL = "global"  # All trading
    SYMBOL = "symbol"  # Specific symbol
    STRATEGY = "strategy"  # Specific strategy
    AGENT = "agent"  # Specific agent


class CircuitBreakerSeverity(str, Enum):
    """Severity levels for circuit breakers."""
    WARNING = "warning"  # Alert only, no action
    SOFT = "soft"  # Reduce position sizes/exposure
    HARD = "hard"  # Stop opening new positions
    EMERGENCY = "emergency"  # Close all positions


class CircuitBreakerState:
    """State tracking for a circuit breaker instance."""
    
    def __init__(self, scope: CircuitBreakerScope, identifier: str = None):
        self.scope = scope
        self.identifier = identifier  # Symbol, strategy, or agent ID depending on scope
        self.is_active = False
        self.activation_time: Optional[float] = None
        self.deactivation_time: Optional[float] = None
        self.duration: Optional[int] = None
        self.trigger: Optional[CircuitBreakerTrigger] = None
        self.severity: Optional[CircuitBreakerSeverity] = None
        self.threshold_value: Optional[float] = None
        self.current_value: Optional[float] = None
        self.activation_count = 0
        self.last_check_time: Optional[float] = None
        self.metadata: Dict[str, Any] = {}

    def activate(self, 
                trigger: CircuitBreakerTrigger, 
                severity: CircuitBreakerSeverity,
                duration: int,
                threshold: float,
                current_value: float,
                metadata: Dict[str, Any] = None):
        """
        Activate the circuit breaker.
        
        Args:
            trigger: The reason for activation
            severity: Severity level
            duration: Duration in seconds
            threshold: Threshold value that was exceeded
            current_value: Current value that exceeded the threshold
            metadata: Additional metadata
        """
        self.is_active = True
        self.activation_time = time.time()
        self.deactivation_time = self.activation_time + duration
        self.duration = duration
        self.trigger = trigger
        self.severity = severity
        self.threshold_value = threshold
        self.current_value = current_value
        self.activation_count += 1
        self.metadata = metadata or {}
        
        identifier_str = f" for {self.identifier}" if self.identifier else ""
        logger.warning(
            f"Circuit breaker activated{identifier_str}: "
            f"{severity.value.upper()} level due to {trigger.value} "
            f"({current_value:.6f} > {threshold:.6f}). "
            f"Duration: {duration}s"
        )

    def deactivate(self):
        """Deactivate the circuit breaker."""
        if not self.is_active:
            return
            
        self.is_active = False
        actual_duration = time.time() - self.activation_time
        
        identifier_str = f" for {self.identifier}" if self.identifier else ""
        logger.info(
            f"Circuit breaker deactivated{identifier_str}. "
            f"Was active for {actual_duration:.1f}s due to {self.trigger.value}"
        )
        
        # Reset state but keep history
        self.activation_time = None
        self.deactivation_time = None
        self.duration = None
        self.trigger = None
        self.severity = None
        self.threshold_value = None
        self.current_value = None
        self.metadata = {}

    def check_expiration(self) -> bool:
        """
        Check if the circuit breaker has expired.
        
        Returns:
            True if the circuit breaker was active but has now expired
        """
        if not self.is_active:
            return False
            
        current_time = time.time()
        self.last_check_time = current_time
        
        if current_time >= self.deactivation_time:
            self.deactivate()
            return True
            
        return False

    def get_remaining_time(self) -> Optional[float]:
        """
        Get remaining time until deactivation.
        
        Returns:
            Remaining time in seconds, or None if not active
        """
        if not self.is_active or not self.deactivation_time:
            return None
            
        return max(0, self.deactivation_time - time.time())

    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of this circuit breaker.
        
        Returns:
            Status dictionary
        """
        status = {
            "scope": self.scope.value,
            "is_active": self.is_active,
            "activation_count": self.activation_count,
        }
        
        if self.identifier:
            status["identifier"] = self.identifier
            
        if self.is_active:
            status.update({
                "trigger": self.trigger.value,
                "severity": self.severity.value,
                "activation_time": self.activation_time,
                "deactivation_time": self.deactivation_time,
                "remaining_time": self.get_remaining_time(),
                "threshold_value": self.threshold_value,
                "current_value": self.current_value,
            })
            
            if self.metadata:
                status["metadata"] = self.metadata
                
        return status


class CircuitBreaker:
    """
    Circuit breaker system for risk management.
    
    This class implements circuit breakers to automatically suspend trading
    during extreme market conditions to prevent excessive losses and manage risk.
    """
    
    def __init__(self, 
                 enabled: bool = True,
                 config: Dict[str, Any] = None,
                 alert_callback: Optional[Callable] = None):
        """
        Initialize the circuit breaker system.
        
        Args:
            enabled: Whether circuit breakers are enabled
            config: Configuration parameters
            alert_callback: Callback function for alerts
        """
        self.enabled = enabled
        self.config = config or {}
        self.alert_callback = alert_callback
        
        # Set default configuration
        self.config.setdefault("global", {
            "volatility": {
                "threshold": 3.0,  # 3x normal volatility 
                "lookback_periods": 20,
                "duration": 300,  # 5 minutes
                "severity": CircuitBreakerSeverity.HARD.value
            },
            "price_change": {
                "threshold": 0.05,  # 5% sudden change
                "lookback_periods": 5,
                "duration": 300,  # 5 minutes
                "severity": CircuitBreakerSeverity.HARD.value
            },
            "drawdown": {
                "threshold": 0.10,  # 10% drawdown
                "duration": 300,  # 5 minutes
                "severity": CircuitBreakerSeverity.HARD.value
            },
            "loss_rate": {
                "threshold": 0.05,  # 5% loss in 1 hour
                "timeframe": 3600,  # 1 hour in seconds
                "duration": 300,  # 5 minutes
                "severity": CircuitBreakerSeverity.HARD.value
            },
            "position_limit": {
                "threshold": 0.80,  # 80% of max exposure
                "duration": 0,  # Until manually reset or conditions change
                "severity": CircuitBreakerSeverity.SOFT.value
            }
        })
        
        # Initialize circuit breaker states
        self.states = {
            CircuitBreakerScope.GLOBAL: {"_global": CircuitBreakerState(CircuitBreakerScope.GLOBAL)},
            CircuitBreakerScope.SYMBOL: {},
            CircuitBreakerScope.STRATEGY: {},
            CircuitBreakerScope.AGENT: {}
        }
        
        # Market data cache for volatility calculation
        self.market_data_cache = {}
        
        logger.info(f"Circuit breaker initialized. Enabled: {enabled}")
    
    def reconfigure(self, config: Dict[str, Any]) -> None:
        """
        Reconfigure circuit breaker parameters.
        
        Args:
            config: New configuration
        """
        self.config.update(config)
        logger.info("Circuit breaker configuration updated")
    
    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable circuit breakers.
        
        Args:
            enabled: Whether circuit breakers should be enabled
        """
        self.enabled = enabled
        logger.info(f"Circuit breakers {'enabled' if enabled else 'disabled'}")
    
    def is_enabled(self) -> bool:
        """
        Check if circuit breakers are enabled.
        
        Returns:
            True if enabled
        """
        return self.enabled
    
    def is_active(self, 
                 scope: CircuitBreakerScope = CircuitBreakerScope.GLOBAL, 
                 identifier: str = None,
                 min_severity: CircuitBreakerSeverity = None) -> bool:
        """
        Check if a circuit breaker is active.
        
        Args:
            scope: Scope of the circuit breaker
            identifier: Identifier within scope (symbol, strategy, agent)
            min_severity: Minimum severity level to consider
            
        Returns:
            True if active
        """
        if not self.enabled:
            return False
            
        # Check specific circuit breaker if provided
        if scope and identifier:
            state = self._get_state(scope, identifier)
            
            if state.is_active:
                # Check if expired
                if state.check_expiration():
                    return False
                    
                # Check severity filter
                if min_severity and state.severity.value < min_severity.value:
                    return False
                    
                return True
                
            return False
            
        # Check global circuit breaker
        global_state = self._get_state(CircuitBreakerScope.GLOBAL)
        
        if global_state.is_active:
            # Check if expired
            if global_state.check_expiration():
                return False
                
            # Check severity filter
            if min_severity and global_state.severity.value < min_severity.value:
                return False
                
            return True
            
        # For GLOBAL scope without identifier, we're done
        if scope == CircuitBreakerScope.GLOBAL and not identifier:
            return False
            
        # Check all states of the given scope
        states = self.states[scope]
        
        for state_id, state in states.items():
            if state.is_active:
                # Check if expired
                if state.check_expiration():
                    continue
                    
                # Check severity filter
                if min_severity and state.severity.value < min_severity.value:
                    continue
                    
                return True
                
        return False
    
    def _get_state(self, 
                  scope: CircuitBreakerScope, 
                  identifier: str = None) -> CircuitBreakerState:
        """
        Get a circuit breaker state, creating it if needed.
        
        Args:
            scope: Scope of the circuit breaker
            identifier: Identifier within scope (symbol, strategy, agent)
            
        Returns:
            CircuitBreakerState instance
        """
        if scope == CircuitBreakerScope.GLOBAL:
            return self.states[scope]["_global"]
            
        # Use provided identifier or default
        identifier = identifier or "_default"
        
        # Create if doesn't exist
        if identifier not in self.states[scope]:
            self.states[scope][identifier] = CircuitBreakerState(scope, identifier)
            
        return self.states[scope][identifier]
    
    def activate(self, 
                trigger: CircuitBreakerTrigger,
                scope: CircuitBreakerScope = CircuitBreakerScope.GLOBAL,
                identifier: str = None,
                severity: CircuitBreakerSeverity = CircuitBreakerSeverity.HARD,
                duration: int = 300,
                threshold_value: float = None,
                current_value: float = None,
                metadata: Dict[str, Any] = None) -> CircuitBreakerState:
        """
        Manually activate a circuit breaker.
        
        Args:
            trigger: Reason for activation
            scope: Scope of the circuit breaker
            identifier: Identifier within scope (symbol, strategy, agent)
            severity: Severity level
            duration: Duration in seconds
            threshold_value: Threshold value that was exceeded
            current_value: Current value that exceeded threshold
            metadata: Additional metadata
            
        Returns:
            Activated CircuitBreakerState
        """
        if not self.enabled:
            logger.warning("Cannot activate circuit breaker: system is disabled")
            return None
            
        state = self._get_state(scope, identifier)
        
        # If already active with same or higher severity, extend duration
        if state.is_active and CircuitBreakerSeverity[state.severity.name].value >= severity.value:
            remaining = state.get_remaining_time() or 0
            new_duration = max(duration, remaining)
            state.deactivation_time = time.time() + new_duration
            state.duration = new_duration
            
            logger.info(
                f"Extended existing {state.severity.value} circuit breaker "
                f"(scope: {scope.value}, id: {identifier}, trigger: {state.trigger.value}). "
                f"New duration: {new_duration}s"
            )
        else:
            # Activate new circuit breaker
            state.activate(
                trigger=trigger,
                severity=severity,
                duration=duration,
                threshold=threshold_value or 0,
                current_value=current_value or 0,
                metadata=metadata
            )
            
            # Send alert
            if self.alert_callback:
                self._send_alert(state)
        
        return state
    
    def deactivate(self,
                  scope: CircuitBreakerScope = CircuitBreakerScope.GLOBAL,
                  identifier: str = None) -> bool:
        """
        Manually deactivate a circuit breaker.
        
        Args:
            scope: Scope of the circuit breaker
            identifier: Identifier within scope (symbol, strategy, agent)
            
        Returns:
            True if a circuit breaker was deactivated
        """
        state = self._get_state(scope, identifier)
        
        if state.is_active:
            state.deactivate()
            return True
            
        return False
    
    def deactivate_all(self) -> int:
        """
        Deactivate all circuit breakers.
        
        Returns:
            Number of circuit breakers deactivated
        """
        count = 0
        
        for scope_states in self.states.values():
            for state in scope_states.values():
                if state.is_active:
                    state.deactivate()
                    count += 1
                    
        logger.info(f"Deactivated {count} circuit breakers")
        return count
    
    def update_market_data(self, symbol: str, market_data: pd.DataFrame) -> None:
        """
        Update market data cache for a symbol.
        
        Args:
            symbol: Trading symbol
            market_data: Market data DataFrame
        """
        self.market_data_cache[symbol] = market_data.copy()
    
    def check_volatility(self, 
                        symbol: str,
                        current_price: float,
                        custom_threshold: float = None) -> Optional[Dict[str, Any]]:
        """
        Check if volatility exceeds threshold for a symbol.
        
        Args:
            symbol: Trading symbol
            current_price: Current price
            custom_threshold: Optional custom threshold multiplier
            
        Returns:
            Dict with check results if threshold exceeded, None otherwise
        """
        if not self.enabled:
            return None
            
        if symbol not in self.market_data_cache:
            logger.warning(f"No market data available for {symbol}, skipping volatility check")
            return None
            
        # Get configuration
        config = self.config.get("symbols", {}).get(symbol, {}).get("volatility")
        
        if not config:
            config = self.config["global"]["volatility"]
            
        threshold = custom_threshold or config["threshold"]
        lookback = config["lookback_periods"]
        
        try:
            # Get market data
            market_data = self.market_data_cache[symbol]
            
            # Ensure market data is sufficient
            if len(market_data) < lookback + 1:
                logger.debug(f"Insufficient market data for {symbol}, only {len(market_data)} points")
                return None
                
            # Calculate recent volatility (standard deviation of returns)
            returns = market_data['close'].pct_change().dropna()
            normal_volatility = returns[-lookback:-1].std()
            
            # Calculate current volatility (most recent point to current price)
            current_return = (current_price / market_data['close'].iloc[-1]) - 1
            recent_returns = returns[-lookback:].tolist() + [current_return]
            current_volatility = pd.Series(recent_returns).std()
            
            volatility_ratio = current_volatility / normal_volatility if normal_volatility > 0 else 0
            
            # Check if exceeds threshold
            if volatility_ratio > threshold:
                result = {
                    "symbol": symbol,
                    "normal_volatility": normal_volatility,
                    "current_volatility": current_volatility,
                    "volatility_ratio": volatility_ratio,
                    "threshold": threshold,
                    "exceeded": True
                }
                
                logger.warning(
                    f"Volatility threshold exceeded for {symbol}: "
                    f"ratio {volatility_ratio:.2f}x (threshold: {threshold:.2f}x)"
                )
                
                return result
        except Exception as e:
            logger.error(f"Error in volatility check for {symbol}: {e}")
        
        return None
    
    def check_price_change(self,
                          symbol: str,
                          current_price: float,
                          custom_threshold: float = None) -> Optional[Dict[str, Any]]:
        """
        Check if price change exceeds threshold for a symbol.
        
        Args:
            symbol: Trading symbol
            current_price: Current price
            custom_threshold: Optional custom threshold percentage
            
        Returns:
            Dict with check results if threshold exceeded, None otherwise
        """
        if not self.enabled:
            return None
            
        if symbol not in self.market_data_cache:
            logger.warning(f"No market data available for {symbol}, skipping price change check")
            return None
            
        # Get configuration
        config = self.config.get("symbols", {}).get(symbol, {}).get("price_change")
        
        if not config:
            config = self.config["global"]["price_change"]
            
        threshold = custom_threshold or config["threshold"]
        lookback = config["lookback_periods"]
        
        try:
            # Get market data
            market_data = self.market_data_cache[symbol]
            
            # Ensure market data is sufficient
            if len(market_data) < lookback:
                logger.debug(f"Insufficient market data for {symbol}, only {len(market_data)} points")
                return None
                
            # Get price lookback periods ago
            reference_price = market_data['close'].iloc[-lookback]
            
            # Calculate price change
            price_change = abs((current_price / reference_price) - 1)
            
            # Check if exceeds threshold
            if price_change > threshold:
                result = {
                    "symbol": symbol,
                    "reference_price": reference_price,
                    "current_price": current_price,
                    "price_change": price_change,
                    "threshold": threshold,
                    "exceeded": True
                }
                
                logger.warning(
                    f"Price change threshold exceeded for {symbol}: "
                    f"{price_change:.2%} (threshold: {threshold:.2%})"
                )
                
                return result
        except Exception as e:
            logger.error(f"Error in price change check for {symbol}: {e}")
        
        return None
    
    def check_drawdown(self,
                      equity_series: pd.Series,
                      custom_threshold: float = None) -> Optional[Dict[str, Any]]:
        """
        Check if drawdown exceeds threshold.
        
        Args:
            equity_series: Series of equity values
            custom_threshold: Optional custom threshold percentage
            
        Returns:
            Dict with check results if threshold exceeded, None otherwise
        """
        if not self.enabled:
            return None
            
        # Get configuration
        config = self.config["global"]["drawdown"]
        threshold = custom_threshold or config["threshold"]
        
        try:
            # Ensure data is sufficient
            if len(equity_series) < 2:
                logger.debug("Insufficient equity data points")
                return None
                
            # Calculate running maximum
            running_max = equity_series.cummax()
            
            # Calculate drawdown
            drawdown = (equity_series / running_max) - 1
            
            # Get maximum drawdown
            max_drawdown = abs(drawdown.min())
            
            # Check if exceeds threshold
            if max_drawdown > threshold:
                result = {
                    "max_equity": running_max.max(),
                    "current_equity": equity_series.iloc[-1],
                    "max_drawdown": max_drawdown,
                    "threshold": threshold,
                    "exceeded": True
                }
                
                logger.warning(
                    f"Drawdown threshold exceeded: "
                    f"{max_drawdown:.2%} (threshold: {threshold:.2%})"
                )
                
                return result
        except Exception as e:
            logger.error(f"Error in drawdown check: {e}")
        
        return None
    
    def check_loss_rate(self,
                       pnl_series: pd.Series,
                       timestamps: pd.Series,
                       custom_threshold: float = None,
                       custom_timeframe: int = None) -> Optional[Dict[str, Any]]:
        """
        Check if loss rate exceeds threshold.
        
        Args:
            pnl_series: Series of P&L values
            timestamps: Series of timestamps matching P&L values
            custom_threshold: Optional custom threshold percentage
            custom_timeframe: Optional custom timeframe in seconds
            
        Returns:
            Dict with check results if threshold exceeded, None otherwise
        """
        if not self.enabled:
            return None
            
        # Get configuration
        config = self.config["global"]["loss_rate"]
        threshold = custom_threshold or config["threshold"]
        timeframe = custom_timeframe or config["timeframe"]
        
        try:
            # Ensure data is sufficient
            if len(pnl_series) < 2:
                logger.debug("Insufficient P&L data points")
                return None
                
            # Convert timestamps to datetime if needed
            if not isinstance(timestamps.iloc[0], (datetime, np.datetime64)):
                timestamps = pd.to_datetime(timestamps)
                
            # Create DataFrame with timestamp and P&L
            df = pd.DataFrame({
                'timestamp': timestamps,
                'pnl': pnl_series
            })
            
            # Calculate cumulative P&L
            df['cumulative_pnl'] = df['pnl'].cumsum()
            
            # Get current time and cutoff time
            current_time = timestamps.iloc[-1]
            cutoff_time = current_time - pd.Timedelta(seconds=timeframe)
            
            # Filter to recent data
            recent_df = df[df['timestamp'] >= cutoff_time]
            
            # Skip if insufficient recent data
            if len(recent_df) < 2:
                logger.debug(f"Insufficient recent P&L data points within {timeframe}s timeframe")
                return None
                
            # Calculate loss rate (change in cumulative P&L over period)
            start_pnl = recent_df['cumulative_pnl'].iloc[0]
            end_pnl = recent_df['cumulative_pnl'].iloc[-1]
            pnl_change = end_pnl - start_pnl
            
            # Convert to percentage of equity
            # TODO: This would need to be adapted to reference actual equity
            loss_rate = -pnl_change / 10000  # Assuming $10k equity for now
            
            # Check if exceeds threshold (only for losses)
            if loss_rate > threshold:
                result = {
                    "timeframe": timeframe,
                    "start_time": recent_df['timestamp'].iloc[0],
                    "end_time": recent_df['timestamp'].iloc[-1],
                    "pnl_change": pnl_change,
                    "loss_rate": loss_rate,
                    "threshold": threshold,
                    "exceeded": True
                }
                
                logger.warning(
                    f"Loss rate threshold exceeded: "
                    f"{loss_rate:.2%} in {timeframe}s (threshold: {threshold:.2%})"
                )
                
                return result
        except Exception as e:
            logger.error(f"Error in loss rate check: {e}")
        
        return None
    
    def check_position_limit(self,
                            current_exposure: float,
                            max_exposure: float,
                            custom_threshold: float = None) -> Optional[Dict[str, Any]]:
        """
        Check if position exposure exceeds threshold.
        
        Args:
            current_exposure: Current exposure value
            max_exposure: Maximum allowed exposure
            custom_threshold: Optional custom threshold ratio
            
        Returns:
            Dict with check results if threshold exceeded, None otherwise
        """
        if not self.enabled:
            return None
            
        # Get configuration
        config = self.config["global"]["position_limit"]
        threshold = custom_threshold or config["threshold"]
        
        try:
            # Calculate exposure ratio
            exposure_ratio = current_exposure / max_exposure if max_exposure > 0 else 0
            
            # Check if exceeds threshold
            if exposure_ratio > threshold:
                result = {
                    "current_exposure": current_exposure,
                    "max_exposure": max_exposure,
                    "exposure_ratio": exposure_ratio,
                    "threshold": threshold,
                    "exceeded": True
                }
                
                logger.warning(
                    f"Position limit threshold exceeded: "
                    f"{exposure_ratio:.2%} of maximum (threshold: {threshold:.2%})"
                )
                
                return result
        except Exception as e:
            logger.error(f"Error in position limit check: {e}")
        
        return None
    
    def process_symbol_update(self,
                            symbol: str,
                            current_price: float,
                            market_data: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
        """
        Process a symbol update, checking all relevant circuit breakers.
        
        Args:
            symbol: Trading symbol
            current_price: Current price
            market_data: Optional updated market data
            
        Returns:
            List of triggered circuit breakers
        """
        if not self.enabled:
            return []
            
        # Update market data if provided
        if market_data is not None:
            self.update_market_data(symbol, market_data)
            
        # Skip if no market data available
        if symbol not in self.market_data_cache:
            logger.debug(f"No market data available for {symbol}, skipping circuit breaker checks")
            return []
            
        triggered = []
        
        # Check volatility
        volatility_result = self.check_volatility(symbol, current_price)
        if volatility_result and volatility_result.get("exceeded"):
            # Get configuration
            config = self.config.get("symbols", {}).get(symbol, {}).get("volatility")
            if not config:
                config = self.config["global"]["volatility"]
                
            cb_state = self.activate(
                trigger=CircuitBreakerTrigger.VOLATILITY,
                scope=CircuitBreakerScope.SYMBOL,
                identifier=symbol,
                severity=CircuitBreakerSeverity(config["severity"]),
                duration=config["duration"],
                threshold_value=volatility_result["threshold"],
                current_value=volatility_result["volatility_ratio"],
                metadata=volatility_result
            )
            
            triggered.append({
                "type": "volatility",
                "symbol": symbol,
                "threshold": volatility_result["threshold"],
                "value": volatility_result["volatility_ratio"],
                "circuit_breaker": cb_state.get_status() if cb_state else None
            })
            
        # Check price change
        price_change_result = self.check_price_change(symbol, current_price)
        if price_change_result and price_change_result.get("exceeded"):
            # Get configuration
            config = self.config.get("symbols", {}).get(symbol, {}).get("price_change")
            if not config:
                config = self.config["global"]["price_change"]
                
            cb_state = self.activate(
                trigger=CircuitBreakerTrigger.PRICE_CHANGE,
                scope=CircuitBreakerScope.SYMBOL,
                identifier=symbol,
                severity=CircuitBreakerSeverity(config["severity"]),
                duration=config["duration"],
                threshold_value=price_change_result["threshold"],
                current_value=price_change_result["price_change"],
                metadata=price_change_result
            )
            
            triggered.append({
                "type": "price_change",
                "symbol": symbol,
                "threshold": price_change_result["threshold"],
                "value": price_change_result["price_change"],
                "circuit_breaker": cb_state.get_status() if cb_state else None
            })
            
        return triggered
    
    def get_all_statuses(self) -> Dict[str, Any]:
        """
        Get status of all circuit breakers.
        
        Returns:
            Dict of all circuit breaker statuses
        """
        result = {
            "enabled": self.enabled,
            "global": {},
            "symbols": {},
            "strategies": {},
            "agents": {}
        }
        
        # Global circuit breakers
        for cb_id, state in self.states[CircuitBreakerScope.GLOBAL].items():
            result["global"][cb_id] = state.get_status()
            
        # Symbol circuit breakers
        for cb_id, state in self.states[CircuitBreakerScope.SYMBOL].items():
            result["symbols"][cb_id] = state.get_status()
            
        # Strategy circuit breakers
        for cb_id, state in self.states[CircuitBreakerScope.STRATEGY].items():
            result["strategies"][cb_id] = state.get_status()
            
        # Agent circuit breakers
        for cb_id, state in self.states[CircuitBreakerScope.AGENT].items():
            result["agents"][cb_id] = state.get_status()
            
        return result
    
    def _send_alert(self, state: CircuitBreakerState) -> None:
        """
        Send an alert for a circuit breaker state.
        
        Args:
            state: Circuit breaker state
        """
        if not self.alert_callback:
            return
            
        try:
            alert_data = {
                "event": "circuit_breaker_activated",
                "timestamp": time.time(),
                "state": state.get_status()
            }
            
            self.alert_callback(alert_data)
        except Exception as e:
            logger.error(f"Error sending circuit breaker alert: {e}")
    
    def __str__(self) -> str:
        """String representation of circuit breaker system."""
        active_count = sum(
            1 for scope_states in self.states.values() 
            for state in scope_states.values() 
            if state.is_active
        )
        
        return f"CircuitBreaker(enabled={self.enabled}, active={active_count})" 