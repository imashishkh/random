import os
import time
import logging
import threading
from typing import Dict, List, Set, Optional, Any, Callable, Tuple
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict

from .health_monitoring.metrics_collector import MetricsCollector, MetricType

logger = logging.getLogger(__name__)

class AgentHealthStatus(Enum):
    """Possible health statuses for an agent"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    RECOVERING = "recovering"
    UNKNOWN = "unknown"

class HealthMonitor:
    """
    Central health monitoring system for agents. Collects health data,
    detects issues, and coordinates recovery actions.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(HealthMonitor, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._metrics_collector = MetricsCollector()
        self._agent_statuses: Dict[str, AgentHealthStatus] = {}
        self._agent_last_heartbeat: Dict[str, float] = {}
        self._agent_metadata: Dict[str, Dict[str, Any]] = {}
        self._status_change_callbacks: Set[Callable] = set()
        self._heartbeat_thread = None
        self._is_running = False
        self._heartbeat_interval = 30  # seconds
        self._heartbeat_timeout = 90   # seconds
        
        # Register for anomaly notifications from metrics collector
        self._metrics_collector.register_anomaly_callback(self._handle_metric_anomaly)
        
        self._initialized = True
    
    def start(self) -> None:
        """Start the health monitoring service"""
        if self._is_running:
            logger.warning("Health monitor is already running")
            return
            
        self._is_running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_monitor_loop,
            daemon=True,
            name="HealthMonitorHeartbeat"
        )
        self._heartbeat_thread.start()
        logger.info("Health monitoring service started")
        
    def stop(self) -> None:
        """Stop the health monitoring service"""
        if not self._is_running:
            logger.warning("Health monitor is not running")
            return
            
        self._is_running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5.0)
        logger.info("Health monitoring service stopped")
    
    def register_agent(
        self, 
        agent_id: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Register an agent with the health monitoring system
        
        Args:
            agent_id: Unique identifier for the agent
            metadata: Optional metadata about the agent (type, capabilities, etc.)
        """
        self._metrics_collector.register_agent(agent_id)
        self._agent_statuses[agent_id] = AgentHealthStatus.UNKNOWN
        self._agent_last_heartbeat[agent_id] = time.time()
        self._agent_metadata[agent_id] = metadata or {}
        logger.info(f"Agent '{agent_id}' registered with health monitoring system")
    
    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent from health monitoring"""
        if agent_id in self._agent_statuses:
            del self._agent_statuses[agent_id]
            
        if agent_id in self._agent_last_heartbeat:
            del self._agent_last_heartbeat[agent_id]
            
        if agent_id in self._agent_metadata:
            del self._agent_metadata[agent_id]
            
        self._metrics_collector.unregister_agent(agent_id)
        logger.info(f"Agent '{agent_id}' unregistered from health monitoring system")
    
    def record_heartbeat(self, agent_id: str, metrics: Optional[Dict[str, float]] = None) -> None:
        """
        Record a heartbeat from an agent
        
        Args:
            agent_id: Agent ID
            metrics: Optional metrics to record with the heartbeat
        """
        if agent_id not in self._agent_statuses:
            self.register_agent(agent_id)
            
        self._agent_last_heartbeat[agent_id] = time.time()
        
        # Record any provided metrics
        if metrics:
            for metric_name, value in metrics.items():
                try:
                    metric_type = MetricType(metric_name)
                    self._metrics_collector.record_metric(agent_id, metric_type, value)
                except ValueError:
                    logger.warning(f"Unknown metric type: {metric_name}")
        
        # If agent was previously unknown, mark as healthy upon first heartbeat
        if self._agent_statuses[agent_id] == AgentHealthStatus.UNKNOWN:
            self._update_agent_status(agent_id, AgentHealthStatus.HEALTHY)
            
    def _update_agent_status(self, agent_id: str, new_status: AgentHealthStatus) -> None:
        """
        Update an agent's health status and notify subscribers
        
        Args:
            agent_id: Agent ID
            new_status: New health status
        """
        if agent_id not in self._agent_statuses:
            return
            
        old_status = self._agent_statuses[agent_id]
        if old_status != new_status:
            self._agent_statuses[agent_id] = new_status
            logger.info(f"Agent '{agent_id}' health status changed: {old_status.value} -> {new_status.value}")
            
            # Notify status change callbacks
            status_change_info = {
                "agent_id": agent_id,
                "previous_status": old_status.value,
                "new_status": new_status.value,
                "timestamp": time.time()
            }
            
            for callback in self._status_change_callbacks:
                try:
                    callback(status_change_info)
                except Exception as e:
                    logger.error(f"Error in status change callback: {str(e)}")
    
    def _heartbeat_monitor_loop(self) -> None:
        """Background thread to monitor agent heartbeats"""
        logger.info("Heartbeat monitoring thread started")
        
        while self._is_running:
            try:
                self._check_heartbeats()
                time.sleep(self._heartbeat_interval)
            except Exception as e:
                logger.error(f"Error in heartbeat monitoring loop: {str(e)}")
                time.sleep(5)  # Back off on error
                
        logger.info("Heartbeat monitoring thread stopped")
    
    def _check_heartbeats(self) -> None:
        """Check all agent heartbeats for timeouts"""
        current_time = time.time()
        
        for agent_id, last_heartbeat in list(self._agent_last_heartbeat.items()):
            time_since_last_heartbeat = current_time - last_heartbeat
            
            # If agent has timed out
            if time_since_last_heartbeat > self._heartbeat_timeout:
                logger.warning(
                    f"Agent '{agent_id}' missed heartbeat: "
                    f"{time_since_last_heartbeat:.1f}s since last heartbeat"
                )
                
                # Update status to unhealthy if it's not already
                if self._agent_statuses[agent_id] != AgentHealthStatus.UNHEALTHY:
                    self._update_agent_status(agent_id, AgentHealthStatus.UNHEALTHY)
    
    def _handle_metric_anomaly(self, anomaly_info: Dict[str, Any]) -> None:
        """
        Handle a metric anomaly notification from the metrics collector
        
        Args:
            anomaly_info: Information about the anomaly
        """
        agent_id = anomaly_info.get("agent_id")
        if not agent_id or agent_id not in self._agent_statuses:
            return
            
        current_status = self._agent_statuses[agent_id]
        metric_type = anomaly_info.get("metric_type", "unknown")
        z_score = anomaly_info.get("z_score", 0)
        
        logger.warning(
            f"Metric anomaly for agent '{agent_id}': {metric_type}, "
            f"z-score: {z_score:.2f}"
        )
        
        # If the agent is currently healthy, mark it as degraded
        if current_status == AgentHealthStatus.HEALTHY:
            self._update_agent_status(agent_id, AgentHealthStatus.DEGRADED)
            
        # If we're already in degraded state and this is a severe anomaly,
        # potentially mark as unhealthy
        elif current_status == AgentHealthStatus.DEGRADED and z_score > 5.0:
            self._update_agent_status(agent_id, AgentHealthStatus.UNHEALTHY)
    
    def register_status_change_callback(self, callback: Callable) -> None:
        """Register a callback to be notified of agent status changes"""
        self._status_change_callbacks.add(callback)
    
    def unregister_status_change_callback(self, callback: Callable) -> None:
        """Unregister a status change callback"""
        self._status_change_callbacks.discard(callback)
    
    def get_agent_status(self, agent_id: str) -> Optional[str]:
        """Get the current health status for an agent"""
        if agent_id not in self._agent_statuses:
            return None
        return self._agent_statuses[agent_id].value
    
    def get_agent_health_data(self, agent_id: str) -> Dict[str, Any]:
        """Get comprehensive health data for an agent"""
        if agent_id not in self._agent_statuses:
            return {}
            
        health_score = self._metrics_collector.get_health_score(agent_id)
        metrics = self._metrics_collector.get_agent_metrics(agent_id)
        last_heartbeat = self._agent_last_heartbeat.get(agent_id, 0)
        
        return {
            "agent_id": agent_id,
            "status": self._agent_statuses[agent_id].value,
            "health_score": health_score,
            "last_heartbeat": last_heartbeat,
            "heartbeat_age": time.time() - last_heartbeat,
            "metrics": metrics,
            "metadata": self._agent_metadata.get(agent_id, {})
        }
    
    def get_all_agents_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health data for all registered agents"""
        return {
            agent_id: self.get_agent_health_data(agent_id)
            for agent_id in self._agent_statuses
        }
    
    def set_heartbeat_parameters(self, interval: int, timeout: int) -> None:
        """
        Set heartbeat monitoring parameters
        
        Args:
            interval: How often to check for missed heartbeats (seconds)
            timeout: How long to wait before marking an agent unhealthy (seconds)
        """
        self._heartbeat_interval = max(5, interval)
        self._heartbeat_timeout = max(self._heartbeat_interval * 2, timeout)
        logger.info(
            f"Heartbeat parameters updated: interval={self._heartbeat_interval}s, "
            f"timeout={self._heartbeat_timeout}s"
        ) 