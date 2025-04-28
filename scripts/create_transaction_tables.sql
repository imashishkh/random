-- SQL script to create tables for blockchain transaction monitoring

-- Table to track blockchain sync status
CREATE TABLE IF NOT EXISTS blockchain_sync_status (
    chain_id INTEGER PRIMARY KEY,
    block_number BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Table to store all blockchain transactions
CREATE TABLE IF NOT EXISTS blockchain_transactions (
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

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_tx_hash ON blockchain_transactions(tx_hash);
CREATE INDEX IF NOT EXISTS idx_to_address ON blockchain_transactions(to_address);
CREATE INDEX IF NOT EXISTS idx_user_id ON blockchain_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_status ON blockchain_transactions(status);
CREATE INDEX IF NOT EXISTS idx_created_at ON blockchain_transactions(created_at);

-- Table to store account transactions (deposits, withdrawals, etc.)
CREATE TABLE IF NOT EXISTS account_transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    type VARCHAR(20) NOT NULL, -- deposit, withdrawal, transfer, etc.
    amount NUMERIC(28, 18) NOT NULL,
    reference VARCHAR(128), -- Could be a blockchain tx hash or internal reference
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user
        FOREIGN KEY(user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_account_tx_user_id ON account_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_account_tx_type ON account_transactions(type);
CREATE INDEX IF NOT EXISTS idx_account_tx_created_at ON account_transactions(created_at); 