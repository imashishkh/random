"""
VADER sentiment analyzer for social media content.

This module implements a sentiment analyzer using VADER (Valence Aware Dictionary and 
Sentiment Reasoner), which is specifically designed for social media text analysis.
"""

import logging
import re
import string
from typing import Any, Dict, List, Optional, Tuple

import nltk
try:
    nltk.data.find('vader_lexicon')
except LookupError:
    nltk.download('vader_lexicon')

from nltk.sentiment.vader import SentimentIntensityAnalyzer

from ...db.mongodb_schema import SentimentScore

logger = logging.getLogger(__name__)


class VaderSentimentAnalyzer:
    """
    VADER-based sentiment analyzer for social media content.
    
    VADER (Valence Aware Dictionary and Sentiment Reasoner) is a lexicon and rule-based 
    sentiment analysis tool that is specifically attuned to sentiments expressed in 
    social media. It handles emoji, slang, and informal text well.
    """
    
    def __init__(self):
        """Initialize the VADER sentiment analyzer."""
        self.analyzer = SentimentIntensityAnalyzer()
        
        # Add forex-specific terms to VADER lexicon with sentiment values
        self._add_forex_lexicon()
        
    def _add_forex_lexicon(self):
        """Add forex-specific terms to VADER lexicon with appropriate sentiment values."""
        # Positive terms in forex
        bullish_terms = {
            "bullish": 2.0,
            "bull": 1.8,
            "rally": 1.5,
            "uptrend": 1.5,
            "breakout": 1.2,
            "long": 1.0,
            "buy": 1.0,
            "strong": 1.0,
            "strength": 1.0,
            "support": 0.8,
            "higher high": 1.2,
            "higher low": 1.0,
            "oversold": 0.8,
            "undervalued": 0.8,
            "hawkish": 1.5,
            "rate hike": 1.0,
            "upgraded": 1.2,
            "growth": 1.0,
            "expansion": 1.0,
            "recovery": 1.0,
            "outperform": 1.5,
            "beat expectations": 1.5,
        }
        
        # Negative terms in forex
        bearish_terms = {
            "bearish": -2.0,
            "bear": -1.8,
            "sell-off": -1.5,
            "sell off": -1.5,
            "downtrend": -1.5,
            "breakdown": -1.2,
            "short": -1.0,
            "sell": -1.0,
            "weak": -1.0,
            "weakness": -1.0,
            "resistance": -0.8,
            "lower low": -1.2,
            "lower high": -1.0,
            "overbought": -0.8,
            "overvalued": -0.8,
            "dovish": -1.5,
            "rate cut": -1.0,
            "downgraded": -1.2,
            "contraction": -1.0,
            "recession": -1.5,
            "slowdown": -1.0,
            "underperform": -1.5,
            "miss expectations": -1.5,
        }
        
        # Add both positive and negative terms to lexicon
        for term, score in bullish_terms.items():
            self.analyzer.lexicon[term] = score
            
        for term, score in bearish_terms.items():
            self.analyzer.lexicon[term] = score
            
    def preprocess_text(self, text: str) -> str:
        """
        Preprocess text for sentiment analysis.
        
        Args:
            text: Raw text to preprocess
            
        Returns:
            Preprocessed text
        """
        if not text:
            return ""
            
        # Handle cashtags and tickers
        text = re.sub(r'\$([A-Za-z]+)', r'\1', text)
        
        # Handle URLs
        text = re.sub(r'https?://\S+', '', text)
        
        # Remove repeated punctuation
        for p in string.punctuation:
            text = re.sub(f'\\{p}+', f' {p} ', text)
            
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
        
    def analyze(self, text: str) -> Tuple[SentimentScore, Dict[str, Any]]:
        """
        Analyze sentiment of text using VADER.
        
        Args:
            text: Text to analyze
            
        Returns:
            Tuple of (SentimentScore, detailed_scores)
        """
        if not text:
            # Return neutral sentiment for empty text
            return SentimentScore(score=0.0, confidence=0.0), {}
            
        # Preprocess text
        processed_text = self.preprocess_text(text)
        
        # Get VADER scores
        scores = self.analyzer.polarity_scores(processed_text)
        
        # Convert compound score from [-1, 1] to sentiment score
        sentiment_score = scores['compound']
        
        # Calculate confidence based on non-neutrality of pos/neg scores
        # Higher when pos and neg scores are farther apart
        confidence = abs(scores['pos'] - scores['neg'])
        
        # Create SentimentScore object
        sentiment = SentimentScore(
            score=sentiment_score,
            confidence=confidence
        )
        
        # Return sentiment and detailed scores
        return sentiment, scores
        
    def batch_analyze(self, contents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze sentiment for a batch of content.
        
        Args:
            contents: List of content dictionaries with 'text' field
            
        Returns:
            List of content dictionaries with added sentiment information
        """
        if not contents:
            return []
            
        results = []
        
        for content in contents:
            # Skip if no text
            if not content.get("text"):
                continue
                
            # Get text (include title if available)
            text = content.get("title", "") + " " + content.get("text", "")
            
            # Analyze sentiment
            sentiment, details = self.analyze(text)
            
            # Add sentiment to content
            content_copy = content.copy()
            content_copy["vader_sentiment"] = {
                "score": sentiment.score,
                "confidence": sentiment.confidence,
                "pos": details.get("pos"),
                "neg": details.get("neg"),
                "neu": details.get("neu"),
            }
            
            results.append(content_copy)
            
        return results 