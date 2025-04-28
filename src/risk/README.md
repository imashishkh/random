# Risk Manager Module

## Overview

The Risk Manager module provides comprehensive risk management capabilities for a forex trading system, handling position tracking, risk metrics calculation, and risk limit enforcement. It is designed to help traders maintain disciplined risk management practices by monitoring positions in real-time and enforcing configurable risk limits.

## Key Features

- **Position Tracking**: Maintains an internal state of all current positions across different trading agents and symbols
- **Risk Metrics Calculation**: Calculates key risk metrics like total exposure, per-asset exposure, and per-symbol exposure
- **Position Update Loop**: Automatically refreshes position data at configurable intervals
- **Configuration System**: Customizable risk parameters via YAML configuration file
- **Risk Limit Enforcement**: Checks if positions exceed warning or hard thresholds and takes appropriate actions
- **Circuit Breakers**: Automatically suspends trading during extreme market conditions
- **Emergency Controls**: Provides emergency shutdown functionality for risk events

## Components

- **RiskManager**: Main class that orchestrates all risk management functionality
- **PositionDataFetcher**: Retrieves position data from the exchange with caching and error handling
- **Position Sizers**: Calculate position sizes based on risk parameters and market data
- **Circuit Breakers**: Detect and respond to abnormal market conditions

## Usage Examples

### Basic Usage

```python
from src.risk.manager import RiskManager
from src.risk.position_fetcher import PositionDataFetcher

# Initialize RiskManager with account balance and parameters
risk_manager = RiskManager(
    account_balance=10000.0,
    params={
        'max_risk_per_trade': 0.02,
        'max_asset_exposure': 0.10,
        'max_class_exposure': 0.25
    }
)

# Fetch current positions
position_fetcher = PositionDataFetcher()
positions = position_fetcher.fetch_positions()

# Update risk manager with current positions
risk_manager._update_position_tracking(positions)

# Check risk limits
risk_status = risk_manager.check_risk_limits(positions)

# Get exposure summary
exposure_summary = risk_manager.get_exposure_summary()
print(f"Total exposure: ${exposure_summary['total_exposure']:.2f}")
```

### Position Monitoring Loop

```python
def position_monitoring_loop(risk_manager, interval=60):
    """Run a continuous position monitoring loop."""
    while True:
        # Fetch latest position data
        position_fetcher = PositionDataFetcher()
        positions = position_fetcher.fetch_positions(force_refresh=True)
        
        # Update risk manager with fresh positions
        risk_manager._update_position_tracking(positions)
        
        # Check risk limits
        risk_status = risk_manager.check_risk_limits(positions)
        
        # Handle any violations
        if risk_status.get('violations'):
            print(f"Found {len(risk_status['violations'])} risk violations!")
            # Take appropriate actions
            
        # Wait for next update
        time.sleep(interval)
```

### Loading Config from YAML

```python
import yaml

# Load configuration from YAML
with open('config/risk_config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Initialize RiskManager with loaded config
risk_manager = RiskManager(
    account_balance=10000.0,
    params=config
)
```

## Configuration Options

The Risk Manager can be configured via a YAML file with the following parameters:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `max_risk_per_trade` | Maximum risk per trade as percentage of equity | 0.02 (2%) |
| `max_asset_exposure` | Maximum exposure per asset as percentage of equity | 0.10 (10%) |
| `max_class_exposure` | Maximum exposure per asset class as percentage of equity | 0.25 (25%) |
| `max_total_exposure` | Maximum total exposure as percentage of equity | 0.75 (75%) |
| `max_global_exposure` | Maximum global exposure as percentage of equity | 0.80 (80%) |
| `position_update_interval` | Position update interval in seconds | 60 |
| `circuit_breaker_enabled` | Whether circuit breakers are enabled | `true` |
| `volatility_threshold` | Volatility multiplier threshold for circuit breaker | 3.0 |
| `price_change_threshold` | Sudden price change threshold for circuit breaker | 0.05 (5%) |
| `circuit_breaker_timeout` | Circuit breaker timeout in seconds | 300 (5 min) |
| `auto_emergency_shutdown` | Whether to automatically trigger emergency shutdown | `false` |

## Monitoring Risk Metrics

The `get_exposure_summary()` method provides a comprehensive view of current risk metrics:

```python
exposure_summary = risk_manager.get_exposure_summary()

# Total exposure
total_exposure = exposure_summary['total_exposure']
total_exposure_ratio = exposure_summary['total_exposure_ratio']

# Per-asset exposure
asset_exposure = exposure_summary['asset_exposure']
for symbol, exposure in asset_exposure.items():
    exposure_ratio = exposure / risk_manager.account_balance
    print(f"{symbol} exposure: {exposure_ratio:.2%}")

# Per-class exposure
class_exposure = exposure_summary['class_exposure']
for asset_class, exposure in class_exposure.items():
    exposure_ratio = exposure / risk_manager.account_balance
    print(f"{asset_class} exposure: {exposure_ratio:.2%}")
```

## Risk Violations

Risk violations are detected by `check_risk_limits()` and returned as a list:

```python
risk_status = risk_manager.check_risk_limits()
violations = risk_status.get('violations', [])

for violation in violations:
    violation_type = violation['type']
    severity = violation['severity']
    current = violation['current']
    limit = violation['limit']
    
    if violation_type == 'global_exposure':
        print(f"Global exposure {current:.2%} exceeds limit {limit:.2%}")
    elif violation_type == 'symbol_exposure':
        symbol = violation['symbol']
        print(f"{symbol} exposure {current:.2%} exceeds limit {limit:.2%}")
```

## Circuit Breakers

Circuit breakers can be activated manually or automatically:

```python
# Check if circuit breaker is active
if risk_manager.is_circuit_breaker_active():
    print("Circuit breaker is active, trading suspended")

# Manually activate circuit breaker
risk_manager.activate_circuit_breaker(
    reason="Extreme market volatility", 
    duration=300  # 5 minutes
)

# Manually deactivate circuit breaker
risk_manager.deactivate_circuit_breaker()
```

## Emergency Controls

In case of severe risk events, the emergency shutdown can be triggered:

```python
# Trigger emergency shutdown
result = risk_manager.emergency_shutdown(reason="Risk limits severely exceeded")

if result['success']:
    print(f"Successfully closed {len(result['closed_positions'])} positions")
else:
    print(f"Emergency shutdown failed: {result.get('error')}")
```

## Advanced Features

### Slack Alerts

Configure Slack alerts for risk events:

```python
# Configure Slack alerts
risk_manager.configure_slack_alerts(webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL")
```

### Custom Position Sizers

Create and register custom position sizing algorithms:

```python
from src.risk.base import PositionSizer

class CustomPositionSizer(PositionSizer):
    # Implement custom position sizing logic
    pass

# Register custom position sizer
custom_sizer = CustomPositionSizer("custom_sizer")
risk_manager.register_position_sizer(custom_sizer)

# Use custom position sizer
position_result = risk_manager.calculate_position_size(
    symbol="EURUSD",
    market_data=market_data,
    position_sizer_name="custom_sizer"
)
``` 