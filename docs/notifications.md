# Notification System Documentation

The Forex Trading Bot includes a robust notification system that can alert you about important events, errors, and trading activities through various channels including email and Slack.

## Configuration

Notifications are configured through the `config/notification_config.json` file. 

### Example Configuration

```json
{
  "email": {
    "enabled": true,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "username": "your-email@gmail.com",
    "password": "your-app-password",
    "from_email": "trading-bot@yourdomain.com",
    "recipients": ["admin@yourdomain.com", "analyst@yourdomain.com"],
    "use_tls": true
  },
  "slack": {
    "enabled": true,
    "webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
    "channel": "#trading-alerts",
    "username": "ForexTradingBot"
  },
  "general": {
    "environment": "development",
    "log_notifications": true,
    "notification_level": "info"
  }
}
```

### Configuration Options

#### Email Settings:

- `enabled`: Set to `true` to enable email notifications, `false` to disable
- `smtp_server`: SMTP server address
- `smtp_port`: SMTP port (typically 587 for TLS, 465 for SSL)
- `username`: Email account username
- `password`: Email account password or app-specific password
- `from_email`: Email address that appears in the "From" field
- `recipients`: Array of email addresses to receive notifications
- `use_tls`: Set to `true` to use TLS encryption

#### Slack Settings:

- `enabled`: Set to `true` to enable Slack notifications, `false` to disable
- `webhook_url`: Your Slack workspace webhook URL
- `channel`: Slack channel to send notifications to (e.g., "#trading-alerts")
- `username`: Name that will appear as the sender in Slack

#### General Settings:

- `environment`: Environment name (e.g., "development", "production")
- `log_notifications`: Set to `true` to log all notifications to file
- `notification_level`: Minimum level for sending notifications ("error", "warning", "info")

## Using the Notification System

### Basic Usage

```python
from src.notifications.notification_manager import NotificationManager

# Initialize the notification manager
notification_manager = NotificationManager()

# Send different types of notifications
notification_manager.send_info("Daily Summary", "Trading day completed with 2.5% profit")
notification_manager.send_warning("Unusual Market Activity", "Volatility exceeding 3 standard deviations")
notification_manager.send_error("Connection Failed", "Unable to connect to broker API")

# Or use the generic method with custom level
notification_manager.send_notification(
    level="info",
    subject="Custom Notification",
    message="This is a custom notification message"
)
```

### Formatting Special Messages

The notification system includes formatters for common scenarios:

```python
# Format a model validation message
validation_result = {
    "model_name": "GBP/USD Forecaster",
    "accuracy": 0.87,
    "precision": 0.82,
    "recall": 0.85,
    "f1_score": 0.83
}
message = notification_manager.format_model_validation_message(validation_result)
notification_manager.send_info("Model Validation Results", message)

# Format a deployment message
deployment_info = {
    "model_name": "EUR/USD Predictor v2.1",
    "environment": "production",
    "version": "2.1.0",
    "timestamp": "2023-05-20T14:30:00Z",
    "status": "success"
}
message = notification_manager.format_deployment_message(deployment_info)
notification_manager.send_info("Model Deployment Update", message)
```

### Viewing Notification History

You can also retrieve the notification history:

```python
# Get the last 10 notifications
history = notification_manager.get_notification_history(limit=10)
for notification in history:
    print(f"{notification['timestamp']} - {notification['level']} - {notification['subject']}")
```

## Troubleshooting

1. **Email notifications not sending**
   - Verify SMTP settings are correct
   - For Gmail, ensure you're using an app-specific password
   - Check that recipient email addresses are valid

2. **Slack notifications not sending**
   - Verify the webhook URL is correct and active
   - Ensure the specified channel exists in your Slack workspace

3. **Missing notifications**
   - Check your `notification_level` setting; a higher level (e.g., "error") will filter out lower-level notifications
   - Verify the notification channel is enabled (`"enabled": true`)

4. **Configuration file not found**
   - By default, the system looks for `config/notification_config.json`
   - You can specify a custom path when initializing: `NotificationManager(config_path="path/to/config.json")` 