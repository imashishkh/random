"""
Market Regime Filter Module

This module provides a filter that filters out signals that don't align with
the current market regime (trend, volatility, etc.).
"""

import logging
from typing import Dict, Any, Optional

from ..models import TradingSignal, MarketConditions, SignalFilteringResult
from .base_filter import BaseSignalFilter

logger = logging.getLogger(__name__)

class MarketRegimeFilter(BaseSignalFilter):
    """
    Filters signals based on market regime compatibility.
    
    This filter evaluates whether a trading signal aligns with the current
    market regime, which includes factors like trend direction, volatility,
    and market conditions.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the market regime filter.
        
        Args:
            config: Configuration parameters for the filter
        """
        default_config = {
            'filtering_threshold': 0.6,
            'trend_alignment_weight': 0.5,
            'volatility_compatibility_weight': 0.3,
            'volume_significance_weight': 0.2,
            'min_trend_strength': 0.3,
            'max_volatility_for_weak_signals': 0.7,
            'min_volume_percentile': 0.4,
            'log_level': 'INFO'
        }
        
        # Merge default config with provided config
        merged_config = default_config.copy()
        if config:
            merged_config.update(config)
        
        super().__init__('market_regime_filter', merged_config)
        logger.info("Initialized MarketRegimeFilter")
    
    def _filter_signal(self, signal: TradingSignal, market_conditions: Optional[MarketConditions] = None) -> SignalFilteringResult:
        """
        Evaluate whether the signal aligns with the current market regime.
        
        Args:
            signal: The trading signal to filter
            market_conditions: The current market conditions
            
        Returns:
            SignalFilteringResult containing the filtering assessment
        """
        # If no market conditions provided, we can't do proper filtering
        if not market_conditions:
            logger.warning(f"No market conditions provided for signal {signal.id}, unable to perform market regime filtering")
            return SignalFilteringResult(
                signal_id=signal.id,
                is_filtered_out=False,  # Conservative approach: let it pass
                confidence=0.0,
                threshold=self.filtering_threshold,
                reason="No market conditions available for filtering"
            )
        
        # Calculate overall confidence based on multiple factors
        confidence = self._calculate_confidence(signal, market_conditions)
        
        # Determine if the signal should be filtered out
        is_filtered_out = confidence < self.filtering_threshold
        
        # Prepare reason text
        if is_filtered_out:
            reason = f"Signal doesn't align with market regime (confidence: {confidence:.2f}, threshold: {self.filtering_threshold:.2f})"
        else:
            reason = f"Signal aligns with market regime (confidence: {confidence:.2f}, threshold: {self.filtering_threshold:.2f})"
        
        return SignalFilteringResult(
            signal_id=signal.id,
            is_filtered_out=is_filtered_out,
            confidence=confidence,
            threshold=self.filtering_threshold,
            reason=reason
        )
    
    def _calculate_confidence(self, signal: TradingSignal, market_conditions: MarketConditions) -> float:
        """
        Calculate the confidence score for the signal in the current market regime.
        
        Args:
            signal: The trading signal
            market_conditions: The current market conditions
            
        Returns:
            Confidence score between 0 and 1
        """
        # Extract relevant weights from config
        trend_weight = self.config['trend_alignment_weight']
        volatility_weight = self.config['volatility_compatibility_weight']
        volume_weight = self.config['volume_significance_weight']
        
        # Calculate individual scores
        trend_score = self._calculate_trend_alignment(signal, market_conditions)
        volatility_score = self._calculate_volatility_compatibility(signal, market_conditions)
        volume_score = self._calculate_volume_significance(signal, market_conditions)
        
        # Combine scores using weighted average
        confidence = (
            trend_weight * trend_score + 
            volatility_weight * volatility_score + 
            volume_weight * volume_score
        )
        
        logger.debug(
            f"Signal {signal.id} confidence calculation: "
            f"trend={trend_score:.2f}*{trend_weight:.2f}, "
            f"volatility={volatility_score:.2f}*{volatility_weight:.2f}, "
            f"volume={volume_score:.2f}*{volume_weight:.2f}, "
            f"total={confidence:.2f}"
        )
        
        return confidence
    
    def _calculate_trend_alignment(self, signal: TradingSignal, market_conditions: MarketConditions) -> float:
        """
        Calculate how well the signal aligns with the current market trend.
        
        Args:
            signal: The trading signal
            market_conditions: The current market conditions
            
        Returns:
            Trend alignment score between 0 and 1
        """
        # Extract trend information
        trend_strength = market_conditions.trend_strength
        min_strength = self.config['min_trend_strength']
        
        # If trend is too weak, we consider any signal aligned (neutral)
        if trend_strength < min_strength:
            return 0.7  # Slightly favor signals in neutral/unclear trends
        
        # Check if signal direction aligns with market regime
        if market_conditions.regime == 'uptrend' and signal.direction == 'buy':
            alignment = 1.0  # Perfect alignment: buy in uptrend
        elif market_conditions.regime == 'downtrend' and signal.direction == 'sell':
            alignment = 1.0  # Perfect alignment: sell in downtrend
        elif market_conditions.regime == 'neutral':
            alignment = 0.7  # Neutral market: any signal gets moderate score
        else:
            # Signal opposes trend, how strongly do we reject?
            # We scale from 0.0 (strongest trend) to 0.4 (weaker trend)
            alignment = max(0.0, 0.4 - 0.4 * trend_strength)
        
        return alignment
    
    def _calculate_volatility_compatibility(self, signal: TradingSignal, market_conditions: MarketConditions) -> float:
        """
        Calculate how compatible the signal is with current volatility levels.
        
        Args:
            signal: The trading signal
            market_conditions: The current market conditions
            
        Returns:
            Volatility compatibility score between 0 and 1
        """
        # Extract volatility information
        volatility = market_conditions.volatility
        max_volatility = self.config['max_volatility_for_weak_signals']
        
        # Strong signals can work in any volatility
        if signal.strength >= 0.8:
            return 1.0
        
        # Weaker signals perform poorly in high volatility
        if volatility > max_volatility and signal.strength < 0.5:
            # Linear scale from 0.0 (weakest signals) to 0.5 (medium-strength signals)
            return max(0.0, signal.strength)
        
        # For medium-strength signals or lower volatility, calculate compatibility
        compatibility = 1.0 - (volatility * (1.0 - signal.strength))
        
        return max(0.0, min(1.0, compatibility))
    
    def _calculate_volume_significance(self, signal: TradingSignal, market_conditions: MarketConditions) -> float:
        """
        Calculate how significant the current volume is for this signal.
        
        Args:
            signal: The trading signal
            market_conditions: The current market conditions
            
        Returns:
            Volume significance score between 0 and 1
        """
        # Extract volume information
        volume = market_conditions.volume
        min_volume = self.config['min_volume_percentile']
        
        # If volume below threshold, reduce confidence in signal
        if volume < min_volume:
            # Scale from 0.3 (lowest volume) to 0.7 (near threshold)
            return 0.3 + (0.4 * volume / min_volume)
        
        # Higher volume gives higher confidence, up to 1.0
        return min(1.0, 0.7 + 0.3 * (volume - min_volume) / (1.0 - min_volume)) 