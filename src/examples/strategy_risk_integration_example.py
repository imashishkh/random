"""
Strategy and Risk Management Integration Example

This example demonstrates how to use the StrategyRiskIntegrator class
to integrate the strategy engine with the risk management system.
"""

import logging
import pandas as pd
import os
import sys
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add parent directory to sys.path to allow importing from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ..strategies.engine import StrategyEngine
from ..strategies.moving_average_crossover import MovingAverageCrossover
from ..risk.risk_manager import RiskManager
from ..strategies.integration import StrategyRiskIntegrator


def generate_sample_data(symbol: str = 'EURUSD', days: int = 90) -> pd.DataFrame:
    """Generate sample price data for testing."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Generate dates
    dates = pd.date_range(start=start_date, end=end_date, freq='1h')
    n = len(dates)
    
    # Generate price data with realistic patterns
    import numpy as np
    np.random.seed(42)  # For reproducibility
    
    # Start with a base price
    if symbol == 'EURUSD':
        price = 1.1000  # Start with typical EURUSD rate
    elif symbol == 'GBPUSD':
        price = 1.3000  # Start with typical GBPUSD rate
    else:
        price = 1.2000  # Default starting price
        
    prices = [price]
    
    # Generate subsequent prices with random walk + trends + cycles
    for i in range(1, n):
        # Random component (random walk)
        random_change = np.random.normal(0, 0.0005)  # Small random changes for forex
        
        # Trend component (slowly rising or falling)
        trend = 0.0001 * np.sin(i / n * np.pi)
        
        # Cyclic component (multiple cycles)
        cycle1 = 0.001 * np.sin(i / 24 * np.pi)  # Daily cycle
        cycle2 = 0.002 * np.sin(i / (24 * 7) * np.pi)  # Weekly cycle
        
        # Combine components
        price += random_change + trend + cycle1 + cycle2
        prices.append(max(price, 0.5))  # Ensure price doesn't go too low
    
    # Create dataframe with OHLCV data
    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * (1 + np.random.uniform(0, 0.001)) for p in prices],  # Small range for forex
        'low': [p * (1 - np.random.uniform(0, 0.001)) for p in prices],
        'close': prices,
        'volume': [np.random.uniform(100, 1000) for _ in range(n)],
        'symbol': symbol
    })
    
    df.set_index('timestamp', inplace=True)
    return df


def simulate_order_execution(signal, **kwargs):
    """
    Simulate order execution for demonstration purposes.
    
    Args:
        signal: Processed signal from StrategyRiskIntegrator
        
    Returns:
        Dictionary with execution results
    """
    # In a real system, this would interact with a broker or exchange
    return {
        'success': True,
        'order_id': f"order_{int(datetime.now().timestamp())}",
        'executed_price': signal['entry_price'],
        'executed_size': signal['position_size'],
        'timestamp': datetime.now(),
        'commission': signal['position_value'] * 0.001,  # Simulated commission
        'slippage': 0.0,
        'message': f"Executed {signal['action']} order for {signal['symbol']}",
        'signal': signal
    }


def main():
    """
    Run the strategy and risk management integration example.
    """
    logging.info("Starting strategy and risk management integration example")
    
    # Step 1: Create and configure the strategy engine
    strategy_engine = StrategyEngine(max_workers=2)
    
    # Register the moving average crossover strategy
    strategy_engine.register_strategy_class(MovingAverageCrossover)
    
    # Create a strategy instance
    strategy = strategy_engine.create_strategy(
        strategy_name="MovingAverageCrossover",
        instance_name="MA_Crossover",
        params={
            'fast_period': 10,
            'slow_period': 30,
            'ma_type': 'ema',
            'signal_threshold': 0.0
        }
    )
    
    # Initialize the strategy
    strategy_engine.initialize_strategy("MA_Crossover")
    
    # Step 2: Create and configure the risk manager
    risk_manager = RiskManager(
        account_equity=10000.0,
        default_sizer="fixed_percent",
        default_sizer_params={"risk_percent": 1.0},
        max_portfolio_risk_percent=5.0,
        max_asset_risk_percent=2.0,
        max_correlated_risk_percent=4.0,
        max_leverage=10.0
    )
    
    # Step 3: Create the strategy-risk integrator
    integrator = StrategyRiskIntegrator(
        strategy_engine=strategy_engine,
        risk_manager=risk_manager,
        default_position_sizer="fixed_percent",
        default_risk_percent=1.0,
        default_pip_value=0.0001,
        default_stop_loss_pips=30,
        default_take_profit_pips=60
    )
    
    # Step 4: Generate sample data for multiple symbols
    data = {
        'EURUSD': generate_sample_data(symbol='EURUSD', days=90),
        'GBPUSD': generate_sample_data(symbol='GBPUSD', days=90)
    }
    
    # Step 5: Analyze data, generate signals, and process them
    processed_signals = integrator.analyze_and_process(data)
    
    # Log the processed signals
    logging.info(f"Generated {len(processed_signals)} processed signals")
    for i, signal in enumerate(processed_signals):
        logging.info(f"Signal {i+1}: {signal['action']} {signal['symbol']} @ {signal['entry_price']:.5f}")
        logging.info(f"  Position Size: {signal['position_size']:.2f} units")
        logging.info(f"  Position Value: ${signal['position_value']:.2f}")
        logging.info(f"  Risk Amount: ${signal['risk_amount']:.2f} ({signal['risk_percent']:.2%})")
        logging.info(f"  Stop Loss: {signal['stop_loss']:.5f}")
        logging.info(f"  Take Profit: {signal['take_profit']:.5f}")
    
    # Step 6: Execute the signals
    if processed_signals:
        execution_results = integrator.execute_signals(
            processed_signals,
            execute_fn=simulate_order_execution
        )
        
        # Log the execution results
        logging.info(f"Executed {len(execution_results)} signals")
        for i, result in enumerate(execution_results):
            if result['success']:
                logging.info(f"Execution {i+1}: {result['message']}")
                logging.info(f"  Order ID: {result['order_id']}")
                logging.info(f"  Executed Price: {result['executed_price']:.5f}")
                logging.info(f"  Executed Size: {result['executed_size']:.2f}")
                logging.info(f"  Commission: ${result['commission']:.2f}")
            else:
                logging.error(f"Execution {i+1} failed: {result.get('error', 'Unknown error')}")
    
    # Step 7: Get risk metrics
    risk_metrics = integrator.get_risk_metrics()
    logging.info("Current Risk Metrics:")
    logging.info(f"  Total Portfolio Risk: {risk_metrics['portfolio_risk_percent']:.2%}")
    logging.info(f"  Number of Open Positions: {len(risk_metrics['positions'])}")
    for symbol, risk in risk_metrics['asset_risk_percent'].items():
        logging.info(f"  {symbol} Risk: {risk:.2%}")
    
    # Step 8: Get signal history
    signal_history = integrator.get_signal_history()
    logging.info(f"Signal History (last {len(signal_history)} signals):")
    for i, signal in enumerate(signal_history[:5]):  # Show just the first 5
        logging.info(f"  {i+1}: {signal['action']} {signal['symbol']} @ {signal['entry_price']:.5f} - {signal['timestamp']}")
    
    logging.info("Strategy and risk management integration example completed")


if __name__ == "__main__":
    main() 