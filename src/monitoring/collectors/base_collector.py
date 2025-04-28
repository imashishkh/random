"""
Base collector module for Prometheus metrics.

This module provides the base class for all metric collectors.
"""

import abc
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily

logger = logging.getLogger(__name__)


class BaseCollector(abc.ABC):
    """
    Abstract base class for all metric collectors.
    
    This class implements the Prometheus collector interface and provides
    common functionality for all collectors. Subclasses must implement
    the collect_metrics method.
    """
    
    def __init__(self, collection_interval: float = 60.0):
        """
        Initialize the collector.
        
        Args:
            collection_interval: Interval in seconds between metric collection
        """
        self.collection_interval = collection_interval
        self.metrics_cache: Dict[str, Any] = {}
        self.last_collection_time: Optional[datetime] = None
        self.collection_running = False
        self._collection_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Stats
        self.collection_count = 0
        self.collection_errors = 0
        self.last_collection_duration = 0.0
    
    def collect(self) -> List[Any]:
        """
        Collect metrics for Prometheus.
        
        This method is called by Prometheus when scraping metrics.
        It returns cached metrics if available, or collects new metrics
        if the cache is empty or expired.
        
        Returns:
            List of metrics for Prometheus
        """
        try:
            # If we have cached metrics and they're fresh enough, use them
            if self.metrics_cache and self.last_collection_time:
                time_since_collection = (datetime.now() - self.last_collection_time).total_seconds()
                if time_since_collection < self.collection_interval:
                    logger.debug(f"Using cached metrics (age: {time_since_collection:.2f}s)")
                    return self.metrics_cache.copy()
            
            # Otherwise, collect fresh metrics
            return self.collect_metrics()
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}", exc_info=True)
            self.collection_errors += 1
            
            # Return empty list or last known good metrics
            return self.metrics_cache.copy() if self.metrics_cache else []
    
    @abc.abstractmethod
    def collect_metrics(self) -> List[Any]:
        """
        Collect metrics from the monitored system.
        
        This method must be implemented by subclasses. It should collect
        metrics from the monitored system and return them in a format
        suitable for Prometheus.
        
        Returns:
            List of metrics for Prometheus
        """
        pass
    
    def start_collection(self) -> None:
        """
        Start collecting metrics in a background thread.
        
        This method starts a thread that periodically collects metrics
        and caches them for Prometheus to scrape.
        """
        if self.collection_running:
            logger.warning(f"Collection already running for {self.__class__.__name__}")
            return
        
        self._stop_event.clear()
        self.collection_running = True
        
        def collection_loop():
            """Background collection loop."""
            logger.info(f"Starting collection loop for {self.__class__.__name__} "
                       f"(interval: {self.collection_interval}s)")
            
            while not self._stop_event.is_set():
                try:
                    start_time = time.time()
                    self.metrics_cache = self.collect_metrics()
                    self.last_collection_time = datetime.now()
                    end_time = time.time()
                    
                    self.last_collection_duration = end_time - start_time
                    self.collection_count += 1
                    
                    logger.debug(f"Collected metrics in {self.last_collection_duration:.2f}s "
                                f"(collection #{self.collection_count})")
                    
                except Exception as e:
                    logger.error(f"Error in collection loop: {e}", exc_info=True)
                    self.collection_errors += 1
                
                # Sleep until next collection or stop event
                self._stop_event.wait(self.collection_interval)
            
            logger.info(f"Collection loop stopped for {self.__class__.__name__}")
        
        self._collection_thread = threading.Thread(
            target=collection_loop,
            daemon=True,
            name=f"{self.__class__.__name__}-collector"
        )
        self._collection_thread.start()
        logger.info(f"Started collection thread for {self.__class__.__name__}")
    
    def stop(self) -> None:
        """
        Stop collecting metrics.
        
        This method stops the background collection thread.
        """
        if not self.collection_running:
            logger.warning(f"Collection not running for {self.__class__.__name__}")
            return
        
        logger.info(f"Stopping collection for {self.__class__.__name__}")
        self._stop_event.set()
        
        if self._collection_thread and self._collection_thread.is_alive():
            self._collection_thread.join(timeout=self.collection_interval + 5.0)
            if self._collection_thread.is_alive():
                logger.warning(f"Collection thread did not terminate cleanly for {self.__class__.__name__}")
        
        self.collection_running = False
        logger.info(f"Stopped collection for {self.__class__.__name__}")
    
    def get_collector_metrics(self) -> List[Any]:
        """
        Get metrics about the collector itself.
        
        Returns:
            List of metrics about the collector
        """
        metrics = []
        
        # Collection count
        counter = CounterMetricFamily(
            'collector_collection_count', 
            'Number of collections performed',
            labels=['collector']
        )
        counter.add_metric([self.__class__.__name__], self.collection_count)
        metrics.append(counter)
        
        # Collection errors
        counter = CounterMetricFamily(
            'collector_collection_errors', 
            'Number of collection errors',
            labels=['collector']
        )
        counter.add_metric([self.__class__.__name__], self.collection_errors)
        metrics.append(counter)
        
        # Last collection duration
        gauge = GaugeMetricFamily(
            'collector_last_collection_duration_seconds', 
            'Duration of the last collection in seconds',
            labels=['collector']
        )
        gauge.add_metric([self.__class__.__name__], self.last_collection_duration)
        metrics.append(gauge)
        
        # Last collection time
        if self.last_collection_time:
            gauge = GaugeMetricFamily(
                'collector_last_collection_timestamp', 
                'Timestamp of the last collection',
                labels=['collector']
            )
            timestamp = self.last_collection_time.timestamp()
            gauge.add_metric([self.__class__.__name__], timestamp)
            metrics.append(gauge)
        
        return metrics 