"""
Tests for the Forex-specific watchdog monitoring functionality.
"""

import time
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from typing import Dict, List, Any

from src.agents.health_monitoring.watchdog import (
    AgentWatchdog,
    ForexWatchdogCheck,
    WatchdogPriority,
    WatchdogAction
)

class MockVolatilityService:
    """Mock service for testing market volatility features."""
    
    def __init__(self, volatility_levels: Dict[str, float] = None):
        self.volatility_levels = volatility_levels or {}
        self.is_active = True
        self.news_events = []
    
    def get_volatility(self, market_pair: str) -> float:
        """Get mock volatility level for a market pair."""
        return self.volatility_levels.get(market_pair, 0.3)
    
    def is_active_trading_hours(self) -> bool:
        """Check if currently in active trading hours."""
        return self.is_active
    
    def get_recent_news_events(self) -> List[str]:
        """Get mock recent market news events."""
        return self.news_events

@pytest.fixture
def volatility_service():
    """Fixture providing a mock volatility service."""
    return MockVolatilityService()

@pytest.fixture
def watchdog():
    """Fixture providing a clean watchdog instance for each test."""
    # Reset the singleton instance
    AgentWatchdog._instance = None
    return AgentWatchdog()

def test_forex_check_initialization():
    """Test that ForexWatchdogCheck initializes correctly."""
    check = ForexWatchdogCheck(
        agent_id="test_agent",
        check_func=lambda: True,
        interval_seconds=15.0,
        market_pairs=["EUR/USD", "GBP/USD"],
        volatility_service=MockVolatilityService(),
        description="Test forex check"
    )
    
    assert check.agent_id == "test_agent"
    assert check.interval_seconds == 15.0
    assert check.market_pairs == ["EUR/USD", "GBP/USD"]
    assert check.trade_latency_threshold_ms == 500.0  # Default value
    assert check.quote_staleness_threshold_ms == 2000.0  # Default value
    assert check.market_data_gap_threshold == 5  # Default value
    assert isinstance(check.trade_latencies, dict)
    assert isinstance(check.last_quote_times, dict)
    assert isinstance(check.market_data_gaps, dict)

def test_forex_metrics_tracking(watchdog: AgentWatchdog):
    """Test that Forex-specific metrics are tracked correctly."""
    agent_id = "test_forex_agent"
    market_pairs = ["EUR/USD", "GBP/USD"]
    
    # Register a Forex agent
    watchdog.register_forex_agent_check(
        agent_id=agent_id,
        market_pairs=market_pairs,
        volatility_service=MockVolatilityService(),
        check_func=lambda: True
    )
    
    # Update various metrics
    watchdog.update_forex_metrics(
        agent_id=agent_id,
        market_pair="EUR/USD",
        trade_latency=100.0,
        quote_time=time.time(),
        has_market_data_gap=False
    )
    
    # Get status and verify metrics
    status = watchdog.get_forex_agent_status(agent_id)
    assert status is not None
    assert "forex_metrics" in status
    
    metrics = status["forex_metrics"]
    assert "EUR/USD" in metrics["market_pairs"]
    assert metrics["trade_latencies"]["EUR/USD"] == 100.0
    assert metrics["market_data_gaps"]["EUR/USD"] == 0

def test_market_aware_thresholds(watchdog: AgentWatchdog):
    """Test that thresholds adjust based on market conditions."""
    agent_id = "test_forex_agent"
    market_pairs = ["EUR/USD"]
    
    # Create volatility service with high volatility
    vol_service = MockVolatilityService({"EUR/USD": 0.9})  # High volatility
    
    # Register agent
    watchdog.register_forex_agent_check(
        agent_id=agent_id,
        market_pairs=market_pairs,
        volatility_service=vol_service,
        check_func=lambda: True,
        trade_latency_threshold_ms=500.0
    )
    
    # Get the check
    status = watchdog.get_forex_agent_status(agent_id)
    assert status is not None
    
    # Verify thresholds were adjusted for high volatility
    check = next(
        check for check in watchdog._checks_by_agent[agent_id] 
        if isinstance(check, ForexWatchdogCheck)
    )
    check._adjust_thresholds_for_market_conditions()
    
    # Thresholds should be higher due to high volatility
    assert check.trade_latency_threshold_ms > 500.0
    assert check.max_consecutive_failures > 3  # Default value

def test_forex_health_check_warnings(watchdog: AgentWatchdog):
    """Test that appropriate warnings are generated for various health issues."""
    agent_id = "test_forex_agent"
    market_pairs = ["EUR/USD"]
    
    # Register agent
    watchdog.register_forex_agent_check(
        agent_id=agent_id,
        market_pairs=market_pairs,
        volatility_service=MockVolatilityService(),
        check_func=lambda: True,
        trade_latency_threshold_ms=500.0,
        quote_staleness_threshold_ms=2000.0
    )
    
    # Simulate high latency
    watchdog.update_forex_metrics(
        agent_id=agent_id,
        market_pair="EUR/USD",
        trade_latency=1000.0  # Above threshold
    )
    
    # Get the check and run it
    check = next(
        check for check in watchdog._checks_by_agent[agent_id] 
        if isinstance(check, ForexWatchdogCheck)
    )
    is_healthy, error_message = check.run_check()
    
    assert not is_healthy
    assert "High trade latency" in error_message
    assert "EUR/USD" in error_message

def test_forex_agent_recovery_context(watchdog: AgentWatchdog):
    """Test that recovery actions include market context."""
    agent_id = "test_forex_agent"
    market_pairs = ["EUR/USD"]
    
    # Create volatility service with high volatility and news
    vol_service = MockVolatilityService({"EUR/USD": 0.9})
    vol_service.news_events = ["Major economic announcement"]
    
    # Register agent with a failing check
    watchdog.register_forex_agent_check(
        agent_id=agent_id,
        market_pairs=market_pairs,
        volatility_service=vol_service,
        check_func=lambda: False,  # Always fail
        actions=[WatchdogAction.NOTIFY]
    )
    
    # Process checks (this will trigger recovery actions)
    watchdog.start()
    time.sleep(0.1)  # Allow check to process
    watchdog.stop()
    
    # Verify recovery history includes market context
    history = watchdog.get_recovery_history()
    assert len(history) > 0
    latest_recovery = history[-1]
    assert "Market Context" in latest_recovery["details"]
    assert "High volatility" in latest_recovery["details"]
    assert "economic announcement" in latest_recovery["details"]

def test_multiple_forex_agents(watchdog: AgentWatchdog):
    """Test monitoring multiple Forex agents simultaneously."""
    agents = {
        "agent1": ["EUR/USD", "GBP/USD"],
        "agent2": ["USD/JPY", "AUD/USD"]
    }
    
    # Register multiple agents
    for agent_id, pairs in agents.items():
        watchdog.register_forex_agent_check(
            agent_id=agent_id,
            market_pairs=pairs,
            volatility_service=MockVolatilityService(),
            check_func=lambda: True
        )
    
    # Update metrics for all agents
    for agent_id, pairs in agents.items():
        for pair in pairs:
            watchdog.update_forex_metrics(
                agent_id=agent_id,
                market_pair=pair,
                trade_latency=100.0,
                quote_time=time.time()
            )
    
    # Get all statuses
    statuses = watchdog.get_all_forex_agent_statuses()
    
    assert len(statuses) == len(agents)
    for agent_id, status in statuses.items():
        assert status is not None
        assert "forex_metrics" in status
        metrics = status["forex_metrics"]
        expected_pairs = agents[agent_id]
        assert all(pair in metrics["market_pairs"] for pair in expected_pairs)

def test_forex_check_cleanup(watchdog: AgentWatchdog):
    """Test proper cleanup of Forex agent resources."""
    agent_id = "test_forex_agent"
    market_pairs = ["EUR/USD"]
    
    # Register agent
    watchdog.register_forex_agent_check(
        agent_id=agent_id,
        market_pairs=market_pairs,
        volatility_service=MockVolatilityService(),
        check_func=lambda: True
    )
    
    # Verify registration
    assert agent_id in watchdog.forex_agents
    assert agent_id in watchdog.market_pairs_by_agent
    
    # Remove agent
    watchdog._remove_agent_checks(agent_id)
    
    # Verify cleanup
    assert agent_id not in watchdog.forex_agents
    assert agent_id not in watchdog.market_pairs_by_agent
    assert agent_id not in watchdog._checks_by_agent 