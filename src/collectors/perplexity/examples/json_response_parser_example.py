#!/usr/bin/env python3
"""
Example demonstrating the use of the Perplexity JSON response parser.

This script shows how to use the enhanced structured response parsing
capabilities of the PerplexityClient to get both structured data and
metadata from Perplexity API responses.
"""

import logging
import os
import json
from typing import Dict, Any

from .perplexity.client import get_client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def pretty_print_result(result: Dict[str, Any]) -> None:
    """
    Pretty print the parsed result in a readable format.
    
    Args:
        result: The parsed result from the Perplexity API
    """
    # Print basic info
    print("\n" + "="*80)
    print(f"QUERY: {result.get('query', 'Unknown')}")
    print(f"MODEL: {result.get('model_used', 'Unknown')}")
    print(f"CONTENT TYPE: {result.get('content_type', 'Unknown')}")
    print(f"TOKENS USED: {result.get('total_tokens', 'Unknown')}")
    print("="*80)
    
    # Print text summary (truncated if too long)
    text = result.get('text', '')
    if text:
        print("\nRESPONSE TEXT (EXCERPT):")
        print("-"*80)
        print(text[:500] + "..." if len(text) > 500 else text)
        print("-"*80)
    
    # Print sources if available
    sources = result.get('sources', [])
    if sources:
        print("\nSOURCES:")
        print("-"*80)
        for i, source in enumerate(sources[:3], 1):  # Show up to 3 sources
            print(f"{i}. {source.get('title', 'Untitled')}")
            print(f"   URL: {source.get('url', 'No URL')}")
            print()
        
        if len(sources) > 3:
            print(f"... and {len(sources) - 3} more sources.")
        print("-"*80)
    
    # Print structured data if available
    parsed_data = result.get('parsed_data')
    if parsed_data:
        print("\nSTRUCTURED DATA:")
        print("-"*80)
        
        # Handle different content types differently
        content_type = result.get('content_type')
        
        if content_type == 'currency_pair':
            pair = parsed_data.get('pair', 'Unknown')
            sentiment = parsed_data.get('sentiment', 'Unknown')
            
            print(f"PAIR: {pair}")
            print(f"SENTIMENT: {sentiment}")
            
            # Print support/resistance levels
            levels = parsed_data.get('support_resistance_levels', [])
            if levels:
                print("\nSUPPORT/RESISTANCE LEVELS:")
                for level in levels:
                    print(f"  {level.get('type', 'Unknown').upper()}: {level.get('level')}")
            
            # Print technical indicators
            indicators = parsed_data.get('technical_indicators', {})
            if indicators:
                print("\nTECHNICAL INDICATORS:")
                for indicator, value in indicators.items():
                    print(f"  {indicator.upper()}: {value}")
            
            # Print price targets
            targets = parsed_data.get('price_targets', [])
            if targets:
                print("\nPRICE TARGETS:")
                for target in targets:
                    print(f"  {target.get('type', 'Unknown').upper()}: {target.get('value')}")
        
        elif content_type == 'market_news':
            news_items = parsed_data if isinstance(parsed_data, list) else []
            print(f"Total news items: {len(news_items)}")
            
            for i, item in enumerate(news_items[:3], 1):  # Show up to 3 news items
                print(f"\nNEWS ITEM {i}:")
                print(f"TITLE: {item.get('title', 'No title')}")
                print(f"DATE: {item.get('date', 'No date')}")
                if 'source' in item:
                    print(f"SOURCE: {item.get('source')}")
                if 'impact' in item:
                    print(f"IMPACT: {item.get('impact')}")
            
            if len(news_items) > 3:
                print(f"\n... and {len(news_items) - 3} more news items.")
        
        elif content_type == 'economic_indicator':
            indicators = parsed_data if isinstance(parsed_data, list) else []
            print(f"Total economic indicators: {len(indicators)}")
            
            for i, indicator in enumerate(indicators[:3], 1):  # Show up to 3 indicators
                print(f"\nINDICATOR {i}:")
                print(f"NAME: {indicator.get('indicator', 'Unnamed')}")
                print(f"COUNTRY: {indicator.get('country', 'Unknown')}")
                print(f"DATE: {indicator.get('date', 'No date')}")
                if 'previous_value' in indicator:
                    print(f"PREVIOUS: {indicator.get('previous_value')}")
                if 'forecast_value' in indicator:
                    print(f"FORECAST: {indicator.get('forecast_value')}")
                if 'actual_value' in indicator:
                    print(f"ACTUAL: {indicator.get('actual_value')}")
                if 'importance' in indicator:
                    print(f"IMPORTANCE: {indicator.get('importance')}")
            
            if len(indicators) > 3:
                print(f"\n... and {len(indicators) - 3} more indicators.")
        
        else:  # General market analysis
            sentiment = parsed_data.get('market_sentiment', 'Unknown')
            print(f"MARKET SENTIMENT: {sentiment}")
            
            # Print key themes
            themes = parsed_data.get('key_themes', [])
            if themes:
                print("\nKEY THEMES:")
                for theme in themes[:5]:  # Show up to 5 themes
                    print(f"  - {theme}")
            
            # Print risk factors
            risks = parsed_data.get('risk_factors', [])
            if risks:
                print("\nRISK FACTORS:")
                for risk in risks[:5]:  # Show up to 5 risks
                    print(f"  - {risk}")
            
            # Print trading recommendations
            recs = parsed_data.get('trading_recommendations', [])
            if recs:
                print("\nTRADING RECOMMENDATIONS:")
                for rec in recs[:3]:  # Show up to 3 recommendations
                    print(f"  - {rec}")
        
        print("-"*80)


def main():
    """Run the example."""
    # Get the client
    client = get_client()
    
    # Check if API key is set
    if not client.api_key:
        logger.error("Please set the PERPLEXITY_API_KEY environment variable")
        return
    
    # Example queries for different types of analyses
    queries = [
        {
            "query": "What is the current technical analysis for EUR/USD? Include support and resistance levels.",
            "type": "currency_pair"
        },
        {
            "query": "What are the latest market news affecting forex trading today?",
            "type": "market_news"
        },
        {
            "query": "What are the upcoming economic indicators this week that could affect forex markets?",
            "type": "economic_indicator"
        },
        {
            "query": "What is the current general sentiment in forex markets? What are the key themes?",
            "type": "general"
        }
    ]
    
    # Run each query and display results
    for query_info in queries:
        query_text = query_info["query"]
        query_type = query_info["type"]
        
        print(f"\n\nRunning {query_type} query: {query_text}")
        
        try:
            # Use the structured search method
            result = client.search_structured(
                query_text=query_text,
                query_type=query_type
            )
            
            # Display the result
            pretty_print_result(result)
            
            # Option to save the full result to a file
            # with open(f"{query_type}_example.json", "w") as f:
            #     json.dump(result, f, indent=2)
            
        except Exception as e:
            logger.error(f"Error running query: {str(e)}")
    
    # Close the client
    client.close()


if __name__ == "__main__":
    main() 