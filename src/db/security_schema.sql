-- Security database schema for withdrawal system

-- Security alerts for suspicious activities
CREATE TABLE IF NOT EXISTS security_alerts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,  -- Type of alert (e.g., withdrawal_velocity, login_attempt)
    details JSONB NOT NULL,  -- Detailed information about the alert
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_by VARCHAR(255),
    resolution_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_security_alerts_user_id ON security_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_security_alerts_alert_type ON security_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_security_alerts_is_resolved ON security_alerts(is_resolved);

-- User authentication events
CREATE TABLE IF NOT EXISTS user_auth_events (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,  -- Type of event (e.g., login, logout, password_change)
    ip_address VARCHAR(45),  -- IPv4 or IPv6 address
    device_id VARCHAR(255),  -- Unique device identifier
    device_info JSONB,  -- Device information (browser, OS, etc.)
    location JSONB,  -- Location data (city, country, etc.)
    is_successful BOOLEAN DEFAULT TRUE,
    failed_reason VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_user_auth_events_user_id ON user_auth_events(user_id);
CREATE INDEX IF NOT EXISTS idx_user_auth_events_ip_address ON user_auth_events(ip_address);
CREATE INDEX IF NOT EXISTS idx_user_auth_events_device_id ON user_auth_events(device_id);
CREATE INDEX IF NOT EXISTS idx_user_auth_events_created_at ON user_auth_events(created_at);

-- Withdrawal verifications
CREATE TABLE IF NOT EXISTS withdrawal_verifications (
    id SERIAL PRIMARY KEY,
    withdrawal_request_id INTEGER NOT NULL REFERENCES withdrawal_requests(id) ON DELETE CASCADE,
    verification_type VARCHAR(50) NOT NULL,  -- Type of verification (e.g., email, sms, totp)
    verification_code VARCHAR(255),  -- Verification code (if applicable)
    expiration_time TIMESTAMP WITH TIME ZONE,
    is_verified BOOLEAN DEFAULT FALSE,
    verification_time TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_withdrawal_verifications_request_id ON withdrawal_verifications(withdrawal_request_id);

-- IP whitelist for administrative actions
CREATE TABLE IF NOT EXISTS ip_whitelist (
    id SERIAL PRIMARY KEY,
    ip_address VARCHAR(45) NOT NULL,
    cidr_range VARCHAR(45),  -- CIDR notation for IP range
    description VARCHAR(255),
    added_by VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ip_address)
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_ip_whitelist_ip_address ON ip_whitelist(ip_address);

-- Additional fields for users table
-- Note: This assumes the users table already exists
ALTER TABLE users ADD COLUMN IF NOT EXISTS tier VARCHAR(20) DEFAULT 'basic';
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS withdrawal_limit_daily DECIMAL(28, 18);
ALTER TABLE users ADD COLUMN IF NOT EXISTS withdrawal_limit_weekly DECIMAL(28, 18);
ALTER TABLE users ADD COLUMN IF NOT EXISTS withdrawal_limit_monthly DECIMAL(28, 18);
ALTER TABLE users ADD COLUMN IF NOT EXISTS withdrawal_limit_per_tx DECIMAL(28, 18);
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_withdrawal_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_type VARCHAR(20);  -- 'totp', 'sms', etc.
ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_secret TEXT;

-- MFA backup codes
CREATE TABLE IF NOT EXISTS mfa_backup_codes (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    code VARCHAR(20) NOT NULL,
    is_used BOOLEAN DEFAULT FALSE,
    used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, code)
);

-- Trigger to update the updated_at timestamp on ip_whitelist
CREATE OR REPLACE FUNCTION update_updated_at_column_ip_whitelist()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = CURRENT_TIMESTAMP;
   RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_ip_whitelist_updated_at
    BEFORE UPDATE ON ip_whitelist
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column_ip_whitelist(); 