"""
Database access layer package
"""

# PostgreSQL connections
from .connection import get_connection, close_connection, init_db

# MongoDB connections
from .mongo_connection import get_database, get_collection
from .mongo_init import initialize_mongodb
from .mongodb_schema import (
    NewsArticle, 
    SentimentAnalysis, 
    MarketEvent, 
    DataSource, 
    DataSourceType
)

"""
MongoDB module for Forex Trading application.

This package provides MongoDB database functionality for the Forex Trading
application, including connection management, schema definitions, CRUD operations,
and business-level queries.
"""

from .mongodb_connection import (
    get_mongodb_client,
    get_mongodb_database,
    get_collection,
    get_available_collections,
    close_mongodb_connection
)

from .mongodb_operations import (
    # Trade operations
    create_trade,
    get_trade_by_id,
    get_trades,
    update_trade,
    close_trade,
    delete_trade,
    
    # Account operations
    create_account,
    get_account_by_id,
    get_accounts,
    update_account,
    delete_account,
    
    # Strategy operations
    create_strategy,
    get_strategy_by_id,
    get_strategies,
    update_strategy,
    delete_strategy,
    
    # Journal entry operations
    create_journal_entry,
    get_journal_entry_by_id,
    get_journal_entries,
    update_journal_entry,
    delete_journal_entry
)

from .mongodb_queries import (
    get_account_performance,
    get_strategy_performance,
    get_trade_with_context,
    get_trade_statistics_by_symbol,
    get_daily_performance
)

# MongoDB initialization
from .mongodb_init import (
    initialize_database,
    verify_database_setup
)

# MongoDB configuration
from .mongodb_config import (
    get_config,
    load_config_from_env,
    load_config_from_file,
    save_config_to_file
) 