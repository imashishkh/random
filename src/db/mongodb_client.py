"""
MongoDB client for the Forex sentiment analysis system.

This module handles connections and operations with MongoDB for storing social media data.
"""

import logging
from typing import Any, Dict, List, Optional, Union

import motor.motor_asyncio
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError

from .mongodb_schema import (
    RedditComment, RedditPost, SentimentAnalysisResult, SocialMediaPost, TwitterPost
)

logger = logging.getLogger(__name__)


class MongoDBClient:
    """Client for interacting with MongoDB."""
    
    def __init__(
        self,
        connection_string: str = "mongodb://localhost:27017",
        database_name: str = "forex_sentiment",
        max_pool_size: int = 10,
        timeout_ms: int = 5000,
    ):
        """
        Initialize MongoDB client.
        
        Args:
            connection_string: MongoDB connection URI
            database_name: Name of the database to use
            max_pool_size: Maximum pool size for the client
            timeout_ms: Connection timeout in milliseconds
        """
        self.connection_string = connection_string
        self.database_name = database_name
        self.max_pool_size = max_pool_size
        self.timeout_ms = timeout_ms
        
        self.client = None
        self.db = None
        
        # Collections
        self.posts_collection = None
        self.sentiment_collection = None
        self.indicators_collection = None
    
    async def connect(self) -> None:
        """Connect to MongoDB and initialize collections."""
        try:
            # Create client
            self.client = motor.motor_asyncio.AsyncIOMotorClient(
                self.connection_string,
                maxPoolSize=self.max_pool_size,
                serverSelectionTimeoutMS=self.timeout_ms,
            )
            
            # Get database
            self.db = self.client[self.database_name]
            
            # Initialize collections
            self.posts_collection = self.db["social_media_posts"]
            self.sentiment_collection = self.db["sentiment_analysis"]
            self.indicators_collection = self.db["forex_indicators"]
            
            # Create indexes
            await self._create_indexes()
            
            # Test connection
            await self.db.command("ping")
            logger.info(f"Connected to MongoDB: {self.database_name}")
        
        except ServerSelectionTimeoutError as e:
            logger.error(f"MongoDB connection error: {e}")
            raise
    
    async def close(self) -> None:
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")
    
    async def _create_indexes(self) -> None:
        """Create necessary indexes for the collections."""
        # Posts collection indexes
        await self.posts_collection.create_index([("id", ASCENDING), ("source", ASCENDING)], unique=True)
        await self.posts_collection.create_index([("created_at", DESCENDING)])
        await self.posts_collection.create_index([("source", ASCENDING)])
        await self.posts_collection.create_index([("sentiment_score", ASCENDING)])
        await self.posts_collection.create_index([("forex_pairs", ASCENDING)])
        
        # Sentiment collection indexes
        await self.sentiment_collection.create_index([("post_id", ASCENDING), ("source", ASCENDING)], unique=True)
        await self.sentiment_collection.create_index([("analyzed_at", DESCENDING)])
        await self.sentiment_collection.create_index([("score", ASCENDING)])
        await self.sentiment_collection.create_index([("forex_pairs", ASCENDING)])
        
        # Indicators collection indexes
        await self.indicators_collection.create_index([("pair", ASCENDING), ("timestamp", DESCENDING), ("timeframe", ASCENDING)], unique=True)
    
    async def insert_post(self, post: Union[SocialMediaPost, RedditPost, RedditComment, TwitterPost]) -> Optional[str]:
        """
        Insert a social media post into the database.
        
        Args:
            post: Post to insert
            
        Returns:
            Post ID if successful, None if duplicate
        """
        try:
            post_dict = post.dict()
            result = await self.posts_collection.insert_one(post_dict)
            logger.debug(f"Inserted post: {result.inserted_id}")
            return str(result.inserted_id)
        except DuplicateKeyError:
            logger.debug(f"Duplicate post: {post.id} from {post.source}")
            return None
    
    async def insert_posts(self, posts: List[Union[SocialMediaPost, RedditPost, RedditComment, TwitterPost]]) -> int:
        """
        Insert multiple social media posts into the database.
        
        Args:
            posts: List of posts to insert
            
        Returns:
            Number of inserted posts
        """
        if not posts:
            return 0
        
        post_dicts = [post.dict() for post in posts]
        
        try:
            result = await self.posts_collection.insert_many(post_dicts, ordered=False)
            logger.debug(f"Inserted {len(result.inserted_ids)} posts")
            return len(result.inserted_ids)
        except Exception as e:
            if isinstance(e, DuplicateKeyError):
                # Some were duplicates, but some may have been inserted
                logger.debug(f"Duplicate key error during bulk insert: {e}")
                return e.details.get('nInserted', 0)
            else:
                logger.error(f"Error inserting posts: {e}")
                raise
    
    async def get_post(self, post_id: str, source: str) -> Optional[Dict[str, Any]]:
        """
        Get a post by ID and source.
        
        Args:
            post_id: Post ID
            source: Source platform
            
        Returns:
            Post document or None if not found
        """
        return await self.posts_collection.find_one({"id": post_id, "source": source})
    
    async def get_posts(
        self,
        source: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: int = DESCENDING,
        sentiment_range: Optional[tuple] = None,
        forex_pair: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get posts with various filters.
        
        Args:
            source: Filter by source platform
            limit: Maximum number of posts to return
            offset: Number of posts to skip
            sort_by: Field to sort by
            sort_order: Sort order (ASCENDING or DESCENDING)
            sentiment_range: Tuple of (min_score, max_score)
            forex_pair: Filter by mentioned forex pair
            
        Returns:
            List of post documents
        """
        query = {}
        
        if source:
            query["source"] = source
        
        if sentiment_range:
            min_score, max_score = sentiment_range
            query["sentiment_score"] = {"$gte": min_score, "$lte": max_score}
        
        if forex_pair:
            query["forex_pairs"] = forex_pair
        
        cursor = self.posts_collection.find(query).sort(sort_by, sort_order).skip(offset).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    async def insert_sentiment(self, sentiment: SentimentAnalysisResult) -> Optional[str]:
        """
        Insert a sentiment analysis result.
        
        Args:
            sentiment: Sentiment analysis result
            
        Returns:
            Inserted ID if successful, None if duplicate
        """
        try:
            sentiment_dict = sentiment.dict()
            result = await self.sentiment_collection.insert_one(sentiment_dict)
            logger.debug(f"Inserted sentiment analysis: {result.inserted_id}")
            return str(result.inserted_id)
        except DuplicateKeyError:
            logger.debug(f"Duplicate sentiment analysis: {sentiment.post_id} from {sentiment.source}")
            return None
    
    async def update_post_sentiment(
        self, post_id: str, source: str, sentiment_score: float, sentiment_label: str, details: Dict[str, Any] = None
    ) -> bool:
        """
        Update the sentiment fields of a post.
        
        Args:
            post_id: Post ID
            source: Source platform
            sentiment_score: Overall sentiment score
            sentiment_label: Sentiment label
            details: Detailed sentiment analysis
            
        Returns:
            True if updated, False if post not found
        """
        update_data = {
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
        }
        
        if details:
            update_data["sentiment_details"] = details
        
        result = await self.posts_collection.update_one(
            {"id": post_id, "source": source},
            {"$set": update_data}
        )
        
        return result.modified_count > 0
    
    async def get_sentiment_stats(
        self, source: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get sentiment statistics for posts.
        
        Args:
            source: Filter by source platform
            start_date: Start date for filtering
            end_date: End date for filtering
            
        Returns:
            Dictionary with sentiment statistics
        """
        query = {}
        
        if source:
            query["source"] = source
        
        date_query = {}
        if start_date:
            date_query["$gte"] = start_date
        
        if end_date:
            date_query["$lte"] = end_date
        
        if date_query:
            query["created_at"] = date_query
        
        pipeline = [
            {"$match": query},
            {"$match": {"sentiment_score": {"$ne": None}}},
            {
                "$group": {
                    "_id": None,
                    "average_score": {"$avg": "$sentiment_score"},
                    "count": {"$sum": 1},
                    "positive_count": {
                        "$sum": {"$cond": [{"$eq": ["$sentiment_label", "positive"]}, 1, 0]}
                    },
                    "negative_count": {
                        "$sum": {"$cond": [{"$eq": ["$sentiment_label", "negative"]}, 1, 0]}
                    },
                    "neutral_count": {
                        "$sum": {"$cond": [{"$eq": ["$sentiment_label", "neutral"]}, 1, 0]}
                    },
                }
            },
        ]
        
        result = await self.posts_collection.aggregate(pipeline).to_list(length=1)
        
        if not result:
            return {
                "average_score": 0,
                "count": 0,
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
            }
        
        stats = result[0]
        del stats["_id"]
        
        return stats 