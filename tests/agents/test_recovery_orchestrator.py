"""
Tests for the Recovery Orchestrator component of the health monitoring system.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from src.agents.health_monitoring.recovery_orchestrator import (
    RecoveryOrchestrator,
    RecoveryStrategy,
    RecoveryRequest,
    RecoveryStatus
)


@pytest.fixture
def mock_agent_registry():
    """Mock agent registry for testing."""
    mock_registry = Mock()
    mock_registry.get_agent.return_value = Mock()
    mock_registry.stop_agent.return_value = True
    mock_registry.start_agent.return_value = True
    return mock_registry


@pytest.fixture
def orchestrator():
    """Fixture providing a fresh recovery orchestrator for each test."""
    # Reset the singleton instance for testing
    RecoveryOrchestrator._instances = {}
    return RecoveryOrchestrator()


def test_orchestrator_initialization():
    """Test that the recovery orchestrator initializes correctly."""
    orchestrator = RecoveryOrchestrator()
    
    # Check default handlers are registered
    assert RecoveryStrategy.RESTART in orchestrator._default_recovery_handlers
    assert RecoveryStrategy.RECREATE in orchestrator._default_recovery_handlers
    assert RecoveryStrategy.FAILOVER in orchestrator._default_recovery_handlers
    assert RecoveryStrategy.THROTTLED in orchestrator._default_recovery_handlers
    assert RecoveryStrategy.ISOLATION in orchestrator._default_recovery_handlers


def test_submit_recovery_request(orchestrator):
    """Test submitting a recovery request."""
    agent_id = "test_agent"
    strategy = RecoveryStrategy.RESTART
    
    # Submit a request
    recovery_id = orchestrator.submit_recovery_request(
        agent_id=agent_id,
        strategy=strategy,
        priority=1,
        reason="Test recovery"
    )
    
    # Verify request was created and queued
    assert recovery_id is not None
    assert len(orchestrator._recovery_queue) == 1
    assert orchestrator._recovery_queue[0].agent_id == agent_id
    assert orchestrator._recovery_queue[0].strategy == strategy
    assert orchestrator._recovery_queue[0].status == RecoveryStatus.PENDING


def test_get_recovery_status(orchestrator):
    """Test getting recovery status."""
    # Submit a request
    recovery_id = orchestrator.submit_recovery_request(
        agent_id="test_agent",
        strategy=RecoveryStrategy.RESTART,
        priority=1,
        reason="Test recovery"
    )
    
    # Check status
    status = orchestrator.get_recovery_status(recovery_id)
    assert status == RecoveryStatus.PENDING


@patch("src.agents.health_monitoring.recovery_orchestrator.get_agent_registry")
def test_default_restart_handler(mock_get_registry, orchestrator, mock_agent_registry):
    """Test the default restart handler."""
    agent_id = "test_agent"
    mock_get_registry.return_value = mock_agent_registry
    
    # Call restart handler
    result = orchestrator._default_restart_handler(agent_id)
    
    # Verify agent was restarted
    assert result is True
    mock_agent_registry.get_agent.assert_called_once_with(agent_id)
    mock_agent_registry.stop_agent.assert_called_once_with(agent_id)
    mock_agent_registry.start_agent.assert_called_once_with(agent_id)


@patch("src.agents.health_monitoring.recovery_orchestrator.get_agent_registry")
def test_process_recovery_request_success(mock_get_registry, orchestrator, mock_agent_registry):
    """Test successful processing of a recovery request."""
    agent_id = "test_agent"
    mock_get_registry.return_value = mock_agent_registry
    
    # Submit request
    recovery_id = orchestrator.submit_recovery_request(
        agent_id=agent_id,
        strategy=RecoveryStrategy.RESTART,
        priority=1,
        reason="Test recovery"
    )
    
    # Process the request (manually call the method that would be called by the thread)
    orchestrator._process_recovery_requests()
    
    # Verify request was processed successfully
    assert orchestrator.get_recovery_status(recovery_id) == RecoveryStatus.SUCCEEDED


@patch("src.agents.health_monitoring.recovery_orchestrator.get_agent_registry")
def test_process_recovery_request_failure(mock_get_registry, orchestrator):
    """Test handling of a failed recovery request."""
    agent_id = "test_agent"
    
    # Configure registry to fail
    mock_registry = mock_get_registry.return_value
    mock_registry.get_agent.return_value = Mock()
    mock_registry.stop_agent.return_value = True
    mock_registry.start_agent.return_value = False  # Failure
    
    # Submit request
    recovery_id = orchestrator.submit_recovery_request(
        agent_id=agent_id,
        strategy=RecoveryStrategy.RESTART,
        priority=1,
        reason="Test recovery",
        max_attempts=1  # Only try once
    )
    
    # Process the request
    orchestrator._process_recovery_requests()
    
    # Verify request failed
    assert orchestrator.get_recovery_status(recovery_id) == RecoveryStatus.FAILED


def test_register_custom_recovery_handler(orchestrator):
    """Test registering a custom recovery handler."""
    agent_type = "custom_agent"
    strategy = RecoveryStrategy.RESTART
    
    # Create a mock handler
    mock_handler = Mock(return_value=True)
    
    # Register the handler
    orchestrator.register_recovery_handler(agent_type, strategy, mock_handler)
    
    # Verify handler was registered
    assert agent_type in orchestrator._recovery_handlers
    assert strategy in orchestrator._recovery_handlers[agent_type]
    assert orchestrator._recovery_handlers[agent_type][strategy] == mock_handler


@patch("src.agents.health_monitoring.recovery_orchestrator.get_agent_registry")
def test_recovery_with_backoff(mock_get_registry, orchestrator):
    """Test recovery with backoff for repeated failures."""
    agent_id = "test_agent"
    
    # Configure registry to fail
    mock_registry = mock_get_registry.return_value
    mock_registry.get_agent.return_value = Mock()
    mock_registry.stop_agent.return_value = True
    mock_registry.start_agent.side_effect = [False, False, True]  # Fail twice, then succeed
    
    # Submit request with multiple attempts
    recovery_id = orchestrator.submit_recovery_request(
        agent_id=agent_id,
        strategy=RecoveryStrategy.RESTART,
        priority=1,
        reason="Test recovery",
        max_attempts=3
    )
    
    # Process recovery - should fail first attempt
    orchestrator._process_recovery_requests()
    
    # First attempt should be retrying
    assert orchestrator.get_recovery_status(recovery_id) == RecoveryStatus.RETRYING
    
    # Get the request and check backoff timing
    request = orchestrator._get_recovery_request(recovery_id)
    assert request.attempt_count == 1
    
    # Process again for the last successful attempt
    orchestrator._process_recovery_requests()
    orchestrator._process_recovery_requests()
    
    # Verify eventually succeeded after retries
    assert orchestrator.get_recovery_status(recovery_id) == RecoveryStatus.SUCCEEDED
    assert mock_registry.start_agent.call_count == 3


def test_recovery_history(orchestrator):
    """Test tracking and retrieving recovery history."""
    # Submit a couple of requests
    recovery_id1 = orchestrator.submit_recovery_request(
        agent_id="agent1",
        strategy=RecoveryStrategy.RESTART,
        priority=1,
        reason="Test recovery 1"
    )
    
    recovery_id2 = orchestrator.submit_recovery_request(
        agent_id="agent2",
        strategy=RecoveryStrategy.RECREATE,
        priority=2,
        reason="Test recovery 2"
    )
    
    # Manually mark them as completed for this test
    request1 = orchestrator._get_recovery_request(recovery_id1)
    request1.status = RecoveryStatus.SUCCEEDED
    orchestrator._recovery_history.append(request1)
    
    request2 = orchestrator._get_recovery_request(recovery_id2)
    request2.status = RecoveryStatus.FAILED
    orchestrator._recovery_history.append(request2)
    
    # Get history
    history = orchestrator.get_recovery_history()
    
    # Verify history contains both requests
    assert len(history) == 2
    assert any(entry["recovery_id"] == recovery_id1 for entry in history)
    assert any(entry["recovery_id"] == recovery_id2 for entry in history)
    
    # Get history for specific agent
    agent1_history = orchestrator.get_recovery_history(agent_id="agent1")
    assert len(agent1_history) == 1
    assert agent1_history[0]["agent_id"] == "agent1"


def test_cancel_recovery_request(orchestrator):
    """Test canceling a pending recovery request."""
    # Submit a request
    recovery_id = orchestrator.submit_recovery_request(
        agent_id="test_agent",
        strategy=RecoveryStrategy.RESTART,
        priority=1,
        reason="Test recovery"
    )
    
    # Cancel the request
    result = orchestrator.cancel_recovery_request(recovery_id)
    
    # Verify cancellation
    assert result is True
    assert orchestrator.get_recovery_status(recovery_id) == RecoveryStatus.CANCELLED 