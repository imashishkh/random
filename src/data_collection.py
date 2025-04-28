"""
Data collection script for the Forex sentiment analysis system.

This script demonstrates how to use the Reddit collector and sentiment analyzer
to collect and analyze social media data for Forex sentiment analysis.
"""

import asyncio
import json
import logging
import os
from datetime import datetime

from .collectors.reddit_collector import RedditCollector
from .db.mongodb_client import MongoDBClient
from .sentiment.sentiment_analyzer import SentimentAnalyzer
from .utils.config import (
    AppConfig, Config, RedditConfig, MongoDBConfig, SentimentAnalysisConfig
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data_collection.log")
    ]
)

logger = logging.getLogger(__name__)


async def load_or_create_config() -> Config:
    """
    Load configuration from file or create a new one.
    
    Returns:
        Config instance
    """
    config_path = "config.json"
    
    if os.path.exists(config_path):
        logger.info(f"Loading configuration from {config_path}")
        with open(config_path, "r") as f:
            config_dict = json.load(f)
        return Config.from_dict(config_dict)
    
    # Create a default configuration
    logger.info("Creating default configuration")
    config = Config()
    
    # Set up Reddit configuration (replace with your own API keys)
    config.reddit = RedditConfig(
        client_id="YOUR_REDDIT_CLIENT_ID",
        client_secret="YOUR_REDDIT_CLIENT_SECRET",
        user_agent="forex_sentiment_analyzer/1.0 (by /u/YOUR_USERNAME)",
        username=None,  # Optional
        password=None,  # Optional
        subreddits=[
            "forex", "forextrading", "investing", "economy", "finance",
            "trading", "wallstreetbets", "stocks", "cryptocurrency",
            "foreignexchange", "UKInvesting", "CanadianInvestor"
        ],
        keywords=[
            "forex", "currency", "exchange rate", "pip", "trend", "chart pattern",
            "technical analysis", "fundamental analysis", "indicator",
            "bull market", "bear market", "volatility", "strength", "weak", "strong",
            # Currency pairs
            "eurusd", "eur/usd", "eurjpy", "eur/jpy", "gbpusd", "gbp/usd",
            "audusd", "aud/usd", "usdjpy", "usd/jpy", "usdchf", "usd/chf",
            "nzdusd", "nzd/usd", "usdcad", "usd/cad", "eurgbp", "eur/gbp"
        ]
    )
    
    # Save the configuration
    with open(config_path, "w") as f:
        json.dump(config.__dict__, f, indent=2, default=lambda x: x.__dict__)
    
    return config


async def main():
    """Main function."""
    # Load or create configuration
    config = await load_or_create_config()
    
    # Check if Reddit API credentials are configured
    if config.reddit.client_id == "YOUR_REDDIT_CLIENT_ID":
        logger.error("Reddit API credentials not configured. Please edit config.json")
        return
    
    # Initialize MongoDB client
    mongodb_client = MongoDBClient(
        connection_string=config.mongodb.connection_string,
        database_name=config.mongodb.database_name,
        max_pool_size=config.mongodb.max_pool_size,
        timeout_ms=config.mongodb.timeout_ms,
    )
    
    try:
        await mongodb_client.connect()
        
        # Initialize Reddit collector
        reddit_collector = RedditCollector.from_config(
            config=config.reddit,
            mongodb_client=mongodb_client
        )
        
        # Initialize sentiment analyzer
        sentiment_analyzer = SentimentAnalyzer(
            config=config.sentiment,
            mongodb_client=mongodb_client
        )
        
        # Collect Reddit data
        logger.info("Collecting Reddit data...")
        posts, comments = await reddit_collector.collect_data(time_filter="day")
        
        logger.info(f"Collected {len(posts)} posts and {len(comments)} comments")
        
        # Analyze sentiment
        logger.info("Analyzing sentiment...")
        post_sentiments, comment_sentiments = await sentiment_analyzer.analyze_reddit_data(posts, comments)
        
        logger.info(f"Analyzed {len(post_sentiments)} posts and {len(comment_sentiments)} comments")
        
        # Get sentiment statistics for major currency pairs
        major_pairs = [
            "EUR/USD", "USD/JPY", "GBP/USD", "USD/CHF", 
            "USD/CAD", "AUD/USD", "NZD/USD"
        ]
        
        logger.info("Forex pair sentiment:")
        for pair in major_pairs:
            sentiment = sentiment_analyzer.get_forex_sentiment(post_sentiments + comment_sentiments, pair)
            if sentiment["count"] > 0:
                logger.info(f"{pair}: {sentiment['sentiment']} (score: {sentiment['average_score']:.2f}, mentions: {sentiment['count']})")
        
    finally:
        # Close MongoDB connection
        await mongodb_client.close()


if __name__ == "__main__":
    # Run the main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process interrupted")
    except Exception as e:
        logger.exception(f"Error in main process: {e}")