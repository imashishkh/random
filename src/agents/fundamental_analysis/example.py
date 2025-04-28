"""
Example usage of the Fundamental Analysis Agent.

This module provides examples of how to use the FundamentalAnalysisAgent
to analyze different currency pairs and generate trading signals.
"""

import asyncio
import os
import json
from datetime import datetime
from typing import Dict, Any

from .fundamental_analysis.agent import FundamentalAnalysisAgent


async def example_analysis():
    """Run an example fundamental analysis for multiple currency pairs."""
    
    # Load config
    config = {
        'news_api_key': os.environ.get('NEWS_API_KEY', ''),
        'signal': {
            'weights': {
                'financial': 0.3,
                'economic': 0.4,
                'news': 0.3
            },
            'thresholds': {
                'buy': 0.6,
                'sell': 0.6,
                'neutral': 0.2
            }
        },
        'cache_ttl': {
            'financial': 86400,  # 24 hours
            'economic': 43200,   # 12 hours
            'news': 3600         # 1 hour
        }
    }
    
    # Create agent
    agent = FundamentalAnalysisAgent(config=config, name="Example-Agent")
    
    # Currency pairs to analyze
    currency_pairs = ['EUR/USD', 'GBP/USD', 'USD/JPY']
    
    # Run analysis for each pair
    for pair in currency_pairs:
        try:
            print(f"\nAnalyzing {pair}...")
            result = await agent.analyze(
                currency_pair=pair,
                timeframe='medium',
                include_companies=True,
                include_economic=True,
                include_news=True
            )
            
            # Print signal
            signal = result['signal']
            print(f"Signal: {signal['type'].upper()} with confidence {signal['confidence']:.2f}")
            print(f"Score components: Financial={signal['components']['financial']:.2f}, "
                  f"Economic={signal['components']['economic']:.2f}, "
                  f"News={signal['components']['news']:.2f}")
            
        except Exception as e:
            print(f"Error analyzing {pair}: {str(e)}")
    
    # Get the latest signals
    latest_signals = agent.get_latest_signals()
    print(f"\nGenerated {len(latest_signals)} signals:")
    
    for signal in latest_signals:
        print(f"- {signal['currency_pair']}: {signal['type'].upper()} ({signal['timeframe']}), "
              f"confidence: {signal['confidence']:.2f}")


async def detailed_analysis(currency_pair: str, timeframe: str = 'medium') -> Dict[str, Any]:
    """
    Run a detailed fundamental analysis for a specific currency pair.
    
    Args:
        currency_pair: Currency pair to analyze
        timeframe: Analysis timeframe ('short', 'medium', 'long')
        
    Returns:
        Analysis results dictionary
    """
    # Load config
    config = {
        'news_api_key': os.environ.get('NEWS_API_KEY', ''),
        'signal': {
            'weights': {
                'financial': 0.3,
                'economic': 0.4,
                'news': 0.3
            }
        }
    }
    
    # Create agent
    agent = FundamentalAnalysisAgent(config=config, name="Detailed-Agent")
    
    # Run analysis
    result = await agent.analyze(
        currency_pair=currency_pair,
        timeframe=timeframe,
        include_companies=True,
        include_economic=True,
        include_news=True
    )
    
    return result


def save_analysis_result(result: Dict[str, Any], filename: str) -> None:
    """
    Save analysis results to a JSON file.
    
    Args:
        result: Analysis results
        filename: Output filename
    """
    # Create timestamped filename if not provided
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pair = result['currency_pair'].replace('/', '_')
        filename = f"analysis_{pair}_{timestamp}.json"
    
    # Ensure the directory exists
    os.makedirs('analysis_results', exist_ok=True)
    file_path = os.path.join('analysis_results', filename)
    
    # Save to file
    with open(file_path, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"Analysis saved to {file_path}")


if __name__ == "__main__":
    # Run the example
    asyncio.run(example_analysis())
    
    # Uncomment to run a detailed analysis and save results
    # result = asyncio.run(detailed_analysis('EUR/USD', 'medium'))
    # save_analysis_result(result, 'eur_usd_analysis.json') 