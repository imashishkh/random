"""
MongoDB initialization module for Forex Trading system.

This module is responsible for initializing MongoDB collections and indexes.
"""

import os
import logging
from typing import List, Dict, Any, Optional

from .mongo_connection import get_database, get_collection

# Check if we're in mock mode
MOCK_DB = os.getenv("MOCK_DB", "false").lower() == "true"

# Configure logger
logger = logging.getLogger(__name__)

def initialize_mongodb() -> bool:
    """
    Initialize MongoDB collections and indexes.
    
    Returns:
        bool: True if initialization was successful, False otherwise
    """
    if MOCK_DB:
        logger.info("Mock mode enabled, skipping MongoDB initialization")
        return True
        
    try:
        db = get_database()
        if not db:
            logger.error("Failed to get MongoDB database")
            return False
            
        # Create collections if they don't exist
        _create_collections(db)
        
        # Create indexes
        _create_indexes(db)
        
        logger.info("MongoDB initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Error initializing MongoDB: {e}")
        return False

def _create_collections(db) -> None:
    """
    Create collections if they don't exist.
    
    Args:
        db: MongoDB database
    """
    collections_to_create = [
        "news_articles",
        "sentiment_analysis",
        "market_events",
        "data_sources"
    ]
    
    existing_collections = db.list_collection_names()
    
    for collection_name in collections_to_create:
        if collection_name not in existing_collections:
            db.create_collection(collection_name)
            logger.info(f"Created collection: {collection_name}")

def _create_indexes(db) -> None:
    """
    Create indexes on collections.
    
    Args:
        db: MongoDB database
    """
    # News articles indexes
    news_collection = db["news_articles"]
    news_collection.create_index("published_at")
    news_collection.create_index("source")
    news_collection.create_index([("title", "text"), ("content", "text")])
    
    # Sentiment analysis indexes
    sentiment_collection = db["sentiment_analysis"]
    sentiment_collection.create_index("entity")
    sentiment_collection.create_index("created_at")
    
    # Market events indexes
    events_collection = db["market_events"]
    events_collection.create_index("timestamp")
    events_collection.create_index("event_type")
    
    # Data sources indexes
    sources_collection = db["data_sources"]
    sources_collection.create_index("name", unique=True)
    sources_collection.create_index("type")
    
    logger.info("Created MongoDB indexes")


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Run initialization
    initialize_mongodb() 