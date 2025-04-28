"""
Temporal Filter Module

This module provides a filter that evaluates the temporal validity of signals,
filtering out signals that are outdated or outside their effective timeframe.
"""

import logging
import time
from typing import Dict, Any, Optional

from ..models import TradingSignal, SignalFilteringResult
from .base_filter import BaseSignalFilter

logger = logging.getLogger(__name__)

class TemporalFilter(BaseSignalFilter):
    """
    Filters signals based on their temporal validity.
    
    This filter evaluates whether a signal is still relevant based on its age,
    timeframe, and other temporal factors.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the temporal filter.
        
        Args:
            config: Configuration parameters for the filter
        """
        default_config = {
            'filtering_threshold': 0.5,
            'max_age_seconds': {
                'm1': 60,        # 1 minute signals valid for 1 minute
                'm5': 300,       # 5 minute signals valid for 5 minutes
                'm15': 900,      # 15 minute signals valid for 15 minutes
                'm30': 1800,     # 30 minute signals valid for 30 minutes
                'h1': 3600,      # 1 hour signals valid for 1 hour
                'h4': 14400,     # 4 hour signals valid for 4 hours
                'd1': 86400,     # 1 day signals valid for 1 day
                'w1': 604800,    # 1 week signals valid for 1 week
            },
            'age_decay_factor': 0.8,  # How quickly confidence decays with age
            'log_level': 'INFO'
        }
        
        # Merge default config with provided config
        merged_config = default_config.copy()
        if config:
            merged_config.update(config)
            
            # Handle nested dict updates for max_age_seconds
            if 'max_age_seconds' in config and isinstance(config['max_age_seconds'], dict):
                for timeframe, value in config['max_age_seconds'].items():
                    merged_config['max_age_seconds'][timeframe] = value
        
        super().__init__('temporal_filter', merged_config)
        logger.info("Initialized TemporalFilter")
    
    def _filter_signal(self, signal: TradingSignal) -> SignalFilteringResult:
        """
        Evaluate the temporal validity of the signal.
        
        Args:
            signal: The trading signal to filter
            
        Returns:
            SignalFilteringResult containing the filtering assessment
        """
        # Calculate signal age in seconds
        current_time = time.time()
        signal_age_seconds = current_time - signal.created_at
        
        # Get the maximum age for this timeframe
        timeframe = signal.timeframe
        if timeframe not in self.config['max_age_seconds']:
            logger.warning(f"Unknown timeframe '{timeframe}' for signal {signal.id}, using default threshold")
            max_age = 300  # Default to 5 minutes
        else:
            max_age = self.config['max_age_seconds'][timeframe]
        
        # Calculate confidence based on age
        confidence = self._calculate_temporal_confidence(signal_age_seconds, max_age)
        
        # Determine if the signal should be filtered out
        is_filtered_out = confidence < self.filtering_threshold
        
        # Prepare reason text
        if is_filtered_out:
            reason = f"Signal is too old (age: {signal_age_seconds:.1f}s, max: {max_age}s, confidence: {confidence:.2f})"
        else:
            reason = f"Signal is still valid (age: {signal_age_seconds:.1f}s, max: {max_age}s, confidence: {confidence:.2f})"
        
        return SignalFilteringResult(
            signal_id=signal.id,
            is_filtered_out=is_filtered_out,
            confidence=confidence,
            threshold=self.filtering_threshold,
            reason=reason
        )
    
    def _calculate_temporal_confidence(self, age_seconds: float, max_age: float) -> float:
        """
        Calculate confidence score based on signal age.
        
        The confidence decays exponentially as the signal gets older,
        reaching the filtering threshold at max_age.
        
        Args:
            age_seconds: Age of the signal in seconds
            max_age: Maximum valid age for the signal in seconds
            
        Returns:
            Confidence score between 0 and 1
        """
        # If signal is already older than max_age, return 0
        if age_seconds >= max_age:
            return 0.0
        
        # Calculate relative age (0.0 to 1.0)
        relative_age = age_seconds / max_age
        
        # Apply decay factor to determine how quickly confidence drops
        # Higher decay_factor = faster drop in confidence
        decay_factor = self.config['age_decay_factor']
        
        # Exponential decay formula
        confidence = 1.0 - (relative_age ** decay_factor)
        
        return max(0.0, min(1.0, confidence)) 