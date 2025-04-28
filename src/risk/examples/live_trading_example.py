#!/usr/bin/env python3
"""
Example script that demonstrates how to use RiskManager in a live trading scenario.
This script creates a simple trading loop that checks positions and applies risk management.
"""

import os
import time
import yaml
import random
import logging
from typing import Dict, List, Any
from datetime import datetime

from .manager import RiskManager
from .position_fetcher import PositionDataFetcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('risk_manager_example')


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    if not os.path.exists(config_path):
        logger.warning(f"Configuration file not found: {config_path}")
        return {}
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


class TradingExampleSimulator:
    """Simple simulator to demonstrate risk management in a live trading scenario."""
    
    def __init__(self, risk_manager: RiskManager, position_fetcher: PositionDataFetcher):
        self.risk_manager = risk_manager
        self.position_fetcher = position_fetcher
        self.running = False
        self.trading_allowed = True
        self.last_circuit_breaker_state = False
        
        # Configure risk manager to call our callback when a circuit breaker is triggered
        if hasattr(self.risk_manager, 'set_circuit_breaker_callback'):
            self.risk_manager.set_circuit_breaker_callback(self.circuit_breaker_callback)
    
    def circuit_breaker_callback(self, is_active: bool, reason: str = None):
        """Callback function for circuit breaker status changes."""
        if is_active != self.last_circuit_breaker_state:
            if is_active:
                logger.warning(f"CIRCUIT BREAKER ACTIVATED: {reason}")
                self.trading_allowed = False
            else:
                logger.info("CIRCUIT BREAKER DEACTIVATED")
                self.trading_allowed = True
            
            self.last_circuit_breaker_state = is_active
    
    def execute_order(self, symbol: str, direction: str, amount: float) -> Dict[str, Any]:
        """
        Simulates order execution and returns the order result.
        In a real implementation, this would connect to a broker API.
        """
        # Simulate some processing time
        time.sleep(0.5)
        
        # In a real application, this would be the result from your broker's API
        order_result = {
            "order_id": f"ORD-{int(time.time())}-{random.randint(1000, 9999)}",
            "symbol": symbol,
            "direction": direction,
            "amount": amount,
            "status": "filled",
            "filled_price": random.uniform(1.0, 2.0),  # Simulate a price
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"Order executed: {symbol} {direction} {amount}")
        return order_result
    
    def check_potential_trade(self, symbol: str, direction: str, 
                             amount: float, entry_price: float) -> Dict[str, Any]:
        """Check if a potential trade is within risk limits."""
        # Get current positions
        positions = self.position_fetcher.fetch_positions()
        
        # Create a simulated position for the trade we want to make
        potential_position = {
            "symbol": symbol,
            "direction": direction, 
            "amount": amount,
            "entry_price": entry_price,
            "current_price": entry_price,
            "pnl": 0,
            "timestamp": datetime.now().isoformat()
        }
        
        # Check if adding this position would violate risk limits
        augmented_positions = positions + [potential_position]
        risk_status = self.risk_manager.check_risk_limits(augmented_positions)
        
        return risk_status
    
    def place_trade_if_safe(self, symbol: str, direction: str, 
                           amount: float, entry_price: float) -> Dict[str, Any]:
        """Place a trade only if it doesn't violate risk limits."""
        if not self.trading_allowed:
            logger.warning("Trading is currently not allowed (circuit breaker active)")
            return {"status": "rejected", "reason": "circuit_breaker_active"}
        
        # Check risk limits before placing the trade
        risk_status = self.check_potential_trade(symbol, direction, amount, entry_price)
        
        if risk_status.get("violations", []):
            violations = risk_status["violations"]
            logger.warning(f"Trade rejected due to risk violations: {violations}")
            return {"status": "rejected", "reason": "risk_limits", "violations": violations}
        
        # If we reach here, the trade is safe to execute
        return self.execute_order(symbol, direction, amount)
    
    def run_trading_loop(self, interval: int = 10, max_iterations: int = 30):
        """Main trading loop that periodically checks positions and risk status."""
        self.running = True
        iteration = 0
        
        try:
            while self.running and (max_iterations <= 0 or iteration < max_iterations):
                logger.info(f"Trading loop iteration {iteration + 1}")
                
                # 1. Fetch current positions
                positions = self.position_fetcher.fetch_positions(force_refresh=True)
                logger.info(f"Current positions: {len(positions)}")
                
                # 2. Update the risk manager with latest position data
                self.risk_manager.update_positions(positions)
                
                # 3. Get current risk metrics
                exposure_summary = self.risk_manager.get_exposure_summary()
                logger.info(f"Total exposure: {exposure_summary.get('total_exposure', 0)}")
                
                # 4. Check for risk limit violations
                risk_status = self.risk_manager.check_risk_limits(positions)
                if risk_status.get("violations", []):
                    violations = risk_status["violations"]
                    logger.warning(f"Risk violations detected: {violations}")
                    
                    # Take corrective action if needed
                    if any(v.get("severity") == "critical" for v in violations):
                        logger.critical("Critical violation detected - would reduce positions here")
                        # In a real application, you would reduce positions here
                
                # 5. Simulate a new trade (in a real app, this would come from your strategy)
                if iteration % 5 == 0 and self.trading_allowed:
                    # Simulate different trade scenarios
                    if iteration % 15 == 0:
                        # Simulate a trade that might exceed limits
                        symbol = "EUR/USD"
                        direction = "buy"
                        amount = self.risk_manager.account_balance * 0.2  # Large position
                    else:
                        # Normal trade
                        symbol = random.choice(["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"])
                        direction = random.choice(["buy", "sell"])
                        amount = self.risk_manager.account_balance * random.uniform(0.01, 0.05)
                    
                    entry_price = random.uniform(1.0, 2.0)
                    
                    logger.info(f"Attempting to place trade: {symbol} {direction} {amount:.2f}")
                    result = self.place_trade_if_safe(symbol, direction, amount, entry_price)
                    logger.info(f"Trade result: {result.get('status', 'unknown')}")
                
                # 6. Wait for next iteration
                time.sleep(interval)
                iteration += 1
                
        except KeyboardInterrupt:
            logger.info("Trading loop terminated by user")
        finally:
            self.running = False
            logger.info("Trading loop ended")


def main():
    """Main entry point for the example."""
    # Load configuration
    config_path = "config/risk_config.yaml"
    config = load_config(config_path)
    
    # Create default config if it doesn't exist
    if not config:
        config = {
            "max_risk_per_trade": 0.02,  # 2% max risk per trade
            "max_asset_exposure": 0.1,   # 10% max exposure per asset
            "max_class_exposure": 0.25,  # 25% max exposure per asset class
            "max_global_exposure": 0.6,  # 60% max total exposure
            "circuit_breaker_enabled": True,
            "circuit_breaker_threshold": 0.05,  # 5% drawdown triggers circuit breaker
            "warning_threshold": 0.8,    # 80% of any limit triggers warning
            "danger_threshold": 0.95,    # 95% of any limit triggers danger
        }
    
    # Initialize risk manager
    risk_manager = RiskManager(
        account_balance=10000.0,  # $10,000 starting balance
        params=config
    )
    
    # Initialize position fetcher
    position_fetcher = PositionDataFetcher()
    
    # Create trading simulator
    simulator = TradingExampleSimulator(risk_manager, position_fetcher)
    
    # Run the trading loop (10-second intervals, 30 iterations max)
    logger.info("Starting trading simulation with risk management")
    simulator.run_trading_loop(interval=10, max_iterations=30)
    logger.info("Trading simulation completed")


if __name__ == "__main__":
    main() 