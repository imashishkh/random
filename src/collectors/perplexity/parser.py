"""
Perplexity Response Parser

This module parses responses from Perplexity API into structured data formats
for storage and analysis. It transforms raw text responses into categorized
and normalized data points.
"""

import logging
import re
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

# Set up logging
logger = logging.getLogger(__name__)


class PerplexityParser:
    """
    Parser for Perplexity API responses.
    
    Extracts structured data from natural language responses
    for financial analysis and forex trading insights.
    """
    
    def __init__(self):
        """Initialize the parser with necessary configurations."""
        logger.info("PerplexityParser initialized")
    
    def parse_json_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse the full JSON response from Perplexity API.
        
        This method handles direct JSON responses from the API,
        extracting both the text content and metadata like sources,
        model information, and request details.
        
        Args:
            response_data: The full JSON response from Perplexity API
            
        Returns:
            Dictionary with parsed response data including text, sources, and metadata
        """
        logger.debug("Parsing JSON response from Perplexity API")
        
        # Initialize the result structure
        result = {
            "timestamp": datetime.now().isoformat(),
            "text": None,
            "sources": [],
            "model_used": None,
            "completion_tokens": None,
            "prompt_tokens": None,
            "total_tokens": None,
            "response_id": None,
            "search_queries": [],
            "finish_reason": None
        }
        
        try:
            # Extract model information
            if "model" in response_data:
                result["model_used"] = response_data["model"]
            
            # Extract usage information
            if "usage" in response_data:
                usage = response_data["usage"]
                result["completion_tokens"] = usage.get("completion_tokens")
                result["prompt_tokens"] = usage.get("prompt_tokens") 
                result["total_tokens"] = usage.get("total_tokens")
            
            # Extract response ID
            if "id" in response_data:
                result["response_id"] = response_data["id"]
                
            # Extract main content and metadata from choices
            if "choices" in response_data and len(response_data["choices"]) > 0:
                choice = response_data["choices"][0]
                
                # Extract finish reason
                if "finish_reason" in choice:
                    result["finish_reason"] = choice["finish_reason"]
                
                # Extract message content
                if "message" in choice:
                    message = choice["message"]
                    
                    # Extract the main text content
                    if "content" in message:
                        result["text"] = message["content"]
                    
                    # Extract tool calls for sources and search queries
                    if "tool_calls" in message:
                        for tool_call in message["tool_calls"]:
                            if tool_call.get("type") == "search":
                                function = tool_call.get("function", {})
                                
                                if function.get("name") == "search":
                                    # Try to parse the search arguments
                                    try:
                                        args = json.loads(function.get("arguments", "{}"))
                                        
                                        # Extract search query
                                        if "query" in args:
                                            result["search_queries"].append(args["query"])
                                        
                                        # Extract sources
                                        if "sources" in args and isinstance(args["sources"], list):
                                            for source in args["sources"]:
                                                result["sources"].append({
                                                    "title": source.get("title", ""),
                                                    "url": source.get("url", ""),
                                                    "snippet": source.get("snippet", "")
                                                })
                                    except json.JSONDecodeError:
                                        logger.warning("Failed to parse tool call arguments")
            
            # Fallback for sources if not found in tool_calls
            if not result["sources"] and "choices" in response_data and len(response_data["choices"]) > 0:
                message = response_data["choices"][0].get("message", {})
                if "context" in message and "citations" in message["context"]:
                    for citation in message["context"]["citations"]:
                        result["sources"].append({
                            "title": citation.get("title", ""),
                            "url": citation.get("url", ""),
                            "snippet": citation.get("text", "")
                        })
            
            # Parse the text content if available
            if result["text"]:
                # Detect the content type from the text
                content_type = self.detect_content_type(result["text"])
                
                # Add the parsed data based on content type
                parsed_data = None
                
                if content_type == "currency_pair":
                    # Try to extract the currency pair from the text or search queries
                    pair = "UNKNOWN"
                    pair_pattern = r'\b([A-Z]{3}/[A-Z]{3})\b'
                    
                    # First check the text
                    pair_match = re.search(pair_pattern, result["text"])
                    if pair_match:
                        pair = pair_match.group(1)
                    # Then check search queries
                    elif result["search_queries"]:
                        for query in result["search_queries"]:
                            pair_match = re.search(pair_pattern, query)
                            if pair_match:
                                pair = pair_match.group(1)
                                break
                    
                    parsed_data = self.parse_currency_pair_analysis(result["text"], pair)
                
                elif content_type == "market_news":
                    parsed_data = self.parse_market_news(result["text"])
                
                elif content_type == "economic_indicator":
                    parsed_data = self.parse_economic_indicators(result["text"])
                
                else:  # Default to general analysis
                    parsed_data = self.parse_general_market_analysis(result["text"])
                
                result["content_type"] = content_type
                result["parsed_data"] = parsed_data
        
        except Exception as e:
            logger.error(f"Error parsing JSON response: {str(e)}")
            # Include the error in the result
            result["error"] = str(e)
        
        logger.debug("Completed parsing JSON response")
        return result
    
    def parse_currency_pair_analysis(self, text: str, pair: str) -> Dict[str, Any]:
        """
        Parse currency pair analysis from text response.
        
        Args:
            text: Raw text from Perplexity API
            pair: Currency pair being analyzed (e.g., "EUR/USD")
            
        Returns:
            Dictionary with structured analysis data
        """
        logger.debug(f"Parsing currency pair analysis for {pair}")
        
        # Initialize result structure
        result = {
            "pair": pair,
            "timestamp": datetime.now().isoformat(),
            "analysis": {},
            "sentiment": None,
            "support_resistance_levels": [],
            "technical_indicators": {},
            "key_drivers": [],
            "price_targets": [],
            "raw_text": text
        }
        
        # Extract sentiment
        sentiment_patterns = [
            r"(?i)sentiment\s*(?:is|:|appears to be|remains)\s*(bullish|bearish|neutral)",
            r"(?i)(bullish|bearish|neutral)\s*(?:sentiment|outlook|bias)",
            r"(?i)traders are (bullish|bearish|neutral)",
            r"(?i)market is (bullish|bearish|neutral)"
        ]
        
        for pattern in sentiment_patterns:
            sentiment_match = re.search(pattern, text)
            if sentiment_match:
                result["sentiment"] = sentiment_match.group(1).lower()
                break
        
        # Extract support and resistance levels
        support_resistance_pattern = r"(?i)(?:support|resistance)(?:\s*level)?\s*(?:at|:|\s)\s*(\d+\.\d+)"
        support_resistance_matches = re.finditer(support_resistance_pattern, text)
        
        for match in support_resistance_matches:
            try:
                level = float(match.group(1))
                level_type = "support" if "support" in text[match.start()-10:match.start()].lower() else "resistance"
                result["support_resistance_levels"].append({
                    "type": level_type,
                    "level": level
                })
            except (ValueError, IndexError):
                pass
        
        # Extract technical indicators
        indicator_patterns = {
            "rsi": r"(?i)RSI\s*(?:is|at|:|\s)\s*(\d+(?:\.\d+)?)",
            "macd": r"(?i)MACD\s*(?:is|:|\s)\s*(bullish|bearish|neutral|positive|negative|above|below)",
            "moving_averages": r"(?i)(?:price is|trading)\s*(above|below)\s*the\s*(\d+)[\s-]*(?:day|period)?\s*(?:moving average|MA|EMA|SMA)",
        }
        
        for indicator, pattern in indicator_patterns.items():
            indicator_matches = re.finditer(pattern, text)
            for match in indicator_matches:
                if indicator == "rsi":
                    try:
                        result["technical_indicators"]["rsi"] = float(match.group(1))
                    except (ValueError, IndexError):
                        pass
                elif indicator == "macd":
                    result["technical_indicators"]["macd"] = match.group(1).lower()
                elif indicator == "moving_averages":
                    direction = match.group(1).lower()
                    try:
                        period = int(match.group(2))
                        ma_type = "simple" if "SMA" in text[match.start():match.end()] else "exponential"
                        
                        if "moving_averages" not in result["technical_indicators"]:
                            result["technical_indicators"]["moving_averages"] = []
                            
                        result["technical_indicators"]["moving_averages"].append({
                            "period": period,
                            "type": ma_type,
                            "position": direction
                        })
                    except (ValueError, IndexError):
                        pass
        
        # Extract key market drivers
        key_driver_patterns = [
            r"(?i)(?:key|main|primary)\s*(?:driver|factor)s?(?:[:\s]+)([^.]+)",
            r"(?i)(?:is|are)\s*(?:driven|influenced|affected)\s*by([^.]+)",
            r"(?i)(?:impacted|affected)\s*by([^.]+)"
        ]
        
        for pattern in key_driver_patterns:
            driver_matches = re.finditer(pattern, text)
            for match in driver_matches:
                try:
                    drivers_text = match.group(1).strip()
                    # Split by commas or "and"
                    drivers = re.split(r'(?:,\s*|\s+and\s+)', drivers_text)
                    for driver in drivers:
                        if driver and len(driver) > 3:  # Avoid short/meaningless matches
                            result["key_drivers"].append(driver.strip())
                except (IndexError, AttributeError):
                    pass
        
        # Extract price targets if available
        price_target_patterns = [
            r"(?i)price\s*target\s*(?:of|at|:|\s)\s*(\d+\.\d+)",
            r"(?i)(?:could|may|might|is expected to)\s*(?:reach|hit|move to)\s*(\d+\.\d+)",
            r"(?i)target\s*(?:of|at|:|\s)\s*(\d+\.\d+)"
        ]
        
        for pattern in price_target_patterns:
            target_matches = re.finditer(pattern, text)
            for match in target_matches:
                try:
                    target = float(match.group(1))
                    # Determine if it's upside or downside by context
                    target_type = "upside"
                    context = text[max(0, match.start()-50):min(match.end()+50, len(text))]
                    if re.search(r"downside|lower|decline|decrease|fall", context, re.I):
                        target_type = "downside"
                    
                    result["price_targets"].append({
                        "value": target,
                        "type": target_type
                    })
                except (ValueError, IndexError):
                    pass
        
        return result
    
    def parse_market_news(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse market news items from text response.
        
        Args:
            text: Raw text from Perplexity API
            
        Returns:
            List of news item dictionaries
        """
        logger.debug("Parsing market news")
        
        # Initialize results
        news_items = []
        
        # Split the text into potential news items
        # Look for patterns like numbered items, dates, or news headlines
        item_separators = [
            r"\d+\.\s+",  # Numbered items: "1. ", "2. ", etc.
            r"\*\*[\w\s]+\*\*",  # Bold headers: "**News Item**"
            r"\n\d+\/\d+\/\d+",  # Dates at start of line: "\n01/15/2023"
            r"\n[A-Z][a-z]{2,}\s\d+,\s\d{4}",  # Month format: "\nJanuary 15, 2023"
        ]
        
        # Create a combined pattern
        separator_pattern = "|".join(f"({pat})" for pat in item_separators)
        
        # Split text using the combined pattern
        potential_items = re.split(separator_pattern, text)
        
        # Process each potential news item
        current_item = {}
        
        for i, segment in enumerate(potential_items):
            if not segment or segment.isspace():
                continue
                
            # Check if this segment is a separator/header
            is_separator = any(re.fullmatch(pattern, segment) for pattern in item_separators)
            
            if is_separator and current_item and "content" in current_item:
                # We found a new separator and have a current item - save it
                news_items.append(current_item)
                current_item = {}
            
            if is_separator:
                # This is a header/separator, not content
                current_item["header"] = segment.strip()
            else:
                # This is content
                if "content" not in current_item:
                    current_item["content"] = segment.strip()
                else:
                    current_item["content"] += "\n" + segment.strip()
                    
                # Try to extract date
                date_patterns = [
                    r"(\d{1,2}/\d{1,2}/\d{2,4})",  # MM/DD/YYYY or DD/MM/YYYY
                    r"([A-Z][a-z]{2,}\s\d{1,2},?\s\d{4})",  # Month DD, YYYY
                ]
                
                for pattern in date_patterns:
                    date_match = re.search(pattern, segment)
                    if date_match and "date" not in current_item:
                        current_item["date"] = date_match.group(1)
                
                # Try to extract source
                source_patterns = [
                    r"(?:Source|from)[:\s]+([A-Za-z0-9\s]+)",
                    r"according to ([A-Za-z0-9\s]+)",
                    r"reported by ([A-Za-z0-9\s]+)",
                ]
                
                for pattern in source_patterns:
                    source_match = re.search(pattern, segment, re.I)
                    if source_match and "source" not in current_item:
                        current_item["source"] = source_match.group(1).strip()
                
                # Try to extract impact/sentiment
                impact_patterns = [
                    r"(bullish|bearish|neutral) impact",
                    r"impact[:\s]+(bullish|bearish|neutral)",
                    r"impact on the market is (bullish|bearish|neutral)",
                ]
                
                for pattern in impact_patterns:
                    impact_match = re.search(pattern, segment, re.I)
                    if impact_match and "impact" not in current_item:
                        current_item["impact"] = impact_match.group(1).lower()
                        
                # Try to extract affected currencies
                currency_pattern = r"(?:affected currencies|impact on)[:\s]+([A-Z]{3}(?:/[A-Z]{3})?(?:,\s*[A-Z]{3}(?:/[A-Z]{3})?)*)"
                currency_match = re.search(currency_pattern, segment, re.I)
                if currency_match and "affected_currencies" not in current_item:
                    currencies_text = currency_match.group(1)
                    current_item["affected_currencies"] = [c.strip() for c in currencies_text.split(",")]
        
        # Don't forget the last item
        if current_item and "content" in current_item:
            news_items.append(current_item)
        
        # Post-process each news item
        for item in news_items:
            # Try to extract a title if not already present
            if "title" not in item and "content" in item:
                # Use the first sentence or up to 100 chars as title
                first_line = item["content"].split('\n')[0]
                title = re.split(r'[.!?]', first_line)[0]
                if len(title) > 10:  # Ensure it's a meaningful title
                    item["title"] = title.strip()
            
            # Add timestamp
            item["timestamp"] = datetime.now().isoformat()
        
        logger.debug(f"Extracted {len(news_items)} news items")
        return news_items
    
    def parse_economic_indicators(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse economic indicators data from text response.
        
        Args:
            text: Raw text from Perplexity API
            
        Returns:
            List of economic indicator dictionaries
        """
        logger.debug("Parsing economic indicators")
        
        # Initialize results
        indicators = []
        
        # Split the text into potential indicator items
        # Similar approach to news items but with different patterns
        item_separators = [
            r"\d+\.\s+",  # Numbered items: "1. ", "2. ", etc.
            r"\*\*[\w\s]+\*\*",  # Bold headers: "**Indicator**"
            r"\n(?:Release|Event|Indicator):",  # Headers at start of line: "\nRelease:" 
            r"\n[A-Z][a-z]{2,}\s\d+,\s\d{4}",  # Month format: "\nJanuary 15, 2023"
        ]
        
        # Create a combined pattern
        separator_pattern = "|".join(f"({pat})" for pat in item_separators)
        
        # Split text using the combined pattern
        potential_items = re.split(separator_pattern, text)
        
        # Process each potential indicator item
        current_item = {}
        
        for i, segment in enumerate(potential_items):
            if not segment or segment.isspace():
                continue
                
            # Check if this segment is a separator/header
            is_separator = any(re.fullmatch(pattern, segment) for pattern in item_separators)
            
            if is_separator and current_item and "content" in current_item:
                # We found a new separator and have a current item - save it
                indicators.append(current_item)
                current_item = {}
            
            if is_separator:
                # This is a header/separator, not content
                current_item["header"] = segment.strip()
            else:
                # This is content
                if "content" not in current_item:
                    current_item["content"] = segment.strip()
                else:
                    current_item["content"] += "\n" + segment.strip()
                    
                # Try to extract date
                date_patterns = [
                    r"(?:Release )?(?:Date|Time)[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
                    r"(?:Release )?(?:Date|Time)[:\s]+([A-Z][a-z]{2,}\s\d{1,2},?\s\d{4})",
                    r"(\d{1,2}/\d{1,2}/\d{2,4})",  # MM/DD/YYYY or DD/MM/YYYY
                    r"([A-Z][a-z]{2,}\s\d{1,2},?\s\d{4})",  # Month DD, YYYY
                ]
                
                for pattern in date_patterns:
                    date_match = re.search(pattern, segment)
                    if date_match and "date" not in current_item:
                        current_item["date"] = date_match.group(1)
                
                # Try to extract country
                country_patterns = [
                    r"(?:Country|Region)[:\s]+([A-Za-z\s]+)",
                    r"([A-Za-z\s]+)'s (?:economic|indicator|data)",
                ]
                
                for pattern in country_patterns:
                    country_match = re.search(pattern, segment, re.I)
                    if country_match and "country" not in current_item:
                        current_item["country"] = country_match.group(1).strip()
                
                # Try to extract indicator name
                indicator_patterns = [
                    r"(?:Indicator|Release|Event)[:\s]+([A-Za-z0-9\s\-\(\)]+)",
                    r"(?:the|recent|upcoming) ([A-Za-z0-9\s\-\(\)]+) (?:data|release|report|indicator)",
                ]
                
                for pattern in indicator_patterns:
                    indicator_match = re.search(pattern, segment, re.I)
                    if indicator_match and "indicator" not in current_item:
                        current_item["indicator"] = indicator_match.group(1).strip()
                
                # Try to extract previous value
                previous_patterns = [
                    r"(?:Previous|Prior)[:\s]+([\-\+]?\d+\.?\d*%?)",
                    r"previous reading of ([\-\+]?\d+\.?\d*%?)",
                ]
                
                for pattern in previous_patterns:
                    previous_match = re.search(pattern, segment, re.I)
                    if previous_match and "previous_value" not in current_item:
                        current_item["previous_value"] = previous_match.group(1)
                
                # Try to extract forecast value
                forecast_patterns = [
                    r"(?:Forecast|Expected|Consensus)[:\s]+([\-\+]?\d+\.?\d*%?)",
                    r"forecast(?:ed)? (?:at|to be) ([\-\+]?\d+\.?\d*%?)",
                ]
                
                for pattern in forecast_patterns:
                    forecast_match = re.search(pattern, segment, re.I)
                    if forecast_match and "forecast_value" not in current_item:
                        current_item["forecast_value"] = forecast_match.group(1)
                
                # Try to extract actual value if released
                actual_patterns = [
                    r"(?:Actual|Released|Reported)[:\s]+([\-\+]?\d+\.?\d*%?)",
                    r"came in at ([\-\+]?\d+\.?\d*%?)",
                    r"reported (?:at|as) ([\-\+]?\d+\.?\d*%?)",
                ]
                
                for pattern in actual_patterns:
                    actual_match = re.search(pattern, segment, re.I)
                    if actual_match and "actual_value" not in current_item:
                        current_item["actual_value"] = actual_match.group(1)
                
                # Try to extract importance/impact
                importance_patterns = [
                    r"(?:Importance|Impact)[:\s]+(high|medium|low)",
                    r"(high|medium|low)(?:-|\s)impact",
                ]
                
                for pattern in importance_patterns:
                    importance_match = re.search(pattern, segment, re.I)
                    if importance_match and "importance" not in current_item:
                        current_item["importance"] = importance_match.group(1).lower()
        
        # Don't forget the last item
        if current_item and "content" in current_item:
            indicators.append(current_item)
        
        # Post-process each indicator item
        for item in indicators:
            # Try to extract market impact if not already present
            if "market_impact" not in item and "content" in item:
                impact_patterns = [
                    r"(?:market|forex|currency)\s+impact[:\s]+(bullish|bearish|neutral|positive|negative)",
                    r"(bullish|bearish|neutral|positive|negative)\s+(?:for|impact on)\s+(?:the\s+)?(?:market|currency|forex)",
                ]
                
                for pattern in impact_patterns:
                    impact_match = re.search(pattern, item["content"], re.I)
                    if impact_match:
                        impact = impact_match.group(1).lower()
                        # Normalize impact terms
                        if impact == "positive":
                            impact = "bullish"
                        elif impact == "negative":
                            impact = "bearish"
                        item["market_impact"] = impact
                        break
            
            # Add timestamp
            item["timestamp"] = datetime.now().isoformat()
        
        logger.debug(f"Extracted {len(indicators)} economic indicators")
        return indicators
    
    def parse_general_market_analysis(self, text: str) -> Dict[str, Any]:
        """
        Parse general market analysis from text response.
        
        Args:
            text: Raw text from Perplexity API
            
        Returns:
            Dictionary with structured market analysis
        """
        logger.debug("Parsing general market analysis")
        
        # Initialize result structure
        result = {
            "timestamp": datetime.now().isoformat(),
            "market_sentiment": None,
            "key_themes": [],
            "currency_mentions": {},
            "important_events": [],
            "risk_factors": [],
            "trading_recommendations": [],
            "raw_text": text
        }
        
        # Extract market sentiment
        sentiment_patterns = [
            r"(?:overall|market|general)\s+sentiment\s+(?:is|appears to be|remains)\s+(bullish|bearish|neutral|mixed)",
            r"traders are (?:generally|mostly) (bullish|bearish|neutral|mixed)",
            r"market is (bullish|bearish|neutral|mixed)",
            r"(bullish|bearish|neutral|mixed) sentiment prevails",
        ]
        
        for pattern in sentiment_patterns:
            sentiment_match = re.search(pattern, text, re.I)
            if sentiment_match:
                result["market_sentiment"] = sentiment_match.group(1).lower()
                break
        
        # Extract key themes
        theme_patterns = [
            r"(?:key|main|primary)\s+themes?[:\s]+([^.]+)",
            r"(?:key|main|primary)\s+factors?[:\s]+([^.]+)",
            r"(?:markets are|trading is)\s+focused on\s+([^.]+)",
        ]
        
        for pattern in theme_patterns:
            theme_matches = re.finditer(pattern, text, re.I)
            for match in theme_matches:
                try:
                    themes_text = match.group(1).strip()
                    # Split by commas or "and"
                    themes = re.split(r'(?:,\s*|\s+and\s+)', themes_text)
                    for theme in themes:
                        if theme and len(theme) > 3:  # Avoid short/meaningless matches
                            if theme.strip() not in result["key_themes"]:
                                result["key_themes"].append(theme.strip())
                except (IndexError, AttributeError):
                    pass
        
        # Extract currency mentions with sentiment
        currency_codes = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
        for currency in currency_codes:
            # Look for currency mentions in proximity to sentiment words
            currency_pattern = fr"{currency}\s+(?:\w+\s+){{0,5}}(strengthening|weakening|bullish|bearish|outperforming|underperforming)"
            alt_pattern = fr"(strengthening|weakening|bullish|bearish|outperforming|underperforming)(?:\s+\w+){{0,5}}\s+{currency}"
            
            # Check both patterns
            for pattern in [currency_pattern, alt_pattern]:
                currency_matches = re.finditer(pattern, text, re.I)
                for match in currency_matches:
                    sentiment = match.group(1).lower()
                    # Normalize sentiment terms
                    if sentiment in ["strengthening", "outperforming", "bullish"]:
                        normalized_sentiment = "bullish"
                    elif sentiment in ["weakening", "underperforming", "bearish"]:
                        normalized_sentiment = "bearish"
                    else:
                        normalized_sentiment = sentiment
                    
                    if currency not in result["currency_mentions"]:
                        result["currency_mentions"][currency] = []
                    
                    if normalized_sentiment not in result["currency_mentions"][currency]:
                        result["currency_mentions"][currency].append(normalized_sentiment)
        
        # Extract important events
        event_patterns = [
            r"(?:important|key|upcoming|major)\s+events?[:\s]+([^.]+)",
            r"(?:watch|monitor)\s+for[:\s]+([^.]+)",
            r"(?:upcoming|scheduled)\s+(?:releases|announcements)[:\s]+([^.]+)",
        ]
        
        for pattern in event_patterns:
            event_matches = re.finditer(pattern, text, re.I)
            for match in event_matches:
                try:
                    events_text = match.group(1).strip()
                    # Split by commas, semicolons, or "and"
                    events = re.split(r'(?:[,;]\s*|\s+and\s+)', events_text)
                    for event in events:
                        if event and len(event) > 5:  # Avoid short/meaningless matches
                            if event.strip() not in result["important_events"]:
                                result["important_events"].append(event.strip())
                except (IndexError, AttributeError):
                    pass
        
        # Extract risk factors
        risk_patterns = [
            r"(?:risk|downside)\s+factors?[:\s]+([^.]+)",
            r"(?:risks|concerns)\s+include[:\s]+([^.]+)",
            r"(?:market|traders)\s+(?:are )?concerned about[:\s]+([^.]+)",
        ]
        
        for pattern in risk_patterns:
            risk_matches = re.finditer(pattern, text, re.I)
            for match in risk_matches:
                try:
                    risks_text = match.group(1).strip()
                    # Split by commas or "and"
                    risks = re.split(r'(?:,\s*|\s+and\s+)', risks_text)
                    for risk in risks:
                        if risk and len(risk) > 5:  # Avoid short/meaningless matches
                            if risk.strip() not in result["risk_factors"]:
                                result["risk_factors"].append(risk.strip())
                except (IndexError, AttributeError):
                    pass
        
        # Extract trading recommendations
        rec_patterns = [
            r"(?:recommend|suggest|advise)[:\s]+([^.]+)",
            r"traders should[:\s]+([^.]+)",
            r"(?:trading|investment)\s+(?:strategy|approach)[:\s]+([^.]+)",
        ]
        
        for pattern in rec_patterns:
            rec_matches = re.finditer(pattern, text, re.I)
            for match in rec_matches:
                try:
                    rec_text = match.group(1).strip()
                    if rec_text and len(rec_text) > 10:  # Ensure it's meaningful
                        if rec_text not in result["trading_recommendations"]:
                            result["trading_recommendations"].append(rec_text)
                except (IndexError, AttributeError):
                    pass
        
        logger.debug("Finished parsing general market analysis")
        return result
    
    def detect_content_type(self, text: str) -> str:
        """
        Detect the type of content in the text response.
        
        Args:
            text: Raw text from Perplexity API
            
        Returns:
            Content type: 'currency_pair', 'market_news', 'economic_indicator', or 'general'
        """
        # Check for currency pair analysis markers
        if (re.search(r"technical analysis", text, re.I) and 
            re.search(r"support.{1,10}resistance", text, re.I)):
            return "currency_pair"
        
        # Check for market news markers
        if ((re.search(r"recent news", text, re.I) or re.search(r"market news", text, re.I)) and
            (re.search(r"source", text, re.I) or re.search(r"reported by", text, re.I))):
            return "market_news"
        
        # Check for economic indicator markers
        if ((re.search(r"economic indicators?", text, re.I) or re.search(r"economic data", text, re.I)) and
            (re.search(r"previous", text, re.I) or re.search(r"forecast", text, re.I))):
            return "economic_indicator"
        
        # Default to general analysis
        return "general"
    
    def parse_response(self, text: str, query_type: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Parse response based on detected or specified type.
        
        Args:
            text: Raw text from Perplexity API
            query_type: Type of query that was sent (if known)
            **kwargs: Additional context parameters
            
        Returns:
            Parsed data in appropriate format
        """
        # Detect content type if not provided
        content_type = query_type if query_type else self.detect_content_type(text)
        
        result = {
            "content_type": content_type,
            "timestamp": datetime.now().isoformat(),
            "raw_text": text,
            "parsed_data": None
        }
        
        # Parse based on content type
        if content_type == "currency_pair":
            pair = kwargs.get("pair", "UNKNOWN")
            result["parsed_data"] = self.parse_currency_pair_analysis(text, pair)
            
        elif content_type == "market_news":
            result["parsed_data"] = self.parse_market_news(text)
            
        elif content_type == "economic_indicator":
            result["parsed_data"] = self.parse_economic_indicators(text)
            
        elif content_type == "general":
            result["parsed_data"] = self.parse_general_market_analysis(text)
            
        else:
            logger.warning(f"Unknown content type: {content_type}, using general")
            result["parsed_data"] = self.parse_general_market_analysis(text)
        
        logger.info(f"Parsed response of type {content_type}")
        return result


# Singleton instance
parser = PerplexityParser()


def get_parser() -> PerplexityParser:
    """
    Get the PerplexityParser instance.
    
    Returns:
        The PerplexityParser singleton
    """
    return parser 