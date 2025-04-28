#!/bin/bash
set -e

# Script to initialize Airflow and Grafana databases and users in PostgreSQL
# This script runs automatically when the PostgreSQL container starts for the first time

# Create Airflow database and user
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE DATABASE ${AIRFLOW_DB:-airflow};
  CREATE USER ${AIRFLOW_USER:-airflow} WITH PASSWORD '${AIRFLOW_PASSWORD:-airflow}';
  GRANT ALL PRIVILEGES ON DATABASE ${AIRFLOW_DB:-airflow} TO ${AIRFLOW_USER:-airflow};
  \c ${AIRFLOW_DB:-airflow}
  GRANT ALL ON SCHEMA public TO ${AIRFLOW_USER:-airflow};
EOSQL

# Create Grafana database and read-only user
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE DATABASE grafana;
  CREATE USER ${GRAFANA_USER:-grafana_reader} WITH PASSWORD '${GRAFANA_PASSWORD:-grafana_pass}';
  GRANT ALL PRIVILEGES ON DATABASE grafana TO ${GRAFANA_USER:-grafana_reader};
  \c grafana
  GRANT ALL ON SCHEMA public TO ${GRAFANA_USER:-grafana_reader};
  
  -- Create a read-only user for Grafana to access forex database
  \c ${POSTGRES_DB:-forex}
  GRANT CONNECT ON DATABASE ${POSTGRES_DB:-forex} TO ${GRAFANA_USER:-grafana_reader};
  GRANT USAGE ON SCHEMA public TO ${GRAFANA_USER:-grafana_reader};
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO ${GRAFANA_USER:-grafana_reader};
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ${GRAFANA_USER:-grafana_reader};
EOSQL

echo "Airflow and Grafana databases and users initialized successfully" 