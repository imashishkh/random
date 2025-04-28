"""
Health Monitoring Notifications

This module manages notifications for health anomalies, alerts, and status reports
from the agent health monitoring system. It supports multiple notification channels
and prioritization of alerts.
"""

import logging
import json
from enum import Enum
from typing import Dict, List, Any, Optional, Callable, Set, Union
from datetime import datetime

from ...utils.logging.logger import get_logger

logger = get_logger()


class AlertSeverity(Enum):
    """Severity levels for health alerts."""
    INFO = 0
    WARNING = 1
    ERROR = 2
    CRITICAL = 3


class AlertChannel(Enum):
    """Notification channels for health alerts."""
    CONSOLE = 0
    LOG = 1
    EMAIL = 2
    SMS = 3
    WEBHOOK = 4
    SLACK = 5


class HealthAlert:
    """Represents a health monitoring alert."""
    
    def __init__(
        self,
        agent_id: str,
        alert_type: str,
        message: str,
        severity: AlertSeverity,
        data: Dict[str, Any] = None,
        timestamp: Optional[datetime] = None,
    ):
        """
        Initialize a new health alert.
        
        Args:
            agent_id: ID of the agent this alert is for
            alert_type: Type of alert (e.g., 'heartbeat_timeout', 'memory_leak')
            message: Human-readable alert message
            severity: Severity level of the alert
            data: Additional alert data
            timestamp: Time when the alert was created (defaults to now)
        """
        self.agent_id = agent_id
        self.alert_type = alert_type
        self.message = message
        self.severity = severity
        self.data = data or {}
        self.timestamp = timestamp or datetime.utcnow()
        self.alert_id = f"{agent_id}-{alert_type}-{self.timestamp.timestamp()}"
        self.acknowledged = False
        self.resolved = False
        self.resolved_timestamp: Optional[datetime] = None
    
    def acknowledge(self) -> None:
        """Mark the alert as acknowledged."""
        self.acknowledged = True
    
    def resolve(self) -> None:
        """Mark the alert as resolved."""
        self.resolved = True
        self.resolved_timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the alert to a dictionary."""
        return {
            "alert_id": self.alert_id,
            "agent_id": self.agent_id,
            "alert_type": self.alert_type,
            "message": self.message,
            "severity": self.severity.name,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged": self.acknowledged,
            "resolved": self.resolved,
            "resolved_timestamp": self.resolved_timestamp.isoformat() if self.resolved_timestamp else None,
        }
    
    def __str__(self) -> str:
        """String representation of the alert."""
        return (
            f"[{self.severity.name}] {self.agent_id}: {self.message} "
            f"({self.alert_type}, {'resolved' if self.resolved else 'active'})"
        )


class NotificationManager:
    """
    Manages health monitoring notifications across different channels.
    Implements the Singleton pattern to ensure only one notification manager exists.
    """
    _instance = None
    
    @classmethod
    def get_instance(cls) -> 'NotificationManager':
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = NotificationManager()
        return cls._instance
    
    def __init__(self):
        """Initialize the notification manager. Use get_instance() instead of constructor."""
        if NotificationManager._instance is not None:
            raise RuntimeError("Use NotificationManager.get_instance() instead of constructor")
        
        self._alert_callbacks: Dict[AlertChannel, List[Callable[[HealthAlert], None]]] = {
            channel: [] for channel in AlertChannel
        }
        self._active_alerts: Dict[str, HealthAlert] = {}
        self._alert_history: List[HealthAlert] = []
        self._channel_severity_thresholds: Dict[AlertChannel, AlertSeverity] = {
            AlertChannel.CONSOLE: AlertSeverity.INFO,
            AlertChannel.LOG: AlertSeverity.INFO,
            AlertChannel.EMAIL: AlertSeverity.ERROR,
            AlertChannel.SMS: AlertSeverity.CRITICAL,
            AlertChannel.WEBHOOK: AlertSeverity.WARNING,
            AlertChannel.SLACK: AlertSeverity.WARNING,
        }
        self._muted_agent_ids: Set[str] = set()
        self._muted_alert_types: Set[str] = set()
        
        # Register default handlers
        self.register_channel_handler(AlertChannel.CONSOLE, self._console_handler)
        self.register_channel_handler(AlertChannel.LOG, self._log_handler)
    
    def register_channel_handler(
        self, 
        channel: AlertChannel, 
        handler: Callable[[HealthAlert], None]
    ) -> None:
        """
        Register a handler function for a notification channel.
        
        Args:
            channel: The notification channel
            handler: Callback function that will receive the alert
        """
        if handler not in self._alert_callbacks[channel]:
            self._alert_callbacks[channel].append(handler)
            logger.debug(f"Registered handler for {channel.name} channel")
    
    def unregister_channel_handler(
        self, 
        channel: AlertChannel, 
        handler: Callable[[HealthAlert], None]
    ) -> None:
        """
        Unregister a handler function from a notification channel.
        
        Args:
            channel: The notification channel
            handler: The handler function to unregister
        """
        if handler in self._alert_callbacks[channel]:
            self._alert_callbacks[channel].remove(handler)
            logger.debug(f"Unregistered handler from {channel.name} channel")
    
    def set_channel_severity_threshold(
        self, 
        channel: AlertChannel, 
        threshold: AlertSeverity
    ) -> None:
        """
        Set the minimum severity threshold for a notification channel.
        
        Args:
            channel: The notification channel
            threshold: Minimum severity level for alerts on this channel
        """
        self._channel_severity_thresholds[channel] = threshold
        logger.debug(f"Set {channel.name} threshold to {threshold.name}")
    
    def mute_agent(self, agent_id: str) -> None:
        """
        Mute all notifications for a specific agent.
        
        Args:
            agent_id: ID of the agent to mute
        """
        self._muted_agent_ids.add(agent_id)
        logger.info(f"Muted notifications for agent {agent_id}")
    
    def unmute_agent(self, agent_id: str) -> None:
        """
        Unmute notifications for a specific agent.
        
        Args:
            agent_id: ID of the agent to unmute
        """
        if agent_id in self._muted_agent_ids:
            self._muted_agent_ids.remove(agent_id)
            logger.info(f"Unmuted notifications for agent {agent_id}")
    
    def mute_alert_type(self, alert_type: str) -> None:
        """
        Mute all notifications of a specific alert type.
        
        Args:
            alert_type: Type of alert to mute
        """
        self._muted_alert_types.add(alert_type)
        logger.info(f"Muted notifications for alert type '{alert_type}'")
    
    def unmute_alert_type(self, alert_type: str) -> None:
        """
        Unmute notifications of a specific alert type.
        
        Args:
            alert_type: Type of alert to unmute
        """
        if alert_type in self._muted_alert_types:
            self._muted_alert_types.remove(alert_type)
            logger.info(f"Unmuted notifications for alert type '{alert_type}'")
    
    def send_alert(self, alert: HealthAlert) -> None:
        """
        Send an alert through all appropriate channels.
        
        Args:
            alert: The health alert to send
        """
        # Skip if agent or alert type is muted
        if alert.agent_id in self._muted_agent_ids or alert.alert_type in self._muted_alert_types:
            logger.debug(f"Alert {alert.alert_id} was muted")
            return
        
        # Add to active alerts and history
        self._active_alerts[alert.alert_id] = alert
        self._alert_history.append(alert)
        
        # Send to appropriate channels based on severity
        for channel, threshold in self._channel_severity_thresholds.items():
            if alert.severity.value >= threshold.value:
                for handler in self._alert_callbacks[channel]:
                    try:
                        handler(alert)
                    except Exception as e:
                        logger.error(f"Error in {channel.name} handler: {e}")
    
    def resolve_alert(self, alert_id: str) -> None:
        """
        Mark an alert as resolved.
        
        Args:
            alert_id: ID of the alert to resolve
        """
        if alert_id in self._active_alerts:
            alert = self._active_alerts[alert_id]
            alert.resolve()
            del self._active_alerts[alert_id]
            logger.debug(f"Resolved alert {alert_id}")
    
    def acknowledge_alert(self, alert_id: str) -> None:
        """
        Mark an alert as acknowledged.
        
        Args:
            alert_id: ID of the alert to acknowledge
        """
        if alert_id in self._active_alerts:
            alert = self._active_alerts[alert_id]
            alert.acknowledge()
            logger.debug(f"Acknowledged alert {alert_id}")
    
    def get_active_alerts(
        self, 
        agent_id: Optional[str] = None, 
        min_severity: Optional[AlertSeverity] = None
    ) -> List[HealthAlert]:
        """
        Get all active (unresolved) alerts, optionally filtered.
        
        Args:
            agent_id: Filter by agent ID (optional)
            min_severity: Minimum severity level (optional)
            
        Returns:
            List of active health alerts
        """
        alerts = list(self._active_alerts.values())
        
        if agent_id:
            alerts = [a for a in alerts if a.agent_id == agent_id]
            
        if min_severity:
            alerts = [a for a in alerts if a.severity.value >= min_severity.value]
            
        return alerts
    
    def get_alert_history(
        self,
        agent_id: Optional[str] = None,
        alert_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        min_severity: Optional[AlertSeverity] = None,
        limit: int = 100
    ) -> List[HealthAlert]:
        """
        Get alert history with optional filters.
        
        Args:
            agent_id: Filter by agent ID (optional)
            alert_type: Filter by alert type (optional)
            start_time: Filter by start time (inclusive, optional)
            end_time: Filter by end time (inclusive, optional)
            min_severity: Minimum severity level (optional)
            limit: Maximum number of alerts to return
            
        Returns:
            List of health alerts from history
        """
        alerts = self._alert_history.copy()
        
        if agent_id:
            alerts = [a for a in alerts if a.agent_id == agent_id]
            
        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]
            
        if start_time:
            alerts = [a for a in alerts if a.timestamp >= start_time]
            
        if end_time:
            alerts = [a for a in alerts if a.timestamp <= end_time]
            
        if min_severity:
            alerts = [a for a in alerts if a.severity.value >= min_severity.value]
        
        # Sort by timestamp (newest first) and apply limit
        alerts.sort(key=lambda a: a.timestamp, reverse=True)
        return alerts[:limit]
    
    def generate_health_report(
        self,
        agent_ids: Optional[List[str]] = None,
        include_resolved: bool = False,
        time_window_hours: Optional[int] = 24
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive health report.
        
        Args:
            agent_ids: List of agent IDs to include (None for all)
            include_resolved: Whether to include resolved alerts
            time_window_hours: Time window for historical alerts (None for all time)
            
        Returns:
            Dictionary with health report data
        """
        start_time = None
        if time_window_hours is not None:
            start_time = datetime.utcnow().replace(
                microsecond=0
            ) - datetime.timedelta(hours=time_window_hours)
        
        # Get alerts
        alerts = self._alert_history.copy()
        
        if agent_ids:
            alerts = [a for a in alerts if a.agent_id in agent_ids]
            
        if not include_resolved:
            alerts = [a for a in alerts if not a.resolved]
            
        if start_time:
            alerts = [a for a in alerts if a.timestamp >= start_time]
        
        # Group alerts by agent
        alerts_by_agent: Dict[str, List[HealthAlert]] = {}
        for alert in alerts:
            if alert.agent_id not in alerts_by_agent:
                alerts_by_agent[alert.agent_id] = []
            alerts_by_agent[alert.agent_id].append(alert)
        
        # Calculate statistics
        alert_counts_by_type: Dict[str, int] = {}
        alert_counts_by_severity: Dict[str, int] = {}
        
        for alert in alerts:
            alert_counts_by_type[alert.alert_type] = alert_counts_by_type.get(alert.alert_type, 0) + 1
            alert_counts_by_severity[alert.severity.name] = alert_counts_by_severity.get(alert.severity.name, 0) + 1
        
        # Build report
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "time_window_hours": time_window_hours,
            "total_alerts": len(alerts),
            "active_alerts": len([a for a in alerts if not a.resolved]),
            "agent_count": len(alerts_by_agent),
            "alert_counts_by_type": alert_counts_by_type,
            "alert_counts_by_severity": alert_counts_by_severity,
            "agents": {}
        }
        
        # Add agent-specific data
        for agent_id, agent_alerts in alerts_by_agent.items():
            report["agents"][agent_id] = {
                "alert_count": len(agent_alerts),
                "active_alerts": len([a for a in agent_alerts if not a.resolved]),
                "highest_severity": max([a.severity.value for a in agent_alerts]) if agent_alerts else None,
                "latest_alert": max([a.timestamp for a in agent_alerts]).isoformat() if agent_alerts else None,
            }
        
        return report
    
    # Default handlers
    def _console_handler(self, alert: HealthAlert) -> None:
        """Default console handler."""
        color_codes = {
            AlertSeverity.INFO: "\033[0;34m",  # Blue
            AlertSeverity.WARNING: "\033[0;33m",  # Yellow
            AlertSeverity.ERROR: "\033[0;31m",  # Red
            AlertSeverity.CRITICAL: "\033[1;31m",  # Bold Red
        }
        reset_code = "\033[0m"
        
        color = color_codes.get(alert.severity, "")
        print(f"{color}[HEALTH ALERT] {alert}{reset_code}")
    
    def _log_handler(self, alert: HealthAlert) -> None:
        """Default logging handler."""
        log_methods = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.ERROR: logger.error,
            AlertSeverity.CRITICAL: logger.critical,
        }
        
        log_method = log_methods.get(alert.severity, logger.info)
        log_method(f"[HEALTH ALERT] {alert}")


# Convenience function to get the singleton notification manager
def get_notification_manager() -> NotificationManager:
    """Get the singleton NotificationManager instance."""
    return NotificationManager.get_instance()


# Convenience functions for sending alerts
def send_health_alert(
    agent_id: str,
    alert_type: str,
    message: str,
    severity: AlertSeverity,
    data: Dict[str, Any] = None
) -> HealthAlert:
    """
    Send a health alert through the notification manager.
    
    Args:
        agent_id: ID of the agent this alert is for
        alert_type: Type of alert
        message: Human-readable alert message
        severity: Severity level of the alert
        data: Additional alert data
        
    Returns:
        The created HealthAlert instance
    """
    alert = HealthAlert(
        agent_id=agent_id,
        alert_type=alert_type,
        message=message,
        severity=severity,
        data=data
    )
    
    notification_manager = get_notification_manager()
    notification_manager.send_alert(alert)
    
    return alert 