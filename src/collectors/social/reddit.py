"""
Reddit data collector for sentiment analysis.

This module implements a collector for Reddit data using the PRAW library.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import praw
from praw.models import Comment, Submission

from .base import BaseCollector, DataType
from ...db.mongodb_schema import DataSource, DataSourceType

logger = logging.getLogger(__name__)


class RedditCollector(BaseCollector):
    """
    Reddit data collector using PRAW.
    
    This collector fetches posts and comments from specified subreddits
    and searches, focusing on forex-related content for sentiment analysis.
    """
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        name: str = "reddit_collector",
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the Reddit collector.
        
        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: User agent string for Reddit API
            name: Collector name
            config: Configuration dictionary with optional fields:
                - subreddits: List of subreddits to monitor
                - keywords: List of keywords to search for
                - search_time: Time window to search (default: 'day')
                - max_posts: Maximum posts per subreddit (default: 25)
                - max_comments: Maximum comments per post (default: 50)
                - kafka_topic: Kafka topic to publish to (default: 'reddit_forex')
                - batch_size: Number of items to batch before publishing (default: 100)
        """
        super().__init__(name, config)
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        self.subreddits = self.config.get("subreddits", [])
        self.keywords = self.config.get("keywords", [])
        self.search_time = self.config.get("search_time", "day")  # hour, day, week, month, year, all
        self.max_posts = self.config.get("max_posts", 25)
        self.max_comments = self.config.get("max_comments", 50)
        self.kafka_topic = self.config.get("kafka_topic", "reddit_forex")
        self.batch_size = self.config.get("batch_size", 100)
        
        # Internal state
        self.content_buffer = []
        self.processed_ids = set()
        
    async def start(self):
        """Start the Reddit collector."""
        await super().start()
        
        # Initialize buffer
        self.content_buffer = []
        
        # Schedule tasks
        if self.subreddits:
            self.schedule_task(self.fetch_subreddits_periodic(interval=1800))  # 30 minutes
            
        if self.keywords:
            self.schedule_task(self.fetch_keyword_search_periodic(interval=3600))  # 1 hour
            
    async def stop(self):
        """Stop the Reddit collector and flush any remaining content."""
        # Process any remaining content in buffer
        if self.content_buffer:
            await self.publish_content(self.content_buffer)
            self.content_buffer = []
            
        await super().stop()
        
    async def collect(self) -> List[Dict[str, Any]]:
        """
        Collect posts from specified subreddits.
        
        Returns:
            List of collected posts as dictionaries
        """
        return await self.fetch_subreddit_content()
        
    async def fetch_subreddits_periodic(self, interval: float = 1800):
        """
        Periodically fetch content from specified subreddits.
        
        Args:
            interval: Collection interval in seconds
        """
        while self.running:
            try:
                posts = await self.fetch_subreddit_content()
                
                if posts:
                    # Add to buffer
                    self.content_buffer.extend(posts)
                    
                    # Publish when batch size is reached
                    if len(self.content_buffer) >= self.batch_size:
                        await self.publish_content(self.content_buffer)
                        self.content_buffer = []
                        
                # Wait until next collection interval
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                logger.info("Subreddit collection cancelled")
                break
                
            except Exception as e:
                logger.exception(f"Error in subreddit collection: {e}")
                await asyncio.sleep(interval)  # Sleep before retry
                
    async def fetch_keyword_search_periodic(self, interval: float = 3600):
        """
        Periodically search Reddit for specified keywords.
        
        Args:
            interval: Collection interval in seconds
        """
        while self.running:
            try:
                posts = await self.fetch_keyword_content()
                
                if posts:
                    # Add to buffer
                    self.content_buffer.extend(posts)
                    
                    # Publish when batch size is reached
                    if len(self.content_buffer) >= self.batch_size:
                        await self.publish_content(self.content_buffer)
                        self.content_buffer = []
                        
                # Wait until next collection interval
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                logger.info("Keyword search cancelled")
                break
                
            except Exception as e:
                logger.exception(f"Error in keyword search: {e}")
                await asyncio.sleep(interval)  # Sleep before retry
                
    async def fetch_subreddit_content(self) -> List[Dict[str, Any]]:
        """
        Fetch posts and comments from specified subreddits.
        
        Returns:
            List of processed Reddit posts and comments
        """
        collected_content = []
        
        # Use asyncio to run Reddit API calls (which are blocking) in a thread pool
        loop = asyncio.get_event_loop()
        
        for subreddit_name in self.subreddits:
            try:
                # Get subreddit posts
                subreddit = await loop.run_in_executor(
                    None, lambda: self.reddit.subreddit(subreddit_name)
                )
                
                # Get top posts for the time period
                posts = await loop.run_in_executor(
                    None, lambda: list(subreddit.top(time_filter=self.search_time, limit=self.max_posts))
                )
                
                # Process each post
                for post in posts:
                    # Skip if already processed
                    if post.id in self.processed_ids:
                        continue
                        
                    # Process post
                    post_dict = await self._process_submission(post)
                    if post_dict:
                        collected_content.append(post_dict)
                        self.processed_ids.add(post.id)
                        
                    # Fetch and process comments
                    await loop.run_in_executor(None, post.comments.replace_more, limit=0)
                    comments = await loop.run_in_executor(None, lambda: post.comments.list())
                    
                    # Limit comments
                    comments = comments[:min(len(comments), self.max_comments)]
                    
                    for comment in comments:
                        # Skip if already processed
                        if comment.id in self.processed_ids:
                            continue
                            
                        # Process comment
                        comment_dict = await self._process_comment(comment, post.id)
                        if comment_dict:
                            collected_content.append(comment_dict)
                            self.processed_ids.add(comment.id)
                            
                    # Prevent processing too much at once - sleep briefly
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                logger.exception(f"Error fetching content from subreddit {subreddit_name}: {e}")
                
        return collected_content
        
    async def fetch_keyword_content(self) -> List[Dict[str, Any]]:
        """
        Search Reddit for posts containing specified keywords.
        
        Returns:
            List of processed Reddit posts and comments
        """
        collected_content = []
        
        # Use asyncio to run Reddit API calls in a thread pool
        loop = asyncio.get_event_loop()
        
        for keyword in self.keywords:
            try:
                # Search for keyword
                search_results = await loop.run_in_executor(
                    None, 
                    lambda: list(self.reddit.subreddit("all").search(
                        query=keyword, 
                        time_filter=self.search_time, 
                        limit=self.max_posts
                    ))
                )
                
                # Process each post
                for post in search_results:
                    # Skip if already processed
                    if post.id in self.processed_ids:
                        continue
                        
                    # Process post
                    post_dict = await self._process_submission(post)
                    if post_dict:
                        collected_content.append(post_dict)
                        self.processed_ids.add(post.id)
                        
                    # Fetch and process comments (limited)
                    await loop.run_in_executor(None, post.comments.replace_more, limit=0)
                    comments = await loop.run_in_executor(None, lambda: post.comments.list())
                    
                    # Limit comments
                    comments = comments[:min(len(comments), self.max_comments)]
                    
                    for comment in comments:
                        # Skip if already processed
                        if comment.id in self.processed_ids:
                            continue
                            
                        # Process comment
                        comment_dict = await self._process_comment(comment, post.id)
                        if comment_dict:
                            collected_content.append(comment_dict)
                            self.processed_ids.add(comment.id)
                            
                    # Prevent processing too much at once - sleep briefly
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                logger.exception(f"Error searching for keyword {keyword}: {e}")
                
        return collected_content
        
    async def publish_content(self, content: List[Dict[str, Any]]):
        """
        Publish Reddit content to Kafka.
        
        Args:
            content: List of processed Reddit content dictionaries
        """
        if not content:
            return
            
        try:
            # TODO: Implement Kafka producer integration
            # For now, just log the number of items
            logger.info(f"Publishing {len(content)} Reddit items to Kafka topic '{self.kafka_topic}'")
            
        except Exception as e:
            logger.exception(f"Error publishing Reddit content to Kafka: {e}")
            
    async def _process_submission(self, submission: Submission) -> Dict[str, Any]:
        """
        Process a Reddit submission into a standardized dictionary.
        
        Args:
            submission: Reddit submission object
            
        Returns:
            Processed submission dictionary
        """
        try:
            # Extract submission data
            created_at = datetime.fromtimestamp(submission.created_utc)
            
            # Create standardized submission dict
            submission_dict = {
                "id": submission.id,
                "title": submission.title,
                "text": submission.selftext,
                "url": submission.url,
                "permalink": f"https://reddit.com{submission.permalink}",
                "created_at": created_at.isoformat(),
                "subreddit": submission.subreddit.display_name,
                "author": submission.author.name if submission.author else "[deleted]",
                "score": submission.score,
                "upvote_ratio": submission.upvote_ratio,
                "num_comments": submission.num_comments,
                "is_post": True,
                "source": "reddit",
                "collected_at": datetime.utcnow().isoformat(),
                "data_source": self._get_data_source().dict(),
            }
            
            return submission_dict
            
        except Exception as e:
            logger.exception(f"Error processing submission {submission.id}: {e}")
            return None
            
    async def _process_comment(self, comment: Comment, post_id: str) -> Dict[str, Any]:
        """
        Process a Reddit comment into a standardized dictionary.
        
        Args:
            comment: Reddit comment object
            post_id: ID of parent post
            
        Returns:
            Processed comment dictionary
        """
        try:
            # Extract comment data
            created_at = datetime.fromtimestamp(comment.created_utc)
            
            # Create standardized comment dict
            comment_dict = {
                "id": comment.id,
                "post_id": post_id,
                "text": comment.body,
                "permalink": f"https://reddit.com{comment.permalink}",
                "created_at": created_at.isoformat(),
                "subreddit": comment.subreddit.display_name,
                "author": comment.author.name if comment.author else "[deleted]",
                "score": comment.score,
                "is_post": False,
                "source": "reddit",
                "collected_at": datetime.utcnow().isoformat(),
                "data_source": self._get_data_source().dict(),
            }
            
            return comment_dict
            
        except Exception as e:
            logger.exception(f"Error processing comment {comment.id}: {e}")
            return None
            
    def _get_data_source(self) -> DataSource:
        """
        Create a DataSource object for Reddit.
        
        Returns:
            DataSource object
        """
        return DataSource(
            name="Reddit",
            url="https://reddit.com",
            type=DataSourceType.SOCIAL,
            reliability_score=0.6,  # Moderate reliability for social media
        ) 