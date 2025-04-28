"""
Strategy Engine Usage Example

This example demonstrates how to use the strategy engine with the Moving Average Crossover strategy.
"""

import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add parent directory to sys.path to allow importing from src
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ..strategies import StrategyEngine, strategy_factory
from ..strategies.moving_average_crossover import MovingAverageCrossover


def generate_sample_data(symbol: str = 'BTCUSDT', days: int = 90) -> pd.DataFrame:
    """Generate sample price data for testing."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Generate dates
    dates = pd.date_range(start=start_date, end=end_date, freq='1h')
    n = len(dates)
    
    # Generate price data with realistic patterns
    np.random.seed(42)  # For reproducibility
    
    # Start with a random price around 30000 for BTC
    price = 30000.0
    prices = [price]
    
    # Generate subsequent prices with random walk + trends + cycles
    for i in range(1, n):
        # Random component (random walk)
        random_change = np.random.normal(0, 50.0)
        
        # Trend component (slowly rising)
        trend = 5.0 * np.sin(i / n * np.pi)
        
        # Cyclic component (multiple cycles)
        cycle1 = 200.0 * np.sin(i / 24 * np.pi)  # Daily cycle
        cycle2 = 500.0 * np.sin(i / (24 * 7) * np.pi)  # Weekly cycle
        
        # Combine components
        price += random_change + trend + cycle1 + cycle2
        prices.append(max(price, 100.0))  # Ensure price doesn't go too low
    
    # Create dataframe with OHLCV data
    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * (1 + np.random.uniform(0, 0.01)) for p in prices],
        'low': [p * (1 - np.random.uniform(0, 0.01)) for p in prices],
        'close': prices,
        'volume': [np.random.uniform(100, 1000) for _ in range(n)],
        'symbol': symbol
    })
    
    df.set_index('timestamp', inplace=True)
    return df


def main():
    """Main example function demonstrating the strategy engine."""
    logging.info("Starting strategy engine example")
    
    # Register the MovingAverageCrossover strategy
    strategy_factory.register_strategy(MovingAverageCrossover)
    
    # Create a strategy engine
    engine = StrategyEngine(max_workers=2)
    
    # Create strategy instances with different parameters
    engine.register_strategy_class(MovingAverageCrossover, "MA_Crossover")
    
    # Create strategies with different parameters
    engine.create_strategy(
        strategy_name="MA_Crossover",
        instance_name="FastMA",
        params={
            'fast_period': 5,
            'slow_period': 20,
            'ma_type': 'ema',
            'signal_threshold': 0.0
        }
    )
    
    engine.create_strategy(
        strategy_name="MA_Crossover",
        instance_name="SlowMA",
        params={
            'fast_period': 20,
            'slow_period': 50,
            'ma_type': 'sma',
            'signal_threshold': 0.0
        }
    )
    
    # Initialize strategies
    engine.initialize_all_strategies()
    
    # Generate sample data
    btc_data = generate_sample_data(symbol='BTCUSDT', days=60)
    eth_data = generate_sample_data(symbol='ETHUSDT', days=60)
    
    # Combine data
    all_data = pd.concat([btc_data, eth_data])
    
    # Prepare data dictionary (same data for both strategies in this example)
    data_dict = {
        'FastMA': all_data,
        'SlowMA': all_data
    }
    
    # Run analysis
    analysis_results = engine.analyze_all_strategies(data_dict)
    
    # Generate signals
    signals_by_strategy = engine.generate_signals_from_all_strategies(data_dict)
    
    # Aggregate signals with custom weights
    weights = {'FastMA': 0.7, 'SlowMA': 0.3}  # Give more weight to the fast MA strategy
    aggregated_signals = engine.aggregate_signals(signals_by_strategy, weights)
    
    # Print analysis results
    logging.info("Analysis Results:")
    for strategy_name, results in analysis_results.items():
        logging.info(f"Strategy: {strategy_name}")
        for symbol, symbol_results in results.items():
            if 'error' not in symbol_results:
                logging.info(f"  Symbol: {symbol}")
                logging.info(f"    Last Price: {symbol_results['last_price']:.2f}")
                logging.info(f"    MA Difference: {symbol_results['ma_diff']:.2f}")
                logging.info(f"    Current Position: {symbol_results['current_position']}")
    
    # Print signals
    logging.info("\nTrading Signals:")
    for strategy_name, signals in signals_by_strategy.items():
        logging.info(f"Strategy: {strategy_name}")
        for signal in signals:
            logging.info(f"  {signal}")
    
    # Print aggregated signals
    logging.info("\nAggregated Signals:")
    for signal in aggregated_signals:
        logging.info(f"  {signal}")
        logging.info(f"  Strategies: {signal.metadata['strategies']}")
    
    # Plot data and signals for visualization
    plot_signals(btc_data, signals_by_strategy, "BTCUSDT")
    
    # Shutdown the engine
    engine.shutdown()
    logging.info("Strategy engine example completed")


def plot_signals(
    data: pd.DataFrame, 
    signals_by_strategy: dict, 
    symbol: str
):
    """Plot price data and signals."""
    symbol_data = data[data.index.isin(data.index)]
    
    plt.figure(figsize=(12, 6))
    plt.plot(symbol_data.index, symbol_data['close'], label='Price')
    
    # Plot signals for each strategy
    colors = {'FastMA': 'g', 'SlowMA': 'b'}
    markers = {
        'BUY': '^',  # Triangle up for buy
        'SELL': 'v'  # Triangle down for sell
    }
    
    for strategy_name, signals in signals_by_strategy.items():
        for signal in signals:
            if signal.symbol == symbol:
                color = colors.get(strategy_name, 'r')
                marker = markers.get(signal.signal_type.value, 'o')
                
                plt.scatter(
                    signal.timestamp, 
                    signal.price, 
                    color=color, 
                    marker=marker, 
                    s=100, 
                    label=f"{strategy_name} {signal.signal_type.value}"
                )
    
    plt.title(f"{symbol} Price and Signals")
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.legend()
    plt.grid(True)
    
    # Save to file
    os.makedirs('output', exist_ok=True)
    plt.savefig(f"output/{symbol}_signals.png")
    plt.close()
    
    logging.info(f"Plot saved to output/{symbol}_signals.png")


if __name__ == "__main__":
    main() 