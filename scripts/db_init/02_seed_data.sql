-- Insert sample trading strategies
INSERT INTO trading.strategies (name, description, parameters, is_active)
VALUES 
    ('Moving Average Crossover', 'Simple strategy based on crossover of fast and slow moving averages', 
     '{"fast_period": 10, "slow_period": 50, "timeframe": "1h"}'::jsonb, TRUE),
    ('RSI Oversold/Overbought', 'Strategy based on RSI indicator for oversold and overbought conditions', 
     '{"rsi_period": 14, "oversold_threshold": 30, "overbought_threshold": 70, "timeframe": "4h"}'::jsonb, TRUE),
    ('Bollinger Bands Bounce', 'Strategy using Bollinger Bands for mean reversion trading', 
     '{"bb_period": 20, "bb_std_dev": 2, "timeframe": "1h"}'::jsonb, TRUE);

-- Insert sample symbols
WITH symbols AS (
    SELECT 'EUR/USDT' as symbol UNION ALL
    SELECT 'GBP/USDT' UNION ALL
    SELECT 'CAD/USDT' UNION ALL
    SELECT 'JPY/USDT' UNION ALL
    SELECT 'AUD/USDT'
)
-- No action needed with the symbols yet, but we can use them later for market data or signal generation

-- Create a sample account with placeholder API key reference
INSERT INTO trading.api_keys (name, exchange, encrypted_key, encrypted_secret, permissions)
VALUES ('Test Account Key', 'binance', 'ENCRYPTED_KEY_PLACEHOLDER', 'ENCRYPTED_SECRET_PLACEHOLDER', 
       '{"trading": true, "viewOnly": true}'::jsonb);

INSERT INTO trading.accounts (account_id, account_name, exchange, api_key_id)
SELECT 'test-account-001', 'Test Trading Account', 'binance', id
FROM trading.api_keys
LIMIT 1;

-- Add some sample balances
INSERT INTO trading.balances (account_id, asset, free, locked, timestamp)
SELECT 
    (SELECT id FROM trading.accounts LIMIT 1),
    asset,
    amount,
    0,
    NOW()
FROM (
    VALUES
        ('USDT', 10000.00),
        ('BTC', 0.15),
        ('ETH', 2.5)
) AS assets(asset, amount);

-- Add sample agent states
INSERT INTO trading.agent_states (agent_id, agent_type, state)
VALUES
    ('data-collector-agent', 'DataCollector', '{"status": "idle", "last_run": null, "targets": ["EUR/USDT", "GBP/USDT"]}'::jsonb),
    ('analysis-agent', 'MarketAnalysis', '{"status": "idle", "active_indicators": ["RSI", "MACD", "BB"]}'::jsonb),
    ('trading-agent', 'TradingExecutor', '{"status": "idle", "position_limit": 5, "risk_per_trade": 1.0}'::jsonb);

-- Insert sample log entries
INSERT INTO audit.system_logs (log_level, component, message, data)
VALUES
    ('INFO', 'system', 'System initialization complete', NULL),
    ('INFO', 'database', 'Database schema created successfully', '{"version": "1.0.0"}'::jsonb),
    ('INFO', 'trading_engine', 'Trading engine started', '{"timestamp": "' || NOW()::text || '"}'::jsonb); 