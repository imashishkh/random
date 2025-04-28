"""
Exposure Management System Example

This example demonstrates how to use the exposure management system, including
setting up exposure limits, circuit breakers, and monitoring market conditions.
"""

import logging
import time
import threading
from datetime import datetime
import random
import signal
import sys

from ..trading.risk import (
    ExposureManager,
    ExposureLimitType,
    ExposureLimit,
    CircuitBreaker,
    CircuitBreakerTrigger,
    CircuitBreakerDefinition,
    CircuitBreakerConfig,
    CircuitBreakerState,
    Observer,
    create_default_exposure_manager,
    create_exposure_limit_for_symbol,
    create_circuit_breaker_for_symbol,
    ExposureDashboard
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ExposureEventLogger(Observer):
    """Sample observer that logs exposure and circuit breaker events."""
    
    def update(self, subject, data=None):
        """Log events from the exposure manager."""
        if not data:
            return
            
        # Log circuit breaker events
        if "event" in data:
            event_type = data["event"]
            name = data.get("name", "unknown")
            
            if event_type == "triggered":
                logger.warning(f"CIRCUIT BREAKER TRIGGERED: {name} ({data.get('trigger_type', 'unknown')})")
                logger.warning(f"Action: {data.get('action', 'none')}")
                logger.warning(f"Applies to: {', '.join(data.get('applies_to', ['unknown']))}")
            elif event_type == "closed":
                logger.info(f"Circuit breaker closed: {name}")
            elif event_type == "half_open":
                logger.info(f"Circuit breaker in half-open state: {name}")


class MockMarketDataService:
    """Mock market data service for testing."""
    
    def __init__(self):
        """Initialize the mock market data service."""
        self.prices = {
            "BTC/USDT": 50000.0,
            "ETH/USDT": 3000.0,
            "EUR/USD": 1.10,
            "GBP/USD": 1.30
        }
        self.spreads = {
            "BTC/USDT": 1.0,
            "ETH/USDT": 0.5,
            "EUR/USD": 0.0002,
            "GBP/USD": 0.0003
        }
        self.volatilities = {
            "BTC/USDT": 0.02,
            "ETH/USDT": 0.025,
            "EUR/USD": 0.005,
            "GBP/USD": 0.006
        }
        
    def get_market_data(self, symbol):
        """Get market data for a symbol."""
        if symbol not in self.prices:
            return None
            
        # Add some random movement
        price_change = random.normalvariate(0, 0.002) * self.prices[symbol]
        self.prices[symbol] += price_change
        
        # Occasionally add volatility spike
        if random.random() < 0.05:  # 5% chance
            self.volatilities[symbol] *= (1.0 + random.uniform(0.1, 0.5))
        else:
            # Return to normal
            self.volatilities[symbol] = max(
                self.volatilities[symbol] * 0.95,
                {"BTC/USDT": 0.02, "ETH/USDT": 0.025, "EUR/USD": 0.005, "GBP/USD": 0.006}.get(symbol, 0.01)
            )
            
        # Occasionally add spread spike
        if random.random() < 0.05:  # 5% chance
            self.spreads[symbol] *= (1.0 + random.uniform(0.5, 2.0))
        else:
            # Return to normal
            self.spreads[symbol] = max(
                self.spreads[symbol] * 0.9,
                {"BTC/USDT": 1.0, "ETH/USDT": 0.5, "EUR/USD": 0.0002, "GBP/USD": 0.0003}.get(symbol, 0.1)
            )
            
        return {
            "symbol": symbol,
            "price": self.prices[symbol],
            "bid": self.prices[symbol] - self.spreads[symbol] / 2,
            "ask": self.prices[symbol] + self.spreads[symbol] / 2,
            "spread": self.spreads[symbol],
            "volatility": self.volatilities[symbol],
            "volume": random.uniform(100, 1000),
            "timestamp": datetime.now()
        }


def run_simulation():
    """Run a simulation of the exposure management system."""
    logger.info("Starting exposure management simulation")
    
    # Create a mock market data service
    market_data_service = MockMarketDataService()
    
    # Create the exposure manager with a starting balance of $100,000
    account_balance = 100000.0
    exposure_manager = create_default_exposure_manager(account_balance)
    
    # Create and attach an event logger
    event_logger = ExposureEventLogger()
    exposure_manager.attach(event_logger)
    
    # Create a dashboard
    dashboard = ExposureDashboard(exposure_manager, update_interval_seconds=1)
    
    # Set up sector mappings
    exposure_manager.set_symbol_sector("BTC/USDT", "crypto")
    exposure_manager.set_symbol_sector("ETH/USDT", "crypto")
    exposure_manager.set_symbol_sector("EUR/USD", "forex")
    exposure_manager.set_symbol_sector("GBP/USD", "forex")
    
    # Start the dashboard
    dashboard.start()
    
    # Register traders
    strategies = ["trend_following", "momentum", "value", "arbitrage"]
    
    # Add custom symbol-specific circuit breaker
    btc_volatility_breaker = create_circuit_breaker_for_symbol(
        "BTC/USDT", 
        CircuitBreakerTrigger.VOLATILITY_SPIKE,
        2.0,  # Lower threshold for BTC
        900   # 15 minute cooldown
    )
    exposure_manager.add_circuit_breaker(btc_volatility_breaker)
    
    # Simulate trading
    try:
        # Simulate adding positions over time
        symbols = ["BTC/USDT", "ETH/USDT", "EUR/USD", "GBP/USD"]
        positions = {}  # symbol -> exposure value
        
        for i in range(30):  # Run for 30 cycles
            # Randomly add or modify a position
            symbol = random.choice(symbols)
            
            # Get current exposure
            current_exposure = exposure_manager.get_asset_exposure(symbol)
            
            # Decide whether to increase or decrease position
            if symbol in positions:
                if random.random() < 0.3:  # 30% chance to decrease
                    new_exposure = max(0, current_exposure * random.uniform(0.5, 0.9))
                else:  # 70% chance to increase
                    new_exposure = current_exposure * random.uniform(1.1, 1.3)
            else:
                # New position
                new_exposure = random.uniform(5000, 15000)
                
            # Pick a random strategy
            strategy = random.choice(strategies)
            
            # Update the position
            logger.info(f"Updating position for {symbol} from {current_exposure:.2f} to {new_exposure:.2f} ({strategy})")
            result = exposure_manager.update_position(symbol, new_exposure, strategy)
            
            # Store the position
            positions[symbol] = new_exposure
            
            # Check for warnings or violations
            if result["warnings"]:
                logger.warning(f"Position update warnings: {', '.join(result['warnings'])}")
                
            if result["hard_limit_violated"]:
                logger.error(f"Position update rejected due to hard limit violation")
                
            # Simulate a volatility spike for testing circuit breakers
            if i == 10:  # On the 10th iteration
                logger.info("Simulating volatility spike for BTC/USDT")
                market_data_service.volatilities["BTC/USDT"] *= 5.0
                
            if i == 15:  # On the 15th iteration
                logger.info("Simulating spread spike for ETH/USDT")
                market_data_service.spreads["ETH/USDT"] *= 10.0
                
            # Fetch market data for all symbols for dashboard updates
            for sym in symbols:
                market_data_service.get_market_data(sym)
                
            # Wait a bit
            time.sleep(2)
            
        # Pause at the end to view the dashboard
        logger.info("Simulation complete - waiting 10 seconds before terminating")
        time.sleep(10)
            
    except KeyboardInterrupt:
        logger.info("Simulation interrupted by user")
    finally:
        # Stop the dashboard
        dashboard.stop()
        
    logger.info("Exposure management simulation complete")
    

if __name__ == "__main__":
    run_simulation() 