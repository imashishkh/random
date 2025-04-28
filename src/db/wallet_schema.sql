-- Wallet database schema for BEP20 wallet integration

-- Wallet table to store wallet information
CREATE TABLE IF NOT EXISTS wallets (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    address VARCHAR(42) NOT NULL,  -- Ethereum/BSC addresses are 42 chars (0x + 40 hex chars)
    wallet_type VARCHAR(20) NOT NULL CHECK (wallet_type IN ('hot', 'cold', 'exchange', 'multisig')),
    chain_id INTEGER NOT NULL,  -- Chain ID (56 for BSC mainnet, 97 for BSC testnet)
    encrypted_private_key TEXT,  -- Encrypted private key (for hot wallets)
    encrypted_mnemonic TEXT,  -- Encrypted mnemonic phrase
    name VARCHAR(255),  -- User-defined wallet name
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, address)
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_wallets_user_id ON wallets(user_id);
CREATE INDEX IF NOT EXISTS idx_wallets_address ON wallets(address);

-- Wallet transaction history
CREATE TABLE IF NOT EXISTS wallet_transactions (
    id SERIAL PRIMARY KEY,
    wallet_id INTEGER NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
    transaction_hash VARCHAR(66) NOT NULL,  -- Transaction hash is 66 chars (0x + 64 hex chars)
    from_address VARCHAR(42) NOT NULL,
    to_address VARCHAR(42) NOT NULL,
    token_address VARCHAR(42),  -- BEP20 token contract address
    amount NUMERIC(28, 18) NOT NULL,  -- Large numeric type for token amounts
    gas_used BIGINT,
    gas_price NUMERIC(28, 18),
    block_number BIGINT,
    block_timestamp TIMESTAMP WITH TIME ZONE,
    status BOOLEAN,  -- Transaction success status
    nonce INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(wallet_id, transaction_hash)
);

-- Index for faster transaction lookups
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_wallet_id ON wallet_transactions(wallet_id);
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_transaction_hash ON wallet_transactions(transaction_hash);

-- Wallet balances
CREATE TABLE IF NOT EXISTS wallet_balances (
    id SERIAL PRIMARY KEY,
    wallet_id INTEGER NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
    token_address VARCHAR(42),  -- NULL for native token (BNB)
    token_symbol VARCHAR(20) NOT NULL,
    balance NUMERIC(28, 18) NOT NULL DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(wallet_id, token_address)
);

-- Index for faster balance lookups
CREATE INDEX IF NOT EXISTS idx_wallet_balances_wallet_id ON wallet_balances(wallet_id);

-- Multi-signature wallets
CREATE TABLE IF NOT EXISTS multisig_wallets (
    id SERIAL PRIMARY KEY,
    wallet_id INTEGER NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
    contract_address VARCHAR(42) NOT NULL,
    threshold INTEGER NOT NULL,  -- Number of signatures required
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(wallet_id)
);

-- Multi-signature signers
CREATE TABLE IF NOT EXISTS multisig_signers (
    id SERIAL PRIMARY KEY,
    multisig_id INTEGER NOT NULL REFERENCES multisig_wallets(id) ON DELETE CASCADE,
    signer_address VARCHAR(42) NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(multisig_id, signer_address)
);

-- Pending withdrawal requests
CREATE TABLE IF NOT EXISTS withdrawal_requests (
    id SERIAL PRIMARY KEY,
    wallet_id INTEGER NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
    to_address VARCHAR(42) NOT NULL,
    token_address VARCHAR(42),  -- NULL for native token (BNB)
    amount NUMERIC(28, 18) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'approved', 'rejected', 'completed', 'failed')),
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Withdrawal approvals (for multi-signature)
CREATE TABLE IF NOT EXISTS withdrawal_approvals (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES withdrawal_requests(id) ON DELETE CASCADE,
    approver_address VARCHAR(42) NOT NULL,
    approved BOOLEAN NOT NULL,
    signature TEXT,  -- Transaction signature
    approved_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(request_id, approver_address)
);

-- Trigger to update the updated_at timestamp on wallets
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = CURRENT_TIMESTAMP;
   RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_wallets_updated_at
    BEFORE UPDATE ON wallets
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column(); 