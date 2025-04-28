"""
Binance collector monitoring.

This module provides monitoring functionality for Binance collectors,
including connection health checks and data completeness metrics.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import pandas as pd

logger = logging.getLogger(__name__)


class BinanceMonitor:
    """
    Monitor for Binance collectors.
    
    Provides functionality to track connection health, data completeness,
    and collector performance metrics.
    """
    
    def __init__(self, collector_name: str, check_interval: int = 60):
        """
        Initialize the monitor.
        
        Args:
            collector_name: Name of the collector being monitored
            check_interval: How often to perform health checks (seconds)
        """
        self.collector_name = collector_name
        self.check_interval = check_interval
        
        # Health metrics
        self.last_health_check = None
        self.connection_status = "unknown"
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3
        
        # Data metrics
        self.collection_stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "last_success_time": None,
            "last_error": None,
            "data_points_collected": 0,
        }
        
        # WebSocket metrics
        self.ws_stats = {
            "connected": False,
            "last_message_time": None,
            "total_messages": 0,
            "reconnects": 0,
            "subscriptions": set(),
        }
        
        # Monitoring task
        self._monitoring_task = None
        self._running = False
    
    async def start_monitoring(self):
        """Start the monitoring process."""
        if self._running:
            return
            
        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitor_loop())
        logger.info(f"Started monitoring for {self.collector_name}")
    
    async def stop_monitoring(self):
        """Stop the monitoring process."""
        if not self._running:
            return
            
        self._running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
            
        logger.info(f"Stopped monitoring for {self.collector_name}")
    
    async def _monitor_loop(self):
        """Monitoring loop that periodically checks health and metrics."""
        while self._running:
            try:
                await self.check_health()
                
                # Check for stale WebSocket connections
                if self.ws_stats["connected"] and self.ws_stats["last_message_time"]:
                    time_since_last_msg = time.time() - self.ws_stats["last_message_time"]
                    if time_since_last_msg > self.check_interval * 2:
                        logger.warning(
                            f"WebSocket connection for {self.collector_name} may be stale. "
                            f"No messages received in {time_since_last_msg:.1f} seconds."
                        )
                        
                # Check for data collection gaps
                if self.collection_stats["last_success_time"]:
                    time_since_last_success = datetime.now() - self.collection_stats["last_success_time"]
                    if time_since_last_success > timedelta(minutes=5):
                        logger.warning(
                            f"Data collection gap detected for {self.collector_name}. "
                            f"No successful collections in {time_since_last_success}."
                        )
                
                # Log periodic stats
                logger.info(f"Collector stats for {self.collector_name}: "
                           f"Requests: {self.collection_stats['total_requests']}, "
                           f"Success: {self.collection_stats['successful_requests']}, "
                           f"Failed: {self.collection_stats['failed_requests']}, "
                           f"Data points: {self.collection_stats['data_points_collected']}")
                
            except Exception as e:
                logger.error(f"Error in monitoring loop for {self.collector_name}: {str(e)}")
                
            await asyncio.sleep(self.check_interval)
    
    async def check_health(self) -> bool:
        """
        Check the health of the collector.
        
        Returns:
            True if healthy, False otherwise
        """
        self.last_health_check = datetime.now()
        
        # Basic health check implementation
        # In a real implementation, this would check the actual collector's state
        
        # If there have been recent successful collections, consider it healthy
        if (self.collection_stats["last_success_time"] and 
            (datetime.now() - self.collection_stats["last_success_time"]) < timedelta(minutes=10)):
            self.connection_status = "healthy"
            self.consecutive_failures = 0
            return True
            
        # If there have been consecutive failures, consider it unhealthy
        if self.consecutive_failures >= self.max_consecutive_failures:
            self.connection_status = "unhealthy"
            logger.error(f"Collector {self.collector_name} is unhealthy after {self.consecutive_failures} consecutive failures")
            return False
            
        # If no data yet, consider it unknown
        self.connection_status = "unknown"
        return False
    
    def record_request(self, success: bool, error: Optional[str] = None, data_points: int = 0):
        """
        Record a request attempt and its outcome.
        
        Args:
            success: Whether the request was successful
            error: Error message if the request failed
            data_points: Number of data points collected
        """
        self.collection_stats["total_requests"] += 1
        
        if success:
            self.collection_stats["successful_requests"] += 1
            self.collection_stats["last_success_time"] = datetime.now()
            self.collection_stats["data_points_collected"] += data_points
            self.consecutive_failures = 0
        else:
            self.collection_stats["failed_requests"] += 1
            self.collection_stats["last_error"] = error
            self.consecutive_failures += 1
    
    def record_ws_message(self, message: Any = None):
        """
        Record receipt of a WebSocket message.
        
        Args:
            message: The message received (optional)
        """
        self.ws_stats["last_message_time"] = time.time()
        self.ws_stats["total_messages"] += 1
    
    def record_ws_connection(self, connected: bool):
        """
        Record WebSocket connection status change.
        
        Args:
            connected: New connection status
        """
        prev_status = self.ws_stats["connected"]
        self.ws_stats["connected"] = connected
        
        if not prev_status and connected:
            logger.info(f"WebSocket for {self.collector_name} connected")
        elif prev_status and not connected:
            logger.warning(f"WebSocket for {self.collector_name} disconnected")
            self.ws_stats["reconnects"] += 1
    
    def record_ws_subscription(self, stream: str, subscribed: bool = True):
        """
        Record WebSocket subscription status.
        
        Args:
            stream: Stream name
            subscribed: Whether subscribing or unsubscribing
        """
        if subscribed:
            self.ws_stats["subscriptions"].add(stream)
            logger.debug(f"Added subscription to {stream} for {self.collector_name}")
        else:
            self.ws_stats["subscriptions"].discard(stream)
            logger.debug(f"Removed subscription to {stream} for {self.collector_name}")
    
    def get_status_report(self) -> Dict[str, Any]:
        """
        Get a comprehensive status report.
        
        Returns:
            Status report dictionary
        """
        return {
            "collector_name": self.collector_name,
            "connection_status": self.connection_status,
            "last_health_check": self.last_health_check,
            "consecutive_failures": self.consecutive_failures,
            "collection_stats": self.collection_stats,
            "websocket_stats": {
                "connected": self.ws_stats["connected"],
                "last_message": self.ws_stats["last_message_time"],
                "message_count": self.ws_stats["total_messages"],
                "reconnects": self.ws_stats["reconnects"],
                "active_subscriptions": list(self.ws_stats["subscriptions"]),
            }
        }
    
    def check_data_completeness(
        self,
        data: pd.DataFrame,
        expected_interval: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """
        Check the completeness of time series data.
        
        Args:
            data: DataFrame with time series data
            expected_interval: Expected data interval (e.g., '1m', '1h')
            start_time: Expected start time
            end_time: Expected end time
            
        Returns:
            Completeness metrics
        """
        # Convert interval string to pandas frequency
        interval_map = {
            '1m': '1min', '3m': '3min', '5m': '5min', '15m': '15min', '30m': '30min',
            '1h': '1H', '2h': '2H', '4h': '4H', '6h': '6H', '8h': '8H', '12h': '12H',
            '1d': '1D', '3d': '3D', '1w': '1W', '1M': '1M'
        }
        
        pandas_freq = interval_map.get(expected_interval, '1H')
        
        # Generate expected index
        expected_index = pd.date_range(start=start_time, end=end_time, freq=pandas_freq)
        
        # Check for missing data points
        if not data.empty:
            missing_points = expected_index.difference(data.index)
            missing_count = len(missing_points)
            completeness_pct = 100 * (1 - missing_count / len(expected_index)) if len(expected_index) > 0 else 0
            
            return {
                "expected_points": len(expected_index),
                "actual_points": len(data),
                "missing_points": missing_count,
                "completeness_pct": completeness_pct,
                "missing_dates": [d.strftime("%Y-%m-%d %H:%M:%S") for d in missing_points[:10]]  # First 10 missing dates
            }
        else:
            return {
                "expected_points": len(expected_index),
                "actual_points": 0,
                "missing_points": len(expected_index),
                "completeness_pct": 0,
                "missing_dates": []
            }


# Usage example
async def example_usage():
    """Example of using the BinanceMonitor."""
    # Create a monitor
    monitor = BinanceMonitor("BTCUSDT-OHLCV")
    
    # Start monitoring
    await monitor.start_monitoring()
    
    try:
        # Simulate some collection activity
        for i in range(5):
            # Record successful request
            monitor.record_request(success=True, data_points=100)
            await asyncio.sleep(1)
            
        # Simulate WebSocket connection and messages
        monitor.record_ws_connection(connected=True)
        monitor.record_ws_subscription("btcusdt@kline_1m")
        
        for i in range(10):
            monitor.record_ws_message()
            await asyncio.sleep(0.5)
            
        # Simulate a failed request
        monitor.record_request(success=False, error="API timeout")
        
        # Get status report
        status = monitor.get_status_report()
        print(f"Status report: {status}")
        
        # Wait a bit
        await asyncio.sleep(5)
        
    finally:
        # Stop monitoring
        await monitor.stop_monitoring()
        

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_usage()) 