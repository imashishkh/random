# Technical Indicators Calculation and Orchestration System

This module provides a robust, scalable system for calculating and managing technical indicators for financial market data. It includes a multi-level caching strategy, real-time streaming calculations, and Airflow-based orchestration.

## Features

- Calculate 100+ technical indicators using TA-Lib
- Multi-level caching to avoid redundant calculations
- Real-time indicator calculation on streaming market data
- Batch processing for multiple indicators
- Airflow DAGs for orchestration and monitoring
- Horizontal scaling support for high-volume data processing

## Core Components

### IndicatorFactory

The `IndicatorFactory` is a registry for all available technical indicators. It provides a convenient way to register, retrieve, and manage indicator calculation functions.

```python
from src.indicators.factory import IndicatorFactory

# Register a custom indicator
def custom_indicator(data, **kwargs):
    # Your calculation logic here
    return result

IndicatorFactory.register('CUSTOM_IND', custom_indicator)

# Get all available indicators
all_indicators = IndicatorFactory.list_indicators()
```

### IndicatorCalculator

The `IndicatorCalculator` performs the actual indicator calculations with caching support.

```python
from src.indicators.calculator import IndicatorCalculator
from src.cache.redis_client import RedisClient

# Initialize calculator with Redis cache
redis_client = RedisClient()
calculator = IndicatorCalculator(redis_client=redis_client)

# Calculate a single indicator
sma_result = calculator.calculate(
    'SMA',
    market_data,
    params={'period': 14},
    use_cache=True,
    metadata={'symbol': 'EUR/USD', 'timeframe': '1h'}
)

# Calculate multiple indicators in batch
indicators = [
    {'name': 'SMA', 'params': {'period': 50}},
    {'name': 'RSI', 'params': {'period': 14}},
    {'name': 'MACD', 'params': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9}}
]
batch_results = calculator.batch_calculate(indicators, market_data)
```

### IndicatorStreamProcessor

The `IndicatorStreamProcessor` maintains sliding windows of market data and recalculates indicators when new data arrives.

```python
from src.indicators.stream_processor import IndicatorStreamProcessor

# Initialize stream processor
processor = IndicatorStreamProcessor(calculator, redis_client)

# Define callback for indicator updates
def on_indicator_update(symbol, timeframe, indicator, result):
    print(f"Updated {indicator} for {symbol} {timeframe}: {result.iloc[-1]}")

# Subscribe to indicator updates
processor.subscribe('EUR/USD', '1h', 'RSI', params={'period': 14}, callback=on_indicator_update)

# Process incoming market data
processor.process_market_data('EUR/USD', '1h', new_market_data)

# Start background processing (in an event loop)
await processor.start_processing()
```

## Airflow DAGs

### Technical Indicators Calculation DAG

This DAG fetches market data and calculates technical indicators on a regular schedule.

- Location: `src/airflow/dags/indicators_calculation_dag.py`
- Schedule: Every 5 minutes
- Tasks:
  - Fetch market data for each symbol/timeframe
  - Calculate technical indicators
  - Store results in the database

### Indicators Monitoring DAG

This DAG monitors the health and performance of the indicators calculation system.

- Location: `src/airflow/dags/indicators_monitoring_dag.py`
- Schedule: Every 15 minutes
- Tasks:
  - Check market data freshness
  - Verify indicator calculation status
  - Monitor cache health
  - Generate system health reports
  - Send alerts for issues

## Getting Started

1. **Install Dependencies**

   Make sure you have TA-Lib and other dependencies installed:

   ```bash
   pip install -r requirements.txt
   ```

2. **Initialize Redis**

   Ensure Redis is running for caching:

   ```bash
   docker-compose up -d redis
   ```

3. **Start Airflow**

   Initialize and start Airflow for orchestration:

   ```bash
   export AIRFLOW_HOME=/path/to/airflow
   airflow db init
   airflow webserver -p 8080
   airflow scheduler
   ```

4. **Run Example**

   Try the example script to verify everything works:

   ```bash
   python -m src.indicators.example
   ```

## Customization

### Adding New Indicators

To add a new indicator:

1. Create a function in `src/indicators/factory.py`
2. Register it with `IndicatorFactory.register('NAME', func)`
3. Use it with the calculator: `calculator.calculate('NAME', data, params)`

### Tuning Cache Settings

Adjust caching behavior in `IndicatorCalculator`:

```python
calculator = IndicatorCalculator(
    redis_client=redis_client,
    disk_cache_dir="/custom/cache/path",
    cache_ttl=7200  # 2 hours TTL
)
```

## Performance Considerations

- Use batch calculations when possible to reduce overhead
- Pre-aggregate data for long timeframes
- Use the stream processor for real-time calculations
- Horizontally scale by running multiple instances

## Examples

See `src/indicators/example.py` for comprehensive examples of using the indicator calculation system. 