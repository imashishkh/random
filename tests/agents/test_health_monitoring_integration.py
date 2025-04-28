"""
Integration tests for the health monitoring system.

These tests verify that all components of the health monitoring system work together
correctly, including the interaction between agents, watchdog, circuit breaker,
anomaly detection, and recovery orchestration.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import threading

from src.agents.base_agent import BaseAgent
from src.agents.health import get_health_monitor
from src.agents.health_monitoring.watchdog import AgentWatchdog
from src.agents.health_monitoring.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    get_circuit_breaker_registry
)
from src.agents.health_monitoring.recovery_orchestrator import RecoveryOrchestrator
from src.agents.health_monitoring.anomaly_detector import AnomalyDetector


class MockAgent(BaseAgent):
    """Mock agent for testing health monitoring integration."""
    
    def __init__(self, agent_id, **kwargs):
        super().__init__(
            agent_id=agent_id,
            agent_type="mock",
            agent_name=f"Mock Agent {agent_id}",
            **kwargs
        )
        self.fail_next_execution = False
        self.execution_time = 0.1  # Fast execution by default
    
    def _create_agent(self):
        """Create mock agent for testing."""
        return Mock()
    
    def run(self, input_text, **kwargs):
        """Mock run method that can be configured to succeed or fail."""
        self.send_heartbeat()
        
        if self.fail_next_execution:
            self.fail_next_execution = False
            raise Exception("Simulated agent failure")
        
        time.sleep(self.execution_time)
        return f"Mock response from {self.agent_id}"


@pytest.fixture
def reset_health_components():
    """Reset all health monitoring components between tests."""
    # Reset health monitor
    from src.agents.health import _health_monitor
    _health_monitor = None
    
    # Reset watchdog
    AgentWatchdog._instance = None
    
    # Reset circuit breaker registry
    from src.agents.health_monitoring.circuit_breaker import _registry
    _registry = None
    
    # Reset recovery orchestrator
    RecoveryOrchestrator._instances = {}
    
    # Reset anomaly detector
    AnomalyDetector._instance = None
    
    yield
    
    # Stop any running monitors after the test
    try:
        health_monitor = get_health_monitor()
        if health_monitor.running:
            health_monitor.stop_monitoring()
    except:
        pass


@pytest.fixture
def mock_agent(reset_health_components):
    """Create a mock agent for testing."""
    agent = MockAgent(agent_id="test_agent_1")
    yield agent
    # Clean up
    if hasattr(agent, "_callback_manager"):
        del agent._callback_manager


@pytest.fixture
def health_monitor():
    """Get the health monitor instance."""
    monitor = get_health_monitor()
    monitor.start_monitoring()
    yield monitor
    monitor.stop_monitoring()


def test_agent_registration_and_heartbeat(mock_agent, health_monitor):
    """Test that agents register with health monitoring and send heartbeats."""
    # Agent should already be registered during initialization
    assert "test_agent_1" in health_monitor.agent_metrics
    
    # Check initial health status
    metrics = health_monitor.get_agent_health("test_agent_1")
    assert metrics is not None
    assert metrics["heartbeat"]["last_timestamp"] is not None
    
    # Send a heartbeat and verify it's recorded
    initial_timestamp = metrics["heartbeat"]["last_timestamp"]
    time.sleep(0.1)
    mock_agent.send_heartbeat()
    
    # Get updated metrics
    updated_metrics = health_monitor.get_agent_health("test_agent_1")
    assert updated_metrics["heartbeat"]["last_timestamp"] > initial_timestamp


def test_agent_success_and_failure_tracking(mock_agent, health_monitor):
    """Test that agent success and failure are properly tracked."""
    # Get initial metrics
    initial_metrics = health_monitor.get_agent_health("test_agent_1")
    initial_success = initial_metrics["execution"]["success_count"]
    initial_failure = initial_metrics["execution"]["failure_count"]
    
    # Execute successfully
    result = mock_agent.run("Test input")
    assert "Mock response" in result
    
    # Check success count increased
    metrics = health_monitor.get_agent_health("test_agent_1")
    assert metrics["execution"]["success_count"] == initial_success + 1
    
    # Set up a failure and execute
    mock_agent.fail_next_execution = True
    try:
        mock_agent.run("Test input")
        assert False, "Should have raised an exception"
    except Exception:
        pass
    
    # Check failure count increased
    metrics = health_monitor.get_agent_health("test_agent_1")
    assert metrics["execution"]["failure_count"] == initial_failure + 1


def test_watchdog_integration(mock_agent, health_monitor):
    """Test integration with the watchdog system."""
    # Get the watchdog
    watchdog = AgentWatchdog()
    
    # Register a health check for the agent
    watchdog.register_agent_check(
        agent_id="test_agent_1",
        check_func=lambda: not mock_agent.fail_next_execution,
        interval_seconds=0.5
    )
    
    # Start the watchdog
    watchdog.start()
    
    # Initially, agent should be healthy
    time.sleep(0.6)  # Wait for a check to run
    status = watchdog.get_agent_status("test_agent_1")
    assert status["healthy"] is True
    
    # Make the agent unhealthy
    mock_agent.fail_next_execution = True
    
    # Wait for the check to run again
    time.sleep(0.6)
    status = watchdog.get_agent_status("test_agent_1")
    assert status["healthy"] is False
    
    # Stop the watchdog
    watchdog.stop()


def test_circuit_breaker_integration():
    """Test integration with the circuit breaker system."""
    # Get the circuit breaker registry
    registry = get_circuit_breaker_registry()
    
    # Create a circuit breaker
    circuit = registry.create_circuit(
        name="test_circuit",
        failure_threshold=3,
        recovery_timeout=1.0  # Short timeout for testing
    )
    
    # Initially, circuit should be closed
    assert circuit.state == CircuitState.CLOSED
    
    # Record failures to trip the circuit
    for _ in range(3):
        with pytest.raises(Exception):
            with circuit:
                raise Exception("Simulated failure")
    
    # Circuit should now be open
    assert circuit.state == CircuitState.OPEN
    
    # Attempts should fail fast when circuit is open
    start_time = time.time()
    with pytest.raises(Exception) as excinfo:
        with circuit:
            pass
    assert "Circuit breaker" in str(excinfo.value)
    assert time.time() - start_time < 0.1  # Should fail fast
    
    # Wait for recovery timeout
    time.sleep(1.1)
    
    # Circuit should now be half-open
    assert circuit.state == CircuitState.HALF_OPEN
    
    # Successful operation should close the circuit
    with circuit:
        pass
    
    # Circuit should now be closed again
    assert circuit.state == CircuitState.CLOSED


def test_recovery_orchestrator_integration(mock_agent, health_monitor):
    """Test integration with the recovery orchestrator."""
    # Get the recovery orchestrator
    orchestrator = RecoveryOrchestrator()
    
    # Register a mock agent for recovery testing
    with patch("src.agents.health_monitoring.recovery_orchestrator.get_agent_registry") as mock_registry:
        # Setup mock registry
        registry = Mock()
        registry.get_agent.return_value = mock_agent
        registry.stop_agent.return_value = True
        registry.start_agent.return_value = True
        mock_registry.return_value = registry
        
        # Submit a recovery request
        recovery_id = orchestrator.submit_recovery_request(
            agent_id="test_agent_1",
            strategy="restart",
            priority=1,
            reason="Test recovery"
        )
        
        # Wait for processing
        time.sleep(0.5)
        
        # Check recovery status
        status = orchestrator.get_recovery_status(recovery_id)
        assert status == "succeeded"
        
        # Verify agent registry methods were called
        registry.get_agent.assert_called_with("test_agent_1")
        registry.stop_agent.assert_called_with("test_agent_1")
        registry.start_agent.assert_called_with("test_agent_1")


def test_anomaly_detection_integration(health_monitor):
    """Test integration with the anomaly detection system."""
    # Get the anomaly detector
    detector = AnomalyDetector()
    
    # Setup a mock callback to capture notifications
    callback = Mock()
    detector.register_callback(callback)
    
    # Start the detector
    detector.start()
    
    # Create a new agent with high execution time to trigger latency anomalies
    slow_agent = MockAgent(agent_id="slow_agent")
    slow_agent.execution_time = 1.0  # 1 second, which is high for this test
    
    # Run the agent multiple times to generate metrics
    for _ in range(5):
        slow_agent.run("Test input")
    
    # Wait for anomaly detection cycle
    time.sleep(detector._detection_interval + 1)
    
    # Check if callback was called with anomalies
    assert callback.call_count > 0
    
    # Cleanup
    detector.stop()
    
    
def test_end_to_end_health_monitoring(reset_health_components):
    """Test end-to-end health monitoring flow."""
    # Initialize components
    health_monitor = get_health_monitor()
    watchdog = AgentWatchdog()
    detector = AnomalyDetector()
    
    # Start monitoring
    health_monitor.start_monitoring()
    watchdog.start()
    detector.start()
    
    # Create an agent that will fail
    failing_agent = MockAgent(agent_id="failing_agent")
    
    # Register a check with recovery action
    watchdog.register_agent_check(
        agent_id="failing_agent",
        check_func=lambda: not failing_agent.fail_next_execution,
        interval_seconds=0.5,
        actions=["restart"]
    )
    
    # Run agent successfully first
    failing_agent.run("Test input")
    
    # Setup to track recovery calls
    recovery_calls = []
    original_restart = health_monitor._restart_agent
    
    def mock_restart(agent_id, metrics):
        recovery_calls.append(agent_id)
        failing_agent.fail_next_execution = False  # Fix the agent
        return original_restart(agent_id, metrics)
    
    # Replace the restart method
    health_monitor._restart_agent = mock_restart
    
    # Make agent fail
    failing_agent.fail_next_execution = True
    
    try:
        failing_agent.run("Test input")
    except:
        pass  # Expected to fail
    
    # Wait for recovery to happen
    time.sleep(2.0)
    
    # Check that recovery was triggered
    assert "failing_agent" in recovery_calls
    
    # Agent should now be healthy again
    status = watchdog.get_agent_status("failing_agent")
    assert status["healthy"] is True
    
    # Stop monitoring components
    health_monitor.stop_monitoring()
    watchdog.stop()
    detector.stop() 