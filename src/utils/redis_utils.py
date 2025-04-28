"""
Redis utilities for caching and rate limiting.

This module provides:
1. Redis connection management
2. Caching decorators
3. Rate limiting functionality
"""
import json
import time
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar, Union, cast
from functools import wraps
from datetime import datetime, timedelta

import redis.asyncio as redis
from fastapi import Request, Response, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..config import settings

# Type definitions
T = TypeVar('T')
CacheableReturn = Union[Dict[str, Any], List[Dict[str, Any]], BaseModel]

# Configure logging
logger = logging.getLogger(__name__)

# Redis connection
redis_client: Optional[redis.Redis] = None

async def get_redis_client() -> redis.Redis:
    """Get or create Redis client."""
    global redis_client
    if redis_client is None:
        logger.info(f"Connecting to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=True
        )
    return redis_client

async def close_redis_connection():
    """Close Redis connection when application stops."""
    global redis_client
    if redis_client is not None:
        logger.info("Closing Redis connection")
        await redis_client.close()
        redis_client = None

# Caching utilities
def serialize_value(value: Any) -> str:
    """Serialize a value to a JSON string."""
    if isinstance(value, BaseModel):
        return value.json()
    return json.dumps(value)

def deserialize_value(value_str: str, expected_type: Optional[Type] = None) -> Any:
    """Deserialize a JSON string to the specified type."""
    try:
        data = json.loads(value_str)
        if expected_type and issubclass(expected_type, BaseModel):
            return expected_type.parse_obj(data)
        return data
    except Exception as e:
        logger.warning(f"Failed to deserialize value: {e}")
        return None

def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate a cache key based on function arguments."""
    # Filter out Request and Response objects
    filtered_kwargs = {k: v for k, v in kwargs.items() if not isinstance(v, (Request, Response))}
    
    # Handle datetime objects
    for k, v in filtered_kwargs.items():
        if isinstance(v, datetime):
            filtered_kwargs[k] = v.isoformat()
    
    args_str = '_'.join(str(arg) for arg in args if not isinstance(arg, (Request, Response)))
    kwargs_str = '_'.join(f"{k}:{v}" for k, v in sorted(filtered_kwargs.items()))
    
    key_parts = [prefix]
    if args_str:
        key_parts.append(args_str)
    if kwargs_str:
        key_parts.append(kwargs_str)
    
    return ':'.join(key_parts)

def cache(
    prefix: str, 
    ttl: int = 300,
    skip_kwargs: List[str] = None,
    expected_return_type: Optional[Type] = None
):
    """
    Cache decorator for async functions.
    
    Args:
        prefix: Prefix for cache key
        ttl: Time to live in seconds
        skip_kwargs: List of kwarg names to exclude from cache key
        expected_return_type: Expected return type for deserialization
    """
    skip_kwargs = skip_kwargs or []
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Skip caching if explicitly requested
            no_cache = kwargs.pop('no_cache', False)
            if no_cache:
                return await func(*args, **kwargs)
            
            # Filter out skipped kwargs for cache key
            key_kwargs = {k: v for k, v in kwargs.items() if k not in skip_kwargs}
            
            # Generate cache key
            cache_key = generate_cache_key(prefix, *args, **key_kwargs)
            
            # Get Redis client
            redis_conn = await get_redis_client()
            
            # Try to get from cache
            cached_value = await redis_conn.get(cache_key)
            
            if cached_value:
                logger.debug(f"Cache hit for key: {cache_key}")
                return deserialize_value(cached_value, expected_return_type)
            
            # If not in cache, call the function
            logger.debug(f"Cache miss for key: {cache_key}")
            result = await func(*args, **kwargs)
            
            if result is not None:
                # Store in cache
                try:
                    serialized = serialize_value(result)
                    await redis_conn.setex(cache_key, ttl, serialized)
                except Exception as e:
                    logger.warning(f"Failed to cache value for key {cache_key}: {e}")
            
            return result
        
        return wrapper
    
    return decorator

async def invalidate_cache(pattern: str):
    """Invalidate all cache keys matching the pattern."""
    redis_conn = await get_redis_client()
    keys = await redis_conn.keys(pattern)
    
    if keys:
        logger.info(f"Invalidating {len(keys)} cache keys matching pattern: {pattern}")
        await redis_conn.delete(*keys)

# Rate limiting utilities
class RateLimiter:
    """Rate limiter using Redis."""
    
    def __init__(
        self,
        limit: int = 100, 
        window: int = 60,
        user_identifier: Optional[Callable[[Request], str]] = None
    ):
        """
        Initialize rate limiter.
        
        Args:
            limit: Maximum number of requests in the window
            window: Time window in seconds
            user_identifier: Function to extract user identifier from request
        """
        self.limit = limit
        self.window = window
        self.user_identifier = user_identifier or self._default_user_identifier
    
    @staticmethod
    def _default_user_identifier(request: Request) -> str:
        """Default function to extract user identifier from request."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            ip = forwarded_for.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        
        # Use API key if available
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"{api_key}:{ip}"
        
        return ip
    
    async def is_rate_limited(self, request: Request) -> Tuple[bool, Dict[str, Union[int, str]]]:
        """
        Check if request is rate limited.
        
        Returns:
            Tuple of (is_limited, rate_limit_info)
        """
        redis_conn = await get_redis_client()
        
        # Get user identifier
        identifier = self.user_identifier(request)
        endpoint = request.url.path
        rate_key = f"ratelimit:{endpoint}:{identifier}"
        
        pipe = redis_conn.pipeline()
        now = int(time.time())
        window_start = now - self.window
        
        # Add current timestamp to sliding window
        await pipe.zadd(rate_key, {str(now): now})
        
        # Remove old timestamps outside the window
        await pipe.zremrangebyscore(rate_key, 0, window_start)
        
        # Count requests in current window
        await pipe.zcard(rate_key)
        
        # Set key expiration
        await pipe.expire(rate_key, self.window)
        
        # Execute pipeline
        _, _, request_count, _ = await pipe.execute()
        
        # Calculate time to reset
        reset_time = now + self.window
        
        # Determine if rate limited
        is_limited = request_count > self.limit
        
        # Rate limit headers
        headers = {
            "X-RateLimit-Limit": self.limit,
            "X-RateLimit-Remaining": max(0, self.limit - request_count),
            "X-RateLimit-Reset": reset_time
        }
        
        return is_limited, headers

    async def __call__(self, request: Request, response: Response):
        """
        Rate limiting dependency for FastAPI.
        
        Raises:
            HTTPException: If rate limit is exceeded
        """
        is_limited, headers = await self.is_rate_limited(request)
        
        # Add rate limit headers to response
        for key, value in headers.items():
            response.headers[key] = str(value)
        
        if is_limited:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later."
            )
        
        return True 