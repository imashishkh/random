#!/usr/bin/env python3
"""
Database initialization script for Forex Trading Platform v4.

This script:
1. Ensures the database exists
2. Sets up the Alembic migration environment if it doesn't exist
3. Runs all pending migrations to bring the schema up to date
"""

import os
import sys
import logging
import subprocess
import argparse
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('init_db')

# Load environment variables
load_dotenv()

# Database connection parameters from environment variables
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "forex")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")


def ensure_database_exists():
    """
    Ensure the database exists, creating it if necessary.
    """
    try:
        # Connect to the default 'postgres' database to create our database if needed
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname="postgres"
        )
        conn.autocommit = True
        
        with conn.cursor() as cursor:
            # Check if our database exists
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
            exists = cursor.fetchone()
            
            if not exists:
                logger.info(f"Creating database '{DB_NAME}'...")
                # Create the database (PostgreSQL requires us to be outside of a transaction)
                cursor.execute(f"CREATE DATABASE {DB_NAME}")
                logger.info(f"Database '{DB_NAME}' created successfully")
            else:
                logger.info(f"Database '{DB_NAME}' already exists")
                
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error ensuring database exists: {e}")
        return False


def setup_alembic():
    """
    Set up the Alembic migration environment if it doesn't exist.
    """
    migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
    versions_dir = os.path.join(migrations_dir, 'versions')
    
    # Check if migrations directory exists
    if not os.path.exists(migrations_dir):
        logger.info("Creating migrations directory...")
        os.makedirs(migrations_dir, exist_ok=True)
    
    # Check if versions directory exists
    if not os.path.exists(versions_dir):
        logger.info("Creating versions directory...")
        os.makedirs(versions_dir, exist_ok=True)
    
    # Check if alembic.ini exists
    if not os.path.exists(os.path.join(migrations_dir, 'alembic.ini')):
        logger.warning("alembic.ini not found. Please run 'alembic init migrations' manually.")
    
    return True


def run_migrations():
    """
    Run Alembic migrations to bring the database schema up to date.
    """
    try:
        migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
        
        # Change to the migrations directory
        os.chdir(migrations_dir)
        
        # Run the migrations
        logger.info("Running database migrations...")
        result = subprocess.run(['alembic', 'upgrade', 'head'], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("Migrations completed successfully")
            if result.stdout:
                logger.info(f"Migration output: {result.stdout}")
            return True
        else:
            logger.error(f"Migration failed: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        return False


def run_manual_initialization():
    """
    Run manual initialization using the SQL schema file directly.
    This is a fallback if Alembic migration fails.
    """
    try:
        from src.db.trade_analytics import initialize_tables
        
        logger.info("Running manual schema initialization...")
        result = initialize_tables()
        
        if result:
            logger.info("Manual schema initialization completed successfully")
        else:
            logger.error("Manual schema initialization failed")
        
        return result
    except Exception as e:
        logger.error(f"Error during manual initialization: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Initialize the Forex Trading Platform database')
    parser.add_argument('--manual', action='store_true', help='Skip Alembic and use manual initialization')
    args = parser.parse_args()
    
    logger.info("Starting database initialization")
    
    # Ensure the database exists
    if not ensure_database_exists():
        logger.error("Failed to ensure database exists, exiting")
        return False
    
    if args.manual:
        # Skip Alembic and run manual initialization
        logger.info("Using manual initialization (skipping Alembic)")
        return run_manual_initialization()
    else:
        # Set up Alembic if needed
        if not setup_alembic():
            logger.error("Failed to set up Alembic, falling back to manual initialization")
            return run_manual_initialization()
        
        # Run migrations
        if not run_migrations():
            logger.warning("Alembic migrations failed, falling back to manual initialization")
            return run_manual_initialization()
    
    logger.info("Database initialization completed successfully")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 