"""
Ensemble Signal Validator

This module provides a validator that combines results from multiple
signal validators to produce a more robust validation result.
"""

from typing import Dict, List, Any, Optional, Union, Type
import numpy as np
from datetime import datetime

from ....utils.logging.logger import get_logger
from .orchestration.models import TradingSignal, MarketConditions
from .orchestration.validation.base_validator import BaseSignalValidator
from .orchestration.validation.statistical_validator import StatisticalValidator
from .orchestration.validation.ml_validator import MLValidator
# Import additional validators as needed

logger = get_logger()


class EnsembleValidator(BaseSignalValidator):
    """
    Ensemble validator that combines multiple validators to produce a more robust
    validation result. Uses configurable weighting and combination strategies.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the ensemble validator.
        
        Args:
            config: Configuration dictionary
        """
        # Default configuration
        default_config = {
            'validators': {
                'statistical': {
                    'enabled': True,
                    'weight': 0.6,
                    'config': {}  # Pass-through config for validator
                },
                'ml': {
                    'enabled': True,
                    'weight': 0.4,
                    'config': {}  # Pass-through config for validator
                }
                # Add other validators here
            },
            'combine_method': 'weighted_average',  # Options: weighted_average, max, min, majority_vote
            'min_valid_validators': 1,             # Minimum validators needed for result
            'base_threshold': 0.65,                # Base threshold for signal validation
            'normalization': True,                 # Whether to normalize scores before combining
            'dynamic_weighting': False,            # Whether to adjust weights based on performance
            'performance_window': 100,             # Window size for performance tracking
            'performance_update_frequency': 50,    # How often to update dynamic weights
        }
        
        # Merge with provided config
        if config:
            merged_config = default_config.copy()
            self._deep_update(merged_config, config)
        else:
            merged_config = default_config
        
        # Initialize base class
        super().__init__(name="EnsembleValidator", config=merged_config)
        
        # Initialize validators
        self.validators = {}
        self._initialize_validators()
        
        # Initialize performance tracking
        self.validator_performance = {name: {'correct': 0, 'total': 0, 'score': 0.5} 
                                    for name in self.validators}
        self.validation_history = []
        self.last_weight_update = None
        
        logger.info("Ensemble validator initialized")
    
    def _deep_update(self, target: Dict, source: Dict) -> None:
        """
        Deep update of nested dictionaries.
        
        Args:
            target: Target dictionary to update
            source: Source dictionary with updates
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value
    
    def _initialize_validators(self) -> None:
        """
        Initialize the individual validators based on configuration.
        """
        validator_mapping = {
            'statistical': StatisticalValidator,
            'ml': MLValidator,
            # Add other validators here
        }
        
        # Initialize each enabled validator
        for name, config in self.config['validators'].items():
            if config.get('enabled', False):
                validator_class = validator_mapping.get(name)
                
                if validator_class:
                    # Initialize with specific config
                    validator = validator_class(config=config.get('config', {}))
                    self.validators[name] = validator
                    logger.info(f"Initialized {name} validator")
                else:
                    logger.warning(f"Unknown validator type: {name}")
        
        if not self.validators:
            logger.warning("No validators enabled in ensemble")
    
    def _validate_signal(self, signal: TradingSignal, market_conditions: Optional[MarketConditions] = None) -> Dict[str, Any]:
        """
        Validate a trading signal using multiple validators.
        
        Args:
            signal: Trading signal to validate
            market_conditions: Current market conditions
            
        Returns:
            Validation data dictionary
        """
        if not self.validators:
            logger.warning("No validators available in ensemble, using fallback")
            return {
                'confidence': signal.confidence * 0.8,  # Apply a discount
                'threshold': self.config['base_threshold'],
                'is_valid': signal.confidence > self.config['base_threshold'],
                'components': {},
                'metadata': {'validators_used': []}
            }
        
        # Collect validation results from each validator
        validation_results = {}
        valid_count = 0
        for name, validator in self.validators.items():
            try:
                result = validator.validate(signal, market_conditions)
                validation_results[name] = result
                if result.get('is_valid', False):
                    valid_count += 1
            except Exception as e:
                logger.error(f"Error in {name} validator: {str(e)}")
        
        # Prepare return structure
        validation_data = {
            'confidence': 0.0,
            'threshold': self.config['base_threshold'],
            'is_valid': False,
            'components': {},
            'metadata': {'validators_used': list(validation_results.keys())}
        }
        
        # Check if we have enough valid validators
        if len(validation_results) < self.config['min_valid_validators']:
            logger.warning(f"Not enough valid validators. Got {len(validation_results)}, need {self.config['min_valid_validators']}")
            validation_data['confidence'] = 0.0
            return validation_data
        
        # Combine results based on selected method
        combined_confidence = self._combine_validation_results(validation_results)
        
        # Set output fields
        validation_data['confidence'] = combined_confidence
        validation_data['is_valid'] = combined_confidence > self.config['base_threshold']
        
        # Store component scores for transparency
        validation_data['components'] = {
            f"{name}_confidence": result.get('confidence', 0.0)
            for name, result in validation_results.items()
        }
        
        # Store metadata
        validation_data['metadata']['valid_count'] = valid_count
        validation_data['metadata']['total_validators'] = len(validation_results)
        
        # Store validation for performance tracking
        self._store_validation(signal.id, validation_data, validation_results)
        
        # Update weights if dynamic weighting is enabled
        if (self.config['dynamic_weighting'] and
            len(self.validation_history) % self.config['performance_update_frequency'] == 0):
            self._update_validator_weights()
        
        return validation_data
    
    def _combine_validation_results(self, validation_results: Dict[str, Dict[str, Any]]) -> float:
        """
        Combine multiple validation results based on the configured method.
        
        Args:
            validation_results: Dictionary of validation results by validator name
            
        Returns:
            Combined confidence score
        """
        method = self.config['combine_method']
        
        # Extract confidences
        confidences = {}
        for name, result in validation_results.items():
            if 'confidence' in result:
                confidences[name] = result['confidence']
        
        # Check if we have any confidences
        if not confidences:
            return 0.0
        
        # Apply normalization if enabled
        if self.config['normalization'] and len(confidences) > 1:
            self._normalize_confidences(confidences)
        
        # Get validator weights (either static or dynamic)
        weights = self._get_validator_weights()
        
        # Apply combination method
        if method == 'weighted_average':
            total_weight = 0.0
            weighted_sum = 0.0
            
            for name, confidence in confidences.items():
                if name in weights:
                    weight = weights[name]
                    weighted_sum += confidence * weight
                    total_weight += weight
            
            if total_weight > 0:
                return weighted_sum / total_weight
            else:
                return sum(confidences.values()) / len(confidences)
                
        elif method == 'max':
            return max(confidences.values())
            
        elif method == 'min':
            return min(confidences.values())
            
        elif method == 'majority_vote':
            threshold = self.config['base_threshold']
            votes = sum(1 for conf in confidences.values() if conf > threshold)
            return votes / len(confidences)
            
        else:
            logger.warning(f"Unknown combination method: {method}")
            return sum(confidences.values()) / len(confidences)
    
    def _normalize_confidences(self, confidences: Dict[str, float]) -> None:
        """
        Normalize confidence scores, modifying the dictionary in place.
        
        Args:
            confidences: Dictionary of confidence scores by validator name
        """
        values = list(confidences.values())
        min_val = min(values)
        max_val = max(values)
        
        # Skip normalization if all values are the same
        if max_val == min_val:
            return
        
        # Apply min-max normalization
        for name in confidences:
            confidences[name] = (confidences[name] - min_val) / (max_val - min_val)
    
    def _get_validator_weights(self) -> Dict[str, float]:
        """
        Get the current weights for each validator.
        
        Returns:
            Dictionary of weights by validator name
        """
        if not self.config['dynamic_weighting']:
            # Use static weights from config
            return {name: self.config['validators'][name]['weight']
                   for name in self.validators
                   if name in self.config['validators']}
        else:
            # Use dynamically updated weights
            total_score = sum(data['score'] for data in self.validator_performance.values())
            
            if total_score > 0:
                return {name: data['score'] / total_score
                       for name, data in self.validator_performance.items()}
            else:
                # Fallback to equal weights
                return {name: 1.0 / len(self.validators) for name in self.validators}
    
    def _store_validation(self, signal_id: str, validation_data: Dict[str, Any], 
                         validator_results: Dict[str, Dict[str, Any]]) -> None:
        """
        Store validation result for performance tracking.
        
        Args:
            signal_id: ID of the validated signal
            validation_data: Combined validation result
            validator_results: Individual validator results
        """
        validation_entry = {
            'signal_id': signal_id,
            'timestamp': datetime.utcnow().isoformat(),
            'ensemble_result': validation_data.copy(),
            'validator_results': validator_results.copy(),
            'was_profitable': None  # Will be updated later
        }
        
        self.validation_history.append(validation_entry)
        
        # Keep history to a reasonable size
        max_history = self.config['performance_window'] * 2
        if len(self.validation_history) > max_history:
            excess = len(self.validation_history) - max_history
            self.validation_history = self.validation_history[excess:]
    
    def update_signal_performance(self, signal_id: str, was_profitable: bool) -> None:
        """
        Update signal performance in validation history and underlying validators.
        
        Args:
            signal_id: ID of the validated signal
            was_profitable: Whether the signal was profitable
        """
        # Update performance in validation history
        for entry in self.validation_history:
            if entry['signal_id'] == signal_id:
                entry['was_profitable'] = was_profitable
                break
        
        # Forward the update to individual validators
        for name, validator in self.validators.items():
            if hasattr(validator, 'update_signal_performance'):
                validator.update_signal_performance(signal_id, was_profitable)
    
    def _update_validator_weights(self) -> None:
        """
        Update validator weights based on their recent performance.
        """
        if not self.config['dynamic_weighting']:
            return
        
        # Get recent validation entries with known outcomes
        recent_entries = [
            entry for entry in self.validation_history[-self.config['performance_window']:]
            if entry['was_profitable'] is not None
        ]
        
        if len(recent_entries) < self.config['min_valid_validators']:
            logger.info("Not enough data to update validator weights")
            return
        
        # Reset performance tracking
        for name in self.validator_performance:
            self.validator_performance[name] = {'correct': 0, 'total': 0, 'score': 0.5}
        
        # Count correct predictions for each validator
        for entry in recent_entries:
            was_profitable = entry['was_profitable']
            
            for name, result in entry['validator_results'].items():
                if name in self.validator_performance:
                    is_valid = result.get('is_valid', False)
                    
                    # A signal is correctly validated if:
                    # - It was validated as valid and it was profitable, or
                    # - It was validated as invalid and it was not profitable
                    is_correct = (is_valid and was_profitable) or (not is_valid and not was_profitable)
                    
                    self.validator_performance[name]['total'] += 1
                    if is_correct:
                        self.validator_performance[name]['correct'] += 1
        
        # Calculate scores (accuracy with a lower bound)
        for name, data in self.validator_performance.items():
            if data['total'] > 0:
                accuracy = data['correct'] / data['total']
                # Use a lower bound to avoid completely ignoring a validator
                data['score'] = max(0.1, accuracy)
            else:
                data['score'] = 0.5  # Default neutral score
        
        self.last_weight_update = datetime.utcnow()
        
        logger.info(f"Updated validator weights: {self._get_validator_weights()}")
    
    def get_validator_performance(self) -> Dict[str, Dict[str, Any]]:
        """
        Get performance metrics for each validator.
        
        Returns:
            Dictionary of performance metrics by validator
        """
        performance = {}
        
        for name, data in self.validator_performance.items():
            if data['total'] > 0:
                accuracy = data['correct'] / data['total']
            else:
                accuracy = None
                
            performance[name] = {
                'correct': data['correct'],
                'total': data['total'],
                'accuracy': accuracy,
                'weight': self._get_validator_weights().get(name)
            }
            
            # Add validator-specific performance data if available
            if name in self.validators and hasattr(self.validators[name], 'get_performance'):
                validator_perf = self.validators[name].get_performance()
                performance[name]['detailed'] = validator_perf
        
        return performance 