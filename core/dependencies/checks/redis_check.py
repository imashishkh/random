"""
Redis dependency check for the Forex Trading system.

This module provides a dependency check that verifies connectivity and
basic functionality of the Redis instance used by the system.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
import redis.asyncio as redis_async
import redis as redis_sync

from core.dependencies.checker import DependencyCheck, CheckResult, CheckStatus
from core.config import ConfigManager


logger = logging.getLogger(__name__)


class RedisCheck(DependencyCheck):
    """
    Dependency check for Redis connection and functionality.
    
    This check verifies connectivity to the Redis server and validates
    basic operations such as set/get to ensure the Redis instance is
    functioning properly.
    """
    
    def __init__(self, config_manager: ConfigManager):
        """
        Initialize the Redis dependency check with configuration.
        
        Args:
            config_manager: The configuration manager containing Redis connection settings.
        """
        super().__init__(
            name="redis",
            description="Checks connectivity and functionality of Redis",
            dependencies=[],  # Redis typically doesn't depend on other services
            priority=1  # High priority as other services may depend on Redis
        )
        self.config_manager = config_manager
    
    def _get_redis_config(self) -> Dict[str, Any]:
        """
        Extract Redis configuration from the config manager.
        
        Returns:
            Dictionary containing Redis connection parameters.
        """
        redis_config = self.config_manager.get("redis", {})
        
        # Default Redis configuration if not specified
        default_config = {
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "password": None,
            "ssl": False,
            "timeout": 5
        }
        
        # Merge provided config with defaults
        for key, default_value in default_config.items():
            if key not in redis_config:
                redis_config[key] = default_value
                
        return redis_config
    
    def run(self) -> CheckResult:
        """
        Run the Redis check synchronously. This uses the synchronous Redis client.
        
        Returns:
            CheckResult: The result of the Redis connectivity check.
        """
        redis_config = self._get_redis_config()
        
        # Create a configuration without password for logging
        log_config = redis_config.copy()
        if "password" in log_config and log_config["password"]:
            log_config["password"] = "******"
        
        logger.debug(f"Checking Redis connection with config: {log_config}")
        
        # Create Redis client
        client = redis_sync.Redis(
            host=redis_config["host"],
            port=redis_config["port"],
            db=redis_config["db"],
            password=redis_config["password"],
            ssl=redis_config["ssl"],
            socket_timeout=redis_config["timeout"],
            socket_connect_timeout=redis_config["timeout"]
        )
        
        try:
            # Test simple connection
            pong = client.ping()
            if not pong:
                return CheckResult(
                    status=CheckStatus.FAILURE,
                    message="Redis server is reachable but ping failed",
                    details={"host": redis_config["host"], "port": redis_config["port"]}
                )
            
            # Test basic operations
            test_key = "forex:dependency:test"
            test_value = "redis_check_value"
            
            # Set a test value
            client.set(test_key, test_value)
            
            # Get the test value back
            fetched_value = client.get(test_key)
            
            # Clean up
            client.delete(test_key)
            
            # Verify fetched value
            if fetched_value and fetched_value.decode("utf-8") == test_value:
                return CheckResult(
                    status=CheckStatus.SUCCESS,
                    message="Redis connection successful and operations verified",
                    details={
                        "host": redis_config["host"],
                        "port": redis_config["port"],
                        "db": redis_config["db"],
                        "test_key": test_key
                    }
                )
            else:
                return CheckResult(
                    status=CheckStatus.FAILURE,
                    message="Redis SET/GET operations failed verification",
                    details={
                        "host": redis_config["host"],
                        "port": redis_config["port"],
                        "expected": test_value,
                        "received": fetched_value.decode("utf-8") if fetched_value else None
                    }
                )
                
        except redis_sync.ConnectionError as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"Redis connection error: {str(e)}",
                details={
                    "host": redis_config["host"],
                    "port": redis_config["port"],
                    "error": str(e)
                }
            )
        except redis_sync.RedisError as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"Redis error: {str(e)}",
                details={"error": str(e)}
            )
        except Exception as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"Unexpected error checking Redis: {str(e)}",
                details={"error": str(e)}
            )
        finally:
            # Close the connection
            client.close()
    
    async def run_async(self) -> CheckResult:
        """
        Run the Redis dependency check asynchronously using the async Redis client.
        
        Returns:
            CheckResult: The result of the Redis connectivity check.
        """
        redis_config = self._get_redis_config()
        
        # Create a configuration without password for logging
        log_config = redis_config.copy()
        if "password" in log_config and log_config["password"]:
            log_config["password"] = "******"
        
        logger.debug(f"Checking Redis connection asynchronously with config: {log_config}")
        
        # Create Redis client
        client = redis_async.Redis(
            host=redis_config["host"],
            port=redis_config["port"],
            db=redis_config["db"],
            password=redis_config["password"],
            ssl=redis_config["ssl"],
            socket_timeout=redis_config["timeout"],
            socket_connect_timeout=redis_config["timeout"]
        )
        
        try:
            # Test simple connection
            pong = await client.ping()
            if not pong:
                return CheckResult(
                    status=CheckStatus.FAILURE,
                    message="Redis server is reachable but ping failed",
                    details={"host": redis_config["host"], "port": redis_config["port"]}
                )
            
            # Test basic operations
            test_key = "forex:dependency:test"
            test_value = "redis_check_value"
            
            # Test operation with pipeline
            pipeline = client.pipeline()
            pipeline.set(test_key, test_value)
            pipeline.get(test_key)
            pipeline.delete(test_key)
            
            # Execute pipeline
            results = await pipeline.execute()
            
            # Verify pipeline results
            if len(results) >= 2 and results[1] and results[1].decode("utf-8") == test_value:
                return CheckResult(
                    status=CheckStatus.SUCCESS,
                    message="Redis connection successful and operations verified",
                    details={
                        "host": redis_config["host"],
                        "port": redis_config["port"],
                        "db": redis_config["db"],
                        "pipeline_operations": "SET, GET, DEL",
                        "test_key": test_key
                    }
                )
            else:
                return CheckResult(
                    status=CheckStatus.FAILURE,
                    message="Redis pipeline operations failed verification",
                    details={
                        "host": redis_config["host"],
                        "port": redis_config["port"],
                        "expected": test_value,
                        "pipeline_results": results
                    }
                )
                
        except redis_async.ConnectionError as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"Redis connection error: {str(e)}",
                details={
                    "host": redis_config["host"],
                    "port": redis_config["port"],
                    "error": str(e)
                }
            )
        except redis_async.RedisError as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"Redis error: {str(e)}",
                details={"error": str(e)}
            )
        except Exception as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"Unexpected error checking Redis: {str(e)}",
                details={"error": str(e)}
            )
        finally:
            # Close the connection
            await client.close() 