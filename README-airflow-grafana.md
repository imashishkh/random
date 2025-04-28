# Airflow and Grafana Integration Guide

This guide provides information on how to use the Airflow and Grafana services that have been integrated into the FX-Swarm Docker Compose stack.

## Overview

The Docker Compose stack now includes:

- **Airflow**: A platform to programmatically author, schedule, and monitor workflows
- **Grafana**: A multi-platform open source analytics and interactive visualization platform

These services complement the existing core services:
- FX-Swarm application
- PostgreSQL database
- Redis cache

## Getting Started

### Prerequisites

- Docker and Docker Compose installed
- Copy `.env-example` to `.env` and fill in the required values

### Generate Airflow Fernet Key

Before starting the services, generate a Fernet key for Airflow encryption:

```bash
# Run the included script
./docker/airflow/scripts/generate_fernet_key.sh

# Add the generated key to your .env file
```

### Starting the Services

Start all services using Docker Compose:

```bash
docker-compose up -d
```

## Accessing the Services

- **Airflow Webserver**: http://localhost:8080
  - Default credentials: admin/admin

- **Grafana**: http://localhost:3000
  - Default credentials: admin/admin

## Airflow Configuration

### DAGs

Airflow DAGs (Directed Acyclic Graphs) are defined in Python files located in the `docker/airflow/dags` directory. This directory is mounted into the Airflow containers, so any changes you make will be automatically detected.

A sample DAG is included at `docker/airflow/dags/example_dag.py`.

### Connections

Airflow needs connections to interact with external systems. The following connections are pre-configured:

- **postgres_default**: Connection to the PostgreSQL database
- **redis_default**: Connection to the Redis instance

You can manage connections through the Airflow UI:
1. Navigate to Admin > Connections
2. Add or modify connections as needed

### Variables

Environment-specific configuration can be stored in Airflow Variables:

1. Navigate to Admin > Variables
2. Add variables as needed

## Grafana Configuration

### Data Sources

Grafana is pre-configured with the following data sources:

- **FX-Swarm-Main-DB**: Connection to the main forex database
- **Airflow-DB**: Connection to the Airflow database for monitoring workflow status

### Dashboards

Pre-configured dashboards are available:

- **FX-Swarm Overview**: General system status and metrics
- **Airflow Monitoring**: Workflow execution metrics and status

### Creating Custom Dashboards

You can create custom dashboards using the Grafana UI:

1. Click the "+" icon in the sidebar
2. Select "Dashboard"
3. Add panels as needed
4. Save your dashboard

To make dashboards persistent across container restarts, export them and add to the `docker/grafana/dashboards` directory.

## Health Checks

Both Airflow and Grafana have health checks configured:

- **Airflow Webserver**: Checks the `/health` endpoint
- **Airflow Scheduler**: Verifies the scheduler is running properly
- **Airflow Worker**: Confirms the Celery worker is operational
- **Grafana**: Checks the `/api/health` endpoint

You can monitor the health status using:

```bash
docker-compose ps
```

## Customization

### Airflow

- Modify environment variables in `docker-compose.yml` to change Airflow settings
- Add custom Python packages to `requirements.txt` to extend Airflow's functionality
- Adjust resource limits based on your host capabilities

### Grafana

- Add custom datasources to `docker/grafana/provisioning/datasources`
- Add custom dashboards to `docker/grafana/dashboards`
- Modify environment variables in `docker-compose.yml` to change Grafana settings

## Troubleshooting

### Airflow Issues

- Check logs: `docker-compose logs airflow-webserver`
- Verify the database connection
- Ensure Redis is running
- Check the health check script: `docker/airflow/scripts/health_check.py`

### Grafana Issues

- Check logs: `docker-compose logs grafana`
- Verify the database connection
- Check permissions for the grafana_data volume

## Production Considerations

For production deployment:

- Use a production-grade secret management solution instead of .env files
- Configure proper authentication for both Airflow and Grafana
- Set up regular backups of the PostgreSQL database
- Consider setting up monitoring for the Docker hosts
- Adjust resource limits based on workload and available resources
- Set up HTTPS for all web interfaces 