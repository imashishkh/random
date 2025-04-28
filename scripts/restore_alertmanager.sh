#!/bin/bash
# Alertmanager configuration restore script
# This script restores Alertmanager configurations and silences from backups

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
BACKUP_DIR="./backups/alertmanager"
ALERTMANAGER_CONFIG_DIR="./configs/alertmanager"
ALERTMANAGER_SERVICE="alertmanager"
RESTART_ALERTMANAGER=true

# Function to display usage information
function usage {
  echo "Usage: $0 [OPTIONS] <backup_file>"
  echo ""
  echo "Options:"
  echo "  -n, --no-restart       Don't restart Alertmanager after restore"
  echo "  -s, --silences         Restore silences from the corresponding silences file"
  echo "  -h, --help             Display this help message"
  echo ""
  echo "Examples:"
  echo "  $0 ./backups/alertmanager/alertmanager_backup_20240415_123045.tar.gz"
  echo "  $0 --silences ./backups/alertmanager/alertmanager_backup_latest.tar.gz"
  echo "  $0 --no-restart ./backups/alertmanager/alertmanager_backup_latest.tar.gz"
  exit 1
}

# Process command line arguments
RESTORE_SILENCES=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--no-restart)
      RESTART_ALERTMANAGER=false
      shift
      ;;
    -s|--silences)
      RESTORE_SILENCES=true
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      BACKUP_FILE="$1"
      shift
      ;;
  esac
done

# Check if backup file is provided
if [ -z "${BACKUP_FILE}" ]; then
  echo -e "${RED}Error: No backup file specified.${NC}"
  usage
fi

# Check if backup file exists
if [ ! -f "${BACKUP_FILE}" ]; then
  echo -e "${RED}Error: Backup file does not exist: ${BACKUP_FILE}${NC}"
  exit 1
fi

echo -e "${YELLOW}Starting Alertmanager configuration restore...${NC}"

# Create temporary directory for restore
TEMP_DIR=$(mktemp -d)
trap "rm -rf ${TEMP_DIR}" EXIT

# Extract backup to temporary directory
echo -e "${YELLOW}Extracting backup file...${NC}"
tar -xzf "${BACKUP_FILE}" -C "${TEMP_DIR}"

if [ $? -ne 0 ]; then
  echo -e "${RED}Failed to extract backup file.${NC}"
  exit 1
fi

# Verify extracted content
if [ ! -d "${TEMP_DIR}/configs/alertmanager" ] && [ ! -d "${TEMP_DIR}/alertmanager" ]; then
  echo -e "${RED}Invalid backup file: Alertmanager configuration directory not found in the backup.${NC}"
  exit 1
fi

# Determine source directory from extracted content
SRC_DIR="${TEMP_DIR}/configs/alertmanager"
if [ ! -d "${SRC_DIR}" ]; then
  SRC_DIR="${TEMP_DIR}/alertmanager"
fi

# Create a backup of current configuration before restoring
CURRENT_DATE=$(date +"%Y%m%d_%H%M%S")
CURRENT_BACKUP="${BACKUP_DIR}/pre_restore_backup_${CURRENT_DATE}.tar.gz"

if [ -d "${ALERTMANAGER_CONFIG_DIR}" ]; then
  echo -e "${YELLOW}Creating backup of current configuration...${NC}"
  tar -czf "${CURRENT_BACKUP}" -C "$(dirname ${ALERTMANAGER_CONFIG_DIR})" "$(basename ${ALERTMANAGER_CONFIG_DIR})"
  echo -e "${GREEN}Current configuration backed up to ${CURRENT_BACKUP}${NC}"
fi

# Restore configuration files
echo -e "${YELLOW}Restoring Alertmanager configuration files...${NC}"
mkdir -p "$(dirname ${ALERTMANAGER_CONFIG_DIR})"
rm -rf "${ALERTMANAGER_CONFIG_DIR}"
cp -r "${SRC_DIR}" "$(dirname ${ALERTMANAGER_CONFIG_DIR})/"

if [ $? -eq 0 ]; then
  echo -e "${GREEN}Alertmanager configuration restored successfully.${NC}"
else
  echo -e "${RED}Failed to restore Alertmanager configuration.${NC}"
  exit 1
fi

# Restart Alertmanager if requested
if [ "${RESTART_ALERTMANAGER}" = true ]; then
  echo -e "${YELLOW}Restarting Alertmanager service...${NC}"
  
  # Detect system type and restart appropriately
  if command -v systemctl &> /dev/null; then
    sudo systemctl restart "${ALERTMANAGER_SERVICE}" || true
  elif command -v service &> /dev/null; then
    sudo service "${ALERTMANAGER_SERVICE}" restart || true
  elif [ -f docker-compose.yml ] && command -v docker-compose &> /dev/null; then
    docker-compose restart alertmanager || true
  else
    echo -e "${YELLOW}Could not automatically restart Alertmanager. Please restart it manually.${NC}"
  fi
  
  # Check if Alertmanager is running
  if curl -s http://localhost:9093/-/healthy > /dev/null; then
    echo -e "${GREEN}Alertmanager service restarted successfully.${NC}"
  else
    echo -e "${YELLOW}Alertmanager service may not have restarted properly. Please check it manually.${NC}"
  fi
else
  echo -e "${YELLOW}Alertmanager service restart skipped as requested.${NC}"
  echo -e "${YELLOW}Remember to restart Alertmanager manually to apply the restored configuration.${NC}"
fi

# Restore silences if requested
if [ "${RESTORE_SILENCES}" = true ]; then
  echo -e "${YELLOW}Restoring silences...${NC}"
  
  # Determine the silences file path
  SILENCES_FILE="${BACKUP_FILE/alertmanager_backup_/silences_}"
  SILENCES_FILE="${SILENCES_FILE/.tar.gz/.json}"
  
  if [ ! -f "${SILENCES_FILE}" ]; then
    echo -e "${YELLOW}Silences file not found: ${SILENCES_FILE}${NC}"
    echo -e "${YELLOW}Looking for any silences file with similar timestamp...${NC}"
    
    # Extract timestamp from backup filename
    TIMESTAMP=$(basename "${BACKUP_FILE}" | grep -o '[0-9]\{8\}_[0-9]\{6\}')
    
    if [ -n "${TIMESTAMP}" ]; then
      SILENCES_FILE=$(find "${BACKUP_DIR}" -name "silences_${TIMESTAMP}*.json" -type f | head -n 1)
    fi
  fi
  
  if [ -f "${SILENCES_FILE}" ]; then
    echo -e "${YELLOW}Found silences file: ${SILENCES_FILE}${NC}"
    
    # Check if Alertmanager is running
    if curl -s http://localhost:9093/-/healthy > /dev/null; then
      # Parse silences JSON and restore each silence
      echo -e "${YELLOW}Importing silences...${NC}"
      
      # Get the list of active silences
      ACTIVE_SILENCES=$(curl -s http://localhost:9093/api/v1/silences | jq -r '.data[] | select(.status.state=="active") | .id')
      
      # Import silences from the backup file
      SILENCE_COUNT=0
      while read -r silence; do
        # Remove id field and timestamps for new silence creation
        SILENCE_DATA=$(echo "${silence}" | jq 'del(.id) | del(.createdBy) | del(.startsAt) | del(.endsAt) | del(.updatedAt)')
        
        # Set appropriate start and end times
        CURRENT_TIME=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")
        END_TIME=$(date -u -v+4h +"%Y-%m-%dT%H:%M:%S.000Z")  # 4 hours from now
        
        SILENCE_DATA=$(echo "${SILENCE_DATA}" | jq --arg start "${CURRENT_TIME}" --arg end "${END_TIME}" '.startsAt = $start | .endsAt = $end')
        
        # Post the silence to Alertmanager
        RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" -d "${SILENCE_DATA}" http://localhost:9093/api/v1/silences)
        SILENCE_ID=$(echo "${RESPONSE}" | jq -r '.silenceID')
        
        if [ -n "${SILENCE_ID}" ] && [ "${SILENCE_ID}" != "null" ]; then
          SILENCE_COUNT=$((SILENCE_COUNT + 1))
        fi
      done < <(jq -c '.data[]? // empty' "${SILENCES_FILE}")
      
      echo -e "${GREEN}Restored ${SILENCE_COUNT} silences from backup.${NC}"
    else
      echo -e "${YELLOW}Alertmanager is not running. Cannot restore silences.${NC}"
    fi
  else
    echo -e "${YELLOW}No silences file found for this backup. Skipping silences restore.${NC}"
  fi
fi

echo -e "${GREEN}Alertmanager configuration restore completed successfully.${NC}"
echo -e "${GREEN}Restored from: ${BACKUP_FILE}${NC}" 