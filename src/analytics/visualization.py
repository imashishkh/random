import plotext as plt
from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from rich.text import Text
from rich.layout import Layout
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any, Union
import math

from .data_models import Trade, PerformanceTimePeriod, TradeFilter
from .metrics_calculator import MetricsCalculator


class VisualizationManager:
    """Manages the creation of various trading visualizations"""
    
    def __init__(self, calculator: MetricsCalculator):
        self.calculator = calculator
        self.console = Console()
        
    def clear_screen(self) -> None:
        """Clear the terminal screen"""
        plt.clear_figure()
        plt.clear_terminal()
    
    def create_pnl_chart(self, trades: List[Trade], period: str = 'daily', 
                        show_cumulative: bool = True) -> None:
        """Create a P&L chart with specified time aggregation"""
        if not trades:
            print("No trades to display")
            return
            
        # Get P&L by period
        pnl_by_period = self.calculator.calculate_pnl_by_period(trades, period)
        
        # Extract dates and P&L values for plotting
        dates = list(pnl_by_period.keys())
        pnl_values = list(pnl_by_period.values())
        
        # Format dates for plotext compatibility
        formatted_dates = []
        for date_str in dates:
            if period == 'daily':
                # Format as DD/MM/YYYY for plotext
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    formatted_dates.append(date_obj.strftime("%d/%m/%Y"))
                except:
                    # Use simple labels if parsing fails
                    formatted_dates.append(f"Day {len(formatted_dates)+1}")
            elif period == 'weekly':
                # Format week numbers
                formatted_dates.append(f"W{date_str.split('-W')[1]}")
            elif period == 'monthly':
                # Format month names
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m")
                    formatted_dates.append(date_obj.strftime("%b %Y"))
                except:
                    formatted_dates.append(date_str)
            elif period == 'yearly':
                # Years are already in correct format
                formatted_dates.append(date_str)
            else:
                formatted_dates.append(date_str)
        
        # Calculate cumulative P&L
        cumulative_pnl = []
        running_total = 0
        for pnl in pnl_values:
            running_total += pnl
            cumulative_pnl.append(running_total)
        
        # Create the chart
        plt.clear_figure()
        
        # Plot P&L bars
        colors = ['green' if pnl >= 0 else 'red' for pnl in pnl_values]
        
        # Simple numerical x-axis to avoid date formatting issues
        x = list(range(len(formatted_dates)))
        plt.bar(x, pnl_values, color=colors)
        
        # Plot cumulative P&L line if requested
        if show_cumulative:
            plt.plot(x, cumulative_pnl, color="blue", label="Cumulative P&L")
        
        # Set title and labels
        plt.title(f"Trading P&L ({period.capitalize()})")
        plt.xlabel("Date")
        plt.ylabel("P&L")
        
        # Set custom tick labels
        plt.xticks(x, formatted_dates)
        
        # Show the plot
        plt.show()
    
    def create_win_rate_gauge(self, trades: List[Trade]) -> str:
        """Create a win rate gauge visualization"""
        win_rate = self.calculator.calculate_win_rate(trades)
        
        gauge_width = 40
        filled_width = int(win_rate / 100 * gauge_width)
        empty_width = gauge_width - filled_width
        
        # Determine color based on win rate
        if win_rate >= 60:
            color = "green"
        elif win_rate >= 45:
            color = "yellow"
        else:
            color = "red"
            
        gauge = f"[{color}]{'█' * filled_width}{'░' * empty_width}[/{color}] {win_rate:.1f}%"
        
        return gauge
    
    def create_trade_table(self, trades: List[Trade], limit: int = 10) -> Table:
        """Create a table of recent trades"""
        table = Table(title="Recent Trades")
        
        table.add_column("Time", justify="left")
        table.add_column("Symbol", justify="center")
        table.add_column("Dir", justify="center")
        table.add_column("Size", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Exit", justify="right")
        table.add_column("P&L", justify="right")
        
        sorted_trades = sorted(trades, key=lambda t: t.close_time, reverse=True)
        for trade in sorted_trades[:limit]:
            pnl_color = "green" if trade.pnl > 0 else "red"
            table.add_row(
                trade.close_time.strftime("%Y-%m-%d %H:%M"),
                trade.symbol,
                "🔼" if trade.direction.value == "BUY" else "🔽",
                f"{trade.size:.2f}",
                f"{trade.open_price:.5f}",
                f"{trade.close_price:.5f}",
                f"[{pnl_color}]{trade.pnl:.2f}[/{pnl_color}]"
            )
            
        return table
    
    def create_performance_summary(self, trades: List[Trade]) -> Panel:
        """Create a summary panel with key performance metrics"""
        metrics = []
        
        if not trades:
            return Panel("No trades to analyze", title="Performance Summary")
        
        # Calculate key metrics
        total_pnl = self.calculator.calculate_total_pnl(trades)
        win_rate = self.calculator.calculate_win_rate(trades)
        profit_factor = self.calculator.calculate_profit_factor(trades)
        avg_win = self.calculator.calculate_average_win(trades)
        avg_loss = self.calculator.calculate_average_loss(trades)
        max_dd, dd_start, dd_end = self.calculator.calculate_max_drawdown(trades)
        sharpe = self.calculator.calculate_sharpe_ratio(trades)
        
        # Format metrics for display
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t.is_winning])
        losing_trades = total_trades - winning_trades
        
        # Create a rich Text object for formatting
        summary = Text()
        
        # Add metrics with appropriate formatting
        summary.append(f"Total P&L: ", style="bold")
        summary.append(f"${total_pnl:.2f}\n", style="green" if total_pnl >= 0 else "red")
        
        summary.append(f"Win Rate: ", style="bold")
        summary.append(f"{win_rate:.1f}%\n", style="green" if win_rate >= 50 else "red")
        
        summary.append(f"Profit Factor: ", style="bold")
        if profit_factor == float('inf'):
            summary.append("∞\n", style="green")
        else:
            summary.append(f"{profit_factor:.2f}\n", style="green" if profit_factor > 1 else "red")
        
        summary.append(f"Trades: ", style="bold")
        summary.append(f"{total_trades} total ")
        summary.append(f"({winning_trades} ", style="green")
        summary.append("wins / ")
        summary.append(f"{losing_trades} ", style="red")
        summary.append("losses)\n")
        
        summary.append(f"Average Win: ", style="bold")
        summary.append(f"${avg_win:.2f}\n", style="green")
        
        summary.append(f"Average Loss: ", style="bold")
        summary.append(f"${abs(avg_loss):.2f}\n", style="red")
        
        summary.append(f"Max Drawdown: ", style="bold")
        summary.append(f"${max_dd:.2f}", style="red")
        if dd_start and dd_end:
            summary.append(f" ({dd_start.strftime('%Y-%m-%d')} to {dd_end.strftime('%Y-%m-%d')})\n")
        else:
            summary.append("\n")
        
        summary.append(f"Sharpe Ratio: ", style="bold")
        summary.append(f"{sharpe:.2f}\n", style="green" if sharpe > 1 else "yellow" if sharpe > 0 else "red")
        
        # Include win rate gauge
        summary.append("\nWin Rate: ", style="bold")
        summary.append(self.create_win_rate_gauge(trades))
        
        return Panel(summary, title="Performance Summary")
    
    def create_symbol_performance_table(self, trades: List[Trade]) -> Table:
        """Create a table showing performance by symbol"""
        table = Table(title="Performance by Symbol")
        
        table.add_column("Symbol", justify="left")
        table.add_column("Trades", justify="right")
        table.add_column("Win Rate", justify="right")
        table.add_column("P&L", justify="right")
        table.add_column("Profit Factor", justify="right")
        
        # Get performance metrics by symbol
        trades_by_symbol = {}
        for trade in trades:
            if trade.symbol not in trades_by_symbol:
                trades_by_symbol[trade.symbol] = []
            trades_by_symbol[trade.symbol].append(trade)
        
        # Sort symbols by P&L
        symbols_by_pnl = sorted(
            trades_by_symbol.keys(),
            key=lambda s: sum(t.pnl for t in trades_by_symbol[s]),
            reverse=True
        )
        
        # Add rows for each symbol
        for symbol in symbols_by_pnl:
            symbol_trades = trades_by_symbol[symbol]
            
            # Calculate metrics for this symbol
            total_pnl = sum(t.pnl for t in symbol_trades)
            win_rate = len([t for t in symbol_trades if t.is_winning]) / len(symbol_trades) * 100
            
            # Calculate profit factor
            gross_profit = sum(t.pnl for t in symbol_trades if t.is_winning)
            gross_loss = abs(sum(t.pnl for t in symbol_trades if not t.is_winning))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
            
            # Format profit factor
            pf_str = "∞" if profit_factor == float('inf') else f"{profit_factor:.2f}"
            
            # Add table row with appropriate coloring
            pnl_color = "green" if total_pnl >= 0 else "red"
            win_color = "green" if win_rate >= 50 else "red"
            pf_color = "green" if profit_factor > 1 else "red"
            
            table.add_row(
                symbol,
                str(len(symbol_trades)),
                f"[{win_color}]{win_rate:.1f}%[/{win_color}]",
                f"[{pnl_color}]${total_pnl:.2f}[/{pnl_color}]",
                f"[{pf_color}]{pf_str}[/{pf_color}]"
            )
        
        return table
    
    def create_drawdown_chart(self, trades: List[Trade]) -> None:
        """Create a drawdown chart"""
        if not trades:
            print("No trades to display")
            return
            
        # Sort trades by close time
        sorted_trades = sorted(trades, key=lambda t: t.close_time)
        
        # Calculate cumulative P&L and drawdowns
        dates = []
        cumulative_pnl = []
        drawdowns = []
        
        running_total = 0
        peak = 0
        
        for trade in sorted_trades:
            date_str = trade.close_time.strftime("%Y-%m-%d")
            dates.append(date_str)
            
            running_total += trade.pnl
            cumulative_pnl.append(running_total)
            
            peak = max(peak, running_total)
            drawdown = (peak - running_total) / (peak + 1e-10) * 100  # Avoid division by zero
            drawdowns.append(drawdown)
        
        # Create the chart
        plt.clear_figure()
        
        # Plot drawdown
        plt.plot(dates, drawdowns, color="red", label="Drawdown %")
        
        # Set title and labels
        plt.title("Drawdown Analysis")
        plt.xlabel("Date")
        plt.ylabel("Drawdown %")
        
        # Show the plot
        plt.show()
    
    def create_trade_distribution_chart(self, trades: List[Trade], 
                                      by: str = 'hour') -> None:
        """Create a chart showing trade distribution by time of day/week"""
        if not trades:
            print("No trades to display")
            return
            
        # Collect trades by time period
        counts = {}
        wins = {}
        losses = {}
        
        if by == 'hour':
            # Distribution by hour of day
            for i in range(24):
                counts[i] = 0
                wins[i] = 0
                losses[i] = 0
                
            for trade in trades:
                hour = trade.close_time.hour
                counts[hour] += 1
                if trade.is_winning:
                    wins[hour] += 1
                else:
                    losses[hour] += 1
                    
            labels = [f"{h:02d}" for h in range(24)]
            
        elif by == 'day':
            # Distribution by day of week
            days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            for i in range(7):
                counts[i] = 0
                wins[i] = 0
                losses[i] = 0
                
            for trade in trades:
                day = trade.close_time.weekday()
                counts[day] += 1
                if trade.is_winning:
                    wins[day] += 1
                else:
                    losses[day] += 1
                    
            labels = days
            
        else:
            print(f"Unknown distribution type: {by}")
            return
        
        # Extract data for plotting
        x = list(range(len(labels)))
        win_values = [wins[i] for i in range(len(labels))]
        loss_values = [losses[i] for i in range(len(labels))]
        
        # Create the chart
        plt.clear_figure()
        
        # Plot stacked bars
        plt.multiple_bar(
            x, 
            [win_values, loss_values],
            labels=labels,
            color=["green", "red"],
            width=0.6
        )
        
        # Set title and labels
        title = "Trade Distribution by Hour" if by == 'hour' else "Trade Distribution by Day"
        plt.title(title)
        plt.xlabel(by.capitalize())
        plt.ylabel("Number of Trades")
        
        # Show the plot
        plt.show()
    
    def create_pnl_by_month_heatmap(self, trades: List[Trade]) -> None:
        """Create a heatmap of P&L by month and year"""
        if not trades:
            print("No trades to display")
            return
            
        # Find min and max dates in trades
        dates = [t.close_time for t in trades]
        min_date = min(dates)
        max_date = max(dates)
        
        # Calculate number of years and months to display
        years = list(range(min_date.year, max_date.year + 1))
        months = list(range(1, 13))
        
        # Collect P&L by year and month
        pnl_data = {}
        for year in years:
            pnl_data[year] = {}
            for month in months:
                pnl_data[year][month] = 0
        
        # Aggregate P&L
        for trade in trades:
            year = trade.close_time.year
            month = trade.close_time.month
            if year in pnl_data and month in pnl_data[year]:
                pnl_data[year][month] += trade.pnl
        
        # Convert to 2D array for heatmap
        data = []
        for year in years:
            row = [pnl_data[year][month] for month in months]
            data.append(row)
        
        # Create labels
        y_labels = [str(year) for year in years]
        x_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        # Create the heatmap
        plt.clear_figure()
        plt.colormap('seismic')  # This colormap goes from blue to red through white
        plt.heatmap(data, x_labels, y_labels)
        
        plt.title("P&L by Month")
        plt.xlabel("Month")
        plt.ylabel("Year")
        
        # Show the plot
        plt.show()
    
    def create_asset_allocation_chart(self, trades: List[Trade]) -> None:
        """Create a chart showing asset allocation"""
        if not trades:
            print("No trades to display")
            return
            
        # Count trades by symbol
        trades_by_symbol = {}
        for trade in trades:
            if trade.symbol not in trades_by_symbol:
                trades_by_symbol[trade.symbol] = 0
            trades_by_symbol[trade.symbol] += 1
        
        # Sort symbols by trade count
        sorted_symbols = sorted(
            trades_by_symbol.keys(),
            key=lambda s: trades_by_symbol[s],
            reverse=True
        )
        
        # Prepare data for chart
        labels = sorted_symbols[:10]  # Top 10 symbols
        values = [trades_by_symbol[s] for s in labels]
        
        # Create the chart
        plt.clear_figure()
        plt.bar(labels, values, width=0.6)
        
        plt.title("Trades by Symbol")
        plt.xlabel("Symbol")
        plt.ylabel("Number of Trades")
        
        # Show the plot
        plt.show()
    
    def create_winning_trades_chart(self, trades: List[Trade], limit: int = 10) -> None:
        """Create a chart of best and worst trades"""
        if not trades:
            print("No trades to display")
            return
            
        # Get best and worst trades
        best_trades = self.calculator.get_best_trades(trades, limit)
        worst_trades = self.calculator.get_worst_trades(trades, limit)
        
        # Prepare data for chart
        best_labels = [f"{t.symbol}/{t.id[:4]}" for t in best_trades]
        best_values = [t.pnl for t in best_trades]
        
        worst_labels = [f"{t.symbol}/{t.id[:4]}" for t in worst_trades]
        worst_values = [t.pnl for t in worst_trades]
        
        # Combine into one chart
        labels = best_labels + worst_labels
        values = best_values + worst_values
        colors = ["green"] * len(best_labels) + ["red"] * len(worst_labels)
        
        # Create the chart
        plt.clear_figure()
        plt.bar(labels, values, color=colors, width=0.6)
        
        plt.title(f"Best and Worst {limit} Trades")
        plt.xlabel("Symbol/ID")
        plt.ylabel("P&L")
        
        # Show the plot
        plt.show()
    
    def create_risk_metrics_panel(self, trades: List[Trade]) -> Panel:
        """Create a panel showing risk metrics"""
        if not trades:
            return Panel("No trades to analyze", title="Risk Metrics")
        
        # Calculate risk metrics
        max_dd, dd_start, dd_end = self.calculator.calculate_max_drawdown(trades)
        sharpe = self.calculator.calculate_sharpe_ratio(trades)
        sortino = self.calculator.calculate_sortino_ratio(trades)
        total_pnl = self.calculator.calculate_total_pnl(trades)
        
        # Calculate additional risk metrics
        if max_dd > 0:
            recovery_factor = abs(total_pnl / max_dd) if max_dd != 0 else float('inf')
        else:
            recovery_factor = float('inf')
        
        # Max consecutive wins/losses
        max_wins, max_losses = self.calculator.calculate_consecutive_wins_losses(trades)
        
        # Create a rich Text object for formatting
        risk_text = Text()
        
        # Add metrics with appropriate formatting
        risk_text.append("Sharpe Ratio: ", style="bold")
        risk_text.append(f"{sharpe:.2f}\n", style="green" if sharpe > 1 else "yellow" if sharpe > 0 else "red")
        
        risk_text.append("Sortino Ratio: ", style="bold")
        risk_text.append(f"{sortino:.2f}\n", style="green" if sortino > 1 else "yellow" if sortino > 0 else "red")
        
        risk_text.append("Max Drawdown: ", style="bold")
        risk_text.append(f"${max_dd:.2f} ", style="red")
        if total_pnl > 0:
            risk_text.append(f"({(max_dd / (total_pnl + max_dd) * 100):.1f}%)\n", style="red")
        else:
            risk_text.append("\n")
        
        if dd_start and dd_end:
            risk_text.append("Drawdown Period: ", style="bold")
            risk_text.append(f"{dd_start.strftime('%Y-%m-%d')} to {dd_end.strftime('%Y-%m-%d')}\n")
            
            # Calculate drawdown duration
            dd_duration = dd_end - dd_start
            risk_text.append("Drawdown Duration: ", style="bold")
            risk_text.append(f"{dd_duration.days} days\n")
        
        risk_text.append("Recovery Factor: ", style="bold")
        if recovery_factor == float('inf'):
            risk_text.append("∞\n", style="green")
        else:
            risk_text.append(f"{recovery_factor:.2f}\n", style="green" if recovery_factor > 1 else "red")
        
        risk_text.append("Max Consecutive Wins: ", style="bold")
        risk_text.append(f"{max_wins}\n", style="green")
        
        risk_text.append("Max Consecutive Losses: ", style="bold")
        risk_text.append(f"{max_losses}\n", style="red")
        
        # Calculate trade expectancy
        expectancy = self.calculator.calculate_trade_expectancy(trades)
        risk_text.append("\nTrade Expectancy: ", style="bold")
        risk_text.append(f"${expectancy:.2f} per trade\n", 
                        style="green" if expectancy > 0 else "red")
        
        return Panel(risk_text, title="Risk Metrics")
    
    def display_full_dashboard(self, trades: List[Trade]) -> None:
        """Display a full dashboard with multiple panels"""
        self.clear_screen()
        
        # Create layout
        layout = Layout()
        
        # Split into top and bottom
        layout.split(
            Layout(name="top", ratio=1),
            Layout(name="bottom", ratio=1)
        )
        
        # Split top into summary and trades
        layout["top"].split_row(
            Layout(name="summary", ratio=1),
            Layout(name="trades", ratio=2)
        )
        
        # Split bottom into charts
        layout["bottom"].split_row(
            Layout(name="symbols", ratio=1),
            Layout(name="risk", ratio=1)
        )
        
        # Add content to each section
        layout["summary"].update(self.create_performance_summary(trades))
        layout["trades"].update(self.create_trade_table(trades, limit=10))
        layout["symbols"].update(self.create_symbol_performance_table(trades))
        layout["risk"].update(self.create_risk_metrics_panel(trades))
        
        # Render the layout
        self.console.print(layout)
        
        # Now render the charts (these use plotext, so they're separate)
        print("\n\nP&L Chart:\n")
        self.create_pnl_chart(trades, period='daily', show_cumulative=True)
        
        print("\n\nDrawdown Chart:\n")
        self.create_drawdown_chart(trades)
        
        print("\n\nTrade Distribution by Hour:\n")
        self.create_trade_distribution_chart(trades, by='hour')
        
        print("\n\nP&L by Month Heatmap:\n")
        self.create_pnl_by_month_heatmap(trades)
        
        print("\n\nAsset Allocation Chart:\n")
        self.create_asset_allocation_chart(trades)
        
        print("\n\nWinning Trades Chart:\n")
        self.create_winning_trades_chart(trades, limit=10) 