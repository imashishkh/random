# Market Condition Analyzer

This module implements a market condition analyzer that detects market anomalies, regime changes, and extreme market conditions for forex trading.

## Overview

The `MarketConditionAnalyzer` is a specialized agent built on the `TechnicalAnalysisAgent` framework that focuses on detecting abnormal market conditions and regime changes. This information is valuable for:

1. Risk management - reducing exposure during highly volatile or uncertain markets
2. Strategy adjustment - modifying trading parameters based on the current market regime
3. Anomaly detection - identifying potential trading opportunities or warning signs
4. Confidence modulation - adjusting trade confidence based on current market conditions

## Key Features

- **Volatility Analysis**: Detects abnormally high or low volatility regimes
- **Liquidity Analysis**: Monitors unusual volume patterns and liquidity conditions
- **Trend State Detection**: Identifies strength and direction of the current market trend
- **Regime Change Detection**: Alerts when the market transitions between different regimes
- **Anomaly Detection**:
  - Price gaps (opening gaps, breakaway gaps)
  - Volatility clustering
  - Volume-price divergences
  - Correlation breakdowns (with configured correlated assets)
  - Pattern repetition detection (fractals)

## Usage

### Basic Usage

```python
# Create the analyzer through the factory
from src.agents.technical_analysis.factory import TechnicalAnalysisAgentFactory

# Create with default settings
analyzer = TechnicalAnalysisAgentFactory.create_market_condition_analyzer()

# Or with custom configuration
analyzer = TechnicalAnalysisAgentFactory.create_market_condition_analyzer(
    config={
        'vol_window': 20,
        'vol_threshold_high': 2.5,
        'anomaly_sensitivity': 3.0
    }
)

# Analyze market data
import pandas as pd
data = pd.DataFrame(...)  # OHLCV data
analyzer.compute_indicators(data)
signals = analyzer.generate_signals(data)

# Get market conditions
current_conditions = analyzer.conditions
print(f"Volatility state: {current_conditions['volatility_state']}")
print(f"Regime state: {current_conditions['regime_state']}")

# Check for anomalies
if current_conditions['anomalies']:
    for anomaly in current_conditions['anomalies']:
        print(f"Detected {anomaly['type']} anomaly ({anomaly['severity']})")
```

### Integration with SignalSynthesizer

The `MarketConditionAnalyzer` is automatically integrated with the `SignalSynthesizer` to adjust signal confidence based on current market conditions:

```python
from src.agents.signal_synthesizer import SignalSynthesizer

# The SignalSynthesizer creates and registers a MarketConditionAnalyzer by default
synthesizer = SignalSynthesizer()

# The market condition analyzer's signals will be included in the synthesis process
# and will affect the confidence of the final trading signal
signals = synthesizer.generate_trading_signal('EUR/USD')

# Market context is included in the result
if 'market_context' in signals:
    context = signals['market_context']
    print(f"Current market volatility: {context['volatility']}")
    print(f"Current market regime: {context['regime']}")
```

## Configuration Options

The `MarketConditionAnalyzer` supports the following configuration options:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `vol_window` | Window size for volatility calculations | 20 |
| `vol_threshold_high` | Standard deviations above mean for high volatility | 2.5 |
| `vol_threshold_low` | Standard deviations below mean for low volatility | 0.5 |
| `volume_window` | Window size for volume calculations | 20 |
| `volume_threshold` | Standard deviations for unusual volume | 2.0 |
| `trend_short_window` | Window size for short-term moving average | 20 |
| `trend_long_window` | Window size for long-term moving average | 50 |
| `trend_strength_threshold` | Minimum threshold for strong trend | 0.8 |
| `regime_window` | Window size for regime detection | 50 |
| `regime_threshold` | Change threshold for regime shift detection | 0.5 |
| `correlation_assets` | List of correlated assets to track | [] |
| `correlation_window` | Window for correlation calculations | 30 |
| `correlation_threshold` | Change threshold for correlation breakdown | 0.3 |
| `anomaly_sensitivity` | Standard deviations for anomaly detection | 3.0 |
| `anomaly_lookback` | Lookback period for anomaly detection | 100 |
| `pattern_sensitivity` | Similarity threshold for pattern matching | 0.85 |
| `pattern_min_length` | Minimum candles for pattern recognition | 5 |
| `pattern_max_length` | Maximum candles for pattern recognition | 20 |

## Signal Types

The market condition analyzer produces the following types of signals:

- `caution`: Generated for high volatility, liquidity issues, or concerning anomalies
- `opportunity`: Generated for specific conditions that may present trading opportunities
- `regime_change`: Generated when a market regime transition is detected
- `anomaly`: Generated for various detected market anomalies

## Examples

See the `src/agents/technical_analysis/examples/market_condition_example.py` for a basic demonstration of the `MarketConditionAnalyzer`.

For integration with the `SignalSynthesizer`, see `src/agents/examples/integrated_signal_example.py`.

## Adding New Anomaly Detectors

To add new anomaly detection capabilities:

1. Create a new method in the `MarketConditionAnalyzer` class following the pattern `_detect_your_anomaly_type`
2. Call your method from the `_detect_anomalies` method
3. When an anomaly is detected, add it to the `self.conditions['anomalies']` list with appropriate metadata

Example:

```python
def _detect_my_new_anomaly(self, data: pd.DataFrame) -> None:
    # Implement detection logic
    if anomaly_detected:
        self.conditions['anomalies'].append({
            'type': 'my_new_anomaly',
            'severity': 'significant',
            'value': calculated_value,
            'additional_info': extra_data
        })
``` 