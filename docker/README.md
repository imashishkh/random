# Docker Setup for Forex Trading AI System

This directory contains the Docker configuration for the Forex Trading AI System. The setup includes containers for the main application, PostgreSQL database, Redis for caching and message queueing, and Celery for background tasks.

## Prerequisites

- Docker Engine (version 20.10.0 or higher)
- Docker Compose (version 2.0.0 or higher)
- At least 4GB of free RAM

## Environment Setup

1. Copy the `.env.example` file to `.env` in the root directory:
   ```bash
   cp .env.example .env
   ```

2. Update the `.env` file with your API keys:
   - Binance API key and secret
   - OpenAI API key
   - Perplexity API key
   - Database credentials
   - Other configurations as needed

## Container Services

The Docker Compose setup includes the following services:

- **api**: The main FastAPI application
- **postgres**: PostgreSQL database for application data storage
- **redis**: Redis for caching and message queueing
- **celery_worker**: Celery worker for background tasks
- **celery_beat**: Celery beat for scheduled tasks

## Running the Environment

### Starting the Services

To start all services:

```bash
docker-compose up -d
```

To start only specific services:

```bash
docker-compose up -d postgres redis
```

### Checking Service Status

```bash
docker-compose ps
```

### Viewing Logs

For all services:

```bash
docker-compose logs -f
```

For a specific service:

```bash
docker-compose logs -f api
```

### Stopping the Services

```bash
docker-compose down
```

To stop and remove volumes (will delete all data):

```bash
docker-compose down -v
```

## Database Management

### Initialize the Database

The database will be automatically initialized with the schema defined in the `scripts/db_init` directory when the PostgreSQL container starts for the first time.

If you need to manually initialize or update the database schema:

```bash
# Inside the container
docker-compose exec api python scripts/db_migrations.py init

# Or from the host
./scripts/run_migrations.sh init
```

### Run Database Migrations

```bash
# Inside the container
docker-compose exec api python scripts/db_migrations.py migrate

# Or from the host
./scripts/run_migrations.sh migrate
```

### Create a New Migration

```bash
# Inside the container
docker-compose exec api python scripts/db_migrations.py create add_new_table

# Or from the host
./scripts/run_migrations.sh create add_new_table
```

### Backup and Restore

To backup the database:

```bash
# From the host
./scripts/backup_db.sh
```

To restore the database:

```bash
# From the host
./scripts/restore_db.sh backups/db/forex_backup_20230101_120000.sql.gz
```

## Redis Configuration

Redis is configured with:

- Persistence enabled (AOF mode)
- Memory limit of 1GB
- LRU eviction policy
- Password protection (if configured in the .env file)

The configuration file is located at `docker/redis.conf`.

## Health Checks

All services include health checks to ensure they are running correctly. You can access the application health check at:

```
http://localhost:8000/health
```

## Development Workflow

For development, the containers mount the local code directory, allowing you to make changes without rebuilding the containers. The FastAPI server will automatically reload when code changes are detected.

## Troubleshooting

### Service Startup Issues

If a service fails to start, check its logs:

```bash
docker-compose logs <service_name>
```

### Database Connection Issues

Check that the connection strings in the .env file match the Docker Compose configuration:

```
DB_HOST=postgres
DB_PORT=5432
DB_NAME=forex
DB_USER=postgres
DB_PASSWORD=postgres
```

### Redis Connection Issues

Check the Redis connection parameters:

```
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_password_here
```

### Celery Worker Issues

If the Celery workers aren't processing tasks:

```bash
docker-compose logs celery_worker
docker-compose restart celery_worker
``` 