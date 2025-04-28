# MongoDB Database Module for Forex Trading Application

This directory contains the MongoDB database modules for the Forex Trading application. These modules handle all database operations including connection management, schema definitions, CRUD operations, and business-level queries.

## Module Structure

- `mongodb_config.py`: Configuration settings for MongoDB connection
- `mongodb_connection.py`: Connection management and pooling
- `mongodb_schema.py`: Schema and index definitions for collections
- `mongodb_init.py`: Database initialization and validation
- `mongodb_operations.py`: Basic CRUD operations for collections
- `mongodb_queries.py`: Business-level queries and aggregations

## Collections

The database uses the following collections:

1. **trades**: Trading activity records
2. **accounts**: Trading accounts information
3. **strategies**: Trading strategies definitions
4. **journal_entries**: Trader's journal entries

## Getting Started

### Prerequisites

- MongoDB server (4.2+)
- pymongo package (`pip install pymongo`)

### Environment Variables

The module uses the following environment variables for configuration:

```
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_DB_NAME=forex_trading
MONGODB_USERNAME=
MONGODB_PASSWORD=
MONGODB_AUTH_SOURCE=admin
MONGODB_AUTH_MECHANISM=SCRAM-SHA-256
MONGODB_MIN_POOL_SIZE=5
MONGODB_MAX_POOL_SIZE=10
```

### Basic Usage

```python
# Initialize the database connection
from src.db.mongodb_connection import get_mongodb_database, get_collection

# Get the database
db = get_mongodb_database()

# Perform CRUD operations
from src.db.mongodb_operations import create_trade, get_trades

# Create a new trade
trade_data = {
    "symbol": "EURUSD",
    "direction": "BUY",
    "open_time": datetime.datetime.utcnow(),
    "open_price": 1.1050,
    "lot_size": 0.1,
    "status": "OPEN",
    "account_id": "account123"
}
trade_id = create_trade(trade_data)

# Get trades for an account
trades = get_trades(account_id="account123", limit=10)

# Use business-level queries
from src.db.mongodb_queries import get_account_performance

# Get account performance metrics
performance = get_account_performance(
    account_id="account123",
    start_date=datetime.datetime.utcnow() - datetime.timedelta(days=30),
    end_date=datetime.datetime.utcnow()
)
```

## Schema Validation

The database uses MongoDB schema validation to ensure data integrity. The schemas are defined in `mongodb_schema.py` and are applied when initializing the database.

## Connection Pooling

The module implements connection pooling to efficiently manage database connections. The pool size and other parameters can be configured via environment variables or the configuration file.

## Examples

See the `examples` directory for sample code demonstrating how to use the MongoDB modules.

## Error Handling

All database operations include proper error handling and logging. The module logs errors, warnings, and informational messages using the Python logging module.

## Thread Safety

The connection and operations are designed to be thread-safe, allowing for concurrent database access from multiple threads or processes.

## Indexes

The module creates appropriate indexes on collections to optimize query performance. The indexes are defined in `mongodb_schema.py` and are applied when initializing the database. 