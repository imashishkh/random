#!/usr/bin/env python
"""
Deposit Monitor Service Runner

This script starts the deposit monitoring service to track blockchain transactions
to user deposit addresses. It can be run as a standalone script or as a daemon process.

Usage:
    python run_deposit_monitor.py [--daemon]
    python run_deposit_monitor.py --stop

Options:
    --daemon    Run the monitor as a background daemon process
    --stop      Stop the running daemon process
    --config    Path to custom configuration file
"""

import os
import sys
import time
import signal
import logging
import argparse
import json
from pathlib import Path

# Add the parent directory to the path so we can import modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.account.deposit_monitor import (
    get_deposit_monitor_service, 
    BlockchainConfig
)

# Configure logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='logs/deposit_monitor.log',
    filemode='a'
)
logger = logging.getLogger('deposit_monitor_runner')

# Default paths
DEFAULT_PID_FILE = '/tmp/deposit_monitor.pid'
DEFAULT_CONFIG_FILE = 'config/deposit_monitor.json'

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Deposit Monitor Service Runner')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    parser.add_argument('--stop', action='store_true', help='Stop the daemon')
    parser.add_argument('--config', type=str, default=DEFAULT_CONFIG_FILE, 
                        help='Path to configuration file')
    return parser.parse_args()

def load_config(config_file):
    """Load configuration from JSON file."""
    if not os.path.exists(config_file):
        logger.warning(f"Config file {config_file} not found, using defaults")
        return {}
    
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config file: {e}")
        return {}

def setup_chains(service, config):
    """Setup blockchain configurations from config."""
    # Get chain configurations
    chains = config.get('chains', [
        {
            'chain_id': 56,  # BSC Mainnet
            'rpc_url': 'https://bsc-dataseed.binance.org/',
            'confirmation_threshold': 12
        }
    ])
    
    # Add each chain
    for chain in chains:
        try:
            chain_config = BlockchainConfig(
                chain_id=chain['chain_id'],
                rpc_url=chain['rpc_url'],
                confirmation_threshold=chain.get('confirmation_threshold', 12),
                poll_interval=chain.get('poll_interval', 15)
            )
            service.add_blockchain(chain_config)
        except Exception as e:
            logger.error(f"Error setting up chain {chain.get('chain_id')}: {e}")

def stop_daemon():
    """Stop the running daemon process."""
    try:
        if not os.path.exists(DEFAULT_PID_FILE):
            logger.error("PID file not found, service may not be running")
            return

        with open(DEFAULT_PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        
        # Send termination signal
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info(f"Sent SIGTERM to process {pid}")
            
            # Wait for process to terminate
            attempts = 0
            while attempts < 10:
                try:
                    os.kill(pid, 0)  # Check if process exists
                    time.sleep(0.5)
                    attempts += 1
                except OSError:
                    break
            
            if attempts >= 10:
                logger.warning(f"Process {pid} did not terminate gracefully, sending SIGKILL")
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            logger.warning(f"Process {pid} not found")
        
        # Remove PID file
        try:
            os.remove(DEFAULT_PID_FILE)
        except OSError as e:
            logger.error(f"Error removing PID file: {e}")
            
        logger.info("Deposit monitor service stopped")
        
    except Exception as e:
        logger.error(f"Error stopping daemon: {e}")

def run_service(config_file):
    """Run the deposit monitor service."""
    try:
        # Load configuration
        config = load_config(config_file)
        
        # Get the service
        service = get_deposit_monitor_service()
        
        # Setup chains from config
        setup_chains(service, config)
        
        # Handle interrupt signal
        def handle_signal(signum, frame):
            logger.info(f"Received signal {signum}, shutting down")
            service.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
        
        # Start the service
        logger.info("Starting deposit monitor service")
        service.start()
        
        # Keep the main thread running
        while True:
            time.sleep(60)
            # Refresh monitored addresses periodically
            service.refresh_monitored_addresses()
            
    except Exception as e:
        logger.error(f"Error running deposit monitor service: {e}")
        if 'service' in locals() and service.running:
            service.stop()
        sys.exit(1)

def run_as_daemon(config_file):
    """Run the service as a daemon process."""
    try:
        # Try to import daemon library
        try:
            import daemon
            from daemon import pidfile
        except ImportError:
            logger.error("python-daemon library not found. Install with: pip install python-daemon")
            sys.exit(1)
        
        # Ensure config directory exists
        os.makedirs('config', exist_ok=True)
        
        # Set up stdout/stderr files
        stdout_file = open('logs/deposit_monitor_stdout.log', 'a+')
        stderr_file = open('logs/deposit_monitor_stderr.log', 'a+')
        
        # Create daemon context
        context = daemon.DaemonContext(
            pidfile=pidfile.TimeoutPIDLockFile(DEFAULT_PID_FILE),
            stdout=stdout_file,
            stderr=stderr_file,
            working_directory=str(Path(__file__).resolve().parent.parent),
            umask=0o022,
            detach_process=True
        )
        
        # Start the daemon
        logger.info("Starting deposit monitor as daemon")
        with context:
            run_service(config_file)
            
    except Exception as e:
        logger.error(f"Error starting daemon: {e}")
        sys.exit(1)

def main():
    """Main entry point."""
    # Parse arguments
    args = parse_args()
    
    # Handle --stop
    if args.stop:
        stop_daemon()
        return
    
    # Check if already running
    if os.path.exists(DEFAULT_PID_FILE):
        try:
            with open(DEFAULT_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            try:
                # Check if process is still running
                os.kill(pid, 0)
                logger.error(f"Deposit monitor is already running with PID {pid}")
                sys.exit(1)
            except OSError:
                # Process not running, remove stale PID file
                logger.warning(f"Removing stale PID file (process {pid} not running)")
                os.remove(DEFAULT_PID_FILE)
        except (ValueError, FileNotFoundError):
            # Invalid PID file, remove it
            try:
                os.remove(DEFAULT_PID_FILE)
            except FileNotFoundError:
                pass
    
    # Ensure config directory exists
    os.makedirs('config', exist_ok=True)
    if not os.path.exists(args.config) and args.config == DEFAULT_CONFIG_FILE:
        # Create default config if it doesn't exist
        default_config = {
            'chains': [
                {
                    'chain_id': 56,
                    'rpc_url': 'https://bsc-dataseed.binance.org/',
                    'confirmation_threshold': 12,
                    'poll_interval': 15
                }
            ]
        }
        try:
            with open(DEFAULT_CONFIG_FILE, 'w') as f:
                json.dump(default_config, f, indent=2)
            logger.info(f"Created default configuration file at {DEFAULT_CONFIG_FILE}")
        except Exception as e:
            logger.error(f"Error creating default config file: {e}")
    
    # Run as daemon or foreground process
    if args.daemon:
        run_as_daemon(args.config)
    else:
        run_service(args.config)

if __name__ == "__main__":
    main() 