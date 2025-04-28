-- Accounting and Reconciliation Database Schema
-- This schema establishes the tables needed for double-entry accounting and balance reconciliation

-- Chart of accounts
CREATE TABLE IF NOT EXISTS accounting_accounts (
    id SERIAL PRIMARY KEY,
    account_code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    account_type VARCHAR(20) NOT NULL CHECK (account_type IN ('asset', 'liability', 'equity', 'income', 'expense')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Journal entries (transactions)
CREATE TABLE IF NOT EXISTS accounting_journal_entries (
    id SERIAL PRIMARY KEY,
    entry_date DATE NOT NULL,
    reference VARCHAR(100),
    memo TEXT,
    created_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Line items for journal entries
CREATE TABLE IF NOT EXISTS accounting_line_items (
    id SERIAL PRIMARY KEY,
    journal_entry_id INTEGER NOT NULL REFERENCES accounting_journal_entries(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounting_accounts(id),
    description TEXT,
    debit NUMERIC(28, 18) DEFAULT 0,
    credit NUMERIC(28, 18) DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Fund transfers to Binance
CREATE TABLE IF NOT EXISTS fund_transfers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    wallet_id INTEGER NOT NULL REFERENCES wallets(id),
    amount NUMERIC(28, 18) NOT NULL,
    token_symbol VARCHAR(20) NOT NULL,
    binance_transaction_id VARCHAR(100),
    blockchain_tx_hash VARCHAR(66),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Reconciliation records
CREATE TABLE IF NOT EXISTS balance_reconciliations (
    id SERIAL PRIMARY KEY,
    reconciliation_date TIMESTAMP WITH TIME ZONE NOT NULL,
    wallet_id INTEGER NOT NULL REFERENCES wallets(id),
    token_symbol VARCHAR(20) NOT NULL,
    internal_balance NUMERIC(28, 18) NOT NULL,
    blockchain_balance NUMERIC(28, 18) NOT NULL,
    exchange_balance NUMERIC(28, 18),
    blockchain_discrepancy NUMERIC(28, 18),
    exchange_discrepancy NUMERIC(28, 18),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('matched', 'discrepancy', 'pending', 'resolved')),
    resolved_by VARCHAR(100),
    resolution_notes TEXT,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_accounting_journal_entries_date ON accounting_journal_entries(entry_date);
CREATE INDEX IF NOT EXISTS idx_accounting_journal_entries_reference ON accounting_journal_entries(reference);
CREATE INDEX IF NOT EXISTS idx_accounting_line_items_journal_entry_id ON accounting_line_items(journal_entry_id);
CREATE INDEX IF NOT EXISTS idx_accounting_line_items_account_id ON accounting_line_items(account_id);
CREATE INDEX IF NOT EXISTS idx_fund_transfers_user_id ON fund_transfers(user_id);
CREATE INDEX IF NOT EXISTS idx_fund_transfers_wallet_id ON fund_transfers(wallet_id);
CREATE INDEX IF NOT EXISTS idx_fund_transfers_blockchain_tx_hash ON fund_transfers(blockchain_tx_hash);
CREATE INDEX IF NOT EXISTS idx_balance_reconciliations_wallet_id ON balance_reconciliations(wallet_id);
CREATE INDEX IF NOT EXISTS idx_balance_reconciliations_date ON balance_reconciliations(reconciliation_date);
CREATE INDEX IF NOT EXISTS idx_balance_reconciliations_status ON balance_reconciliations(status);

-- Default accounts for the accounting system
INSERT INTO accounting_accounts (account_code, name, account_type)
VALUES 
    ('ASSET-BNB', 'BNB Asset', 'asset'),
    ('ASSET-BUSD', 'BUSD Asset', 'asset'),
    ('ASSET-USDT', 'USDT Asset', 'asset'),
    ('BINANCE-BNB', 'Binance BNB', 'asset'),
    ('BINANCE-BUSD', 'Binance BUSD', 'asset'),
    ('BINANCE-USDT', 'Binance USDT', 'asset'),
    ('DEPOSIT-INCOME-BNB', 'BNB Deposit Income', 'income'),
    ('DEPOSIT-INCOME-BUSD', 'BUSD Deposit Income', 'income'),
    ('DEPOSIT-INCOME-USDT', 'USDT Deposit Income', 'income'),
    ('WITHDRAWAL-EXPENSE-BNB', 'BNB Withdrawal Expense', 'expense'),
    ('WITHDRAWAL-EXPENSE-BUSD', 'BUSD Withdrawal Expense', 'expense'),
    ('WITHDRAWAL-EXPENSE-USDT', 'USDT Withdrawal Expense', 'expense'),
    ('FEE-EXPENSE', 'Transaction Fee Expense', 'expense')
ON CONFLICT (account_code) DO NOTHING;

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = CURRENT_TIMESTAMP;
   RETURN NEW;
END;
$$ language 'plpgsql';

-- Add triggers to tables
CREATE TRIGGER update_accounting_accounts_updated_at
    BEFORE UPDATE ON accounting_accounts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_accounting_journal_entries_updated_at
    BEFORE UPDATE ON accounting_journal_entries
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_fund_transfers_updated_at
    BEFORE UPDATE ON fund_transfers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column(); 