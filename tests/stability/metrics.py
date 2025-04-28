"""
Metrics Collection for Stability Tests

This module provides utilities for collecting, storing, and analyzing metrics
during stability tests. It includes mechanisms for tracking system performance,
error rates, and resource utilization.
"""

import time
import datetime
import threading
import asyncio
import logging
import os
import json
import csv
from typing import Dict, List, Any, Optional, Callable, Union, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
import statistics
import numpy as np
from collections import deque

# Configure logging
logger = logging.getLogger("stability_metrics")


class MetricType(Enum):
    """Types of metrics collected during stability tests."""
    LATENCY = "latency"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    MEMORY_USAGE = "memory_usage"
    CPU_USAGE = "cpu_usage"
    QUEUE_DEPTH = "queue_depth"
    CIRCUIT_BREAKER = "circuit_breaker"
    CUSTOM = "custom"


@dataclass
class MetricSample:
    """Single metric sample."""
    timestamp: float  # Unix timestamp
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSeries:
    """Time series for a specific metric."""
    name: str
    type: MetricType
    description: str = ""
    unit: str = ""
    samples: List[MetricSample] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)

    def add_sample(self, value: float, timestamp: Optional[float] = None,
                   labels: Optional[Dict[str, str]] = None) -> None:
        """
        Add a new sample to the series.
        
        Args:
            value: Metric value
            timestamp: Optional timestamp (current time if None)
            labels: Optional additional labels for this sample
        """
        ts = timestamp if timestamp is not None else time.time()
        sample_labels = self.labels.copy()
        if labels:
            sample_labels.update(labels)
            
        self.samples.append(MetricSample(
            timestamp=ts,
            value=value,
            labels=sample_labels
        ))

    def get_statistics(self) -> Dict[str, float]:
        """
        Calculate statistics for this metric series.
        
        Returns:
            Dictionary with statistics (min, max, avg, etc.)
        """
        if not self.samples:
            return {
                "count": 0,
                "min": None,
                "max": None,
                "avg": None,
                "median": None,
                "p95": None,
                "p99": None,
                "stddev": None
            }
            
        values = [s.value for s in self.samples]
        
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": statistics.mean(values),
            "median": statistics.median(values),
            "p95": np.percentile(values, 95),
            "p99": np.percentile(values, 99),
            "stddev": statistics.stdev(values) if len(values) > 1 else 0
        }


class MetricsCollector:
    """
    Collects and manages metrics for stability tests.
    
    This class provides a centralized way to record, store, and analyze
    various performance metrics during test execution.
    """
    
    def __init__(self, test_name: str, output_dir: str = "test_results"):
        """
        Initialize the metrics collector.
        
        Args:
            test_name: Name of the test
            output_dir: Directory to store metrics
        """
        self.test_name = test_name
        self.output_dir = output_dir
        self.start_time = time.time()
        self.metrics: Dict[str, MetricSeries] = {}
        self.lock = threading.RLock()
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"Initialized metrics collector for test: {test_name}")
        
    def register_metric(self, name: str, metric_type: MetricType, 
                        description: str = "", unit: str = "",
                        labels: Optional[Dict[str, str]] = None) -> None:
        """
        Register a new metric for collection.
        
        Args:
            name: Metric name
            metric_type: Type of metric
            description: Description of the metric
            unit: Unit of measurement (e.g., "ms", "percent")
            labels: Labels to attach to all samples
        """
        with self.lock:
            if name in self.metrics:
                logger.warning(f"Metric '{name}' already registered, ignoring")
                return
                
            self.metrics[name] = MetricSeries(
                name=name,
                type=metric_type,
                description=description,
                unit=unit,
                labels=labels or {}
            )
            
            logger.debug(f"Registered metric: {name} ({metric_type.value})")
            
    def record_value(self, name: str, value: float, 
                     timestamp: Optional[float] = None,
                     labels: Optional[Dict[str, str]] = None) -> None:
        """
        Record a value for a registered metric.
        
        Args:
            name: Metric name
            value: Metric value
            timestamp: Optional timestamp (current time if None)
            labels: Optional additional labels for this sample
        """
        with self.lock:
            if name not in self.metrics:
                logger.warning(f"Metric '{name}' not registered, ignoring")
                return
                
            self.metrics[name].add_sample(
                value=value,
                timestamp=timestamp,
                labels=labels
            )
            
    def record_latency(self, operation: str, latency_ms: float,
                       service: Optional[str] = None,
                       additional_labels: Optional[Dict[str, str]] = None) -> None:
        """
        Record a latency measurement.
        
        Args:
            operation: Operation being measured
            latency_ms: Latency in milliseconds
            service: Optional service name
            additional_labels: Optional additional labels
        """
        name = f"latency_{operation}"
        labels = {"operation": operation}
        
        if service:
            labels["service"] = service
            
        if additional_labels:
            labels.update(additional_labels)
            
        self.record_value(
            name=name,
            value=latency_ms,
            labels=labels
        )
        
    def record_error(self, operation: str, 
                     service: Optional[str] = None,
                     error_type: Optional[str] = None,
                     additional_labels: Optional[Dict[str, str]] = None) -> None:
        """
        Record an error occurrence.
        
        Args:
            operation: Operation that errored
            service: Optional service name
            error_type: Optional error type/category
            additional_labels: Optional additional labels
        """
        name = f"error_{operation}"
        labels = {"operation": operation}
        
        if service:
            labels["service"] = service
            
        if error_type:
            labels["error_type"] = error_type
            
        if additional_labels:
            labels.update(additional_labels)
            
        self.record_value(
            name=name,
            value=1.0,  # Each error is counted as 1
            labels=labels
        )
        
    def record_throughput(self, operation: str, count: float,
                         service: Optional[str] = None,
                         additional_labels: Optional[Dict[str, str]] = None) -> None:
        """
        Record throughput measurement.
        
        Args:
            operation: Operation being measured
            count: Number of operations
            service: Optional service name
            additional_labels: Optional additional labels
        """
        name = f"throughput_{operation}"
        labels = {"operation": operation}
        
        if service:
            labels["service"] = service
            
        if additional_labels:
            labels.update(additional_labels)
            
        self.record_value(
            name=name,
            value=count,
            labels=labels
        )
        
    def record_resource_usage(self, resource_type: str, value: float,
                             service: Optional[str] = None,
                             additional_labels: Optional[Dict[str, str]] = None) -> None:
        """
        Record resource usage measurement.
        
        Args:
            resource_type: Type of resource (e.g., "memory", "cpu")
            value: Resource usage value
            service: Optional service name
            additional_labels: Optional additional labels
        """
        name = f"resource_{resource_type}"
        labels = {"resource_type": resource_type}
        
        if service:
            labels["service"] = service
            
        if additional_labels:
            labels.update(additional_labels)
            
        self.record_value(
            name=name,
            value=value,
            labels=labels
        )
        
    def record_custom_metric(self, name: str, value: float,
                            labels: Optional[Dict[str, str]] = None) -> None:
        """
        Record a custom metric.
        
        Args:
            name: Metric name
            value: Metric value
            labels: Optional labels
        """
        self.record_value(
            name=name,
            value=value,
            labels=labels
        )
        
    def get_statistics(self) -> Dict[str, Dict[str, float]]:
        """
        Get statistics for all metrics.
        
        Returns:
            Dictionary mapping metric names to their statistics
        """
        with self.lock:
            return {
                name: series.get_statistics()
                for name, series in self.metrics.items()
            }
            
    def save_metrics(self, format: str = "json") -> str:
        """
        Save metrics to a file.
        
        Args:
            format: Output format ("json" or "csv")
            
        Returns:
            Path to the saved file
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"{self.test_name}_{timestamp}"
        
        if format.lower() == "json":
            return self._save_json(f"{base_filename}.json")
        elif format.lower() == "csv":
            return self._save_csv(f"{base_filename}.csv")
        else:
            logger.warning(f"Unsupported format: {format}, using JSON")
            return self._save_json(f"{base_filename}.json")
            
    def _save_json(self, filename: str) -> str:
        """
        Save metrics to a JSON file.
        
        Args:
            filename: Output filename
            
        Returns:
            Path to the saved file
        """
        file_path = os.path.join(self.output_dir, filename)
        
        with self.lock:
            # Convert metrics to serializable format
            data = {
                "test_name": self.test_name,
                "start_time": self.start_time,
                "end_time": time.time(),
                "duration": time.time() - self.start_time,
                "metrics": {}
            }
            
            for name, series in self.metrics.items():
                data["metrics"][name] = {
                    "name": series.name,
                    "type": series.type.value,
                    "description": series.description,
                    "unit": series.unit,
                    "labels": series.labels,
                    "statistics": series.get_statistics(),
                    "samples": [
                        {
                            "timestamp": sample.timestamp,
                            "value": sample.value,
                            "labels": sample.labels
                        }
                        for sample in series.samples
                    ]
                }
                
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
                
            logger.info(f"Saved metrics to: {file_path}")
            return file_path
            
    def _save_csv(self, filename: str) -> str:
        """
        Save metrics to a CSV file.
        
        Args:
            filename: Output filename
            
        Returns:
            Path to the saved file
        """
        file_path = os.path.join(self.output_dir, filename)
        
        with self.lock:
            with open(file_path, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Write header
                writer.writerow([
                    "metric_name", "timestamp", "value", "labels"
                ])
                
                # Write samples
                for name, series in self.metrics.items():
                    for sample in series.samples:
                        # Serialize labels
                        labels_str = ';'.join([
                            f"{k}={v}" for k, v in sample.labels.items()
                        ])
                        
                        writer.writerow([
                            name,
                            sample.timestamp,
                            sample.value,
                            labels_str
                        ])
                        
            logger.info(f"Saved metrics to: {file_path}")
            return file_path


class LatencyTracker:
    """
    Utility for tracking operation latency.
    
    Can be used as a context manager to time operations:
    
    ```
    with LatencyTracker(metrics_collector, "my_operation") as tracker:
        # Perform operation
        ...
    # Latency is automatically recorded
    ```
    """
    
    def __init__(self, collector: MetricsCollector, operation: str,
                service: Optional[str] = None,
                labels: Optional[Dict[str, str]] = None):
        """
        Initialize the latency tracker.
        
        Args:
            collector: Metrics collector
            operation: Operation being tracked
            service: Optional service name
            labels: Optional additional labels
        """
        self.collector = collector
        self.operation = operation
        self.service = service
        self.labels = labels
        self.start_time = None
        
    def __enter__(self) -> 'LatencyTracker':
        """Start timing as we enter the context."""
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Record latency as we exit the context."""
        if self.start_time:
            latency_ms = (time.time() - self.start_time) * 1000.0
            
            self.collector.record_latency(
                operation=self.operation,
                latency_ms=latency_ms,
                service=self.service,
                additional_labels=self.labels
            )
            
            # If there was an error, record it
            if exc_type:
                error_type = exc_type.__name__
                
                self.collector.record_error(
                    operation=self.operation,
                    service=self.service,
                    error_type=error_type,
                    additional_labels=self.labels
                )


# Global metrics collector instance (for convenience)
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """
    Get the global metrics collector instance.
    
    If no collector has been initialized, a default one is created.
    
    Returns:
        The global MetricsCollector instance
    """
    global _metrics_collector
    
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector(
            test_name="default",
            output_dir="test_results"
        )
        
    return _metrics_collector


def set_metrics_collector(collector: MetricsCollector) -> None:
    """
    Set the global metrics collector instance.
    
    Args:
        collector: MetricsCollector instance to use
    """
    global _metrics_collector
    _metrics_collector = collector 