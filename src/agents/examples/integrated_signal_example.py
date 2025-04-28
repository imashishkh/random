#!/usr/bin/env python3
"""
Integrated Signal Example with Market Condition Analyzer

This example demonstrates how the MarketConditionAnalyzer integrates with
the SignalSynthesizer to improve trading signals by accounting for market regimes
and anomalies.
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from pathlib import Path

# Add the parent directory to the path so we can import the modules
sys.path.append(str(Path(__file__).parent.parent.parent))

from .signal_synthesizer import SignalSynthesizer
from .technical_analysis.factory import TechnicalAnalysisAgentFactory
from .technical_analysis.specialized_agents import (
    MomentumAnalysisAgent,
    TrendAnalysisAgent,
    VolatilityAnalysisAgent
)
from .technical_analysis.market_condition_analyzer import MarketConditionAnalyzer
from ...utils.logging.logger import get_logger, configure_logging

# Configure logging
configure_logging(level="INFO")
logger = get_logger()


def generate_sample_data(days=200, regime_change_at=100):
    """
    Generate sample market data with a regime change.
    
    Args:
        days: Number of days of data to generate
        regime_change_at: Day at which regime changes
        
    Returns:
        Pandas DataFrame with OHLCV data
    """
    # Set a seed for reproducibility
    np.random.seed(42)
    
    # Generate dates
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    
    # Initialize price and trend parameters
    price = 100.0
    trend_1 = 0.0005  # First regime: slight uptrend
    trend_2 = -0.001  # Second regime: moderate downtrend
    vol_1 = 0.01      # First regime: low volatility
    vol_2 = 0.025     # Second regime: higher volatility
    
    # Generate price path with regime change
    prices = []
    for i in range(days):
        # Regime change
        trend = trend_1 if i < regime_change_at else trend_2
        vol = vol_1 if i < regime_change_at else vol_2
        
        # Random daily return with changing trend and volatility
        daily_return = trend + np.random.normal(0, vol)
        price *= (1 + daily_return)
        prices.append(price)
    
    # Convert to OHLCV format
    data = pd.DataFrame(index=dates[-len(prices):])
    data['close'] = prices
    
    # Generate open, high, low based on close
    data['open'] = data['close'].shift(1)
    data.loc[data.index[0], 'open'] = data['close'].iloc[0] * 0.99
    
    # Add noise to create high and low
    data['high'] = data['close'] * (1 + np.random.uniform(0, 0.015, size=len(data)))
    data['low'] = data['close'] * (1 - np.random.uniform(0, 0.015, size=len(data)))
    
    # Make sure high is always > close and open
    data['high'] = data[['high', 'close', 'open']].max(axis=1)
    
    # Make sure low is always < close and open
    data['low'] = data[['low', 'close', 'open']].min(axis=1)
    
    # Add volume with a separate regime change
    base_volume = 1000000
    data['volume'] = base_volume * (1 + np.random.uniform(-0.5, 0.8, size=len(data)))
    
    # Add some volume spikes
    spike_indices = np.random.choice(range(len(data)), size=5, replace=False)
    for idx in spike_indices:
        data.iloc[idx, data.columns.get_loc('volume')] *= np.random.uniform(3, 5)
    
    # Add a price gap
    gap_idx = np.random.randint(regime_change_at - 10, regime_change_at + 10)
    data.iloc[gap_idx, data.columns.get_loc('open')] = data.iloc[gap_idx-1, data.columns.get_loc('close')] * 0.95
    
    return data


def main():
    """Run the integrated signal example."""
    print("\n==== INTEGRATED SIGNAL EXAMPLE WITH MARKET CONDITION ANALYZER ====\n")
    
    # Generate sample data with a regime change
    data = generate_sample_data(days=200, regime_change_at=100)
    print(f"Generated sample data with {len(data)} days and a regime change")
    
    # Create signal synthesizer with standard configuration
    synthesizer = SignalSynthesizer()
    print("Created standard signal synthesizer")
    
    # Create technical analysis agents
    momentum_agent = TechnicalAnalysisAgentFactory.create_momentum_agent()
    trend_agent = TechnicalAnalysisAgentFactory.create_trend_agent()
    volatility_agent = TechnicalAnalysisAgentFactory.create_volatility_agent()
    
    # Register agents
    synthesizer.register_agent(momentum_agent, 'technical', 'momentum')
    synthesizer.register_agent(trend_agent, 'technical', 'trend')
    synthesizer.register_agent(volatility_agent, 'technical', 'volatility')
    
    print("Registered technical analysis agents")
    
    # The market condition analyzer is automatically created in the synthesizer
    # We can access it directly
    market_analyzer = next(iter(synthesizer.agents['market_condition'].values()))['agent']
    print(f"Market condition analyzer is already registered: {market_analyzer.name}")
    
    # Generate signals for the entire dataset
    signal_history = []
    window_size = 50  # Analysis window size
    
    print("\nGenerating signals with rolling window...")
    
    for i in range(window_size, len(data)):
        # Get analysis window
        analysis_window = data.iloc[i-window_size:i]
        
        # Process window data with each agent to generate signals
        momentum_agent.generate_signals(analysis_window)
        trend_agent.generate_signals(analysis_window)
        volatility_agent.generate_signals(analysis_window)
        
        # Process market conditions
        market_analyzer.compute_indicators(analysis_window)
        market_analyzer.generate_signals(analysis_window)
        
        # Collect all signals through the synthesizer
        collected_signals = {
            'technical': momentum_agent.signals + trend_agent.signals + volatility_agent.signals,
            'market_condition': market_analyzer.signals
        }
        
        # Resolve signals
        result = synthesizer.resolve_conflicts(collected_signals)
        
        # Add timestamp and price for plotting
        result['timestamp'] = data.index[i]
        result['price'] = data['close'].iloc[i]
        
        signal_history.append(result)
    
    # Convert to DataFrame for analysis
    signal_df = pd.DataFrame(signal_history)
    
    print("\n--- Signal Generation Results ---")
    print(f"Generated {len(signal_df)} signals")
    
    # Count signal types
    buy_signals = sum(1 for s in signal_history if s['type'] == 'buy')
    sell_signals = sum(1 for s in signal_history if s['type'] == 'sell')
    neutral_signals = sum(1 for s in signal_history if s['type'] == 'neutral')
    
    print(f"Buy signals: {buy_signals}")
    print(f"Sell signals: {sell_signals}")
    print(f"Neutral signals: {neutral_signals}")
    
    # Plot results
    plot_results(data, signal_df, market_analyzer)
    
    # Compare with a vanilla approach (no market condition analyzer)
    compare_with_standard_approach(data, signal_df)


def plot_results(data, signal_df, market_analyzer):
    """
    Plot the data with signals and market conditions.
    
    Args:
        data: Market data DataFrame
        signal_df: DataFrame with generated signals
        market_analyzer: MarketConditionAnalyzer instance
    """
    plt.figure(figsize=(14, 12))
    
    # Plot price with signals
    ax1 = plt.subplot(3, 1, 1)
    ax1.plot(data.index, data['close'], label='Close Price')
    
    # Plot buy signals
    buy_signals = signal_df[signal_df['type'] == 'buy']
    if not buy_signals.empty:
        ax1.scatter(buy_signals['timestamp'], 
                   buy_signals['price'] * 0.99,  # Offset slightly for visibility
                   marker='^', color='green', s=100, label='Buy Signal')
    
    # Plot sell signals
    sell_signals = signal_df[signal_df['type'] == 'sell']
    if not sell_signals.empty:
        ax1.scatter(sell_signals['timestamp'], 
                   sell_signals['price'] * 1.01,  # Offset slightly for visibility
                   marker='v', color='red', s=100, label='Sell Signal')
    
    ax1.set_title('Price Chart with Trading Signals')
    ax1.set_ylabel('Price')
    ax1.legend()
    
    # Plot confidence and score
    ax2 = plt.subplot(3, 1, 2, sharex=ax1)
    ax2.plot(signal_df['timestamp'], signal_df['confidence'], label='Signal Confidence', color='blue')
    ax2.plot(signal_df['timestamp'], signal_df['score'], label='Signal Score', color='purple')
    ax2.set_ylabel('Value')
    ax2.axhline(y=0, color='black', linestyle='-', alpha=0.2)
    ax2.legend()
    
    # Plot market conditions
    ax3 = plt.subplot(3, 1, 3, sharex=ax1)
    
    # Identify regime change points
    regime_changes = []
    volatility_changes = []
    
    # Extract from signal context
    for i, row in signal_df.iterrows():
        if 'market_context' in row and isinstance(row['market_context'], dict):
            context = row['market_context']
            
            # Check for regime changes
            if context.get('regime') == 'changing':
                regime_changes.append(row['timestamp'])
            
            # Check for volatility state changes
            if context.get('volatility') in ['extremely_high', 'high']:
                volatility_changes.append((row['timestamp'], 'high'))
            elif context.get('volatility') in ['extremely_low', 'low']:
                volatility_changes.append((row['timestamp'], 'low'))
    
    # Plot volume as background
    ax3.bar(data.index, data['volume'], alpha=0.3, color='gray', label='Volume')
    
    # Mark regime changes
    for change_point in regime_changes:
        ax3.axvline(x=change_point, color='red', linestyle='--', alpha=0.5)
    
    # Mark volatility changes
    for change_point, vol_type in volatility_changes:
        color = 'purple' if vol_type == 'high' else 'blue'
        ax3.scatter(change_point, 0, marker='o', color=color, s=100, alpha=0.7)
    
    ax3.set_ylabel('Volume')
    ax3.set_xlabel('Date')
    ax3.text(0.02, 0.9, 'Red lines = Regime Changes', transform=ax3.transAxes, color='red')
    ax3.text(0.02, 0.85, 'Purple dots = High Volatility', transform=ax3.transAxes, color='purple')
    ax3.text(0.02, 0.8, 'Blue dots = Low Volatility', transform=ax3.transAxes, color='blue')
    
    plt.tight_layout()
    plt.savefig('integrated_signal_analysis.png')
    print("\nPlot saved as 'integrated_signal_analysis.png'")
    
    # Show plot if in interactive mode
    try:
        plt.show()
    except:
        pass


def compare_with_standard_approach(data, signal_df):
    """
    Compare market-condition aware signals with standard approach.
    
    Args:
        data: Market data DataFrame
        signal_df: DataFrame with market-condition aware signals
    """
    # Create a simple strategy: buy in uptrends, sell in downtrends
    sma_short = data['close'].rolling(window=20).mean()
    sma_long = data['close'].rolling(window=50).mean()
    
    # Generate simple signals: buy when short > long, sell when short < long
    simple_signals = []
    
    for i in range(max(50, len(signal_df))):
        idx = i + (len(data) - len(signal_df))
        if idx < len(data):
            if sma_short.iloc[idx] > sma_long.iloc[idx]:
                signal_type = 'buy'
            else:
                signal_type = 'sell'
                
            simple_signals.append({
                'timestamp': data.index[idx],
                'price': data['close'].iloc[idx],
                'type': signal_type,
                'confidence': 0.8  # Fixed confidence
            })
    
    # Convert to DataFrame
    simple_df = pd.DataFrame(simple_signals)
    
    if len(simple_df) != len(signal_df):
        print("Warning: Signal lengths differ, comparison may not be accurate")
    
    # Compare performance
    print("\n--- Strategy Comparison ---")
    
    # Calculate returns for market-condition aware strategy
    market_aware_returns = calculate_returns(signal_df)
    
    # Calculate returns for simple strategy
    simple_returns = calculate_returns(simple_df)
    
    print(f"Market-condition aware strategy return: {market_aware_returns:.2%}")
    print(f"Simple moving average strategy return: {simple_returns:.2%}")
    
    # Compare signal agreement
    comparison = pd.merge(
        signal_df[['timestamp', 'type']], 
        simple_df[['timestamp', 'type']], 
        on='timestamp', 
        suffixes=('_market_aware', '_simple')
    )
    
    agreement_count = sum(comparison['type_market_aware'] == comparison['type_simple'])
    agreement_pct = agreement_count / len(comparison) if len(comparison) > 0 else 0
    
    print(f"Signal agreement: {agreement_count}/{len(comparison)} ({agreement_pct:.2%})")
    disagreement_points = len(comparison) - agreement_count
    print(f"Signals differ at {disagreement_points} points")


def calculate_returns(signal_df):
    """
    Calculate simple returns from signals.
    
    Args:
        signal_df: DataFrame with signal data
        
    Returns:
        Total return as a percentage
    """
    if signal_df.empty:
        return 0.0
    
    # Simple strategy: Buy on buy signals, sell on sell signals
    position = 0  # 0 = no position, 1 = long
    entry_price = 0
    total_return = 1.0  # Multiplicative return
    
    for i, row in signal_df.iterrows():
        price = row['price']
        
        if row['type'] == 'buy' and position == 0:
            # Enter long position
            position = 1
            entry_price = price
        elif row['type'] == 'sell' and position == 1:
            # Exit long position
            position = 0
            # Calculate return
            trade_return = price / entry_price
            total_return *= trade_return
    
    # Close any open position
    if position == 1:
        final_price = signal_df['price'].iloc[-1]
        trade_return = final_price / entry_price
        total_return *= trade_return
    
    # Convert to percentage return
    return total_return - 1.0


if __name__ == "__main__":
    main() 