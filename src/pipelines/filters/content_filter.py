"""
Content filtering for social media data.

This module implements filtering mechanisms to identify forex-related content
from social media sources before sentiment analysis.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import nltk
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
    
try:
    nltk.data.find('stopwords')
except LookupError:
    nltk.download('stopwords')

from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

logger = logging.getLogger(__name__)


class ForexContentFilter:
    """
    Filter to identify forex-related content from social media.
    
    This filter uses keyword matching and regex patterns to filter content
    that is relevant to forex trading and market sentiment.
    """
    
    def __init__(self, min_score: float = 0.2):
        """
        Initialize the content filter.
        
        Args:
            min_score: Minimum relevance score for content to be considered relevant (0-1)
        """
        self.min_score = min_score
        self.stop_words = set(stopwords.words('english'))
        
        # Initialize forex-related dictionaries
        self._init_dictionaries()
        
    def _init_dictionaries(self):
        """Initialize dictionaries of forex-related terms and patterns."""
        # Currency symbols and codes
        self.currencies = {
            "usd", "eur", "gbp", "jpy", "aud", "cad", "chf", "nzd", "cny", "hkd",
            "sgd", "inr", "mxn", "brl", "rub", "krw", "try", "zar", "sek", "nok",
            "dkk", "pln", "thb", "myr", "php", "idr", "dollar", "euro", "pound",
            "yen", "franc", "yuan", "rupee", "peso", "lira", "won", "rand",
            "crown", "krone", "baht", "ringgit",
        }
        
        # Common currency pairs
        self.currency_pairs = {
            "eur/usd", "gbp/usd", "usd/jpy", "usd/chf", "aud/usd", "usd/cad", 
            "nzd/usd", "eur/jpy", "gbp/jpy", "eur/gbp", "eur/chf", "aud/jpy",
            "eurusd", "gbpusd", "usdjpy", "usdchf", "audusd", "usdcad", 
            "nzdusd", "eurjpy", "gbpjpy", "eurgbp", "eurchf", "audjpy",
            "cable", "fiber", "swissy", "loonie", "aussie", "kiwi", "gopher",
        }
        
        # Forex trading terminology
        self.forex_terms = {
            "forex", "fx", "foreign exchange", "currency", "exchange rate",
            "pip", "lot", "margin", "leverage", "spread", "swap", "rollover",
            "bid", "ask", "quote", "base", "position", "long", "short", "hedge",
            "broker", "dealer", "liquidity", "volatility", "trend", "reversal",
            "support", "resistance", "range", "breakout", "channel", "correction",
            "retracement", "fib", "fibonacci", "elliot", "wave", "divergence",
            "convergence", "macd", "rsi", "stochastic", "oscillator", "momentum",
            "ichimoku", "bollinger", "ema", "sma", "wma", "indicator", "signal",
            "chart", "candlestick", "doji", "hammer", "engulfing", "harami",
            "triangle", "flag", "pennant", "head and shoulders", "double top",
            "double bottom", "consolidation", "accumulation", "distribution",
            "scalping", "swing", "day trading", "position trading", "carry trade",
        }
        
        # Central banks and institutions
        self.institutions = {
            "fed", "federal reserve", "ecb", "european central bank", 
            "boe", "bank of england", "boj", "bank of japan", 
            "rba", "reserve bank of australia", "snb", "swiss national bank",
            "pboc", "people's bank of china", "rbi", "reserve bank of india",
            "bank of canada", "riksbank", "norges", "central bank", "fomc",
            "imf", "world bank", "bis", "bank for international settlements",
            "treasury", "ministry of finance", "bundesbank",
        }
        
        # Economic indicators and events
        self.indicators = {
            "gdp", "inflation", "cpi", "ppi", "unemployment", "nonfarm", "payroll",
            "retail sales", "industrial production", "manufacturing", "pmi", "ism",
            "consumer confidence", "business confidence", "sentiment", "housing",
            "existing home", "new home", "building permits", "durable goods",
            "trade balance", "current account", "budget", "deficit", "surplus",
            "interest rate", "rate decision", "monetary policy", "fiscal policy",
            "quantitative easing", "qe", "tapering", "tightening", "hiking",
            "rate hike", "rate cut", "hawkish", "dovish", "statement", "minutes",
            "testimony", "speech", "report", "data", "release", "forecast",
        }
        
        # Compile regex patterns for currency pairs
        self.currency_pair_patterns = [
            re.compile(r'\b(eur|gbp|aud|nzd|usd|cad|jpy|chf|cny)/?(eur|gbp|aud|nzd|usd|cad|jpy|chf|cny)\b', re.IGNORECASE),
            re.compile(r'\b(euro|pound|aussie|kiwi|dollar|loonie|yen|franc|yuan)/?(euro|pound|aussie|kiwi|dollar|loonie|yen|franc|yuan)\b', re.IGNORECASE),
        ]
        
    def filter(self, content: Dict[str, Any]) -> Tuple[bool, float, List[str]]:
        """
        Filter content to determine if it's relevant for forex sentiment analysis.
        
        Args:
            content: Content dictionary with 'text' field
            
        Returns:
            Tuple of (is_relevant, relevance_score, matched_terms)
        """
        if not content or "text" not in content:
            return False, 0.0, []
            
        # Combine title and text if available
        text = content.get("title", "") + " " + content.get("text", "")
        text = text.lower()
        
        # Check for direct currency pair mentions (highest relevance)
        for pair in self.currency_pairs:
            if pair in text:
                return True, 1.0, [pair]
                
        # Check regex patterns for currency pairs
        for pattern in self.currency_pair_patterns:
            matches = pattern.findall(text)
            if matches:
                # Found currency pair pattern
                return True, 0.9, [f"{m[0]}/{m[1]}" for m in matches]
                
        # Tokenize text
        tokens = [word.lower() for word in word_tokenize(text) if word.isalpha()]
        tokens = [word for word in tokens if word not in self.stop_words]
        
        if not tokens:
            return False, 0.0, []
            
        # Check for term matches
        matches = []
        
        # Check currency codes (moderate relevance)
        currency_matches = [word for word in tokens if word in self.currencies]
        matches.extend(currency_matches)
        
        # Check forex terminology (high relevance)
        forex_term_matches = [word for word in tokens if word in self.forex_terms]
        matches.extend(forex_term_matches)
        
        # Check institution names (moderate relevance)
        institution_matches = [word for word in tokens if word in self.institutions]
        matches.extend(institution_matches)
        
        # Check economic indicators (moderate relevance)
        indicator_matches = [word for word in tokens if word in self.indicators]
        matches.extend(indicator_matches)
        
        # Calculate score based on number and type of matches
        if not matches:
            return False, 0.0, []
            
        # Weight by term type
        score = min(1.0, (
            len(currency_matches) * 0.4 + 
            len(forex_term_matches) * 0.8 + 
            len(institution_matches) * 0.6 + 
            len(indicator_matches) * 0.5
        ) / 5)
        
        is_relevant = score >= self.min_score
        return is_relevant, score, matches
        
    def batch_filter(self, contents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter a batch of content items.
        
        Args:
            contents: List of content dictionaries
            
        Returns:
            List of relevant content dictionaries with added metadata
        """
        if not contents:
            return []
            
        relevant_contents = []
        
        for content in contents:
            is_relevant, score, matches = self.filter(content)
            
            if is_relevant:
                # Add metadata
                content_copy = content.copy()
                content_copy["forex_relevance"] = {
                    "score": score,
                    "matched_terms": matches
                }
                relevant_contents.append(content_copy)
                
        return relevant_contents 