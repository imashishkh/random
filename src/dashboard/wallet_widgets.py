"""
Wallet management and fund monitoring widgets for the Forex Trading dashboard.
"""
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Union
from collections import defaultdict

from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.console import Group
from rich.progress_bar import ProgressBar
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, DataTable, Label, Button, Input, Select, BarChart, Sparkline
from textual.reactive import reactive
import asyncio

from .utils import (
    format_bytes, 
    format_time_delta, 
    format_currency, 
    format_percentage, 
    format_time
)

from rich.sparkline import Sparkline as RichSparkline
from rich.progress import Progress, BarColumn, TextColumn, TaskID
import logging

logger = logging.getLogger(__name__)

class WalletOverviewWidget(Static):
    """Widget displaying basic wallet information."""
    
    wallet_data = reactive({})
    
    def __init__(self, title: str = "Wallet Overview", **kwargs):
        super().__init__(**kwargs)
        self.panel_title = title
    
    def compose(self) -> ComposeResult:
        """Create child widgets for the wallet overview."""
        yield Container(
            Label(self.panel_title, id="wallet-title", classes="widget-title"),
            Horizontal(
                # Left side with basic info
                Vertical(
                    Static(id="wallet-info", classes="wallet-info"),
                    classes="wallet-info-container"
                ),
                # Right side with balance chart
                Vertical(
                    Static(id="wallet-balance", classes="wallet-balance"),
                    classes="wallet-balance-container"
                ),
                id="wallet-overview-content"
            )
        )
    
    def on_mount(self) -> None:
        """Initialize the widget when mounted."""
        self.refresh_wallet_data()
    
    def refresh_wallet_data(self) -> None:
        """Update the wallet overview display with current data."""
        # Update wallet info section
        wallet_info = self.query_one("#wallet-info")
        wallet_balance = self.query_one("#wallet-balance")
        
        if not self.wallet_data:
            wallet_info.update("No wallet data available")
            wallet_balance.update("")
            return
        
        # Create wallet info text
        info_text = Text()
        
        # Wallet name and type
        wallet_name = self.wallet_data.get("name", "Unnamed Wallet")
        wallet_type = self.wallet_data.get("wallet_type", "unknown").upper()
        
        info_text.append(f"[bold]{wallet_name}[/bold]\n")
        
        # Wallet type with appropriate color
        type_colors = {
            "HOT": "yellow",
            "COLD": "blue",
            "EXCHANGE": "green",
            "MULTISIG": "magenta"
        }
        type_color = type_colors.get(wallet_type, "white")
        info_text.append(f"Type: ", style="dim")
        info_text.append(f"{wallet_type}\n", style=type_color)
        
        # Wallet address with truncation
        address = self.wallet_data.get("address", "No address")
        truncated_address = f"{address[:6]}...{address[-4:]}" if len(address) > 10 else address
        info_text.append(f"Address: {truncated_address}\n")
        
        # Last updated timestamp
        last_updated = self.wallet_data.get("last_updated", datetime.utcnow())
        if isinstance(last_updated, str):
            try:
                last_updated = datetime.fromisoformat(last_updated)
            except ValueError:
                last_updated = datetime.utcnow()
        
        info_text.append(f"Last Updated: {format_time(last_updated)}\n\n")
        
        # Balance information
        balances = self.wallet_data.get("balances", {})
        if balances:
            info_text.append("[bold]Assets:[/bold]\n")
            
            # Sort balances by value (descending)
            sorted_balances = sorted(balances.items(), key=lambda x: x[1], reverse=True)
            
            for asset, value in sorted_balances:
                info_text.append(f"{asset}: ")
                info_text.append(f"{format_currency(value, asset)}\n", 
                               style="green" if value > 0 else "red")
        
        wallet_info.update(info_text)
        
        # Create balance visualization
        balance_text = Text()
        balance_text.append("[bold]Balance Distribution[/bold]\n\n")
        
        # Calculate total balance
        total_balance = sum(balances.values())
        
        if total_balance > 0:
            # Show top 5 assets as bars
            top_assets = sorted_balances[:5]
            
            for asset, value in top_assets:
                percentage = (value / total_balance) * 100
                bar_width = min(int(percentage / 2), 50)  # Adjust scale for display
                
                balance_text.append(f"{asset}: ")
                balance_text.append(f"{format_percentage(percentage)}\n")
                
                # Add progress bar
                bar = ProgressBar(completed=bar_width, total=50)
                balance_text.append(str(bar) + "\n")
        else:
            balance_text.append("No balance data available\n")
        
        wallet_balance.update(balance_text)
    
    def update_wallet_data(self, wallet_data: Dict[str, Any]) -> None:
        """Update wallet data and refresh the display."""
        self.wallet_data = wallet_data
        self.refresh_wallet_data()


class TransactionHistoryWidget(Static):
    """Widget displaying wallet transaction history."""
    
    transactions = reactive([])
    transaction_types = reactive([])
    current_filter = reactive("")
    
    def __init__(self, title: str = "Transaction History", **kwargs):
        super().__init__(**kwargs)
        self.panel_title = title
        self.transaction_types = ["ALL", "DEPOSIT", "WITHDRAWAL", "TRANSFER"]
    
    def compose(self) -> ComposeResult:
        """Create child widgets for the transaction history."""
        yield Container(
            Label(self.panel_title, id="transactions-title", classes="widget-title"),
            Horizontal(
                # Filter controls
                Select(
                    ((type, type) for type in self.transaction_types),
                    value="ALL",
                    id="transaction-type-filter"
                ),
                Button("Refresh", id="refresh-transactions"),
                id="transaction-controls"
            ),
            # Transaction table
            Static(id="transaction-table"),
            id="transaction-container"
        )
    
    def on_mount(self) -> None:
        """Initialize the widget when mounted."""
        self.refresh_transactions()
        
        # Connect button event
        self.query_one("#refresh-transactions").on_click = self.handle_refresh_click
        
        # Connect filter event
        self.query_one("#transaction-type-filter").on_change = self.handle_filter_change
    
    def handle_refresh_click(self, event):
        """Handle refresh button click event."""
        self.refresh_transactions()
    
    def handle_filter_change(self, event):
        """Handle transaction type filter change event."""
        self.current_filter = event.select.value
        self.refresh_transactions()
    
    def refresh_transactions(self) -> None:
        """Update the transaction history display with current data."""
        table_widget = self.query_one("#transaction-table")
        
        # Create table
        table = Table(expand=True)
        table.add_column("Date")
        table.add_column("Type")
        table.add_column("Asset")
        table.add_column("Amount", justify="right")
        table.add_column("Status")
        
        # Filter transactions if needed
        filtered_transactions = self.transactions
        if self.current_filter and self.current_filter != "ALL":
            filtered_transactions = [
                tx for tx in self.transactions
                if tx.get("transaction_type", "") == self.current_filter
            ]
        
        # Add rows
        for tx in filtered_transactions:
            tx_time = tx.get("timestamp")
            if isinstance(tx_time, str):
                try:
                    tx_time = datetime.fromisoformat(tx_time)
                except ValueError:
                    tx_time = None
            
            tx_type = tx.get("transaction_type", "")
            tx_asset = tx.get("asset", "")
            tx_amount = tx.get("amount", 0)
            tx_status = tx.get("status", "UNKNOWN")
            
            # Format timestamp
            formatted_time = format_time(tx_time) if tx_time else "Unknown"
            
            # Style based on transaction type
            type_style = ""
            if tx_type == "DEPOSIT":
                type_style = "green"
            elif tx_type == "WITHDRAWAL":
                type_style = "red"
            elif tx_type == "TRANSFER":
                type_style = "yellow"
            
            # Style based on status
            status_style = ""
            if tx_status == "PENDING":
                status_style = "yellow"
            elif tx_status == "CONFIRMED":
                status_style = "green"
            elif tx_status == "FAILED":
                status_style = "red"
            
            # Format amount with sign
            amount_str = format_currency(tx_amount, tx_asset)
            amount_style = "green" if tx_type == "DEPOSIT" else "red" if tx_type == "WITHDRAWAL" else ""
            
            table.add_row(
                formatted_time,
                tx_type,
                tx_asset,
                amount_str,
                tx_status,
                style=None,
                end_section=(tx != filtered_transactions[-1])
            )
        
        # If no transactions
        if not filtered_transactions:
            table.add_row("No transactions found", "", "", "", "")
        
        table_widget.update(table)
    
    def update_transactions(self, transactions: List[Dict[str, Any]]) -> None:
        """Update transaction data and refresh the display."""
        self.transactions = transactions
        self.refresh_transactions()


class FundAllocationWidget(Static):
    """Widget displaying fund allocation across different assets."""
    
    allocation = reactive({})
    
    def __init__(self, title: str = "Fund Allocation", **kwargs):
        super().__init__(**kwargs)
        self.panel_title = title
    
    def compose(self) -> ComposeResult:
        """Create child widgets for the fund allocation."""
        yield Container(
            Label(self.panel_title, id="allocation-title", classes="widget-title"),
            Static(id="allocation-chart"),
            id="allocation-container"
        )
    
    def on_mount(self) -> None:
        """Initialize the widget when mounted."""
        self.refresh_allocation()
    
    def refresh_allocation(self) -> None:
        """Update the fund allocation display with current data."""
        chart_widget = self.query_one("#allocation-chart")
        
        if not self.allocation:
            chart_widget.update("No allocation data available")
            return
        
        # Create allocation visualization
        chart_text = Text()
        
        # Sort by percentage (descending)
        sorted_allocation = sorted(self.allocation.items(), key=lambda x: x[1], reverse=True)
        
        for asset, percentage in sorted_allocation:
            # Skip very small allocations
            if percentage < 1.0:
                continue
                
            # Calculate bar length based on percentage
            bar_length = min(int(percentage / 2), 50)
            bar = "■" * bar_length
            
            # Use different colors for different assets
            asset_colors = {
                "BTC": "bright_yellow",
                "ETH": "blue",
                "USDT": "green",
                "BNB": "bright_yellow",
                "SOL": "purple",
                "USDC": "blue"
            }
            
            color = asset_colors.get(asset, "white")
            
            chart_text.append(f"{asset}: ")
            chart_text.append(f"{format_percentage(percentage, False)}", style="bold")
            chart_text.append(" ")
            chart_text.append(f"{bar}\n", style=color)
        
        # Add "Others" category for small allocations
        small_allocations = [item for item in sorted_allocation if item[1] < 1.0]
        if small_allocations:
            total_small = sum(item[1] for item in small_allocations)
            if total_small > 0:
                bar_length = min(int(total_small / 2), 50)
                bar = "■" * bar_length
                
                chart_text.append("Others: ")
                chart_text.append(f"{format_percentage(total_small, False)}", style="bold")
                chart_text.append(" ")
                chart_text.append(f"{bar}\n", style="dim")
        
        chart_widget.update(chart_text)
    
    def update_allocation(self, allocation: Dict[str, float]) -> None:
        """Update allocation data and refresh the display."""
        self.allocation = allocation
        self.refresh_allocation()


class BalanceHistoryWidget(Static):
    """Widget displaying balance history over time."""
    
    balance_data = reactive([])
    current_period = reactive("week")
    current_asset = reactive(None)
    
    def __init__(self, title: str = "Balance History", **kwargs):
        super().__init__(**kwargs)
        self.panel_title = title
    
    def compose(self) -> ComposeResult:
        """Create child widgets for the balance history."""
        yield Container(
            Label(self.panel_title, id="history-title", classes="widget-title"),
            Horizontal(
                # Period selection
                Select(
                    ((period, period.capitalize()) for period in ["day", "week", "month", "year"]),
                    value="week",
                    id="period-selector"
                ),
                # Asset selection (will be populated later)
                Select(
                    [(None, "All Assets")],
                    value=None,
                    id="asset-selector"
                ),
                id="history-controls"
            ),
            Static(id="history-chart"),
            id="history-container"
        )
    
    def on_mount(self) -> None:
        """Initialize the widget when mounted."""
        self.refresh_history()
        
        # Connect period selector
        self.query_one("#period-selector").on_change = self.handle_period_change
        
        # Connect asset selector
        self.query_one("#asset-selector").on_change = self.handle_asset_change
    
    def handle_period_change(self, event):
        """Handle period selection change event."""
        self.current_period = event.select.value
        self.refresh_history()
    
    def handle_asset_change(self, event):
        """Handle asset selection change event."""
        self.current_asset = event.select.value
        self.refresh_history()
    
    def update_asset_options(self, assets: List[str]):
        """Update the asset selector options."""
        asset_selector = self.query_one("#asset-selector")
        
        # Create options list with "All Assets" as the first option
        options = [(None, "All Assets")]
        options.extend([(asset, asset) for asset in assets])
        
        # Update selector
        asset_selector.options = options
    
    def refresh_history(self) -> None:
        """Update the balance history display with current data."""
        chart_widget = self.query_one("#history-chart")
        
        if not self.balance_data:
            chart_widget.update("No balance history data available")
            return
        
        # Filter by asset if needed
        filtered_history = self.balance_data
        if self.current_asset:
            filtered_history = [
                point for point in self.balance_data
                if point.get("asset") == self.current_asset
            ]
        
        # Sort by timestamp
        filtered_history.sort(key=lambda x: x.get("timestamp", datetime.min))
        
        # Create ASCII chart
        chart_text = Text()
        chart_text.append(f"[bold]Balance History ({self.current_period.capitalize()})[/bold]\n\n")
        
        if not filtered_history:
            chart_text.append("No data for the selected filters")
            chart_widget.update(chart_text)
            return
        
        # Find min and max values for scaling
        min_balance = min(point.get("balance", 0) for point in filtered_history)
        max_balance = max(point.get("balance", 0) for point in filtered_history)
        
        # Ensure there's a range to display
        if min_balance == max_balance:
            min_balance = 0.9 * min_balance if min_balance > 0 else 0
        
        # Constants for chart
        chart_height = 10
        chart_width = 40
        
        # Calculate scaling factor
        value_range = max_balance - min_balance
        scale = chart_height / value_range if value_range > 0 else 1
        
        # Determine time format based on period
        if self.current_period == "day":
            time_format = "%H:%M"
        elif self.current_period == "week" or self.current_period == "month":
            time_format = "%d %b"
        else:  # year
            time_format = "%b %Y"
        
        # Create empty chart grid
        chart_grid = [[" " for _ in range(chart_width)] for _ in range(chart_height)]
        
        # Fill in the chart points
        x_step = max(1, len(filtered_history) / chart_width)
        for i in range(chart_width):
            index = min(int(i * x_step), len(filtered_history) - 1)
            point = filtered_history[index]
            
            # Calculate y position (inverted because 0,0 is top-left)
            balance = point.get("balance", 0)
            y_pos = chart_height - 1 - int((balance - min_balance) * scale)
            y_pos = max(0, min(y_pos, chart_height - 1))
            
            # Place point in grid
            chart_grid[y_pos][i] = "●"
        
        # Draw horizontal grid lines
        for i in range(chart_height):
            value = max_balance - (i * value_range / chart_height)
            value_str = format_currency(value, self.current_asset or "USD")
            chart_text.append(f"{value_str:>10} ")
            
            # Draw the line
            line = "".join(chart_grid[i])
            if i == 0:
                chart_text.append(f"{line}\n", style="green")
            elif i == chart_height - 1:
                chart_text.append(f"{line}\n", style="red")
            else:
                chart_text.append(f"{line}\n")
        
        # Draw time labels
        chart_text.append(" " * 11)
        time_labels = []
        for i in range(0, chart_width, chart_width // 4):
            index = min(int(i * x_step), len(filtered_history) - 1)
            point = filtered_history[index]
            timestamp = point.get("timestamp")
            
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp)
                except ValueError:
                    timestamp = datetime.utcnow()
            
            time_label = timestamp.strftime(time_format)
            time_labels.append((i, time_label))
        
        # Add time labels with proper spacing
        label_positions = {}
        for pos, label in time_labels:
            label_positions[pos] = label
        
        time_line = ""
        for i in range(chart_width):
            if i in label_positions:
                label = label_positions[i]
                # Pad or truncate label to fit
                time_line += label[:1]
            else:
                time_line += " "
        
        chart_text.append(time_line + "\n")
        
        # Add detailed time labels below
        chart_text.append(" " * 11)
        for pos, label in time_labels:
            if pos > 0:
                chart_text.append(" " * (pos - len(time_line)))
            chart_text.append(label)
            time_line = ""
        
        chart_widget.update(chart_text)
    
    def update_balance_history(self, history: List[Dict[str, Any]]) -> None:
        """Update balance history data and refresh the display."""
        self.balance_data = history
        
        # Extract unique assets from history
        assets = set()
        for point in history:
            asset = point.get("asset")
            if asset:
                assets.add(asset)
        
        # Update asset options
        self.update_asset_options(sorted(list(assets)))
        
        # Refresh display
        self.refresh_history()


class AlertsWidget(Static):
    """Widget displaying security alerts for the wallet."""
    
    alerts = reactive([])
    
    def __init__(self, title: str = "Security Alerts", **kwargs):
        super().__init__(**kwargs)
        self.panel_title = title
    
    def compose(self) -> ComposeResult:
        """Create child widgets for the alerts."""
        yield Container(
            Label(self.panel_title, id="alerts-title", classes="widget-title"),
            Static(id="alerts-list"),
            id="alerts-container"
        )
    
    def on_mount(self) -> None:
        """Initialize the widget when mounted."""
        self.refresh_alerts()
    
    def refresh_alerts(self) -> None:
        """Update the alerts display with current data."""
        alerts_widget = self.query_one("#alerts-list")
        
        if not self.alerts:
            alerts_widget.update("No security alerts at this time")
            return
        
        # Create alerts visualization
        alerts_text = Text()
        
        # Sort by severity
        severity_order = {"high": 0, "medium": 1, "low": 2}
        sorted_alerts = sorted(
            self.alerts, 
            key=lambda x: (severity_order.get(x.get("severity", "low"), 3), x.get("timestamp", datetime.min))
        )
        
        for alert in sorted_alerts:
            alert_type = alert.get("type", "unknown")
            severity = alert.get("severity", "low")
            description = alert.get("description", "No description")
            
            # Timestamp formatting
            timestamp = alert.get("timestamp")
            if not timestamp:
                timestamp = alert.get("date")  # Some alerts use 'date' instead
            
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp)
                except ValueError:
                    timestamp = None
            
            time_str = format_time(timestamp) if timestamp else "Unknown time"
            
            # Style based on severity
            severity_style = {
                "high": "red bold",
                "medium": "yellow",
                "low": "blue"
            }.get(severity, "white")
            
            # Alert symbol based on type
            alert_symbol = {
                "large_transaction": "💰",
                "high_frequency": "⚡",
                "multiple_failures": "❌",
                "suspicious_login": "🔑",
                "unusual_ip": "🌐"
            }.get(alert_type, "⚠️")
            
            # Format alert
            alerts_text.append(f"{alert_symbol} ", style=severity_style)
            alerts_text.append(f"[{severity.upper()}] ", style=severity_style)
            alerts_text.append(f"{description}\n")
            alerts_text.append(f"Time: {time_str}\n\n")
        
        alerts_widget.update(alerts_text)
    
    def update_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        """Update alerts data and refresh the display."""
        self.alerts = alerts
        self.refresh_alerts()


class WalletActionsWidget(Static):
    """Widget for wallet actions like deposit, withdraw, etc."""
    
    wallet_id = reactive(None)
    
    def __init__(self, title: str = "Wallet Operations", **kwargs):
        super().__init__(**kwargs)
        self.panel_title = title
    
    def compose(self) -> ComposeResult:
        """Create child widgets for the wallet operations."""
        yield Container(
            Label(self.panel_title, id="actions-title", classes="widget-title"),
            Vertical(
                Button("Deposit Funds", id="deposit-btn", classes="action-button"),
                Button("Withdraw Funds", id="withdraw-btn", classes="action-button"),
                Button("Transfer Between Accounts", id="transfer-btn", classes="action-button"),
                Button("Export Transactions", id="export-btn", classes="action-button"),
                Button("Hide/Show Balances", id="toggle-visibility-btn", classes="action-button"),
                id="action-buttons"
            ),
            id="actions-container"
        )
    
    def on_mount(self) -> None:
        """Initialize the widget when mounted."""
        # Connect buttons
        self.query_one("#deposit-btn").on_click = self.handle_deposit
        self.query_one("#withdraw-btn").on_click = self.handle_withdraw
        self.query_one("#transfer-btn").on_click = self.handle_transfer
        self.query_one("#export-btn").on_click = self.handle_export
        self.query_one("#toggle-visibility-btn").on_click = self.handle_toggle_visibility
    
    def handle_deposit(self, event):
        """Handle deposit button click."""
        self.post_message({"type": "deposit", "wallet_id": self.wallet_id})
    
    def handle_withdraw(self, event):
        """Handle withdraw button click."""
        self.post_message({"type": "withdraw", "wallet_id": self.wallet_id})
    
    def handle_transfer(self, event):
        """Handle transfer button click."""
        self.post_message({"type": "transfer", "wallet_id": self.wallet_id})
    
    def handle_export(self, event):
        """Handle export button click."""
        self.post_message({"type": "export", "wallet_id": self.wallet_id})
    
    def handle_toggle_visibility(self, event):
        """Handle toggle visibility button click."""
        self.post_message({"type": "toggle_visibility", "wallet_id": self.wallet_id})
    
    def update_wallet_id(self, wallet_id: int) -> None:
        """Update the current wallet ID."""
        self.wallet_id = wallet_id 