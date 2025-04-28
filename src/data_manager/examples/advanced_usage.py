"""
Advanced Data Manager Example Script

This script demonstrates more complex usage patterns for the DataManager class, 
including advanced preprocessing, technical analysis, and multi-timeframe analysis.
"""

import os
import asyncio
import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import matplotlib.dates as mdates
from mplfinance.original_flavor import candlestick_ohlc

from .data_manager import DataManager
from ...utils.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def market_patterns_example():
    """
    Advanced example that demonstrates candlestick pattern recognition
    and visualization for Bitcoin.
    """
    logger.info("Running candlestick pattern recognition example...")
    
    try:
        # Initialize the DataManager with caching enabled
        config = Config.get_instance()
        data_manager = DataManager(
            default_source_type='ccxt',
            default_exchange=config.get('exchange', 'binance'),
            use_cache=True
        )
        
        # Fetch 100 days of daily data for BTC/USDT
        start_time = datetime.now() - timedelta(days=100)
        df = await data_manager.get_market_data(
            symbol='BTC/USDT',
            timeframe='1d',
            since=start_time,
            limit=100,
            preprocess=True  # Enable standard preprocessing
        )
        
        # Add candlestick pattern recognition
        df = await add_candlestick_patterns(df, data_manager)
        
        # Visualize the data with patterns
        visualize_candlestick_patterns(df)
        
        logger.info(f"Successfully analyzed candlestick patterns for BTC/USDT")
        return df
    
    except Exception as e:
        logger.error(f"Error in market_patterns_example: {str(e)}")
        raise


async def multi_timeframe_analysis():
    """
    Advanced example that demonstrates analyzing a single trading pair
    across multiple timeframes.
    """
    logger.info("Running multi-timeframe analysis example...")
    
    try:
        # Initialize the DataManager with caching enabled
        config = Config.get_instance()
        data_manager = DataManager(
            default_source_type='ccxt',
            default_exchange=config.get('exchange', 'binance'),
            use_cache=True
        )
        
        # Define the timeframes to analyze
        timeframes = ['5m', '15m', '1h', '4h', '1d']
        
        # Calculate appropriate start times for each timeframe
        start_times = {
            '5m': datetime.now() - timedelta(days=1),
            '15m': datetime.now() - timedelta(days=3),
            '1h': datetime.now() - timedelta(days=7),
            '4h': datetime.now() - timedelta(days=30),
            '1d': datetime.now() - timedelta(days=100)
        }
        
        # Fetch data for each timeframe
        results = {}
        for tf in timeframes:
            results[tf] = await data_manager.get_market_data(
                symbol='ETH/USDT',
                timeframe=tf,
                since=start_times[tf],
                limit=100,
                preprocess=True
            )
            
            # Calculate additional indicators for each timeframe
            results[tf] = calculate_advanced_indicators(results[tf])
            
            logger.info(f"Fetched and processed ETH/USDT data for {tf} timeframe")
        
        # Visualize multi-timeframe analysis
        plot_multi_timeframe(results, 'ETH/USDT')
        
        logger.info("Successfully completed multi-timeframe analysis")
        return results
    
    except Exception as e:
        logger.error(f"Error in multi_timeframe_analysis: {str(e)}")
        raise


async def correlation_matrix_example():
    """
    Advanced example that creates a correlation matrix for top cryptocurrencies.
    """
    logger.info("Running correlation matrix example...")
    
    try:
        # Initialize the DataManager with caching enabled
        config = Config.get_instance()
        data_manager = DataManager(
            default_source_type='ccxt',
            default_exchange=config.get('exchange', 'binance'),
            use_cache=True
        )
        
        # Define the top crypto symbols to analyze
        symbols = [
            'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 
            'ADA/USDT', 'XRP/USDT', 'DOT/USDT', 'DOGE/USDT',
            'AVAX/USDT', 'MATIC/USDT'
        ]
        
        # Fetch 30 days of daily data for all symbols
        start_time = datetime.now() - timedelta(days=30)
        
        # Use the multi-symbol fetching capability
        data_dict = await data_manager.get_multi_symbol_data(
            symbols=symbols,
            timeframe='1d',
            since=start_time,
            limit=30,
            preprocess=True
        )
        
        # Create a DataFrame with just the closing prices
        price_df = pd.DataFrame()
        for symbol, df in data_dict.items():
            # Extract just the symbol name without /USDT
            symbol_name = symbol.split('/')[0]
            price_df[symbol_name] = df['close']
        
        # Calculate and visualize the correlation matrix
        create_correlation_matrix(price_df)
        
        # Calculate rolling correlation between BTC and other assets
        if 'BTC/USDT' in data_dict and len(data_dict) > 1:
            calculate_rolling_correlation(data_dict, 'BTC/USDT')
        
        logger.info("Successfully created correlation matrix")
        return price_df
    
    except Exception as e:
        logger.error(f"Error in correlation_matrix_example: {str(e)}")
        raise


async def volume_profile_example():
    """
    Advanced example that creates a volume profile analysis for a trading pair.
    """
    logger.info("Running volume profile example...")
    
    try:
        # Initialize the DataManager with caching enabled
        config = Config.get_instance()
        data_manager = DataManager(
            default_source_type='ccxt',
            default_exchange=config.get('exchange', 'binance'),
            use_cache=True
        )
        
        # Fetch 30 days of hourly data for BTC/USDT
        start_time = datetime.now() - timedelta(days=30)
        df = await data_manager.get_market_data(
            symbol='BTC/USDT',
            timeframe='1h',
            since=start_time,
            limit=30*24,  # 30 days with hourly data
            preprocess=True
        )
        
        # Create and visualize the volume profile
        create_volume_profile(df, 'BTC/USDT')
        
        logger.info("Successfully created volume profile")
        return df
    
    except Exception as e:
        logger.error(f"Error in volume_profile_example: {str(e)}")
        raise


# ===== Helper Functions =====

async def add_candlestick_patterns(df, data_manager):
    """
    Add candlestick pattern recognition to the DataFrame.
    
    Args:
        df: DataFrame with OHLCV data
        data_manager: DataManager instance
    
    Returns:
        DataFrame with candlestick pattern columns added
    """
    # These would typically come from a more sophisticated pattern detection system
    # For this example, we'll create some simple pattern detections
    
    # Doji detection (open and close are very close)
    df['doji'] = abs(df['close'] - df['open']) <= (0.1 * (df['high'] - df['low']))
    
    # Hammer detection (small body at top, long lower wick)
    df['hammer'] = (
        (abs(df['close'] - df['open']) <= 0.3 * (df['high'] - df['low'])) & 
        (min(df['close'], df['open']) - df['low'] >= 2 * abs(df['close'] - df['open'])) &
        (df['high'] - max(df['close'], df['open']) <= 0.3 * abs(df['close'] - df['open']))
    )
    
    # Bullish engulfing pattern
    df['bullish_engulfing'] = (
        (df['open'].shift(1) > df['close'].shift(1)) &  # Previous candle is red
        (df['close'] > df['open']) &  # Current candle is green
        (df['open'] <= df['close'].shift(1)) &  # Open below previous close
        (df['close'] >= df['open'].shift(1))  # Close above previous open
    )
    
    # Bearish engulfing pattern
    df['bearish_engulfing'] = (
        (df['close'].shift(1) > df['open'].shift(1)) &  # Previous candle is green
        (df['open'] > df['close']) &  # Current candle is red
        (df['open'] >= df['close'].shift(1)) &  # Open above previous close
        (df['close'] <= df['open'].shift(1))  # Close below previous open
    )
    
    # Morning star (simplified)
    df['morning_star'] = (
        (df['close'].shift(2) < df['open'].shift(2)) &  # First candle is bearish
        (abs(df['close'].shift(1) - df['open'].shift(1)) < abs(df['close'].shift(2) - df['open'].shift(2)) * 0.5) &  # Second candle is small
        (df['close'] > df['open']) &  # Third candle is bullish
        (df['close'] > (df['open'].shift(2) + df['close'].shift(2)) / 2)  # Third candle closes above middle of first candle
    )
    
    # Evening star (simplified)
    df['evening_star'] = (
        (df['close'].shift(2) > df['open'].shift(2)) &  # First candle is bullish
        (abs(df['close'].shift(1) - df['open'].shift(1)) < abs(df['close'].shift(2) - df['open'].shift(2)) * 0.5) &  # Second candle is small
        (df['close'] < df['open']) &  # Third candle is bearish
        (df['close'] < (df['open'].shift(2) + df['close'].shift(2)) / 2)  # Third candle closes below middle of first candle
    )
    
    return df


def visualize_candlestick_patterns(df):
    """
    Create a visualization of OHLC data with candlestick patterns highlighted.
    
    Args:
        df: DataFrame with OHLCV data and pattern columns
    """
    # Create a copy with date column in matplotlib format
    plot_df = df.copy()
    plot_df.reset_index(inplace=True)
    plot_df['date_as_float'] = mdates.date2num(plot_df['timestamp'])
    
    # Create figure and axis
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={'height_ratios': [3, 1]})
    
    # Create OHLC chart
    candlestick_ohlc(ax1, 
                     plot_df[['date_as_float', 'open', 'high', 'low', 'close']].values,
                     width=0.6, colorup='green', colordown='red', alpha=0.8)
    
    # Format x axis
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.setp(ax1.get_xticklabels(), rotation=45, ha='right')
    
    # Add volume bars
    ax2.bar(plot_df['date_as_float'], plot_df['volume'], width=0.6, alpha=0.7, color='blue')
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.setp(ax2.get_xticklabels(), rotation=45, ha='right')
    
    # Add 20-day moving average
    ax1.plot(plot_df['date_as_float'], plot_df['close'].rolling(window=20).mean(), color='orange', label='20-day MA')
    
    # Highlight patterns
    patterns_to_plot = ['doji', 'hammer', 'bullish_engulfing', 'bearish_engulfing', 'morning_star', 'evening_star']
    colors = ['blue', 'green', 'purple', 'red', 'cyan', 'magenta']
    
    for pattern, color in zip(patterns_to_plot, colors):
        for idx, row in plot_df[plot_df[pattern]].iterrows():
            if pattern in ['doji', 'hammer']:
                marker = 'o'
            elif pattern in ['bullish_engulfing', 'morning_star']:
                marker = '^'  # up arrow
            else:
                marker = 'v'  # down arrow
                
            # Add pattern marker
            ax1.plot(row['date_as_float'], row['high'] * 1.01, marker=marker, 
                     markersize=10, color=color, label=pattern if not any(p in l.get_label() for p in [pattern] for l in ax1.get_legend_handles_labels()[1]) else "")
    
    # Add legend (only showing unique pattern types)
    handles, labels = ax1.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax1.legend(by_label.values(), by_label.keys(), loc='upper left')
    
    # Add titles and labels
    ax1.set_ylabel('Price')
    ax2.set_ylabel('Volume')
    ax1.set_title('BTC/USDT with Candlestick Patterns')
    plt.tight_layout()
    
    # Save the figure
    os.makedirs('output/charts', exist_ok=True)
    plt.savefig('output/charts/btc_candlestick_patterns.png')
    plt.close()


def calculate_advanced_indicators(df):
    """
    Calculate advanced technical indicators.
    
    Args:
        df: DataFrame with OHLCV data
    
    Returns:
        DataFrame with additional indicators
    """
    # Simple Moving Averages
    df['sma_20'] = df['close'].rolling(window=20).mean()
    df['sma_50'] = df['close'].rolling(window=50).mean()
    
    # Exponential Moving Averages
    df['ema_12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema_26'] = df['close'].ewm(span=26, adjust=False).mean()
    
    # MACD
    df['macd'] = df['ema_12'] - df['ema_26']
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_histogram'] = df['macd'] - df['macd_signal']
    
    # Bollinger Bands
    df['bollinger_mid'] = df['close'].rolling(window=20).mean()
    df['bollinger_std'] = df['close'].rolling(window=20).std()
    df['bollinger_upper'] = df['bollinger_mid'] + 2 * df['bollinger_std']
    df['bollinger_lower'] = df['bollinger_mid'] - 2 * df['bollinger_std']
    
    # RSI (Relative Strength Index)
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # Average True Range (ATR)
    df['tr1'] = abs(df['high'] - df['low'])
    df['tr2'] = abs(df['high'] - df['close'].shift())
    df['tr3'] = abs(df['low'] - df['close'].shift())
    df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    df['atr'] = df['true_range'].rolling(window=14).mean()
    
    # Clean up intermediate columns
    df.drop(['tr1', 'tr2', 'tr3'], axis=1, inplace=True)
    
    return df


def plot_multi_timeframe(results, symbol):
    """
    Create a visualization of a symbol across multiple timeframes.
    
    Args:
        results: Dictionary of DataFrames for each timeframe
        symbol: The symbol being analyzed
    """
    fig, axes = plt.subplots(len(results), 1, figsize=(14, 4 * len(results)), sharex=False)
    
    for i, (timeframe, df) in enumerate(results.items()):
        ax = axes[i]
        
        # Plot price with bollinger bands
        ax.plot(df.index, df['close'], label='Close Price', color='blue')
        ax.plot(df.index, df['bollinger_upper'], label='Upper Band', color='red', alpha=0.3)
        ax.plot(df.index, df['bollinger_mid'], label='Middle Band', color='orange', alpha=0.3)
        ax.plot(df.index, df['bollinger_lower'], label='Lower Band', color='green', alpha=0.3)
        ax.fill_between(df.index, df['bollinger_upper'], df['bollinger_lower'], color='gray', alpha=0.1)
        
        # Add SMA curves
        ax.plot(df.index, df['sma_20'], label='SMA 20', color='purple', linestyle='--')
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
        
        # Add label and title
        ax.set_ylabel('Price')
        ax.set_title(f'{symbol} - {timeframe} Timeframe')
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save the figure
    os.makedirs('output/charts', exist_ok=True)
    plt.savefig(f'output/charts/{symbol.replace("/", "_")}_multi_timeframe.png')
    plt.close()


def create_correlation_matrix(price_df):
    """
    Create and visualize a correlation matrix.
    
    Args:
        price_df: DataFrame with closing prices for multiple symbols
    """
    # Calculate the correlation matrix
    corr_matrix = price_df.corr()
    
    # Create heatmap
    plt.figure(figsize=(12, 10))
    plt.matshow(corr_matrix, fignum=1, cmap='RdBu', vmin=-1, vmax=1)
    
    # Add correlation values
    for i in range(len(corr_matrix.columns)):
        for j in range(len(corr_matrix.columns)):
            plt.text(i, j, f"{corr_matrix.iloc[i, j]:.2f}", 
                     ha="center", va="center", 
                     color="white" if abs(corr_matrix.iloc[i, j]) > 0.5 else "black")
    
    # Add labels
    plt.xticks(range(len(corr_matrix.columns)), corr_matrix.columns, rotation=45)
    plt.yticks(range(len(corr_matrix.columns)), corr_matrix.columns)
    
    # Add title and labels
    plt.title('Correlation Matrix of Top Cryptocurrencies')
    plt.colorbar(label='Correlation Coefficient')
    
    # Save the figure
    os.makedirs('output/charts', exist_ok=True)
    plt.savefig('output/charts/crypto_correlation_matrix.png')
    plt.close()


def calculate_rolling_correlation(data_dict, base_symbol, window=7):
    """
    Calculate and visualize rolling correlation between a base symbol and others.
    
    Args:
        data_dict: Dictionary of DataFrames for each symbol
        base_symbol: The base symbol to compare against (e.g., 'BTC/USDT')
        window: Rolling window in days
    """
    # Extract base symbol data
    base_df = data_dict[base_symbol]['close']
    
    # Create DataFrame to hold rolling correlations
    rolling_corr = pd.DataFrame(index=base_df.index)
    
    # Calculate rolling correlation for each symbol
    for symbol, df in data_dict.items():
        if symbol != base_symbol:
            symbol_name = symbol.split('/')[0]
            combined = pd.DataFrame({
                'base': base_df,
                'compare': df['close']
            })
            rolling_corr[symbol_name] = combined['base'].rolling(window=window).corr(combined['compare'])
    
    # Plot rolling correlations
    plt.figure(figsize=(14, 8))
    
    for column in rolling_corr.columns:
        plt.plot(rolling_corr.index, rolling_corr[column], label=column)
    
    plt.axhline(y=0, color='black', linestyle='--', alpha=0.3)
    plt.title(f'{window}-Day Rolling Correlation with {base_symbol.split("/")[0]}')
    plt.ylabel('Correlation Coefficient')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # Format x-axis
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.gcf().autofmt_xdate()
    
    # Save the figure
    os.makedirs('output/charts', exist_ok=True)
    plt.savefig(f'output/charts/rolling_correlation_{base_symbol.split("/")[0]}.png')
    plt.close()


def create_volume_profile(df, symbol, bins=20):
    """
    Create and visualize a volume profile.
    
    Args:
        df: DataFrame with OHLCV data
        symbol: The symbol being analyzed
        bins: Number of price bins
    """
    # Find price range
    price_min = df['low'].min()
    price_max = df['high'].max()
    
    # Create price bins
    price_bins = np.linspace(price_min, price_max, bins+1)
    
    # Initialize volume profile
    volume_profile = np.zeros(bins)
    
    # Distribute volume across price bins
    for idx, row in df.iterrows():
        # Calculate proportion of candle in each bin
        for i in range(bins):
            bin_low = price_bins[i]
            bin_high = price_bins[i+1]
            
            # If candle overlaps with bin
            if not (row['high'] < bin_low or row['low'] > bin_high):
                # Calculate overlap
                overlap_low = max(row['low'], bin_low)
                overlap_high = min(row['high'], bin_high)
                overlap_ratio = (overlap_high - overlap_low) / (row['high'] - row['low'])
                
                # Add proportional volume
                volume_profile[i] += row['volume'] * overlap_ratio
    
    # Create figure
    fig, ax = plt.subplots(1, 2, figsize=(16, 8), gridspec_kw={'width_ratios': [3, 1]})
    
    # Plot price chart
    ax[0].plot(df.index, df['close'], label='Close Price')
    ax[0].set_ylabel('Price')
    ax[0].set_title(f'{symbol} - Price Chart (30 Days)')
    ax[0].grid(True, alpha=0.3)
    
    # Format x-axis
    ax[0].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.setp(ax[0].get_xticklabels(), rotation=45, ha='right')
    
    # Plot volume profile
    ax[1].barh([(price_bins[i] + price_bins[i+1])/2 for i in range(bins)], 
              volume_profile, height=(price_max-price_min)/bins, color='blue', alpha=0.7)
    ax[1].set_xlabel('Volume')
    ax[1].set_title('Volume Profile')
    ax[1].set_ylim(price_min, price_max)
    ax[1].grid(True, alpha=0.3)
    
    # Add POC (Point of Control) line
    poc_index = np.argmax(volume_profile)
    poc_price = (price_bins[poc_index] + price_bins[poc_index+1])/2
    ax[0].axhline(y=poc_price, color='red', linestyle='--', label=f'POC: {poc_price:.2f}')
    ax[1].axhline(y=poc_price, color='red', linestyle='--')
    
    # Add legend
    ax[0].legend()
    
    plt.tight_layout()
    
    # Save the figure
    os.makedirs('output/charts', exist_ok=True)
    plt.savefig(f'output/charts/{symbol.replace("/", "_")}_volume_profile.png')
    plt.close()


async def main():
    """Main function to run all examples."""
    logger.info("Starting advanced DataManager examples")
    
    # Create output directory if it doesn't exist
    os.makedirs('output/charts', exist_ok=True)
    
    try:
        # Run the examples
        await market_patterns_example()
        await multi_timeframe_analysis()
        await correlation_matrix_example()
        await volume_profile_example()
        
        logger.info("All examples completed successfully")
    
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise


if __name__ == "__main__":
    asyncio.run(main()) 