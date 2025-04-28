# Custom Risk Notifier Example

This example demonstrates how to build a custom risk monitoring system using the `RiskNotifier` to track market volatility and correlation breakdowns between assets.

## Features

- **Volatility Monitoring**: Detects abnormal volatility in assets and sends alerts when thresholds are exceeded
- **Correlation Breakdown Detection**: Identifies significant changes in correlation between asset pairs
- **Severity-Based Alerting**: Dynamically assigns severity levels based on the magnitude of risk events
- **Custom Notification Templates**: Uses specialized templates for different types of risk events
- **Sample Data Generation**: Includes functions to generate realistic market data with volatility and correlation patterns

## Running the Example

### Prerequisites

- Python 3.7+
- Required packages: pandas, numpy
- Slack webhook URL (optional, will fall back to logging if not provided)

### Setup

1. Set up your environment variables in the `.env` file:
   ```
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   ```

2. Run the example directly:
   ```bash
   python src/risk/examples/custom_notifier_example.py
   ```

3. Or use the runner script with additional options:
   ```bash
   python run_custom_notifier.py [--debug] [--slack-webhook URL]
   ```

## Volatility Monitoring

The example calculates historical volatility for each asset using a rolling standard deviation of returns:

```python
def calculate_volatility(prices, window=20):
    """Calculate rolling volatility for a price series."""
    returns = prices.pct_change().dropna()
    volatility = returns.rolling(window=window).std() * np.sqrt(window) * 100
    return volatility
```

Volatility thresholds are configured per asset:

```python
volatility_thresholds = {
    'BTCUSD': 15.0,  # 15% threshold for BTC
    'ETHUSD': 18.0,  # 18% threshold for ETH
    'XAUUSD': 8.0,   # 8% threshold for Gold
    'default': 10.0  # Default threshold for other assets
}
```

When volatility exceeds the threshold, an alert is triggered with a severity level proportional to how much the threshold is exceeded:

- **Critical** (>2x threshold): "Consider closing positions immediately"
- **Warning** (>1.5x threshold): "Consider reducing position sizes"
- **Info** (>1x threshold): "Monitor closely for further increases"

## Correlation Breakdown Detection

The example monitors the relationship between asset pairs by comparing historical correlation with recent correlation:

```python
def monitor_correlations(notifier, market_data, correlation_thresholds):
    """Monitor correlations between assets and send alerts when significant changes occur."""
    # Historical correlation (first half of data)
    historical_corr = price_df.iloc[:mid_point].corr()
    
    # Current correlation (last n rows)
    window = correlation_thresholds.get('window', 20)
    current_corr = price_df.iloc[-window:].corr()
    
    # Calculate correlation changes
    corr_change = current_corr - historical_corr
```

When the absolute change in correlation exceeds the threshold, an alert is triggered:

```python
threshold = correlation_thresholds.get('threshold', 0.3)
if abs(change) > threshold:
    # Send alert with appropriate severity level
```

The severity is determined by the magnitude of change:

- **Critical** (>2x threshold): "Major diversification loss or regime change"
- **Warning** (>1.5x threshold): "Significant relationship change, reevaluate portfolio allocation"
- **Info** (>1x threshold): "Monitor for further changes in relationship"

## Notification Templates

The example uses two custom notification templates:

### High Volatility Alert

```python
notifier.add_template("high_volatility_alert", NotificationTemplate(
    title="High Volatility Alert",
    message="High volatility detected for {symbol}. Current volatility is {volatility:.2f}%, exceeding the {threshold:.2f}% threshold.",
    fields={
        "Symbol": "{symbol}",
        "Current Volatility": "{volatility:.2f}%",
        "Threshold": "{threshold:.2f}%",
        "Time Period": "{period} periods",
        "Current Price": "${current_price:.2f}",
        "Recommendation": "{recommendation}"
    },
    actions=[
        {"text": "View Chart", "url": "https://www.tradingview.com/chart/?symbol={symbol}"},
        {"text": "Adjust Risk Settings", "url": "https://example.com/risk-settings"}
    ]
))
```

### Correlation Breakdown Alert

```python
notifier.add_template("correlation_breakdown_alert", NotificationTemplate(
    title="Correlation Breakdown Alert",
    message="Unusual correlation breakdown detected between {symbol1} and {symbol2}.",
    fields={
        "Symbol Pair": "{symbol1}/{symbol2}",
        "Historical Correlation": "{historical_correlation:.2f}",
        "Current Correlation": "{current_correlation:.2f}",
        "Change": "{correlation_change:.2f}",
        "Analysis Period": "{period} periods",
        "Potential Impact": "{impact}"
    }
))
```

## Sample Data Generation

The example includes a `generate_sample_data()` function that creates realistic market data with:

1. Normal price movements for three assets (BTC, ETH, Gold)
2. Correlation patterns (ETH correlated with BTC, Gold less correlated)
3. A volatility shock in BTC during the last 5 periods
4. A correlation breakdown between ETH and Gold in the last 10 periods

```python
# Create a volatility shock in the last 5 days for BTC
volatility_multiplier = np.linspace(1, 5, 5)  # Gradually increasing volatility
for i in range(5):
    idx = -5 + i
    shock = np.random.normal(0, 0.05 * volatility_multiplier[i])
    market_data['BTCUSD']['close'].iloc[idx] = market_data['BTCUSD']['close'].iloc[idx-1] * (1 + shock)

# Create correlation breakdown in the last 10 days between ETH and XAU
for i in range(10):
    idx = -10 + i
    if market_data['ETHUSD']['close'].iloc[idx-1] > market_data['ETHUSD']['close'].iloc[idx-2]:
        market_data['XAUUSD']['close'].iloc[idx] = market_data['XAUUSD']['close'].iloc[idx-1] * 0.995
    else:
        market_data['XAUUSD']['close'].iloc[idx] = market_data['XAUUSD']['close'].iloc[idx-1] * 1.005
```

## Extending the Example

This example can be extended in several ways:

1. **Additional Risk Metrics**: Add support for other risk metrics like drawdown, Sharpe ratio, or VaR
2. **Real-Time Data**: Connect to exchange APIs to monitor live market data
3. **Machine Learning**: Add anomaly detection models to identify unusual market behavior
4. **Multiple Timeframes**: Monitor volatility and correlations across different timeframes
5. **Portfolio Integration**: Incorporate position sizing recommendations based on detected risk
6. **Custom Actions**: Add webhook callbacks to automatically adjust trading parameters

## Suggested Improvements

- Add more asset pairs and markets
- Implement a more sophisticated volatility calculation (e.g., GARCH model)
- Add a backtesting capability to test different threshold settings
- Create a web dashboard to visualize the risk metrics
- Add persistence to track historical alerts and risk patterns over time 