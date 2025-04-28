-- Trade Analytics Schema for Forex Trading Platform v4
-- Contains tables for tracking trades, positions, agent states, and risk alerts

-- Symbols reference table
CREATE TABLE IF NOT EXISTS symbols (
    symbol VARCHAR(20) PRIMARY KEY,
    base_asset VARCHAR(10) NOT NULL,      -- e.g., "BTC" in "BTCUSDT"
    quote_asset VARCHAR(10) NOT NULL,     -- e.g., "USDT" in "BTCUSDT"
    min_quantity NUMERIC(20, 8) NOT NULL, -- Minimum order size
    quantity_precision INT NOT NULL,      -- Decimal places for quantity
    price_precision INT NOT NULL,         -- Decimal places for price
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create index on assets for faster lookups
CREATE INDEX IF NOT EXISTS idx_symbols_assets ON symbols(base_asset, quote_asset);

-- Agent state tracking table
CREATE TABLE IF NOT EXISTS agent_states (
    id BIGSERIAL PRIMARY KEY,
    agent_id VARCHAR(36) NOT NULL UNIQUE, -- Unique identifier for the agent
    agent_name VARCHAR(100) NOT NULL,
    current_balance NUMERIC(20, 8) NOT NULL, -- Total balance including open positions
    available_balance NUMERIC(20, 8) NOT NULL, -- Free balance not in positions
    status VARCHAR(20) NOT NULL CHECK (status IN ('ACTIVE', 'PAUSED', 'STOPPED', 'ERROR')),
    last_heartbeat TIMESTAMPTZ NOT NULL,  -- Last time agent reported status
    configuration JSONB NOT NULL,         -- Flexible storage for agent config
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for agent_states
CREATE INDEX IF NOT EXISTS idx_agent_states_status ON agent_states(status);
CREATE INDEX IF NOT EXISTS idx_agent_states_last_heartbeat ON agent_states(last_heartbeat);
CREATE INDEX IF NOT EXISTS idx_agent_states_config ON agent_states USING GIN (configuration); -- JSONB index for querying config

-- Position tracking table
CREATE TABLE IF NOT EXISTS positions (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,     -- Current position size
    entry_price NUMERIC(20, 8) NOT NULL,  -- Average entry price
    current_price NUMERIC(20, 8) NOT NULL, -- Latest market price
    unrealized_pnl NUMERIC(20, 8) NOT NULL, -- Current unrealized P&L
    realized_pnl NUMERIC(20, 8) NOT NULL DEFAULT 0, -- Locked-in P&L from partial closes
    agent_id VARCHAR(36) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('OPEN', 'CLOSED', 'LIQUIDATED')),
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,               -- NULL for open positions
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_agent FOREIGN KEY (agent_id) REFERENCES agent_states(agent_id) ON DELETE CASCADE,
    CONSTRAINT fk_symbol FOREIGN KEY (symbol) REFERENCES symbols(symbol) ON DELETE RESTRICT
);

-- Indexes for positions
CREATE INDEX IF NOT EXISTS idx_positions_agent_id ON positions(agent_id);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_opened_at ON positions(opened_at);
-- Partial index for open positions (most commonly queried)
CREATE INDEX IF NOT EXISTS idx_positions_open ON positions(agent_id, symbol) WHERE status = 'OPEN';

-- Individual trade fills
CREATE TABLE IF NOT EXISTS trade_fills (
    id BIGSERIAL PRIMARY KEY,
    trade_id VARCHAR(50) NOT NULL,        -- Exchange-provided trade ID
    symbol VARCHAR(20) NOT NULL,          -- Trading pair (e.g., "BTCUSDT")
    price NUMERIC(20, 8) NOT NULL,        -- Execution price
    quantity NUMERIC(20, 8) NOT NULL,     -- Executed quantity
    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    executed_at TIMESTAMPTZ NOT NULL,
    fee NUMERIC(20, 8) NOT NULL,          -- Fee amount
    fee_asset VARCHAR(10) NOT NULL,       -- Fee currency
    order_id VARCHAR(50) NOT NULL,        -- Exchange-provided order ID
    agent_id VARCHAR(36) NOT NULL,        -- Reference to agent
    position_id BIGINT,                   -- Reference to position (can be NULL initially)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_position FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE SET NULL,
    CONSTRAINT fk_agent FOREIGN KEY (agent_id) REFERENCES agent_states(agent_id) ON DELETE CASCADE,
    CONSTRAINT fk_symbol FOREIGN KEY (symbol) REFERENCES symbols(symbol) ON DELETE RESTRICT
);

-- Indexes for trade_fills
CREATE INDEX IF NOT EXISTS idx_trade_fills_agent_id ON trade_fills(agent_id);
CREATE INDEX IF NOT EXISTS idx_trade_fills_position_id ON trade_fills(position_id);
CREATE INDEX IF NOT EXISTS idx_trade_fills_symbol_executed_at ON trade_fills(symbol, executed_at);
CREATE INDEX IF NOT EXISTS idx_trade_fills_trade_id ON trade_fills(trade_id);
-- Time-based index for efficient time range queries
CREATE INDEX IF NOT EXISTS idx_trade_fills_executed_at ON trade_fills(executed_at);

-- Risk alerting system
CREATE TABLE IF NOT EXISTS risk_alerts (
    id BIGSERIAL PRIMARY KEY,
    agent_id VARCHAR(36) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,      -- Type of alert (e.g., 'MARGIN_CALL', 'EXPOSURE_LIMIT')
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL', 'EMERGENCY')),
    message TEXT NOT NULL,                -- Detailed alert description
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,             -- When alert was resolved (NULL if unresolved)
    metadata JSONB,                      -- Additional context about the alert
    CONSTRAINT fk_agent FOREIGN KEY (agent_id) REFERENCES agent_states(agent_id) ON DELETE CASCADE
);

-- Indexes for risk_alerts
CREATE INDEX IF NOT EXISTS idx_risk_alerts_agent_id ON risk_alerts(agent_id);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_type_severity ON risk_alerts(alert_type, severity);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_resolved ON risk_alerts(resolved);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_triggered_at ON risk_alerts(triggered_at);

-- View for quickly getting agent performance metrics
CREATE OR REPLACE VIEW agent_performance AS
SELECT
    a.agent_id,
    a.agent_name,
    a.current_balance,
    a.available_balance,
    SUM(p.realized_pnl) AS total_realized_pnl,
    SUM(CASE WHEN p.status = 'OPEN' THEN p.unrealized_pnl ELSE 0 END) AS total_unrealized_pnl,
    COUNT(CASE WHEN p.status = 'OPEN' THEN 1 END) AS open_positions_count,
    COUNT(CASE WHEN p.status = 'CLOSED' THEN 1 END) AS closed_positions_count,
    AVG(CASE WHEN p.status = 'CLOSED' THEN p.realized_pnl ELSE NULL END) AS avg_position_pnl
FROM
    agent_states a
LEFT JOIN
    positions p ON a.agent_id = p.agent_id
GROUP BY
    a.agent_id, a.agent_name, a.current_balance, a.available_balance;

-- View for daily PnL aggregation
CREATE OR REPLACE VIEW daily_pnl AS
SELECT
    agent_id,
    DATE_TRUNC('day', closed_at) AS date,
    SUM(realized_pnl) AS daily_realized_pnl,
    COUNT(*) AS positions_closed
FROM
    positions
WHERE
    status = 'CLOSED'
    AND closed_at IS NOT NULL
GROUP BY
    agent_id, DATE_TRUNC('day', closed_at)
ORDER BY
    agent_id, date;

-- Function to update 'updated_at' timestamp automatically
CREATE OR REPLACE FUNCTION update_timestamp_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = NOW();
   RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for timestamp updates
CREATE TRIGGER update_agent_states_timestamp
    BEFORE UPDATE ON agent_states
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp_column();

CREATE TRIGGER update_positions_timestamp
    BEFORE UPDATE ON positions
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp_column();

CREATE TRIGGER update_symbols_timestamp
    BEFORE UPDATE ON symbols
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp_column();

-- Set up time-based partitioning for trade_fills table (runs monthly)
-- This will require pg_partman extension to be installed
-- COMMENT OUT if pg_partman is not available
/*
SELECT create_parent(
    'public.trade_fills',
    'executed_at',
    'time',
    'monthly',
    p_start_partition := date_trunc('month', CURRENT_DATE)::text
);

UPDATE part_config
SET retention = '12 months',
    retention_keep_table = false
WHERE parent_table = 'public.trade_fills';
*/

COMMENT ON TABLE symbols IS 'Reference data for trading symbols and pairs';
COMMENT ON TABLE agent_states IS 'Current state and configuration of trading agents';
COMMENT ON TABLE positions IS 'Open and closed trading positions with P&L tracking';
COMMENT ON TABLE trade_fills IS 'Individual trade execution fills from exchanges';
COMMENT ON TABLE risk_alerts IS 'Risk management alerts and notifications'; 