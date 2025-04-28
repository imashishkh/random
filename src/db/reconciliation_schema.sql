-- Reconciliation System Database Schema
-- Contains tables for tracking accounting entries, reconciliation reports, and fund transfers

-- Function to update timestamp
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = NOW();
   RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Table for tracking all accounting entries
CREATE TABLE IF NOT EXISTS accounting_entries (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    entry_type VARCHAR(50) NOT NULL, -- 'deposit', 'withdrawal', 'fee', 'transfer'
    amount NUMERIC(24, 8) NOT NULL,
    fee NUMERIC(24, 8) DEFAULT 0,
    token_symbol VARCHAR(10) NOT NULL,
    tx_hash VARCHAR(66),  -- Blockchain transaction hash if applicable
    wallet_id INTEGER,    -- Reference to user wallet if applicable
    binance_order_id VARCHAR(100), -- Binance order ID if applicable
    notes TEXT,
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'completed', 'failed'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Table for reconciliation reports
CREATE TABLE IF NOT EXISTS reconciliation_reports (
    id SERIAL PRIMARY KEY,
    wallet_id INTEGER,
    user_id INTEGER,
    token_symbol VARCHAR(10) NOT NULL,
    blockchain_balance NUMERIC(24, 8),
    internal_balance NUMERIC(24, 8),
    binance_balance NUMERIC(24, 8),
    discrepancy_amount NUMERIC(24, 8),
    discrepancy_status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'resolved', 'investigating'
    severity VARCHAR(10) DEFAULT 'low', -- 'low', 'medium', 'high', 'critical'
    resolution_notes TEXT,
    resolved_by VARCHAR(100),
    reconciliation_date TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Table for fund transfers to/from Binance
CREATE TABLE IF NOT EXISTS fund_transfers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    wallet_id INTEGER,
    amount NUMERIC(24, 8) NOT NULL,
    fee NUMERIC(24, 8) DEFAULT 0,
    token_symbol VARCHAR(10) NOT NULL,
    blockchain_tx_hash VARCHAR(66), -- Blockchain transaction hash
    binance_tx_id VARCHAR(100),     -- Binance transaction ID
    transfer_type VARCHAR(20) NOT NULL, -- 'to_binance', 'from_binance'
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'completed', 'failed'
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    last_retry_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for accounting_entries
CREATE INDEX idx_accounting_entries_user_id ON accounting_entries(user_id);
CREATE INDEX idx_accounting_entries_entry_type ON accounting_entries(entry_type);
CREATE INDEX idx_accounting_entries_token_symbol ON accounting_entries(token_symbol);
CREATE INDEX idx_accounting_entries_created_at ON accounting_entries(created_at);
CREATE INDEX idx_accounting_entries_tx_hash ON accounting_entries(tx_hash);
CREATE INDEX idx_accounting_entries_binance_order_id ON accounting_entries(binance_order_id);

-- Indexes for reconciliation_reports
CREATE INDEX idx_reconciliation_reports_user_id ON reconciliation_reports(user_id);
CREATE INDEX idx_reconciliation_reports_token_symbol ON reconciliation_reports(token_symbol);
CREATE INDEX idx_reconciliation_reports_discrepancy_status ON reconciliation_reports(discrepancy_status);
CREATE INDEX idx_reconciliation_reports_severity ON reconciliation_reports(severity);
CREATE INDEX idx_reconciliation_reports_reconciliation_date ON reconciliation_reports(reconciliation_date);

-- Indexes for fund_transfers
CREATE INDEX idx_fund_transfers_user_id ON fund_transfers(user_id);
CREATE INDEX idx_fund_transfers_token_symbol ON fund_transfers(token_symbol);
CREATE INDEX idx_fund_transfers_status ON fund_transfers(status);
CREATE INDEX idx_fund_transfers_transfer_type ON fund_transfers(transfer_type);
CREATE INDEX idx_fund_transfers_created_at ON fund_transfers(created_at);
CREATE INDEX idx_fund_transfers_blockchain_tx_hash ON fund_transfers(blockchain_tx_hash);
CREATE INDEX idx_fund_transfers_binance_tx_id ON fund_transfers(binance_tx_id);

-- Triggers to update timestamps
CREATE TRIGGER update_accounting_entries_timestamp
BEFORE UPDATE ON accounting_entries
FOR EACH ROW
EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_reconciliation_reports_timestamp
BEFORE UPDATE ON reconciliation_reports
FOR EACH ROW
EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_fund_transfers_timestamp
BEFORE UPDATE ON fund_transfers
FOR EACH ROW
EXECUTE FUNCTION update_timestamp(); 