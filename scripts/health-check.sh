#!/bin/bash
# Health check script for all services
set -e

# Check Docker service status
echo "Checking service health status..."
docker-compose ps

# Function to check container health status
check_health() {
  local container=$1
  local health=$(docker inspect --format='{{.State.Health.Status}}' $container 2>/dev/null)
  
  if [ $? -ne 0 ]; then
    echo "❌ Container $container not found"
    return 1
  fi
  
  if [ "$health" = "healthy" ]; then
    echo "✅ $container is healthy"
    return 0
  else
    echo "❌ $container is $health"
    return 1
  fi
}

# Check each service
SERVICES=(
  "fx-swarm"
  "fx-swarm-postgres"
  "fx-swarm-redis"
  "fx-swarm-airflow-webserver"
  "fx-swarm-airflow-scheduler"
  "fx-swarm-airflow-worker"
  "fx-swarm-grafana"
)

failures=0

echo "Checking individual service health..."
for service in "${SERVICES[@]}"; do
  if ! check_health "$service"; then
    failures=$((failures + 1))
  fi
done

if [ $failures -eq 0 ]; then
  echo "✅ All services are healthy"
  exit 0
else
  echo "❌ $failures services are unhealthy"
  exit 1
fi 