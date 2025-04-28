"""
Statistical Validator Module

This module provides a signal validator that uses statistical methods to validate trading signals.
"""

import logging
import numpy as np
from typing import Dict, Any, Optional, List, Tuple

from ..models import TradingSignal, SignalValidationResult
from .base_validator import BaseSignalValidator

class StatisticalValidator(BaseSignalValidator):
    """
    Validates trading signals using statistical methods.
    
    This validator uses statistical techniques like z-score analysis and 
    historical success rates to validate trading signals. It adapts thresholds 
    based on current market conditions and historical performance.
    """
    
    def __init__(self, name: str = "statistical_validator", config: Dict[str, Any] = None):
        """
        Initialize the statistical validator.
        
        Args:
            name: Name of the validator
            config: Configuration dictionary
        """
        super().__init__(name, config or {})
        
        # Confidence threshold for signal validation
        self.confidence_threshold = self.config.get("confidence_threshold", 0.7)
        
        # Window sizes for various calculations
        self.historical_window = self.config.get("historical_window", 50)
        
        # Historical signal data for each agent and trading pair
        # Format: {(agent_id, trading_pair, signal_type): [success_rate_history]}
        self.historical_data = {}
        
        # Signal type weights for confidence calculation
        self.signal_type_weights = self.config.get("signal_type_weights", {
            "trend": 0.8,
            "reversal": 0.6,
            "breakout": 0.7,
            "support_resistance": 0.65,
            "momentum": 0.75,
            "volume": 0.6,
            "volatility": 0.5,
            "default": 0.5
        })
        
        self.logger.info(f"Statistical validator initialized with threshold {self.confidence_threshold}")
    
    def _validate_signal(self, signal: TradingSignal) -> SignalValidationResult:
        """
        Validate a trading signal using statistical methods.
        
        This method analyzes the signal using statistical techniques and historical
        performance data to determine its validity.
        
        Args:
            signal: Trading signal to validate
            
        Returns:
            SignalValidationResult indicating whether the signal is valid
        """
        # Calculate confidence score based on signal attributes and historical data
        confidence = self._calculate_confidence(signal)
        
        # Determine if signal is valid based on confidence threshold
        is_valid = confidence >= self.confidence_threshold
        
        # Log validation result
        if is_valid:
            self.logger.info(f"Signal {signal.id} validated with confidence {confidence:.2f}")
        else:
            self.logger.info(f"Signal {signal.id} rejected with confidence {confidence:.2f}")
        
        # Create validation result
        result = SignalValidationResult(
            signal_id=signal.id,
            is_valid=is_valid,
            confidence=confidence,
            threshold=self.confidence_threshold,
            validator_name=self.name
        )
        
        return result
    
    def _calculate_confidence(self, signal: TradingSignal) -> float:
        """
        Calculate confidence score for a signal.
        
        Args:
            signal: Trading signal to calculate confidence for
            
        Returns:
            Confidence score between 0 and 1
        """
        # Get base confidence from signal
        base_confidence = signal.confidence or 0.5
        
        # Get weight for signal type
        signal_type_weight = self.signal_type_weights.get(
            signal.signal_type, 
            self.signal_type_weights["default"]
        )
        
        # Get historical performance if available
        key = (signal.agent_id, signal.trading_pair, signal.signal_type)
        historical_success = self.historical_data.get(key, [0.5])[-1] if key in self.historical_data else 0.5
        
        # Calculate weighted confidence
        confidence = (
            base_confidence * 0.4 +  # 40% signal's own confidence
            signal_type_weight * 0.3 +  # 30% signal type weight
            historical_success * 0.3    # 30% historical performance
        )
        
        return min(max(confidence, 0.0), 1.0)  # Ensure between 0 and 1
    
    def update_historical_data(self, signal: TradingSignal, was_successful: bool) -> None:
        """
        Update historical performance data for a signal source.
        
        Args:
            signal: The signal that was validated
            was_successful: Whether the signal resulted in a successful trade
        """
        key = (signal.agent_id, signal.trading_pair, signal.signal_type)
        
        # Initialize history if not exists
        if key not in self.historical_data:
            self.historical_data[key] = [0.5]  # Start with neutral value
        
        # Get current history
        history = self.historical_data[key]
        
        # Calculate new success rate (exponential moving average)
        current_rate = history[-1]
        alpha = 2 / (self.historical_window + 1)  # Smoothing factor
        new_rate = current_rate + alpha * (1.0 if was_successful else 0.0 - current_rate)
        
        # Update history
        history.append(new_rate)
        
        # Keep only the last N values
        self.historical_data[key] = history[-self.historical_window:]
        
        self.logger.debug(f"Updated success rate for {key} to {new_rate:.2f}")
    
    def update_threshold(self, new_threshold: float) -> None:
        """
        Update the confidence threshold.
        
        Args:
            new_threshold: New confidence threshold between 0 and 1
        """
        if not (0 <= new_threshold <= 1):
            self.logger.warning(f"Invalid threshold {new_threshold}, must be between 0 and 1")
            return
            
        self.confidence_threshold = new_threshold
        self.logger.info(f"Updated confidence threshold to {new_threshold}")
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for the validator.
        
        Returns:
            Dictionary of performance metrics
        """
        metrics = super().get_performance_metrics()
        
        # Add additional metrics specific to statistical validator
        metrics.update({
            "confidence_threshold": self.confidence_threshold,
            "signal_type_weights": self.signal_type_weights,
            "historical_data_count": len(self.historical_data)
        })
        
        return metrics 