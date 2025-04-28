"""
Market Condition Filter Module

This module contains the MarketConditionFilter which filters trading signals
based on current market conditions such as volatility and volume.
"""

import logging
from typing import Dict, Any, Optional

from ..models import TradingSignal, SignalFilteringResult, MarketConditions
from .base_filter import BaseSignalFilter

class MarketConditionFilter(BaseSignalFilter):
    """
    Filter that evaluates trading signals against current market conditions.
    
    This filter analyzes market conditions such as volatility, volume, and market regime
    to determine if a signal should be filtered out. For example, certain signal types
    may be less reliable during high volatility periods or low volume conditions.
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize the market condition filter.
        
        Args:
            name: Unique identifier for this filter
            config: Configuration with settings like volatility thresholds
        """
        super().__init__(name, config)
        
        # Set default thresholds if not provided in config
        if "volatility_threshold" not in self.config:
            self.config["volatility_threshold"] = 0.8  # High volatility threshold
            
        if "volume_threshold" not in self.config:
            self.config["volume_threshold"] = 0.3  # Low volume threshold
            
        if "regime_confidence" not in self.config:
            # Confidence required for market regime compatibility
            self.config["regime_confidence"] = 0.7
            
        self.logger.info("Initialized with thresholds: volatility=%.2f, volume=%.2f, regime_confidence=%.2f",
                        self.config["volatility_threshold"],
                        self.config["volume_threshold"],
                        self.config["regime_confidence"])
    
    def _filter_signal(self, signal: TradingSignal, 
                       market_conditions: Optional[MarketConditions] = None) -> SignalFilteringResult:
        """
        Filter signals based on market conditions.
        
        The filter evaluates:
        1. Whether market volatility is too high for the signal type
        2. Whether trading volume is sufficient for the signal
        3. Whether the signal is appropriate for the current market regime
        
        Args:
            signal: Trading signal to evaluate
            market_conditions: Current market conditions for the trading pair
            
        Returns:
            SignalFilteringResult with filtering decision
        """
        # Default threshold from configuration
        threshold = self.config.get("threshold", 0.7)
        
        # If no market conditions data is available, we can't filter properly
        if market_conditions is None:
            self.logger.warning("No market conditions data for %s, passing signal through", 
                               signal.trading_pair)
            return SignalFilteringResult(
                signal_id=signal.id,
                is_filtered_out=False,
                confidence=0.5,
                threshold=threshold
            )
        
        # Calculate filtering confidence based on multiple factors
        confidence = 0.0
        reasons = []
        
        # Check if volatility is too high for this signal type
        volatility_threshold = self.config["volatility_threshold"]
        if market_conditions.volatility > volatility_threshold:
            if signal.signal_type in ["trend_following", "support_resistance"]:
                # These signals are less reliable in high volatility
                confidence += 0.4
                reasons.append(f"High volatility ({market_conditions.volatility:.2f} > {volatility_threshold:.2f})")
                
        # Check if volume is too low
        volume_threshold = self.config["volume_threshold"]
        if market_conditions.volume < volume_threshold:
            # Low volume can lead to false signals across most types
            confidence += 0.3
            reasons.append(f"Low volume ({market_conditions.volume:.2f} < {volume_threshold:.2f})")
            
        # Check if signal matches current market regime
        regime = market_conditions.regime
        regime_confidence = self.config["regime_confidence"]
        
        if regime == "trending" and signal.signal_type in ["trend_following", "momentum"]:
            # These signals work well in trending markets
            pass  # No confidence penalty
        elif regime == "ranging" and signal.signal_type in ["oscillator", "mean_reversion", "support_resistance"]:
            # These signals work well in ranging markets
            pass  # No confidence penalty
        elif regime == "volatile" and signal.signal_type in ["breakout", "volatility"]:
            # These signals work well in volatile markets
            pass  # No confidence penalty
        else:
            # Signal type doesn't align well with current market regime
            confidence += 0.3
            reasons.append(f"Signal type {signal.signal_type} not optimal for {regime} regime")
        
        # Adjust confidence based on signal's own confidence
        # Lower signal confidence means higher filtering confidence
        if signal.confidence < 0.5:
            confidence += 0.2
            reasons.append(f"Low signal confidence ({signal.confidence:.2f})")
            
        # Normalize confidence to 0-1 range
        # Cap at 0.95 to avoid absolute certainty
        confidence = min(0.95, confidence)
        
        # If below threshold, we don't filter out
        is_filtered_out = confidence >= threshold
        
        if is_filtered_out:
            reason_str = ", ".join(reasons)
            self.logger.info("Filtered out signal %s due to: %s", signal.id, reason_str)
        
        return SignalFilteringResult(
            signal_id=signal.id,
            is_filtered_out=is_filtered_out,
            confidence=confidence,
            threshold=threshold
        ) 