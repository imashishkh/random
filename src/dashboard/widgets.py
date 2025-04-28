"""
Reusable widgets for the Forex Trading dashboard application.
"""
from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable

from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.console import Group
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, DataTable, Label
from textual.reactive import Reactive, reactive
from rich.layout import Layout
import time
import psutil

from .utils import (
    format_bytes, 
    format_time_delta, 
    format_currency, 
    format_percentage, 
    format_time
)

# Import analytics visualization tools
from ..analytics import TradingPerformanceAnalytics


class StatusIndicator(Static):
    """A status indicator that shows a colored dot with a label."""
    
    status: Reactive[str] = Reactive("unknown")
    
    def __init__(self, status: str = "unknown", **kwargs):
        super().__init__(**kwargs)
        self.status = status
    
    def render(self) -> Text:
        colors = {
            "active": "green",
            "running": "green",
            "online": "green",
            "warning": "yellow",
            "error": "red",
            "stopped": "red",
            "offline": "red",
            "pending": "yellow",
            "unknown": "grey"
        }
        
        status_lower = self.status.lower()
        color = colors.get(status_lower, "grey")
        
        text = Text()
        text.append("● ", color)
        text.append(self.status.upper())
        
        return text
    
    def update_status(self, new_status: str) -> None:
        """Update the status of the indicator."""
        self.status = new_status
        self.refresh()


class MetricsPanel(Static):
    """A panel for displaying key metrics."""
    
    metrics: Reactive[Dict[str, Any]] = Reactive({})
    
    def __init__(
        self, 
        title: str = "Metrics", 
        metrics: Dict[str, Any] = None,
        classes: Optional[str] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.panel_title = title
        self.metrics = metrics or {}
        
        if classes:
            self.add_class(classes)
    
    def render(self) -> Panel:
        """Render the metrics panel."""
        content = Text()
        
        for label, value in self.metrics.items():
            content.append(f"[bold]{label}:[/bold] ")
            
            # Style numeric values based on their sign
            if isinstance(value, (int, float, Decimal)) and value != 0:
                if value > 0:
                    content.append(f"{value}\n", "green")
                else:
                    content.append(f"{value}\n", "red")
            # Style percentage values
            elif isinstance(value, str) and "%" in value:
                if value.startswith("-"):
                    content.append(f"{value}\n", "red")
                elif value.startswith("+") or any(c.isdigit() for c in value):
                    content.append(f"{value}\n", "green")
                else:
                    content.append(f"{value}\n")
            # Handle strings that look like money values with + or -
            elif isinstance(value, str) and (value.startswith("+$") or value.startswith("-$")):
                if value.startswith("+"):
                    content.append(f"{value}\n", "green")
                else:
                    content.append(f"{value}\n", "red")
            else:
                content.append(f"{value}\n")
        
        return Panel(content, title=self.panel_title)
    
    def update_metrics(self, metrics: Dict[str, Any]) -> None:
        """Update the metrics displayed in the panel."""
        self.metrics = metrics
        self.refresh()
    
    def update_single_metric(self, key: str, value: Any) -> None:
        """Update a single metric value."""
        self.metrics[key] = value
        self.refresh()


class PriceTickerWidget(Static):
    """A ticker widget for displaying cryptocurrency prices."""
    
    prices: Reactive[Dict[str, Dict[str, Any]]] = Reactive({})
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Initialize with some default pairs
        self.prices = {
            "BTC/USDT": {"price": "30000.00", "change": "+1.2%"},
            "ETH/USDT": {"price": "2000.00", "change": "-0.5%"},
            "XRP/USDT": {"price": "0.5000", "change": "+0.8%"}
        }
    
    def compose(self) -> ComposeResult:
        yield Container(
            Label("Market Prices", classes="widget-title"),
            Static(id="ticker-content"),
            classes="ticker-container"
        )
    
    def on_mount(self) -> None:
        """Initialize ticker display."""
        self.refresh_ticker()
    
    def refresh_ticker(self) -> None:
        """Update the ticker display with current prices."""
        ticker_widget = self.query_one("#ticker-content")
        
        table = Table(expand=True)
        table.add_column("Pair")
        table.add_column("Price", justify="right")
        table.add_column("Change (24h)", justify="right")
        
        for pair, data in self.prices.items():
            price = data["price"]
            change = data["change"]
            
            # Style the change value based on direction
            change_style = "green" if change.startswith("+") else "red"
            
            table.add_row(
                pair,
                price,
                change,
                style=change_style
            )
        
        ticker_widget.update(table)
    
    def update_prices(self, new_prices: Dict[str, Dict[str, Any]]) -> None:
        """Update prices data and refresh the display."""
        self.prices.update(new_prices)
        self.refresh_ticker()


class OrderBookWidget(Static):
    """Widget displaying order book for a trading pair."""
    
    bids: Reactive[List[List[str]]] = Reactive([])
    asks: Reactive[List[List[str]]] = Reactive([])
    pair: Reactive[str] = Reactive("BTC/USDT")
    
    def __init__(self, pair: str = "BTC/USDT", **kwargs):
        super().__init__(**kwargs)
        self.pair = pair
    
    def compose(self) -> ComposeResult:
        yield Container(
            Label(id="orderbook-title", classes="widget-title"),
            Static(id="orderbook-content"),
            id="orderbook-container"
        )
    
    def on_mount(self) -> None:
        """Initialize order book display."""
        self.query_one("#orderbook-title").update(f"Order Book: {self.pair}")
        
        # Placeholder data
        self.bids = [
            ["29900.00", "0.5", "14950.00"],
            ["29850.00", "1.2", "35820.00"],
            ["29800.00", "2.5", "74500.00"]
        ]
        
        self.asks = [
            ["30000.00", "0.8", "24000.00"],
            ["30050.00", "1.5", "45075.00"],
            ["30100.00", "3.2", "96320.00"]
        ]
        
        self.refresh_orderbook()
    
    def refresh_orderbook(self) -> None:
        """Update the order book display."""
        content = self.query_one("#orderbook-content")
        
        table = Table(expand=True)
        table.add_column("Price", justify="right")
        table.add_column("Amount", justify="right")
        table.add_column("Total", justify="right")
        
        # Add asks in reverse order (highest to lowest)
        for ask in reversed(self.asks):
            table.add_row(*ask, style="red")
        
        # Add a divider row
        table.add_row("", "", "", style="bold")
        
        # Add bids (highest to lowest)
        for bid in self.bids:
            table.add_row(*bid, style="green")
        
        content.update(table)
    
    def update_pair(self, new_pair: str) -> None:
        """Change the trading pair and reset order book."""
        self.pair = new_pair
        self.query_one("#orderbook-title").update(f"Order Book: {self.pair}")
        # This would normally fetch new order book data
        self.refresh_orderbook()
    
    def update_orders(self, bids: List[List[str]], asks: List[List[str]]) -> None:
        """Update orders and refresh the display."""
        self.bids = bids
        self.asks = asks
        self.refresh_orderbook()


class SystemMetricsWidget(Static):
    """Widget for displaying system metrics like CPU, memory, disk."""
    
    metrics = reactive({})
    
    def __init__(self, title: str = "System Metrics", **kwargs):
        super().__init__(**kwargs)
        self.panel_title = title
    
    def render(self) -> Panel:
        """Render the system metrics widget."""
        cpu_metrics = self.metrics.get("cpu")
        memory_metrics = self.metrics.get("memory")
        disk_metrics = self.metrics.get("disk")
        network_metrics = self.metrics.get("network")
        
        sections = []
        
        # CPU section
        if cpu_metrics:
            cpu_text = Text()
            cpu_text.append("\n[bold]CPU[/bold]\n")
            
            # Overall CPU usage bar
            cpu_percent = cpu_metrics.get("percent", 0)
            cpu_status = cpu_metrics.get("status", "normal")
            
            # Set color based on status
            if cpu_status == "critical":
                color = "red"
            elif cpu_status == "warning":
                color = "yellow"
            else:
                color = "green"
                
            # Create a progress bar visual
            bar_width = 40
            filled = int(bar_width * cpu_percent / 100)
            cpu_bar = f"[{color}]{'█' * filled}{'░' * (bar_width - filled)}[/] {cpu_percent:.1f}%"
            cpu_text.append(cpu_bar + "\n")
            
            # Per-core CPU usage if available
            if "per_core" in cpu_metrics:
                cpu_text.append("\n[bold]CPU Cores[/bold]\n")
                for i, core_pct in enumerate(cpu_metrics["per_core"]):
                    if core_pct >= 90:
                        core_color = "red"
                    elif core_pct >= 70:
                        core_color = "yellow"
                    else:
                        core_color = "green"
                    
                    filled = int(bar_width * core_pct / 100)
                    core_bar = f"Core {i}: [{core_color}]{'█' * filled}{'░' * (bar_width - filled)}[/] {core_pct:.1f}%"
                    cpu_text.append(core_bar + "\n")
            
            sections.append(cpu_text)
        
        # Memory section
        if memory_metrics:
            memory_text = Text()
            memory_text.append("\n[bold]Memory[/bold]\n")
            
            memory_percent = memory_metrics.get("percent", 0)
            memory_status = memory_metrics.get("status", "normal")
            
            # Format memory values
            used = format_bytes(memory_metrics.get("used", 0))
            total = format_bytes(memory_metrics.get("total", 0))
            available = format_bytes(memory_metrics.get("available", 0))
            
            # Set color based on status
            if memory_status == "critical":
                color = "red"
            elif memory_status == "warning":
                color = "yellow"
            else:
                color = "green"
                
            # Create a progress bar visual
            bar_width = 40
            filled = int(bar_width * memory_percent / 100)
            memory_bar = f"[{color}]{'█' * filled}{'░' * (bar_width - filled)}[/] {memory_percent:.1f}%"
            memory_text.append(memory_bar + "\n")
            memory_text.append(f"Used: {used} of {total} ({available} available)\n")
            
            sections.append(memory_text)
        
        # Disk section
        if disk_metrics and "usage" in disk_metrics:
            disk_text = Text()
            disk_text.append("\n[bold]Disk Usage[/bold]\n")
            
            for mount, usage in disk_metrics["usage"].items():
                # Skip if percentage is not available
                if "percent" not in usage:
                    continue
                    
                disk_percent = usage["percent"]
                disk_status = usage.get("status", "normal")
                
                # Format disk values
                used = format_bytes(usage.get("used", 0))
                total = format_bytes(usage.get("total", 0))
                free = format_bytes(usage.get("free", 0))
                
                # Set color based on status
                if disk_status == "critical":
                    color = "red"
                elif disk_status == "warning":
                    color = "yellow"
                else:
                    color = "green"
                    
                # Create a progress bar visual
                bar_width = 40
                filled = int(bar_width * disk_percent / 100)
                disk_bar = f"{mount}: [{color}]{'█' * filled}{'░' * (bar_width - filled)}[/] {disk_percent:.1f}%"
                disk_text.append(disk_bar + "\n")
                disk_text.append(f"  Used: {used} of {total} ({free} free)\n")
            
            # Show disk I/O if available
            if "io_rates" in disk_metrics:
                read_rate = format_bytes(disk_metrics["io_rates"].get("read_rate", 0)) + "/s"
                write_rate = format_bytes(disk_metrics["io_rates"].get("write_rate", 0)) + "/s"
                disk_text.append(f"Read: {read_rate}, Write: {write_rate}\n")
                
            sections.append(disk_text)
        
        # Network section
        if network_metrics and "stats" in network_metrics:
            network_text = Text()
            network_text.append("\n[bold]Network[/bold]\n")
            
            # Show network rates if available
            if "rates" in network_metrics["stats"]:
                send_rate = format_bytes(network_metrics["stats"]["rates"].get("send_rate", 0)) + "/s"
                recv_rate = format_bytes(network_metrics["stats"]["rates"].get("recv_rate", 0)) + "/s"
                network_text.append(f"Upload: {send_rate}, Download: {recv_rate}\n")
            
            # Show connection count if available
            conn_count = network_metrics["stats"].get("connections", 0)
            network_text.append(f"Active connections: {conn_count}\n")
                
            sections.append(network_text)
        
        # Combine all sections into a single content group
        content = Group(*sections) if sections else Text("No metrics available")
        
        return Panel(content, title=self.panel_title)
    
    def update_metrics(self, metrics: Dict[str, Any]) -> None:
        """Update the metrics displayed in the panel."""
        self.metrics = metrics
        self.refresh()


class AgentStatusWidget(Static):
    """Widget for displaying agent status and activities."""
    
    agents = reactive({})
    
    def __init__(self, title: str = "Agent Status", **kwargs):
        super().__init__(**kwargs)
        self.panel_title = title
    
    def render(self) -> Panel:
        """Render the agent status widget."""
        if not self.agents:
            return Panel(Text("No agent data available"), title=self.panel_title)
        
        # Create a table to display agent status
        table = Table(box=None)
        table.add_column("Agent")
        table.add_column("Status")
        table.add_column("Uptime")
        table.add_column("Success Rate")
        table.add_column("Trades")
        
        now = datetime.now()
        
        # Add a row for each agent
        for agent_name, status in self.agents.items():
            # Skip if status is not a dictionary
            if not isinstance(status, dict):
                continue
                
            # Format status color based on value
            status_value = status.get("status", "unknown").lower()
            if status_value == "active":
                status_text = Text("ACTIVE", style="bold green")
            elif status_value == "warning":
                status_text = Text("WARNING", style="bold yellow")
            elif status_value == "error":
                status_text = Text("ERROR", style="bold red")
            elif status_value == "stopped":
                status_text = Text("STOPPED", style="dim")
            else:
                status_text = Text(status_value.upper())
            
            # Calculate uptime if we have created timestamp
            uptime = "Unknown"
            if "created" in status:
                uptime_delta = now - status["created"]
                uptime = format_time_delta(uptime_delta)
            
            # Format success rate if available
            success_rate = "N/A"
            if "success_rate" in status:
                success_rate = f"{status['success_rate'] * 100:.1f}%"
            
            # Get processed trades count
            trades = str(status.get("processed_trades", 0))
            
            # Add the row
            table.add_row(agent_name, status_text, uptime, success_rate, trades)
        
        return Panel(table, title=self.panel_title)
    
    def update_agents(self, agents: Dict[str, Dict[str, Any]]) -> None:
        """Update the agents displayed in the widget."""
        self.agents = agents
        self.refresh()


class AgentLogWidget(Static):
    """Widget for displaying agent activity logs."""
    
    logs = reactive([])
    
    def __init__(self, title: str = "Agent Activity Log", **kwargs):
        super().__init__(**kwargs)
        self.panel_title = title
    
    def render(self) -> Panel:
        """Render the agent log widget."""
        if not self.logs:
            return Panel(Text("No log entries available"), title=self.panel_title)
        
        content = Text()
        
        # Add each log entry
        for entry in self.logs:
            timestamp = entry.get("timestamp", datetime.now())
            agent = entry.get("agent", "Unknown")
            message = entry.get("message", "")
            
            time_str = timestamp.strftime("%H:%M:%S")
            
            # Format with timestamp and agent name
            content.append(f"[dim]{time_str}[/dim] ")
            content.append(f"[bold]{agent}:[/bold] ")
            content.append(f"{message}\n")
        
        return Panel(content, title=self.panel_title)
    
    def update_logs(self, logs: List[Dict[str, Any]]) -> None:
        """Update the logs displayed in the widget."""
        self.logs = logs
        self.refresh()


class TradePerformanceWidget(Static):
    """A widget displaying trading performance analytics visualizations."""
    
    def __init__(self, title: str = "Trading Performance"):
        """Initialize the trade performance widget.
        
        Args:
            title: Title of the widget
        """
        super().__init__()
        self.title = title
        self.analytics = None
        self.period = "last_30_days"
        self.render_performance()
    
    def render_performance(self) -> None:
        """Render the trading performance visualizations."""
        if not self.analytics:
            # Show placeholder if no analytics available
            self.update(Panel(
                "[i]Trading performance data not available. Please connect to a data source.[/i]",
                title=self.title,
                border_style="bright_blue"
            ))
            return
        
        # Create a console for capturing rich content
        console = Console(width=100, height=30)
        
        # Create layout for the dashboard
        layout = Layout()
        layout.split(
            Layout(name="top", ratio=1),
            Layout(name="bottom", ratio=1)
        )
        
        # Split top section for summary and trade table
        layout["top"].split_row(
            Layout(name="summary", ratio=1),
            Layout(name="trades", ratio=2)
        )
        
        # Split bottom section for charts
        layout["bottom"].split_row(
            Layout(name="symbols", ratio=1),
            Layout(name="risk", ratio=1)
        )
        
        # Get trade data for the current period
        try:
            trades = self.analytics.get_trades_for_period(self.period)
            
            # Get performance summary
            summary = self.analytics.visualizer.create_performance_summary(trades)
            layout["summary"].update(summary)
            
            # Get trade table
            trade_table = self.analytics.visualizer.create_trade_table(trades, limit=10)
            layout["trades"].update(trade_table)
            
            # Get symbol performance
            symbol_table = self.analytics.visualizer.create_symbol_performance_table(trades)
            layout["symbols"].update(symbol_table)
            
            # Get risk metrics
            risk_panel = self.analytics.visualizer.create_risk_metrics_panel(trades)
            layout["bottom"].update(risk_panel)
            
            # Capture the layout in the console
            with console.capture() as capture:
                console.print(layout)
            
            # Update the widget with the rendered content
            self.update(Panel(
                capture.get(),
                title=f"{self.title} ({self.period})",
                border_style="bright_blue"
            ))
            
            # Add text summary of additional visualizations not shown
            text = Text()
            text.append("\n[bold]Additional Charts Available:[/bold]\n")
            text.append("• P&L Chart (daily/weekly/monthly)\n")
            text.append("• Drawdown Analysis\n")
            text.append("• Trade Distribution by Time\n")
            text.append("• Asset Allocation Chart\n")
            text.append("\nView full analytics dashboard with: [bold]analytics.display_dashboard()[/bold]\n")
            
            self.update(Panel(
                layout,
                title=f"{self.title} ({self.period})",
                border_style="bright_blue"
            ))
            
        except Exception as e:
            # Show error if analytics fails
            self.update(Panel(
                f"[red]Error rendering trading performance visualizations: {str(e)}[/red]",
                title=self.title,
                border_style="bright_blue"
            ))
    
    def update_analytics(self, analytics: TradingPerformanceAnalytics, period: str = None) -> None:
        """Update the analytics instance and period.
        
        Args:
            analytics: TradingPerformanceAnalytics instance
            period: Time period to display (e.g., "last_30_days")
        """
        self.analytics = analytics
        if period:
            self.period = period
        self.render_performance()
    
    def update_period(self, period: str) -> None:
        """Update the displayed time period.
        
        Args:
            period: Time period to display (e.g., "last_30_days")
        """
        self.period = period
        self.render_performance() 