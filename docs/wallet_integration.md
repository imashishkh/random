# BEP20 Wallet Integration

This document provides a guide to using the BEP20 wallet integration module for the Forex Trading system.

## Overview

The BEP20 wallet integration allows the system to create and manage wallets on the Binance Smart Chain (BSC), enabling users to deposit and withdraw funds, check balances, and interact with BEP20 tokens.

## Features

- Create and manage BEP20-compatible wallets
- Secure private key encryption
- Deposit address generation and monitoring
- Secure withdrawal functionality
- Transaction verification and monitoring
- Balance reconciliation and accounting
- Multi-signature wallet support (future enhancement)

## Prerequisites

Before using the wallet integration, ensure:

1. Web3.py is installed (`pip install web3>=6.0.0`)
2. PostgreSQL database is configured
3. Environment variables are set (see Configuration section)
4. Database tables are initialized (see Setup section)

## Configuration

Add the following environment variables to your `.env` file:

```
# BEP20 Wallet Settings
WALLET_ENCRYPTION_KEY=your_wallet_encryption_key_here  # Generate with: openssl rand -base64 32
BSC_MAINNET_RPC_URL=https://bsc-dataseed.binance.org/  # Primary BSC mainnet RPC
BSC_MAINNET_RPC_URL_BACKUP1=https://bsc-dataseed1.defibit.io/  # Backup BSC mainnet RPC 1
BSC_MAINNET_RPC_URL_BACKUP2=https://bsc-dataseed1.ninicoin.io/  # Backup BSC mainnet RPC 2
BSC_TESTNET_RPC_URL=https://data-seed-prebsc-1-s1.binance.org:8545/  # Primary BSC testnet RPC
BSC_TESTNET_RPC_URL_BACKUP1=https://data-seed-prebsc-2-s1.binance.org:8545/  # Backup BSC testnet RPC
BSC_CHAIN_ID=56  # 56 for mainnet, 97 for testnet
WALLET_DEFAULT_TYPE=hot  # 'hot', 'cold', 'exchange' or 'multisig'
```

## Setup

Initialize the wallet database tables by running:

```bash
python scripts/init_wallet_db.py
```

This creates the necessary tables for wallet management, transaction history, balances, and withdrawal requests.

## Basic Usage

### Creating a Wallet

```python
from src.account import create_wallet, WalletType, BSC_TESTNET_CHAIN_ID

# Create a hot wallet (with private key)
wallet = create_wallet(
    user_id="user123",
    chain_id=BSC_TESTNET_CHAIN_ID,  # Use testnet for development
    wallet_type=WalletType.HOT,
    password="secure_password",  # Required for hot wallets
    name="My Test Wallet"
)

print(f"Created wallet with address: {wallet.address}")
```

### Importing a Wallet from Private Key

```python
from src.account import import_wallet_from_private_key, WalletType, BSC_TESTNET_CHAIN_ID

wallet = import_wallet_from_private_key(
    user_id="user123",
    private_key="0x5367d0bbadad9f8b0e2863bc9c69a7c012b9f83a96ce407b24cc26c69afd2a0c",
    chain_id=BSC_TESTNET_CHAIN_ID,
    wallet_type=WalletType.HOT,
    password="secure_password",
    name="Imported Wallet"
)
```

### Retrieving User Wallets

```python
from src.account import get_wallets_by_user_id

wallets = get_wallets_by_user_id("user123")
for wallet in wallets:
    print(f"Wallet: {wallet.name}, Address: {wallet.address}")
```

### Checking Balances

```python
from src.account import get_bnb_balance, get_token_balance, update_wallet_balances

# Check BNB balance
address = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
bnb_balance = get_bnb_balance(address)
print(f"BNB Balance: {bnb_balance}")

# Check token balance
token_address = "0x0123456789abcdef0123456789abcdef01234567"  # BEP20 token contract
token_balance = get_token_balance(address, token_address)
print(f"Token Balance: {token_balance}")

# Update and get all balances for a wallet
wallet_id = 1
balances = update_wallet_balances(wallet_id)
print(f"All balances: {balances}")
```

### Validating Addresses

```python
from src.account import is_valid_bep20_address

address = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
is_valid = is_valid_bep20_address(address)
print(f"Is valid address: {is_valid}")
```

## Security Considerations

- Always use strong passwords for hot wallets
- Store the `WALLET_ENCRYPTION_KEY` securely and never expose it
- Use secure HTTPS connections to BSC RPC nodes
- Consider implementing rate limiting for wallet-related API endpoints
- Regularly backup encrypted private keys
- Implement proper access controls for wallet operations
- Use multi-signature wallets for large funds

## Database Schema

The wallet integration uses the following database tables:

- `wallets`: Stores wallet information including addresses and encrypted keys
- `wallet_transactions`: Records transaction history
- `wallet_balances`: Tracks token balances
- `multisig_wallets`: Stores multi-signature wallet configurations
- `multisig_signers`: Records signer addresses for multi-signature wallets
- `withdrawal_requests`: Manages withdrawal requests
- `withdrawal_approvals`: Tracks approvals for multi-signature withdrawals

## Testing

Run the wallet tests with:

```bash
python -m unittest src/account/test_wallet.py
```

## Future Enhancements

- Multi-signature wallet implementation
- Support for additional BEP20 tokens
- Enhanced transaction monitoring
- Hardware wallet integration
- BNB staking capabilities 