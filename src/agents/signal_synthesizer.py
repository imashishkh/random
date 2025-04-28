"""
Signal Synthesizer for Trading Recommendations

This module provides the SignalSynthesizer class, which combines signals from technical
and fundamental analysis agents to produce unified trading recommendations.
"""

import uuid
import logging
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Union, Tuple, Set
import pandas as pd
import numpy as np

from ..utils.logging.logger import get_logger
from .technical_analysis.market_condition_analyzer import MarketConditionAnalyzer
from .technical_analysis.factory import TechnicalAnalysisAgentFactory

logger = get_logger()


class SignalSynthesizer:
    """
    Combines signals from technical and fundamental agents to produce unified trading recommendations.
    
    Features:
    - Aggregates signals from multiple agents
    - Resolves conflicting signals using configurable weighting schemes
    - Applies machine learning models to improve prediction accuracy
    - Generates final actionable trading signals with confidence metrics
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the signal synthesizer.
        
        Args:
            config: Configuration dictionary with weights and settings
        """
        # Set default weights
        self.weights = {
            'technical': 0.6,
            'fundamental': 0.4,
            'momentum': 0.25,
            'trend': 0.25,
            'volatility': 0.25,
            'pattern': 0.25,
            'financial': 0.4,
            'economic': 0.3,
            'news': 0.3,
            'market_condition': 0.2  # Weight for market condition signals
        }
        
        # Override with user config if provided
        if config and 'weights' in config:
            self.weights.update(config['weights'])
            
        # Initialize containers
        self.agents = {
            'technical': {},
            'fundamental': {},
            'market_condition': {}  # Add market condition agents container
        }
        
        # Performance tracking
        self.agent_performance = {}
        
        # Signal buffer
        self.signal_buffer = {}
        
        # ML models
        self.ml_models = {}
        self.ensemble_model = None
        
        # Configure ML if enabled
        self.use_ml = config.get('use_ml', False)
        if self.use_ml:
            self._initialize_ml_models()
            
        # Create market condition analyzer
        self._initialize_market_condition_analyzer(config)
        
        logger.info("SignalSynthesizer initialized")
    
    def _initialize_ml_models(self):
        """Initialize machine learning models for signal enhancement."""
        model_config = self.config.get('ml_models', {})
        
        # Check if ML models should be used
        if model_config.get('use_ml', True):
            try:
                import sklearn
                self.sklearn_available = True
                logger.info("scikit-learn available for ML models")
            except ImportError:
                self.sklearn_available = False
                logger.warning("scikit-learn not available, ML enhancement disabled")
        else:
            self.sklearn_available = False
            
        # Initialize ensemble model if enabled and sklearn is available
        if model_config.get('use_ensemble', True) and self.sklearn_available:
            try:
                self._create_ensemble_model()
            except Exception as e:
                logger.error(f"Failed to initialize ensemble model: {str(e)}")
                self.ensemble_model = None
    
    def _create_ensemble_model(self):
        """Create ensemble model for signal enhancement."""
        if not self.sklearn_available:
            return
            
        try:
            from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline
            
            # Create a simple ensemble model for signal enhancement
            # This is a placeholder that should be expanded in a real implementation
            self.ensemble_model = {
                'random_forest': RandomForestClassifier(n_estimators=100, random_state=42),
                'gradient_boosting': GradientBoostingClassifier(n_estimators=100, random_state=42),
                'logistic': Pipeline([
                    ('scaler', StandardScaler()),
                    ('classifier', LogisticRegression(random_state=42))
                ])
            }
            
            logger.info("Ensemble model created")
        except Exception as e:
            logger.error(f"Failed to create ensemble model: {str(e)}")
            self.ensemble_model = None
    
    def register_agent(self, agent, agent_type: str, agent_subtype: Optional[str] = None, weight: Optional[float] = None):
        """
        Register an agent with the synthesizer.
        
        Args:
            agent: Agent instance to register
            agent_type: Type of agent ('technical' or 'fundamental')
            agent_subtype: Subtype of agent (e.g., 'momentum', 'trend', 'financial')
            weight: Weight to assign to this agent's signals
            
        Returns:
            Agent ID for future reference
        """
        agent_id = getattr(agent, 'name', str(uuid.uuid4()))
        
        # Determine agent category (technical or fundamental)
        if agent_type not in self.agents:
            raise ValueError(f"Unknown agent type: {agent_type}. Must be 'technical' or 'fundamental'")
        
        # Assign weight based on agent type and subtype
        if weight is None:
            if agent_subtype and agent_subtype in self.weights:
                weight = self.weights[agent_subtype]
            else:
                weight = self.weights[agent_type]
        
        # Store agent with metadata
        self.agents[agent_type][agent_id] = {
            'agent': agent,
            'weight': weight,
            'subtype': agent_subtype
        }
        
        # Initialize performance tracking
        self.agent_performance[agent_id] = {
            'total_signals': 0,
            'correct_signals': 0,
            'accuracy': 0.0,
            'recent_signals': []
        }
        
        logger.info(f"Registered {agent_type} agent: {agent_id} with weight {weight}")
        return agent_id
    
    def collect_signals(self, currency_pair: str, timeframe: str = 'all') -> Dict[str, List[Dict[str, Any]]]:
        """
        Collect signals from all registered agents.
        
        Args:
            currency_pair: Currency pair to analyze (e.g., 'EUR/USD')
            timeframe: Time frame for analysis ('short', 'medium', 'long', or 'all')
            
        Returns:
            Dictionary mapping agent types to lists of signals
        """
        collected_signals = {
            'technical': [],
            'fundamental': [],
            'market_condition': []  # Add market condition signals
        }
        
        # Collect signals from technical agents
        for agent_id, agent_data in self.agents['technical'].items():
            agent = agent_data['agent']
            try:
                if hasattr(agent, 'generate_signals'):
                    data = self._get_data_for_agent(agent, currency_pair, timeframe)
                    signals = agent.generate_signals(data)
                    
                    # Add agent metadata to signals
                    for signal in signals:
                        signal['agent_id'] = agent_id
                        signal['agent_type'] = 'technical'
                        signal['agent_subtype'] = agent_data['subtype']
                        signal['agent_weight'] = agent_data['weight']
                    
                    collected_signals['technical'].extend(signals)
                    logger.debug(f"Collected {len(signals)} signals from technical agent {agent_id}")
            except Exception as e:
                logger.error(f"Error collecting signals from technical agent {agent_id}: {str(e)}")
        
        # Collect signals from fundamental agents
        for agent_id, agent_data in self.agents['fundamental'].items():
            agent = agent_data['agent']
            try:
                if hasattr(agent, 'analyze'):
                    analysis_result = agent.analyze(
                        currency_pair=currency_pair,
                        timeframe=timeframe if timeframe != 'all' else 'medium'
                    )
                    
                    # Extract signal from analysis result
                    if 'signal' in analysis_result:
                        signal = analysis_result['signal']
                        signal['agent_id'] = agent_id
                        signal['agent_type'] = 'fundamental'
                        signal['agent_subtype'] = agent_data['subtype']
                        signal['agent_weight'] = agent_data['weight']
                        
                        collected_signals['fundamental'].append(signal)
                        logger.debug(f"Collected signal from fundamental agent {agent_id}")
            except Exception as e:
                logger.error(f"Error collecting signals from fundamental agent {agent_id}: {str(e)}")
        
        # Collect signals from market condition analyzer
        for agent_id, agent_data in self.agents['market_condition'].items():
            agent = agent_data['agent']
            try:
                if hasattr(agent, 'generate_signals'):
                    data = self._get_data_for_agent(agent, currency_pair, timeframe)
                    agent.compute_indicators(data)  # Ensure indicators are computed
                    signals = agent.generate_signals(data)
                    
                    # Add agent metadata to signals
                    for signal in signals:
                        signal['agent_id'] = agent_id
                        signal['agent_type'] = 'market_condition'
                        signal['agent_subtype'] = 'market_analyzer'
                        signal['agent_weight'] = agent_data['weight']
                    
                    collected_signals['market_condition'].extend(signals)
                    
                    # Store market conditions for later use
                    self.market_conditions = agent.conditions
                    
                    logger.debug(f"Collected {len(signals)} signals from market condition analyzer {agent_id}")
            except Exception as e:
                logger.error(f"Error collecting signals from market condition analyzer {agent_id}: {str(e)}")
        
        # Store in signal buffer
        self.signal_buffer[currency_pair] = collected_signals
        
        return collected_signals
    
    def _get_data_for_agent(self, agent, currency_pair: str, timeframe: str) -> pd.DataFrame:
        """
        Get appropriate data for an agent based on currency pair and timeframe.
        
        This is a placeholder method that should be implemented based on the
        data provider integration in the actual system.
        
        Args:
            agent: Agent instance
            currency_pair: Currency pair
            timeframe: Time frame for analysis
            
        Returns:
            DataFrame with required data
        """
        # This would integrate with the data provider in a real implementation
        # For now, return a mock DataFrame with OHLCV data
        return pd.DataFrame({
            'open': np.random.random(100),
            'high': np.random.random(100),
            'low': np.random.random(100),
            'close': np.random.random(100),
            'volume': np.random.random(100)
        })
    
    def resolve_conflicts(self, signals: Dict[str, List[Dict[str, Any]]], resolution_method: str = 'weighted') -> Dict[str, Any]:
        """
        Resolve conflicting signals using the specified method.
        
        Args:
            signals: Collected signals from agents
            resolution_method: Method for resolving conflicts ('weighted', 'voting', 'bayesian', 'ml')
            
        Returns:
            Resolved signal with confidence metrics
        """
        if resolution_method == 'weighted':
            return self._resolve_weighted(signals)
        elif resolution_method == 'voting':
            return self._resolve_voting(signals)
        elif resolution_method == 'bayesian':
            return self._resolve_bayesian(signals)
        elif resolution_method == 'ml':
            return self._resolve_ml(signals)
        else:
            logger.warning(f"Unknown resolution method: {resolution_method}, using weighted method")
            return self._resolve_weighted(signals)
    
    def _resolve_weighted(self, signals: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Resolve conflicts using weighted average of signals.
        
        Args:
            signals: Collected signals from agents
            
        Returns:
            Resolved signal with confidence metrics
        """
        # Combine all signals into a flat list
        all_signals = signals['technical'] + signals['fundamental']
        
        # Add market condition signals if available
        if 'market_condition' in signals:
            all_signals.extend(signals['market_condition'])
        
        if not all_signals:
            return {
                'type': 'neutral',
                'score': 0,
                'confidence': 0,
                'timestamp': datetime.now().isoformat(),
                'error': 'No signals available'
            }
        
        # Calculate weighted score
        total_weight = 0
        weighted_score = 0
        
        for signal in all_signals:
            signal_type = signal.get('type', 'neutral')
            confidence = signal.get('confidence', 0.5)
            weight = signal.get('agent_weight', 0.5)
            
            # Convert signal type to numeric score
            if signal_type == 'buy':
                score = 1.0
            elif signal_type == 'sell':
                score = -1.0
            elif signal_type == 'caution':  # Special case for market condition signals
                score = 0.0  # Neutral score but will affect confidence
            elif signal_type == 'opportunity':  # Special case for market condition signals
                score = 0.5 * (weighted_score > 0 and 1.0 or -1.0)  # Amplify existing trend direction
            elif signal_type == 'regime_change':  # Special case for market condition signals
                score = 0.0  # Neutral but will reduce confidence
            elif signal_type == 'anomaly':  # Special case for market condition signals
                score = 0.0  # Neutral but will reduce confidence
            else:  # neutral
                score = 0.0
            
            # Adjust weight by confidence
            adjusted_weight = weight * confidence
            
            # Check for market condition signals to adjust confidence
            if signal.get('agent_type') == 'market_condition':
                # These signals don't directly contribute to direction, but affect confidence
                if signal_type in ['caution', 'regime_change', 'anomaly']:
                    # Add to total weight but don't affect score
                    total_weight += adjusted_weight
                    continue
            
            # Add to weighted score and total weight
            weighted_score += score * adjusted_weight
            total_weight += adjusted_weight
        
        # Determine signal type and normalized score
        if total_weight > 0:
            normalized_score = weighted_score / total_weight
        else:
            normalized_score = 0
        
        if normalized_score > 0.2:
            signal_type = 'buy'
        elif normalized_score < -0.2:
            signal_type = 'sell'
        else:
            signal_type = 'neutral'
        
        # Calculate confidence - higher when signals agree
        signal_directions = [s.get('type') for s in all_signals if s.get('type') in ['buy', 'sell']]
        if signal_directions:
            agreement_ratio = max(signal_directions.count('buy'), signal_directions.count('sell')) / len(signal_directions)
            confidence = min(0.9, agreement_ratio)  # Cap at 0.9
        else:
            confidence = 0.5
        
        # Adjust confidence based on market conditions if available
        if hasattr(self, 'market_conditions'):
            # Reduce confidence in extreme volatility
            if self.market_conditions.get('volatility_state') in ['extremely_high', 'high']:
                confidence *= 0.8  # 20% confidence reduction in high volatility
            
            # Reduce confidence during regime changes
            if self.market_conditions.get('regime_state') == 'changing':
                confidence *= 0.75  # 25% confidence reduction during regime change
            
            # Reduce confidence if anomalies detected
            if self.market_conditions.get('anomalies'):
                confidence *= 0.9  # 10% confidence reduction for each anomaly (capped)
        
        # Compile the final signal
        result = {
            'type': signal_type,
            'score': normalized_score,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat(),
            'components': {
                'technical': sum([s.get('confidence', 0) * s.get('agent_weight', 0.5) for s in signals.get('technical', [])]),
                'fundamental': sum([s.get('confidence', 0) * s.get('agent_weight', 0.5) for s in signals.get('fundamental', [])]),
            }
        }
        
        # Add market condition component if available
        if 'market_condition' in signals and signals['market_condition']:
            result['components']['market_condition'] = sum([s.get('confidence', 0) * s.get('agent_weight', 0.5) 
                                                        for s in signals.get('market_condition', [])])
            
            # Add market conditions context to result
            if hasattr(self, 'market_conditions'):
                result['market_context'] = {
                    'volatility': self.market_conditions.get('volatility_state'),
                    'liquidity': self.market_conditions.get('liquidity_state'),
                    'trend': self.market_conditions.get('trend_state'),
                    'regime': self.market_conditions.get('regime_state'),
                    'anomalies': [a['type'] for a in self.market_conditions.get('anomalies', [])]
                }
        
        return result
    
    def _resolve_voting(self, signals: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Resolve conflicts using voting system.
        
        Args:
            signals: Collected signals from agents
            
        Returns:
            Resolved signal with confidence metrics
        """
        # Combine all signals into a flat list
        all_signals = signals['technical'] + signals['fundamental']
        
        if not all_signals:
            return {
                'type': 'neutral',
                'score': 0,
                'confidence': 0,
                'timestamp': datetime.now().isoformat(),
                'error': 'No signals available'
            }
        
        # Count votes for each signal type
        buy_votes = 0
        sell_votes = 0
        neutral_votes = 0
        
        for signal in all_signals:
            signal_type = signal.get('type', 'neutral')
            confidence = signal.get('confidence', 0.5)
            
            # Only count signals with confidence above threshold
            if confidence >= 0.3:
                if signal_type == 'buy':
                    buy_votes += 1
                elif signal_type == 'sell':
                    sell_votes += 1
                else:
                    neutral_votes += 1
        
        # Determine winning signal type
        total_votes = buy_votes + sell_votes + neutral_votes
        
        if total_votes == 0:
            signal_type = 'neutral'
            confidence = 0
        elif buy_votes > sell_votes and buy_votes > neutral_votes:
            signal_type = 'buy'
            confidence = buy_votes / total_votes
        elif sell_votes > buy_votes and sell_votes > neutral_votes:
            signal_type = 'sell'
            confidence = sell_votes / total_votes
        else:
            signal_type = 'neutral'
            confidence = neutral_votes / total_votes
        
        # Create resolved signal
        resolved_signal = {
            'type': signal_type,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat(),
            'votes': {
                'buy': buy_votes,
                'sell': sell_votes,
                'neutral': neutral_votes,
                'total': total_votes
            },
            'method': 'voting'
        }
        
        return resolved_signal
    
    def _resolve_bayesian(self, signals: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Resolve conflicts using Bayesian probability combination.
        
        Args:
            signals: Collected signals from agents
            
        Returns:
            Resolved signal with confidence metrics
        """
        # This is a simplified implementation of Bayesian combination
        # A full implementation would use proper Bayesian network or probabilistic methods
        
        # Combine all signals into a flat list
        all_signals = signals['technical'] + signals['fundamental']
        
        if not all_signals:
            return {
                'type': 'neutral',
                'score': 0,
                'confidence': 0,
                'timestamp': datetime.now().isoformat(),
                'error': 'No signals available'
            }
        
        # Prior probabilities
        prior_buy = 0.33  # Equal priors for the three possible outcomes
        prior_sell = 0.33
        prior_neutral = 0.34
        
        # Update probabilities based on signals
        p_buy = prior_buy
        p_sell = prior_sell
        p_neutral = prior_neutral
        
        for signal in all_signals:
            signal_type = signal.get('type', 'neutral')
            confidence = signal.get('confidence', 0.5)
            weight = signal.get('agent_weight', 0.5)
            
            # Adjust confidence by weight
            adjusted_confidence = confidence * weight
            
            # Likelihood of the signal given each hypothesis
            # These are simplified approximations
            if signal_type == 'buy':
                p_buy *= adjusted_confidence
                p_sell *= (1 - adjusted_confidence) / 2
                p_neutral *= (1 - adjusted_confidence) / 2
            elif signal_type == 'sell':
                p_buy *= (1 - adjusted_confidence) / 2
                p_sell *= adjusted_confidence
                p_neutral *= (1 - adjusted_confidence) / 2
            else:  # neutral
                p_buy *= (1 - adjusted_confidence) / 2
                p_sell *= (1 - adjusted_confidence) / 2
                p_neutral *= adjusted_confidence
        
        # Normalize probabilities
        total_p = p_buy + p_sell + p_neutral
        if total_p > 0:
            p_buy /= total_p
            p_sell /= total_p
            p_neutral /= total_p
        
        # Determine signal type based on highest probability
        if p_buy > p_sell and p_buy > p_neutral:
            signal_type = 'buy'
            confidence = p_buy
        elif p_sell > p_buy and p_sell > p_neutral:
            signal_type = 'sell'
            confidence = p_sell
        else:
            signal_type = 'neutral'
            confidence = p_neutral
        
        # Create resolved signal
        resolved_signal = {
            'type': signal_type,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat(),
            'probabilities': {
                'buy': p_buy,
                'sell': p_sell,
                'neutral': p_neutral
            },
            'method': 'bayesian'
        }
        
        return resolved_signal
    
    def _resolve_ml(self, signals: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Resolve conflicts using machine learning models.
        
        Args:
            signals: Collected signals from agents
            
        Returns:
            Resolved signal with confidence metrics
        """
        # Check if ML is available
        if not self.sklearn_available or not self.ensemble_model:
            logger.warning("ML resolution not available, falling back to weighted method")
            return self._resolve_weighted(signals)
        
        # This would be a more complex implementation using the trained ensemble model
        # For now, fall back to weighted method
        return self._resolve_weighted(signals)
    
    def apply_ml_model(self, signals: Dict[str, List[Dict[str, Any]]], model_type: str = 'ensemble') -> Dict[str, Any]:
        """
        Apply machine learning to improve predictions.
        
        Args:
            signals: Collected signals from agents
            model_type: Type of ML model to apply
            
        Returns:
            Enhanced signals with adjusted confidence
        """
        # Check if ML is available
        if not self.sklearn_available:
            logger.warning("ML enhancement not available")
            return signals
        
        # This would be a more complex implementation using various ML models
        # For now, return the original signals
        return signals
    
    def adjust_weights(self, performance_data: Dict[str, Dict[str, Any]]):
        """
        Update agent weights based on historical performance.
        
        Args:
            performance_data: Dictionary mapping agent IDs to performance metrics
        """
        for agent_id, metrics in performance_data.items():
            # Find the agent in our registry
            agent_entry = None
            agent_type = None
            
            for agent_type_key in self.agents:
                if agent_id in self.agents[agent_type_key]:
                    agent_entry = self.agents[agent_type_key][agent_id]
                    agent_type = agent_type_key
                    break
            
            if not agent_entry:
                continue
            
            # Update performance metrics
            self.agent_performance[agent_id].update(metrics)
            
            # Adjust weight based on accuracy
            accuracy = metrics.get('accuracy', 0.5)
            current_weight = agent_entry['weight']
            
            # Adjust weight up or down based on accuracy
            # Use a logistic function to bound the weight adjustment
            adjustment_factor = 1 + (accuracy - 0.5)
            new_weight = current_weight * adjustment_factor
            
            # Ensure weight stays in reasonable range
            new_weight = max(0.1, min(2.0, new_weight))
            
            # Update weight
            agent_entry['weight'] = new_weight
            logger.info(f"Adjusted weight for agent {agent_id} from {current_weight:.2f} to {new_weight:.2f} based on accuracy {accuracy:.2f}")
    
    def generate_trading_signal(self, currency_pair: str, timeframe: str = 'all', resolution_method: str = 'weighted') -> Dict[str, Any]:
        """
        Main method to produce final trading signals.
        
        Args:
            currency_pair: Currency pair to analyze (e.g., 'EUR/USD')
            timeframe: Time frame for analysis ('short', 'medium', 'long', or 'all')
            resolution_method: Method for resolving conflicts
            
        Returns:
            Final trading signal with confidence metrics
        """
        logger.info(f"Generating trading signal for {currency_pair} using {resolution_method} method")
        
        # Step 1: Collect signals from all agents
        signals = self.collect_signals(currency_pair, timeframe)
        
        # Step 2: Resolve conflicts
        resolved_signal = self.resolve_conflicts(signals, resolution_method)
        
        # Step 3: Apply ML enhancement if available
        if self.sklearn_available and self.config.get('use_ml', True):
            # In a real implementation, we would enhance the signal here
            # For now, just use the resolved signal
            pass
        
        # Step 4: Add additional metadata
        resolved_signal['currency_pair'] = currency_pair
        resolved_signal['timeframe'] = timeframe
        resolved_signal['signal_count'] = len(signals['technical']) + len(signals['fundamental'])
        
        logger.info(f"Generated {resolved_signal['type']} signal for {currency_pair} with confidence {resolved_signal.get('confidence', 0):.2f}")
        return resolved_signal
    
    def backtest(self, historical_data: pd.DataFrame, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Test synthesizer against historical data.
        
        Args:
            historical_data: Historical market data
            start_date: Start date for backtest
            end_date: End date for backtest
            
        Returns:
            Backtest results
        """
        logger.info(f"Starting backtest from {start_date} to {end_date}")
        
        # Filter data based on date range
        if 'timestamp' in historical_data.columns:
            data = historical_data[(historical_data['timestamp'] >= start_date) & (historical_data['timestamp'] <= end_date)]
        elif isinstance(historical_data.index, pd.DatetimeIndex):
            data = historical_data[(historical_data.index >= start_date) & (historical_data.index <= end_date)]
        else:
            data = historical_data
            logger.warning("Could not filter historical data by date range")
        
        # This would be a more complex implementation that:
        # 1. Iterates through the historical data
        # 2. Generates signals for each time point
        # 3. Tracks performance metrics
        # 4. Updates agent weights based on performance
        # For now, return a placeholder result
        
        return {
            'start_date': start_date,
            'end_date': end_date,
            'total_signals': 0,
            'win_rate': 0,
            'profit': 0,
            'signals': []
        }
    
    @classmethod
    def create_default(cls) -> 'SignalSynthesizer':
        """Create a default signal synthesizer with standard configuration."""
        return cls()
    
    @classmethod
    def create_ml_enhanced(cls) -> 'SignalSynthesizer':
        """
        Create a SignalSynthesizer instance with ML-enhanced signal resolution.
        
        Returns:
            Configured SignalSynthesizer instance
        """
        config = {
            'use_ml': True,
            'weights': {
                'technical': 0.6,
                'fundamental': 0.3,
                'market_condition': 0.1  # Include market condition in ML-enhanced synthesizer
            }
        }
        return cls(config=config)
    
    @classmethod
    def create_rule_based(cls) -> 'SignalSynthesizer':
        """Create a signal synthesizer using only rule-based resolution."""
        config = {
            'use_ml': False
        }
        return cls(config)
    
    def _initialize_market_condition_analyzer(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the market condition analyzer.
        
        Args:
            config: Configuration dictionary
        """
        market_config = config.get('market_condition', {}) if config else {}
        
        # Create market condition analyzer
        self.market_analyzer = TechnicalAnalysisAgentFactory.create_market_condition_analyzer(
            config=market_config
        )
        
        # Register the market analyzer
        self.register_agent(
            self.market_analyzer, 
            'market_condition',
            weight=self.weights.get('market_condition', 0.2)
        )
        
        logger.info("Market condition analyzer initialized") 