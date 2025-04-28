"""
Fundamental Analysis Agent implementation.

This module provides a comprehensive agent for analyzing fundamental data
and generating trading signals based on financial metrics, economic indicators,
and news sentiment.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import numpy as np

from .base_agent import BaseAgent
from .fundamental_analysis.data_provider import (
    CacheManager,
    FinancialDataProvider,
    EconomicDataProvider,
    NewsDataProvider
)
from .fundamental_analysis.signal_generator import FundamentalSignalGenerator
from ...utils.logging.logger import get_logger

logger = get_logger()


class FundamentalAnalysisAgent:
    """
    Agent for analyzing fundamental data and generating trading signals.
    
    This agent integrates financial metrics, economic indicators, and news sentiment
    to generate trading signals for forex markets.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, name: Optional[str] = None):
        """
        Initialize the fundamental analysis agent.
        
        Args:
            config: Configuration dictionary
            name: Name for the agent instance
        """
        self.name = name or f"Fundamental-Agent-{uuid.uuid4().hex[:8]}"
        self.config = config or {}
        
        # Create cache manager
        self.cache_manager = CacheManager(
            ttl_map=self.config.get('cache_ttl', {
                'financial': 86400,  # 24 hours
                'economic': 43200,   # 12 hours
                'news': 3600         # 1 hour
            })
        )
        
        # Create data providers
        self.financial_provider = FinancialDataProvider(self.cache_manager)
        self.economic_provider = EconomicDataProvider(self.cache_manager)
        self.news_provider = NewsDataProvider(
            api_key=self.config.get('news_api_key'),
            cache_manager=self.cache_manager
        )
        
        # Create signal generator
        self.signal_generator = FundamentalSignalGenerator(self.config.get('signal', {}))
        
        # Initialize results storage
        self.signals = []
        self.last_analysis = None
        
        logger.info(f"Initialized {self.name}")
    
    async def analyze(self, 
                    currency_pair: str,
                    timeframe: str = 'medium',
                    include_companies: bool = True,
                    include_economic: bool = True,
                    include_news: bool = True) -> Dict[str, Any]:
        """
        Analyze fundamental data for a currency pair.
        
        Args:
            currency_pair: Currency pair to analyze (e.g., 'EUR/USD')
            timeframe: Analysis timeframe ('short', 'medium', 'long')
            include_companies: Whether to include company financial metrics
            include_economic: Whether to include economic indicators
            include_news: Whether to include news sentiment
            
        Returns:
            Analysis results with signal
        """
        logger.info(f"Starting fundamental analysis for {currency_pair}")
        
        # Parse currency pair to get economies
        economies = self._parse_currency_pair(currency_pair)
        if not economies:
            logger.error(f"Invalid currency pair format: {currency_pair}")
            return {
                'error': f"Invalid currency pair format: {currency_pair}",
                'timestamp': datetime.now().isoformat()
            }
        
        base_economy, quote_economy = economies
        
        # Gather data asynchronously
        tasks = []
        
        # Financial data
        if include_companies:
            financial_task = self._gather_financial_data(base_economy, quote_economy)
            tasks.append(financial_task)
        
        # Economic data
        if include_economic:
            economic_task = self._gather_economic_data(base_economy, quote_economy)
            tasks.append(economic_task)
        
        # News data
        if include_news:
            news_task = self._gather_news_data(currency_pair)
            tasks.append(news_task)
        
        # Wait for all data gathering to complete
        task_results = await asyncio.gather(*tasks)
        
        # Process results
        result_index = 0
        financial_data = task_results[result_index] if include_companies else {}
        result_index += 1 if include_companies else 0
        
        economic_data = task_results[result_index] if include_economic else {}
        result_index += 1 if include_economic else 0
        
        news_data = task_results[result_index] if include_news else {}
        
        # Generate signal
        signal = self.signal_generator.generate_signal(
            currency_pair=currency_pair,
            financial_data=financial_data,
            economic_data=economic_data,
            news_data=news_data,
            timeframe=timeframe
        )
        
        # Store signal
        self.signals.append(signal)
        
        # Create analysis result
        analysis_result = {
            'currency_pair': currency_pair,
            'timeframe': timeframe,
            'timestamp': datetime.now().isoformat(),
            'signal': signal,
            'data': {
                'financial': financial_data if include_companies else None,
                'economic': economic_data if include_economic else None,
                'news': news_data if include_news else None
            }
        }
        
        self.last_analysis = analysis_result
        
        logger.info(f"Completed fundamental analysis for {currency_pair}")
        return analysis_result
    
    async def _gather_financial_data(self, base_economy: str, quote_economy: str) -> Dict[str, Any]:
        """
        Gather financial data for relevant companies.
        
        Args:
            base_economy: Base currency economy (e.g., 'EUR')
            quote_economy: Quote currency economy (e.g., 'USD')
            
        Returns:
            Dictionary of financial data
        """
        economy_tickers = self.signal_generator.economy_tickers
        
        # Get tickers for relevant economies
        base_tickers = economy_tickers.get(base_economy, [])
        quote_tickers = economy_tickers.get(quote_economy, [])
        
        tickers = base_tickers + quote_tickers
        
        # Gather data for each ticker
        tasks = []
        for ticker in tickers:
            tasks.append(self.financial_provider.get_data(ticker))
        
        # Wait for all requests to complete
        ticker_data = await asyncio.gather(*tasks)
        
        # Combine results
        result = {}
        for i, ticker in enumerate(tickers):
            result[ticker] = ticker_data[i]
        
        return result
    
    async def _gather_economic_data(self, base_economy: str, quote_economy: str) -> Dict[str, Any]:
        """
        Gather economic indicator data.
        
        Args:
            base_economy: Base currency economy (e.g., 'EUR')
            quote_economy: Quote currency economy (e.g., 'USD')
            
        Returns:
            Dictionary of economic indicator data
        """
        # Get data for both economies
        base_data = await self.economic_provider.get_data(country=base_economy)
        quote_data = await self.economic_provider.get_data(country=quote_economy)
        
        # Combine results
        combined_data = {}
        combined_data.update(base_data)
        combined_data.update(quote_data)
        
        # Add combined metadata
        combined_data['_metadata'] = {
            'base_economy': base_economy,
            'quote_economy': quote_economy,
            'timestamp': datetime.now().isoformat()
        }
        
        return combined_data
    
    async def _gather_news_data(self, currency_pair: str) -> Dict[str, Any]:
        """
        Gather news data relevant to the currency pair.
        
        Args:
            currency_pair: Currency pair (e.g., 'EUR/USD')
            
        Returns:
            Dictionary of news data with sentiment analysis
        """
        # Create search query based on currency pair
        currencies = currency_pair.split('/')
        
        if len(currencies) != 2:
            logger.warning(f"Invalid currency pair format: {currency_pair}")
            return {}
        
        base, quote = currencies
        
        # Map currency codes to full names
        currency_names = {
            'USD': 'Dollar',
            'EUR': 'Euro',
            'GBP': 'Pound',
            'JPY': 'Yen',
            'AUD': 'Australian Dollar',
            'CAD': 'Canadian Dollar',
            'CHF': 'Swiss Franc',
            'NZD': 'New Zealand Dollar'
        }
        
        base_name = currency_names.get(base, base)
        quote_name = currency_names.get(quote, quote)
        
        # Create search query
        query = f"({base} OR {base_name}) AND ({quote} OR {quote_name}) AND (forex OR currency OR exchange rate OR economy)"
        
        # Get news data
        news_data = await self.news_provider.get_data(query=query)
        
        # Process news data with sentiment analysis
        if news_data and 'articles' in news_data:
            await self._process_news_sentiment(news_data)
        
        return news_data
    
    async def _process_news_sentiment(self, news_data: Dict[str, Any]) -> None:
        """
        Process news articles with sentiment analysis.
        
        Args:
            news_data: News data dictionary to update in-place
        """
        if 'articles' not in news_data:
            return
        
        try:
            from src.sentiment.sentiment_analyzer import SentimentAnalyzer
            from src.utils.config import SentimentAnalysisConfig
            
            # Create sentiment analyzer
            config = SentimentAnalysisConfig(model_name="vader")
            analyzer = SentimentAnalyzer(config)
            
            # Process each article
            for article in news_data['articles']:
                # Combine title and description for analysis
                text = f"{article.get('title', '')} {article.get('description', '')}"
                
                # Analyze sentiment
                sentiment_scores = analyzer.analyze_text(text)
                
                # Add sentiment to article
                article['sentiment'] = {
                    'score': sentiment_scores.get('compound', 0),
                    'positive': sentiment_scores.get('pos', 0),
                    'negative': sentiment_scores.get('neg', 0),
                    'neutral': sentiment_scores.get('neu', 0)
                }
                
                # Calculate relevance based on presence of keywords in title
                article['relevance'] = 1.0  # Default relevance
                if 'title' in article:
                    title = article['title'].lower()
                    # Reduce relevance if title doesn't contain key financial terms
                    if not any(term in title for term in ['exchange', 'currency', 'forex', 'economy', 'rate', 'central bank']):
                        article['relevance'] = 0.7
            
            logger.debug(f"Processed sentiment for {len(news_data['articles'])} news articles")
        
        except Exception as e:
            logger.error(f"Error processing news sentiment: {str(e)}")
    
    def _parse_currency_pair(self, currency_pair: str) -> Optional[Tuple[str, str]]:
        """
        Parse a currency pair to get base and quote economies.
        
        Args:
            currency_pair: Currency pair (e.g., 'EUR/USD')
            
        Returns:
            Tuple of (base_economy, quote_economy) or None if invalid
        """
        try:
            currencies = currency_pair.split('/')
            
            if len(currencies) != 2:
                return None
            
            base, quote = currencies
            
            # Map to economy codes (some currencies might need special mapping)
            special_mapping = {
                'JPY': 'JP',
                'CHF': 'CH'
            }
            
            base_economy = special_mapping.get(base, base)
            quote_economy = special_mapping.get(quote, quote)
            
            return (base_economy, quote_economy)
            
        except Exception as e:
            logger.error(f"Error parsing currency pair {currency_pair}: {str(e)}")
            return None
    
    def get_latest_signals(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recent signals generated by the agent.
        
        Args:
            limit: Maximum number of signals to return
            
        Returns:
            List of signal dictionaries
        """
        return self.signals[-limit:] if self.signals else []
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the agent to a dictionary representation.
        
        Returns:
            Dictionary representation of the agent
        """
        return {
            'name': self.name,
            'type': self.__class__.__name__,
            'config': self.config,
            'signals_count': len(self.signals),
            'last_analysis_time': self.last_analysis['timestamp'] if self.last_analysis else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FundamentalAnalysisAgent':
        """
        Create an agent from a dictionary representation.
        
        Args:
            data: Dictionary representation
            
        Returns:
            FundamentalAnalysisAgent instance
        """
        return cls(config=data.get('config'), name=data.get('name')) 