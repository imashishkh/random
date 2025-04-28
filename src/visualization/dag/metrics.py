"""
Performance metrics collection for the DAG visualization.

This module provides a collector that pulls metrics from the agent health monitoring
system and adapts them for use in the visualization.
"""

import time
import logging
from typing import Dict, Any, Optional, List

# Import the metrics collector from the health monitoring system
try:
    from src.agents.health_monitoring.metrics_collector import (
        MetricsCollector, 
        MetricType
    )
except ImportError:
    # If the actual metrics collector isn't available, use a mock
    class MetricType:
        """Mock metric types"""
        RESPONSE_TIME_MS = "response_time_ms"
        MEMORY_USAGE_MB = "memory_usage_mb"
        CPU_USAGE_PERCENT = "cpu_usage_percent"
        COMPLETION_RATE = "completion_rate"
        ERROR_RATE = "error_rate"
        THROUGHPUT = "throughput"
        TASK_QUEUE_SIZE = "task_queue_size"

    class MetricsCollector:
        """Mock metrics collector"""
        def get_agent_metrics(self, agent_id):
            return {}
        
        def get_health_score(self, agent_id):
            return 0.5

# Set up logging
logger = logging.getLogger(__name__)


class PerformanceMetricsCollector:
    """
    Collects and caches performance metrics for the DAG visualization.
    
    This class acts as a bridge between the health monitoring metrics system
    and the DAG visualization, with caching to prevent excessive metric fetching.
    """
    
    def __init__(self, refresh_interval: float = 2.0):
        """
        Initialize the performance metrics collector.
        
        Args:
            refresh_interval: Minimum time between refreshes in seconds
        """
        self.metrics_collector = MetricsCollector()
        self.min_refresh_interval = refresh_interval
        self.last_refresh_time = 0
        self.metrics_cache: Dict[str, Dict[str, Any]] = {}
        self.health_score_cache: Dict[str, float] = {}
        self.adaptive_interval = refresh_interval
        
    def refresh_metrics(self, force: bool = False) -> bool:
        """
        Refresh the metrics cache if enough time has passed.
        
        Args:
            force: Whether to force a refresh regardless of the time interval
            
        Returns:
            Whether the metrics were refreshed
        """
        current_time = time.time()
        
        # Check if it's time to refresh
        if not force and current_time - self.last_refresh_time < self.adaptive_interval:
            return False
            
        self.last_refresh_time = current_time
        
        try:
            # This will be expanded later to actually fetch and cache metrics
            return True
        except Exception as e:
            logger.error(f"Error refreshing metrics: {str(e)}")
            return False
            
    def get_agent_metrics(self, agent_id: str) -> Dict[str, Any]:
        """
        Get metrics for an agent, using the cache if available.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Dictionary of metric data
        """
        # Refresh metrics if needed
        self.refresh_metrics()
        
        # If we have cached metrics, return those
        if agent_id in self.metrics_cache:
            return self.metrics_cache[agent_id]
            
        # Otherwise get from the collector
        try:
            metrics = self.metrics_collector.get_agent_metrics(agent_id)
            if metrics:
                self.metrics_cache[agent_id] = metrics
                return metrics
        except Exception as e:
            logger.error(f"Error getting metrics for agent {agent_id}: {str(e)}")
            
        return {}
        
    def get_health_score(self, agent_id: str) -> float:
        """
        Get the health score for an agent.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Health score from 0.0 (unhealthy) to 1.0 (healthy)
        """
        # Refresh metrics if needed
        self.refresh_metrics()
        
        # If we have a cached score, return it
        if agent_id in self.health_score_cache:
            return self.health_score_cache[agent_id]
            
        # Otherwise calculate from the collector
        try:
            score = self.metrics_collector.get_health_score(agent_id)
            self.health_score_cache[agent_id] = score
            return score
        except Exception as e:
            logger.error(f"Error getting health score for agent {agent_id}: {str(e)}")
            
        return 0.5  # Default neutral score
        
    def get_metric_trend(self, agent_id: str, metric_type: str, 
                        window: int = 5) -> Optional[float]:
        """
        Calculate the trend for a specific metric (positive = increasing, negative = decreasing).
        
        Args:
            agent_id: Agent ID
            metric_type: Type of metric
            window: Number of data points to use for trend calculation
            
        Returns:
            Trend value or None if insufficient data
        """
        try:
            # Get the metric values
            values = self.metrics_collector.get_metric_values(agent_id, metric_type, window=300)
            
            if len(values) < 2:
                return None
                
            # Use the last 'window' values or all if fewer
            values = values[-min(window, len(values)):]
            
            if len(values) >= 2:
                # Calculate slope as a simple trend indicator
                return (values[-1] - values[0]) / len(values)
        except Exception as e:
            logger.error(f"Error calculating metric trend: {str(e)}")
            
        return None
    
    def update_adaptive_interval(self, render_time: float, node_count: int) -> None:
        """
        Update the adaptive refresh interval based on rendering performance.
        
        Args:
            render_time: Time taken to render in seconds
            node_count: Number of nodes in the graph
        """
        # Base interval on rendering time and node count
        # More nodes or longer render time = longer interval
        if render_time > 0:
            # Scale between 0.5s (small graph, fast render) and 5s (large graph, slow render)
            scale_factor = min(1.0, (render_time * (node_count / 10)) / 2.0)
            new_interval = 0.5 + (4.5 * scale_factor)
            
            # Smooth transition to new value (70% old, 30% new)
            self.adaptive_interval = (0.7 * self.adaptive_interval) + (0.3 * new_interval)
            
            # Ensure we stay within reasonable bounds
            self.adaptive_interval = max(0.5, min(5.0, self.adaptive_interval))
            
    def get_metrics_summary(self, agent_id: str) -> Dict[str, Any]:
        """
        Get a summarized view of metrics with key health indicators.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Dictionary of summarized metrics
        """
        metrics = self.get_agent_metrics(agent_id)
        health_score = self.get_health_score(agent_id)
        
        summary = {
            "health_score": health_score,
            "status": self._get_health_status(health_score),
            "key_metrics": {},
            "trends": {}
        }
        
        # Extract key metrics
        for key in ["response_time_ms", "memory_usage_mb", "cpu_usage_percent", 
                   "error_rate", "completion_rate"]:
            if key in metrics:
                summary["key_metrics"][key] = {
                    "latest": metrics[key].get("latest"),
                    "average": metrics[key].get("average")
                }
                
                # Add trend
                trend = self.get_metric_trend(agent_id, key)
                if trend is not None:
                    summary["trends"][key] = trend
        
        return summary
    
    def _get_health_status(self, score: float) -> str:
        """Convert a health score to a status string."""
        if score >= 0.9:
            return "excellent"
        elif score >= 0.75:
            return "good"
        elif score >= 0.5:
            return "fair"
        elif score >= 0.25:
            return "poor"
        else:
            return "critical" 