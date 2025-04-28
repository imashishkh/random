# Alert Runbooks

This directory contains runbooks for handling alerts from the monitoring system. Each runbook provides step-by-step instructions for diagnosing and resolving the issue that triggered an alert.

## Runbook Structure

Each runbook follows a consistent structure:

- **Alert Name and Description**: The name of the alert and what it means
- **Severity Level**: The severity of the alert (critical, warning, info)
- **Service Impact**: How this issue affects the trading system
- **Investigation Steps**: Step-by-step guide to diagnose the issue
- **Resolution Steps**: Actions to take to resolve the issue
- **Prevention Measures**: How to prevent this issue in the future

## Runbook Categories

Runbooks are organized into the following categories:

- **Infrastructure**: Issues related to system resources, containers, and databases
  - [High CPU Usage](infrastructure/high_cpu_usage.md)
  - [Low Disk Space](infrastructure/low_disk_space.md)
  - [Instance Down](infrastructure/instance_down.md)
  - [High Memory Usage](infrastructure/high_memory_usage.md)
  - [Database Issues](infrastructure/database_issues.md)

- **Trading**: Issues related to trading operations
  - [Abnormal Trade Volume](trading/abnormal_volume.md)
  - [High Trade Execution Error Rate](trading/high_execution_error_rate.md)
  - [High Trade Execution Latency](trading/high_execution_latency.md)
  - [Agent Swarm Health](trading/agent_swarm_health.md)
  - [Unusual Profit/Loss Patterns](trading/unusual_loss_pattern.md)

- **Application**: Issues related to application services and APIs
  - [High API Error Rate](application/high_api_error_rate.md)
  - [High API Latency](application/high_api_latency.md)
  - [Service Issues](application/service_issues.md)
  - [Queue Issues](application/queue_issues.md)

## Alert Testing

To test alerts, you can:

1. Temporarily lower thresholds in the alert rules
2. Use the `amtool` utility to send test alerts
3. Simulate conditions that would trigger alerts

Example for testing with `amtool`:

```bash
# Test alert firing
amtool alert add --alertmanager.url=http://localhost:9093 \
  alertname="TestAlert" \
  severity="critical" \
  service="test" \
  instance="test:9090" \
  job="test" \
  summary="This is a test alert" \
  description="This is a test alert description"

# Check alerts
amtool alert --alertmanager.url=http://localhost:9093

# Silence an alert
amtool silence add --alertmanager.url=http://localhost:9093 \
  --comment="Testing silence" \
  --duration=1h \
  alertname="TestAlert"
``` 