import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from src.analytics.data_models import Trade, TradeDirection
from src.services.pnl_calculation_service import PnLCalculationService, CalculationMethod


class TestPnLCalculationService(unittest.TestCase):
    """Test suite for PnL calculation service"""

    def setUp(self):
        """Set up test environment"""
        # Create mock repositories and clients
        self.mock_trade_repo = MagicMock()
        self.mock_position_repo = MagicMock()
        self.mock_binance_client = MagicMock()
        
        # Create service instance with mocks
        self.service = PnLCalculationService(
            trade_repository=self.mock_trade_repo,
            position_repository=self.mock_position_repo,
            binance_client=self.mock_binance_client,
            cache_ttl=0  # Disable caching for tests
        )
        
        # Create sample trade data
        self.sample_trades = self._create_sample_trades()
        
    def _create_sample_trades(self):
        """Create sample trade data for testing"""
        base_time = datetime.now()
        
        return [
            # Trade 1: Buy 1.0 BTC at $50,000
            Trade(
                id="1",
                symbol="BTCUSDT",
                open_time=base_time - timedelta(days=5),
                close_time=base_time - timedelta(days=5),
                direction=TradeDirection.BUY,
                open_price=50000.0,
                close_price=50000.0,
                size=1.0,
                pnl=0.0,
                fees=50.0,
                strategy="test",
                tags=["test"]
            ),
            # Trade 2: Sell 0.5 BTC at $55,000 (+$2,500 profit)
            Trade(
                id="2",
                symbol="BTCUSDT",
                open_time=base_time - timedelta(days=3),
                close_time=base_time - timedelta(days=3),
                direction=TradeDirection.SELL,
                open_price=50000.0,
                close_price=55000.0,
                size=0.5,
                pnl=2500.0,
                fees=27.5,
                strategy="test",
                tags=["test"]
            ),
            # Trade 3: Buy 2.0 ETH at $3,000
            Trade(
                id="3",
                symbol="ETHUSDT",
                open_time=base_time - timedelta(days=4),
                close_time=base_time - timedelta(days=4),
                direction=TradeDirection.BUY,
                open_price=3000.0,
                close_price=3000.0,
                size=2.0,
                pnl=0.0,
                fees=12.0,
                strategy="test",
                tags=["test"]
            ),
            # Trade 4: Sell 1.0 ETH at $3,500 (+$500 profit)
            Trade(
                id="4",
                symbol="ETHUSDT",
                open_time=base_time - timedelta(days=2),
                close_time=base_time - timedelta(days=2),
                direction=TradeDirection.SELL,
                open_price=3000.0,
                close_price=3500.0,
                size=1.0,
                pnl=500.0,
                fees=7.0,
                strategy="test",
                tags=["test"]
            ),
            # Trade 5: Sell 0.5 BTC at $48,000 (-$1,000 loss)
            Trade(
                id="5",
                symbol="BTCUSDT",
                open_time=base_time - timedelta(days=1),
                close_time=base_time - timedelta(days=1),
                direction=TradeDirection.SELL,
                open_price=50000.0,
                close_price=48000.0,
                size=0.5,
                pnl=-1000.0,
                fees=24.0,
                strategy="test",
                tags=["test"]
            )
        ]
        
    def test_get_trade_data(self):
        """Test getting trade data from multiple sources"""
        # Configure mock repository to return sample data
        self.mock_trade_repo.get_trades.return_value = self.sample_trades[:3]
        
        # Configure mock Binance client to return sample data
        self.mock_binance_client.get_my_trades.return_value = self.sample_trades[3:]
        
        # Call the service method
        trades = self.service.get_trade_data()
        
        # Verify the mocks were called
        self.mock_trade_repo.get_trades.assert_called_once()
        self.mock_binance_client.get_my_trades.assert_called_once()
        
        # Verify combined result contains all trades
        self.assertEqual(len(trades), 5)
        
    def test_calculate_fifo_pnl(self):
        """Test FIFO PnL calculation method"""
        # Mock get_trade_data to return sample trades
        self.service.get_trade_data = MagicMock(return_value=self.sample_trades)
        
        # Calculate realized PnL using FIFO method
        realized_pnl = self.service.calculate_realized_pnl(
            calculation_method=CalculationMethod.FIFO,
            include_fees=True
        )
        
        # Expected PnL should be:
        # - Buy 1.0 BTC at $50,000, fee $50
        # - Sell 0.5 BTC at $55,000 (oldest), profit $2,500, fee $27.5
        # - Sell 0.5 BTC at $48,000 (oldest), loss $1,000, fee $24
        # - Buy 2.0 ETH at $3,000, fee $12
        # - Sell 1.0 ETH at $3,500, profit $500, fee $7
        # Total: $2,500 - $27.5 - $1,000 - $24 + $500 - $7 - $50 - $12 = $1,879.5
        expected_pnl = Decimal('1879.5')
        
        self.assertEqual(realized_pnl, expected_pnl)
        
    def test_calculate_lifo_pnl(self):
        """Test LIFO PnL calculation method"""
        # Create a specific scenario for LIFO testing
        base_time = datetime.now()
        lifo_trades = [
            # Trade 1: Buy 1.0 BTC at $40,000
            Trade(
                id="1",
                symbol="BTCUSDT",
                open_time=base_time - timedelta(days=10),
                close_time=base_time - timedelta(days=10),
                direction=TradeDirection.BUY,
                open_price=40000.0,
                close_price=40000.0,
                size=1.0,
                pnl=0.0,
                fees=40.0,
                strategy="test",
                tags=["test"]
            ),
            # Trade 2: Buy 1.0 BTC at $50,000
            Trade(
                id="2",
                symbol="BTCUSDT",
                open_time=base_time - timedelta(days=5),
                close_time=base_time - timedelta(days=5),
                direction=TradeDirection.BUY,
                open_price=50000.0,
                close_price=50000.0,
                size=1.0,
                pnl=0.0,
                fees=50.0,
                strategy="test",
                tags=["test"]
            ),
            # Trade 3: Sell 1.5 BTC at $45,000
            Trade(
                id="3",
                symbol="BTCUSDT",
                open_time=base_time - timedelta(days=2),
                close_time=base_time - timedelta(days=2),
                direction=TradeDirection.SELL,
                open_price=45000.0,
                close_price=45000.0,
                size=1.5,
                pnl=-5000.0,  # Estimated, will be calculated by service
                fees=67.5,
                strategy="test",
                tags=["test"]
            ),
        ]
        
        # Mock get_trade_data to return LIFO test trades
        self.service.get_trade_data = MagicMock(return_value=lifo_trades)
        
        # Calculate realized PnL using LIFO method
        realized_pnl = self.service.calculate_realized_pnl(
            calculation_method=CalculationMethod.LIFO,
            include_fees=True
        )
        
        # Expected PnL with LIFO should be:
        # - Sell the newest 1.0 BTC first (bought at $50,000): ($45,000 - $50,000) * 1.0 = -$5,000
        # - Sell the remaining 0.5 BTC from the older batch: ($45,000 - $40,000) * 0.5 = $2,500
        # - Subtract fees: -$40 - $50 - $67.5 = -$157.5
        # Total: -$5,000 + $2,500 - $157.5 = -$2,657.5
        expected_lifo_pnl = Decimal('-2657.5')
        
        self.assertEqual(realized_pnl, expected_lifo_pnl)
        
    def test_calculate_average_cost_pnl(self):
        """Test Average Cost PnL calculation method"""
        # Create a specific scenario for average cost testing
        base_time = datetime.now()
        avg_cost_trades = [
            # Trade 1: Buy 1.0 BTC at $40,000
            Trade(
                id="1",
                symbol="BTCUSDT",
                open_time=base_time - timedelta(days=10),
                close_time=base_time - timedelta(days=10),
                direction=TradeDirection.BUY,
                open_price=40000.0,
                close_price=40000.0,
                size=1.0,
                pnl=0.0,
                fees=40.0,
                strategy="test",
                tags=["test"]
            ),
            # Trade 2: Buy 1.0 BTC at $50,000
            Trade(
                id="2",
                symbol="BTCUSDT",
                open_time=base_time - timedelta(days=5),
                close_time=base_time - timedelta(days=5),
                direction=TradeDirection.BUY,
                open_price=50000.0,
                close_price=50000.0,
                size=1.0,
                pnl=0.0,
                fees=50.0,
                strategy="test",
                tags=["test"]
            ),
            # Trade 3: Sell 1.5 BTC at $45,000
            Trade(
                id="3",
                symbol="BTCUSDT",
                open_time=base_time - timedelta(days=2),
                close_time=base_time - timedelta(days=2),
                direction=TradeDirection.SELL,
                open_price=45000.0,
                close_price=45000.0,
                size=1.5,
                pnl=0.0,  # Estimated, will be calculated by service
                fees=67.5,
                strategy="test",
                tags=["test"]
            ),
        ]
        
        # Mock get_trade_data to return average cost test trades
        self.service.get_trade_data = MagicMock(return_value=avg_cost_trades)
        
        # Calculate realized PnL using Average Cost method
        realized_pnl = self.service.calculate_realized_pnl(
            calculation_method=CalculationMethod.AVERAGE_COST,
            include_fees=True
        )
        
        # Expected PnL with Average Cost should be:
        # - Average cost of 2 BTC: ($40,000 + $50,000) / 2 = $45,000 per BTC
        # - Sell 1.5 BTC at $45,000: ($45,000 - $45,000) * 1.5 = $0
        # - Subtract fees: -$40 - $50 - $67.5 = -$157.5
        # Total: $0 - $157.5 = -$157.5
        expected_avg_cost_pnl = Decimal('-157.5')
        
        self.assertEqual(realized_pnl, expected_avg_cost_pnl)
        
    def test_calculate_unrealized_pnl(self):
        """Test unrealized PnL calculation"""
        # Mock methods used by calculate_unrealized_pnl
        self.service.get_trade_data = MagicMock(return_value=self.sample_trades)
        self.service._get_open_positions = MagicMock(return_value=[
            {
                'symbol': 'BTCUSDT',
                'size': Decimal('0'),  # All BTC sold (ignore this, will be calculated from trades)
                'entry_price': Decimal('50000')
            },
            {
                'symbol': 'ETHUSDT',
                'size': Decimal('1'),  # 1 ETH remaining (ignore this, will be calculated from trades)
                'entry_price': Decimal('3000')
            }
        ])
        self.service._get_current_market_prices = MagicMock(return_value={
            'BTCUSDT': Decimal('60000'),
            'ETHUSDT': Decimal('4000')
        })
        
        # Calculate unrealized PnL
        unrealized_pnl = self.service.calculate_unrealized_pnl(
            calculation_method=CalculationMethod.FIFO,
            include_fees=False  # Exclude fees to simplify calculation
        )
        
        # Expected unrealized PnL:
        # - BTCUSDT: 0 BTC remaining (all sold)
        # - ETHUSDT: 1 ETH remaining, bought at $3,000, current price $4,000
        # - Unrealized PnL for ETH: ($4,000 - $3,000) * 1 = $1,000
        # Total unrealized: $1,000
        expected_unrealized_pnl = Decimal('1000')
        
        self.assertEqual(unrealized_pnl, expected_unrealized_pnl)
        
    def test_calculate_pnl_metrics(self):
        """Test PnL metrics calculation"""
        # Mock methods used by calculate_pnl_metrics
        self.service.get_trade_data = MagicMock(return_value=self.sample_trades)
        self.service.calculate_realized_pnl = MagicMock(return_value=Decimal('1879.5'))
        self.service.calculate_unrealized_pnl = MagicMock(return_value=Decimal('1000'))
        
        # Calculate PnL metrics
        metrics = self.service.calculate_pnl_metrics()
        
        # Verify metrics
        self.assertEqual(metrics['realized_pnl'], float(Decimal('1879.5')))
        self.assertEqual(metrics['unrealized_pnl'], float(Decimal('1000')))
        self.assertEqual(metrics['total_pnl'], float(Decimal('2879.5')))
        self.assertEqual(metrics['winning_trades'], 2)  # 2 profitable trades
        self.assertEqual(metrics['losing_trades'], 1)   # 1 losing trade
        self.assertEqual(metrics['total_trades'], 5)    # 5 total trades
        
        # Win rate should be 2/3 = 66.66...%
        self.assertAlmostEqual(metrics['win_rate'], 66.66, delta=0.1)


if __name__ == '__main__':
    unittest.main() 