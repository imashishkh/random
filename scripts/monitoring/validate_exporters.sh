#!/bin/bash
#
# Prometheus Exporters Validation Script
# This script validates that all configured exporters are working properly
# and exporting metrics in the correct format.

set -e

# Color codes for output formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Forex Trading System - Monitoring Exporters Validation ===${NC}"
echo "Checking all Prometheus exporters are functioning correctly..."
echo

# Function to check if a service is running
check_service_running() {
  local service=$1
  
  if docker ps | grep -q "$service"; then
    echo -e "  ${GREEN}✓${NC} $service container is running"
    return 0
  else
    echo -e "  ${RED}✗${NC} $service container is not running"
    return 1
  fi
}

# Function to check if metrics endpoint is accessible
check_metrics_endpoint() {
  local service=$1
  local port=$2
  local endpoint=${3:-"/metrics"}
  local host=${4:-"localhost"}
  
  local url="http://$host:$port$endpoint"
  echo -e "\nChecking $service metrics endpoint at $url..."
  
  if curl -s --head "$url" | grep -q "200 OK"; then
    echo -e "  ${GREEN}✓${NC} $service metrics endpoint is accessible"
    
    # Check if response contains Prometheus metrics format
    if curl -s "$url" | grep -q "^# HELP"; then
      echo -e "  ${GREEN}✓${NC} $service is exporting metrics in Prometheus format"
      return 0
    else
      echo -e "  ${RED}✗${NC} $service is not exporting metrics in Prometheus format"
      return 1
    fi
  else
    echo -e "  ${RED}✗${NC} $service metrics endpoint is not accessible"
    return 1
  fi
}

# Check system status
echo -e "${YELLOW}Checking container status:${NC}"
check_service_running "node_exporter"
check_service_running "cadvisor"
check_service_running "postgres_exporter"
check_service_running "mongodb_exporter"
check_service_running "redis_exporter"

# Check metrics endpoints
check_metrics_endpoint "Node Exporter" 9100
check_metrics_endpoint "cAdvisor" 8080
check_metrics_endpoint "PostgreSQL Exporter" 9187
check_metrics_endpoint "MongoDB Exporter" 9216
check_metrics_endpoint "Redis Exporter" 9121

# Check for important metrics
echo -e "\n${YELLOW}Checking for critical metrics:${NC}"

# Node Exporter critical metrics
if curl -s http://localhost:9100/metrics | grep -q "node_cpu_seconds_total"; then
  echo -e "  ${GREEN}✓${NC} Node Exporter: CPU metrics found"
else
  echo -e "  ${RED}✗${NC} Node Exporter: CPU metrics missing"
fi

# cAdvisor critical metrics
if curl -s http://localhost:8080/metrics | grep -q "container_cpu_usage_seconds_total"; then
  echo -e "  ${GREEN}✓${NC} cAdvisor: Container CPU metrics found"
else
  echo -e "  ${RED}✗${NC} cAdvisor: Container CPU metrics missing"
fi

# PostgreSQL Exporter critical metrics
if curl -s http://localhost:9187/metrics | grep -q "pg_stat_database_"; then
  echo -e "  ${GREEN}✓${NC} PostgreSQL Exporter: Database stats metrics found"
else
  echo -e "  ${RED}✗${NC} PostgreSQL Exporter: Database stats metrics missing"
fi

# MongoDB Exporter critical metrics
if curl -s http://localhost:9216/metrics | grep -q "mongodb_connections"; then
  echo -e "  ${GREEN}✓${NC} MongoDB Exporter: Connection metrics found"
else
  echo -e "  ${RED}✗${NC} MongoDB Exporter: Connection metrics missing"
fi

# Redis Exporter critical metrics
if curl -s http://localhost:9121/metrics | grep -q "redis_up"; then
  echo -e "  ${GREEN}✓${NC} Redis Exporter: Up metric found"
else
  echo -e "  ${RED}✗${NC} Redis Exporter: Up metric missing"
fi

echo -e "\n${YELLOW}Validation complete!${NC}" 