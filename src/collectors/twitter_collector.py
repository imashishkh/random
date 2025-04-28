"""
Twitter data collector for the Forex sentiment analysis system.

This module implements a Twitter collector that fetches tweets related to forex trading
using Twitter API v2.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import tweepy
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings
from ..db.mongodb_schema import Tweet


logger = logging.getLogger(__name__)


class TwitterCollector:
    """
    Collector for Twitter data related to forex trading.
    
    This class handles the collection of tweets related to forex trading using the
    Twitter API v2. It supports both search queries and streaming.
    """
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: str,
        access_token_secret: str,
        bearer_token: str,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        query: str = "forex OR FX OR currency trading OR foreign exchange",
        languages: List[str] = ["en"],
        batch_size: int = 100,
        poll_interval: int = 60,
    ):
        """
        Initialize the Twitter collector.
        
        Args:
            api_key: Twitter API key
            api_secret: Twitter API secret
            access_token: Twitter access token
            access_token_secret: Twitter access token secret
            bearer_token: Twitter bearer token
            callback: Function to call with each batch of tweets
            query: Search query for tweets
            languages: List of language codes to filter tweets
            batch_size: Number of tweets to collect in each batch
            poll_interval: Interval in seconds between API calls
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.access_token_secret = access_token_secret  
        self.bearer_token = bearer_token
        self.callback = callback
        self.query = query
        self.languages = languages
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        
        self.client = None
        self.stream = None
        self.is_running = False
        self._initialize_client()
        
        # Keep track of the most recent tweet ID to avoid duplicates
        self.most_recent_id = None
        
    def _initialize_client(self) -> None:
        """Initialize the Twitter API client."""
        try:
            self.client = tweepy.Client(
                bearer_token=self.bearer_token,
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret,
                wait_on_rate_limit=True,
            )
            logger.info("Twitter API client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Twitter API client: {str(e)}")
            raise
            
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=60))
    async def _fetch_tweets(self) -> List[Dict[str, Any]]:
        """
        Fetch tweets using the Twitter API.
        
        Returns:
            List of tweets as dictionaries
        """
        try:
            # Construct the query with language filter
            full_query = f"{self.query} lang:{' OR lang:'.join(self.languages)}"
            
            # Set up parameters for the search
            params = {
                "query": full_query,
                "max_results": self.batch_size,
                "tweet.fields": "created_at,public_metrics,entities,lang,author_id",
                "expansions": "author_id",
                "user.fields": "username,name,description,public_metrics",
            }
            
            # Add since_id if we have a most recent ID
            if self.most_recent_id:
                params["since_id"] = self.most_recent_id
                
            # Execute the search asynchronously
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.client.search_recent_tweets(**params)
            )
            
            if not response.data:
                logger.info("No new tweets found")
                return []
                
            # Update most recent ID
            self.most_recent_id = max(int(t.id) for t in response.data)
            
            # Process tweets into our schema format
            processed_tweets = []
            for tweet in response.data:
                # Create user dictionary for metadata
                user = None
                if response.includes and "users" in response.includes:
                    for u in response.includes["users"]:
                        if u.id == tweet.author_id:
                            user = {
                                "id": u.id,
                                "username": u.username,
                                "name": u.name,
                                "description": u.description,
                                "followers_count": u.public_metrics["followers_count"] 
                                if hasattr(u, "public_metrics") else 0,
                            }
                
                # Extract hashtags and mentions
                hashtags = []
                mentions = []
                if hasattr(tweet, "entities") and tweet.entities:
                    if "hashtags" in tweet.entities:
                        hashtags = [h["tag"] for h in tweet.entities["hashtags"]]
                    if "mentions" in tweet.entities:
                        mentions = [m["username"] for m in tweet.entities["mentions"]]
                
                # Create Tweet model
                tweet_dict = Tweet(
                    id=tweet.id,
                    source="twitter",
                    content=tweet.text,
                    created_at=tweet.created_at,
                    author_id=tweet.author_id,
                    metadata={"user": user} if user else {},
                    collected_at=datetime.utcnow(),
                    retweet_count=tweet.public_metrics["retweet_count"] if hasattr(tweet, "public_metrics") else 0,
                    like_count=tweet.public_metrics["like_count"] if hasattr(tweet, "public_metrics") else 0,
                    reply_count=tweet.public_metrics["reply_count"] if hasattr(tweet, "public_metrics") else 0,
                    quote_count=tweet.public_metrics["quote_count"] if hasattr(tweet, "public_metrics") else 0,
                    hashtags=hashtags,
                    mentions=mentions,
                    is_retweet="RT @" in tweet.text,
                    lang=tweet.lang,
                ).dict()
                
                processed_tweets.append(tweet_dict)
            
            logger.info(f"Fetched {len(processed_tweets)} tweets")
            return processed_tweets
            
        except Exception as e:
            logger.error(f"Error fetching tweets: {str(e)}")
            raise
            
    async def _collection_loop(self) -> None:
        """Main collection loop that periodically fetches tweets."""
        while self.is_running:
            try:
                tweets = await self._fetch_tweets()
                
                if tweets and self.callback:
                    await asyncio.to_thread(self.callback, tweets)
                    
                # Sleep for the poll interval
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"Error in Twitter collection loop: {str(e)}")
                # Sleep before retrying
                await asyncio.sleep(self.poll_interval)
    
    async def start(self) -> None:
        """Start the Twitter collector."""
        if self.is_running:
            logger.warning("Twitter collector is already running")
            return
            
        logger.info("Starting Twitter collector")
        self.is_running = True
        
        # Start the collection loop
        asyncio.create_task(self._collection_loop())
        
    async def stop(self) -> None:
        """Stop the Twitter collector."""
        if not self.is_running:
            logger.warning("Twitter collector is not running")
            return
            
        logger.info("Stopping Twitter collector")
        self.is_running = False


def create_twitter_collector(callback: Callable[[Dict[str, Any]], None] = None) -> TwitterCollector:
    """
    Create a Twitter collector using settings from the config.
    
    Args:
        callback: Function to call with each batch of tweets
        
    Returns:
        Configured TwitterCollector instance
    """
    return TwitterCollector(
        api_key=settings.twitter.api_key,
        api_secret=settings.twitter.api_secret,
        access_token=settings.twitter.access_token,
        access_token_secret=settings.twitter.access_token_secret,
        bearer_token=settings.twitter.bearer_token,
        callback=callback,
        query=settings.twitter.query,
        languages=settings.twitter.languages,
        batch_size=settings.twitter.batch_size,
        poll_interval=settings.twitter.poll_interval,
    ) 