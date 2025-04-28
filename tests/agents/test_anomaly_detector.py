"""
Tests for the Anomaly Detector component of the health monitoring system.
"""

import pytest
import time
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from typing import Dict, List, Any

from src.agents.health_monitoring.anomaly_detector import (
    AnomalyDetector,
    AnomalyType,
    AnomalySeverity,
    TimeSeriesData
)


@pytest.fixture
def timeseries_data():
    """Fixture providing sample time series data for testing."""
    # Create a time series with a clear anomaly spike
    timestamps = [time.time() - i for i in range(100, 0, -1)]  # 100 timestamps, most recent first
    
    # Normal values with a spike in the middle
    values = [10.0 + np.random.normal(0, 1) for _ in range(100)]
    values[30] = 50.0  # Anomaly spike
    
    return TimeSeriesData(
        name="test_metric",
        timestamps=timestamps,
        values=values
    )


@pytest.fixture
def detector():
    """Fixture providing a clean anomaly detector instance for each test."""
    # Reset the singleton instance
    AnomalyDetector._instance = None
    return AnomalyDetector()


def test_detector_initialization():
    """Test that the anomaly detector initializes correctly."""
    detector = AnomalyDetector()
    
    assert hasattr(detector, "_anomaly_callbacks")
    assert hasattr(detector, "_running")
    assert hasattr(detector, "_detection_thread")
    assert detector._running is False
    assert detector._detection_interval > 0


def test_register_callback(detector):
    """Test registering and unregistering callbacks."""
    callback = Mock()
    
    # Register callback
    detector.register_callback(callback)
    assert callback in detector._anomaly_callbacks
    
    # Unregister callback
    detector.unregister_callback(callback)
    assert callback not in detector._anomaly_callbacks


def test_start_stop(detector):
    """Test starting and stopping the detector."""
    # Start
    detector.start()
    assert detector._running is True
    assert detector._detection_thread is not None
    
    # Stop
    detector.stop()
    assert detector._running is False
    assert detector._detection_thread is None


def test_detect_threshold_anomaly(detector, timeseries_data):
    """Test detection of threshold-based anomalies."""
    # Set threshold for anomaly detection
    threshold = 30.0
    
    # Detect anomalies
    anomalies = detector._detect_threshold_anomalies(
        timeseries_data,
        threshold=threshold,
        anomaly_type=AnomalyType.MEMORY_USAGE,
        lookback_window=50
    )
    
    # Verify an anomaly was detected
    assert len(anomalies) > 0
    assert anomalies[0].metric_name == "test_metric"
    assert anomalies[0].anomaly_type == AnomalyType.MEMORY_USAGE
    assert anomalies[0].value > threshold


def test_detect_zscore_anomaly(detector, timeseries_data):
    """Test detection of z-score based anomalies."""
    # Detect anomalies
    anomalies = detector._detect_zscore_anomalies(
        timeseries_data,
        z_threshold=3.0,  # 3 standard deviations
        anomaly_type=AnomalyType.CPU_USAGE,
        lookback_window=50
    )
    
    # Verify an anomaly was detected
    assert len(anomalies) > 0
    assert anomalies[0].metric_name == "test_metric"
    assert anomalies[0].anomaly_type == AnomalyType.CPU_USAGE
    assert anomalies[0].severity >= AnomalySeverity.MEDIUM


def test_detect_trend_anomaly(detector):
    """Test detection of trend-based anomalies (increasing or decreasing trends)."""
    # Create a trending time series
    timestamps = [time.time() - i for i in range(100, 0, -1)]
    
    # Increasing trend
    increasing_values = [i * 0.5 + np.random.normal(0, 1) for i in range(100)]
    increasing_data = TimeSeriesData(
        name="increasing_metric",
        timestamps=timestamps,
        values=increasing_values
    )
    
    # Detect anomalies
    anomalies = detector._detect_trend_anomalies(
        increasing_data,
        trend_threshold=0.3,  # Significant positive correlation
        anomaly_type=AnomalyType.LATENCY,
        lookback_window=50
    )
    
    # Verify an anomaly was detected
    assert len(anomalies) > 0
    assert anomalies[0].metric_name == "increasing_metric"
    assert anomalies[0].anomaly_type == AnomalyType.LATENCY
    assert "increasing" in anomalies[0].description.lower()


def test_severity_assignment(detector, timeseries_data):
    """Test proper severity assignment based on deviation magnitude."""
    minor_anomaly = detector._create_anomaly(
        timeseries_data.name,
        AnomalyType.MEMORY_USAGE,
        15.0,  # Value just above normal
        "Minor deviation",
        deviation_percent=10
    )
    
    major_anomaly = detector._create_anomaly(
        timeseries_data.name,
        AnomalyType.MEMORY_USAGE,
        50.0,  # Value significantly above normal
        "Major deviation",
        deviation_percent=150
    )
    
    critical_anomaly = detector._create_anomaly(
        timeseries_data.name,
        AnomalyType.MEMORY_USAGE,
        100.0,  # Extreme value
        "Critical deviation",
        deviation_percent=400
    )
    
    assert minor_anomaly.severity == AnomalySeverity.LOW
    assert major_anomaly.severity == AnomalySeverity.HIGH
    assert critical_anomaly.severity == AnomalySeverity.CRITICAL


def test_callback_notification(detector):
    """Test that callbacks are notified when anomalies are detected."""
    callback = Mock()
    detector.register_callback(callback)
    
    # Create an anomaly
    anomaly = detector._create_anomaly(
        "test_metric",
        AnomalyType.MEMORY_USAGE,
        50.0,
        "Test anomaly",
        deviation_percent=100
    )
    
    # Notify callbacks
    detector._notify_callbacks([anomaly])
    
    # Verify callback was called with the anomaly
    callback.assert_called_once()
    args, _ = callback.call_args
    assert len(args) == 1
    assert args[0][0] == anomaly


def test_process_time_series(detector):
    """Test end-to-end processing of time series data."""
    # Create a time series with anomalies
    timestamps = [time.time() - i for i in range(100, 0, -1)]
    
    # Values with a spike and a trend
    values = [10.0 + np.random.normal(0, 1) for _ in range(100)]
    values[30] = 50.0  # Spike anomaly
    for i in range(70, 100):
        values[i] += (i - 70) * 0.5  # Trend anomaly at the end
    
    data = TimeSeriesData(
        name="complex_metric",
        timestamps=timestamps,
        values=values
    )
    
    # Register callback
    callback = Mock()
    detector.register_callback(callback)
    
    # Process the time series
    detector._process_time_series(data)
    
    # Verify callback was called with anomalies
    assert callback.call_count > 0


def test_forex_specific_anomalies(detector):
    """Test detection of forex-specific anomalies."""
    # Create time series for trade latency
    timestamps = [time.time() - i for i in range(100, 0, -1)]
    
    # Normal latencies with increasing trend under volatility
    latencies = [50.0 + np.random.normal(0, 10) for _ in range(100)]
    for i in range(70, 100):
        latencies[i] += (i - 70) * 2  # Increasing latency trend
    
    data = TimeSeriesData(
        name="forex_trade_latency",
        timestamps=timestamps,
        values=latencies
    )
    
    # Create mock market context
    market_context = {
        "volatility": 0.8,  # High volatility
        "trading_hours": True,
        "recent_news": ["Major economic announcement"]
    }
    
    # Process with forex context
    anomalies = detector._detect_forex_anomalies(
        data,
        market_context=market_context,
        anomaly_type=AnomalyType.TRADE_LATENCY
    )
    
    # Under high volatility, increasing latency might be normal
    # Verify detection accounts for market conditions
    for anomaly in anomalies:
        assert "market context" in anomaly.description.lower()
        
    # Verify at least some anomalies were detected
    assert len(anomalies) > 0 