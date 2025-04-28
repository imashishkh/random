"""
Basic usage example for the DataManager.

This script demonstrates how to use the DataManager to fetch
and preprocess market data for multiple trading pairs.
"""

import asyncio
import os
import logging
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

import pandas as pd

from . import DataManager


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def basic_market_data_example():
    """
    Demonstrate fetching and processing OHLCV data for a single symbol.
    """
    # Create a DataManager instance
    data_manager = DataManager(
        default_source_type='ccxt',
        default_exchange='binance',
        use_fallbacks=True
    )
    
    try:
        # Fetch market data for BTC/USDT
        symbol = 'BTC/USDT'
        timeframe = '1h'
        limit = 100
        since = datetime.now() - timedelta(days=7)
        
        logger.info(f"Fetching {timeframe} data for {symbol} since {since}")
        df = await data_manager.get_market_data(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            since=since,
            preprocess=True
        )
        
        # Display data info
        logger.info(f"Fetched {len(df)} candles for {symbol}")
        logger.info(f"Columns: {df.columns.tolist()}")
        logger.info(f"Date range: {df.index.min()} to {df.index.max()}")
        
        # Display the first few rows
        print("\nSample data:")
        print(df.head())
        
        # Plot closing price and some indicators
        plt.figure(figsize=(12, 8))
        
        # Plot price
        ax1 = plt.subplot(211)
        ax1.set_title(f"{symbol} - {timeframe}")
        df['close'].plot(ax=ax1, label='Close Price')
        
        # Plot indicators if available
        if 'sma_20' in df.columns:
            df['sma_20'].plot(ax=ax1, label='SMA 20', linestyle='--')
        if 'ema_50' in df.columns:
            df['ema_50'].plot(ax=ax1, label='EMA 50', linestyle='-.')
        
        ax1.legend()
        ax1.grid(True)
        
        # Plot RSI if available
        if 'rsi_14' in df.columns:
            ax2 = plt.subplot(212, sharex=ax1)
            df['rsi_14'].plot(ax=ax2, label='RSI 14', color='purple')
            ax2.axhline(y=70, color='r', linestyle='--', alpha=0.5)
            ax2.axhline(y=30, color='g', linestyle='--', alpha=0.5)
            ax2.set_ylim(0, 100)
            ax2.legend()
            ax2.grid(True)
        
        plt.tight_layout()
        plt.savefig('market_data_example.png')
        logger.info("Saved plot to market_data_example.png")
        
    except Exception as e:
        logger.error(f"Error in market data example: {e}")
    finally:
        await data_manager.close()


async def multi_symbol_comparison_example():
    """
    Demonstrate fetching and comparing data across multiple symbols.
    """
    # Create a DataManager instance
    data_manager = DataManager(
        default_source_type='ccxt',
        default_exchange='binance',
        use_fallbacks=True
    )
    
    try:
        # Define symbols and parameters
        symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'ADA/USDT']
        timeframe = '1d'
        limit = 30
        since = datetime.now() - timedelta(days=30)
        
        logger.info(f"Fetching {timeframe} data for multiple symbols since {since}")
        
        # Fetch data for all symbols in parallel
        symbol_data = await data_manager.get_multi_symbol_data(
            symbols=symbols,
            timeframe=timeframe,
            limit=limit,
            since=since,
            preprocess=True
        )
        
        # Process results
        logger.info(f"Successfully fetched data for {len(symbol_data)} symbols")
        
        # Prepare comparison DataFrame
        comparison_df = pd.DataFrame()
        
        for symbol, df in symbol_data.items():
            if df.empty:
                logger.warning(f"No data available for {symbol}")
                continue
                
            # Calculate percentage change from first close price
            symbol_name = symbol.split('/')[0]
            close_prices = df['close']
            normalized = close_prices / close_prices.iloc[0]
            comparison_df[symbol_name] = normalized
        
        # Plot comparison
        plt.figure(figsize=(12, 6))
        comparison_df.plot(figsize=(12, 6))
        plt.title(f"30-Day Price Comparison (Normalized)")
        plt.ylabel("Normalized Price")
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.savefig('multi_symbol_comparison.png')
        logger.info("Saved comparison plot to multi_symbol_comparison.png")
        
    except Exception as e:
        logger.error(f"Error in multi-symbol comparison example: {e}")
    finally:
        await data_manager.close()


async def caching_example():
    """
    Demonstrate caching features of the DataManager.
    """
    # Create a DataManager instance
    data_manager = DataManager(
        default_source_type='ccxt',
        default_exchange='binance',
        default_cache_ttl=60,  # Short TTL for testing
        use_fallbacks=True
    )
    
    try:
        symbol = 'ETH/USDT'
        timeframe = '15m'
        limit = 50
        
        # First fetch - should hit the API
        logger.info(f"First fetch for {symbol} - should hit the API")
        start_time = datetime.now()
        df1 = await data_manager.get_market_data(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            use_cache=True
        )
        elapsed1 = (datetime.now() - start_time).total_seconds()
        logger.info(f"First fetch completed in {elapsed1:.2f} seconds")
        
        # Second fetch - should hit the cache
        logger.info(f"Second fetch for {symbol} - should hit the cache")
        start_time = datetime.now()
        df2 = await data_manager.get_market_data(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            use_cache=True
        )
        elapsed2 = (datetime.now() - start_time).total_seconds()
        logger.info(f"Second fetch completed in {elapsed2:.2f} seconds")
        
        # Clear cache
        logger.info("Clearing cache")
        data_manager.clear_cache()
        
        # Third fetch - should hit the API again
        logger.info(f"Third fetch for {symbol} after cache clear - should hit the API")
        start_time = datetime.now()
        df3 = await data_manager.get_market_data(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            use_cache=True
        )
        elapsed3 = (datetime.now() - start_time).total_seconds()
        logger.info(f"Third fetch completed in {elapsed3:.2f} seconds")
        
        # Summary
        logger.info(f"Fetch times: First: {elapsed1:.2f}s, Second (cached): {elapsed2:.2f}s, Third (after clear): {elapsed3:.2f}s")
        
    except Exception as e:
        logger.error(f"Error in caching example: {e}")
    finally:
        await data_manager.close()


async def main():
    """Run all example functions."""
    logger.info("Starting DataManager examples")
    
    # Example 1: Basic market data
    logger.info("\n=== Example 1: Basic Market Data ===")
    await basic_market_data_example()
    
    # Example 2: Multi-symbol comparison
    logger.info("\n=== Example 2: Multi-Symbol Comparison ===")
    await multi_symbol_comparison_example()
    
    # Example 3: Caching functionality
    logger.info("\n=== Example 3: Caching Functionality ===")
    await caching_example()
    
    logger.info("All examples completed")


if __name__ == "__main__":
    # Ensure directory exists
    os.makedirs('src/data_manager/examples', exist_ok=True)
    
    # Run the async examples
    asyncio.run(main()) 