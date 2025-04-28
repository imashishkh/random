"""
Base Signal Validator

This module provides the base class for signal validation components.
Signal validators assess the quality and reliability of trading signals.
"""

import logging
import time
from typing import Dict, List, Any, Optional, Union, Callable
from datetime import datetime

from ....utils.logging.logger import get_logger
from .orchestration.models import TradingSignal, SignalValidationResult, MarketConditions

logger = get_logger()


class BaseSignalValidator:
    """
    Base class for signal validators.
    
    Signal validators assess the quality and reliability of trading signals
    based on various criteria such as statistical properties, historical
    performance, and market conditions.
    """
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the signal validator.
        
        Args:
            name: Name of the validator for identification
            config: Configuration dictionary for the validator
        """
        self.name = name
        self.config = config or {}
        
        # Configure logging level
        self._configure_logging()
        
        # Performance tracking
        self.performance_metrics = {
            'signals_processed': 0,
            'signals_validated': 0,
            'signals_rejected': 0,
            'validation_time_ms': [],
            'true_positives': 0,
            'false_positives': 0
        }
        
        logger.info(f"Initialized signal validator: {name}")
    
    def _configure_logging(self):
        """Configure logging based on validator config."""
        log_level = self.config.get('log_level', 'INFO')
        log_levels = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        logger.setLevel(log_levels.get(log_level, logging.INFO))
    
    def validate(self, signal: TradingSignal, market_conditions: Optional[MarketConditions] = None) -> SignalValidationResult:
        """
        Validate a trading signal.
        
        This is the main validation method that should be called externally.
        It handles performance tracking, timing, and validation result creation.
        
        Args:
            signal: Trading signal to validate
            market_conditions: Current market conditions (optional)
            
        Returns:
            Validation result
        """
        # Start timing
        start_time = time.time()
        
        try:
            # Perform the actual validation
            validation_data = self._validate_signal(signal, market_conditions)
            
            # Create validation result
            is_valid = validation_data['confidence'] >= validation_data['threshold']
            
            result = SignalValidationResult(
                signal_id=signal.id,
                is_valid=is_valid,
                confidence=validation_data['confidence'],
                threshold=validation_data['threshold'],
                components=validation_data.get('components', {}),
                metadata=validation_data.get('metadata', {})
            )
            
            # Update performance metrics
            self.performance_metrics['signals_processed'] += 1
            if is_valid:
                self.performance_metrics['signals_validated'] += 1
            else:
                self.performance_metrics['signals_rejected'] += 1
                
            # Log validation result
            if is_valid:
                logger.debug(f"Signal {signal.id} validated with confidence {result.confidence:.2f}")
            else:
                logger.debug(f"Signal {signal.id} rejected with confidence {result.confidence:.2f} (threshold: {result.threshold:.2f})")
            
            return result
            
        except Exception as e:
            # Handle validation errors
            logger.error(f"Error validating signal {signal.id}: {str(e)}")
            
            # Create failure result
            result = SignalValidationResult(
                signal_id=signal.id,
                is_valid=False,
                confidence=0.0,
                threshold=self.config.get('base_threshold', 0.6),
                metadata={'error': str(e)}
            )
            
            return result
            
        finally:
            # End timing and record
            end_time = time.time()
            validation_time_ms = (end_time - start_time) * 1000
            self.performance_metrics['validation_time_ms'].append(validation_time_ms)
            
            # Keep only the most recent 1000 measurements
            if len(self.performance_metrics['validation_time_ms']) > 1000:
                self.performance_metrics['validation_time_ms'] = self.performance_metrics['validation_time_ms'][-1000:]
    
    def _validate_signal(self, signal: TradingSignal, market_conditions: Optional[MarketConditions] = None) -> Dict[str, Any]:
        """
        Internal validation method to be implemented by derived classes.
        
        Args:
            signal: Trading signal to validate
            market_conditions: Current market conditions (optional)
            
        Returns:
            Dictionary with validation data including at least:
            - confidence: Validation confidence score
            - threshold: Threshold for valid/invalid decision
            - components: Individual component scores (optional)
            - metadata: Additional validation metadata (optional)
        """
        # Base implementation always invalidates signals
        # This should be overridden by derived classes
        logger.warning(f"Using base validator implementation for {signal.id} - should be overridden")
        
        return {
            'confidence': 0.0,
            'threshold': self.config.get('base_threshold', 0.6),
            'components': {},
            'metadata': {'warning': 'Using base implementation, should override'}
        }
    
    def update_threshold(self, new_threshold: float) -> None:
        """
        Update the validation threshold.
        
        Args:
            new_threshold: New threshold value between 0 and 1
        """
        if 0 <= new_threshold <= 1:
            self.config['base_threshold'] = new_threshold
            logger.info(f"Updated validation threshold to {new_threshold:.2f}")
        else:
            logger.warning(f"Invalid threshold value: {new_threshold}. Must be between 0 and 1.")
    
    def update_config(self, config_updates: Dict[str, Any]) -> None:
        """
        Update validator configuration.
        
        Args:
            config_updates: Dictionary of configuration updates
        """
        self.config.update(config_updates)
        logger.info(f"Updated validator configuration with {len(config_updates)} parameters")
        
        # Reconfigure logging if log_level was updated
        if 'log_level' in config_updates:
            self._configure_logging()
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get validator performance metrics.
        
        Returns:
            Dictionary of performance metrics
        """
        metrics = self.performance_metrics.copy()
        
        # Calculate average validation time
        if metrics['validation_time_ms']:
            metrics['avg_validation_time_ms'] = sum(metrics['validation_time_ms']) / len(metrics['validation_time_ms'])
        else:
            metrics['avg_validation_time_ms'] = 0
        
        # Calculate validation rate
        if metrics['signals_processed'] > 0:
            metrics['validation_rate'] = metrics['signals_validated'] / metrics['signals_processed']
        else:
            metrics['validation_rate'] = 0
            
        # Calculate precision if we have ground truth data
        if (metrics['true_positives'] + metrics['false_positives']) > 0:
            metrics['precision'] = metrics['true_positives'] / (metrics['true_positives'] + metrics['false_positives'])
        else:
            metrics['precision'] = 0
            
        return metrics
    
    def record_ground_truth(self, signal_id: str, was_correct: bool) -> None:
        """
        Record ground truth data for a validated signal.
        
        This is used to track the actual performance of the validator based on
        whether signals it validated resulted in profitable trades or not.
        
        Args:
            signal_id: ID of the signal
            was_correct: Whether the signal resulted in a profitable trade
        """
        # Update true/false positive counts
        if was_correct:
            self.performance_metrics['true_positives'] += 1
        else:
            self.performance_metrics['false_positives'] += 1
            
        logger.debug(f"Recorded ground truth for signal {signal_id}: {'correct' if was_correct else 'incorrect'}")
    
    def reset_performance_metrics(self) -> None:
        """Reset performance metrics."""
        self.performance_metrics = {
            'signals_processed': 0,
            'signals_validated': 0,
            'signals_rejected': 0,
            'validation_time_ms': [],
            'true_positives': 0,
            'false_positives': 0
        }
        logger.info(f"Reset performance metrics for validator: {self.name}") 