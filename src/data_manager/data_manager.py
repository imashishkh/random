"""
Data Manager Module

This module contains the DataManager class which coordinates data fetching
and preprocessing across multiple data sources.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Tuple

import pandas as pd

from .data_source import DataSourceAdapter, DataSourceFactory
from .preprocessor import DataPreprocessor, PreprocessorFactory
from ..cache.redis_client import get_cache, set_cache, delete_pattern

# Configure logger
logger = logging.getLogger(__name__)


class DataManager:
    """
    Central manager for data fetching and preprocessing operations.
    
    Coordinates interactions between data sources and preprocessors,
    with caching and error handling.
    """
    
    def __init__(
        self,
        source_factory: Optional[DataSourceFactory] = None,
        preprocessor_factory: Optional[PreprocessorFactory] = None,
        default_source_type: str = 'ccxt',
        default_exchange: str = 'binance',
        default_cache_ttl: int = 3600,
        use_fallbacks: bool = True
    ):
        """
        Initialize the DataManager.
        
        Args:
            source_factory: Optional factory for creating data sources
            preprocessor_factory: Optional factory for creating preprocessors
            default_source_type: Default data source type ('ccxt', 'yfinance', etc.)
            default_exchange: Default exchange when using ccxt
            default_cache_ttl: Default cache TTL in seconds
            use_fallbacks: Whether to try fallback data sources on failure
        """
        self.source_factory = source_factory or DataSourceFactory()
        self.preprocessor_factory = preprocessor_factory or PreprocessorFactory()
        self.default_source_type = default_source_type
        self.default_exchange = default_exchange
        self.default_cache_ttl = default_cache_ttl
        self.use_fallbacks = use_fallbacks
        
        # Cache configuration
        self.cache_prefix = "data_manager:"
        
        # Configure sources
        self._configure_sources()
        
        # Configure preprocessors
        self._configure_preprocessors()
    
    def _configure_sources(self):
        """
        Configure and initialize data sources.
        """
        # Set up source configurations with appropriate API keys
        self.source_configs = {
            'ccxt': {
                'exchange_id': self.default_exchange,
                'api_key': os.getenv(f"{self.default_exchange.upper()}_API_KEY"),
                'api_secret': os.getenv(f"{self.default_exchange.upper()}_API_SECRET"),
                'cache_ttl': self.default_cache_ttl
            },
            'yfinance': {
                'cache_ttl': self.default_cache_ttl
            },
            'alpha_vantage': {
                'api_key': os.getenv("ALPHA_VANTAGE_API_KEY"),
                'cache_ttl': self.default_cache_ttl
            },
            'news_api': {
                'api_key': os.getenv("NEWS_API_KEY"),
                'cache_ttl': 1800  # 30 minutes for news
            },
            'fred': {
                'api_key': os.getenv("FRED_API_KEY"),
                'cache_ttl': 86400  # 1 day for economic indicators
            }
        }
        
        # Define fallback chains for different data types
        self.fallback_chains = {
            'market_data': ['ccxt', 'yfinance', 'alpha_vantage'],
            'fundamental_data': ['yfinance', 'alpha_vantage'],
            'news': ['news_api'],
            'economic': ['fred']
        }
    
    def _configure_preprocessors(self):
        """
        Configure data preprocessors.
        """
        # Set up preprocessor configurations
        self.preprocessor_configs = {
            'technical': {
                'indicators': ['sma', 'ema', 'rsi', 'macd', 'bbands', 'atr'],
                'fill_method': 'ffill',
                'normalize': True,
                'normalization_method': 'minmax',
                'scaling_window': None,
                'outlier_std_threshold': 3.0
            },
            'fundamental': {
                'fill_method': 'ffill',
                'normalize': True,
                'calculate_ratios': True
            },
            'news': {
                'perform_sentiment': True,
                'summarize': True,
                'extract_entities': True
            },
            'economic': {
                'fill_method': 'interpolate',
                'normalize': True,
                'handle_seasonality': True
            }
        }
    
    def _get_source(self, source_type: str) -> DataSourceAdapter:
        """
        Get a configured data source adapter.
        
        Args:
            source_type: Type of data source
            
        Returns:
            Configured data source adapter
        """
        config = self.source_configs.get(source_type, {})
        return self.source_factory.get_adapter(source_type, **config)
    
    def _get_preprocessor(self, preprocessor_type: str) -> DataPreprocessor:
        """
        Get a configured data preprocessor.
        
        Args:
            preprocessor_type: Type of preprocessor
            
        Returns:
            Configured data preprocessor
        """
        config = self.preprocessor_configs.get(preprocessor_type, {})
        return self.preprocessor_factory.get_preprocessor(preprocessor_type, **config)
    
    def _get_cache_key(self, operation: str, params: Dict[str, Any]) -> str:
        """
        Generate a standardized cache key.
        
        Args:
            operation: Operation name
            params: Operation parameters
            
        Returns:
            Formatted cache key
        """
        # Sort params for consistent keys regardless of dict order
        sorted_params = sorted(
            (k, str(v)) for k, v in params.items() 
            if v is not None and k != 'preprocess'
        )
        param_str = "_".join(f"{k}:{v}" for k, v in sorted_params)
        return f"{self.cache_prefix}{operation}:{param_str}"
    
    async def get_market_data(
        self,
        symbol: str,
        timeframe: str = '1h',
        limit: int = 1000,
        since: Optional[Union[datetime, int]] = None,
        source_type: Optional[str] = None,
        preprocess: bool = True,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Get market OHLCV data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe for the data
            limit: Maximum number of candles
            since: Start time
            source_type: Data source type (ccxt, yfinance, etc.)
            preprocess: Whether to preprocess the data
            use_cache: Whether to use cache
            
        Returns:
            DataFrame with market data
        """
        # Use default source if not specified
        source_type = source_type or self.default_source_type
        
        # Check cache first if enabled
        if use_cache:
            cache_key = self._get_cache_key('market_data', {
                'symbol': symbol,
                'timeframe': timeframe,
                'limit': limit,
                'since': since.isoformat() if isinstance(since, datetime) else since,
                'source_type': source_type
            })
            
            cached_data = get_cache(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for {cache_key}")
                df = pd.DataFrame(
                    data=cached_data.get('data', []),
                    index=pd.to_datetime(cached_data.get('index', [])),
                    columns=cached_data.get('columns', [])
                )
                return df
        
        # Try primary source
        try:
            source = self._get_source(source_type)
            df = await source.fetch_ohlcv(symbol, timeframe, limit, since)
            
            # Preprocess if requested
            if preprocess:
                preprocessor = self._get_preprocessor('technical')
                df = preprocessor.process(df)
            
            # Cache the result if enabled
            if use_cache:
                cache_data = df.to_dict(orient='split')
                set_cache(cache_key, cache_data, self.source_configs[source_type]['cache_ttl'])
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching market data from {source_type}: {str(e)}")
            
            # Try fallbacks if enabled
            if self.use_fallbacks:
                fallbacks = [s for s in self.fallback_chains['market_data'] if s != source_type]
                
                for fallback_source in fallbacks:
                    try:
                        logger.info(f"Trying fallback source {fallback_source} for market data")
                        source = self._get_source(fallback_source)
                        df = await source.fetch_ohlcv(symbol, timeframe, limit, since)
                        
                        # Preprocess if requested
                        if preprocess:
                            preprocessor = self._get_preprocessor('technical')
                            df = preprocessor.process(df)
                        
                        # Cache the successful fallback result
                        if use_cache:
                            cache_data = df.to_dict(orient='split')
                            set_cache(cache_key, cache_data, self.source_configs[fallback_source]['cache_ttl'])
                        
                        return df
                        
                    except Exception as fallback_error:
                        logger.error(f"Error fetching market data from fallback {fallback_source}: {str(fallback_error)}")
            
            # If we get here, all sources failed
            raise RuntimeError(f"Failed to fetch market data for {symbol} from all sources")
    
    async def get_fundamental_data(
        self,
        symbol: str,
        data_type: str = 'info',
        source_type: Optional[str] = None,
        preprocess: bool = True,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get fundamental data for a symbol.
        
        Args:
            symbol: Trading pair or stock symbol
            data_type: Type of fundamental data
            source_type: Data source type
            preprocess: Whether to preprocess the data
            use_cache: Whether to use cache
            
        Returns:
            Dictionary with fundamental data
        """
        # Select appropriate source type for fundamental data
        if not source_type:
            source_type = 'yfinance'  # Default for fundamental data
        
        # Check cache first if enabled
        if use_cache:
            cache_key = self._get_cache_key('fundamental_data', {
                'symbol': symbol,
                'data_type': data_type,
                'source_type': source_type
            })
            
            cached_data = get_cache(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_data
        
        # Try primary source
        try:
            source = self._get_source(source_type)
            data = await source.fetch_fundamental_data(symbol, data_type)
            
            # Preprocess if requested
            if preprocess:
                preprocessor = self._get_preprocessor('fundamental')
                data = preprocessor.process(data)
            
            # Cache the result if enabled
            if use_cache:
                set_cache(cache_key, data, self.source_configs[source_type]['cache_ttl'])
            
            return data
            
        except Exception as e:
            logger.error(f"Error fetching fundamental data from {source_type}: {str(e)}")
            
            # Try fallbacks if enabled
            if self.use_fallbacks:
                fallbacks = [s for s in self.fallback_chains['fundamental_data'] if s != source_type]
                
                for fallback_source in fallbacks:
                    try:
                        logger.info(f"Trying fallback source {fallback_source} for fundamental data")
                        source = self._get_source(fallback_source)
                        data = await source.fetch_fundamental_data(symbol, data_type)
                        
                        # Preprocess if requested
                        if preprocess:
                            preprocessor = self._get_preprocessor('fundamental')
                            data = preprocessor.process(data)
                        
                        # Cache the successful fallback result
                        if use_cache:
                            set_cache(cache_key, data, self.source_configs[fallback_source]['cache_ttl'])
                        
                        return data
                        
                    except Exception as fallback_error:
                        logger.error(f"Error fetching fundamental data from fallback {fallback_source}: {str(fallback_error)}")
            
            # If we get here, all sources failed
            raise RuntimeError(f"Failed to fetch fundamental data for {symbol} from all sources")
    
    async def get_news(
        self,
        keywords: List[str],
        limit: int = 10,
        days: int = 1,
        source_type: Optional[str] = None,
        preprocess: bool = True,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get news articles related to keywords.
        
        Args:
            keywords: List of keywords to search for
            limit: Maximum number of articles
            days: How many days of news
            source_type: Data source type
            preprocess: Whether to preprocess the data
            use_cache: Whether to use cache
            
        Returns:
            List of news articles
        """
        # Select appropriate source type for news
        if not source_type:
            source_type = 'news_api'  # Default for news data
        
        # Check cache first if enabled
        if use_cache:
            cache_key = self._get_cache_key('news', {
                'keywords': ','.join(keywords),
                'limit': limit,
                'days': days,
                'source_type': source_type
            })
            
            cached_data = get_cache(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_data
        
        # Try to get news
        try:
            source = self._get_source(source_type)
            articles = await source.fetch_news(keywords, limit, days)
            
            # Preprocess if requested
            if preprocess:
                preprocessor = self._get_preprocessor('news')
                articles = preprocessor.process(articles)
            
            # Cache the result if enabled
            if use_cache:
                set_cache(cache_key, articles, self.source_configs[source_type]['cache_ttl'])
            
            return articles
            
        except Exception as e:
            logger.error(f"Error fetching news from {source_type}: {str(e)}")
            return []  # Return empty list if news fetching fails
    
    async def get_economic_indicator(
        self,
        indicator: str,
        country: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        source_type: Optional[str] = None,
        preprocess: bool = True,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Get economic indicator data.
        
        Args:
            indicator: Indicator code
            country: Country code
            start_date: Start date
            end_date: End date
            source_type: Data source type
            preprocess: Whether to preprocess the data
            use_cache: Whether to use cache
            
        Returns:
            DataFrame with economic indicator data
        """
        # Select appropriate source type for economic indicators
        if not source_type:
            source_type = 'fred'  # Default for economic data
        
        # Check cache first if enabled
        if use_cache:
            cache_key = self._get_cache_key('economic', {
                'indicator': indicator,
                'country': country,
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
                'source_type': source_type
            })
            
            cached_data = get_cache(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for {cache_key}")
                df = pd.DataFrame(
                    data=cached_data.get('data', []),
                    index=pd.to_datetime(cached_data.get('index', [])),
                    columns=cached_data.get('columns', [])
                )
                return df
        
        # Try to get economic data
        try:
            source = self._get_source(source_type)
            df = await source.fetch_economic_indicator(indicator, country, start_date, end_date)
            
            # Preprocess if requested
            if preprocess:
                preprocessor = self._get_preprocessor('economic')
                df = preprocessor.process(df)
            
            # Cache the result if enabled
            if use_cache:
                cache_data = df.to_dict(orient='split')
                set_cache(cache_key, cache_data, self.source_configs[source_type]['cache_ttl'])
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching economic indicator from {source_type}: {str(e)}")
            return pd.DataFrame()  # Return empty DataFrame if fetching fails
    
    async def get_multi_symbol_data(
        self,
        symbols: List[str],
        timeframe: str = '1h',
        limit: int = 1000,
        since: Optional[Union[datetime, int]] = None,
        source_type: Optional[str] = None,
        preprocess: bool = True,
        use_cache: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """
        Get market data for multiple symbols in parallel.
        
        Args:
            symbols: List of symbols
            timeframe: Timeframe for the data
            limit: Maximum number of candles
            since: Start time
            source_type: Data source type
            preprocess: Whether to preprocess the data
            use_cache: Whether to use cache
            
        Returns:
            Dictionary of symbol -> DataFrame
        """
        # Create tasks for all symbols
        tasks = []
        for symbol in symbols:
            task = self.get_market_data(
                symbol, timeframe, limit, since, source_type, preprocess, use_cache
            )
            tasks.append(task)
        
        # Run all tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        data_dict = {}
        for i, result in enumerate(results):
            symbol = symbols[i]
            if isinstance(result, Exception):
                logger.error(f"Error fetching data for {symbol}: {str(result)}")
                data_dict[symbol] = pd.DataFrame()  # Empty DataFrame for failed fetches
            else:
                data_dict[symbol] = result
        
        return data_dict
    
    def clear_cache(self, pattern: Optional[str] = None):
        """
        Clear cached data.
        
        Args:
            pattern: Optional pattern to match cache keys (None for all)
        """
        if pattern:
            cache_pattern = f"{self.cache_prefix}{pattern}*"
        else:
            cache_pattern = f"{self.cache_prefix}*"
        
        deleted = delete_pattern(cache_pattern)
        logger.info(f"Cleared {deleted} cache entries matching {cache_pattern}")
    
    async def close(self):
        """
        Close connections and clean up resources.
        """
        # Nothing specific to clean up at the moment
        pass 