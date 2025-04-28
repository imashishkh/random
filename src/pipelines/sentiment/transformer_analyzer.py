"""
Transformer-based sentiment analyzer using HuggingFace models.

This module implements a sentiment analyzer using pre-trained transformer models
from HuggingFace, with a focus on financial sentiment analysis.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import torch
try:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
except ImportError:
    logging.error("transformers library not found. Please install with: pip install transformers")
    
from ...db.mongodb_schema import SentimentScore

logger = logging.getLogger(__name__)


class TransformerSentimentAnalyzer:
    """
    Transformer-based sentiment analyzer for financial text.
    
    Uses a pre-trained model from HuggingFace for sentiment analysis,
    with support for financial domain-specific models.
    """
    
    def __init__(
        self,
        model_name: str = "ProsusAI/finbert",
        use_gpu: bool = torch.cuda.is_available(),
        max_length: int = 512,
    ):
        """
        Initialize the transformer-based sentiment analyzer.
        
        Args:
            model_name: HuggingFace model name/path 
                - "ProsusAI/finbert" for financial text
                - "yiyanghkust/finbert-tone" for fine-grained financial sentiment
                - "distilbert-base-uncased-finetuned-sst-2-english" for general sentiment
            use_gpu: Whether to use GPU if available
            max_length: Maximum input sequence length
        """
        self.model_name = model_name
        self.max_length = max_length
        
        # Set up device
        self.device = torch.device("cuda" if use_gpu and torch.cuda.is_available() else "cpu")
        logger.info(f"Using device: {self.device}")
        
        # Load tokenizer and model
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self.model.to(self.device)
            self.model.eval()  # Set to evaluation mode
            
            # Determine label mapping based on model
            self._set_label_mapping()
            
            logger.info(f"Successfully loaded model {model_name}")
            
        except Exception as e:
            logger.error(f"Error loading model {model_name}: {e}")
            raise
            
    def _set_label_mapping(self):
        """Set up label mapping based on the loaded model."""
        if "finbert" in self.model_name.lower():
            if "tone" in self.model_name.lower():
                # yiyanghkust/finbert-tone
                self.labels = ["negative", "neutral", "positive"]
                self.positive_idx = 2
                self.negative_idx = 0
                self.neutral_idx = 1
            else:
                # ProsusAI/finbert
                self.labels = ["positive", "negative", "neutral"]
                self.positive_idx = 0
                self.negative_idx = 1
                self.neutral_idx = 2
        else:
            # Default for SST-2 style models
            self.labels = ["negative", "positive"]
            self.positive_idx = 1
            self.negative_idx = 0
            self.neutral_idx = None  # No neutral class
            
    def analyze(self, text: str) -> Tuple[SentimentScore, Dict[str, Any]]:
        """
        Analyze sentiment of text using the transformer model.
        
        Args:
            text: Text to analyze
            
        Returns:
            Tuple of (SentimentScore, detailed_scores)
        """
        if not text:
            # Return neutral sentiment for empty text
            return SentimentScore(score=0.0, confidence=0.0), {}
            
        try:
            # Truncate text if needed (to avoid excessive processing time)
            if len(text) > self.max_length * 10:  # Rough character estimate
                text = text[:self.max_length * 10]
                
            # Tokenize
            tokens = self.tokenizer(
                text,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt"
            )
            
            # Move to device
            tokens = {k: v.to(self.device) for k, v in tokens.items()}
            
            # Disable gradient calculation for inference
            with torch.no_grad():
                outputs = self.model(**tokens)
                
            # Get probabilities using softmax
            probabilities = torch.nn.functional.softmax(outputs.logits, dim=1)
            probabilities = probabilities.cpu().numpy()[0]
            
            # Prepare result dictionary
            result = {label: float(prob) for label, prob in zip(self.labels, probabilities)}
            
            # Calculate sentiment score
            if self.neutral_idx is not None:
                # Models with neutral class
                positive_prob = result[self.labels[self.positive_idx]]
                negative_prob = result[self.labels[self.negative_idx]]
                
                # Score from -1 to 1 (similar to VADER)
                sentiment_score = positive_prob - negative_prob
                
                # Higher confidence when neutral is low and pos/neg difference is high
                confidence = abs(positive_prob - negative_prob) * (1 - result[self.labels[self.neutral_idx]])
            else:
                # Binary sentiment models
                positive_prob = result[self.labels[self.positive_idx]]
                
                # Score from -1 to 1
                sentiment_score = (positive_prob - 0.5) * 2
                
                # Higher confidence when probabilities are farther from 0.5
                confidence = abs(positive_prob - 0.5) * 2
                
            # Create SentimentScore object
            sentiment = SentimentScore(
                score=float(sentiment_score),
                confidence=float(confidence)
            )
            
            return sentiment, result
            
        except Exception as e:
            logger.exception(f"Error analyzing sentiment with transformer model: {e}")
            # Return neutral sentiment on error
            return SentimentScore(score=0.0, confidence=0.0), {}
            
    def batch_analyze(
        self, 
        contents: List[Dict[str, Any]], 
        batch_size: int = 8
    ) -> List[Dict[str, Any]]:
        """
        Analyze sentiment for a batch of content.
        
        Args:
            contents: List of content dictionaries with 'text' field
            batch_size: Batch size for transformer processing
            
        Returns:
            List of content dictionaries with added sentiment information
        """
        if not contents:
            return []
            
        results = []
        
        # Process in batches to avoid OOM errors
        for i in range(0, len(contents), batch_size):
            batch = contents[i:i + batch_size]
            batch_results = []
            
            for content in batch:
                # Skip if no text
                if not content.get("text"):
                    continue
                    
                # Get text (include title if available)
                text = content.get("title", "") + " " + content.get("text", "")
                
                # Analyze sentiment
                sentiment, details = self.analyze(text)
                
                # Add sentiment to content
                content_copy = content.copy()
                content_copy["transformer_sentiment"] = {
                    "score": sentiment.score,
                    "confidence": sentiment.confidence,
                    "model": self.model_name,
                    "labels": details,
                }
                
                batch_results.append(content_copy)
                
            results.extend(batch_results)
            
            # Brief pause between batches to avoid GPU memory issues
            if torch.cuda.is_available() and i + batch_size < len(contents):
                torch.cuda.empty_cache()
                time.sleep(0.1)
                
        return results 