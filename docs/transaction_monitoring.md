# Blockchain Transaction Monitoring System

## Overview

The Blockchain Transaction Monitoring System is designed to track deposits to user wallet addresses on the Binance Smart Chain (BSC). It monitors blockchain transactions, matches them to user wallets, processes them based on confirmation thresholds, and updates user balances accordingly.

## Features

- **Blockchain Listener**: Continuously monitors new blocks on the BSC network for transactions to user wallets
- **Confirmation Threshold**: Configurable number of block confirmations required before a transaction is considered final
- **Transaction Processing Queue**: Efficiently processes incoming transactions
- **Balance Synchronization**: Periodically checks for discrepancies between on-chain and database balances
- **Chain Reorganization Handling**: Detects and handles blockchain reorganizations to prevent double-counting
- **Automatic Recovery**: Automatically recovers from network disruptions
- **Logging**: Comprehensive logging of transaction processing and errors
- **Configurable**: Extensive configuration options via JSON configuration file

## Installation

### Prerequisites

- Python 3.7+
- PostgreSQL database
- `web3.py` and other dependencies listed in `requirements.txt`

### Setup

1. Install required dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Set up environment variables or use a `.env` file with the following variables:
   ```
   DATABASE_URL=postgresql://user:password@localhost:5432/forex
   WALLET_ENCRYPTION_KEY=your_secure_key
   BSC_MAINNET_RPC_URL=https://bsc-dataseed.binance.org/
   BSC_TESTNET_RPC_URL=https://data-seed-prebsc-1-s1.binance.org:8545/
   BLOCKCHAIN_NETWORK=bsc_mainnet  # or bsc_testnet for testing
   ```

3. Create config directory and settings file:
   ```
   mkdir -p config
   cp config/monitor_settings.example.json config/monitor_settings.json
   ```

4. Edit the configuration file to match your requirements.

## Configuration

The system is configured via `config/monitor_settings.json`. Here's an explanation of key configuration options:

### Network Configuration

```json
"network": {
  "bsc_mainnet": {
    "rpc_url": "https://bsc-dataseed.binance.org/",
    "chain_id": 56,
    "block_time": 3,
    "confirmation_blocks": 12,
    "retry_interval": 5,
    "max_retries": 5
  },
  "bsc_testnet": {
    "rpc_url": "https://data-seed-prebsc-1-s1.binance.org:8545/",
    "chain_id": 97,
    "block_time": 3,
    "confirmation_blocks": 6,
    "retry_interval": 5,
    "max_retries": 5
  }
}
```

- `rpc_url`: URL for the blockchain RPC endpoint
- `chain_id`: Blockchain network identifier
- `block_time`: Average block time in seconds
- `confirmation_blocks`: Number of blocks required for confirmation
- `retry_interval`: Seconds to wait between retries on failure
- `max_retries`: Maximum number of retry attempts before giving up

### Monitoring Configuration

```json
"monitoring": {
  "enabled": true,
  "polling_interval": 30,
  "batch_size": 100,
  "log_level": "INFO",
  "confirmation_threshold": 12,
  "max_blocks_per_batch": 50,
  "alert_on_reorg": true,
  "balance_check_interval": 900
}
```

- `enabled`: Whether monitoring is enabled
- `polling_interval`: Seconds between blockchain checks
- `batch_size`: Maximum number of transactions to process in one batch
- `log_level`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `confirmation_threshold`: Number of confirmations required for a transaction
- `max_blocks_per_batch`: Maximum number of blocks to process in one cycle
- `alert_on_reorg`: Whether to alert on chain reorganizations
- `balance_check_interval`: Seconds between balance synchronization checks

## Usage

### Starting the Monitor

#### As a Python Module

```python
from src.account.blockchain_monitor import start_monitoring

# Start with default config
start_monitoring()

# Or with custom config path
start_monitoring("path/to/custom_config.json")
```

#### Using the Command-Line Script

```bash
# Start in foreground mode
python scripts/start_transaction_monitor.py

# Start in daemon mode
python scripts/start_transaction_monitor.py --daemon

# Use testnet
python scripts/start_transaction_monitor.py --network bsc_testnet

# Use custom config
python scripts/start_transaction_monitor.py --config path/to/custom_config.json
```

#### Using Systemd Service

1. Copy the service file to systemd directory:
   ```
   sudo cp config/blockchain-monitor.service /etc/systemd/system/
   ```

2. Edit the service file to match your installation path.

3. Enable and start the service:
   ```
   sudo systemctl daemon-reload
   sudo systemctl enable blockchain-monitor.service
   sudo systemctl start blockchain-monitor.service
   ```

4. Check service status:
   ```
   sudo systemctl status blockchain-monitor.service
   ```

### Stopping the Monitor

```python
from src.account.blockchain_monitor import stop_monitoring

# Stop the monitor
stop_monitoring()
```

Or if using systemd:

```bash
sudo systemctl stop blockchain-monitor.service
```

## Database Schema

The system uses the following tables:

### blockchain_sync_status

Tracks the last processed block for each blockchain.

```sql
CREATE TABLE blockchain_sync_status (
    chain_id INTEGER PRIMARY KEY,
    block_number BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

### blockchain_transactions

Stores information about monitored blockchain transactions.

```sql
CREATE TABLE blockchain_transactions (
    id SERIAL PRIMARY KEY,
    tx_hash VARCHAR(66) NOT NULL,
    from_address VARCHAR(42) NOT NULL,
    to_address VARCHAR(42) NOT NULL,
    block_number BIGINT NOT NULL,
    value NUMERIC(30, 18) NOT NULL,
    chain_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    confirmations INTEGER NOT NULL DEFAULT 0,
    user_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE(tx_hash, chain_id)
);
CREATE INDEX idx_blockchain_tx_to_address ON blockchain_transactions(to_address);
CREATE INDEX idx_blockchain_tx_block_number ON blockchain_transactions(block_number);
CREATE INDEX idx_blockchain_tx_status ON blockchain_transactions(status);
CREATE INDEX idx_blockchain_tx_user_id ON blockchain_transactions(user_id);
```

### balance_discrepancies

Records discrepancies between on-chain and database balances.

```sql
CREATE TABLE balance_discrepancies (
    id SERIAL PRIMARY KEY,
    wallet_id INTEGER NOT NULL REFERENCES wallets(id),
    chain_balance NUMERIC(30, 18) NOT NULL,
    db_balance NUMERIC(30, 18) NOT NULL,
    difference NUMERIC(30, 18) NOT NULL,
    resolved BOOLEAN DEFAULT FALSE,
    resolution_notes TEXT,
    created_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP
);
CREATE INDEX idx_balance_discrepancies_wallet_id ON balance_discrepancies(wallet_id);
CREATE INDEX idx_balance_discrepancies_created_at ON balance_discrepancies(created_at);
```

## Monitoring and Maintenance

### Logs

Check the logs for monitoring activity:

```bash
# For systemd service
sudo journalctl -u blockchain-monitor.service

# For foreground process
tail -f blockchain_monitor.log
```

### Balance Discrepancies

Query the `balance_discrepancies` table to find and resolve balance issues:

```sql
-- Find unresolved discrepancies
SELECT * FROM balance_discrepancies WHERE resolved = FALSE ORDER BY created_at DESC;

-- Resolve a discrepancy
UPDATE balance_discrepancies SET resolved = TRUE, resolution_notes = 'Manual adjustment made', resolved_at = NOW() WHERE id = 123;
```

### Transaction Status

Check transaction status in the `blockchain_transactions` table:

```sql
-- Check transactions by status
SELECT * FROM blockchain_transactions WHERE status = 'pending' ORDER BY created_at DESC;

-- Find transactions for a specific user
SELECT * FROM blockchain_transactions WHERE user_id = 456 ORDER BY created_at DESC;
```

## Troubleshooting

### Common Issues

#### Monitor not processing transactions

1. Check if the service is running:
   ```
   sudo systemctl status blockchain-monitor.service
   ```

2. Verify RPC endpoint connectivity:
   ```python
   from web3 import Web3
   web3 = Web3(Web3.HTTPProvider("https://bsc-dataseed.binance.org/"))
   print(web3.is_connected())  # Should return True
   ```

3. Check the logs for errors.

#### Balance discrepancies

If there are unexplained balance discrepancies:

1. Check for transactions still pending confirmation:
   ```sql
   SELECT * FROM blockchain_transactions WHERE to_address = '0x...' AND status = 'pending';
   ```

2. Look for chain reorganizations:
   ```sql
   SELECT * FROM blockchain_transactions WHERE status = 'reorg';
   ```

3. Manually verify the on-chain balance:
   ```python
   from web3 import Web3
   web3 = Web3(Web3.HTTPProvider("https://bsc-dataseed.binance.org/"))
   balance_wei = web3.eth.get_balance("0x...")
   balance_ether = web3.from_wei(balance_wei, 'ether')
   print(balance_ether)
   ```

## Security Considerations

1. **Private Keys**: The system does not handle private keys for transaction sending, only monitoring.

2. **Database Security**: Ensure database access is properly secured.

3. **RPC Endpoints**: Use reliable RPC providers and consider running your own BSC node for production.

4. **Confirmation Thresholds**: Higher confirmation thresholds are more secure but introduce more delay.

5. **Chain Reorganizations**: The system handles reorgs automatically, but deep reorgs (beyond the confirmation threshold) could cause issues. 