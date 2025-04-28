#!/bin/bash
# Staging deployment script
set -e

echo "Deploying FX-Swarm staging environment..."

# Copy staging environment file if it doesn't exist
if [ ! -f .env ]; then
  cp .env.staging .env
  echo "Created .env from .env.staging"
fi

# Start services with staging configuration
docker-compose up -d

# Verify deployment health
echo "Checking service health..."
sleep 10
./scripts/health-check.sh

echo "✅ Staging environment deployed successfully"
echo "- API: http://localhost:8000"
echo "- Airflow: http://localhost:8080"
echo "- Grafana: http://localhost:3000" 