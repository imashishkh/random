#!/usr/bin/env python3
"""
Blockchain Transaction Monitor Starter

This script starts the blockchain transaction monitoring service
that tracks deposits to user wallet addresses.
"""

import os
import sys
import time
import signal
import argparse
import logging
from pathlib import Path

# Add the parent directory to the path so we can import our modules
script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
project_root = script_dir.parent
sys.path.append(str(project_root))

# Import our modules
from dotenv import load_dotenv
from src.account.blockchain_monitor import (
    start_monitoring,
    stop_monitoring,
    get_monitor_instance
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('monitor_starter')

# Handle signals for graceful shutdown
def signal_handler(sig, frame):
    """Handle termination signals to stop monitor gracefully."""
    logger.info("Received termination signal, shutting down...")
    stop_monitoring()
    sys.exit(0)

def main():
    """Main function to start the transaction monitor."""
    parser = argparse.ArgumentParser(description='Start the blockchain transaction monitoring service')
    parser.add_argument('--config', type=str, default='config/monitor_settings.json',
                        help='Path to the configuration file')
    parser.add_argument('--daemon', action='store_true',
                        help='Run as a daemon process')
    parser.add_argument('--network', type=str, choices=['bsc_mainnet', 'bsc_testnet'],
                        help='Override blockchain network to use (default: use ENV setting)')
    args = parser.parse_args()
    
    # Set network environment variable if specified
    if args.network:
        os.environ["BLOCKCHAIN_NETWORK"] = args.network
        logger.info(f"Using network: {args.network}")
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Starting blockchain transaction monitoring service")
    
    try:
        # Start the monitoring service
        start_monitoring(args.config)
        
        # If not running as daemon, keep main thread alive
        if not args.daemon:
            logger.info("Monitor running in foreground mode. Press Ctrl+C to stop.")
            
            # Keep the script running
            while True:
                time.sleep(1)
        else:
            logger.info("Monitor started in daemon mode")
            
    except Exception as e:
        logger.error(f"Error starting monitor: {str(e)}")
        stop_monitoring()
        sys.exit(1)

if __name__ == "__main__":
    main() 