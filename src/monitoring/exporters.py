"""
Exporter module for Prometheus metrics.

This module provides functionality to setup and manage Prometheus exporters,
including HTTP server initialization and collector registration.
"""

import logging
import threading
from typing import Dict, Any, Optional

import prometheus_client
from prometheus_client import start_http_server

from ..config import get_config
from .collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)

# Global server reference for clean shutdown
_http_server_thread: Optional[threading.Thread] = None
_collectors_threads: Dict[str, threading.Thread] = {}

def start_exporters(**collectors: BaseCollector) -> None:
    """
    Start the Prometheus HTTP server and register all provided collectors.
    
    Args:
        **collectors: Dictionary of collector instances to register with Prometheus.
    """
    global _http_server_thread, _collectors_threads
    
    config = get_config()
    
    if not config.prometheus.server_enabled:
        logger.info("Prometheus server is disabled, skipping exporter setup")
        return
    
    port = config.prometheus.port
    addr = config.prometheus.host
    
    # Start the HTTP server in a separate thread
    logger.info(f"Starting Prometheus HTTP server on {addr}:{port}")
    
    def run_http_server():
        """Run the Prometheus HTTP server."""
        try:
            start_http_server(port=port, addr=addr)
            logger.info(f"Prometheus HTTP server running on {addr}:{port}")
        except Exception as e:
            logger.error(f"Failed to start Prometheus HTTP server: {e}", exc_info=True)
            raise
    
    _http_server_thread = threading.Thread(target=run_http_server, daemon=True)
    _http_server_thread.start()
    
    # Start and register all collectors
    for name, collector in collectors.items():
        logger.info(f"Registering collector: {name}")
        prometheus_client.REGISTRY.register(collector)
        
        # Start the collector in a separate thread
        collector_thread = threading.Thread(
            target=collector.start_collection,
            daemon=True,
            name=f"collector-{name}"
        )
        collector_thread.start()
        _collectors_threads[name] = collector_thread
        
    logger.info(f"Registered {len(collectors)} collectors")

def stop_exporters() -> None:
    """
    Stop all exporters and collectors gracefully.
    """
    global _http_server_thread, _collectors_threads
    
    logger.info("Stopping exporters")
    
    # Nothing to stop if the server wasn't started
    if _http_server_thread is None:
        return
    
    # Wait for collector threads to terminate (should be done via the collector's stop() method)
    for name, thread in _collectors_threads.items():
        if thread.is_alive():
            logger.info(f"Waiting for collector thread to terminate: {name}")
            thread.join(timeout=5.0)
            if thread.is_alive():
                logger.warning(f"Collector thread did not terminate cleanly: {name}")
    
    _collectors_threads.clear()
    
    # The HTTP server thread is a daemon thread and will terminate when the main thread exits
    _http_server_thread = None
    
    logger.info("All exporters stopped") 