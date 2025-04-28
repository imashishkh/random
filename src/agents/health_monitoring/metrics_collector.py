import time
import logging
import statistics
from enum import Enum
from typing import Dict, List, Set, Optional, Any, Callable, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

class MetricType(str, Enum):
    """Types of metrics that can be collected for agent health monitoring"""
    RESPONSE_TIME_MS = "response_time_ms"
    MEMORY_USAGE_MB = "memory_usage_mb"
    CPU_USAGE_PERCENT = "cpu_usage_percent"
    COMPLETION_RATE = "completion_rate"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    TASK_QUEUE_SIZE = "task_queue_size"
    TOKEN_USAGE = "token_usage"
    API_CALLS = "api_calls"
    CUSTOM = "custom"

class MetricDataPoint:
    """Individual data point for a metric"""
    def __init__(self, value: float, timestamp: Optional[float] = None):
        self.value = value
        self.timestamp = timestamp or time.time()
        
    def __repr__(self) -> str:
        return f"DataPoint({self.value}, {self.timestamp})"

class MetricSeries:
    """Time series collection of metric data points"""
    def __init__(self, max_points: int = 1000, max_age: Optional[float] = None):
        """
        Initialize a new metric series
        
        Args:
            max_points: Maximum number of data points to keep
            max_age: Maximum age of data points in seconds (None = no limit)
        """
        self.data_points = deque(maxlen=max_points)
        self.max_age = max_age
        self.last_cleaned = time.time()
        self.min_value = float('inf')
        self.max_value = float('-inf')
        self._sum = 0.0
        self._count = 0
        
    def add_data_point(self, data_point: MetricDataPoint) -> None:
        """Add a new data point to the series"""
        self.data_points.append(data_point)
        self._sum += data_point.value
        self._count += 1
        
        # Update min/max tracking
        self.min_value = min(self.min_value, data_point.value)
        self.max_value = max(self.max_value, data_point.value)
        
        # Clean old data points if needed
        current_time = time.time()
        if self.max_age is not None and current_time - self.last_cleaned > 60:
            self._clean_old_data_points(current_time)
            self.last_cleaned = current_time
    
    def _clean_old_data_points(self, current_time: float) -> None:
        """Remove data points older than max_age"""
        if self.max_age is None:
            return
            
        cutoff_time = current_time - self.max_age
        
        # Count how many points to remove
        points_to_remove = 0
        for dp in self.data_points:
            if dp.timestamp <= cutoff_time:
                points_to_remove += 1
            else:
                break
                
        # Remove old points and update statistics
        if points_to_remove > 0:
            removed_sum = 0
            for _ in range(points_to_remove):
                dp = self.data_points.popleft()
                removed_sum += dp.value
                
            self._sum -= removed_sum
            self._count -= points_to_remove
            
            # Recalculate min/max if any points were removed
            if self.data_points:
                self.min_value = min(dp.value for dp in self.data_points)
                self.max_value = max(dp.value for dp in self.data_points)
            else:
                self.min_value = float('inf')
                self.max_value = float('-inf')
    
    def get_values(self, window: Optional[float] = None) -> List[float]:
        """
        Get values from the data points, optionally filtered by age
        
        Args:
            window: Time window in seconds to filter data points (None = all points)
            
        Returns:
            List of values from the data points
        """
        if not self.data_points:
            return []
            
        if window is None:
            return [dp.value for dp in self.data_points]
            
        cutoff_time = time.time() - window
        return [dp.value for dp in self.data_points if dp.timestamp >= cutoff_time]
    
    def get_timestamps(self, window: Optional[float] = None) -> List[float]:
        """
        Get timestamps from the data points, optionally filtered by age
        
        Args:
            window: Time window in seconds to filter data points (None = all points)
            
        Returns:
            List of timestamps from the data points
        """
        if not self.data_points:
            return []
            
        if window is None:
            return [dp.timestamp for dp in self.data_points]
            
        cutoff_time = time.time() - window
        return [dp.timestamp for dp in self.data_points if dp.timestamp >= cutoff_time]
    
    def get_as_xy_pairs(self, window: Optional[float] = None) -> List[Tuple[float, float]]:
        """
        Get data points as (timestamp, value) pairs, optionally filtered by age
        
        Args:
            window: Time window in seconds to filter data points (None = all points)
            
        Returns:
            List of (timestamp, value) tuples
        """
        if not self.data_points:
            return []
            
        if window is None:
            return [(dp.timestamp, dp.value) for dp in self.data_points]
            
        cutoff_time = time.time() - window
        return [(dp.timestamp, dp.value) for dp in self.data_points if dp.timestamp >= cutoff_time]
        
    def get_average(self, window: Optional[float] = None) -> Optional[float]:
        """
        Get the average value from the data points, optionally filtered by age
        
        Args:
            window: Time window in seconds to calculate average (None = all points)
            
        Returns:
            Average value or None if no data points
        """
        values = self.get_values(window)
        if not values:
            return None
        return sum(values) / len(values)
    
    def get_percentile(self, percentile: float, window: Optional[float] = None) -> Optional[float]:
        """
        Get a percentile value from the data points
        
        Args:
            percentile: Percentile to calculate (0-100)
            window: Time window in seconds to filter data points (None = all points)
            
        Returns:
            Percentile value or None if no data points
        """
        values = self.get_values(window)
        if not values:
            return None
        
        try:
            return statistics.quantiles(values, n=100)[int(percentile)-1] if int(percentile) > 0 else min(values)
        except (ValueError, IndexError):
            # If not enough data for percentiles, fall back to sorted values
            sorted_values = sorted(values)
            index = int((percentile / 100) * (len(sorted_values) - 1))
            return sorted_values[index]
    
    def get_max(self, window: Optional[float] = None) -> Optional[float]:
        """
        Get the maximum value from the data points, optionally filtered by age
        
        Args:
            window: Time window in seconds to filter data points (None = all points)
            
        Returns:
            Maximum value or None if no data points
        """
        if window is None and self.data_points:
            return self.max_value
            
        values = self.get_values(window)
        if not values:
            return None
        return max(values)
    
    def get_min(self, window: Optional[float] = None) -> Optional[float]:
        """
        Get the minimum value from the data points, optionally filtered by age
        
        Args:
            window: Time window in seconds to filter data points (None = all points)
            
        Returns:
            Minimum value or None if no data points
        """
        if window is None and self.data_points:
            return self.min_value
            
        values = self.get_values(window)
        if not values:
            return None
        return min(values)
    
    def get_stddev(self, window: Optional[float] = None) -> Optional[float]:
        """
        Get the standard deviation from the data points
        
        Args:
            window: Time window in seconds to filter data points (None = all points)
            
        Returns:
            Standard deviation or None if insufficient data points
        """
        values = self.get_values(window)
        if len(values) < 2:
            return None
        
        try:
            return statistics.stdev(values)
        except statistics.StatisticsError:
            return None
    
    def get_data_points_count(self, window: Optional[float] = None) -> int:
        """
        Get the number of data points, optionally filtered by age
        
        Args:
            window: Time window in seconds to filter data points (None = all points)
            
        Returns:
            Number of data points
        """
        if window is None:
            return len(self.data_points)
            
        cutoff_time = time.time() - window
        return sum(1 for dp in self.data_points if dp.timestamp >= cutoff_time)
    
    def get_anomalies(self, z_threshold: float = 3.0, window: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Detect anomalies in the data points based on z-score
        
        Args:
            z_threshold: Z-score threshold for anomaly detection
            window: Time window in seconds to filter data points (None = all points)
            
        Returns:
            List of anomalies as dictionaries
        """
        values = self.get_values(window)
        timestamps = self.get_timestamps(window)
        
        if len(values) < 4:  # Need a minimum number of points for meaningful detection
            return []
            
        try:
            mean = statistics.mean(values)
            stdev = statistics.stdev(values)
            
            if stdev == 0:
                return []
                
            anomalies = []
            for i, value in enumerate(values):
                z_score = abs((value - mean) / stdev)
                if z_score > z_threshold:
                    anomalies.append({
                        "value": value,
                        "timestamp": timestamps[i],
                        "z_score": z_score,
                        "mean": mean,
                        "stdev": stdev
                    })
            
            return anomalies
        except statistics.StatisticsError:
            return []


class MetricsCollector:
    """
    Collector for agent metrics used in health monitoring.
    Handles storing, analyzing, and detecting anomalies in metrics.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MetricsCollector, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        # Main data structures
        self._agent_metrics: Dict[str, Dict[str, MetricSeries]] = defaultdict(dict)
        self._anomaly_callbacks: Set[Callable] = set()
        
        # Metric weights for health score calculation
        self._metric_weights = {
            MetricType.RESPONSE_TIME_MS: 0.2,
            MetricType.MEMORY_USAGE_MB: 0.15,
            MetricType.CPU_USAGE_PERCENT: 0.15,
            MetricType.COMPLETION_RATE: 0.2,
            MetricType.ERROR_RATE: 0.2,
            MetricType.THROUGHPUT: 0.1,
            MetricType.TASK_QUEUE_SIZE: 0.1,
            MetricType.TOKEN_USAGE: 0.05,
            MetricType.API_CALLS: 0.05,
            MetricType.CUSTOM: 0.05
        }
        
        # Anomaly detection settings
        self._anomaly_z_threshold = 3.0
        self._anomaly_check_window = 300  # 5 minutes
        
        self._initialized = True
    
    def register_agent(self, agent_id: str) -> None:
        """Register an agent for metrics collection"""
        if agent_id not in self._agent_metrics:
            self._agent_metrics[agent_id] = {}
            logger.info(f"Agent '{agent_id}' registered with metrics collector")
    
    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent from metrics collection"""
        if agent_id in self._agent_metrics:
            del self._agent_metrics[agent_id]
            logger.info(f"Agent '{agent_id}' unregistered from metrics collector")
    
    def record_metric(self, agent_id: str, metric_type: MetricType, value: float) -> None:
        """
        Record a metric value for an agent
        
        Args:
            agent_id: Agent ID
            metric_type: Type of metric
            value: Metric value
        """
        if agent_id not in self._agent_metrics:
            self.register_agent(agent_id)
            
        # Create metric series if it doesn't exist
        if metric_type.value not in self._agent_metrics[agent_id]:
            max_age = 86400  # 24 hours retention by default
            self._agent_metrics[agent_id][metric_type.value] = MetricSeries(max_age=max_age)
            
        # Record the data point
        data_point = MetricDataPoint(value)
        self._agent_metrics[agent_id][metric_type.value].add_data_point(data_point)
        
        # Check for anomalies
        self._check_for_anomalies(agent_id, metric_type)
    
    def _check_for_anomalies(self, agent_id: str, metric_type: MetricType) -> None:
        """
        Check for anomalies in a metric series
        
        Args:
            agent_id: Agent ID
            metric_type: Type of metric
        """
        if not self._anomaly_callbacks:
            return  # Skip if no callbacks registered
            
        if agent_id not in self._agent_metrics:
            return
            
        if metric_type.value not in self._agent_metrics[agent_id]:
            return
            
        series = self._agent_metrics[agent_id][metric_type.value]
        
        # Need at least a few data points for anomaly detection
        if series.get_data_points_count(self._anomaly_check_window) < 4:
            return
            
        # Detect anomalies
        anomalies = series.get_anomalies(
            z_threshold=self._anomaly_z_threshold,
            window=self._anomaly_check_window
        )
        
        # Notify about the most recent anomaly if any
        if anomalies:
            most_recent = max(anomalies, key=lambda a: a["timestamp"])
            anomaly_info = {
                "agent_id": agent_id,
                "metric_type": metric_type.value,
                "value": most_recent["value"],
                "timestamp": most_recent["timestamp"],
                "z_score": most_recent["z_score"],
                "mean": most_recent["mean"],
                "std_dev": most_recent["stdev"]
            }
            
            logger.warning(
                f"Anomaly detected for agent '{agent_id}', metric '{metric_type.value}': "
                f"value={most_recent['value']}, z-score={most_recent['z_score']:.2f}"
            )
            
            # Notify all registered callbacks
            for callback in self._anomaly_callbacks:
                try:
                    callback(anomaly_info)
                except Exception as e:
                    logger.error(f"Error in anomaly callback: {str(e)}")
    
    def register_anomaly_callback(self, callback: Callable) -> None:
        """Register a callback to be notified of metric anomalies"""
        self._anomaly_callbacks.add(callback)
    
    def unregister_anomaly_callback(self, callback: Callable) -> None:
        """Unregister an anomaly callback"""
        self._anomaly_callbacks.discard(callback)
    
    def get_metric_values(
        self, 
        agent_id: str, 
        metric_type: MetricType, 
        window: Optional[float] = None
    ) -> List[float]:
        """
        Get values for a specific metric
        
        Args:
            agent_id: Agent ID
            metric_type: Type of metric
            window: Time window in seconds (None = all available data)
            
        Returns:
            List of metric values
        """
        if agent_id not in self._agent_metrics:
            return []
            
        if metric_type.value not in self._agent_metrics[agent_id]:
            return []
            
        return self._agent_metrics[agent_id][metric_type.value].get_values(window)
    
    def get_metric_series(
        self, 
        agent_id: str, 
        metric_type: MetricType
    ) -> Optional[MetricSeries]:
        """
        Get the metric series for a specific metric
        
        Args:
            agent_id: Agent ID
            metric_type: Type of metric
            
        Returns:
            MetricSeries object or None if not found
        """
        if agent_id not in self._agent_metrics:
            return None
            
        if metric_type.value not in self._agent_metrics[agent_id]:
            return None
            
        return self._agent_metrics[agent_id][metric_type.value]
    
    def get_agent_metrics(self, agent_id: str) -> Dict[str, Dict[str, float]]:
        """
        Get all metrics for an agent with summary statistics
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Dictionary of metrics and their summary statistics
        """
        if agent_id not in self._agent_metrics:
            return {}
            
        result = {}
        
        for metric_name, series in self._agent_metrics[agent_id].items():
            # Use a 5-minute window for recent statistics
            window = 300
            
            avg = series.get_average(window)
            min_val = series.get_min(window)
            max_val = series.get_max(window)
            p95 = series.get_percentile(95, window)
            count = series.get_data_points_count(window)
            
            # Skip metrics with no recent data
            if count == 0:
                continue
                
            result[metric_name] = {
                "average": avg,
                "min": min_val,
                "max": max_val,
                "p95": p95,
                "count": count,
                "latest": series.get_values(window)[-1] if count > 0 else None
            }
            
        return result
    
    def get_health_score(self, agent_id: str) -> float:
        """
        Calculate a health score for an agent based on its metrics
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Health score from 0.0 (unhealthy) to 1.0 (healthy)
        """
        if agent_id not in self._agent_metrics:
            return 0.0
            
        # Define score contribution for each metric
        scores = {}
        
        # Response time: lower is better
        if MetricType.RESPONSE_TIME_MS.value in self._agent_metrics[agent_id]:
            series = self._agent_metrics[agent_id][MetricType.RESPONSE_TIME_MS.value]
            avg = series.get_average(300)  # 5-minute window
            
            if avg is not None:
                # Scale response time score (assuming 2000ms is bad, 100ms is good)
                # Clamping to range [0, 1]
                normalized_score = max(0.0, min(1.0, 1.0 - (avg - 100) / 1900))
                scores[MetricType.RESPONSE_TIME_MS.value] = normalized_score
        
        # Memory usage: lower is better but contextual
        if MetricType.MEMORY_USAGE_MB.value in self._agent_metrics[agent_id]:
            series = self._agent_metrics[agent_id][MetricType.MEMORY_USAGE_MB.value]
            recent_values = series.get_values(300)  # 5-minute window
            
            if recent_values:
                # Look for rapid growth rather than absolute value
                if len(recent_values) >= 2:
                    earliest = recent_values[0]
                    latest = recent_values[-1]
                    
                    if earliest > 0:
                        growth_ratio = latest / earliest
                        # Penalize growth over 50% in 5 minutes
                        normalized_score = max(0.0, min(1.0, 1.0 - (growth_ratio - 1.0) / 0.5))
                        scores[MetricType.MEMORY_USAGE_MB.value] = normalized_score
        
        # CPU usage: lower is better
        if MetricType.CPU_USAGE_PERCENT.value in self._agent_metrics[agent_id]:
            series = self._agent_metrics[agent_id][MetricType.CPU_USAGE_PERCENT.value]
            avg = series.get_average(300)  # 5-minute window
            
            if avg is not None:
                # Scale CPU usage score (0-100%)
                normalized_score = max(0.0, min(1.0, 1.0 - avg / 100.0))
                scores[MetricType.CPU_USAGE_PERCENT.value] = normalized_score
        
        # Completion rate: higher is better
        if MetricType.COMPLETION_RATE.value in self._agent_metrics[agent_id]:
            series = self._agent_metrics[agent_id][MetricType.COMPLETION_RATE.value]
            avg = series.get_average(300)  # 5-minute window
            
            if avg is not None:
                # Direct mapping as it's already 0-1
                normalized_score = max(0.0, min(1.0, avg))
                scores[MetricType.COMPLETION_RATE.value] = normalized_score
        
        # Error rate: lower is better
        if MetricType.ERROR_RATE.value in self._agent_metrics[agent_id]:
            series = self._agent_metrics[agent_id][MetricType.ERROR_RATE.value]
            avg = series.get_average(300)  # 5-minute window
            
            if avg is not None:
                # Scale error rate (assuming 0-100%)
                normalized_score = max(0.0, min(1.0, 1.0 - avg))
                scores[MetricType.ERROR_RATE.value] = normalized_score
        
        # Calculate weighted average if we have any scores
        if not scores:
            return 0.5  # No data, return neutral score
            
        weighted_sum = 0.0
        total_weight = 0.0
        
        for metric_name, score in scores.items():
            metric_type = MetricType(metric_name)
            weight = self._metric_weights.get(metric_type, 0.1)
            
            weighted_sum += score * weight
            total_weight += weight
            
        if total_weight == 0:
            return 0.5
            
        return weighted_sum / total_weight
    
    def set_anomaly_detection_parameters(
        self, 
        z_threshold: float = 3.0, 
        check_window: float = 300
    ) -> None:
        """
        Set parameters for anomaly detection
        
        Args:
            z_threshold: Z-score threshold for anomaly detection
            check_window: Time window in seconds for analysis
        """
        self._anomaly_z_threshold = max(1.0, z_threshold)
        self._anomaly_check_window = max(60, check_window)
        logger.info(
            f"Anomaly detection parameters updated: z_threshold={self._anomaly_z_threshold}, "
            f"check_window={self._anomaly_check_window}s"
        )
    
    def set_metric_weight(self, metric_type: MetricType, weight: float) -> None:
        """
        Set the weight for a metric in health score calculation
        
        Args:
            metric_type: Type of metric
            weight: Weight value (0.0 - 1.0)
        """
        self._metric_weights[metric_type] = max(0.0, min(1.0, weight))
        
        # Normalize weights
        total = sum(self._metric_weights.values())
        if total > 0:
            for mt in self._metric_weights:
                self._metric_weights[mt] /= total 