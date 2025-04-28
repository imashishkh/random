#!/bin/bash
# scripts/measure-health-check-impact.sh

echo "Measuring health check performance impact..."

# Create a temporary docker-compose file without health checks
cp docker-compose.yml docker-compose.no-health.yml

# Remove health check configurations
sed -i '' '/healthcheck:/,/start_period:/d' docker-compose.no-health.yml

# Start services without health checks
echo "Starting services without health checks..."
COMPOSE_FILE=docker-compose.no-health.yml docker-compose up -d

# Measure baseline performance
echo "Measuring baseline CPU and memory usage..."
sleep 30
docker stats --no-stream > baseline.txt

# Stop services
docker-compose -f docker-compose.no-health.yml down

# Start services with health checks
echo "Starting services with health checks..."
docker-compose up -d

# Measure with health checks
echo "Measuring CPU and memory usage with health checks..."
sleep 30
docker stats --no-stream > with_health.txt

# Calculate difference
echo "Calculating performance impact..."
python3 -c '
import re
import sys

def extract_metrics(file):
    metrics = {}
    with open(file, "r") as f:
        for line in f:
            if "fx-swarm" in line or "postgres" in line or "redis" in line:
                parts = re.split(r"\s+", line.strip())
                name = parts[1]
                cpu = float(parts[2].replace("%", ""))
                mem = parts[3]
                metrics[name] = {"cpu": cpu, "mem": mem}
    return metrics

baseline = extract_metrics("baseline.txt")
with_health = extract_metrics("with_health.txt")

total_cpu_diff = 0
for name, metrics in with_health.items():
    if name in baseline:
        cpu_diff = metrics["cpu"] - baseline[name]["cpu"]
        print(f"{name}: CPU +{cpu_diff:.2f}%, Memory {metrics[\'mem\']} vs {baseline[name][\'mem\']}")
        total_cpu_diff += cpu_diff

print(f"\nTotal CPU impact: +{total_cpu_diff:.2f}%")
'

# Clean up
rm docker-compose.no-health.yml baseline.txt with_health.txt

echo "Performance measurement complete!" 