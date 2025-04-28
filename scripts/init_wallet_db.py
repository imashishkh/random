#!/usr/bin/env python
"""
Initialize BEP20 Wallet Database Tables

This script initializes the database tables required for the BEP20 wallet integration.
It should be run once during application setup.
"""
import os
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Import database connection
from src.db.connection import get_db_connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def read_sql_file(file_path):
    """Read SQL from file."""
    with open(file_path, 'r') as f:
        return f.read()


def init_wallet_tables(sql_file=None):
    """
    Initialize wallet database tables.
    
    Args:
        sql_file: Optional SQL file path. If not provided, use the default.
    """
    # If no SQL file provided, use the default from src/db
    if sql_file is None:
        # Get the path to wallet_schema.sql
        base_dir = Path(__file__).resolve().parent.parent
        sql_file = base_dir / 'src' / 'db' / 'wallet_schema.sql'
    
    # Read SQL file
    logger.info(f"Reading SQL schema from {sql_file}")
    sql = read_sql_file(sql_file)
    
    # Execute SQL schema
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            logger.info("Creating wallet database tables...")
            cursor.execute(sql)
            conn.commit()
            logger.info("Wallet database tables created successfully")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating wallet tables: {e}")
            raise


def main():
    """Main function to initialize wallet database tables."""
    parser = argparse.ArgumentParser(description='Initialize wallet database tables')
    parser.add_argument('--sql-file', help='Path to SQL schema file')
    args = parser.parse_args()
    
    try:
        init_wallet_tables(args.sql_file)
    except Exception as e:
        logger.error(f"Failed to initialize wallet database: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main()) 