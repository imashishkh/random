#!/bin/bash
# 
# Wallet Audit Scheduler
# This script sets up cron jobs to run regular wallet balance audits and reconciliation
#

set -e

# Define paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REPORTS_DIR="$PROJECT_ROOT/reports"
LOGS_DIR="$PROJECT_ROOT/logs"

# Ensure directories exist
mkdir -p "$REPORTS_DIR"
mkdir -p "$LOGS_DIR"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Display header
echo -e "${GREEN}==========================${NC}"
echo -e "${GREEN}Wallet Audit Scheduler${NC}"
echo -e "${GREEN}==========================${NC}"

# Function to add a cron job
add_cron_job() {
    local schedule="$1"
    local command="$2"
    local job_name="$3"
    
    # Check if job already exists
    if crontab -l 2>/dev/null | grep -q "$command"; then
        echo -e "${YELLOW}Cron job for $job_name already exists. Skipping...${NC}"
    else
        (crontab -l 2>/dev/null; echo "$schedule $command # $job_name") | crontab -
        echo -e "${GREEN}Added cron job for $job_name${NC}"
    fi
}

# Function to remove a cron job
remove_cron_job() {
    local job_name="$1"
    
    if crontab -l 2>/dev/null | grep -q "$job_name"; then
        crontab -l 2>/dev/null | grep -v "$job_name" | crontab -
        echo -e "${GREEN}Removed cron job for $job_name${NC}"
    else
        echo -e "${YELLOW}No cron job found for $job_name${NC}"
    fi
}

# Function to display help
show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  --setup         Setup all scheduled audit jobs"
    echo "  --remove        Remove all scheduled audit jobs"
    echo "  --list          List current scheduled jobs"
    echo "  --help          Display this help message"
    echo
}

# Function to list current cron jobs
list_jobs() {
    echo -e "${GREEN}Current scheduled wallet audit jobs:${NC}"
    if crontab -l 2>/dev/null | grep -q "wallet"; then
        crontab -l | grep "wallet"
    else
        echo -e "${YELLOW}No wallet audit jobs scheduled${NC}"
    fi
}

# Setup all cron jobs
setup_jobs() {
    echo -e "${GREEN}Setting up wallet audit cron jobs...${NC}"
    
    # Daily balance report - every day at 1:00 AM
    add_cron_job "0 1 * * *" "cd $PROJECT_ROOT && python $SCRIPT_DIR/generate_wallet_report.py --report-type balance --format json >> $LOGS_DIR/daily_balance_report.log 2>&1" "Daily wallet balance report"
    
    # Weekly transaction report - every Sunday at 2:00 AM
    add_cron_job "0 2 * * 0" "cd $PROJECT_ROOT && python $SCRIPT_DIR/generate_wallet_report.py --report-type transactions --days 7 --format json >> $LOGS_DIR/weekly_transaction_report.log 2>&1" "Weekly wallet transaction report"
    
    # Monthly full audit - 1st of every month at 3:00 AM
    add_cron_job "0 3 1 * *" "cd $PROJECT_ROOT && python $SCRIPT_DIR/generate_wallet_report.py --report-type both --days 30 --format json >> $LOGS_DIR/monthly_full_audit.log 2>&1" "Monthly full wallet audit"
    
    # Check stale withdrawal approvals - every day at 9:00 AM
    add_cron_job "0 9 * * *" "cd $PROJECT_ROOT && python $SCRIPT_DIR/check_withdrawal_approvals.py --days 3 --notify >> $LOGS_DIR/stale_withdrawal_check.log 2>&1" "Check stale withdrawal approvals"
    
    echo -e "${GREEN}All wallet audit jobs have been scheduled successfully!${NC}"
}

# Remove all cron jobs
remove_jobs() {
    echo -e "${YELLOW}Removing wallet audit cron jobs...${NC}"
    
    remove_cron_job "Daily wallet balance report"
    remove_cron_job "Weekly wallet transaction report"
    remove_cron_job "Monthly full wallet audit"
    remove_cron_job "Check stale withdrawal approvals"
    
    echo -e "${GREEN}All wallet audit jobs have been removed!${NC}"
}

# Process command line arguments
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

case "$1" in
    --setup)
        setup_jobs
        ;;
    --remove)
        remove_jobs
        ;;
    --list)
        list_jobs
        ;;
    --help)
        show_help
        ;;
    *)
        echo -e "${RED}Invalid option: $1${NC}"
        show_help
        exit 1
        ;;
esac

echo -e "${GREEN}Done!${NC}"
exit 0 