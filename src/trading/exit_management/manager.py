import logging
import time
from typing import Dict, List, Optional

from .models import Position, MarketData
from .config import ExitManagerConfig, StrategyExitConfig, GlobalRiskParameters
from .factory import ExitStrategyFactory
from .monitor import ExitOrderMonitor


logger = logging.getLogger(__name__)


class ExitManager:
    """
    Main facade for managing exits (stop-loss and take-profit) of trading positions.
    
    This class provides a high-level interface for registering positions,
    configuring exit strategies, and ensuring exit orders are properly managed.
    """
    
    def __init__(self, exchange_client, market_data_service, position_service,
                 config: Optional[ExitManagerConfig] = None):
        """
        Initialize the exit manager
        
        Args:
            exchange_client: Client for placing/canceling orders
            market_data_service: Service for retrieving market data
            position_service: Service for tracking positions
            config: Configuration for the exit manager
        """
        self.config = config or ExitManagerConfig()
        self.exchange_client = exchange_client
        self.market_data_service = market_data_service
        self.position_service = position_service
        
        # Create the monitor
        self.monitor = ExitOrderMonitor(
            exchange_client=exchange_client,
            market_data_service=market_data_service,
            position_service=position_service,
            config=self.config
        )
        
    def start(self):
        """Start the exit management service"""
        logger.info("Starting exit management service")
        self.monitor.start()
        
    def stop(self):
        """Stop the exit management service"""
        logger.info("Stopping exit management service")
        self.monitor.stop()
        
    def register_position(self, position: Position, strategy_id: Optional[str] = None,
                         exit_config: Optional[StrategyExitConfig] = None):
        """
        Register a position for exit management
        
        Args:
            position: The position to register
            strategy_id: Optional strategy ID to use for configuration lookup
            exit_config: Optional exit configuration for this position
        """
        if exit_config is None and strategy_id is not None:
            # Look up exit config by strategy ID
            exit_config = self.config.get_strategy_config(strategy_id)
            
        # Register with the monitor
        self.monitor.register_position(position, exit_config)
        logger.info(f"Registered position {position.position_id} for exit management")
        
    def update_global_risk_parameters(self, updated_params: GlobalRiskParameters):
        """
        Update the global risk parameters
        
        Args:
            updated_params: Updated global risk parameters
        """
        self.config.global_params = updated_params
        logger.info("Updated global risk parameters")
        
    def update_strategy_config(self, strategy_id: str, config: StrategyExitConfig):
        """
        Update configuration for a specific strategy
        
        Args:
            strategy_id: Strategy ID
            config: Updated exit configuration
        """
        self.config.strategy_configs[strategy_id] = config
        logger.info(f"Updated exit configuration for strategy {strategy_id}")
        
    def calculate_position_size(self, symbol: str, entry_price: float, 
                               stop_loss_price: float, strategy_id: Optional[str] = None,
                               account_balance: Optional[float] = None) -> float:
        """
        Calculate position size based on risk parameters
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price for the position
            stop_loss_price: Stop-loss price for the position
            strategy_id: Optional strategy ID for configuration lookup
            account_balance: Optional account balance (will be fetched if not provided)
            
        Returns:
            Recommended position size in base currency
        """
        # Get risk percentage from strategy config or global defaults
        risk_percent = self.config.global_params.default_risk_per_trade
        if strategy_id is not None:
            strategy_config = self.config.get_strategy_config(strategy_id)
            risk_percent = strategy_config.get_risk_percent(self.config.global_params)
            
        # Get account balance if not provided
        if account_balance is None:
            account_info = self.exchange_client.get_account()
            account_balance = float(account_info.get("totalWalletBalance", 0.0))
            
        # Calculate risk amount in quote currency
        risk_amount = account_balance * risk_percent
        
        # Calculate stop loss distance (absolute)
        stop_loss_distance = abs(entry_price - stop_loss_price)
        
        if stop_loss_distance <= 0:
            logger.warning(f"Invalid stop loss distance for {symbol}: {stop_loss_distance}")
            # Use 2% as default risk distance
            stop_loss_distance = entry_price * 0.02
            
        # Calculate position size
        position_size = risk_amount / stop_loss_distance
        
        # Get exchange info for rounding
        exchange_info = self.exchange_client.get_exchange_info(symbol)
        
        # Round to appropriate precision
        step_size = float(exchange_info.get("stepSize", 0.001))
        position_size = self._round_to_step(position_size, step_size)
        
        logger.info(f"Calculated position size for {symbol}: {position_size} " +
                   f"(risk: {risk_percent*100:.2f}%, amount: {risk_amount:.2f})")
                   
        return position_size
        
    def _round_to_step(self, value: float, step_size: float) -> float:
        """Round a value to a specific step size"""
        return round(value / step_size) * step_size 