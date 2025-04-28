# Secure Withdrawal Processing System

This document describes the secure withdrawal processing system for BEP20 token withdrawals from the Forex Trading platform. The system is designed with multiple layers of security to protect user funds and prevent unauthorized withdrawals.

## Table of Contents
1. [Overview](#overview)
2. [Security Features](#security-features)
3. [Withdrawal Process Workflow](#withdrawal-process-workflow)
4. [Multi-Factor Authentication](#multi-factor-authentication)
5. [Multi-Signature Approvals](#multi-signature-approvals)
6. [Withdrawal Limits and Velocity Checks](#withdrawal-limits-and-velocity-checks)
7. [Hot Wallet Management](#hot-wallet-management)
8. [Monitoring and Alerts](#monitoring-and-alerts)
9. [API Endpoints](#api-endpoints)
10. [Database Schema](#database-schema)
11. [Testing](#testing)
12. [Troubleshooting](#troubleshooting)

## Overview

The secure withdrawal system enables users to withdraw BEP20 tokens (including BNB) from their wallets on the platform. It includes multiple security layers to protect user funds, prevent fraud, and ensure compliance with security best practices.

Key components of the system include:
- Multi-factor authentication (MFA) for withdrawal requests
- Multi-signature approvals for large withdrawals
- Withdrawal limits based on user tier
- Velocity checks to detect suspicious patterns
- Hot wallet monitoring and management
- Security alerts and notifications

## Security Features

### Authentication and Authorization
- **User Authentication**: All withdrawal requests require user authentication
- **Multi-Factor Authentication (MFA)**: Required for all withdrawal requests
- **Session Validation**: Ensure the user's session is valid and not expired
- **IP Address Verification**: Check for suspicious IP address changes

### Fraud Prevention
- **Withdrawal Limits**: Per-transaction, daily, weekly, and monthly limits
- **Velocity Checks**: Monitor withdrawal frequency and amount patterns
- **Device Fingerprinting**: Track user devices for suspicious changes
- **Risk Scoring**: Calculate risk scores based on multiple factors

### Operational Security
- **Multi-Signature Wallets**: Large withdrawals require multiple approvals
- **Hot Wallet Management**: Monitor and manage hot wallet balances
- **Cold Storage Segregation**: Majority of funds kept in cold storage
- **Encrypted Private Keys**: Wallet private keys are encrypted at rest

### Monitoring and Alerts
- **Real-time Monitoring**: Continuous monitoring of withdrawal activity
- **Security Alerts**: Immediate alerts for suspicious activity
- **Audit Logging**: Comprehensive logging of all withdrawal actions
- **Balance Reconciliation**: Regular reconciliation of balances

## Withdrawal Process Workflow

The withdrawal process follows this general workflow:

1. **Withdrawal Request**
   - User authenticates to the platform
   - User creates a withdrawal request specifying:
     - Source wallet (must be owned by the user)
     - Destination address
     - Token and amount
   - System validates the request against:
     - User's available balance
     - Withdrawal limits
     - Cooldown periods

2. **Security Verification**
   - User completes MFA verification
   - System performs security checks:
     - Velocity checks
     - IP and device verification
     - Risk scoring

3. **Approval Process**
   - For standard withdrawals (below threshold):
     - Automated approval if all checks pass
   - For large withdrawals (above threshold):
     - Multi-signature approval workflow initiated
     - Required approvers notified
     - Each approver verifies and approves/rejects

4. **Execution**
   - Approved withdrawals are queued for processing
   - Hot wallet ensures sufficient balance
   - Transaction is broadcast to the blockchain
   - Transaction hash and status are recorded

5. **Confirmation and Notification**
   - System monitors transaction confirmations
   - User is notified of withdrawal status changes
   - Final confirmation once transaction is settled

## Multi-Factor Authentication

The system supports multiple MFA methods to secure withdrawal requests:

### TOTP Authentication
- Time-based One-Time Password (TOTP) via apps like Google Authenticator
- QR code for easy setup
- Backup codes provided for account recovery

### Setup Process
1. User initiates MFA setup
2. System generates a secret key and QR code
3. User scans the QR code with their authenticator app
4. User verifies setup by entering a code from their app
5. System provides backup codes for the user to save

### Verification Process
1. User initiates a withdrawal request
2. System prompts for the current TOTP code
3. User enters the code from their authenticator app
4. System verifies the code validity
5. If valid, the withdrawal process continues

### Backup Codes
- 10 one-time use backup codes are generated
- Used when user loses access to their authenticator app
- Each code can only be used once
- Codes can be regenerated (invalidating existing ones)

## Multi-Signature Approvals

Large withdrawals (above configured thresholds) require multiple approvals:

### Approval Workflow
1. Withdrawal request is created and marked as pending
2. Required approvers are notified
3. Each approver reviews the request details
4. Approvers authenticate and provide their signature
5. Once the threshold of approvals is reached, withdrawal is marked as approved
6. If any approver rejects, the withdrawal is marked as rejected

### Approval Thresholds
- Standard withdrawals: Automated approval
- Medium withdrawals (10-100 BNB): 2 approvals
- Large withdrawals (>100 BNB): 3 approvals
- Threshold values are configurable

### Stale Approval Monitoring
- Approval requests older than 3 days are flagged
- Notifications are sent for stale approvals
- Stale approvals can be escalated to administrators

## Withdrawal Limits and Velocity Checks

The system implements limits and velocity checks to prevent fraud:

### User Tiers and Limits
- **Basic**: Lower limits for new users
  - Per transaction: 500 USD
  - Daily: 1,000 USD
  - Weekly: 5,000 USD
  - Monthly: 20,000 USD
- **Verified**: Medium limits for verified users
  - Per transaction: 2,000 USD
  - Daily: 5,000 USD
  - Weekly: 20,000 USD
  - Monthly: 50,000 USD
- **Premium**: Higher limits for premium users
  - Per transaction: 10,000 USD
  - Daily: 20,000 USD
  - Weekly: 50,000 USD
  - Monthly: 100,000 USD

### Velocity Checks
- **Time Windows**: 1 hour, 24 hours, 7 days
- **Historical Comparison**: Compare current activity to user's historical patterns
- **Alert Levels**:
  - Medium: 1.5x normal activity
  - High: 3.0x normal activity
- **Risk Factors**:
  - Withdrawal frequency
  - Total withdrawal amount
  - New destination addresses
  - New IP addresses or devices

## Hot Wallet Management

The system includes tools for secure hot wallet management:

### Balance Monitoring
- Regular checking of hot wallet balances
- Alerts for low balances that need replenishment
- Alerts for high balances that should be moved to cold storage

### Threshold Configuration
- Low balance threshold (default: 0.1 BNB)
- High balance threshold (default: 1.0 BNB)
- Token-specific thresholds can be configured

### Replenishment Process
- Low balance alerts trigger replenishment workflow
- Cold storage to hot wallet transfers require multi-signature approval
- Only enough funds for near-term withdrawals are kept in hot wallets

### Security Measures
- Private keys are encrypted at rest
- Hot wallets are monitored for unauthorized transactions
- Unusual balance changes trigger immediate alerts

## Monitoring and Alerts

The system includes comprehensive monitoring and alerting:

### Monitoring Components
- Hot wallet balances
- Withdrawal requests status
- Approval queues
- Transaction confirmations
- Security alerts

### Alert Types
- **Security Alerts**: Suspicious activity detection
- **Operational Alerts**: Process failures or delays
- **Balance Alerts**: Low or high balances
- **Stale Request Alerts**: Pending requests or approvals

### Notification Channels
- Email notifications for administrators
- Dashboard alerts for operators
- API webhooks for system integration

## API Endpoints

The withdrawal system exposes the following API endpoints:

### Withdrawal Management
- `POST /api/withdrawal/request` - Create a new withdrawal request
- `GET /api/withdrawal/request/:id` - Get withdrawal request details
- `GET /api/withdrawal/user` - Get user's withdrawal requests
- `GET /api/withdrawal/pending` - Get pending withdrawal requests (admin)

### Approval Management
- `POST /api/withdrawal/approve/:id` - Approve a withdrawal request
- `POST /api/withdrawal/reject/:id` - Reject a withdrawal request
- `POST /api/withdrawal/process` - Process approved withdrawals (admin)

### MFA Management
- `GET /api/mfa/status` - Get MFA status
- `POST /api/mfa/setup` - Set up MFA
- `GET /api/mfa/qrcode` - Get QR code for TOTP setup
- `POST /api/mfa/verify` - Verify an MFA code
- `POST /api/mfa/disable` - Disable MFA
- `POST /api/mfa/backup-codes` - Generate new backup codes

## Database Schema

The withdrawal system uses the following database tables:

### Core Tables
- `wallets` - User wallet information
- `withdrawal_requests` - Withdrawal request details
- `withdrawal_approvals` - Approval records for withdrawals
- `wallet_transactions` - Transaction history

### Security Tables
- `security_alerts` - Security alert records
- `user_auth_events` - Authentication event history
- `withdrawal_verifications` - MFA verification records
- `ip_whitelist` - Whitelisted IP addresses
- `mfa_backup_codes` - MFA backup codes

## Testing

The withdrawal system includes comprehensive testing:

### Unit Tests
- Test individual components in isolation
- Mock external dependencies
- Verify business logic correctness

### Integration Tests
- Test component interactions
- Verify end-to-end workflows
- Test database interactions

### Security Tests
- Penetration testing of API endpoints
- Authentication and authorization testing
- Limit and velocity check testing

### Test Environment
- Testnet for blockchain interactions
- Simulated multi-signature wallets
- Test admin accounts for approval workflows

## Troubleshooting

Common issues and their resolutions:

### Withdrawal Stuck in Pending
- Check for missing approvals
- Verify MFA completion
- Check for security flags

### Failed Transactions
- Check hot wallet balance
- Verify gas price settings
- Check blockchain network status

### MFA Issues
- Time synchronization problems
- Backup code usage
- Recovery process

### Balance Discrepancies
- Reconciliation process
- Transaction hash verification
- Manual balance adjustment process 