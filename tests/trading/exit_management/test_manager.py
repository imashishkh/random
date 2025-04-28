import unittest
from unittest.mock import Mock, patch, MagicMock, call
import uuid
from datetime import datetime
from src.trading.exit_management import (
    ExitManager,
    ExitManagerConfig,
    ExitOrderMonitor,
    ExitStrategyConfig,
    ExitStrategyFactory,
    ExitStrategyType,
    Position
)


class TestExitManager(unittest.TestCase):
    """Test cases for the ExitManager class"""
    
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
        
        # Create a mock for the ExitOrderMonitor
        self.monitor_mock = Mock(spec=ExitOrderMonitor)
        
        # Initialize ExitManager with the mock monitor
        self.exit_manager = ExitManager(
            exchange_client=self.exchange_client,
            market_data_service=self.market_data_service,
            position_service=self.position_service,
            config=self.config,
            monitor=self.monitor_mock
        )
        
        # Sample position data
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
    
    def test_initialization(self):
        """Test if the manager is properly initialized"""
        self.assertEqual(self.exit_manager._config, self.config)
        self.assertEqual(self.exit_manager._monitor, self.monitor_mock)
    
    def test_initialization_without_monitor(self):
        """Test initialization when no monitor is provided"""
        with patch('src.trading.exit_management.ExitOrderMonitor') as monitor_mock:
            # Create a new instance without providing a monitor
            monitor_instance = MagicMock()
            monitor_mock.return_value = monitor_instance
            
            exit_manager = ExitManager(
                exchange_client=self.exchange_client,
                market_data_service=self.market_data_service,
                position_service=self.position_service,
                config=self.config
            )
            
            # Check that a monitor was created
            monitor_mock.assert_called_once_with(
                exchange_client=self.exchange_client,
                market_data_service=self.market_data_service,
                position_service=self.position_service,
                config=self.config
            )
            self.assertEqual(exit_manager._monitor, monitor_instance)
    
    def test_start_stop(self):
        """Test starting and stopping the manager"""
        # Test start
        self.exit_manager.start()
        self.monitor_mock.start.assert_called_once()
        
        # Test stop
        self.exit_manager.stop()
        self.monitor_mock.stop.assert_called_once()
    
    def test_apply_default_exit_strategies(self):
        """Test applying default exit strategies to a position"""
        # Setup
        with patch('src.trading.exit_management.ExitStrategyFactory') as factory_mock:
            # Mock the factory methods
            default_sl = Mock()
            default_tp = Mock()
            factory_mock.create_default_stop_loss.return_value = default_sl
            factory_mock.create_default_take_profit.return_value = default_tp
            
            # Call the method
            self.exit_manager.apply_default_exit_strategies(self.position)
            
            # Verify
            factory_mock.create_default_stop_loss.assert_called_once()
            factory_mock.create_default_take_profit.assert_called_once()
            self.monitor_mock.register_position.assert_called_once_with(
                self.position,
                default_sl,
                default_tp
            )
    
    def test_apply_position_exit_strategies(self):
        """Test applying custom exit strategies to a position"""
        # Setup
        stop_loss_config = ExitStrategyConfig(
            type=ExitStrategyType.FIXED_STOP_LOSS,
            params={"risk_percentage": 0.03}
        )
        
        take_profit_config = ExitStrategyConfig(
            type=ExitStrategyType.FIXED_TAKE_PROFIT,
            params={"reward_percentage": 0.06}
        )
        
        with patch('src.trading.exit_management.ExitStrategyFactory') as factory_mock:
            # Create mock strategies
            stop_loss_strategy = Mock()
            take_profit_strategy = Mock()
            factory_mock.create_strategy.side_effect = [
                stop_loss_strategy,
                take_profit_strategy
            ]
            
            # Call the method
            self.exit_manager.apply_position_exit_strategies(
                self.position,
                stop_loss_config,
                take_profit_config
            )
            
            # Verify factory calls
            self.assertEqual(factory_mock.create_strategy.call_count, 2)
            factory_mock.create_strategy.assert_has_calls([
                call(stop_loss_config),
                call(take_profit_config)
            ])
            
            # Verify monitor registration
            self.monitor_mock.register_position.assert_called_once_with(
                self.position,
                stop_loss_strategy,
                take_profit_strategy
            )
    
    def test_apply_only_stop_loss(self):
        """Test applying only a stop-loss strategy"""
        # Setup
        stop_loss_config = ExitStrategyConfig(
            type=ExitStrategyType.TRAILING_STOP_LOSS,
            params={"initial_percentage": 0.02, "step_percentage": 0.005}
        )
        
        with patch('src.trading.exit_management.ExitStrategyFactory') as factory_mock:
            # Create mock strategy
            stop_loss_strategy = Mock()
            default_tp = Mock()
            
            factory_mock.create_strategy.return_value = stop_loss_strategy
            factory_mock.create_default_take_profit.return_value = default_tp
            
            # Call the method
            self.exit_manager.apply_stop_loss(self.position, stop_loss_config)
            
            # Verify
            factory_mock.create_strategy.assert_called_once_with(stop_loss_config)
            factory_mock.create_default_take_profit.assert_called_once()
            
            self.monitor_mock.register_position.assert_called_once_with(
                self.position,
                stop_loss_strategy,
                default_tp
            )
    
    def test_apply_only_take_profit(self):
        """Test applying only a take-profit strategy"""
        # Setup
        take_profit_config = ExitStrategyConfig(
            type=ExitStrategyType.TRAILING_TAKE_PROFIT,
            params={"initial_percentage": 0.04, "step_percentage": 0.01}
        )
        
        with patch('src.trading.exit_management.ExitStrategyFactory') as factory_mock:
            # Create mock strategy
            take_profit_strategy = Mock()
            default_sl = Mock()
            
            factory_mock.create_strategy.return_value = take_profit_strategy
            factory_mock.create_default_stop_loss.return_value = default_sl
            
            # Call the method
            self.exit_manager.apply_take_profit(self.position, take_profit_config)
            
            # Verify
            factory_mock.create_strategy.assert_called_once_with(take_profit_config)
            factory_mock.create_default_stop_loss.assert_called_once()
            
            self.monitor_mock.register_position.assert_called_once_with(
                self.position,
                default_sl,
                take_profit_strategy
            )
    
    def test_remove_position(self):
        """Test removing a position from monitoring"""
        # Call the method
        self.exit_manager.remove_position(self.position)
        
        # Verify
        self.monitor_mock.remove_position.assert_called_once_with(self.position.id)


if __name__ == '__main__':
    unittest.main() 