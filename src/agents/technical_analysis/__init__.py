"""
Technical Analysis Agent Package.

This package provides a framework for creating and using technical analysis agents
to analyze financial market data, generate trading signals, and evaluate strategies.
"""

from .technical_analysis.agent import TechnicalAnalysisAgent
from .technical_analysis.data_provider import DataProvider
from .technical_analysis.indicator_factory import TAIndicatorFactory
from .technical_analysis.factory import TechnicalAnalysisAgentFactory
from .technical_analysis.specialized_agents import (
    MomentumAnalysisAgent,
    VolatilityAnalysisAgent,
    TrendAnalysisAgent,
    PatternRecognitionAgent,
    CombinedAnalysisAgent
)
from .technical_analysis.market_condition_analyzer import MarketConditionAnalyzer

__all__ = [
    'TechnicalAnalysisAgent',
    'DataProvider',
    'TAIndicatorFactory',
    'TechnicalAnalysisAgentFactory',
    'MomentumAnalysisAgent',
    'VolatilityAnalysisAgent',
    'TrendAnalysisAgent',
    'PatternRecognitionAgent',
    'CombinedAnalysisAgent',
    'MarketConditionAnalyzer',
] 