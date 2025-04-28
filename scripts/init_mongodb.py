#!/usr/bin/env python
"""
MongoDB Initialization Script for Forex Trading Application

This script initializes the MongoDB database with the proper collections,
schemas, and indexes for the Forex Trading application.

Usage:
    python init_mongodb.py [--config CONFIG_FILE] [--db-name DB_NAME]
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Import required modules
from src.db.mongodb_connection import get_mongodb_client, close_mongodb_connection
from src.db.mongodb_init import initialize_database, verify_database_setup
from src.db.mongodb_config import get_config, save_config_to_file

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Initialize MongoDB for Forex Trading application'
    )
    parser.add_argument(
        '--config',
        help='Path to the MongoDB configuration file'
    )
    parser.add_argument(
        '--db-name',
        help='Name of the MongoDB database to initialize'
    )
    parser.add_argument(
        '--save-config',
        help='Save current configuration to the specified file'
    )
    parser.add_argument(
        '--host',
        help='MongoDB host (overrides config file and environment variables)'
    )
    parser.add_argument(
        '--port',
        type=int,
        help='MongoDB port (overrides config file and environment variables)'
    )
    parser.add_argument(
        '--username',
        help='MongoDB username (overrides config file and environment variables)'
    )
    parser.add_argument(
        '--password',
        help='MongoDB password (overrides config file and environment variables)'
    )
    
    return parser.parse_args()

def main():
    """Initialize the MongoDB database."""
    args = parse_args()
    
    # Get configuration
    config = get_config(args.config)
    
    # Override configuration with command-line arguments
    if args.db_name:
        os.environ["MONGODB_DB_NAME"] = args.db_name
        config["db_name"] = args.db_name
    
    if args.host:
        os.environ["MONGODB_HOST"] = args.host
        config["host"] = args.host
    
    if args.port:
        os.environ["MONGODB_PORT"] = str(args.port)
        config["port"] = args.port
    
    if args.username:
        os.environ["MONGODB_USERNAME"] = args.username
        config["username"] = args.username
    
    if args.password:
        os.environ["MONGODB_PASSWORD"] = args.password
        config["password"] = args.password
    
    # Save configuration if requested
    if args.save_config:
        save_config_to_file(config, args.save_config)
        logger.info(f"Configuration saved to {args.save_config}")
    
    try:
        # Connect to MongoDB
        client = get_mongodb_client()
        
        # Initialize database
        db_name = config.get("db_name")
        logger.info(f"Initializing MongoDB database: {db_name}")
        db = initialize_database(client, db_name)
        
        # Verify database setup
        verification = verify_database_setup(db)
        
        if verification["overall_status"] == "success":
            logger.info("Database initialization completed successfully.")
        else:
            logger.warning("Database initialization completed with warnings.")
            # Print details of warnings
            for collection_name, status in verification["collections"].items():
                if status["status"] != "success":
                    logger.warning(f"Collection '{collection_name}': {status['status']}")
                    if "indexes" in status:
                        for index_name, index_status in status["indexes"].items():
                            if index_status == "missing":
                                logger.warning(f"  Missing index: {index_name}")
        
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        sys.exit(1)
    finally:
        # Close connection
        close_mongodb_connection()

if __name__ == "__main__":
    main() 