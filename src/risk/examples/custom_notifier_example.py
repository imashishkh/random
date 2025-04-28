"""
Custom Risk Notifier Example

This script demonstrates how to use the RiskNotifier class to send
risk alerts for custom volatility thresholds.
"""

import os
import sys
import logging
import time
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

# Add the parent directory to sys.path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
sys.path.append(str(project_root))

# Now imports should work regardless of how the script is run
try:
    from src.risk.notifier import RiskNotifier, NotificationConfig, NotificationLevel, NotificationTemplate
except ImportError:
    # Handle the case when running from the project root
    from risk.notifier import RiskNotifier, NotificationConfig, NotificationLevel, NotificationTemplate

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_notifier():
    """Set up a RiskNotifier with custom templates for volatility monitoring."""
    # Get webhook URL from environment variable
    webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
    
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not found in environment variables. Notifications will fall back to logging.")
    
    # Create notification config
    config = NotificationConfig(
        slack_webhook_url=webhook_url,
        rate_limit_period=60,  # 1 minute rate limit period
        rate_limit_count={
            NotificationLevel.INFO.value: 5,
            NotificationLevel.WARNING.value: 3,
            NotificationLevel.CRITICAL.value: 1,
        },
        fallback_to_logging=True
    )
    
    # Create notifier
    notifier = RiskNotifier(config)
    
    # Add custom volatility templates
    notifier.add_template("high_volatility_alert", NotificationTemplate(
        title="High Volatility Alert",
        message="High volatility detected for {symbol}. Current volatility is {volatility:.2f}%, exceeding the {threshold:.2f}% threshold.",
        fields={
            "Symbol": "{symbol}",
            "Current Volatility": "{volatility:.2f}%",
            "Threshold": "{threshold:.2f}%",
            "Time Period": "{period} periods",
            "Current Price": "${current_price:.2f}",
            "Recommendation": "{recommendation}"
        },
        actions=[
            {"text": "View Chart", "url": "https://www.tradingview.com/chart/?symbol={symbol}"},
            {"text": "Adjust Risk Settings", "url": "https://example.com/risk-settings"}
        ]
    ))
    
    notifier.add_template("correlation_breakdown_alert", NotificationTemplate(
        title="Correlation Breakdown Alert",
        message="Unusual correlation breakdown detected between {symbol1} and {symbol2}.",
        fields={
            "Symbol Pair": "{symbol1}/{symbol2}",
            "Historical Correlation": "{historical_correlation:.2f}",
            "Current Correlation": "{current_correlation:.2f}",
            "Change": "{correlation_change:.2f}",
            "Analysis Period": "{period} periods",
            "Potential Impact": "{impact}"
        }
    ))
    
    return notifier


def calculate_volatility(prices, window=20):
    """
    Calculate rolling volatility for a price series.
    
    Args:
        prices: DataFrame or Series with price data
        window: Rolling window size for volatility calculation
        
    Returns:
        Series with rolling volatility values (percentage)
    """
    # Calculate returns
    returns = prices.pct_change().dropna()
    
    # Calculate rolling standard deviation
    volatility = returns.rolling(window=window).std() * np.sqrt(window) * 100
    
    return volatility


def monitor_volatility(notifier, market_data, thresholds):
    """
    Monitor volatility and send alerts when thresholds are exceeded.
    
    Args:
        notifier: RiskNotifier instance
        market_data: Dictionary of price DataFrames for each symbol
        thresholds: Dictionary of volatility thresholds for each symbol
    """
    logger.info("Starting volatility monitoring...")
    
    results = {}
    for symbol, data in market_data.items():
        # Calculate volatility
        vol = calculate_volatility(data['close'])
        current_volatility = vol.iloc[-1]
        
        # Get threshold for this symbol
        threshold = thresholds.get(symbol, thresholds.get('default', 10.0))
        
        # Store result
        results[symbol] = {
            'current_volatility': current_volatility,
            'threshold': threshold,
            'exceeded': current_volatility > threshold
        }
        
        # Send alert if threshold exceeded
        if current_volatility > threshold:
            logger.warning(f"High volatility detected for {symbol}: {current_volatility:.2f}% (threshold: {threshold:.2f}%)")
            
            # Determine severity based on how much threshold is exceeded
            if current_volatility > threshold * 2:
                severity = NotificationLevel.CRITICAL
                recommendation = "Consider closing positions immediately"
            elif current_volatility > threshold * 1.5:
                severity = NotificationLevel.WARNING
                recommendation = "Consider reducing position sizes"
            else:
                severity = NotificationLevel.INFO
                recommendation = "Monitor closely for further increases"
            
            # Send notification
            notifier.notify(
                severity,
                "high_volatility_alert",
                {
                    "symbol": symbol,
                    "volatility": current_volatility,
                    "threshold": threshold,
                    "period": vol.name or 20,
                    "current_price": data['close'].iloc[-1],
                    "recommendation": recommendation
                }
            )
    
    return results


def monitor_correlations(notifier, market_data, correlation_thresholds):
    """
    Monitor correlations between assets and send alerts when significant changes occur.
    
    Args:
        notifier: RiskNotifier instance
        market_data: Dictionary of price DataFrames for each symbol
        correlation_thresholds: Dictionary with correlation change thresholds
    """
    logger.info("Starting correlation monitoring...")
    
    # Extract close prices for all symbols
    close_prices = {}
    for symbol, data in market_data.items():
        close_prices[symbol] = data['close']
    
    # Combine into a single DataFrame
    price_df = pd.DataFrame(close_prices)
    
    # Calculate historical correlation (first half of data)
    mid_point = len(price_df) // 2
    historical_corr = price_df.iloc[:mid_point].corr()
    
    # Calculate current correlation (last n rows)
    window = correlation_thresholds.get('window', 20)
    current_corr = price_df.iloc[-window:].corr()
    
    # Calculate correlation changes
    corr_change = current_corr - historical_corr
    
    results = []
    
    # Check all pairs
    for symbol1 in market_data.keys():
        for symbol2 in market_data.keys():
            if symbol1 >= symbol2:  # Skip duplicates and self-comparisons
                continue
            
            # Get correlation change
            change = corr_change.loc[symbol1, symbol2]
            
            # Get threshold
            threshold = correlation_thresholds.get('threshold', 0.3)
            
            # Check if change exceeds threshold (absolute value)
            if abs(change) > threshold:
                logger.warning(f"Correlation breakdown between {symbol1} and {symbol2}: change of {change:.2f}")
                
                # Determine impact
                if abs(change) > threshold * 2:
                    severity = NotificationLevel.CRITICAL
                    impact = "Major diversification loss or regime change"
                elif abs(change) > threshold * 1.5:
                    severity = NotificationLevel.WARNING
                    impact = "Significant relationship change, reevaluate portfolio allocation"
                else:
                    severity = NotificationLevel.INFO
                    impact = "Monitor for further changes in relationship"
                
                # Send notification
                notifier.notify(
                    severity,
                    "correlation_breakdown_alert",
                    {
                        "symbol1": symbol1,
                        "symbol2": symbol2,
                        "historical_correlation": historical_corr.loc[symbol1, symbol2],
                        "current_correlation": current_corr.loc[symbol1, symbol2],
                        "correlation_change": change,
                        "period": window,
                        "impact": impact
                    }
                )
                
                # Store result
                results.append({
                    "symbol_pair": f"{symbol1}/{symbol2}",
                    "historical_correlation": historical_corr.loc[symbol1, symbol2],
                    "current_correlation": current_corr.loc[symbol1, symbol2],
                    "change": change,
                    "threshold": threshold,
                    "exceeded": True
                })
    
    return results


def generate_sample_data():
    """Generate sample market data for demonstration."""
    # Set up date range
    dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
    
    # Create sample price data for 3 symbols
    np.random.seed(42)  # For reproducibility
    
    market_data = {}
    
    # BTCUSD - Higher volatility
    btc_prices = 30000 + np.cumsum(np.random.normal(0.001, 0.03, size=len(dates)))
    market_data['BTCUSD'] = pd.DataFrame({
        'date': dates,
        'open': btc_prices,
        'high': btc_prices * (1 + np.abs(np.random.normal(0, 0.01, size=len(dates)))),
        'low': btc_prices * (1 - np.abs(np.random.normal(0, 0.01, size=len(dates)))),
        'close': btc_prices * (1 + np.random.normal(0, 0.01, size=len(dates))),
        'volume': np.random.normal(1000, 100, size=len(dates))
    }).set_index('date')
    
    # ETHUSD - Correlated with BTC but with own dynamics
    eth_prices = 2000 + np.cumsum(
        0.7 * np.random.normal(0.001, 0.03, size=len(dates)) +  # Correlated component
        0.3 * np.random.normal(0.0005, 0.02, size=len(dates))    # Independent component
    )
    market_data['ETHUSD'] = pd.DataFrame({
        'date': dates,
        'open': eth_prices,
        'high': eth_prices * (1 + np.abs(np.random.normal(0, 0.015, size=len(dates)))),
        'low': eth_prices * (1 - np.abs(np.random.normal(0, 0.015, size=len(dates)))),
        'close': eth_prices * (1 + np.random.normal(0, 0.015, size=len(dates))),
        'volume': np.random.normal(5000, 500, size=len(dates))
    }).set_index('date')
    
    # XAUUSD (Gold) - Lower correlation with crypto
    gold_prices = 1800 + np.cumsum(
        0.1 * np.random.normal(0.0005, 0.01, size=len(dates)) +  # Small correlated component
        0.9 * np.random.normal(0.0002, 0.005, size=len(dates))   # Mostly independent
    )
    market_data['XAUUSD'] = pd.DataFrame({
        'date': dates,
        'open': gold_prices,
        'high': gold_prices * (1 + np.abs(np.random.normal(0, 0.005, size=len(dates)))),
        'low': gold_prices * (1 - np.abs(np.random.normal(0, 0.005, size=len(dates)))),
        'close': gold_prices * (1 + np.random.normal(0, 0.002, size=len(dates))),
        'volume': np.random.normal(10000, 1000, size=len(dates))
    }).set_index('date')
    
    # Create a volatility shock in the last 5 days for BTC
    volatility_multiplier = np.linspace(1, 5, 5)  # Gradually increasing volatility
    for i in range(5):
        idx = -5 + i
        shock = np.random.normal(0, 0.05 * volatility_multiplier[i])
        market_data['BTCUSD']['close'].iloc[idx] = market_data['BTCUSD']['close'].iloc[idx-1] * (1 + shock)
    
    # Create correlation breakdown in the last 10 days between ETH and XAU
    # Add a strong negative correlation where there was previously little correlation
    for i in range(10):
        idx = -10 + i
        if market_data['ETHUSD']['close'].iloc[idx-1] > market_data['ETHUSD']['close'].iloc[idx-2]:
            market_data['XAUUSD']['close'].iloc[idx] = market_data['XAUUSD']['close'].iloc[idx-1] * 0.995
        else:
            market_data['XAUUSD']['close'].iloc[idx] = market_data['XAUUSD']['close'].iloc[idx-1] * 1.005
    
    return market_data


if __name__ == "__main__":
    try:
        # Set up the notifier
        notifier = setup_notifier()
        
        # Generate sample market data
        market_data = generate_sample_data()
        
        # Define volatility thresholds
        volatility_thresholds = {
            'BTCUSD': 15.0,  # 15% threshold for BTC
            'ETHUSD': 18.0,  # 18% threshold for ETH
            'XAUUSD': 8.0,   # 8% threshold for Gold
            'default': 10.0  # Default threshold for other assets
        }
        
        # Define correlation thresholds
        correlation_thresholds = {
            'threshold': 0.3,  # Alert when correlation changes by more than 0.3
            'window': 20       # Use last 20 periods for current correlation
        }
        
        # Monitor volatility and send alerts
        volatility_results = monitor_volatility(notifier, market_data, volatility_thresholds)
        
        # Monitor correlations and send alerts
        correlation_results = monitor_correlations(notifier, market_data, correlation_thresholds)
        
        # Print summary
        logger.info("Volatility monitoring results:")
        for symbol, result in volatility_results.items():
            logger.info(f"  {symbol}: {result['current_volatility']:.2f}% (threshold: {result['threshold']:.2f}%) - {'EXCEEDED' if result['exceeded'] else 'OK'}")
        
        logger.info("Correlation monitoring results:")
        for result in correlation_results:
            logger.info(f"  {result['symbol_pair']}: Change of {result['change']:.2f} (threshold: {result['threshold']:.2f})")
        
    except Exception as e:
        logger.error(f"Error in demonstration: {e}", exc_info=True) 