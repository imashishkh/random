"""
Main dashboard application for the Forex Trading platform.
"""
from rich.console import Console
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, TabPane, TabbedContent, Tabs, Tab
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual import events
from textual.reactive import reactive
import asyncio
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Set, Callable

from .widgets import (
    StatusIndicator, 
    MetricsPanel, 
    PriceTickerWidget, 
    OrderBookWidget,
    SystemMetricsWidget,
    AgentStatusWidget,
    AgentLogWidget,
    TradePerformanceWidget
)
from .wallet_widgets import (
    WalletOverviewWidget,
    TransactionHistoryWidget,
    FundAllocationWidget,
    BalanceHistoryWidget,
    AlertsWidget,
    WalletActionsWidget
)
from .monitors import SystemMonitor, AgentMonitor
from .utils import (
    generate_mock_wallet,
    format_currency,
    format_percentage,
    format_time
)
from .agent_widgets import AgentControlWidget, AgentLogsWidget
from .system_widgets import (
    SystemHealthWidget,
    NetworkActivityWidget,
    DiskUsageWidget,
    SystemOpsWidget,
    StatusBarWidget
)

# Import the analytics module
from ..analytics import TradingPerformanceAnalytics

# Import account modules
from ..account.manager import WalletManager

# Mock wallet service import (replace with actual implementation)
from ..services.wallet import WalletService

# Configure logging
logger = logging.getLogger(__name__)

class TradingDashboard(App):
    """Forex Trading Dashboard Application with Agent Control and Wallet Management."""
    
    TITLE = "Forex Trading Dashboard"
    SUB_TITLE = "Monitor and control your trading systems"
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    #header-container {
        height: 3;
        margin: 0 0 1 0;
    }
    
    #balance-container {
        height: 10;
        margin: 0 1 1 1;
    }
    
    #trading-view {
        height: 30;
        margin: 0 1 1 1;
    }
    
    #orders-container {
        height: 17;
        margin: 0 1 1 1;
    }
    
    #agent-container {
        height: 12;
        margin: 0 1 1 1;
    }
    
    StatusIndicator {
        width: 20;
        height: 1;
        margin: 0 1 0 0;
    }
    
    #ticker-container {
        height: 5;
        margin: 0 0 1 0;
    }
    
    .agent-panel {
        height: 100%;
        width: 1fr;
    }
    
    .balance-panel {
        height: 100%;
        width: 1fr;
    }
    
    MetricsPanel {
        height: 100%;
    }
    
    OrderBookWidget {
        height: 100%;
        width: 1fr;
    }
    
    .stats-panel {
        height: 100%;
        width: 1fr;
    }
    
    PriceTickerWidget {
        height: 100%;
        width: 100%;
    }
    
    TradePerformanceWidget {
        height: 100%;
        width: 100%;
    }
    
    #performance-container {
        height: 30;
        margin: 0 1 1 1;
    }
    
    /* Wallet Management Styling */
    #wallet-overview {
        height: 12;
        margin: 0 1 1 1;
    }
    
    #wallet-alerts {
        height: 10;
        margin: 0 1 1 1;
    }
    
    #wallet-transactions {
        height: 16;
        margin: 0 1 1 1;
    }
    
    #wallet-visualization {
        height: 16;
        margin: 0 1 1 1;
    }
    
    .wallet-panel {
        height: 100%;
        width: 2fr;
    }
    
    .wallet-actions-panel {
        height: 100%;
        width: 1fr;
    }
    
    .wallet-info-container {
        width: 1fr;
    }
    
    .wallet-balance-container {
        width: 1fr;
    }
    
    .wallet-chart-panel {
        height: 100%;
        width: 1fr;
    }
    
    .action-button {
        width: 100%;
        margin: 0 0 1 0;
    }
    
    Select {
        width: 30;
        margin: 0 1 0 0;
    }
    
    #wallet-controls {
        height: 3;
        margin: 0 0 1 0;
    }
    
    #transaction-controls {
        height: 3;
        margin: 0 0 1 0;
    }
    
    #history-controls {
        height: 3;
        margin: 0 0 1 0;
    }
    
    #dashboard-tabs {
        dock: top;
        height: auto;
        border-bottom: solid white;
    }
    
    .agent-control-panel {
        height: 25%;
        margin: 1 1;
    }
    
    .agent-status-panel {
        height: 25%;
        margin: 1 1;
    }
    
    .agent-log-panel {
        height: 50%;
        margin: 1 1;
    }
    
    .system-panel {
        width: 50%;
        margin: 1 1;
    }
    
    .network-panel {
        width: 50%;
        margin: 1 1;
    }
    
    .wallet-overview-panel {
        height: 25%;
        margin: 1 1;
    }
    
    .wallet-actions-panel {
        height: 25%;
        margin: 1 1;
    }
    
    .alerts-panel {
        height: 25%;
        margin: 1 1;
    }
    
    .transactions-panel {
        height: 50%;
        margin: 1 1;
    }
    
    .balance-history-panel {
        width: 50%;
        margin: 1 1;
    }
    
    .fund-allocation-panel {
        width: 50%;
        margin: 1 1;
    }
    
    .top-half {
        height: 50%;
    }
    
    .bottom-half {
        height: 50%;
    }
    
    .left-panel {
        width: 30%;
        min-width: 30;
        max-width: 50;
    }
    
    .right-panel {
        width: 70%;
        min-width: 40;
    }
    
    .top-panel {
        height: 30%;
        min-height: 10;
        max-height: 40%;
    }
    
    .bottom-panel {
        height: 70%;
        min-height: 20;
    }
    
    .status-bar {
        height: 1;
        width: 100%;
        dock: bottom;
    }
    
    #wallet-container {
        layout: grid;
        grid-size: 2 3;
        grid-gutter: 1 1;
        height: 100%;
        padding: 1;
    }
    
    #wallet-overview {
        row-span: 1;
        column-span: 1;
    }
    
    #fund-allocation {
        row-span: 1;
        column-span: 1;
    }
    
    #balance-history {
        row-span: 2;
        column-span: 1;
    }
    
    #alerts-widget {
        row-span: 1;
        column-span: 1;
    }
    
    #transactions-history {
        row-span: 2;
        column-span: 1;
    }
    
    #wallet-actions {
        row-span: 1;
        column-span: 2;
        height: auto;
        dock: bottom;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("t", "toggle_agent", "Toggle Agent", show=True),
        Binding("d", "toggle_dark", "Toggle Dark Mode"),
    ]
    
    # Reactive state
    update_interval = reactive(5.0)  # Update interval in seconds
    show_balances = reactive(True)  # Whether to show sensitive balance information
    current_wallet_id = reactive(None)  # Currently selected wallet ID
    dev_mode = reactive(False)    # Development mode flag
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.console = Console()
        self.system_monitor = SystemMonitor()
        self.agent_monitor = AgentMonitor()
        
        # Initialize wallet manager
        self.wallet_manager = WalletManager()
        
        # Initialize analytics
        self.analytics = TradingPerformanceAnalytics("mock", num_trades=100)
        self.last_update = 0
        
        # Initialize wallet service
        self.wallet_service = WalletService()
    
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(show_clock=True)
        
        with Tabs("Agents", "System", "Wallet"):
            # Agents Tab
            with TabPane("Agents", id="tab-agents"):
                with Horizontal(classes="horizontal-split container"):
                    # Left Panel - Controls
                    with Vertical(classes="left-panel"):
                        yield AgentControlWidget(classes="section")
                    
                    # Right Panel - Status and Logs
                    with Vertical(classes="right-panel"):
                        with Vertical(classes="top-panel"):
                            yield AgentStatusWidget(classes="section")
                        
                        with Vertical(classes="bottom-panel"):
                            yield AgentLogsWidget(classes="section")
            
            # System Tab
            with TabPane("System", id="tab-system"):
                with Vertical(classes="container"):
                    with Horizontal(classes="top-panel"):
                        yield SystemMetricsWidget(classes="section")
                    
                    with Horizontal(classes="bottom-panel"):
                        yield SystemOpsWidget(classes="section")
            
            # Wallet Tab
            with TabPane("Wallet", id="tab-wallet"):
                with Container(id="wallet-container"):
                    yield WalletOverviewWidget(id="wallet-overview", classes="section")
                    yield FundAllocationWidget(id="fund-allocation", classes="section")
                    yield BalanceHistoryWidget(id="balance-history", classes="section")
                    yield AlertsWidget(id="alerts-widget", classes="section")
                    yield TransactionHistoryWidget(id="transactions-history", classes="section")
                yield WalletActionsWidget(id="wallet-actions", classes="section")
        
        # Status bar at the bottom
        yield StatusBarWidget(classes="status-bar")
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize the dashboard when mounted."""
        # Start system monitor
        self.system_monitor.start()
        
        # Set up periodic refresh
        self.set_interval(self.update_interval, self.refresh_dashboard)
        
        # Initial dashboard update
        self.refresh_dashboard()
    
    def refresh_dashboard(self) -> None:
        """Refresh all dashboard data."""
        current_time = time.time()
        
        try:
            # Update all widgets with fresh data
            self.update_overview_data()
            self.update_wallet_data()
            self.update_system_data()
            
            # Update last refresh time
            self.last_update = current_time
            
        except Exception as e:
            logger.error(f"Error refreshing dashboard: {str(e)}", exc_info=True)
    
    def update_overview_data(self) -> None:
        """Update data for the overview tab."""
        try:
            # Update balance panel
            balance_panel = self.query_one("#tab-overview .balance-panel:first-child", MetricsPanel)
            wallet_data = generate_mock_wallet()
            
            # Format balance metrics
            balance_metrics = {
                "Balance": format_currency(wallet_data["balance"], wallet_data["currency"]),
                "Equity": format_currency(wallet_data["equity"], wallet_data["currency"]),
                "Margin": format_currency(wallet_data["margin"], wallet_data["currency"]),
                "Free Margin": format_currency(wallet_data["free_margin"], wallet_data["currency"]),
                "Margin Level": f"{wallet_data['margin_level']}%"
            }
            
            balance_panel.update_metrics(balance_metrics)
            
            # Update performance panel
            from src.dashboard.utils import generate_mock_performance
            performance_panel = self.query_one("#tab-overview .balance-panel:nth-child(2)", MetricsPanel)
            performance_data = generate_mock_performance()
            performance_panel.update_metrics(performance_data)
            
            # Update ticker
            ticker = self.query_one("#tab-overview PriceTickerWidget", PriceTickerWidget)
            from src.dashboard.utils import generate_mock_forex_prices
            ticker.update_prices(generate_mock_forex_prices())
            
            # Update order book
            orderbook = self.query_one("#tab-overview OrderBookWidget", OrderBookWidget)
            bids = [
                ["1.0865", "10,000", "10,000"],
                ["1.0864", "15,000", "25,000"],
                ["1.0863", "20,000", "45,000"],
                ["1.0862", "25,000", "70,000"],
                ["1.0861", "30,000", "100,000"]
            ]
            asks = [
                ["1.0866", "12,000", "12,000"],
                ["1.0867", "18,000", "30,000"],
                ["1.0868", "22,000", "52,000"],
                ["1.0869", "28,000", "80,000"],
                ["1.0870", "35,000", "115,000"]
            ]
            orderbook.update_orders(bids, asks)
            
            # Update trades table
            trades_table = self.query_one("#trades-table", DataTable)
            
            # Check if table is already set up
            if not trades_table.columns:
                trades_table.add_columns("ID", "Pair", "Side", "Size", "Price", "Status", "Time", "P/L")
            
            # Clear existing rows
            trades_table.clear()
            
            # Add mock trade data
            from src.dashboard.utils import generate_mock_trades
            trades = generate_mock_trades(10)
            
            for trade in trades:
                # Format profit/loss
                pl_str = format_currency(trade["profit_loss"], "USD")
                pl_style = "green" if trade["profit_loss"] > 0 else "red"
                
                # Format timestamp
                time_str = format_time(trade["timestamp"])
                
                trades_table.add_row(
                    trade["id"],
                    trade["pair"],
                    trade["side"],
                    str(trade["size"]),
                    str(trade["price"]),
                    trade["status"],
                    time_str,
                    pl_str,
                    style=pl_style if trade["status"] == "FILLED" else None
                )
            
            # Update agent status
            agents_panel = self.query_one("#tab-overview .agent-panel", MetricsPanel)
            from src.dashboard.utils import generate_mock_agent_status
            
            agents = generate_mock_agent_status()
            agent_metrics = {}
            
            for agent in agents:
                status_symbol = "✓" if agent["status"] == "active" else "⚠" if agent["status"] == "warning" else "✗"
                agent_metrics[agent["name"]] = status_symbol
            
            agents_panel.update_metrics(agent_metrics)
            
            # Update system stats on overview
            system_panel = self.query_one("#tab-overview .stats-panel", MetricsPanel)
            
            import psutil
            stats_metrics = {
                "CPU": f"{psutil.cpu_percent()}%",
                "Memory": f"{psutil.virtual_memory().percent}%",
                "Disk": f"{psutil.disk_usage('/').percent}%",
                "Uptime": format_time_delta(time.time() - psutil.boot_time())
            }
            
            system_panel.update_metrics(stats_metrics)
            
        except Exception as e:
            self.console.print(f"Error updating overview data: {str(e)}")
    
    def update_wallet_data(self) -> None:
        """Update data for the wallet management tab."""
        try:
            # Get wallet widgets
            wallet_overview = self.query_one("#tab-wallet WalletOverviewWidget", WalletOverviewWidget)
            wallet_actions = self.query_one("#tab-wallet WalletActionsWidget", WalletActionsWidget)
            transaction_history = self.query_one("#tab-wallet TransactionHistoryWidget", TransactionHistoryWidget)
            fund_allocation = self.query_one("#tab-wallet FundAllocationWidget", FundAllocationWidget)
            balance_history = self.query_one("#tab-wallet BalanceHistoryWidget", BalanceHistoryWidget)
            alerts_widget = self.query_one("#tab-wallet AlertsWidget", AlertsWidget)
            
            # Update wallet overview with current wallet data
            # In a real implementation, we would fetch the wallet data from the wallet manager
            # For now, we'll use mock data
            
            # Mock getting wallet data
            try:
                # Try to get real wallet data
                wallet_data = self.wallet_manager.get_wallet(self.current_wallet_id)
            except Exception as e:
                # Fall back to mock data
                self.console.print(f"Using mock wallet data: {str(e)}")
                from src.account.models import WalletType
                
                wallet_data = {
                    "id": self.current_wallet_id,
                    "name": "Main Trading Wallet",
                    "wallet_type": WalletType.HOT,
                    "address": "0x3a9d84958e01904Fd5A5219E692aa492D8ac1600",
                    "balances": {
                        "BTC": 0.5,
                        "ETH": 5.2,
                        "USDT": 10000,
                        "BNB": 12.5,
                        "SOL": 54.2,
                        "USDC": 5000
                    },
                    "last_updated": datetime.datetime.utcnow()
                }
            
            # Update wallet ID in actions widget
            wallet_actions.update_wallet_id(self.current_wallet_id)
            
            # Apply balance visibility setting
            if not self.show_balances:
                # Hide sensitive information
                masked_balances = {k: 0 for k in wallet_data.get("balances", {}).keys()}
                masked_data = wallet_data.copy()
                masked_data["balances"] = masked_balances
                wallet_overview.update_wallet_data(masked_data)
            else:
                wallet_overview.update_wallet_data(wallet_data)
            
            # Update transaction history
            # In a real implementation, we would fetch transactions from the wallet manager
            # For now, we'll use mock data
            mock_transactions = []
            import random
            from datetime import datetime, timedelta
            
            # Generate some mock transactions
            for i in range(20):
                tx_type = random.choice(["DEPOSIT", "WITHDRAWAL", "TRANSFER"])
                asset = random.choice(list(wallet_data.get("balances", {}).keys()))
                
                # Set amount range based on type
                if tx_type == "DEPOSIT":
                    amount = round(random.uniform(0.1, 5.0), 4)
                elif tx_type == "WITHDRAWAL":
                    amount = round(random.uniform(0.1, 2.0), 4)
                else:
                    amount = round(random.uniform(0.1, 10.0), 4)
                
                # Set timestamp to a random time in the last 30 days
                days_ago = random.randint(0, 30)
                hours_ago = random.randint(0, 23)
                timestamp = datetime.utcnow() - timedelta(days=days_ago, hours=hours_ago)
                
                # Set status
                if days_ago < 1:
                    status = random.choices(
                        ["PENDING", "CONFIRMED", "FAILED"],
                        weights=[0.2, 0.7, 0.1]
                    )[0]
                else:
                    status = random.choices(
                        ["CONFIRMED", "FAILED"],
                        weights=[0.95, 0.05]
                    )[0]
                
                mock_transactions.append({
                    "transaction_id": f"tx_{i}_{random.randint(1000, 9999)}",
                    "transaction_type": tx_type,
                    "asset": asset,
                    "amount": amount,
                    "status": status,
                    "timestamp": timestamp
                })
            
            # Sort by timestamp (newest first)
            mock_transactions.sort(key=lambda x: x["timestamp"], reverse=True)
            
            transaction_history.update_transactions(mock_transactions)
            
            # Update fund allocation
            # In a real implementation, we would get this from wallet_manager.get_fund_allocation()
            # For now, we'll calculate from mock data
            total = sum(wallet_data.get("balances", {}).values())
            allocation = {
                asset: (value / total) * 100 if total > 0 else 0
                for asset, value in wallet_data.get("balances", {}).items()
            }
            
            fund_allocation.update_allocation(allocation)
            
            # Update balance history
            # In a real implementation, we would get this from wallet_manager.get_wallet_balance_history()
            # For now, we'll generate mock data
            
            # Generate balance history for the last month
            mock_history = []
            starting_balance = total * 0.8  # Start slightly lower than current
            
            # Generate daily points for the last 30 days
            for days_back in range(30, 0, -1):
                date = datetime.utcnow() - timedelta(days=days_back)
                
                # Random daily change between -3% and +5%
                daily_change = random.uniform(-0.03, 0.05)
                starting_balance *= (1 + daily_change)
                
                mock_history.append({
                    "timestamp": date,
                    "balance": starting_balance,
                    "asset": None  # None represents total balance
                })
                
                # Add a few individual asset history points
                for asset in ["BTC", "ETH", "USDT"]:
                    if asset in wallet_data.get("balances", {}):
                        asset_balance = wallet_data["balances"][asset] * 0.8 * (1 + random.uniform(-0.05, 0.05))
                        mock_history.append({
                            "timestamp": date,
                            "balance": asset_balance,
                            "asset": asset
                        })
            
            balance_history.update_balance_history(mock_history)
            
            # Update alerts
            # In a real implementation, we would get this from wallet_manager.detect_suspicious_activity()
            # For now, we'll generate mock alerts
            mock_alerts = []
            
            # Add some random alerts
            alert_types = [
                {
                    "type": "large_transaction",
                    "description": "Unusually large withdrawal of 2.5 ETH",
                    "severity": "medium",
                    "timestamp": datetime.utcnow() - timedelta(hours=6)
                },
                {
                    "type": "high_frequency",
                    "description": "Unusual number of transactions (15) on April 15",
                    "severity": "low",
                    "date": datetime.utcnow() - timedelta(days=4)
                },
                {
                    "type": "multiple_failures",
                    "description": "3 failed withdrawal attempts detected",
                    "severity": "medium",
                    "timestamp": datetime.utcnow() - timedelta(days=1)
                }
            ]
            
            # Only show some alerts randomly
            for alert in alert_types:
                if random.random() < 0.7:  # 70% chance to show each alert
                    mock_alerts.append(alert)
            
            alerts_widget.update_alerts(mock_alerts)
            
        except Exception as e:
            self.console.print(f"Error updating wallet data: {str(e)}")
    
    def update_system_data(self) -> None:
        """Update data for the system monitoring tab."""
        try:
            # Get system metrics
            metrics = self.system_monitor.get_current_metrics()
            
            # Update system metrics widget
            system_widget = self.query_one("#tab-system SystemMetricsWidget", SystemMetricsWidget)
            system_widget.update_metrics(metrics)
            
            # Update system health widget
            health_widget = self.query_one("#tab-system SystemHealthWidget", SystemHealthWidget)
            health_widget.update_health(metrics)
            
            # Update network activity widget
            network_widget = self.query_one("#tab-system NetworkActivityWidget", NetworkActivityWidget)
            network_widget.update_network_activity(metrics)
            
            # Update disk usage widget
            disk_widget = self.query_one("#tab-system DiskUsageWidget", DiskUsageWidget)
            disk_widget.update_disk_usage(metrics)
            
            # Update agent status widget
            agent_widget = self.query_one("#tab-system AgentStatusWidget", AgentStatusWidget)
            
            # In a real implementation, we would get this from a real agent monitor
            # For now, we'll generate mock data
            agents = {}
            for i in range(5):
                agent_name = f"Agent-{i}"
                agent_type = ["TrendFollower", "MeanReversion", "GridTrader", "BreakoutTrader", "NewsTrader"][i]
                
                agents[agent_name] = {
                    "type": agent_type,
                    "status": random.choice(["active", "stopped", "warning"]),
                    "uptime": format_time_delta(timedelta(hours=random.randint(1, 120))),
                    "last_trade": format_time(datetime.datetime.utcnow() - timedelta(minutes=random.randint(5, 120))),
                    "trades_today": random.randint(0, 15)
                }
            
            agent_widget.update_agents(agents)
            
            # Update agent log widget
            log_widget = self.query_one("#tab-system AgentLogWidget", AgentLogWidget)
            
            # Generate mock logs
            logs = []
            for i in range(20):
                agent_name = f"Agent-{random.randint(0, 4)}"
                minutes_ago = random.randint(1, 60)
                timestamp = datetime.datetime.utcnow() - timedelta(minutes=minutes_ago)
                
                log_types = [
                    "Started trading session",
                    "Placed new order",
                    "Closed position",
                    "API connection error",
                    "Insufficient balance for trade",
                    "Strategy conditions met",
                    "Stopped trading session"
                ]
                
                logs.append({
                    "agent": agent_name,
                    "message": random.choice(log_types),
                    "timestamp": timestamp,
                    "level": random.choice(["INFO", "WARNING", "ERROR", "DEBUG"])
                })
            
            # Sort by timestamp (newest first)
            logs.sort(key=lambda x: x["timestamp"], reverse=True)
            
            log_widget.update_logs(logs)
            
        except Exception as e:
            self.console.print(f"Error updating system data: {str(e)}")
    
    def on_unmount(self) -> None:
        """Clean up resources when the app is closing."""
        self.system_monitor.stop()

    def action_refresh(self) -> None:
        """Refresh the dashboard manually."""
        self.refresh_dashboard()
        self.notify("Dashboard refreshed")
    
    def action_toggle_agent(self) -> None:
        """Toggle agent status (start/stop)."""
        try:
            control_widget = self.query_one(AgentControlWidget)
            control_widget.toggle_selected_agent()
        except NoMatches:
            self.notify("Agent control not available")
    
    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        """Handle tab activation events."""
        # Ensure appropriate refresh when switching tabs
        self.refresh_dashboard()

    def action_toggle_dark(self) -> None:
        """Toggle between light and dark mode."""
        self.dark = not self.dark
        mode = "Dark" if self.dark else "Light"
        self.notify(f"Switched to {mode} mode")

def run_dashboard(refresh_rate: float = 5.0, dev_mode: bool = False) -> None:
    """Run the trading dashboard application.
    
    Args:
        refresh_rate: How often to refresh the dashboard data (in seconds)
        dev_mode: Enable development mode for additional logging/features
    """
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if dev_mode else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logger.info(f"Starting dashboard with refresh rate: {refresh_rate}s, dev_mode: {dev_mode}")
    
    try:
        # Create and run the application
        app = TradingDashboard(refresh_rate=refresh_rate, dev_mode=dev_mode)
        app.run()
    except KeyboardInterrupt:
        logger.info("Dashboard terminated by user")
    except Exception as e:
        logger.error(f"Dashboard terminated due to error: {str(e)}")
        raise

if __name__ == "__main__":
    run_dashboard() 