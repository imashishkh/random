"""
Data providers for fundamental analysis.

This module contains classes for retrieving financial metrics, economic indicators,
and news data for fundamental analysis.
"""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import numpy as np
import yfinance as yf
from pandas_datareader import data as pdr

from ...utils.logging.logger import get_logger

logger = get_logger()


class CacheManager:
    """
    Manages cached data with expiration times.
    
    This implementation uses in-memory caching with different expiration 
    times based on data types.
    """
    
    def __init__(self, ttl_map: Optional[Dict[str, int]] = None):
        """
        Initialize the cache manager.
        
        Args:
            ttl_map: Map of data type to time-to-live in seconds
        """
        self._cache = {}
        self._ttl_map = ttl_map or {
            'financial': 86400,  # 24 hours
            'economic': 43200,   # 12 hours
            'news': 3600         # 1 hour
        }
    
    def get(self, key: str, data_type: str) -> Optional[Any]:
        """
        Get data from cache if it exists and is not expired.
        
        Args:
            key: Cache key
            data_type: Type of data (financial, economic, news)
            
        Returns:
            Cached data or None if not cached or expired
        """
        if key not in self._cache:
            return None
            
        entry = self._cache[key]
        expiration = entry['timestamp'] + self._ttl_map.get(data_type, 3600)
        
        if time.time() > expiration:
            del self._cache[key]
            return None
            
        return entry['data']
    
    def set(self, key: str, data: Any, data_type: str) -> None:
        """
        Store data in cache with appropriate expiration.
        
        Args:
            key: Cache key
            data: Data to cache
            data_type: Type of data (financial, economic, news)
        """
        self._cache[key] = {
            'data': data,
            'timestamp': time.time(),
            'type': data_type
        }
    
    def invalidate(self, key: str) -> None:
        """
        Invalidate a specific cache entry.
        
        Args:
            key: Cache key to invalidate
        """
        if key in self._cache:
            del self._cache[key]
    
    def invalidate_type(self, data_type: str) -> None:
        """
        Invalidate all cache entries of a specific type.
        
        Args:
            data_type: Type of data to invalidate
        """
        keys_to_delete = []
        for key, entry in self._cache.items():
            if entry['type'] == data_type:
                keys_to_delete.append(key)
                
        for key in keys_to_delete:
            del self._cache[key]


class BaseDataProvider(ABC):
    """Base class for all data providers."""
    
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        """
        Initialize the data provider.
        
        Args:
            cache_manager: Cache manager for caching data
        """
        self.cache_manager = cache_manager or CacheManager()
    
    @abstractmethod
    async def get_data(self, *args, **kwargs) -> Any:
        """Get data from the provider."""
        pass
    
    def _get_cache_key(self, *args, **kwargs) -> str:
        """
        Generate a cache key from arguments.
        
        This method should be overridden by subclasses to provide
        appropriate cache keys based on their specific arguments.
        """
        raise NotImplementedError("Subclasses must implement _get_cache_key")
    
    def _get_data_type(self) -> str:
        """Get the data type for caching purposes."""
        raise NotImplementedError("Subclasses must implement _get_data_type")


class FinancialDataProvider(BaseDataProvider):
    """
    Provider for financial metrics data using yfinance.
    
    This provider retrieves financial metrics for companies that can
    influence forex markets.
    """
    
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        """
        Initialize the financial data provider.
        
        Args:
            cache_manager: Cache manager for caching data
        """
        super().__init__(cache_manager)
    
    async def get_data(self, ticker: str, period: str = '1y') -> Dict[str, Any]:
        """
        Retrieve financial data for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            period: Period of data to retrieve
            
        Returns:
            Dictionary of financial metrics
        """
        cache_key = self._get_cache_key(ticker, period)
        cached_data = self.cache_manager.get(cache_key, self._get_data_type())
        
        if cached_data is not None:
            logger.debug(f"Retrieved financial data for {ticker} from cache")
            return cached_data
        
        try:
            # Get stock info
            stock = yf.Ticker(ticker)
            
            # Get financials
            income_stmt = stock.income_stmt
            balance_sheet = stock.balance_sheet
            cash_flow = stock.cashflow
            
            # Get info and history
            info = stock.info
            history = stock.history(period=period)
            
            # Process financial data
            financial_data = {
                'ticker': ticker,
                'info': info,
                'history': history,
                'income_statement': income_stmt,
                'balance_sheet': balance_sheet,
                'cash_flow': cash_flow,
                'metrics': self._calculate_metrics(income_stmt, balance_sheet, cash_flow, info),
                'timestamp': datetime.now().isoformat()
            }
            
            # Cache the data
            self.cache_manager.set(cache_key, financial_data, self._get_data_type())
            
            logger.info(f"Retrieved financial data for {ticker}")
            return financial_data
        
        except Exception as e:
            logger.error(f"Error retrieving financial data for {ticker}: {str(e)}")
            # Return empty data structure with error information
            return {
                'ticker': ticker,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _calculate_metrics(self, income_stmt, balance_sheet, cash_flow, info) -> Dict[str, Any]:
        """
        Calculate financial metrics from raw data.
        
        Args:
            income_stmt: Income statement data
            balance_sheet: Balance sheet data
            cash_flow: Cash flow data
            info: Stock info
            
        Returns:
            Dictionary of calculated metrics
        """
        metrics = {}
        
        try:
            # P/E ratio
            if 'trailingPE' in info:
                metrics['pe_ratio'] = info['trailingPE']
            
            # Revenue growth (YoY)
            if not income_stmt.empty and 'Total Revenue' in income_stmt.index:
                revenue = income_stmt.loc['Total Revenue']
                if len(revenue) >= 2:
                    latest_revenue = revenue.iloc[0]
                    previous_revenue = revenue.iloc[1]
                    metrics['revenue_growth'] = (latest_revenue - previous_revenue) / previous_revenue if previous_revenue else None
            
            # Profit margin
            if not income_stmt.empty and 'Net Income' in income_stmt.index and 'Total Revenue' in income_stmt.index:
                net_income = income_stmt.loc['Net Income'].iloc[0] if not income_stmt.loc['Net Income'].empty else None
                total_revenue = income_stmt.loc['Total Revenue'].iloc[0] if not income_stmt.loc['Total Revenue'].empty else None
                
                if net_income is not None and total_revenue is not None and total_revenue != 0:
                    metrics['profit_margin'] = net_income / total_revenue
            
            # Debt-to-equity ratio
            if not balance_sheet.empty and 'Total Debt' in balance_sheet.index and 'Stockholders Equity' in balance_sheet.index:
                total_debt = balance_sheet.loc['Total Debt'].iloc[0] if not balance_sheet.loc['Total Debt'].empty else None
                equity = balance_sheet.loc['Stockholders Equity'].iloc[0] if not balance_sheet.loc['Stockholders Equity'].empty else None
                
                if total_debt is not None and equity is not None and equity != 0:
                    metrics['debt_to_equity'] = total_debt / equity
            
            # Current ratio
            if not balance_sheet.empty and 'Current Assets' in balance_sheet.index and 'Current Liabilities' in balance_sheet.index:
                current_assets = balance_sheet.loc['Current Assets'].iloc[0] if not balance_sheet.loc['Current Assets'].empty else None
                current_liabilities = balance_sheet.loc['Current Liabilities'].iloc[0] if not balance_sheet.loc['Current Liabilities'].empty else None
                
                if current_assets is not None and current_liabilities is not None and current_liabilities != 0:
                    metrics['current_ratio'] = current_assets / current_liabilities
            
            # Return on equity (ROE)
            if not income_stmt.empty and not balance_sheet.empty and 'Net Income' in income_stmt.index and 'Stockholders Equity' in balance_sheet.index:
                net_income = income_stmt.loc['Net Income'].iloc[0] if not income_stmt.loc['Net Income'].empty else None
                equity = balance_sheet.loc['Stockholders Equity'].iloc[0] if not balance_sheet.loc['Stockholders Equity'].empty else None
                
                if net_income is not None and equity is not None and equity != 0:
                    metrics['roe'] = net_income / equity
            
            # Free cash flow
            if not cash_flow.empty and 'Free Cash Flow' in cash_flow.index:
                metrics['free_cash_flow'] = cash_flow.loc['Free Cash Flow'].iloc[0] if not cash_flow.loc['Free Cash Flow'].empty else None
            
        except Exception as e:
            logger.error(f"Error calculating financial metrics: {str(e)}")
        
        return metrics
    
    def _get_cache_key(self, ticker: str, period: str) -> str:
        """
        Generate a cache key for financial data.
        
        Args:
            ticker: Stock ticker symbol
            period: Period of data
            
        Returns:
            Cache key string
        """
        return f"financial_{ticker}_{period}"
    
    def _get_data_type(self) -> str:
        """Get the data type for caching purposes."""
        return 'financial'


class EconomicDataProvider(BaseDataProvider):
    """
    Provider for economic indicators using pandas-datareader with FRED.
    
    This provider retrieves economic indicators that can influence forex markets.
    """
    
    # Mapping of indicator codes to descriptions
    INDICATOR_MAP = {
        'GDP': 'GDP',                        # Gross Domestic Product
        'UNRATE': 'Unemployment Rate',       # Unemployment Rate
        'CPIAUCSL': 'Consumer Price Index',  # Consumer Price Index (Inflation)
        'FEDFUNDS': 'Federal Funds Rate',    # Federal Funds Rate (Interest Rate)
        'INDPRO': 'Industrial Production',   # Industrial Production Index
        'RSAFS': 'Retail Sales',             # Retail Sales
        'HOUST': 'Housing Starts',           # Housing Starts
        'USREC': 'Recession Indicator',      # US Recession Indicator
        'NIKKEI225': 'Nikkei 225',           # Nikkei 225 Index
        'DEXUSEU': 'USD/EUR Exchange Rate',  # USD to Euro Exchange Rate
        'DEXJPUS': 'JPY/USD Exchange Rate',  # Yen to USD Exchange Rate
        'DEXUSUK': 'USD/GBP Exchange Rate',  # USD to Pound Exchange Rate
        'PCE': 'Personal Consumption Expenditures',  # Personal Consumption Expenditures
        'PAYEMS': 'Total Nonfarm Payrolls',  # Nonfarm Payrolls
        'UMCSENT': 'Consumer Sentiment'      # Consumer Sentiment Index
    }
    
    # Country-specific indicators
    COUNTRY_INDICATORS = {
        'US': ['GDP', 'UNRATE', 'CPIAUCSL', 'FEDFUNDS', 'INDPRO', 'PAYEMS', 'UMCSENT'],
        'EUR': ['DEXUSEU'],
        'UK': ['DEXUSUK'],
        'JP': ['DEXJPUS', 'NIKKEI225']
    }
    
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        """
        Initialize the economic data provider.
        
        Args:
            cache_manager: Cache manager for caching data
        """
        super().__init__(cache_manager)
    
    async def get_data(self, indicators: Optional[List[str]] = None, 
                      start_date: Optional[str] = None, 
                      end_date: Optional[str] = None,
                      country: Optional[str] = None) -> Dict[str, pd.DataFrame]:
        """
        Retrieve economic indicator data.
        
        Args:
            indicators: List of indicator codes to retrieve (default: all)
            start_date: Start date for data in 'YYYY-MM-DD' format
            end_date: End date for data in 'YYYY-MM-DD' format
            country: Specific country to get indicators for
            
        Returns:
            Dictionary mapping indicator codes to DataFrames
        """
        # Determine which indicators to fetch
        if country is not None and country in self.COUNTRY_INDICATORS:
            indicators_to_fetch = self.COUNTRY_INDICATORS[country]
        else:
            indicators_to_fetch = indicators or list(self.INDICATOR_MAP.keys())
        
        # Set default dates if not provided
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        
        cache_key = self._get_cache_key(indicators_to_fetch, start_date, end_date)
        cached_data = self.cache_manager.get(cache_key, self._get_data_type())
        
        if cached_data is not None:
            logger.debug(f"Retrieved economic data from cache")
            return cached_data
        
        result = {}
        
        try:
            # Fetch each indicator
            for indicator in indicators_to_fetch:
                try:
                    df = pdr.DataReader(indicator, 'fred', start_date, end_date)
                    result[indicator] = df
                    logger.debug(f"Retrieved {indicator} ({self.INDICATOR_MAP.get(indicator, 'Unknown')}) data")
                except Exception as e:
                    logger.warning(f"Error retrieving {indicator} data: {str(e)}")
                    result[indicator] = pd.DataFrame()  # Empty DataFrame for failed fetch
            
            # Cache the result
            self.cache_manager.set(cache_key, result, self._get_data_type())
            
            logger.info(f"Retrieved economic data for {len(result)} indicators")
            
            # Add metadata
            metadata = {
                'start_date': start_date,
                'end_date': end_date,
                'indicators': indicators_to_fetch,
                'timestamp': datetime.now().isoformat()
            }
            result['_metadata'] = metadata
            
            return result
            
        except Exception as e:
            logger.error(f"Error retrieving economic data: {str(e)}")
            return {
                '_metadata': {
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }
            }
    
    def _get_cache_key(self, indicators: List[str], start_date: str, end_date: str) -> str:
        """
        Generate a cache key for economic data.
        
        Args:
            indicators: List of indicator codes
            start_date: Start date string
            end_date: End date string
            
        Returns:
            Cache key string
        """
        indicators_str = '_'.join(sorted(indicators))
        return f"economic_{indicators_str}_{start_date}_{end_date}"
    
    def _get_data_type(self) -> str:
        """Get the data type for caching purposes."""
        return 'economic'


class NewsDataProvider(BaseDataProvider):
    """
    Provider for financial news data.
    
    This provider retrieves financial news that can influence forex markets.
    """
    
    def __init__(self, api_key: Optional[str] = None, cache_manager: Optional[CacheManager] = None):
        """
        Initialize the news data provider.
        
        Args:
            api_key: API key for the news service
            cache_manager: Cache manager for caching data
        """
        super().__init__(cache_manager)
        self.api_key = api_key
        
        # Default news sources
        self.default_sources = [
            'bloomberg', 'reuters', 'financial-times', 'wall-street-journal',
            'cnbc', 'the-economist', 'business-insider', 'fortune'
        ]
    
    async def get_data(self, query: Optional[str] = None, 
                      sources: Optional[List[str]] = None,
                      from_date: Optional[str] = None,
                      to_date: Optional[str] = None,
                      max_results: int = 100) -> Dict[str, Any]:
        """
        Retrieve news data.
        
        Args:
            query: Search query for news
            sources: List of news sources
            from_date: Start date for news in 'YYYY-MM-DD' format
            to_date: End date for news in 'YYYY-MM-DD' format
            max_results: Maximum number of results to return
            
        Returns:
            Dictionary of news data
        """
        sources = sources or self.default_sources
        query = query or "forex OR currency OR economy OR financial OR central bank"
        
        # Set default dates if not provided
        if to_date is None:
            to_date = datetime.now().strftime('%Y-%m-%d')
        if from_date is None:
            from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        cache_key = self._get_cache_key(query, sources, from_date, to_date)
        cached_data = self.cache_manager.get(cache_key, self._get_data_type())
        
        if cached_data is not None:
            logger.debug(f"Retrieved news data from cache")
            return cached_data
        
        try:
            import requests
            
            # Check if API key is available
            if not self.api_key:
                logger.warning("NewsAPI key not available, returning empty results")
                return {
                    'articles': [],
                    'status': 'error',
                    'error': 'API key not configured',
                    'timestamp': datetime.now().isoformat()
                }
            
            # Format sources for API
            sources_str = ','.join(sources)
            
            # Make API request to NewsAPI
            url = 'https://newsapi.org/v2/everything'
            params = {
                'q': query,
                'sources': sources_str,
                'from': from_date,
                'to': to_date,
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': min(max_results, 100),  # API limit
                'apiKey': self.api_key
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                # Add metadata
                result = {
                    'articles': data.get('articles', []),
                    'status': data.get('status'),
                    'totalResults': data.get('totalResults', 0),
                    'query': query,
                    'sources': sources,
                    'from_date': from_date,
                    'to_date': to_date,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Cache the result
                self.cache_manager.set(cache_key, result, self._get_data_type())
                
                logger.info(f"Retrieved {len(result['articles'])} news articles")
                return result
            else:
                logger.error(f"News API error: {response.status_code} - {response.text}")
                return {
                    'articles': [],
                    'status': 'error',
                    'error': f"API error: {response.status_code}",
                    'response': response.text,
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error retrieving news data: {str(e)}")
            return {
                'articles': [],
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _get_cache_key(self, query: str, sources: List[str], from_date: str, to_date: str) -> str:
        """
        Generate a cache key for news data.
        
        Args:
            query: Search query
            sources: List of news sources
            from_date: Start date string
            to_date: End date string
            
        Returns:
            Cache key string
        """
        sources_str = '_'.join(sorted(sources))
        return f"news_{query}_{sources_str}_{from_date}_{to_date}"
    
    def _get_data_type(self) -> str:
        """Get the data type for caching purposes."""
        return 'news' 