"""
Test Harness Configuration Module

This module provides configuration classes and utilities for defining test scenarios,
including market data simulation parameters, execution settings, and reporting options.
"""

import os
import yaml
import json
from enum import Enum
from typing import Dict, List, Optional, Union, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, validator


class MarketDataType(str, Enum):
    """Types of market data to generate."""
    TICK = "tick"
    TRADE = "trade"
    ORDER_BOOK = "order_book"
    CANDLE = "candle"


class OrderType(str, Enum):
    """Types of orders to generate."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class PatternType(str, Enum):
    """Market pattern types for data generation."""
    NORMAL = "normal"
    VOLATILE = "volatile"
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGE_BOUND = "range_bound"
    OPENING = "opening"
    CLOSING = "closing"
    CUSTOM = "custom"
    CYCLICAL = "cyclical"
    MULTI_PHASE = "multi_phase"
    STRESS_TEST = "stress_test"


class ExecutionMode(str, Enum):
    """Test execution modes."""
    LOCAL = "local"
    DISTRIBUTED = "distributed"
    HYBRID = "hybrid"


class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class MarketDataConfig(BaseModel):
    """Configuration for market data generation."""
    data_type: MarketDataType = Field(default=MarketDataType.TICK, description="Type of market data to generate")
    symbols: List[str] = Field(default=["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"], description="Symbols to generate data for")
    rate: int = Field(default=1000, ge=1, description="Ticks per second to generate")
    burst_rate: Optional[int] = Field(default=None, description="Burst rate for spike scenarios (ticks per second)")
    pattern: PatternType = Field(default=PatternType.NORMAL, description="Market pattern to simulate")
    volatility: float = Field(default=0.0002, ge=0, description="Base volatility level (e.g., 0.0002 = 0.02%)")
    custom_pattern_path: Optional[str] = Field(default=None, description="Path to custom pattern definition file")
    realistic_spreads: bool = Field(default=True, description="Use realistic, variable spreads based on volatility")
    
    # Cyclical pattern parameters
    cycle_amplitude: float = Field(default=0.01, ge=0, description="Amplitude of price cycles as percentage (e.g., 0.01 = 1%)")
    cycle_frequency: float = Field(default=0.005, ge=0, description="Frequency of price cycles (cycles per tick)")
    cycle_phase_offset: float = Field(default=0, description="Starting phase offset for cyclical patterns")
    
    # Multi-phase pattern parameters
    phases: Optional[List[Dict[str, Any]]] = Field(default=None, description="List of phases for multi-phase patterns")
    transition_ticks: int = Field(default=500, ge=0, description="Number of ticks for smooth transition between phases")
    
    # Stress test pattern parameters
    base_pattern: PatternType = Field(default=PatternType.NORMAL, description="Base pattern for stress test")
    stress_events: Optional[List[Dict[str, Any]]] = Field(default=None, description="List of stress events to simulate")

    @validator('burst_rate')
    def burst_rate_must_be_greater_than_rate(cls, v, values):
        if v is not None and 'rate' in values and v <= values['rate']:
            raise ValueError(f"burst_rate ({v}) must be greater than rate ({values['rate']})")
        return v


class OrderGenerationConfig(BaseModel):
    """Configuration for order generation."""
    enabled: bool = Field(default=False, description="Whether to generate orders")
    order_types: List[OrderType] = Field(default=[OrderType.MARKET, OrderType.LIMIT], description="Types of orders to generate")
    rate: float = Field(default=10, ge=0, description="Orders per second to generate")
    burst_rate: Optional[float] = Field(default=None, description="Burst rate for spike scenarios (orders per second)")
    burst_duration: Optional[float] = Field(default=None, description="Duration of burst in seconds")
    size_min: float = Field(default=0.1, ge=0, description="Minimum order size")
    size_max: float = Field(default=10.0, ge=0, description="Maximum order size")
    correlated_to_market: bool = Field(default=True, description="Whether orders should correlate with market movements")

    @validator('size_max')
    def size_max_must_be_greater_than_min(cls, v, values):
        if 'size_min' in values and v <= values['size_min']:
            raise ValueError(f"size_max ({v}) must be greater than size_min ({values['size_min']})")
        return v


class DistributedConfig(BaseModel):
    """Configuration for distributed test execution."""
    enabled: bool = Field(default=False, description="Whether to use distributed execution")
    worker_count: int = Field(default=1, ge=1, description="Number of worker nodes")
    redis_url: str = Field(default="redis://localhost:6379", description="Redis URL for coordination")
    timeout: int = Field(default=30, ge=1, description="Timeout for worker coordination in seconds")


class MetricsConfig(BaseModel):
    """Configuration for metrics collection."""
    enabled: bool = Field(default=True, description="Whether to collect metrics")
    interval: float = Field(default=1.0, ge=0.1, description="Metrics collection interval in seconds")
    prometheus_export: bool = Field(default=False, description="Whether to export metrics to Prometheus")
    prometheus_port: int = Field(default=8000, ge=1, description="Prometheus exporter port")
    system_metrics: bool = Field(default=True, description="Whether to collect system metrics (CPU, memory, etc.)")
    application_metrics: bool = Field(default=True, description="Whether to collect application metrics")
    output_path: Optional[str] = Field(default=None, description="Path to write metrics data")


class ReportingConfig(BaseModel):
    """Configuration for test reporting."""
    formats: List[str] = Field(default=["json"], description="Report formats to generate (json, csv, html)")
    output_dir: str = Field(default="./reports", description="Directory for report output")
    include_charts: bool = Field(default=True, description="Whether to include charts in reports")
    include_system_info: bool = Field(default=True, description="Whether to include system information in reports")
    include_raw_data: bool = Field(default=False, description="Whether to include raw data in reports")


class ScenarioConfig(BaseModel):
    """Configuration for a test scenario."""
    name: str = Field(..., description="Scenario name")
    description: Optional[str] = Field(default=None, description="Scenario description")
    duration: float = Field(default=60.0, ge=0.1, description="Test duration in seconds")
    warmup_period: float = Field(default=5.0, ge=0, description="Warmup period in seconds")
    cooldown_period: float = Field(default=5.0, ge=0, description="Cooldown period in seconds")
    market_data: MarketDataConfig = Field(default_factory=MarketDataConfig, description="Market data generation settings")
    order_generation: OrderGenerationConfig = Field(default_factory=OrderGenerationConfig, description="Order generation settings")
    distributed: DistributedConfig = Field(default_factory=DistributedConfig, description="Distributed execution settings")
    metrics: MetricsConfig = Field(default_factory=MetricsConfig, description="Metrics collection settings")
    reporting: ReportingConfig = Field(default_factory=ReportingConfig, description="Reporting settings")
    tags: List[str] = Field(default=[], description="Tags for categorizing scenarios")


class TestHarnessConfig(BaseModel):
    """Master configuration for the test harness."""
    name: str = Field(default="Test Harness", description="Test harness name")
    description: Optional[str] = Field(default=None, description="Test harness description")
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Logging level")
    execution_mode: ExecutionMode = Field(default=ExecutionMode.LOCAL, description="Test execution mode")
    scenarios: List[ScenarioConfig] = Field(default=[], description="Test scenarios")
    base_output_dir: str = Field(default="./test_results", description="Base directory for all test outputs")
    global_metrics: MetricsConfig = Field(default_factory=MetricsConfig, description="Global metrics settings")
    global_reporting: ReportingConfig = Field(default_factory=ReportingConfig, description="Global reporting settings")

    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'TestHarnessConfig':
        """
        Load configuration from a YAML file.
        
        Args:
            yaml_path: Path to YAML configuration file
            
        Returns:
            TestHarnessConfig instance
        """
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"Configuration file not found: {yaml_path}")
            
        with open(yaml_path, 'r') as f:
            config_dict = yaml.safe_load(f)
            
        return cls(**config_dict)
        
    @classmethod
    def from_json(cls, json_path: str) -> 'TestHarnessConfig':
        """
        Load configuration from a JSON file.
        
        Args:
            json_path: Path to JSON configuration file
            
        Returns:
            TestHarnessConfig instance
        """
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"Configuration file not found: {json_path}")
            
        with open(json_path, 'r') as f:
            config_dict = json.load(f)
            
        return cls(**config_dict)
        
    def to_yaml(self, yaml_path: str) -> None:
        """
        Save configuration to a YAML file.
        
        Args:
            yaml_path: Path to save YAML configuration
        """
        os.makedirs(os.path.dirname(os.path.abspath(yaml_path)), exist_ok=True)
        
        with open(yaml_path, 'w') as f:
            yaml.dump(self.dict(), f, default_flow_style=False)
            
    def to_json(self, json_path: str) -> None:
        """
        Save configuration to a JSON file.
        
        Args:
            json_path: Path to save JSON configuration
        """
        os.makedirs(os.path.dirname(os.path.abspath(json_path)), exist_ok=True)
        
        with open(json_path, 'w') as f:
            json.dump(self.dict(), f, indent=2) 