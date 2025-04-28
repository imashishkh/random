#!/bin/bash
# Database backup script
set -e

echo "Starting FX-Swarm data backup process..."

# Create backup directory if it doesn't exist
BACKUP_DIR="./backups/$(date +%Y-%m-%d)"
mkdir -p $BACKUP_DIR

# Backup PostgreSQL database
echo "Backing up PostgreSQL database..."
docker exec -t fx-swarm-postgres pg_dumpall -c -U postgres | gzip > "$BACKUP_DIR/postgres_$(date +%Y-%m-%d_%H-%M-%S).sql.gz"
echo "✅ PostgreSQL backup completed"

# Backup Redis data
echo "Backing up Redis data..."
docker exec -t fx-swarm-redis redis-cli SAVE
docker cp fx-swarm-redis:/data/dump.rdb "$BACKUP_DIR/redis_$(date +%Y-%m-%d_%H-%M-%S).rdb"
echo "✅ Redis backup completed"

# Backup Airflow data (optional)
if [ "$1" == "--with-airflow" ]; then
  echo "Backing up Airflow DAGs and configurations..."
  mkdir -p "$BACKUP_DIR/airflow"
  docker cp fx-swarm-airflow-webserver:/opt/airflow/dags "$BACKUP_DIR/airflow/"
  docker cp fx-swarm-airflow-webserver:/opt/airflow/plugins "$BACKUP_DIR/airflow/"
  echo "✅ Airflow backup completed"
fi

echo "✅ Backup completed successfully: $BACKUP_DIR"
echo "Files:"
ls -lh $BACKUP_DIR 