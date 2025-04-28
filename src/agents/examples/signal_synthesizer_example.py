"""
Example usage of the SignalSynthesizer class.

This module demonstrates how to use the SignalSynthesizer to combine signals
from technical and fundamental analysis agents.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

from .signal_synthesizer import SignalSynthesizer
from .signal_synthesizer_factory import SignalSynthesizerFactory
from .technical_analysis.agent import TechnicalAnalysisAgent
from .technical_analysis.specialized_agents import (
    MomentumAnalysisAgent,
    TrendAnalysisAgent,
    VolatilityAnalysisAgent,
    PatternRecognitionAgent
)
from .fundamental_analysis.agent import FundamentalAnalysisAgent


def create_sample_data(days=100):
    """Create sample OHLCV data for testing."""
    # Generate sample price data
    np.random.seed(42)
    dates = [datetime.now() - timedelta(days=i) for i in range(days)]
    dates.reverse()
    
    close = 100 + np.cumsum(np.random.normal(0, 1, days))
    high = close + np.random.uniform(0, 2, days)
    low = close - np.random.uniform(0, 2, days)
    open_price = close - np.random.uniform(-1, 1, days)
    volume = np.random.uniform(1000, 5000, days)
    
    # Create DataFrame
    df = pd.DataFrame({
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    }, index=dates)
    
    return df


def example_basic_usage():
    """Demonstrate basic usage of the SignalSynthesizer."""
    print("\n=== Basic SignalSynthesizer Usage ===")
    
    # Create sample data
    data = create_sample_data()
    
    # Create specialized technical analysis agents
    momentum_agent = MomentumAnalysisAgent(name="MomentumAgent")
    trend_agent = TrendAnalysisAgent(name="TrendAgent")
    volatility_agent = VolatilityAnalysisAgent(name="VolatilityAgent")
    
    # Generate signals for each agent
    momentum_signals = momentum_agent.compute_indicators(data)
    momentum_agent.generate_signals(data)
    
    trend_signals = trend_agent.compute_indicators(data)
    trend_agent.generate_signals(data)
    
    volatility_signals = volatility_agent.compute_indicators(data)
    volatility_agent.generate_signals(data)
    
    # Create a SignalSynthesizer
    synthesizer = SignalSynthesizerFactory.create_default()
    
    # Register agents
    synthesizer.register_agent(momentum_agent, 'technical', 'momentum')
    synthesizer.register_agent(trend_agent, 'technical', 'trend')
    synthesizer.register_agent(volatility_agent, 'technical', 'volatility')
    
    # Generate a trading signal
    signal = synthesizer.generate_trading_signal('EUR/USD', timeframe='medium')
    
    # Print the signal
    print(f"Generated signal: {signal['type']}")
    print(f"Confidence: {signal['confidence']:.2f}")
    print(f"Components: {signal['components']}")


def example_different_resolution_methods():
    """Demonstrate different signal resolution methods."""
    print("\n=== Different Resolution Methods ===")
    
    # Create sample data
    data = create_sample_data()
    
    # Create technical analysis agents
    momentum_agent = MomentumAnalysisAgent(name="MomentumAgent")
    trend_agent = TrendAnalysisAgent(name="TrendAgent")
    
    # Generate signals for each agent
    momentum_agent.compute_indicators(data)
    momentum_agent.generate_signals(data)
    
    trend_agent.compute_indicators(data)
    trend_agent.generate_signals(data)
    
    # Create a SignalSynthesizer
    synthesizer = SignalSynthesizerFactory.create_balanced()
    
    # Register agents
    synthesizer.register_agent(momentum_agent, 'technical', 'momentum')
    synthesizer.register_agent(trend_agent, 'technical', 'trend')
    
    # Generate signals with different resolution methods
    weighted_signal = synthesizer.generate_trading_signal('EUR/USD', resolution_method='weighted')
    voting_signal = synthesizer.generate_trading_signal('EUR/USD', resolution_method='voting')
    bayesian_signal = synthesizer.generate_trading_signal('EUR/USD', resolution_method='bayesian')
    
    # Print signals
    print(f"Weighted Method: {weighted_signal['type']} (confidence: {weighted_signal['confidence']:.2f})")
    print(f"Voting Method: {voting_signal['type']} (confidence: {voting_signal['confidence']:.2f})")
    print(f"Bayesian Method: {bayesian_signal['type']} (confidence: {bayesian_signal['confidence']:.2f})")


def example_with_factory():
    """Demonstrate using the factory to create different synthesizers."""
    print("\n=== Using Factory Methods ===")
    
    # Create synthesizers with different configurations
    default_synth = SignalSynthesizerFactory.create_default()
    balanced_synth = SignalSynthesizerFactory.create_balanced()
    technical_synth = SignalSynthesizerFactory.create_technical_biased()
    fundamental_synth = SignalSynthesizerFactory.create_fundamental_biased()
    ml_synth = SignalSynthesizerFactory.create_ml_enhanced()
    
    # Print configurations
    print(f"Default weights: Technical: {default_synth.weights['technical']}, Fundamental: {default_synth.weights['fundamental']}")
    print(f"Balanced weights: Technical: {balanced_synth.weights['technical']}, Fundamental: {balanced_synth.weights['fundamental']}")
    print(f"Technical-biased weights: Technical: {technical_synth.weights['technical']}, Fundamental: {technical_synth.weights['fundamental']}")
    print(f"Fundamental-biased weights: Technical: {fundamental_synth.weights['technical']}, Fundamental: {fundamental_synth.weights['fundamental']}")
    print(f"ML-enhanced using ML: {ml_synth.config.get('use_ml', False)}")


def example_with_performance_feedback():
    """Demonstrate updating weights based on performance feedback."""
    print("\n=== Performance Feedback ===")
    
    # Create a SignalSynthesizer
    synthesizer = SignalSynthesizerFactory.create_default()
    
    # Create agents
    momentum_agent = MomentumAnalysisAgent(name="MomentumAgent")
    trend_agent = TrendAnalysisAgent(name="TrendAgent")
    
    # Register agents
    momentum_id = synthesizer.register_agent(momentum_agent, 'technical', 'momentum')
    trend_id = synthesizer.register_agent(trend_agent, 'technical', 'trend')
    
    # Print initial weights
    print(f"Initial weights:")
    print(f"  Momentum Agent: {synthesizer.agents['technical'][momentum_id]['weight']:.2f}")
    print(f"  Trend Agent: {synthesizer.agents['technical'][trend_id]['weight']:.2f}")
    
    # Update weights based on simulated performance
    performance_data = {
        momentum_id: {'accuracy': 0.75, 'total_signals': 100, 'correct_signals': 75},
        trend_id: {'accuracy': 0.4, 'total_signals': 100, 'correct_signals': 40}
    }
    
    synthesizer.adjust_weights(performance_data)
    
    # Print updated weights
    print(f"Updated weights after performance feedback:")
    print(f"  Momentum Agent (accuracy: 0.75): {synthesizer.agents['technical'][momentum_id]['weight']:.2f}")
    print(f"  Trend Agent (accuracy: 0.40): {synthesizer.agents['technical'][trend_id]['weight']:.2f}")


def main():
    """Run all examples."""
    print("SignalSynthesizer Usage Examples")
    print("===============================")
    
    example_basic_usage()
    example_different_resolution_methods()
    example_with_factory()
    example_with_performance_feedback()
    
    print("\nAll examples completed successfully!")


if __name__ == "__main__":
    main() 