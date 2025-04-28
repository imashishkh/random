"""
Redis Connection Manager

This module provides a connection manager for Redis that handles connection pooling,
automatic reconnection, and error handling.
"""

import os
import redis
from redis.connection import BlockingConnectionPool
import logging
import time
from typing import Optional

# Import logger from project utilities
from ...utils.logging.logger import get_logger

logger = get_logger()

class RedisConnectionManager:
    """
    Manages Redis connections with connection pooling and automatic reconnection.
    
    This class provides a robust connection management system for Redis, including:
    - Connection pooling for efficiency
    - Automatic reconnection on failure
    - Health checking
    - Error handling
    
    It serves as the foundation for the Redis-based communication system.
    """
    
    def __init__(
        self,
        host: str = os.environ.get("REDIS_HOST", "localhost"),
        port: int = int(os.environ.get("REDIS_PORT", 6379)),
        password: Optional[str] = os.environ.get("REDIS_PASSWORD", None),
        db: int = int(os.environ.get("REDIS_DB", 0)),
        max_connections: int = 10,
        socket_timeout: int = 5,
        retry_on_timeout: bool = True,
        health_check_interval: int = 30
    ):
        """
        Initialize the Redis connection manager.
        
        Args:
            host: Redis server hostname
            port: Redis server port
            password: Redis password (optional)
            db: Redis database number
            max_connections: Maximum number of connections in the pool
            socket_timeout: Socket timeout in seconds
            retry_on_timeout: Whether to retry on timeout
            health_check_interval: Health check interval in seconds
        """
        self.connection_params = {
            "host": host,
            "port": port,
            "password": password,
            "db": db,
            "decode_responses": True,  # Automatically decode responses to strings
            "socket_timeout": socket_timeout,
            "retry_on_timeout": retry_on_timeout,
            "health_check_interval": health_check_interval
        }
        
        logger.info(f"Initializing Redis connection manager for {host}:{port}")
        
        # Create a connection pool with blocking behavior
        self.pool = BlockingConnectionPool(
            max_connections=max_connections,
            timeout=20,  # Maximum wait time for connection from pool
            **self.connection_params
        )
        
        # Test connection during initialization
        self._test_connection()
        
    def _test_connection(self, max_retries: int = 3, retry_delay: int = 2) -> None:
        """
        Test the Redis connection with retry logic.
        
        Args:
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            
        Raises:
            redis.RedisError: If connection fails after all retries
        """
        client = None
        for attempt in range(max_retries):
            try:
                client = redis.Redis(connection_pool=self.pool)
                client.ping()
                logger.info("Successfully connected to Redis")
                return
            except redis.RedisError as e:
                logger.warning(f"Redis connection attempt {attempt+1}/{max_retries} failed: {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Failed to connect to Redis after multiple attempts")
                    raise
            finally:
                if client:
                    # Don't actually close the connection, just return it to the pool
                    pass
    
    def get_connection(self) -> redis.Redis:
        """
        Get a Redis connection from the pool.
        
        Returns:
            Redis client instance
        """
        return redis.Redis(connection_pool=self.pool)
    
    def close(self) -> None:
        """Close the connection pool."""
        self.pool.disconnect()
        logger.info("Redis connection pool closed") 