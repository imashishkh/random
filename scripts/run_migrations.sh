#!/bin/bash
# Database migration script for the Forex Trading AI System

# Load environment variables
if [ -f .env ]; then
  export $(cat .env | grep -v '#' | xargs)
else
  echo "Error: .env file not found. Please create a .env file with database credentials."
  exit 1
fi

# Default command is migrate
COMMAND=${1:-"migrate"}

# Valid commands
VALID_COMMANDS=("init" "migrate" "create")

# Check if command is valid
if [[ ! " ${VALID_COMMANDS[@]} " =~ " ${COMMAND} " ]]; then
  echo "Error: Invalid command '${COMMAND}'"
  echo "Valid commands: init, migrate, create"
  exit 1
fi

# If command is create, ensure a name is provided
if [ "${COMMAND}" = "create" ] && [ $# -lt 2 ]; then
  echo "Error: Migration name is required for 'create' command"
  echo "Usage: $0 create <migration_name>"
  exit 1
fi

# Arguments for the migration script
ARGS=""
if [ "${COMMAND}" = "create" ]; then
  ARGS="$2"
fi

# Run the migration script
echo "Running database migration command: ${COMMAND}"
python scripts/db_migrations.py ${COMMAND} ${ARGS}

# Check if migration was successful
if [ $? -eq 0 ]; then
  echo "Database migration '${COMMAND}' completed successfully"
else
  echo "Error: Database migration '${COMMAND}' failed"
  exit 1
fi

exit 0 