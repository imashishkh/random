#!/bin/bash
# Alertmanager configuration backup script
# This script backs up Alertmanager configurations and silences

set -e

# Configuration
BACKUP_DIR="./backups/alertmanager"
BACKUP_RETENTION_DAYS=30
ALERTMANAGER_CONFIG_DIR="./configs/alertmanager"
DATE_FORMAT=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILENAME="alertmanager_backup_${DATE_FORMAT}.tar.gz"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_DIR}"

echo -e "${YELLOW}Starting Alertmanager configuration backup...${NC}"

# Backup Alertmanager configs
if [ -d "${ALERTMANAGER_CONFIG_DIR}" ]; then
  echo -e "${YELLOW}Backing up Alertmanager configuration files...${NC}"
  
  # Create a tarball of the configuration directory
  tar -czf "${BACKUP_DIR}/${BACKUP_FILENAME}" -C "$(dirname ${ALERTMANAGER_CONFIG_DIR})" "$(basename ${ALERTMANAGER_CONFIG_DIR})"
  
  if [ $? -eq 0 ]; then
    echo -e "${GREEN}Backup created successfully: ${BACKUP_DIR}/${BACKUP_FILENAME}${NC}"
  else
    echo -e "${RED}Failed to create backup.${NC}"
    exit 1
  fi
else
  echo -e "${RED}Alertmanager configuration directory not found: ${ALERTMANAGER_CONFIG_DIR}${NC}"
  exit 1
fi

# Export Alertmanager silences if Alertmanager is running
if curl -s http://localhost:9093/-/healthy > /dev/null; then
  echo -e "${YELLOW}Alertmanager is running. Exporting silences...${NC}"
  
  # Export silences to JSON file
  SILENCES_FILE="${BACKUP_DIR}/silences_${DATE_FORMAT}.json"
  curl -s http://localhost:9093/api/v1/silences -o "${SILENCES_FILE}"
  
  if [ $? -eq 0 ] && [ -s "${SILENCES_FILE}" ]; then
    echo -e "${GREEN}Silences exported successfully: ${SILENCES_FILE}${NC}"
  else
    echo -e "${YELLOW}No silences found or failed to export silences.${NC}"
    [ -f "${SILENCES_FILE}" ] && rm "${SILENCES_FILE}"
  fi
else
  echo -e "${YELLOW}Alertmanager is not running. Skipping silences export.${NC}"
fi

# Clean up old backups
echo -e "${YELLOW}Cleaning up backups older than ${BACKUP_RETENTION_DAYS} days...${NC}"
find "${BACKUP_DIR}" -name "alertmanager_backup_*.tar.gz" -type f -mtime +${BACKUP_RETENTION_DAYS} -delete
find "${BACKUP_DIR}" -name "silences_*.json" -type f -mtime +${BACKUP_RETENTION_DAYS} -delete

# Count remaining backups
BACKUP_COUNT=$(find "${BACKUP_DIR}" -name "alertmanager_backup_*.tar.gz" | wc -l)
echo -e "${GREEN}Backup completed. ${BACKUP_COUNT} backups are currently stored in ${BACKUP_DIR}${NC}"

# Create a symlink to the latest backup
ln -sf "${BACKUP_DIR}/${BACKUP_FILENAME}" "${BACKUP_DIR}/alertmanager_backup_latest.tar.gz"
echo -e "${GREEN}Created symlink to latest backup: ${BACKUP_DIR}/alertmanager_backup_latest.tar.gz${NC}"

echo -e "${GREEN}Alertmanager configuration backup completed successfully.${NC}" 