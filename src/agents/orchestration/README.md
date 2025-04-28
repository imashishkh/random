# Signal Validation and Orchestration System

A comprehensive system for validating, filtering, and orchestrating trading signals across multiple trading pairs.

## Overview

This system addresses the challenge of coordinating multiple market analysis agents, validating their signals, filtering out false positives, and providing a unified API for consuming trading signals.

The architecture follows a microservices approach with the following key components:

1. **Base Orchestrator**: Foundation for all orchestration functionality
2. **Signal Orchestrator**: Coordinates the signal validation and filtering pipeline
3. **Signal Validators**: Validate trading signals using various methods
4. **Signal Filters**: Filter out false positive signals
5. **Market Conditions Provider**: Analyzes market data to determine current market conditions
6. **Signal API**: Provides a unified interface for consuming validated signals

## Components

### Models

The system uses several data models to represent trading signals and market conditions:

- `TradingSignal`: Represents a trading signal from an agent
- `SignalValidationResult`: Result of validating a signal
- `SignalFilteringResult`: Result of filtering a signal
- `PublishedSignal`: A validated and filtered signal ready for consumption
- `MarketConditions`: Current market conditions for a trading pair

### Validators

Signal validators assess the quality and reliability of trading signals:

- `BaseSignalValidator`: Abstract base class for all validators
- `StatisticalValidator`: Uses statistical methods to validate signals

### Filters

Signal filters identify and remove false positive signals:

- `BaseFilter`: Abstract base class for all filters
- `MarketConditionFilter`: Filters signals based on current market conditions

### API

The system provides a unified API for consuming trading signals:

- `SignalAPI`: Offers both REST-like and streaming interfaces for accessing signals

## Getting Started

### Installation

The Signal Validation and Orchestration System is integrated directly into the project. No additional installation is required.

### Basic Usage

```python
from src.agents.orchestration import setup_orchestration_system
from src.agents.orchestration.models import TradingSignal

# Configure the system
config = {
    "log_level": "INFO",
    "orchestrator": {
        "max_signals_cache_size": 100
    },
    "validators": {
        "statistical": {
            "threshold": 0.6
        }
    },
    "filters": {
        "market_condition": {
            "volatility_threshold": 0.8
        }
    }
}

# Initialize the system with a price data provider
system = setup_orchestration_system(config, price_data_provider)

# Extract components
orchestrator = system["orchestrator"]
api = system["api"]

# Register trading pairs
orchestrator.register_trading_pair("BTC/USD")

# Subscribe to signals
def on_new_signal(signal):
    print(f"New signal: {signal.trading_pair} {signal.direction}")

api.subscribe(api_key="your_api_key", callback=on_new_signal)

# Process a signal
signal = TradingSignal(
    id="unique_id",
    trading_pair="BTC/USD",
    created_at=datetime.now(),
    agent_id="agent_1",
    signal_type="trend",
    direction="buy",
    timeframe="1h",
    strength=0.8,
    confidence=0.75
)

# Process the signal through validation and filtering
result = orchestrator.process_signal(signal)

# Check the result
if result:
    print(f"Signal published with confidence: {result.confidence}")
else:
    print("Signal rejected during validation or filtering")
```

For a more detailed example, see [`examples/simple_usage_example.py`](examples/simple_usage_example.py).

## Architecture

The system implements a multi-layered approach to signal validation and filtering:

1. **Collection**: Trading signals are collected from various market analysis agents
2. **Validation**: Signals are validated using statistical and historical methods
3. **Filtering**: False positives are filtered out based on market conditions
4. **Publication**: Valid signals are published for consumption

## Configuration

The system is highly configurable with parameters for each component:

- **Orchestrator**: Controls caching and general behavior
- **Validators**: Define thresholds and parameters for validation
- **Filters**: Configure filtering criteria
- **API**: Set up authentication and access control

## Performance and Scalability

The system is designed to handle a high volume of signals across multiple trading pairs:

- Efficient caching of signals and market conditions
- Asynchronous processing of signals
- Fine-grained control over validation and filtering thresholds
- Comprehensive performance metrics tracking

## Contributing

Extend the system by creating new validators and filters:

1. Create a new validator by extending `BaseSignalValidator`
2. Create a new filter by extending `BaseFilter`
3. Register your component with the orchestrator

## Future Enhancements

Planned improvements:

- Additional validators using machine learning models
- More sophisticated market regime detection
- Integration with real-time market data sources
- Web-based dashboard for monitoring signal quality
- Historical backtesting of validation and filtering strategies 