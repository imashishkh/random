import unittest
from unittest.mock import Mock, patch, MagicMock, call
import threading
import uuid
from datetime import datetime
from src.trading.exit_management import (
    ExitOrderMonitor,
    ExitManagerConfig,
    ExitStrategyFactory,
    Position,
    Order,
    OrderType,
    OrderSide,
    MarketData
)


class TestExitOrderMonitor(unittest.TestCase):
    """Test cases for the ExitOrderMonitor class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.exchange_client = Mock()
        self.market_data_service = Mock()
        self.position_service = Mock()
        self.config = ExitManagerConfig(
            refresh_interval_ms=100,
            max_failures=3,
            circuit_breaker_reset_seconds=300,
            default_risk_percentage=0.02,
            default_reward_percentage=0.05
        )
        
        self.monitor = ExitOrderMonitor(
            exchange_client=self.exchange_client,
            market_data_service=self.market_data_service,
            position_service=self.position_service,
            config=self.config
        )
        
        # Sample position and strategy data
        self.position_id = str(uuid.uuid4())
        self.position = Position(
            id=self.position_id,
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=1.0,
            timestamp=datetime.now().timestamp(),
            status="open"
        )
        
        # Mock market data
        self.market_data = MarketData(
            symbol="BTC/USDT",
            timestamp=datetime.now().timestamp(),
            open=49000.0,
            high=51000.0,
            low=49000.0,
            close=50500.0,
            volume=100.0,
            indicators={"atr": 1000.0}
        )
        
        # Setup mock stop-loss and take-profit orders
        self.sl_order = Order(
            id="sl-1",
            symbol="BTC/USDT",
            order_type=OrderType.STOP_MARKET,
            side=OrderSide.SELL,
            quantity=1.0,
            price=49000.0,
            status="open",
            linked_position_id=self.position_id,
            is_reduce_only=True
        )
        
        self.tp_order = Order(
            id="tp-1",
            symbol="BTC/USDT",
            order_type=OrderType.LIMIT,
            side=OrderSide.SELL,
            quantity=1.0,
            price=52000.0,
            status="open",
            linked_position_id=self.position_id,
            is_reduce_only=True
        )
    
    def tearDown(self):
        """Clean up after tests"""
        if hasattr(self.monitor, '_monitoring_thread') and self.monitor._monitoring_thread:
            self.monitor.stop()
    
    def test_initialization(self):
        """Test if the monitor is properly initialized"""
        self.assertEqual(self.monitor._exchange_client, self.exchange_client)
        self.assertEqual(self.monitor._market_data_service, self.market_data_service)
        self.assertEqual(self.monitor._position_service, self.position_service)
        self.assertEqual(self.monitor._config, self.config)
        self.assertFalse(self.monitor._running)
        self.assertEqual(self.monitor._failure_count, 0)
        self.assertFalse(self.monitor._circuit_breaker_tripped)
        self.assertIsNone(self.monitor._circuit_breaker_time)
        self.assertIsNotNone(self.monitor._lock)
        self.assertEqual(len(self.monitor._strategy_cache), 0)
    
    def test_start_stop(self):
        """Test starting and stopping the monitor"""
        # Mock the _monitoring_loop method to prevent actual thread execution
        self.monitor._monitoring_loop = Mock()
        
        # Start the monitor
        self.monitor.start()
        self.assertTrue(self.monitor._running)
        self.assertIsNotNone(self.monitor._monitoring_thread)
        self.assertTrue(self.monitor._monitoring_thread.is_alive())
        
        # Stop the monitor
        self.monitor.stop()
        self.assertFalse(self.monitor._running)
        
        # Verify the monitoring loop was called
        self.monitor._monitoring_loop.assert_called_once()
    
    @patch('time.sleep')
    def test_monitoring_loop(self, mock_sleep):
        """Test the monitoring loop behavior"""
        # Setup to exit the loop after one iteration
        def side_effect(*args):
            self.monitor._running = False
            return None
        
        mock_sleep.side_effect = side_effect
        self.monitor._update_all_positions = Mock()
        
        # Start the monitoring loop directly
        self.monitor._running = True
        self.monitor._monitoring_loop()
        
        # Verify update_all_positions was called
        self.monitor._update_all_positions.assert_called_once()
    
    def test_update_all_positions(self):
        """Test updating all positions"""
        # Setup
        self.position_service.get_open_positions.return_value = [self.position]
        self.monitor._update_position_exit_orders = Mock()
        
        # Call the method
        self.monitor._update_all_positions()
        
        # Verify
        self.position_service.get_open_positions.assert_called_once()
        self.monitor._update_position_exit_orders.assert_called_once_with(self.position)
    
    def test_update_position_exit_orders(self):
        """Test updating exit orders for a position"""
        # Setup
        self.market_data_service.get_latest_data.return_value = self.market_data
        self.monitor._get_position_strategies = Mock(return_value=(Mock(), Mock()))
        self.monitor._update_exit_strategy_orders = Mock()
        
        # Call the method
        self.monitor._update_position_exit_orders(self.position)
        
        # Verify
        self.market_data_service.get_latest_data.assert_called_once_with(self.position.symbol)
        self.monitor._get_position_strategies.assert_called_once_with(self.position)
        self.assertEqual(self.monitor._update_exit_strategy_orders.call_count, 2)
    
    def test_register_position(self):
        """Test registering a position with the monitor"""
        # Setup
        stop_loss_strategy = ExitStrategyFactory.create_default_stop_loss()
        take_profit_strategy = ExitStrategyFactory.create_default_take_profit()
        
        # Call the method
        self.monitor.register_position(
            self.position,
            stop_loss_strategy,
            take_profit_strategy
        )
        
        # Verify
        self.assertIn(self.position_id, self.monitor._strategy_cache)
        cache_entry = self.monitor._strategy_cache[self.position_id]
        self.assertEqual(cache_entry["stop_loss"], stop_loss_strategy)
        self.assertEqual(cache_entry["take_profit"], take_profit_strategy)
    
    def test_orders_have_changed(self):
        """Test detecting if orders have changed"""
        # Setup
        existing_orders = [self.sl_order, self.tp_order]
        
        # Test with identical orders (no change)
        new_orders = [
            Order(
                id="sl-1",
                symbol="BTC/USDT",
                order_type=OrderType.STOP_MARKET,
                side=OrderSide.SELL,
                quantity=1.0,
                price=49000.0,
                status="open",
                linked_position_id=self.position_id,
                is_reduce_only=True
            ),
            Order(
                id="tp-1",
                symbol="BTC/USDT",
                order_type=OrderType.LIMIT,
                side=OrderSide.SELL,
                quantity=1.0,
                price=52000.0,
                status="open",
                linked_position_id=self.position_id,
                is_reduce_only=True
            )
        ]
        self.assertFalse(self.monitor._orders_have_changed(existing_orders, new_orders))
        
        # Test with changed price
        changed_orders = [
            Order(
                id="sl-1",
                symbol="BTC/USDT",
                order_type=OrderType.STOP_MARKET,
                side=OrderSide.SELL,
                quantity=1.0,
                price=48500.0,  # Changed price
                status="open",
                linked_position_id=self.position_id,
                is_reduce_only=True
            ),
            Order(
                id="tp-1",
                symbol="BTC/USDT",
                order_type=OrderType.LIMIT,
                side=OrderSide.SELL,
                quantity=1.0,
                price=52000.0,
                status="open",
                linked_position_id=self.position_id,
                is_reduce_only=True
            )
        ]
        self.assertTrue(self.monitor._orders_have_changed(existing_orders, changed_orders))
        
        # Test with different number of orders
        fewer_orders = [self.sl_order]
        self.assertTrue(self.monitor._orders_have_changed(existing_orders, fewer_orders))
    
    def test_update_exit_strategy_orders(self):
        """Test updating exit strategy orders"""
        # Setup
        strategy = Mock()
        strategy.get_exit_orders.return_value = [
            Order(
                id=None,
                symbol="BTC/USDT",
                order_type=OrderType.STOP_MARKET,
                side=OrderSide.SELL,
                quantity=1.0,
                price=48000.0,  # Different from existing
                status="new",
                linked_position_id=self.position_id,
                is_reduce_only=True
            )
        ]
        
        self.position.stop_loss_order = self.sl_order
        
        self.exchange_client.cancel_order = Mock()
        self.exchange_client.place_order = Mock(return_value="new-order-id")
        
        # Call the method
        self.monitor._update_exit_strategy_orders(
            self.position, 
            self.market_data, 
            strategy, 
            "stop_loss"
        )
        
        # Verify
        strategy.get_exit_orders.assert_called_once_with(self.position, self.market_data)
        self.exchange_client.cancel_order.assert_called_once_with(self.sl_order.id)
        self.exchange_client.place_order.assert_called_once()
    
    def test_circuit_breaker(self):
        """Test circuit breaker functionality"""
        # Test incrementing failure count
        self.monitor._increment_failure_count()
        self.assertEqual(self.monitor._failure_count, 1)
        
        # Test circuit breaker not tripped
        self.assertFalse(self.monitor._is_circuit_breaker_open())
        
        # Trip the circuit breaker
        for _ in range(self.config.max_failures):
            self.monitor._increment_failure_count()
        
        # Verify circuit breaker is tripped
        self.assertTrue(self.monitor._is_circuit_breaker_open())
        self.assertIsNotNone(self.monitor._circuit_breaker_time)
        
        # Test resetting failure count
        self.monitor._reset_failure_count()
        self.assertEqual(self.monitor._failure_count, 0)
        self.assertFalse(self.monitor._circuit_breaker_tripped)
        self.assertIsNone(self.monitor._circuit_breaker_time)


if __name__ == '__main__':
    unittest.main() 