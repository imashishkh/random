"""
Rate limiting middleware for the API.

This module provides a sliding window rate limiter using Redis
to enforce API usage limits based on user tiers.
"""
import time
import logging
from fastapi import Request, HTTPException, Depends
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from ...cache.redis_cache import get_redis_connection
from ...security.api_key import ApiKey, get_api_key
from ...config import settings

# Configure logger
logger = logging.getLogger(__name__)

class RateLimiter:
    """
    Sliding window rate limiter for API endpoints.
    
    Implements a Redis-based rate limiting mechanism with tier-based limits.
    """
    
    def __init__(
        self, 
        times: int = None, 
        seconds: int = None,
        tier_multiplier: dict = None
    ):
        """
        Initialize the rate limiter.
        
        Args:
            times: Number of requests allowed in the time window
            seconds: Time window in seconds
            tier_multiplier: Multiplier for different user tiers
        """
        self.times = times or settings.RATE_LIMIT_DEFAULT
        self.seconds = seconds or settings.RATE_LIMIT_WINDOW
        self.tier_multiplier = tier_multiplier or settings.RATE_LIMIT_TIERS
    
    async def __call__(self, request: Request, api_key: ApiKey = Depends(get_api_key)):
        """
        Check if the current request exceeds rate limits.
        
        Args:
            request: FastAPI request object
            api_key: API key object from authentication
            
        Returns:
            True if rate limit not exceeded
            
        Raises:
            HTTPException: If rate limit exceeded
        """
        # Get Redis client
        try:
            redis = await get_redis_connection()
            
            # Determine key and limits based on API key tier
            key = f"ratelimit:{api_key.key}"
            tier = getattr(api_key, 'tier', 'basic')
            limit = self.times * self.tier_multiplier.get(tier, 1)
            
            # Get current count and TTL
            pipe = redis.pipeline()
            pipe.get(key)
            pipe.ttl(key)
            count_result, ttl = await pipe.execute()
            
            # Convert results
            count = int(count_result) if count_result else 0
            ttl = max(0, ttl) if ttl > 0 else self.seconds
            
            # Check if limit exceeded
            if count >= limit:
                # Store rate limit info for headers
                request.state.rate_limit = {
                    "limit": limit,
                    "remaining": 0,
                    "reset": ttl
                }
                
                logger.warning(
                    f"Rate limit exceeded for API key: {api_key.key[-8:]} "
                    f"(tier: {tier}, limit: {limit})"
                )
                
                raise HTTPException(
                    status_code=HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Try again in {ttl} seconds."
                )
            
            # Increment counter
            pipe = redis.pipeline()
            pipe.incr(key)
            
            # Set expiry if not already set
            if ttl <= 0 or ttl == self.seconds:
                pipe.expire(key, self.seconds)
                
            await pipe.execute()
            
            # Store rate limit info for headers
            request.state.rate_limit = {
                "limit": limit,
                "remaining": limit - count - 1,
                "reset": ttl
            }
            
            return True
            
        except Exception as e:
            # If Redis fails, log but allow the request
            logger.error(f"Rate limiting error: {e}")
            return True

async def add_rate_limit_headers(request: Request, call_next):
    """
    Middleware to add rate limit headers to responses.
    
    Args:
        request: FastAPI request
        call_next: Next middleware in chain
        
    Returns:
        Response with rate limit headers
    """
    response = await call_next(request)
    
    # Add rate limit headers if available
    if hasattr(request.state, "rate_limit"):
        rate_limit = request.state.rate_limit
        response.headers["X-RateLimit-Limit"] = str(rate_limit["limit"])
        response.headers["X-RateLimit-Remaining"] = str(rate_limit["remaining"])
        response.headers["X-RateLimit-Reset"] = str(rate_limit["reset"])
    
    return response 