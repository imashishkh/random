"""
Unit tests for the RiskAwareAgent mixin.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio

from src.agents.risk import RiskAwareAgent, require_risk_approval
from src.agents.base_agent import BaseAgent


class TestAgent(RiskAwareAgent, BaseAgent):
    """Test implementation of RiskAwareAgent for testing."""
    
    def __init__(self, agent_id, max_risk_per_trade=1.0, **kwargs):
        super().__init__(agent_id=agent_id, max_risk_per_trade=max_risk_per_trade, **kwargs)
    
    @require_risk_approval
    def execute_trade(self, symbol, entry_price, is_long, stop_loss):
        """Test trade execution method that requires risk approval."""
        return {"status": "executed", "symbol": symbol}
    
    @require_risk_approval
    async def execute_trade_async(self, symbol, entry_price, is_long, stop_loss):
        """Test async trade execution method that requires risk approval."""
        return {"status": "executed", "symbol": symbol}
    
    def execute_without_approval(self, symbol):
        """Test method that doesn't require risk approval."""
        return {"status": "executed", "symbol": symbol}


@pytest.fixture
def risk_aware_agent():
    """Create a RiskAwareAgent instance for testing."""
    return TestAgent(agent_id="test-agent", max_risk_per_trade=1.0)


@pytest.fixture
def mock_risk_manager():
    """Create a mock risk manager."""
    risk_manager = MagicMock()
    risk_manager.approve_trade = MagicMock(return_value=True)
    risk_manager.get_position_size = MagicMock(return_value=1.0)
    risk_manager.calculate_max_risk = MagicMock(return_value=100.0)
    return risk_manager


class TestRiskAwareAgent:
    """Tests for the RiskAwareAgent mixin."""

    def test_initialization(self):
        """Test RiskAwareAgent initialization."""
        agent = TestAgent(agent_id="test-agent", max_risk_per_trade=2.5)
        
        assert agent.agent_id == "test-agent"
        assert agent.max_risk_per_trade == 2.5
        assert agent._risk_manager is None

    def test_set_risk_manager(self, risk_aware_agent, mock_risk_manager):
        """Test setting the risk manager."""
        risk_aware_agent.set_risk_manager(mock_risk_manager)
        
        assert risk_aware_agent._risk_manager is mock_risk_manager

    def test_check_risk_status_no_manager(self, risk_aware_agent):
        """Test checking risk status with no risk manager set."""
        status = risk_aware_agent.check_risk_status()
        
        assert "Risk Manager" in status
        assert status["Risk Manager"] == "Not configured"

    def test_check_risk_status_with_manager(self, risk_aware_agent, mock_risk_manager):
        """Test checking risk status with a risk manager set."""
        # Setup mock risk manager with status data
        mock_risk_manager.get_status = MagicMock(return_value={
            "Current Portfolio Risk": 500,
            "Max Portfolio Risk": 1000
        })
        
        risk_aware_agent.set_risk_manager(mock_risk_manager)
        status = risk_aware_agent.check_risk_status()
        
        assert "Risk Manager" in status
        assert status["Risk Manager"] == "Configured"
        assert "Current Portfolio Risk" in status
        assert status["Current Portfolio Risk"] == 500
        assert "Max Portfolio Risk" in status
        assert status["Max Portfolio Risk"] == 1000

    def test_trade_with_risk_approval_no_manager(self, risk_aware_agent):
        """Test trade execution with no risk manager set."""
        with pytest.raises(ValueError) as excinfo:
            risk_aware_agent.execute_trade("EUR/USD", 1.1000, True, 1.0950)
        
        assert "Risk manager not configured" in str(excinfo.value)

    def test_trade_with_risk_approval_success(self, risk_aware_agent, mock_risk_manager):
        """Test successful trade execution with risk approval."""
        risk_aware_agent.set_risk_manager(mock_risk_manager)
        
        result = risk_aware_agent.execute_trade("EUR/USD", 1.1000, True, 1.0950)
        
        # Verify risk manager was called properly
        mock_risk_manager.approve_trade.assert_called_once_with(
            symbol="EUR/USD",
            entry_price=1.1000,
            is_long=True,
            stop_loss=1.0950,
            max_risk_per_trade=1.0
        )
        
        # Verify result
        assert result["status"] == "executed"
        assert result["symbol"] == "EUR/USD"

    def test_trade_with_risk_approval_rejected(self, risk_aware_agent, mock_risk_manager):
        """Test rejected trade execution with risk approval."""
        # Setup mock to reject the trade
        mock_risk_manager.approve_trade = MagicMock(return_value=False)
        risk_aware_agent.set_risk_manager(mock_risk_manager)
        
        with pytest.raises(ValueError) as excinfo:
            risk_aware_agent.execute_trade("EUR/USD", 1.1000, True, 1.0950)
        
        assert "Trade not approved by risk manager" in str(excinfo.value)
        mock_risk_manager.approve_trade.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_trade_with_risk_approval_success(self, risk_aware_agent, mock_risk_manager):
        """Test successful async trade execution with risk approval."""
        risk_aware_agent.set_risk_manager(mock_risk_manager)
        
        result = await risk_aware_agent.execute_trade_async("EUR/USD", 1.1000, True, 1.0950)
        
        # Verify risk manager was called properly
        mock_risk_manager.approve_trade.assert_called_once_with(
            symbol="EUR/USD",
            entry_price=1.1000,
            is_long=True,
            stop_loss=1.0950,
            max_risk_per_trade=1.0
        )
        
        # Verify result
        assert result["status"] == "executed"
        assert result["symbol"] == "EUR/USD"

    @pytest.mark.asyncio
    async def test_async_trade_with_risk_approval_rejected(self, risk_aware_agent, mock_risk_manager):
        """Test rejected async trade execution with risk approval."""
        # Setup mock to reject the trade
        mock_risk_manager.approve_trade = MagicMock(return_value=False)
        risk_aware_agent.set_risk_manager(mock_risk_manager)
        
        with pytest.raises(ValueError) as excinfo:
            await risk_aware_agent.execute_trade_async("EUR/USD", 1.1000, True, 1.0950)
        
        assert "Trade not approved by risk manager" in str(excinfo.value)
        mock_risk_manager.approve_trade.assert_called_once()

    def test_execute_without_approval(self, risk_aware_agent):
        """Test execution of a method that doesn't require risk approval."""
        # This should work even without a risk manager set
        result = risk_aware_agent.execute_without_approval("EUR/USD")
        
        assert result["status"] == "executed"
        assert result["symbol"] == "EUR/USD"

    def test_calculate_position_size_no_manager(self, risk_aware_agent):
        """Test calculating position size with no risk manager set."""
        with pytest.raises(ValueError) as excinfo:
            risk_aware_agent.calculate_position_size(
                symbol="EUR/USD",
                entry_price=1.1000,
                stop_loss=1.0950
            )
        
        assert "Risk manager not configured" in str(excinfo.value)

    def test_calculate_position_size_with_manager(self, risk_aware_agent, mock_risk_manager):
        """Test calculating position size with a risk manager set."""
        risk_aware_agent.set_risk_manager(mock_risk_manager)
        
        position_size = risk_aware_agent.calculate_position_size(
            symbol="EUR/USD",
            entry_price=1.1000,
            stop_loss=1.0950
        )
        
        assert position_size == 1.0
        mock_risk_manager.get_position_size.assert_called_once_with(
            symbol="EUR/USD",
            entry_price=1.1000,
            stop_loss=1.0950,
            risk_per_trade=1.0
        )

    def test_calculate_max_risk_no_manager(self, risk_aware_agent):
        """Test calculating max risk with no risk manager set."""
        with pytest.raises(ValueError) as excinfo:
            risk_aware_agent.calculate_max_risk()
        
        assert "Risk manager not configured" in str(excinfo.value)

    def test_calculate_max_risk_with_manager(self, risk_aware_agent, mock_risk_manager):
        """Test calculating max risk with a risk manager set."""
        risk_aware_agent.set_risk_manager(mock_risk_manager)
        
        max_risk = risk_aware_agent.calculate_max_risk()
        
        assert max_risk == 100.0
        mock_risk_manager.calculate_max_risk.assert_called_once()

    def test_require_risk_approval_decorator(self):
        """Test the require_risk_approval decorator behavior."""
        # Create a test function with the decorator
        @require_risk_approval
        def test_func(self, symbol, entry_price, is_long, stop_loss, extra_param=None):
            return {"symbol": symbol, "extra": extra_param}
        
        # Verify the function signature is preserved
        import inspect
        sig = inspect.signature(test_func)
        params = list(sig.parameters.keys())
        
        assert params[0] == "self"
        assert params[1] == "symbol"
        assert params[2] == "entry_price"
        assert params[3] == "is_long"
        assert params[4] == "stop_loss"
        assert params[5] == "extra_param"

    def test_risk_aware_with_custom_risk_params(self):
        """Test RiskAwareAgent with custom risk parameters."""
        agent = TestAgent(
            agent_id="custom-risk-agent",
            max_risk_per_trade=3.0,
            max_daily_risk=10.0,
            risk_tolerance="high"
        )
        
        assert agent.max_risk_per_trade == 3.0
        assert agent.max_daily_risk == 10.0
        assert agent.risk_tolerance == "high" 