"""
MongoDB schema definitions for Forex Trading application.

This module defines the schemas and indexes for the MongoDB collections used
in the Forex Trading application.
"""

import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, validator
from pymongo import IndexModel, ASCENDING, DESCENDING


class DataSourceType(str, Enum):
    """Enumeration of data source types."""
    NEWS = "news"
    SOCIAL = "social"
    MARKET = "market"
    SENTIMENT = "sentiment"
    REPORT = "report"
    OTHER = "other"


class DataSource(BaseModel):
    """Data source information model."""
    name: str
    url: Optional[str] = None
    type: DataSourceType
    reliability_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    
    class Config:
        validate_assignment = True


class SentimentEnum(str, Enum):
    """Sentiment classification enum."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class SentimentScore(BaseModel):
    """
    Sentiment score model with both numeric and categorical representation.
    """
    score: float = Field(..., ge=-1.0, le=1.0, description="Numeric sentiment score [-1.0, 1.0]")
    magnitude: float = Field(..., ge=0.0, description="Sentiment magnitude [0.0, +inf)")
    label: SentimentEnum = Field(..., description="Categorical sentiment label")
    
    @validator('label', pre=True)
    def validate_label(cls, v, values):
        """Auto-assign label if not provided but score is available."""
        if v is None and 'score' in values:
            score = values['score']
            if score >= 0.05:
                return SentimentEnum.POSITIVE
            elif score <= -0.05:
                return SentimentEnum.NEGATIVE
            else:
                return SentimentEnum.NEUTRAL
        return v


class NewsArticle(BaseModel):
    """News article data model."""
    title: str
    content: str
    summary: Optional[str] = None
    source: DataSource
    published_at: datetime.datetime
    collected_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    url: Optional[str] = None
    author: Optional[str] = None
    categories: List[str] = []
    tags: List[str] = []
    entities: Dict[str, List[str]] = {}  # e.g., {"organizations": ["Tesla", "Apple"], "countries": ["US", "China"]}
    currency_pairs: List[str] = []  # e.g., ["EUR/USD", "GBP/JPY"]
    metadata: Dict[str, Any] = {}
    
    class Config:
        validate_assignment = True
    
    @validator('published_at')
    def check_published_date(cls, v):
        """Validate published date is not in the future."""
        if v > datetime.datetime.utcnow():
            raise ValueError("Published date cannot be in the future")
        return v


class SentimentAnalysisResult(BaseModel):
    """
    Sentiment analysis result for a social media document.
    """
    id: str = Field(..., description="Unique ID for the sentiment analysis")
    post_id: str = Field(..., description="ID of the analyzed post")
    source: str = Field(..., description="Source platform (reddit, twitter, etc.)")
    score: float = Field(..., ge=-1.0, le=1.0, description="Sentiment score [-1.0, 1.0]")
    magnitude: float = Field(..., ge=0.0, description="Sentiment magnitude [0.0, +inf)")
    label: SentimentEnum = Field(..., description="Sentiment classification")
    analyzer: str = Field(..., description="Sentiment analyzer used (vader, textblob, etc.)")
    analyzed_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, description="Analysis timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class SocialMediaDocument(BaseModel):
    """
    Base model for social media documents.
    """
    id: str = Field(..., description="Unique document ID")
    source: str = Field(..., description="Source platform (twitter, reddit, etc.)")
    content: str = Field(..., description="Document text content")
    created_at: datetime.datetime = Field(..., description="Creation timestamp")
    author_id: Optional[str] = Field(None, description="Author ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    forex_relevance: Optional[float] = Field(None, description="Forex relevance score")
    collected_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, description="Collection timestamp")


class Tweet(SocialMediaDocument):
    """
    Twitter-specific document schema.
    """
    retweet_count: int = Field(default=0, description="Number of retweets")
    like_count: int = Field(default=0, description="Number of likes")
    reply_count: int = Field(default=0, description="Number of replies")
    quote_count: int = Field(default=0, description="Number of quotes")
    hashtags: List[str] = Field(default_factory=list, description="Hashtags in the tweet")
    mentions: List[str] = Field(default_factory=list, description="User mentions in the tweet")
    is_retweet: bool = Field(default=False, description="Whether this is a retweet")
    lang: str = Field(default="en", description="Tweet language")


class RedditPost(SocialMediaDocument):
    """
    Reddit-specific document schema for posts.
    """
    subreddit: str = Field(..., description="Subreddit name")
    title: str = Field(..., description="Post title")
    score: int = Field(default=0, description="Post score (upvotes - downvotes)")
    upvote_ratio: float = Field(default=0.0, description="Upvote ratio")
    num_comments: int = Field(default=0, description="Number of comments")
    is_self: bool = Field(default=True, description="Whether this is a self-post")
    permalink: str = Field(..., description="Permanent link to the post")
    url: str = Field(..., description="URL of the post")
    flair: Optional[str] = Field(None, description="Post flair")
    forex_pairs: List[str] = Field(default_factory=list, description="Currency pairs mentioned")
    sentiment_score: Optional[float] = Field(None, description="Overall sentiment score")
    sentiment_label: Optional[str] = Field(None, description="Sentiment label")


class RedditComment(SocialMediaDocument):
    """
    Reddit-specific document schema for comments.
    """
    post_id: str = Field(..., description="Parent post ID")
    subreddit: str = Field(..., description="Subreddit name")
    score: int = Field(default=0, description="Comment score (upvotes - downvotes)")
    parent_id: str = Field(..., description="Parent comment ID or post ID")
    permalink: str = Field(..., description="Permanent link to the comment")
    depth: int = Field(default=0, description="Comment depth in the thread")
    is_submitter: bool = Field(default=False, description="Whether comment author is the post submitter")
    parent_comment_id: Optional[str] = Field(None, description="ID of parent comment")
    forex_pairs: List[str] = Field(default_factory=list, description="Currency pairs mentioned")
    sentiment_score: Optional[float] = Field(None, description="Overall sentiment score")
    sentiment_label: Optional[str] = Field(None, description="Sentiment label")


class MarketEvent(BaseModel):
    """Market event model for significant events."""
    title: str
    description: str
    event_type: str  # economic_release, policy_change, geopolitical, etc.
    severity: int = Field(..., ge=1, le=10)  # Impact severity
    source: DataSource
    timestamp: datetime.datetime
    collected_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    affected_markets: List[str] = []  # e.g., ["forex", "equities"]
    affected_currencies: List[str] = []  # e.g., ["USD", "EUR"]
    affected_pairs: List[str] = []  # e.g., ["EUR/USD", "GBP/USD"]
    expected_impact: Optional[Dict[str, Any]] = None
    actual_impact: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}
    
    class Config:
        validate_assignment = True


class SocialMediaPost(BaseModel):
    """Base model for all social media posts."""
    
    id: str = Field(..., description="Unique identifier for the post")
    source: str = Field(..., description="Source platform (twitter, reddit, etc.)")
    content: str = Field(..., description="Text content of the post")
    created_at: datetime.datetime = Field(..., description="Creation timestamp")
    author_id: str = Field(..., description="ID of the post author")
    collected_at: datetime.datetime = Field(..., description="Timestamp when the post was collected")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    # Sentiment analysis fields
    sentiment_score: Optional[float] = Field(None, description="Overall sentiment score")
    sentiment_label: Optional[str] = Field(None, description="Sentiment label (positive, negative, neutral)")
    sentiment_details: Optional[Dict[str, Any]] = Field(None, description="Detailed sentiment analysis")
    
    # Forex-specific fields
    forex_pairs: Optional[List[str]] = Field(None, description="Mentioned forex pairs")
    keywords: Optional[List[str]] = Field(None, description="Extracted keywords")
    
    class Config:
        allow_population_by_field_name = True


class TwitterPost(SocialMediaPost):
    """Twitter-specific post model."""
    
    tweet_id: str = Field(..., description="Twitter tweet ID")
    user_name: Optional[str] = Field(None, description="Twitter username")
    user_screen_name: Optional[str] = Field(None, description="Twitter screen name")
    user_followers: Optional[int] = Field(None, description="User follower count")
    retweet_count: Optional[int] = Field(None, description="Number of retweets")
    favorite_count: Optional[int] = Field(None, description="Number of likes")
    hashtags: Optional[List[str]] = Field(None, description="Hashtags in the tweet")
    mentions: Optional[List[str]] = Field(None, description="User mentions in the tweet")
    is_retweet: bool = Field(False, description="Whether the tweet is a retweet")
    reply_to_id: Optional[str] = Field(None, description="ID of the tweet this is replying to")
    
    @classmethod
    def from_tweet(cls, tweet: Dict[str, Any]) -> "TwitterPost":
        """Create a TwitterPost from a tweet object."""
        # Implementation would depend on the Twitter API version and library
        pass


class RedditPost(SocialMediaPost):
    """Reddit submission (post) model."""
    
    title: str = Field(..., description="Title of the post")
    score: int = Field(..., description="Post score (upvotes - downvotes)")
    upvote_ratio: float = Field(..., description="Ratio of upvotes to total votes")
    num_comments: int = Field(..., description="Number of comments")
    is_self: bool = Field(..., description="Whether the post is a self post")
    flair: Optional[str] = Field(None, description="Post flair")
    subreddit: str = Field(..., description="Subreddit name")


class RedditComment(SocialMediaPost):
    """Reddit comment model."""
    
    post_id: str = Field(..., description="ID of the parent post")
    score: int = Field(..., description="Comment score (upvotes - downvotes)")
    is_submitter: bool = Field(..., description="Whether the comment author is the post submitter")
    parent_id: Optional[str] = Field(None, description="ID of the parent comment (if any)")
    subreddit: str = Field(..., description="Subreddit name")


class ForexIndicator(BaseModel):
    """Model for forex technical indicators."""
    
    pair: str = Field(..., description="Forex pair code (e.g., 'EUR/USD')")
    timestamp: datetime = Field(..., description="Timestamp of the indicator")
    timeframe: str = Field(..., description="Timeframe (e.g., '1h', '4h', '1d')")
    type: str = Field(..., description="Indicator type (e.g., 'RSI', 'MACD')")
    value: Union[float, Dict[str, float]] = Field(..., description="Indicator value(s)")
    
    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# Schema and index definitions for MongoDB collections
# These are used for documentation and validation purposes

# ===== Trades Collection =====
TRADES_SCHEMA = {
    "validator": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["symbol", "direction", "entry_price", "size", "entry_time", "status"],
            "properties": {
                "trade_id": {
                    "bsonType": "string",
                    "description": "Unique identifier for the trade"
                },
                "account_id": {
                    "bsonType": "string",
                    "description": "Reference to the account this trade belongs to"
                },
                "strategy_id": {
                    "bsonType": "string",
                    "description": "Reference to the strategy that generated this trade"
                },
                "symbol": {
                    "bsonType": "string",
                    "description": "Trading symbol (e.g., 'EURUSD', 'GBPJPY')"
                },
                "direction": {
                    "enum": ["BUY", "SELL"],
                    "description": "Trade direction (BUY or SELL)"
                },
                "entry_price": {
                    "bsonType": "double",
                    "description": "Entry price of the trade"
                },
                "exit_price": {
                    "bsonType": "double",
                    "description": "Exit price of the trade (if closed)"
                },
                "size": {
                    "bsonType": "double",
                    "description": "Size/volume of the trade"
                },
                "tp": {
                    "bsonType": "double",
                    "description": "Take profit price"
                },
                "sl": {
                    "bsonType": "double",
                    "description": "Stop loss price"
                },
                "risk_reward_ratio": {
                    "bsonType": "double",
                    "description": "Risk-to-reward ratio for the trade"
                },
                "entry_time": {
                    "bsonType": "date",
                    "description": "Date and time when the trade was entered"
                },
                "exit_time": {
                    "bsonType": "date",
                    "description": "Date and time when the trade was exited (if closed)"
                },
                "status": {
                    "enum": ["OPEN", "CLOSED", "CANCELLED", "PENDING"],
                    "description": "Current status of the trade"
                },
                "pnl": {
                    "bsonType": "double",
                    "description": "Profit or loss from the trade (if closed)"
                },
                "notes": {
                    "bsonType": "string",
                    "description": "Additional notes about the trade"
                },
                "tags": {
                    "bsonType": "array",
                    "description": "Tags or categories for this trade",
                    "items": {
                        "bsonType": "string"
                    }
                },
                "setup_type": {
                    "bsonType": "string",
                    "description": "Type of trading setup (e.g., 'breakout', 'pullback')"
                },
                "timeframe": {
                    "bsonType": "string",
                    "description": "Timeframe used for analysis (e.g., '1h', '4h', '1d')"
                },
                "screenshot_urls": {
                    "bsonType": "array",
                    "description": "URLs to trade screenshots",
                    "items": {
                        "bsonType": "string"
                    }
                },
                "created_at": {
                    "bsonType": "date",
                    "description": "Date and time when this document was created"
                },
                "last_modified": {
                    "bsonType": "date",
                    "description": "Date and time when this document was last modified"
                }
            }
        }
    }
}

TRADES_INDEXES = [
    {
        "key": {"trade_id": 1},
        "name": "trade_id_index",
        "unique": True,
        "sparse": True  # Only applies to documents with trade_id field
    },
    {
        "key": {"symbol": 1},
        "name": "symbol_index"
    },
    {
        "key": {"entry_time": -1},
        "name": "entry_time_index"
    },
    {
        "key": {"status": 1},
        "name": "status_index"
    },
    {
        "key": {"account_id": 1},
        "name": "account_id_index"
    },
    {
        "key": {"strategy_id": 1},
        "name": "strategy_id_index"
    }
]

# ===== Accounts Collection =====
ACCOUNTS_SCHEMA = {
    "validator": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["name", "balance"],
            "properties": {
                "account_id": {
                    "bsonType": "string",
                    "description": "Unique identifier for the account"
                },
                "name": {
                    "bsonType": "string",
                    "description": "Name of the account"
                },
                "type": {
                    "enum": ["DEMO", "LIVE"],
                    "description": "Type of account (DEMO or LIVE)"
                },
                "balance": {
                    "bsonType": "double",
                    "description": "Current balance of the account"
                },
                "currency": {
                    "bsonType": "string",
                    "description": "Currency of the account"
                },
                "broker": {
                    "bsonType": "string",
                    "description": "Broker name"
                },
                "initial_deposit": {
                    "bsonType": "double",
                    "description": "Initial deposit amount"
                },
                "leverage": {
                    "bsonType": "int",
                    "description": "Account leverage (e.g., 100 for 1:100)"
                },
                "created_at": {
                    "bsonType": "date",
                    "description": "Date and time when this account was created"
                },
                "updated_at": {
                    "bsonType": "date",
                    "description": "Date and time when this account was last updated"
                },
                "status": {
                    "enum": ["ACTIVE", "INACTIVE", "CLOSED"],
                    "description": "Current status of the account"
                },
                "notes": {
                    "bsonType": "string",
                    "description": "Additional notes about the account"
                },
                "risk_settings": {
                    "bsonType": "object",
                    "description": "Risk management settings",
                    "properties": {
                        "max_risk_per_trade": {
                            "bsonType": "double",
                            "description": "Maximum risk percentage per trade"
                        },
                        "max_daily_loss": {
                            "bsonType": "double",
                            "description": "Maximum allowed daily loss percentage"
                        },
                        "max_open_trades": {
                            "bsonType": "int",
                            "description": "Maximum number of simultaneous open trades"
                        }
                    }
                }
            }
        }
    }
}

ACCOUNTS_INDEXES = [
    {
        "key": {"account_id": 1},
        "name": "account_id_index",
        "unique": True,
        "sparse": True  # Only applies to documents with account_id field
    },
    {
        "key": {"name": 1},
        "name": "name_index"
    },
    {
        "key": {"type": 1},
        "name": "type_index"
    },
    {
        "key": {"broker": 1},
        "name": "broker_index"
    }
]

# ===== Strategies Collection =====
STRATEGIES_SCHEMA = {
    "validator": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["name", "description"],
            "properties": {
                "strategy_id": {
                    "bsonType": "string",
                    "description": "Unique identifier for the strategy"
                },
                "name": {
                    "bsonType": "string",
                    "description": "Name of the strategy"
                },
                "description": {
                    "bsonType": "string",
                    "description": "Detailed description of the strategy"
                },
                "timeframes": {
                    "bsonType": "array",
                    "description": "Timeframes this strategy is designed for",
                    "items": {
                        "bsonType": "string"
                    }
                },
                "markets": {
                    "bsonType": "array",
                    "description": "Markets this strategy is designed for",
                    "items": {
                        "bsonType": "string"
                    }
                },
                "indicators": {
                    "bsonType": "array",
                    "description": "Technical indicators used in this strategy",
                    "items": {
                        "bsonType": "string"
                    }
                },
                "entry_conditions": {
                    "bsonType": "array",
                    "description": "Conditions for entering a trade",
                    "items": {
                        "bsonType": "string"
                    }
                },
                "exit_conditions": {
                    "bsonType": "array",
                    "description": "Conditions for exiting a trade",
                    "items": {
                        "bsonType": "string"
                    }
                },
                "risk_per_trade": {
                    "bsonType": "double",
                    "description": "Default risk percentage per trade"
                },
                "take_profit": {
                    "bsonType": "object",
                    "description": "Take profit settings",
                    "properties": {
                        "type": {
                            "enum": ["FIXED", "DYNAMIC", "MULTIPLE"],
                            "description": "Type of take profit strategy"
                        },
                        "value": {
                            "bsonType": "double",
                            "description": "Value for fixed take profit (in pips or price)"
                        }
                    }
                },
                "stop_loss": {
                    "bsonType": "object",
                    "description": "Stop loss settings",
                    "properties": {
                        "type": {
                            "enum": ["FIXED", "DYNAMIC", "ATR"],
                            "description": "Type of stop loss strategy"
                        },
                        "value": {
                            "bsonType": "double",
                            "description": "Value for fixed stop loss (in pips or price)"
                        }
                    }
                },
                "status": {
                    "enum": ["ACTIVE", "INACTIVE", "TESTING", "ARCHIVED"],
                    "description": "Current status of the strategy"
                },
                "performance": {
                    "bsonType": "object",
                    "description": "Strategy performance metrics",
                    "properties": {
                        "win_rate": {
                            "bsonType": "double",
                            "description": "Win rate percentage"
                        },
                        "profit_factor": {
                            "bsonType": "double",
                            "description": "Profit factor"
                        },
                        "avg_winner": {
                            "bsonType": "double",
                            "description": "Average winning trade"
                        },
                        "avg_loser": {
                            "bsonType": "double",
                            "description": "Average losing trade"
                        },
                        "max_drawdown": {
                            "bsonType": "double",
                            "description": "Maximum drawdown percentage"
                        }
                    }
                },
                "created_at": {
                    "bsonType": "date",
                    "description": "Date and time when this strategy was created"
                },
                "updated_at": {
                    "bsonType": "date",
                    "description": "Date and time when this strategy was last updated"
                },
                "notes": {
                    "bsonType": "string",
                    "description": "Additional notes about the strategy"
                }
            }
        }
    }
}

STRATEGIES_INDEXES = [
    {
        "key": {"strategy_id": 1},
        "name": "strategy_id_index",
        "unique": True,
        "sparse": True  # Only applies to documents with strategy_id field
    },
    {
        "key": {"name": 1},
        "name": "name_index",
        "unique": True
    },
    {
        "key": {"status": 1},
        "name": "status_index"
    }
]

# ===== Journal Entries Collection =====
JOURNAL_ENTRIES_SCHEMA = {
    "validator": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["date", "content"],
            "properties": {
                "entry_id": {
                    "bsonType": "string",
                    "description": "Unique identifier for the journal entry"
                },
                "date": {
                    "bsonType": "date",
                    "description": "Date of the journal entry"
                },
                "title": {
                    "bsonType": "string",
                    "description": "Title of the journal entry"
                },
                "content": {
                    "bsonType": "string",
                    "description": "Content of the journal entry"
                },
                "market_conditions": {
                    "bsonType": "string",
                    "description": "Description of market conditions"
                },
                "mood": {
                    "bsonType": "string",
                    "description": "Trader's mood during this trading session"
                },
                "lessons_learned": {
                    "bsonType": "array",
                    "description": "Lessons learned from this trading session",
                    "items": {
                        "bsonType": "string"
                    }
                },
                "trade_ids": {
                    "bsonType": "array",
                    "description": "Associated trade IDs",
                    "items": {
                        "bsonType": "string"
                    }
                },
                "tags": {
                    "bsonType": "array",
                    "description": "Tags or categories for this entry",
                    "items": {
                        "bsonType": "string"
                    }
                },
                "screenshot_urls": {
                    "bsonType": "array",
                    "description": "URLs to screenshots",
                    "items": {
                        "bsonType": "string"
                    }
                },
                "created_at": {
                    "bsonType": "date",
                    "description": "Date and time when this entry was created"
                },
                "updated_at": {
                    "bsonType": "date",
                    "description": "Date and time when this entry was last updated"
                }
            }
        }
    }
}

JOURNAL_ENTRIES_INDEXES = [
    {
        "key": {"entry_id": 1},
        "name": "entry_id_index",
        "unique": True,
        "sparse": True  # Only applies to documents with entry_id field
    },
    {
        "key": {"date": -1},
        "name": "date_index"
    },
    {
        "key": {"tags": 1},
        "name": "tags_index"
    }
]

# Complete collection configuration map
COLLECTIONS_CONFIG = {
    "trades": {
        "schema": TRADES_SCHEMA,
        "indexes": TRADES_INDEXES
    },
    "accounts": {
        "schema": ACCOUNTS_SCHEMA,
        "indexes": ACCOUNTS_INDEXES
    },
    "strategies": {
        "schema": STRATEGIES_SCHEMA,
        "indexes": STRATEGIES_INDEXES
    },
    "journal_entries": {
        "schema": JOURNAL_ENTRIES_SCHEMA,
        "indexes": JOURNAL_ENTRIES_INDEXES
    }
}

def get_collection_config(collection_name: str) -> Dict[str, Any]:
    """
    Get configuration for a specific collection
    
    Args:
        collection_name (str): Name of the collection
    
    Returns:
        Dict[str, Any]: Configuration for the collection or empty dict if not found
    """
    return COLLECTIONS_CONFIG.get(collection_name, {}) 