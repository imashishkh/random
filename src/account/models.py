"""
Data models for account management.

This module defines the data models used in the account management system,
including account balances, positions, transactions, and risk metrics.
"""
from typing import Dict, List, Optional, Union, Any, Tuple
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, validator, Field


class PositionSide(str, Enum):
    """Position side enum."""
    LONG = "long"
    SHORT = "short"
    BOTH = "both"  # For cases where a position can be both long and short


class PositionStatus(str, Enum):
    """Position status enum."""
    OPEN = "open"
    CLOSED = "closed"
    PARTIALLY_CLOSED = "partially_closed"


class TransactionType(str, Enum):
    """Transaction type enum."""
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRADE = "trade"
    FEE = "fee"
    TRANSFER = "transfer"
    INTEREST = "interest"
    DIVIDEND = "dividend"
    MARGIN = "margin"
    OTHER = "other"


class WalletType(str, Enum):
    """Wallet type enum."""
    HOT = "hot"  # Online wallet with private key (encrypted)
    COLD = "cold"  # Offline wallet without private key
    EXCHANGE = "exchange"  # Wallet on an exchange
    MULTISIG = "multisig"  # Multi-signature wallet


class AssetBalance(BaseModel):
    """Model for individual asset balance."""
    asset: str
    free: float
    locked: float  # Amount locked in orders or processes
    total: float = 0.0
    
    @validator('total', pre=True, always=True)
    def calculate_total(cls, v, values):
        """Calculate total balance from free and locked amounts."""
        if 'free' in values and 'locked' in values:
            return values['free'] + values['locked']
        return v


class AccountBalance(BaseModel):
    """Model for overall account balance."""
    exchange: str
    balances: List[AssetBalance]
    total_btc_value: Optional[float] = None
    total_usd_value: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    

class Wallet(BaseModel):
    """Model for cryptocurrency wallet."""
    user_id: str
    address: str
    wallet_type: WalletType
    chain_id: int  # Chain ID (56 for BSC mainnet, 97 for BSC testnet)
    encrypted_private_key: Optional[str] = None  # Encrypted private key (for hot wallets)
    encrypted_mnemonic: Optional[str] = None  # Encrypted mnemonic phrase
    name: Optional[str] = None  # User-defined wallet name
    is_default: bool = False  # Whether this is the user's default wallet
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    @validator('address')
    def validate_address(cls, v):
        """Validate Ethereum/BSC address format."""
        if not v.startswith('0x') or len(v) != 42:
            raise ValueError('Invalid Ethereum/BSC address format')
        return v


class Position(BaseModel):
    """Model for trading position."""
    symbol: str
    side: PositionSide
    entry_price: float
    amount: float
    leverage: float = 1.0
    liquidation_price: Optional[float] = None
    margin_type: str = "isolated"  # or "cross"
    status: PositionStatus = PositionStatus.OPEN
    unrealized_pnl: Optional[float] = None
    realized_pnl: float = 0.0
    open_time: datetime = Field(default_factory=datetime.utcnow)
    close_time: Optional[datetime] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    exchange: str
    
    @validator('unrealized_pnl', pre=True)
    def calculate_unrealized_pnl(cls, v, values):
        """Calculate unrealized PNL if not provided."""
        # Simple calculation, accurate calculation would need current market price
        if v is None and all(key in values for key in ['entry_price', 'amount', 'side']):
            # This is just a placeholder - real implementation would need current price
            return 0.0
        return v


class TransactionStatus(Enum):
    """Status of blockchain transactions."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class Transaction(BaseModel):
    """Model for tracking blockchain transactions."""
    transaction_id: str
    transaction_type: TransactionType
    symbol: Optional[str] = None
    asset: str
    amount: float
    price: Optional[float] = None
    fee: float = 0.0
    fee_asset: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    exchange: str
    order_id: Optional[str] = None
    trade_id: Optional[str] = None
    notes: Optional[str] = None
    status: TransactionStatus = TransactionStatus.PENDING
    
    # Additional fields for blockchain transactions
    hash: Optional[str] = None
    from_address: Optional[str] = None
    to_address: Optional[str] = None
    block_number: Optional[int] = None
    chain_id: Optional[int] = None
    confirmations: int = 0
    user_id: Optional[str] = None
    
    @classmethod
    def get_by_hash(cls, tx_hash: str) -> Optional['Transaction']:
        """
        Get a transaction by its hash.
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            Transaction object if found, None otherwise
        """
        # Implementation would typically use a database query
        # This is a placeholder for demonstration purposes
        import os
        import psycopg2
        from dotenv import load_dotenv
        
        load_dotenv()
        
        # Database connection parameters
        db_params = {
            'dbname': os.getenv('DB_NAME', 'forex_trading'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'postgres'),
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432')
        }
        
        try:
            conn = psycopg2.connect(**db_params)
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT * FROM blockchain_transactions
                WHERE tx_hash = %s
                """,
                (tx_hash,)
            )
            
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                # Convert database row to Transaction object
                # Column mapping would depend on actual database schema
                return cls(
                    transaction_id=str(row[0]),  # Assuming ID is first column
                    transaction_type=TransactionType.DEPOSIT,
                    asset="BNB",  # Assuming BNB for simplicity
                    amount=float(row[4]),  # Assuming value is 5th column
                    hash=row[1],  # Assuming tx_hash is 2nd column
                    from_address=row[2],  # Assuming from_address is 3rd column
                    to_address=row[3],  # Assuming to_address is 4th column
                    block_number=row[4],  # Assuming block_number is 5th column
                    chain_id=row[6],  # Assuming chain_id is 7th column
                    status=TransactionStatus.PENDING if row[7] == "pending" else 
                           TransactionStatus.CONFIRMED if row[7] == "confirmed" else
                           TransactionStatus.FAILED,
                    user_id=str(row[9]),  # Assuming user_id is 10th column
                    exchange="binance",  # Placeholder
                )
            return None
            
        except Exception as e:
            logging.error(f"Error getting transaction by hash: {e}")
            return None
    
    @classmethod
    def get_pending_by_chain(cls, chain_id: int) -> List['Transaction']:
        """
        Get all pending transactions for a specific blockchain.
        
        Args:
            chain_id: Blockchain ID
            
        Returns:
            List of Transaction objects
        """
        # Implementation would typically use a database query
        # This is a placeholder for demonstration purposes
        import os
        import psycopg2
        from dotenv import load_dotenv
        import logging
        
        load_dotenv()
        
        # Database connection parameters
        db_params = {
            'dbname': os.getenv('DB_NAME', 'forex_trading'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'postgres'),
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432')
        }
        
        try:
            conn = psycopg2.connect(**db_params)
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT * FROM blockchain_transactions
                WHERE chain_id = %s AND (status = 'pending' OR status = 'confirming')
                """,
                (chain_id,)
            )
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            result = []
            for row in rows:
                # Convert database row to Transaction object
                transaction = cls(
                    transaction_id=str(row[0]),  # Assuming ID is first column
                    transaction_type=TransactionType.DEPOSIT,
                    asset="BNB",  # Assuming BNB for simplicity
                    amount=float(row[4]),  # Assuming value is 5th column
                    hash=row[1],  # Assuming tx_hash is 2nd column
                    from_address=row[2],  # Assuming from_address is 3rd column
                    to_address=row[3],  # Assuming to_address is 4th column
                    block_number=row[4],  # Assuming block_number is 5th column
                    chain_id=row[6],  # Assuming chain_id is 7th column
                    status=TransactionStatus.PENDING if row[7] == "pending" else 
                           TransactionStatus.CONFIRMED if row[7] == "confirming" else
                           TransactionStatus.FAILED,
                    user_id=str(row[9]),  # Assuming user_id is 10th column
                    exchange="binance",  # Placeholder
                )
                result.append(transaction)
            
            return result
            
        except Exception as e:
            logging.error(f"Error getting pending transactions: {e}")
            return []
    
    def save(self) -> bool:
        """
        Save the transaction to the database.
        
        Returns:
            True if successful, False otherwise
        """
        # Implementation would typically use a database query
        # This is a placeholder for demonstration purposes
        import os
        import psycopg2
        import logging
        from dotenv import load_dotenv
        
        load_dotenv()
        
        # Database connection parameters
        db_params = {
            'dbname': os.getenv('DB_NAME', 'forex_trading'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'postgres'),
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432')
        }
        
        try:
            conn = psycopg2.connect(**db_params)
            cursor = conn.cursor()
            
            if self.hash:  # This is a blockchain transaction
                # Check if transaction already exists
                cursor.execute(
                    "SELECT id FROM blockchain_transactions WHERE tx_hash = %s",
                    (self.hash,)
                )
                
                if cursor.fetchone():
                    # Update existing transaction
                    cursor.execute(
                        """
                        UPDATE blockchain_transactions 
                        SET status = %s, confirmations = %s, updated_at = %s
                        WHERE tx_hash = %s
                        """,
                        (
                            self.status.value, 
                            self.confirmations,
                            datetime.utcnow(),
                            self.hash
                        )
                    )
                else:
                    # Insert new transaction
                    cursor.execute(
                        """
                        INSERT INTO blockchain_transactions
                        (tx_hash, from_address, to_address, block_number, value, 
                        chain_id, status, confirmations, user_id, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            self.hash,
                            self.from_address,
                            self.to_address,
                            self.block_number,
                            self.amount,
                            self.chain_id,
                            self.status.value,
                            self.confirmations,
                            self.user_id,
                            datetime.utcnow(),
                            datetime.utcnow()
                        )
                    )
            else:  # This is a regular transaction
                # Insert or update the transaction in the account_transactions table
                cursor.execute(
                    """
                    INSERT INTO account_transactions
                    (user_id, type, amount, reference, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        self.user_id,
                        self.transaction_type.value,
                        self.amount,
                        self.transaction_id,
                        self.timestamp
                    )
                )
            
            conn.commit()
            cursor.close()
            conn.close()
            return True
            
        except Exception as e:
            logging.error(f"Error saving transaction: {e}")
            return False


class RiskMetrics(BaseModel):
    """Model for risk metrics."""
    account_value: float  # Total account value in base currency
    free_margin: float  # Available margin
    used_margin: float  # Margin currently in use
    margin_level: float  # Margin level (%)
    positions_risk: float  # Risk from open positions (%)
    daily_drawdown: float  # Daily drawdown (%)
    max_drawdown: float  # Maximum drawdown (%)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    @validator('margin_level', pre=True, always=True)
    def calculate_margin_level(cls, v, values):
        """Calculate margin level if not provided."""
        if all(key in values for key in ['account_value', 'used_margin']):
            if values['used_margin'] > 0:
                return (values['account_value'] / values['used_margin']) * 100
            else:
                return 100.0  # No margin used
        return v 