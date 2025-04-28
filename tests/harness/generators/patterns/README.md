# Market Data Pattern Configuration

This directory contains example pattern configurations for the market data generators.

## Available Pattern Types

The following pattern types are available:

### Basic Patterns
- `normal`: Random walk with small steps
- `volatile`: Random walk with larger steps (higher volatility)
- `trending_up`: Upward trend with noise
- `trending_down`: Downward trend with noise
- `range_bound`: Mean-reverting pattern within a range
- `opening`: Higher volatility with slight upward drift
- `closing`: Declining volatility with slight convergence to base price

### Advanced Patterns
- `cyclical`: Oscillating price movements with configurable frequency and amplitude
- `multi_phase`: Transitions between different pattern types with configurable durations
- `stress_test`: Base pattern with configurable stress events (crashes, spikes, gaps)
- `custom`: Custom pattern loaded from a JSON/YAML file

## Configuration Options

### Common Options
- `data_type`: Type of market data to generate (`tick`, `trade`, etc.)
- `symbols`: List of symbols to generate data for
- `rate`: Ticks per second to generate
- `burst_rate`: Optional burst rate for spike scenarios
- `volatility`: Base volatility level (e.g., 0.0002 = 0.02%)
- `realistic_spreads`: Use realistic, variable spreads based on volatility

### Cyclical Pattern Options
- `cycle_amplitude`: Amplitude of price cycles as percentage (e.g., 0.01 = 1%)
- `cycle_frequency`: Frequency of price cycles (cycles per tick)
- `cycle_phase_offset`: Starting phase offset for cyclical patterns

### Multi-Phase Pattern Options
- `phases`: List of phases, each with:
  - `type`: Pattern type for this phase
  - `duration`: Duration of this phase in ticks
  - `weight`: Weight of this phase (for blending)
- `transition_ticks`: Number of ticks for smooth transition between phases

### Stress Test Pattern Options
- `base_pattern`: Base pattern type for normal operation
- `stress_events`: List of stress events, each with:
  - `type`: Event type (`crash`, `spike`, `gap`)
  - `tick`: Tick number when the event should occur
  - `magnitude`: Magnitude of the event as percentage
  - `duration`: Duration of the event in ticks

### Custom Pattern Options
- `custom_pattern_path`: Path to custom pattern definition file

## Custom Pattern Format

Custom patterns are defined in JSON or YAML files with the following format:

```json
{
    "type": "relative",
    "modifiers": [0.0005, 0.0008, 0.0010, 0.0007, 0.0003, -0.0002, -0.0005, -0.0008, -0.0010, -0.0007, -0.0003, 0.0002],
    "description": "Example cyclical pattern with 12 points"
}
```

The available types are:
- `relative`: Modifiers are applied as percentage changes to the current price
- `absolute`: Modifiers are used as absolute prices
- `additive`: Modifiers are added to the current price

## Example Configurations

This directory includes example configurations for the different pattern types:
- `cyclical_pattern_config.json`: Example configuration for cyclical patterns
- `multi_phase_pattern_config.json`: Example configuration for multi-phase patterns
- `stress_test_pattern_config.json`: Example configuration for stress test patterns
- `example_custom_pattern.json`: Example custom pattern definition

## Usage

To use these patterns in your test harness, specify the pattern type and related parameters in your test configuration:

```python
config = {
    "data_type": "tick",
    "symbols": ["EURUSD", "GBPUSD"],
    "rate": 1000,
    "pattern": "cyclical",
    "cycle_amplitude": 0.005,
    "cycle_frequency": 0.0001,
    "volatility": 0.0002
}

generator = TickDataGenerator(config)
```

For custom patterns, specify the path to your pattern file:

```python
config = {
    "data_type": "tick",
    "symbols": ["EURUSD", "GBPUSD"],
    "rate": 1000,
    "pattern": "custom",
    "custom_pattern_path": "path/to/pattern.json",
    "volatility": 0.0002
}

generator = TickDataGenerator(config)
``` 