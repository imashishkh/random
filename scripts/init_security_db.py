#!/usr/bin/env python3
"""
Security Database Initialization Script

This script initializes the security-related database tables required for
the enhanced withdrawal security features.
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Add the parent directory to the path so we can import our modules
script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
project_root = script_dir.parent
sys.path.append(str(project_root))

from dotenv import load_dotenv
from src.db import get_db_connection

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('security_db_init')

def read_sql_file(file_path):
    """Read SQL commands from a file"""
    with open(file_path, 'r') as file:
        return file.read()

def init_security_tables(sql_file_path=None):
    """
    Initialize security database tables from the SQL schema file.
    
    Args:
        sql_file_path: Path to the SQL schema file (default: src/db/security_schema.sql)
    
    Returns:
        True if successful, False otherwise
    """
    # Default schema path if not provided
    if not sql_file_path:
        sql_file_path = project_root / "src" / "db" / "security_schema.sql"
    
    logger.info(f"Initializing security database tables from {sql_file_path}")
    
    try:
        # Read SQL schema file
        sql = read_sql_file(sql_file_path)
        
        # Connect to database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Execute SQL commands
        cursor.execute(sql)
        conn.commit()
        
        logger.info("Security database tables created successfully")
        
        # Verify tables were created
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND 
                  table_name IN ('security_alerts', 'user_auth_events', 'withdrawal_verifications', 
                                'ip_whitelist', 'mfa_backup_codes')
        """)
        
        tables = cursor.fetchall()
        logger.info(f"Verified tables: {', '.join([t[0] for t in tables])}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error initializing security database tables: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def main():
    """Main function to initialize security database tables"""
    parser = argparse.ArgumentParser(description='Initialize security database tables')
    parser.add_argument('--sql-file', type=str,
                        help='Path to the SQL schema file')
    args = parser.parse_args()
    
    sql_file_path = args.sql_file
    
    # If SQL file path is provided, convert to Path object
    if sql_file_path:
        sql_file_path = Path(sql_file_path)
    
    # Initialize security tables
    success = init_security_tables(sql_file_path)
    
    if success:
        logger.info("Security database initialization completed successfully")
    else:
        logger.error("Security database initialization failed")
        sys.exit(1)

if __name__ == "__main__":
    main() 