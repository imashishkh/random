"""
Rule-Based Safeguards for Hybrid Models
---------------------------------------
Implements various rule-based safeguards for trading strategies.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Union, List, Tuple
from abc import ABC, abstractmethod


class Safeguard(ABC):
    """
    Base class for rule-based safeguards.
    
    Safeguards are used to override or modify the actions of a trading strategy
    based on predefined rules, to mitigate risk in extreme market conditions.
    """
    
    def __init__(self, name: str = None):
        """
        Initialize the safeguard.
        
        Args:
            name: Optional name for the safeguard
        """
        self.name = name or self.__class__.__name__
        self.is_active = True
    
    @abstractmethod
    def check(self, 
              data: pd.DataFrame, 
              action: Dict[str, Any], 
              state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if the safeguard should be triggered.
        
        Args:
            data: Market data
            action: Action proposed by the strategy
            state: Current state of the environment/strategy
            
        Returns:
            Tuple of (should_override, modified_action)
        """
        pass
    
    def activate(self):
        """Activate the safeguard."""
        self.is_active = True
    
    def deactivate(self):
        """Deactivate the safeguard."""
        self.is_active = False
    
    def __str__(self) -> str:
        """String representation of the safeguard."""
        return f"{self.name} ({'active' if self.is_active else 'inactive'})"


class VolatilitySafeguard(Safeguard):
    """
    Safeguard that reduces position size during high volatility.
    
    This safeguard monitors market volatility and reduces the size of positions
    when volatility exceeds a certain threshold.
    """
    
    def __init__(self, 
                 lookback_window: int = 20,
                 volatility_threshold: float = 2.0,
                 reduction_factor: float = 0.5,
                 name: str = "VolatilitySafeguard"):
        """
        Initialize the volatility safeguard.
        
        Args:
            lookback_window: Number of periods to calculate volatility
            volatility_threshold: Threshold in standard deviations above which to trigger
            reduction_factor: Factor by which to reduce position size
            name: Name for the safeguard
        """
        super().__init__(name)
        self.lookback_window = lookback_window
        self.volatility_threshold = volatility_threshold
        self.reduction_factor = reduction_factor
        
        # Track historical volatility
        self.volatility_history = []
    
    def check(self, 
              data: pd.DataFrame, 
              action: Dict[str, Any], 
              state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if volatility safeguard should be triggered.
        
        Args:
            data: Market data
            action: Action proposed by the strategy
            state: Current state of the environment/strategy
            
        Returns:
            Tuple of (should_override, modified_action)
        """
        if not self.is_active:
            return False, action
        
        # Calculate current volatility
        if len(data) >= self.lookback_window:
            recent_data = data.iloc[-self.lookback_window:]
            returns = recent_data['close'].pct_change().dropna()
            current_volatility = returns.std()
            
            # Get historical average volatility if available
            if self.volatility_history:
                avg_volatility = np.mean(self.volatility_history)
                
                # Check if current volatility exceeds threshold
                if current_volatility > avg_volatility * self.volatility_threshold:
                    # Create a deep copy of the action to modify
                    modified_action = action.copy()
                    
                    # Reduce position size
                    if 'position_size' in modified_action:
                        modified_action['position_size'] *= self.reduction_factor
                    elif 'size' in modified_action:
                        modified_action['size'] *= self.reduction_factor
                    
                    # Log the safeguard trigger
                    trigger_info = {
                        'safeguard': self.name,
                        'current_volatility': current_volatility,
                        'avg_volatility': avg_volatility,
                        'threshold': avg_volatility * self.volatility_threshold,
                        'reduction_factor': self.reduction_factor
                    }
                    
                    modified_action['safeguard_triggered'] = True
                    modified_action['safeguard_info'] = trigger_info
                    
                    return True, modified_action
            
            # Update volatility history
            self.volatility_history.append(current_volatility)
            
            # Limit the history length
            if len(self.volatility_history) > 100:  # Arbitrary limit to prevent unlimited growth
                self.volatility_history = self.volatility_history[-100:]
        
        return False, action


class CircuitBreaker(Safeguard):
    """
    Circuit breaker that prevents trading during extreme market conditions.
    
    This safeguard completely stops trading when certain market conditions are met,
    such as extreme price movements or liquidity issues.
    """
    
    def __init__(self, 
                 price_change_threshold: float = 0.05,  # 5% price change
                 volume_drop_threshold: float = 0.7,    # 70% volume drop
                 cooldown_periods: int = 5,            # 5 periods before resuming
                 lookback_window: int = 10,
                 name: str = "CircuitBreaker"):
        """
        Initialize the circuit breaker.
        
        Args:
            price_change_threshold: Threshold for price change to trigger the breaker
            volume_drop_threshold: Threshold for volume drop to trigger the breaker
            cooldown_periods: Number of periods to wait before allowing trades again
            lookback_window: Window for calculating baseline metrics
            name: Name for the safeguard
        """
        super().__init__(name)
        self.price_change_threshold = price_change_threshold
        self.volume_drop_threshold = volume_drop_threshold
        self.cooldown_periods = cooldown_periods
        self.lookback_window = lookback_window
        
        # State variables
        self.is_triggered = False
        self.cooldown_counter = 0
        self.baseline_volume = None
    
    def check(self, 
              data: pd.DataFrame, 
              action: Dict[str, Any], 
              state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if circuit breaker should be triggered.
        
        Args:
            data: Market data
            action: Action proposed by the strategy
            state: Current state of the environment/strategy
            
        Returns:
            Tuple of (should_override, modified_action)
        """
        if not self.is_active:
            return False, action
        
        # Create a default "no trade" action
        no_trade_action = action.copy()
        no_trade_action['type'] = 'none'
        no_trade_action['position_size'] = 0.0 if 'position_size' in action else 0.0
        no_trade_action['safeguard_triggered'] = True
        no_trade_action['safeguard_info'] = {'safeguard': self.name}
        
        # If already triggered, update cooldown and check if we can resume
        if self.is_triggered:
            self.cooldown_counter -= 1
            
            if self.cooldown_counter <= 0:
                self.is_triggered = False
                return False, action
            else:
                no_trade_action['safeguard_info']['cooldown_remaining'] = self.cooldown_counter
                return True, no_trade_action
        
        # Check for triggering conditions
        if len(data) >= self.lookback_window + 1:  # Need at least lookback + current
            # Get recent and current data
            recent_data = data.iloc[-(self.lookback_window+1):-1]
            current_data = data.iloc[-1]
            
            # Check for price change trigger
            prev_close = recent_data['close'].iloc[-1]
            current_close = current_data['close']
            price_change = abs(current_close - prev_close) / prev_close
            
            # Check for volume drop trigger
            if self.baseline_volume is None and 'volume' in recent_data.columns:
                self.baseline_volume = recent_data['volume'].mean()
            
            volume_trigger = False
            if self.baseline_volume is not None and 'volume' in current_data:
                volume_drop = current_data['volume'] / self.baseline_volume
                volume_trigger = volume_drop < self.volume_drop_threshold
            
            # Trigger circuit breaker if any condition is met
            if price_change > self.price_change_threshold or volume_trigger:
                self.is_triggered = True
                self.cooldown_counter = self.cooldown_periods
                
                # Add trigger information
                no_trade_action['safeguard_info'].update({
                    'price_change': price_change,
                    'price_threshold': self.price_change_threshold,
                    'volume_trigger': volume_trigger,
                    'cooldown_periods': self.cooldown_periods
                })
                
                return True, no_trade_action
        
        return False, action


class PositionSizingSafeguard(Safeguard):
    """
    Safeguard that adjusts position sizing based on various risk factors.
    
    This safeguard implements position sizing rules like Kelly criterion or
    volatility-based sizing to manage risk exposure.
    """
    
    def __init__(self, 
                 max_position_size: float = 0.2,         # 20% of capital
                 base_volatility: float = 0.01,          # 1% baseline volatility
                 lookback_window: int = 20,
                 kelly_fraction: float = 0.5,            # Half-Kelly for conservatism
                 min_position_size: float = 0.01,        # 1% min position
                 name: str = "PositionSizingSafeguard"):
        """
        Initialize the position sizing safeguard.
        
        Args:
            max_position_size: Maximum position size as a fraction of capital
            base_volatility: Baseline volatility for scaling
            lookback_window: Window for calculating volatility
            kelly_fraction: Fraction of Kelly-suggested size to use
            min_position_size: Minimum position size
            name: Name for the safeguard
        """
        super().__init__(name)
        self.max_position_size = max_position_size
        self.base_volatility = base_volatility
        self.lookback_window = lookback_window
        self.kelly_fraction = kelly_fraction
        self.min_position_size = min_position_size
        
        # Win rate tracking
        self.trades_history = []
    
    def check(self, 
              data: pd.DataFrame, 
              action: Dict[str, Any], 
              state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if position sizing safeguard should be triggered.
        
        Args:
            data: Market data
            action: Action proposed by the strategy
            state: Current state of the environment/strategy
            
        Returns:
            Tuple of (should_override, modified_action)
        """
        if not self.is_active:
            return False, action
        
        # Skip if not a trade action
        if 'type' not in action or action['type'] == 'none':
            return False, action
        
        # Create a modified action to adjust
        modified_action = action.copy()
        
        # Calculate volatility-based position size
        volatility_factor = 1.0
        
        if len(data) >= self.lookback_window:
            recent_data = data.iloc[-self.lookback_window:]
            returns = recent_data['close'].pct_change().dropna()
            current_volatility = returns.std()
            
            # Scale position size inversely with volatility
            volatility_factor = min(1.0, self.base_volatility / max(current_volatility, 1e-6))
        
        # Calculate Kelly-based position size if we have trade history
        kelly_factor = 1.0
        
        if len(self.trades_history) >= 10:  # Need reasonable history
            wins = [t for t in self.trades_history if t > 0]
            win_rate = len(wins) / len(self.trades_history)
            
            if win_rate > 0:
                avg_win = sum(wins) / len(wins) if wins else 0
                losses = [abs(t) for t in self.trades_history if t < 0]
                avg_loss = sum(losses) / len(losses) if losses else 1
                
                if avg_loss > 0:
                    # Kelly formula: f* = (p * b - q) / b where:
                    # f* = fraction of capital to bet
                    # p = probability of winning
                    # q = probability of losing (1-p)
                    # b = win/loss ratio (average win / average loss)
                    
                    b = avg_win / avg_loss
                    q = 1 - win_rate
                    
                    kelly_size = (win_rate * b - q) / b
                    
                    # Apply Kelly fraction and clamp to valid range
                    kelly_factor = max(0, min(1, kelly_size * self.kelly_fraction))
        
        # Determine position size
        base_size = min(self.max_position_size, volatility_factor * self.max_position_size)
        position_size = max(self.min_position_size, base_size * kelly_factor)
        
        # Update action
        if 'position_size' in modified_action:
            original_size = modified_action['position_size']
            modified_action['position_size'] = min(original_size, position_size)
        elif 'size' in modified_action:
            original_size = modified_action['size']
            modified_action['size'] = min(original_size, position_size)
        else:
            modified_action['position_size'] = position_size
        
        # Add safeguard info
        modified_action['safeguard_triggered'] = True
        modified_action['safeguard_info'] = {
            'safeguard': self.name,
            'volatility_factor': volatility_factor,
            'kelly_factor': kelly_factor,
            'original_size': original_size if 'original_size' in locals() else None,
            'adjusted_size': modified_action.get('position_size', modified_action.get('size'))
        }
        
        # Update trade history if this is a completed trade
        if 'trade_result' in state:
            self.trades_history.append(state['trade_result'])
            
            # Limit history to most recent trades
            if len(self.trades_history) > 100:
                self.trades_history = self.trades_history[-100:]
        
        return True, modified_action  # Always apply position sizing


class TimeBasedSafeguard(Safeguard):
    """
    Safeguard that restricts trading during specific time periods.
    
    This safeguard prevents trading around important economic announcements 
    or during known periods of low liquidity.
    """
    
    def __init__(self, 
                 restricted_times: List[Dict[str, Any]] = None,
                 prohibited_days: List[int] = None,  # 0=Monday, 6=Sunday
                 time_zone: str = 'UTC',
                 name: str = "TimeBasedSafeguard"):
        """
        Initialize the time-based safeguard.
        
        Args:
            restricted_times: List of dicts with start_time, end_time, and description
            prohibited_days: List of days of the week to avoid trading
            time_zone: Time zone for the restrictions
            name: Name for the safeguard
        """
        super().__init__(name)
        self.restricted_times = restricted_times or []
        self.prohibited_days = prohibited_days or []
        self.time_zone = time_zone
    
    def check(self, 
              data: pd.DataFrame, 
              action: Dict[str, Any], 
              state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if time-based safeguard should be triggered.
        
        Args:
            data: Market data
            action: Action proposed by the strategy
            state: Current state of the environment/strategy
            
        Returns:
            Tuple of (should_override, modified_action)
        """
        if not self.is_active:
            return False, action
        
        # Skip if not a trade action
        if 'type' not in action or action['type'] == 'none':
            return False, action
        
        # Get current timestamp
        current_time = data.iloc[-1]['timestamp']
        
        # Check if the timestamp is a pandas Timestamp, if not convert it
        if not isinstance(current_time, pd.Timestamp):
            try:
                current_time = pd.Timestamp(current_time)
            except:
                return False, action  # Can't parse timestamp, don't trigger
        
        # Create a "no trade" action to return if restrictions apply
        no_trade_action = action.copy()
        no_trade_action['type'] = 'none'
        no_trade_action['position_size'] = 0.0 if 'position_size' in action else 0.0
        no_trade_action['safeguard_triggered'] = True
        no_trade_action['safeguard_info'] = {'safeguard': self.name}
        
        # Check for prohibited days
        if self.prohibited_days and current_time.weekday() in self.prohibited_days:
            no_trade_action['safeguard_info']['restriction'] = f"Prohibited day: {current_time.day_name()}"
            return True, no_trade_action
        
        # Check for restricted time ranges
        for restriction in self.restricted_times:
            start_time = restriction.get('start_time')
            end_time = restriction.get('end_time')
            description = restriction.get('description', 'Restricted time')
            
            # Convert time strings to time objects if needed
            if isinstance(start_time, str):
                start_time = pd.Timestamp(start_time).time()
            if isinstance(end_time, str):
                end_time = pd.Timestamp(end_time).time()
            
            # Check if current time is within restricted range
            if start_time and end_time:
                current_time_only = current_time.time()
                
                # Handle cases where start_time > end_time (overnight)
                if start_time > end_time:
                    if current_time_only >= start_time or current_time_only <= end_time:
                        no_trade_action['safeguard_info']['restriction'] = description
                        return True, no_trade_action
                else:
                    if start_time <= current_time_only <= end_time:
                        no_trade_action['safeguard_info']['restriction'] = description
                        return True, no_trade_action
        
        return False, action


class CorrelationBreakdownSafeguard(Safeguard):
    """
    Safeguard that detects breakdowns in correlation patterns.
    
    This safeguard monitors correlations between related assets and reduces
    exposure when usual correlations break down, which can signal market stress.
    """
    
    def __init__(self, 
                 correlation_pairs: List[Tuple[str, str]] = None,
                 lookback_window: int = 60,
                 threshold: float = 1.5,  # Std devs from mean correlation
                 reduction_factor: float = 0.5,
                 name: str = "CorrelationBreakdownSafeguard"):
        """
        Initialize the correlation breakdown safeguard.
        
        Args:
            correlation_pairs: List of tuples with asset pairs to monitor
            lookback_window: Window for calculating correlation
            threshold: Threshold in standard deviations to trigger
            reduction_factor: Factor by which to reduce position size
            name: Name for the safeguard
        """
        super().__init__(name)
        self.correlation_pairs = correlation_pairs or []
        self.lookback_window = lookback_window
        self.threshold = threshold
        self.reduction_factor = reduction_factor
        
        # Track correlation history
        self.correlation_history = {pair: [] for pair in self.correlation_pairs}
    
    def check(self, 
              data: pd.DataFrame, 
              action: Dict[str, Any], 
              state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if correlation breakdown safeguard should be triggered.
        
        Args:
            data: Market data (must include columns for all assets in correlation_pairs)
            action: Action proposed by the strategy
            state: Current state of the environment/strategy
            
        Returns:
            Tuple of (should_override, modified_action)
        """
        if not self.is_active or not self.correlation_pairs:
            return False, action
        
        # Skip if we don't have enough data
        if len(data) < self.lookback_window + 1:  # Need data for returns
            return False, action
        
        # Create a modified action
        modified_action = action.copy()
        trigger_info = []
        
        # Check each correlation pair
        breakdown_detected = False
        
        for asset1, asset2 in self.correlation_pairs:
            # Skip if we don't have data for both assets
            if asset1 not in data.columns or asset2 not in data.columns:
                continue
            
            # Calculate returns
            recent_data = data.iloc[-self.lookback_window:]
            returns1 = recent_data[asset1].pct_change().dropna()
            returns2 = recent_data[asset2].pct_change().dropna()
            
            # Skip if we don't have enough return data
            if len(returns1) < 20 or len(returns2) < 20:
                continue
            
            # Calculate current correlation
            current_corr = returns1.corr(returns2)
            pair_key = f"{asset1}_{asset2}"
            
            # If we have correlation history, check for breakdown
            if pair_key in self.correlation_history and self.correlation_history[pair_key]:
                corr_history = self.correlation_history[pair_key]
                mean_corr = np.mean(corr_history)
                std_corr = np.std(corr_history)
                
                # Check for significant deviation
                if std_corr > 0 and abs(current_corr - mean_corr) > self.threshold * std_corr:
                    breakdown_detected = True
                    
                    # Add to trigger info
                    trigger_info.append({
                        'pair': (asset1, asset2),
                        'current_corr': current_corr,
                        'mean_corr': mean_corr,
                        'std_corr': std_corr,
                        'threshold': self.threshold,
                        'deviation': abs(current_corr - mean_corr) / std_corr
                    })
            
            # Update correlation history
            if pair_key in self.correlation_history:
                self.correlation_history[pair_key].append(current_corr)
                
                # Limit history length
                if len(self.correlation_history[pair_key]) > 100:
                    self.correlation_history[pair_key] = self.correlation_history[pair_key][-100:]
            else:
                self.correlation_history[pair_key] = [current_corr]
        
        # If correlation breakdown detected, reduce position size
        if breakdown_detected:
            if 'position_size' in modified_action:
                modified_action['position_size'] *= self.reduction_factor
            elif 'size' in modified_action:
                modified_action['size'] *= self.reduction_factor
            
            modified_action['safeguard_triggered'] = True
            modified_action['safeguard_info'] = {
                'safeguard': self.name,
                'reduction_factor': self.reduction_factor,
                'trigger_details': trigger_info
            }
            
            return True, modified_action
        
        return False, action


class SafeguardEnsemble:
    """
    Ensemble of multiple safeguards with priority-based execution.
    
    This class applies multiple safeguards in order of priority, with higher
    priority safeguards having the ability to override lower priority ones.
    """
    
    def __init__(self, 
                 safeguards: List[Tuple[Safeguard, int]] = None,
                 fallback_action: Optional[Dict[str, Any]] = None,
                 name: str = "SafeguardEnsemble"):
        """
        Initialize the safeguard ensemble.
        
        Args:
            safeguards: List of tuples (safeguard, priority)
            fallback_action: Default action to take if all safeguards fail
            name: Name for the ensemble
        """
        self.safeguards = safeguards or []
        self.fallback_action = fallback_action
        self.name = name
        
        # Sort safeguards by priority (higher priority first)
        self.safeguards.sort(key=lambda x: x[1], reverse=True)
    
    def add_safeguard(self, safeguard: Safeguard, priority: int = 0):
        """
        Add a safeguard to the ensemble.
        
        Args:
            safeguard: Safeguard instance to add
            priority: Priority level (higher values = higher priority)
        """
        self.safeguards.append((safeguard, priority))
        self.safeguards.sort(key=lambda x: x[1], reverse=True)
    
    def remove_safeguard(self, safeguard_name: str):
        """
        Remove a safeguard from the ensemble.
        
        Args:
            safeguard_name: Name of the safeguard to remove
        """
        self.safeguards = [(s, p) for s, p in self.safeguards if s.name != safeguard_name]
    
    def check_safeguards(self, 
                         data: pd.DataFrame, 
                         action: Dict[str, Any], 
                         state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply all safeguards in priority order.
        
        Args:
            data: Market data
            action: Action proposed by the strategy
            state: Current state of the environment/strategy
            
        Returns:
            Modified action after applying safeguards
        """
        current_action = action.copy()
        triggered_safeguards = []
        
        # Apply safeguards in priority order
        for safeguard, priority in self.safeguards:
            should_override, modified_action = safeguard.check(data, current_action, state)
            
            if should_override:
                current_action = modified_action
                triggered_safeguards.append({
                    'safeguard': safeguard.name,
                    'priority': priority,
                    'info': modified_action.get('safeguard_info', {})
                })
        
        # Add ensemble info
        if triggered_safeguards:
            current_action['ensemble_info'] = {
                'name': self.name,
                'triggered_safeguards': triggered_safeguards,
                'safeguard_count': len(triggered_safeguards)
            }
        
        return current_action
    
    def __str__(self) -> str:
        """String representation of the ensemble."""
        return f"{self.name} with {len(self.safeguards)} safeguards" 