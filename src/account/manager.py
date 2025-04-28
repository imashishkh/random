"""
Account manager implementation.

This module provides the AccountManager class, which is responsible for
managing account-related functionality such as balance checking, position
sizing, and transaction history.
"""
import logging
import uuid
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime, timedelta
import threading

from ..exchange.base import BaseExchange
from .models import (
    AccountBalance,
    AssetBalance,
    Position,
    Transaction,
    RiskMetrics,
    TransactionType,
    PositionSide,
    PositionStatus
)
from ..cache import get_cache, set_cache, get_cache_key

# Configure logger
logger = logging.getLogger(__name__)

# Cache TTL values (in seconds)
CACHE_TTL_BALANCE = 60  # 1 minute
CACHE_TTL_POSITIONS = 30  # 30 seconds
CACHE_TTL_METRICS = 120  # 2 minutes


class AccountManager:
    """Account manager for trading operations."""
    
    def __init__(self, exchange: BaseExchange, cache_enabled: bool = True):
        """
        Initialize the account manager.
        
        Args:
            exchange: The exchange client
            cache_enabled: Whether to use caching for account data
        """
        self.exchange = exchange
        self.cache_enabled = cache_enabled
        self.exchange_name = exchange.exchange_name.lower()
        
        logger.info(f"Initialized account manager for {self.exchange_name}")
    
    def get_balance(self, cache: bool = True) -> AccountBalance:
        """
        Get account balance information.
        
        Args:
            cache: Whether to use cached data if available
            
        Returns:
            AccountBalance model with balance information
        """
        # Check cache first if enabled and requested
        if self.cache_enabled and cache:
            cache_key = get_cache_key(self.exchange_name, "account", "balance")
            cached_data = get_cache(cache_key)
            
            if cached_data:
                logger.debug("Retrieved account balance from cache")
                return AccountBalance(**cached_data)
        
        try:
            # Get balance from exchange
            balance_data = self.exchange.get_balance()
            
            if not balance_data or "success" in balance_data and not balance_data["success"]:
                error_msg = balance_data.get("error", "Unknown error") if isinstance(balance_data, dict) else "Failed to fetch balance"
                logger.error(f"Error fetching balance: {error_msg}")
                raise ValueError(f"Failed to get balance: {error_msg}")
            
            # Process balance data
            balances = []
            total_btc = 0.0
            total_usd = 0.0
            
            # Extract balance information
            if "total" in balance_data:
                # For exchanges that provide a formatted balance response
                for asset, amounts in balance_data.get("total", {}).items():
                    if isinstance(amounts, (int, float)) and amounts > 0:
                        # Simple case where amounts is just a number
                        free = balance_data.get("free", {}).get(asset, 0.0)
                        used = balance_data.get("used", {}).get(asset, 0.0)
                        
                        balances.append(AssetBalance(
                            asset=asset,
                            free=float(free),
                            locked=float(used),
                            total=float(amounts)
                        ))
                    elif isinstance(amounts, dict) and amounts.get("total", 0) > 0:
                        # Case where amounts is a dictionary with total, free, used
                        balances.append(AssetBalance(
                            asset=asset,
                            free=float(amounts.get("free", 0.0)),
                            locked=float(amounts.get("used", 0.0)),
                            total=float(amounts.get("total", 0.0))
                        ))
            
            # Extract BTC and USD equivalent values if available
            if "info" in balance_data and "totalBtcValue" in balance_data["info"]:
                total_btc = float(balance_data["info"]["totalBtcValue"])
            
            if "info" in balance_data and "totalUsdtValue" in balance_data["info"]:
                total_usd = float(balance_data["info"]["totalUsdtValue"])
            
            # Create account balance model
            account_balance = AccountBalance(
                exchange=self.exchange_name,
                balances=balances,
                total_btc_value=total_btc if total_btc > 0 else None,
                total_usd_value=total_usd if total_usd > 0 else None,
                timestamp=datetime.utcnow()
            )
            
            # Cache the data
            if self.cache_enabled:
                set_cache(cache_key, account_balance.dict(), CACHE_TTL_BALANCE)
            
            return account_balance
        
        except Exception as e:
            logger.error(f"Error getting account balance: {str(e)}")
            raise
    
    def get_asset_balance(self, asset: str, cache: bool = True) -> AssetBalance:
        """
        Get balance for a specific asset.
        
        Args:
            asset: Asset symbol (e.g., 'BTC')
            cache: Whether to use cached data if available
            
        Returns:
            AssetBalance model for the specified asset
        """
        # Get overall account balance
        account_balance = self.get_balance(cache=cache)
        
        # Find the specific asset
        for balance in account_balance.balances:
            if balance.asset.upper() == asset.upper():
                return balance
        
        # Asset not found, return zero balance
        return AssetBalance(
            asset=asset.upper(),
            free=0.0,
            locked=0.0,
            total=0.0
        )
    
    def calculate_position_size(self, symbol: str, risk_percent: float, 
                              stop_loss_price: float, entry_price: float,
                              account_value: Optional[float] = None) -> float:
        """
        Calculate position size based on risk parameters.
        
        Args:
            symbol: Trading pair symbol
            risk_percent: Risk percentage (0-100)
            stop_loss_price: Stop loss price
            entry_price: Entry price
            account_value: Account value to use (if None, uses current balance)
            
        Returns:
            Recommended position size
        """
        try:
            # Validate parameters
            if risk_percent <= 0 or risk_percent > 100:
                raise ValueError(f"Risk percentage must be between 0 and 100, got {risk_percent}")
            
            if stop_loss_price <= 0:
                raise ValueError(f"Stop loss price must be positive, got {stop_loss_price}")
            
            if entry_price <= 0:
                raise ValueError(f"Entry price must be positive, got {entry_price}")
            
            # Determine account value
            if account_value is None:
                balance = self.get_balance()
                if balance.total_usd_value:
                    account_value = balance.total_usd_value
                else:
                    # Calculate account value from balances
                    # This is a simplified approach - for real implementation,
                    # we would need to convert all assets to a base currency
                    account_value = 0
                    for asset_balance in balance.balances:
                        if asset_balance.asset in ['USDT', 'USD', 'BUSD', 'USDC']:
                            account_value += asset_balance.total
                    
                    if account_value == 0:
                        raise ValueError("Could not determine account value")
            
            # Calculate risk amount
            risk_amount = account_value * (risk_percent / 100)
            
            # Calculate position size
            price_difference = abs(entry_price - stop_loss_price)
            
            if price_difference == 0:
                raise ValueError("Entry price and stop loss price cannot be the same")
            
            # Position size in base currency
            position_size_base = risk_amount / price_difference
            
            # Convert to asset amount
            position_size = position_size_base / entry_price
            
            logger.info(f"Calculated position size: {position_size} for {symbol} with {risk_percent}% risk")
            return position_size
        
        except Exception as e:
            logger.error(f"Error calculating position size: {str(e)}")
            raise
    
    def record_transaction(self, 
                         transaction_type: Union[TransactionType, str],
                         asset: str,
                         amount: float,
                         price: Optional[float] = None,
                         fee: float = 0.0,
                         fee_asset: Optional[str] = None,
                         symbol: Optional[str] = None,
                         order_id: Optional[str] = None,
                         trade_id: Optional[str] = None,
                         notes: Optional[str] = None) -> Transaction:
        """
        Record a transaction in the transaction history.
        
        Args:
            transaction_type: Type of transaction
            asset: Asset involved
            amount: Transaction amount
            price: Price per unit (for trades)
            fee: Transaction fee amount
            fee_asset: Asset used for fee
            symbol: Trading pair symbol (for trades)
            order_id: Associated order ID
            trade_id: Associated trade ID
            notes: Additional notes
            
        Returns:
            Transaction model representing the recorded transaction
        """
        try:
            # Convert string type to enum if needed
            if isinstance(transaction_type, str):
                transaction_type = TransactionType(transaction_type.lower())
            
            # Generate a unique transaction ID
            transaction_id = f"txn_{uuid.uuid4().hex[:16]}_{int(datetime.utcnow().timestamp())}"
            
            # Create transaction record
            transaction = Transaction(
                transaction_id=transaction_id,
                transaction_type=transaction_type,
                asset=asset,
                amount=amount,
                price=price,
                fee=fee,
                fee_asset=fee_asset or asset,
                symbol=symbol,
                order_id=order_id,
                trade_id=trade_id,
                notes=notes,
                timestamp=datetime.utcnow(),
                exchange=self.exchange_name
            )
            
            # TODO: Store transaction in database
            # This is a placeholder - actual implementation would save to a database
            logger.info(f"Recorded transaction: {transaction_id} ({transaction_type}) for {amount} {asset}")
            
            return transaction
        
        except Exception as e:
            logger.error(f"Error recording transaction: {str(e)}")
            raise
    
    def get_transactions(self, 
                       asset: Optional[str] = None,
                       transaction_type: Optional[Union[TransactionType, str]] = None,
                       start_time: Optional[datetime] = None,
                       end_time: Optional[datetime] = None,
                       limit: int = 100) -> List[Transaction]:
        """
        Get transaction history with optional filters.
        
        Args:
            asset: Filter by asset
            transaction_type: Filter by transaction type
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum number of transactions to return
            
        Returns:
            List of Transaction models
        """
        try:
            # TODO: Implement database query for transaction history
            # This is a placeholder - actual implementation would query a database
            
            # For now, return an empty list
            logger.info(f"Requested transaction history (placeholder)")
            return []
        
        except Exception as e:
            logger.error(f"Error getting transactions: {str(e)}")
            raise
    
    def calculate_risk_metrics(self, cache: bool = True) -> RiskMetrics:
        """
        Calculate risk metrics for the account.
        
        Args:
            cache: Whether to use cached data if available
            
        Returns:
            RiskMetrics model with risk metrics
        """
        # Check cache first if enabled and requested
        if self.cache_enabled and cache:
            cache_key = get_cache_key(self.exchange_name, "account", "risk_metrics")
            cached_data = get_cache(cache_key)
            
            if cached_data:
                logger.debug("Retrieved risk metrics from cache")
                return RiskMetrics(**cached_data)
        
        try:
            # Get account balance
            balance = self.get_balance(cache=cache)
            
            # Determine account value
            account_value = balance.total_usd_value or 0
            if account_value == 0:
                # Calculate from stable coin balances
                for asset_balance in balance.balances:
                    if asset_balance.asset in ['USDT', 'USD', 'BUSD', 'USDC']:
                        account_value += asset_balance.total
            
            # TODO: Get positions and calculate used margin
            # This is a placeholder - actual implementation would calculate from positions
            used_margin = 0.0
            free_margin = account_value - used_margin
            
            # Calculate margin level
            margin_level = 100.0
            if used_margin > 0:
                margin_level = (account_value / used_margin) * 100
            
            # TODO: Calculate drawdown metrics
            # This is a placeholder - actual implementation would calculate from historical data
            daily_drawdown = 0.0
            max_drawdown = 0.0
            
            # TODO: Calculate position risk
            # This is a placeholder - actual implementation would calculate from positions
            positions_risk = 0.0
            
            # Create risk metrics model
            risk_metrics = RiskMetrics(
                account_value=account_value,
                free_margin=free_margin,
                used_margin=used_margin,
                margin_level=margin_level,
                positions_risk=positions_risk,
                daily_drawdown=daily_drawdown,
                max_drawdown=max_drawdown,
                timestamp=datetime.utcnow()
            )
            
            # Cache the data
            if self.cache_enabled:
                set_cache(cache_key, risk_metrics.dict(), CACHE_TTL_METRICS)
            
            return risk_metrics
        
        except Exception as e:
            logger.error(f"Error calculating risk metrics: {str(e)}")
            raise
    
    def get_positions(self, symbol: Optional[str] = None, cache: bool = True) -> List[Position]:
        """
        Get open positions.
        
        Args:
            symbol: Filter by symbol
            cache: Whether to use cached data if available
            
        Returns:
            List of Position models
        """
        # Check cache first if enabled and requested
        cache_key = get_cache_key(self.exchange_name, "account", "positions")
        if self.cache_enabled and cache:
            cached_data = get_cache(cache_key)
            
            if cached_data:
                logger.debug("Retrieved positions from cache")
                positions = [Position(**p) for p in cached_data]
                
                # Filter by symbol if requested
                if symbol:
                    positions = [p for p in positions if p.symbol == symbol]
                
                return positions
        
        try:
            # TODO: Implement getting positions from exchange
            # This is a placeholder - actual implementation would use exchange API
            # For now, return an empty list
            positions = []
            
            # Cache the data
            if self.cache_enabled:
                set_cache(cache_key, [p.dict() for p in positions], CACHE_TTL_POSITIONS)
            
            logger.info(f"Retrieved positions (placeholder)")
            return positions
        
        except Exception as e:
            logger.error(f"Error getting positions: {str(e)}")
            raise

class WalletManager:
    """Manage wallet operations and fund monitoring for trading accounts."""
    
    def __init__(self, cache_enabled: bool = True):
        """
        Initialize the wallet manager.
        
        Args:
            cache_enabled: Whether to use caching for wallet data
        """
        self.cache_enabled = cache_enabled
        self._wallets = {}  # Cached wallet data
        self._transactions = {}  # Cached transaction data
        self._lock = threading.RLock()
        
        # Cache TTL values (in seconds)
        self.CACHE_TTL_WALLET = 60  # 1 minute
        self.CACHE_TTL_TRANSACTIONS = 30  # 30 seconds
        
        logger.info("Initialized wallet manager")
    
    def get_wallet(self, wallet_id: int, cache: bool = True) -> Dict[str, Any]:
        """
        Get wallet information by wallet ID.
        
        Args:
            wallet_id: The wallet ID
            cache: Whether to use cached data if available
            
        Returns:
            Wallet information dictionary
        """
        # Check cache first if enabled and requested
        cache_key = f"wallet_{wallet_id}"
        if self.cache_enabled and cache and cache_key in self._wallets:
            logger.debug(f"Retrieved wallet {wallet_id} from cache")
            return self._wallets[cache_key]
        
        try:
            from src.account.wallet import get_wallet_by_id, get_wallet_balances
            
            # Get wallet from database
            wallet = get_wallet_by_id(wallet_id)
            if not wallet:
                raise ValueError(f"Wallet with ID {wallet_id} not found")
            
            # Get balances for the wallet
            balances = get_wallet_balances(wallet_id)
            
            # Combine wallet and balance information
            wallet_data = wallet.dict()
            wallet_data["balances"] = balances
            wallet_data["last_updated"] = datetime.utcnow()
            
            # Cache the data
            if self.cache_enabled:
                with self._lock:
                    self._wallets[cache_key] = wallet_data
            
            return wallet_data
        
        except Exception as e:
            logger.error(f"Error getting wallet {wallet_id}: {str(e)}")
            raise
    
    def get_user_wallets(self, user_id: str, cache: bool = True) -> List[Dict[str, Any]]:
        """
        Get all wallets for a user.
        
        Args:
            user_id: The user ID
            cache: Whether to use cached data if available
            
        Returns:
            List of wallet information dictionaries
        """
        # Check cache first if enabled and requested
        cache_key = f"user_wallets_{user_id}"
        if self.cache_enabled and cache and cache_key in self._wallets:
            logger.debug(f"Retrieved wallets for user {user_id} from cache")
            return self._wallets[cache_key]
        
        try:
            from src.account.wallet import get_wallets_by_user_id
            
            # Get wallets from database
            wallets = get_wallets_by_user_id(user_id)
            
            # Get balances for each wallet
            wallet_data_list = []
            for wallet in wallets:
                wallet_data = wallet.dict()
                try:
                    from src.account.wallet import get_wallet_balances
                    balances = get_wallet_balances(wallet_data.get("id"))
                    wallet_data["balances"] = balances
                except Exception as balance_error:
                    logger.warning(f"Error getting balances for wallet {wallet_data.get('id')}: {str(balance_error)}")
                    wallet_data["balances"] = {}
                
                wallet_data["last_updated"] = datetime.utcnow()
                wallet_data_list.append(wallet_data)
            
            # Cache the data
            if self.cache_enabled:
                with self._lock:
                    self._wallets[cache_key] = wallet_data_list
            
            return wallet_data_list
        
        except Exception as e:
            logger.error(f"Error getting wallets for user {user_id}: {str(e)}")
            raise
    
    def get_wallet_transactions(self, wallet_id: int, 
                              start_time: Optional[datetime] = None,
                              end_time: Optional[datetime] = None,
                              transaction_type: Optional[str] = None,
                              limit: int = 100,
                              offset: int = 0,
                              cache: bool = True) -> List[Dict[str, Any]]:
        """
        Get transactions for a wallet.
        
        Args:
            wallet_id: The wallet ID
            start_time: Start time for filtering transactions
            end_time: End time for filtering transactions
            transaction_type: Type of transaction to filter
            limit: Maximum number of transactions to return
            offset: Offset for pagination
            cache: Whether to use cached data if available
            
        Returns:
            List of transaction dictionaries
        """
        # Generate cache key based on parameters
        cache_key = f"wallet_transactions_{wallet_id}_{start_time}_{end_time}_{transaction_type}_{limit}_{offset}"
        if self.cache_enabled and cache and cache_key in self._transactions:
            logger.debug(f"Retrieved transactions for wallet {wallet_id} from cache")
            return self._transactions[cache_key]
        
        try:
            from src.account.transaction import get_wallet_transactions as fetch_wallet_transactions
            
            # Set default date range if not provided
            if not end_time:
                end_time = datetime.utcnow()
            if not start_time:
                start_time = end_time - timedelta(days=7)
            
            # Get transactions from database
            transactions = fetch_wallet_transactions(
                wallet_id=wallet_id,
                start_time=start_time,
                end_time=end_time,
                transaction_type=transaction_type,
                limit=limit,
                offset=offset
            )
            
            # Convert transactions to dictionaries
            transaction_list = [tx.dict() for tx in transactions]
            
            # Cache the data
            if self.cache_enabled:
                with self._lock:
                    self._transactions[cache_key] = transaction_list
            
            return transaction_list
        
        except Exception as e:
            logger.error(f"Error getting transactions for wallet {wallet_id}: {str(e)}")
            raise
    
    def detect_suspicious_activity(self, wallet_id: int) -> List[Dict[str, Any]]:
        """
        Detect suspicious activity for a wallet.
        
        Args:
            wallet_id: The wallet ID
            
        Returns:
            List of suspicious activity reports
        """
        try:
            # Get recent transactions for analysis
            recent_transactions = self.get_wallet_transactions(
                wallet_id=wallet_id,
                start_time=datetime.utcnow() - timedelta(days=30),
                limit=500,
                cache=False  # Always get fresh data for security analysis
            )
            
            # Implement detection logic
            suspicious_activities = []
            
            # 1. Check for unusually large transactions
            from src.account.wallet import get_wallet_by_id
            wallet = get_wallet_by_id(wallet_id)
            
            if wallet:
                # Get average transaction size
                if recent_transactions:
                    amounts = [tx.get("amount", 0) for tx in recent_transactions]
                    avg_amount = sum(amounts) / len(amounts)
                    std_dev = (sum((x - avg_amount) ** 2 for x in amounts) / len(amounts)) ** 0.5
                    
                    # Flag transactions that are significantly larger than average
                    threshold = avg_amount + (3 * std_dev)
                    
                    for tx in recent_transactions:
                        if tx.get("amount", 0) > threshold:
                            suspicious_activities.append({
                                "transaction_id": tx.get("transaction_id"),
                                "timestamp": tx.get("timestamp"),
                                "type": "large_transaction",
                                "description": f"Transaction amount ({tx.get('amount')}) is significantly larger than average ({avg_amount:.2f})",
                                "severity": "medium"
                            })
            
            # 2. Check for unusual transaction frequency
            # Group transactions by day
            from collections import defaultdict
            daily_counts = defaultdict(int)
            
            for tx in recent_transactions:
                if "timestamp" in tx and tx["timestamp"]:
                    date_key = tx["timestamp"].date()
                    daily_counts[date_key] += 1
            
            # Calculate average daily transactions
            if daily_counts:
                avg_daily = sum(daily_counts.values()) / len(daily_counts)
                
                # Flag days with unusual activity
                for date, count in daily_counts.items():
                    if count > (avg_daily * 3):
                        suspicious_activities.append({
                            "date": date,
                            "type": "high_frequency",
                            "description": f"Unusual number of transactions ({count}) on {date} compared to average ({avg_daily:.2f})",
                            "severity": "low"
                        })
            
            # 3. Check for multiple failed transactions
            failed_txs = [tx for tx in recent_transactions if tx.get("status") == "FAILED"]
            if len(failed_txs) >= 3:
                suspicious_activities.append({
                    "type": "multiple_failures",
                    "description": f"Multiple failed transactions detected ({len(failed_txs)} in the last 30 days)",
                    "severity": "medium",
                    "failed_transactions": [tx.get("transaction_id") for tx in failed_txs[:5]]  # Include up to 5 examples
                })
            
            return suspicious_activities
            
        except Exception as e:
            logger.error(f"Error detecting suspicious activity for wallet {wallet_id}: {str(e)}")
            raise
    
    def get_wallet_balance_history(self, wallet_id: int, 
                                 period: str = "week",
                                 asset: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get historical balance data for a wallet.
        
        Args:
            wallet_id: The wallet ID
            period: Time period ('day', 'week', 'month', 'year')
            asset: Specific asset to filter by
            
        Returns:
            List of balance history records
        """
        try:
            # Determine time range based on period
            end_time = datetime.utcnow()
            if period == "day":
                start_time = end_time - timedelta(days=1)
                interval = "hour"
            elif period == "week":
                start_time = end_time - timedelta(weeks=1)
                interval = "day"
            elif period == "month":
                start_time = end_time - timedelta(days=30)
                interval = "day"
            elif period == "year":
                start_time = end_time - timedelta(days=365)
                interval = "month"
            else:
                raise ValueError(f"Invalid period: {period}")
            
            # Fetch transaction history for the specified period
            transactions = self.get_wallet_transactions(
                wallet_id=wallet_id,
                start_time=start_time,
                end_time=end_time,
                limit=1000,
                cache=True
            )
            
            # Sort transactions by timestamp
            transactions.sort(key=lambda x: x.get("timestamp", datetime.min))
            
            # Get current balance
            from src.account.wallet import get_wallet_balances
            current_balances = get_wallet_balances(wallet_id)
            
            # Filter by asset if specified
            if asset:
                if asset in current_balances:
                    current_balance = current_balances[asset]
                else:
                    current_balance = 0
            else:
                # Use total balance in USD equivalent
                current_balance = sum(current_balances.values())
            
            # Work backwards from current balance
            balance_history = []
            running_balance = current_balance
            
            # Group transactions by interval
            grouped_txs = defaultdict(list)
            
            for tx in reversed(transactions):
                tx_time = tx.get("timestamp")
                if not tx_time:
                    continue
                
                # Generate interval key
                if interval == "hour":
                    interval_key = tx_time.replace(minute=0, second=0, microsecond=0)
                elif interval == "day":
                    interval_key = tx_time.replace(hour=0, minute=0, second=0, microsecond=0)
                elif interval == "month":
                    interval_key = tx_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                
                # Filter by asset if specified
                tx_asset = tx.get("asset")
                if asset and tx_asset != asset:
                    continue
                
                # Add transaction to group
                grouped_txs[interval_key].append(tx)
            
            # Calculate balance for each interval
            for interval_time, interval_txs in sorted(grouped_txs.items()):
                # Calculate net change for this interval
                interval_change = 0
                for tx in interval_txs:
                    if tx.get("transaction_type") in ["DEPOSIT", "TRANSFER_IN"]:
                        interval_change -= tx.get("amount", 0)  # Subtract deposits (working backwards)
                    elif tx.get("transaction_type") in ["WITHDRAWAL", "TRANSFER_OUT"]:
                        interval_change += tx.get("amount", 0)  # Add withdrawals (working backwards)
                
                # Update running balance
                running_balance -= interval_change
                
                # Add balance point
                balance_history.append({
                    "timestamp": interval_time,
                    "balance": running_balance,
                    "asset": asset
                })
            
            # Add starting point if there are no transactions
            if not balance_history:
                balance_history.append({
                    "timestamp": start_time,
                    "balance": current_balance,
                    "asset": asset
                })
            
            # Sort by timestamp (oldest first)
            balance_history.sort(key=lambda x: x["timestamp"])
            
            return balance_history
            
        except Exception as e:
            logger.error(f"Error getting balance history for wallet {wallet_id}: {str(e)}")
            raise
    
    def get_fund_allocation(self, wallet_id: int) -> Dict[str, float]:
        """
        Get fund allocation by asset for a wallet.
        
        Args:
            wallet_id: The wallet ID
            
        Returns:
            Dictionary mapping asset symbols to their percentage allocation
        """
        try:
            from src.account.wallet import get_wallet_balances
            
            # Get current balances
            balances = get_wallet_balances(wallet_id)
            
            # Calculate total value
            total_value = sum(balances.values())
            
            # Calculate percentages
            allocation = {}
            if total_value > 0:
                for asset, value in balances.items():
                    allocation[asset] = (value / total_value) * 100
            
            return allocation
            
        except Exception as e:
            logger.error(f"Error getting fund allocation for wallet {wallet_id}: {str(e)}")
            raise
    
    def clear_cache(self, wallet_id: Optional[int] = None):
        """
        Clear cached wallet data.
        
        Args:
            wallet_id: Specific wallet ID to clear, or None to clear all
        """
        with self._lock:
            if wallet_id:
                # Clear specific wallet cache
                cache_key = f"wallet_{wallet_id}"
                if cache_key in self._wallets:
                    del self._wallets[cache_key]
                
                # Clear transaction cache for this wallet
                for key in list(self._transactions.keys()):
                    if key.startswith(f"wallet_transactions_{wallet_id}"):
                        del self._transactions[key]
            else:
                # Clear all cache
                self._wallets.clear()
                self._transactions.clear()
        
        logger.debug(f"Cleared cache for wallet{f' {wallet_id}' if wallet_id else 's'}") 