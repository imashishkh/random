# Prometheus Server Setup

This document details the setup and configuration of the Prometheus server for the Forex Trading System monitoring solution.

## Overview

Prometheus is configured to scrape metrics from various exporters, with appropriate scrape intervals based on the criticality of the metrics. It also includes recording rules for query optimization and file-based service discovery for dynamic targets.

## Components

1. **Prometheus Server** (`prometheus`):
   - Container image: `prom/prometheus:v2.45.0`
   - Port: 9090
   - Storage retention: 15 days / 10GB
   - Web UI: http://localhost:9090

2. **Exporters**:
   - Node Exporter (system metrics): Port 9100
   - cAdvisor (container metrics): Port 8080
   - PostgreSQL Exporter (database metrics): Port 9187
   - MongoDB Exporter (database metrics): Port 9216
   - Redis Exporter (cache metrics): Port 9121
   - Trading Exporter (custom metrics): Port 9180

## Configuration

The main configuration is located in `config/prometheus/prometheus.yml` with the following structure:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  scrape_timeout: 10s
  external_labels:
    environment: production
    region: us-east

rule_files:
  - "rules/recording_rules.yml"

scrape_configs:
  # Various job configurations...
```

### Scrape Intervals

- Critical trading metrics: 15s
- Infrastructure metrics: 30s
- Less critical metrics: 60s

### Service Discovery

File-based service discovery is configured in the `file_sd_targets` job, with configuration files located in `config/prometheus/file_sd/`.

### Recording Rules

Recording rules are defined in `config/prometheus/rules/recording_rules.yml` and include:

- CPU and memory utilization metrics
- Trading-specific metrics (order rate, execution latency)
- API metrics (request rate, error rate)

## Validation

Run the following script to validate the Prometheus setup:

```bash
./scripts/monitoring/validate_prometheus.sh
```

This script checks:
- Prometheus server running status
- Configuration validity
- Target scraping status
- Metric availability
- Recording rule evaluation

## Grafana Integration

For visualization of Prometheus metrics, please refer to the Grafana setup documentation (coming in subtask 15.5).

## Alerting

For alerting configuration, please refer to the Alertmanager setup documentation (coming in subtask 15.4).

## Troubleshooting

### Common Issues

1. **Prometheus server not starting**:
   - Check the configuration with `promtool`
   - Ensure all required volumes are mounted correctly

2. **Exporters not being scraped**:
   - Verify network connectivity
   - Check that exporters are running and exposing metrics

3. **Missing metrics**:
   - Check exporter configuration
   - Verify scrape interval and timeout settings

### Useful Commands

- Check Prometheus configuration: `docker exec prometheus promtool check config /etc/prometheus/prometheus.yml`
- View Prometheus logs: `docker logs prometheus`
- Check target status: `curl http://localhost:9090/api/v1/targets | jq` 