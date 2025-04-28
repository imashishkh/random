"""
Reddit collector module for fetching posts and comments from relevant subreddits.

This module uses PRAW (Python Reddit API Wrapper) to collect data from Reddit
for sentiment analysis of Forex-related content.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import praw
from praw.models import Comment, Submission
from prawcore.exceptions import PrawcoreException

from ..db.mongodb_client import MongoDBClient
from ..db.mongodb_schema import RedditComment, RedditPost
from ..utils.config import RedditConfig
from ..utils.forex_utils import extract_forex_pairs

logger = logging.getLogger(__name__)


class RedditCollector:
    """Collector for Reddit data."""
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        subreddits: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        mongodb_client: Optional[MongoDBClient] = None,
    ):
        """
        Initialize Reddit collector.
        
        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: Reddit API user agent
            username: Reddit username (optional)
            password: Reddit password (optional)
            subreddits: List of subreddits to monitor
            keywords: List of keywords to filter by
            mongodb_client: MongoDB client for storing data
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.username = username
        self.password = password
        
        self.subreddits = subreddits or [
            "forex", "forextrading", "investing", "economy", "finance",
            "trading", "wallstreetbets", "stocks", "cryptocurrency",
            "foreignexchange", "UKInvesting", "CanadianInvestor"
        ]
        
        self.keywords = keywords or [
            "forex", "currency", "exchange rate", "pip", "trend", "chart pattern",
            "technical analysis", "fundamental analysis", "indicator",
            "bull market", "bear market", "volatility", "strength", "weak", "strong",
            # Currency pairs
            "eurusd", "eur/usd", "eurjpy", "eur/jpy", "gbpusd", "gbp/usd",
            "audusd", "aud/usd", "usdjpy", "usd/jpy", "usdchf", "usd/chf",
            "nzdusd", "nzd/usd", "usdcad", "usd/cad", "eurgbp", "eur/gbp"
        ]
        
        self.reddit = None
        self.mongodb_client = mongodb_client
        self.post_limit = 100  # Default post limit per subreddit
        self.comment_limit = 200  # Default comment limit per post
        
        # Setup regex patterns for keywords
        self.keyword_pattern = re.compile(
            r'\b(' + '|'.join(re.escape(kw) for kw in self.keywords) + r')\b', 
            re.IGNORECASE
        )
    
    def initialize(self) -> None:
        """Initialize Reddit client."""
        try:
            if self.username and self.password:
                self.reddit = praw.Reddit(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    user_agent=self.user_agent,
                    username=self.username,
                    password=self.password,
                )
            else:
                self.reddit = praw.Reddit(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    user_agent=self.user_agent,
                )
            
            logger.info("Reddit client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Reddit client: {e}")
            raise
    
    @classmethod
    def from_config(cls, config: RedditConfig, mongodb_client: Optional[MongoDBClient] = None) -> 'RedditCollector':
        """
        Create a RedditCollector from configuration.
        
        Args:
            config: Reddit configuration
            mongodb_client: MongoDB client
            
        Returns:
            RedditCollector instance
        """
        collector = cls(
            client_id=config.client_id,
            client_secret=config.client_secret,
            user_agent=config.user_agent,
            username=config.username,
            password=config.password,
            subreddits=config.subreddits,
            keywords=config.keywords,
            mongodb_client=mongodb_client,
        )
        collector.initialize()
        return collector
    
    def _contains_keywords(self, text: str) -> bool:
        """
        Check if text contains any of the keywords.
        
        Args:
            text: Text to check
            
        Returns:
            True if text contains any keyword, False otherwise
        """
        if not text:
            return False
        
        return bool(self.keyword_pattern.search(text))
    
    def _extract_post_metadata(self, submission: Submission) -> Dict[str, Any]:
        """
        Extract metadata from a Reddit post.
        
        Args:
            submission: Reddit submission
            
        Returns:
            Post metadata
        """
        return {
            "url": submission.url,
            "permalink": f"https://www.reddit.com{submission.permalink}",
            "domain": submission.domain,
            "is_video": submission.is_video,
            "is_original_content": submission.is_original_content,
            "over_18": submission.over_18,
            "spoiler": submission.spoiler,
            "stickied": submission.stickied,
            "locked": submission.locked,
            "archived": submission.archived,
            "distinguished": submission.distinguished,
        }
    
    def _extract_comment_metadata(self, comment: Comment) -> Dict[str, Any]:
        """
        Extract metadata from a Reddit comment.
        
        Args:
            comment: Reddit comment
            
        Returns:
            Comment metadata
        """
        return {
            "permalink": f"https://www.reddit.com{comment.permalink}",
            "stickied": comment.stickied,
            "distinguished": comment.distinguished,
            "is_submitter": comment.is_submitter,
            "depth": getattr(comment, "depth", 0),
        }
    
    def _convert_to_reddit_post(self, submission: Submission) -> RedditPost:
        """
        Convert a PRAW Submission to RedditPost.
        
        Args:
            submission: Reddit submission
            
        Returns:
            RedditPost instance
        """
        # Extract forex pairs from title and body
        body_text = submission.selftext if submission.selftext else ""
        forex_pairs = extract_forex_pairs(f"{submission.title} {body_text}")
        
        # Get created UTC timestamp
        created_at = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
        
        # Create RedditPost
        return RedditPost(
            id=submission.id,
            source="reddit",
            content=submission.selftext,
            created_at=created_at,
            collected_at=datetime.now(timezone.utc),
            author_id=str(submission.author.name if submission.author else "[deleted]"),
            metadata=self._extract_post_metadata(submission),
            forex_pairs=list(forex_pairs),
            title=submission.title,
            score=submission.score,
            upvote_ratio=submission.upvote_ratio,
            num_comments=submission.num_comments,
            is_self=submission.is_self,
            flair=submission.link_flair_text,
            subreddit=submission.subreddit.display_name
        )
    
    def _convert_to_reddit_comment(self, comment: Comment, post_id: str) -> RedditComment:
        """
        Convert a PRAW Comment to RedditComment.
        
        Args:
            comment: Reddit comment
            post_id: Parent post ID
            
        Returns:
            RedditComment instance
        """
        # Extract forex pairs from comment body
        forex_pairs = extract_forex_pairs(comment.body)
        
        # Get created UTC timestamp
        created_at = datetime.fromtimestamp(comment.created_utc, tz=timezone.utc)
        
        # Get parent comment ID if it exists
        parent_comment_id = None
        if comment.parent_id.startswith("t1_"):  # t1_ prefix indicates a comment
            parent_comment_id = comment.parent_id[3:]  # Remove t1_ prefix
        
        # Create RedditComment
        return RedditComment(
            id=comment.id,
            source="reddit",
            content=comment.body,
            created_at=created_at,
            collected_at=datetime.now(timezone.utc),
            author_id=str(comment.author.name if comment.author else "[deleted]"),
            metadata=self._extract_comment_metadata(comment),
            forex_pairs=list(forex_pairs),
            post_id=post_id,
            score=comment.score,
            is_submitter=comment.is_submitter,
            parent_comment_id=parent_comment_id,
            subreddit=comment.subreddit.display_name
        )
    
    async def collect_posts(self, time_filter: str = "day", limit: int = None) -> List[RedditPost]:
        """
        Collect posts from monitored subreddits.
        
        Args:
            time_filter: Time filter for posts (hour, day, week, month, year, all)
            limit: Maximum number of posts to collect per subreddit
            
        Returns:
            List of collected RedditPost objects
        """
        if not self.reddit:
            self.initialize()
        
        post_limit = limit or self.post_limit
        collected_posts = []
        
        for subreddit_name in self.subreddits:
            try:
                logger.info(f"Collecting posts from r/{subreddit_name}")
                subreddit = self.reddit.subreddit(subreddit_name)
                
                # Get top posts for the time period
                for submission in subreddit.top(time_filter=time_filter, limit=post_limit):
                    if self._contains_keywords(f"{submission.title} {submission.selftext}"):
                        try:
                            reddit_post = self._convert_to_reddit_post(submission)
                            collected_posts.append(reddit_post)
                            
                            # Save to MongoDB if client is available
                            if self.mongodb_client:
                                await self.mongodb_client.insert_post(reddit_post)
                        except Exception as e:
                            logger.error(f"Error processing post {submission.id}: {e}")
                
                # Also get new posts
                for submission in subreddit.new(limit=post_limit):
                    if self._contains_keywords(f"{submission.title} {submission.selftext}"):
                        try:
                            reddit_post = self._convert_to_reddit_post(submission)
                            
                            # Check if post already collected (avoid duplicates)
                            if not any(post.id == reddit_post.id for post in collected_posts):
                                collected_posts.append(reddit_post)
                                
                                # Save to MongoDB if client is available
                                if self.mongodb_client:
                                    await self.mongodb_client.insert_post(reddit_post)
                        except Exception as e:
                            logger.error(f"Error processing post {submission.id}: {e}")
            
            except PrawcoreException as e:
                logger.error(f"Reddit API error for subreddit {subreddit_name}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error collecting posts from {subreddit_name}: {e}")
        
        logger.info(f"Collected {len(collected_posts)} posts")
        return collected_posts
    
    async def collect_comments(self, post_ids: List[str], limit: int = None) -> List[RedditComment]:
        """
        Collect comments from specific posts.
        
        Args:
            post_ids: List of post IDs to collect comments from
            limit: Maximum number of comments to collect per post
            
        Returns:
            List of collected RedditComment objects
        """
        if not self.reddit:
            self.initialize()
        
        comment_limit = limit or self.comment_limit
        collected_comments = []
        
        for post_id in post_ids:
            try:
                logger.info(f"Collecting comments from post {post_id}")
                submission = self.reddit.submission(id=post_id)
                
                # Force fetch all comments
                submission.comments.replace_more(limit=10)  # Limit replace_more calls to avoid API rate limits
                
                # Process comments
                comments_processed = 0
                for comment in submission.comments.list():
                    if comments_processed >= comment_limit:
                        break
                    
                    if self._contains_keywords(comment.body):
                        try:
                            reddit_comment = self._convert_to_reddit_comment(comment, post_id)
                            collected_comments.append(reddit_comment)
                            
                            # Save to MongoDB if client is available
                            if self.mongodb_client:
                                await self.mongodb_client.insert_post(reddit_comment)
                            
                            comments_processed += 1
                        except Exception as e:
                            logger.error(f"Error processing comment {comment.id}: {e}")
            
            except PrawcoreException as e:
                logger.error(f"Reddit API error for post {post_id}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error collecting comments from post {post_id}: {e}")
        
        logger.info(f"Collected {len(collected_comments)} comments")
        return collected_comments
    
    async def collect_data(self, time_filter: str = "day") -> Tuple[List[RedditPost], List[RedditComment]]:
        """
        Collect both posts and comments from monitored subreddits.
        
        Args:
            time_filter: Time filter for posts
            
        Returns:
            Tuple of (collected posts, collected comments)
        """
        # Collect posts
        posts = await self.collect_posts(time_filter=time_filter)
        
        # Collect comments from the posts
        post_ids = [post.id for post in posts]
        comments = await self.collect_comments(post_ids)
        
        return posts, comments 