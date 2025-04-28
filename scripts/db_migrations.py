#!/usr/bin/env python3
"""
Database migration script for the Forex Trading AI System.
This script manages database schema changes and version upgrades.
"""
import os
import sys
import argparse
import logging
import datetime
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("db_migrations")

# Load environment variables
load_dotenv()

# Database connection parameters from environment variables
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "forex")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")


def get_connection(db_name=None):
    """Create a database connection."""
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=db_name or DB_NAME
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


def create_database_if_not_exists():
    """Create the database if it doesn't exist."""
    try:
        # Connect to default database to check if our target database exists
        with get_connection(db_name="postgres") as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT 1 FROM pg_database WHERE datname='{DB_NAME}'")
            if cursor.fetchone() is None:
                logger.info(f"Creating database {DB_NAME}")
                cursor.execute(f"CREATE DATABASE {DB_NAME}")
                logger.info(f"Database {DB_NAME} created successfully")
            else:
                logger.info(f"Database {DB_NAME} already exists")
    except Exception as e:
        logger.error(f"Error creating database: {e}")
        sys.exit(1)


def create_migrations_table():
    """Create the migrations tracking table if it doesn't exist."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS migrations (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("Migrations table created or already exists")
    except Exception as e:
        logger.error(f"Error creating migrations table: {e}")
        sys.exit(1)


def get_applied_migrations():
    """Get the list of applied migrations."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM migrations ORDER BY id")
            return {row[0] for row in cursor.fetchall()}
    except Exception as e:
        logger.error(f"Error getting applied migrations: {e}")
        return set()


def apply_migration(migration_file, dry_run=False):
    """Apply a single migration file."""
    try:
        with open(migration_file, 'r') as f:
            sql = f.read()
        
        migration_name = os.path.basename(migration_file)
        
        if dry_run:
            logger.info(f"Would apply migration: {migration_name}")
            return True
        
        with get_connection() as conn:
            cursor = conn.cursor()
            logger.info(f"Applying migration: {migration_name}")
            cursor.execute(sql)
            
            # Record the migration
            cursor.execute(
                "INSERT INTO migrations (name) VALUES (%s)",
                (migration_name,)
            )
            logger.info(f"Migration {migration_name} applied successfully")
        return True
    except Exception as e:
        logger.error(f"Error applying migration {migration_file}: {e}")
        return False


def create_new_migration(name):
    """Create a new migration file."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{timestamp}_{name}.sql"
    migrations_dir = os.path.join(os.path.dirname(__file__), "db_migrations")
    
    os.makedirs(migrations_dir, exist_ok=True)
    
    filepath = os.path.join(migrations_dir, filename)
    
    with open(filepath, 'w') as f:
        f.write(f"-- Migration: {name}\n")
        f.write(f"-- Created at: {datetime.datetime.now().isoformat()}\n\n")
        f.write("-- Write your SQL statements here\n\n")
    
    logger.info(f"Created new migration file: {filepath}")
    return filepath


def init_db():
    """Initialize the database with the initial schema."""
    try:
        init_dir = os.path.join(os.path.dirname(__file__), "db_init")
        
        # Get all SQL files in the init directory
        sql_files = sorted([
            os.path.join(init_dir, f) for f in os.listdir(init_dir) 
            if f.endswith('.sql')
        ])
        
        for sql_file in sql_files:
            logger.info(f"Executing initialization script: {os.path.basename(sql_file)}")
            with open(sql_file, 'r') as f:
                sql = f.read()
            
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql)
                logger.info(f"Initialization script {os.path.basename(sql_file)} executed successfully")
        
        logger.info("Database initialization completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        return False


def run_migrations(dry_run=False):
    """Run all pending migrations."""
    migrations_dir = os.path.join(os.path.dirname(__file__), "db_migrations")
    os.makedirs(migrations_dir, exist_ok=True)
    
    # Get all SQL files in the migrations directory
    sql_files = sorted([
        os.path.join(migrations_dir, f) for f in os.listdir(migrations_dir) 
        if f.endswith('.sql')
    ])
    
    # Get already applied migrations
    applied_migrations = get_applied_migrations()
    
    # Apply pending migrations
    pending_migrations = [
        f for f in sql_files 
        if os.path.basename(f) not in applied_migrations
    ]
    
    if not pending_migrations:
        logger.info("No pending migrations to apply")
        return True
    
    logger.info(f"Found {len(pending_migrations)} pending migrations")
    
    success = True
    for migration in pending_migrations:
        if not apply_migration(migration, dry_run):
            success = False
            break
    
    if success:
        logger.info("All pending migrations applied successfully")
    else:
        logger.error("Failed to apply all migrations")
    
    return success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Database migration tool")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # init command
    init_parser = subparsers.add_parser("init", help="Initialize the database with the base schema")
    
    # migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Apply pending migrations")
    migrate_parser.add_argument(
        "--dry-run", action="store_true", 
        help="Show what migrations would be run without making changes"
    )
    
    # create command
    create_parser = subparsers.add_parser("create", help="Create a new migration file")
    create_parser.add_argument("name", help="Name of the migration (will be prefixed with timestamp)")
    
    args = parser.parse_args()
    
    # Ensure the database exists
    create_database_if_not_exists()
    
    if args.command == "init":
        create_migrations_table()
        init_db()
    elif args.command == "migrate":
        create_migrations_table()
        run_migrations(args.dry_run)
    elif args.command == "create":
        create_new_migration(args.name)
    else:
        parser.print_help()


if __name__ == "__main__":
    main() 