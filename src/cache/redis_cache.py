"""
Redis caching implementation for the analytics API.

This module provides Redis connection management and caching decorators
for optimizing performance of frequently accessed analytics data.
"""
from functools import wraps
import json
import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Callable

import aioredis
from ..config import settings

# Configure logger
logger = logging.getLogger(__name__)

# Redis connection singleton
_redis = None

async def get_redis_connection():
    """
    Get or create Redis connection.
    
    Returns:
        Redis connection instance
    """
    global _redis
    if _redis is None:
        try:
            _redis = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info(f"Connected to Redis at {settings.REDIS_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    return _redis

def generate_cache_key(prefix: str, **kwargs) -> str:
    """
    Generate a unique cache key from prefix and parameters.
    
    Args:
        prefix: Key prefix for the cache namespace
        **kwargs: Parameters to include in the key
        
    Returns:
        Formatted cache key
    """
    # Remove None values and any internal params
    clean_kwargs = {k: v for k, v in kwargs.items() 
                   if v is not None and not k.startswith('_')}
    
    # Normalize datetime objects
    for k, v in clean_kwargs.items():
        if isinstance(v, datetime):
            clean_kwargs[k] = v.isoformat()
    
    # Sort keys for consistent hashing
    param_str = json.dumps(clean_kwargs, sort_keys=True)
    key_hash = hashlib.md5(param_str.encode()).hexdigest()
    
    return f"{prefix}:{key_hash}"

def cache_result(ttl: int = 300, prefix: str = "analytics"):
    """
    Decorator to cache function results in Redis.
    
    Args:
        ttl: Time-to-live in seconds for cache entries
        prefix: Key prefix for the cache namespace
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            key = generate_cache_key(prefix, **kwargs)
            
            try:
                # Get Redis connection
                redis = await get_redis_connection()
                
                # Try to get from cache
                cached = await redis.get(key)
                
                if cached:
                    logger.debug(f"Cache hit for key: {key}")
                    return json.loads(cached)
                
                logger.debug(f"Cache miss for key: {key}")
                
                # Execute function if not cached
                result = await func(*args, **kwargs)
                
                # Cache the result
                await redis.set(
                    key,
                    json.dumps(result, default=str),
                    ex=ttl
                )
                
                return result
            except Exception as e:
                # If Redis fails, log the error but continue with the original function
                logger.error(f"Redis caching error: {e}")
                return await func(*args, **kwargs)
                
        return wrapper
    return decorator

async def invalidate_cache(prefix: str, **kwargs):
    """
    Invalidate specific cache entries by pattern.
    
    Args:
        prefix: Key prefix for the cache namespace
        **kwargs: Parameters used in the key (if any)
    """
    try:
        redis = await get_redis_connection()
        
        if kwargs:
            # Invalidate specific key
            key = generate_cache_key(prefix, **kwargs)
            await redis.delete(key)
            logger.debug(f"Invalidated specific cache key: {key}")
        else:
            # Invalidate all keys with this prefix
            pattern = f"{prefix}:*"
            cursor = "0"
            while cursor != 0:
                cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=1000)
                if keys:
                    await redis.delete(*keys)
                    logger.debug(f"Invalidated {len(keys)} cache keys with pattern: {pattern}")
                cursor = int(cursor)
    except Exception as e:
        logger.error(f"Failed to invalidate cache: {e}") 