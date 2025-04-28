#!/bin/bash
# Test script for Docker Compose health checks
# This script helps validate the health check functionality by:
# 1. Starting all services
# 2. Verifying health status
# 3. Simulating failures
# 4. Observing recovery behavior

set -e
DOCKER_COMPOSE_FILE="../docker-compose.yml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "$SCRIPT_DIR/.."

echo "===== HEALTH CHECK TESTING SCRIPT ====="
echo "This script will test health checks and recovery for FX-Swarm services"
echo

echo "🔍 Testing health checks for all services..."

# Function to check service health
check_health() {
  SERVICE=$1
  echo "Testing $SERVICE health check..."
  HEALTH_STATUS=$(docker inspect --format='{{.State.Health.Status}}' fx-swarm_$SERVICE\_1)
  echo "Status: $HEALTH_STATUS"
  
  if [ "$HEALTH_STATUS" != "healthy" ]; then
    echo "❌ $SERVICE is not healthy!"
    docker logs fx-swarm_$SERVICE\_1 | tail -n 20
    return 1
  else
    echo "✅ $SERVICE is healthy"
    return 0
  fi
}

# Function to simulate various failures
simulate_failure() {
  local service=$1
  local failure_type=$2
  
  echo "Simulating $failure_type failure in $service..."
  
  case "$service" in
    "postgres")
      case "$failure_type" in
        "crash")
          echo "Stopping PostgreSQL service abruptly..."
          docker-compose exec postgres pg_ctl stop -m immediate
          ;;
        "network")
          echo "Simulating network partition for PostgreSQL..."
          docker-compose exec postgres iptables -A INPUT -p tcp --dport 5432 -j DROP
          sleep 30
          echo "Restoring network for PostgreSQL..."
          docker-compose exec postgres iptables -D INPUT -p tcp --dport 5432 -j DROP
          ;;
      esac
      ;;
    "redis")
      case "$failure_type" in
        "crash")
          echo "Crashing Redis service..."
          docker-compose exec redis redis-cli DEBUG SEGFAULT
          ;;
        "memory")
          echo "Simulating Redis memory exhaustion..."
          docker-compose exec redis bash -c 'redis-cli config set maxmemory 1'
          sleep 15
          echo "Restoring Redis memory settings..."
          docker-compose exec redis bash -c 'redis-cli config set maxmemory 0'
          ;;
      esac
      ;;
    "fx_swarm")
      case "$failure_type" in
        "crash")
          echo "Stopping FX-Swarm service..."
          docker-compose stop fx_swarm
          sleep 5
          echo "Restarting FX-Swarm service..."
          docker-compose start fx_swarm
          ;;
        "health")
          echo "Creating temporary health check failure..."
          # Assuming /tmp is mounted in the container
          docker-compose exec fx_swarm touch /tmp/health_failure
          sleep 30
          echo "Restoring health check..."
          docker-compose exec fx_swarm rm /tmp/health_failure
          ;;
      esac
      ;;
  esac
  
  echo "Waiting for recovery..."
  sleep 30
}

# Main test sequence
main() {
  echo "Starting all services..."
  docker-compose down
  docker-compose up -d
  
  echo "Waiting for initial startup..."
  sleep 60
  
  check_health postgres
  check_health redis
  check_health fx_swarm
  
  # Test PostgreSQL recovery
  simulate_failure "postgres" "crash"
  check_health postgres
  
  # Test Redis recovery
  simulate_failure "redis" "crash"
  check_health redis
  
  # Test application recovery
  simulate_failure "fx_swarm" "crash"
  check_health fx_swarm
  
  echo "All tests completed."
  echo "Review the results to verify health check functionality."
}

# Run tests
main 