"""
Main sentiment analysis pipeline for social media data.

This module implements the full sentiment analysis pipeline, coordinating the
data flow between collectors, filters, analyzers, and aggregators.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from ..collectors.social import TwitterCollector, RedditCollector
from .filters.content_filter import ForexContentFilter
from .sentiment.vader_analyzer import VaderSentimentAnalyzer
from .sentiment.transformer_analyzer import TransformerSentimentAnalyzer
from .entity.forex_ner import ForexEntityRecognizer
from .aggregation.sentiment_aggregator import SentimentAggregator
from ..db.mongodb_schema import SentimentAnalysis, SentimentScore

logger = logging.getLogger(__name__)


class SentimentPipeline:
    """
    Sentiment analysis pipeline for forex-related social media content.
    
    This class coordinates the full process from data collection to
    sentiment analysis, entity recognition, and aggregation.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the sentiment analysis pipeline.
        
        Args:
            config: Configuration dictionary with settings for each component
        """
        self.config = config or {}
        
        # Initialize pipeline components
        self.content_filter = ForexContentFilter(
            min_score=self.config.get("filter_min_score", 0.2)
        )
        
        self.vader_analyzer = VaderSentimentAnalyzer()
        
        self.transformer_analyzer = TransformerSentimentAnalyzer(
            model_name=self.config.get("transformer_model", "ProsusAI/finbert"),
            use_gpu=self.config.get("use_gpu", False),
            max_length=self.config.get("max_length", 512)
        )
        
        self.entity_recognizer = ForexEntityRecognizer(
            entity_data_path=self.config.get("entity_data_path")
        )
        
        self.aggregator = SentimentAggregator(
            config=self.config.get("aggregator", {})
        )
        
        # Initialize collectors
        self._init_collectors()
        
        # Set up internal queue
        self.queue = asyncio.Queue()
        self.processed_items = []
        
    def _init_collectors(self):
        """Initialize social media data collectors."""
        self.collectors = []
        
        # Twitter collector
        if self.config.get("use_twitter", True):
            twitter_config = self.config.get("twitter", {})
            if "bearer_token" in twitter_config:
                twitter_collector = TwitterCollector(
                    bearer_token=twitter_config["bearer_token"],
                    config=twitter_config
                )
                self.collectors.append(twitter_collector)
                
        # Reddit collector
        if self.config.get("use_reddit", True):
            reddit_config = self.config.get("reddit", {})
            if "client_id" in reddit_config and "client_secret" in reddit_config:
                reddit_collector = RedditCollector(
                    client_id=reddit_config["client_id"],
                    client_secret=reddit_config["client_secret"],
                    user_agent=reddit_config.get("user_agent", "ForexSentimentAnalyzer/1.0"),
                    config=reddit_config
                )
                self.collectors.append(reddit_collector)
                
    async def start(self):
        """Start the sentiment pipeline and all collectors."""
        # Start all collectors
        logger.info("Starting sentiment analysis pipeline")
        
        for collector in self.collectors:
            await collector.start()
            
        # Start processing task
        self.processing_task = asyncio.create_task(self._process_queue())
        logger.info("Sentiment pipeline started")
        
    async def stop(self):
        """Stop the pipeline and all collectors."""
        logger.info("Stopping sentiment analysis pipeline")
        
        # Stop collectors
        for collector in self.collectors:
            await collector.stop()
            
        # Cancel processing task
        if hasattr(self, "processing_task") and not self.processing_task.done():
            self.processing_task.cancel()
            
        logger.info("Sentiment pipeline stopped")
        
    async def process_batch(self, content_batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process a batch of content through the sentiment pipeline.
        
        Args:
            content_batch: List of content dictionaries
            
        Returns:
            List of processed content with sentiment analysis results
        """
        if not content_batch:
            return []
            
        logger.info(f"Processing batch of {len(content_batch)} content items")
        
        # Step 1: Filter content for forex relevance
        logger.debug("Filtering content for forex relevance")
        filtered_content = self.content_filter.batch_filter(content_batch)
        
        if not filtered_content:
            logger.info("No relevant content found in batch")
            return []
            
        logger.info(f"Found {len(filtered_content)} relevant items out of {len(content_batch)}")
        
        # Step 2: Analyze sentiment with VADER
        logger.debug("Analyzing sentiment with VADER")
        vader_results = self.vader_analyzer.batch_analyze(filtered_content)
        
        # Step 3: Analyze sentiment with transformer model (FinBERT)
        logger.debug("Analyzing sentiment with transformer model")
        transformer_results = self.transformer_analyzer.batch_analyze(vader_results)
        
        # Step 4: Perform entity recognition and sentiment attribution
        logger.debug("Performing entity recognition")
        entity_results = self.entity_recognizer.batch_process(transformer_results)
        
        # Add processed items to history
        self.processed_items.extend(entity_results)
        
        # Trim history if too large
        max_history = self.config.get("max_history_items", 10000)
        if len(self.processed_items) > max_history:
            self.processed_items = self.processed_items[-max_history:]
            
        return entity_results
        
    async def _process_queue(self):
        """Process items from the queue continuously."""
        while True:
            try:
                # Get batch from queue
                batch = []
                timeout = self.config.get("batch_timeout", 1.0)
                
                try:
                    # Get first item (with timeout)
                    item = await asyncio.wait_for(self.queue.get(), timeout=timeout)
                    batch.append(item)
                    self.queue.task_done()
                    
                    # Get more items if available (without waiting)
                    batch_size = self.config.get("batch_size", 50)
                    while len(batch) < batch_size and not self.queue.empty():
                        item = self.queue.get_nowait()
                        batch.append(item)
                        self.queue.task_done()
                        
                except asyncio.TimeoutError:
                    # No items available
                    if not batch:
                        continue
                        
                # Process batch
                if batch:
                    try:
                        await self.process_batch(batch)
                    except Exception as e:
                        logger.exception(f"Error processing batch: {e}")
                        
            except asyncio.CancelledError:
                logger.info("Queue processing task cancelled")
                break
                
            except Exception as e:
                logger.exception(f"Unexpected error in queue processing: {e}")
                await asyncio.sleep(1)  # Sleep before retrying
                
    async def add_content(self, content: Union[Dict[str, Any], List[Dict[str, Any]]]):
        """
        Add content to the processing queue.
        
        Args:
            content: Content dictionary or list of content dictionaries
        """
        if isinstance(content, list):
            for item in content:
                await self.queue.put(item)
        else:
            await self.queue.put(content)
            
    def get_aggregate_sentiment(
        self,
        time_window: Optional[int] = None,
        entity_filter: Optional[str] = None,
        source_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated sentiment metrics.
        
        Args:
            time_window: Time window in hours
            entity_filter: Filter by entity
            source_filter: Filter by source
            
        Returns:
            Dictionary with aggregated sentiment metrics
        """
        return self.aggregator.aggregate_by_time(
            self.processed_items,
            time_window=time_window,
            entity_filter=entity_filter,
            source_filter=source_filter
        )
        
    def get_entity_sentiment(
        self,
        time_window: Optional[int] = None,
        entity_types: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get sentiment aggregated by entity.
        
        Args:
            time_window: Time window in hours
            entity_types: List of entity types to include
            
        Returns:
            Dictionary mapping entity keys to sentiment metrics
        """
        return self.aggregator.aggregate_by_entity(
            self.processed_items,
            time_window=time_window,
            entity_types=entity_types
        )
        
    def create_sentiment_analysis_object(
        self,
        document_id: str,
        document_type: str,
        sentiment_score: SentimentScore,
        entity_sentiments: Dict[str, Dict[str, Any]] = None,
        currency_pairs: List[str] = None
    ) -> SentimentAnalysis:
        """
        Create a SentimentAnalysis object for database storage.
        
        Args:
            document_id: Reference to the analyzed document
            document_type: Type of document (tweet, reddit_post, etc.)
            sentiment_score: Overall sentiment score
            entity_sentiments: Entity-specific sentiment scores
            currency_pairs: List of currency pairs mentioned
            
        Returns:
            SentimentAnalysis object
        """
        # Convert entity sentiments to SentimentScore objects
        entity_scores = {}
        aspect_scores = {}
        
        if entity_sentiments:
            for entity_key, data in entity_sentiments.items():
                parts = entity_key.split(":")
                if len(parts) == 2:
                    entity_type, entity_name = parts
                    
                    # Create sentiment score
                    score = SentimentScore(
                        score=data["score"],
                        confidence=data.get("confidence", 0.5)
                    )
                    
                    if entity_type in ("currency_pairs", "currencies"):
                        entity_scores[entity_name] = score
                    else:
                        aspect_scores[entity_name] = score
                        
        # Create SentimentAnalysis object
        return SentimentAnalysis(
            document_id=document_id,
            document_type=document_type,
            overall_sentiment=sentiment_score,
            entity_sentiments=entity_scores,
            aspect_sentiments=aspect_scores,
            analyzed_at=datetime.utcnow(),
            model_info={
                "vader": "nltk.sentiment.vader",
                "transformer": self.transformer_analyzer.model_name
            },
            currency_pairs=currency_pairs or []
        ) 