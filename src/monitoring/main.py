#!/usr/bin/env python3
"""
Main entry point for the monitoring module.

This module initializes and runs the Prometheus exporter when executed directly.
It configures all enabled collectors based on environment settings and handles
graceful shutdown on termination signals.
"""

import logging
import signal
import sys
import time
from typing import Optional

from ..config import get_config
from .exporters import start_exporters, stop_exporters
from .collectors.agent_collector import AgentCollector
from .collectors.trade_collector import TradeCollector
from .collectors.api_collector import APICollector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Global references to collectors for clean shutdown
_agent_collector: Optional[AgentCollector] = None
_trade_collector: Optional[TradeCollector] = None
_api_collector: Optional[APICollector] = None

def initialize_collectors():
    """Initialize all enabled collectors based on configuration."""
    global _agent_collector, _trade_collector, _api_collector
    
    config = get_config()
    collectors = {}
    
    # Initialize collectors based on configuration
    if config.prometheus.agent_collector_enabled:
        logger.info("Initializing Agent Collector")
        _agent_collector = AgentCollector(
            collection_interval=config.prometheus.agent_collection_interval,
            cache_ttl=config.prometheus.agent_cache_ttl
        )
        collectors['agent'] = _agent_collector
    
    if config.prometheus.trade_collector_enabled:
        logger.info("Initializing Trade Collector")
        _trade_collector = TradeCollector(
            collection_interval=config.prometheus.trade_collection_interval,
            cache_ttl=config.prometheus.trade_cache_ttl
        )
        collectors['trade'] = _trade_collector
    
    if config.prometheus.api_collector_enabled:
        logger.info("Initializing API Collector")
        _api_collector = APICollector(
            collection_interval=config.prometheus.api_collection_interval,
            cache_ttl=config.prometheus.api_cache_ttl
        )
        collectors['api'] = _api_collector
    
    return collectors

def shutdown_collectors():
    """Gracefully stop all collectors."""
    if _agent_collector:
        logger.info("Stopping Agent Collector")
        _agent_collector.stop()
    
    if _trade_collector:
        logger.info("Stopping Trade Collector")
        _trade_collector.stop()
    
    if _api_collector:
        logger.info("Stopping API Collector")
        _api_collector.stop()

def handle_signal(signum, frame):
    """Handle termination signals and perform cleanup."""
    logger.info(f"Received signal {signum}, shutting down...")
    shutdown_collectors()
    stop_exporters()
    sys.exit(0)

def main():
    """Initialize and run the monitoring system."""
    logger.info("Starting Forex Trading monitoring system")
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    try:
        # Initialize collectors
        collectors = initialize_collectors()
        
        # Start the Prometheus exporter
        start_exporters(**collectors)
        
        logger.info("Monitoring system started. Press CTRL+C to exit.")
        
        # Keep the main thread alive
        while True:
            time.sleep(1)
            
    except Exception as e:
        logger.error(f"Error in monitoring system: {e}", exc_info=True)
        shutdown_collectors()
        stop_exporters()
        sys.exit(1)

if __name__ == "__main__":
    main() 