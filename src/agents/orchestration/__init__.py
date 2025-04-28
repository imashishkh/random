"""
Signal Orchestration System

This package provides a comprehensive system for validating, filtering, and orchestrating
trading signals across multiple trading pairs.
"""

import logging
from typing import Dict, Any, Optional

from .base_orchestrator import BaseOrchestrator
from .signal_orchestrator import SignalOrchestrator
from .market_conditions_provider import MarketConditionsProvider
from .validation.statistical_validator import StatisticalValidator
from .filtering.market_condition_filter import MarketConditionFilter
from .api.signal_api import SignalAPI

def setup_orchestration_system(config: Dict[str, Any], price_data_provider) -> Dict[str, Any]:
    """
    Set up the complete signal orchestration system.
    
    Args:
        config: Configuration dictionary
        price_data_provider: Object that provides price data for market analysis
        
    Returns:
        Dictionary containing initialized components
    """
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.get("log_level", "INFO").upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger("orchestration")
    
    # Initialize market conditions provider
    market_provider = MarketConditionsProvider(
        config=config.get("market_conditions", {}),
        price_data_provider=price_data_provider
    )
    
    # Initialize signal orchestrator
    orchestrator = SignalOrchestrator(config=config.get("orchestrator", {}))
    
    # Create market condition provider function
    def get_market_conditions(trading_pair):
        return market_provider.get_market_conditions(trading_pair)
    
    # Register market conditions provider
    orchestrator.register_market_condition_provider(
        provider_id="default",
        provider_func=get_market_conditions
    )
    
    # Initialize validators
    statistical_validator = StatisticalValidator(
        name="statistical_validator",
        config=config.get("validators", {}).get("statistical", {})
    )
    
    # Register validators
    orchestrator.register_validator(statistical_validator)
    
    # Initialize filters
    market_filter = MarketConditionFilter(
        name="market_condition_filter",
        config=config.get("filters", {}).get("market_condition", {})
    )
    
    # Register filters
    orchestrator.register_filter(market_filter)
    
    # Initialize API
    signal_api = SignalAPI(
        orchestrator=orchestrator,
        config=config.get("api", {})
    )
    
    logger.info("Signal orchestration system initialized")
    
    # Return initialized components
    return {
        "orchestrator": orchestrator,
        "market_provider": market_provider,
        "validators": {
            "statistical": statistical_validator
        },
        "filters": {
            "market_condition": market_filter
        },
        "api": signal_api
    } 