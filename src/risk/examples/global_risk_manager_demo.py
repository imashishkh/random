"""
Global Risk Manager Usage Demo

This script demonstrates how to use the GlobalRiskManager for risk management,
position limit enforcement, and emergency controls.
"""

import logging
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import asyncio
import json
from pprint import pprint

from . import GlobalRiskManager
from .circuit_breakers import (
    CircuitBreaker,
    CircuitBreakerTrigger,
    CircuitBreakerScope,
    CircuitBreakerSeverity
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def demo_global_risk_manager():
    """
    Demonstrate GlobalRiskManager functionality.
    """
    logger.info("Starting Global Risk Manager Demo")
    
    # Create a risk manager with 100,000 USDT balance
    risk_manager = GlobalRiskManager(account_balance=100000.0)
    
    # Step 1: Configure global limits
    logger.info("\n----- Step 1: Configure global limits -----")
    risk_manager.set_global_limits(
        max_global_exposure=0.75,  # 75% max global exposure
        max_agent_exposure={
            'trend_following': 0.30,  # 30% max exposure for trend following strategy
            'mean_reversion': 0.25,   # 25% max exposure for mean reversion strategy
            'arbitrage': 0.20         # 20% max exposure for arbitrage strategy
        },
        max_symbol_exposure={
            'BTCUSDT': 0.25,          # 25% max exposure for Bitcoin
            'ETHUSDT': 0.20,          # 20% max exposure for Ethereum
            'BNBUSDT': 0.15           # 15% max exposure for Binance Coin
        }
    )
    
    logger.info("Global limits configured")
    
    # Step 2: Configure circuit breakers
    logger.info("\n----- Step 2: Configure circuit breakers -----")
    risk_manager.configure_circuit_breakers(
        enabled=True,
        volatility_threshold=2.5,     # Trigger when volatility is 2.5x normal
        price_change_threshold=0.03,  # Trigger on 3% sudden price change
        timeout=180                   # Circuit breaker lasts for 3 minutes
    )
    
    logger.info("Circuit breakers configured")
    
    # Step 3: Configure Slack alerts (if available)
    logger.info("\n----- Step 3: Configure alerts -----")
    try:
        # Ideally, this would be loaded from a secure config
        webhook_url = "https://hooks.slack.com/services/your/webhook/url"
        risk_manager.configure_slack_alerts(webhook_url)
        logger.info("Slack alerts configured")
    except Exception as e:
        logger.warning(f"Couldn't configure Slack alerts: {e}")
    
    # Step 4: Demo position sizing with normal conditions
    logger.info("\n----- Step 4: Demo normal position sizing -----")
    
    # Create sample market data
    price = 50000.0  # BTC price
    dates = pd.date_range(start=datetime.now() - timedelta(days=30), periods=30, freq='D')
    market_data = pd.DataFrame({
        'open': np.linspace(price * 0.9, price, 30),
        'high': np.linspace(price * 0.95, price * 1.05, 30),
        'low': np.linspace(price * 0.85, price * 0.95, 30),
        'close': np.linspace(price * 0.9, price, 30),
        'volume': np.random.rand(30) * 1000
    }, index=dates)
    
    # Calculate position size for BTC
    btc_position = risk_manager.calculate_position_size(
        symbol='BTCUSDT',
        market_data=market_data,
        risk_params={'risk_per_trade': 0.01}  # 1% risk per trade
    )
    
    logger.info(f"BTC Position result:")
    pprint(btc_position)
    
    # Add the position to tracking
    risk_manager.add_position('BTCUSDT', btc_position, asset_class='crypto')
    
    # Step 5: Demo exposure limits
    logger.info("\n----- Step 5: Demo exposure limits -----")
    
    # Simulate having positions that take up significant exposure
    # We'll do this by mocking the global positions
    risk_manager._global_positions = {
        'BTCUSDT': {
            'symbol': 'BTCUSDT',
            'position_amount': 1.0,
            'entry_price': 50000.0,
            'mark_price': 50000.0,
            'notional_value': 50000.0  # 50% of 100,000
        },
        'ETHUSDT': {
            'symbol': 'ETHUSDT',
            'position_amount': 10.0,
            'entry_price': 2000.0,
            'mark_price': 2000.0,
            'notional_value': 20000.0  # 20% of 100,000
        }
    }
    
    # Try to add another large position
    market_data.loc[:, 'close'] = np.linspace(2000 * 0.9, 2000, 30)  # Adjust for ETH price
    eth_position = risk_manager.calculate_position_size(
        symbol='ETHUSDT',
        market_data=market_data,
        risk_params={'risk_per_trade': 0.02}  # 2% risk per trade
    )
    
    logger.info("ETH Position result after high exposure (should be reduced):")
    pprint(eth_position)
    
    # Check current exposure
    exposure = risk_manager.get_exposure_summary()
    logger.info("Current exposure:")
    pprint(exposure)
    
    # Step 6: Demo risk limit checks
    logger.info("\n----- Step 6: Demo risk limit checks -----")
    
    # Mock fetch_binance_position_risk to return our simulated positions
    def mock_fetch():
        return [
            {
                'symbol': 'BTCUSDT',
                'position_amount': 1.0,
                'entry_price': 50000.0,
                'mark_price': 50000.0,
                'unreal_pnl': 0.0,
                'liquidation_price': 30000.0,
                'leverage': 1.0,
                'notional_value': 50000.0,
                'margin_type': 'cross',
                'isolated_margin': 0.0,
                'is_auto_add_margin': 'false',
                'position_side': 'BOTH'
            },
            {
                'symbol': 'ETHUSDT',
                'position_amount': 10.0,
                'entry_price': 2000.0,
                'mark_price': 2000.0,
                'unreal_pnl': 0.0,
                'liquidation_price': 1500.0,
                'leverage': 1.0,
                'notional_value': 20000.0,
                'margin_type': 'cross',
                'isolated_margin': 0.0,
                'is_auto_add_margin': 'false',
                'position_side': 'BOTH'
            }
        ]
    
    # Replace the actual method with our mock
    risk_manager.fetch_binance_position_risk = mock_fetch
    
    # Check risk limits
    risk_status = risk_manager.check_risk_limits()
    logger.info("Risk status:")
    pprint(risk_status)
    
    # Step 7: Demo circuit breaker activation
    logger.info("\n----- Step 7: Demo circuit breaker activation -----")
    
    # Manually activate a circuit breaker
    risk_manager.activate_circuit_breaker(
        reason="Demo activation",
        duration=120  # 2 minutes
    )
    
    # Check if circuit breaker is active
    is_active = risk_manager.is_circuit_breaker_active()
    logger.info(f"Circuit breaker active: {is_active}")
    
    # Try to calculate position size with circuit breaker active
    btc_position_blocked = risk_manager.calculate_position_size(
        symbol='BTCUSDT',
        market_data=market_data
    )
    
    logger.info("Position calculation with circuit breaker active:")
    pprint(btc_position_blocked)
    
    # Deactivate the circuit breaker
    risk_manager.deactivate_circuit_breaker()
    logger.info(f"Circuit breaker manually deactivated, active: {risk_manager.is_circuit_breaker_active()}")
    
    # Step 8: Demo emergency shutdown (simulation only)
    logger.info("\n----- Step 8: Demo emergency shutdown (simulation) -----")
    
    # We'll mock the actual exchange interaction to avoid real orders
    original_method = risk_manager.emergency_shutdown
    
    def mock_emergency_shutdown(reason="manual"):
        logger.info(f"SIMULATION: Emergency shutdown triggered: {reason}")
        positions = mock_fetch()
        
        # Simulated shutdown results
        results = []
        for position in positions:
            symbol = position['symbol']
            amount = position['position_amount']
            side = "SELL" if amount > 0 else "BUY"
            
            results.append({
                "symbol": symbol,
                "amount": amount,
                "success": True,
                "order": {"orderId": "simulation"}
            })
            
            logger.info(f"SIMULATION: Closed position for {symbol}, amount: {amount}")
        
        return {
            "success": True,
            "closed_positions": results
        }
    
    # Replace with mock
    risk_manager.emergency_shutdown = mock_emergency_shutdown
    
    # Trigger emergency shutdown
    shutdown_result = risk_manager.emergency_shutdown(reason="demo_emergency")
    logger.info("Emergency shutdown result:")
    pprint(shutdown_result)
    
    # Restore original method
    risk_manager.emergency_shutdown = original_method
    
    logger.info("\nGlobal Risk Manager Demo completed")


if __name__ == "__main__":
    asyncio.run(demo_global_risk_manager()) 