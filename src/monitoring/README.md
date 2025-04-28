# Trade Performance Monitoring System

This is a comprehensive monitoring system for analyzing and reporting on the performance of a Forex trading system. It collects metrics from various sources, analyzes them for bottlenecks and anomalies, and generates detailed performance reports.

## Features

- **Flexible Data Collection**: Collect performance metrics from multiple sources including:
  - Direct collection from trading system
  - Prometheus time-series database
  - CSV files

- **Comprehensive Analysis**:
  - Pattern-based bottleneck detection
  - Correlation analysis between metrics
  - Statistical anomaly detection
  - Severity assessment

- **Rich Reporting**:
  - HTML reports with color-coded severity indicators
  - JSON reports for programmatic consumption
  - Multiple report formats for different use cases

- **Configurable**: Extensive configuration options via JSON configuration files

## Architecture

The system is built around three main components:

1. **Data Collection** (`PerformanceCollector`): Gathers trade execution metrics like latency, slippage, fill rates, and more.

2. **Data Processing** (`MetricsLoader`): Processes metrics from various sources, handles preprocessing like removing outliers, interpolating missing values, and smoothing.

3. **Analysis & Reporting** (`BottleneckAnalyzer` and `PerformanceReport`): Analyzes metrics to identify bottlenecks, correlations, and anomalies, and generates detailed reports.

## Installation

### Prerequisites

- Python 3.7+
- Required Python packages (install via pip):
  ```
  pip install pandas numpy requests pytz jsonschema
  ```

### Setup

1. Clone this repository
2. Navigate to the project directory
3. Configure the system by creating a custom configuration file (see Configuration section)

## Usage

### Basic Usage

Run the performance monitoring system with default settings:

```bash
python src/monitoring/run_performance_monitor.py
```

### Specifying a Configuration File

```bash
python src/monitoring/run_performance_monitor.py --config /path/to/your/config.json
```

### Analyzing a Specific Time Range

```bash
python src/monitoring/run_performance_monitor.py --start-time "2023-06-01T00:00:00" --end-time "2023-06-02T00:00:00"
```

### Analyzing the Last Few Hours

```bash
python src/monitoring/run_performance_monitor.py --last-hours 24
```

### Changing the Report Format

```bash
python src/monitoring/run_performance_monitor.py --report-format json
```

### Using a Different Data Source

```bash
python src/monitoring/run_performance_monitor.py --data-source prometheus --prometheus-url http://your-prometheus:9090
```

```bash
python src/monitoring/run_performance_monitor.py --data-source csv --csv-dir /path/to/csv/files
```

## Configuration

The system is configured using JSON configuration files that define various aspects of its behavior.

### Default Configuration

A default configuration is provided at `src/monitoring/config/default_config.json`.

### Configuration Schema

The configuration schema is defined in `src/monitoring/config/schema.json` and includes:

- **Exchanges and Trading Pairs**: Define which exchanges and trading pairs to monitor
- **Collection Settings**: Configure data collection intervals and parameters
- **Analysis Settings**: Set thresholds for correlation and anomaly detection
- **Data Source Configuration**: Configure connection to Prometheus or CSV settings
- **Reporting Configuration**: Set report format and output directory
- **Logging Configuration**: Configure logging level and file location

### Example Configuration

```json
{
  "exchanges": ["binance", "coinbase"],
  "pairs": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
  "collection": {
    "interval": 15,
    "max_trade_history": 1000
  },
  "analysis": {
    "correlation_threshold": 0.7,
    "anomaly_z_threshold": 3.0,
    "time_window": 300,
    "min_samples": 10
  },
  "data_sources": {
    "prometheus": {
      "url": "http://localhost:9090",
      "step": "15s"
    },
    "csv": {
      "directory": "./data/metrics",
      "timestamp_column": "timestamp",
      "value_column": "value"
    }
  },
  "reporting": {
    "output_directory": "./reports",
    "format": "html",
    "save_metrics": false
  },
  "logging": {
    "level": "INFO",
    "file": "performance_monitor.log"
  }
}
```

## Command-Line Options

```
usage: run_performance_monitor.py [-h] [--config CONFIG]
                                  [--output-dir OUTPUT_DIR]
                                  [--start-time START_TIME] [--end-time END_TIME]
                                  [--last-hours LAST_HOURS]
                                  [--exchanges EXCHANGES [EXCHANGES ...]]
                                  [--pairs PAIRS [PAIRS ...]]
                                  [--report-format {html,json,both}]
                                  [--correlation-threshold CORRELATION_THRESHOLD]
                                  [--anomaly-threshold ANOMALY_THRESHOLD]
                                  [--data-source {collector,prometheus,csv}]
                                  [--prometheus-url PROMETHEUS_URL]
                                  [--csv-dir CSV_DIR]
```

## Understanding the Reports

### HTML Reports

HTML reports are designed for human readability and include:

- **Test Configuration**: Shows the parameters used for the analysis
- **Detected Bottlenecks**: Lists bottlenecks with severity indicators (high, medium, low)
- **Metric Correlations**: Shows relationships between different metrics
- **Detected Anomalies**: Highlights metrics with unusual values
- **Recommendations**: Provides actionable recommendations to address issues

### JSON Reports

JSON reports provide the same information in a machine-readable format, with additional statistical summaries for each metric.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 