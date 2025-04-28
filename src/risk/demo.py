#!/usr/bin/env python3
"""
Risk Manager Integration Demo

This script demonstrates the integration of trading agents with the Risk Manager API.
It creates test agents, registers them with the risk manager, and simulates various
trading scenarios to test the risk controls.
"""

import time
import logging
import random
import argparse
from typing import Dict, List, Any, Optional

from .client import RiskManagerClient
from ..agents.risk import create_example_risk_aware_agent, RiskAwareBaseAgent

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Sample forex symbols for testing
FOREX_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", 
    "NZDUSD", "USDCAD", "EURGBP", "EURJPY", "GBPJPY"
]

# Sample prices for testing
SYMBOL_PRICES = {
    "EURUSD": 1.0850,
    "GBPUSD": 1.2750,
    "USDJPY": 150.50,
    "AUDUSD": 0.6580,
    "USDCHF": 0.9120,
    "NZDUSD": 0.6120,
    "USDCAD": 1.3580,
    "EURGBP": 0.8580,
    "EURJPY": 163.10,
    "GBPJPY": 191.30
}


def create_test_agents(base_url: str, api_key: Optional[str] = None, num_agents: int = 3) -> List[RiskAwareBaseAgent]:
    """Create test agents for the demo."""
    agents = []
    
    # Agent types
    agent_types = ["trend_following", "mean_reversion", "breakout", "scalping", "ml_prediction"]
    
    for i in range(num_agents):
        agent_id = f"test-agent-{i+1}"
        agent_type = agent_types[i % len(agent_types)]
        agent_name = f"{agent_type.replace('_', ' ').title()} Agent {i+1}"
        
        # Assign different risk parameters to each agent
        max_risk_per_trade = 0.5 + (i * 0.5)  # 0.5%, 1.0%, 1.5%, etc.
        max_total_risk = 2.0 + (i * 1.0)      # 2.0%, 3.0%, 4.0%, etc.
        
        # Assign random symbols to each agent
        allowed_symbols = random.sample(FOREX_SYMBOLS, min(len(FOREX_SYMBOLS), 3 + i))
        
        # Create agent
        agent = create_example_risk_aware_agent(
            agent_id=agent_id,
            agent_name=agent_name,
            base_url=base_url,
            api_key=api_key,
            allowed_symbols=allowed_symbols
        )
        
        agents.append(agent)
        logger.info(f"Created {agent_name} (ID: {agent_id})")
    
    return agents


def simulate_random_trade(
    agent: RiskAwareBaseAgent, 
    account_equity: float = 10000.0
) -> Dict[str, Any]:
    """Simulate a random trade for an agent."""
    # Select random symbol from allowed symbols
    if agent.allowed_symbols:
        symbol = random.choice(agent.allowed_symbols)
    else:
        symbol = random.choice(FOREX_SYMBOLS)
    
    # Get price for the symbol
    price = SYMBOL_PRICES.get(symbol, 1.0)
    
    # Randomize direction
    is_long = random.choice([True, False])
    
    # Calculate stop loss and take profit
    spread = price * 0.0010  # Simulated 1 pip spread
    
    if is_long:
        stop_loss = price - (price * random.uniform(0.005, 0.015))
        take_profit = price + (price * random.uniform(0.010, 0.030))
    else:
        stop_loss = price + (price * random.uniform(0.005, 0.015))
        take_profit = price - (price * random.uniform(0.010, 0.030))
    
    # Adjust for variable risk
    risk_percent = random.uniform(0.5, 2.0)
    sizer_params = {"risk_percent": risk_percent}
    
    # Request trade approval
    try:
        approval_data = agent.risk_client.request_trade_approval(
            symbol=symbol,
            entry_price=price,
            is_long=is_long,
            stop_loss=stop_loss,
            take_profit=take_profit,
            account_balance=account_equity,
            sizer_type="fixed_percent",
            sizer_params=sizer_params
        )
        
        # Log result
        if approval_data.get('approved', False):
            logger.info(f"Trade APPROVED for {agent.agent_name}: {symbol} {'LONG' if is_long else 'SHORT'} @ {price:.4f}, "
                        f"Position Size: {approval_data.get('position_size', 0):.2f}, "
                        f"Risk: {approval_data.get('risk_percent', 0):.2f}%")
        else:
            reason = approval_data.get('rejection_reason', 'Unknown reason')
            logger.warning(f"Trade REJECTED for {agent.agent_name}: {symbol} {'LONG' if is_long else 'SHORT'} @ {price:.4f}, "
                          f"Reason: {reason}")
        
        return {
            'agent_id': agent.agent_id,
            'agent_name': agent.agent_name,
            'symbol': symbol,
            'entry_price': price,
            'is_long': is_long,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk_percent': risk_percent,
            'approval_data': approval_data
        }
        
    except Exception as e:
        logger.error(f"Error requesting trade approval for {agent.agent_name}: {str(e)}")
        return {
            'agent_id': agent.agent_id,
            'agent_name': agent.agent_name,
            'symbol': symbol,
            'error': str(e)
        }


def update_positions(client: RiskManagerClient, trades: List[Dict[str, Any]]) -> None:
    """Update position tracking with approved trades."""
    for trade in trades:
        approval_data = trade.get('approval_data', {})
        
        # Only register approved trades
        if approval_data.get('approved', False):
            symbol = trade['symbol']
            try:
                # Register position with the risk manager
                client.session.post(
                    f"{client.base_url}/api/risk/positions",
                    json={
                        'symbol': symbol,
                        'position_result': approval_data,
                        'agent_id': trade['agent_id']
                    },
                    headers=client.session.headers,
                    timeout=client.timeout
                )
                logger.info(f"Registered position for {symbol}")
            except Exception as e:
                logger.error(f"Error registering position for {symbol}: {str(e)}")


def run_demo(
    base_url: str = "http://localhost:5000",
    api_key: Optional[str] = None,
    num_agents: int = 3,
    num_rounds: int = 5,
    account_equity: float = 10000.0,
    round_delay: float = 2.0
):
    """Run the risk manager integration demo."""
    logger.info("Starting Risk Manager Integration Demo")
    
    # Create a direct client for administrative operations
    admin_client = RiskManagerClient(
        base_url=base_url,
        api_key=api_key,
        auto_register=False
    )
    
    # Update account equity
    try:
        admin_client.update_risk_config({'account_equity': account_equity})
        logger.info(f"Updated account equity to ${account_equity:,.2f}")
    except Exception as e:
        logger.error(f"Error updating account equity: {str(e)}")
    
    # Create test agents
    agents = create_test_agents(base_url, api_key, num_agents)
    
    # Run simulation rounds
    for round_num in range(1, num_rounds + 1):
        logger.info(f"\n===== ROUND {round_num}/{num_rounds} =====")
        
        approved_trades = []
        
        # Each agent attempts a trade
        for agent in agents:
            trade_result = simulate_random_trade(agent, account_equity)
            
            # Save approved trades for position registration
            if trade_result.get('approval_data', {}).get('approved', False):
                approved_trades.append(trade_result)
            
            # Small delay between trades
            time.sleep(0.5)
        
        # Update positions after all trades
        # NOTE: This would typically be handled by the exchange integration
        # We're simulating it here for demo purposes
        # update_positions(admin_client, approved_trades)
        
        # Get risk status
        try:
            risk_status = admin_client.get_risk_status()
            current_risk = risk_status.get('current_portfolio_risk_percent', 0)
            logger.info(f"Current Portfolio Risk: {current_risk:.2f}%")
        except Exception as e:
            logger.error(f"Error getting risk status: {str(e)}")
        
        # Delay between rounds
        if round_num < num_rounds:
            logger.info(f"Waiting {round_delay} seconds until next round...")
            time.sleep(round_delay)
    
    logger.info("\nDemo completed successfully!")


def main():
    """Main entry point for the demo script."""
    parser = argparse.ArgumentParser(description="Risk Manager Integration Demo")
    parser.add_argument("--url", default="http://localhost:5000", help="Base URL for the Risk Manager API")
    parser.add_argument("--api-key", help="API key for authentication")
    parser.add_argument("--agents", type=int, default=3, help="Number of test agents to create")
    parser.add_argument("--rounds", type=int, default=5, help="Number of trading rounds to simulate")
    parser.add_argument("--equity", type=float, default=10000.0, help="Starting account equity")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between trading rounds in seconds")
    args = parser.parse_args()
    
    run_demo(
        base_url=args.url,
        api_key=args.api_key,
        num_agents=args.agents,
        num_rounds=args.rounds,
        account_equity=args.equity,
        round_delay=args.delay
    )


if __name__ == "__main__":
    main() 