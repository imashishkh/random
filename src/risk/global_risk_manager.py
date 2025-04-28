"""
Global Risk Manager Implementation

This module provides a comprehensive global risk management solution that combines
position tracking, risk limit enforcement, circuit breakers, and emergency controls.
"""

import logging
import time
import asyncio
from typing import Dict, Any, Optional, List, Union, Set, Callable
import pandas as pd
import json
import threading
from datetime import datetime

from .manager import RiskManager
from .circuit_breakers import (
    CircuitBreaker,
    CircuitBreakerTrigger,
    CircuitBreakerScope,
    CircuitBreakerSeverity
)


# Configure logger
logger = logging.getLogger(__name__)


class GlobalRiskManager:
    """
    Global Risk Management System
    
    This class combines the RiskManager with CircuitBreaker to provide a comprehensive
    risk management solution that enforces position limits, monitors market conditions,
    activates protective measures during volatility, and provides emergency controls.
    """
    
    def __init__(self, 
                 account_balance: float = 10000.0,
                 config_file: Optional[str] = None):
        """
        Initialize the global risk manager.
        
        Args:
            account_balance: Initial account balance
            config_file: Optional configuration file path
        """
        # Load configuration
        self.config = self._load_config(config_file)
        
        # Initialize risk manager
        self.risk_manager = RiskManager(account_balance=account_balance, params=self.config.get('risk_manager', {}))
        
        # Initialize circuit breaker
        self.circuit_breaker = CircuitBreaker(
            enabled=self.config.get('circuit_breaker', {}).get('enabled', True),
            config=self.config.get('circuit_breaker', {}),
            alert_callback=self._handle_circuit_breaker_alert
        )
        
        # Initialize monitoring thread
        self._monitoring_enabled = False
        self._monitoring_thread = None
        self._monitoring_interval = self.config.get('monitoring', {}).get('interval', 60)  # Default: 60 seconds
        
        # Initialize last update timestamp
        self._last_position_update = 0
        self._last_market_data_update = {}  # symbol -> timestamp
        
        logger.info(f"GlobalRiskManager initialized with account balance {account_balance}")
        
        # Start monitoring if auto-start is enabled
        if self.config.get('monitoring', {}).get('auto_start', False):
            self.start_monitoring()
    
    def _load_config(self, config_file: Optional[str]) -> Dict[str, Any]:
        """
        Load configuration from file or use defaults.
        
        Args:
            config_file: Path to configuration file
            
        Returns:
            Configuration dictionary
        """
        config = {
            'risk_manager': {
                'max_risk_per_trade': 0.02,
                'max_asset_exposure': 0.10,
                'max_class_exposure': 0.25,
                'max_total_exposure': 0.75,
                'max_global_exposure': 0.80,
                'position_update_interval': 60,
                'circuit_breaker_enabled': True,
                'volatility_threshold': 3.0,
                'price_change_threshold': 0.05,
                'circuit_breaker_timeout': 300
            },
            'circuit_breaker': {
                'enabled': True,
                'global': {
                    'volatility': {
                        'threshold': 3.0,
                        'lookback_periods': 20,
                        'duration': 300,
                        'severity': 'hard'
                    },
                    'price_change': {
                        'threshold': 0.05,
                        'lookback_periods': 5,
                        'duration': 300,
                        'severity': 'hard'
                    }
                }
            },
            'monitoring': {
                'enabled': True,
                'auto_start': False,
                'interval': 60  # seconds
            }
        }
        
        # Load from file if provided
        if config_file:
            try:
                with open(config_file, 'r') as f:
                    loaded_config = json.load(f)
                    
                # Merge with defaults
                self._deep_update(config, loaded_config)
                logger.info(f"Loaded configuration from {config_file}")
            except Exception as e:
                logger.error(f"Error loading configuration from {config_file}: {e}")
                logger.info("Using default configuration")
        
        return config
    
    def _deep_update(self, d: Dict, u: Dict) -> Dict:
        """
        Deep update a nested dictionary.
        
        Args:
            d: Dictionary to update
            u: Dictionary with updates
            
        Returns:
            Updated dictionary
        """
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                self._deep_update(d[k], v)
            else:
                d[k] = v
        return d
    
    def set_global_limits(self, 
                          max_global_exposure: float = None,
                          max_agent_exposure: Dict[str, float] = None,
                          max_symbol_exposure: Dict[str, float] = None):
        """
        Set global risk limits across the entire trading system.
        
        Args:
            max_global_exposure: Maximum global exposure as percentage of equity
            max_agent_exposure: Dict mapping agent IDs to their max exposure
            max_symbol_exposure: Dict mapping symbols to their max exposure
        """
        # Set limits in risk manager
        self.risk_manager.set_global_limits(
            max_global_exposure=max_global_exposure,
            max_agent_exposure=max_agent_exposure,
            max_symbol_exposure=max_symbol_exposure
        )
        
        # Update config
        if max_global_exposure is not None:
            self.config['risk_manager']['max_global_exposure'] = max_global_exposure
            
        if max_agent_exposure is not None:
            self.config['risk_manager'].setdefault('max_agent_exposure', {})
            self.config['risk_manager']['max_agent_exposure'].update(max_agent_exposure)
            
        if max_symbol_exposure is not None:
            self.config['risk_manager'].setdefault('max_symbol_exposure', {})
            self.config['risk_manager']['max_symbol_exposure'].update(max_symbol_exposure)
        
        logger.info(f"Updated global risk limits")
    
    def configure_circuit_breakers(self,
                                  enabled: bool = None,
                                  volatility_threshold: float = None,
                                  price_change_threshold: float = None,
                                  timeout: int = None):
        """
        Configure circuit breaker parameters.
        
        Args:
            enabled: Whether circuit breakers are enabled
            volatility_threshold: Volatility multiplier threshold
            price_change_threshold: Sudden price change threshold
            timeout: Circuit breaker timeout in seconds
        """
        # Configure risk manager's circuit breaker
        self.risk_manager.configure_circuit_breakers(
            enabled=enabled,
            volatility_threshold=volatility_threshold,
            price_change_threshold=price_change_threshold,
            timeout=timeout
        )
        
        # Configure standalone circuit breaker
        if enabled is not None:
            self.circuit_breaker.set_enabled(enabled)
            self.config['circuit_breaker']['enabled'] = enabled
            
        # Update configuration for both volatility and price change
        if volatility_threshold is not None:
            self.config['circuit_breaker']['global']['volatility']['threshold'] = volatility_threshold
            
        if price_change_threshold is not None:
            self.config['circuit_breaker']['global']['price_change']['threshold'] = price_change_threshold
            
        if timeout is not None:
            self.config['circuit_breaker']['global']['volatility']['duration'] = timeout
            self.config['circuit_breaker']['global']['price_change']['duration'] = timeout
            
        # If circuit breaker is already configured, update it
        if volatility_threshold is not None or price_change_threshold is not None or timeout is not None:
            self.circuit_breaker.reconfigure(self.config['circuit_breaker'])
            
        logger.info(f"Updated circuit breaker configuration")
    
    def configure_slack_alerts(self, webhook_url: str) -> None:
        """
        Configure Slack alerts.
        
        Args:
            webhook_url: Slack webhook URL
        """
        self.risk_manager.configure_slack_alerts(webhook_url)
        logger.info("Configured Slack alerts")
    
    def calculate_position_size(self, 
                               symbol: str,
                               market_data: pd.DataFrame,
                               risk_params: Dict[str, Any] = None,
                               position_sizer_name: Optional[str] = None,
                               signal_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Calculate position size for a trade, respecting risk limits and circuit breakers.
        
        Args:
            symbol: Symbol for the trade
            market_data: Market data DataFrame
            risk_params: Risk parameters for the calculation
            position_sizer_name: Name of the position sizer to use
            signal_metadata: Optional metadata from the signal
                
        Returns:
            Position sizing result
        """
        # Check global circuit breaker
        if self.is_circuit_breaker_active():
            logger.warning(f"Circuit breaker active, position sizing blocked for {symbol}")
            return self._create_zero_position_result(symbol, "global_circuit_breaker_active")
        
        # Check symbol-specific circuit breaker
        if self.circuit_breaker.is_active(
            scope=CircuitBreakerScope.SYMBOL, 
            identifier=symbol, 
            min_severity=CircuitBreakerSeverity.HARD
        ):
            logger.warning(f"Symbol-specific circuit breaker active, position sizing blocked for {symbol}")
            return self._create_zero_position_result(symbol, "symbol_circuit_breaker_active")
        
        # Update circuit breaker market data
        self.circuit_breaker.update_market_data(symbol, market_data)
        
        # Check for rapid price changes or volatility spikes
        latest_price = market_data['close'].iloc[-1]
        volatility_result = self.circuit_breaker.check_volatility(symbol, latest_price)
        price_change_result = self.circuit_breaker.check_price_change(symbol, latest_price)
        
        # If either check exceeds threshold, activate appropriate circuit breaker and block position
        if volatility_result and volatility_result.get('exceeded'):
            # Get config for activation
            config = self.config['circuit_breaker']['global']['volatility']
            
            # Activate circuit breaker
            self.circuit_breaker.activate(
                trigger=CircuitBreakerTrigger.VOLATILITY,
                scope=CircuitBreakerScope.SYMBOL,
                identifier=symbol,
                severity=CircuitBreakerSeverity(config['severity']),
                duration=config['duration'],
                threshold_value=volatility_result['threshold'],
                current_value=volatility_result['volatility_ratio'],
                metadata=volatility_result
            )
            
            return self._create_zero_position_result(symbol, "volatility_circuit_breaker")
        
        if price_change_result and price_change_result.get('exceeded'):
            # Get config for activation
            config = self.config['circuit_breaker']['global']['price_change']
            
            # Activate circuit breaker
            self.circuit_breaker.activate(
                trigger=CircuitBreakerTrigger.PRICE_CHANGE,
                scope=CircuitBreakerScope.SYMBOL,
                identifier=symbol,
                severity=CircuitBreakerSeverity(config['severity']),
                duration=config['duration'],
                threshold_value=price_change_result['threshold'],
                current_value=price_change_result['price_change'],
                metadata=price_change_result
            )
            
            return self._create_zero_position_result(symbol, "price_change_circuit_breaker")
        
        # If all checks pass, calculate position size with risk manager
        return self.risk_manager.calculate_position_size(
            symbol=symbol,
            market_data=market_data,
            risk_params=risk_params,
            position_sizer_name=position_sizer_name,
            signal_metadata=signal_metadata
        )
    
    def _create_zero_position_result(self, symbol: str, reason: str) -> Dict[str, Any]:
        """
        Create a zero position result with explanation.
        
        Args:
            symbol: Symbol for the position
            reason: Reason for zero position
            
        Returns:
            Position sizing result with zero size
        """
        return {
            "size": 0.0,
            "value": 0.0,
            "risk_amount": 0.0,
            "risk_percent": 0.0,
            "metadata": {
                "symbol": symbol,
                "adjusted": True,
                "adjustment_reason": reason
            }
        }
    
    def fetch_binance_position_risk(self) -> List[Dict[str, Any]]:
        """
        Fetch real-time position risk data from Binance API.
        
        Returns:
            List of position risk data from Binance
        """
        # Delegate to risk manager
        positions = self.risk_manager.fetch_binance_position_risk()
        
        # Update last update timestamp
        self._last_position_update = time.time()
        
        return positions
    
    def check_risk_limits(self, positions=None) -> Dict[str, Any]:
        """
        Check current positions against risk limits and trigger appropriate actions.
        
        Args:
            positions: Optional positions data, fetches from Binance if None
            
        Returns:
            Dict containing risk status and any violations
        """
        # Delegate to risk manager
        risk_status = self.risk_manager.check_risk_limits(positions)
        
        # Handle severe violations by activating global circuit breaker
        violations = risk_status.get('violations', [])
        hard_violations = [v for v in violations if v.get('severity') == 'hard']
        
        if hard_violations:
            # Activate global circuit breaker
            severity = CircuitBreakerSeverity.HARD
            duration = self.config['circuit_breaker']['global']['volatility']['duration']  # Use same duration as volatility
            
            self.circuit_breaker.activate(
                trigger=CircuitBreakerTrigger.POSITION_LIMIT,
                scope=CircuitBreakerScope.GLOBAL,
                severity=severity,
                duration=duration,
                threshold_value=hard_violations[0].get('limit'),
                current_value=hard_violations[0].get('current'),
                metadata={"violations": hard_violations}
            )
            
            # Also activate risk manager's built-in circuit breaker
            self.risk_manager.activate_circuit_breaker(
                reason="hard_risk_limit_violation",
                duration=duration
            )
        
        return risk_status
    
    def activate_circuit_breaker(self, reason: str, duration: int = None) -> None:
        """
        Manually activate the circuit breaker.
        
        Args:
            reason: Reason for activation
            duration: Override default timeout duration in seconds
        """
        # Activate risk manager's circuit breaker
        self.risk_manager.activate_circuit_breaker(reason=reason, duration=duration)
        
        # Activate global circuit breaker
        timeout = duration or self.config['circuit_breaker']['global']['volatility']['duration']
        
        self.circuit_breaker.activate(
            trigger=CircuitBreakerTrigger.MANUAL,
            scope=CircuitBreakerScope.GLOBAL,
            severity=CircuitBreakerSeverity.HARD,
            duration=timeout,
            threshold_value=0,
            current_value=0,
            metadata={"reason": reason}
        )
        
        logger.warning(f"Circuit breaker manually activated: {reason}. Duration: {timeout}s")
    
    def deactivate_circuit_breaker(self) -> None:
        """
        Manually deactivate the circuit breaker.
        """
        # Deactivate risk manager's circuit breaker
        self.risk_manager.deactivate_circuit_breaker()
        
        # Deactivate global circuit breaker
        self.circuit_breaker.deactivate(scope=CircuitBreakerScope.GLOBAL)
        
        logger.info("Circuit breaker manually deactivated")
    
    def is_circuit_breaker_active(self) -> bool:
        """
        Check if any global circuit breaker is active.
        
        Returns:
            True if a circuit breaker is active
        """
        # Check risk manager's circuit breaker
        if self.risk_manager.is_circuit_breaker_active():
            return True
            
        # Check standalone circuit breaker
        return self.circuit_breaker.is_active(scope=CircuitBreakerScope.GLOBAL)
    
    def emergency_shutdown(self, reason: str = "manual") -> Dict[str, Any]:
        """
        Execute emergency shutdown procedure to close all positions.
        
        Args:
            reason: Reason for emergency shutdown
            
        Returns:
            Success status and details about closed positions
        """
        # Activate circuit breakers first
        self.activate_circuit_breaker(reason=f"emergency_shutdown_{reason}", duration=3600)  # 1 hour
        
        # Delegate to risk manager
        shutdown_result = self.risk_manager.emergency_shutdown(reason=reason)
        
        return shutdown_result
    
    def start_monitoring(self) -> None:
        """
        Start the background monitoring thread.
        """
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            logger.warning("Monitoring thread already running")
            return
            
        self._monitoring_enabled = True
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="RiskMonitoringThread"
        )
        self._monitoring_thread.start()
        
        logger.info(f"Started risk monitoring thread (interval: {self._monitoring_interval}s)")
    
    def stop_monitoring(self) -> None:
        """
        Stop the background monitoring thread.
        """
        if not self._monitoring_thread or not self._monitoring_thread.is_alive():
            logger.warning("No monitoring thread running")
            return
            
        self._monitoring_enabled = False
        self._monitoring_thread.join(timeout=5.0)
        
        if self._monitoring_thread.is_alive():
            logger.warning("Monitoring thread failed to stop cleanly")
        else:
            logger.info("Stopped risk monitoring thread")
    
    def _monitoring_loop(self) -> None:
        """
        Background monitoring loop.
        """
        logger.info("Risk monitoring loop started")
        
        while self._monitoring_enabled:
            try:
                # Fetch positions
                positions = self.fetch_binance_position_risk()
                
                # Check risk limits
                risk_status = self.check_risk_limits(positions)
                
                if risk_status.get('violations'):
                    logger.warning(f"Risk violations detected: {len(risk_status['violations'])}")
                
                # Check circuit breakers
                # This would require market data which we don't have in the background thread
                # For a full implementation, we would need to fetch market data for active symbols
                
                # Sleep until next check
                time.sleep(self._monitoring_interval)
            except Exception as e:
                logger.error(f"Error in risk monitoring loop: {e}")
                time.sleep(10)  # Sleep for a shorter time on error
                
        logger.info("Risk monitoring loop stopped")
    
    def _handle_circuit_breaker_alert(self, alert_data: Dict[str, Any]) -> None:
        """
        Handle alerts from circuit breaker.
        
        Args:
            alert_data: Alert data
        """
        state = alert_data.get('state', {})
        trigger = state.get('trigger')
        severity = state.get('severity')
        scope = state.get('scope')
        identifier = state.get('identifier')
        
        # Create alert message
        message = f"CIRCUIT BREAKER ACTIVATED: {trigger} trigger, {severity} severity\n"
        
        if scope == CircuitBreakerScope.GLOBAL.value:
            message += "Scope: GLOBAL\n"
        else:
            message += f"Scope: {scope}"
            if identifier:
                message += f" ({identifier})"
            message += "\n"
        
        if 'current_value' in state and 'threshold_value' in state:
            message += f"Value: {state['current_value']:.6f} (threshold: {state['threshold_value']:.6f})\n"
            
        message += f"Duration: {state.get('remaining_time', 0):.0f}s\n"
        
        # Send to Slack
        try:
            self.risk_manager._send_slack_alert(message, severity=severity)
        except Exception as e:
            logger.error(f"Error sending circuit breaker alert: {e}")
    
    def add_position(self, symbol: str, position_result: Dict[str, Any], asset_class: Optional[str] = None) -> None:
        """
        Add a position to tracking.
        
        Args:
            symbol: Symbol for the position
            position_result: Position sizing result
            asset_class: Optional asset class for the position
        """
        # Delegate to risk manager
        self.risk_manager.add_position(symbol, position_result, asset_class)
    
    def remove_position(self, symbol: str, asset_class: Optional[str] = None) -> None:
        """
        Remove a position from tracking.
        
        Args:
            symbol: Symbol for the position
            asset_class: Optional asset class for the position
        """
        # Delegate to risk manager
        self.risk_manager.remove_position(symbol, asset_class)
    
    def update_position(self, 
                       symbol: str, 
                       new_position_result: Dict[str, Any], 
                       asset_class: Optional[str] = None) -> None:
        """
        Update an existing position.
        
        Args:
            symbol: Symbol for the position
            new_position_result: New position sizing result
            asset_class: Optional asset class for the position
        """
        # Delegate to risk manager
        self.risk_manager.update_position(symbol, new_position_result, asset_class)
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get a position by symbol.
        
        Args:
            symbol: Symbol for the position
            
        Returns:
            Position data or None if not found
        """
        # Delegate to risk manager
        return self.risk_manager.get_position(symbol)
    
    def get_all_positions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all tracked positions.
        
        Returns:
            Dict of all positions
        """
        # Delegate to risk manager
        return self.risk_manager.get_all_positions()
    
    def get_exposure_summary(self) -> Dict[str, Any]:
        """
        Get a summary of current exposure.
        
        Returns:
            Exposure summary
        """
        # Delegate to risk manager
        return self.risk_manager.get_exposure_summary()
    
    def update_account_balance(self, new_balance: float) -> None:
        """
        Update the account balance.
        
        Args:
            new_balance: New account balance
        """
        # Delegate to risk manager
        self.risk_manager.update_account_balance(new_balance)
    
    def __str__(self) -> str:
        """String representation of the global risk manager."""
        cb_active = "Yes" if self.is_circuit_breaker_active() else "No"
        return f"GlobalRiskManager(balance=${self.risk_manager.account_balance:.2f}, circuit_breaker_active={cb_active})" 