"""
Unit tests for the RiskManager class.
"""

import pytest
from unittest.mock import MagicMock, patch
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from src.agents.risk.manager import RiskManager


@pytest.fixture
def risk_manager():
    """Create a RiskManager instance for testing."""
    return RiskManager(
        max_risk_per_trade=1.0,
        max_portfolio_risk=5.0,
        max_drawdown=20.0
    )


@pytest.fixture
def mock_account():
    """Create a mock account for testing."""
    account = MagicMock()
    account.balance = 10000.0
    account.equity = 10000.0
    account.get_open_positions.return_value = []
    account.get_position_value.return_value = 0.0
    account.get_drawdown.return_value = 5.0
    return account


class TestRiskManager:
    """Tests for the RiskManager class."""

    def test_initialization(self):
        """Test RiskManager initialization with default and custom parameters."""
        # Test with default parameters
        risk_manager = RiskManager()
        
        assert risk_manager.max_risk_per_trade == 2.0
        assert risk_manager.max_portfolio_risk == 8.0
        assert risk_manager.max_drawdown == 25.0
        assert risk_manager.risk_multiplier == 1.0
        
        # Test with custom parameters
        custom_risk_manager = RiskManager(
            max_risk_per_trade=1.5,
            max_portfolio_risk=6.0,
            max_drawdown=15.0,
            risk_multiplier=0.8,
            correlation_threshold=0.7
        )
        
        assert custom_risk_manager.max_risk_per_trade == 1.5
        assert custom_risk_manager.max_portfolio_risk == 6.0
        assert custom_risk_manager.max_drawdown == 15.0
        assert custom_risk_manager.risk_multiplier == 0.8
        assert custom_risk_manager.correlation_threshold == 0.7

    def test_set_account(self, risk_manager, mock_account):
        """Test setting the account for the risk manager."""
        risk_manager.set_account(mock_account)
        
        assert risk_manager._account is mock_account

    def test_approve_trade_no_account(self, risk_manager):
        """Test trade approval with no account set."""
        with pytest.raises(ValueError) as excinfo:
            risk_manager.approve_trade(
                symbol="EUR/USD",
                entry_price=1.1000,
                is_long=True,
                stop_loss=1.0950
            )
        
        assert "Account not configured for risk manager" in str(excinfo.value)

    def test_approve_trade_success(self, risk_manager, mock_account):
        """Test successful trade approval."""
        # Setup
        risk_manager.set_account(mock_account)
        risk_manager.calculate_portfolio_risk = MagicMock(return_value=2.0)
        risk_manager.check_correlation_risk = MagicMock(return_value=True)
        risk_manager.check_drawdown_limit = MagicMock(return_value=True)
        risk_manager.get_position_size = MagicMock(return_value=1.0)
        
        # Test
        approved = risk_manager.approve_trade(
            symbol="EUR/USD",
            entry_price=1.1000,
            is_long=True,
            stop_loss=1.0950
        )
        
        assert approved is True
        
        # Verify all checks were called
        risk_manager.calculate_portfolio_risk.assert_called_once()
        risk_manager.check_correlation_risk.assert_called_once()
        risk_manager.check_drawdown_limit.assert_called_once()

    def test_approve_trade_portfolio_risk_exceeded(self, risk_manager, mock_account):
        """Test trade rejection due to portfolio risk limit exceeded."""
        # Setup
        risk_manager.set_account(mock_account)
        risk_manager.calculate_portfolio_risk = MagicMock(return_value=6.0)  # > max_portfolio_risk (5.0)
        
        # Test
        approved = risk_manager.approve_trade(
            symbol="EUR/USD",
            entry_price=1.1000,
            is_long=True,
            stop_loss=1.0950
        )
        
        assert approved is False
        risk_manager.calculate_portfolio_risk.assert_called_once()

    def test_approve_trade_correlation_risk(self, risk_manager, mock_account):
        """Test trade rejection due to correlation risk."""
        # Setup
        risk_manager.set_account(mock_account)
        risk_manager.calculate_portfolio_risk = MagicMock(return_value=2.0)
        risk_manager.check_correlation_risk = MagicMock(return_value=False)
        
        # Test
        approved = risk_manager.approve_trade(
            symbol="EUR/USD",
            entry_price=1.1000,
            is_long=True,
            stop_loss=1.0950
        )
        
        assert approved is False
        risk_manager.calculate_portfolio_risk.assert_called_once()
        risk_manager.check_correlation_risk.assert_called_once()

    def test_approve_trade_drawdown_exceeded(self, risk_manager, mock_account):
        """Test trade rejection due to drawdown limit exceeded."""
        # Setup
        risk_manager.set_account(mock_account)
        risk_manager.calculate_portfolio_risk = MagicMock(return_value=2.0)
        risk_manager.check_correlation_risk = MagicMock(return_value=True)
        risk_manager.check_drawdown_limit = MagicMock(return_value=False)
        
        # Test
        approved = risk_manager.approve_trade(
            symbol="EUR/USD",
            entry_price=1.1000,
            is_long=True,
            stop_loss=1.0950
        )
        
        assert approved is False
        risk_manager.calculate_portfolio_risk.assert_called_once()
        risk_manager.check_correlation_risk.assert_called_once()
        risk_manager.check_drawdown_limit.assert_called_once()

    def test_get_position_size_no_account(self, risk_manager):
        """Test get_position_size with no account set."""
        with pytest.raises(ValueError) as excinfo:
            risk_manager.get_position_size(
                symbol="EUR/USD",
                entry_price=1.1000,
                stop_loss=1.0950
            )
        
        assert "Account not configured for risk manager" in str(excinfo.value)

    def test_get_position_size(self, risk_manager, mock_account):
        """Test position size calculation."""
        # Setup
        risk_manager.set_account(mock_account)
        
        # Test
        position_size = risk_manager.get_position_size(
            symbol="EUR/USD",
            entry_price=1.1000,
            stop_loss=1.0950,
            risk_per_trade=1.0
        )
        
        # Calculate expected position size
        account_balance = 10000.0
        risk_amount = account_balance * (1.0 / 100)  # 1% risk = $100
        price_risk = abs(1.1000 - 1.0950)  # 0.0050
        expected_position_size = risk_amount / price_risk  # $100 / 0.0050 = 20000 units
        
        assert position_size == pytest.approx(expected_position_size)

    def test_get_position_size_custom_risk(self, risk_manager, mock_account):
        """Test position size calculation with custom risk percentage."""
        # Setup
        risk_manager.set_account(mock_account)
        
        # Test
        position_size = risk_manager.get_position_size(
            symbol="EUR/USD",
            entry_price=1.1000,
            stop_loss=1.0950,
            risk_per_trade=2.0  # 2% risk
        )
        
        # Calculate expected position size
        account_balance = 10000.0
        risk_amount = account_balance * (2.0 / 100)  # 2% risk = $200
        price_risk = abs(1.1000 - 1.0950)  # 0.0050
        expected_position_size = risk_amount / price_risk  # $200 / 0.0050 = 40000 units
        
        assert position_size == pytest.approx(expected_position_size)

    def test_get_position_size_with_volatility_adjustment(self, risk_manager, mock_account):
        """Test position size calculation with volatility adjustment."""
        # Setup
        risk_manager.set_account(mock_account)
        risk_manager.get_volatility_adjustment = MagicMock(return_value=0.8)  # Reduced size due to high volatility
        
        # Test
        position_size = risk_manager.get_position_size(
            symbol="EUR/USD",
            entry_price=1.1000,
            stop_loss=1.0950,
            risk_per_trade=1.0,
            apply_volatility_adjustment=True
        )
        
        # Calculate expected position size
        account_balance = 10000.0
        risk_amount = account_balance * (1.0 / 100)  # 1% risk = $100
        price_risk = abs(1.1000 - 1.0950)  # 0.0050
        expected_position_size = (risk_amount / price_risk) * 0.8  # $100 / 0.0050 * 0.8 = 16000 units
        
        assert position_size == pytest.approx(expected_position_size)
        risk_manager.get_volatility_adjustment.assert_called_once_with("EUR/USD")

    def test_calculate_portfolio_risk_no_account(self, risk_manager):
        """Test calculate_portfolio_risk with no account set."""
        with pytest.raises(ValueError) as excinfo:
            risk_manager.calculate_portfolio_risk()
        
        assert "Account not configured for risk manager" in str(excinfo.value)

    def test_calculate_portfolio_risk_no_positions(self, risk_manager, mock_account):
        """Test portfolio risk calculation with no open positions."""
        # Setup
        risk_manager.set_account(mock_account)
        mock_account.get_open_positions.return_value = []
        
        # Test
        portfolio_risk = risk_manager.calculate_portfolio_risk()
        
        assert portfolio_risk == 0.0

    def test_calculate_portfolio_risk_with_positions(self, risk_manager, mock_account):
        """Test portfolio risk calculation with open positions."""
        # Setup
        risk_manager.set_account(mock_account)
        
        # Create mock positions
        position1 = MagicMock()
        position1.symbol = "EUR/USD"
        position1.size = 10000.0
        position1.entry_price = 1.1000
        position1.stop_loss = 1.0950
        position1.is_long = True
        
        position2 = MagicMock()
        position2.symbol = "GBP/USD"
        position2.size = 5000.0
        position2.entry_price = 1.2500
        position2.stop_loss = 1.2450
        position2.is_long = True
        
        mock_account.get_open_positions.return_value = [position1, position2]
        mock_account.balance = 10000.0
        
        # Calculate expected risk
        risk1 = 10000.0 * abs(1.1000 - 1.0950)  # $50
        risk2 = 5000.0 * abs(1.2500 - 1.2450)  # $25
        total_risk = risk1 + risk2  # $75
        expected_risk_percentage = (total_risk / 10000.0) * 100  # 0.75%
        
        # Test
        portfolio_risk = risk_manager.calculate_portfolio_risk()
        
        assert portfolio_risk == pytest.approx(expected_risk_percentage)

    def test_check_drawdown_limit_no_account(self, risk_manager):
        """Test check_drawdown_limit with no account set."""
        with pytest.raises(ValueError) as excinfo:
            risk_manager.check_drawdown_limit()
        
        assert "Account not configured for risk manager" in str(excinfo.value)

    def test_check_drawdown_limit_below_threshold(self, risk_manager, mock_account):
        """Test drawdown check when below threshold."""
        # Setup
        risk_manager.set_account(mock_account)
        mock_account.get_drawdown.return_value = 10.0  # 10% drawdown, below 20% limit
        
        # Test
        result = risk_manager.check_drawdown_limit()
        
        assert result is True
        mock_account.get_drawdown.assert_called_once()

    def test_check_drawdown_limit_above_threshold(self, risk_manager, mock_account):
        """Test drawdown check when above threshold."""
        # Setup
        risk_manager.set_account(mock_account)
        mock_account.get_drawdown.return_value = 25.0  # 25% drawdown, above 20% limit
        
        # Test
        result = risk_manager.check_drawdown_limit()
        
        assert result is False
        mock_account.get_drawdown.assert_called_once()

    def test_check_correlation_risk_no_account(self, risk_manager):
        """Test check_correlation_risk with no account set."""
        with pytest.raises(ValueError) as excinfo:
            risk_manager.check_correlation_risk("EUR/USD", True)
        
        assert "Account not configured for risk manager" in str(excinfo.value)

    def test_check_correlation_risk_no_positions(self, risk_manager, mock_account):
        """Test correlation risk check with no existing positions."""
        # Setup
        risk_manager.set_account(mock_account)
        mock_account.get_open_positions.return_value = []
        
        # Test
        result = risk_manager.check_correlation_risk("EUR/USD", True)
        
        assert result is True
        mock_account.get_open_positions.assert_called_once()

    @patch("src.agents.risk.manager.RiskManager.get_correlation")
    def test_check_correlation_risk_with_positions(self, mock_get_correlation, risk_manager, mock_account):
        """Test correlation risk check with existing positions."""
        # Setup
        risk_manager.set_account(mock_account)
        risk_manager.correlation_threshold = 0.7
        
        # Create mock positions
        position1 = MagicMock()
        position1.symbol = "GBP/USD"
        position1.is_long = True
        
        position2 = MagicMock()
        position2.symbol = "AUD/USD"
        position2.is_long = False
        
        mock_account.get_open_positions.return_value = [position1, position2]
        
        # Set up mock correlations
        mock_get_correlation.side_effect = lambda pair1, pair2: {
            ("EUR/USD", "GBP/USD"): 0.8,  # High positive correlation
            ("EUR/USD", "AUD/USD"): 0.3   # Low correlation
        }.get((pair1, pair2), 0.0)
        
        # Test
        result = risk_manager.check_correlation_risk("EUR/USD", True)
        
        # Should fail due to high correlation with GBP/USD and same direction
        assert result is False
        mock_account.get_open_positions.assert_called_once()

    def test_get_correlation(self, risk_manager):
        """Test correlation calculation between currency pairs."""
        # Setup
        # We'll patch the internal method that would normally load price data
        with patch.object(risk_manager, '_load_price_data') as mock_load_data:
            # Create mock price data with known correlation
            dates = pd.date_range(start='2023-01-01', periods=100)
            
            # Create correlated price movements
            base_prices = np.linspace(1.0, 2.0, 100) + np.random.normal(0, 0.01, 100)
            correlated_prices = base_prices * 1.1 + np.random.normal(0, 0.01, 100)
            anti_correlated_prices = 3.0 - base_prices + np.random.normal(0, 0.01, 100)
            
            # Convert to DataFrames
            eur_usd_data = pd.DataFrame({'close': base_prices}, index=dates)
            gbp_usd_data = pd.DataFrame({'close': correlated_prices}, index=dates)
            usd_jpy_data = pd.DataFrame({'close': anti_correlated_prices}, index=dates)
            
            # Configure mock to return the appropriate data for each pair
            mock_load_data.side_effect = lambda pair: {
                "EUR/USD": eur_usd_data,
                "GBP/USD": gbp_usd_data,
                "USD/JPY": usd_jpy_data
            }.get(pair, pd.DataFrame())
            
            # Test positive correlation
            corr_pos = risk_manager.get_correlation("EUR/USD", "GBP/USD")
            assert corr_pos > 0.9  # Should be highly positively correlated
            
            # Test negative correlation
            corr_neg = risk_manager.get_correlation("EUR/USD", "USD/JPY")
            assert corr_neg < -0.9  # Should be highly negatively correlated
            
            # Test correlation with self
            corr_self = risk_manager.get_correlation("EUR/USD", "EUR/USD")
            assert corr_self == 1.0  # Perfect correlation with self

    def test_update_risk_multiplier(self, risk_manager, mock_account):
        """Test updating the risk multiplier based on performance."""
        # Setup
        risk_manager.set_account(mock_account)
        
        # Test increase multiplier after good performance
        risk_manager.update_risk_multiplier(win_rate=65.0, profit_factor=2.5)
        assert risk_manager.risk_multiplier > 1.0
        
        # Reset multiplier
        risk_manager.risk_multiplier = 1.0
        
        # Test decrease multiplier after poor performance
        risk_manager.update_risk_multiplier(win_rate=35.0, profit_factor=0.8)
        assert risk_manager.risk_multiplier < 1.0

    def test_get_status(self, risk_manager, mock_account):
        """Test getting risk manager status."""
        # Setup
        risk_manager.set_account(mock_account)
        risk_manager.calculate_portfolio_risk = MagicMock(return_value=2.5)
        
        # Test
        status = risk_manager.get_status()
        
        assert "Current Portfolio Risk" in status
        assert status["Current Portfolio Risk"] == 2.5
        assert "Max Portfolio Risk" in status
        assert status["Max Portfolio Risk"] == 5.0
        assert "Max Risk Per Trade" in status
        assert status["Max Risk Per Trade"] == 1.0
        assert "Current Drawdown" in status
        assert status["Current Drawdown"] == 5.0
        assert "Max Drawdown Limit" in status
        assert status["Max Drawdown Limit"] == 20.0

    def test_calculate_max_risk(self, risk_manager, mock_account):
        """Test calculating maximum acceptable risk amount."""
        # Setup
        risk_manager.set_account(mock_account)
        
        # Test
        max_risk = risk_manager.calculate_max_risk()
        
        # Expected max risk: 1.0% of $10,000 = $100
        assert max_risk == 100.0

    def test_adjust_for_drawdown(self, risk_manager, mock_account):
        """Test risk adjustment based on current drawdown."""
        # Setup
        risk_manager.set_account(mock_account)
        
        # Test with low drawdown (no adjustment)
        mock_account.get_drawdown.return_value = 5.0
        adjusted_risk = risk_manager.adjust_for_drawdown(1.0)
        assert adjusted_risk == 1.0
        
        # Test with higher drawdown (should reduce risk)
        mock_account.get_drawdown.return_value = 15.0
        adjusted_risk = risk_manager.adjust_for_drawdown(1.0)
        assert adjusted_risk < 1.0

    def test_get_volatility_adjustment(self, risk_manager):
        """Test volatility-based risk adjustment."""
        # Setup - we'll patch the method that would normally calculate volatility
        with patch.object(risk_manager, '_calculate_current_volatility') as mock_calc:
            # Test with normal volatility
            mock_calc.return_value = {'current': 1.0, 'average': 1.0}
            adjustment = risk_manager.get_volatility_adjustment("EUR/USD")
            assert adjustment == 1.0
            
            # Test with high volatility (should reduce position size)
            mock_calc.return_value = {'current': 2.0, 'average': 1.0}
            adjustment = risk_manager.get_volatility_adjustment("EUR/USD")
            assert adjustment < 1.0
            
            # Test with low volatility (could increase position size)
            mock_calc.return_value = {'current': 0.5, 'average': 1.0}
            adjustment = risk_manager.get_volatility_adjustment("EUR/USD")
            assert adjustment > 1.0 