# Trading Strategy System

This package implements a flexible, extensible trading strategy system for the Forex Trading platform using the Strategy and Factory design patterns. The system follows best practices in software design and engineering to provide a maintainable and high-performance framework for implementing and managing trading strategies.

## Architecture

The trading strategy system is built around these core components:

1. **Strategy (Interface)**: The base abstract class that all strategies must implement
2. **StrategyEngine**: Manages strategy instances and orchestrates their execution
3. **StrategyFactory**: Creates and configures strategy instances
4. **Concrete Strategies**: Implementations of specific trading strategies

### Design Patterns Used

- **Strategy Pattern**: Encapsulates different trading algorithms and makes them interchangeable
- **Factory Pattern**: Handles the creation and configuration of strategy objects
- **Observer Pattern** (implicit): Used for signal aggregation and notification
- **Composite Pattern** (implicit): Used in the way strategies can be composed and weighted

## Components

### Strategy Interface (`base.py`)

Defines the contract that all trading strategies must follow:

- `initialize()`: Set up the strategy
- `analyze(data)`: Analyze market data and produce analysis results
- `generate_signals(data)`: Generate trading signals based on market data
- `get_required_indicators()`: Report indicator dependencies
- `get_required_timeframes()`: Report timeframe dependencies

### Strategy Engine (`engine.py`)

Manages the lifecycle of strategies and orchestrates their execution:

- Register strategy classes
- Create and initialize strategy instances
- Analyze data with multiple strategies in parallel
- Generate and aggregate signals
- Manage resources and threading

### Strategy Factory (`factory.py`)

Creates strategy instances from registered strategy classes:

- Register strategy classes
- Create strategy instances with configuration
- Discover strategies automatically from the package
- Provide metadata about available strategies

### Concrete Strategies

Implementations of specific trading strategies:

- **MovingAverageCrossover**: Uses two moving averages to generate signals

## Signal System

The system generates standardized `Signal` objects with:

- Signal type (BUY, SELL, HOLD, EXIT)
- Symbol
- Price
- Timestamp
- Strength (confidence level)
- Metadata (strategy-specific information)

## Usage

### Basic Usage

```python
from src.strategies import StrategyEngine, strategy_factory
from src.strategies.moving_average_crossover import MovingAverageCrossover

# Register strategies
strategy_factory.register_strategy(MovingAverageCrossover)

# Create a strategy engine
engine = StrategyEngine()

# Create a strategy instance
engine.create_strategy(
    strategy_name="MovingAverageCrossover",
    instance_name="FastMA",
    params={
        'fast_period': 10,
        'slow_period': 30,
        'ma_type': 'ema'
    }
)

# Initialize strategies
engine.initialize_all_strategies()

# Analyze data and generate signals
data = get_market_data()  # Your data retrieval function
data_dict = {'FastMA': data}
signals = engine.generate_signals_from_all_strategies(data_dict)
```

### Advanced Usage

See `src/examples/strategy_example.py` for a comprehensive example including:

- Creating multiple strategies
- Aggregating signals with weights
- Visualizing signals on price charts

## Implementing New Strategies

To create a new strategy:

1. Create a new file in the `strategies` directory
2. Subclass the `Strategy` abstract base class
3. Implement all required methods
4. Register the strategy with `strategy_factory.register_strategy(YourStrategy)`

Example skeleton:

```python
from typing import Dict, Any, List
import pandas as pd

from .base import Strategy, Signal, SignalType

class YourStrategy(Strategy):
    def __init__(self, name: str, params: Dict[str, Any] = None):
        super().__init__(name, params)
        # Set default parameters
        self.params.setdefault('param1', default_value)
        
    def initialize(self) -> None:
        # Initialize strategy resources
        pass
        
    def analyze(self, data: pd.DataFrame) -> Dict[str, Any]:
        # Analyze market data
        return results
        
    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        # Generate trading signals
        return signals
        
    def get_required_indicators(self) -> List[str]:
        return ['indicator1', 'indicator2']
        
    def get_required_timeframes(self) -> List[str]:
        return ['1h', '4h']
```

## Performance Considerations

The strategy engine is designed for high performance:

1. Parallel execution using ThreadPoolExecutor
2. Signal aggregation optimized for speed
3. Memory-efficient data processing
4. Lazy initialization of strategy resources

## Future Enhancements

Planned improvements to this system:

1. Strategy backtrader integration
2. Machine learning strategy base class
3. Strategy configuration persistence
4. Real-time strategy performance metrics
5. GPU acceleration for compute-intensive strategies 