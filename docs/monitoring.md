# Forex Trading System Monitoring

This document provides information about the monitoring setup for the Forex Trading System, including infrastructure metrics exporters, configuration, and usage.

## Overview

The monitoring system is built on Prometheus and provides comprehensive visibility into system and application metrics. It consists of:

1. **Infrastructure Metrics Exporters** - Collect system-level metrics from host and containers
2. **Business Metrics Exporters** - Collect trading-specific metrics (implemented in Task 15.2)
3. **Prometheus Server** - Scrapes and stores metrics (implemented in Task 15.3)
4. **Grafana Dashboards** - Visualize metrics (implemented in Task 15.5)

## Infrastructure Metrics Exporters

### Node Exporter

The [Node Exporter](https://github.com/prometheus/node_exporter) collects hardware and OS-level metrics from the host system.

- **Port**: 9100
- **Metrics Path**: /metrics
- **Key Metrics**:
  - `node_cpu_seconds_total` - CPU usage by mode (user, system, iowait, etc.)
  - `node_memory_MemFree_bytes` - Free memory in bytes
  - `node_filesystem_avail_bytes` - Available filesystem space
  - `node_network_receive_bytes_total` - Network bytes received
  - `node_disk_io_now` - Number of I/O operations currently in progress

### cAdvisor

[cAdvisor](https://github.com/google/cadvisor) provides container resource usage and performance metrics.

- **Port**: 8080
- **Metrics Path**: /metrics
- **Key Metrics**:
  - `container_cpu_usage_seconds_total` - CPU usage by container
  - `container_memory_usage_bytes` - Memory usage by container
  - `container_network_receive_bytes_total` - Network bytes received by container
  - `container_fs_usage_bytes` - Filesystem usage by container
  - `container_threads` - Number of threads in container

### PostgreSQL Exporter

The [PostgreSQL Exporter](https://github.com/prometheus-community/postgres_exporter) exports PostgreSQL database metrics.

- **Port**: 9187
- **Metrics Path**: /metrics
- **Key Metrics**:
  - `pg_stat_database_tup_fetched` - Number of rows fetched by queries
  - `pg_stat_database_xact_commit` - Number of transactions committed
  - `pg_stat_database_xact_rollback` - Number of transactions rolled back
  - `pg_stat_database_connections` - Number of active connections
  - `pg_locks_count` - Number of locks by type

### MongoDB Exporter

The [MongoDB Exporter](https://github.com/percona/mongodb_exporter) exports MongoDB database metrics.

- **Port**: 9216
- **Metrics Path**: /metrics
- **Key Metrics**:
  - `mongodb_connections` - Number of connections by state
  - `mongodb_op_counters_total` - Operation counters (insert, query, update, delete)
  - `mongodb_ss_connections` - Current connections
  - `mongodb_memory` - Memory usage by type
  - `mongodb_wiredtiger_cache` - WiredTiger cache stats

### Redis Exporter

The [Redis Exporter](https://github.com/oliver006/redis_exporter) exports Redis database metrics.

- **Port**: 9121
- **Metrics Path**: /metrics
- **Key Metrics**:
  - `redis_up` - Whether the Redis server is up (1) or down (0)
  - `redis_connected_clients` - Number of connected clients
  - `redis_commands_processed_total` - Total number of commands processed
  - `redis_memory_used_bytes` - Memory used by Redis
  - `redis_keyspace_hits_total` - Number of successful lookups of keys in the main dictionary

## Configuration

The monitoring system is configured through:

1. **Docker Compose** - Services and networking defined in `docker-compose.yml`
2. **Monitoring Config** - Exporter-specific settings in `config/monitoring.yaml`

### Adding Custom Metrics

To add custom metrics to an exporter:

1. For PostgreSQL, add custom queries to the `postgres_exporter.custom_queries` section in `config/monitoring.yaml`
2. For Node Exporter, enable additional collectors in the `node_exporter.collectors.enabled` section
3. Restart the relevant exporter container to apply changes

## Security Considerations

The current deployment has basic security measures:

1. Exporters are exposed only on localhost ports
2. A dedicated monitoring network is used
3. Read-only filesystem mounts are used where possible

For production deployments, consider:

1. Enabling TLS for all metric endpoints
2. Implementing authentication for all exporters
3. Using a reverse proxy to secure metric endpoints
4. Creating dedicated read-only users for database exporters

## Validation

To validate that the exporters are functioning correctly:

1. Run the validation script:
   ```bash
   ./scripts/monitoring/validate_exporters.sh
   ```

2. Check that all services are running and exporting metrics in the correct format
3. Verify that critical metrics are available

## Troubleshooting

Common issues and resolutions:

1. **Exporter not running**
   - Check container logs: `docker logs <container_name>`
   - Verify container configuration in `docker-compose.yml`

2. **No metrics available**
   - Check exporter configuration in `config/monitoring.yaml`
   - Verify network connectivity to the monitored service
   - Check authentication credentials for database exporters

3. **Missing specific metrics**
   - Check if the collector for those metrics is enabled
   - Verify that the monitored service is configured to expose those metrics

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Node Exporter Documentation](https://github.com/prometheus/node_exporter)
- [cAdvisor Documentation](https://github.com/google/cadvisor)
- [PostgreSQL Exporter Documentation](https://github.com/prometheus-community/postgres_exporter)
- [MongoDB Exporter Documentation](https://github.com/percona/mongodb_exporter)
- [Redis Exporter Documentation](https://github.com/oliver006/redis_exporter) 