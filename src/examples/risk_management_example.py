"""
Risk Management System Example

This example demonstrates how to use the risk management system with different
position sizing algorithms.
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

from ..risk import (
    RiskManager,
    FixedPercentagePositionSizer,
    KellyPositionSizer,
    VolatilityAdjustedPositionSizer
)

from ..strategies.moving_average_crossover import MovingAverageCrossover
from ..strategies import strategy_factory, SignalType


def generate_sample_data(symbol: str = 'EURUSD', days: int = 90) -> pd.DataFrame:
    """Generate sample price data for testing."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Generate dates
    dates = pd.date_range(start=start_date, end=end_date, freq='1h')
    n = len(dates)
    
    # Generate price data with realistic patterns
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


def demo_fixed_percentage_sizing():
    """Demonstrate fixed percentage position sizing."""
    logging.info("\n=== Fixed Percentage Position Sizing ===")
    
    # Create risk manager
    risk_manager = RiskManager(account_balance=10000.0, params={
        'max_risk_per_trade': 0.02,  # 2% risk per trade
        'default_position_sizer': 'fixed_percentage'
    })
    
    # Generate sample data
    eurusd_data = generate_sample_data(symbol='EURUSD', days=30)
    
    # Calculate position size with different stop losses
    for stop_loss_pips in [10, 20, 50]:
        position_result = risk_manager.calculate_position_size(
            symbol='EURUSD',
            market_data=eurusd_data,
            risk_params={
                'risk_per_trade': 0.02,  # 2% risk
                'stop_loss_pips': stop_loss_pips,
                'take_profit_pips': stop_loss_pips * 2,  # 1:2 risk-reward
                'pip_value': 0.0001
            },
            signal_metadata={
                'signal_type': 'BUY',
                'price': eurusd_data['close'].iloc[-1]
            }
        )
        
        logging.info(f"Stop Loss: {stop_loss_pips} pips")
        logging.info(f"Position Size: {position_result['size']:.2f} units")
        logging.info(f"Position Value: ${position_result['value']:.2f}")
        logging.info(f"Risk Amount: ${position_result['risk_amount']:.2f}")
        logging.info(f"Risk Percentage: {position_result['risk_percent']:.2%}")
        logging.info(f"Entry Price: {position_result['entry_price']:.5f}")
        logging.info(f"Stop Loss Price: {position_result['stop_loss']:.5f}")
        logging.info(f"Take Profit Price: {position_result['take_profit']:.5f}")
        logging.info("")
    
    # Add the position to the risk manager
    risk_manager.add_position(
        symbol='EURUSD',
        position_result=position_result,
        asset_class='forex'
    )
    
    # Print exposure summary
    exposure_summary = risk_manager.get_exposure_summary()
    logging.info("Exposure Summary:")
    logging.info(f"Total Exposure: ${exposure_summary['total_exposure']:.2f} ({exposure_summary['total_exposure_percent']:.2%})")
    logging.info(f"Asset Exposure (EURUSD): ${exposure_summary['asset_exposure']['EURUSD']:.2f}")
    logging.info(f"Asset Class Exposure (forex): ${exposure_summary['class_exposure']['forex']:.2f}")
    logging.info(f"Total Risk: ${exposure_summary['total_risk']:.2f} ({exposure_summary['total_risk_percent']:.2%})")


def demo_kelly_position_sizing():
    """Demonstrate Kelly Criterion position sizing."""
    logging.info("\n=== Kelly Criterion Position Sizing ===")
    
    # Create risk manager with Kelly position sizer
    risk_manager = RiskManager(account_balance=10000.0)
    
    # Generate sample data
    gbpusd_data = generate_sample_data(symbol='GBPUSD', days=30)
    
    # Calculate position size with different win rates
    for win_rate in [0.4, 0.5, 0.6]:
        position_result = risk_manager.calculate_position_size(
            symbol='GBPUSD',
            market_data=gbpusd_data,
            risk_params={
                'win_rate': win_rate,
                'reward_risk_ratio': 2.0,  # 1:2 risk-reward
                'kelly_fraction': 0.5,  # Half Kelly (more conservative)
                'stop_loss_pips': 30,
                'take_profit_pips': 60,
                'pip_value': 0.0001
            },
            position_sizer_name='kelly',
            signal_metadata={
                'signal_type': 'BUY',
                'price': gbpusd_data['close'].iloc[-1]
            }
        )
        
        logging.info(f"Win Rate: {win_rate:.2f}")
        logging.info(f"Kelly Percentage: {position_result['metadata']['kelly_percentage']:.2%}")
        logging.info(f"Position Size: {position_result['size']:.2f} units")
        logging.info(f"Position Value: ${position_result['value']:.2f}")
        logging.info(f"Risk Amount: ${position_result['risk_amount']:.2f}")
        logging.info(f"Risk Percentage: {position_result['risk_percent']:.2%}")
        logging.info("")
    
    # Add the position to the risk manager
    risk_manager.add_position(
        symbol='GBPUSD',
        position_result=position_result,
        asset_class='forex'
    )


def demo_volatility_adjusted_sizing():
    """Demonstrate volatility-adjusted position sizing."""
    logging.info("\n=== Volatility-Adjusted Position Sizing ===")
    
    # Create risk manager
    risk_manager = RiskManager(account_balance=10000.0)
    
    # Generate sample data with different volatility
    low_vol_data = generate_sample_data(symbol='EURUSD', days=30)
    
    # Create high volatility data by amplifying the price movements
    high_vol_data = low_vol_data.copy()
    high_vol_data['high'] = high_vol_data['close'] * (1 + np.random.uniform(0, 0.003, len(high_vol_data)))
    high_vol_data['low'] = high_vol_data['close'] * (1 - np.random.uniform(0, 0.003, len(high_vol_data)))
    
    # Calculate position size for both datasets
    for data, label in [(low_vol_data, "Low Volatility"), (high_vol_data, "High Volatility")]:
        position_result = risk_manager.calculate_position_size(
            symbol='EURUSD',
            market_data=data,
            risk_params={
                'base_risk_percentage': 0.02,  # 2% base risk
                'volatility_metric': 'atr',
                'atr_period': 14,
                'volatility_lookback': 100,
                'volatility_adjustment_factor': 1.0,
                'stop_loss_pips': None,  # Will use ATR-based stop
                'pip_value': 0.0001
            },
            position_sizer_name='volatility_adjusted',
            signal_metadata={
                'signal_type': 'BUY',
                'price': data['close'].iloc[-1]
            }
        )
        
        logging.info(f"=== {label} ===")
        logging.info(f"Current Volatility (ATR): {position_result['metadata']['current_volatility']:.5f}")
        logging.info(f"Reference Volatility: {position_result['metadata']['reference_volatility']:.5f}")
        logging.info(f"Volatility Ratio: {position_result['metadata']['volatility_ratio']:.2f}")
        logging.info(f"Adjusted Risk Percentage: {position_result['metadata']['adjusted_risk_percentage']:.2%}")
        logging.info(f"Position Size: {position_result['size']:.2f} units")
        logging.info(f"Position Value: ${position_result['value']:.2f}")
        logging.info(f"Risk Amount: ${position_result['risk_amount']:.2f}")
        logging.info(f"Risk Percentage: {position_result['risk_percent']:.2%}")
        logging.info(f"Stop Loss Distance: {position_result['metadata']['stop_loss_pips']:.2f} pips")
        logging.info("")


def demo_risk_limits():
    """Demonstrate risk limits enforcement."""
    logging.info("\n=== Risk Limits Enforcement ===")
    
    # Create risk manager with strict limits
    risk_manager = RiskManager(
        account_balance=10000.0,
        params={
            'max_risk_per_trade': 0.02,     # 2% max risk per trade
            'max_asset_exposure': 0.05,     # 5% max exposure per asset
            'max_class_exposure': 0.15,     # 15% max exposure per asset class
            'max_total_exposure': 0.30,     # 30% max total exposure
            'default_position_sizer': 'fixed_percentage'
        }
    )
    
    # Generate sample data
    eurusd_data = generate_sample_data(symbol='EURUSD', days=30)
    gbpusd_data = generate_sample_data(symbol='GBPUSD', days=30)
    usdjpy_data = generate_sample_data(symbol='USDJPY', days=30)
    
    # Add first position (should be accepted as is)
    position1 = risk_manager.calculate_position_size(
        symbol='EURUSD',
        market_data=eurusd_data,
        risk_params={
            'risk_per_trade': 0.02,
            'stop_loss_pips': 20,
            'pip_value': 0.0001
        },
        signal_metadata={'signal_type': 'BUY'}
    )
    
    risk_manager.add_position(symbol='EURUSD', position_result=position1, asset_class='forex')
    logging.info(f"Added EURUSD position: ${position1['value']:.2f}")
    
    # Add second position (should be accepted as is)
    position2 = risk_manager.calculate_position_size(
        symbol='GBPUSD',
        market_data=gbpusd_data,
        risk_params={
            'risk_per_trade': 0.02,
            'stop_loss_pips': 25,
            'pip_value': 0.0001
        },
        signal_metadata={'signal_type': 'BUY'}
    )
    
    risk_manager.add_position(symbol='GBPUSD', position_result=position2, asset_class='forex')
    logging.info(f"Added GBPUSD position: ${position2['value']:.2f}")
    
    # Add third position (should be scaled down due to asset class limit)
    position3 = risk_manager.calculate_position_size(
        symbol='USDJPY',
        market_data=usdjpy_data,
        risk_params={
            'risk_per_trade': 0.02,
            'stop_loss_pips': 30,
            'pip_value': 0.0001
        },
        signal_metadata={'signal_type': 'BUY'}
    )
    
    risk_manager.add_position(symbol='USDJPY', position_result=position3, asset_class='forex')
    logging.info(f"Added USDJPY position: ${position3['value']:.2f}")
    
    # Print exposure summary
    exposure_summary = risk_manager.get_exposure_summary()
    logging.info("\nExposure Summary After All Positions:")
    logging.info(f"Total Exposure: ${exposure_summary['total_exposure']:.2f} ({exposure_summary['total_exposure_percent']:.2%})")
    for symbol, exposure in exposure_summary['asset_exposure'].items():
        logging.info(f"Asset Exposure ({symbol}): ${exposure:.2f}")
    logging.info(f"Asset Class Exposure (forex): ${exposure_summary['class_exposure']['forex']:.2f} " + 
                 f"({exposure_summary['class_exposure_percent']['forex']:.2%})")
    logging.info(f"Total Risk: ${exposure_summary['total_risk']:.2f} ({exposure_summary['total_risk_percent']:.2%})")
    
    # Check for risk warnings
    warnings = risk_manager.detect_risk_warnings()
    if warnings:
        logging.info("\nRisk Warnings:")
        for warning in warnings:
            logging.info(f"[{warning['level'].upper()}] {warning['message']}")


def demo_integration_with_strategy():
    """Demonstrate integration with strategy system."""
    logging.info("\n=== Integration with Strategy System ===")
    
    # Create risk manager
    risk_manager = RiskManager(account_balance=10000.0)
    
    # Generate sample data
    eurusd_data = generate_sample_data(symbol='EURUSD', days=90)
    
    # Create a moving average crossover strategy
    strategy = MovingAverageCrossover(
        name="MA_Crossover",
        params={
            'fast_period': 10,
            'slow_period': 30,
            'ma_type': 'ema',
            'signal_threshold': 0.0
        }
    )
    
    # Initialize the strategy
    strategy.initialize()
    
    # Generate signals
    signals = strategy.generate_signals(eurusd_data)
    
    # Process each signal
    for signal in signals:
        logging.info(f"\nProcessing {signal.signal_type.value} signal for {signal.symbol} @ {signal.price:.5f}")
        
        # Only process BUY and SELL signals
        if signal.signal_type not in [SignalType.BUY, SignalType.SELL]:
            logging.info(f"Skipping {signal.signal_type.value} signal")
            continue
        
        # Calculate position size
        position_result = risk_manager.calculate_position_size(
            symbol=signal.symbol,
            market_data=eurusd_data,
            risk_params={
                'risk_per_trade': 0.02 * signal.strength,  # Scale risk by signal strength
                'stop_loss_pips': 30,
                'take_profit_pips': 60,
                'pip_value': 0.0001
            },
            position_sizer_name='volatility_adjusted',
            signal_metadata={
                'signal_type': signal.signal_type.value,
                'price': signal.price,
                'timestamp': signal.timestamp,
                'strength': signal.strength
            }
        )
        
        logging.info(f"Signal Strength: {signal.strength:.2f}")
        logging.info(f"Position Size: {position_result['size']:.2f} units")
        logging.info(f"Position Value: ${position_result['value']:.2f}")
        logging.info(f"Risk Amount: ${position_result['risk_amount']:.2f}")
        logging.info(f"Risk Percentage: {position_result['risk_percent']:.2%}")
        logging.info(f"Entry Price: {position_result['entry_price']:.5f}")
        logging.info(f"Stop Loss: {position_result['stop_loss']:.5f}")
        logging.info(f"Take Profit: {position_result['take_profit']:.5f}")
        
        # Add the position to the risk manager
        risk_manager.add_position(
            symbol=signal.symbol,
            position_result=position_result,
            asset_class='forex'
        )


def main():
    """Run all risk management demonstrations."""
    logging.info("Starting risk management examples")
    
    # Run each demonstration
    demo_fixed_percentage_sizing()
    demo_kelly_position_sizing()
    demo_volatility_adjusted_sizing()
    demo_risk_limits()
    demo_integration_with_strategy()
    
    logging.info("\nRisk management examples completed")


if __name__ == "__main__":
    main() 