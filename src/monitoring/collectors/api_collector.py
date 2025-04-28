"""
API metrics collector for Prometheus.

This module collects metrics related to API usage,
including request rates, response times, and error rates.
"""

import logging
import time
from typing import Dict, List, Optional, Any

from prometheus_client import Counter, Gauge, Histogram

from .base_collector import BaseCollector

logger = logging.getLogger(__name__)


class ApiCollector(BaseCollector):
    """
    Collector for API-related metrics.
    
    Collects the following metrics:
    - Request rates by endpoint
    - Response times by endpoint
    - Error rates by endpoint and status code
    """
    
    def __init__(
        self,
        api_service=None,
        registry=None,
        collection_interval: int = 15,
        cache_ttl: int = 30,
    ):
        """
        Initialize the API metrics collector.
        
        Args:
            api_service: The API service to monitor (if applicable)
            registry: Prometheus registry to use
            collection_interval: How often to collect metrics, in seconds
            cache_ttl: How long to cache expensive operations, in seconds
        """
        self.api_service = api_service
        
        super().__init__(
            registry=registry,
            collection_interval=collection_interval,
            cache_ttl=cache_ttl,
            name="ApiCollector"
        )
        
        # In addition to metrics, we'll store some request stats
        # for differential counting and rate calculations
        self._last_request_counts = {}
        self._last_error_counts = {}
    
    def _initialize_metrics(self) -> None:
        """Initialize all API-related metrics."""
        # Counter for API requests
        self._metrics['requests'] = Counter(
            'forex_api_requests_total',
            'Total API requests',
            ['endpoint', 'method'],
            registry=self.registry
        )
        
        # Histogram for API response times
        self._metrics['response_time'] = Histogram(
            'forex_api_response_seconds',
            'API response time in seconds',
            ['endpoint'],
            buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
            registry=self.registry
        )
        
        # Counter for API errors
        self._metrics['errors'] = Counter(
            'forex_api_errors_total',
            'Total API errors',
            ['endpoint', 'method', 'status_code', 'error_type'],
            registry=self.registry
        )
        
        # Gauge for API request rate (requests per second)
        self._metrics['request_rate'] = Gauge(
            'forex_api_request_rate',
            'API requests per second',
            ['endpoint', 'method'],
            registry=self.registry
        )
        
        # Gauge for API error rate (errors per second)
        self._metrics['error_rate'] = Gauge(
            'forex_api_error_rate',
            'API errors per second',
            ['endpoint', 'method'],
            registry=self.registry
        )
        
        # Gauge for concurrent API requests
        self._metrics['concurrent_requests'] = Gauge(
            'forex_api_concurrent_requests',
            'Number of concurrent API requests',
            ['endpoint'],
            registry=self.registry
        )
    
    def _collect_metrics(self) -> None:
        """Collect current API metrics."""
        try:
            # Get request stats
            request_stats = self._cached_operation(
                'request_stats',
                self._get_request_stats
            )
            
            # Update request rates
            self._update_request_rates(request_stats)
            
            # Get error stats
            error_stats = self._cached_operation(
                'error_stats',
                self._get_error_stats
            )
            
            # Update error rates
            self._update_error_rates(error_stats)
            
            # Get concurrent requests
            concurrent = self._cached_operation(
                'concurrent_requests',
                self._get_concurrent_requests
            )
            
            # Update concurrent request gauges
            self._update_concurrent_gauges(concurrent)
            
        except Exception as e:
            logger.error(f"Error collecting API metrics: {e}")
    
    def _get_request_stats(self) -> Dict[str, Dict[str, int]]:
        """
        Get the current request counts by endpoint and method.
        
        Returns:
            Dictionary mapping endpoints to methods to request counts
        """
        try:
            # This is a placeholder. In a real implementation,
            # this would query the API service or logs.
            return {
                '/api/v1/trades': {'GET': 5000, 'POST': 2000},
                '/api/v1/orders': {'GET': 4000, 'POST': 1500, 'DELETE': 500},
                '/api/v1/accounts': {'GET': 3000},
                '/api/v1/positions': {'GET': 4500},
                '/api/v1/market-data': {'GET': 8000},
            }
        except Exception as e:
            logger.error(f"Error getting API request stats: {e}")
            return {}
    
    def _update_request_rates(self, stats: Dict[str, Dict[str, int]]) -> None:
        """
        Update the request rate gauges and counters with current values.
        
        This uses differential counting to calculate rates and increment counters.
        
        Args:
            stats: Dictionary mapping endpoints to methods to request counts
        """
        now = time.time()
        last_time = getattr(self, '_last_request_time', now)
        time_diff = now - last_time
        
        # Store current time for next calculation
        self._last_request_time = now
        
        # Only calculate rates if we have a reasonable time difference
        if time_diff < 0.001:
            logger.warning("Time difference too small for rate calculation")
            return
        
        for endpoint, methods in stats.items():
            for method, count in methods.items():
                # Get the previous count
                last_count = self._last_request_counts.get((endpoint, method), 0)
                
                # Calculate the increment
                increment = max(0, count - last_count)
                
                if increment > 0:
                    # Increment the counter
                    self._metrics['requests'].labels(
                        endpoint=endpoint,
                        method=method
                    ).inc(increment)
                
                # Calculate the rate (requests per second)
                rate = increment / time_diff
                
                # Update the rate gauge
                self._metrics['request_rate'].labels(
                    endpoint=endpoint,
                    method=method
                ).set(rate)
                
                # Store current count for next calculation
                self._last_request_counts[(endpoint, method)] = count
    
    def _get_error_stats(self) -> Dict[str, Dict[str, Dict[str, Dict[str, int]]]]:
        """
        Get the current error counts by endpoint, method, status code, and error type.
        
        Returns:
            Dictionary mapping endpoints to methods to status codes to error types to counts
        """
        try:
            # This is a placeholder. In a real implementation,
            # this would query the API service or logs.
            return {
                '/api/v1/trades': {
                    'GET': {
                        '400': {'validation': 50, 'authentication': 20},
                        '500': {'database': 10, 'internal': 5}
                    },
                    'POST': {
                        '400': {'validation': 100, 'authentication': 30},
                        '500': {'database': 15, 'internal': 8}
                    }
                },
                '/api/v1/orders': {
                    'GET': {
                        '400': {'validation': 40, 'authentication': 15},
                        '500': {'database': 8, 'internal': 4}
                    },
                    'POST': {
                        '400': {'validation': 80, 'authentication': 25},
                        '500': {'database': 12, 'internal': 6}
                    },
                    'DELETE': {
                        '400': {'validation': 20, 'authentication': 10},
                        '500': {'database': 5, 'internal': 3}
                    }
                }
            }
        except Exception as e:
            logger.error(f"Error getting API error stats: {e}")
            return {}
    
    def _update_error_rates(
        self, 
        stats: Dict[str, Dict[str, Dict[str, Dict[str, int]]]]
    ) -> None:
        """
        Update the error rate gauges and counters with current values.
        
        This uses differential counting to calculate rates and increment counters.
        
        Args:
            stats: Dictionary mapping endpoints to methods to status codes to error types to counts
        """
        now = time.time()
        last_time = getattr(self, '_last_error_time', now)
        time_diff = now - last_time
        
        # Store current time for next calculation
        self._last_error_time = now
        
        # Only calculate rates if we have a reasonable time difference
        if time_diff < 0.001:
            logger.warning("Time difference too small for rate calculation")
            return
        
        # Track total errors by endpoint and method for rate calculation
        endpoint_method_errors = {}
        
        for endpoint, methods in stats.items():
            for method, status_codes in methods.items():
                endpoint_method_key = (endpoint, method)
                endpoint_method_errors[endpoint_method_key] = 0
                
                for status_code, error_types in status_codes.items():
                    for error_type, count in error_types.items():
                        # Get the previous count
                        last_count = self._last_error_counts.get(
                            (endpoint, method, status_code, error_type), 0
                        )
                        
                        # Calculate the increment
                        increment = max(0, count - last_count)
                        
                        if increment > 0:
                            # Increment the counter
                            self._metrics['errors'].labels(
                                endpoint=endpoint,
                                method=method,
                                status_code=status_code,
                                error_type=error_type
                            ).inc(increment)
                            
                            # Add to total for rate calculation
                            endpoint_method_errors[endpoint_method_key] += increment
                        
                        # Store current count for next calculation
                        self._last_error_counts[
                            (endpoint, method, status_code, error_type)
                        ] = count
        
        # Update error rate gauges
        for (endpoint, method), total_errors in endpoint_method_errors.items():
            # Calculate the rate (errors per second)
            rate = total_errors / time_diff
            
            # Update the rate gauge
            self._metrics['error_rate'].labels(
                endpoint=endpoint,
                method=method
            ).set(rate)
    
    def _get_concurrent_requests(self) -> Dict[str, int]:
        """
        Get the current number of concurrent requests by endpoint.
        
        Returns:
            Dictionary mapping endpoints to concurrent request counts
        """
        try:
            # This is a placeholder. In a real implementation,
            # this would query the API service for active connections.
            return {
                '/api/v1/trades': 15,
                '/api/v1/orders': 12,
                '/api/v1/accounts': 8,
                '/api/v1/positions': 10,
                '/api/v1/market-data': 25,
            }
        except Exception as e:
            logger.error(f"Error getting concurrent request counts: {e}")
            return {}
    
    def _update_concurrent_gauges(self, concurrent: Dict[str, int]) -> None:
        """
        Update the concurrent request gauges with current values.
        
        Args:
            concurrent: Dictionary mapping endpoints to concurrent request counts
        """
        for endpoint, count in concurrent.items():
            self._metrics['concurrent_requests'].labels(
                endpoint=endpoint
            ).set(count)
    
    # Methods to be called from request handlers
    
    def record_request_start(self, endpoint: str, method: str) -> None:
        """
        Record the start of an API request.
        
        This increments the concurrent requests gauge and returns
        a timestamp that can be used with record_request_end.
        
        Args:
            endpoint: The API endpoint being requested
            method: The HTTP method (GET, POST, etc.)
            
        Returns:
            The current timestamp
        """
        self._metrics['concurrent_requests'].labels(endpoint=endpoint).inc()
        self._metrics['requests'].labels(endpoint=endpoint, method=method).inc()
        return time.time()
    
    def record_request_end(
        self,
        endpoint: str,
        start_time: float,
        status_code: Optional[str] = None,
        error_type: Optional[str] = None,
        method: Optional[str] = None,
    ) -> None:
        """
        Record the end of an API request.
        
        This decrements the concurrent requests gauge and records
        the response time and any errors.
        
        Args:
            endpoint: The API endpoint that was requested
            start_time: The timestamp from record_request_start
            status_code: Optional HTTP status code for errors
            error_type: Optional error type for errors
            method: The HTTP method (required for error recording)
        """
        # Calculate response time
        response_time = time.time() - start_time
        
        # Record response time
        self._metrics['response_time'].labels(endpoint=endpoint).observe(response_time)
        
        # Decrement concurrent requests
        self._metrics['concurrent_requests'].labels(endpoint=endpoint).dec()
        
        # Record errors if applicable
        if status_code and int(status_code) >= 400 and method:
            error_type = error_type or 'unknown'
            self._metrics['errors'].labels(
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                error_type=error_type
            ).inc() 