"""
Agent Health Monitoring System

This module provides functionality for tracking agent health, detecting failures,
and implementing automated recovery mechanisms for agents.
"""

import time
import threading
import logging
import uuid
from typing import Dict, Any, List, Callable, Optional, Type, Union, TYPE_CHECKING
from datetime import datetime, timedelta
from enum import Enum

# Use TYPE_CHECKING for type hints without runtime dependency
if TYPE_CHECKING:
    from src.agents.base_agent import BaseAgent  # Only imported for type checking

from ..utils.logging.logger import get_logger

logger = get_logger()


class AgentHealthStatus(Enum):
    """Health status indicators for agents"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    RECOVERING = "recovering"
    UNKNOWN = "unknown"


class HealthMetrics:
    """Container for agent health metrics"""
    
    def __init__(self) -> None:
        self.last_execution_time: Optional[float] = None
        self.last_heartbeat: float = time.time()
        self.success_count: int = 0
        self.failure_count: int = 0
        self.consecutive_failures: int = 0
        self.avg_response_time: float = 0.0
        self.total_response_time: float = 0.0
        self.response_count: int = 0
        self.memory_usage: float = 0.0
        self.errors: List[Dict[str, Any]] = []
        self.status: AgentHealthStatus = AgentHealthStatus.UNKNOWN
        self.status_timestamp: float = time.time()
        self.recovery_attempts: int = 0
        
    def record_success(self, response_time: float) -> None:
        """Record a successful agent execution"""
        self.last_execution_time = time.time()
        self.success_count += 1
        self.consecutive_failures = 0
        
        # Update average response time
        self.total_response_time += response_time
        self.response_count += 1
        self.avg_response_time = self.total_response_time / self.response_count
        
        self.update_status(AgentHealthStatus.HEALTHY)
    
    def record_failure(self, error: str) -> None:
        """Record a failed agent execution"""
        self.last_execution_time = time.time()
        self.failure_count += 1
        self.consecutive_failures += 1
        
        # Record error
        self.errors.append({
            "timestamp": time.time(),
            "error": error
        })
        
        # Keep error log manageable
        if len(self.errors) > 100:
            self.errors = self.errors[-100:]
            
        # Update status based on consecutive failures
        if self.consecutive_failures >= 5:
            self.update_status(AgentHealthStatus.FAILED)
        elif self.consecutive_failures >= 2:
            self.update_status(AgentHealthStatus.DEGRADED)
    
    def record_heartbeat(self) -> None:
        """Record a heartbeat from the agent"""
        self.last_heartbeat = time.time()
    
    def update_status(self, status: AgentHealthStatus) -> None:
        """Update the health status of the agent"""
        if self.status != status:
            self.status = status
            self.status_timestamp = time.time()
            logger.info(f"Agent health status updated to {status.value}")
    
    def record_recovery_attempt(self) -> None:
        """Record a recovery attempt for the agent"""
        self.recovery_attempts += 1
        self.update_status(AgentHealthStatus.RECOVERING)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the health metrics"""
        return {
            "status": self.status.value,
            "last_execution": self.last_execution_time,
            "last_heartbeat": self.last_heartbeat,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "consecutive_failures": self.consecutive_failures,
            "avg_response_time": self.avg_response_time,
            "status_since": self.status_timestamp,
            "recovery_attempts": self.recovery_attempts,
            "recent_errors": self.errors[-5:] if self.errors else []
        }


class AgentHealthMonitor:
    """
    Health monitoring system for agents.
    
    This class provides functionality to track the health of agents,
    detect failures, and implement automatic recovery mechanisms.
    """
    
    def __init__(
        self,
        health_check_interval: float = 30.0,
        heartbeat_timeout: float = 300.0,
        max_recovery_attempts: int = 3,
        recovery_backoff_factor: float = 2.0
    ):
        """
        Initialize the health monitor.
        
        Args:
            health_check_interval: Interval in seconds between health checks
            heartbeat_timeout: Time in seconds after which an agent is considered
                               unresponsive if no heartbeat is received
            max_recovery_attempts: Maximum number of recovery attempts per agent
            recovery_backoff_factor: Exponential backoff factor for recovery attempts
        """
        self.agent_metrics: Dict[str, HealthMetrics] = {}
        self.health_check_interval = health_check_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.max_recovery_attempts = max_recovery_attempts
        self.recovery_backoff_factor = recovery_backoff_factor
        
        self.monitoring_thread: Optional[threading.Thread] = None
        self.running = False
        self.monitor_lock = threading.RLock()
        
        # Recovery handlers
        self.recovery_strategies: Dict[str, Callable[[str, HealthMetrics], bool]] = {
            "restart": self._restart_agent,
            "recreate": self._recreate_agent,
            "alert": self._alert_on_failure
        }
        
        # Agent references for recovery operations
        # Use Any for agent instances to avoid circular imports at runtime
        self.agents: Dict[str, Any] = {}
        
        # Agent factory for recreating agents
        self.agent_factory_callbacks: Dict[str, Callable[[], Any]] = {}
    
    def register_agent(self, agent: Any, factory_callback: Optional[Callable[[], Any]] = None) -> None:
        """
        Register an agent for health monitoring.
        
        Args:
            agent: Agent instance to monitor
            factory_callback: Optional callback to recreate the agent during recovery
        """
        with self.monitor_lock:
            agent_id = agent.agent_id
            
            # Create metrics if not exists
            if agent_id not in self.agent_metrics:
                self.agent_metrics[agent_id] = HealthMetrics()
                logger.info(f"Registered agent {agent.agent_name} ({agent_id}) for health monitoring")
            
            # Store agent reference and factory callback
            self.agents[agent_id] = agent
            
            if factory_callback:
                self.agent_factory_callbacks[agent_id] = factory_callback
    
    def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent from health monitoring.
        
        Args:
            agent_id: ID of the agent to unregister
            
        Returns:
            True if agent was unregistered, False if agent was not found
        """
        with self.monitor_lock:
            if agent_id in self.agent_metrics:
                self.agent_metrics.pop(agent_id)
                self.agents.pop(agent_id, None)
                self.agent_factory_callbacks.pop(agent_id, None)
                logger.info(f"Unregistered agent {agent_id} from health monitoring")
                return True
            return False
    
    def record_agent_success(self, agent_id: str, response_time: float) -> None:
        """
        Record a successful agent execution.
        
        Args:
            agent_id: ID of the agent
            response_time: Time taken for the agent's execution in seconds
        """
        with self.monitor_lock:
            if agent_id in self.agent_metrics:
                self.agent_metrics[agent_id].record_success(response_time)
                self.agent_metrics[agent_id].record_heartbeat()
    
    def record_agent_failure(self, agent_id: str, error: str) -> None:
        """
        Record a failed agent execution.
        
        Args:
            agent_id: ID of the agent
            error: Error message or reason for failure
        """
        with self.monitor_lock:
            if agent_id in self.agent_metrics:
                self.agent_metrics[agent_id].record_failure(error)
                self.agent_metrics[agent_id].record_heartbeat()
    
    def record_agent_heartbeat(self, agent_id: str) -> None:
        """
        Record a heartbeat from an agent.
        
        Args:
            agent_id: ID of the agent
        """
        with self.monitor_lock:
            if agent_id in self.agent_metrics:
                self.agent_metrics[agent_id].record_heartbeat()
    
    def get_agent_health(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the health metrics for an agent.
        
        Args:
            agent_id: ID of the agent
            
        Returns:
            Health metrics summary or None if agent is not registered
        """
        with self.monitor_lock:
            if agent_id in self.agent_metrics:
                return self.agent_metrics[agent_id].get_summary()
            return None
    
    def get_all_health_metrics(self) -> Dict[str, Dict[str, Any]]:
        """
        Get health metrics for all registered agents.
        
        Returns:
            Dictionary of agent IDs to health metric summaries
        """
        with self.monitor_lock:
            return {
                agent_id: metrics.get_summary()
                for agent_id, metrics in self.agent_metrics.items()
            }
    
    def start_monitoring(self) -> None:
        """Start the health monitoring thread"""
        if self.running:
            logger.warning("Health monitoring is already running")
            return
        
        self.running = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        logger.info("Agent health monitoring started")
    
    def stop_monitoring(self) -> None:
        """Stop the health monitoring thread"""
        if not self.running:
            logger.warning("Health monitoring is not running")
            return
        
        self.running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5.0)
            self.monitoring_thread = None
        
        logger.info("Agent health monitoring stopped")
    
    def _monitoring_loop(self) -> None:
        """Main monitoring loop that runs in a separate thread"""
        while self.running:
            try:
                self._check_agent_health()
                time.sleep(self.health_check_interval)
            except Exception as e:
                logger.error(f"Error in agent health monitoring loop: {str(e)}")
                time.sleep(5.0)  # Sleep briefly before retrying
    
    def _check_agent_health(self) -> None:
        """Check the health of all registered agents"""
        current_time = time.time()
        
        with self.monitor_lock:
            for agent_id, metrics in self.agent_metrics.items():
                try:
                    # Check for heartbeat timeout
                    if current_time - metrics.last_heartbeat > self.heartbeat_timeout:
                        logger.warning(f"Agent {agent_id} heartbeat timeout. Last seen {metrics.last_heartbeat}")
                        metrics.record_failure("Heartbeat timeout")
                    
                    # Check if agent is in failed state and needs recovery
                    if metrics.status == AgentHealthStatus.FAILED:
                        # Only attempt recovery if we haven't exceeded max attempts
                        if metrics.recovery_attempts < self.max_recovery_attempts:
                            self._attempt_recovery(agent_id, metrics)
                        else:
                            logger.error(f"Agent {agent_id} exceeded maximum recovery attempts. Manual intervention required.")
                            # Send alert for manual intervention
                            self._alert_on_failure(agent_id, metrics)
                
                except Exception as e:
                    logger.error(f"Error checking health of agent {agent_id}: {str(e)}")
    
    def _attempt_recovery(self, agent_id: str, metrics: HealthMetrics) -> None:
        """
        Attempt to recover a failed agent.
        
        Args:
            agent_id: ID of the agent to recover
            metrics: Health metrics for the agent
        """
        logger.info(f"Attempting recovery for agent {agent_id} (attempt {metrics.recovery_attempts + 1})")
        metrics.record_recovery_attempt()
        
        # Try different recovery strategies based on failure count
        if metrics.recovery_attempts == 1:
            # First attempt: try restarting the agent
            strategy = "restart"
        elif metrics.recovery_attempts == 2:
            # Second attempt: try recreating the agent
            strategy = "recreate"
        else:
            # Final attempt: alert for manual intervention
            strategy = "alert"
        
        # Get recovery function
        recovery_func = self.recovery_strategies.get(strategy)
        if recovery_func:
            success = recovery_func(agent_id, metrics)
            if success:
                logger.info(f"Successfully recovered agent {agent_id} using {strategy} strategy")
                metrics.update_status(AgentHealthStatus.HEALTHY)
                metrics.consecutive_failures = 0
            else:
                logger.warning(f"Failed to recover agent {agent_id} using {strategy} strategy")
        else:
            logger.error(f"No recovery strategy found for {strategy}")
    
    def _restart_agent(self, agent_id: str, metrics: HealthMetrics) -> bool:
        """
        Restart an agent as a recovery mechanism.
        
        Args:
            agent_id: ID of the agent to restart
            metrics: Health metrics for the agent
            
        Returns:
            True if restart was successful, False otherwise
        """
        try:
            agent = self.agents.get(agent_id)
            if not agent:
                logger.error(f"Cannot restart agent {agent_id}: agent reference not found")
                return False
            
            # Call agent's reset method
            agent.reset()
            
            # Record recovery in metrics
            logger.info(f"Agent {agent_id} restarted successfully")
            return True
        except Exception as e:
            logger.error(f"Error restarting agent {agent_id}: {str(e)}")
            return False
    
    def _recreate_agent(self, agent_id: str, metrics: HealthMetrics) -> bool:
        """
        Recreate an agent from scratch as a recovery mechanism.
        
        Args:
            agent_id: ID of the agent to recreate
            metrics: Health metrics for the agent
            
        Returns:
            True if recreation was successful, False otherwise
        """
        try:
            # Check if we have a factory callback for this agent
            factory_callback = self.agent_factory_callbacks.get(agent_id)
            if not factory_callback:
                logger.error(f"Cannot recreate agent {agent_id}: no factory callback registered")
                return False
            
            # Create a new agent instance
            new_agent = factory_callback()
            
            # Replace the agent reference
            self.agents[agent_id] = new_agent
            
            logger.info(f"Agent {agent_id} recreated successfully")
            return True
        except Exception as e:
            logger.error(f"Error recreating agent {agent_id}: {str(e)}")
            return False
    
    def _alert_on_failure(self, agent_id: str, metrics: HealthMetrics) -> bool:
        """
        Send alerts for agent failures.
        
        Args:
            agent_id: ID of the failed agent
            metrics: Health metrics for the agent
            
        Returns:
            True if alert was sent, False otherwise
        """
        try:
            # In a production system, this would send alerts via email, Slack, etc.
            logger.critical(f"ALERT: Agent {agent_id} has failed and requires manual intervention")
            logger.critical(f"Agent health metrics: {metrics.get_summary()}")
            
            # In this implementation, we just log the alert, but return True
            # to indicate the alert mechanism itself worked
            return True
        except Exception as e:
            logger.error(f"Error sending alert for agent {agent_id}: {str(e)}")
            return False
    
    def register_recovery_strategy(self, name: str, strategy_func: Callable[[str, HealthMetrics], bool]) -> None:
        """
        Register a custom recovery strategy.
        
        Args:
            name: Name of the recovery strategy
            strategy_func: Function that implements the recovery strategy
        """
        self.recovery_strategies[name] = strategy_func
        logger.info(f"Registered recovery strategy: {name}")


# Global instance
_health_monitor: Optional[AgentHealthMonitor] = None

def get_health_monitor() -> AgentHealthMonitor:
    """
    Get the global health monitor instance.
    
    Returns:
        Global health monitor instance
    """
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = AgentHealthMonitor()
    return _health_monitor 