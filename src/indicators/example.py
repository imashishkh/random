"""
Example usage of the indicator calculation and stream processor.
"""

import os
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import asyncio

from .calculator import IndicatorCalculator
from .stream_processor import IndicatorStreamProcessor
from ..cache.redis_client import RedisClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_sample_market_data(symbol='EUR/USD', timeframe='1h', periods=100):
    """
    Generate sample OHLCV market data for demonstration.
    
    Args:
        symbol: Market symbol
        timeframe: Timeframe
        periods: Number of periods to generate
        
    Returns:
        DataFrame with market data
    """
    # Generate date range
    if timeframe.endswith('m'):
        minutes = int(timeframe[:-1])
        end = datetime.now().replace(second=0, microsecond=0)
        start = end - timedelta(minutes=minutes * periods)
        date_range = pd.date_range(start=start, end=end, freq=f'{minutes}min')
    elif timeframe.endswith('h'):
        hours = int(timeframe[:-1])
        end = datetime.now().replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(hours=hours * periods)
        date_range = pd.date_range(start=start, end=end, freq=f'{hours}H')
    else:
        days = int(timeframe[:-1])
        end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=days * periods)
        date_range = pd.date_range(start=start, end=end, freq=f'{days}D')
    
    # Generate random price data
    seed = sum(ord(c) for c in symbol)  # Generate seed from symbol
    np.random.seed(seed)
    
    # Start with a base price
    base_price = 1.0 if symbol.startswith('EUR') else (0.8 if symbol.startswith('GBP') else 110.0)
    
    # Generate price with random walk
    close = np.random.normal(0, 0.001, size=len(date_range)).cumsum() + base_price
    
    # Generate OHLCV
    high = close + np.random.uniform(0.0005, 0.003, size=len(date_range))
    low = close - np.random.uniform(0.0005, 0.003, size=len(date_range))
    open_price = np.roll(close, 1)
    open_price[0] = base_price
    volume = np.random.uniform(50, 200, size=len(date_range)) * 1000
    
    # Create DataFrame
    df = pd.DataFrame({
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    }, index=date_range)
    
    # Add symbol and timeframe as attributes
    df.symbol = symbol
    df.timeframe = timeframe
    
    return df

def calculate_indicators_example():
    """Example of calculating technical indicators using the calculator."""
    try:
        logger.info("Running indicator calculation example")
        
        # Generate sample market data
        data = generate_sample_market_data(symbol='EUR/USD', timeframe='1h', periods=500)
        logger.info(f"Generated sample data: {len(data)} periods for EUR/USD 1h")
        
        # Initialize Redis client and calculator
        redis_client = RedisClient()
        calculator = IndicatorCalculator(redis_client=redis_client)
        
        # Calculate a single indicator
        sma_result = calculator.calculate(
            'SMA', 
            data, 
            params={'period': 14},
            metadata={'symbol': 'EUR/USD', 'timeframe': '1h'}
        )
        
        logger.info(f"SMA(14) result shape: {sma_result.shape}")
        logger.info(f"Last 5 values: {sma_result.tail(5).values}")
        
        # Calculate multiple indicators in batch
        indicators = [
            {'name': 'SMA', 'params': {'period': 50}},
            {'name': 'EMA', 'params': {'period': 14}},
            {'name': 'RSI', 'params': {'period': 14}},
            {'name': 'MACD', 'params': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9}},
            {'name': 'BBANDS', 'params': {'period': 20, 'std_dev': 2}},
        ]
        
        batch_results = calculator.batch_calculate(indicators, data)
        
        # Print results
        for name, result in batch_results.items():
            if isinstance(result, pd.Series):
                logger.info(f"{name} result shape: {result.shape}")
                logger.info(f"Last value: {result.iloc[-1]}")
            else:
                logger.info(f"{name} result components: {result.keys()}")
                for component, series in result.items():
                    logger.info(f"{name}.{component} last value: {series.iloc[-1]}")
        
        logger.info("Indicator calculation example completed successfully")
        return batch_results
        
    except Exception as e:
        logger.exception(f"Error in indicator calculation example: {e}")
        return None

async def stream_processor_example():
    """Example of using the indicator stream processor for real-time calculations."""
    try:
        logger.info("Running indicator stream processor example")
        
        # Initialize Redis client and calculator
        redis_client = RedisClient()
        calculator = IndicatorCalculator(redis_client=redis_client)
        
        # Initialize stream processor
        processor = IndicatorStreamProcessor(calculator, redis_client)
        
        # Start the processor
        processor_task = asyncio.create_task(processor.start_processing())
        
        # Define callback function for indicator updates
        def on_indicator_update(symbol, timeframe, indicator, result):
            if isinstance(result, pd.Series):
                logger.info(f"Update: {indicator} for {symbol} {timeframe}: {result.iloc[-1]}")
            else:
                for component, series in result.items():
                    logger.info(f"Update: {indicator}.{component} for {symbol} {timeframe}: {series.iloc[-1]}")
        
        # Subscribe to indicators
        processor.subscribe('EUR/USD', '1h', 'RSI', params={'period': 14}, callback=on_indicator_update)
        processor.subscribe('EUR/USD', '1h', 'BBANDS', params={'period': 20, 'std_dev': 2}, callback=on_indicator_update)
        
        # Generate initial data
        initial_data = generate_sample_market_data('EUR/USD', '1h', 100)
        
        # Process the initial data
        processor.process_market_data('EUR/USD', '1h', initial_data)
        
        # Simulate incoming market data
        for i in range(5):
            # Wait a bit
            await asyncio.sleep(1)
            
            # Generate new candle
            new_timestamp = initial_data.index[-1] + timedelta(hours=1)
            last_close = initial_data['close'].iloc[-1]
            
            # Random price movement
            close = last_close + np.random.normal(0, 0.001)
            high = close + np.random.uniform(0.0005, 0.002)
            low = close - np.random.uniform(0.0005, 0.002)
            open_price = last_close
            volume = np.random.uniform(50, 150) * 1000
            
            # Create new data
            new_data = pd.DataFrame({
                'open': [open_price],
                'high': [high],
                'low': [low],
                'close': [close],
                'volume': [volume]
            }, index=[new_timestamp])
            
            # Add symbol and timeframe as attributes
            new_data.symbol = 'EUR/USD'
            new_data.timeframe = '1h'
            
            logger.info(f"Processing new market data for EUR/USD 1h at {new_timestamp}")
            
            # Process the new data
            processor.process_market_data('EUR/USD', '1h', new_data)
            
            # Update our initial data for the next iteration
            initial_data = pd.concat([initial_data, new_data])
        
        # Clean up
        processor.stop_processing()
        processor_task.cancel()
        try:
            await processor_task
        except asyncio.CancelledError:
            pass
        
        logger.info("Stream processor example completed successfully")
        
    except Exception as e:
        logger.exception(f"Error in stream processor example: {e}")
    
    return True

async def main():
    """Run the examples."""
    # Run the calculator example
    calculate_indicators_example()
    
    # Run the stream processor example
    await stream_processor_example()

if __name__ == "__main__":
    # Run the examples
    asyncio.run(main()) 