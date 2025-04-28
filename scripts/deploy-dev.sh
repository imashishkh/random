#!/bin/bash
# Development deployment script
set -e

echo "Deploying FX-Swarm development environment..."

# Copy development environment file if it doesn't exist
if [ ! -f .env ]; then
  cp .env.development .env
  echo "Created .env from .env.development"
fi

# Start services with development configuration
docker-compose up -d

echo "✅ Development environment deployed successfully"
echo "- API: http://localhost:8000"
echo "- Airflow: http://localhost:8080"
echo "- Grafana: http://localhost:3000" 