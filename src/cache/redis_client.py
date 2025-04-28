"""
Redis client module for the Forex Trading AI System.
Provides functionality for caching and data retrieval.
"""
import os
import json
import logging
from typing import Any, Dict, List, Optional, Union
import time

import redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)

# Redis connection parameters from environment variables
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_SSL = os.getenv("REDIS_SSL", "False").lower() == "true"

# Default TTL for cached items (in seconds)
DEFAULT_TTL = int(os.getenv("REDIS_DEFAULT_TTL", "3600"))  # 1 hour

# Initialize Redis client
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        ssl=REDIS_SSL,
        decode_responses=True
    )
    # Test connection
    redis_client.ping()
    logger.info(f"Redis connection established to {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    logger.error(f"Error connecting to Redis: {e}")
    redis_client = None


def get_redis_client() -> redis.Redis:
    """
    Get the Redis client instance.
    
    Returns:
        redis.Redis: Redis client
    
    Raises:
        Exception: If Redis client is not initialized
    """
    if redis_client is None:
        raise Exception("Redis client not initialized")
    return redis_client


def set_cache(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """
    Set a value in the cache.
    
    Args:
        key: Cache key
        value: Value to cache (will be JSON serialized)
        ttl: Time to live in seconds (None for no expiry)
    
    Returns:
        bool: True if successful, False otherwise
    """
    if redis_client is None:
        logger.warning("Redis client not initialized, skipping cache set")
        return False
    
    try:
        serialized_value = json.dumps(value)
        if ttl is None:
            ttl = DEFAULT_TTL
        
        redis_client.set(key, serialized_value, ex=ttl)
        return True
    except Exception as e:
        logger.error(f"Error setting cache value for key '{key}': {e}")
        return False


def get_cache(key: str) -> Optional[Any]:
    """
    Get a value from the cache.
    
    Args:
        key: Cache key
    
    Returns:
        Cached value or None if not found
    """
    if redis_client is None:
        logger.warning("Redis client not initialized, skipping cache get")
        return None
    
    try:
        value = redis_client.get(key)
        if value is None:
            return None
        
        return json.loads(value)
    except Exception as e:
        logger.error(f"Error getting cache value for key '{key}': {e}")
        return None


def delete_cache(key: str) -> bool:
    """
    Delete a value from the cache.
    
    Args:
        key: Cache key
    
    Returns:
        bool: True if successful, False otherwise
    """
    if redis_client is None:
        logger.warning("Redis client not initialized, skipping cache delete")
        return False
    
    try:
        redis_client.delete(key)
        return True
    except Exception as e:
        logger.error(f"Error deleting cache key '{key}': {e}")
        return False


def flush_all() -> bool:
    """
    Flush all keys from the current database.
    
    Returns:
        bool: True if successful, False otherwise
    """
    if redis_client is None:
        logger.warning("Redis client not initialized, skipping flush")
        return False
    
    try:
        redis_client.flushdb()
        logger.info("Redis cache flushed")
        return True
    except Exception as e:
        logger.error(f"Error flushing Redis cache: {e}")
        return False


def get_pattern(pattern: str) -> Dict[str, Any]:
    """
    Get all keys matching a pattern and their values.
    
    Args:
        pattern: Redis key pattern (e.g., "user:*")
    
    Returns:
        Dictionary of keys and values
    """
    if redis_client is None:
        logger.warning("Redis client not initialized, skipping pattern get")
        return {}
    
    try:
        keys = redis_client.keys(pattern)
        result = {}
        
        for key in keys:
            value = get_cache(key)
            if value is not None:
                result[key] = value
        
        return result
    except Exception as e:
        logger.error(f"Error getting keys for pattern '{pattern}': {e}")
        return {}


def delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching a pattern.
    
    Args:
        pattern: Redis key pattern (e.g., "user:*")
    
    Returns:
        Number of keys deleted
    """
    if redis_client is None:
        logger.warning("Redis client not initialized, skipping pattern delete")
        return 0
    
    try:
        keys = redis_client.keys(pattern)
        if not keys:
            return 0
        
        deleted = redis_client.delete(*keys)
        return deleted
    except Exception as e:
        logger.error(f"Error deleting keys for pattern '{pattern}': {e}")
        return 0


def set_list(key: str, values: List[Any], ttl: Optional[int] = None) -> bool:
    """
    Set a list in the cache.
    
    Args:
        key: Cache key
        values: List of values
        ttl: Time to live in seconds (None for no expiry)
    
    Returns:
        bool: True if successful, False otherwise
    """
    return set_cache(key, values, ttl)


def get_list(key: str) -> List[Any]:
    """
    Get a list from the cache.
    
    Args:
        key: Cache key
    
    Returns:
        List of values or empty list if not found
    """
    result = get_cache(key)
    if result is None or not isinstance(result, list):
        return []
    return result


def set_hash(key: str, hash_dict: Dict[str, Any], ttl: Optional[int] = None) -> bool:
    """
    Set a hash in the cache.
    
    Args:
        key: Cache key
        hash_dict: Dictionary to store
        ttl: Time to live in seconds (None for no expiry)
    
    Returns:
        bool: True if successful, False otherwise
    """
    return set_cache(key, hash_dict, ttl)


def get_hash(key: str) -> Dict[str, Any]:
    """
    Get a hash from the cache.
    
    Args:
        key: Cache key
    
    Returns:
        Dictionary of values or empty dict if not found
    """
    result = get_cache(key)
    if result is None or not isinstance(result, dict):
        return {}
    return result


def increment(key: str, amount: int = 1) -> Optional[int]:
    """
    Increment a counter in the cache.
    
    Args:
        key: Cache key
        amount: Amount to increment by
    
    Returns:
        New value or None if failed
    """
    if redis_client is None:
        logger.warning("Redis client not initialized, skipping increment")
        return None
    
    try:
        return redis_client.incrby(key, amount)
    except Exception as e:
        logger.error(f"Error incrementing key '{key}': {e}")
        return None


def set_key_expiry(key: str, ttl: int) -> bool:
    """
    Set expiry for a key.
    
    Args:
        key: Cache key
        ttl: Time to live in seconds
    
    Returns:
        bool: True if successful, False otherwise
    """
    if redis_client is None:
        logger.warning("Redis client not initialized, skipping expiry set")
        return False
    
    try:
        return redis_client.expire(key, ttl)
    except Exception as e:
        logger.error(f"Error setting expiry for key '{key}': {e}")
        return False


def get_ttl(key: str) -> Optional[int]:
    """
    Get the remaining time to live for a key.
    
    Args:
        key: Cache key
    
    Returns:
        TTL in seconds or None if key does not exist or has no expiry
    """
    if redis_client is None:
        logger.warning("Redis client not initialized, skipping TTL get")
        return None
    
    try:
        ttl = redis_client.ttl(key)
        return ttl if ttl > 0 else None
    except Exception as e:
        logger.error(f"Error getting TTL for key '{key}': {e}")
        return None


def acquire_lock(key: str, ttl: int = 60) -> bool:
    """
    Acquire a distributed lock.
    
    Args:
        key: Lock key name
        ttl: Lock timeout in seconds
    
    Returns:
        bool: True if lock acquired, False otherwise
    """
    if redis_client is None:
        logger.warning("Redis client not initialized, skipping lock acquisition")
        return False
    
    lock_key = f"lock:{key}"
    try:
        # Use NX option to only set if the key does not already exist
        result = redis_client.set(lock_key, "1", ex=ttl, nx=True)
        return result is True
    except Exception as e:
        logger.error(f"Error acquiring lock '{key}': {e}")
        return False


def release_lock(key: str) -> bool:
    """
    Release a distributed lock.
    
    Args:
        key: Lock key name
    
    Returns:
        bool: True if lock released, False otherwise
    """
    lock_key = f"lock:{key}"
    return delete_cache(lock_key)


def get_cache_stats() -> Dict[str, Union[int, str]]:
    """
    Get Redis cache statistics.
    
    Returns:
        Dictionary with cache statistics
    """
    if redis_client is None:
        logger.warning("Redis client not initialized, skipping stats")
        return {"status": "disconnected"}
    
    try:
        info = redis_client.info()
        
        stats = {
            "status": "connected",
            "used_memory": info.get("used_memory_human", "unknown"),
            "connected_clients": info.get("connected_clients", 0),
            "uptime_days": round(info.get("uptime_in_seconds", 0) / 86400, 2),
            "total_keys": 0,
            "hit_rate": 0,
        }
        
        # Get total keys in current DB
        keys_in_db = info.get(f"db{REDIS_DB}", {})
        if keys_in_db:
            keys_count = keys_in_db.get("keys", 0)
            stats["total_keys"] = keys_count
        
        # Calculate hit rate
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses
        if total > 0:
            stats["hit_rate"] = round((hits / total) * 100, 2)
        
        return stats
    except Exception as e:
        logger.error(f"Error getting Redis stats: {e}")
        return {"status": "error", "message": str(e)} 