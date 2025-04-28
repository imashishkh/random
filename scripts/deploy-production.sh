#!/bin/bash
# Production deployment script
set -e

echo "Deploying FX-Swarm production environment..."

# Verify secrets exist
echo "Checking for required secrets..."
for secret in postgres_password redis_password airflow_fernet_key \
  airflow_password grafana_admin_password grafana_db_password; do
  if [ ! -f "./docker/secrets/${secret}.txt" ]; then
    echo "❌ ERROR: Missing secret file: ./docker/secrets/${secret}.txt"
    echo "Please create the missing secret file before proceeding"
    exit 1
  fi
done
echo "✅ All required secrets found"

# Copy production environment file if it doesn't exist
if [ ! -f .env ]; then
  cp .env.production .env
  echo "Created .env from .env.production"
fi

# Start services with production configuration
echo "Starting services with production configuration..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Verify deployment health
echo "Checking service health..."
sleep 30
./scripts/health-check.sh

echo "✅ Production environment deployed successfully"
echo "- Grafana: https://yourdomain.com:3000"  # Assumes configured domain 