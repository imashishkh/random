"""
BEP20 Wallet Management Module

This module implements BEP20 wallet creation, management, and interactions with the
Binance Smart Chain. It provides functionality for creating wallets, encrypting private keys,
and performing blockchain operations.
"""
import os
import json
import logging
import binascii
from typing import Dict, List, Optional, Union, Any, Tuple
from datetime import datetime

from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_utils import to_checksum_address
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

from pydantic import ValidationError
from dotenv import load_dotenv

from .models import Wallet, WalletType
from ..db import connection as db

# Load environment variables
load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)

# BEP20 ABI for token interactions
BEP20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
]

# Chain IDs
BSC_MAINNET_CHAIN_ID = 56
BSC_TESTNET_CHAIN_ID = 97

# BSC RPC endpoints
# Always use multiple providers for redundancy
BSC_MAINNET_RPC_URLS = [
    os.getenv("BSC_MAINNET_RPC_URL", "https://bsc-dataseed.binance.org/"),
    os.getenv("BSC_MAINNET_RPC_URL_BACKUP1", "https://bsc-dataseed1.defibit.io/"),
    os.getenv("BSC_MAINNET_RPC_URL_BACKUP2", "https://bsc-dataseed1.ninicoin.io/")
]

BSC_TESTNET_RPC_URLS = [
    os.getenv("BSC_TESTNET_RPC_URL", "https://data-seed-prebsc-1-s1.binance.org:8545/"),
    os.getenv("BSC_TESTNET_RPC_URL_BACKUP1", "https://data-seed-prebsc-2-s1.binance.org:8545/")
]

# Initialize Web3 with first endpoint (fallback logic will be implemented)
mainnet_web3 = Web3(Web3.HTTPProvider(BSC_MAINNET_RPC_URLS[0]))
testnet_web3 = Web3(Web3.HTTPProvider(BSC_TESTNET_RPC_URLS[0]))

# Apply middleware for Binance Smart Chain (which uses PoA)
mainnet_web3.middleware_onion.inject(geth_poa_middleware, layer=0)
testnet_web3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Master encryption key (should be stored securely, not in code)
ENCRYPTION_KEY = os.getenv("WALLET_ENCRYPTION_KEY", "").encode()
if not ENCRYPTION_KEY:
    logger.warning("No WALLET_ENCRYPTION_KEY found in environment variables. Using a default key (NOT SECURE FOR PRODUCTION).")
    ENCRYPTION_KEY = b'OzMPLzkfqQQKHOGPg9q8SZfIOlJbkBqn-JFfBKLYTvA='


def get_web3(chain_id: int = BSC_MAINNET_CHAIN_ID) -> Web3:
    """
    Get the appropriate Web3 instance for the specified chain ID.
    
    Args:
        chain_id: The chain ID (default: BSC mainnet)
        
    Returns:
        Web3 instance
    """
    if chain_id == BSC_TESTNET_CHAIN_ID:
        return testnet_web3
    return mainnet_web3


def derive_key(password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
    """
    Derive an encryption key from a password using PBKDF2.
    
    Args:
        password: The password to derive the key from
        salt: Optional salt (generated if not provided)
        
    Returns:
        Tuple of (key, salt)
    """
    if salt is None:
        salt = os.urandom(16)
        
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
    )
    
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key, salt


def encrypt_private_key(private_key: str, password: str) -> str:
    """
    Encrypt a private key using a password.
    
    Args:
        private_key: The private key to encrypt
        password: The password to use for encryption
        
    Returns:
        Encrypted private key as a string
    """
    key, salt = derive_key(password)
    fernet = Fernet(key)
    encrypted_data = fernet.encrypt(private_key.encode())
    
    # Store salt with encrypted data
    result = {
        'salt': base64.b64encode(salt).decode(),
        'data': base64.b64encode(encrypted_data).decode()
    }
    
    return json.dumps(result)


def decrypt_private_key(encrypted_data: str, password: str) -> str:
    """
    Decrypt an encrypted private key using a password.
    
    Args:
        encrypted_data: The encrypted private key
        password: The password to use for decryption
        
    Returns:
        Decrypted private key
    """
    try:
        data_dict = json.loads(encrypted_data)
        salt = base64.b64decode(data_dict['salt'])
        encrypted = base64.b64decode(data_dict['data'])
        
        key, _ = derive_key(password, salt)
        fernet = Fernet(key)
        
        return fernet.decrypt(encrypted).decode()
    except Exception as e:
        logger.error(f"Error decrypting private key: {e}")
        raise ValueError("Invalid password or corrupted data")


def create_wallet(user_id: str, chain_id: int = BSC_MAINNET_CHAIN_ID, 
                  wallet_type: WalletType = WalletType.HOT, 
                  password: Optional[str] = None,
                  name: Optional[str] = None) -> Wallet:
    """
    Create a new wallet for a user.
    
    Args:
        user_id: The ID of the user
        chain_id: The chain ID (default: BSC mainnet)
        wallet_type: The wallet type
        password: Password for encrypting the private key (required for HOT wallets)
        name: Optional name for the wallet
        
    Returns:
        Wallet object
    """
    if wallet_type == WalletType.HOT and not password:
        raise ValueError("Password is required for hot wallets")
    
    # Create new account
    account: LocalAccount = Account.create()
    address = account.address
    private_key = account.key.hex()
    
    # Convert to checksum address
    checksum_address = to_checksum_address(address)
    
    # Create wallet object
    wallet_data = {
        'user_id': user_id,
        'address': checksum_address,
        'wallet_type': wallet_type,
        'chain_id': chain_id,
        'name': name,
    }
    
    # For hot wallets, encrypt and store the private key
    if wallet_type == WalletType.HOT:
        wallet_data['encrypted_private_key'] = encrypt_private_key(private_key, password)
    
    # Save to database
    wallet_id = save_wallet_to_db(wallet_data)
    
    # Create and return Wallet object
    wallet = Wallet(**wallet_data)
    return wallet


def import_wallet_from_private_key(user_id: str, private_key: str, 
                                   chain_id: int = BSC_MAINNET_CHAIN_ID,
                                   wallet_type: WalletType = WalletType.HOT,
                                   password: Optional[str] = None,
                                   name: Optional[str] = None) -> Wallet:
    """
    Import a wallet from a private key.
    
    Args:
        user_id: The ID of the user
        private_key: The private key to import
        chain_id: The chain ID (default: BSC mainnet)
        wallet_type: The wallet type
        password: Password for encrypting the private key (required for HOT wallets)
        name: Optional name for the wallet
        
    Returns:
        Wallet object
    """
    if wallet_type == WalletType.HOT and not password:
        raise ValueError("Password is required for hot wallets")
    
    # Remove '0x' prefix if present
    if private_key.startswith('0x'):
        private_key = private_key[2:]
    
    try:
        # Create account from private key
        account: LocalAccount = Account.from_key(private_key)
        address = account.address
        
        # Convert to checksum address
        checksum_address = to_checksum_address(address)
        
        # Create wallet object
        wallet_data = {
            'user_id': user_id,
            'address': checksum_address,
            'wallet_type': wallet_type,
            'chain_id': chain_id,
            'name': name,
        }
        
        # For hot wallets, encrypt and store the private key
        if wallet_type == WalletType.HOT:
            wallet_data['encrypted_private_key'] = encrypt_private_key(private_key, password)
        
        # Save to database
        wallet_id = save_wallet_to_db(wallet_data)
        
        # Create and return Wallet object
        wallet = Wallet(**wallet_data)
        return wallet
    except Exception as e:
        logger.error(f"Error importing wallet from private key: {e}")
        raise ValueError("Invalid private key")


def save_wallet_to_db(wallet_data: Dict[str, Any]) -> int:
    """
    Save wallet data to the database.
    
    Args:
        wallet_data: Dictionary with wallet data
        
    Returns:
        Wallet ID
    """
    # Check if wallet already exists
    query = """
    SELECT id FROM wallets 
    WHERE user_id = %s AND address = %s
    """
    
    existing = db.execute_query(query, (wallet_data['user_id'], wallet_data['address']))
    
    if existing:
        raise ValueError(f"Wallet with address {wallet_data['address']} already exists for this user")
    
    # Insert new wallet
    columns = list(wallet_data.keys())
    placeholders = [f"%({col})s" for col in columns]
    
    query = f"""
    INSERT INTO wallets ({', '.join(columns)})
    VALUES ({', '.join(placeholders)})
    RETURNING id
    """
    
    with db.get_db_cursor() as cursor:
        cursor.execute(query, wallet_data)
        wallet_id = cursor.fetchone()[0]
    
    logger.info(f"Saved wallet with ID {wallet_id} to database")
    return wallet_id


def get_wallet_by_id(wallet_id: int) -> Optional[Wallet]:
    """
    Get a wallet by its ID.
    
    Args:
        wallet_id: The wallet ID
        
    Returns:
        Wallet object or None if not found
    """
    query = "SELECT * FROM wallets WHERE id = %s"
    results = db.execute_query(query, (wallet_id,))
    
    if not results:
        return None
    
    try:
        wallet = Wallet(**results[0])
        return wallet
    except ValidationError as e:
        logger.error(f"Error validating wallet data: {e}")
        return None


def get_wallets_by_user_id(user_id: str) -> List[Wallet]:
    """
    Get all wallets for a user.
    
    Args:
        user_id: The user ID
        
    Returns:
        List of Wallet objects
    """
    query = "SELECT * FROM wallets WHERE user_id = %s ORDER BY is_default DESC, created_at DESC"
    results = db.execute_query(query, (user_id,))
    
    wallets = []
    for result in results:
        try:
            wallet = Wallet(**result)
            wallets.append(wallet)
        except ValidationError as e:
            logger.error(f"Error validating wallet data: {e}")
    
    return wallets


def is_valid_bep20_address(address: str) -> bool:
    """
    Check if an address is a valid BEP20 address.
    
    Args:
        address: The address to check
        
    Returns:
        True if valid, False otherwise
    """
    if not Web3.is_address(address):
        return False
    
    # Convert to checksum address and compare
    try:
        checksum_address = to_checksum_address(address)
        return True
    except ValueError:
        return False


def get_bnb_balance(address: str, chain_id: int = BSC_MAINNET_CHAIN_ID) -> float:
    """
    Get the BNB balance for an address.
    
    Args:
        address: The address to check
        chain_id: The chain ID
        
    Returns:
        Balance in BNB
    """
    web3 = get_web3(chain_id)
    
    try:
        # Get balance in wei
        balance_wei = web3.eth.get_balance(address)
        
        # Convert to BNB (18 decimals)
        balance_bnb = web3.from_wei(balance_wei, 'ether')
        
        return float(balance_bnb)
    except Exception as e:
        logger.error(f"Error getting BNB balance: {e}")
        raise


def get_token_balance(address: str, token_address: str, chain_id: int = BSC_MAINNET_CHAIN_ID) -> float:
    """
    Get the token balance for an address.
    
    Args:
        address: The address to check
        token_address: The token contract address
        chain_id: The chain ID
        
    Returns:
        Token balance
    """
    web3 = get_web3(chain_id)
    
    try:
        # Create contract instance
        token_contract = web3.eth.contract(address=token_address, abi=BEP20_ABI)
        
        # Get balance and decimals
        balance = token_contract.functions.balanceOf(address).call()
        decimals = token_contract.functions.decimals().call()
        
        # Convert to token units
        token_balance = balance / (10 ** decimals)
        
        return float(token_balance)
    except Exception as e:
        logger.error(f"Error getting token balance: {e}")
        raise


def update_wallet_balances(wallet_id: int) -> Dict[str, float]:
    """
    Update and retrieve balances for a wallet.
    
    Args:
        wallet_id: The wallet ID
        
    Returns:
        Dictionary of token symbol -> balance
    """
    wallet = get_wallet_by_id(wallet_id)
    if not wallet:
        raise ValueError(f"Wallet with ID {wallet_id} not found")
    
    web3 = get_web3(wallet.chain_id)
    
    # Get BNB balance
    bnb_balance = get_bnb_balance(wallet.address, wallet.chain_id)
    
    # Store BNB balance
    with db.get_db_cursor() as cursor:
        query = """
        INSERT INTO wallet_balances (wallet_id, token_address, token_symbol, balance, last_updated)
        VALUES (%s, NULL, %s, %s, NOW())
        ON CONFLICT (wallet_id, token_address) 
        DO UPDATE SET balance = %s, last_updated = NOW()
        """
        cursor.execute(query, (wallet_id, 'BNB', bnb_balance, bnb_balance))
    
    # Get stored tokens for this wallet
    query = """
    SELECT token_address, token_symbol FROM wallet_balances 
    WHERE wallet_id = %s AND token_address IS NOT NULL
    """
    tokens = db.execute_query(query, (wallet_id,))
    
    balances = {'BNB': bnb_balance}
    
    # Update token balances
    for token in tokens:
        try:
            token_balance = get_token_balance(wallet.address, token['token_address'], wallet.chain_id)
            
            with db.get_db_cursor() as cursor:
                query = """
                UPDATE wallet_balances 
                SET balance = %s, last_updated = NOW()
                WHERE wallet_id = %s AND token_address = %s
                """
                cursor.execute(query, (token_balance, wallet_id, token['token_address']))
            
            balances[token['token_symbol']] = token_balance
        except Exception as e:
            logger.error(f"Error updating balance for token {token['token_symbol']}: {e}")
    
    return balances


def get_wallet_balances(wallet_id: int) -> Dict[str, float]:
    """
    Get current balances for a wallet from the database.
    
    Args:
        wallet_id: The wallet ID
        
    Returns:
        Dictionary of token symbol -> balance
    """
    query = """
    SELECT token_symbol, balance FROM wallet_balances 
    WHERE wallet_id = %s
    """
    results = db.execute_query(query, (wallet_id,))
    
    balances = {}
    for result in results:
        balances[result['token_symbol']] = float(result['balance'])
    
    return balances


def get_all_wallet_addresses(connection) -> List[str]:
    """
    Get all wallet addresses in the system.
    
    Args:
        connection: Database connection object
        
    Returns:
        List of wallet addresses
    """
    try:
        cursor = connection.cursor()
        query = "SELECT address FROM wallets"
        cursor.execute(query)
        results = cursor.fetchall()
        
        addresses = [row[0] for row in results]
        return addresses
    except Exception as e:
        logger.error(f"Error getting wallet addresses: {e}")
        return []


def get_all_wallets(connection) -> List[Dict[str, Any]]:
    """
    Get all wallets in the system with basic information.
    
    Args:
        connection: Database connection object
        
    Returns:
        List of wallet data dictionaries
    """
    try:
        cursor = connection.cursor()
        query = """
        SELECT id, user_id, address, type, chain_id 
        FROM wallets
        """
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        
        wallets = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return wallets
    except Exception as e:
        logger.error(f"Error getting all wallets: {e}")
        return []


def get_wallet_balance(connection, wallet_id: int) -> float:
    """
    Get the BNB balance for a wallet from the database.
    
    Args:
        connection: Database connection object
        wallet_id: The wallet ID
        
    Returns:
        BNB balance as a float
    """
    try:
        cursor = connection.cursor()
        query = """
        SELECT balance FROM wallet_balances 
        WHERE wallet_id = %s AND token_symbol = 'BNB'
        """
        cursor.execute(query, (wallet_id,))
        result = cursor.fetchone()
        
        if result:
            return float(result[0])
        return 0.0
    except Exception as e:
        logger.error(f"Error getting wallet balance: {e}")
        return 0.0


def get_on_chain_balance(address: str, chain_id: int = BSC_MAINNET_CHAIN_ID) -> float:
    """
    Get the current on-chain BNB balance for a wallet address.
    
    Args:
        address: The wallet address
        chain_id: The chain ID 
        
    Returns:
        BNB balance as a float
    """
    try:
        web3 = get_web3(chain_id)
        balance_wei = web3.eth.get_balance(Web3.to_checksum_address(address))
        balance_ether = web3.from_wei(balance_wei, 'ether')
        return float(balance_ether)
    except Exception as e:
        logger.error(f"Error getting on-chain balance for {address}: {e}")
        return 0.0


def update_wallet_balance(connection, wallet_id: int, amount: float, 
                          transaction_type: str, reference: str) -> bool:
    """
    Update a wallet's BNB balance based on a transaction.
    
    Args:
        connection: Database connection object
        wallet_id: The wallet ID
        amount: The amount to add (positive) or subtract (negative)
        transaction_type: Type of transaction (deposit, withdrawal, etc.)
        reference: Transaction reference
        
    Returns:
        True if successful, False otherwise
    """
    try:
        cursor = connection.cursor()
        
        # Check if balance record exists
        check_query = """
        SELECT balance FROM wallet_balances 
        WHERE wallet_id = %s AND token_symbol = 'BNB'
        """
        cursor.execute(check_query, (wallet_id,))
        result = cursor.fetchone()
        
        if result:
            # Update existing balance
            current_balance = float(result[0])
            new_balance = current_balance + amount
            
            if new_balance < 0:
                logger.error(f"Insufficient balance for wallet {wallet_id}: {current_balance} < {abs(amount)}")
                return False
            
            update_query = """
            UPDATE wallet_balances 
            SET balance = %s, updated_at = NOW() 
            WHERE wallet_id = %s AND token_symbol = 'BNB'
            """
            cursor.execute(update_query, (new_balance, wallet_id))
        else:
            # Insert new balance record
            if amount < 0:
                logger.error(f"Insufficient balance for wallet {wallet_id}: 0 < {abs(amount)}")
                return False
            
            insert_query = """
            INSERT INTO wallet_balances (wallet_id, token_symbol, balance, created_at, updated_at)
            VALUES (%s, %s, %s, NOW(), NOW())
            """
            cursor.execute(insert_query, (wallet_id, 'BNB', amount))
        
        # Record transaction
        tx_query = """
        INSERT INTO wallet_transactions 
        (wallet_id, type, amount, reference, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        """
        cursor.execute(tx_query, (wallet_id, transaction_type, amount, reference))
        
        connection.commit()
        logger.info(f"Updated balance for wallet {wallet_id}: {amount} {transaction_type}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating wallet balance: {e}")
        connection.rollback()
        return False 