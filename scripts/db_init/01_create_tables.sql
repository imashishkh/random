-- Create extension for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable TimescaleDB extension for time-series data
-- CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create schema for trading data
CREATE SCHEMA IF NOT EXISTS trading;

-- Table for storing market data
CREATE TABLE IF NOT EXISTS trading.market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open DECIMAL(20, 8) NOT NULL,
    high DECIMAL(20, 8) NOT NULL,
    low DECIMAL(20, 8) NOT NULL,
    close DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(30, 8) NOT NULL,
    timeframe VARCHAR(10) NOT NULL, -- e.g., '1m', '5m', '1h', '1d'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create index on the market_data table
CREATE INDEX IF NOT EXISTS idx_market_data_symbol_timestamp ON trading.market_data (symbol, timestamp);
CREATE INDEX IF NOT EXISTS idx_market_data_timeframe ON trading.market_data (timeframe);

-- Create hypertable for time-series data (commented out as TimescaleDB not used yet)
-- SELECT create_hypertable('trading.market_data', 'timestamp', chunk_time_interval => INTERVAL '1 day');

-- Table for trading accounts
CREATE TABLE IF NOT EXISTS trading.accounts (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(100) NOT NULL UNIQUE,
    account_name VARCHAR(100) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    api_key_id UUID NOT NULL, -- References the API key in the secure vault
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table for balances
CREATE TABLE IF NOT EXISTS trading.balances (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES trading.accounts(id),
    asset VARCHAR(20) NOT NULL,
    free DECIMAL(30, 8) NOT NULL DEFAULT 0,
    locked DECIMAL(30, 8) NOT NULL DEFAULT 0,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(account_id, asset, timestamp)
);

-- Table for trading strategies
CREATE TABLE IF NOT EXISTS trading.strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table for trading signals
CREATE TABLE IF NOT EXISTS trading.signals (
    id SERIAL PRIMARY KEY,
    strategy_id INTEGER NOT NULL REFERENCES trading.strategies(id),
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    signal_type VARCHAR(20) NOT NULL, -- 'buy', 'sell', 'close'
    entry_price DECIMAL(20, 8) NULL,
    stop_loss DECIMAL(20, 8) NULL,
    take_profit DECIMAL(20, 8) NULL,
    risk_reward_ratio DECIMAL(10, 2) NULL,
    confidence DECIMAL(5, 2) NULL, -- 0-1 scale
    signal_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_executed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_symbol_created_at ON trading.signals (symbol, created_at);
CREATE INDEX IF NOT EXISTS idx_signals_strategy ON trading.signals (strategy_id);

-- Table for orders
CREATE TABLE IF NOT EXISTS trading.orders (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES trading.accounts(id),
    signal_id INTEGER REFERENCES trading.signals(id),
    exchange_order_id VARCHAR(100) NULL,
    symbol VARCHAR(20) NOT NULL,
    order_type VARCHAR(20) NOT NULL, -- 'market', 'limit', 'stop_loss', etc.
    side VARCHAR(10) NOT NULL, -- 'buy', 'sell'
    status VARCHAR(20) NOT NULL, -- 'new', 'filled', 'canceled', 'rejected', etc.
    quantity DECIMAL(30, 8) NOT NULL,
    price DECIMAL(20, 8) NULL,
    executed_price DECIMAL(20, 8) NULL,
    order_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_account_symbol ON trading.orders (account_id, symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON trading.orders (status);

-- Table for trading positions
CREATE TABLE IF NOT EXISTS trading.positions (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES trading.accounts(id),
    strategy_id INTEGER REFERENCES trading.strategies(id),
    symbol VARCHAR(20) NOT NULL,
    position_size DECIMAL(30, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8) NOT NULL,
    stop_loss DECIMAL(20, 8) NULL,
    take_profit DECIMAL(20, 8) NULL,
    unrealized_pnl DECIMAL(30, 8) NOT NULL DEFAULT 0,
    realized_pnl DECIMAL(30, 8) NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL, -- 'open', 'closed'
    open_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    close_time TIMESTAMPTZ NULL,
    position_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_positions_account_symbol ON trading.positions (account_id, symbol);
CREATE INDEX IF NOT EXISTS idx_positions_status ON trading.positions (status);

-- Table for performance metrics
CREATE TABLE IF NOT EXISTS trading.performance (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES trading.accounts(id),
    strategy_id INTEGER REFERENCES trading.strategies(id),
    symbol VARCHAR(20) NULL, -- NULL for overall performance
    timeframe VARCHAR(10) NULL, -- NULL for overall performance
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    num_trades INTEGER NOT NULL DEFAULT 0,
    win_rate DECIMAL(5, 2) NULL, -- Percentage
    profit_factor DECIMAL(10, 2) NULL,
    sharpe_ratio DECIMAL(10, 2) NULL,
    max_drawdown DECIMAL(10, 2) NULL, -- Percentage
    total_pnl DECIMAL(30, 8) NOT NULL DEFAULT 0,
    metrics_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table for agent states
CREATE TABLE IF NOT EXISTS trading.agent_states (
    id SERIAL PRIMARY KEY,
    agent_id VARCHAR(100) NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    state JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(agent_id)
);

-- Table for API keys (encrypted)
CREATE TABLE IF NOT EXISTS trading.api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    encrypted_key TEXT NOT NULL,
    encrypted_secret TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    permissions JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create audit schema for logging
CREATE SCHEMA IF NOT EXISTS audit;

-- Audit log table
CREATE TABLE IF NOT EXISTS audit.system_logs (
    id SERIAL PRIMARY KEY,
    log_level VARCHAR(20) NOT NULL,
    component VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create index on log_level and component
CREATE INDEX IF NOT EXISTS idx_system_logs_level_component ON audit.system_logs (log_level, component);
CREATE INDEX IF NOT EXISTS idx_system_logs_created_at ON audit.system_logs (created_at);

-- Function to update timestamps
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for timestamp updates
CREATE TRIGGER update_accounts_timestamp
BEFORE UPDATE ON trading.accounts
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_strategies_timestamp
BEFORE UPDATE ON trading.strategies
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_signals_timestamp
BEFORE UPDATE ON trading.signals
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_orders_timestamp
BEFORE UPDATE ON trading.orders
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_positions_timestamp
BEFORE UPDATE ON trading.positions
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_agent_states_timestamp
BEFORE UPDATE ON trading.agent_states
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER update_api_keys_timestamp
BEFORE UPDATE ON trading.api_keys
FOR EACH ROW EXECUTE FUNCTION update_timestamp(); 