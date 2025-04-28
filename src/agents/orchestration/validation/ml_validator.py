"""
Machine Learning Signal Validator

This module provides a ML-based validator for trading signals
that uses machine learning models to assess signal quality.
"""

import numpy as np
import pickle
import os
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime, timedelta
import joblib

from ....utils.logging.logger import get_logger
from .orchestration.models import TradingSignal, MarketConditions
from .orchestration.validation.base_validator import BaseSignalValidator

logger = get_logger()


class MLValidator(BaseSignalValidator):
    """
    Machine Learning validator for trading signals.
    
    Uses ML models to validate signals based on historical outcomes,
    market conditions, and signal properties.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the ML validator.
        
        Args:
            config: Configuration dictionary
        """
        # Default configuration
        default_config = {
            'base_threshold': 0.65,              # Base threshold for validation
            'model_path': 'models/signal_validation',  # Path to store/load models
            'training_frequency': 500,           # How many samples before retraining
            'min_training_samples': 100,         # Minimum samples needed for training
            'feature_columns': [                 # Features to use for prediction
                'confidence', 'strength', 'volatility', 'trend_strength',
                'agent_type_encoded', 'timeframe_encoded', 'hour_of_day',
                'day_of_week', 'market_regime_encoded'
            ],
            'target_column': 'was_profitable',   # Target variable for prediction
            'model_type': 'random_forest',       # Type of ML model to use
            'fallback_threshold': 0.6,           # Threshold to use if model isn't trained
            'retraining_enabled': True,          # Whether to enable model retraining
            'ensemble_size': 3,                  # Number of models in ensemble
            'calibration_window': 100,           # Samples to use for probability calibration
        }
        
        # Merge with provided config
        if config:
            merged_config = default_config.copy()
            merged_config.update(config)
        else:
            merged_config = default_config
        
        # Initialize base class
        super().__init__(name="MLValidator", config=merged_config)
        
        # Initialize model storage
        self.models = {}
        self.feature_encoders = {}
        self.training_data = []
        self.calibration_data = []
        self.last_retrain_time = None
        self.samples_since_training = 0
        
        # Ensure model directory exists
        os.makedirs(self.config['model_path'], exist_ok=True)
        
        # Load models if they exist
        self._load_models()
        
        logger.info("ML validator initialized")
    
    def _validate_signal(self, signal: TradingSignal, market_conditions: Optional[MarketConditions] = None) -> Dict[str, Any]:
        """
        Validate a trading signal using ML models.
        
        Args:
            signal: Trading signal to validate
            market_conditions: Current market conditions
            
        Returns:
            Validation data dictionary
        """
        # Prepare return structure
        validation_data = {
            'confidence': 0.0,
            'threshold': self.config['base_threshold'],
            'components': {},
            'metadata': {}
        }
        
        # Extract features for prediction
        features = self._extract_features(signal, market_conditions)
        
        # Check if we have a model for this trading pair
        trading_pair = signal.trading_pair
        agent_type = signal.agent_type
        
        # Try to use pair-specific model
        if trading_pair in self.models:
            prediction, confidence = self._predict_with_model(
                features, self.models[trading_pair], trading_pair
            )
            validation_data['metadata']['model_used'] = f'pair_specific_{trading_pair}'
        
        # Try to use agent-type model as fallback
        elif agent_type in self.models:
            prediction, confidence = self._predict_with_model(
                features, self.models[agent_type], agent_type
            )
            validation_data['metadata']['model_used'] = f'agent_type_{agent_type}'
        
        # Use global model as final fallback
        elif 'global' in self.models:
            prediction, confidence = self._predict_with_model(
                features, self.models['global'], 'global'
            )
            validation_data['metadata']['model_used'] = 'global'
        
        # No model available, use heuristic
        else:
            # Use signal confidence with a small discount
            confidence = signal.confidence * 0.9
            prediction = confidence > self.config['fallback_threshold']
            validation_data['metadata']['model_used'] = 'heuristic'
        
        # Store prediction results
        validation_data['confidence'] = confidence
        validation_data['components']['ml_confidence'] = confidence
        validation_data['components']['raw_prediction'] = 1.0 if prediction else 0.0
        validation_data['is_valid'] = prediction
        
        # Store training data for future model updates
        self._store_training_data(signal, features, market_conditions)
        
        # Check if we should retrain models
        if (self.config['retraining_enabled'] and 
            self.samples_since_training >= self.config['training_frequency'] and
            len(self.training_data) >= self.config['min_training_samples']):
            self._retrain_models()
        
        return validation_data
    
    def _extract_features(self, signal: TradingSignal, market_conditions: Optional[MarketConditions] = None) -> Dict[str, Any]:
        """
        Extract features from signal and market conditions for ML model.
        
        Args:
            signal: Trading signal to validate
            market_conditions: Current market conditions
            
        Returns:
            Dictionary of features
        """
        # Initialize with signal features
        features = {
            'confidence': signal.confidence,
            'strength': signal.strength,
            'agent_type': signal.agent_type,
            'agent_id': signal.agent_id,
            'direction': signal.direction,
            'timeframe': signal.timeframe,
        }
        
        # Add market condition features if available
        if market_conditions:
            if hasattr(market_conditions, 'volatility'):
                features['volatility'] = market_conditions.volatility
            if hasattr(market_conditions, 'trend_strength'):
                features['trend_strength'] = market_conditions.trend_strength
            if hasattr(market_conditions, 'volume'):
                features['volume'] = market_conditions.volume
            if hasattr(market_conditions, 'regime'):
                features['market_regime'] = market_conditions.regime
            if hasattr(market_conditions, 'liquidity'):
                features['liquidity'] = market_conditions.liquidity
        
        # Add time-based features
        now = datetime.utcnow()
        features['hour_of_day'] = now.hour
        features['day_of_week'] = now.weekday()
        features['month'] = now.month
        
        # Add direction match if trend direction is available
        if market_conditions and hasattr(market_conditions, 'trend_direction'):
            trend_dir = market_conditions.trend_direction
            signal_dir = signal.direction
            
            features['direction_match'] = (
                (trend_dir == 'up' and signal_dir == 'buy') or 
                (trend_dir == 'down' and signal_dir == 'sell')
            )
        
        # Add categorical encoding
        self._encode_categorical_features(features)
        
        return features
    
    def _encode_categorical_features(self, features: Dict[str, Any]) -> None:
        """
        Encode categorical features using one-hot encoding or label encoding.
        
        Modifies the features dictionary in place.
        
        Args:
            features: Dictionary of features to encode
        """
        # Encode agent type
        if 'agent_type' in features:
            agent_type = features['agent_type']
            agent_types = ['trend', 'mean_reversion', 'volatility', 'pattern', 'sentiment', 'fundamental']
            
            if agent_type in agent_types:
                features['agent_type_encoded'] = agent_types.index(agent_type) / len(agent_types)
            else:
                features['agent_type_encoded'] = -1.0  # Unknown agent type
        
        # Encode timeframe
        if 'timeframe' in features:
            timeframe = features['timeframe']
            timeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']
            
            if timeframe in timeframes:
                features['timeframe_encoded'] = timeframes.index(timeframe) / len(timeframes)
            else:
                features['timeframe_encoded'] = -1.0  # Unknown timeframe
        
        # Encode market regime
        if 'market_regime' in features:
            regime = features['market_regime']
            regimes = ['normal', 'trending', 'ranging', 'volatile']
            
            if regime in regimes:
                features['market_regime_encoded'] = regimes.index(regime) / len(regimes)
            else:
                features['market_regime_encoded'] = -1.0  # Unknown regime
        
        # Encode direction
        if 'direction' in features:
            direction = features['direction']
            features['direction_encoded'] = 1.0 if direction == 'buy' else 0.0
    
    def _predict_with_model(self, features: Dict[str, Any], model, model_key: str) -> Tuple[bool, float]:
        """
        Make a prediction using a trained model.
        
        Args:
            features: Dictionary of features
            model: Trained model for prediction
            model_key: Key identifying the model (for logging)
            
        Returns:
            Tuple of (prediction boolean, confidence score)
        """
        try:
            # Extract required features in the correct order
            feature_list = []
            for feature_name in self.config['feature_columns']:
                if feature_name in features:
                    feature_list.append(features[feature_name])
                else:
                    logger.warning(f"Missing feature: {feature_name}")
                    feature_list.append(0.0)  # Use default value
            
            # Convert to numpy array
            X = np.array([feature_list])
            
            # Get prediction probability
            if hasattr(model, 'predict_proba'):
                proba = model.predict_proba(X)[0][1]  # Probability of positive class
            else:
                proba = model.predict(X)[0]  # Use raw prediction if no probabilities
            
            # Apply probability calibration if we have calibration data
            if model_key in self.calibration_data and self.calibration_data[model_key]:
                proba = self._calibrate_probability(proba, model_key)
            
            # Determine threshold and make prediction
            threshold = self.config['base_threshold']
            prediction = proba > threshold
            
            return prediction, proba
            
        except Exception as e:
            logger.error(f"Error predicting with {model_key} model: {str(e)}")
            # Fallback to signal's own confidence
            return features['confidence'] > self.config['fallback_threshold'], features['confidence']
    
    def _store_training_data(self, signal: TradingSignal, features: Dict[str, Any], 
                           market_conditions: Optional[MarketConditions]) -> None:
        """
        Store data for future model training.
        
        Args:
            signal: Trading signal
            features: Extracted features
            market_conditions: Market conditions
        """
        # Create a training sample (outcome will be updated later)
        sample = {
            'signal_id': signal.id,
            'agent_id': signal.agent_id,
            'trading_pair': signal.trading_pair,
            'agent_type': signal.agent_type,
            'timestamp': datetime.utcnow().isoformat(),
            'features': features.copy(),
            'outcome': None,  # Will be updated when we know if signal was profitable
            'market_conditions': market_conditions.to_dict() if market_conditions else {}
        }
        
        self.training_data.append(sample)
        self.samples_since_training += 1
        
        # Keep training data to a reasonable size
        max_samples = self.config['min_training_samples'] * 5
        if len(self.training_data) > max_samples:
            # Remove oldest samples
            excess = len(self.training_data) - max_samples
            self.training_data = self.training_data[excess:]
    
    def _retrain_models(self) -> None:
        """
        Retrain ML models with collected training data.
        """
        if not self.config['retraining_enabled'] or len(self.training_data) < self.config['min_training_samples']:
            return
        
        logger.info(f"Retraining ML validator models with {len(self.training_data)} samples")
        
        try:
            # Filter for samples with outcomes
            valid_samples = [s for s in self.training_data if s['outcome'] is not None]
            
            if len(valid_samples) < self.config['min_training_samples']:
                logger.info(f"Not enough samples with outcomes for training. Have {len(valid_samples)}, need {self.config['min_training_samples']}")
                return
            
            # Process training data into features and targets
            X, y = self._prepare_training_data(valid_samples)
            
            # Train new models
            self._train_new_models(X, y, valid_samples)
            
            # Save models
            self._save_models()
            
            # Reset counter
            self.samples_since_training = 0
            self.last_retrain_time = datetime.utcnow()
            
            logger.info("ML validator models retrained successfully")
            
        except Exception as e:
            logger.error(f"Error retraining ML validator models: {str(e)}")
    
    def _prepare_training_data(self, samples: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare training data for ML models.
        
        Args:
            samples: List of training samples with outcomes
            
        Returns:
            Tuple of (features array, target array)
        """
        X = []
        y = []
        
        for sample in samples:
            # Get features and encode them
            features = sample['features']
            
            # Extract feature values in the correct order
            feature_list = []
            for feature_name in self.config['feature_columns']:
                if feature_name in features:
                    feature_list.append(features[feature_name])
                else:
                    feature_list.append(0.0)  # Default value
            
            # Add to training data
            X.append(feature_list)
            y.append(1 if sample['outcome'] == 'profitable' else 0)
        
        return np.array(X), np.array(y)
    
    def _train_new_models(self, X: np.ndarray, y: np.ndarray, samples: List[Dict[str, Any]]) -> None:
        """
        Train new ML models for signal validation.
        
        Args:
            X: Feature matrix
            y: Target vector
            samples: Original samples for group-specific models
        """
        from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
        from sklearn.model_selection import train_test_split
        
        # Train global model first
        if len(X) >= self.config['min_training_samples']:
            X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
            
            # Create global model
            if self.config['model_type'] == 'random_forest':
                global_model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
            else:
                global_model = GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42)
            
            # Train model
            global_model.fit(X_train, y_train)
            
            # Store model
            self.models['global'] = global_model
            
            # Track calibration data
            self._update_calibration_data('global', global_model, X_val, y_val)
        
        # Group samples by trading pair and agent type
        by_pair = {}
        by_agent_type = {}
        
        for i, sample in enumerate(samples):
            pair = sample['trading_pair']
            agent_type = sample['agent_type']
            
            if pair not in by_pair:
                by_pair[pair] = []
            by_pair[pair].append(i)
            
            if agent_type not in by_agent_type:
                by_agent_type[agent_type] = []
            by_agent_type[agent_type].append(i)
        
        # Train pair-specific models
        for pair, indices in by_pair.items():
            if len(indices) >= self.config['min_training_samples']:
                X_pair = X[indices]
                y_pair = y[indices]
                
                X_train, X_val, y_train, y_val = train_test_split(X_pair, y_pair, test_size=0.2, random_state=42)
                
                # Create pair model
                if self.config['model_type'] == 'random_forest':
                    pair_model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
                else:
                    pair_model = GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42)
                
                # Train model
                pair_model.fit(X_train, y_train)
                
                # Store model
                self.models[pair] = pair_model
                
                # Track calibration data
                self._update_calibration_data(pair, pair_model, X_val, y_val)
        
        # Train agent-type models
        for agent_type, indices in by_agent_type.items():
            if len(indices) >= self.config['min_training_samples']:
                X_agent = X[indices]
                y_agent = y[indices]
                
                X_train, X_val, y_train, y_val = train_test_split(X_agent, y_agent, test_size=0.2, random_state=42)
                
                # Create agent type model
                if self.config['model_type'] == 'random_forest':
                    agent_model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
                else:
                    agent_model = GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42)
                
                # Train model
                agent_model.fit(X_train, y_train)
                
                # Store model
                self.models[agent_type] = agent_model
                
                # Track calibration data
                self._update_calibration_data(agent_type, agent_model, X_val, y_val)
    
    def _update_calibration_data(self, model_key: str, model, X_val: np.ndarray, y_val: np.ndarray) -> None:
        """
        Update probability calibration data for a model.
        
        Args:
            model_key: Key identifying the model
            model: The trained model
            X_val: Validation features
            y_val: Validation targets
        """
        if not hasattr(model, 'predict_proba'):
            return
        
        # Get predicted probabilities
        y_proba = model.predict_proba(X_val)[:, 1]
        
        # Create calibration data
        calibration_data = []
        for i in range(len(y_val)):
            calibration_data.append({
                'predicted_proba': y_proba[i],
                'actual': y_val[i]
            })
        
        # Sort by predicted probability
        calibration_data.sort(key=lambda x: x['predicted_proba'])
        
        # Keep a limited window of calibration data
        window_size = min(len(calibration_data), self.config['calibration_window'])
        self.calibration_data[model_key] = calibration_data[-window_size:]
    
    def _calibrate_probability(self, raw_prob: float, model_key: str) -> float:
        """
        Calibrate a raw prediction probability using isotonic regression.
        
        Args:
            raw_prob: Raw predicted probability
            model_key: Key identifying the model
            
        Returns:
            Calibrated probability
        """
        calibration_data = self.calibration_data.get(model_key, [])
        if not calibration_data:
            return raw_prob
        
        # Find closest calibration points
        closest_lower = None
        closest_higher = None
        
        for point in calibration_data:
            if point['predicted_proba'] <= raw_prob:
                if closest_lower is None or point['predicted_proba'] > closest_lower['predicted_proba']:
                    closest_lower = point
            if point['predicted_proba'] >= raw_prob:
                if closest_higher is None or point['predicted_proba'] < closest_higher['predicted_proba']:
                    closest_higher = point
        
        # If we have bounds on both sides, interpolate
        if closest_lower and closest_higher:
            lower_prob = closest_lower['predicted_proba']
            higher_prob = closest_higher['predicted_proba']
            lower_actual = closest_lower['actual']
            higher_actual = closest_higher['actual']
            
            # Linear interpolation
            if higher_prob > lower_prob:
                weight = (raw_prob - lower_prob) / (higher_prob - lower_prob)
                calibrated = lower_actual + weight * (higher_actual - lower_actual)
                return calibrated
        
        # Otherwise, find nearest neighbor
        if closest_lower:
            return closest_lower['actual']
        if closest_higher:
            return closest_higher['actual']
        
        # Fallback to original
        return raw_prob
    
    def update_signal_performance(self, signal_id: str, was_profitable: bool) -> None:
        """
        Update signal performance in training data.
        
        Args:
            signal_id: ID of the validated signal
            was_profitable: Whether the signal was profitable
        """
        # Update training data with outcome
        outcome = 'profitable' if was_profitable else 'unprofitable'
        
        for sample in self.training_data:
            if sample['signal_id'] == signal_id:
                sample['outcome'] = outcome
                break
    
    def _save_models(self) -> None:
        """
        Save trained models to disk.
        """
        try:
            for model_key, model in self.models.items():
                model_path = os.path.join(self.config['model_path'], f"{model_key}_model.joblib")
                joblib.dump(model, model_path)
                
                # Save calibration data
                if model_key in self.calibration_data:
                    calib_path = os.path.join(self.config['model_path'], f"{model_key}_calibration.pkl")
                    with open(calib_path, 'wb') as f:
                        pickle.dump(self.calibration_data[model_key], f)
            
            # Save training metadata
            metadata = {
                'last_trained': datetime.utcnow().isoformat(),
                'num_samples': len(self.training_data),
                'model_keys': list(self.models.keys())
            }
            
            metadata_path = os.path.join(self.config['model_path'], 'metadata.pkl')
            with open(metadata_path, 'wb') as f:
                pickle.dump(metadata, f)
                
            logger.info(f"Saved {len(self.models)} ML validator models")
            
        except Exception as e:
            logger.error(f"Error saving ML validator models: {str(e)}")
    
    def _load_models(self) -> None:
        """
        Load trained models from disk.
        """
        try:
            metadata_path = os.path.join(self.config['model_path'], 'metadata.pkl')
            
            if not os.path.exists(metadata_path):
                logger.info("No ML validator models found")
                return
                
            # Load metadata
            with open(metadata_path, 'rb') as f:
                metadata = pickle.load(f)
            
            # Load models
            for model_key in metadata.get('model_keys', []):
                model_path = os.path.join(self.config['model_path'], f"{model_key}_model.joblib")
                
                if os.path.exists(model_path):
                    self.models[model_key] = joblib.load(model_path)
                    
                    # Load calibration data if available
                    calib_path = os.path.join(self.config['model_path'], f"{model_key}_calibration.pkl")
                    if os.path.exists(calib_path):
                        with open(calib_path, 'rb') as f:
                            self.calibration_data[model_key] = pickle.load(f)
            
            logger.info(f"Loaded {len(self.models)} ML validator models from {self.config['model_path']}")
            
        except Exception as e:
            logger.error(f"Error loading ML validator models: {str(e)}")
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the trained models.
        
        Returns:
            Dictionary with model information
        """
        info = {
            'num_models': len(self.models),
            'model_keys': list(self.models.keys()),
            'training_samples': len(self.training_data),
            'samples_since_training': self.samples_since_training,
            'last_retrain_time': self.last_retrain_time.isoformat() if self.last_retrain_time else None
        }
        
        return info 