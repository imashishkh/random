#!/usr/bin/env python3
"""
Risk Manager Demo

This script demonstrates how to use the Risk Manager client library
to interact with the Risk Manager API. It shows various operations
such as agent registration, position management, trade approval, and
risk status monitoring.
"""

import os
import sys
import time
import uuid
import json
import logging
from datetime import datetime

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import Risk Manager client
from src.risk.client import RiskManagerClient, RiskManagerConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Run the Risk Manager demonstration."""
    logger.info("Starting Risk Manager Demo")
    
    # Create configuration
    config = RiskManagerConfig(
        api_url="http://localhost:5000",
        api_key="test_key",
        agent_id=str(uuid.uuid4()),
        agent_name="Demo Trading Agent",
        agent_type="demo"
    )
    
    # Create client
    client = RiskManagerClient(config)
    
    # Step 1: Check if API is running
    try:
        logger.info("Checking API health")
        response = client.check_health()
        logger.info(f"API health status: {response.get('status', 'unknown')}")
    except Exception as e:
        logger.error(f"API health check failed: {str(e)}")
        logger.info("Make sure the Risk Manager API is running on http://localhost:5000")
        logger.info("You can start it with: python -m src.risk.api")
        return
    
    # Step 2: Register agent
    try:
        logger.info("Registering agent")
        agent = client.register_agent(
            name=config.agent_name,
            agent_type=config.agent_type,
            description="Demo agent for testing Risk Manager API",
            risk_limits={
                "max_risk_per_trade": 1.0,
                "max_open_positions": 5
            },
            metadata={
                "created_by": "risk_manager_demo.py",
                "purpose": "demonstration"
            }
        )
        logger.info(f"Agent registered with ID: {agent.get('agent_id')}")
    except Exception as e:
        logger.error(f"Agent registration failed: {str(e)}")
        return
    
    # Step 3: Get risk status
    logger.info("Getting current risk status")
    risk_status = client.get_risk_status()
    logger.info(f"Risk level: {risk_status.get('risk_level')}")
    logger.info(f"Account balance: ${risk_status.get('account_balance')}")
    logger.info(f"Position count: {risk_status.get('position_count')}")
    
    # Step 4: Update configuration
    logger.info("Updating risk configuration")
    updated_config = client.update_risk_config({
        "account_balance": 20000.0,
        "max_risk_per_trade": 1.5,
        "max_daily_risk": 8.0
    })
    logger.info(f"Updated config: {json.dumps(updated_config, indent=2)}")
    
    # Step 5: Calculate position size
    logger.info("Calculating position size for EUR/USD trade")
    position_calc = client.calculate_position_size(
        symbol="EURUSD",
        entry_price=1.1200,
        stop_loss=1.1150,
        risk_percent=1.0
    )
    logger.info(f"Calculated position size: {position_calc.get('units')} units")
    logger.info(f"Risk dollars: ${position_calc.get('risk_dollars')}")
    logger.info(f"Notional value: ${position_calc.get('notional_value')}")
    
    # Step 6: Request trade approval
    logger.info("Requesting trade approval")
    trade_request = client.request_trade_approval(
        symbol="EURUSD",
        direction="long",
        entry_price=1.1200,
        stop_loss=1.1150,
        risk_percent=1.0,
        metadata={
            "strategy": "trend_following",
            "timeframe": "H1"
        }
    )
    
    if trade_request.get("approved"):
        logger.info("Trade approved!")
        position_id = trade_request.get("position", {}).get("position_id")
        logger.info(f"Position ID: {position_id}")
        
        # Step 7: Add position if approved
        logger.info("Adding position")
        position = client.add_position(
            symbol="EURUSD",
            direction="long",
            entry_price=1.1200,
            stop_loss=1.1150,
            risk_percent=1.0,
            metadata={
                "strategy": "trend_following",
                "timeframe": "H1",
                "entry_reason": "Breakout of resistance"
            }
        )
        logger.info(f"Position added with ID: {position.get('position_id')}")
        position_id = position.get('position_id')
    else:
        logger.warning("Trade rejected!")
        violations = trade_request.get("analysis", {}).get("violations", [])
        for violation in violations:
            logger.warning(f"Violation: {violation}")
        # Create a test position ID for demonstration
        position_id = str(uuid.uuid4())
    
    # Step 8: Get positions
    logger.info("Getting all positions")
    positions = client.get_positions()
    logger.info(f"Found {len(positions)} positions")
    
    if positions:
        for pos in positions:
            logger.info(f"Position: {pos.get('symbol')} {pos.get('direction')} - ID: {pos.get('position_id')}")
    
    # Step 9: Get specific position
    if position_id:
        logger.info(f"Getting position details for ID: {position_id}")
        try:
            position_details = client.get_position(position_id)
            if position_details:
                logger.info(f"Position details: {json.dumps(position_details, indent=2)}")
            else:
                logger.warning(f"Position with ID {position_id} not found")
        except Exception as e:
            logger.error(f"Error getting position: {str(e)}")
    
    # Step 10: Get agent info
    logger.info(f"Getting agent info for ID: {config.agent_id}")
    agent_info = client.get_agent(config.agent_id)
    if agent_info:
        logger.info(f"Agent info: {json.dumps(agent_info, indent=2)}")
    
    # Step 11: Update agent
    logger.info("Updating agent information")
    updated_agent = client.update_agent(
        agent_id=config.agent_id,
        name=f"{config.agent_name} (Updated)",
        risk_limits={
            "max_risk_per_trade": 0.5,
            "max_open_positions": 3
        },
        metadata={
            "updated_at": datetime.now().isoformat(),
            "performance_score": 85
        }
    )
    logger.info(f"Agent updated: {json.dumps(updated_agent, indent=2)}")
    
    # Step 12: Remove position
    if position_id and positions:
        logger.info(f"Removing position with ID: {position_id}")
        try:
            result = client.remove_position(position_id)
            if result:
                logger.info(f"Position {position_id} removed successfully")
            else:
                logger.warning(f"Failed to remove position {position_id}")
        except Exception as e:
            logger.error(f"Error removing position: {str(e)}")
    
    # Final status check
    logger.info("Getting final risk status")
    final_status = client.get_risk_status()
    logger.info(f"Final risk level: {final_status.get('risk_level')}")
    logger.info(f"Final position count: {final_status.get('position_count')}")
    
    logger.info("Risk Manager Demo completed")

if __name__ == "__main__":
    main() 