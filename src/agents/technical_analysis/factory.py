"""
Factory for Technical Analysis Agents.

This module provides a factory for creating different types of technical analysis
agents with appropriate configurations.
"""

from typing import Dict, Any, Optional, List, Type, Union

from .technical_analysis.agent import TechnicalAnalysisAgent
from .technical_analysis.specialized_agents import (
    MomentumAnalysisAgent,
    VolatilityAnalysisAgent,
    TrendAnalysisAgent,
    PatternRecognitionAgent,
    CombinedAnalysisAgent
)
from .technical_analysis.market_condition_analyzer import MarketConditionAnalyzer


class TechnicalAnalysisAgentFactory:
    """
    Factory for creating technical analysis agents.
    
    This class provides methods to create different types of technical analysis
    agents with appropriate configurations.
    """
    
    @staticmethod
    def create_agent(agent_type: str, config: Optional[Dict[str, Any]] = None, 
                    name: Optional[str] = None) -> TechnicalAnalysisAgent:
        """
        Create a technical analysis agent of the specified type.
        
        Args:
            agent_type: Type of agent to create
            config: Configuration dictionary
            name: Optional name for the agent
            
        Returns:
            Initialized technical analysis agent
            
        Raises:
            ValueError: If agent_type is not recognized
        """
        agent_type = agent_type.lower()
        
        if agent_type == 'momentum':
            return TechnicalAnalysisAgentFactory.create_momentum_agent(config, name)
        elif agent_type == 'volatility':
            return TechnicalAnalysisAgentFactory.create_volatility_agent(config, name)
        elif agent_type == 'trend':
            return TechnicalAnalysisAgentFactory.create_trend_agent(config, name)
        elif agent_type == 'pattern':
            return TechnicalAnalysisAgentFactory.create_pattern_agent(config, name)
        elif agent_type == 'combined':
            return TechnicalAnalysisAgentFactory.create_combined_agent(config, name)
        elif agent_type == 'market_condition' or agent_type == 'market_analyzer':
            return TechnicalAnalysisAgentFactory.create_market_condition_analyzer(config, name)
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")
    
    @staticmethod
    def create_momentum_agent(config: Optional[Dict[str, Any]] = None, 
                             name: Optional[str] = None) -> MomentumAnalysisAgent:
        """
        Create a momentum analysis agent.
        
        Args:
            config: Configuration dictionary
            name: Optional name for the agent
            
        Returns:
            Initialized momentum analysis agent
        """
        return MomentumAnalysisAgent(name=name, config=config)
    
    @staticmethod
    def create_volatility_agent(config: Optional[Dict[str, Any]] = None,
                              name: Optional[str] = None) -> VolatilityAnalysisAgent:
        """
        Create a volatility analysis agent.
        
        Args:
            config: Configuration dictionary
            name: Optional name for the agent
            
        Returns:
            Initialized volatility analysis agent
        """
        return VolatilityAnalysisAgent(name=name, config=config)
    
    @staticmethod
    def create_trend_agent(config: Optional[Dict[str, Any]] = None,
                         name: Optional[str] = None) -> TrendAnalysisAgent:
        """
        Create a trend analysis agent.
        
        Args:
            config: Configuration dictionary
            name: Optional name for the agent
            
        Returns:
            Initialized trend analysis agent
        """
        return TrendAnalysisAgent(name=name, config=config)
    
    @staticmethod
    def create_pattern_agent(config: Optional[Dict[str, Any]] = None,
                           name: Optional[str] = None) -> PatternRecognitionAgent:
        """
        Create a pattern recognition agent.
        
        Args:
            config: Configuration dictionary
            name: Optional name for the agent
            
        Returns:
            Initialized pattern recognition agent
        """
        return PatternRecognitionAgent(name=name, config=config)
    
    @staticmethod
    def create_combined_agent(config: Optional[Dict[str, Any]] = None,
                            name: Optional[str] = None) -> CombinedAnalysisAgent:
        """
        Create a combined analysis agent that integrates multiple analysis types.
        
        Args:
            config: Configuration dictionary
            name: Optional name for the agent
            
        Returns:
            Initialized combined analysis agent
        """
        return CombinedAnalysisAgent(name=name, config=config)
    
    @staticmethod
    def create_market_condition_analyzer(config: Optional[Dict[str, Any]] = None,
                                       name: Optional[str] = None) -> MarketConditionAnalyzer:
        """
        Create a market condition analyzer that detects anomalies and regime changes.
        
        Args:
            config: Configuration dictionary
            name: Optional name for the agent
            
        Returns:
            Initialized market condition analyzer
        """
        return MarketConditionAnalyzer(config=config)
    
    @staticmethod
    def create_custom_rsi_agent(period: int = 14, overbought: int = 70, 
                               oversold: int = 30, name: Optional[str] = None) -> MomentumAnalysisAgent:
        """
        Create a custom RSI-based momentum agent with specific parameters.
        
        Args:
            period: RSI period
            overbought: RSI overbought threshold
            oversold: RSI oversold threshold
            name: Optional name for the agent
            
        Returns:
            Configured RSI-focused momentum agent
        """
        config = {
            'rsi_period': period,
            'rsi_overbought': overbought,
            'rsi_oversold': oversold
        }
        return MomentumAnalysisAgent(name=name or f"RSI({period})-Agent", config=config)
    
    @staticmethod
    def create_custom_macd_agent(fast_period: int = 12, slow_period: int = 26,
                              signal_period: int = 9, name: Optional[str] = None) -> MomentumAnalysisAgent:
        """
        Create a custom MACD-based momentum agent with specific parameters.
        
        Args:
            fast_period: MACD fast period
            slow_period: MACD slow period
            signal_period: MACD signal period
            name: Optional name for the agent
            
        Returns:
            Configured MACD-focused momentum agent
        """
        config = {
            'macd_fast_period': fast_period,
            'macd_slow_period': slow_period,
            'macd_signal_period': signal_period
        }
        return MomentumAnalysisAgent(name=name or f"MACD({fast_period},{slow_period},{signal_period})-Agent", config=config)
    
    @staticmethod
    def create_custom_bollinger_agent(period: int = 20, std_dev: float = 2.0,
                                  name: Optional[str] = None) -> VolatilityAnalysisAgent:
        """
        Create a custom Bollinger Bands volatility agent with specific parameters.
        
        Args:
            period: Bollinger Bands period
            std_dev: Number of standard deviations
            name: Optional name for the agent
            
        Returns:
            Configured Bollinger Bands-focused volatility agent
        """
        config = {
            'bb_period': period,
            'bb_std_dev': std_dev
        }
        return VolatilityAnalysisAgent(name=name or f"Bollinger({period},{std_dev})-Agent", config=config)
    
    @staticmethod
    def create_custom_moving_average_agent(short_period: int = 20, medium_period: int = 50,
                                      long_period: int = 200, name: Optional[str] = None) -> TrendAnalysisAgent:
        """
        Create a custom moving average trend agent with specific parameters.
        
        Args:
            short_period: Short-term MA period
            medium_period: Medium-term MA period
            long_period: Long-term MA period
            name: Optional name for the agent
            
        Returns:
            Configured moving average-focused trend agent
        """
        config = {
            'short_period': short_period,
            'medium_period': medium_period,
            'long_period': long_period
        }
        return TrendAnalysisAgent(name=name or f"MA({short_period},{medium_period},{long_period})-Agent", config=config)
        
    @staticmethod
    def create_custom_market_condition_analyzer(
        volatility_window: int = 20,
        volatility_threshold: float = 2.5,
        regime_window: int = 50,
        anomaly_sensitivity: float = 3.0,
        name: Optional[str] = None
    ) -> MarketConditionAnalyzer:
        """
        Create a custom market condition analyzer with specific parameters.
        
        Args:
            volatility_window: Window for volatility calculations
            volatility_threshold: Threshold for high volatility detection
            regime_window: Window for regime change detection
            anomaly_sensitivity: Sensitivity for anomaly detection (higher = less sensitive)
            name: Optional name for the agent
            
        Returns:
            Configured market condition analyzer
        """
        config = {
            'vol_window': volatility_window,
            'vol_threshold_high': volatility_threshold,
            'regime_window': regime_window,
            'anomaly_sensitivity': anomaly_sensitivity
        }
        return MarketConditionAnalyzer(config=config) 