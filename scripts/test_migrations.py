#!/usr/bin/env python3
"""
Migration Testing Script

This script provides a controlled environment for testing database migrations.
It creates a test database, applies migrations, verifies that indexes are created
correctly, tests rollback procedures, and validates the database state after each step.

Usage:
    python test_migrations.py --create-test-db
    python test_migrations.py --verify-migration [migration_id]
    python test_migrations.py --test-rollback [migration_id]
    python test_migrations.py --run-all-tests
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_migrations")

# Load environment variables
load_dotenv()

# Database connection parameters
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "forex")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
TEST_DB_NAME = f"{DB_NAME}_test"

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "src" / "db" / "migrations"


def get_connection(db_name: Optional[str] = None, autocommit: bool = True) -> psycopg2.extensions.connection:
    """Create a database connection."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname=db_name or "postgres"  # Connect to default postgres DB if not specified
        )
        if autocommit:
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        raise


def create_test_database() -> bool:
    """
    Create a test database for migration testing.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Connect to default postgres database to create/drop test DB
        conn = get_connection()
        cursor = conn.cursor()
        
        # Check if test database exists
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{TEST_DB_NAME}'")
        exists = cursor.fetchone()
        
        if exists:
            # If it exists, drop it first
            logger.info(f"Test database '{TEST_DB_NAME}' exists, dropping it...")
            cursor.execute(f"DROP DATABASE {TEST_DB_NAME}")
        
        # Create test database
        logger.info(f"Creating test database '{TEST_DB_NAME}'...")
        cursor.execute(f"CREATE DATABASE {TEST_DB_NAME}")
        
        # Close connection to postgres
        conn.close()
        
        # Set up alembic.ini for test database
        update_alembic_config()
        
        logger.info(f"Test database '{TEST_DB_NAME}' created successfully")
        return True
    except Exception as e:
        logger.error(f"Error creating test database: {e}")
        return False


def update_alembic_config() -> bool:
    """
    Update alembic.ini to point to the test database.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        alembic_ini = MIGRATIONS_DIR / "alembic.ini"
        
        # Read alembic.ini
        with open(alembic_ini, 'r') as f:
            config_lines = f.readlines()
        
        # Update sqlalchemy.url to use test database
        test_db_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{TEST_DB_NAME}"
        for i, line in enumerate(config_lines):
            if line.startswith("sqlalchemy.url = "):
                config_lines[i] = f"sqlalchemy.url = {test_db_url}\n"
                break
        
        # Write updated config
        with open(alembic_ini, 'w') as f:
            f.writelines(config_lines)
        
        logger.info(f"Updated alembic.ini to use test database '{TEST_DB_NAME}'")
        return True
    except Exception as e:
        logger.error(f"Error updating alembic.ini: {e}")
        return False


def restore_alembic_config() -> bool:
    """
    Restore alembic.ini to point to the original database.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        alembic_ini = MIGRATIONS_DIR / "alembic.ini"
        
        # Read alembic.ini
        with open(alembic_ini, 'r') as f:
            config_lines = f.readlines()
        
        # Update sqlalchemy.url to use original database
        db_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        for i, line in enumerate(config_lines):
            if line.startswith("sqlalchemy.url = "):
                config_lines[i] = f"sqlalchemy.url = {db_url}\n"
                break
        
        # Write updated config
        with open(alembic_ini, 'w') as f:
            f.writelines(config_lines)
        
        logger.info(f"Restored alembic.ini to use original database '{DB_NAME}'")
        return True
    except Exception as e:
        logger.error(f"Error restoring alembic.ini: {e}")
        return False


def get_indexes(db_name: str) -> Dict[str, List[str]]:
    """
    Get all indexes for all tables in the database.
    
    Args:
        db_name: Database name
        
    Returns:
        Dictionary mapping table names to lists of index names
    """
    indexes = {}
    try:
        conn = get_connection(db_name)
        cursor = conn.cursor()
        
        # Query to get all indexes
        cursor.execute("""
            SELECT
                tablename,
                indexname,
                indexdef
            FROM
                pg_indexes
            WHERE
                schemaname = 'public'
            ORDER BY
                tablename, indexname
        """)
        
        for tablename, indexname, indexdef in cursor.fetchall():
            if tablename not in indexes:
                indexes[tablename] = []
            indexes[tablename].append({
                "name": indexname, 
                "definition": indexdef
            })
        
        conn.close()
        return indexes
    except Exception as e:
        logger.error(f"Error getting indexes: {e}")
        return {}


def run_alembic_command(command: str) -> Tuple[bool, str]:
    """
    Run an Alembic command.
    
    Args:
        command: Alembic command to run (e.g., 'upgrade head', 'downgrade -1')
        
    Returns:
        Tuple of (success, output)
    """
    try:
        # Change directory to migrations directory
        os.chdir(MIGRATIONS_DIR)
        
        # Run alembic command
        logger.info(f"Running alembic {command}...")
        process = subprocess.run(
            f"alembic {command}",
            shell=True,
            capture_output=True,
            text=True
        )
        
        if process.returncode == 0:
            logger.info(f"Alembic command succeeded: {command}")
            return True, process.stdout
        else:
            logger.error(f"Alembic command failed: {command}")
            logger.error(f"Error: {process.stderr}")
            return False, process.stderr
    except Exception as e:
        logger.error(f"Error running alembic command: {e}")
        return False, str(e)


def verify_migration(migration_id: str) -> bool:
    """
    Verify that a migration has been applied correctly.
    
    Args:
        migration_id: Migration ID to verify (e.g., '002')
        
    Returns:
        bool: True if verification passes, False otherwise
    """
    # First, get a mapping of expected indexes from the migration
    expected_indexes = get_expected_indexes(migration_id)
    if not expected_indexes:
        logger.error(f"Could not determine expected indexes for migration {migration_id}")
        return False
    
    # Get actual indexes from database
    actual_indexes = get_indexes(TEST_DB_NAME)
    if not actual_indexes:
        logger.error("Could not retrieve actual indexes from database")
        return False
    
    # Verify each expected index exists
    all_verified = True
    for table, indexes in expected_indexes.items():
        if table not in actual_indexes:
            logger.error(f"Table {table} not found in database")
            all_verified = False
            continue
        
        for expected_index in indexes:
            found = False
            for actual_index in actual_indexes[table]:
                if expected_index.lower() in actual_index["name"].lower():
                    logger.info(f"Verified index {expected_index} on table {table}")
                    found = True
                    break
            
            if not found:
                logger.error(f"Index {expected_index} not found on table {table}")
                all_verified = False
    
    return all_verified


def get_expected_indexes(migration_id: str) -> Dict[str, List[str]]:
    """
    Get the expected indexes for a migration.
    
    Args:
        migration_id: Migration ID (e.g., '002')
        
    Returns:
        Dictionary mapping table names to lists of expected index names
    """
    # Hardcoded expected indexes for known migrations
    if migration_id == "002":
        return {
            "trade_fills": [
                "idx_trade_fills_symbol_timestamp",
                "idx_trade_fills_agent_id"
            ],
            "positions": [
                "idx_positions_agent_id_status",
                "idx_positions_symbol_status"
            ],
            "risk_alerts": [
                "idx_risk_alerts_agent_id_resolved"
            ],
            "agent_states": [
                "idx_agent_states_agent_id"
            ]
        }
    
    # For other migrations, try to parse the migration file
    try:
        migration_file = list(MIGRATIONS_DIR.glob(f"versions/*_{migration_id}_*.py"))
        if not migration_file:
            migration_file = list(MIGRATIONS_DIR.glob(f"versions/{migration_id}_*.py"))
        
        if not migration_file:
            logger.error(f"Could not find migration file for {migration_id}")
            return {}
        
        with open(migration_file[0], 'r') as f:
            content = f.read()
        
        # Simple parsing to extract index names
        # This is a basic approach - a real implementation would need more robust parsing
        indexes = {}
        for line in content.splitlines():
            if "CREATE INDEX" in line and "ON" in line:
                index_name = line.split("CREATE INDEX")[1].split("ON")[0].strip()
                table_name = line.split("ON")[1].split("(")[0].strip()
                
                if table_name not in indexes:
                    indexes[table_name] = []
                indexes[table_name].append(index_name)
        
        return indexes
    except Exception as e:
        logger.error(f"Error parsing migration file: {e}")
        return {}


def test_rollback(migration_id: str) -> bool:
    """
    Test that a migration can be rolled back correctly.
    
    Args:
        migration_id: Migration ID to test (e.g., '002')
        
    Returns:
        bool: True if rollback test passes, False otherwise
    """
    # Get indexes before rollback
    logger.info(f"Getting indexes before rollback of migration {migration_id}...")
    before_indexes = get_indexes(TEST_DB_NAME)
    
    # Run the downgrade
    downgrade_success, _ = run_alembic_command(f"downgrade {migration_id}~1")
    if not downgrade_success:
        logger.error(f"Failed to downgrade from migration {migration_id}")
        return False
    
    # Get indexes after rollback
    logger.info("Getting indexes after rollback...")
    after_indexes = get_indexes(TEST_DB_NAME)
    
    # Expected indexes to be removed
    expected_removed = get_expected_indexes(migration_id)
    if not expected_removed:
        logger.error(f"Could not determine expected indexes for migration {migration_id}")
        return False
    
    # Verify indexes were removed
    all_verified = True
    for table, indexes in expected_removed.items():
        if table not in before_indexes:
            logger.warning(f"Table {table} not found in before_indexes")
            continue
        
        for expected_index in indexes:
            # Check if index was in before_indexes
            was_present = False
            for before_index in before_indexes.get(table, []):
                if expected_index.lower() in before_index["name"].lower():
                    was_present = True
                    break
            
            if not was_present:
                logger.warning(f"Index {expected_index} was not present before rollback")
                continue
            
            # Check if index is removed in after_indexes
            is_removed = True
            for after_index in after_indexes.get(table, []):
                if expected_index.lower() in after_index["name"].lower():
                    logger.error(f"Index {expected_index} still exists after rollback")
                    is_removed = False
                    break
            
            if is_removed:
                logger.info(f"Verified removal of index {expected_index} from table {table}")
            else:
                all_verified = False
    
    return all_verified


def reset_test_db() -> bool:
    """
    Reset the test database to a clean state.
    
    Returns:
        bool: True if successful, False otherwise
    """
    return create_test_database()


def setup_test_environment() -> bool:
    """
    Set up the test environment.
    
    Returns:
        bool: True if successful, False otherwise
    """
    # Create test database
    if not create_test_database():
        return False
    
    # Apply base migration
    success, _ = run_alembic_command("upgrade head")
    if not success:
        logger.error("Failed to apply base migration")
        return False
    
    logger.info("Test environment set up successfully")
    return True


def run_all_tests() -> bool:
    """
    Run all migration tests.
    
    Returns:
        bool: True if all tests pass, False otherwise
    """
    try:
        # Set up test environment
        if not setup_test_environment():
            return False
        
        # Get all migration IDs
        migration_ids = []
        try:
            result = subprocess.run(
                "alembic history",
                shell=True,
                cwd=MIGRATIONS_DIR,
                capture_output=True,
                text=True
            )
            
            for line in result.stdout.splitlines():
                if ":" in line:
                    migration_id = line.split(":")[0].strip().strip(">")
                    migration_ids.append(migration_id)
        except Exception as e:
            logger.error(f"Error getting migration history: {e}")
            return False
        
        # Skip the base migration (usually 'base')
        if 'base' in migration_ids:
            migration_ids.remove('base')
        
        # Test each migration
        all_passed = True
        for migration_id in migration_ids:
            logger.info(f"Testing migration {migration_id}...")
            
            # Reset database to a clean state
            if not reset_test_db():
                logger.error(f"Failed to reset test database for migration {migration_id}")
                all_passed = False
                continue
            
            # Apply migrations up to and including this one
            success, _ = run_alembic_command(f"upgrade {migration_id}")
            if not success:
                logger.error(f"Failed to upgrade to migration {migration_id}")
                all_passed = False
                continue
            
            # Verify migration
            if not verify_migration(migration_id):
                logger.error(f"Verification failed for migration {migration_id}")
                all_passed = False
                continue
            
            # Test rollback
            if not test_rollback(migration_id):
                logger.error(f"Rollback test failed for migration {migration_id}")
                all_passed = False
                continue
            
            logger.info(f"All tests passed for migration {migration_id}")
        
        return all_passed
    finally:
        # Restore alembic config
        restore_alembic_config()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Database migration testing tool")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--create-test-db", action="store_true",
                     help="Create test database and apply base migration")
    group.add_argument("--verify-migration", metavar="ID",
                     help="Verify a specific migration (e.g., '002')")
    group.add_argument("--test-rollback", metavar="ID",
                     help="Test rollback for a specific migration")
    group.add_argument("--run-all-tests", action="store_true",
                     help="Run all migration tests")
    
    args = parser.parse_args()
    
    try:
        if args.create_test_db:
            if setup_test_environment():
                logger.info("Test database created and initialized successfully")
                sys.exit(0)
            else:
                logger.error("Failed to create test database")
                sys.exit(1)
        
        elif args.verify_migration:
            if not setup_test_environment():
                logger.error("Failed to set up test environment")
                sys.exit(1)
                
            # Apply migration
            success, _ = run_alembic_command(f"upgrade {args.verify_migration}")
            if not success:
                logger.error(f"Failed to apply migration {args.verify_migration}")
                sys.exit(1)
                
            # Verify migration
            if verify_migration(args.verify_migration):
                logger.info(f"Migration {args.verify_migration} verified successfully")
                sys.exit(0)
            else:
                logger.error(f"Migration {args.verify_migration} verification failed")
                sys.exit(1)
        
        elif args.test_rollback:
            if not setup_test_environment():
                logger.error("Failed to set up test environment")
                sys.exit(1)
                
            # Apply migration
            success, _ = run_alembic_command(f"upgrade {args.test_rollback}")
            if not success:
                logger.error(f"Failed to apply migration {args.test_rollback}")
                sys.exit(1)
                
            # Test rollback
            if test_rollback(args.test_rollback):
                logger.info(f"Rollback test for migration {args.test_rollback} passed")
                sys.exit(0)
            else:
                logger.error(f"Rollback test for migration {args.test_rollback} failed")
                sys.exit(1)
        
        elif args.run_all_tests:
            if run_all_tests():
                logger.info("All migration tests passed")
                sys.exit(0)
            else:
                logger.error("Some migration tests failed")
                sys.exit(1)
    
    finally:
        # Always restore alembic config
        restore_alembic_config()


if __name__ == "__main__":
    main() 