"""
Example usage of the Technical Analysis Agent Framework.

This script demonstrates how to use the different components of the
Technical Analysis Agent Framework to analyze market data and generate signals.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, List, Any
import os
from datetime import datetime, timedelta

from .technical_analysis.data_provider import DataProvider
from .technical_analysis.factory import TechnicalAnalysisAgentFactory


def plot_signals(data: pd.DataFrame, signals: List[Dict[str, Any]], title: str):
    """
    Plot price data with trading signals.
    
    Args:
        data: DataFrame with OHLCV data
        signals: List of signal dictionaries
        title: Title for the plot
    """
    plt.figure(figsize=(12, 6))
    
    # Plot price
    plt.plot(data.index, data['close'], label='Close Price')
    
    # Plot buy signals
    buy_signals = [s for s in signals if s['type'] == 'buy']
    if buy_signals:
        buy_x = [s['timestamp'] for s in buy_signals]
        buy_y = [data.loc[s['timestamp'], 'close'] for s in buy_signals]
        plt.scatter(buy_x, buy_y, marker='^', color='green', s=100, label='Buy Signal')
    
    # Plot sell signals
    sell_signals = [s for s in signals if s['type'] == 'sell']
    if sell_signals:
        sell_x = [s['timestamp'] for s in sell_signals]
        sell_y = [data.loc[s['timestamp'], 'close'] for s in sell_signals]
        plt.scatter(sell_x, sell_y, marker='v', color='red', s=100, label='Sell Signal')
    
    plt.title(title)
    plt.xlabel('Date')
    plt.ylabel('Price')
    plt.legend()
    plt.grid(True)
    
    # Create directory if not exists
    os.makedirs('outputs', exist_ok=True)
    
    # Save the plot
    filename = f"outputs/{title.replace(' ', '_').lower()}.png"
    plt.savefig(filename)
    print(f"Plot saved to {filename}")
    
    plt.close()


def main():
    print("Technical Analysis Agent Framework Example")
    print("=========================================")
    
    # 1. Create a data provider for EUR/USD
    print("\n1. Creating data provider for EUR/USD...")
    data_provider = DataProvider(symbol="EUR/USD", timeframe="1h")
    
    # 2. Fetch sample data
    print("2. Fetching sample data...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    data = data_provider.fetch_data(
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d')
    )
    print(f"   Fetched {len(data)} data points")
    
    # 3. Create different types of agents
    print("\n3. Creating technical analysis agents...")
    
    # Momentum Agent (RSI-based)
    momentum_agent = TechnicalAnalysisAgentFactory.create_custom_rsi_agent(
        period=14,
        overbought=70,
        oversold=30,
        name="RSI-Agent"
    )
    print(f"   Created {momentum_agent.name}")
    
    # Volatility Agent (Bollinger Bands-based)
    volatility_agent = TechnicalAnalysisAgentFactory.create_custom_bollinger_agent(
        period=20,
        std_dev=2.0,
        name="Bollinger-Agent"
    )
    print(f"   Created {volatility_agent.name}")
    
    # Trend Agent (Moving Average-based)
    trend_agent = TechnicalAnalysisAgentFactory.create_custom_moving_average_agent(
        short_period=20,
        medium_period=50,
        long_period=200,
        name="MA-Agent"
    )
    print(f"   Created {trend_agent.name}")
    
    # Combined Agent
    combined_agent = TechnicalAnalysisAgentFactory.create_combined_agent(
        name="Combined-Agent"
    )
    print(f"   Created {combined_agent.name}")
    
    # 4. Generate signals with each agent
    print("\n4. Generating trading signals...")
    
    # Momentum signals
    momentum_signals = momentum_agent.generate_signals(data)
    print(f"   {momentum_agent.name} generated {len(momentum_signals)} signals")
    
    # Volatility signals
    volatility_signals = volatility_agent.generate_signals(data)
    print(f"   {volatility_agent.name} generated {len(volatility_signals)} signals")
    
    # Trend signals
    trend_signals = trend_agent.generate_signals(data)
    print(f"   {trend_agent.name} generated {len(trend_signals)} signals")
    
    # Combined signals
    combined_signals = combined_agent.generate_signals(data)
    print(f"   {combined_agent.name} generated {len(combined_signals)} signals")
    
    # 5. Run backtests
    print("\n5. Running backtests...")
    
    momentum_results = momentum_agent.backtest(data)
    print(f"   {momentum_agent.name} backtest results:")
    print(f"     - Win rate: {momentum_results['win_rate']:.2%}")
    print(f"     - Avg profit: {momentum_results['avg_profit']:.2f}%")
    print(f"     - Total signals: {momentum_results['total_signals']}")
    
    volatility_results = volatility_agent.backtest(data)
    print(f"   {volatility_agent.name} backtest results:")
    print(f"     - Win rate: {volatility_results['win_rate']:.2%}")
    print(f"     - Avg profit: {volatility_results['avg_profit']:.2f}%")
    print(f"     - Total signals: {volatility_results['total_signals']}")
    
    trend_results = trend_agent.backtest(data)
    print(f"   {trend_agent.name} backtest results:")
    print(f"     - Win rate: {trend_results['win_rate']:.2%}")
    print(f"     - Avg profit: {trend_results['avg_profit']:.2f}%")
    print(f"     - Total signals: {trend_results['total_signals']}")
    
    combined_results = combined_agent.backtest(data)
    print(f"   {combined_agent.name} backtest results:")
    print(f"     - Win rate: {combined_results['win_rate']:.2%}")
    print(f"     - Avg profit: {combined_results['avg_profit']:.2f}%")
    print(f"     - Total signals: {combined_results['total_signals']}")
    
    # 6. Plot signals
    print("\n6. Plotting signals...")
    
    # Plot momentum signals
    if momentum_signals:
        plot_signals(data, momentum_signals, f"{momentum_agent.name} Signals")
    
    # Plot volatility signals
    if volatility_signals:
        plot_signals(data, volatility_signals, f"{volatility_agent.name} Signals")
    
    # Plot trend signals
    if trend_signals:
        plot_signals(data, trend_signals, f"{trend_agent.name} Signals")
    
    # Plot combined signals
    if combined_signals:
        plot_signals(data, combined_signals, f"{combined_agent.name} Signals")
    
    print("\nExample completed successfully!")


if __name__ == "__main__":
    main() 