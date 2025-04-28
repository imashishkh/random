import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from pydantic import BaseModel, Field

from .health_monitoring.agent_health_sdk import HealthStatus, HealthCheckResult
from .health_monitoring.recovery_orchestrator import RecoveryOrchestrator, RecoveryStrategy, RecoveryRequest
from ...utils.singleton import Singleton
from ...utils.logging.logger import get_logger
from .health import AgentHealthStatus
from .health_monitoring.metrics_collector import MetricsCollector
from .health_monitoring.anomaly_detector import (
    HealthAnomalyDetector, AnomalyResult, get_anomaly_detector
)

logger = get_logger()

class AgentHealthRecord(BaseModel):
    """Represents the health record of an agent."""
    agent_id: str
    agent_type: str
    last_heartbeat: float = Field(default_factory=time.time)
    consecutive_failures: int = 0
    status: HealthStatus = HealthStatus.HEALTHY
    last_check_result: Optional[HealthCheckResult] = None
    health_metrics: Dict[str, Any] = Field(default_factory=dict)
    
    def update_heartbeat(self) -> None:
        """Update the last heartbeat time."""
        self.last_heartbeat = time.time()
        
    def record_health_check(self, result: HealthCheckResult) -> None:
        """Record a health check result."""
        self.last_check_result = result
        
        if result.status == HealthStatus.HEALTHY:
            # Reset consecutive failures on success
            if self.consecutive_failures > 0:
                self.consecutive_failures = 0
                logger.info(f"Agent {self.agent_id} has recovered after {self.consecutive_failures} consecutive failures")
            self.status = HealthStatus.HEALTHY
        else:
            # Increment failures and update status
            self.consecutive_failures += 1
            self.status = result.status
            logger.warning(f"Agent {self.agent_id} health check failed: {result.status.name}. Consecutive failures: {self.consecutive_failures}")
    
    def record_metrics(self, metrics: Dict[str, Any]) -> None:
        """Record health metrics from the agent."""
        self.health_metrics.update(metrics)
        
    def has_missed_heartbeat(self, heartbeat_timeout_seconds: int) -> bool:
        """Check if the agent has missed its heartbeat."""
        return (time.time() - self.last_heartbeat) > heartbeat_timeout_seconds
        
    def get_last_result_age(self) -> Optional[float]:
        """Get the age of the last health check result in seconds."""
        if self.last_check_result:
            return time.time() - self.last_check_result.timestamp
        return None


class HealthMonitorService(metaclass=Singleton):
    """
    Central service for monitoring agent health across the system.
    
    This service:
    1. Maintains health records for all registered agents
    2. Schedules regular health checks
    3. Processes heartbeats from agents
    4. Triggers recovery actions when issues are detected
    5. Provides health status information to other system components
    """
    
    def __init__(
        self,
        heartbeat_timeout_seconds: int = 60,
        health_check_interval_seconds: int = 30,
        recovery_enabled: bool = True,
        early_warning_enabled: bool = True,
        early_warning_severity_threshold: int = 7
    ):
        """
        Initialize the health monitor service.
        
        Args:
            heartbeat_timeout_seconds: Time in seconds after which a missed heartbeat 
                will be considered a failure
            health_check_interval_seconds: How often to run health checks
            recovery_enabled: Whether to trigger recovery actions for unhealthy agents
            early_warning_enabled: Whether to enable early warning through anomaly detection
            early_warning_severity_threshold: Minimum severity level for early warnings
        """
        # Health storage
        self.agent_health = {}  # agent_id -> AgentHealthStatus
        
        # Configuration
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self.health_check_interval_seconds = health_check_interval_seconds
        self.recovery_enabled = recovery_enabled
        self.early_warning_enabled = early_warning_enabled
        self.early_warning_severity_threshold = early_warning_severity_threshold
        
        # Recovery components
        self.recovery_orchestrator = RecoveryOrchestrator()
        
        # Metrics collection
        self.metrics_collector = MetricsCollector()
        
        # Anomaly detection for early warning
        self.anomaly_detector = get_anomaly_detector()
        
        # Background scheduler for health checks
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(
            self._run_health_checks,
            'interval',
            seconds=self.health_check_interval_seconds,
            id='health_check_job',
            max_instances=1,
            replace_existing=True
        )
        
        # Keep track of if service is running
        self.running = False
        
        logger.info(
            f"HealthMonitorService initialized with heartbeat timeout: {heartbeat_timeout_seconds}s, "
            f"check interval: {health_check_interval_seconds}s, recovery enabled: {recovery_enabled}, "
            f"early warning enabled: {early_warning_enabled}"
        )
    
    def start(self):
        """Start the health monitoring service."""
        if not self.running:
            self.scheduler.start()
            
            # Also start the anomaly detector if early warning is enabled
            if self.early_warning_enabled:
                self.anomaly_detector.start()
                
                # Register callback for anomaly notifications
                self.anomaly_detector.register_callback(self._handle_anomaly)
                
                logger.info("Early warning system enabled - anomaly detector started")
                
            self.running = True
            logger.info("Health monitoring service started")
    
    def stop(self):
        """Stop the health monitoring service."""
        if self.running:
            self.scheduler.shutdown()
            
            # Also stop the anomaly detector if it was started
            if self.early_warning_enabled:
                self.anomaly_detector.unregister_callback(self._handle_anomaly)
                self.anomaly_detector.stop()
                
            self.running = False
            logger.info("Health monitoring service stopped")
    
    def register_agent(self, agent_id, agent_type=None, recovery_strategy=None):
        """
        Register an agent with the health monitoring service.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_type: Type of agent (researcher, executor, etc.)
            recovery_strategy: Strategy to use for recovery (default: RestartRecovery)
        """
        if agent_id in self.agent_health:
            logger.warning(f"Agent already registered: {agent_id}")
            return
            
        # Create new health status record
        agent_status = AgentHealthStatus(
            agent_id=agent_id,
            agent_type=agent_type
        )
        
        # Add early_warnings list for anomaly tracking
        agent_status.early_warnings = []
        
        # Set recovery strategy
        if not recovery_strategy:
            recovery_strategy = RecoveryStrategy.RESTART
            
        agent_status.recovery_strategy = recovery_strategy
        
        # Store the agent status
        self.agent_health[agent_id] = agent_status
        
        logger.info(f"Agent registered: {agent_id}, type: {agent_type}")
    
    def unregister_agent(self, agent_id: str) -> None:
        """
        Unregister an agent from health monitoring.
        
        Args:
            agent_id: Unique identifier for the agent
        """
        if agent_id in self.agent_health:
            del self.agent_health[agent_id]
            logger.info(f"Agent {agent_id} unregistered from health monitoring")
    
    def receive_heartbeat(self, agent_id: str, metrics: Dict[str, Any] = None) -> None:
        """
        Process a heartbeat from an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            metrics: Optional metrics to record with the heartbeat
        """
        if agent_id not in self.agent_health:
            logger.warning(f"Received heartbeat from unregistered agent {agent_id}")
            return
        
        agent_status = self.agent_health[agent_id]
        agent_status.last_heartbeat = time.time()
        
        if metrics:
            agent_status.health_metrics.update(metrics)
        
        # If agent was previously unhealthy due to missed heartbeats, log recovery
        if agent_status.status == HealthStatus.UNRESPONSIVE:
            logger.info(f"Agent {agent_id} has resumed sending heartbeats after being unresponsive")
            # We don't immediately change status to HEALTHY - let the next health check confirm
    
    def record_health_check(self, agent_id: str, result: HealthCheckResult) -> None:
        """
        Record an external health check result for an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            result: The health check result
        """
        if agent_id not in self.agent_health:
            logger.warning(f"Received health check for unregistered agent {agent_id}")
            return
            
        agent_status = self.agent_health[agent_id]
        agent_status.record_health_check(result)
        
        # Check if recovery needs to be triggered
        self._check_recovery_needed(agent_id)
    
    def get_agent_status(self, agent_id: str) -> Optional[HealthStatus]:
        """
        Get the current health status of an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            
        Returns:
            HealthStatus if agent is registered, None otherwise
        """
        if agent_id in self.agent_health:
            return self.agent_health[agent_id].status
        return None
    
    def get_all_agent_statuses(self) -> Dict[str, HealthStatus]:
        """
        Get the health status of all registered agents.
        
        Returns:
            Dictionary mapping agent IDs to health statuses
        """
        return {
            agent_id: agent_status.status
            for agent_id, agent_status in self.agent_health.items()
        }
    
    def get_unhealthy_agents(self) -> List[Tuple[str, HealthStatus]]:
        """
        Get all agents that are not in a healthy state.
        
        Returns:
            List of tuples containing agent ID and status for all unhealthy agents
        """
        return [
            (agent_id, agent_status.status)
            for agent_id, agent_status in self.agent_health.items()
            if agent_status.status != HealthStatus.HEALTHY
        ]
    
    def register_health_check_callback(self, agent_type: str, callback: Callable[[str], HealthCheckResult]) -> None:
        """
        Register a callback for custom health checks for a specific agent type.
        
        Args:
            agent_type: Type of agent this callback should be used for
            callback: Function that performs the health check and returns HealthCheckResult
        """
        # This method is not used in the new implementation
        pass
    
    def manual_recovery(self, agent_id: str, strategy: RecoveryStrategy) -> bool:
        """
        Manually trigger recovery for an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            strategy: Recovery strategy to use
            
        Returns:
            True if recovery was initiated, False otherwise
        """
        if agent_id not in self.agent_health:
            logger.error(f"Cannot initiate recovery for unregistered agent {agent_id}")
            return False
            
        agent_status = self.agent_health[agent_id]
        self.recovery_orchestrator.schedule_recovery(
            agent_id=agent_id,
            agent_type=agent_status.agent_type,
            recovery_strategy=strategy
        )
        logger.info(f"Manual recovery initiated for agent {agent_id} with strategy {strategy.name}")
        return True
    
    def _run_health_checks(self):
        """Run health checks on all registered agents."""
        logger.debug("Running scheduled health checks")
        for agent_id in list(self.agent_health.keys()):
            self._check_agent_health(agent_id)
            
    def _check_agent_health(self, agent_id):
        """
        Check health status of a specific agent.
        
        Verifies:
        1. Recent heartbeat (within timeout period)
        2. Acceptable failure rate
        3. Response time within acceptable range
        4. No critical early warnings
        
        Args:
            agent_id: ID of the agent to check
        """
        if agent_id not in self.agent_health:
            logger.warning(f"Health check requested for unknown agent: {agent_id}")
            return
            
        agent_status = self.agent_health[agent_id]
        now = time.time()
        
        # Record metrics for this check
        metrics = {}
        
        # Check most recent heartbeat
        if agent_status.last_heartbeat:
            heartbeat_age = now - agent_status.last_heartbeat
            metrics["heartbeat_age"] = heartbeat_age
            
            if heartbeat_age > self.heartbeat_timeout_seconds:
                self._record_health_check_failure(
                    agent_id, 
                    reason=f"Missed heartbeat (last: {int(heartbeat_age)}s ago)"
                )
                return
        else:
            # No heartbeat recorded yet
            self._record_health_check_failure(
                agent_id, 
                reason="No heartbeat received"
            )
            return
            
        # Check failure rate
        total_ops = agent_status.metrics.success_count + agent_status.metrics.failure_count
        if total_ops > 0:
            failure_rate = agent_status.metrics.failure_count / total_ops
            metrics["failure_rate"] = failure_rate
            
            # Alert if failure rate is above 20%
            if failure_rate > 0.2 and total_ops >= 10:
                self._record_health_check_failure(
                    agent_id, 
                    reason=f"High failure rate: {failure_rate:.2%}"
                )
                return
                
        # Check response time
        if agent_status.metrics.avg_response_time is not None:
            avg_response_time = agent_status.metrics.avg_response_time
            metrics["avg_response_time"] = avg_response_time
            
            # Alert if average response time is above 5 seconds
            if avg_response_time > 5000:  # 5000ms = 5 seconds
                self._record_health_check_failure(
                    agent_id, 
                    reason=f"Slow response time: {avg_response_time:.2f}ms"
                )
                return
                
        # Check for critical early warnings
        if self.early_warning_enabled and hasattr(agent_status, 'early_warnings'):
            # Look at recent critical warnings (last 5 minutes)
            recent_critical_warnings = [
                w for w in agent_status.early_warnings 
                if now - w["timestamp"] < 300 and w["severity"] >= 9
            ]
            
            if recent_critical_warnings:
                self._record_health_check_failure(
                    agent_id, 
                    reason=f"Critical early warnings: {len(recent_critical_warnings)}"
                )
                return
        
        # If we reach here, the agent is healthy
        self._record_health_check_success(agent_id, metrics)
    
    def _check_recovery_needed(self, agent_id: str) -> None:
        """
        Check if an agent needs recovery based on its health status and thresholds.
        
        Args:
            agent_id: The agent to check
        """
        if agent_id not in self.agent_health:
            return
            
        agent_status = self.agent_health[agent_id]
        
        # Skip if agent is healthy
        if agent_status.status == HealthStatus.HEALTHY:
            return
            
        # Check if we've passed the threshold for this status
        if (agent_status.status in self.recovery_thresholds and 
            agent_status.consecutive_failures >= self.recovery_thresholds[agent_status.status]):
            
            # Determine appropriate recovery strategy based on status
            if agent_status.status == HealthStatus.UNRESPONSIVE:
                strategy = RecoveryStrategy.RESTART
            elif agent_status.status == HealthStatus.CRITICAL:
                strategy = RecoveryStrategy.RECREATE
            else:  # DEGRADED
                strategy = RecoveryStrategy.RESTART
            
            logger.info(
                f"Triggering recovery for agent {agent_id} ({agent_status.agent_type}): "
                f"Status={agent_status.status.name}, Failures={agent_status.consecutive_failures}, Strategy={strategy.name}"
            )
            
            # Schedule recovery action
            self.recovery_orchestrator.schedule_recovery(
                agent_id=agent_id,
                agent_type=agent_status.agent_type,
                recovery_strategy=strategy
            )
    
    def _handle_anomaly(self, anomaly: AnomalyResult) -> None:
        """
        Handle anomaly detection results for early warning.
        
        This method is called when the anomaly detector identifies a potential issue.
        It can trigger proactive actions before a full health check failure occurs.
        
        Args:
            anomaly: The detected anomaly information
        """
        agent_id = anomaly.agent_id
        
        # Only process if agent is registered and anomaly severity meets threshold
        if agent_id in self.agent_health and anomaly.severity >= self.early_warning_severity_threshold:
            agent_status = self.agent_health[agent_id]
            
            # Log the early warning
            logger.warning(
                f"Early warning for agent {agent_id}: {anomaly.pattern_name} "
                f"(severity: {anomaly.severity}) - {anomaly.description}"
            )
            
            # Update agent health record with early warning flag
            agent_status.early_warnings.append({
                "timestamp": time.time(),
                "pattern": anomaly.pattern_name,
                "severity": anomaly.severity,
                "description": anomaly.description
            })
            
            # For high severity anomalies, consider preemptive action
            if anomaly.severity >= 9:
                logger.warning(f"Critical early warning for agent {agent_id} - considering preemptive action")
                
                # For critical issues, we might take preemptive action
                # depending on the specific anomaly pattern
                if anomaly.pattern_name in ["market_data_gaps", "quote_staleness"]:
                    logger.warning(f"Triggering preemptive market data verification for agent {agent_id}")
                    # Here you would trigger specific verification or recovery actions
                    # such as reconnecting to market data feeds
                
                # Add logic for other critical patterns as needed
            
            # For medium-high severity anomalies, schedule an immediate health check
            elif anomaly.severity >= 7:
                logger.info(f"Scheduling immediate health check for agent {agent_id} due to early warning")
                # Add a one-off job to check this specific agent immediately
                self.scheduler.add_job(
                    lambda: self._check_agent_health(agent_id),
                    id=f'early_warning_check_{agent_id}_{int(time.time())}',
                    replace_existing=False
                )
    
    def _record_health_check_failure(self, agent_id, reason):
        """
        Record a health check failure for an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            reason: Reason for the health check failure
        """
        if agent_id not in self.agent_health:
            logger.warning(f"Health check failure recorded for unknown agent: {agent_id}")
            return
            
        agent_status = self.agent_health[agent_id]
        agent_status.status = HealthStatus.DEGRADED
        agent_status.consecutive_failures += 1
        logger.warning(f"Health check failure recorded for agent {agent_id}: {reason}")
        
        # Check if recovery is needed
        self._check_recovery_needed(agent_id)
    
    def _record_health_check_success(self, agent_id, metrics):
        """
        Record a health check success for an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            metrics: Health metrics from the health check
        """
        if agent_id not in self.agent_health:
            logger.warning(f"Health check success recorded for unknown agent: {agent_id}")
            return
            
        agent_status = self.agent_health[agent_id]
        agent_status.status = HealthStatus.HEALTHY
        agent_status.consecutive_failures = 0
        agent_status.health_metrics.update(metrics)
        logger.info(f"Health check success recorded for agent {agent_id}")
        
        # Check if recovery is needed
        self._check_recovery_needed(agent_id) 