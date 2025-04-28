"""
MongoDB connection module for Forex Trading system.

This module provides functionality to connect to MongoDB and get database and collection objects.
"""

import os
import logging
from typing import Dict, Any, Optional
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from pymongo.database import Database
from pymongo.collection import Collection

# Load configuration from environment
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "forex")
MONGO_CONNECT_TIMEOUT = int(os.getenv("MONGO_CONNECT_TIMEOUT", "5000"))

# Check if we're in mock mode
MOCK_DB = os.getenv("MOCK_DB", "false").lower() == "true"

# Configure logger
logger = logging.getLogger(__name__)

# Singleton client
_mongo_client = None

def _get_mongo_client() -> Optional[MongoClient]:
    """
    Get MongoDB client with connection pooling. Uses singleton pattern.
    
    Returns:
        MongoDB client instance or None if connection failed
    """
    global _mongo_client
    
    if MOCK_DB:
        logger.info("Using mock MongoDB client")
        return "MOCK_CLIENT"
    
    if _mongo_client is not None:
        return _mongo_client
        
    try:
        # Connection options
        options = {
            "serverSelectionTimeoutMS": MONGO_CONNECT_TIMEOUT,
            "connect": True,
            "appname": "ForexTradingV4",
            "retryWrites": True,
        }
        
        # Create client
        client = MongoClient(MONGO_URI, **options)
        
        # Test connection
        client.admin.command("ping")
        
        _mongo_client = client
        logger.info(f"Connected to MongoDB at {MONGO_URI}")
        return client
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        return None

def get_database(db_name: Optional[str] = None) -> Optional[Database]:
    """
    Get MongoDB database.
    
    Args:
        db_name: Database name (default: from environment)
        
    Returns:
        MongoDB database object or None if connection failed
    """
    if MOCK_DB:
        logger.debug("Using mock MongoDB database")
        return "MOCK_DATABASE"
        
    client = _get_mongo_client()
    if client is None:
        return None
        
    db_name = db_name or MONGO_DB_NAME
    return client[db_name]

def get_collection(collection_name: str, db_name: Optional[str] = None) -> Optional[Collection]:
    """
    Get MongoDB collection.
    
    Args:
        collection_name: Collection name
        db_name: Database name (default: from environment)
        
    Returns:
        MongoDB collection object or None if connection failed
    """
    if MOCK_DB:
        logger.debug(f"Using mock MongoDB collection: {collection_name}")
        return "MOCK_COLLECTION"
        
    db = get_database(db_name)
    if db is None:
        return None
        
    return db[collection_name]

def close_mongo_connection() -> None:
    """Close MongoDB connection."""
    global _mongo_client
    
    if MOCK_DB:
        logger.debug("Closing mock MongoDB connection")
        return
        
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
        logger.info("Closed MongoDB connection") 