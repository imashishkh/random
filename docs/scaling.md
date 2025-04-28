# Scaling Guide for FX-Swarm

This document describes how to scale the FX-Swarm services horizontally and vertically to handle increased load.

## Table of Contents
- [Horizontal Scaling Options](#horizontal-scaling-options)
- [Vertical Scaling Options](#vertical-scaling-options)
- [Monitoring Scaled Services](#monitoring-scaled-services)
- [Load Balancing](#load-balancing)
- [Scaling Limitations](#scaling-limitations)

## Horizontal Scaling Options

Horizontal scaling involves running multiple instances of a service. The following services in FX-Swarm support horizontal scaling:

### Airflow Workers

Airflow workers can be scaled horizontally to process more tasks in parallel:

```bash
# Scale to 3 worker instances
docker-compose up -d --scale airflow-worker=3
```

This will create 3 instances of the Airflow worker. Note:
- Each worker consumes resources, ensure your host has sufficient capacity
- Workers automatically register with the scheduler
- Task execution is distributed across all available workers

### FX-Swarm Application

For the main application:

```bash
# Development/Staging
docker-compose up -d --scale fx_swarm=3

# Production
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale fx_swarm=3
```

**Important Notes:**
- When scaling the application horizontally, add a load balancer (see [Load Balancing](#load-balancing))
- Each instance must be stateless (session management in Redis, not local memory)
- Shared resources (uploads, temp files) should use a shared volume

## Vertical Scaling Options

Vertical scaling involves allocating more resources to existing services:

### PostgreSQL

Increase resources in `docker-compose.prod.yml`:

```yaml
postgres:
  deploy:
    resources:
      limits:
        cpus: "4.0"  # Increase CPU allocation
        memory: "8G"  # Increase memory
```

**Configuration Tuning:**
- Adjust `shared_buffers` to 25% of available memory
- Increase `work_mem` based on query complexity
- Optimize `effective_cache_size` to reflect available system memory

Example custom configuration:
```yaml
postgres:
  volumes:
    - ./docker/postgres/custom.conf:/etc/postgresql/postgresql.conf
  command: postgres -c config_file=/etc/postgresql/postgresql.conf
```

### Redis

Increase memory and optimize performance:

```yaml
redis:
  command: redis-server --appendonly yes --maxmemory 8gb --maxmemory-policy allkeys-lru
  deploy:
    resources:
      limits:
        cpus: "2.0"
        memory: "9G"  # Allow overhead plus maxmemory
```

**Redis Optimization:**
- Consider enabling Redis cluster mode for very large datasets
- Set `maxmemory-policy` appropriate for your use case (`allkeys-lru` is general purpose)
- Tune `tcp-backlog` for high-throughput environments

## Monitoring Scaled Services

When running scaled services, use these commands to monitor:

```bash
# Check all running containers (including scaled instances)
docker-compose ps

# Monitor resource usage of all containers
docker stats

# View logs from all instances of a scaled service
docker-compose logs fx_swarm

# View logs from a specific instance
docker-compose logs fx_swarm_1
```

### Monitoring Tools

For comprehensive monitoring of scaled services:
- The Grafana dashboard includes container-level metrics
- Use the included `/metrics` endpoint with Prometheus for custom metrics
- Check network throughput using `docker network inspect`

## Load Balancing

When scaling the application horizontally, a load balancer is required:

### Nginx Load Balancer

Example `nginx.conf` for load balancing FX-Swarm instances:

```nginx
upstream fx_swarm {
    server fx-swarm_1:8000;
    server fx-swarm_2:8000;
    server fx-swarm_3:8000;
}

server {
    listen 80;
    
    location / {
        proxy_pass http://fx_swarm;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Traefik Load Balancer

Alternatively, use Traefik for automatic service discovery:

```yaml
# In docker-compose.yml
services:
  traefik:
    image: traefik:v2.5
    command:
      - "--api.insecure=true"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
    ports:
      - "80:80"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    networks:
      - frontend_net

  fx_swarm:
    # ... existing config ...
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.fx-swarm.rule=Host(`api.example.com`)"
      - "traefik.http.services.fx-swarm.loadbalancer.server.port=8000"
```

## Scaling Limitations

Consider these limitations when scaling:

1. **Database Bottlenecks**: PostgreSQL doesn't scale horizontally in this setup. For very high loads, consider:
   - Read replicas for read-heavy workloads
   - Database sharding for extreme scale
   - Connection pooling with PgBouncer

2. **Redis Constraints**: Single Redis instance can become a bottleneck. Options:
   - Redis Cluster for distributed caching
   - Redis Sentinel for high availability

3. **Stateful Services**: Not all services can scale horizontally:
   - Airflow Scheduler (only one active scheduler allowed)
   - PostgreSQL (primary node)

4. **Network Overhead**: As services scale, network traffic increases. Ensure:
   - Network settings are optimized
   - Consider placement of services to minimize cross-network traffic
   - Monitor network throughput between services

For extremely high scale requirements beyond these recommendations, consider migrating to a Kubernetes deployment with specialized scaling strategies. 