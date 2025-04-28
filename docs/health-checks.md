# Health Check Strategy for FX-Swarm

This document describes the health check implementation for the FX-Swarm Docker Compose environment, including configuration details and troubleshooting information.

## Overview

Health checks are critical for ensuring service reliability in a containerized environment. They provide:

1. Automated detection of service failures
2. Proper dependency ordering during startup
3. Self-healing capabilities after failures
4. Integration with monitoring systems

## Service Health Checks

### PostgreSQL Health Check

The PostgreSQL health check uses the `pg_isready` utility:

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U postgres -d forex -h localhost -p 5432"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 30s
```

**Failure modes:**
- Database process crash
- Corrupted data files
- Resource exhaustion
- Network partition

### Redis Health Check

The Redis health check uses the `redis-cli ping` command:

```yaml
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 15s
```

**Failure modes:**
- Redis process crash
- Memory exhaustion
- Network issues

### FX-Swarm Application Health Check

The application health check calls a dedicated `/health` endpoint:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 45s
```

**Best practices for the health endpoint:**
- Check database connectivity
- Check Redis connectivity
- Verify critical application components
- Keep response times short (<1s)
- Minimize resource usage during checks

**Failure modes:**
- Application crash
- Database connectivity issues
- Redis connectivity issues
- Internal application errors
- Resource exhaustion

## Dependency Management

Services are configured to start in the correct order using the `depends_on` directive with the `condition: service_healthy` parameter:

```yaml
depends_on:
  postgres:
    condition: service_healthy
    restart: true
  redis:
    condition: service_healthy
    restart: true
```

**Startup order:**
1. PostgreSQL and Redis start simultaneously 
2. FX-Swarm application starts only after both PostgreSQL and Redis are healthy
3. (Future) Airflow and Grafana will depend on core services

The `restart: true` parameter ensures that if a dependency is restarted, dependent services are also restarted to prevent connection issues.

## Testing Health Checks

A test script is provided at `scripts/test-health-checks.sh` to verify health check functionality:

```bash
# Run the health check test script
./scripts/test-health-checks.sh
```

This script performs the following tests:
1. Starts all services
2. Verifies initial health status
3. Simulates failures in each service
4. Observes recovery behavior

## Monitoring Health Status

To check the current health status:

```bash
docker-compose ps
```

For detailed health information:

```bash
docker inspect --format='{{json .State.Health}}' container_name | jq
```

## Health Dashboard

A health dashboard is available to monitor the status of all services. To start the dashboard:

```bash
npm run health-dashboard
```

The dashboard will be available at http://localhost:3000 and automatically refreshes every 10 seconds.

## Troubleshooting

### Common Issues

1. **Services marked as unhealthy**:
   - Check container logs: `docker-compose logs service_name`
   - Verify connectivity between services

2. **Long startup times**:
   - Adjust `start_period` parameter to allow more initialization time

3. **Intermittent health check failures**:
   - Increase `retries` for flaky services

## Circuit Breaker Pattern

A circuit breaker implementation is available in `src/utils/circuit-breaker.js` to prevent cascading failures. Usage example:

```javascript
const CircuitBreaker = require('../utils/circuit-breaker');

const dbBreaker = new CircuitBreaker({
  failureThreshold: 3,
  resetTimeout: 10000
});

async function queryDatabase() {
  return dbBreaker.executeWithBreaker(async () => {
    // Database operations here
    return await db.query('SELECT * FROM users');
  });
}
```

## Health Check Best Practices

1. **Keep checks lightweight**: Health checks should be quick and consume minimal resources
2. **Test real functionality**: Verify the service can actually perform its core functions
3. **Set appropriate intervals**: Balance between quick detection and system overhead
4. **Handle transient failures**: Use retries to prevent false alarms
5. **Document expected behavior**: Ensure team understands what constitutes "healthy"

## Future Enhancements

1. **Integration with monitoring systems** (Prometheus, Grafana)
2. **Enhanced health endpoints** with more detailed diagnostics
3. **Circuit breakers** for service dependencies
4. **Health metrics collection** for trend analysis
5. **Automated recovery procedures** for specific failure modes 