#!/usr/bin/env python
"""
MongoDB Example Script for Forex Trading Application

This script demonstrates how to use the MongoDB modules for the Forex Trading application.
It provides examples of initializing the database, creating and retrieving data,
and performing business-level queries.
"""

import os
import sys
import logging
import datetime
import random
import uuid
from decimal import Decimal
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.db.mongodb_connection import (
    get_mongodb_client, get_mongodb_database, 
    get_collection, close_mongodb_connection
)
from src.db.mongodb_init import initialize_database, verify_database_setup
from src.db.mongodb_operations import (
    create_trade, get_trade_by_id, get_trades, update_trade, close_trade, delete_trade,
    create_account, get_account_by_id, get_accounts, update_account, delete_account,
    create_strategy, get_strategy_by_id, get_strategies, update_strategy, delete_strategy,
    create_journal_entry, get_journal_entry_by_id, get_journal_entries
)
from src.db.mongodb_queries import (
    get_account_performance, get_strategy_performance,
    get_trade_with_context, get_trade_statistics_by_symbol, get_daily_performance
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_sample_data():
    """Create sample data for demonstration purposes."""
    logger.info("Creating sample data...")
    
    # Create a sample account
    account_data = {
        'account_id': str(uuid.uuid4()),
        'name': 'Demo Trading Account',
        'broker': 'Demo Broker',
        'account_type': 'DEMO',
        'currency': 'USD',
        'balance': 10000.0,
        'equity': 10000.0,
        'leverage': 100,
        'is_active': True,
        'notes': 'Sample account for demonstration purposes'
    }
    
    account_id = create_account(account_data)
    logger.info(f"Created account with ID: {account_id}")
    
    # Create a sample strategy
    strategy_data = {
        'strategy_id': str(uuid.uuid4()),
        'name': 'Trend Following Strategy',
        'description': 'A simple trend following strategy based on moving averages',
        'category': 'trend-following',
        'timeframes': ['1h', '4h', 'daily'],
        'instruments': ['EURUSD', 'GBPUSD', 'USDJPY'],
        'risk_per_trade': 2.0,
        'typical_rr_ratio': 2.5,
        'is_active': True,
        'entry_rules': 'Enter when fast MA crosses above slow MA',
        'exit_rules': 'Exit when fast MA crosses below slow MA or at take profit/stop loss'
    }
    
    strategy_id = create_strategy(strategy_data)
    logger.info(f"Created strategy with ID: {strategy_id}")
    
    # Create sample trades
    currency_pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD']
    directions = ['BUY', 'SELL']
    
    # Create some closed trades in the past
    for i in range(20):
        # Random trade data
        symbol = random.choice(currency_pairs)
        direction = random.choice(directions)
        
        # Random dates in the past month
        days_ago = random.randint(1, 30)
        hours_ago = random.randint(1, 24)
        
        open_time = datetime.datetime.utcnow() - datetime.timedelta(days=days_ago, hours=hours_ago)
        close_time = open_time + datetime.timedelta(hours=random.randint(1, 48))
        
        # Random prices
        base_price = round(random.uniform(1.0, 1.5), 5)
        
        if direction == 'BUY':
            open_price = base_price
            # 60% chance of profit
            if random.random() < 0.6:
                close_price = round(base_price + random.uniform(0.001, 0.01), 5)
            else:
                close_price = round(base_price - random.uniform(0.001, 0.005), 5)
        else:  # SELL
            open_price = base_price
            # 60% chance of profit
            if random.random() < 0.6:
                close_price = round(base_price - random.uniform(0.001, 0.01), 5)
            else:
                close_price = round(base_price + random.uniform(0.001, 0.005), 5)
        
        # Calculate PNL
        lot_size = random.choice([0.1, 0.2, 0.5, 1.0])
        pip_value = 10.0 if lot_size == 1.0 else lot_size * 10.0
        
        if direction == 'BUY':
            pips = (close_price - open_price) * 10000
            pnl = round(pips * pip_value, 2)
        else:  # SELL
            pips = (open_price - close_price) * 10000
            pnl = round(pips * pip_value, 2)
        
        # Create the trade
        trade_data = {
            'trade_id': str(uuid.uuid4()),
            'account_id': account_id,
            'strategy_id': strategy_id if random.random() < 0.7 else None,
            'symbol': symbol,
            'direction': direction,
            'open_time': open_time,
            'close_time': close_time,
            'open_price': open_price,
            'close_price': close_price,
            'lot_size': lot_size,
            'stop_loss': round(open_price - 0.005 if direction == 'BUY' else open_price + 0.005, 5),
            'take_profit': round(open_price + 0.01 if direction == 'BUY' else open_price - 0.01, 5),
            'pips': pips,
            'profit_loss': pnl,
            'status': 'CLOSED',
            'notes': f'Sample {direction} trade #{i+1}',
            'tags': ['sample', 'demo', symbol.lower()],
            'entry_type': 'MANUAL'
        }
        
        trade_id = create_trade(trade_data)
        logger.info(f"Created trade #{i+1} with ID: {trade_id}")
        
        # Create a journal entry for some trades
        if random.random() < 0.5:
            journal_data = {
                'entry_id': str(uuid.uuid4()),
                'account_id': account_id,
                'trade_id': trade_id,
                'date': close_time,
                'title': f'Journal for {symbol} {direction} trade',
                'content': f'This trade was executed according to the plan. Entry at {open_price}, exit at {close_price}.',
                'mood': random.choice(['POSITIVE', 'NEUTRAL', 'NEGATIVE']),
                'tags': ['sample', symbol.lower()],
                'market_conditions': 'Ranging market with low volatility',
                'lessons_learned': 'Need to be more patient with entries'
            }
            
            entry_id = create_journal_entry(journal_data)
            logger.info(f"Created journal entry for trade #{i+1} with ID: {entry_id}")
    
    # Create a couple of open trades
    for i in range(3):
        symbol = random.choice(currency_pairs)
        direction = random.choice(directions)
        
        # Recent open time
        hours_ago = random.randint(1, 24)
        open_time = datetime.datetime.utcnow() - datetime.timedelta(hours=hours_ago)
        
        # Random price
        base_price = round(random.uniform(1.0, 1.5), 5)
        
        # Create the trade
        trade_data = {
            'trade_id': str(uuid.uuid4()),
            'account_id': account_id,
            'strategy_id': strategy_id if random.random() < 0.7 else None,
            'symbol': symbol,
            'direction': direction,
            'open_time': open_time,
            'open_price': base_price,
            'lot_size': random.choice([0.1, 0.2, 0.5, 1.0]),
            'stop_loss': round(base_price - 0.005 if direction == 'BUY' else base_price + 0.005, 5),
            'take_profit': round(base_price + 0.01 if direction == 'BUY' else base_price - 0.01, 5),
            'status': 'OPEN',
            'notes': f'Open {direction} trade #{i+1}',
            'tags': ['sample', 'demo', symbol.lower()],
            'entry_type': 'MANUAL'
        }
        
        trade_id = create_trade(trade_data)
        logger.info(f"Created open trade #{i+1} with ID: {trade_id}")
    
    return account_id, strategy_id

def demo_basic_operations():
    """Demonstrate basic MongoDB operations."""
    logger.info("\n=== Basic Database Operations ===")
    
    # Initialize database
    db = get_mongodb_database()
    
    # Verify database setup
    verify_result = verify_database_setup(db)
    logger.info(f"Database verification result: {verify_result['overall_status']}")
    
    # Create sample data
    account_id, strategy_id = create_sample_data()
    
    # Retrieve account
    account = get_account_by_id(account_id)
    logger.info(f"Retrieved account: {account['name']} with balance {account['balance']}")
    
    # Get all trades
    trades = get_trades(account_id=account_id, limit=5)
    logger.info(f"Retrieved {len(trades)} trades")
    
    if trades:
        # Get a specific trade
        trade_id = trades[0]['trade_id']
        trade = get_trade_by_id(trade_id)
        logger.info(f"Retrieved trade: {trade['symbol']} {trade['direction']} opened at {trade['open_time']}")
        
        # Update a trade
        if trade['status'] == 'OPEN':
            update_success = update_trade(trade_id, {
                'notes': 'Updated trade notes',
                'tags': trade.get('tags', []) + ['updated']
            })
            logger.info(f"Updated trade: {update_success}")
            
            # Close a trade
            current_price = trade['open_price'] * 1.01 if trade['direction'] == 'BUY' else trade['open_price'] * 0.99
            close_success = close_trade(
                trade_id=trade_id,
                close_price=current_price,
                close_time=datetime.datetime.utcnow(),
                notes='Closed trade manually'
            )
            logger.info(f"Closed trade: {close_success}")
        
        # Delete a trade (commented out for safety)
        # delete_success = delete_trade(trade_id)
        # logger.info(f"Deleted trade: {delete_success}")
    
    return account_id, strategy_id

def demo_business_queries(account_id, strategy_id):
    """Demonstrate business-level queries."""
    logger.info("\n=== Business-Level Queries ===")
    
    # Get account performance
    performance = get_account_performance(
        account_id=account_id,
        start_date=datetime.datetime.utcnow() - datetime.timedelta(days=30),
        end_date=datetime.datetime.utcnow()
    )
    
    logger.info(f"Account Performance for {performance['account_name']}:")
    logger.info(f"  Total Trades: {performance['total_trades']}")
    logger.info(f"  Win Rate: {performance['win_rate']:.2f}%")
    logger.info(f"  Total PnL: ${performance['total_pnl']:.2f}")
    logger.info(f"  Profit Factor: {performance['profit_factor']:.2f}")
    
    # Get strategy performance
    strategy_perf = get_strategy_performance(
        strategy_id=strategy_id,
        start_date=datetime.datetime.utcnow() - datetime.timedelta(days=30),
        end_date=datetime.datetime.utcnow()
    )
    
    logger.info(f"\nStrategy Performance for {strategy_perf['strategy_name']}:")
    logger.info(f"  Total Trades: {strategy_perf['total_trades']}")
    logger.info(f"  Win Rate: {strategy_perf['win_rate']:.2f}%")
    logger.info(f"  Total PnL: ${strategy_perf['total_pnl']:.2f}")
    
    # Get symbol performance
    symbol_stats = get_trade_statistics_by_symbol(
        account_id=account_id,
        start_date=datetime.datetime.utcnow() - datetime.timedelta(days=30),
        end_date=datetime.datetime.utcnow()
    )
    
    logger.info(f"\nPerformance by Symbol:")
    for symbol, stats in symbol_stats['symbols'].items():
        logger.info(f"  {symbol}: {stats['total_trades']} trades, Win Rate: {stats['win_rate']:.2f}%, PnL: ${stats['total_pnl']:.2f}")
    
    # Get daily performance
    daily_perf = get_daily_performance(
        account_id=account_id,
        start_date=datetime.datetime.utcnow() - datetime.timedelta(days=30),
        end_date=datetime.datetime.utcnow()
    )
    
    logger.info(f"\nDaily Performance:")
    for day in daily_perf:
        date_str = day['date'].strftime('%Y-%m-%d')
        logger.info(f"  {date_str}: {day['total_trades']} trades, PnL: ${day['total_pnl']:.2f}")
    
    return

def main():
    """Main function to demonstrate MongoDB usage."""
    try:
        logger.info("Starting MongoDB Example Script")
        
        # Test connection
        client = get_mongodb_client()
        logger.info("Successfully connected to MongoDB")
        
        # Run demonstrations
        account_id, strategy_id = demo_basic_operations()
        demo_business_queries(account_id, strategy_id)
        
        logger.info("Example script completed successfully")
    except Exception as e:
        logger.error(f"Error in example script: {str(e)}")
    finally:
        # Close connection
        close_mongodb_connection()
        logger.info("Closed MongoDB connection")

if __name__ == "__main__":
    main() 