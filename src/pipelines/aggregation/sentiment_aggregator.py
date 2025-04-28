"""
Sentiment aggregation for forex-related content.

This module implements aggregation functions to calculate sentiment scores
over different time periods and across different entities.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np
import pandas as pd

from ...db.mongodb_schema import SentimentScore

logger = logging.getLogger(__name__)


class SentimentAggregator:
    """
    Aggregator for sentiment scores from social media content.
    
    Provides functions to aggregate sentiment across time periods,
    entities, and sources with various weighting options.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the sentiment aggregator.
        
        Args:
            config: Configuration dictionary with optional settings
        """
        self.config = config or {}
        
        # Default settings
        self.default_decay_factor = self.config.get("decay_factor", 0.1)  # For exponential decay
        self.default_time_window = self.config.get("time_window", 24)  # Hours
        self.default_min_items = self.config.get("min_items", 10)  # Minimum items for valid aggregation
        
    def aggregate_by_time(
        self,
        sentiment_data: List[Dict[str, Any]],
        time_window: int = None,
        decay_factor: float = None,
        min_items: int = None,
        entity_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate sentiment over a time window with recency weighting.
        
        Args:
            sentiment_data: List of content items with sentiment scores
            time_window: Time window in hours (default from config)
            decay_factor: Decay factor for time weighting (default from config)
            min_items: Minimum items required for aggregation (default from config)
            entity_filter: Only include data for this entity if specified
            source_filter: Only include data from this source if specified
            
        Returns:
            Dictionary with aggregated sentiment metrics
        """
        if not sentiment_data:
            return {"score": 0.0, "confidence": 0.0, "item_count": 0}
            
        # Use defaults if not specified
        time_window = time_window if time_window is not None else self.default_time_window
        decay_factor = decay_factor if decay_factor is not None else self.default_decay_factor
        min_items = min_items if min_items is not None else self.default_min_items
        
        # Filter by entity if specified
        if entity_filter:
            filtered_data = []
            for item in sentiment_data:
                entities = item.get("entities", {})
                entity_sentiments = item.get("entity_sentiments", {})
                
                # Check if entity is in the entity lists
                found = False
                for entity_type in entities:
                    for entity in entities[entity_type]:
                        if entity_filter.lower() in entity.get("text", "").lower():
                            found = True
                            break
                    if found:
                        break
                        
                # Or check if entity is in entity_sentiments
                if not found:
                    for entity_key in entity_sentiments:
                        if entity_filter.lower() in entity_key.lower():
                            found = True
                            break
                            
                if found:
                    filtered_data.append(item)
            sentiment_data = filtered_data
            
        # Filter by source if specified
        if source_filter:
            sentiment_data = [
                item for item in sentiment_data 
                if item.get("source", "").lower() == source_filter.lower()
            ]
            
        # Check if we have enough data
        if len(sentiment_data) < min_items:
            return {
                "score": 0.0, 
                "confidence": 0.0, 
                "item_count": len(sentiment_data),
                "reliable": False,
                "error": f"Insufficient data: {len(sentiment_data)} items (minimum {min_items})"
            }
            
        # Calculate current timestamp for recency calculations
        now = datetime.utcnow()
        
        # Convert to DataFrame for easier aggregation
        rows = []
        for item in sentiment_data:
            # Skip items without sentiment
            if not ("vader_sentiment" in item or "transformer_sentiment" in item):
                continue
                
            # Get timestamp
            timestamp = item.get("collected_at") or item.get("created_at")
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                except ValueError:
                    # Skip items with invalid timestamp
                    continue
                    
            # Skip items outside time window
            if timestamp < now - timedelta(hours=time_window):
                continue
                
            # Prepare row data
            row = {
                "timestamp": timestamp,
                "age_hours": (now - timestamp).total_seconds() / 3600,
            }
            
            # Add sentiment data, preferring transformer over VADER if both available
            if "transformer_sentiment" in item:
                row["score"] = item["transformer_sentiment"]["score"]
                row["confidence"] = item["transformer_sentiment"]["confidence"]
                row["sentiment_type"] = "transformer"
            elif "vader_sentiment" in item:
                row["score"] = item["vader_sentiment"]["score"]
                row["confidence"] = item["vader_sentiment"]["confidence"]
                row["sentiment_type"] = "vader"
            else:
                continue  # Skip items without sentiment
                
            # Add source information
            row["source"] = item.get("source", "unknown")
            
            # Add to rows
            rows.append(row)
            
        # Convert to DataFrame
        if not rows:
            return {
                "score": 0.0, 
                "confidence": 0.0, 
                "item_count": 0,
                "reliable": False,
                "error": "No data within time window"
            }
            
        df = pd.DataFrame(rows)
        
        # Calculate time-based weights using exponential decay
        df["time_weight"] = np.exp(-decay_factor * df["age_hours"])
        
        # Calculate weighted scores
        df["weighted_score"] = df["score"] * df["confidence"] * df["time_weight"]
        
        # Aggregate
        total_weight = (df["confidence"] * df["time_weight"]).sum()
        if total_weight > 0:
            aggregated_score = df["weighted_score"].sum() / total_weight
        else:
            aggregated_score = 0.0
            
        # Calculate volatility as weighted standard deviation of scores
        if len(df) > 1:
            variance = ((df["score"] - aggregated_score) ** 2 * df["time_weight"]).sum() / df["time_weight"].sum()
            volatility = math.sqrt(variance)
        else:
            volatility = 0.0
            
        # Additional metrics
        recent_trend = self._calculate_trend(df)
        source_stats = self._calculate_source_stats(df)
        
        return {
            "score": float(aggregated_score),
            "confidence": float(min(1.0, len(df) / (min_items * 2))),  # Scale confidence by data volume
            "volatility": float(volatility),
            "item_count": len(df),
            "recent_trend": recent_trend,
            "source_breakdown": source_stats,
            "time_window_hours": time_window,
            "reliable": True,
            "timestamp": now.isoformat()
        }
        
    def aggregate_by_entity(
        self,
        sentiment_data: List[Dict[str, Any]],
        time_window: Optional[int] = None,
        entity_types: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Aggregate sentiment by entity.
        
        Args:
            sentiment_data: List of content items with sentiment scores
            time_window: Time window in hours (default from config)
            entity_types: List of entity types to include (default: all)
            
        Returns:
            Dictionary mapping entity keys to aggregated sentiment metrics
        """
        if not sentiment_data:
            return {}
            
        # Use defaults if not specified
        time_window = time_window if time_window is not None else self.default_time_window
        
        # Filter for items with entities and sentiment
        filtered_data = []
        for item in sentiment_data:
            has_entities = "entities" in item and item["entities"]
            has_sentiment = "vader_sentiment" in item or "transformer_sentiment" in item
            
            if has_entities and has_sentiment:
                filtered_data.append(item)
                
        # Calculate current timestamp
        now = datetime.utcnow()
        
        # Build entity sentiment map
        entity_mentions = {}  # Map entity keys to lists of sentiment mentions
        
        for item in filtered_data:
            # Skip items outside time window
            timestamp = item.get("collected_at") or item.get("created_at")
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                except ValueError:
                    continue
                    
            if timestamp < now - timedelta(hours=time_window):
                continue
                
            # Get sentiment
            sentiment_score = None
            confidence = None
            
            if "transformer_sentiment" in item:
                sentiment_score = item["transformer_sentiment"]["score"]
                confidence = item["transformer_sentiment"]["confidence"]
            elif "vader_sentiment" in item:
                sentiment_score = item["vader_sentiment"]["score"]
                confidence = item["vader_sentiment"]["confidence"]
                
            if sentiment_score is None:
                continue
                
            # Get entity sentiments if available
            entity_sentiments = item.get("entity_sentiments", {})
            
            if entity_sentiments:
                # Use entity-specific sentiments
                for entity_key, entity_data in entity_sentiments.items():
                    entity_type = entity_data.get("type")
                    
                    # Filter by entity type if specified
                    if entity_types and entity_type not in entity_types:
                        continue
                        
                    if entity_key not in entity_mentions:
                        entity_mentions[entity_key] = []
                        
                    entity_mentions[entity_key].append({
                        "score": entity_data.get("score", 0.0),
                        "timestamp": timestamp,
                        "age_hours": (now - timestamp).total_seconds() / 3600,
                        "confidence": 0.7,  # Lower confidence for entity-level sentiment
                    })
            else:
                # Extract entities and use document sentiment
                entities = item.get("entities", {})
                
                for entity_type, entity_list in entities.items():
                    # Filter by entity type if specified
                    if entity_types and entity_type not in entity_types:
                        continue
                        
                    for entity in entity_list:
                        # Create entity key
                        if entity_type == "currency_pairs":
                            key = f"{entity_type}:{entity['text']}"
                        elif entity_type == "currencies":
                            key = f"{entity_type}:{entity.get('code', entity['text'])}"
                        elif entity_type in ("central_banks", "economic_indicators"):
                            key = f"{entity_type}:{entity.get('name', entity['text'])}"
                        else:
                            key = f"{entity_type}:{entity['text']}"
                            
                        if key not in entity_mentions:
                            entity_mentions[key] = []
                            
                        entity_mentions[key].append({
                            "score": sentiment_score,
                            "timestamp": timestamp,
                            "age_hours": (now - timestamp).total_seconds() / 3600,
                            "confidence": confidence * 0.8,  # Lower confidence when using document-level sentiment
                        })
                        
        # Aggregate sentiment for each entity
        results = {}
        
        for entity_key, mentions in entity_mentions.items():
            # Skip entities with too few mentions
            if len(mentions) < self.default_min_items / 2:  # Lower threshold for entities
                continue
                
            # Convert to DataFrame
            df = pd.DataFrame(mentions)
            
            # Calculate time-based weights
            df["time_weight"] = np.exp(-self.default_decay_factor * df["age_hours"])
            
            # Calculate weighted scores
            df["weighted_score"] = df["score"] * df["confidence"] * df["time_weight"]
            
            # Aggregate
            total_weight = (df["confidence"] * df["time_weight"]).sum()
            if total_weight > 0:
                aggregated_score = df["weighted_score"].sum() / total_weight
            else:
                aggregated_score = 0.0
                
            # Calculate volatility
            if len(df) > 1:
                variance = ((df["score"] - aggregated_score) ** 2 * df["time_weight"]).sum() / df["time_weight"].sum()
                volatility = math.sqrt(variance)
            else:
                volatility = 0.0
                
            # Calculate trend
            recent_trend = self._calculate_trend(df)
            
            # Add to results
            results[entity_key] = {
                "score": float(aggregated_score),
                "confidence": float(min(1.0, len(df) / self.default_min_items)),
                "volatility": float(volatility),
                "mention_count": len(df),
                "recent_trend": recent_trend,
                "reliable": len(df) >= self.default_min_items / 2,
                "timestamp": now.isoformat()
            }
            
        return results
        
    def _calculate_trend(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate trend in sentiment over time.
        
        Args:
            df: DataFrame with sentiment data
            
        Returns:
            Dictionary with trend metrics
        """
        if len(df) < 5:
            return {"slope": 0.0, "r_value": 0.0, "significant": False}
            
        # Sort by timestamp
        df = df.sort_values("timestamp")
        
        # Calculate hours from start
        start_time = df["timestamp"].min()
        df["hours_from_start"] = (df["timestamp"] - start_time).dt.total_seconds() / 3600
        
        # Linear regression
        try:
            from scipy import stats
            slope, intercept, r_value, p_value, std_err = stats.linregress(
                df["hours_from_start"], df["score"]
            )
            
            # Determine if trend is significant
            significant = abs(r_value) > 0.3 and p_value < 0.05
            
            return {
                "slope": float(slope),
                "r_value": float(r_value),
                "p_value": float(p_value),
                "significant": significant
            }
        except Exception as e:
            logger.exception(f"Error calculating trend: {e}")
            return {"slope": 0.0, "r_value": 0.0, "significant": False}
            
    def _calculate_source_stats(self, df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
        """
        Calculate statistics broken down by source.
        
        Args:
            df: DataFrame with sentiment data
            
        Returns:
            Dictionary with source statistics
        """
        result = {}
        
        # Group by source
        grouped = df.groupby("source")
        
        for source, group in grouped:
            # Calculate weighted average
            group["weighted_score"] = group["score"] * group["confidence"] * group["time_weight"]
            total_weight = (group["confidence"] * group["time_weight"]).sum()
            
            if total_weight > 0:
                avg_score = group["weighted_score"].sum() / total_weight
            else:
                avg_score = 0.0
                
            result[source] = {
                "score": float(avg_score),
                "count": len(group),
                "percent": float(len(group) / len(df) * 100)
            }
            
        return result 