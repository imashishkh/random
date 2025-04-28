"""
Demonstration of the MarketDataRepository.

This script demonstrates the basic functionality of the MarketDataRepository
without requiring the full dependency tree.
"""
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Import locally to avoid dependency issues
from repository import MarketDataRepository

def main():
    """Run a demonstration of the MarketDataRepository."""
    # Create repository
    repo = MarketDataRepository()
    
    # Add some trade data
    symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]
    
    for symbol in symbols:
        # Create dummy trade data
        trade_data = {
            "symbol": symbol,
            "price": 1000.0 if symbol == "BTCUSDT" else 100.0,
            "quantity": 1.0,
            "timestamp": int(time.time() * 1000)
        }
        
        # Add to repository
        repo.update_trade(trade_data)
        logging.info(f"Added trade data for {symbol}")
    
    # Retrieve data
    for symbol in symbols:
        trade = repo.get_latest_trade(symbol)
        logging.info(f"Retrieved {symbol} trade: {trade}")
    
    # Test TTL expiration
    logging.info("Setting short TTL and waiting for expiration")
    repo.set_ttl("trades", 1)  # 1 second TTL
    
    # Wait for TTL to expire
    time.sleep(2)
    
    # Try to retrieve expired data
    for symbol in symbols:
        trade = repo.get_latest_trade(symbol)
        if trade is None:
            logging.info(f"{symbol} trade data has expired (as expected)")
        else:
            logging.warning(f"{symbol} trade data did not expire as expected")
    
    # Test clean expired data
    logging.info("Testing clean_expired_data")
    
    # Add new data
    for symbol in symbols:
        trade_data = {
            "symbol": symbol,
            "price": 2000.0 if symbol == "BTCUSDT" else 200.0,
            "quantity": 2.0,
            "timestamp": int(time.time() * 1000)
        }
        repo.update_trade(trade_data)
    
    # Set short TTL
    repo.set_ttl("trades", 1)
    
    # Wait for TTL to expire
    time.sleep(2)
    
    # Count trades before cleaning
    logging.info(f"Trades before cleaning: {len(repo.trades)}")
    
    # Clean expired data
    repo.clean_expired_data()
    
    # Count trades after cleaning
    logging.info(f"Trades after cleaning: {len(repo.trades)}")
    
    logging.info("Demonstration completed successfully")

if __name__ == "__main__":
    main() 