"""
MongoDB connection module for Forex Trading application.

This module handles MongoDB connection management including connection pooling,
connection string parsing, and database/collection access.
"""

import os
import logging
from typing import Dict, Any, Optional, List
from urllib.parse import quote_plus

import pymongo
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure, ConfigurationError

# Import MongoDB initialization and schema modules
from .mongodb_init import initialize_database, verify_database_setup

# Set up logging
logger = logging.getLogger(__name__)

# Default MongoDB connection parameters
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 27017
DEFAULT_DB_NAME = "forex_trading"
DEFAULT_USERNAME = None
DEFAULT_PASSWORD = None
DEFAULT_AUTH_SOURCE = "admin"
DEFAULT_AUTH_MECHANISM = "SCRAM-SHA-256"  # Use SCRAM-SHA-256 for newer MongoDB instances

# Connection pool settings
DEFAULT_MIN_POOL_SIZE = 5
DEFAULT_MAX_POOL_SIZE = 10
DEFAULT_MAX_IDLE_TIME_MS = 10000  # 10 seconds
DEFAULT_CONNECT_TIMEOUT_MS = 5000  # 5 seconds
DEFAULT_SERVER_SELECTION_TIMEOUT_MS = 5000  # 5 seconds

# Global client instance for connection pooling
_mongo_client: Optional[MongoClient] = None
_mongo_db: Optional[Database] = None


def build_connection_string(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    username: Optional[str] = DEFAULT_USERNAME,
    password: Optional[str] = DEFAULT_PASSWORD,
    auth_source: str = DEFAULT_AUTH_SOURCE,
    auth_mechanism: str = DEFAULT_AUTH_MECHANISM
) -> str:
    """
    Build MongoDB connection string with proper authentication.
    
    Args:
        host (str): MongoDB host
        port (int): MongoDB port
        username (Optional[str]): Username for authentication
        password (Optional[str]): Password for authentication
        auth_source (str): Authentication source database
        auth_mechanism (str): Authentication mechanism
        
    Returns:
        str: MongoDB connection string
    """
    # Basic connection string
    connection_string = f"mongodb://"
    
    # Add authentication if provided
    if username and password:
        encoded_username = quote_plus(username)
        encoded_password = quote_plus(password)
        connection_string += f"{encoded_username}:{encoded_password}@"
    
    # Add host and port
    connection_string += f"{host}:{port}"
    
    # Add authentication parameters if username is provided
    if username:
        connection_string += f"/?authSource={auth_source}&authMechanism={auth_mechanism}"
    
    return connection_string


def get_connection_options() -> Dict[str, Any]:
    """
    Get MongoDB connection options from environment variables or defaults.
    
    Returns:
        Dict[str, Any]: Dictionary of connection options
    """
    return {
        "host": os.environ.get("MONGODB_HOST", DEFAULT_HOST),
        "port": int(os.environ.get("MONGODB_PORT", DEFAULT_PORT)),
        "username": os.environ.get("MONGODB_USERNAME", DEFAULT_USERNAME),
        "password": os.environ.get("MONGODB_PASSWORD", DEFAULT_PASSWORD),
        "db_name": os.environ.get("MONGODB_DB_NAME", DEFAULT_DB_NAME),
        "auth_source": os.environ.get("MONGODB_AUTH_SOURCE", DEFAULT_AUTH_SOURCE),
        "auth_mechanism": os.environ.get("MONGODB_AUTH_MECHANISM", DEFAULT_AUTH_MECHANISM),
        "min_pool_size": int(os.environ.get("MONGODB_MIN_POOL_SIZE", DEFAULT_MIN_POOL_SIZE)),
        "max_pool_size": int(os.environ.get("MONGODB_MAX_POOL_SIZE", DEFAULT_MAX_POOL_SIZE)),
        "max_idle_time_ms": int(os.environ.get("MONGODB_MAX_IDLE_TIME_MS", DEFAULT_MAX_IDLE_TIME_MS)),
        "connect_timeout_ms": int(os.environ.get("MONGODB_CONNECT_TIMEOUT_MS", DEFAULT_CONNECT_TIMEOUT_MS)),
        "server_selection_timeout_ms": int(os.environ.get("MONGODB_SERVER_SELECTION_TIMEOUT_MS", DEFAULT_SERVER_SELECTION_TIMEOUT_MS)),
    }


def get_mongodb_client() -> MongoClient:
    """
    Get or create a MongoDB client with connection pooling.
    
    Returns:
        MongoClient: MongoDB client instance
    
    Raises:
        ConnectionFailure: If unable to connect to MongoDB
    """
    global _mongo_client
    
    if _mongo_client is not None:
        return _mongo_client
    
    # Get connection options
    options = get_connection_options()
    
    # Build connection string
    connection_string = build_connection_string(
        host=options["host"],
        port=options["port"],
        username=options["username"],
        password=options["password"],
        auth_source=options["auth_source"],
        auth_mechanism=options["auth_mechanism"]
    )
    
    # Create client with connection pooling
    try:
        logger.info(f"Connecting to MongoDB at {options['host']}:{options['port']}")
        _mongo_client = MongoClient(
            connection_string,
            minPoolSize=options["min_pool_size"],
            maxPoolSize=options["max_pool_size"],
            maxIdleTimeMS=options["max_idle_time_ms"],
            connectTimeoutMS=options["connect_timeout_ms"],
            serverSelectionTimeoutMS=options["server_selection_timeout_ms"]
        )
        
        # Ping the server to verify connection
        _mongo_client.admin.command('ping')
        logger.info("Successfully connected to MongoDB")
        
        return _mongo_client
    except (ConnectionFailure, ConfigurationError) as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        raise ConnectionFailure(f"Could not connect to MongoDB: {str(e)}")


def get_mongodb_database() -> Database:
    """
    Get the MongoDB database, initializing it if necessary.
    
    Returns:
        Database: MongoDB database instance
    
    Raises:
        ConnectionFailure: If unable to connect to MongoDB
    """
    global _mongo_db
    
    if _mongo_db is not None:
        return _mongo_db
    
    # Get client and database name
    client = get_mongodb_client()
    options = get_connection_options()
    db_name = options["db_name"]
    
    # Initialize database with collections and schemas
    _mongo_db = initialize_database(client, db_name)
    
    # Verify database setup
    verification = verify_database_setup(_mongo_db)
    if verification["overall_status"] != "success":
        logger.warning("Database verification completed with warnings or errors")
    
    return _mongo_db


def get_collection(collection_name: str) -> Collection:
    """
    Get a MongoDB collection by name.
    
    Args:
        collection_name (str): Name of the collection to retrieve
        
    Returns:
        Collection: MongoDB collection instance
    
    Raises:
        ValueError: If the collection name is invalid
    """
    if not collection_name:
        raise ValueError("Collection name cannot be empty")
    
    # Get database
    db = get_mongodb_database()
    
    # Check if collection exists
    if collection_name not in db.list_collection_names():
        logger.warning(f"Collection '{collection_name}' not found. It will be created on first insert.")
    
    return db[collection_name]


def get_available_collections() -> List[str]:
    """
    Get a list of all available collections in the database.
    
    Returns:
        List[str]: List of collection names
    """
    db = get_mongodb_database()
    return db.list_collection_names()


def close_mongodb_connection() -> None:
    """
    Close the MongoDB connection.
    """
    global _mongo_client, _mongo_db
    
    if _mongo_client is not None:
        logger.info("Closing MongoDB connection")
        _mongo_client.close()
        _mongo_client = None
        _mongo_db = None 