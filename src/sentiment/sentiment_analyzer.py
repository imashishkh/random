"""
Sentiment analysis module for social media content.

This module provides sentiment analysis for social media posts
using various sentiment analysis techniques.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

from ..db.mongodb_client import MongoDBClient
from ..db.mongodb_schema import (
    RedditComment, RedditPost, SentimentAnalysisResult,
    SocialMediaPost, SentimentEnum
)
from ..utils.config import SentimentAnalysisConfig

# Set up logging
logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """Sentiment analyzer for social media content."""
    
    def __init__(
        self,
        config: SentimentAnalysisConfig,
        mongodb_client: Optional[MongoDBClient] = None
    ):
        """
        Initialize sentiment analyzer.
        
        Args:
            config: Sentiment analysis configuration
            mongodb_client: MongoDB client for storing results
        """
        self.config = config
        self.mongodb_client = mongodb_client
        self.vader = None
        
        # Download NLTK resources if needed
        try:
            nltk.data.find('vader_lexicon')
        except LookupError:
            nltk.download('vader_lexicon', quiet=True)
        
        # Initialize VADER
        self.vader = SentimentIntensityAnalyzer()
        
        logger.info("SentimentAnalyzer initialized")
    
    def analyze_text(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment of text using VADER.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary with sentiment scores
        """
        if not text or not self.vader:
            return {
                "compound": 0.0,
                "pos": 0.0,
                "neu": 0.0,
                "neg": 0.0
            }
        
        return self.vader.polarity_scores(text)
    
    def get_sentiment_label(self, score: float) -> SentimentEnum:
        """
        Convert sentiment score to label.
        
        Args:
            score: Compound sentiment score (-1 to 1)
            
        Returns:
            Sentiment label (positive, negative, neutral)
        """
        if score >= 0.05:
            return SentimentEnum.POSITIVE
        elif score <= -0.05:
            return SentimentEnum.NEGATIVE
        else:
            return SentimentEnum.NEUTRAL
    
    async def analyze_post(
        self,
        post: Union[SocialMediaPost, RedditPost, RedditComment],
        save_result: bool = True
    ) -> SentimentAnalysisResult:
        """
        Analyze sentiment of a social media post.
        
        Args:
            post: Post to analyze
            save_result: Whether to save result to database
            
        Returns:
            SentimentAnalysisResult
        """
        # Determine text to analyze based on post type
        if isinstance(post, RedditPost):
            text = f"{post.title} {post.content}"
        else:
            text = post.content
        
        # Analyze text
        scores = self.analyze_text(text)
        compound_score = scores["compound"]
        sentiment_label = self.get_sentiment_label(compound_score)
        
        # Create sentiment analysis result
        result = SentimentAnalysisResult(
            id=f"{post.id}_{self.config.model_name}",
            post_id=post.id,
            source=post.source,
            score=compound_score,
            magnitude=abs(compound_score),
            label=sentiment_label,
            analyzer=self.config.model_name,
            analyzed_at=datetime.now(timezone.utc),
            metadata={
                "scores": scores,
                "forex_pairs": post.forex_pairs
            }
        )
        
        # Save to database if requested
        if save_result and self.mongodb_client:
            await self.mongodb_client.insert_sentiment(result)
            
            # Update post with sentiment data
            await self.mongodb_client.update_post_sentiment(
                post_id=post.id,
                source=post.source,
                sentiment_score=compound_score,
                sentiment_label=sentiment_label.value,
                details={"scores": scores}
            )
        
        return result
    
    async def analyze_posts(
        self,
        posts: List[Union[SocialMediaPost, RedditPost, RedditComment]],
        save_results: bool = True
    ) -> List[SentimentAnalysisResult]:
        """
        Analyze sentiment of multiple social media posts.
        
        Args:
            posts: Posts to analyze
            save_results: Whether to save results to database
            
        Returns:
            List of SentimentAnalysisResult
        """
        results = []
        
        for post in posts:
            try:
                result = await self.analyze_post(post, save_result=save_results)
                results.append(result)
            except Exception as e:
                logger.error(f"Error analyzing post {post.id}: {e}")
        
        logger.info(f"Analyzed {len(results)} posts")
        return results
    
    async def analyze_reddit_data(
        self,
        posts: List[RedditPost],
        comments: List[RedditComment]
    ) -> Tuple[List[SentimentAnalysisResult], List[SentimentAnalysisResult]]:
        """
        Analyze sentiment of Reddit posts and comments.
        
        Args:
            posts: Reddit posts to analyze
            comments: Reddit comments to analyze
            
        Returns:
            Tuple of (post sentiment results, comment sentiment results)
        """
        logger.info(f"Analyzing {len(posts)} Reddit posts and {len(comments)} comments")
        
        # Analyze posts
        post_results = await self.analyze_posts(posts)
        
        # Analyze comments
        comment_results = await self.analyze_posts(comments)
        
        return post_results, comment_results
    
    def get_forex_sentiment(
        self,
        results: List[SentimentAnalysisResult],
        forex_pair: str
    ) -> Dict[str, Any]:
        """
        Calculate aggregate sentiment for a specific forex pair.
        
        Args:
            results: List of sentiment analysis results
            forex_pair: Forex pair to calculate sentiment for
            
        Returns:
            Dictionary with aggregate sentiment data
        """
        # Filter results for the specified forex pair
        pair_results = [r for r in results if forex_pair in r.metadata.get("forex_pairs", [])]
        
        if not pair_results:
            return {
                "pair": forex_pair,
                "count": 0,
                "average_score": 0.0,
                "average_magnitude": 0.0,
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "sentiment": "neutral"
            }
        
        # Calculate aggregates
        scores = [r.score for r in pair_results]
        magnitudes = [r.magnitude for r in pair_results]
        labels = [r.label for r in pair_results]
        
        average_score = sum(scores) / len(scores)
        average_magnitude = sum(magnitudes) / len(magnitudes)
        
        positive_count = sum(1 for label in labels if label == SentimentEnum.POSITIVE)
        negative_count = sum(1 for label in labels if label == SentimentEnum.NEGATIVE)
        neutral_count = sum(1 for label in labels if label == SentimentEnum.NEUTRAL)
        
        # Determine overall sentiment
        overall_sentiment = self.get_sentiment_label(average_score)
        
        return {
            "pair": forex_pair,
            "count": len(pair_results),
            "average_score": average_score,
            "average_magnitude": average_magnitude,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "neutral_count": neutral_count,
            "sentiment": overall_sentiment.value
        }