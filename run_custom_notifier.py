#!/usr/bin/env python3
"""
Runner script for the custom risk notifier example.

This script provides a convenient way to run the custom risk notifier
example with proper logging configuration and error handling.
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('notifier_run.log')
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Run the custom notifier example."""
    parser = argparse.ArgumentParser(description='Run the custom risk notifier example')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--slack-webhook', help='Slack webhook URL (overrides env variable)')
    args = parser.parse_args()
    
    # Set log level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Load environment variables
    load_dotenv()
    logger.info("Environment variables loaded")
    
    # Override webhook URL if provided
    if args.slack_webhook:
        os.environ['SLACK_WEBHOOK_URL'] = args.slack_webhook
        logger.info("Using provided Slack webhook URL")
    
    # Print environment configuration
    logger.info(f"SLACK_WEBHOOK_URL configured: {bool(os.environ.get('SLACK_WEBHOOK_URL'))}")
    
    # Add src directory to path to ensure imports work
    project_root = Path(__file__).resolve().parent
    sys.path.append(str(project_root))
    
    try:
        # Import and run the example
        logger.info("Starting custom notifier example")
        
        # Try different import paths to handle various run scenarios
        try:
            from src.risk.examples.custom_notifier_example import (
                setup_notifier, 
                generate_sample_data, 
                monitor_volatility, 
                monitor_correlations
            )
        except ImportError:
            try:
                # Try direct import for when run from project root
                from risk.examples.custom_notifier_example import (
                    setup_notifier, 
                    generate_sample_data, 
                    monitor_volatility, 
                    monitor_correlations
                )
            except ImportError:
                # Last resort, try with the full file path
                logger.info("Using direct import method")
                example_file = project_root / 'src' / 'risk' / 'examples' / 'custom_notifier_example.py'
                
                if not example_file.exists():
                    logger.error(f"Cannot find example file at {example_file}")
                    return 1
                
                # Add directory to path
                sys.path.append(str(example_file.parent))
                
                # Use importlib for a cleaner import
                import importlib.util
                spec = importlib.util.spec_from_file_location("custom_notifier_example", example_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Get the required functions
                setup_notifier = module.setup_notifier
                generate_sample_data = module.generate_sample_data
                monitor_volatility = module.monitor_volatility
                monitor_correlations = module.monitor_correlations
        
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
        logger.info("===== Run Complete =====")
        logger.info("Volatility monitoring results:")
        for symbol, result in volatility_results.items():
            logger.info(f"  {symbol}: {result['current_volatility']:.2f}% (threshold: {result['threshold']:.2f}%) - {'EXCEEDED' if result['exceeded'] else 'OK'}")
        
        logger.info("Correlation monitoring results:")
        for result in correlation_results:
            logger.info(f"  {result['symbol_pair']}: Change of {result['change']:.2f} (threshold: {result['threshold']:.2f})")
            
    except Exception as e:
        logger.error(f"Error running example: {e}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 