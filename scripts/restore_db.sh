#!/bin/bash
# Database restore script for the Forex Trading AI System

# Check if a backup file is provided
if [ $# -lt 1 ]; then
  echo "Usage: $0 <backup_file>"
  echo "Example: $0 backups/db/forex_backup_20230101_120000.sql.gz"
  exit 1
fi

BACKUP_FILE=$1

# Check if the backup file exists
if [ ! -f "${BACKUP_FILE}" ]; then
  echo "Error: Backup file '${BACKUP_FILE}' not found."
  exit 1
fi

# Load environment variables
if [ -f .env ]; then
  export $(cat .env | grep -v '#' | xargs)
else
  echo "Error: .env file not found. Please create a .env file with database credentials."
  exit 1
fi

# Default values if not in env
DB_HOST=${DB_HOST:-"localhost"}
DB_PORT=${DB_PORT:-"5432"}
DB_NAME=${DB_NAME:-"forex"}
DB_USER=${DB_USER:-"postgres"}
DB_PASSWORD=${DB_PASSWORD:-"postgres"}

# Confirmation
echo "WARNING: This will overwrite the current database '${DB_NAME}' on ${DB_HOST}:${DB_PORT}"
echo "Backup file to restore: ${BACKUP_FILE}"
read -p "Are you sure you want to proceed? (y/n): " CONFIRM

if [ "${CONFIRM}" != "y" ] && [ "${CONFIRM}" != "Y" ]; then
  echo "Restore cancelled."
  exit 0
fi

# Additional confirmation for production
if [ "${ENVIRONMENT}" = "production" ]; then
  read -p "You are restoring to a PRODUCTION database. Type 'CONFIRM' to proceed: " PROD_CONFIRM
  if [ "${PROD_CONFIRM}" != "CONFIRM" ]; then
    echo "Restore to production cancelled."
    exit 0
  fi
fi

echo "Starting restore of database ${DB_NAME} on ${DB_HOST}:${DB_PORT} from ${BACKUP_FILE}"

# Drop and recreate the database
echo "Dropping existing database..."
PGPASSWORD=${DB_PASSWORD} psql \
  -h ${DB_HOST} \
  -p ${DB_PORT} \
  -U ${DB_USER} \
  -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DB_NAME}';"

PGPASSWORD=${DB_PASSWORD} psql \
  -h ${DB_HOST} \
  -p ${DB_PORT} \
  -U ${DB_USER} \
  -d postgres \
  -c "DROP DATABASE IF EXISTS ${DB_NAME};"

echo "Creating new database..."
PGPASSWORD=${DB_PASSWORD} psql \
  -h ${DB_HOST} \
  -p ${DB_PORT} \
  -U ${DB_USER} \
  -d postgres \
  -c "CREATE DATABASE ${DB_NAME};"

# Restore the database
echo "Restoring backup..."
gunzip -c ${BACKUP_FILE} | PGPASSWORD=${DB_PASSWORD} psql \
  -h ${DB_HOST} \
  -p ${DB_PORT} \
  -U ${DB_USER} \
  -d ${DB_NAME}

# Check if restore was successful
if [ $? -eq 0 ]; then
  echo "Restore completed successfully"
else
  echo "Error: Restore failed"
  exit 1
fi

echo "Restore process completed at $(date)"
exit 0 