"""
Market Circuit Breaker

This module provides a sophisticated circuit breaker implementation
that monitors market volatility and can temporarily halt trading
when predefined thresholds are exceeded.
"""

import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from .action_log import RiskActionLog

# Configure logger
logger = logging.getLogger(__name__)


class MarketCircuitBreaker:
    """
    Market Circuit Breaker that monitors price volatility and halts trading
    when configurable thresholds are breached.
    
    Features:
    - Multiple threshold levels for different circuit breaker responses
    - Progressive cooldown periods for repeated triggers
    - Per-symbol circuit breakers with global coordination
    - Detailed event tracking and logging
    """
    
    def __init__(
        self,
        config: Dict[str, Any] = None,
        action_log: Optional[RiskActionLog] = None
    ):
        """
        Initialize the Market Circuit Breaker.
        
        Args:
            config: Configuration dictionary with thresholds and settings
            action_log: RiskActionLog instance for detailed event logging
        """
        self.config = config or {}
        self.action_log = action_log
        
        # Set default configuration
        self.config.setdefault('enabled', True)
        
        # Default thresholds - key is level name, value is config for that level
        self.config.setdefault('thresholds', {
            'LEVEL1': {
                'percentage': 3.0,       # 3% price movement
                'cooldown_period': 300,  # 5 minutes
                'description': 'Minor volatility'
            },
            'LEVEL2': {
                'percentage': 5.0,       # 5% price movement
                'cooldown_period': 600,  # 10 minutes
                'description': 'Moderate volatility'
            },
            'LEVEL3': {
                'percentage': 10.0,      # 10% price movement
                'cooldown_period': 1800, # 30 minutes
                'description': 'Severe volatility'
            }
        })
        
        # Progressive cooldown settings
        self.config.setdefault('progressive_cooldown', {
            'enabled': True,
            'window': 3600,   # 1 hour window for counting triggers
            'multiplier': 2,  # Double cooldown period for repeated triggers
            'max_multiplier': 4  # Maximum multiplication factor
        })
        
        # Internal state
        self.breaker_status = {}  # symbol -> status dict
        self.last_trigger_time = {}  # symbol -> timestamp dict
        self.trigger_count = {}  # symbol -> count within window
        
        logger.info(f"Initialized Market Circuit Breaker with {len(self.config['thresholds'])} levels")
    
    def check_price_volatility(
        self, 
        symbol: str, 
        current_price: float, 
        reference_price: float
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if price volatility has breached circuit breaker thresholds.
        
        Args:
            symbol: The trading symbol to check
            current_price: Current price of the symbol
            reference_price: Reference price to compare against (e.g., previous close)
            
        Returns:
            Tuple of (should_halt_trading, trigger_details)
            - should_halt_trading: True if trading should be halted
            - trigger_details: Details about the trigger if activated, None otherwise
        """
        # Skip check if circuit breaker is disabled
        if not self.config['enabled']:
            return False, None
            
        # Skip check if already in cooldown
        if self.is_in_cooldown(symbol):
            return True, self.breaker_status[symbol]
            
        # Check for zero reference price to avoid division by zero
        if reference_price == 0:
            logger.warning(f"Zero reference price for {symbol}, skipping circuit breaker check")
            return False, None
            
        # Calculate price movement percentage
        price_change_pct = abs(current_price - reference_price) / reference_price * 100
        
        # Check against thresholds in descending order (highest first)
        sorted_levels = sorted(
            self.config['thresholds'].items(),
            key=lambda x: x[1]['percentage'],
            reverse=True
        )
        
        for level, threshold in sorted_levels:
            if price_change_pct >= threshold['percentage']:
                # Circuit breaker triggered
                trigger_details = self.trigger_circuit_breaker(
                    symbol, level, price_change_pct
                )
                return True, trigger_details
                
        # No threshold breached
        return False, None
    
    def trigger_circuit_breaker(
        self, 
        symbol: str, 
        level: str, 
        price_change_pct: float
    ) -> Dict[str, Any]:
        """
        Activate the circuit breaker for a symbol.
        
        Args:
            symbol: The trading symbol that triggered the circuit breaker
            level: The threshold level that was triggered
            price_change_pct: The price change percentage that triggered it
            
        Returns:
            Details about the circuit breaker activation
        """
        # Get the threshold configuration for this level
        threshold = self.config['thresholds'][level]
        cooldown_period = threshold['cooldown_period']
        
        # Apply progressive cooldown if enabled
        cooldown_multiplier = 1.0
        if self.config['progressive_cooldown']['enabled']:
            cooldown_multiplier = self._calculate_progressive_cooldown(symbol)
            cooldown_period = int(cooldown_period * cooldown_multiplier)
        
        # Calculate cooldown end time
        triggered_at = time.time()
        cooldown_until = triggered_at + cooldown_period
        
        # Create circuit breaker status
        status = {
            'active': True,
            'symbol': symbol,
            'level': level,
            'triggered_at': triggered_at,
            'cooldown_until': cooldown_until,
            'price_change_pct': price_change_pct,
            'description': threshold['description'],
            'cooldown_period': cooldown_period,
            'cooldown_multiplier': cooldown_multiplier
        }
        
        # Update internal state
        self.breaker_status[symbol] = status
        self.last_trigger_time[symbol] = triggered_at
        
        # Increment trigger count for this symbol
        self.trigger_count.setdefault(symbol, 0)
        self.trigger_count[symbol] += 1
        
        # Log the event
        logger.warning(
            f"Circuit breaker triggered for {symbol}: {price_change_pct:.2f}% move, "
            f"level {level}, cooldown for {cooldown_period} seconds"
        )
        
        # Record in action log if available
        if self.action_log:
            self.action_log.log_circuit_breaker({
                'symbol': symbol,
                'level': level,
                'price_change_pct': price_change_pct,
                'cooldown_period': cooldown_period,
                'cooldown_until': cooldown_until,
                'cooldown_multiplier': cooldown_multiplier,
                'description': threshold['description']
            })
        
        return status
    
    def _calculate_progressive_cooldown(self, symbol: str) -> float:
        """
        Calculate the progressive cooldown multiplier based on recent triggers.
        
        Args:
            symbol: The trading symbol
            
        Returns:
            Multiplier for the cooldown period
        """
        # No progressive cooldown for first trigger
        if symbol not in self.last_trigger_time:
            return 1.0
            
        # Get progressive cooldown settings
        settings = self.config['progressive_cooldown']
        window = settings['window']
        base_multiplier = settings['multiplier']
        max_multiplier = settings['max_multiplier']
        
        # Calculate time since last trigger
        time_since_last = time.time() - self.last_trigger_time[symbol]
        
        # If outside window, reset to base cooldown
        if time_since_last > window:
            return 1.0
            
        # Calculate number of triggers in window (including this one)
        trigger_count = self.trigger_count.get(symbol, 0)
        
        # Calculate multiplier based on trigger count, capped at max
        multiplier = min(base_multiplier ** (trigger_count - 1), max_multiplier)
        
        logger.info(
            f"Progressive cooldown for {symbol}: multiplier = {multiplier} "
            f"based on {trigger_count} triggers in {window}s window"
        )
        
        return multiplier
    
    def is_in_cooldown(self, symbol: str) -> bool:
        """
        Check if a symbol is currently in circuit breaker cooldown.
        
        Args:
            symbol: The trading symbol to check
            
        Returns:
            True if symbol is in cooldown, False otherwise
        """
        # Not in cooldown if not in status dict
        if symbol not in self.breaker_status:
            return False
            
        # Not in cooldown if not active
        if not self.breaker_status[symbol]['active']:
            return False
            
        # Check if cooldown period has expired
        now = time.time()
        cooldown_until = self.breaker_status[symbol]['cooldown_until']
        
        if now > cooldown_until:
            # Reset circuit breaker
            self.breaker_status[symbol]['active'] = False
            logger.info(f"Circuit breaker cooldown ended for {symbol}")
            return False
            
        # Still in cooldown period
        return True
    
    def can_trade(self, symbol: str) -> bool:
        """
        Check if trading is allowed for a symbol based on circuit breaker status.
        
        Args:
            symbol: The trading symbol to check
            
        Returns:
            True if trading is allowed, False if halted
        """
        # Trading allowed if circuit breaker is disabled
        if not self.config['enabled']:
            return True
            
        # Trading not allowed if in cooldown
        return not self.is_in_cooldown(symbol)
    
    def get_status(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get the current circuit breaker status.
        
        Args:
            symbol: Optional symbol to get status for. If None, returns all statuses.
            
        Returns:
            Dictionary with circuit breaker status information
        """
        if symbol:
            # Return status for specific symbol
            if symbol in self.breaker_status:
                status = dict(self.breaker_status[symbol])
                # Add remaining cooldown time for convenience
                if status['active']:
                    status['cooldown_remaining'] = max(0, status['cooldown_until'] - time.time())
                return status
            else:
                return {'active': False, 'symbol': symbol}
        else:
            # Return status for all symbols
            result = {
                'enabled': self.config['enabled'],
                'active_breakers': {}
            }
            
            # Add active breakers
            for sym, status in self.breaker_status.items():
                if status['active']:
                    result['active_breakers'][sym] = dict(status)
                    # Add remaining cooldown time
                    result['active_breakers'][sym]['cooldown_remaining'] = max(
                        0, status['cooldown_until'] - time.time()
                    )
            
            return result
    
    def reset(self, symbol: Optional[str] = None) -> None:
        """
        Reset circuit breaker status.
        
        Args:
            symbol: Optional symbol to reset. If None, resets all circuit breakers.
        """
        if symbol:
            # Reset specific symbol
            if symbol in self.breaker_status:
                self.breaker_status[symbol]['active'] = False
                logger.info(f"Circuit breaker manually reset for {symbol}")
        else:
            # Reset all circuit breakers
            for sym in list(self.breaker_status.keys()):
                self.breaker_status[sym]['active'] = False
            logger.info("All circuit breakers manually reset")
    
    def enable(self) -> None:
        """Enable the circuit breaker system."""
        self.config['enabled'] = True
        logger.info("Circuit breaker system enabled")
    
    def disable(self) -> None:
        """Disable the circuit breaker system."""
        self.config['enabled'] = False
        logger.info("Circuit breaker system disabled")
    
    def configure(self, new_config: Dict[str, Any]) -> None:
        """
        Update circuit breaker configuration.
        
        Args:
            new_config: New configuration dictionary
        """
        # Merge new configuration into existing config
        if 'enabled' in new_config:
            self.config['enabled'] = new_config['enabled']
            
        if 'thresholds' in new_config:
            # Update individual thresholds
            for level, threshold in new_config['thresholds'].items():
                if level in self.config['thresholds']:
                    # Update existing threshold
                    self.config['thresholds'][level].update(threshold)
                else:
                    # Add new threshold
                    self.config['thresholds'][level] = threshold
                    
        if 'progressive_cooldown' in new_config:
            # Update progressive cooldown settings
            self.config['progressive_cooldown'].update(new_config['progressive_cooldown'])
            
        logger.info(f"Circuit breaker configuration updated: {self.config}")
        
    def get_active_breakers(self) -> List[Dict[str, Any]]:
        """
        Get a list of all currently active circuit breakers.
        
        Returns:
            List of active circuit breaker status dictionaries
        """
        active_breakers = []
        
        for symbol, status in self.breaker_status.items():
            if status['active']:
                # Deep copy the status and add remaining time
                breaker_info = dict(status)
                breaker_info['cooldown_remaining'] = max(
                    0, status['cooldown_until'] - time.time()
                )
                active_breakers.append(breaker_info)
                
        return active_breakers 