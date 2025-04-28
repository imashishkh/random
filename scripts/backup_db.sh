#!/bin/bash
# Database backup script for the Forex Trading AI System

# Load environment variables
if [ -f .env ]; then
  export $(cat .env | grep -v '#' | xargs)
else
  echo "Error: .env file not found. Please create a .env file with database credentials."
  exit 1
fi

# Configuration
BACKUP_DIR="./backups/db"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/forex_backup_${TIMESTAMP}.sql.gz"

# Default values if not in env
DB_HOST=${DB_HOST:-"localhost"}
DB_PORT=${DB_PORT:-"5432"}
DB_NAME=${DB_NAME:-"forex"}
DB_USER=${DB_USER:-"postgres"}
DB_PASSWORD=${DB_PASSWORD:-"postgres"}

# Ensure backup directory exists
mkdir -p ${BACKUP_DIR}

# Inform user
echo "Starting backup of database ${DB_NAME} on ${DB_HOST}:${DB_PORT}"
echo "Backup will be saved to ${BACKUP_FILE}"

# Perform backup using pg_dump and compress with gzip
PGPASSWORD=${DB_PASSWORD} pg_dump \
  -h ${DB_HOST} \
  -p ${DB_PORT} \
  -U ${DB_USER} \
  -F p \
  -b \
  -v \
  -f - \
  ${DB_NAME} | gzip > ${BACKUP_FILE}

# Check if backup was successful
if [ $? -eq 0 ]; then
  echo "Backup completed successfully"
  echo "Backup file: ${BACKUP_FILE}"
  echo "Backup size: $(du -h ${BACKUP_FILE} | cut -f1)"
  
  # Cleanup old backups (keep last 10)
  echo "Cleaning up old backups (keeping last 10)"
  ls -t ${BACKUP_DIR}/forex_backup_*.sql.gz | tail -n +11 | xargs -r rm
  echo "Cleanup completed"
else
  echo "Error: Backup failed"
  exit 1
fi

echo "Backup process completed at $(date)"
exit 0 