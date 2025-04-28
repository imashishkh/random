"""
Configuration module for the Forex sentiment analysis system.

This module defines configuration classes for various components of the system.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class RedditConfig:
    """Reddit API configuration."""
    client_id: str
    client_secret: str
    user_agent: str
    username: Optional[str] = None
    password: Optional[str] = None
    subreddits: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)


@dataclass
class TwitterConfig:
    """Twitter API configuration."""
    api_key: str
    api_secret: str
    access_token: str
    access_token_secret: str
    bearer_token: str
    keywords: List[str] = field(default_factory=list)


@dataclass
class MongoDBConfig:
    """MongoDB configuration."""
    connection_string: str = "mongodb://localhost:27017"
    database_name: str = "forex_sentiment"
    max_pool_size: int = 10
    timeout_ms: int = 5000


@dataclass
class SentimentAnalysisConfig:
    """Sentiment analysis configuration."""
    model_name: str = "vader"  # Options: vader, textblob, transformers
    model_path: Optional[str] = None
    batch_size: int = 32
    use_gpu: bool = False


@dataclass
class AppConfig:
    """Application configuration."""
    log_level: str = "INFO"
    data_dir: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
    tmp_dir: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "tmp")
    collectors: List[str] = field(default_factory=lambda: ["reddit", "twitter"])
    collection_interval: int = 3600  # seconds
    analyzers: List[str] = field(default_factory=lambda: ["sentiment"])
    analysis_interval: int = 7200  # seconds


@dataclass
class Config:
    """Main configuration class."""
    app: AppConfig = field(default_factory=AppConfig)
    reddit: Optional[RedditConfig] = None
    twitter: Optional[TwitterConfig] = None
    mongodb: MongoDBConfig = field(default_factory=MongoDBConfig)
    sentiment: SentimentAnalysisConfig = field(default_factory=SentimentAnalysisConfig)
    
    @classmethod
    def from_dict(cls, config_dict: Dict) -> 'Config':
        """
        Create a Config instance from a dictionary.
        
        Args:
            config_dict: Configuration dictionary
            
        Returns:
            Config instance
        """
        config = cls()
        
        if "app" in config_dict:
            config.app = AppConfig(**config_dict["app"])
        
        if "reddit" in config_dict:
            config.reddit = RedditConfig(**config_dict["reddit"])
        
        if "twitter" in config_dict:
            config.twitter = TwitterConfig(**config_dict["twitter"])
        
        if "mongodb" in config_dict:
            config.mongodb = MongoDBConfig(**config_dict["mongodb"])
        
        if "sentiment" in config_dict:
            config.sentiment = SentimentAnalysisConfig(**config_dict["sentiment"])
        
        return config


def load_config(config_path: str) -> Config:
    """
    Load configuration from a file.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        Config instance
    """
    import json
    
    with open(config_path, "r") as f:
        config_dict = json.load(f)
    
    return Config.from_dict(config_dict)


def save_config(config: Config, config_path: str) -> None:
    """
    Save configuration to a file.
    
    Args:
        config: Config instance
        config_path: Path to save the configuration file
    """
    import json
    from dataclasses import asdict
    
    config_dict = asdict(config)
    
    with open(config_path, "w") as f:
        json.dump(config_dict, f, indent=2) 