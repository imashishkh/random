"""
Entity recognition for forex-related content.

This module implements named entity recognition (NER) for forex content,
identifying currency pairs, institutions, and other forex-related entities.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import spacy
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    logging.warning("Spacy model not found. Downloading en_core_web_sm...")
    from spacy.cli import download
    download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

logger = logging.getLogger(__name__)


class ForexEntityRecognizer:
    """
    Named Entity Recognizer for forex-related content.
    
    Identifies entities such as currency pairs, central banks, financial 
    institutions, and economic indicators in forex-related text.
    """
    
    def __init__(self, entity_data_path: Optional[str] = None):
        """
        Initialize the forex entity recognizer.
        
        Args:
            entity_data_path: Path to JSON file with entity definitions
        """
        self.nlp = nlp
        
        # Load entity data
        if entity_data_path:
            self.entity_data = self._load_entity_data(entity_data_path)
        else:
            self.entity_data = self._default_entity_data()
            
        # Initialize regex patterns
        self._init_regex_patterns()
        
    def _load_entity_data(self, filepath: str) -> Dict[str, Any]:
        """
        Load entity data from JSON file.
        
        Args:
            filepath: Path to JSON file
            
        Returns:
            Dictionary with entity data
        """
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.exception(f"Error loading entity data: {e}")
            return self._default_entity_data()
            
    def _default_entity_data(self) -> Dict[str, Any]:
        """
        Create default entity data.
        
        Returns:
            Dictionary with default entity data
        """
        return {
            "currency_codes": {
                "USD": "US Dollar",
                "EUR": "Euro",
                "GBP": "British Pound",
                "JPY": "Japanese Yen",
                "AUD": "Australian Dollar",
                "CAD": "Canadian Dollar",
                "CHF": "Swiss Franc",
                "NZD": "New Zealand Dollar",
                "CNY": "Chinese Yuan",
                "HKD": "Hong Kong Dollar",
                "SGD": "Singapore Dollar",
                "INR": "Indian Rupee",
                "MXN": "Mexican Peso",
                "BRL": "Brazilian Real",
                "RUB": "Russian Ruble",
                "KRW": "South Korean Won",
                "TRY": "Turkish Lira",
                "ZAR": "South African Rand",
                "SEK": "Swedish Krona",
                "NOK": "Norwegian Krone",
                "DKK": "Danish Krone",
                "PLN": "Polish Zloty"
            },
            "currency_pairs": {
                "EUR/USD": ["EURUSD", "euro/dollar", "euro-dollar", "fiber"],
                "GBP/USD": ["GBPUSD", "sterling/dollar", "cable"],
                "USD/JPY": ["USDJPY", "dollar/yen", "gopher"],
                "USD/CHF": ["USDCHF", "dollar/franc", "swissy"],
                "AUD/USD": ["AUDUSD", "aussie/dollar", "aussie"],
                "USD/CAD": ["USDCAD", "dollar/loonie", "loonie"],
                "NZD/USD": ["NZDUSD", "kiwi/dollar", "kiwi"]
            },
            "central_banks": {
                "Federal Reserve": ["Fed", "FOMC", "US central bank", "Powell"],
                "European Central Bank": ["ECB", "Eurozone central bank", "Lagarde"],
                "Bank of England": ["BoE", "UK central bank", "British central bank", "Bailey"],
                "Bank of Japan": ["BoJ", "Japanese central bank", "Ueda"],
                "Reserve Bank of Australia": ["RBA", "Australian central bank", "Lowe"],
                "Bank of Canada": ["BoC", "Canadian central bank", "Macklem"],
                "Swiss National Bank": ["SNB", "Swiss central bank", "Jordan"],
                "Reserve Bank of New Zealand": ["RBNZ", "New Zealand central bank", "Orr"]
            },
            "economic_indicators": {
                "Gross Domestic Product": ["GDP", "economic growth", "economic output"],
                "Consumer Price Index": ["CPI", "inflation", "consumer inflation"],
                "Producer Price Index": ["PPI", "producer inflation", "wholesale prices"],
                "Non-Farm Payrolls": ["NFP", "employment report", "jobs report", "employment data"],
                "Interest Rate": ["rate decision", "policy rate", "interest rates", "monetary policy"],
                "Purchasing Managers Index": ["PMI", "manufacturing PMI", "services PMI"],
                "Retail Sales": ["consumer spending", "retail figures", "consumption data"],
                "Unemployment Rate": ["jobless rate", "unemployment data", "employment figures"]
            }
        }
            
    def _init_regex_patterns(self):
        """Initialize regex patterns for entity recognition."""
        # Currency pair patterns
        # Match standard notation like EUR/USD or EURUSD
        self.currency_pair_pattern = re.compile(
            r'\b(EUR|GBP|AUD|NZD|USD|CAD|JPY|CHF|CNY)/?'
            r'(EUR|GBP|AUD|NZD|USD|CAD|JPY|CHF|CNY)\b',
            re.IGNORECASE
        )
        
        # Economic data patterns
        # Match percentage changes, basis points
        self.economic_data_pattern = re.compile(
            r'\b(\d+\.?\d*)\s?(%|percent|percentage|bps|basis points)\b'
        )
        
    def recognize_entities(self, text: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Identify forex-related entities in text.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary mapping entity types to lists of found entities
        """
        if not text:
            return {}
            
        # Apply spaCy NER
        doc = self.nlp(text)
        
        # Initialize results
        entities = {
            "currency_pairs": [],
            "currencies": [],
            "central_banks": [],
            "economic_indicators": [],
            "organizations": [],
            "locations": [],
            "dates": [],
            "numeric_values": []
        }
        
        # Extract spaCy entities
        for ent in doc.ents:
            if ent.label_ == "ORG":
                entities["organizations"].append({
                    "text": ent.text,
                    "start": ent.start_char,
                    "end": ent.end_char
                })
            elif ent.label_ == "GPE":
                entities["locations"].append({
                    "text": ent.text,
                    "start": ent.start_char,
                    "end": ent.end_char
                })
            elif ent.label_ == "DATE":
                entities["dates"].append({
                    "text": ent.text,
                    "start": ent.start_char,
                    "end": ent.end_char
                })
            elif ent.label_ in ("MONEY", "PERCENT", "QUANTITY"):
                entities["numeric_values"].append({
                    "text": ent.text,
                    "start": ent.start_char,
                    "end": ent.end_char,
                    "type": ent.label_
                })
                
        # Find currency pairs using regex
        for match in self.currency_pair_pattern.finditer(text):
            pair = match.group(0)
            base_currency = match.group(1).upper()
            quote_currency = match.group(2).upper()
            
            if '/' not in pair:
                # Convert EURUSD format to EUR/USD
                pair = f"{base_currency}/{quote_currency}"
                
            entities["currency_pairs"].append({
                "text": pair,
                "start": match.start(),
                "end": match.end(),
                "base_currency": base_currency,
                "quote_currency": quote_currency
            })
            
        # Extract currencies mentioned
        for code in self.entity_data["currency_codes"]:
            pattern = r'\b' + re.escape(code) + r'\b'
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entities["currencies"].append({
                    "text": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                    "code": code,
                    "name": self.entity_data["currency_codes"][code]
                })
                
        # Extract central banks
        for bank, aliases in self.entity_data["central_banks"].items():
            patterns = [re.escape(bank)] + [re.escape(alias) for alias in aliases]
            pattern = '|'.join([r'\b' + p + r'\b' for p in patterns])
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entities["central_banks"].append({
                    "text": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                    "name": bank
                })
                
        # Extract economic indicators
        for indicator, aliases in self.entity_data["economic_indicators"].items():
            patterns = [re.escape(indicator)] + [re.escape(alias) for alias in aliases]
            pattern = '|'.join([r'\b' + p + r'\b' for p in patterns])
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entities["economic_indicators"].append({
                    "text": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                    "name": indicator
                })
                
        # Remove duplicates
        for entity_type in entities:
            unique_entities = []
            seen = set()
            
            for entity in entities[entity_type]:
                key = (entity["text"], entity["start"], entity["end"])
                if key not in seen:
                    seen.add(key)
                    unique_entities.append(entity)
                    
            entities[entity_type] = unique_entities
            
        return entities
        
    def entity_sentiment_link(
        self, 
        text: str, 
        sentiment_score: float,
        entities: Optional[Dict[str, List[Dict[str, Any]]]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Link sentiment to specific entities based on proximity.
        
        Args:
            text: Analyzed text
            sentiment_score: Overall sentiment score
            entities: Pre-extracted entities (optional)
            
        Returns:
            Dictionary mapping entity keys to sentiment scores
        """
        if not text:
            return {}
            
        # Extract entities if not provided
        if entities is None:
            entities = self.recognize_entities(text)
            
        # Initialize result
        entity_sentiments = {}
        
        # Create a list of all entity spans and their types
        entity_spans = []
        for entity_type, entity_list in entities.items():
            for entity in entity_list:
                # Skip dates and purely numeric values
                if entity_type in ("dates", "numeric_values"):
                    continue
                    
                # Create a key for the entity
                if entity_type == "currency_pairs":
                    key = entity["text"]
                elif entity_type == "currencies":
                    key = entity["code"]
                elif entity_type in ("central_banks", "economic_indicators"):
                    key = entity["name"]
                else:
                    key = entity["text"]
                    
                entity_spans.append({
                    "type": entity_type,
                    "key": key,
                    "start": entity["start"],
                    "end": entity["end"],
                    "context": "",
                })
                
        # Link sentiment to entities based on context window
        WINDOW_SIZE = 100  # characters
        
        for entity in entity_spans:
            # Extract context around entity
            start = max(0, entity["start"] - WINDOW_SIZE)
            end = min(len(text), entity["end"] + WINDOW_SIZE)
            context = text[start:end]
            entity["context"] = context
            
            # For now, just use the overall sentiment
            # In a more advanced version, we could use VADER on just this context
            # or use dependency parsing to link sentiment expressions to entities
            
            entity_key = f"{entity['type']}:{entity['key']}"
            if entity_key not in entity_sentiments:
                entity_sentiments[entity_key] = {
                    "type": entity["type"],
                    "name": entity["key"],
                    "score": sentiment_score,
                    "mentions": 1
                }
            else:
                # Average sentiment across mentions
                current = entity_sentiments[entity_key]
                count = current["mentions"]
                current["score"] = (current["score"] * count + sentiment_score) / (count + 1)
                current["mentions"] += 1
                
        return entity_sentiments
        
    def batch_process(
        self, 
        contents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Process a batch of content to extract entities and link sentiment.
        
        Args:
            contents: List of content dictionaries
            
        Returns:
            List of content dictionaries with added entity information
        """
        if not contents:
            return []
            
        results = []
        
        for content in contents:
            # Skip if no text
            if not content.get("text"):
                continue
                
            # Get text (include title if available)
            text = content.get("title", "") + " " + content.get("text", "")
            
            # Extract entities
            entities = self.recognize_entities(text)
            
            # Link sentiment to entities if sentiment score is available
            entity_sentiments = {}
            sentiment_score = None
            
            # Try to find sentiment score from VADER or transformer
            if "vader_sentiment" in content:
                sentiment_score = content["vader_sentiment"]["score"]
            elif "transformer_sentiment" in content:
                sentiment_score = content["transformer_sentiment"]["score"]
                
            if sentiment_score is not None:
                entity_sentiments = self.entity_sentiment_link(text, sentiment_score, entities)
                
            # Add entities and entity sentiments to content
            content_copy = content.copy()
            content_copy["entities"] = entities
            content_copy["entity_sentiments"] = entity_sentiments
            
            results.append(content_copy)
            
        return results 