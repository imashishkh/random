"""
Health Monitoring Alert Integrations

This module integrates the health monitoring system with the notification system,
connecting health events to appropriate alert channels.
"""

from typing import Dict, Any, List, Optional, Callable
import logging
from datetime import datetime

from .health_monitoring.notifications import (
    AlertSeverity,
    HealthAlert,
    get_notification_manager,
    send_health_alert
)
from .health_monitoring.registry import (
    get_health_monitor_service,
    get_anomaly_detector
)
from ...utils.logging.logger import get_logger

logger = get_logger()


class HealthAlertIntegrationManager:
    """
    Manages integrations between health monitoring events and the notification system.
    Implements the Singleton pattern.
    """
    _instance = None
    
    @classmethod
    def get_instance(cls) -> 'HealthAlertIntegrationManager':
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = HealthAlertIntegrationManager()
        return cls._instance
    
    def __init__(self):
        """Initialize the integration manager. Use get_instance() instead of constructor."""
        if HealthAlertIntegrationManager._instance is not None:
            raise RuntimeError("Use HealthAlertIntegrationManager.get_instance() instead of constructor")
        
        self._health_monitor = get_health_monitor_service()
        self._anomaly_detector = get_anomaly_detector()
        self._notification_manager = get_notification_manager()
        self._event_handlers = {}
        self._is_initialized = False
    
    def initialize(self) -> None:
        """Initialize all integrations with the health monitoring system."""
        if self._is_initialized:
            logger.warning("HealthAlertIntegrationManager is already initialized")
            return
        
        # Register event handlers for health monitoring events
        self._health_monitor.register_event_handler("agent_unhealthy", self._on_agent_unhealthy)
        self._health_monitor.register_event_handler("agent_recovered", self._on_agent_recovered)
        self._health_monitor.register_event_handler("heartbeat_timeout", self._on_heartbeat_timeout)
        self._health_monitor.register_event_handler("agent_started", self._on_agent_started)
        self._health_monitor.register_event_handler("agent_terminated", self._on_agent_terminated)
        
        # Register event handlers for anomaly detection
        self._anomaly_detector.register_event_handler("memory_anomaly", self._on_memory_anomaly)
        self._anomaly_detector.register_event_handler("latency_anomaly", self._on_latency_anomaly)
        self._anomaly_detector.register_event_handler("error_rate_anomaly", self._on_error_rate_anomaly)
        
        self._is_initialized = True
        logger.info("HealthAlertIntegrationManager initialized")
    
    def shutdown(self) -> None:
        """Shutdown all integrations and unregister event handlers."""
        if not self._is_initialized:
            return
        
        # Unregister event handlers
        self._health_monitor.unregister_event_handler("agent_unhealthy", self._on_agent_unhealthy)
        self._health_monitor.unregister_event_handler("agent_recovered", self._on_agent_recovered)
        self._health_monitor.unregister_event_handler("heartbeat_timeout", self._on_heartbeat_timeout)
        self._health_monitor.unregister_event_handler("agent_started", self._on_agent_started)
        self._health_monitor.unregister_event_handler("agent_terminated", self._on_agent_terminated)
        
        self._anomaly_detector.unregister_event_handler("memory_anomaly", self._on_memory_anomaly)
        self._anomaly_detector.unregister_event_handler("latency_anomaly", self._on_latency_anomaly)
        self._anomaly_detector.unregister_event_handler("error_rate_anomaly", self._on_error_rate_anomaly)
        
        self._is_initialized = False
        logger.info("HealthAlertIntegrationManager shutdown complete")
    
    def register_custom_event_handler(
        self, 
        event_type: str, 
        severity: AlertSeverity,
        message_template: str
    ) -> None:
        """
        Register a custom event handler for health monitoring events.
        
        Args:
            event_type: Type of event to handle
            severity: Severity level for alerts from this event
            message_template: Template string for alert messages. Can include {agent_id} and
                              other event data keys as format placeholders.
        """
        def handler(event_data: Dict[str, Any]) -> None:
            agent_id = event_data.get("agent_id", "unknown")
            try:
                message = message_template.format(**event_data)
            except KeyError:
                # Fallback if template contains keys not in event_data
                message = f"{event_type.replace('_', ' ').title()} event for {agent_id}"
            
            send_health_alert(
                agent_id=agent_id,
                alert_type=event_type,
                message=message,
                severity=severity,
                data=event_data
            )
        
        # Register with health monitor if it's a health event
        if hasattr(self._health_monitor, "register_event_handler"):
            try:
                self._health_monitor.register_event_handler(event_type, handler)
                logger.debug(f"Registered custom handler for health event: {event_type}")
            except ValueError:
                # Not a valid health event type
                pass
        
        # Register with anomaly detector if it's an anomaly event
        if hasattr(self._anomaly_detector, "register_event_handler"):
            try:
                self._anomaly_detector.register_event_handler(event_type, handler)
                logger.debug(f"Registered custom handler for anomaly event: {event_type}")
            except ValueError:
                # Not a valid anomaly event type
                pass
        
        # Save for later unregistration
        self._event_handlers[event_type] = handler
    
    def unregister_custom_event_handler(self, event_type: str) -> None:
        """
        Unregister a custom event handler.
        
        Args:
            event_type: Type of event to unregister handler for
        """
        if event_type not in self._event_handlers:
            return
        
        handler = self._event_handlers[event_type]
        
        # Unregister from health monitor
        if hasattr(self._health_monitor, "unregister_event_handler"):
            try:
                self._health_monitor.unregister_event_handler(event_type, handler)
            except ValueError:
                # Not a valid health event type
                pass
        
        # Unregister from anomaly detector
        if hasattr(self._anomaly_detector, "unregister_event_handler"):
            try:
                self._anomaly_detector.unregister_event_handler(event_type, handler)
            except ValueError:
                # Not a valid anomaly event type
                pass
        
        del self._event_handlers[event_type]
        logger.debug(f"Unregistered custom handler for event: {event_type}")
    
    # Default event handlers
    def _on_agent_unhealthy(self, event_data: Dict[str, Any]) -> None:
        """Handle agent unhealthy event."""
        agent_id = event_data.get("agent_id", "unknown")
        reason = event_data.get("reason", "Unknown reason")
        metric_value = event_data.get("metric_value")
        threshold = event_data.get("threshold")
        
        message = f"Agent {agent_id} is unhealthy: {reason}"
        if metric_value is not None and threshold is not None:
            message += f" (value: {metric_value}, threshold: {threshold})"
        
        send_health_alert(
            agent_id=agent_id,
            alert_type="agent_unhealthy",
            message=message,
            severity=AlertSeverity.ERROR,
            data=event_data
        )
    
    def _on_agent_recovered(self, event_data: Dict[str, Any]) -> None:
        """Handle agent recovered event."""
        agent_id = event_data.get("agent_id", "unknown")
        downtime_seconds = event_data.get("downtime_seconds", 0)
        
        message = f"Agent {agent_id} has recovered"
        if downtime_seconds > 0:
            message += f" after being down for {downtime_seconds} seconds"
        
        send_health_alert(
            agent_id=agent_id,
            alert_type="agent_recovered",
            message=message,
            severity=AlertSeverity.INFO,
            data=event_data
        )
    
    def _on_heartbeat_timeout(self, event_data: Dict[str, Any]) -> None:
        """Handle heartbeat timeout event."""
        agent_id = event_data.get("agent_id", "unknown")
        missed_heartbeats = event_data.get("missed_heartbeats", 0)
        
        message = f"Agent {agent_id} missed {missed_heartbeats} heartbeats"
        
        # Adjust severity based on number of missed heartbeats
        severity = AlertSeverity.WARNING
        if missed_heartbeats >= 5:
            severity = AlertSeverity.ERROR
        if missed_heartbeats >= 10:
            severity = AlertSeverity.CRITICAL
        
        send_health_alert(
            agent_id=agent_id,
            alert_type="heartbeat_timeout",
            message=message,
            severity=severity,
            data=event_data
        )
    
    def _on_agent_started(self, event_data: Dict[str, Any]) -> None:
        """Handle agent started event."""
        agent_id = event_data.get("agent_id", "unknown")
        agent_type = event_data.get("agent_type", "unknown")
        
        message = f"Agent {agent_id} ({agent_type}) started"
        
        send_health_alert(
            agent_id=agent_id,
            alert_type="agent_started",
            message=message,
            severity=AlertSeverity.INFO,
            data=event_data
        )
    
    def _on_agent_terminated(self, event_data: Dict[str, Any]) -> None:
        """Handle agent terminated event."""
        agent_id = event_data.get("agent_id", "unknown")
        reason = event_data.get("reason", "Unknown reason")
        graceful = event_data.get("graceful", False)
        
        message = f"Agent {agent_id} terminated"
        if reason:
            message += f": {reason}"
        
        # Adjust severity based on whether termination was graceful
        severity = AlertSeverity.INFO if graceful else AlertSeverity.WARNING
        
        send_health_alert(
            agent_id=agent_id,
            alert_type="agent_terminated",
            message=message,
            severity=severity,
            data=event_data
        )
    
    def _on_memory_anomaly(self, event_data: Dict[str, Any]) -> None:
        """Handle memory anomaly event."""
        agent_id = event_data.get("agent_id", "unknown")
        current_memory = event_data.get("current_memory_mb", 0)
        threshold = event_data.get("threshold_mb", 0)
        growth_rate = event_data.get("growth_rate_mb_per_min", 0)
        
        message = f"Memory usage anomaly detected for agent {agent_id}"
        message += f": {current_memory}MB used (threshold: {threshold}MB"
        if growth_rate > 0:
            message += f", growing at {growth_rate}MB/min"
        message += ")"
        
        # Adjust severity based on how far over threshold
        severity = AlertSeverity.WARNING
        if current_memory > threshold * 1.5:
            severity = AlertSeverity.ERROR
        if current_memory > threshold * 2:
            severity = AlertSeverity.CRITICAL
        
        send_health_alert(
            agent_id=agent_id,
            alert_type="memory_anomaly",
            message=message,
            severity=severity,
            data=event_data
        )
    
    def _on_latency_anomaly(self, event_data: Dict[str, Any]) -> None:
        """Handle latency anomaly event."""
        agent_id = event_data.get("agent_id", "unknown")
        current_latency = event_data.get("current_latency_ms", 0)
        threshold = event_data.get("threshold_ms", 0)
        percent_increase = event_data.get("percent_increase", 0)
        
        message = f"Latency anomaly detected for agent {agent_id}"
        message += f": {current_latency}ms (threshold: {threshold}ms"
        if percent_increase > 0:
            message += f", {percent_increase}% increase from baseline"
        message += ")"
        
        # Adjust severity based on how far over threshold
        severity = AlertSeverity.WARNING
        if current_latency > threshold * 2:
            severity = AlertSeverity.ERROR
        if current_latency > threshold * 5:
            severity = AlertSeverity.CRITICAL
        
        send_health_alert(
            agent_id=agent_id,
            alert_type="latency_anomaly",
            message=message,
            severity=severity,
            data=event_data
        )
    
    def _on_error_rate_anomaly(self, event_data: Dict[str, Any]) -> None:
        """Handle error rate anomaly event."""
        agent_id = event_data.get("agent_id", "unknown")
        error_count = event_data.get("error_count", 0)
        time_window_minutes = event_data.get("time_window_minutes", 5)
        threshold = event_data.get("threshold", 0)
        
        message = f"Error rate anomaly detected for agent {agent_id}"
        message += f": {error_count} errors in {time_window_minutes} minutes"
        message += f" (threshold: {threshold})"
        
        # Adjust severity based on error count
        severity = AlertSeverity.WARNING
        if error_count >= threshold * 2:
            severity = AlertSeverity.ERROR
        if error_count >= threshold * 5:
            severity = AlertSeverity.CRITICAL
        
        send_health_alert(
            agent_id=agent_id,
            alert_type="error_rate_anomaly",
            message=message,
            severity=severity,
            data=event_data
        )


# Convenience function to get the singleton integration manager
def get_alert_integration_manager() -> HealthAlertIntegrationManager:
    """Get the singleton HealthAlertIntegrationManager instance."""
    return HealthAlertIntegrationManager.get_instance()


# Convenience function to initialize the integration system
def initialize_health_alert_integrations() -> None:
    """Initialize all health alert integrations."""
    manager = get_alert_integration_manager()
    manager.initialize()


# Convenience function to shutdown the integration system
def shutdown_health_alert_integrations() -> None:
    """Shutdown all health alert integrations."""
    manager = get_alert_integration_manager()
    manager.shutdown() 