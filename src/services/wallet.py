import logging
import datetime
import random
from typing import Dict, List, Any, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)

class WalletService:
    """Service for managing wallet data and operations."""
    
    def __init__(self):
        """Initialize the wallet service with mock data."""
        self._active_wallet_id = "main"
        self._wallets = {
            "main": {
                "id": "main",
                "name": "Main Trading Wallet",
                "balance": Decimal("10000.00"),
                "currency": "USD",
                "created_at": datetime.datetime.now() - datetime.timedelta(days=90),
                "last_active": datetime.datetime.now(),
                "status": "active",
                "type": "trading",
                "is_default": True,
                "risk_level": "medium"
            },
            "savings": {
                "id": "savings",
                "name": "Savings Wallet",
                "balance": Decimal("5000.00"),
                "currency": "USD",
                "created_at": datetime.datetime.now() - datetime.timedelta(days=60),
                "last_active": datetime.datetime.now() - datetime.timedelta(days=5),
                "status": "active",
                "type": "savings",
                "is_default": False,
                "risk_level": "low"
            },
            "high-risk": {
                "id": "high-risk",
                "name": "High Risk Trading",
                "balance": Decimal("2500.00"),
                "currency": "USD",
                "created_at": datetime.datetime.now() - datetime.timedelta(days=30),
                "last_active": datetime.datetime.now() - datetime.timedelta(days=2),
                "status": "active",
                "type": "trading",
                "is_default": False,
                "risk_level": "high"
            }
        }
        
        # Generate mock transaction history
        self._transactions = self._generate_mock_transactions()
        
        # Generate mock balance history
        self._balance_history = self._generate_mock_balance_history()
        
        # Generate mock fund allocation
        self._allocations = self._generate_mock_allocations()
        
        # Generate mock alerts
        self._alerts = self._generate_mock_alerts()
        
        logger.info("Wallet service initialized with mock data")
    
    def get_wallets(self) -> Dict[str, Dict[str, Any]]:
        """Get all available wallets.
        
        Returns:
            Dict of wallet IDs to wallet data
        """
        return self._wallets
    
    def get_wallet(self, wallet_id: str) -> Optional[Dict[str, Any]]:
        """Get data for a specific wallet.
        
        Args:
            wallet_id: The ID of the wallet to retrieve
            
        Returns:
            Wallet data or None if not found
        """
        return self._wallets.get(wallet_id)
    
    def get_active_wallet(self) -> Optional[Dict[str, Any]]:
        """Get the currently active wallet.
        
        Returns:
            Active wallet data or None if no active wallet
        """
        return self._wallets.get(self._active_wallet_id)
    
    def set_active_wallet(self, wallet_id: str) -> bool:
        """Set the active wallet.
        
        Args:
            wallet_id: The ID of the wallet to set as active
            
        Returns:
            True if successful, False otherwise
        """
        if wallet_id in self._wallets:
            self._active_wallet_id = wallet_id
            return True
        return False
    
    def get_transactions(self, wallet_id: str) -> List[Dict[str, Any]]:
        """Get transaction history for a wallet.
        
        Args:
            wallet_id: The ID of the wallet to get transactions for
            
        Returns:
            List of transaction records
        """
        if wallet_id not in self._transactions:
            return []
        return self._transactions[wallet_id]
    
    def get_balance_history(self, wallet_id: str) -> List[Dict[str, Any]]:
        """Get balance history for a wallet.
        
        Args:
            wallet_id: The ID of the wallet to get balance history for
            
        Returns:
            List of balance history records
        """
        if wallet_id not in self._balance_history:
            return []
        return self._balance_history[wallet_id]
    
    def get_allocation(self, wallet_id: str) -> Dict[str, float]:
        """Get fund allocation for a wallet.
        
        Args:
            wallet_id: The ID of the wallet to get allocation for
            
        Returns:
            Dict mapping asset types to allocation percentages
        """
        if wallet_id not in self._allocations:
            return {}
        return self._allocations[wallet_id]
    
    def get_alerts(self, wallet_id: str) -> List[Dict[str, Any]]:
        """Get security alerts for a wallet.
        
        Args:
            wallet_id: The ID of the wallet to get alerts for
            
        Returns:
            List of alert records
        """
        if wallet_id not in self._alerts:
            return []
        return self._alerts[wallet_id]
    
    def add_transaction(self, wallet_id: str, transaction_type: str, 
                        amount: Decimal, description: str = None) -> bool:
        """Add a new transaction to a wallet.
        
        Args:
            wallet_id: The ID of the wallet to add transaction to
            transaction_type: Type of transaction ('deposit', 'withdraw', 'transfer')
            amount: Transaction amount
            description: Optional transaction description
            
        Returns:
            True if successful, False otherwise
        """
        if wallet_id not in self._wallets:
            return False
        
        wallet = self._wallets[wallet_id]
        
        # Create transaction record
        transaction = {
            "id": f"tx-{random.randint(1000000, 9999999)}",
            "wallet_id": wallet_id,
            "type": transaction_type,
            "amount": amount,
            "balance_after": wallet["balance"] + amount if transaction_type == "deposit" else wallet["balance"] - amount,
            "timestamp": datetime.datetime.now(),
            "status": "completed",
            "description": description or f"{transaction_type.capitalize()} transaction"
        }
        
        # Update wallet balance
        if transaction_type == "deposit":
            wallet["balance"] += amount
        elif transaction_type == "withdraw":
            if wallet["balance"] < amount:
                return False
            wallet["balance"] -= amount
        
        # Add to transaction history
        if wallet_id not in self._transactions:
            self._transactions[wallet_id] = []
        self._transactions[wallet_id].insert(0, transaction)
        
        # Update last active time
        wallet["last_active"] = datetime.datetime.now()
        
        return True
    
    def _generate_mock_transactions(self) -> Dict[str, List[Dict[str, Any]]]:
        """Generate mock transaction history for all wallets.
        
        Returns:
            Dict mapping wallet IDs to lists of transaction records
        """
        transactions = {}
        
        for wallet_id, wallet in self._wallets.items():
            wallet_transactions = []
            
            # Number of transactions to generate
            num_transactions = random.randint(10, 30)
            
            # Starting balance
            balance = Decimal("0.00")
            
            for i in range(num_transactions):
                # Random transaction amount
                amount = Decimal(str(random.uniform(100, 1000))).quantize(Decimal("0.01"))
                
                # Random transaction type with bias towards deposits for a positive balance
                tx_type = random.choices(
                    ["deposit", "withdraw", "transfer"], 
                    weights=[0.6, 0.3, 0.1]
                )[0]
                
                # Ensure we don't go negative
                if tx_type == "withdraw" and balance < amount:
                    tx_type = "deposit"
                
                # Update balance
                if tx_type == "deposit":
                    balance += amount
                elif tx_type == "withdraw":
                    balance -= amount
                
                # Random timestamp in the past 90 days
                days_ago = random.randint(0, 90)
                timestamp = datetime.datetime.now() - datetime.timedelta(days=days_ago, 
                                                                        hours=random.randint(0, 23),
                                                                        minutes=random.randint(0, 59))
                
                # Create transaction record
                transaction = {
                    "id": f"tx-{random.randint(1000000, 9999999)}",
                    "wallet_id": wallet_id,
                    "type": tx_type,
                    "amount": amount,
                    "balance_after": balance,
                    "timestamp": timestamp,
                    "status": "completed",
                    "description": f"Mock {tx_type} transaction #{i+1}"
                }
                
                wallet_transactions.append(transaction)
            
            # Sort by timestamp, most recent first
            wallet_transactions.sort(key=lambda x: x["timestamp"], reverse=True)
            
            transactions[wallet_id] = wallet_transactions
        
        return transactions
    
    def _generate_mock_balance_history(self) -> Dict[str, List[Dict[str, Any]]]:
        """Generate mock balance history for all wallets.
        
        Returns:
            Dict mapping wallet IDs to lists of balance history records
        """
        balance_history = {}
        
        for wallet_id, wallet in self._wallets.items():
            history = []
            
            # Start with a base balance
            base_balance = Decimal("1000.00")
            
            # Generate daily balance entries for the past 90 days
            for days_ago in range(90, -1, -1):
                date = datetime.datetime.now() - datetime.timedelta(days=days_ago)
                
                # Add some random fluctuation to the balance
                change = Decimal(str(random.uniform(-50, 100))).quantize(Decimal("0.01"))
                
                # Add a trend component
                trend = Decimal(str(days_ago * 100 / 90)).quantize(Decimal("0.01"))
                
                # Combine base, trend, and random component
                balance = base_balance + trend + change
                
                # Ensure always positive
                if balance < Decimal("100.00"):
                    balance = Decimal("100.00")
                
                history.append({
                    "date": date,
                    "balance": balance,
                    "change_percent": Decimal(str(random.uniform(-2, 3))).quantize(Decimal("0.01"))
                })
                
                # Update base balance for next day
                base_balance = balance
            
            balance_history[wallet_id] = history
        
        return balance_history
    
    def _generate_mock_allocations(self) -> Dict[str, Dict[str, float]]:
        """Generate mock fund allocations for all wallets.
        
        Returns:
            Dict mapping wallet IDs to dicts of asset type -> percentage
        """
        allocations = {}
        
        # Default asset types
        asset_types = ["USD", "EUR", "GBP", "JPY", "CAD", "AUD"]
        
        for wallet_id, wallet in self._wallets.items():
            # Different allocation strategy based on risk level
            risk_level = wallet.get("risk_level", "medium")
            
            if risk_level == "low":
                # Low risk: More in USD, fewer currencies
                assets = asset_types[:3]
                allocation = {"USD": 0.7}
                remaining = 0.3
                for asset in assets[1:]:
                    if remaining > 0:
                        share = round(random.uniform(0.05, remaining - 0.05), 2)
                        allocation[asset] = share
                        remaining -= share
                
                # Assign any remainder to the last asset
                if remaining > 0:
                    allocation[assets[-1]] += remaining
                
            elif risk_level == "high":
                # High risk: More diverse, less in USD
                assets = asset_types
                allocation = {"USD": 0.3}
                remaining = 0.7
                
                for asset in assets[1:]:
                    if remaining > 0:
                        share = round(random.uniform(0.05, remaining - 0.05 if len(assets) > 2 else remaining), 2)
                        allocation[asset] = share
                        remaining -= share
                
                # Assign any remainder to the last asset
                if remaining > 0:
                    allocation[assets[-1]] += remaining
                
            else:  # medium
                # Medium risk: Balanced approach
                assets = asset_types[:5]
                allocation = {"USD": 0.5}
                remaining = 0.5
                
                for asset in assets[1:]:
                    if remaining > 0:
                        share = round(random.uniform(0.05, remaining - 0.05 if len(assets) > 2 else remaining), 2)
                        allocation[asset] = share
                        remaining -= share
                
                # Assign any remainder to the last asset
                if remaining > 0:
                    allocation[assets[-1]] += remaining
            
            allocations[wallet_id] = allocation
        
        return allocations
    
    def _generate_mock_alerts(self) -> Dict[str, List[Dict[str, Any]]]:
        """Generate mock security alerts for all wallets.
        
        Returns:
            Dict mapping wallet IDs to lists of alert records
        """
        alerts = {}
        
        alert_types = [
            "login_attempt", "large_withdrawal", "suspicious_transfer",
            "password_changed", "new_device", "security_update"
        ]
        
        severity_mapping = {
            "login_attempt": "medium",
            "large_withdrawal": "high",
            "suspicious_transfer": "high",
            "password_changed": "low",
            "new_device": "medium",
            "security_update": "low"
        }
        
        for wallet_id, wallet in self._wallets.items():
            wallet_alerts = []
            
            # Number of alerts to generate (0-5)
            num_alerts = random.randint(0, 5)
            
            for i in range(num_alerts):
                alert_type = random.choice(alert_types)
                severity = severity_mapping[alert_type]
                
                # Random timestamp in the past 30 days
                days_ago = random.randint(0, 30)
                timestamp = datetime.datetime.now() - datetime.timedelta(days=days_ago,
                                                                        hours=random.randint(0, 23),
                                                                        minutes=random.randint(0, 59))
                
                descriptions = {
                    "login_attempt": "Multiple failed login attempts detected",
                    "large_withdrawal": f"Large withdrawal of ${random.randint(1000, 5000)} detected",
                    "suspicious_transfer": f"Suspicious transfer to unknown account detected",
                    "password_changed": "Password was changed recently",
                    "new_device": "New device detected accessing your wallet",
                    "security_update": "Security update available for your wallet"
                }
                
                alert = {
                    "id": f"alert-{random.randint(1000, 9999)}",
                    "wallet_id": wallet_id,
                    "type": alert_type,
                    "severity": severity,
                    "timestamp": timestamp,
                    "description": descriptions[alert_type],
                    "is_read": random.choice([True, False]),
                    "action_required": severity in ["medium", "high"]
                }
                
                wallet_alerts.append(alert)
            
            # Sort by timestamp, most recent first
            wallet_alerts.sort(key=lambda x: x["timestamp"], reverse=True)
            
            alerts[wallet_id] = wallet_alerts
        
        return alerts 