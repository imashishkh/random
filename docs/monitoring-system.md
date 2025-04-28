# Forex Trading Monitoring System Documentation

This document provides comprehensive information about the monitoring system implemented for the Forex Trading platform. The monitoring system is designed to track both infrastructure metrics and business-specific metrics to ensure high availability, performance, and reliability of the trading platform.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Components](#components)
3. [Metrics](#metrics)
4. [Dashboards](#dashboards)
5. [Alerting](#alerting)
6. [Scaling Considerations](#scaling-considerations)
7. [Troubleshooting](#troubleshooting)
8. [Operations Runbook](#operations-runbook)

## System Architecture

The monitoring system is built around a Prometheus-based metrics collection pipeline with Grafana for visualization. The architecture follows these key principles:

- **Pull-based metrics collection**: Prometheus server scrapes metrics from exporters.
- **Hierarchical metric organization**: Metrics are organized by domain (infrastructure, trading, API).
- **Standardized labeling**: Consistent labels across all metrics for better filtering and aggregation.
- **Integrated alerting**: Prometheus AlertManager for centralized alert management.
- **Dashboard-based visualization**: Grafana dashboards for different domains and use cases.

The high-level architecture diagram:

```
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│ Infrastructure │    │ Trading-Specific│    │  API/Service   │
│    Exporters   │    │    Exporters    │    │    Metrics     │
└───────┬────────┘    └────────┬────────┘    └────────┬───────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│                      Prometheus Server                       │
└─────────────────────────────┬───────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌────────────────────────┐      ┌────────────────────────┐
│      Grafana            │      │     AlertManager       │
│   (Visualization)       │      │   (Alert Management)   │
└────────────────────────┘      └────────────────────────┘
```

## Components

### Infrastructure Exporters

| Exporter | Purpose | Metrics Prefix | Primary Metrics |
|----------|---------|---------------|----------------|
| node_exporter | Hardware and OS metrics | `node_` | CPU, memory, disk, network |
| cadvisor | Container metrics | `container_` | CPU, memory, I/O for containers |
| postgres_exporter | PostgreSQL database metrics | `pg_` | Connections, queries, transaction rates |
| mongodb_exporter | MongoDB database metrics | `mongodb_` | Operations, connections, document metrics |
| redis_exporter | Redis metrics | `redis_` | Commands, memory, connections |

### Trading-Specific Exporters

| Exporter | Purpose | Metrics Prefix | Primary Metrics |
|----------|---------|---------------|----------------|
| trading_exporter | Trading system metrics | `forex_` | Trade volume, execution time, error rates |
| agent_exporter | Agent metrics | `agent_` | Agent count, operations, health |
| api_metrics | API usage metrics | `api_` | Request rate, errors, latency |

### Prometheus Server

- **Location**: Running as a Docker container (prometheus:9090)
- **Configuration**: `/config/prometheus/prometheus.yml`
- **Storage Retention**: 15 days
- **Scrape Intervals**:
  - Critical trading metrics: 15s
  - Infrastructure metrics: 30s
  - Less critical metrics: 1m

### Alert Manager

- **Location**: Running as a Docker container (alertmanager:9093)
- **Configuration**: `/config/alertmanager/alertmanager.yml`
- **Notification Channels**:
  - Email for non-urgent alerts
  - Slack/Teams for team notifications
  - PagerDuty for critical alerts

### Grafana

- **Location**: Running as a Docker container (grafana:3000)
- **Authentication**: Admin user configured via environment variables
- **Data Sources**: Prometheus
- **Dashboards**: Stored as JSON in version control

## Metrics

### Infrastructure Metrics

#### System Metrics (node_exporter)

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| node_cpu_seconds_total | Counter | CPU time spent in different modes | cpu, mode |
| node_memory_MemAvailable_bytes | Gauge | Available memory | - |
| node_memory_MemTotal_bytes | Gauge | Total memory | - |
| node_filesystem_avail_bytes | Gauge | Available space by filesystem | device, fstype, mountpoint |
| node_filesystem_size_bytes | Gauge | Total size by filesystem | device, fstype, mountpoint |
| node_network_receive_bytes_total | Counter | Network bytes received | device |
| node_network_transmit_bytes_total | Counter | Network bytes transmitted | device |
| node_disk_reads_completed_total | Counter | Completed disk read operations | device |
| node_disk_writes_completed_total | Counter | Completed disk write operations | device |

#### Container Metrics (cadvisor)

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| container_cpu_usage_seconds_total | Counter | Cumulative CPU time consumed | container_name, image |
| container_memory_usage_bytes | Gauge | Current memory usage | container_name, image |
| container_network_receive_bytes_total | Counter | Network bytes received | container_name, interface |
| container_network_transmit_bytes_total | Counter | Network bytes transmitted | container_name, interface |

#### Database Metrics

**PostgreSQL Metrics (postgres_exporter)**

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| pg_stat_database_tup_fetched | Counter | Rows fetched from database | datname |
| pg_stat_database_tup_inserted | Counter | Rows inserted into database | datname |
| pg_stat_database_tup_updated | Counter | Rows updated in database | datname |
| pg_stat_database_tup_deleted | Counter | Rows deleted from database | datname |
| pg_stat_database_xact_commit | Counter | Transactions committed | datname |
| pg_stat_database_xact_rollback | Counter | Transactions rolled back | datname |
| pg_stat_database_blks_hit | Counter | Block cache hits | datname |
| pg_stat_database_blks_read | Counter | Block reads from disk | datname |

**MongoDB Metrics (mongodb_exporter)**

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| mongodb_connections | Gauge | Current connections | state |
| mongodb_op_counters_total | Counter | Operations by type | type |
| mongodb_document_operations_total | Counter | Document operations | type |

**Redis Metrics (redis_exporter)**

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| redis_connected_clients | Gauge | Number of connected clients | - |
| redis_commands_processed_total | Counter | Total commands processed | - |
| redis_memory_used_bytes | Gauge | Used memory | - |

### Trading Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| forex_trade_volume_total | Counter | Number of trades | currency_pair, trade_type |
| forex_trade_volume_usd | Gauge | Total trading volume in USD | currency_pair |
| forex_trade_execution_seconds | Histogram | Trade execution latency | currency_pair, trade_type |
| forex_trade_errors_total | Counter | Trading errors | currency_pair, error_type |
| forex_orderbook_depth | Gauge | Depth of order book | currency_pair, side |
| agent_count | Gauge | Number of active agents | agent_type |
| agent_operations_total | Counter | Agent operations performed | agent_type, operation |
| agent_initialization_seconds | Histogram | Agent initialization time | agent_type |
| api_requests_total | Counter | API requests | endpoint, method |
| api_request_duration_seconds | Histogram | API request duration | endpoint, method |
| api_errors_total | Counter | API errors | endpoint, method, error_code |

## Dashboards

### Infrastructure Overview Dashboard

**Purpose**: Monitor the health and performance of the underlying infrastructure.

**Key Panels**:
- CPU usage across all hosts
- Memory usage across all hosts
- Service health status
- Network traffic in/out
- Disk usage percentage
- Disk I/O operations

**Template Variables**:
- Host: Filter by specific host

**Location**: `http://grafana:3000/d/infrastructure`

### Trading Activity Dashboard

**Purpose**: Monitor trading activity and performance metrics.

**Key Panels**:
- Trade volume by currency pair
- Current trading volume (USD)
- Trade distribution by currency pair
- Trade execution latency
- Order book depth
- Trade error rate

**Template Variables**:
- Currency Pair: Filter by specific currency pairs
- Time Range: Adjust the time range for analysis

**Location**: `http://grafana:3000/d/trading_volume`

### Agent Performance Dashboard

**Purpose**: Monitor agent swarm health and performance.

**Key Panels**:
- Active agents count
- Agent operations per second
- Agent initialization time
- Failed operations by type
- Agent resource utilization

**Template Variables**:
- Agent Type: Filter by agent type
- Operation: Filter by operation type

**Location**: `http://grafana:3000/d/agent_health`

### Profit/Loss Dashboard

**Purpose**: Track trading profit/loss metrics.

**Key Panels**:
- Realized P/L by currency pair
- Unrealized P/L by currency pair
- P/L trends over time
- Risk exposure metrics
- Trade success rate

**Template Variables**:
- Currency Pair: Filter by specific currency pairs
- Time Period: Select time period for analysis

**Location**: `http://grafana:3000/d/profit_loss`

### API Performance Dashboard

**Purpose**: Monitor API usage and performance.

**Key Panels**:
- Request rate by endpoint
- Response time histograms
- Error rate tracking
- Endpoint utilization heatmap
- Rate limiting metrics

**Template Variables**:
- Endpoint: Filter by specific API endpoints
- Status Code: Filter by HTTP status codes

**Location**: `http://grafana:3000/d/api_performance`

## Alerting

### Alert Rules

#### Infrastructure Alerts

| Alert Name | Severity | Description | Condition | Runbook |
|------------|----------|-------------|-----------|---------|
| HighCPUUsage | warning | High CPU usage | CPU > 85% for 5m | [CPU Runbook](#high-cpu-usage) |
| LowDiskSpace | warning | Low disk space | Disk space < 15% for 5m | [Disk Runbook](#low-disk-space) |
| InstanceDown | critical | Service instance down | up == 0 for 5m | [Service Down Runbook](#service-down) |
| HighMemoryUsage | warning | High memory usage | Memory > 90% for 5m | [Memory Runbook](#high-memory-usage) |
| DatabaseHighConnections | warning | Database connections near limit | pg_stat_activity_count > 80% of max_connections | [DB Connections Runbook](#database-high-connections) |

#### Trading Alerts

| Alert Name | Severity | Description | Condition | Runbook |
|------------|----------|-------------|-----------|---------|
| TradingVolumeDropped | warning | Trading volume dropped significantly | forex_trade_volume_total rate dropped > 50% | [Volume Drop Runbook](#trading-volume-dropped) |
| HighTradeExecutionLatency | warning | High trade execution latency | forex_trade_execution_seconds > 500ms for 5m | [Latency Runbook](#high-trade-execution-latency) |
| TradeErrorRateHigh | critical | High rate of trading errors | forex_trade_errors_total / forex_trade_volume_total > 0.05 for 5m | [Error Rate Runbook](#trade-error-rate-high) |
| AgentSwarmDegraded | warning | Agent swarm health degraded | agent_count < 80% of expected for 5m | [Agent Swarm Runbook](#agent-swarm-degraded) |
| AbnormalProfitLoss | warning | Unusual profit/loss pattern | Significant deviation from expected P/L | [P/L Anomaly Runbook](#abnormal-profit-loss) |

#### API Alerts

| Alert Name | Severity | Description | Condition | Runbook |
|------------|----------|-------------|-----------|---------|
| HighAPIErrorRate | warning | High API error rate | api_errors_total / api_requests_total > 0.05 for 5m | [API Error Runbook](#high-api-error-rate) |
| APILatencyHigh | warning | High API response times | api_request_duration_seconds > 1s for 5m | [API Latency Runbook](#api-latency-high) |
| APIRateLimitApproaching | warning | API rate limit approaching | api_rate_limit_remaining < 20% for 5m | [Rate Limit Runbook](#api-rate-limit-approaching) |

### Alert Response Procedures

#### High CPU Usage

1. Identify which processes are consuming CPU using `top` or `htop`
2. Check if this is due to normal trading activity or unexpected processes
3. For persistent high CPU:
   - Scale horizontally by adding more instances
   - Optimize code in CPU-intensive operations
   - Check for CPU-intensive queries and optimize

#### Low Disk Space

1. Identify which partition is running out of space using `df -h`
2. Check for large files that can be deleted or archived: `find / -type f -size +100M | sort -nk 5`
3. Remove old logs and temporary files
4. For persistent disk space issues:
   - Increase disk size
   - Implement log rotation
   - Move data to external storage

#### Service Down

1. Check if the service container is running: `docker ps | grep <service_name>`
2. Look for errors in the service logs: `docker logs <container_id>`
3. Attempt to restart the service: `docker restart <container_id>`
4. Check if dependencies (databases, etc.) are available
5. Escalate to on-call developer if service cannot be restored

#### High Memory Usage

1. Identify memory-consuming processes: `ps aux --sort=-%mem | head`
2. Check for memory leaks by observing if memory usage grows over time
3. Restart service if memory leak is suspected
4. For persistent memory issues:
   - Increase instance memory
   - Optimize code for memory usage
   - Implement caching or memory management strategies

#### Database High Connections

1. Check current connections: `SELECT count(*) FROM pg_stat_activity;`
2. Identify which applications are creating many connections
3. Look for connection leaks or improperly closed connections
4. Implement connection pooling or optimize connection usage
5. Consider increasing `max_connections` parameter if necessary

#### Trading Volume Dropped

1. Check market conditions to determine if this is expected behavior
2. Verify connectivity to trading APIs and data sources
3. Check for errors in trading service logs
4. Verify that trading agents are functioning correctly
5. Escalate to trading team if volume drop is not due to market conditions

#### High Trade Execution Latency

1. Check network connectivity to trading APIs
2. Monitor system resource utilization during high latency periods
3. Check for concurrent resource-intensive operations
4. Verify that database queries related to trading are optimized
5. Consider optimizing trade execution code or scaling infrastructure

#### Trade Error Rate High

1. Examine the specific error types in the logs
2. Check connectivity to trading APIs and data sources
3. Verify trading parameters and configuration
4. Check for market conditions causing higher rejection rates
5. Escalate to development team with detailed error information

#### Agent Swarm Degraded

1. Check agent logs for error messages
2. Verify that agent initialization is working correctly
3. Check resource availability for new agents
4. Restart agent manager service if necessary
5. Escalate to development team if agents cannot be restored

#### Abnormal Profit/Loss

1. Check for unusual market conditions or volatility
2. Verify trading strategy parameters
3. Check for errors in trade execution
4. Review recent trades for anomalies
5. Consider pausing trading if significant unexpected losses occur
6. Escalate to trading strategy team

#### High API Error Rate

1. Check API logs for specific error types
2. Verify that all dependent services are functioning
3. Check for rate limiting or authentication issues
4. Monitor recent changes or deployments that could affect the API
5. Escalate to API development team with detailed error information

#### API Latency High

1. Check system resource utilization
2. Monitor database performance for API-related queries
3. Check for concurrent resource-intensive operations
4. Verify network latency to API dependencies
5. Consider scaling API services horizontally if load-related

#### API Rate Limit Approaching

1. Verify the source of high API usage
2. Implement request throttling if appropriate
3. Optimize API calls to reduce frequency
4. Consider increasing rate limits if usage is legitimate
5. Cache API responses where possible to reduce call frequency

## Scaling Considerations

### Prometheus Scaling

- **Vertical Scaling**: Increase CPU and memory for Prometheus server.
- **Federation**: Implement Prometheus federation for large-scale deployments.
- **Sharding**: Shard metrics collection by domain or environment.
- **Remote Storage**: Implement remote storage for long-term metrics retention.

### Metrics Optimization

- **Cardinality Control**: Limit label values to avoid high cardinality.
- **Aggregation**: Use recording rules to pre-compute aggregates.
- **Retention Policy**: Adjust retention based on metric importance.
- **Scrape Intervals**: Adjust scrape intervals based on metric volatility.

### Grafana Scaling

- **User Session Management**: Configure session timeouts and limits.
- **Caching**: Enable query caching for frequently accessed dashboards.
- **Read-Only Data Sources**: Use read-only users for Prometheus data sources.
- **Dashboard Provisioning**: Automate dashboard deployment with provisioning.

## Troubleshooting

### Common Issues

#### Prometheus Not Scraping Metrics

1. Check if the exporter is running and accessible
2. Verify Prometheus configuration in `prometheus.yml`
3. Check for network connectivity issues between Prometheus and exporters
4. Verify that the exporter is exposing metrics on the expected endpoint
5. Check Prometheus logs for errors

#### Grafana Not Showing Data

1. Verify that Prometheus data source is configured correctly
2. Check if Prometheus has the metrics being queried
3. Test Prometheus queries directly in Prometheus UI
4. Check for syntax errors in dashboard queries
5. Verify time range selection in Grafana

#### Alerts Not Firing

1. Check if the alert rule is defined correctly
2. Verify that the alert condition is being met
3. Check AlertManager configuration
4. Verify notification channel configuration
5. Check AlertManager logs for errors

#### Exporter Failures

1. Check exporter logs for errors
2. Verify connectivity to the systems being monitored
3. Check authentication credentials if applicable
4. Verify that the exporter has sufficient permissions
5. Restart the exporter and check for initialization errors

### Diagnostic Commands

```bash
# Check Prometheus targets
curl -s http://prometheus:9090/api/v1/targets | jq .

# Check AlertManager status
curl -s http://alertmanager:9093/api/v1/status | jq .

# Validate Prometheus configuration
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml

# Check Alert Rules
docker exec prometheus promtool check rules /etc/prometheus/rules/*.yml

# Test specific alert
curl -s 'http://prometheus:9090/api/v1/query?query=ALERTS{alertname="HighCPUUsage"}'
```

## Operations Runbook

### Daily Operations

1. **Morning Check**:
   - Review active alerts
   - Check dashboard for anomalies
   - Verify all exporters are reporting data

2. **Routine Maintenance**:
   - Rotate logs if necessary
   - Check disk space on monitoring servers
   - Review long-term metric trends

3. **Alert Response**:
   - Follow alert-specific runbooks
   - Document all incidents
   - Update runbooks based on new findings

### Backup and Recovery

1. **Prometheus Data**:
   - Prometheus data is persisted in Docker volumes
   - Backup volumes regularly
   - Consider remote write for additional redundancy

2. **Grafana Configuration**:
   - Dashboard JSONs are stored in Git
   - Grafana settings are managed through environment variables
   - Backup Grafana database for saved queries and preferences

3. **Recovery Procedure**:
   - Restore Prometheus volume from backup
   - Deploy Grafana dashboards from Git
   - Restore Grafana database if necessary

### Monitoring Maintenance

1. **Adding New Metrics**:
   - Update exporter configuration
   - Update Prometheus scrape configuration
   - Create recording rules if necessary
   - Update dashboards to include new metrics

2. **Updating Alert Rules**:
   - Edit alert rule files in `/config/prometheus/rules/`
   - Validate rules with `promtool check rules`
   - Reload Prometheus configuration
   - Test alert conditions

3. **Dashboard Maintenance**:
   - Export updated dashboards to JSON
   - Commit dashboard JSONs to Git
   - Document dashboard changes
   - Consider versioning dashboards

### Training and Documentation

- Provide regular training on monitoring system
- Update documentation for new components
- Create specific runbooks for critical alerts
- Document recurring issues and resolutions

---

This documentation is intended to provide a comprehensive overview of the monitoring system. For specific questions or issues, please contact the DevOps team. 