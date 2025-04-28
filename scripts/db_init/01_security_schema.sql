-- Initialize security schema for the Forex Trading AI System
-- This script creates the necessary tables and indexes for security features

-- Create security schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS security;

-- Create API keys table
CREATE TABLE IF NOT EXISTS security.api_keys (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    key_prefix VARCHAR(50) NOT NULL,
    hashed_key TEXT NOT NULL,
    encrypted_key TEXT,
    owner_id INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_used_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    scopes JSONB NOT NULL DEFAULT '[]'::JSONB,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
);

-- Create unique index on key_prefix
CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_prefix ON security.api_keys(key_prefix);

-- Create index on owner_id for quick lookups
CREATE INDEX IF NOT EXISTS idx_api_keys_owner ON security.api_keys(owner_id);

-- Create index on is_active for filtering active keys
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON security.api_keys(is_active);

-- Create audit log table for security events
CREATE TABLE IF NOT EXISTS security.audit_log (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    actor_id INTEGER,
    actor_type VARCHAR(50),
    ip_address VARCHAR(50),
    event_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),
    action VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    details JSONB
);

-- Create index on event_time for efficient querying
CREATE INDEX IF NOT EXISTS idx_audit_event_time ON security.audit_log(event_time);

-- Create index on actor_id for user activity tracking
CREATE INDEX IF NOT EXISTS idx_audit_actor ON security.audit_log(actor_id);

-- Create combined index for specific queries
CREATE INDEX IF NOT EXISTS idx_audit_resource ON security.audit_log(resource_type, resource_id);

-- Create IP whitelist table
CREATE TABLE IF NOT EXISTS security.ip_whitelist (
    id SERIAL PRIMARY KEY,
    ip_address VARCHAR(50) NOT NULL,
    description VARCHAR(255),
    added_by INTEGER,
    added_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- Create unique index on ip_address
CREATE UNIQUE INDEX IF NOT EXISTS idx_ip_whitelist_address ON security.ip_whitelist(ip_address);

-- Comments for tables
COMMENT ON TABLE security.api_keys IS 'API keys for application authentication';
COMMENT ON TABLE security.audit_log IS 'Audit log for security-related events';
COMMENT ON TABLE security.ip_whitelist IS 'Whitelist of allowed IP addresses';

-- Grant appropriate permissions to application role
-- Replace 'forex_app' with your application's database role
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_catalog.pg_roles
        WHERE rolname = 'forex_app'
    ) THEN
        GRANT USAGE ON SCHEMA security TO forex_app;
        GRANT SELECT, INSERT, UPDATE ON security.api_keys TO forex_app;
        GRANT SELECT, INSERT ON security.audit_log TO forex_app;
        GRANT SELECT ON security.ip_whitelist TO forex_app;
        
        -- Grant sequence usage for ID generation
        GRANT USAGE, SELECT ON SEQUENCE security.api_keys_id_seq TO forex_app;
        GRANT USAGE, SELECT ON SEQUENCE security.audit_log_id_seq TO forex_app;
    END IF;
END
$$; 