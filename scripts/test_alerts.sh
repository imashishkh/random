#!/bin/bash
# Test script for Prometheus and Alertmanager alerts
# Usage: ./test_alerts.sh [fire|silence|resolve]

set -e

# Configuration
PROMETHEUS_URL="http://localhost:9090"
ALERTMANAGER_URL="http://localhost:9093"
TEST_DURATION=${TEST_DURATION:-5m}
TEST_ALERT_NAME="TestAlert"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Print usage
usage() {
  echo "Usage: $0 [fire|silence|resolve]"
  echo
  echo "Commands:"
  echo "  fire     - Trigger test alerts"
  echo "  silence  - Silence existing alerts"
  echo "  resolve  - Resolve existing alerts"
  echo
  exit 1
}

# Check if Alertmanager is running
check_alertmanager() {
  echo -e "${YELLOW}Checking Alertmanager status...${NC}"
  if curl -s "${ALERTMANAGER_URL}/-/healthy" > /dev/null; then
    echo -e "${GREEN}Alertmanager is running.${NC}"
  else
    echo -e "${RED}Alertmanager is not running or not accessible at ${ALERTMANAGER_URL}.${NC}"
    exit 1
  fi
}

# Fire test alerts
fire_alerts() {
  echo -e "${YELLOW}Firing test alerts...${NC}"
  
  # Critical alert for infrastructure
  curl -s -XPOST "${ALERTMANAGER_URL}/api/v1/alerts" -d "[{
    \"labels\": {
      \"alertname\": \"${TEST_ALERT_NAME}InfrastructureCritical\",
      \"severity\": \"critical\",
      \"service\": \"host\",
      \"instance\": \"test:9100\",
      \"job\": \"test\"
    },
    \"annotations\": {
      \"summary\": \"Critical CPU usage on test instance\",
      \"description\": \"CPU usage has been above 95% for the last 3 minutes. This is a test alert.\",
      \"dashboard\": \"http://grafana:3000/d/infrastructure\",
      \"runbook\": \"https://wiki.example.com/runbooks/infrastructure/high_cpu_usage\"
    },
    \"startsAt\": \"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\"
  }]" -H "Content-Type: application/json"
  
  echo -e "${GREEN}Infrastructure critical alert fired.${NC}"
  
  # Warning alert for trading
  curl -s -XPOST "${ALERTMANAGER_URL}/api/v1/alerts" -d "[{
    \"labels\": {
      \"alertname\": \"${TEST_ALERT_NAME}TradingWarning\",
      \"severity\": \"warning\",
      \"service\": \"trading\",
      \"currency_pair\": \"BTC/USD\",
      \"instance\": \"test:9180\",
      \"job\": \"test\"
    },
    \"annotations\": {
      \"summary\": \"High error rate in trade execution for BTC/USD\",
      \"description\": \"Error rate in trade execution for BTC/USD has been above 1% for the last 5 minutes. This is a test alert.\",
      \"dashboard\": \"http://grafana:3000/d/trading_execution\",
      \"runbook\": \"https://wiki.example.com/runbooks/trading/high_execution_error_rate\"
    },
    \"startsAt\": \"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\"
  }]" -H "Content-Type: application/json"
  
  echo -e "${GREEN}Trading warning alert fired.${NC}"
  
  # Warning alert for API
  curl -s -XPOST "${ALERTMANAGER_URL}/api/v1/alerts" -d "[{
    \"labels\": {
      \"alertname\": \"${TEST_ALERT_NAME}APIWarning\",
      \"severity\": \"warning\",
      \"service\": \"api\",
      \"endpoint\": \"/api/v1/trades\",
      \"instance\": \"test:8000\",
      \"job\": \"test\"
    },
    \"annotations\": {
      \"summary\": \"High API latency for /api/v1/trades\",
      \"description\": \"95th percentile of request duration for /api/v1/trades has been above 1s for the last 5 minutes. This is a test alert.\",
      \"dashboard\": \"http://grafana:3000/d/api_performance\",
      \"runbook\": \"https://wiki.example.com/runbooks/application/high_api_latency\"
    },
    \"startsAt\": \"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\"
  }]" -H "Content-Type: application/json"
  
  echo -e "${GREEN}API warning alert fired.${NC}"
  
  echo -e "${YELLOW}Test alerts have been fired. They will automatically resolve after ${TEST_DURATION}.${NC}"
  echo -e "${YELLOW}Check Alertmanager UI at ${ALERTMANAGER_URL} to see the alerts.${NC}"
}

# Silence alerts
silence_alerts() {
  echo -e "${YELLOW}Silencing test alerts...${NC}"
  
  # Create silences for test alerts
  SILENCE_ID=$(curl -s -XPOST "${ALERTMANAGER_URL}/api/v1/silences" -d "{
    \"matchers\": [
      {
        \"name\": \"alertname\",
        \"value\": \"${TEST_ALERT_NAME}.*\",
        \"isRegex\": true
      }
    ],
    \"startsAt\": \"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\",
    \"endsAt\": \"$(date -u -d "+${TEST_DURATION}" +"%Y-%m-%dT%H:%M:%SZ")\",
    \"createdBy\": \"test_script\",
    \"comment\": \"Silencing test alerts\"
  }" -H "Content-Type: application/json" | jq -r .silenceID)
  
  if [ -n "$SILENCE_ID" ]; then
    echo -e "${GREEN}Test alerts silenced with ID: ${SILENCE_ID}${NC}"
    echo -e "${YELLOW}The silence will expire after ${TEST_DURATION}.${NC}"
  else
    echo -e "${RED}Failed to silence alerts.${NC}"
  fi
}

# Resolve alerts
resolve_alerts() {
  echo -e "${YELLOW}Resolving test alerts...${NC}"
  
  # Resolve infrastructure alert
  curl -s -XPOST "${ALERTMANAGER_URL}/api/v1/alerts" -d "[{
    \"labels\": {
      \"alertname\": \"${TEST_ALERT_NAME}InfrastructureCritical\",
      \"severity\": \"critical\",
      \"service\": \"host\",
      \"instance\": \"test:9100\",
      \"job\": \"test\"
    },
    \"annotations\": {
      \"summary\": \"Critical CPU usage on test instance\",
      \"description\": \"CPU usage has been above 95% for the last 3 minutes. This is a test alert.\",
      \"dashboard\": \"http://grafana:3000/d/infrastructure\",
      \"runbook\": \"https://wiki.example.com/runbooks/infrastructure/high_cpu_usage\"
    },
    \"startsAt\": \"$(date -u -d "-10 minutes" +"%Y-%m-%dT%H:%M:%SZ")\",
    \"endsAt\": \"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\"
  }]" -H "Content-Type: application/json"
  
  # Resolve trading alert
  curl -s -XPOST "${ALERTMANAGER_URL}/api/v1/alerts" -d "[{
    \"labels\": {
      \"alertname\": \"${TEST_ALERT_NAME}TradingWarning\",
      \"severity\": \"warning\",
      \"service\": \"trading\",
      \"currency_pair\": \"BTC/USD\",
      \"instance\": \"test:9180\",
      \"job\": \"test\"
    },
    \"annotations\": {
      \"summary\": \"High error rate in trade execution for BTC/USD\",
      \"description\": \"Error rate in trade execution for BTC/USD has been above 1% for the last 5 minutes. This is a test alert.\",
      \"dashboard\": \"http://grafana:3000/d/trading_execution\",
      \"runbook\": \"https://wiki.example.com/runbooks/trading/high_execution_error_rate\"
    },
    \"startsAt\": \"$(date -u -d "-10 minutes" +"%Y-%m-%dT%H:%M:%SZ")\",
    \"endsAt\": \"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\"
  }]" -H "Content-Type: application/json"
  
  # Resolve API alert
  curl -s -XPOST "${ALERTMANAGER_URL}/api/v1/alerts" -d "[{
    \"labels\": {
      \"alertname\": \"${TEST_ALERT_NAME}APIWarning\",
      \"severity\": \"warning\",
      \"service\": \"api\",
      \"endpoint\": \"/api/v1/trades\",
      \"instance\": \"test:8000\",
      \"job\": \"test\"
    },
    \"annotations\": {
      \"summary\": \"High API latency for /api/v1/trades\",
      \"description\": \"95th percentile of request duration for /api/v1/trades has been above 1s for the last 5 minutes. This is a test alert.\",
      \"dashboard\": \"http://grafana:3000/d/api_performance\",
      \"runbook\": \"https://wiki.example.com/runbooks/application/high_api_latency\"
    },
    \"startsAt\": \"$(date -u -d "-10 minutes" +"%Y-%m-%dT%H:%M:%SZ")\",
    \"endsAt\": \"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\"
  }]" -H "Content-Type: application/json"
  
  echo -e "${GREEN}Test alerts have been resolved.${NC}"
}

# Main function
main() {
  # Check arguments
  if [ $# -lt 1 ]; then
    usage
  fi
  
  # Check Alertmanager
  check_alertmanager
  
  # Process command
  case "$1" in
    fire)
      fire_alerts
      ;;
    silence)
      silence_alerts
      ;;
    resolve)
      resolve_alerts
      ;;
    *)
      usage
      ;;
  esac
}

# Run main function
main "$@" 