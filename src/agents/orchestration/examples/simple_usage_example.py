"""
Simple Usage Example

This script demonstrates the basic usage of the Signal Validation and Orchestration System.
"""

import sys
import os
import time
import uuid
import logging
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from .orchestration import setup_orchestration_system
from .orchestration.models import TradingSignal, MarketConditions

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("example")

class MockPriceDataProvider:
    """Mock price data provider for demonstration purposes."""
    
    def get_price_data(self, trading_pair: str, timeframe: str, limit: int) -> List[Dict[str, Any]]:
        """Get mock price data."""
        # Generate mock OHLCV data
        base_price = 100.0
        if trading_pair == "BTC/USD":
            base_price = 50000.0
        elif trading_pair == "ETH/USD":
            base_price = 3000.0
        
        result = []
        for i in range(limit):
            # Generate slightly random prices
            close = base_price * (1 + 0.01 * random.uniform(-1, 1))
            open_price = close * (1 + 0.005 * random.uniform(-1, 1))
            high = max(open_price, close) * (1 + 0.003 * random.uniform(0, 1))
            low = min(open_price, close) * (1 - 0.003 * random.uniform(0, 1))
            volume = 1000 * random.uniform(0.5, 1.5)
            
            # Add timestamp
            timestamp = datetime.now() - timedelta(hours=limit-i)
            
            # Add to result
            result.append({
                "timestamp": timestamp,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume
            })
        
        return result

def generate_mock_signal(trading_pair: str) -> TradingSignal:
    """Generate a mock trading signal."""
    # Create random signal attributes
    signal_types = ["trend", "momentum", "pattern", "reversal"]
    directions = ["buy", "sell"]
    timeframes = ["5m", "15m", "1h", "4h", "1d"]
    
    return TradingSignal(
        id=str(uuid.uuid4()),
        trading_pair=trading_pair,
        created_at=datetime.now(),
        agent_id=f"mock_agent_{random.randint(1, 5)}",
        signal_type=random.choice(signal_types),
        direction=random.choice(directions),
        timeframe=random.choice(timeframes),
        strength=random.uniform(0.5, 1.0),
        confidence=random.uniform(0.5, 1.0)
    )

def main():
    """Main function demonstrating the orchestration system."""
    # Define configuration
    config = {
        "log_level": "INFO",
        "orchestrator": {
            "max_signals_cache_size": 100
        },
        "market_conditions": {
            "cache_expiry_seconds": 60,
            "trend_threshold": 0.6,
            "volatility_threshold": 0.7
        },
        "validators": {
            "statistical": {
                "threshold": 0.6,
                "zscore_threshold": 2.0,
                "min_samples": 3
            }
        },
        "filters": {
            "market_condition": {
                "volatility_threshold": 0.8,
                "volume_threshold": 0.3,
                "regime_confidence": 0.7
            }
        },
        "api": {
            "api_keys": {
                "test_key": {"permissions": ["read", "subscribe"]}
            }
        }
    }
    
    # Create mock price data provider
    price_provider = MockPriceDataProvider()
    
    # Set up orchestration system
    logger.info("Setting up orchestration system...")
    system = setup_orchestration_system(config, price_provider)
    
    # Extract components
    orchestrator = system["orchestrator"]
    api = system["api"]
    
    # Define trading pairs
    trading_pairs = ["BTC/USD", "ETH/USD", "XRP/USD"]
    
    # Register trading pairs with orchestrator
    for pair in trading_pairs:
        orchestrator.register_trading_pair(pair)
    
    # Define signal handling callback
    def on_new_signal(signal):
        logger.info(f"New signal received: {signal.trading_pair} {signal.direction} "
                   f"(confidence: {signal.confidence:.2f})")
    
    # Subscribe to signals via API
    api.subscribe(api_key="test_key", callback=on_new_signal)
    
    # Process some mock signals
    logger.info("Processing mock signals...")
    for i in range(20):
        # Randomly select a trading pair
        pair = random.choice(trading_pairs)
        
        # Generate and process a mock signal
        signal = generate_mock_signal(pair)
        logger.info(f"Generated signal: {pair} {signal.direction} "
                   f"(confidence: {signal.confidence:.2f})")
        
        # Process the signal
        result = orchestrator.process_signal(signal)
        
        if result:
            logger.info(f"Signal published: {result.id}")
        else:
            logger.info("Signal rejected")
            
        # Wait a bit
        time.sleep(0.5)
    
    # Print some statistics
    logger.info("\nOrchestration system statistics:")
    for pair in trading_pairs:
        metrics = orchestrator.performance_metrics.get(pair, {})
        signals_processed = metrics.get("signals_processed", 0)
        avg_time = metrics.get("avg_processing_time_ms", 0)
        logger.info(f"{pair}: Processed {signals_processed} signals, "
                   f"avg processing time: {avg_time:.2f}ms")
    
    # Get recent published signals
    recent_signals = api.get_signals(api_key="test_key", limit=5)
    logger.info(f"\nRecent published signals ({len(recent_signals)}):")
    for signal in recent_signals:
        logger.info(f"{signal.trading_pair} {signal.direction} "
                  f"(confidence: {signal.confidence:.2f})")
    
    logger.info("Example completed.")

if __name__ == "__main__":
    main() 