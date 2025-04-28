"""
Market Regime Detector
---------------------
Detects different market regimes using statistical methods.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from hmmlearn import hmm
import datetime
import json
import os


class MarketRegimeDetector:
    """
    Detects different market regimes using statistical methods.
    
    This class implements various methods to identify distinct market regimes,
    including Hidden Markov Models, clustering, and change point detection.
    """
    
    def __init__(self, 
                 method: str = 'hmm',
                 n_regimes: int = 3,
                 lookback_window: int = 252,  # 1 year of daily data
                 features: List[str] = None,
                 log_dir: Optional[str] = None):
        """
        Initialize the market regime detector.
        
        Args:
            method: Method to use ('hmm', 'kmeans', 'changepoint')
            n_regimes: Number of distinct regimes to identify
            lookback_window: Window size for regime detection
            features: List of features to use for regime detection
            log_dir: Directory to save logs
        """
        self.method = method
        self.n_regimes = n_regimes
        self.lookback_window = lookback_window
        self.features = features or ['returns', 'volatility', 'momentum']
        
        # Set up logging directory
        self.log_dir = log_dir
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Initialize models
        self.models = {}
        self.scaler = StandardScaler()
        
        # State variables
        self.current_regime = 0
        self.regime_history = []
        self.regime_probabilities = np.zeros(n_regimes)
        self.feature_importance = {}
        
        # HMM model parameters
        self.hmm_params = {
            'n_components': n_regimes,
            'n_iter': 100,
            'random_state': 42,
            'covariance_type': 'full'
        }
    
    def _extract_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Extract relevant features for regime detection.
        
        Args:
            data: Market data DataFrame
            
        Returns:
            DataFrame with extracted features
        """
        features_df = pd.DataFrame(index=data.index)
        
        # Return-based features
        if 'returns' in self.features:
            # Daily returns
            features_df['returns'] = data['close'].pct_change()
        
        # Volatility-based features
        if 'volatility' in self.features:
            # Historical volatility (20-day)
            features_df['volatility_20d'] = data['close'].pct_change().rolling(window=20).std()
            
            # Volatility of volatility
            features_df['vol_of_vol'] = features_df['volatility_20d'].rolling(window=20).std()
        
        # Momentum-based features
        if 'momentum' in self.features:
            # 10-day momentum
            features_df['momentum_10d'] = data['close'].pct_change(periods=10)
            
            # 50-day momentum
            features_df['momentum_50d'] = data['close'].pct_change(periods=50)
        
        # Trend-based features
        if 'trend' in self.features:
            # Short-term trend (ratio of 20-day to 50-day moving average)
            features_df['trend_20_50'] = (
                data['close'].rolling(window=20).mean() / 
                data['close'].rolling(window=50).mean()
            )
            
            # Medium-term trend (ratio of 50-day to 200-day moving average)
            features_df['trend_50_200'] = (
                data['close'].rolling(window=50).mean() / 
                data['close'].rolling(window=200).mean()
            )
        
        # Volume-based features
        if 'volume' in self.features and 'volume' in data.columns:
            # Volume change
            features_df['volume_change'] = data['volume'].pct_change()
            
            # Volume relative to 20-day average
            features_df['volume_rel_20d'] = (
                data['volume'] / 
                data['volume'].rolling(window=20).mean()
            )
        
        # Remove NaN values
        features_df = features_df.dropna()
        
        return features_df
    
    def _normalize_features(self, features_df: pd.DataFrame) -> np.ndarray:
        """
        Normalize features for model training.
        
        Args:
            features_df: DataFrame with extracted features
            
        Returns:
            Normalized feature array
        """
        # Fit the scaler if it hasn't been fit yet
        if not hasattr(self.scaler, 'mean_') or self.scaler.mean_ is None:
            self.scaler.fit(features_df.values)
        
        # Transform the features
        normalized_features = self.scaler.transform(features_df.values)
        
        return normalized_features
    
    def _train_hmm(self, features: np.ndarray) -> hmm.GaussianHMM:
        """
        Train a Hidden Markov Model for regime detection.
        
        Args:
            features: Normalized feature array
            
        Returns:
            Trained HMM model
        """
        model = hmm.GaussianHMM(**self.hmm_params)
        model.fit(features)
        
        # Store the model
        self.models['hmm'] = model
        
        return model
    
    def _train_kmeans(self, features: np.ndarray) -> KMeans:
        """
        Train a K-means clustering model for regime detection.
        
        Args:
            features: Normalized feature array
            
        Returns:
            Trained K-means model
        """
        model = KMeans(n_clusters=self.n_regimes, random_state=42)
        model.fit(features)
        
        # Store the model
        self.models['kmeans'] = model
        
        return model
    
    def _detect_changepoints(self, features: np.ndarray) -> List[int]:
        """
        Detect change points in the feature data.
        
        Args:
            features: Normalized feature array
            
        Returns:
            List of change point indices
        """
        # Simple changepoint detection based on cumulative sum
        import ruptures as rpt  # Import here for optional dependency
        
        # Use a more robust method if available
        try:
            algo = rpt.Pelt(model="rbf").fit(features)
            changepoints = algo.predict(pen=0.5)
        except:
            # Fallback to simpler method
            means = np.mean(features, axis=1)
            
            # Calculate cumulative sum
            cusum = np.cumsum(means - np.mean(means))
            
            # Find points where direction changes
            changepoints = np.where(np.diff(np.sign(np.diff(cusum))))[0].tolist()
            
            # Limit to n_regimes - 1 points
            if len(changepoints) > self.n_regimes - 1:
                # Select the most significant changes
                changes = np.abs(np.diff(cusum))
                significant_indices = np.argsort(changes[changepoints])[:-(self.n_regimes-1)]
                changepoints = [changepoints[i] for i in significant_indices]
        
        # Store the changepoints
        self.models['changepoints'] = changepoints
        
        return changepoints
    
    def _analyze_feature_importance(self, 
                                   features_df: pd.DataFrame, 
                                   regimes: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Analyze the importance of different features for each regime.
        
        Args:
            features_df: DataFrame with extracted features
            regimes: Array of regime labels
            
        Returns:
            Dictionary with feature importance for each regime
        """
        feature_importance = {}
        
        # For each regime, calculate the average value of each feature
        for i in range(self.n_regimes):
            regime_indices = regimes == i
            
            if np.sum(regime_indices) > 0:
                regime_data = features_df.iloc[regime_indices]
                
                # Calculate mean and std for each feature in this regime
                feature_stats = {
                    'mean': regime_data.mean(),
                    'std': regime_data.std(),
                    'z_score': (regime_data.mean() - features_df.mean()) / features_df.std()
                }
                
                feature_importance[f'regime_{i}'] = feature_stats
        
        # Store the feature importance
        self.feature_importance = feature_importance
        
        return feature_importance
    
    def train(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Train the regime detection model.
        
        Args:
            data: Market data DataFrame
            
        Returns:
            Dictionary with training results
        """
        # Extract features
        features_df = self._extract_features(data)
        
        # Normalize features
        normalized_features = self._normalize_features(features_df)
        
        # Train the appropriate model
        if self.method == 'hmm':
            model = self._train_hmm(normalized_features)
            regimes = model.predict(normalized_features)
            
        elif self.method == 'kmeans':
            model = self._train_kmeans(normalized_features)
            regimes = model.predict(normalized_features)
            
        elif self.method == 'changepoint':
            changepoints = self._detect_changepoints(normalized_features)
            
            # Convert changepoints to regimes
            regimes = np.zeros(len(normalized_features), dtype=int)
            for i, cp in enumerate(sorted(changepoints)):
                regimes[cp:] = i + 1
        else:
            raise ValueError(f"Unknown method: {self.method}")
        
        # Analyze feature importance
        feature_importance = self._analyze_feature_importance(features_df, regimes)
        
        # Store regime history
        timestamps = features_df.index.tolist()
        self.regime_history = [
            {'timestamp': timestamps[i], 'regime': int(regimes[i])}
            for i in range(len(regimes))
        ]
        
        # Get current regime (most recent)
        self.current_regime = int(regimes[-1]) if len(regimes) > 0 else 0
        
        # If HMM, get regime probabilities
        if self.method == 'hmm':
            frame_log_prob = model.score_samples(normalized_features)
            self.regime_probabilities = np.exp(model.predict_proba(normalized_features[-1:]))[0]
        
        # Calculate regime statistics
        regime_stats = {}
        for i in range(self.n_regimes):
            regime_indices = regimes == i
            if np.sum(regime_indices) > 0:
                stats = {
                    'count': int(np.sum(regime_indices)),
                    'frequency': float(np.sum(regime_indices) / len(regimes)),
                    'longest_duration': int(self._get_longest_duration(regimes, i))
                }
                
                # If we have returns, calculate regime-specific market stats
                if 'returns' in features_df.columns:
                    regime_returns = features_df.loc[regime_indices, 'returns']
                    stats.update({
                        'mean_return': float(np.mean(regime_returns)),
                        'std_return': float(np.std(regime_returns)),
                        'sharpe': float(np.mean(regime_returns) / max(1e-10, np.std(regime_returns))),
                        'min_return': float(np.min(regime_returns)),
                        'max_return': float(np.max(regime_returns))
                    })
                
                regime_stats[f'regime_{i}'] = stats
        
        results = {
            'method': self.method,
            'n_regimes': self.n_regimes,
            'features': list(features_df.columns),
            'current_regime': self.current_regime,
            'regime_probabilities': self.regime_probabilities.tolist(),
            'regime_stats': regime_stats,
            'feature_importance': {k: v.to_dict() for k, v in feature_importance.items()}
        }
        
        # Log the results
        if self.log_dir:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = os.path.join(self.log_dir, f"regime_detection_{timestamp}.json")
            
            with open(log_file, 'w') as f:
                json.dump(results, f, indent=2, default=self._json_serialize)
        
        return results
    
    def predict(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Predict the current market regime.
        
        Args:
            data: Market data DataFrame
            
        Returns:
            Dictionary with prediction results
        """
        # Check if we have a trained model
        if self.method not in self.models:
            raise ValueError("Model not trained. Call train() first.")
        
        # Extract features
        features_df = self._extract_features(data)
        
        # Use the most recent lookback_window rows
        if len(features_df) > self.lookback_window:
            features_df = features_df.iloc[-self.lookback_window:]
        
        # Normalize features
        normalized_features = self.scaler.transform(features_df.values)
        
        # Predict the regime
        if self.method == 'hmm':
            model = self.models['hmm']
            regime = model.predict(normalized_features)[-1]
            
            # Get regime probabilities
            frame_log_prob = model.score_samples(normalized_features)
            self.regime_probabilities = np.exp(model.predict_proba(normalized_features[-1:]))[0]
            
        elif self.method == 'kmeans':
            model = self.models['kmeans']
            regime = model.predict(normalized_features)[-1]
            
            # Get distance to each cluster center
            distances = np.linalg.norm(
                normalized_features[-1] - model.cluster_centers_, 
                axis=1
            )
            # Convert distances to probabilities (closer = higher probability)
            self.regime_probabilities = 1 / (1 + distances)
            self.regime_probabilities /= np.sum(self.regime_probabilities)
            
        elif self.method == 'changepoint':
            # For changepoint, we need to analyze the recent changes
            changepoints = self._detect_changepoints(normalized_features)
            
            # If there's a recent changepoint, update the regime
            if changepoints and changepoints[-1] > len(normalized_features) - 10:
                regime = (self.current_regime + 1) % self.n_regimes
            else:
                regime = self.current_regime
            
            # Set simple probabilities
            self.regime_probabilities = np.zeros(self.n_regimes)
            self.regime_probabilities[regime] = 1.0
            
        # Update current regime
        self.current_regime = int(regime)
        
        # Add to history
        timestamp = data.index[-1] if isinstance(data.index, pd.DatetimeIndex) else datetime.datetime.now()
        self.regime_history.append({
            'timestamp': timestamp,
            'regime': self.current_regime,
            'probabilities': self.regime_probabilities.tolist()
        })
        
        # Limit history length
        if len(self.regime_history) > 1000:
            self.regime_history = self.regime_history[-1000:]
        
        return {
            'regime': self.current_regime,
            'probabilities': self.regime_probabilities.tolist(),
            'timestamp': timestamp
        }
    
    def get_regime_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the regimes.
        
        Returns:
            Dictionary with regime statistics
        """
        # Count regime transitions
        transitions = {}
        for i in range(1, len(self.regime_history)):
            prev_regime = self.regime_history[i-1]['regime']
            curr_regime = self.regime_history[i]['regime']
            
            key = f"{prev_regime}_to_{curr_regime}"
            transitions[key] = transitions.get(key, 0) + 1
        
        # Count regime frequencies
        frequencies = {}
        for history in self.regime_history:
            regime = history['regime']
            frequencies[regime] = frequencies.get(regime, 0) + 1
        
        # Calculate average duration for each regime
        durations = {}
        if self.regime_history:
            current_regime = self.regime_history[0]['regime']
            duration = 1
            
            for i in range(1, len(self.regime_history)):
                regime = self.regime_history[i]['regime']
                
                if regime == current_regime:
                    duration += 1
                else:
                    if current_regime not in durations:
                        durations[current_regime] = []
                    
                    durations[current_regime].append(duration)
                    current_regime = regime
                    duration = 1
            
            # Add the last duration
            if current_regime not in durations:
                durations[current_regime] = []
            
            durations[current_regime].append(duration)
        
        avg_durations = {
            regime: np.mean(durs) for regime, durs in durations.items()
        }
        
        return {
            'transitions': transitions,
            'frequencies': frequencies,
            'avg_durations': avg_durations,
            'feature_importance': self.feature_importance
        }
    
    def _get_longest_duration(self, regimes: np.ndarray, regime_id: int) -> int:
        """
        Get the longest duration of a specific regime.
        
        Args:
            regimes: Array of regime labels
            regime_id: ID of the regime to analyze
            
        Returns:
            Longest duration in time steps
        """
        if len(regimes) == 0:
            return 0
        
        # Convert to binary (1 if in regime, 0 otherwise)
        binary = (regimes == regime_id).astype(int)
        
        # Find runs of 1s
        runs = np.where(np.diff(np.hstack(([0], binary, [0]))))[0]
        
        # Calculate run lengths
        run_lengths = np.diff(runs)
        
        # Return the longest run
        return int(np.max(run_lengths)) if len(run_lengths) > 0 else 0
    
    def save(self, path: str = None) -> str:
        """
        Save the model and history to files.
        
        Args:
            path: Directory to save files (defaults to log_dir)
            
        Returns:
            Path to the saved files
        """
        if not path:
            if not self.log_dir:
                raise ValueError("No log directory specified")
            path = self.log_dir
        
        os.makedirs(path, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save regime history
        history_file = os.path.join(path, f"regime_history_{timestamp}.json")
        with open(history_file, 'w') as f:
            json.dump(self.regime_history, f, default=self._json_serialize, indent=2)
        
        # Save feature importance
        importance_file = os.path.join(path, f"feature_importance_{timestamp}.json")
        with open(importance_file, 'w') as f:
            json.dump(self.feature_importance, f, default=self._json_serialize, indent=2)
        
        # Save regime stats
        stats_file = os.path.join(path, f"regime_stats_{timestamp}.json")
        with open(stats_file, 'w') as f:
            json.dump(self.get_regime_stats(), f, default=self._json_serialize, indent=2)
        
        return path
    
    def _json_serialize(self, obj):
        """Helper method to serialize objects to JSON."""
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, pd.Series):
            return obj.to_dict()
        elif isinstance(obj, (pd.Timestamp, datetime.datetime)):
            return obj.isoformat()
        elif hasattr(obj, 'to_dict'):
            return obj.to_dict()
        
        return str(obj) 