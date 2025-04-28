#!/usr/bin/env python3
"""
Example script demonstrating basic usage of the exit management system.
"""

import logging
import time
import uuid
from typing import Dict, List

from .exit_management import (
    ExitManager,
    Position,
    MarketData,
    ExitStrategyConfig,
    ExitStrategyType,
    StrategyExitConfig,
    GlobalRiskParameters
)


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


# Mock exchange client for demonstration
class MockExchangeClient:
    def __init__(self):
        self.orders = {}
        
    def place_order(self, symbol, side, type, quantity, price):
        order_id = str(uuid.uuid4())
        order = {
            "orderId": order_id,
            "symbol": symbol,
            "side": side,
            "type": type,
            "quantity": quantity,
            "price": price,
            "status": "NEW"
        }
        self.orders[order_id] = order
        logger.info(f"Placed {type} order: {order}")
        return order
        
    def cancel_order(self, symbol, order_id):
        if order_id in self.orders:
            self.orders[order_id]["status"] = "CANCELED"
            logger.info(f"Canceled order {order_id}")
            return {"orderId": order_id, "status": "CANCELED"}
        return {"error": "Order not found"}
        
    def get_account(self):
        return {"totalWalletBalance": 10000.0}
        
    def get_exchange_info(self, symbol):
        return {"stepSize": 0.001}


# Mock market data service
class MockMarketDataService:
    def __init__(self):
        self.prices = {
            "BTCUSDT": 50000.0,
            "ETHUSDT": 3000.0
        }
        self.atr_values = {
            "BTCUSDT": 1500.0,
            "ETHUSDT": 100.0
        }
        
    def get_market_data(self, symbol):
        return MarketData(
            symbol=symbol,
            last_price=self.prices.get(symbol, 1000.0),
            timestamp=int(time.time()),
            atr=self.atr_values.get(symbol, 50.0)
        )
        
    def update_price(self, symbol, new_price):
        self.prices[symbol] = new_price
        logger.info(f"Updated {symbol} price to {new_price}")


# Mock position service
class MockPositionService:
    def __init__(self):
        self.positions = {}
        
    def get_open_positions(self):
        return list(self.positions.values())
        
    def get_position(self, position_id):
        return self.positions.get(position_id)
        
    def update_position(self, position):
        self.positions[position.position_id] = position
        return position
        
    def add_position(self, position):
        self.positions[position.position_id] = position
        logger.info(f"Added position {position.position_id}")
        return position


def main():
    # Create mock services
    exchange_client = MockExchangeClient()
    market_data_service = MockMarketDataService()
    position_service = MockPositionService()
    
    # Create exit manager with custom global risk parameters
    global_params = GlobalRiskParameters(
        max_drawdown_percent=0.05,
        default_risk_per_trade=0.01,
        default_atr_multiplier=2.5
    )
    
    exit_manager = ExitManager(
        exchange_client=exchange_client,
        market_data_service=market_data_service,
        position_service=position_service,
        config=None  # Use default config
    )
    
    # Start the exit management service
    exit_manager.start()
    
    # Update global risk parameters
    exit_manager.update_global_risk_parameters(global_params)
    
    # Create a strategy-specific exit configuration
    btc_strategy_config = StrategyExitConfig(
        strategy_id="btc_trend_following",
        risk_percent_override=0.015,  # 1.5% risk per trade
        stop_loss_config=ExitStrategyConfig(
            strategy_type=ExitStrategyType.TRAILING_STOP_LOSS,
            parameters={"trail_percentage": 0.03, "activation_percentage": 0.01}
        ),
        take_profit_config=ExitStrategyConfig(
            strategy_type=ExitStrategyType.PARTIAL_EXIT,
            parameters={"levels": [
                {"percentage": 0.05, "quantity_percentage": 0.3},
                {"percentage": 0.1, "quantity_percentage": 0.3},
                {"percentage": 0.2, "quantity_percentage": 0.4}
            ]}
        )
    )
    
    # Update the strategy configuration
    exit_manager.update_strategy_config("btc_trend_following", btc_strategy_config)
    
    # Calculate position size for a BTC trade
    position_size = exit_manager.calculate_position_size(
        symbol="BTCUSDT",
        entry_price=50000.0,
        stop_loss_price=48500.0,
        strategy_id="btc_trend_following"
    )
    
    logger.info(f"Calculated position size: {position_size} BTC")
    
    # Create a position
    position = Position(
        symbol="BTCUSDT",
        position_id="pos_" + str(uuid.uuid4()),
        entry_price=50000.0,
        quantity=position_size,
        side="BUY",
        open_time=int(time.time())
    )
    
    # Add position to the position service
    position_service.add_position(position)
    
    # Register the position with the exit manager
    exit_manager.register_position(position, strategy_id="btc_trend_following")
    
    # Simulate price movements
    for i in range(10):
        time.sleep(1)
        
        # Update price
        new_price = 50000.0 + (i * 200)  # Price increases
        market_data_service.update_price("BTCUSDT", new_price)
        
        # Get updated position
        updated_position = position_service.get_position(position.position_id)
        logger.info(f"Position {updated_position.position_id} now has " +
                   f"{len(updated_position.stop_loss_orders)} stop-loss orders and " +
                   f"{len(updated_position.take_profit_orders)} take-profit orders")
    
    # Sleep a bit to see the updates
    time.sleep(3)
    
    # Stop the exit management service
    exit_manager.stop()
    logger.info("Example completed")


if __name__ == "__main__":
    main() 