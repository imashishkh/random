"""
Perplexity Research Storage

This module provides functionality for storing and retrieving
research data collected from the Perplexity API.
"""
import logging
import json
import hashlib
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta

from ...db.mongo_connection import get_collection
from ...cache.redis_client import set_cache, get_cache, delete_pattern

# Set up logging
logger = logging.getLogger(__name__)

class ResearchStorage:
    """
    Storage handler for Perplexity API research data.
    Provides methods for storing and retrieving collected data.
    """
    
    def __init__(self):
        """Initialize the storage handler."""
        # MongoDB collection names
        self.collections = {
            "market_news": "perplexity_market_news",
            "economic_indicator": "perplexity_economic_indicators",
            "central_bank": "perplexity_central_bank",
            "market_sentiment": "perplexity_market_sentiment",
            "general": "perplexity_research"
        }
        
        # Cache key prefixes
        self.cache_prefixes = {
            "market_news": "perplexity:news:",
            "economic_indicator": "perplexity:economic:",
            "central_bank": "perplexity:bank:",
            "market_sentiment": "perplexity:sentiment:",
            "search": "perplexity:search:",
            "recent": "perplexity:recent:"
        }
        
        # Cache TTLs (in seconds)
        self.cache_ttls = {
            "market_news": 1800,        # 30 minutes
            "economic_indicator": 7200,  # 2 hours
            "central_bank": 14400,       # 4 hours
            "market_sentiment": 3600,    # 1 hour
            "search": 600,               # 10 minutes
            "recent": 300                # 5 minutes
        }
        
        logger.info("Research storage initialized")
    
    async def store_item(self, item: Dict[str, Any]) -> bool:
        """
        Store a research item in the appropriate collection.
        
        Args:
            item: Research item to store
            
        Returns:
            Success status
        """
        if not item:
            logger.warning("Cannot store empty item")
            return False
        
        # Determine collection type
        collection_type = item.get("collection_type", "general")
        collection_name = self.collections.get(collection_type, self.collections["general"])
        
        # Generate content hash for deduplication
        content_hash = self._generate_content_hash(item)
        item["content_hash"] = content_hash
        
        # Add timestamps if not present
        if "created_at" not in item:
            item["created_at"] = datetime.now().isoformat()
        if "updated_at" not in item:
            item["updated_at"] = datetime.now().isoformat()
        
        try:
            # Get collection
            collection = get_collection(collection_name)
            
            # Check for existing item with same hash
            existing = await collection.find_one({"content_hash": content_hash})
            if existing:
                logger.debug(f"Item with hash {content_hash[:8]} already exists, skipping")
                return False
            
            # Insert the item
            result = await collection.insert_one(item)
            if result.inserted_id:
                logger.debug(f"Stored item in {collection_name} with ID {result.inserted_id}")
                
                # Invalidate related cache
                cache_prefix = self.cache_prefixes.get(collection_type, "perplexity:")
                await delete_pattern(f"{cache_prefix}*")
                
                return True
            else:
                logger.error("Failed to insert item, no ID returned")
                return False
                
        except Exception as e:
            logger.error(f"Error storing item in {collection_name}: {e}")
            return False
    
    async def get_recent_items(
        self,
        collection_type: str,
        limit: int = 10,
        skip: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get recent items from a specific collection.
        
        Args:
            collection_type: Type of collection (market_news, economic_indicator, etc.)
            limit: Maximum number of items to return
            skip: Number of items to skip
            filters: Additional filters to apply
            use_cache: Whether to use cache
            
        Returns:
            List of items
        """
        # Generate cache key
        cache_key = f"{self.cache_prefixes['recent']}{collection_type}:limit={limit}:skip={skip}:filters={json.dumps(filters or {})}"
        
        # Try to get from cache
        if use_cache:
            cached = await get_cache(cache_key)
            if cached:
                logger.debug(f"Retrieved {len(cached)} recent {collection_type} items from cache")
                return cached
        
        # Get collection name
        collection_name = self.collections.get(collection_type, self.collections["general"])
        
        try:
            # Get collection
            collection = get_collection(collection_name)
            
            # Build query
            query = filters or {}
            
            # Get items
            cursor = collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
            items = await cursor.to_list(length=limit)
            
            # Convert ObjectId to string for JSON serialization
            for item in items:
                if "_id" in item:
                    item["_id"] = str(item["_id"])
            
            # Cache results
            if use_cache:
                await set_cache(
                    cache_key,
                    items,
                    ttl=self.cache_ttls.get("recent", 300)
                )
            
            logger.debug(f"Retrieved {len(items)} recent {collection_type} items from database")
            return items
            
        except Exception as e:
            logger.error(f"Error retrieving recent items from {collection_name}: {e}")
            return []
    
    async def search_items(
        self,
        query: str,
        collection_types: Optional[List[str]] = None,
        limit: int = 20,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for items across collections.
        
        Args:
            query: Search query
            collection_types: Types of collections to search (None for all)
            limit: Maximum number of items to return
            use_cache: Whether to use cache
            
        Returns:
            List of matching items
        """
        # Generate cache key
        cache_key = f"{self.cache_prefixes['search']}q={query}:types={'-'.join(collection_types or ['all'])}:limit={limit}"
        
        # Try to get from cache
        if use_cache:
            cached = await get_cache(cache_key)
            if cached:
                logger.debug(f"Retrieved {len(cached)} search results from cache for query '{query}'")
                return cached
        
        # Determine collections to search
        if not collection_types:
            collection_types = list(self.collections.keys())
        
        collection_names = [self.collections[t] for t in collection_types if t in self.collections]
        
        # Create text search query
        text_query = {"$text": {"$search": query}}
        
        results = []
        try:
            # Search each collection
            for collection_name in collection_names:
                collection = get_collection(collection_name)
                
                # Check if text index exists
                indexes = await collection.list_indexes().to_list(length=100)
                has_text_index = any(idx.get("key", {}).get("_fts") == "text" for idx in indexes)
                
                if has_text_index:
                    # Use text index
                    cursor = collection.find(
                        text_query,
                        {"score": {"$meta": "textScore"}}
                    ).sort([("score", {"$meta": "textScore"})]).limit(limit)
                else:
                    # Fallback to basic regex search
                    regex_query = {"$or": [
                        {"text": {"$regex": query, "$options": "i"}},
                        {"headline": {"$regex": query, "$options": "i"}},
                        {"tags": {"$elemMatch": {"$regex": query, "$options": "i"}}}
                    ]}
                    cursor = collection.find(regex_query).sort("created_at", -1).limit(limit)
                
                # Get items
                items = await cursor.to_list(length=limit)
                
                # Convert ObjectId to string
                for item in items:
                    if "_id" in item:
                        item["_id"] = str(item["_id"])
                    
                    # Add collection type if not present
                    if "collection_type" not in item:
                        for ctype, cname in self.collections.items():
                            if cname == collection_name:
                                item["collection_type"] = ctype
                                break
                
                results.extend(items)
            
            # Sort combined results by relevance or recency
            results.sort(key=lambda x: x.get("score", 0) or x.get("created_at", ""), reverse=True)
            
            # Limit combined results
            results = results[:limit]
            
            # Cache results
            if use_cache:
                await set_cache(
                    cache_key,
                    results,
                    ttl=self.cache_ttls.get("search", 600)
                )
            
            logger.debug(f"Retrieved {len(results)} search results from database for query '{query}'")
            return results
            
        except Exception as e:
            logger.error(f"Error searching for '{query}': {e}")
            return []
    
    async def get_items_by_tag(
        self,
        tag: str,
        collection_types: Optional[List[str]] = None,
        limit: int = 20,
        skip: int = 0,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get items by tag.
        
        Args:
            tag: Tag to search for
            collection_types: Types of collections to search (None for all)
            limit: Maximum number of items to return
            skip: Number of items to skip
            use_cache: Whether to use cache
            
        Returns:
            List of matching items
        """
        # Generate cache key
        cache_key = f"{self.cache_prefixes['search']}tag={tag}:types={'-'.join(collection_types or ['all'])}:limit={limit}:skip={skip}"
        
        # Try to get from cache
        if use_cache:
            cached = await get_cache(cache_key)
            if cached:
                logger.debug(f"Retrieved {len(cached)} items with tag '{tag}' from cache")
                return cached
        
        # Determine collections to search
        if not collection_types:
            collection_types = list(self.collections.keys())
        
        collection_names = [self.collections[t] for t in collection_types if t in self.collections]
        
        # Create tag query
        tag_query = {"tags": tag}
        
        results = []
        try:
            # Search each collection
            for collection_name in collection_names:
                collection = get_collection(collection_name)
                
                # Get items
                cursor = collection.find(tag_query).sort("created_at", -1).skip(skip).limit(limit)
                items = await cursor.to_list(length=limit)
                
                # Convert ObjectId to string
                for item in items:
                    if "_id" in item:
                        item["_id"] = str(item["_id"])
                    
                    # Add collection type if not present
                    if "collection_type" not in item:
                        for ctype, cname in self.collections.items():
                            if cname == collection_name:
                                item["collection_type"] = ctype
                                break
                
                results.extend(items)
            
            # Sort by recency
            results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            # Limit combined results
            results = results[:limit]
            
            # Cache results
            if use_cache:
                await set_cache(
                    cache_key,
                    results,
                    ttl=self.cache_ttls.get("search", 600)
                )
            
            logger.debug(f"Retrieved {len(results)} items with tag '{tag}' from database")
            return results
            
        except Exception as e:
            logger.error(f"Error getting items with tag '{tag}': {e}")
            return []
    
    async def get_item_by_id(
        self,
        item_id: str,
        collection_type: Optional[str] = None,
        use_cache: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific item by ID.
        
        Args:
            item_id: Item ID
            collection_type: Type of collection (None to search all)
            use_cache: Whether to use cache
            
        Returns:
            Item or None if not found
        """
        # Generate cache key
        cache_key = f"{self.cache_prefixes.get(collection_type, 'perplexity:')}id={item_id}"
        
        # Try to get from cache
        if use_cache:
            cached = await get_cache(cache_key)
            if cached:
                logger.debug(f"Retrieved item {item_id} from cache")
                return cached
        
        # Determine collections to search
        if collection_type:
            collection_names = [self.collections.get(collection_type, self.collections["general"])]
        else:
            collection_names = list(self.collections.values())
        
        try:
            # Convert string ID to ObjectId if necessary
            from bson.objectid import ObjectId
            try:
                obj_id = ObjectId(item_id)
                id_query = {"_id": obj_id}
            except:
                # If not a valid ObjectId, try as string
                id_query = {"_id": item_id}
            
            # Search each collection
            for collection_name in collection_names:
                collection = get_collection(collection_name)
                
                # Try to find item
                item = await collection.find_one(id_query)
                
                if item:
                    # Convert ObjectId to string
                    if "_id" in item:
                        item["_id"] = str(item["_id"])
                    
                    # Add collection type if not present
                    if "collection_type" not in item:
                        for ctype, cname in self.collections.items():
                            if cname == collection_name:
                                item["collection_type"] = ctype
                                break
                    
                    # Cache result
                    if use_cache:
                        await set_cache(
                            cache_key,
                            item,
                            ttl=self.cache_ttls.get(collection_type, 3600)
                        )
                    
                    logger.debug(f"Retrieved item {item_id} from {collection_name}")
                    return item
            
            logger.debug(f"Item {item_id} not found in any collection")
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving item {item_id}: {e}")
            return None
    
    async def get_popular_tags(
        self,
        collection_type: Optional[str] = None,
        limit: int = 20,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get popular tags across collections.
        
        Args:
            collection_type: Type of collection (None for all)
            limit: Maximum number of tags to return
            use_cache: Whether to use cache
            
        Returns:
            List of tags with counts
        """
        # Generate cache key
        cache_key = f"perplexity:tags:type={collection_type or 'all'}:limit={limit}"
        
        # Try to get from cache
        if use_cache:
            cached = await get_cache(cache_key)
            if cached:
                logger.debug(f"Retrieved {len(cached)} popular tags from cache")
                return cached
        
        # Determine collections to search
        if collection_type:
            collection_names = [self.collections.get(collection_type, self.collections["general"])]
        else:
            collection_names = list(self.collections.values())
        
        tag_counts = {}
        try:
            # Get tags from each collection
            for collection_name in collection_names:
                collection = get_collection(collection_name)
                
                # Aggregate tags
                pipeline = [
                    {"$unwind": "$tags"},
                    {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                    {"$limit": limit * 2}  # Get more than needed to account for combining
                ]
                
                cursor = collection.aggregate(pipeline)
                results = await cursor.to_list(length=limit * 2)
                
                # Combine results
                for result in results:
                    tag = result["_id"]
                    count = result["count"]
                    
                    if tag in tag_counts:
                        tag_counts[tag] += count
                    else:
                        tag_counts[tag] = count
            
            # Sort and limit
            popular_tags = [{"tag": tag, "count": count} for tag, count in tag_counts.items()]
            popular_tags.sort(key=lambda x: x["count"], reverse=True)
            popular_tags = popular_tags[:limit]
            
            # Cache results
            if use_cache:
                await set_cache(
                    cache_key,
                    popular_tags,
                    ttl=3600  # 1 hour
                )
            
            logger.debug(f"Retrieved {len(popular_tags)} popular tags from database")
            return popular_tags
            
        except Exception as e:
            logger.error(f"Error retrieving popular tags: {e}")
            return []
    
    async def get_collection_stats(
        self,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get statistics for all collections.
        
        Args:
            use_cache: Whether to use cache
            
        Returns:
            Dictionary of collection statistics
        """
        # Generate cache key
        cache_key = "perplexity:stats"
        
        # Try to get from cache
        if use_cache:
            cached = await get_cache(cache_key)
            if cached:
                logger.debug(f"Retrieved collection stats from cache")
                return cached
        
        stats = {}
        total_count = 0
        try:
            # Get stats for each collection
            for collection_type, collection_name in self.collections.items():
                collection = get_collection(collection_name)
                
                # Get count
                count = await collection.count_documents({})
                stats[collection_type] = {
                    "count": count,
                    "collection": collection_name
                }
                total_count += count
                
                # Get earliest and latest dates
                if count > 0:
                    latest = await collection.find_one(
                        {},
                        sort=[("created_at", -1)]
                    )
                    earliest = await collection.find_one(
                        {},
                        sort=[("created_at", 1)]
                    )
                    
                    stats[collection_type]["latest"] = latest.get("created_at") if latest else None
                    stats[collection_type]["earliest"] = earliest.get("created_at") if earliest else None
            
            # Add total
            stats["total"] = total_count
            
            # Cache results
            if use_cache:
                await set_cache(
                    cache_key,
                    stats,
                    ttl=3600  # 1 hour
                )
            
            logger.debug(f"Retrieved collection stats from database")
            return stats
            
        except Exception as e:
            logger.error(f"Error retrieving collection stats: {e}")
            return {"error": str(e)}
    
    def _generate_content_hash(self, item: Dict[str, Any]) -> str:
        """Generate a hash for content deduplication."""
        # Extract key fields for hashing
        hash_fields = {}
        
        # Include text or content
        if "text" in item:
            hash_fields["text"] = item["text"]
        elif "content" in item:
            hash_fields["content"] = item["content"]
        
        # Include headline if available
        if "headline" in item:
            hash_fields["headline"] = item["headline"]
        
        # Include date if available
        if "date" in item:
            hash_fields["date"] = item["date"]
        
        # Generate hash
        hash_str = json.dumps(hash_fields, sort_keys=True)
        return hashlib.md5(hash_str.encode()).hexdigest()


# Singleton instance
research_storage = ResearchStorage()


def get_research_storage() -> ResearchStorage:
    """
    Get the ResearchStorage instance.
    
    Returns:
        The ResearchStorage singleton
    """
    return research_storage 