"""
Agent Health SDK

This module provides a simple client API for agents to report their health status
and metrics to the health monitoring system.
"""

import time
import json
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime

from ...utils.logging.logger import get_logger

logger = get_logger()


class HealthStatus(str, Enum):
    """Health status enum for agents"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNRESPONSIVE = "unresponsive"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Results from a health check"""
    agent_id: str
    status: HealthStatus
    message: str
    timestamp: float = field(default_factory=time.time)
    details: Dict[str, Any] = field(default_factory=dict)


class AgentHealthClient:
    """
    Simple client for agents to report health information.
    
    This class provides methods for sending heartbeats, reporting health metrics,
    and registering for health checks with the monitoring system.
    """
    
    def __init__(
        self, 
        agent_id: str,
        agent_type: str,
        health_monitor_service: Optional[Any] = None,
        heartbeat_interval_seconds: int = 30,
        enable_forex_metrics: bool = False,
        market_pairs: Optional[List[str]] = None
    ):
        """
        Initialize the health client.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_type: Type of agent (e.g., 'trader', 'analyzer')
            health_monitor_service: Optional health monitor service reference
            heartbeat_interval_seconds: How often to send automatic heartbeats 
            enable_forex_metrics: Whether to enable forex-specific metrics
            market_pairs: List of market pairs (required if forex metrics enabled)
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.health_monitor_service = health_monitor_service
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.enable_forex_metrics = enable_forex_metrics
        self.market_pairs = market_pairs or []
        
        # Verify market pairs are provided if forex metrics are enabled
        if enable_forex_metrics and not market_pairs:
            logger.warning("Forex metrics enabled but no market pairs provided")
            
        # Internal state
        self._last_heartbeat = 0
        self._automatic_heartbeat_enabled = False
        self._heartbeat_thread = None
        
        # Initialize forex-specific metrics containers if needed
        if enable_forex_metrics:
            self._trade_latencies = {pair: [] for pair in self.market_pairs}
            self._last_quote_times = {pair: 0 for pair in self.market_pairs}
            self._market_data_gaps = {pair: 0 for pair in self.market_pairs}
            
        # Register with health monitor if provided
        if health_monitor_service:
            health_monitor_service.register_agent(agent_id, agent_type)
            logger.info(f"Agent {agent_id} registered with health monitoring service")
    
    def send_heartbeat(self, metrics: Optional[Dict[str, Any]] = None):
        """
        Send a heartbeat to the health monitoring service.
        
        Args:
            metrics: Optional metrics to include with the heartbeat
        """
        self._last_heartbeat = time.time()
        
        if not self.health_monitor_service:
            logger.debug(f"Heartbeat generated for agent {self.agent_id} but no monitor service available")
            return
            
        # Create default metrics if none provided
        if metrics is None:
            metrics = {}
            
        # Add forex-specific metrics if enabled
        if self.enable_forex_metrics:
            forex_metrics = self._collect_forex_metrics()
            metrics.update(forex_metrics)
            
        # Send to health monitor service
        try:
            self.health_monitor_service.receive_heartbeat(self.agent_id, metrics)
            logger.debug(f"Heartbeat sent for agent {self.agent_id}")
        except Exception as e:
            logger.error(f"Error sending heartbeat: {str(e)}")
    
    def start_automatic_heartbeats(self):
        """
        Start sending automatic heartbeats at the configured interval.
        """
        import threading
        
        if self._automatic_heartbeat_enabled:
            logger.warning("Automatic heartbeats already enabled")
            return
            
        self._automatic_heartbeat_enabled = True
        
        def heartbeat_loop():
            """Internal function to send periodic heartbeats"""
            while self._automatic_heartbeat_enabled:
                try:
                    self.send_heartbeat()
                    time.sleep(self.heartbeat_interval_seconds)
                except Exception as e:
                    logger.error(f"Error in heartbeat loop: {str(e)}")
                    time.sleep(5)  # Shorter sleep on error
        
        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=heartbeat_loop,
            daemon=True,
            name=f"health-heartbeat-{self.agent_id}"
        )
        self._heartbeat_thread.start()
        logger.info(f"Started automatic heartbeats for agent {self.agent_id}")
    
    def stop_automatic_heartbeats(self):
        """
        Stop sending automatic heartbeats.
        """
        if not self._automatic_heartbeat_enabled:
            return
            
        self._automatic_heartbeat_enabled = False
        
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2.0)
            logger.info(f"Stopped automatic heartbeats for agent {self.agent_id}")
    
    def report_success(self, response_time_ms: Optional[float] = None):
        """
        Report a successful operation to the health monitoring system.
        
        Args:
            response_time_ms: Response time in milliseconds
        """
        if not self.health_monitor_service:
            return
            
        metrics = {}
        if response_time_ms is not None:
            metrics["response_time_ms"] = response_time_ms
            
        self.send_heartbeat(metrics)
    
    def report_failure(self, error: str):
        """
        Report a failed operation to the health monitoring system.
        
        Args:
            error: Error message or description of the failure
        """
        if not self.health_monitor_service:
            return
            
        metrics = {
            "error": error,
            "error_count": 1
        }
            
        self.send_heartbeat(metrics)
    
    def report_health_check(self, status: HealthStatus, message: str, details: Optional[Dict[str, Any]] = None):
        """
        Report a health check result to the monitoring system.
        
        Args:
            status: Health status from the check
            message: Human-readable message describing the health status
            details: Optional additional details about the health check
        """
        if not self.health_monitor_service:
            return
            
        result = HealthCheckResult(
            agent_id=self.agent_id,
            status=status,
            message=message,
            details=details or {}
        )
        
        self.health_monitor_service.record_health_check(self.agent_id, result)
    
    def record_memory_usage(self, memory_mb: float):
        """
        Record current memory usage.
        
        Args:
            memory_mb: Memory usage in megabytes
        """
        self.send_heartbeat({"memory_usage_mb": memory_mb})
    
    def record_cpu_usage(self, cpu_percent: float):
        """
        Record current CPU usage.
        
        Args:
            cpu_percent: CPU usage percentage (0-100)
        """
        self.send_heartbeat({"cpu_usage_percent": cpu_percent})
    
    def record_task_queue_size(self, queue_size: int):
        """
        Record current task queue size.
        
        Args:
            queue_size: Number of tasks in the queue
        """
        self.send_heartbeat({"task_queue_size": queue_size})
    
    def record_token_usage(self, tokens: int):
        """
        Record token usage from LLM calls.
        
        Args:
            tokens: Number of tokens used
        """
        self.send_heartbeat({"token_usage": tokens})
    
    # Forex-specific methods
    
    def record_trade_latency(self, market_pair: str, latency_ms: float):
        """
        Record trade execution latency for a market pair.
        
        Args:
            market_pair: Market pair (e.g., 'EUR/USD')
            latency_ms: Latency in milliseconds
        """
        if not self.enable_forex_metrics:
            return
            
        if market_pair not in self._trade_latencies:
            logger.warning(f"Market pair {market_pair} not registered with health client")
            return
            
        # Record latency
        self._trade_latencies[market_pair].append(latency_ms)
        
        # Keep history manageable
        if len(self._trade_latencies[market_pair]) > 100:
            self._trade_latencies[market_pair] = self._trade_latencies[market_pair][-100:]
            
        # Send heartbeat with updated data
        self.send_heartbeat()
    
    def update_quote_time(self, market_pair: str, quote_time: Optional[float] = None):
        """
        Update the timestamp of the latest quote for a market pair.
        
        Args:
            market_pair: Market pair (e.g., 'EUR/USD')
            quote_time: Timestamp of the quote (defaults to current time)
        """
        if not self.enable_forex_metrics:
            return
            
        if market_pair not in self._last_quote_times:
            logger.warning(f"Market pair {market_pair} not registered with health client")
            return
            
        # If no time provided, use current time
        if quote_time is None:
            quote_time = time.time()
            
        # Check for potential gap in data
        if self._last_quote_times[market_pair] > 0:
            expected_interval = self._get_expected_quote_interval(market_pair)
            actual_interval = quote_time - self._last_quote_times[market_pair]
            
            # If gap is significant, record it
            if actual_interval > expected_interval * 2:
                self._market_data_gaps[market_pair] += 1
                logger.debug(f"Market data gap detected for {market_pair}: "
                          f"{actual_interval:.2f}s (expected {expected_interval:.2f}s)")
                
        # Update timestamp
        self._last_quote_times[market_pair] = quote_time
    
    def record_market_data_gap(self, market_pair: str):
        """
        Explicitly record a gap in market data.
        
        Args:
            market_pair: Market pair (e.g., 'EUR/USD') with gap
        """
        if not self.enable_forex_metrics:
            return
            
        if market_pair not in self._market_data_gaps:
            logger.warning(f"Market pair {market_pair} not registered with health client")
            return
            
        self._market_data_gaps[market_pair] += 1
        logger.debug(f"Market data gap recorded for {market_pair}")
    
    def get_quote_staleness(self, market_pair: str) -> float:
        """
        Get the staleness of the latest quote for a market pair.
        
        Args:
            market_pair: Market pair to check
            
        Returns:
            Staleness in milliseconds
        """
        if not self.enable_forex_metrics or market_pair not in self._last_quote_times:
            return 0
            
        if self._last_quote_times[market_pair] == 0:
            return 0
            
        return (time.time() - self._last_quote_times[market_pair]) * 1000
    
    def _collect_forex_metrics(self) -> Dict[str, Any]:
        """Collect forex-specific metrics for heartbeat."""
        if not self.enable_forex_metrics:
            return {}
            
        metrics = {}
        
        # Calculate average trade latency across all pairs
        all_latencies = []
        for pair, latencies in self._trade_latencies.items():
            if latencies:
                all_latencies.extend(latencies)
                
        if all_latencies:
            metrics["trade_latency_ms"] = sum(all_latencies) / len(all_latencies)
                
        # Calculate quote staleness for each pair
        now = time.time()
        staleness_values = []
        
        for pair, last_time in self._last_quote_times.items():
            if last_time > 0:
                staleness_ms = (now - last_time) * 1000
                staleness_values.append(staleness_ms)
                
        if staleness_values:
            metrics["quote_staleness_ms"] = sum(staleness_values) / len(staleness_values)
            
        # Add market data gaps
        total_gaps = sum(self._market_data_gaps.values())
        if total_gaps > 0:
            metrics["market_data_gaps"] = total_gaps
            
        # Add individual pair metrics
        metrics["pairs"] = {}
        for pair in self.market_pairs:
            pair_metrics = {}
            
            # Add trade latency for this pair
            if self._trade_latencies.get(pair):
                pair_metrics["trade_latency_ms"] = sum(self._trade_latencies[pair]) / len(self._trade_latencies[pair])
                
            # Add quote staleness for this pair
            if self._last_quote_times.get(pair, 0) > 0:
                pair_metrics["quote_staleness_ms"] = (now - self._last_quote_times[pair]) * 1000
                
            # Add market data gaps for this pair
            if self._market_data_gaps.get(pair, 0) > 0:
                pair_metrics["data_gaps"] = self._market_data_gaps[pair]
                
            metrics["pairs"][pair] = pair_metrics
            
        return metrics
    
    def _get_expected_quote_interval(self, market_pair: str) -> float:
        """
        Get the expected interval between quotes for a market pair.
        
        Args:
            market_pair: Market pair to check
            
        Returns:
            Expected interval in seconds
        """
        # Major pairs have more frequent updates
        if market_pair in ["EUR/USD", "USD/JPY", "GBP/USD", "USD/CHF"]:
            return 0.2  # 200ms
        # Minor pairs
        elif any(major in market_pair for major in ["EUR", "USD", "JPY", "GBP", "CHF"]):
            return 0.5  # 500ms
        # Exotic pairs
        else:
            return 1.0  # 1000ms


def get_health_client(
    agent_id: str,
    agent_type: str,
    enable_forex_metrics: bool = False,
    market_pairs: Optional[List[str]] = None
) -> AgentHealthClient:
    """
    Factory function to get a health client for an agent.
    
    Args:
        agent_id: Unique identifier for the agent
        agent_type: Type of agent
        enable_forex_metrics: Whether to enable forex-specific metrics
        market_pairs: List of market pairs (required if forex metrics enabled)
        
    Returns:
        Configured health client
    """
    # Import here to avoid circular imports
    from src.agents.health_monitoring.health_monitor_service import HealthMonitorService
    
    # Get the singleton health monitor service
    health_monitor_service = HealthMonitorService()
    
    # Create and return the client
    return AgentHealthClient(
        agent_id=agent_id,
        agent_type=agent_type,
        health_monitor_service=health_monitor_service,
        enable_forex_metrics=enable_forex_metrics,
        market_pairs=market_pairs
    ) 