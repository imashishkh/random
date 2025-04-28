#!/usr/bin/env python3
"""
Reconciliation Database Initialization Script

This script initializes the database tables required for the reconciliation system,
including accounting entries, reconciliation reports, and fund transfers.

Usage:
    python init_reconciliation_db.py [--sql_file SQL_FILE_PATH]

Options:
    --sql_file  Path to SQL file containing schema (default: src/db/reconciliation_schema.sql)
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add the project root to the Python path
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.append(str(project_root))

# Import the database connection function
from src.db.connection import get_db_connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger('reconciliation-db-init')

def read_sql_from_file(sql_file_path):
    """
    Read SQL commands from a file.
    
    Args:
        sql_file_path (str): Path to the SQL file
        
    Returns:
        str: SQL commands as a string
    """
    try:
        with open(sql_file_path, 'r') as file:
            return file.read()
    except Exception as e:
        logger.error(f"Failed to read SQL file {sql_file_path}: {e}")
        raise

def initialize_reconciliation_tables(sql_file_path):
    """
    Initialize reconciliation system database tables.
    
    Args:
        sql_file_path (str): Path to the SQL file containing the schema
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Load SQL from file
        sql = read_sql_from_file(sql_file_path)
        
        # Connect to the database
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Execute the SQL
        logger.info(f"Executing SQL from {sql_file_path}")
        cursor.execute(sql)
        connection.commit()
        
        # Check if tables were created
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('accounting_entries', 'reconciliation_reports', 'fund_transfers')")
        tables = cursor.fetchall()
        
        if len(tables) == 3:
            logger.info("Reconciliation tables successfully created!")
            for table in tables:
                logger.info(f"  - {table[0]}")
        else:
            created_tables = [table[0] for table in tables]
            missing_tables = [table for table in ['accounting_entries', 'reconciliation_reports', 'fund_transfers'] if table not in created_tables]
            logger.warning(f"Some tables may not have been created: {missing_tables}")
        
        cursor.close()
        connection.close()
        return True
    except Exception as e:
        logger.error(f"Failed to initialize reconciliation tables: {e}")
        return False

def main():
    """Main function to initialize the reconciliation database"""
    # Load environment variables
    load_dotenv()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Initialize reconciliation database tables')
    parser.add_argument('--sql_file', type=str, 
                        default=os.path.join(project_root, 'src', 'db', 'reconciliation_schema.sql'),
                        help='Path to SQL file containing schema')
    args = parser.parse_args()
    
    # Check if SQL file exists
    if not os.path.exists(args.sql_file):
        logger.error(f"SQL file not found: {args.sql_file}")
        return 1
    
    # Initialize the database tables
    if initialize_reconciliation_tables(args.sql_file):
        logger.info("Database initialization completed successfully.")
        return 0
    else:
        logger.error("Database initialization failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 