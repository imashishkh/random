"""
Twitter data collector for sentiment analysis.

This module implements a collector for Twitter/X data using the Twitter API v2.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import tweepy
from tweepy import Client, Response

from .base import BaseCollector, DataType
from ...db.mongodb_schema import DataSource, DataSourceType

logger = logging.getLogger(__name__)


class TwitterCollector(BaseCollector):
    """
    Twitter data collector using Twitter API v2.
    
    This collector fetches tweets based on keywords, hashtags, and users,
    focusing on forex-related content for sentiment analysis.
    """
    
    def __init__(
        self,
        bearer_token: str,
        name: str = "twitter_collector",
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the Twitter collector.
        
        Args:
            bearer_token: Twitter API bearer token
            name: Collector name
            config: Configuration dictionary with optional fields:
                - keywords: List of keywords to track
                - hashtags: List of hashtags to track
                - users: List of user IDs to track
                - max_tweets_per_query: Maximum tweets per query (default: 100)
                - languages: List of language codes (default: ['en'])
                - kafka_topic: Kafka topic to publish to (default: 'twitter_forex')
                - batch_size: Number of tweets to batch before publishing (default: 100)
        """
        super().__init__(name, config)
        self.bearer_token = bearer_token
        self.client = Client(bearer_token=bearer_token)
        self.keywords = self.config.get("keywords", [])
        self.hashtags = self.config.get("hashtags", [])
        self.users = self.config.get("users", [])
        self.max_tweets = self.config.get("max_tweets_per_query", 100)
        self.languages = self.config.get("languages", ["en"])
        self.kafka_topic = self.config.get("kafka_topic", "twitter_forex")
        self.batch_size = self.config.get("batch_size", 100)
        
        # Internal state
        self.tweet_buffer = []
        self.last_tweet_id = None
        self.rate_limit_reset = 0
        
    async def start(self):
        """Start the Twitter collector."""
        await super().start()
        
        # Initialize tweet buffer
        self.tweet_buffer = []
        
        # Schedule tasks for collection
        if self.keywords or self.hashtags:
            self.schedule_task(self.fetch_periodic(interval=60, callback=self.process_tweets))
            
        if self.users:
            self.schedule_task(self.fetch_user_tweets_periodic(interval=300))
            
    async def stop(self):
        """Stop the Twitter collector and flush any remaining tweets."""
        # Process any remaining tweets in buffer
        if self.tweet_buffer:
            await self.publish_tweets(self.tweet_buffer)
            self.tweet_buffer = []
            
        await super().stop()
        
    async def collect(self) -> List[Dict[str, Any]]:
        """
        Collect tweets based on keywords and hashtags.
        
        Returns:
            List of collected tweets as dictionaries
        """
        query = self._build_search_query()
        if not query:
            logger.warning("No search query parameters specified")
            return []
            
        try:
            # Handle rate limiting
            await self._handle_rate_limits()
            
            # Execute search query
            logger.debug(f"Searching Twitter with query: {query}")
            response = self.client.search_recent_tweets(
                query=query,
                max_results=self.max_tweets,
                since_id=self.last_tweet_id,
                tweet_fields=["created_at", "lang", "public_metrics", "entities", "context_annotations"],
                user_fields=["username", "name", "verified", "description", "public_metrics"],
                expansions=["author_id", "referenced_tweets.id", "entities.mentions.username"],
            )
            
            # Update rate limit info
            self._update_rate_limit_info(response)
            
            # Process tweets
            tweets = self._process_response(response)
            
            # Update last tweet ID if we got results
            if tweets and len(tweets) > 0:
                # Sort by ID to get most recent
                sorted_tweets = sorted(tweets, key=lambda x: int(x.get("id", "0")), reverse=True)
                self.last_tweet_id = sorted_tweets[0].get("id")
                
            return tweets
            
        except tweepy.TooManyRequests:
            logger.warning("Rate limit exceeded. Waiting before next request.")
            self.rate_limit_reset = time.time() + 900  # 15 minutes
            return []
            
        except Exception as e:
            logger.exception(f"Error collecting tweets: {e}")
            return []
            
    async def fetch_user_tweets_periodic(self, interval: float = 300):
        """
        Periodically fetch tweets from specified users.
        
        Args:
            interval: Collection interval in seconds
        """
        while self.running:
            try:
                # Split users into chunks to avoid hitting rate limits
                user_chunks = [self.users[i:i + 10] for i in range(0, len(self.users), 10)]
                
                for chunk in user_chunks:
                    # Handle rate limiting
                    await self._handle_rate_limits()
                    
                    for user_id in chunk:
                        try:
                            response = self.client.get_users_tweets(
                                id=user_id,
                                max_results=10,
                                tweet_fields=["created_at", "lang", "public_metrics", "entities"],
                                exclude=["retweets", "replies"],
                            )
                            
                            # Update rate limit info
                            self._update_rate_limit_info(response)
                            
                            # Process tweets
                            tweets = self._process_response(response)
                            if tweets:
                                self.tweet_buffer.extend(tweets)
                                
                                # Publish when batch size is reached
                                if len(self.tweet_buffer) >= self.batch_size:
                                    await self.publish_tweets(self.tweet_buffer)
                                    self.tweet_buffer = []
                                    
                        except Exception as e:
                            logger.exception(f"Error fetching tweets for user {user_id}: {e}")
                            
                        # Sleep briefly between user requests to avoid hitting rate limits
                        await asyncio.sleep(1)
                    
                    # Sleep between chunks
                    await asyncio.sleep(10)
                
                # Wait until next collection interval
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                logger.info("User tweet collection cancelled")
                break
                
            except Exception as e:
                logger.exception(f"Error in user tweet collection: {e}")
                await asyncio.sleep(interval)  # Sleep before retry
                
    async def process_tweets(self, tweets: List[Dict[str, Any]]):
        """
        Process collected tweets and add to the buffer.
        
        Args:
            tweets: List of tweet dictionaries
        """
        if not tweets:
            return
            
        # Add tweets to buffer
        self.tweet_buffer.extend(tweets)
        
        # When buffer reaches batch size, publish to Kafka
        if len(self.tweet_buffer) >= self.batch_size:
            await self.publish_tweets(self.tweet_buffer)
            self.tweet_buffer = []
            
    async def publish_tweets(self, tweets: List[Dict[str, Any]]):
        """
        Publish tweets to Kafka.
        
        Args:
            tweets: List of tweet dictionaries
        """
        if not tweets:
            return
            
        try:
            # TODO: Implement Kafka producer integration
            # For now, just log the number of tweets
            logger.info(f"Publishing {len(tweets)} tweets to Kafka topic '{self.kafka_topic}'")
            
        except Exception as e:
            logger.exception(f"Error publishing tweets to Kafka: {e}")
            
    def _build_search_query(self) -> str:
        """
        Build Twitter search query from keywords and hashtags.
        
        Returns:
            Query string for Twitter API
        """
        query_parts = []
        
        # Add keywords
        if self.keywords:
            keyword_query = " OR ".join([f'"{kw}"' for kw in self.keywords])
            query_parts.append(f"({keyword_query})")
            
        # Add hashtags
        if self.hashtags:
            hashtag_query = " OR ".join([f"#{tag}" for tag in self.hashtags])
            query_parts.append(f"({hashtag_query})")
            
        # Add language filter
        if self.languages:
            lang_filter = " OR ".join([f"lang:{lang}" for lang in self.languages])
            query_parts.append(f"({lang_filter})")
            
        return " ".join(query_parts)
        
    def _process_response(self, response: Response) -> List[Dict[str, Any]]:
        """
        Process Twitter API response into standardized dictionary format.
        
        Args:
            response: Twitter API response object
            
        Returns:
            List of processed tweet dictionaries
        """
        if not response or not response.data:
            return []
            
        tweets = []
        users = {user.id: user for user in (response.includes.get("users", []) if response.includes else [])}
        
        for tweet in response.data:
            # Create user info dict
            user_info = {}
            if hasattr(tweet, "author_id") and tweet.author_id in users:
                user = users[tweet.author_id]
                user_info = {
                    "id": user.id,
                    "username": user.username,
                    "name": user.name,
                    "verified": user.verified,
                    "followers_count": user.public_metrics.get("followers_count") if hasattr(user, "public_metrics") else None,
                }
                
            # Create standardized tweet dict
            tweet_dict = {
                "id": tweet.id,
                "text": tweet.text,
                "created_at": tweet.created_at.isoformat() if hasattr(tweet, "created_at") and tweet.created_at else None,
                "lang": tweet.lang if hasattr(tweet, "lang") else None,
                "user": user_info,
                "public_metrics": tweet.public_metrics if hasattr(tweet, "public_metrics") else {},
                "entities": tweet.entities if hasattr(tweet, "entities") else {},
                "source": "twitter",
                "collected_at": datetime.utcnow().isoformat(),
                "data_source": self._get_data_source().dict(),
            }
            
            tweets.append(tweet_dict)
            
        return tweets
        
    async def _handle_rate_limits(self):
        """Handle Twitter API rate limits by waiting if necessary."""
        if self.rate_limit_reset > time.time():
            wait_time = self.rate_limit_reset - time.time()
            logger.info(f"Rate limit active. Waiting {wait_time:.1f} seconds...")
            await asyncio.sleep(wait_time + 1)  # Add 1 second buffer
            
    def _update_rate_limit_info(self, response: Response):
        """
        Update rate limit information from Twitter API response.
        
        Args:
            response: Twitter API response object
        """
        # Twitter API v2 with tweepy doesn't expose rate limit info in the same way
        # This is a placeholder for future implementation
        pass
        
    def _get_data_source(self) -> DataSource:
        """
        Create a DataSource object for Twitter.
        
        Returns:
            DataSource object
        """
        return DataSource(
            name="Twitter",
            url="https://twitter.com",
            type=DataSourceType.SOCIAL,
            reliability_score=0.7,  # Moderate reliability score for social media
        ) 