#!/bin/bash
# Validation script for environment configurations
# This script checks if all required environment variables are set correctly
# and validates the Docker Compose configuration for different environments

set -e  # Exit on error

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Environment file to validate (default to .env)
ENV_FILE=${1:-".env"}

echo -e "${YELLOW}=======================================${NC}"
echo -e "${YELLOW}= Environment Configuration Validator =${NC}"
echo -e "${YELLOW}=======================================${NC}"
echo -e "Testing environment configuration in ${YELLOW}${ENV_FILE}${NC}\n"

# Check if environment file exists
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: Environment file $ENV_FILE does not exist${NC}"
    echo -e "Please create it from one of the templates:"
    echo -e "  cp .env.development .env"
    echo -e "  cp .env.staging .env"
    echo -e "  cp .env.production .env"
    exit 1
fi

# Function to check if a variable is defined in the environment file
check_var() {
    VAR_NAME=$1
    REQUIRED=$2
    
    if grep -q "^$VAR_NAME=" "$ENV_FILE"; then
        VAR_VALUE=$(grep "^$VAR_NAME=" "$ENV_FILE" | cut -d '=' -f2-)
        if [ -z "$VAR_VALUE" ]; then
            if [ "$REQUIRED" = "true" ]; then
                echo -e "  ${RED}✗ $VAR_NAME is empty but required${NC}"
                return 1
            else
                echo -e "  ${YELLOW}⚠ $VAR_NAME is empty${NC}"
                return 0
            fi
        else
            echo -e "  ${GREEN}✓ $VAR_NAME is set${NC}"
            return 0
        fi
    else
        if [ "$REQUIRED" = "true" ]; then
            echo -e "  ${RED}✗ $VAR_NAME is missing but required${NC}"
            return 1
        else
            echo -e "  ${YELLOW}⚠ $VAR_NAME is missing (optional)${NC}"
            return 0
        fi
    fi
}

# Validate Docker Compose files
echo -e "\n${YELLOW}Validating Docker Compose Files:${NC}"
if docker-compose config > /dev/null 2>&1; then
    echo -e "${GREEN}✓ docker-compose.yml is valid${NC}"
else
    echo -e "${RED}✗ docker-compose.yml has errors${NC}"
    docker-compose config
    exit 1
fi

if [ -f "docker-compose.override.yml" ]; then
    if docker-compose -f docker-compose.yml -f docker-compose.override.yml config > /dev/null 2>&1; then
        echo -e "${GREEN}✓ docker-compose.override.yml is valid${NC}"
    else
        echo -e "${RED}✗ docker-compose.override.yml has errors${NC}"
        exit 1
    fi
fi

if [ -f "docker-compose.prod.yml" ]; then
    if docker-compose -f docker-compose.yml -f docker-compose.prod.yml config > /dev/null 2>&1; then
        echo -e "${GREEN}✓ docker-compose.prod.yml is valid${NC}"
    else
        echo -e "${RED}✗ docker-compose.prod.yml has errors${NC}"
        exit 1
    fi
fi

# Check if using production configuration
if [[ "$ENV_FILE" == ".env.production" || "$ENV_FILE" == ".env" && -f ".env.production" && "$(diff .env .env.production 2>/dev/null)" == "" ]]; then
    PROD_MODE=true
    echo -e "\n${YELLOW}Production environment detected. Checking Docker secrets...${NC}"
    
    # Check for Docker secrets
    mkdir -p docker/secrets
    
    SECRET_FILES=("postgres_password.txt" "redis_password.txt" "airflow_fernet_key.txt" 
                  "airflow_password.txt" "grafana_admin_password.txt" "grafana_db_password.txt")
    
    for SECRET_FILE in "${SECRET_FILES[@]}"; do
        if [ -f "docker/secrets/$SECRET_FILE" ]; then
            if [ -s "docker/secrets/$SECRET_FILE" ]; then
                echo -e "  ${GREEN}✓ docker/secrets/$SECRET_FILE exists and is not empty${NC}"
            else
                echo -e "  ${RED}✗ docker/secrets/$SECRET_FILE exists but is empty${NC}"
            fi
        else
            echo -e "  ${RED}✗ docker/secrets/$SECRET_FILE is missing${NC}"
            # Create an example file
            echo "change_this_to_strong_production_password" > "docker/secrets/$SECRET_FILE"
            echo -e "    ${YELLOW}Created example file. Replace with a secure value before deployment.${NC}"
        fi
    done
fi

# Validate PostgreSQL configuration
echo -e "\n${YELLOW}Checking PostgreSQL Configuration:${NC}"
check_var "POSTGRES_USER" true
check_var "POSTGRES_PASSWORD" true
check_var "POSTGRES_DB" true

# Validate Redis configuration
echo -e "\n${YELLOW}Checking Redis Configuration:${NC}"
check_var "REDIS_PASSWORD" true
check_var "REDIS_MAX_MEMORY" false

# Validate Airflow configuration
echo -e "\n${YELLOW}Checking Airflow Configuration:${NC}"
check_var "AIRFLOW_FERNET_KEY" true
check_var "AIRFLOW_USER" true
check_var "AIRFLOW_PASSWORD" true
check_var "AIRFLOW_DB" true
check_var "AIRFLOW_PARALLELISM" false
check_var "AIRFLOW_DAG_CONCURRENCY" false
check_var "AIRFLOW_WORKER_CONCURRENCY" false

# Validate Grafana configuration
echo -e "\n${YELLOW}Checking Grafana Configuration:${NC}"
check_var "GRAFANA_ADMIN_USER" true
check_var "GRAFANA_ADMIN_PASSWORD" true
check_var "GRAFANA_DB_PASSWORD" true

# Validate Application configuration
echo -e "\n${YELLOW}Checking Application Configuration:${NC}"
check_var "DATABASE_URL" true
check_var "REDIS_URL" true
check_var "LOG_LEVEL" false
check_var "DEBUG" false
check_var "ENABLE_SWAGGER" false

# Validate Timezone configuration
echo -e "\n${YELLOW}Checking Timezone Configuration:${NC}"
check_var "TZ" false

# Validate Resource Limits
echo -e "\n${YELLOW}Checking Resource Limits:${NC}"
check_var "POSTGRES_CPU_LIMIT" false
check_var "POSTGRES_MEMORY_LIMIT" false
check_var "REDIS_CPU_LIMIT" false
check_var "REDIS_MEMORY_LIMIT" false
check_var "APP_CPU_LIMIT" false
check_var "APP_MEMORY_LIMIT" false

# Final summary
echo -e "\n${YELLOW}=======================================${NC}"
echo -e "${GREEN}✓ Environment configuration validation complete${NC}"
echo -e "${YELLOW}=======================================${NC}"

if [ "$PROD_MODE" = true ]; then
    echo -e "\n${YELLOW}PRODUCTION DEPLOYMENT CHECKLIST:${NC}"
    echo -e "1. Ensure all Docker secrets contain secure values"
    echo -e "2. Verify network security settings are appropriate for production"
    echo -e "3. Enable backup procedures for all persistent data"
    echo -e "4. Set up monitoring and alerting for all services"
    echo -e "5. Deploy using: docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
else
    echo -e "\n${YELLOW}DEPLOYMENT INSTRUCTIONS:${NC}"
    echo -e "Deploy using: docker-compose up -d"
fi

echo -e "\n${GREEN}Done!${NC}" 