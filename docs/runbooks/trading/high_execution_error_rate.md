# Runbook: High Trade Execution Error Rate

## Alert Information

- **Alert Name**: HighTradeExecutionErrorRate / CriticalTradeExecutionErrorRate
- **Description**: The rate of errors in trade execution is above the acceptable threshold
- **Severity**: Warning (>1%) / Critical (>5%)
- **Service**: Trading

## Service Impact

Elevated trade execution error rates can have the following impacts:
- Financial loss due to failed trades
- Missed trading opportunities
- Inaccurate position management
- Potential regulatory reporting issues
- Increased latency in the trading system

## Alert Triggers

This alert triggers when:
- **Warning**: Error rate exceeds 1% for 5 minutes
- **Critical**: Error rate exceeds 5% for 3 minutes

Error rate is calculated as:
```
sum(rate(trading_execution_errors_total[5m])) by (currency_pair) / sum(rate(trading_execution_total[5m])) by (currency_pair)
```

## Investigation Steps

### 1. Determine Error Types and Patterns

```bash
# Check error types breakdown
curl -G "http://prometheus:9090/api/v1/query" --data-urlencode 'query=sum(rate(trading_execution_errors_total[10m])) by (currency_pair, error_type)'

# Check if errors are concentrated on specific currency pairs
curl -G "http://prometheus:9090/api/v1/query" --data-urlencode 'query=sum(rate(trading_execution_errors_total[10m])) by (currency_pair)'

# Check if errors correlate with trading volume
curl -G "http://prometheus:9090/api/v1/query" --data-urlencode 'query=sum(rate(trading_order_volume_total[10m])) by (currency_pair)'
```

### 2. Check System Load

```bash
# Check CPU/Memory usage
curl -G "http://prometheus:9090/api/v1/query" --data-urlencode 'query=100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
curl -G "http://prometheus:9090/api/v1/query" --data-urlencode 'query=(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100'

# Check trading service container metrics
curl -G "http://prometheus:9090/api/v1/query" --data-urlencode 'query=sum by(name, instance) (rate(container_cpu_usage_seconds_total{name=~".*trading.*"}[5m])) * 100'
```

### 3. Check External Service Dependencies

```bash
# Check database connectivity
curl -G "http://prometheus:9090/api/v1/query" --data-urlencode 'query=up{job=~"postgres_exporter|mongodb_exporter"}'

# Check database query times
curl -G "http://prometheus:9090/api/v1/query" --data-urlencode 'query=pg_stat_activity_max_tx_duration'
```

### 4. Check Logs

```bash
# Check trading service logs
docker logs trading_exporter -n 100 --tail 500 | grep -i error

# Check API logs
docker logs api -n 100 --tail 500 | grep -i error
```

### 5. Check Market Data Source

```bash
# Check if market data provider is responding
curl -v https://market-data-provider.example.com/api/health

# Check recent response times
curl -G "http://prometheus:9090/api/v1/query" --data-urlencode 'query=histogram_quantile(0.95, sum(rate(market_data_request_duration_seconds_bucket[5m])) by (le))'
```

## Resolution Steps

### For High Volume Related Errors

1. **Scale up resources if needed:**
   ```bash
   # Deploy additional trading service instances
   docker-compose up -d --scale trading_exporter=3
   ```

2. **Implement rate limiting for specific currency pairs:**
   ```bash
   # Edit configuration to add rate limits
   vim config/trading/rate_limits.yml
   # Restart services to apply changes
   docker-compose restart trading_exporter
   ```

### For External Service Dependency Issues

1. **If database related:**
   ```bash
   # Check database connection pool
   docker exec -it postgres psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"
   # Increase connection pool if needed
   vim config/database/connection_pool.conf
   docker-compose restart api
   ```

2. **If market data provider issues:**
   ```bash
   # Switch to backup provider if available
   curl -X POST http://api:8000/admin/switch-market-data-provider
   # Or enable cache mode temporarily
   curl -X POST http://api:8000/admin/enable-market-data-cache
   ```

### For System Resource Issues

1. **If memory pressure is the issue:**
   ```bash
   # Check for memory leaks
   docker exec -it trading_exporter ps -o pid,rss,command ax | sort -rn -k2 | head
   # Restart services if needed
   docker-compose restart trading_exporter
   ```

2. **If CPU is the bottleneck:**
   ```bash
   # Scale horizontally to distribute load
   docker-compose up -d --scale trading_exporter=3
   # Or adjust processing batch size
   vim config/trading/batch_size.yml
   docker-compose restart trading_exporter
   ```

## Prevention Measures

1. **Implement circuit breakers:**
   - Configure circuit breakers for external services
   - Add automatic fallback mechanisms
   - Configure per-currency pair circuit breakers

2. **Optimize resource allocation:**
   - Review and adjust resource limits in Docker Compose
   - Implement auto-scaling based on load
   - Optimize database queries

3. **Improve monitoring:**
   - Add more granular error type tracking
   - Implement automatic anomaly detection
   - Add early warning indicators before critical thresholds

4. **Review rate limits:**
   - Ensure proper rate limiting for external APIs
   - Implement backpressure mechanisms
   - Consider queue-based processing for peak loads

## Related Alerts

- [High Trade Execution Latency](./high_execution_latency.md)
- [Agent Swarm Health](./agent_swarm_health.md)
- [Abnormal Trade Volume](./abnormal_volume.md)
- [Database Issues](../infrastructure/database_issues.md)

## Contact Information

- **Primary Contact**: Trading Operations Team (trading-ops@example.com)
- **Secondary Contact**: Platform Engineering (platform-eng@example.com)
- **Escalation**: Head of Trading Technology (trading-tech-lead@example.com)
- **Slack Channel**: #trading-alerts 