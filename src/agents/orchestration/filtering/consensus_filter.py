"""
Consensus Signal Filter

This module provides a filter that reduces false positives by analyzing signal consensus,
timeframe confirmation, and market regime compatibility.
"""

from typing import Dict, List, Any, Optional, Union, Set
from datetime import datetime, timedelta

from ....utils.logging.logger import get_logger
from .orchestration.models import TradingSignal, MarketConditions
from .orchestration.filtering.base_filter import BaseSignalFilter

logger = get_logger()


class ConsensusFilter(BaseSignalFilter):
    """
    Consensus filter for reducing false positives in trading signals.
    
    Uses multiple confirmation sources including:
    - Signal consensus across multiple agents
    - Timeframe confirmation
    - Market regime compatibility
    - Trend alignment
    - Volume confirmation
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the consensus filter.
        
        Args:
            config: Configuration dictionary
        """
        # Default configuration
        default_config = {
            'base_threshold': 0.55,                  # Base threshold for filtering (lower = more signals pass)
            'lookback_window': 30,                   # Minutes to look back for consensus signals
            'min_consensus_count': 2,                # Minimum number of signals needed for consensus
            'timeframe_weight': 0.3,                 # Weight of timeframe confirmation
            'consensus_weight': 0.4,                 # Weight of agent consensus
            'market_regime_weight': 0.3,             # Weight of market regime compatibility
            'regime_compatibility': {                # Which signal types work well in which market regimes
                'trend': ['trending'],
                'mean_reversion': ['ranging'],
                'volatility': ['volatile'],
                'pattern': ['trending', 'ranging'],
                'sentiment': ['trending', 'volatile'],
                'fundamental': ['normal', 'trending']
            },
            'min_active_filters': 2,                 # Minimum number of filtering methods that should be active
            'enable_timeframe_confirmation': True,   # Whether to check multiple timeframes
            'enable_agent_consensus': True,          # Whether to check for consensus among agents
            'enable_regime_filtering': True,         # Whether to filter based on market regime
            'enable_volume_confirmation': True,      # Whether to check volume confirmation
            'max_signals_per_pair': 3,               # Maximum signals per trading pair in time window
        }
        
        # Merge with provided config
        if config:
            merged_config = default_config.copy()
            merged_config.update(config)
        else:
            merged_config = default_config
        
        # Initialize base class
        super().__init__(name="ConsensusFilter", config=merged_config)
        
        # Store recent signals for consensus checking
        self.recent_signals: Dict[str, List[TradingSignal]] = {}
        
        # Store signal counts per trading pair
        self.signal_counts: Dict[str, int] = {}
        
        logger.info("Consensus filter initialized")
    
    def _filter_signal(self, signal: TradingSignal, market_conditions: Optional[MarketConditions] = None) -> Dict[str, Any]:
        """
        Filter a trading signal using consensus and confirmation methods.
        
        Args:
            signal: Trading signal to filter
            market_conditions: Current market conditions
            
        Returns:
            Filtering data dictionary
        """
        # Prepare return structure
        filtering_data = {
            'confidence': 0.0,
            'threshold': self.config['base_threshold'],
            'components': {},
            'reasons': {},
            'metadata': {}
        }
        
        # Store signal for future consensus checking
        self._store_signal(signal)
        
        # Count active filtering methods to ensure we have enough data
        active_filters = 0
        
        # 1. Check agent consensus (if enabled and we have enough data)
        consensus_score = 0.0
        if self.config['enable_agent_consensus']:
            consensus_score = self._check_agent_consensus(signal)
            filtering_data['components']['consensus'] = consensus_score
            active_filters += 1
        
        # 2. Check timeframe confirmation (if enabled)
        timeframe_score = 0.0
        if self.config['enable_timeframe_confirmation']:
            timeframe_score = self._check_timeframe_confirmation(signal)
            filtering_data['components']['timeframe'] = timeframe_score
            active_filters += 1
        
        # 3. Check market regime compatibility (if enabled and we have market conditions)
        regime_score = 0.0
        if self.config['enable_regime_filtering'] and market_conditions:
            regime_score = self._check_market_regime_compatibility(signal, market_conditions)
            filtering_data['components']['market_regime'] = regime_score
            active_filters += 1
        
        # 4. Check volume confirmation (if enabled and we have market conditions)
        volume_score = 0.0
        if self.config['enable_volume_confirmation'] and market_conditions and hasattr(market_conditions, 'volume'):
            volume_score = self._check_volume_confirmation(signal, market_conditions)
            filtering_data['components']['volume'] = volume_score
            active_filters += 1
        
        # 5. Check signal rate limiting per trading pair
        rate_limit_score = self._check_rate_limiting(signal)
        filtering_data['components']['rate_limit'] = rate_limit_score
        
        # Skip filtering if we don't have enough active filtering methods
        if active_filters < self.config['min_active_filters']:
            logger.warning(f"Not enough active filtering methods for signal {signal.id}. Have {active_filters}, need {self.config['min_active_filters']}")
            filtering_data['confidence'] = 1.0  # High confidence to avoid filtering
            filtering_data['metadata']['insufficient_filters'] = True
            return filtering_data
        
        # Calculate overall confidence
        confidence = (
            (consensus_score * self.config['consensus_weight']) +
            (timeframe_score * self.config['timeframe_weight']) +
            (regime_score * self.config['market_regime_weight']) +
            (volume_score * 0.1)  # Small weight for volume
        ) / (self.config['consensus_weight'] + self.config['timeframe_weight'] + self.config['market_regime_weight'] + 0.1)
        
        # Apply rate limiting as a multiplier (0 = filtered, 1 = passed)
        confidence *= rate_limit_score
        
        # Set confidence
        filtering_data['confidence'] = confidence
        
        # Set filtering reasons if confidence is low
        if confidence < self.config['base_threshold']:
            if consensus_score < 0.5:
                filtering_data['reasons']['insufficient_consensus'] = f"Score: {consensus_score:.2f}"
            if timeframe_score < 0.5:
                filtering_data['reasons']['timeframe_mismatch'] = f"Score: {timeframe_score:.2f}"
            if regime_score < 0.5:
                filtering_data['reasons']['regime_incompatibility'] = f"Score: {regime_score:.2f}"
            if rate_limit_score < 1.0:
                filtering_data['reasons']['rate_limited'] = f"Too many signals for {signal.trading_pair}"
        
        return filtering_data
    
    def _store_signal(self, signal: TradingSignal) -> None:
        """
        Store a signal for future consensus checking.
        
        Args:
            signal: Trading signal to store
        """
        # Initialize list for trading pair if needed
        trading_pair = signal.trading_pair
        if trading_pair not in self.recent_signals:
            self.recent_signals[trading_pair] = []
            self.signal_counts[trading_pair] = 0
        
        # Add signal to list
        self.recent_signals[trading_pair].append(signal)
        
        # Update signal count
        self.signal_counts[trading_pair] += 1
        
        # Prune old signals
        self._prune_old_signals()
    
    def _prune_old_signals(self) -> None:
        """Remove signals older than the lookback window."""
        cutoff_time = datetime.utcnow() - timedelta(minutes=self.config['lookback_window'])
        
        for pair in list(self.recent_signals.keys()):
            self.recent_signals[pair] = [
                signal for signal in self.recent_signals[pair]
                if signal.created_at > cutoff_time
            ]
            
            # If no signals left, remove the trading pair from tracking
            if not self.recent_signals[pair]:
                del self.recent_signals[pair]
                self.signal_counts[pair] = 0
    
    def _check_agent_consensus(self, signal: TradingSignal) -> float:
        """
        Check for consensus among multiple agents.
        
        Args:
            signal: Trading signal to check
            
        Returns:
            Consensus score between 0 and 1
        """
        # Get recent signals for the same trading pair
        trading_pair = signal.trading_pair
        if trading_pair not in self.recent_signals:
            return 0.0
        
        # Find signals in the same direction (excluding this signal)
        signals_in_direction = [
            s for s in self.recent_signals[trading_pair]
            if s.id != signal.id and s.direction == signal.direction
        ]
        
        # Check signal count
        consensus_count = len(signals_in_direction)
        min_required = self.config['min_consensus_count']
        
        # Calculate consensus score based on count
        if consensus_count >= min_required:
            return 1.0
        elif consensus_count > 0:
            return consensus_count / min_required
        else:
            return 0.0
    
    def _check_timeframe_confirmation(self, signal: TradingSignal) -> float:
        """
        Check for confirmation across multiple timeframes.
        
        Args:
            signal: Trading signal to check
            
        Returns:
            Timeframe confirmation score between 0 and 1
        """
        # Get recent signals for the same trading pair
        trading_pair = signal.trading_pair
        if trading_pair not in self.recent_signals:
            return 0.0
        
        # Get signal's timeframe
        timeframe = signal.timeframe
        
        # Define timeframe relationships (larger/smaller)
        # Map timeframes to numerical values for comparison
        timeframe_values = {
            '1m': 1,
            '5m': 5,
            '15m': 15,
            '30m': 30,
            '1h': 60,
            '4h': 240,
            '1d': 1440
        }
        
        # Get value for current timeframe
        if timeframe not in timeframe_values:
            return 0.5  # Unknown timeframe, neutral score
        
        current_value = timeframe_values[timeframe]
        
        # Find signals with different timeframes but same direction
        confirming_signals = []
        larger_timeframe_confirmed = False
        smaller_timeframe_confirmed = False
        
        for s in self.recent_signals[trading_pair]:
            if s.id != signal.id and s.direction == signal.direction and s.timeframe in timeframe_values:
                confirming_signals.append(s)
                
                # Check if timeframe is larger or smaller
                other_value = timeframe_values[s.timeframe]
                if other_value > current_value:
                    larger_timeframe_confirmed = True
                elif other_value < current_value:
                    smaller_timeframe_confirmed = True
        
        # Calculate score based on timeframe confirmation
        # Highest score when confirmed by both larger and smaller timeframes
        if larger_timeframe_confirmed and smaller_timeframe_confirmed:
            return 1.0
        elif larger_timeframe_confirmed or smaller_timeframe_confirmed:
            return 0.75
        elif len(confirming_signals) > 0:
            return 0.5
        else:
            return 0.0
    
    def _check_market_regime_compatibility(self, signal: TradingSignal, market_conditions: MarketConditions) -> float:
        """
        Check if signal type is compatible with current market regime.
        
        Args:
            signal: Trading signal to check
            market_conditions: Current market conditions
            
        Returns:
            Regime compatibility score between 0 and 1
        """
        # Get signal type
        signal_type = signal.agent_type
        if not signal_type:
            return 0.5  # Unknown signal type, neutral score
        
        # Get market regime
        regime = getattr(market_conditions, 'regime', 'normal')
        
        # Check compatibility based on configuration
        compatibility_map = self.config['regime_compatibility']
        
        if signal_type in compatibility_map:
            compatible_regimes = compatibility_map[signal_type]
            
            # Fully compatible
            if regime in compatible_regimes:
                return 1.0
            
            # Somewhat compatible (e.g., trending is somewhat compatible with normal)
            elif regime == 'normal' or 'normal' in compatible_regimes:
                return 0.5
                
            # Incompatible
            else:
                return 0.2
        
        # Unknown signal type compatibility
        return 0.5
    
    def _check_volume_confirmation(self, signal: TradingSignal, market_conditions: MarketConditions) -> float:
        """
        Check if volume confirms the signal.
        
        Args:
            signal: Trading signal to check
            market_conditions: Current market conditions
            
        Returns:
            Volume confirmation score between 0 and 1
        """
        # Get volume and volume percentile
        volume = getattr(market_conditions, 'volume', 0)
        volume_percentile = getattr(market_conditions, 'volume_percentile', 0.5)
        
        # Higher volume is better for trend signals
        if signal.agent_type == 'trend':
            return min(1.0, volume_percentile * 1.5)  # Amplify volume importance for trend signals
            
        # Normal volume is better for mean reversion
        elif signal.agent_type == 'mean_reversion':
            # Score peaks at 0.5 (median volume) and decreases toward extremes
            return 1.0 - abs(volume_percentile - 0.5) * 2
            
        # High volume is good for volatility signals
        elif signal.agent_type == 'volatility':
            return volume_percentile
            
        # Default case
        else:
            return 0.5 + (volume_percentile - 0.5) * 0.5  # Slight preference for higher volume
    
    def _check_rate_limiting(self, signal: TradingSignal) -> float:
        """
        Check if we're exceeding the maximum signals per trading pair.
        
        Args:
            signal: Trading signal to check
            
        Returns:
            Rate limiting score (0 = filtered, 1 = passed)
        """
        trading_pair = signal.trading_pair
        max_signals = self.config['max_signals_per_pair']
        
        # Check current count against max
        if trading_pair in self.signal_counts and self.signal_counts[trading_pair] > max_signals:
            return 0.0  # Filter out, too many signals
        
        return 1.0  # Pass rate limiting check 