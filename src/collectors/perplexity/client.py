"""
Perplexity API Client

This module provides a client for interacting with the Perplexity API
to perform web-based research queries for forex market analysis.
"""

import logging
import json
import time
import os
from typing import Dict, Any, Optional, List, Union
import httpx
from datetime import datetime
import re

# Import the parser
from .perplexity.parser import get_parser

# Set up logging
logger = logging.getLogger(__name__)


class PerplexityClient:
    """
    Client for the Perplexity API to perform web-based research queries.
    
    Provides methods to send queries, handle rate limiting, and process responses.
    """
    
    def __init__(self, 
                 api_key: Optional[str] = None, 
                 base_url: str = "https://api.perplexity.ai",
                 request_timeout: int = 60,
                 retry_delay: int = 5,
                 max_retries: int = 3):
        """
        Initialize the Perplexity API client.
        
        Args:
            api_key: Perplexity API key (defaults to PERPLEXITY_API_KEY env var)
            base_url: Base URL for the Perplexity API
            request_timeout: Timeout for API requests in seconds
            retry_delay: Delay between retries in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.api_key = api_key or os.environ.get("PERPLEXITY_API_KEY")
        if not self.api_key:
            logger.warning("No Perplexity API key provided. Set PERPLEXITY_API_KEY environment variable or pass api_key parameter.")
            
        self.base_url = base_url
        self.request_timeout = request_timeout
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        
        self.httpx_client = httpx.Client(timeout=request_timeout)
        
        logger.info("PerplexityClient initialized")
    
    def query(self, 
              query_text: str, 
              model: str = "sonar-medium-online",
              recency: Optional[str] = None,
              **kwargs) -> Dict[str, Any]:
        """
        Send a query to the Perplexity API.
        
        Args:
            query_text: The query text to send
            model: Model to use (default: sonar-medium-online)
            recency: Time filter for results (day, week, month, year)
            **kwargs: Additional parameters to pass to the API
            
        Returns:
            Response from the Perplexity API as a dictionary
        """
        logger.info(f"Sending query to Perplexity: '{query_text[:50]}...'")
        
        if not self.api_key:
            raise ValueError("No API key provided. Set PERPLEXITY_API_KEY environment variable or pass api_key parameter.")
        
        # Prepare headers
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Prepare payload
        payload = {
            "model": model,
            "query": query_text,
            "search_focus": "internet",
        }
        
        # Add recency if specified
        if recency:
            valid_recency = ["day", "week", "month", "year"]
            if recency in valid_recency:
                payload["search_options"] = {"recency": recency}
            else:
                logger.warning(f"Invalid recency value: {recency}. Using default.")
        
        # Add any additional parameters
        for key, value in kwargs.items():
            if key not in payload:
                payload[key] = value
        
        # Send request with retries
        response_data = None
        retries = 0
        
        while retries <= self.max_retries:
            try:
                # Note the current time for rate limiting
                start_time = time.time()
                
                response = self.httpx_client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                # Check for rate limiting response
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", self.retry_delay))
                    logger.warning(f"Rate limited. Retrying after {retry_after} seconds.")
                    time.sleep(retry_after)
                    retries += 1
                    continue
                
                # Check for successful response
                if response.status_code == 200:
                    response_data = response.json()
                    break
                else:
                    logger.error(f"Error from Perplexity API: {response.status_code} - {response.text}")
                    if retries >= self.max_retries:
                        raise Exception(f"Failed after {retries} retries: {response.status_code} - {response.text}")
                    
                    logger.warning(f"Retrying in {self.retry_delay} seconds... (Attempt {retries+1}/{self.max_retries})")
                    time.sleep(self.retry_delay)
                    retries += 1
                
            except (httpx.RequestError, httpx.TimeoutException) as e:
                logger.error(f"Error connecting to Perplexity API: {str(e)}")
                if retries >= self.max_retries:
                    raise Exception(f"Failed after {retries} retries: {str(e)}")
                
                logger.warning(f"Retrying in {self.retry_delay} seconds... (Attempt {retries+1}/{self.max_retries})")
                time.sleep(self.retry_delay)
                retries += 1
        
        # If we got here without a response, raise an exception
        if not response_data:
            raise Exception("Failed to get response from Perplexity API")
        
        logger.info("Received response from Perplexity API")
        return response_data
    
    def extract_text_from_response(self, response_data: Dict[str, Any]) -> str:
        """
        Extract the main text content from a Perplexity API response.
        
        Args:
            response_data: Response data from Perplexity API
            
        Returns:
            Extracted text content
        """
        try:
            # Extract content from the response based on the Perplexity API structure
            if 'choices' in response_data and len(response_data['choices']) > 0:
                # Get the message content
                message = response_data['choices'][0].get('message', {})
                if 'content' in message:
                    return message['content']
            
            # If we couldn't find the content in the expected structure
            logger.warning("Could not extract content from Perplexity response, using raw response")
            return json.dumps(response_data)
            
        except Exception as e:
            logger.error(f"Error extracting text from Perplexity response: {str(e)}")
            return json.dumps(response_data)
    
    def get_sources_from_response(self, response_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Extract sources/citations from a Perplexity API response.
        
        Args:
            response_data: Response data from Perplexity API
            
        Returns:
            List of source dictionaries with title, url, and snippet
        """
        sources = []
        
        try:
            # Extract sources from the response
            if 'choices' in response_data and len(response_data['choices']) > 0:
                message = response_data['choices'][0].get('message', {})
                
                # Check for sources in message metadata
                if 'tool_calls' in message:
                    for tool_call in message.get('tool_calls', []):
                        if tool_call.get('type') == 'search':
                            function = tool_call.get('function', {})
                            if function.get('name') == 'search':
                                # Try to parse arguments
                                try:
                                    args = json.loads(function.get('arguments', '{}'))
                                    if 'sources' in args and isinstance(args['sources'], list):
                                        for source in args['sources']:
                                            sources.append({
                                                'title': source.get('title', ''),
                                                'url': source.get('url', ''),
                                                'snippet': source.get('snippet', '')
                                            })
                                except json.JSONDecodeError:
                                    logger.warning("Failed to parse sources from tool_calls")
                
                # Check for sources in context citations array
                if not sources and 'context' in message and 'citations' in message['context']:
                    for citation in message['context'].get('citations', []):
                        sources.append({
                            'title': citation.get('title', ''),
                            'url': citation.get('url', ''),
                            'snippet': citation.get('text', '')
                        })
            
        except Exception as e:
            logger.error(f"Error extracting sources from Perplexity response: {str(e)}")
        
        return sources
    
    def search(self, 
               query_text: str, 
               recency: Optional[str] = "month", 
               model: str = "sonar-medium-online") -> Dict[str, Any]:
        """
        Perform a web search query and return processed results.
        
        Args:
            query_text: Query text to send
            recency: Time filter for results (day, week, month, year)
            model: Model to use
            
        Returns:
            Dictionary with response text, sources, and metadata
        """
        # Send the query
        response_data = self.query(query_text, model=model, recency=recency)
        
        # Extract text and sources
        response_text = self.extract_text_from_response(response_data)
        sources = self.get_sources_from_response(response_data)
        
        # Build result
        result = {
            "query": query_text,
            "timestamp": datetime.now().isoformat(),
            "text": response_text,
            "sources": sources,
            "model": model,
            "recency": recency,
            "raw_response": response_data
        }
        
        logger.info(f"Processed search results for query: '{query_text[:50]}...'")
        return result
    
    def search_structured(self,
                         query_text: str,
                         recency: Optional[str] = "month",
                         model: str = "sonar-medium-online",
                         query_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform a web search query and return fully structured results.
        
        This method uses the enhanced JSON parser to extract detailed information
        from the response, including metadata, sources, and parsed content based
        on the detected content type.
        
        Args:
            query_text: Query text to send
            recency: Time filter for results (day, week, month, year)
            model: Model to use
            query_type: Type of query being performed (optional)
            
        Returns:
            Dictionary with fully parsed response data including metadata and
            structured content based on the detected or specified content type
        """
        logger.info(f"Performing structured search: '{query_text[:50]}...'")
        
        # Send the query
        response_data = self.query(query_text, model=model, recency=recency)
        
        # Get the parser instance
        parser = get_parser()
        
        # Use the JSON parser to parse the full response
        parsed_result = parser.parse_json_response(response_data)
        
        # Add the original query information
        parsed_result["query"] = query_text
        parsed_result["recency"] = recency
        
        # If query_type was provided, override the detected content type
        if query_type and "content_type" in parsed_result:
            parsed_result["content_type"] = query_type
            
            # Re-parse the text content if needed with the specified type
            if parsed_result.get("text"):
                if query_type == "currency_pair":
                    # Try to extract the pair from the query
                    pair = "UNKNOWN"
                    pair_match = re.search(r'\b([A-Z]{3}/[A-Z]{3})\b', query_text)
                    if pair_match:
                        pair = pair_match.group(1)
                    parsed_result["parsed_data"] = parser.parse_currency_pair_analysis(
                        parsed_result["text"], pair
                    )
                elif query_type == "market_news":
                    parsed_result["parsed_data"] = parser.parse_market_news(parsed_result["text"])
                elif query_type == "economic_indicator":
                    parsed_result["parsed_data"] = parser.parse_economic_indicators(parsed_result["text"])
                else:
                    parsed_result["parsed_data"] = parser.parse_general_market_analysis(parsed_result["text"])
        
        logger.info(f"Completed structured search for query: '{query_text[:50]}...'")
        return parsed_result
    
    def close(self):
        """Close the HTTP client when done."""
        if self.httpx_client:
            self.httpx_client.close()


# Singleton instance
client = PerplexityClient()


def get_client() -> PerplexityClient:
    """
    Get the PerplexityClient instance.
    
    Returns:
        The PerplexityClient singleton
    """
    return client 