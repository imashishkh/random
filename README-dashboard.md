# Forex Trading Dashboard

A terminal-based dashboard for monitoring and controlling Forex trading operations using [Rich](https://github.com/Textualize/rich) and [Textual](https://github.com/Textualize/textual) libraries.

## Features

- Real-time monitoring of account balances and trading performance
- Trading agent status and control
- Price ticker for major forex pairs
- Order book visualization
- Trading history and performance analytics
- Command-line interface for running the dashboard

## Installation

This dashboard requires Python 3.8+ and the following packages:

```bash
pip install rich textual
```

## Running the Dashboard

You can run the dashboard using the CLI interface:

```bash
# Basic usage
python src/dashboard/cli.py

# With custom refresh rate (seconds)
python src/dashboard/cli.py --refresh-rate 10

# With debug logging
python src/dashboard/cli.py --log-level DEBUG
```

## Architecture

The dashboard consists of several key components:

- `TradingDashboard`: Main application class
- Widgets: Reusable UI components (StatusIndicator, MetricsPanel, etc.)
- Utils: Helper functions for formatting and generating mock data

### Module Structure

```
src/dashboard/
├── __init__.py
├── cli.py           # Command-line interface
├── dashboard.py     # Main dashboard application
├── utils.py         # Utility functions
└── widgets.py       # Reusable UI components
```

## Keyboard Shortcuts

- `q`: Quit the application
- `r`: Refresh data manually
- `h`: Show help information

## Usage Examples

### Running in Development Mode

For development and testing, you can run the dashboard with mock data:

```bash
python src/dashboard/cli.py --dev-mode
```

### Integration with Real Trading Systems

In production, the dashboard connects to real trading data sources:

```python
from dashboard.dashboard import TradingDashboard
from exchange import get_real_account_data

# Create dashboard app
app = TradingDashboard()

# Override data sources with real implementations
app.get_account_data = get_real_account_data

# Run the app
app.run()
```

## Extending the Dashboard

You can extend the dashboard by adding new widgets or tabs:

1. Create a new widget class in `widgets.py`
2. Add the widget to the main UI composition in `TradingDashboard.compose()`
3. Add data update logic in `update_dashboard_data()` method

## License

This project is part of the Forex Trading system and inherits its license. 