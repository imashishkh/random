"""
Dashboard module for terminal-based UI components using Rich and Textual.
"""

from .dashboard import TradingDashboard, run_dashboard
from .widgets import StatusIndicator, MetricsPanel, PriceTickerWidget, OrderBookWidget
from .utils import (
    format_currency, 
    format_percentage,
    format_time,
    generate_mock_trades,
    generate_mock_wallet,
    generate_mock_performance,
    generate_mock_agent_status,
    generate_mock_forex_prices
)

__version__ = "0.1.0" 