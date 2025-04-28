#!/bin/bash
#
# Prometheus Configuration Validation Script
# This script validates the Prometheus configuration and checks that metrics are being collected.

set -e

# Color codes for output formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Forex Trading System - Prometheus Validation ===${NC}"

# Check if Prometheus is running
if docker ps | grep -q "prometheus"; then
  echo -e "  ${GREEN}✓${NC} Prometheus container is running"
else
  echo -e "  ${RED}✗${NC} Prometheus container is not running"
  exit 1
fi

# Check if Prometheus endpoint is accessible
if curl -s --head "http://localhost:9090/-/healthy" | grep -q "200 OK"; then
  echo -e "  ${GREEN}✓${NC} Prometheus health endpoint is accessible"
else
  echo -e "  ${RED}✗${NC} Prometheus health endpoint is not accessible"
  exit 1
fi

# Check prometheus.yml with promtool
echo -e "\n${YELLOW}Checking prometheus.yml with promtool:${NC}"
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml

# Check if exporters are being scraped
echo -e "\n${YELLOW}Checking scrape targets:${NC}"
# Use Prometheus API to check target status
TARGETS=$(curl -s http://localhost:9090/api/v1/targets | jq -r '.data.activeTargets')
TOTAL_TARGETS=$(echo $TARGETS | jq '. | length')
HEALTHY_TARGETS=$(echo $TARGETS | jq '[.[] | select(.health == "up")] | length')

echo -e "  Total targets: $TOTAL_TARGETS"
echo -e "  Healthy targets: $HEALTHY_TARGETS"

if [ "$TOTAL_TARGETS" -eq "$HEALTHY_TARGETS" ]; then
  echo -e "  ${GREEN}✓${NC} All targets are being scraped successfully"
else
  echo -e "  ${RED}✗${NC} Some targets are not being scraped successfully"
  echo -e "\n${YELLOW}Problem targets:${NC}"
  echo $TARGETS | jq '[.[] | select(.health != "up")] | .[] | {job: .labels.job, instance: .labels.instance, health: .health, lastError: .lastError}'
fi

# Check if we can query some basic metrics
echo -e "\n${YELLOW}Checking basic metrics:${NC}"
METRIC_QUERIES=(
  "up"
  "node_cpu_seconds_total"
  "container_cpu_usage_seconds_total"
  "pg_stat_database_tup_fetched"
  "mongodb_connections"
  "redis_up"
  "trading_orders_total"
)

for query in "${METRIC_QUERIES[@]}"; do
  RESULT=$(curl -s "http://localhost:9090/api/v1/query?query=$query" | jq -r '.data.result | length')
  if [ "$RESULT" -gt 0 ]; then
    echo -e "  ${GREEN}✓${NC} Metric $query found with $RESULT series"
  else
    echo -e "  ${RED}✗${NC} Metric $query not found"
  fi
done

# Check recording rules
echo -e "\n${YELLOW}Checking recording rules:${NC}"
RECORDING_RULES=(
  "instance:node_cpu_utilization:avg"
  "instance:node_memory_utilization:avg"
  "trading:order_rate:5m"
  "trading:execution_latency:avg"
)

for rule in "${RECORDING_RULES[@]}"; do
  RESULT=$(curl -s "http://localhost:9090/api/v1/query?query=$rule" | jq -r '.data.result | length')
  if [ "$RESULT" -gt 0 ]; then
    echo -e "  ${GREEN}✓${NC} Recording rule $rule is active with $RESULT series"
  else
    echo -e "  ${RED}✗${NC} Recording rule $rule is not active"
  fi
done

echo -e "\n${YELLOW}Validation complete!${NC}" 