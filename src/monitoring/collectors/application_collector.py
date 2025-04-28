"""
Application metrics collector for Prometheus.

This module provides a collector for monitoring application-specific metrics
like API requests, response times, error rates, and business logic metrics.
"""

import logging
import time
from typing import Dict, List, Any, Optional, Callable

from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, HistogramMetricFamily

from .collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)


class ApplicationCollector(BaseCollector):
    """
    Collector for application-specific metrics.
    
    This collector measures various application metrics including:
    - API request counts and response times
    - Error rates and types
    - Business logic metrics
    - Cache hit/miss ratios
    - Custom application metrics
    """
    
    def __init__(
        self,
        collection_interval: float = 15.0,
        app_name: str = "application"
    ):
        """
        Initialize the application collector.
        
        Args:
            collection_interval: Interval in seconds between metric collection
            app_name: Name of the application (used as metric prefix)
        """
        super().__init__(collection_interval=collection_interval)
        
        self.app_name = app_name
        
        # Request metrics
        self.request_counts = {}  # endpoint -> count
        self.request_errors = {}  # endpoint -> error_type -> count
        self.last_request_time = {}  # endpoint -> timestamp
        
        # Response time tracking
        self.response_times = {}  # endpoint -> list of times
        
        # Error tracking
        self.error_counts = {}  # error_type -> count
        
        # Business metrics
        self.business_metrics = {}  # metric_name -> value
        
        # Cache metrics
        self.cache_hits = {}  # cache_name -> hits
        self.cache_misses = {}  # cache_name -> misses
        
        # Custom metrics (gauge type)
        self.custom_gauges = {}  # name -> value
        self.custom_counters = {}  # name -> value
        
        # Metric collection callbacks
        self.metric_callbacks = []  # list of functions to call during collection
    
    def collect_metrics(self) -> List[Any]:
        """
        Collect application metrics.
        
        Returns:
            List of metrics for Prometheus
        """
        metrics = []
        
        # Call all registered callbacks to update metrics
        self._call_metric_callbacks()
        
        # API request metrics
        metrics.extend(self._collect_request_metrics())
        
        # Error metrics
        metrics.extend(self._collect_error_metrics())
        
        # Business logic metrics
        metrics.extend(self._collect_business_metrics())
        
        # Cache metrics
        metrics.extend(self._collect_cache_metrics())
        
        # Custom metrics
        metrics.extend(self._collect_custom_metrics())
        
        # Add collector's own metrics
        metrics.extend(self.get_collector_metrics())
        
        return metrics
    
    def _call_metric_callbacks(self):
        """Call all registered metric collection callbacks."""
        for callback in self.metric_callbacks:
            try:
                callback(self)
            except Exception as e:
                logger.error(f"Error in metric collection callback: {str(e)}")
    
    def _collect_request_metrics(self) -> List[Any]:
        """
        Collect API request metrics.
        
        Returns:
            List of request metrics
        """
        metrics = []
        
        # Request count metrics
        request_counter = CounterMetricFamily(
            f"{self.app_name}_http_requests_total",
            "Total number of HTTP requests",
            labels=["endpoint", "method"]
        )
        
        # Error count metrics
        error_counter = CounterMetricFamily(
            f"{self.app_name}_http_request_errors_total",
            "Total number of HTTP request errors",
            labels=["endpoint", "method", "error_type"]
        )
        
        # Response time metrics (as gauge of most recent)
        response_time_gauge = GaugeMetricFamily(
            f"{self.app_name}_http_request_duration_seconds",
            "HTTP request duration in seconds (most recent)",
            labels=["endpoint", "method"]
        )
        
        # Response time histogram bucket values
        # We'll convert our raw times into a simple histogram
        response_time_histogram = HistogramMetricFamily(
            f"{self.app_name}_http_request_duration_seconds_histogram",
            "Histogram of HTTP request durations",
            labels=["endpoint", "method"]
        )
        
        # Request rate (requests per second) over the last interval
        request_rate_gauge = GaugeMetricFamily(
            f"{self.app_name}_http_request_rate",
            "HTTP requests per second",
            labels=["endpoint", "method"]
        )
        
        # Process each endpoint's metrics
        for endpoint_key, count in self.request_counts.items():
            if ":" in endpoint_key:
                endpoint, method = endpoint_key.split(":", 1)
            else:
                endpoint, method = endpoint_key, "UNKNOWN"
            
            # Add request count
            request_counter.add_metric([endpoint, method], count)
            
            # Add error counts for this endpoint
            errors = self.request_errors.get(endpoint_key, {})
            for error_type, error_count in errors.items():
                error_counter.add_metric([endpoint, method, error_type], error_count)
            
            # Add response time metrics
            times = self.response_times.get(endpoint_key, [])
            if times:
                # Most recent response time as a gauge
                response_time_gauge.add_metric([endpoint, method], times[-1])
                
                # Create histogram buckets
                # Define buckets (in seconds): 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10
                buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
                bucket_values = [0] * len(buckets)
                
                # Count values in each bucket
                for t in times:
                    for i, threshold in enumerate(buckets):
                        if t <= threshold:
                            bucket_values[i] += 1
                
                # Calculate histogram values
                histogram_values = {}
                for i, bucket in enumerate(buckets):
                    histogram_values[bucket] = bucket_values[i]
                
                # Add histogram metric
                sum_values = sum(times)
                count_values = len(times)
                response_time_histogram.add_metric(
                    [endpoint, method], 
                    buckets=histogram_values, 
                    sum_value=sum_values
                )
                
                # Calculate request rate (requests per second)
                interval = self.collection_interval
                if interval > 0:
                    rate = count_values / interval
                    request_rate_gauge.add_metric([endpoint, method], rate)
        
        metrics.append(request_counter)
        metrics.append(error_counter)
        metrics.append(response_time_gauge)
        metrics.append(response_time_histogram)
        metrics.append(request_rate_gauge)
        
        # Reset tracking for next interval
        self.response_times = {k: [] for k in self.response_times.keys()}
        
        return metrics
    
    def _collect_error_metrics(self) -> List[Any]:
        """
        Collect application error metrics.
        
        Returns:
            List of error metrics
        """
        metrics = []
        
        # General application error counter
        error_counter = CounterMetricFamily(
            f"{self.app_name}_errors_total",
            "Total number of application errors",
            labels=["error_type"]
        )
        
        # Add each error type
        for error_type, count in self.error_counts.items():
            error_counter.add_metric([error_type], count)
        
        metrics.append(error_counter)
        
        return metrics
    
    def _collect_business_metrics(self) -> List[Any]:
        """
        Collect business logic metrics.
        
        Returns:
            List of business metrics
        """
        metrics = []
        
        # Business metrics as gauges
        for name, value in self.business_metrics.items():
            # Extract labels if present (format: "name{label1=value1,label2=value2}")
            labels = {}
            metric_name = name
            
            if "{" in name and name.endswith("}"):
                parts = name.split("{", 1)
                metric_name = parts[0]
                label_str = parts[1][:-1]  # Remove trailing '}'
                
                # Parse labels
                for label_pair in label_str.split(","):
                    if "=" in label_pair:
                        label_name, label_value = label_pair.split("=", 1)
                        labels[label_name.strip()] = label_value.strip()
            
            # Create metric with these labels
            if labels:
                label_names = list(labels.keys())
                label_values = [labels[k] for k in label_names]
                
                gauge = GaugeMetricFamily(
                    f"{self.app_name}_business_{metric_name}",
                    f"Business metric: {metric_name}",
                    labels=label_names
                )
                gauge.add_metric(label_values, value)
                metrics.append(gauge)
            else:
                # No labels, simple gauge
                gauge = GaugeMetricFamily(
                    f"{self.app_name}_business_{metric_name}",
                    f"Business metric: {metric_name}",
                    labels=[]
                )
                gauge.add_metric([], value)
                metrics.append(gauge)
        
        return metrics
    
    def _collect_cache_metrics(self) -> List[Any]:
        """
        Collect cache performance metrics.
        
        Returns:
            List of cache metrics
        """
        metrics = []
        
        # Cache hit counter
        cache_hit_counter = CounterMetricFamily(
            f"{self.app_name}_cache_hits_total",
            "Total number of cache hits",
            labels=["cache_name"]
        )
        
        # Cache miss counter
        cache_miss_counter = CounterMetricFamily(
            f"{self.app_name}_cache_misses_total",
            "Total number of cache misses",
            labels=["cache_name"]
        )
        
        # Cache hit ratio
        cache_hit_ratio_gauge = GaugeMetricFamily(
            f"{self.app_name}_cache_hit_ratio",
            "Cache hit ratio (hits / total)",
            labels=["cache_name"]
        )
        
        # Process each cache's metrics
        for cache_name in set(list(self.cache_hits.keys()) + list(self.cache_misses.keys())):
            hits = self.cache_hits.get(cache_name, 0)
            misses = self.cache_misses.get(cache_name, 0)
            
            cache_hit_counter.add_metric([cache_name], hits)
            cache_miss_counter.add_metric([cache_name], misses)
            
            # Calculate hit ratio
            total = hits + misses
            ratio = hits / total if total > 0 else 0
            cache_hit_ratio_gauge.add_metric([cache_name], ratio)
        
        metrics.append(cache_hit_counter)
        metrics.append(cache_miss_counter)
        metrics.append(cache_hit_ratio_gauge)
        
        return metrics
    
    def _collect_custom_metrics(self) -> List[Any]:
        """
        Collect custom application metrics.
        
        Returns:
            List of custom metrics
        """
        metrics = []
        
        # Process custom gauges
        for name, value_dict in self.custom_gauges.items():
            # Extract base name and labels
            base_name = name
            label_names = []
            
            # Check if this is a multi-label gauge
            if isinstance(value_dict, dict):
                # Format could be either:
                # 1. {(label1, label2): value} for multi-label
                # 2. {label: value} for single-label
                
                # Check first key to see if it's a tuple (multi-label)
                first_key = next(iter(value_dict.keys()), None)
                
                if isinstance(first_key, tuple):
                    # Multi-label case
                    num_labels = len(first_key)
                    label_names = [f"label{i}" for i in range(num_labels)]
                    
                    gauge = GaugeMetricFamily(
                        f"{self.app_name}_custom_{base_name}",
                        f"Custom metric: {base_name}",
                        labels=label_names
                    )
                    
                    for label_values, value in value_dict.items():
                        if isinstance(label_values, tuple):
                            gauge.add_metric(list(label_values), value)
                        else:
                            # Handle case with only one label
                            gauge.add_metric([label_values], value)
                else:
                    # Single label case where the label name is the key
                    gauge = GaugeMetricFamily(
                        f"{self.app_name}_custom_{base_name}",
                        f"Custom metric: {base_name}",
                        labels=["key"]
                    )
                    
                    for label, value in value_dict.items():
                        gauge.add_metric([str(label)], value)
                
                metrics.append(gauge)
            else:
                # Simple gauge with no labels
                gauge = GaugeMetricFamily(
                    f"{self.app_name}_custom_{base_name}",
                    f"Custom metric: {base_name}"
                )
                gauge.add_metric([], value_dict)
                metrics.append(gauge)
        
        # Process custom counters (similar logic as gauges)
        for name, value_dict in self.custom_counters.items():
            base_name = name
            
            # Check if this is a multi-label counter
            if isinstance(value_dict, dict):
                first_key = next(iter(value_dict.keys()), None)
                
                if isinstance(first_key, tuple):
                    # Multi-label case
                    num_labels = len(first_key)
                    label_names = [f"label{i}" for i in range(num_labels)]
                    
                    counter = CounterMetricFamily(
                        f"{self.app_name}_custom_counter_{base_name}",
                        f"Custom counter: {base_name}",
                        labels=label_names
                    )
                    
                    for label_values, value in value_dict.items():
                        if isinstance(label_values, tuple):
                            counter.add_metric(list(label_values), value)
                        else:
                            counter.add_metric([label_values], value)
                else:
                    # Single label case
                    counter = CounterMetricFamily(
                        f"{self.app_name}_custom_counter_{base_name}",
                        f"Custom counter: {base_name}",
                        labels=["key"]
                    )
                    
                    for label, value in value_dict.items():
                        counter.add_metric([str(label)], value)
                
                metrics.append(counter)
            else:
                # Simple counter with no labels
                counter = CounterMetricFamily(
                    f"{self.app_name}_custom_counter_{base_name}",
                    f"Custom counter: {base_name}"
                )
                counter.add_metric([], value_dict)
                metrics.append(counter)
        
        return metrics
    
    def register_metric_callback(self, callback: Callable[['ApplicationCollector'], None]):
        """
        Register a callback function to be called during metric collection.
        
        This allows external systems to add metrics to this collector by 
        calling the collector's methods to update metrics.
        
        Args:
            callback: Function that takes this collector as an argument
        """
        self.metric_callbacks.append(callback)
    
    def track_request(self, endpoint: str, method: str, duration: float, error: str = None):
        """
        Track an API request.
        
        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST, etc.)
            duration: Request duration in seconds
            error: Error type, if any
        """
        key = f"{endpoint}:{method}"
        
        # Initialize if needed
        if key not in self.request_counts:
            self.request_counts[key] = 0
            self.request_errors[key] = {}
            self.response_times[key] = []
            self.last_request_time[key] = time.time()
        
        # Update metrics
        self.request_counts[key] += 1
        self.response_times[key].append(duration)
        self.last_request_time[key] = time.time()
        
        # Track error if present
        if error:
            if error not in self.request_errors[key]:
                self.request_errors[key][error] = 0
            self.request_errors[key][error] += 1
            
            # Also track in general errors
            self.track_error(error)
    
    def track_error(self, error_type: str, count: int = 1):
        """
        Track an application error.
        
        Args:
            error_type: Type of error
            count: Number of occurrences to add
        """
        if error_type not in self.error_counts:
            self.error_counts[error_type] = 0
        
        self.error_counts[error_type] += count
    
    def set_business_metric(self, name: str, value: float):
        """
        Set a business metric value.
        
        Args:
            name: Name of the metric (can include labels in format 'name{label1=value1,label2=value2}')
            value: Current value
        """
        self.business_metrics[name] = value
    
    def track_cache_hit(self, cache_name: str):
        """
        Track a cache hit.
        
        Args:
            cache_name: Name of the cache
        """
        if cache_name not in self.cache_hits:
            self.cache_hits[cache_name] = 0
        
        self.cache_hits[cache_name] += 1
    
    def track_cache_miss(self, cache_name: str):
        """
        Track a cache miss.
        
        Args:
            cache_name: Name of the cache
        """
        if cache_name not in self.cache_misses:
            self.cache_misses[cache_name] = 0
        
        self.cache_misses[cache_name] += 1
    
    def set_gauge(self, name: str, value: float, labels: Dict = None):
        """
        Set a custom gauge metric.
        
        Args:
            name: Name of the gauge
            value: Current value
            labels: Optional dict of labels
        """
        if labels:
            if name not in self.custom_gauges:
                self.custom_gauges[name] = {}
            
            # Convert labels dict to tuple of values for multi-label
            if len(labels) > 1:
                label_key = tuple(labels.values())
            else:
                # Single label case - use the value directly
                label_key = next(iter(labels.values()))
            
            self.custom_gauges[name][label_key] = value
        else:
            # Simple gauge with no labels
            self.custom_gauges[name] = value
    
    def increment_counter(self, name: str, value: float = 1.0, labels: Dict = None):
        """
        Increment a custom counter metric.
        
        Args:
            name: Name of the counter
            value: Amount to increment by
            labels: Optional dict of labels
        """
        if labels:
            if name not in self.custom_counters:
                self.custom_counters[name] = {}
            
            # Convert labels dict to tuple of values for multi-label
            if len(labels) > 1:
                label_key = tuple(labels.values())
            else:
                # Single label case - use the value directly
                label_key = next(iter(labels.values()))
            
            if label_key not in self.custom_counters[name]:
                self.custom_counters[name][label_key] = 0
            
            self.custom_counters[name][label_key] += value
        else:
            # Simple counter with no labels
            if name not in self.custom_counters:
                self.custom_counters[name] = 0
            
            self.custom_counters[name] += value
    
    def create_flask_middleware(self):
        """
        Create a Flask middleware for request tracking.
        
        Returns:
            A function that can be used as a Flask before_request/after_request handler
        """
        def _before_request():
            from flask import request, g
            g.start_time = time.time()
        
        def _after_request(response):
            from flask import request, g
            
            if hasattr(g, 'start_time'):
                duration = time.time() - g.start_time
                endpoint = request.path
                method = request.method
                
                # Track error status codes (4xx, 5xx)
                error = None
                if response.status_code >= 400:
                    error = f"status_{response.status_code}"
                
                self.track_request(endpoint, method, duration, error)
            
            return response
        
        return {'before_request': _before_request, 'after_request': _after_request}
    
    def create_fastapi_middleware(self):
        """
        Create a FastAPI middleware for request tracking.
        
        Returns:
            A FastAPI middleware class
        """
        collector = self
        
        class FastAPIMiddleware:
            async def __call__(self, request, call_next):
                import time
                
                start_time = time.time()
                response = await call_next(request)
                duration = time.time() - start_time
                
                endpoint = request.url.path
                method = request.method
                
                # Track error status codes (4xx, 5xx)
                error = None
                if response.status_code >= 400:
                    error = f"status_{response.status_code}"
                
                collector.track_request(endpoint, method, duration, error)
                
                return response
        
        return FastAPIMiddleware()
    
    def reset_metrics(self):
        """Reset all metrics to initial state."""
        # Keep the dictionary keys but reset the values
        self.request_counts = {k: 0 for k in self.request_counts.keys()}
        self.request_errors = {k: {} for k in self.request_errors.keys()}
        self.response_times = {k: [] for k in self.response_times.keys()}
        
        self.error_counts = {}
        self.business_metrics = {}
        
        self.cache_hits = {k: 0 for k in self.cache_hits.keys()}
        self.cache_misses = {k: 0 for k in self.cache_misses.keys()}
        
        self.custom_gauges = {}
        self.custom_counters = {} 