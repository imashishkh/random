"""
Social media data collectors for sentiment analysis.

Exports:
    TwitterCollector: Twitter data collector
    RedditCollector: Reddit data collector
"""

from .social.twitter import TwitterCollector
from .social.reddit import RedditCollector

__all__ = ["TwitterCollector", "RedditCollector"] 