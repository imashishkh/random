#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import pandas as pd
import numpy as np
import json
from datetime import datetime
import matplotlib.pyplot as plt
import logging

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_adaptation.adaptation_strategy import AdaptationStrategy

# Create a simple regime detector for testing
class SimpleRegimeDetector:
    """A simple market regime detector for testing."""
    
    def __init__(self, num_regimes=3):
        self.num_regimes = num_regimes
        
    def detect_regime(self, market_data):
        """
        Simple detection based on volatility and trend.
        Returns a regime ID and regime properties.
        
        Regimes:
        0: High volatility/bearish
        1: Neutral/range bound
        2: Low volatility/bullish
        """
        # Calculate volatility (simple implementation for testing)
        if isinstance(market_data, pd.DataFrame):
            close_prices = market_data['close'].values
            returns = np.diff(close_prices) / close_prices[:-1]
            volatility = np.std(returns) * np.sqrt(252)  # Annualized
            
            # Calculate trend (simple implementation)
            price_change = (close_prices[-1] / close_prices[0]) - 1
            recent_momentum = close_prices[-1] > close_prices[-min(10, len(close_prices))]
            
            # Determine regime
            if volatility > 0.015 and price_change < 0:  # High volatility and bearish
                regime_id = 0
                description = "High volatility bearish regime"
                properties = {
                    "volatility": volatility,
                    "trend": price_change,
                    "description": description
                }
            elif volatility < 0.008 and price_change > 0 and recent_momentum:  # Low volatility and bullish
                regime_id = 2
                description = "Low volatility bullish regime"
                properties = {
                    "volatility": volatility,
                    "trend": price_change,
                    "description": description
                }
            else:  # Neutral/range bound
                regime_id = 1
                description = "Neutral/ranging regime"
                properties = {
                    "volatility": volatility,
                    "trend": price_change,
                    "description": description
                }
            
            return regime_id, properties
        else:
            # Default to neutral regime if data format is unexpected
            return 1, {"volatility": 0.01, "trend": 0, "description": "Default neutral regime"}


def generate_test_data(days=30, freq='1h'):
    """Generate synthetic market data for testing."""
    periods = 24 * days if freq == '1h' else days
    dates = pd.date_range(start='2023-01-01', periods=periods, freq=freq)
    
    # Generate random price data with some trend and volatility
    np.random.seed(42)  # For reproducibility
    
    # Create a more realistic price series with trend changes
    price = 100
    prices = [price]
    
    # Add some regime changes for testing
    # First 10 days - moderate uptrend (regime 2)
    # Next 10 days - high volatility downtrend (regime 0)
    # Last 10 days - ranging market (regime 1)
    
    volatilities = [0.005] * (periods // 3) + [0.02] * (periods // 3) + [0.01] * (periods - 2*(periods // 3))
    trends = [0.0002] * (periods // 3) + [-0.0003] * (periods // 3) + [0.0] * (periods - 2*(periods // 3))
    
    for i in range(1, periods):
        # Random walk with regime-specific drift and volatility
        change = trends[i-1] + volatilities[i-1] * np.random.randn()
        price = max(0.1, price * (1 + change))  # Ensure price doesn't go below 0.1
        prices.append(price)
    
    # Create DataFrame
    df = pd.DataFrame({
        'datetime': dates,
        'open': prices,
        'high': [p * (1 + 0.002 * np.random.random()) for p in prices],
        'low': [p * (1 - 0.002 * np.random.random()) for p in prices],
        'close': prices,
        'volume': [1000 * (1 + 2 * np.random.random()) for _ in range(len(prices))]
    })
    
    df.set_index('datetime', inplace=True)
    return df


def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Generate test market data
    market_data = generate_test_data(days=30, freq='1h')
    
    # Create regime detector
    regime_detector = SimpleRegimeDetector(num_regimes=3)
    
    # Create adaptation strategy
    adaptation_strategy = AdaptationStrategy(
        regime_detector=regime_detector,
        adaptation_rules=None,  # We'll load from file
        parameter_bounds={
            'position_size': (0.01, 0.5),
            'stop_loss': (0.005, 0.05),
            'take_profit': (0.01, 0.1),
            'entry_threshold': (0.5, 2.0),
            'signal_threshold': (0.5, 2.0),
            'lookback_period': (5, 50)
        }
    )
    
    # Load rules from json file
    rules_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sample_adaptation_rules.json')
    adaptation_strategy.load_rules(rules_file)
    
    # Initial strategy parameters
    initial_parameters = {
        'position_size': 0.1,
        'stop_loss': 0.02,
        'take_profit': 0.04,
        'entry_threshold': 1.0,
        'signal_threshold': 1.0,
        'lookback_period': 20
    }
    
    # Test adaptation for each day
    parameter_history = {}
    for param in initial_parameters:
        parameter_history[param] = []
    
    # Also track regimes
    regimes = []
    
    # Simulate using a sliding window approach
    window_size = 48  # 2 days of hourly data
    current_params = initial_parameters.copy()
    
    for i in range(window_size, len(market_data), 24):  # Check once per day for simplicity
        window_data = market_data.iloc[i-window_size:i]
        
        # Adapt strategy parameters based on market data
        adapted_params = adaptation_strategy.adapt_strategy(
            current_params.copy(), 
            window_data
        )
        
        # Store parameters and regime
        for param, value in adapted_params.items():
            parameter_history[param].append(value)
        
        regime_id, _ = regime_detector.detect_regime(window_data)
        regimes.append(regime_id)
        
        # Update current parameters
        current_params = adapted_params
    
    # Print summary
    print("\nAdaptation Statistics:")
    stats = adaptation_strategy.get_adaptation_stats()
    for rule_type, count in stats['adaptation_counts'].items():
        print(f"  {rule_type}: {count} adaptations")
    
    # Create DataFrame for visualization
    dates = market_data.index[window_size::24][:len(regimes)]
    params_df = pd.DataFrame(parameter_history, index=dates[:len(list(parameter_history.values())[0])])
    
    # Add regimes to DataFrame
    params_df['regime'] = regimes[:len(params_df)]
    
    # Prices for reference
    params_df['price'] = market_data.loc[params_df.index]['close'].values
    
    # Plot the results
    plt.figure(figsize=(15, 12))
    
    # Plot price
    ax1 = plt.subplot(4, 1, 1)
    ax1.plot(params_df.index, params_df['price'], label='Price', color='black')
    ax1.set_title('Price and Market Regime')
    ax1.set_ylabel('Price')
    
    # Add regime as background color
    for i, row in params_df.iterrows():
        if row['regime'] == 0:
            color = 'red'
            alpha = 0.2
        elif row['regime'] == 1:
            color = 'gray'
            alpha = 0.2
        else:
            color = 'green'
            alpha = 0.2
        
        # Add colored background for each regime period
        if i != params_df.index[-1]:
            next_idx = params_df.index[params_df.index.get_loc(i) + 1]
            ax1.axvspan(i, next_idx, alpha=alpha, color=color)
    
    # Plot position size and stop loss/take profit
    ax2 = plt.subplot(4, 1, 2, sharex=ax1)
    ax2.plot(params_df.index, params_df['position_size'], label='Position Size', marker='o')
    ax2.set_ylabel('Position Size')
    ax2.legend(loc='upper left')
    
    ax3 = plt.subplot(4, 1, 3, sharex=ax1)
    ax3.plot(params_df.index, params_df['stop_loss'], label='Stop Loss', marker='o', color='red')
    ax3.plot(params_df.index, params_df['take_profit'], label='Take Profit', marker='o', color='green')
    ax3.set_ylabel('SL/TP Levels')
    ax3.legend(loc='upper left')
    
    # Plot thresholds and lookback
    ax4 = plt.subplot(4, 1, 4, sharex=ax1)
    ax4.plot(params_df.index, params_df['entry_threshold'], label='Entry Threshold', marker='o')
    ax4.plot(params_df.index, params_df['signal_threshold'], label='Signal Threshold', marker='o')
    ax4.set_ylabel('Thresholds')
    ax4.legend(loc='upper left')
    
    plt.tight_layout()
    
    # Save plot if directory exists
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    plt.savefig(os.path.join(output_dir, 'adaptation_test_results.png'))
    print(f"Plot saved to {os.path.join(output_dir, 'adaptation_test_results.png')}")
    
    # Optionally show plot
    plt.show()


if __name__ == "__main__":
    main() 