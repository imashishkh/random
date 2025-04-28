"""
Technical indicator calculator with multi-level caching.
"""

import logging
import time
import hashlib
import json
import pickle
import os
from typing import Dict, Any, Optional, Union, Tuple, List
import pandas as pd
import numpy as np

from .factory import IndicatorFactory
from ..cache.redis_client import RedisClient

# Set up logging
logger = logging.getLogger(__name__)

class IndicatorCalculator:
    """
    Calculator for technical indicators with multi-level caching.
    
    Implements a calculation engine for technical indicators that uses
    a multi-level caching strategy to improve performance:
    
    - L1 Cache: Redis (in-memory, fast access)
    - L2 Cache: Local disk (slower, but persistent)
    - L3 Cache: Database (for long-term storage)
    """
    
    def __init__(self, 
                 redis_client: Optional[RedisClient] = None,
                 disk_cache_dir: str = "/app/cache/indicators",
                 cache_ttl: int = 3600,
                 enable_logging: bool = True):
        """
        Initialize the indicator calculator.
        
        Args:
            redis_client: Redis client for L1 cache
            disk_cache_dir: Directory for L2 disk cache
            cache_ttl: TTL for cached values in seconds (default: 1 hour)
            enable_logging: Whether to enable logging (default: True)
        """
        self.redis_client = redis_client
        self.disk_cache_dir = disk_cache_dir
        self.cache_ttl = cache_ttl
        self.enable_logging = enable_logging
        
        # Create disk cache directory if it doesn't exist
        if not os.path.exists(self.disk_cache_dir):
            os.makedirs(self.disk_cache_dir, exist_ok=True)
        
        logger.info(f"Initialized IndicatorCalculator with {len(IndicatorFactory.list_indicators())} indicators")
    
    def calculate(self, 
                  indicator_name: str,
                  data: pd.DataFrame,
                  params: Dict[str, Any] = None,
                  use_cache: bool = True,
                  refresh_cache: bool = False,
                  metadata: Dict[str, Any] = None) -> Union[pd.Series, Dict[str, pd.Series], None]:
        """
        Calculate a technical indicator with caching support.
        
        Args:
            indicator_name: Name of the indicator to calculate
            data: DataFrame with market data
            params: Parameters for the indicator calculation
            use_cache: Whether to use cache (default: True)
            refresh_cache: Force refresh of cache (default: False)
            metadata: Additional metadata to store with the result
            
        Returns:
            The calculated indicator value(s) or None if calculation failed
        """
        params = params or {}
        metadata = metadata or {}
        
        # Generate cache key
        cache_key = self._generate_cache_key(indicator_name, data, params, metadata)
        
        # If using cache and not forcing refresh, try to get from cache
        if use_cache and not refresh_cache:
            cached_result = self._get_from_cache(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {indicator_name} with key {cache_key[:8]}")
                return cached_result
        
        # Get indicator function from factory
        indicator_func = IndicatorFactory.get(indicator_name)
        if not indicator_func:
            logger.error(f"Indicator {indicator_name} not found")
            return None
        
        # Calculate indicator
        try:
            start_time = time.time()
            result = indicator_func(data, **params)
            calculation_time = time.time() - start_time
            
            logger.debug(f"Calculated {indicator_name} in {calculation_time:.2f}s")
            
            # Store in cache if enabled
            if use_cache:
                cache_metadata = {
                    **metadata,
                    'calculation_time': calculation_time,
                    'calculated_at': time.time(),
                    'params': params,
                    'indicator': indicator_name,
                    'data_points': len(data),
                    'start_date': data.index[0].isoformat() if len(data) > 0 else None,
                    'end_date': data.index[-1].isoformat() if len(data) > 0 else None
                }
                
                self._store_in_cache(cache_key, result, cache_metadata)
            
            return result
            
        except Exception as e:
            logger.exception(f"Error calculating {indicator_name}: {e}")
            return None
    
    def batch_calculate(self, 
                        indicators: List[Dict[str, Any]],
                        data: pd.DataFrame,
                        use_cache: bool = True,
                        refresh_cache: bool = False) -> Dict[str, Any]:
        """
        Calculate multiple indicators in batch.
        
        Args:
            indicators: List of indicator configs with 'name' and 'params'
            data: DataFrame with market data
            use_cache: Whether to use cache
            refresh_cache: Force refresh of cache
            
        Returns:
            Dictionary of indicator results
        """
        results = {}
        
        for ind_config in indicators:
            name = ind_config['name']
            params = ind_config.get('params', {})
            
            result = self.calculate(
                name, 
                data, 
                params, 
                use_cache=use_cache,
                refresh_cache=refresh_cache
            )
            
            results[name] = result
        
        return results
    
    def _generate_cache_key(self, 
                           indicator_name: str,
                           data: pd.DataFrame,
                           params: Dict[str, Any],
                           metadata: Dict[str, Any] = None) -> str:
        """
        Generate a cache key for the indicator calculation.
        
        The key includes the indicator name, parameters, and information
        about the data (symbol, timeframe, start/end times).
        
        Args:
            indicator_name: Name of the indicator
            data: Market data DataFrame
            params: Calculation parameters
            metadata: Additional metadata
            
        Returns:
            Cache key string
        """
        # Extract metadata from DataFrame if possible
        symbol = metadata.get('symbol', getattr(data, 'symbol', 'unknown'))
        timeframe = metadata.get('timeframe', getattr(data, 'timeframe', 'unknown'))
        
        # Get data range
        if len(data) > 0:
            start_date = data.index[0].isoformat()
            end_date = data.index[-1].isoformat()
        else:
            start_date = "empty"
            end_date = "empty"
        
        # Create key components
        key_parts = {
            'indicator': indicator_name.upper(),
            'symbol': symbol,
            'timeframe': timeframe,
            'start': start_date,
            'end': end_date,
            'params': params,
            'data_len': len(data)
        }
        
        # Create key as hash of serialized parts
        key_str = json.dumps(key_parts, sort_keys=True)
        key_hash = hashlib.md5(key_str.encode()).hexdigest()
        
        return f"indicator:{indicator_name.lower()}:{symbol}:{timeframe}:{key_hash}"
    
    def _get_from_cache(self, key: str) -> Optional[Union[pd.Series, Dict[str, pd.Series]]]:
        """
        Get a value from the multi-level cache.
        
        Tries L1 (Redis) first, then L2 (disk), then will add L3 (DB) in the future.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        # Try L1 cache (Redis)
        if self.redis_client:
            try:
                redis_result = self.redis_client.get(key)
                if redis_result:
                    return pickle.loads(redis_result)
            except Exception as e:
                logger.warning(f"Error accessing Redis cache: {e}")
        
        # Try L2 cache (disk)
        try:
            disk_path = os.path.join(self.disk_cache_dir, hashlib.md5(key.encode()).hexdigest())
            if os.path.exists(disk_path):
                with open(disk_path, 'rb') as f:
                    result = pickle.load(f)
                    
                    # Refresh L1 cache if available
                    if self.redis_client:
                        self.redis_client.setex(key, self.cache_ttl, pickle.dumps(result))
                    
                    return result
        except Exception as e:
            logger.warning(f"Error accessing disk cache: {e}")
        
        # L3 cache (DB) will go here in future implementation
        
        return None
    
    def _store_in_cache(self, 
                       key: str, 
                       value: Union[pd.Series, Dict[str, pd.Series]],
                       metadata: Dict[str, Any] = None) -> None:
        """
        Store a value in the multi-level cache.
        
        Stores in L1 (Redis) and L2 (disk) caches.
        
        Args:
            key: Cache key
            value: Value to store
            metadata: Additional metadata
        """
        try:
            serialized = pickle.dumps(value)
            
            # Store in L1 cache (Redis)
            if self.redis_client:
                self.redis_client.setex(key, self.cache_ttl, serialized)
            
            # Store in L2 cache (disk)
            disk_path = os.path.join(self.disk_cache_dir, hashlib.md5(key.encode()).hexdigest())
            with open(disk_path, 'wb') as f:
                pickle.dump(value, f)
            
            # Store metadata for cache management
            if metadata:
                meta_key = f"{key}:meta"
                meta_path = f"{disk_path}.meta"
                
                if self.redis_client:
                    self.redis_client.setex(meta_key, self.cache_ttl, json.dumps(metadata))
                
                with open(meta_path, 'w') as f:
                    json.dump(metadata, f)
            
        except Exception as e:
            logger.warning(f"Error storing in cache: {e}")
    
    def invalidate_cache(self, pattern: str = "*") -> int:
        """
        Invalidate cache entries matching a pattern.
        
        Args:
            pattern: Redis key pattern to match (default: all indicator keys)
            
        Returns:
            Number of invalidated cache entries
        """
        count = 0
        
        # Invalidate L1 cache (Redis)
        if self.redis_client:
            try:
                keys = self.redis_client.keys(f"indicator:{pattern}")
                if keys:
                    count += len(keys)
                    self.redis_client.delete(*keys)
            except Exception as e:
                logger.warning(f"Error invalidating Redis cache: {e}")
        
        # Invalidate L2 cache (disk)
        try:
            if pattern == "*":
                # Clear all disk cache
                for filename in os.listdir(self.disk_cache_dir):
                    file_path = os.path.join(self.disk_cache_dir, filename)
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                        count += 1
            else:
                # Only clear matching pattern (would need metadata lookup)
                # For simplicity, not implemented in this version
                pass
                
        except Exception as e:
            logger.warning(f"Error invalidating disk cache: {e}")
        
        logger.info(f"Invalidated {count} cache entries")
        return count 