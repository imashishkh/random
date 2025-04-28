"""
Stability Test Configuration

This module provides configuration utilities for stability tests, including
test duration, load patterns, and metric collection settings.
"""

from typing import Dict, Any, List, Optional, Union
import os
import json
import logging
from dataclasses import dataclass, field
from enum import Enum

# Configure logging for tests
logger = logging.getLogger("stability_tests")


class TestDuration(Enum):
    """Test duration categories."""
    SHORT = "short"           # < 5 minutes (for quick smoke tests)
    MEDIUM = "medium"         # 5-60 minutes
    LONG = "long"             # 1-8 hours
    EXTENDED = "extended"     # > 8 hours (for overnight tests)


class LoadPattern(Enum):
    """Load pattern types for stability tests."""
    CONSTANT = "constant"     # Consistent load
    RAMP = "ramp"             # Gradually increasing load
    STEP = "step"             # Step-wise increases
    BURST = "burst"           # Short bursts of high load
    OSCILLATING = "oscillating"  # Varying load with peaks and valleys
    RANDOM = "random"         # Randomized load pattern


class NetworkCondition(Enum):
    """Network condition types for stability tests."""
    NORMAL = "normal"         # Normal network conditions
    HIGH_LATENCY = "high_latency"  # Increased response time
    PACKET_LOSS = "packet_loss"    # Random packet loss
    JITTER = "jitter"         # Variable latency
    BANDWIDTH_LIMIT = "bandwidth_limit"  # Reduced bandwidth
    PARTITION = "partition"   # Network partitions between components


@dataclass
class NetworkConfig:
    """Network condition configuration."""
    condition: NetworkCondition = NetworkCondition.NORMAL
    latency_ms: int = 0                # Added latency in milliseconds
    latency_variance_ms: int = 0       # Latency jitter in milliseconds
    packet_loss_percent: float = 0.0   # Percentage of packets to drop
    bandwidth_limit_kbps: Optional[int] = None  # Bandwidth limit in Kbps
    partition_duration_sec: float = 0.0  # Duration of network partition in seconds
    partition_interval_sec: float = 0.0  # Interval between partitions


@dataclass
class LoadConfig:
    """Load generation configuration."""
    pattern: LoadPattern = LoadPattern.CONSTANT
    base_rate: float = 1.0             # Base rate (orders/second, etc.)
    peak_rate: float = 10.0            # Peak rate for variable patterns
    ramp_duration_sec: float = 60.0    # Duration of ramp for RAMP pattern
    step_levels: List[float] = field(default_factory=lambda: [1.0, 2.0, 5.0, 10.0])
    step_duration_sec: float = 30.0    # Duration of each step
    burst_duration_sec: float = 5.0    # Duration of bursts
    burst_interval_sec: float = 60.0   # Interval between bursts
    oscillation_period_sec: float = 60.0  # Period of oscillation


@dataclass
class StabilityTestConfig:
    """Main configuration for stability tests."""
    name: str
    description: str = ""
    duration: TestDuration = TestDuration.MEDIUM
    duration_seconds: float = 300.0    # Actual test duration in seconds
    
    # Load configuration
    load_config: LoadConfig = field(default_factory=LoadConfig)
    
    # Network configuration
    network_config: NetworkConfig = field(default_factory=NetworkConfig)
    
    # Metric collection settings
    collect_metrics: bool = True
    metric_interval_sec: float = 1.0
    
    # Output settings
    output_dir: str = "test_results"
    save_results: bool = True


def load_config_from_file(file_path: str) -> StabilityTestConfig:
    """
    Load test configuration from a JSON file.
    
    Args:
        file_path: Path to the configuration file
        
    Returns:
        Loaded test configuration
    """
    try:
        with open(file_path, 'r') as f:
            config_data = json.load(f)
        
        # Create base config
        config = StabilityTestConfig(
            name=config_data.get('name', 'Unnamed Test'),
            description=config_data.get('description', ''),
            duration=TestDuration(config_data.get('duration', 'medium')),
            duration_seconds=config_data.get('duration_seconds', 300.0),
            collect_metrics=config_data.get('collect_metrics', True),
            metric_interval_sec=config_data.get('metric_interval_sec', 1.0),
            output_dir=config_data.get('output_dir', 'test_results'),
            save_results=config_data.get('save_results', True)
        )
        
        # Configure load if present
        if 'load_config' in config_data:
            lc = config_data['load_config']
            config.load_config = LoadConfig(
                pattern=LoadPattern(lc.get('pattern', 'constant')),
                base_rate=lc.get('base_rate', 1.0),
                peak_rate=lc.get('peak_rate', 10.0),
                ramp_duration_sec=lc.get('ramp_duration_sec', 60.0),
                step_levels=lc.get('step_levels', [1.0, 2.0, 5.0, 10.0]),
                step_duration_sec=lc.get('step_duration_sec', 30.0),
                burst_duration_sec=lc.get('burst_duration_sec', 5.0),
                burst_interval_sec=lc.get('burst_interval_sec', 60.0),
                oscillation_period_sec=lc.get('oscillation_period_sec', 60.0)
            )
            
        # Configure network if present
        if 'network_config' in config_data:
            nc = config_data['network_config']
            config.network_config = NetworkConfig(
                condition=NetworkCondition(nc.get('condition', 'normal')),
                latency_ms=nc.get('latency_ms', 0),
                latency_variance_ms=nc.get('latency_variance_ms', 0),
                packet_loss_percent=nc.get('packet_loss_percent', 0.0),
                bandwidth_limit_kbps=nc.get('bandwidth_limit_kbps', None),
                partition_duration_sec=nc.get('partition_duration_sec', 0.0),
                partition_interval_sec=nc.get('partition_interval_sec', 0.0)
            )
            
        return config
    
    except Exception as e:
        logger.error(f"Error loading config from {file_path}: {e}")
        # Return default config
        return StabilityTestConfig(name=f"Default (Error loading {os.path.basename(file_path)})")


def get_default_config(test_name: str) -> StabilityTestConfig:
    """
    Get a default configuration for a stability test.
    
    Args:
        test_name: Name of the test
        
    Returns:
        Default test configuration
    """
    return StabilityTestConfig(
        name=test_name,
        description=f"Default configuration for {test_name}",
        duration=TestDuration.MEDIUM,
        duration_seconds=300.0
    ) 