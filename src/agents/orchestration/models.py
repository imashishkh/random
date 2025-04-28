"""
Data Models for Signal Orchestration

This module provides data models for representing trading signals, market conditions,
and related entities in the signal orchestration system.
"""

import uuid
from typing import Dict, List, Any, Optional, Union, Literal
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MarketConditions:
    """
    Model representing market conditions for a specific trading pair.
    """
    trading_pair: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Market regime (e.g., trending, ranging, volatile, normal)
    regime: str = "normal"
    
    # Volatility metrics
    volatility: float = 0.0
    volatility_percentile: float = 0.0
    
    # Trend metrics
    trend_strength: float = 0.0
    trend_direction: Literal["up", "down", "sideways"] = "sideways"
    
    # Volume metrics
    volume: float = 0.0
    volume_percentile: float = 0.0
    
    # Liquidity metrics
    liquidity: float = 0.0
    spread: float = 0.0
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'trading_pair': self.trading_pair,
            'timestamp': self.timestamp.isoformat(),
            'regime': self.regime,
            'volatility': self.volatility,
            'volatility_percentile': self.volatility_percentile,
            'trend_strength': self.trend_strength,
            'trend_direction': self.trend_direction,
            'volume': self.volume,
            'volume_percentile': self.volume_percentile,
            'liquidity': self.liquidity,
            'spread': self.spread,
            'metadata': self.metadata
        }


@dataclass
class TradingSignal:
    """
    Model representing a trading signal from an agent.
    """
    # Basic identification
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trading_pair: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    # Signal source
    agent_id: str = ""
    agent_type: str = ""
    signal_type: str = ""  # e.g., "technical", "fundamental", "anomaly"
    
    # Signal details
    direction: Literal["buy", "sell", "neutral"] = "neutral"
    timeframe: str = "1h"  # Timeframe this signal applies to
    strength: float = 0.0  # Raw signal strength from agent
    confidence: float = 0.0  # Agent's confidence in the signal
    
    # Price levels
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    # Signal status throughout the pipeline
    is_validated: bool = False
    is_filtered: bool = False
    is_published: bool = False
    
    # Validation details
    validation_score: float = 0.0
    validation_threshold: float = 0.0
    validation_time: Optional[datetime] = None
    validation_components: Dict[str, float] = field(default_factory=dict)
    
    # Filtering details
    filtering_score: float = 0.0
    filtering_threshold: float = 0.0
    filtering_time: Optional[datetime] = None
    filtering_details: Dict[str, Any] = field(default_factory=dict)
    
    # Supporting data and metadata
    indicators: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            'id': self.id,
            'trading_pair': self.trading_pair,
            'created_at': self.created_at.isoformat(),
            'agent_id': self.agent_id,
            'agent_type': self.agent_type,
            'signal_type': self.signal_type,
            'direction': self.direction,
            'timeframe': self.timeframe,
            'strength': self.strength,
            'confidence': self.confidence,
            'is_validated': self.is_validated,
            'is_filtered': self.is_filtered,
            'is_published': self.is_published,
            'indicators': self.indicators,
            'metadata': self.metadata
        }
        
        # Add optional fields if they exist
        if self.entry_price is not None:
            result['entry_price'] = self.entry_price
        if self.stop_loss is not None:
            result['stop_loss'] = self.stop_loss
        if self.take_profit is not None:
            result['take_profit'] = self.take_profit
            
        # Add validation details if validated
        if self.is_validated:
            result['validation'] = {
                'score': self.validation_score,
                'threshold': self.validation_threshold,
                'time': self.validation_time.isoformat() if self.validation_time else None,
                'components': self.validation_components
            }
            
        # Add filtering details if filtered
        if self.is_filtered:
            result['filtering'] = {
                'score': self.filtering_score,
                'threshold': self.filtering_threshold,
                'time': self.filtering_time.isoformat() if self.filtering_time else None,
                'details': self.filtering_details
            }
            
        return result


@dataclass
class SignalValidationResult:
    """
    Model representing the result of signal validation.
    """
    signal_id: str
    is_valid: bool
    confidence: float
    threshold: float
    validated_at: datetime = field(default_factory=datetime.utcnow)
    components: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'signal_id': self.signal_id,
            'is_valid': self.is_valid,
            'confidence': self.confidence,
            'threshold': self.threshold,
            'validated_at': self.validated_at.isoformat(),
            'components': self.components,
            'metadata': self.metadata
        }


@dataclass
class SignalFilteringResult:
    """
    Model representing the result of signal filtering.
    """
    signal_id: str
    is_filtered_out: bool
    confidence: float
    threshold: float
    filtered_at: datetime = field(default_factory=datetime.utcnow)
    reasons: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'signal_id': self.signal_id,
            'is_filtered_out': self.is_filtered_out,
            'confidence': self.confidence,
            'threshold': self.threshold,
            'filtered_at': self.filtered_at.isoformat(),
            'reasons': self.reasons,
            'metadata': self.metadata
        }


@dataclass
class PublishedSignal:
    """
    Model representing a signal that has been validated, filtered, and published.
    This is the final output of the orchestration system.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    original_signal_id: str = ""
    trading_pair: str = ""
    direction: Literal["buy", "sell", "neutral"] = "neutral"
    timeframe: str = "1h"
    confidence: float = 0.0
    published_at: datetime = field(default_factory=datetime.utcnow)
    
    # Price levels
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    # Risk metrics
    risk_reward_ratio: Optional[float] = None
    position_size_recommendation: Optional[float] = None
    
    # Signal sources and validation
    agent_sources: List[Dict[str, Any]] = field(default_factory=list)
    validation_summary: Dict[str, Any] = field(default_factory=dict)
    market_conditions: Dict[str, Any] = field(default_factory=dict)
    
    # Additional data
    indicators: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            'id': self.id,
            'original_signal_id': self.original_signal_id,
            'trading_pair': self.trading_pair,
            'direction': self.direction,
            'timeframe': self.timeframe,
            'confidence': self.confidence,
            'published_at': self.published_at.isoformat(),
            'agent_sources': self.agent_sources,
            'validation_summary': self.validation_summary,
            'market_conditions': self.market_conditions,
            'indicators': self.indicators,
            'metadata': self.metadata
        }
        
        # Add optional fields if they exist
        if self.entry_price is not None:
            result['entry_price'] = self.entry_price
        if self.stop_loss is not None:
            result['stop_loss'] = self.stop_loss
        if self.take_profit is not None:
            result['take_profit'] = self.take_profit
        if self.risk_reward_ratio is not None:
            result['risk_reward_ratio'] = self.risk_reward_ratio
        if self.position_size_recommendation is not None:
            result['position_size_recommendation'] = self.position_size_recommendation
            
        return result 