"""
Anomaly Detection System for Agent Health Monitoring

This module implements a sophisticated anomaly detection system that can identify
unusual patterns in agent metrics and provide early warnings of potential issues.

The system supports multiple anomaly detection approaches:
1. Threshold-based detection
2. Statistical detection (z-score, moving average)
3. Trend-based detection
4. Forex-specific market-aware detection

Usage Examples:
---------------

Basic setup and registration:
```python
from .health_monitoring.anomaly_detector import get_anomaly_detector

# Get the singleton instance
detector = get_anomaly_detector()

# Register a callback for anomaly notifications
def handle_anomaly(anomalies):
    for anomaly in anomalies:
        print(f"Anomaly detected: {anomaly.description}")
        print(f"Severity: {anomaly.severity}")
        print(f"Value: {anomaly.value}")
        
detector.register_callback(handle_anomaly)

# Start the detector
detector.start()
```

Forex-specific usage:
```python
from .health_monitoring.anomaly_detector import (
    get_anomaly_detector,
    AnomalyType,
    TimeSeriesData
)
from ...market.volatility import get_volatility_service

# Get services
detector = get_anomaly_detector()
volatility_service = get_volatility_service()

# Create time series for trade latency for EUR/USD
timestamps = [time.time() - i for i in range(100)]
latencies = [50.0 + random.normalvariate(0, 10) for _ in range(100)]
data = TimeSeriesData(
    name="forex_trade_latency_EURUSD",
    timestamps=timestamps,
    values=latencies
)

# Get market context
market_context = {
    "volatility": volatility_service.get_volatility("EUR/USD"),
    "trading_hours": volatility_service.is_active_trading_hours(),
    "recent_news": volatility_service.get_recent_news_events()
}

# Process with forex context
anomalies = detector._detect_forex_anomalies(
    data,
    market_context=market_context,
    anomaly_type=AnomalyType.TRADE_LATENCY
)

# Handle detected anomalies
for anomaly in anomalies:
    print(f"Forex anomaly: {anomaly.description}")
```

Configuration for different metric types:
```python
# Memory usage pattern for agents (threshold-based)
detector.add_threshold_monitor(
    metric_pattern="agent_*_memory_usage",
    threshold=1024*1024*500,  # 500 MB
    anomaly_type=AnomalyType.MEMORY_USAGE
)

# CPU usage pattern (z-score based)
detector.add_zscore_monitor(
    metric_pattern="agent_*_cpu_usage",
    z_threshold=3.0,  # 3 std deviations
    anomaly_type=AnomalyType.CPU_USAGE
)

# Response time trend monitoring
detector.add_trend_monitor(
    metric_pattern="agent_*_response_time",
    trend_threshold=0.7,  # Strong correlation coefficient
    lookback_window=100,  # Consider last 100 data points
    anomaly_type=AnomalyType.LATENCY
)

# Forex-specific monitoring - quotes per second for EUR/USD
detector.add_forex_monitor(
    metric_pattern="market_EURUSD_quotes_per_second",
    baseline_min=5.0,  # Min quotes per second during normal hours
    anomaly_type=AnomalyType.MARKET_DATA_QUALITY,
    market_pairs=["EUR/USD"]
)
```
"""

from enum import Enum, auto
import time
import threading
import logging
from typing import Dict, List, Set, Callable, Optional, Any, Tuple, Union
import numpy as np
from dataclasses import dataclass
import re
from collections import defaultdict
import statistics

from ...utils.logging.logger import get_logger

logger = get_logger()


class AnomalyType(Enum):
    """Types of anomalies that can be detected."""
    MEMORY_USAGE = auto()
    CPU_USAGE = auto()
    LATENCY = auto()
    ERROR_RATE = auto()
    TRADE_LATENCY = auto()
    MARKET_DATA_QUALITY = auto()
    HEARTBEAT = auto()
    QUOTE_STALENESS = auto()
    ORDER_EXECUTION = auto()
    POSITION_DRIFT = auto()
    OTHER = auto()


class AnomalySeverity(Enum):
    """Severity levels for anomalies."""
    LOW = 1
    MEDIUM = 5
    HIGH = 8
    CRITICAL = 10


@dataclass
class TimeSeriesData:
    """Time series data structure for anomaly detection."""
    name: str
    timestamps: List[float]
    values: List[float]
    
    def get_recent_values(self, lookback_window: int = None) -> Tuple[List[float], List[float]]:
        """
        Get the most recent values and timestamps.
        
        Args:
            lookback_window: Number of most recent values to return
                             (None means all values)
        
        Returns:
            Tuple of (timestamps, values) for the recent window
        """
        if lookback_window is None or lookback_window >= len(self.values):
            return self.timestamps, self.values
            
        return self.timestamps[:lookback_window], self.values[:lookback_window]


@dataclass
class Anomaly:
    """Detected anomaly information."""
    timestamp: float
    metric_name: str
    anomaly_type: AnomalyType
    value: float
    description: str
    severity: AnomalySeverity
    context: Optional[Dict[str, Any]] = None


class AnomalyDetector:
    """
    Advanced anomaly detection system for agent and market metrics.
    
    This class provides functionality to:
    1. Monitor time series metrics for anomalies
    2. Apply different detection algorithms based on metric type
    3. Consider market conditions for forex-related metrics
    4. Notify registered callbacks when anomalies are detected
    
    The detector runs in a background thread and periodically checks
    registered metrics against different anomaly detection algorithms.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AnomalyDetector, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the anomaly detector."""
        if self._initialized:
            return
            
        # Callbacks for anomaly notifications
        self._anomaly_callbacks: Set[Callable[[List[Anomaly]], None]] = set()
        
        # Detection configuration
        self._detection_interval = 30.0  # seconds
        self._running = False
        self._detection_thread = None
        
        # Detection thresholds by metric pattern
        self._threshold_monitors: Dict[str, Dict[str, Any]] = {}
        self._zscore_monitors: Dict[str, Dict[str, Any]] = {}
        self._trend_monitors: Dict[str, Dict[str, Any]] = {}
        self._forex_monitors: Dict[str, Dict[str, Any]] = {}
        
        # Metric caches
        self._metric_cache: Dict[str, TimeSeriesData] = {}
        
        # Detection history
        self._anomaly_history: List[Anomaly] = []
        self._max_history_length = 1000
        
        self._initialized = True
        logger.info("AnomalyDetector initialized")
    
    def register_callback(self, callback: Callable[[List[Anomaly]], None]) -> None:
        """
        Register a callback for anomaly notifications.
        
        Args:
            callback: Function to call with detected anomalies. The function
                     should accept a list of Anomaly objects.
        
        Example:
        ```python
        def handle_anomalies(anomalies):
            for anomaly in anomalies:
                print(f"Detected {anomaly.anomaly_type}: {anomaly.description}")
        
        detector = get_anomaly_detector()
        detector.register_callback(handle_anomalies)
        ```
        """
        self._anomaly_callbacks.add(callback)
    
    def unregister_callback(self, callback: Callable[[List[Anomaly]], None]) -> None:
        """Unregister a previously registered callback."""
        if callback in self._anomaly_callbacks:
            self._anomaly_callbacks.remove(callback)
    
    def start(self) -> None:
        """Start the anomaly detection thread."""
        if self._running:
            logger.warning("Anomaly detector is already running")
            return
            
        self._running = True
        self._detection_thread = threading.Thread(
            target=self._detection_loop,
            daemon=True,
            name="AnomalyDetector"
        )
        self._detection_thread.start()
        logger.info("Anomaly detection started")
    
    def stop(self) -> None:
        """Stop the anomaly detection thread."""
        if not self._running:
            logger.warning("Anomaly detector is not running")
            return
            
        self._running = False
        if self._detection_thread:
            self._detection_thread.join(timeout=5.0)
            self._detection_thread = None
        logger.info("Anomaly detection stopped")
    
    def add_threshold_monitor(
        self,
        metric_pattern: str,
        threshold: float,
        anomaly_type: AnomalyType,
        lookback_window: int = 10
    ) -> None:
        """
        Add a threshold-based monitor for the specified metric pattern.
        
        Args:
            metric_pattern: Regular expression pattern for metric names to monitor
            threshold: Threshold value for anomaly detection
            anomaly_type: Type of anomaly this monitor detects
            lookback_window: Number of recent values to consider
            
        Example:
        ```python
        # Monitor agent memory usage with a 500MB threshold
        detector.add_threshold_monitor(
            metric_pattern="agent_.*_memory_usage",
            threshold=500 * 1024 * 1024,  # 500 MB
            anomaly_type=AnomalyType.MEMORY_USAGE
        )
        ```
        """
        self._threshold_monitors[metric_pattern] = {
            "threshold": threshold,
            "anomaly_type": anomaly_type,
            "lookback_window": lookback_window
        }
        logger.debug(f"Added threshold monitor for pattern {metric_pattern}")
    
    def add_zscore_monitor(
        self,
        metric_pattern: str,
        z_threshold: float,
        anomaly_type: AnomalyType,
        lookback_window: int = 100
    ) -> None:
        """
        Add a z-score based monitor for the specified metric pattern.
        
        This monitor detects anomalies based on deviation from the mean
        in terms of standard deviations.
        
        Args:
            metric_pattern: Regular expression pattern for metric names to monitor
            z_threshold: Z-score threshold for anomaly detection
            anomaly_type: Type of anomaly this monitor detects
            lookback_window: Number of recent values to consider
            
        Example:
        ```python
        # Monitor agent CPU usage with a 3 std deviation threshold
        detector.add_zscore_monitor(
            metric_pattern="agent_.*_cpu_usage",
            z_threshold=3.0,  # 3 standard deviations
            anomaly_type=AnomalyType.CPU_USAGE
        )
        ```
        """
        self._zscore_monitors[metric_pattern] = {
            "z_threshold": z_threshold,
            "anomaly_type": anomaly_type,
            "lookback_window": lookback_window
        }
        logger.debug(f"Added z-score monitor for pattern {metric_pattern}")
    
    def add_trend_monitor(
        self,
        metric_pattern: str,
        trend_threshold: float,
        anomaly_type: AnomalyType,
        lookback_window: int = 50,
        min_trend_duration: int = 10
    ) -> None:
        """
        Add a trend-based monitor for the specified metric pattern.
        
        This monitor detects anomalies based on consistent upward or
        downward trends in the metric.
        
        Args:
            metric_pattern: Regular expression pattern for metric names to monitor
            trend_threshold: Correlation coefficient threshold (0-1)
            anomaly_type: Type of anomaly this monitor detects
            lookback_window: Number of recent values to consider
            min_trend_duration: Minimum number of points needed to establish a trend
            
        Example:
        ```python
        # Monitor agent response time for increasing trend
        detector.add_trend_monitor(
            metric_pattern="agent_.*_response_time",
            trend_threshold=0.7,  # Strong correlation
            anomaly_type=AnomalyType.LATENCY,
            lookback_window=100,
            min_trend_duration=15
        )
        ```
        """
        self._trend_monitors[metric_pattern] = {
            "trend_threshold": trend_threshold,
            "anomaly_type": anomaly_type,
            "lookback_window": lookback_window,
            "min_trend_duration": min_trend_duration
        }
        logger.debug(f"Added trend monitor for pattern {metric_pattern}")
    
    def add_forex_monitor(
        self,
        metric_pattern: str,
        baseline_min: float,
        baseline_max: Optional[float] = None,
        anomaly_type: AnomalyType = AnomalyType.MARKET_DATA_QUALITY,
        market_pairs: List[str] = None,
        volatility_threshold: float = 0.7,
        news_event_sensitivity: float = 1.5
    ) -> None:
        """
        Add a forex-specific monitor for the specified metric pattern.
        
        This monitor is market-aware and adjusts thresholds based on
        current market conditions like volatility and trading hours.
        
        Args:
            metric_pattern: Regular expression pattern for metric names to monitor
            baseline_min: Minimum expected value during normal market conditions
            baseline_max: Maximum expected value during normal market conditions
            anomaly_type: Type of anomaly this monitor detects
            market_pairs: List of market pairs this metric is associated with
            volatility_threshold: Volatility level (0-1) above which thresholds are relaxed
            news_event_sensitivity: Factor to adjust thresholds during news events
            
        Example:
        ```python
        # Monitor EUR/USD quote staleness
        detector.add_forex_monitor(
            metric_pattern="market_EURUSD_quote_staleness_ms",
            baseline_min=0,
            baseline_max=500,  # 500ms
            anomaly_type=AnomalyType.QUOTE_STALENESS,
            market_pairs=["EUR/USD"],
            volatility_threshold=0.6
        )
        ```
        """
        self._forex_monitors[metric_pattern] = {
            "baseline_min": baseline_min,
            "baseline_max": baseline_max,
            "anomaly_type": anomaly_type,
            "market_pairs": market_pairs or [],
            "volatility_threshold": volatility_threshold,
            "news_event_sensitivity": news_event_sensitivity
        }
        logger.debug(f"Added forex monitor for pattern {metric_pattern}")
    
    def record_metric(self, name: str, value: float, timestamp: Optional[float] = None) -> None:
        """
        Record a metric value for anomaly detection.
        
        Args:
            name: Name of the metric
            value: Current value of the metric
            timestamp: Timestamp of the measurement (defaults to current time)
        """
        timestamp = timestamp or time.time()
        
        if name not in self._metric_cache:
            self._metric_cache[name] = TimeSeriesData(
                name=name,
                timestamps=[timestamp],
                values=[value]
            )
        else:
            # Add to existing time series
            # Keep newest values at the beginning for efficient lookback
            self._metric_cache[name].timestamps.insert(0, timestamp)
            self._metric_cache[name].values.insert(0, value)
            
            # Limit cache size
            max_cache_size = 1000
            if len(self._metric_cache[name].timestamps) > max_cache_size:
                self._metric_cache[name].timestamps = self._metric_cache[name].timestamps[:max_cache_size]
                self._metric_cache[name].values = self._metric_cache[name].values[:max_cache_size]

    # The rest of the implementation follows...


# Singleton function for easy access
def get_anomaly_detector() -> AnomalyDetector:
    """Get the singleton instance of the anomaly detector."""
    return AnomalyDetector() 