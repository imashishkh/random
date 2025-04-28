"""
Factory module for creating SignalSynthesizer instances.

This module provides factory functions to create different types of
SignalSynthesizer instances with appropriate configurations.
"""

from typing import Dict, Any, Optional, List
import uuid

from .signal_synthesizer import SignalSynthesizer


class SignalSynthesizerFactory:
    """Factory class for creating specialized SignalSynthesizer instances."""
    
    @staticmethod
    def create_default() -> SignalSynthesizer:
        """
        Create a default signal synthesizer with standard configuration.
        
        Returns:
            Configured SignalSynthesizer instance
        """
        config = {
            'weights': {
                'technical': 0.5,
                'fundamental': 0.5,
            },
            'thresholds': {
                'buy': 0.6,
                'sell': -0.6,
                'neutral': 0.2
            },
            'use_ml': False
        }
        return SignalSynthesizer(config)
    
    @staticmethod
    def create_balanced() -> SignalSynthesizer:
        """
        Create a signal synthesizer with balanced weights between technical and fundamental.
        
        Returns:
            Configured SignalSynthesizer instance
        """
        config = {
            'weights': {
                'technical': 0.5,
                'fundamental': 0.5,
                'momentum': 0.2,
                'trend': 0.2,
                'volatility': 0.2,
                'pattern': 0.2,
                'financial': 0.15,
                'news': 0.15,
                'economic': 0.2,
            },
            'thresholds': {
                'buy': 0.6,
                'sell': -0.6,
                'neutral': 0.2
            },
            'use_ml': True
        }
        return SignalSynthesizer(config)
    
    @staticmethod
    def create_technical_biased() -> SignalSynthesizer:
        """
        Create a signal synthesizer with stronger weight on technical analysis.
        
        Returns:
            Configured SignalSynthesizer instance
        """
        config = {
            'weights': {
                'technical': 0.7,
                'fundamental': 0.3,
                'momentum': 0.25,
                'trend': 0.25,
                'volatility': 0.1,
                'pattern': 0.1,
                'financial': 0.1,
                'news': 0.1,
                'economic': 0.1,
            },
            'thresholds': {
                'buy': 0.55,  # More sensitive to buy signals
                'sell': -0.55,  # More sensitive to sell signals
                'neutral': 0.15
            },
            'use_ml': True
        }
        return SignalSynthesizer(config)
    
    @staticmethod
    def create_fundamental_biased() -> SignalSynthesizer:
        """
        Create a signal synthesizer with stronger weight on fundamental analysis.
        
        Returns:
            Configured SignalSynthesizer instance
        """
        config = {
            'weights': {
                'technical': 0.3,
                'fundamental': 0.7,
                'momentum': 0.1,
                'trend': 0.1,
                'volatility': 0.05,
                'pattern': 0.05,
                'financial': 0.3,
                'news': 0.2,
                'economic': 0.2,
            },
            'thresholds': {
                'buy': 0.65,  # Less sensitive to buy signals
                'sell': -0.65,  # Less sensitive to sell signals
                'neutral': 0.25
            },
            'use_ml': True
        }
        return SignalSynthesizer(config)
    
    @staticmethod
    def create_ml_enhanced() -> SignalSynthesizer:
        """
        Create a signal synthesizer with enhanced ML capabilities.
        
        Returns:
            Configured SignalSynthesizer instance
        """
        config = {
            'weights': {
                'technical': 0.5,
                'fundamental': 0.5,
            },
            'use_ml': True,
            'ml_models': {
                'use_ensemble': True,
                'use_bayesian': True
            }
        }
        return SignalSynthesizer(config)
    
    @staticmethod
    def create_rule_based() -> SignalSynthesizer:
        """
        Create a signal synthesizer using only rule-based resolution.
        
        Returns:
            Configured SignalSynthesizer instance
        """
        config = {
            'weights': {
                'technical': 0.5,
                'fundamental': 0.5,
            },
            'use_ml': False,
            'default_resolution_method': 'weighted'
        }
        return SignalSynthesizer(config)
    
    @staticmethod
    def create_custom(weights: Dict[str, float], 
                     thresholds: Optional[Dict[str, float]] = None,
                     use_ml: bool = True,
                     resolution_method: str = 'weighted') -> SignalSynthesizer:
        """
        Create a signal synthesizer with custom configuration.
        
        Args:
            weights: Dictionary mapping agent types to weights
            thresholds: Dictionary with buy, sell, and neutral thresholds
            use_ml: Whether to use ML enhancement
            resolution_method: Default conflict resolution method
            
        Returns:
            Configured SignalSynthesizer instance
        """
        config = {
            'weights': weights,
            'thresholds': thresholds or {
                'buy': 0.6,
                'sell': -0.6,
                'neutral': 0.2
            },
            'use_ml': use_ml,
            'default_resolution_method': resolution_method
        }
        return SignalSynthesizer(config)
    
    @staticmethod
    def from_existing_agents(technical_agents: List[Any], 
                           fundamental_agents: List[Any],
                           config: Optional[Dict[str, Any]] = None) -> SignalSynthesizer:
        """
        Create a signal synthesizer and register existing agents.
        
        Args:
            technical_agents: List of technical analysis agents
            fundamental_agents: List of fundamental analysis agents
            config: Optional configuration for the synthesizer
            
        Returns:
            Configured SignalSynthesizer instance with registered agents
        """
        synthesizer = SignalSynthesizer(config)
        
        # Register technical agents
        for agent in technical_agents:
            agent_subtype = None
            if hasattr(agent, '__class__') and hasattr(agent.__class__, '__name__'):
                class_name = agent.__class__.__name__
                if 'Momentum' in class_name:
                    agent_subtype = 'momentum'
                elif 'Trend' in class_name:
                    agent_subtype = 'trend'
                elif 'Volatility' in class_name:
                    agent_subtype = 'volatility'
                elif 'Pattern' in class_name:
                    agent_subtype = 'pattern'
            
            synthesizer.register_agent(agent, 'technical', agent_subtype)
        
        # Register fundamental agents
        for agent in fundamental_agents:
            agent_subtype = None
            if hasattr(agent, '__class__') and hasattr(agent.__class__, '__name__'):
                class_name = agent.__class__.__name__
                if 'Financial' in class_name:
                    agent_subtype = 'financial'
                elif 'News' in class_name:
                    agent_subtype = 'news'
                elif 'Economic' in class_name:
                    agent_subtype = 'economic'
            
            synthesizer.register_agent(agent, 'fundamental', agent_subtype)
        
        return synthesizer 