"""
Market Adaptation Strategy
-------------------------
Adapts trading strategies based on detected market regimes.
"""

import json
import os
from datetime import datetime
from typing import Dict, Any


class AdaptationStrategy:
    """
    AdaptationStrategy adapts trading strategy parameters based on market conditions
    using rules defined in a configuration file.
    
    The strategy can adapt parameters based on:
    - Risk regime adjustments
    - Volatility adjustments
    - Trend adjustments (uptrend, downtrend, ranging)
    - Time-based adjustments (hour of day, day of week)
    - Regime-specific settings
    
    Each adaptation can be configured through the rules file.
    """
    
    def __init__(self, rules_file: str = None):
        """
        Initialize the AdaptationStrategy with rules from a file.
        
        Args:
            rules_file: Path to the JSON file containing adaptation rules.
                       If None, uses the default rules file.
        """
        if rules_file is None:
            # Use default rules file in the same directory as this file
            dir_path = os.path.dirname(os.path.realpath(__file__))
            rules_file = os.path.join(dir_path, "sample_adaptation_rules.json")
        
        # Load rules from file
        with open(rules_file, 'r') as f:
            self.rules = json.load(f)
        
        # Initialize last adaptation time tracking
        self.last_adaptation_time = {}
        
        # Initialize adaptation statistics
        self.reset_adaptation_stats()
    
    def reset_adaptation_stats(self):
        """Reset all adaptation statistics to zero."""
        self.adaptation_stats = {
            "risk_adjustments": 0,
            "volatility_adjustments": 0,
            "trend_adjustments": 0,
            "time_based_adjustments": 0,
            "regime_specific_adjustments": 0,
            "parameter_bounds_enforced": 0,
            "total_adaptations": 0
        }
    
    def get_adaptation_stats(self) -> Dict[str, int]:
        """
        Get statistics on adaptations performed.
        
        Returns:
            Dictionary with adaptation statistics
        """
        return self.adaptation_stats
    
    def adapt_strategy_parameters(self, parameters: Dict[str, float], market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Adapt strategy parameters based on current market conditions and rules.
        
        Args:
            parameters: Dictionary containing strategy parameters to adapt
                       (take_profit, stop_loss, position_size, entry_threshold)
            market_data: Dictionary containing current market data
                         (volatility, trend, regime, etc.)
        
        Returns:
            Dictionary with adapted strategy parameters
        """
        # Clone parameters to avoid modifying the original
        adapted_params = parameters.copy()
        strategy_id = market_data.get("strategy_id", "default")
        
        # Check cooldown period
        current_time = datetime.now()
        if strategy_id in self.last_adaptation_time:
            time_since_last_adaptation = (current_time - self.last_adaptation_time[strategy_id]).total_seconds()
            if time_since_last_adaptation < self.rules["cooldown_period"]:
                # Skip adaptation if within cooldown period
                return parameters  # Return original parameters, not the copy
        
        # Apply different adaptation mechanisms in the correct order
        if "current_regime" in market_data:
            # First apply risk adjustment
            adapted_params = self.apply_risk_adjustment(adapted_params, market_data)
            
        if "current_volatility" in market_data and "baseline_volatility" in market_data:
            # Then volatility adjustment
            adapted_params = self.apply_volatility_adjustment(adapted_params, market_data)
            
        if "current_trend" in market_data:
            # Then trend adjustment
            adapted_params = self.apply_trend_adjustment(adapted_params, market_data)
        
        # Apply time-based adjustment
        adapted_params = self.apply_time_based_adjustment(adapted_params)
        
        # Apply regime-specific settings last (will override previous adjustments)
        if "current_regime" in market_data:
            adapted_params = self.apply_regime_specific_adjustment(adapted_params, market_data)
        
        # Enforce parameter bounds
        adapted_params = self.enforce_parameter_bounds(adapted_params)
        
        # Update adaptation time
        self.last_adaptation_time[strategy_id] = current_time
        
        # Update total adaptations
        self.adaptation_stats["total_adaptations"] = sum([
            self.adaptation_stats["risk_adjustments"],
            self.adaptation_stats["volatility_adjustments"],
            self.adaptation_stats["trend_adjustments"],
            self.adaptation_stats["time_based_adjustments"],
            self.adaptation_stats["regime_specific_adjustments"]
        ])
        
        return adapted_params
    
    def apply_risk_adjustment(self, parameters: Dict[str, float], market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Apply risk adjustment based on current market regime.
        
        Args:
            parameters: Dictionary with strategy parameters
            market_data: Dictionary with current market data, must include 'current_regime'
        
        Returns:
            Dictionary with risk-adjusted parameters
        """
        adjusted_params = parameters.copy()
        current_regime = market_data.get("current_regime")
        
        # Find the risk factor for the current regime
        risk_factor = 1.0  # Default risk factor
        for regime in self.rules["risk_adjustment"]["regimes"]:
            if regime["regime_id"] == current_regime:
                risk_factor = regime["risk_factor"]
                break
        
        # Apply risk factor to position size
        if "position_size" in adjusted_params:
            adjusted_params["position_size"] *= risk_factor
        
        # Update adaptation stats
        self.adaptation_stats["risk_adjustments"] += 1
        
        return adjusted_params
    
    def apply_volatility_adjustment(self, parameters: Dict[str, float], market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Apply volatility-based adjustments to parameters.
        
        Args:
            parameters: Dictionary with strategy parameters
            market_data: Dictionary with current market data, must include 'current_volatility'
                         and 'baseline_volatility'
        
        Returns:
            Dictionary with volatility-adjusted parameters
        """
        adjusted_params = parameters.copy()
        current_volatility = market_data.get("current_volatility")
        baseline_volatility = market_data.get("baseline_volatility", self.rules["volatility_adjustment"]["baseline_volatility"])
        
        # Determine if we're in high or low volatility
        if current_volatility > baseline_volatility:
            # High volatility adjustments
            adjustments = self.rules["volatility_adjustment"]["high_volatility_adjustments"]
            
            if "stop_loss" in adjusted_params and "stop_loss" in adjustments:
                adjusted_params["stop_loss"] = max(adjusted_params["stop_loss"], adjustments["stop_loss"])
                
            if "take_profit" in adjusted_params and "take_profit" in adjustments:
                adjusted_params["take_profit"] = max(adjusted_params["take_profit"], adjustments["take_profit"])
                
            if "entry_threshold" in adjusted_params and "entry_threshold" in adjustments:
                adjusted_params["entry_threshold"] = max(adjusted_params["entry_threshold"], adjustments["entry_threshold"])
                
        elif current_volatility < baseline_volatility:
            # Low volatility adjustments
            adjustments = self.rules["volatility_adjustment"]["low_volatility_adjustments"]
            
            if "stop_loss" in adjusted_params and "stop_loss" in adjustments:
                adjusted_params["stop_loss"] = min(adjusted_params["stop_loss"], adjustments["stop_loss"])
                
            if "take_profit" in adjusted_params and "take_profit" in adjustments:
                adjusted_params["take_profit"] = min(adjusted_params["take_profit"], adjustments["take_profit"])
                
            if "entry_threshold" in adjusted_params and "entry_threshold" in adjustments:
                adjusted_params["entry_threshold"] = min(adjusted_params["entry_threshold"], adjustments["entry_threshold"])
        
        # Update adaptation stats
        self.adaptation_stats["volatility_adjustments"] += 1
        
        return adjusted_params
    
    def apply_trend_adjustment(self, parameters: Dict[str, float], market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Apply trend-based adjustments to parameters.
        
        Args:
            parameters: Dictionary with strategy parameters
            market_data: Dictionary with current market data, must include 'current_trend'
        
        Returns:
            Dictionary with trend-adjusted parameters
        """
        adjusted_params = parameters.copy()
        current_trend = market_data.get("current_trend", "ranging")  # Default to ranging if not specified
        
        # Get trend adjustments
        if current_trend in self.rules["trend_adjustment"]:
            trend_factors = self.rules["trend_adjustment"][current_trend]
            
            # Apply position size factor
            if "position_size" in adjusted_params and "position_size_factor" in trend_factors:
                adjusted_params["position_size"] *= trend_factors["position_size_factor"]
            
            # Apply take profit factor
            if "take_profit" in adjusted_params and "take_profit_factor" in trend_factors:
                adjusted_params["take_profit"] *= trend_factors["take_profit_factor"]
            
            # Apply stop loss factor
            if "stop_loss" in adjusted_params and "stop_loss_factor" in trend_factors:
                adjusted_params["stop_loss"] *= trend_factors["stop_loss_factor"]
        
        # Update adaptation stats
        self.adaptation_stats["trend_adjustments"] += 1
        
        return adjusted_params
    
    def apply_time_based_adjustment(self, parameters: Dict[str, float]) -> Dict[str, float]:
        """
        Apply time-based adjustments based on hour of day and day of week.
        
        Args:
            parameters: Dictionary with strategy parameters
        
        Returns:
            Dictionary with time-adjusted parameters
        """
        adjusted_params = parameters.copy()
        
        # Get current time
        now = self.get_current_time()
        current_hour = now.hour
        current_day = now.strftime("%A").lower()  # Day name in lowercase
        
        # Apply hour-based adjustments
        hour_factor = 1.0
        for hour_range, hour_data in self.rules["time_based_adjustment"]["hours"].items():
            start_hour, end_hour = map(int, hour_range.split('-'))
            if start_hour <= current_hour <= end_hour:
                hour_factor = hour_data["factor"]
                break
        
        # Apply day-based adjustments
        day_factor = 1.0
        if current_day in self.rules["time_based_adjustment"]["days"]:
            day_factor = self.rules["time_based_adjustment"]["days"][current_day]["factor"]
        
        # Combine factors and apply
        combined_factor = hour_factor * day_factor
        
        if "position_size" in adjusted_params:
            adjusted_params["position_size"] *= combined_factor
        
        # Update adaptation stats
        self.adaptation_stats["time_based_adjustments"] += 1
        
        return adjusted_params
    
    def get_current_time(self):
        """
        Get current time. Extracted to a method to allow mocking in tests.
        
        Returns:
            Current datetime
        """
        return datetime.now()
    
    def apply_regime_specific_adjustment(self, parameters: Dict[str, float], market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Apply regime-specific parameter adjustments.
        
        Args:
            parameters: Dictionary with strategy parameters
            market_data: Dictionary with current market data, must include 'current_regime'
        
        Returns:
            Dictionary with regime-adjusted parameters
        """
        adjusted_params = parameters.copy()
        current_regime = market_data.get("current_regime")
        
        # Look up regime-specific settings
        regime_key = f"regime_{current_regime}"
        if regime_key in self.rules["regime_specific_settings"]:
            regime_settings = self.rules["regime_specific_settings"][regime_key]
            
            # Apply regime-specific settings
            for param, value in regime_settings.items():
                if param in adjusted_params:
                    adjusted_params[param] = value
        
        # Update adaptation stats
        self.adaptation_stats["regime_specific_adjustments"] += 1
        
        return adjusted_params
    
    def enforce_parameter_bounds(self, parameters: Dict[str, float]) -> Dict[str, float]:
        """
        Enforce minimum and maximum bounds on parameters.
        
        Args:
            parameters: Dictionary with strategy parameters
        
        Returns:
            Dictionary with bounded parameters
        """
        bounded_params = parameters.copy()
        bounds_enforced = 0
        
        # Enforce bounds for each parameter
        for param, param_bounds in self.rules["parameter_bounds"].items():
            if param in bounded_params:
                min_value = param_bounds.get("min")
                max_value = param_bounds.get("max")
                
                if min_value is not None and bounded_params[param] < min_value:
                    bounded_params[param] = min_value
                    bounds_enforced += 1
                    
                if max_value is not None and bounded_params[param] > max_value:
                    bounded_params[param] = max_value
                    bounds_enforced += 1
        
        # Update adaptation stats
        self.adaptation_stats["parameter_bounds_enforced"] += bounds_enforced
        
        return bounded_params 