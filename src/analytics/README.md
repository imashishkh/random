# Trading Performance Analytics Module

This module provides comprehensive trading performance analytics and visualization capabilities for forex trading systems. It enables detailed analysis of trading performance through various metrics, charts, and visualizations.

## Module Structure

```
analytics/
├── __init__.py              # Package exports
├── data_models.py           # Core data structures
├── metrics_calculator.py    # Performance metrics calculation
├── data_fetcher.py          # Data loading from various sources
├── visualization.py         # Visualization components
├── trading_performance.py   # Main API interface
└── README.md                # This file
```

## Features

* **Comprehensive Metrics**: Calculate over 20 key trading performance metrics including win rate, profit factor, Sharpe ratio, and drawdown analysis.
* **Flexible Data Sources**: Load trade data from JSON files, CSV files, or custom APIs.
* **Mock Data Generation**: Generate realistic trading data for testing and development.
* **Rich Visualizations**: Create terminal-based charts and tables for P&L, drawdown, trade distribution, and more.
* **Time Period Analysis**: Filter and analyze trades by various time periods (daily, weekly, monthly, yearly).
* **Symbol Analysis**: Break down performance metrics by currency pair.
* **Risk Analysis**: Calculate and visualize key risk metrics.
* **Interactive Dashboard**: Display a comprehensive performance dashboard in the terminal.

## Quick Start

```python
from analytics import TradingPerformanceAnalytics

# Using mock data
analytics = TradingPerformanceAnalytics("mock", num_trades=100)

# Display the full dashboard
analytics.display_dashboard()

# Or show specific views
analytics.display_summary(period_type="last_30_days")
analytics.display_pnl_chart(period_type="this_month", period="daily")
analytics.display_risk_metrics(period_type="all_time")

# Filter by symbol
analytics.display_symbol_performance(
    period_type="this_year", 
    symbols=["EURUSD", "GBPUSD"]
)

# Get metrics programmatically
metrics = analytics.get_performance_metrics(period_type="last_90_days")
print(f"Win Rate: {metrics['win_rate']:.2f}%")
print(f"Profit Factor: {metrics['profit_factor']:.2f}")
```

## Usage with Your Own Data

### JSON File
```python
analytics = TradingPerformanceAnalytics(
    "file", 
    file_path="path/to/trades.json"
)
```

Expected JSON format:
```json
[
    {
        "id": "123",
        "symbol": "EURUSD",
        "open_time": "2023-01-01T10:00:00Z",
        "close_time": "2023-01-01T14:30:00Z",
        "direction": "BUY",
        "open_price": 1.0843,
        "close_price": 1.0923,
        "size": 1.0,
        "pnl": 80.0,
        "fees": 2.5,
        "strategy": "trend_following"
    },
    ...
]
```

### CSV File
```python
analytics = TradingPerformanceAnalytics(
    "file", 
    file_path="path/to/trades.csv"
)
```

Expected CSV format:
```
id,symbol,open_time,close_time,direction,open_price,close_price,size,pnl,fees,strategy
123,EURUSD,2023-01-01T10:00:00Z,2023-01-01T14:30:00Z,BUY,1.0843,1.0923,1.0,80.0,2.5,trend_following
...
```

## Command Line Interface

The module includes an example script for command-line usage:

```bash
# Using mock data
python src/examples/performance_dashboard_example.py --mock --num-trades 200

# Using a file
python src/examples/performance_dashboard_example.py --file path/to/trades.json

# Filtering and visualization options
python src/examples/performance_dashboard_example.py --mock \
    --period last_30_days \
    --filter-symbol EURUSD \
    --view pnl \
    --pnl-period weekly
```

## Requirements

* Python 3.7+
* Rich
* Plotext
* NumPy
* (All dependencies are listed in requirements.txt)

## License

This module is part of the Forex Trading application and is subject to the same license. 