#!/usr/bin/env python3
"""
Market Condition Analyzer Example

This example demonstrates how to use the MarketConditionAnalyzer
to detect market anomalies, regime changes, and extreme market conditions.
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from pathlib import Path

# Add the parent directory to the path so we can import the modules
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from .technical_analysis.market_condition_analyzer import MarketConditionAnalyzer
from .technical_analysis.factory import TechnicalAnalysisAgentFactory
from ....utils.logging.logger import get_logger, configure_logging

# Configure logging
configure_logging(level="INFO")
logger = get_logger()


def generate_sample_data(days=200, volatility_change_at=100):
    """
    Generate sample market data with a volatility regime change.
    
    Args:
        days: Number of days of data to generate
        volatility_change_at: Day at which volatility changes
        
    Returns:
        Pandas DataFrame with OHLCV data
    """
    # Set a seed for reproducibility
    np.random.seed(42)
    
    # Generate dates
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    
    # Initialize price and volatility
    price = 100.0
    vol_1 = 0.01  # First regime volatility
    vol_2 = 0.03  # Second regime volatility (higher)
    
    # Generate price path with regime change
    prices = []
    for i in range(days):
        # Volatility regime change
        vol = vol_1 if i < volatility_change_at else vol_2
        
        # Random daily return with changing volatility
        daily_return = np.random.normal(0, vol)
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
    gap_idx = np.random.randint(days - 30, days - 10)
    data.iloc[gap_idx, data.columns.get_loc('open')] = data.iloc[gap_idx-1, data.columns.get_loc('close')] * 1.05
    
    return data


def main():
    """Run the market condition analyzer example."""
    print("\n==== MARKET CONDITION ANALYZER EXAMPLE ====\n")
    
    # Create a market condition analyzer
    analyzer = TechnicalAnalysisAgentFactory.create_market_condition_analyzer(
        config={
            'vol_window': 20,
            'vol_threshold_high': 1.5,  # Make more sensitive for example
            'vol_threshold_low': 0.5,
            'volume_window': 20,
            'volume_threshold': 1.5,  # Make more sensitive for example
            'anomaly_sensitivity': 2.0  # Make more sensitive for example
        }
    )
    
    print(f"Created {analyzer.name} agent")
    
    # Generate sample data with a volatility regime change
    data = generate_sample_data(days=200, volatility_change_at=100)
    print(f"Generated sample data with {len(data)} days and a volatility regime change")
    
    # Compute indicators and analyze market conditions
    analyzer.compute_indicators(data)
    signals = analyzer.generate_signals(data)
    
    print("\n--- Market Condition Analysis Results ---")
    
    # Display market conditions
    conditions = analyzer.conditions
    print(f"Volatility state: {conditions['volatility_state']}")
    print(f"Liquidity state: {conditions['liquidity_state']}")
    print(f"Trend state: {conditions['trend_state']}")
    print(f"Regime state: {conditions['regime_state']}")
    
    # Display detected anomalies
    if conditions['anomalies']:
        print("\nDetected anomalies:")
        for anomaly in conditions['anomalies']:
            print(f"  - {anomaly['type']} ({anomaly['severity']})")
    else:
        print("\nNo anomalies detected")
        
    # Display generated signals
    if signals:
        print("\nGenerated signals:")
        for signal in signals:
            print(f"  - {signal['type']} signal: {signal['indicator']} ({signal['condition']}) with confidence {signal['confidence']:.2f}")
    else:
        print("\nNo signals generated")
    
    # Plot data and highlight anomalies
    plot_results(data, analyzer)


def plot_results(data, analyzer):
    """
    Plot the data with market condition annotations.
    
    Args:
        data: Market data as a pandas DataFrame
        analyzer: MarketConditionAnalyzer instance
    """
    plt.figure(figsize=(14, 10))
    
    # Plot price
    ax1 = plt.subplot(3, 1, 1)
    ax1.plot(data.index, data['close'], label='Close Price')
    ax1.set_title('Market Price with Condition Analysis')
    ax1.set_ylabel('Price')
    ax1.legend()
    
    # Highlight volatility conditions
    vol_state = analyzer.conditions['volatility_state']
    if vol_state in ['high', 'extremely_high']:
        ax1.axhspan(min(data['low']), max(data['high']), alpha=0.2, color='red', label=f'High Volatility ({vol_state})')
    elif vol_state in ['low', 'extremely_low']:
        ax1.axhspan(min(data['low']), max(data['high']), alpha=0.2, color='blue', label=f'Low Volatility ({vol_state})')
    
    # Plot realized volatility
    ax2 = plt.subplot(3, 1, 2, sharex=ax1)
    if 'realized_vol' in analyzer.indicators:
        ax2.plot(data.index, analyzer.indicators['realized_vol'], label='Realized Volatility', color='orange')
        
        # Add threshold lines
        vol_data = analyzer.indicators['realized_vol'].dropna()
        vol_mean = vol_data.mean()
        vol_std = vol_data.std()
        
        ax2.axhline(y=vol_mean, color='k', linestyle='-', alpha=0.3, label='Mean Volatility')
        ax2.axhline(y=vol_mean + analyzer.config['vol_threshold_high'] * vol_std, 
                   color='r', linestyle='--', alpha=0.5, label='High Volatility Threshold')
        ax2.axhline(y=vol_mean - analyzer.config['vol_threshold_low'] * vol_std, 
                   color='g', linestyle='--', alpha=0.5, label='Low Volatility Threshold')
    
    ax2.set_ylabel('Volatility')
    ax2.legend()
    
    # Plot volume with abnormal volume highlighted
    ax3 = plt.subplot(3, 1, 3, sharex=ax1)
    ax3.bar(data.index, data['volume'], label='Volume', alpha=0.5)
    
    # Highlight abnormal volume
    if 'volume_ma' in analyzer.indicators and 'volume_std' in analyzer.indicators:
        vol_ma = analyzer.indicators['volume_ma']
        vol_std = analyzer.indicators['volume_std']
        
        high_vol_threshold = vol_ma + analyzer.config['volume_threshold'] * vol_std
        low_vol_threshold = vol_ma - analyzer.config['volume_threshold'] * vol_std
        
        high_vol_mask = data['volume'] > high_vol_threshold
        low_vol_mask = data['volume'] < low_vol_threshold
        
        if high_vol_mask.any():
            ax3.bar(data.index[high_vol_mask], data['volume'][high_vol_mask], 
                   color='red', label='Abnormally High Volume')
            
        if low_vol_mask.any():
            ax3.bar(data.index[low_vol_mask], data['volume'][low_vol_mask], 
                   color='blue', label='Abnormally Low Volume')
    
    ax3.set_ylabel('Volume')
    ax3.set_xlabel('Date')
    ax3.legend()
    
    # Mark anomalies
    for anomaly in analyzer.conditions['anomalies']:
        if anomaly['type'] == 'price_gap':
            last_idx = data.index[-1]
            ax1.annotate(f"Price Gap ({anomaly['severity']})", 
                        xy=(last_idx, data['close'].iloc[-1]),
                        xytext=(last_idx, data['close'].iloc[-1] * 1.05),
                        arrowprops=dict(facecolor='red', shrink=0.05),
                        horizontalalignment='right')
        
        elif anomaly['type'] == 'volatility_clustering':
            last_idx = data.index[-1]
            ax2.annotate(f"Volatility Clustering ({anomaly['severity']})", 
                        xy=(last_idx, analyzer.indicators['realized_vol'].iloc[-1]),
                        xytext=(last_idx, analyzer.indicators['realized_vol'].iloc[-1] * 1.2),
                        arrowprops=dict(facecolor='purple', shrink=0.05),
                        horizontalalignment='right')
                        
        elif anomaly['type'] == 'volume_price_divergence':
            last_idx = data.index[-1]
            ax3.annotate(f"{anomaly['subtype']} ({anomaly['severity']})", 
                        xy=(last_idx, data['volume'].iloc[-1]),
                        xytext=(last_idx, data['volume'].iloc[-1] * 1.2),
                        arrowprops=dict(facecolor='green', shrink=0.05),
                        horizontalalignment='right')
    
    plt.tight_layout()
    plt.savefig('market_condition_analysis.png')
    print("\nPlot saved as 'market_condition_analysis.png'")
    
    # Show plot if in interactive mode
    try:
        plt.show()
    except:
        pass


if __name__ == "__main__":
    main() 