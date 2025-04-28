"""
Perplexity Query Generator

This module generates optimized queries for the Perplexity API to gather
forex market intelligence and financial research data.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import random

from ...config.settings import get_settings
from ...data.market_data import get_latest_forex_data
from ...data.models import Currency, CurrencyPair

# Set up logging
logger = logging.getLogger(__name__)


class QueryGenerator:
    """
    Generates optimized queries for the Perplexity API to gather forex market intelligence.
    
    This class creates focused queries for different types of market information and
    supports personalization based on trading preferences.
    """
    
    def __init__(self, 
                 base_currencies: Optional[List[str]] = None,
                 quote_currencies: Optional[List[str]] = None,
                 preferred_pairs: Optional[List[str]] = None):
        """
        Initialize the query generator with currency preferences.
        
        Args:
            base_currencies: List of base currencies to focus on (e.g., ['EUR', 'USD'])
            quote_currencies: List of quote currencies to focus on
            preferred_pairs: List of specific currency pairs to prioritize (e.g., ['EUR/USD'])
        """
        # Default major currencies if none provided
        self.base_currencies = base_currencies or ['EUR', 'USD', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'NZD']
        self.quote_currencies = quote_currencies or ['USD', 'EUR', 'GBP', 'JPY']
        
        # Preferred pairs override
        self.preferred_pairs = preferred_pairs or []
        
        # If no preferred pairs specified, generate common ones
        if not self.preferred_pairs:
            self.preferred_pairs = ['EUR/USD', 'GBP/USD', 'USD/JPY', 'AUD/USD', 'USD/CAD', 'USD/CHF', 'NZD/USD']
        
        logger.info(f"QueryGenerator initialized with {len(self.preferred_pairs)} preferred currency pairs")
    
    def generate_currency_pair_analysis_query(self, pair: Optional[str] = None) -> str:
        """
        Generate a query to analyze a specific currency pair.
        
        Args:
            pair: Currency pair to analyze (e.g., 'EUR/USD'). If None, a random preferred pair is used.
            
        Returns:
            Query string for currency pair analysis
        """
        # Select a currency pair if not specified
        if not pair:
            pair = random.choice(self.preferred_pairs)
        
        # Create a detailed query for analyzing the pair
        query = (
            f"Provide a detailed analysis of the {pair} currency pair. Include: "
            f"1. Current price levels, support and resistance points "
            f"2. Recent price action and key technical indicators (RSI, MACD, moving averages) "
            f"3. Major fundamental drivers affecting this pair "
            f"4. Market sentiment (bullish/bearish/neutral) with justification "
            f"5. Important upcoming events that could impact this pair "
            f"6. Short-term and medium-term price targets "
            f"Present the information in a structured format suitable for trading decisions."
        )
        
        logger.debug(f"Generated currency pair analysis query for {pair}")
        return query
    
    def generate_economic_calendar_query(self, 
                                        days_ahead: int = 7, 
                                        countries: Optional[List[str]] = None) -> str:
        """
        Generate a query to get upcoming economic events.
        
        Args:
            days_ahead: Number of days ahead to look for events
            countries: List of countries to focus on. If None, derived from currencies.
            
        Returns:
            Query string for economic calendar
        """
        # If no countries specified, derive from currencies
        if not countries:
            currency_to_country = {
                'USD': 'United States', 
                'EUR': 'Eurozone', 
                'GBP': 'United Kingdom', 
                'JPY': 'Japan',
                'AUD': 'Australia', 
                'CAD': 'Canada', 
                'CHF': 'Switzerland', 
                'NZD': 'New Zealand'
            }
            
            countries = [currency_to_country[curr] for curr in self.base_currencies 
                        if curr in currency_to_country]
        
        # Calculate the date range
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        
        # Format the countries for the query
        countries_str = ", ".join(countries)
        
        query = (
            f"List the important economic indicators and events from {today} to {end_date} for {countries_str}. "
            f"For each event include: "
            f"1. The date and time "
            f"2. The country/region "
            f"3. The indicator name "
            f"4. Previous value, forecast, and importance level (high/medium/low) "
            f"5. Potential impact on related currency pairs "
            f"Format as a structured list organized by date."
        )
        
        logger.debug(f"Generated economic calendar query for next {days_ahead} days")
        return query
    
    def generate_market_news_query(self, 
                                  recency: str = "day", 
                                  focus: Optional[str] = None) -> str:
        """
        Generate a query to get latest market news.
        
        Args:
            recency: Time period to focus on (day, week, month)
            focus: Specific focus area (e.g., 'central banks', 'inflation')
            
        Returns:
            Query string for market news
        """
        # Build focus part of the query
        focus_text = ""
        if focus:
            focus_text = f" with particular focus on {focus}"
        
        # Time description based on recency
        time_desc = {
            "day": "the last 24 hours",
            "week": "the past week",
            "month": "the past month"
        }.get(recency, "recent")
        
        # Currency pairs string
        pairs_str = ", ".join(self.preferred_pairs[:5])  # Limit to top 5 pairs
        
        query = (
            f"Summarize the most important forex market news from {time_desc}{focus_text}. "
            f"Focus on news affecting these currency pairs: {pairs_str}. "
            f"For each significant news item include: "
            f"1. Headline and brief description "
            f"2. Source and timing "
            f"3. Direct impact on specific currency pairs "
            f"4. Market reaction "
            f"Format as a structured list of news items with clear categorization."
        )
        
        logger.debug(f"Generated market news query with {recency} recency")
        return query
    
    def generate_central_bank_query(self, bank: Optional[str] = None) -> str:
        """
        Generate a query about central bank policy.
        
        Args:
            bank: Specific central bank to focus on (e.g., 'Fed', 'ECB')
            
        Returns:
            Query string for central bank policy analysis
        """
        # Map of central banks to their full names and associated currencies
        central_banks = {
            'Fed': {'name': 'Federal Reserve', 'currency': 'USD', 'country': 'United States'},
            'ECB': {'name': 'European Central Bank', 'currency': 'EUR', 'country': 'Eurozone'},
            'BoE': {'name': 'Bank of England', 'currency': 'GBP', 'country': 'United Kingdom'},
            'BoJ': {'name': 'Bank of Japan', 'currency': 'JPY', 'country': 'Japan'},
            'RBA': {'name': 'Reserve Bank of Australia', 'currency': 'AUD', 'country': 'Australia'},
            'BoC': {'name': 'Bank of Canada', 'currency': 'CAD', 'country': 'Canada'},
            'SNB': {'name': 'Swiss National Bank', 'currency': 'CHF', 'country': 'Switzerland'},
            'RBNZ': {'name': 'Reserve Bank of New Zealand', 'currency': 'NZD', 'country': 'New Zealand'}
        }
        
        # Select a random central bank if none specified
        if not bank or bank not in central_banks:
            # Filter for banks associated with preferred currencies
            relevant_banks = [key for key, data in central_banks.items() 
                             if data['currency'] in self.base_currencies or data['currency'] in self.quote_currencies]
            
            if not relevant_banks:
                relevant_banks = list(central_banks.keys())
                
            bank = random.choice(relevant_banks)
        
        bank_info = central_banks[bank]
        
        query = (
            f"Provide a detailed analysis of the {bank_info['name']}'s current monetary policy stance and outlook. Include: "
            f"1. Current interest rates and recent policy changes "
            f"2. Latest statements from key officials and meeting minutes "
            f"3. Inflation and economic growth outlook in {bank_info['country']} "
            f"4. Market expectations for future policy actions "
            f"5. How this is affecting the {bank_info['currency']} in forex markets "
            f"6. Projected policy path for the next 6-12 months "
            f"Present the information in a structured, detailed format for forex trading decisions."
        )
        
        logger.debug(f"Generated central bank query for {bank}")
        return query
    
    def generate_market_sentiment_query(self) -> str:
        """
        Generate a query to analyze overall market sentiment.
        
        Returns:
            Query string for market sentiment analysis
        """
        # Currency pairs string
        pairs_str = ", ".join(self.preferred_pairs[:5])  # Limit to top 5 pairs
        
        query = (
            f"Analyze the current overall forex market sentiment and risk appetite. Include: "
            f"1. General market mood (risk-on/risk-off) with supporting evidence "
            f"2. Sentiment indicators for major pairs ({pairs_str}) "
            f"3. Positioning data and sentiment from institutional investors "
            f"4. Retail trader sentiment and positioning "
            f"5. Key themes driving market psychology currently "
            f"6. How sentiment has shifted in the past week "
            f"Present the information in a structured format that quantifies sentiment where possible."
        )
        
        logger.debug("Generated market sentiment query")
        return query
    
    def generate_technical_analysis_query(self, pair: Optional[str] = None, timeframe: str = "daily") -> str:
        """
        Generate a query for technical analysis of a currency pair.
        
        Args:
            pair: Currency pair to analyze. If None, a random preferred pair is used.
            timeframe: Chart timeframe to analyze (e.g., 'hourly', 'daily', 'weekly')
            
        Returns:
            Query string for technical analysis
        """
        # Select a currency pair if not specified
        if not pair:
            pair = random.choice(self.preferred_pairs)
        
        # Valid timeframes
        valid_timeframes = ["hourly", "4-hour", "daily", "weekly", "monthly"]
        if timeframe not in valid_timeframes:
            timeframe = "daily"
            
        query = (
            f"Provide a detailed technical analysis for {pair} on the {timeframe} timeframe. Include: "
            f"1. Current price action and chart patterns "
            f"2. Key support and resistance levels with price values "
            f"3. Analysis of multiple technical indicators: "
            f"   a. Trend indicators (moving averages, ADX) "
            f"   b. Momentum indicators (RSI, MACD, Stochastic) "
            f"   c. Volatility indicators (Bollinger Bands, ATR) "
            f"4. Identification of potential entry and exit points "
            f"5. Risk-reward ratios for identified trade setups "
            f"6. Overall technical outlook and potential price targets "
            f"Present the analysis in a structured format with specific price levels."
        )
        
        logger.debug(f"Generated technical analysis query for {pair} on {timeframe} timeframe")
        return query
    
    def generate_correlation_analysis_query(self, base_pair: Optional[str] = None) -> str:
        """
        Generate a query to analyze correlations between currency pairs.
        
        Args:
            base_pair: Primary currency pair to analyze correlations against
            
        Returns:
            Query string for correlation analysis
        """
        # Select a base pair if not specified
        if not base_pair:
            base_pair = random.choice(self.preferred_pairs)
            
        # Get other pairs excluding the base pair
        other_pairs = [pair for pair in self.preferred_pairs if pair != base_pair]
        other_pairs_str = ", ".join(other_pairs[:5])  # Limit to 5 other pairs
        
        query = (
            f"Analyze the correlation relationships between {base_pair} and these pairs: {other_pairs_str}. Include: "
            f"1. Current correlation coefficients where available "
            f"2. Historical correlation patterns and recent changes "
            f"3. Fundamental factors driving these correlations "
            f"4. How these correlations can be used for trading strategies: "
            f"   a. Hedging opportunities "
            f"   b. Diversification considerations "
            f"   c. Potential for pairs trading "
            f"5. Correlations with other asset classes (stocks, commodities, bonds) "
            f"Present the information in a structured format with quantitative data where possible."
        )
        
        logger.debug(f"Generated correlation analysis query for {base_pair}")
        return query
    
    def generate_custom_query(self, 
                             topic: str, 
                             pair: Optional[str] = None, 
                             include_specifics: bool = True) -> str:
        """
        Generate a custom query on a specific forex-related topic.
        
        Args:
            topic: The main topic to research
            pair: Specific currency pair to focus on
            include_specifics: Whether to include specific formatting instructions
            
        Returns:
            Custom query string
        """
        # Select a pair if not specified and if we want to include a pair
        pair_text = ""
        if include_specifics and not pair:
            pair = random.choice(self.preferred_pairs)
            pair_text = f" for {pair}"
        elif include_specifics and pair:
            pair_text = f" for {pair}"
        
        # Format instructions based on whether we want specifics
        format_text = ""
        if include_specifics:
            format_text = " Present the information in a structured format suitable for forex trading decisions."
        
        query = f"Provide detailed analysis on {topic}{pair_text}.{format_text}"
        
        logger.debug(f"Generated custom query on '{topic}'")
        return query


# Singleton instance
generator = QueryGenerator()


def get_generator() -> QueryGenerator:
    """
    Get the QueryGenerator instance.
    
    Returns:
        The QueryGenerator singleton
    """
    return generator 