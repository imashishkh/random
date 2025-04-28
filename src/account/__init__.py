"""
Account Management Module

This module provides account management functionality for the Forex Trading platform.
It handles user account creation, authentication, position management, and risk management.
It also provides BEP20 wallet integration for fund management.
"""

from .models import User, Account, AccountType, AccountStatus
from .manager import (
    create_account, get_account, get_accounts_by_user,
    update_account_status, get_account_balance
)
from .position import Position, PositionStatus, PositionType
from .risk import RiskManager, RiskProfile, calculate_max_position_size

# Wallet functionality
from .wallet import (
    Wallet, WalletType, create_wallet, import_wallet_from_private_key,
    get_wallet, get_wallets_by_user, validate_address, get_wallet_balance,
    generate_private_key, calculate_address, encrypt_private_key, decrypt_private_key
)

# Transaction verification and status tracking
from .transaction_verification import (
    TransactionVerifier, get_verifier, VerificationStatus
)
from .transaction_status import (
    TransactionStatus, TransactionType, TransactionStatusManager, 
    get_status_manager
)

__all__ = [
    # Account models
    'User', 'Account', 'AccountType', 'AccountStatus',
    
    # Account management
    'create_account', 'get_account', 'get_accounts_by_user',
    'update_account_status', 'get_account_balance',
    
    # Position management
    'Position', 'PositionStatus', 'PositionType',
    
    # Risk management
    'RiskManager', 'RiskProfile', 'calculate_max_position_size',
    
    # Wallet functionality
    'Wallet', 'WalletType', 'create_wallet', 'import_wallet_from_private_key',
    'get_wallet', 'get_wallets_by_user', 'validate_address', 'get_wallet_balance',
    'generate_private_key', 'calculate_address', 'encrypt_private_key', 'decrypt_private_key',
    
    # Transaction verification and status
    'TransactionVerifier', 'get_verifier', 'VerificationStatus',
    'TransactionStatus', 'TransactionType', 'TransactionStatusManager', 'get_status_manager'
] 