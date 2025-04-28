import logging
from typing import Dict, List, Any, Optional
import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)

class WalletWidget:
    """Base class for all wallet-related widgets."""
    
    def __init__(self, wallet_id: str = None):
        """Initialize the wallet widget.
        
        Args:
            wallet_id: Optional ID of the wallet to display data for
        """
        self.wallet_id = wallet_id
        self.error = None
        self.last_updated = None
    
    def update(self, data: Any) -> bool:
        """Update the widget with new data.
        
        Args:
            data: The data to update the widget with
            
        Returns:
            True if successful, False otherwise
        """
        self.last_updated = datetime.datetime.now()
        return True
    
    def render(self) -> str:
        """Render the widget as HTML.
        
        Returns:
            HTML representation of the widget
        """
        if self.error:
            return f"""
            <div class="widget-error">
                <p>Error loading widget: {self.error}</p>
            </div>
            """
        
        return "<div>Base wallet widget</div>"


class WalletOverviewWidget(WalletWidget):
    """Widget showing an overview of wallet information."""
    
    def __init__(self, wallet_id: str = None):
        """Initialize the wallet overview widget."""
        super().__init__(wallet_id)
        self.wallet_data = None
        self.wallets = []
    
    def update(self, data: Dict[str, Any]) -> bool:
        """Update the widget with wallet data.
        
        Args:
            data: Dictionary containing:
                - active_wallet: Data for the active wallet
                - wallets: List of all available wallets
                
        Returns:
            True if successful, False otherwise
        """
        super().update(data)
        
        if not data:
            self.error = "No wallet data provided"
            return False
        
        self.wallet_data = data.get("active_wallet")
        self.wallets = data.get("wallets", [])
        self.wallet_id = self.wallet_data.get("id") if self.wallet_data else None
        
        return True
    
    def render(self) -> str:
        """Render the wallet overview widget."""
        if self.error:
            return super().render()
        
        if not self.wallet_data:
            return """
            <div class="wallet-overview-widget">
                <h3>Wallet Overview</h3>
                <p>No wallet selected</p>
            </div>
            """
        
        # Format the balance with 2 decimal places
        balance = self.wallet_data.get("balance", Decimal("0.00"))
        formatted_balance = f"{balance:.2f}"
        
        # Format the wallet creation date
        created_at = self.wallet_data.get("created_at")
        created_at_str = created_at.strftime("%b %d, %Y") if created_at else "Unknown"
        
        # Format the last active date
        last_active = self.wallet_data.get("last_active")
        last_active_str = last_active.strftime("%b %d, %Y %H:%M") if last_active else "Unknown"
        
        # Build the wallet dropdown options
        wallet_options = ""
        for wallet in self.wallets:
            selected = "selected" if wallet.get("id") == self.wallet_id else ""
            wallet_options += f'<option value="{wallet.get("id")}" {selected}>{wallet.get("name")}</option>'
        
        return f"""
        <div class="wallet-overview-widget">
            <div class="wallet-header">
                <h3>Wallet Overview</h3>
                <div class="wallet-selector">
                    <select id="wallet-select" onchange="switchWallet(this.value)">
                        {wallet_options}
                    </select>
                </div>
            </div>
            
            <div class="wallet-balance">
                <div class="balance-amount">{self.wallet_data.get("currency", "USD")} {formatted_balance}</div>
                <div class="wallet-name">{self.wallet_data.get("name", "Unnamed Wallet")}</div>
            </div>
            
            <div class="wallet-details">
                <div class="detail-item">
                    <span class="detail-label">Status:</span>
                    <span class="detail-value status-{self.wallet_data.get("status", "unknown")}">{self.wallet_data.get("status", "Unknown").capitalize()}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Type:</span>
                    <span class="detail-value">{self.wallet_data.get("type", "Unknown").capitalize()}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Risk Level:</span>
                    <span class="detail-value risk-{self.wallet_data.get("risk_level", "unknown")}">{self.wallet_data.get("risk_level", "Unknown").capitalize()}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Created:</span>
                    <span class="detail-value">{created_at_str}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Last Active:</span>
                    <span class="detail-value">{last_active_str}</span>
                </div>
            </div>
        </div>
        """


class TransactionHistoryWidget(WalletWidget):
    """Widget showing transaction history for a wallet."""
    
    def __init__(self, wallet_id: str = None):
        """Initialize the transaction history widget."""
        super().__init__(wallet_id)
        self.transactions = []
    
    def update(self, data: List[Dict[str, Any]]) -> bool:
        """Update the widget with transaction data.
        
        Args:
            data: List of transaction records
                
        Returns:
            True if successful, False otherwise
        """
        super().update(data)
        
        if data is None:
            self.error = "No transaction data provided"
            return False
        
        self.transactions = data
        return True
    
    def render(self) -> str:
        """Render the transaction history widget."""
        if self.error:
            return super().render()
        
        if not self.transactions:
            return """
            <div class="transaction-history-widget">
                <h3>Transaction History</h3>
                <p>No transactions available</p>
            </div>
            """
        
        # Build the transaction list
        transaction_rows = ""
        for tx in self.transactions[:10]:  # Limit to 10 most recent transactions
            amount = tx.get("amount", Decimal("0.00"))
            tx_type = tx.get("type", "unknown")
            
            # Format amount with sign based on transaction type
            if tx_type == "deposit":
                amount_str = f"+{amount:.2f}"
                amount_class = "amount-positive"
            elif tx_type == "withdraw":
                amount_str = f"-{amount:.2f}"
                amount_class = "amount-negative"
            else:
                amount_str = f"{amount:.2f}"
                amount_class = "amount-neutral"
            
            # Format timestamp
            timestamp = tx.get("timestamp")
            time_str = timestamp.strftime("%b %d, %H:%M") if timestamp else "Unknown"
            
            transaction_rows += f"""
            <tr class="tx-{tx_type}">
                <td class="tx-time">{time_str}</td>
                <td class="tx-type">{tx_type.capitalize()}</td>
                <td class="tx-description">{tx.get("description", "")}</td>
                <td class="tx-amount {amount_class}">{amount_str}</td>
            </tr>
            """
        
        return f"""
        <div class="transaction-history-widget">
            <div class="widget-header">
                <h3>Transaction History</h3>
                <button class="view-all-btn" onclick="viewAllTransactions()">View All</button>
            </div>
            
            <div class="transaction-list">
                <table>
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Type</th>
                            <th>Description</th>
                            <th>Amount</th>
                        </tr>
                    </thead>
                    <tbody>
                        {transaction_rows}
                    </tbody>
                </table>
            </div>
        </div>
        """


class FundAllocationWidget(WalletWidget):
    """Widget showing fund allocation across different assets."""
    
    def __init__(self, wallet_id: str = None):
        """Initialize the fund allocation widget."""
        super().__init__(wallet_id)
        self.allocations = {}
    
    def update(self, data: Dict[str, float]) -> bool:
        """Update the widget with allocation data.
        
        Args:
            data: Dict mapping asset types to allocation percentages
                
        Returns:
            True if successful, False otherwise
        """
        super().update(data)
        
        if data is None:
            self.error = "No allocation data provided"
            return False
        
        self.allocations = data
        return True
    
    def render(self) -> str:
        """Render the fund allocation widget."""
        if self.error:
            return super().render()
        
        if not self.allocations:
            return """
            <div class="fund-allocation-widget">
                <h3>Fund Allocation</h3>
                <p>No allocation data available</p>
            </div>
            """
        
        # Generate the allocation chart
        allocation_bars = ""
        for asset, percentage in sorted(self.allocations.items(), key=lambda x: x[1], reverse=True):
            # Convert to percentage format
            percent_str = f"{percentage * 100:.1f}%"
            
            allocation_bars += f"""
            <div class="allocation-item">
                <div class="asset-label">{asset}</div>
                <div class="allocation-bar-container">
                    <div class="allocation-bar asset-{asset.lower()}" style="width: {percent_str};"></div>
                </div>
                <div class="allocation-percentage">{percent_str}</div>
            </div>
            """
        
        return f"""
        <div class="fund-allocation-widget">
            <h3>Fund Allocation</h3>
            
            <div class="allocation-chart">
                {allocation_bars}
            </div>
        </div>
        """


class BalanceHistoryWidget(WalletWidget):
    """Widget showing balance history over time."""
    
    def __init__(self, wallet_id: str = None):
        """Initialize the balance history widget."""
        super().__init__(wallet_id)
        self.history = []
    
    def update(self, data: List[Dict[str, Any]]) -> bool:
        """Update the widget with balance history data.
        
        Args:
            data: List of balance history records
                
        Returns:
            True if successful, False otherwise
        """
        super().update(data)
        
        if data is None:
            self.error = "No balance history data provided"
            return False
        
        self.history = data
        return True
    
    def render(self) -> str:
        """Render the balance history widget."""
        if self.error:
            return super().render()
        
        if not self.history:
            return """
            <div class="balance-history-widget">
                <h3>Balance History</h3>
                <p>No history data available</p>
            </div>
            """
        
        # Filter to include only data points at regular intervals
        # For simplicity, take a data point every 5 days
        filtered_history = [entry for i, entry in enumerate(self.history) if i % 5 == 0]
        
        # Prepare data for the chart
        dates = []
        balances = []
        
        for entry in filtered_history:
            date = entry.get("date")
            dates.append(date.strftime("%m/%d") if date else "")
            balances.append(float(entry.get("balance", 0)))
        
        # Calculate statistics
        if balances:
            current_balance = balances[-1]
            initial_balance = balances[0]
            change = current_balance - initial_balance
            change_percent = (change / initial_balance * 100) if initial_balance else 0
            
            # Determine color based on change
            if change > 0:
                change_color = "positive"
                change_sign = "+"
            elif change < 0:
                change_color = "negative"
                change_sign = "-"
            else:
                change_color = "neutral"
                change_sign = ""
        else:
            current_balance = 0
            change = 0
            change_percent = 0
            change_color = "neutral"
            change_sign = ""
        
        # Convert to JavaScript arrays for chart
        dates_js = ", ".join([f"'{date}'" for date in dates])
        balances_js = ", ".join([str(balance) for balance in balances])
        
        return f"""
        <div class="balance-history-widget">
            <h3>Balance History</h3>
            
            <div class="balance-summary">
                <div class="current-balance">${current_balance:.2f}</div>
                <div class="balance-change {change_color}">
                    <span>{change_sign}${abs(change):.2f} ({change_sign}{abs(change_percent):.1f}%)</span>
                </div>
            </div>
            
            <canvas id="balance-chart" width="100%" height="200"></canvas>
            
            <script>
                // Create balance chart
                const ctx = document.getElementById('balance-chart').getContext('2d');
                new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: [{dates_js}],
                        datasets: [{
                            label: 'Balance',
                            data: [{balances_js}],
                            borderColor: '#4A90E2',
                            borderWidth: 2,
                            pointRadius: 0,
                            fill: false,
                            tension: 0.4
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                display: true,
                                grid: {
                                    display: false
                                }
                            },
                            y: {
                                display: true,
                                beginAtZero: false
                            }
                        },
                        plugins: {
                            legend: {
                                display: false
                            }
                        }
                    }
                });
            </script>
        </div>
        """


class AlertsWidget(WalletWidget):
    """Widget showing security alerts for a wallet."""
    
    def __init__(self, wallet_id: str = None):
        """Initialize the alerts widget."""
        super().__init__(wallet_id)
        self.alerts = []
    
    def update(self, data: List[Dict[str, Any]]) -> bool:
        """Update the widget with alerts data.
        
        Args:
            data: List of alert records
                
        Returns:
            True if successful, False otherwise
        """
        super().update(data)
        
        if data is None:
            self.error = "No alerts data provided"
            return False
        
        self.alerts = data
        return True
    
    def render(self) -> str:
        """Render the alerts widget."""
        if self.error:
            return super().render()
        
        # Count unread alerts that require action
        action_required_count = sum(1 for alert in self.alerts if alert.get("action_required") and not alert.get("is_read"))
        
        if not self.alerts:
            return """
            <div class="alerts-widget">
                <h3>Security Alerts</h3>
                <div class="empty-alerts">
                    <i class="fa fa-shield-alt"></i>
                    <p>No security alerts</p>
                </div>
            </div>
            """
        
        # Build alert items
        alert_items = ""
        for alert in self.alerts[:5]:  # Show only the 5 most recent alerts
            severity = alert.get("severity", "low")
            alert_type = alert.get("type", "unknown")
            is_read = alert.get("is_read", False)
            
            # Style based on severity and read status
            severity_class = f"severity-{severity}"
            read_class = "" if is_read else "unread"
            
            # Format timestamp
            timestamp = alert.get("timestamp")
            time_str = timestamp.strftime("%b %d") if timestamp else "Unknown"
            
            alert_items += f"""
            <div class="alert-item {severity_class} {read_class}">
                <div class="alert-icon">
                    <i class="fa fa-exclamation-triangle"></i>
                </div>
                <div class="alert-content">
                    <div class="alert-description">{alert.get("description", "Unknown alert")}</div>
                    <div class="alert-meta">
                        <span class="alert-type">{alert_type.replace("_", " ").title()}</span>
                        <span class="alert-time">{time_str}</span>
                    </div>
                </div>
            </div>
            """
        
        action_badge = ""
        if action_required_count > 0:
            action_badge = f"""
            <div class="action-badge">{action_required_count}</div>
            """
        
        return f"""
        <div class="alerts-widget">
            <div class="widget-header">
                <h3>Security Alerts</h3>
                {action_badge}
                <button class="view-all-btn" onclick="viewAllAlerts()">View All</button>
            </div>
            
            <div class="alerts-list">
                {alert_items}
            </div>
        </div>
        """


class WalletActionsWidget(WalletWidget):
    """Widget for wallet actions like deposit, withdraw, etc."""
    
    def __init__(self, wallet_id: str = None):
        """Initialize the wallet actions widget."""
        super().__init__(wallet_id)
    
    def update(self, data: Dict[str, Any]) -> bool:
        """Update the widget with wallet data.
        
        Args:
            data: Wallet data
                
        Returns:
            True if successful, False otherwise
        """
        super().update(data)
        
        if data is None:
            self.error = "No wallet data provided"
            return False
        
        self.wallet_id = data.get("id")
        return True
    
    def render(self) -> str:
        """Render the wallet actions widget."""
        if self.error:
            return super().render()
        
        if not self.wallet_id:
            return """
            <div class="wallet-actions-widget">
                <h3>Wallet Actions</h3>
                <p>No wallet selected</p>
            </div>
            """
        
        return f"""
        <div class="wallet-actions-widget">
            <h3>Quick Actions</h3>
            
            <div class="action-buttons">
                <button class="action-btn deposit-btn" onclick="showDepositModal('{self.wallet_id}')">
                    <i class="fa fa-arrow-down"></i>
                    <span>Deposit</span>
                </button>
                
                <button class="action-btn withdraw-btn" onclick="showWithdrawModal('{self.wallet_id}')">
                    <i class="fa fa-arrow-up"></i>
                    <span>Withdraw</span>
                </button>
                
                <button class="action-btn transfer-btn" onclick="showTransferModal('{self.wallet_id}')">
                    <i class="fa fa-exchange-alt"></i>
                    <span>Transfer</span>
                </button>
                
                <button class="action-btn settings-btn" onclick="showWalletSettings('{self.wallet_id}')">
                    <i class="fa fa-cog"></i>
                    <span>Settings</span>
                </button>
            </div>
        </div>
        """ 