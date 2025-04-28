# Deposit Address Monitoring System

This document describes the design and implementation of the deposit address monitoring system for tracking blockchain transactions to user deposit addresses.

## Overview

The deposit monitoring system continuously scans the blockchain for transactions sent to user wallet addresses, processes them according to confirmation thresholds, and updates user balances accordingly. The system is designed to be resilient, handling network disruptions and providing detailed logging for unusual transaction patterns.

## Architecture

The monitoring system consists of the following components:

1. **Blockchain Listener**: Monitors the blockchain for new blocks and transactions.
2. **Transaction Processor**: Verifies and processes transactions when they reach the confirmation threshold.
3. **Balance Synchronizer**: Updates user account balances when deposits are confirmed.
4. **Monitoring Service**: Coordinates the components and provides a unified API.

## Features

- **Multi-chain support**: Monitor multiple blockchains (BSC, BSC Testnet) simultaneously.
- **Configurable confirmation thresholds**: Define different confirmation requirements per blockchain.
- **Transaction queue**: Process transactions in an orderly fashion even during high volume periods.
- **Automatic recovery**: Resume from the last processed block after service restarts.
- **Unusual pattern detection**: Log suspicious transaction patterns for review.
- **Dynamic address monitoring**: Automatically detect and monitor new user wallet addresses.

## Requirements

- Python 3.8+
- Web3.py
- PostgreSQL database
- Python-Daemon (for running as a service)

## Configuration

The system is configured via the `config/deposit_monitor.json` file:

```json
{
  "chains": [
    {
      "chain_id": 56,
      "rpc_url": "https://bsc-dataseed.binance.org/",
      "confirmation_threshold": 12,
      "poll_interval": 15
    },
    {
      "chain_id": 97,
      "rpc_url": "https://data-seed-prebsc-1-s1.binance.org:8545/",
      "confirmation_threshold": 6,
      "poll_interval": 10
    }
  ]
}
```

Environment variables can also be used to configure the system:

- `BSC_RPC_URL`: URL for BSC blockchain node
- `BSC_CHAIN_ID`: Chain ID for BSC (default: 56)
- `CONFIRMATION_THRESHOLD`: Number of confirmations required (default: 12)
- `POLL_INTERVAL`: How often to check for new blocks (default: 15 seconds)
- `BACKOFF_TIME`: Base time for exponential backoff on errors (default: 60 seconds)

## Database Schema

The system uses the following database tables:

```sql
-- Table to track blockchain sync status
CREATE TABLE blockchain_sync_status (
    chain_id INTEGER PRIMARY KEY,
    block_number BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Table to store all blockchain transactions
CREATE TABLE blockchain_transactions (
    id SERIAL PRIMARY KEY,
    tx_hash VARCHAR(66) NOT NULL,
    from_address VARCHAR(42) NOT NULL,
    to_address VARCHAR(42) NOT NULL,
    block_number BIGINT NOT NULL,
    value NUMERIC(28, 18) NOT NULL, -- Support for 18 decimal places
    chain_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    confirmations INTEGER NOT NULL DEFAULT 0,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_tx UNIQUE (tx_hash)
);

-- Table to store account transactions (deposits, withdrawals, etc.)
CREATE TABLE account_transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    type VARCHAR(20) NOT NULL,
    amount NUMERIC(28, 18) NOT NULL,
    reference VARCHAR(255),
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

## Usage

### Starting the Service

```bash
# Run in foreground mode
python scripts/run_deposit_monitor.py

# Run as daemon
python scripts/run_deposit_monitor.py --daemon

# Stop daemon
python scripts/run_deposit_monitor.py --stop

# Use custom config file
python scripts/run_deposit_monitor.py --config /path/to/config.json
```

### Integration with Application

The deposit monitor service can be accessed programmatically:

```python
from src.account.deposit_monitor import get_deposit_monitor_service

# Get the singleton service instance
service = get_deposit_monitor_service()

# Start monitoring
service.start()

# Add a new blockchain to monitor
from src.account.deposit_monitor import BlockchainConfig
config = BlockchainConfig(
    chain_id=97,  # BSC Testnet
    rpc_url="https://data-seed-prebsc-1-s1.binance.org:8545/",
    confirmation_threshold=6
)
service.add_blockchain(config)

# Refresh monitored addresses (e.g., after new user registration)
service.refresh_monitored_addresses()

# Stop monitoring
service.stop()
```

## Error Handling and Recovery

The system includes several mechanisms to handle errors and recover from failures:

1. **Exponential backoff**: When RPC connections fail, the system will back off exponentially to avoid overwhelming the node.
2. **Transaction state tracking**: Transaction states are persisted in the database, allowing the system to recover from crashes.
3. **Block synchronization**: The system tracks the last processed block to ensure no transactions are missed during restarts.

## Security Considerations

1. **Private key safety**: The system never handles private keys directly during deposit monitoring.
2. **Unusual pattern detection**: Large deposits or unusual patterns are logged for manual review.
3. **Confirmations**: Configurable confirmation thresholds protect against chain reorganizations.

## Monitoring and Maintenance

### Logs

Log files are stored in the `logs/` directory:

- `deposit_monitor.log`: Main application log
- `deposit_monitor_stdout.log`: Standard output when running as daemon
- `deposit_monitor_stderr.log`: Standard error when running as daemon

### Performance Optimization

For high-volume deployments, consider:

1. Increasing the `poll_interval` to reduce RPC load
2. Using a dedicated blockchain node rather than public endpoints
3. Implementing database indexing for frequently queried tables
4. Sharding transaction history for improved query performance

## Testing

Unit tests are provided in `src/account/test_deposit_monitor.py`, covering:

- Transaction detection and processing
- Confirmation threshold handling
- User balance updates
- Unusual pattern detection

Run the tests with:

```bash
python -m unittest src.account/test_deposit_monitor.py
``` 