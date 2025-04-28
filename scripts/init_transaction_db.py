#!/usr/bin/env python3
"""
Script to initialize transaction monitoring database tables.
This script should be run during system setup to create the necessary 
database tables for monitoring and processing blockchain transactions.
"""

import os
import sys
import logging
import argparse
import psycopg2
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def read_sql_from_file(file_path):
    """Read SQL commands from a file."""
    with open(file_path, 'r') as file:
        return file.read()

def initialize_transaction_tables(conn, sql_file=None):
    """Initialize the transaction database tables using the provided SQL schema."""
    try:
        # Default SQL file path
        if sql_file is None:
            sql_file = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'create_transaction_tables.sql'
            )
        
        # Read SQL commands
        sql_commands = read_sql_from_file(sql_file)
        
        # Execute SQL commands
        cursor = conn.cursor()
        cursor.execute(sql_commands)
        conn.commit()
        cursor.close()
        
        logger.info(f"Transaction database tables initialized successfully using {sql_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize transaction tables: {str(e)}")
        conn.rollback()
        return False

def get_db_connection():
    """Create a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            dbname=os.environ.get('DB_NAME'),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD'),
            host=os.environ.get('DB_HOST', 'localhost'),
            port=os.environ.get('DB_PORT', '5432')
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        return None

def main():
    """Main function to run the script."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Initialize transaction database tables')
    parser.add_argument('--sql-file', type=str, help='Path to SQL schema file')
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    # Get database connection
    conn = get_db_connection()
    if conn is None:
        logger.error("Failed to connect to database")
        sys.exit(1)
    
    try:
        # Initialize tables
        success = initialize_transaction_tables(conn, args.sql_file)
        if success:
            logger.info("Transaction tables created successfully")
        else:
            logger.error("Failed to create transaction tables")
            sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main() 