-- Transaction table for deposit monitoring system
-- Schema for storing and tracking blockchain transactions

-- Drop table if exists to avoid errors on re-creation
DROP TABLE IF EXISTS transactions;

-- Create transactions table
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    chain_id INTEGER NOT NULL,
    hash VARCHAR(255) NOT NULL,
    from_address VARCHAR(255) NOT NULL,
    to_address VARCHAR(255) NOT NULL, 
    token VARCHAR(255) NOT NULL,
    amount NUMERIC(36, 18) NOT NULL,
    block_number INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL,
    confirmation_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_transaction UNIQUE (chain_id, hash)
);

-- Create indexes for faster queries
CREATE INDEX idx_transactions_user_id ON transactions (user_id);
CREATE INDEX idx_transactions_to_address ON transactions (to_address);
CREATE INDEX idx_transactions_status ON transactions (status);
CREATE INDEX idx_transactions_chain_hash ON transactions (chain_id, hash);

-- Table for tracking the last processed block for each chain
DROP TABLE IF EXISTS chain_sync;

CREATE TABLE chain_sync (
    chain_id INTEGER PRIMARY KEY,
    last_processed_block INTEGER NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add comment explaining the purpose of this schema
COMMENT ON TABLE transactions IS 'Stores blockchain transactions related to user deposits';
COMMENT ON TABLE chain_sync IS 'Tracks last processed block for each blockchain to enable resuming monitoring';

-- Update the updated_at column automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_transactions_updated_at
    BEFORE UPDATE ON transactions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column(); 