"""
Perplexity Content Categorizer

This module provides functionality for categorizing and tagging financial
data collected from the Perplexity API.
"""
import logging
import re
from typing import Dict, List, Any, Optional, Union, Set
from datetime import datetime, timedelta

# Set up logging
logger = logging.getLogger(__name__)

class ContentCategorizer:
    """
    Categorizer for financial data from Perplexity API.
    Provides methods to categorize and tag content for efficient retrieval.
    """
    
    def __init__(self):
        """Initialize the categorizer with financial taxonomies."""
        # Financial markets taxonomy
        self.market_sectors = {
            "forex": ["fx", "currency", "currencies", "foreign exchange", "eur/usd", "usd/jpy", "gbp/usd"],
            "equities": ["stocks", "shares", "equity", "nasdaq", "s&p", "dow jones", "stock market"],
            "commodities": ["commodity", "gold", "oil", "silver", "copper", "natural gas", "wti", "brent"],
            "crypto": ["cryptocurrency", "bitcoin", "ethereum", "btc", "eth", "altcoin", "token"],
            "bonds": ["treasury", "treasuries", "yield", "yields", "fixed income", "debt", "credit"]
        }
        
        # Economic indicator taxonomy
        self.economic_indicators = {
            "growth": ["gdp", "growth", "economic growth", "economic output", "expansion"],
            "inflation": ["cpi", "inflation", "price index", "core inflation", "ppi"],
            "employment": ["nfp", "non-farm payrolls", "unemployment", "jobs", "employment", "labor market"],
            "central_bank": ["fed", "federal reserve", "ecb", "boj", "bank of england", "interest rate"],
            "consumer": ["retail sales", "consumer spending", "consumer confidence", "pmi", "purchasing managers"],
            "housing": ["home sales", "housing market", "real estate", "construction", "building permits"],
            "trade": ["trade balance", "trade deficit", "exports", "imports", "tariffs"]
        }
        
        # Event type taxonomy
        self.event_types = {
            "economic_release": ["release", "report", "data", "economic data", "figures", "statistics"],
            "central_bank": ["rate decision", "monetary policy", "fomc", "policy meeting", "press conference"],
            "geopolitical": ["war", "conflict", "election", "political", "treaty", "agreement", "sanctions"],
            "corporate": ["earnings", "financial results", "profit", "loss", "revenue", "guidance"],
            "market_sentiment": ["sentiment", "risk appetite", "risk aversion", "fear", "greed", "momentum"],
            "technical": ["technical analysis", "support", "resistance", "breakout", "trend", "pattern"]
        }
        
        # Currency pairs taxonomy
        self.currency_pairs = {
            "major_pairs": ["eur/usd", "usd/jpy", "gbp/usd", "usd/chf", "usd/cad", "aud/usd", "nzd/usd"],
            "yen_crosses": ["eur/jpy", "gbp/jpy", "aud/jpy", "nzd/jpy", "chf/jpy", "cad/jpy"],
            "euro_crosses": ["eur/gbp", "eur/chf", "eur/aud", "eur/nzd", "eur/cad"],
            "commodity_pairs": ["aud/usd", "usd/cad", "nzd/usd"]
        }
        
        # Time sensitivity taxonomy
        self.time_sensitivity = {
            "breaking": 1,  # Immediate impact (minutes to hours)
            "intraday": 2,  # Short-term impact (hours to a day)
            "daily": 3,     # Near-term impact (1-3 days)
            "weekly": 4,    # Medium-term impact (days to weeks)
            "monthly": 5,   # Longer-term impact (weeks to months)
            "quarterly": 6, # Strategic impact (months to quarters)
            "structural": 7 # Fundamental impact (quarters to years)
        }
        
        logger.info("Content categorizer initialized with financial taxonomies")
    
    def categorize(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Categorize content by adding classification metadata.
        
        Args:
            content: Content dictionary with text and other fields
            
        Returns:
            Content with added categorization metadata
        """
        if not content or "text" not in content:
            logger.warning("Cannot categorize content without text field")
            return content
        
        text = content.get("text", "").lower()
        
        # Create categories field if it doesn't exist
        if "categories" not in content:
            content["categories"] = {}
            
        # Identify market sectors
        content["categories"]["sectors"] = self._identify_sectors(text)
        
        # Identify economic indicators
        content["categories"]["indicators"] = self._identify_indicators(text)
        
        # Identify event types
        content["categories"]["event_types"] = self._identify_event_types(text)
        
        # Identify currency pairs
        content["categories"]["currency_pairs"] = self._identify_currency_pairs(text)
        
        # Determine time sensitivity
        content["categories"]["time_sensitivity"] = self._determine_time_sensitivity(content)
        
        # Determine impact level
        content["categories"]["impact"] = self._determine_impact(content)
        
        # Extract keywords
        content["categories"]["keywords"] = self._extract_keywords(text)
        
        # Generate search tags
        content["tags"] = self._generate_tags(content)
        
        logger.debug(f"Categorized content with {len(content['tags'])} tags")
        return content
    
    def _identify_sectors(self, text: str) -> List[str]:
        """Identify market sectors mentioned in the text."""
        sectors = []
        
        for sector, keywords in self.market_sectors.items():
            if any(kw in text for kw in keywords):
                sectors.append(sector)
        
        return sectors or ["general"]
    
    def _identify_indicators(self, text: str) -> List[str]:
        """Identify economic indicators mentioned in the text."""
        indicators = []
        
        for indicator, keywords in self.economic_indicators.items():
            if any(kw in text for kw in keywords):
                indicators.append(indicator)
        
        return indicators
    
    def _identify_event_types(self, text: str) -> List[str]:
        """Identify event types mentioned in the text."""
        event_types = []
        
        for event_type, keywords in self.event_types.items():
            if any(kw in text for kw in keywords):
                event_types.append(event_type)
        
        return event_types or ["news"]
    
    def _identify_currency_pairs(self, text: str) -> List[str]:
        """Identify currency pairs mentioned in the text."""
        pairs = []
        
        # Check for specific currency pair mentions
        for pair_type, pair_list in self.currency_pairs.items():
            for pair in pair_list:
                if pair in text or pair.replace("/", "") in text:
                    pairs.append(pair)
        
        return pairs
    
    def _determine_time_sensitivity(self, content: Dict[str, Any]) -> str:
        """
        Determine time sensitivity of the content.
        
        Returns:
            Time sensitivity category (breaking, intraday, daily, weekly, monthly, quarterly, structural)
        """
        text = content.get("text", "").lower()
        
        # Check for time-related keywords
        if any(kw in text for kw in ["breaking", "alert", "just in", "just announced", "minutes ago"]):
            return "breaking"
            
        if any(kw in text for kw in ["today", "this morning", "this afternoon", "hours ago"]):
            return "intraday"
            
        if any(kw in text for kw in ["yesterday", "tomorrow", "24 hours", "next day"]):
            return "daily"
            
        if any(kw in text for kw in ["this week", "last week", "next week", "weekly"]):
            return "weekly"
            
        if any(kw in text for kw in ["this month", "last month", "next month", "monthly"]):
            return "monthly"
            
        if any(kw in text for kw in ["quarter", "quarterly", "q1", "q2", "q3", "q4"]):
            return "quarterly"
            
        if any(kw in text for kw in ["long term", "long-term", "structural", "fundamental"]):
            return "structural"
            
        # Default based on event types
        event_types = content.get("categories", {}).get("event_types", [])
        if "economic_release" in event_types or "central_bank" in event_types:
            return "daily"
            
        if "geopolitical" in event_types:
            return "weekly"
            
        if "technical" in event_types:
            return "intraday"
            
        # Default
        return "daily"
    
    def _determine_impact(self, content: Dict[str, Any]) -> str:
        """
        Determine market impact level of the content.
        
        Returns:
            Impact level (high, medium, low)
        """
        # Check if impact is already set
        if "impact" in content:
            impact = content["impact"]
            if impact in ["bullish", "bearish"]:
                return "high"
            elif impact == "neutral":
                return "medium"
        
        text = content.get("text", "").lower()
        
        # Check for impact-related keywords
        if any(kw in text for kw in ["significant", "dramatic", "substantial", "major", "high impact"]):
            return "high"
            
        if any(kw in text for kw in ["modest", "moderate", "medium impact"]):
            return "medium"
            
        if any(kw in text for kw in ["minor", "limited", "minimal", "low impact"]):
            return "low"
            
        # Calculate impact based on market sectors
        sectors = content.get("categories", {}).get("sectors", [])
        if "forex" in sectors and len(sectors) > 1:
            return "high"
            
        # Default
        return "medium"
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract important keywords from the text."""
        keywords = set()
        
        # Add all currencies mentioned
        currency_keywords = ["dollar", "euro", "yen", "pound", "franc", "aussie", "kiwi", "loonie",
                           "usd", "eur", "jpy", "gbp", "chf", "aud", "nzd", "cad", "yuan", "cny"]
        
        for currency in currency_keywords:
            if currency in text:
                keywords.add(currency)
        
        # Add important economic terms
        economic_keywords = ["recession", "growth", "inflation", "deflation", "expansion",
                           "contraction", "unemployment", "employment", "rate", "hike", "cut",
                           "policy", "guidance", "forecast", "outlook", "gdp", "cpi", "nfp"]
        
        for term in economic_keywords:
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                keywords.add(term)
        
        # Add technical analysis terms
        technical_keywords = ["support", "resistance", "breakout", "breakdown", "trend",
                            "reversal", "momentum", "oversold", "overbought", "consolidation"]
        
        for term in technical_keywords:
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                keywords.add(term)
        
        return list(keywords)
    
    def _generate_tags(self, content: Dict[str, Any]) -> List[str]:
        """Generate a set of search tags based on categorization."""
        tags = set()
        
        # Add categories
        categories = content.get("categories", {})
        
        # Add sectors
        for sector in categories.get("sectors", []):
            tags.add(f"sector:{sector}")
        
        # Add indicators
        for indicator in categories.get("indicators", []):
            tags.add(f"indicator:{indicator}")
        
        # Add event types
        for event_type in categories.get("event_types", []):
            tags.add(f"event:{event_type}")
        
        # Add currency pairs
        for pair in categories.get("currency_pairs", []):
            tags.add(f"pair:{pair}")
            # Also add the individual currencies
            if "/" in pair:
                base, quote = pair.split("/")
                tags.add(f"currency:{base.lower()}")
                tags.add(f"currency:{quote.lower()}")
        
        # Add time sensitivity
        time_sensitivity = categories.get("time_sensitivity")
        if time_sensitivity:
            tags.add(f"time:{time_sensitivity}")
        
        # Add impact
        impact = categories.get("impact")
        if impact:
            tags.add(f"impact:{impact}")
        
        # Add entities
        entities = content.get("entities", {})
        
        # Add countries
        for country in entities.get("countries", []):
            tags.add(f"country:{country.lower()}")
        
        # Add organizations
        for org in entities.get("organizations", []):
            tags.add(f"org:{org.lower()}")
        
        # Add sentiment
        sentiment = content.get("impact", "")
        if sentiment:
            tags.add(f"sentiment:{sentiment}")
        
        # Add keywords
        for keyword in categories.get("keywords", []):
            tags.add(keyword)
        
        return sorted(list(tags))


# Singleton instance
content_categorizer = ContentCategorizer()


def get_content_categorizer() -> ContentCategorizer:
    """
    Get the ContentCategorizer instance.
    
    Returns:
        The ContentCategorizer singleton
    """
    return content_categorizer 