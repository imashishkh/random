# Risk Notifier Guide

## Overview

The Risk Notifier is a component that handles sending formatted risk alerts through various channels, primarily Slack. It provides a clean interface for notifying traders or system administrators about risk events, market conditions, and other important trading system information.

## Key Features

- Send notifications through Slack webhooks
- Multiple notification severity levels (INFO, WARNING, CRITICAL)
- Templated notifications with customizable fields
- Rate limiting to prevent notification flooding
- Fallback to logging when Slack is not configured
- Easy integration with the Risk Manager

## Setup and Configuration

### Environment Variables

The Risk Notifier uses the following environment variables:

```
# Required for Slack notifications
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

You can either:
1. Add this to your `.env` file
2. Set it as an environment variable
3. Pass it directly when creating the notifier

### Basic Setup

```python
from src.risk.notifier import RiskNotifier, NotificationConfig, NotificationLevel

# Using defaults (will look for SLACK_WEBHOOK_URL in environment)
notifier = RiskNotifier()

# With custom configuration
config = NotificationConfig(
    slack_webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
    rate_limit_period=60,  # 1 minute rate limit period
    rate_limit_count={
        NotificationLevel.INFO.value: 5,     # 5 info messages per minute
        NotificationLevel.WARNING.value: 3,   # 3 warning messages per minute
        NotificationLevel.CRITICAL.value: 1,  # 1 critical message per minute
    },
    fallback_to_logging=True  # Log messages if webhook fails
)
notifier = RiskNotifier(config)
```

## Sending Notifications

### Simple Notifications

For quick, non-templated notifications:

```python
# Send a simple info notification
notifier.notify_simple(
    NotificationLevel.INFO,
    "System Started",
    "Trading system has been started successfully"
)

# Send a warning
notifier.notify_simple(
    NotificationLevel.WARNING,
    "API Connection Issue",
    "Connection to exchange API is unstable"
)

# Send a critical alert
notifier.notify_simple(
    NotificationLevel.CRITICAL,
    "Emergency Shutdown",
    "Trading system has been shut down due to excessive losses"
)
```

### Templated Notifications

For more complex notifications with structured data:

1. First, create a template:

```python
from src.risk.notifier import NotificationTemplate

# Add a template for market volatility events
notifier.add_template("market_volatility_alert", NotificationTemplate(
    title="Market Volatility Alert",
    message="Unusual volatility detected in {symbol}. Current volatility is {volatility:.2f}x normal levels.",
    fields={
        "Symbol": "{symbol}",
        "Current Volatility": "{volatility:.2f}x normal",
        "Price Change": "{price_change:.2%} in {time_period}",
        "Recommendation": "{recommendation}"
    },
    actions=[
        {"text": "View Chart", "url": "{chart_url}"},
        {"text": "Adjust Risk Settings", "url": "{settings_url}"}
    ]
))
```

2. Then use the template:

```python
# Send a notification using the template
notifier.notify(
    NotificationLevel.WARNING,
    "market_volatility_alert",
    {
        "symbol": "BTCUSDT",
        "volatility": 2.5,
        "price_change": 0.045,
        "time_period": "1 hour",
        "recommendation": "Consider reducing position sizes",
        "chart_url": "https://tradingview.com/chart/BTCUSDT",
        "settings_url": "https://example.com/risk-settings"
    }
)
```

## Default Templates

The notifier comes with several built-in templates:

1. **Global Exposure Exceeded** - When total portfolio exposure exceeds limits
2. **Symbol Exposure Exceeded** - When exposure to a single symbol exceeds limits
3. **Circuit Breaker Activated** - When a trading circuit breaker is activated
4. **Emergency Shutdown** - When the system initiates an emergency shutdown

## Integrating with Risk Manager

The Risk Notifier is designed to work seamlessly with the Risk Manager component:

```python
from src.risk.notifier import RiskNotifier
from src.risk.manager import RiskManager

# Create notifier
notifier = RiskNotifier()

# Create risk manager
risk_manager = RiskManager(account_balance=100000.0)

# Override risk manager's alert methods to use the notifier
def send_slack_alert(message, severity="info"):
    return notifier.notify_simple(severity, "Risk Manager Alert", message)

risk_manager._send_slack_alert = send_slack_alert

# For more complex alerts, override specific methods
def send_risk_alerts(violations):
    if not violations:
        return
        
    for v in violations:
        if v['type'] == 'global_exposure':
            notifier.notify(
                v['severity'],
                "global_exposure_exceeded",
                {
                    "current_exposure": v['current'],
                    "exposure_limit": v['limit'],
                    "limit_type": v['severity'],
                    "portfolio_value": risk_manager.account_balance
                }
            )
        # Handle other violation types...

risk_manager._send_risk_alerts = send_risk_alerts
```

## Rate Limiting

The Risk Notifier includes built-in rate limiting to prevent notification flooding:

```python
# Configure rate limits
config = NotificationConfig(
    slack_webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
    rate_limit_period=300,  # 5 minute period
    rate_limit_count={
        NotificationLevel.INFO.value: 10,     # 10 info messages per 5 minutes
        NotificationLevel.WARNING.value: 5,    # 5 warning messages per 5 minutes
        NotificationLevel.CRITICAL.value: 2,   # 2 critical messages per 5 minutes
    }
)
notifier = RiskNotifier(config)
```

When rate limits are exceeded, the notifier will log a warning and suppress the notification.

## Advanced Usage

### Custom Templates

You can create templates for any kind of notification you need:

```python
# Add a template for margin call warnings
notifier.add_template("margin_call_warning", NotificationTemplate(
    title="Margin Call Warning",
    message="Account {account_id} is approaching margin call levels. Current margin ratio is {margin_ratio:.2f}%.",
    fields={
        "Account ID": "{account_id}",
        "Margin Ratio": "{margin_ratio:.2f}%",
        "Minimum Required": "{min_required:.2f}%",
        "Available Balance": "${available_balance:.2f}",
        "Unrealized PnL": "${unrealized_pnl:.2f}"
    },
    actions=[
        {"text": "Add Funds", "url": "{add_funds_url}"},
        {"text": "Close Positions", "url": "{positions_url}"}
    ]
))

# Adding a template for signal alerts
notifier.add_template("trading_signal", NotificationTemplate(
    title="{signal_type} Signal: {symbol}",
    message="A {signal_type} signal has been detected for {symbol} at {price}",
    fields={
        "Symbol": "{symbol}",
        "Signal Type": "{signal_type}",
        "Price": "${price:.2f}",
        "Confidence": "{confidence:.2f}%",
        "Indicators": "{indicators}",
        "Timeframe": "{timeframe}"
    }
))
```

### Disabling Notifications

You can temporarily disable notifications:

```python
# Disable all notifications
notifier.config.disable_notifications = True

# Later, re-enable them
notifier.config.disable_notifications = False
```

### Dynamic Template Formatting

Templates can include conditional formatting logic:

```python
# In your code that sends notifications
recommendation = (
    "Close positions immediately" if volatility > critical_threshold else
    "Reduce position sizes" if volatility > warning_threshold else
    "Monitor closely"
)

color = (
    "🔴" if volatility > critical_threshold else
    "🟠" if volatility > warning_threshold else
    "🟡"
)

notifier.notify(
    severity,
    "volatility_alert",
    {
        "symbol": symbol,
        "volatility": volatility,
        "threshold": threshold,
        "color": color,
        "recommendation": recommendation
    }
)
```

## Example Use Cases

### Market Condition Monitoring

```python
def monitor_market_volatility(symbols, notifier):
    for symbol in symbols:
        volatility = calculate_volatility(symbol)
        if volatility > CRITICAL_THRESHOLD:
            notifier.notify(
                NotificationLevel.CRITICAL,
                "volatility_alert",
                {"symbol": symbol, "volatility": volatility, /* other data */}
            )
        elif volatility > WARNING_THRESHOLD:
            notifier.notify(
                NotificationLevel.WARNING,
                "volatility_alert",
                {"symbol": symbol, "volatility": volatility, /* other data */}
            )
```

### System Health Checks

```python
def check_system_health(components, notifier):
    for component, status in components.items():
        if not status['healthy']:
            notifier.notify(
                NotificationLevel.WARNING,
                "system_health_alert",
                {
                    "component": component,
                    "status": "Unhealthy",
                    "message": status['message'],
                    "last_check": status['timestamp']
                }
            )
```

### Trading Performance Updates

```python
def send_daily_performance_update(performance_data, notifier):
    notifier.notify(
        NotificationLevel.INFO,
        "daily_performance",
        {
            "date": performance_data['date'],
            "total_pnl": performance_data['total_pnl'],
            "win_rate": performance_data['win_rate'],
            "trade_count": performance_data['trade_count'],
            "best_symbol": performance_data['best_symbol'],
            "worst_symbol": performance_data['worst_symbol']
        }
    )
```

## Troubleshooting

### Webhook Not Working

If your Slack notifications aren't working:

1. Check that your webhook URL is correct in the `.env` file or configuration
2. Ensure your Slack workspace and channel settings allow incoming webhooks
3. Check the application logs for any errors related to Slack API responses
4. Verify network connectivity to Slack's API servers
5. Try the `notify_simple` method to rule out template formatting issues

### Missing Notifications

If some notifications aren't showing up:

1. Check if rate limiting is suppressing them (look for "notification suppressed (rate limited)" log entries)
2. Verify that the notification level is correct for the importance of the message
3. Ensure that `disable_notifications` hasn't been set to True
4. Check for exceptions in the formatting of template variables

## Best Practices

1. **Use Appropriate Severity Levels**: Reserve CRITICAL for truly urgent issues requiring immediate action
2. **Keep Templates Clear**: Use concise language in templates with the most important information first
3. **Set Reasonable Rate Limits**: Configure rate limits based on the typical volume of alerts in your system
4. **Include Actionable Information**: Where possible, include specific actions users can take in response
5. **Avoid Alert Fatigue**: Regularly review and tune thresholds to minimize unnecessary notifications 