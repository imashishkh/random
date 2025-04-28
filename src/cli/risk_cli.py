#!/usr/bin/env python3
"""
Command-Line Interface for Risk Management

This module provides a command-line interface for interacting with the Risk Manager,
including querying risk status, managing agent registrations, and updating risk settings.
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from tabulate import tabulate
from typing import Dict, List, Any, Optional, Union

from ..risk.client import RiskManagerClient

# Setup logger
logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Set up logging configuration."""
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def pretty_print_json(data: Union[Dict, List]):
    """Print JSON data in a formatted way."""
    print(json.dumps(data, indent=2))


def format_percent(value: float) -> str:
    """Format a value as a percentage."""
    return f"{value:.2f}%"


def format_currency(value: float) -> str:
    """Format a value as currency."""
    return f"${value:,.2f}"


def format_direction(is_long: bool) -> str:
    """Format a position direction."""
    return "LONG" if is_long else "SHORT"


def show_risk_status(client: RiskManagerClient, agent_id: Optional[str] = None, json_output: bool = False):
    """Show current risk status."""
    try:
        risk_status = client.get_risk_status()
        
        if json_output:
            pretty_print_json(risk_status)
            return
        
        # Print account information
        print("\n===== RISK STATUS =====")
        print(f"Account Equity: {format_currency(risk_status.get('account_equity', 0))}")
        print(f"Current Portfolio Risk: {format_percent(risk_status.get('current_portfolio_risk_percent', 0))}")
        print(f"Max Portfolio Risk: {format_percent(risk_status.get('max_portfolio_risk_percent', 0))}")
        print(f"Max Asset Risk: {format_percent(risk_status.get('max_asset_risk_percent', 0))}")
        print(f"Max Leverage: {risk_status.get('max_leverage', 0):.1f}x")
        
        # Print current positions
        positions = []
        for symbol, pos in risk_status.get('current_positions', {}).items():
            metadata = pos.get('metadata', {})
            positions.append([
                symbol,
                format_direction(metadata.get('is_long', True)),
                f"{pos.get('size', 0):.2f}",
                format_currency(pos.get('value', 0)),
                format_currency(pos.get('risk_amount', 0)),
                format_percent(pos.get('risk_percent', 0))
            ])
        
        if positions:
            print("\n----- CURRENT POSITIONS -----")
            headers = ["Symbol", "Direction", "Size", "Value", "Risk Amount", "Risk %"]
            print(tabulate(positions, headers=headers, tablefmt="pretty"))
        else:
            print("\nNo current positions.")
            
    except Exception as e:
        logger.error(f"Error getting risk status: {str(e)}")
        sys.exit(1)


def show_agents(client: RiskManagerClient, json_output: bool = False):
    """Show registered trading agents."""
    try:
        # Make direct API request as the client doesn't have a method for this
        response = client.session.get(f"{client.base_url}/api/risk/agents", 
                                      headers=client.session.headers, 
                                      timeout=client.timeout)
        response.raise_for_status()
        data = response.json()
        
        agents = data.get('data', [])
        
        if json_output:
            pretty_print_json(agents)
            return
        
        if not agents:
            print("\nNo agents registered.")
            return
        
        agent_rows = []
        for agent in agents:
            # Format allowed symbols
            allowed_symbols = ", ".join(agent.get('allowed_symbols', []))
            if len(allowed_symbols) > 20:
                allowed_symbols = allowed_symbols[:17] + "..."
                
            # Format registered_at date
            registered_at = agent.get('registered_at', '')
            if registered_at:
                try:
                    dt = datetime.fromisoformat(registered_at.replace('Z', '+00:00'))
                    registered_at = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    pass
            
            agent_rows.append([
                agent.get('id', ''),
                agent.get('name', ''),
                agent.get('type', ''),
                format_percent(agent.get('max_risk_per_trade', 0)),
                format_percent(agent.get('max_total_risk', 0)),
                allowed_symbols,
                "Active" if agent.get('active', True) else "Inactive",
                registered_at
            ])
        
        print("\n===== REGISTERED AGENTS =====")
        headers = ["ID", "Name", "Type", "Max Risk/Trade", "Max Total Risk", "Allowed Symbols", "Status", "Registered At"]
        print(tabulate(agent_rows, headers=headers, tablefmt="pretty"))
            
    except Exception as e:
        logger.error(f"Error getting agents: {str(e)}")
        sys.exit(1)


def show_agent(client: RiskManagerClient, agent_id: str, json_output: bool = False):
    """Show details about a specific agent."""
    try:
        agent_info = client.get_agent_info(agent_id)
        
        if json_output:
            pretty_print_json(agent_info)
            return
        
        print(f"\n===== AGENT: {agent_id} =====")
        print(f"Name: {agent_info.get('name', '')}")
        print(f"Type: {agent_info.get('type', '')}")
        print(f"Max Risk per Trade: {format_percent(agent_info.get('max_risk_per_trade', 0))}")
        print(f"Max Total Risk: {format_percent(agent_info.get('max_total_risk', 0))}")
        print(f"Status: {'Active' if agent_info.get('active', True) else 'Inactive'}")
        
        # Display allowed symbols
        allowed_symbols = agent_info.get('allowed_symbols', [])
        if allowed_symbols:
            print("\nAllowed Symbols:")
            for i, symbol in enumerate(allowed_symbols):
                print(f"  - {symbol}", end=", " if (i + 1) % 5 != 0 else "\n")
            print()  # Extra newline
        else:
            print("\nAllowed Symbols: All")
            
    except Exception as e:
        logger.error(f"Error getting agent info: {str(e)}")
        sys.exit(1)


def register_agent(client: RiskManagerClient, agent_id: str, agent_name: str, agent_type: str,
                  max_risk_per_trade: float = 1.0, max_total_risk: float = 5.0,
                  allowed_symbols: Optional[List[str]] = None, json_output: bool = False):
    """Register a new trading agent."""
    try:
        result = client.register_agent(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=agent_type,
            max_risk_per_trade=max_risk_per_trade,
            max_total_risk=max_total_risk,
            allowed_symbols=allowed_symbols
        )
        
        if json_output:
            pretty_print_json(result)
            return
        
        print(f"\nAgent {agent_id} registered successfully!")
        print(f"Registered at: {result.get('registered_at', '')}")
            
    except Exception as e:
        logger.error(f"Error registering agent: {str(e)}")
        sys.exit(1)


def update_risk_config(client: RiskManagerClient, account_equity: Optional[float] = None,
                      max_portfolio_risk: Optional[float] = None, max_asset_risk: Optional[float] = None,
                      max_leverage: Optional[float] = None, json_output: bool = False):
    """Update risk manager configuration."""
    try:
        # Prepare update data (include only non-None values)
        update_data = {}
        if account_equity is not None:
            update_data['account_equity'] = account_equity
        if max_portfolio_risk is not None:
            update_data['max_portfolio_risk_percent'] = max_portfolio_risk
        if max_asset_risk is not None:
            update_data['max_asset_risk_percent'] = max_asset_risk
        if max_leverage is not None:
            update_data['max_leverage'] = max_leverage
        
        if not update_data:
            logger.error("No update parameters provided")
            sys.exit(1)
        
        success = client.update_risk_config(update_data)
        
        if json_output:
            pretty_print_json({"success": success})
            return
        
        if success:
            print("\nRisk configuration updated successfully!")
            
            # Show updated configuration
            show_risk_status(client, json_output=json_output)
        else:
            print("\nFailed to update risk configuration.")
            
    except Exception as e:
        logger.error(f"Error updating risk configuration: {str(e)}")
        sys.exit(1)


def simulate_trade_approval(client: RiskManagerClient, symbol: str, entry_price: float, is_long: bool,
                           stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
                           sizer_type: Optional[str] = None, risk_percent: Optional[float] = None,
                           json_output: bool = False):
    """Simulate a trade approval request."""
    try:
        # Prepare sizer params if risk_percent is provided
        sizer_params = None
        if risk_percent is not None:
            sizer_params = {"risk_percent": risk_percent}
        
        # Request trade approval
        approval_data = client.request_trade_approval(
            symbol=symbol,
            entry_price=entry_price,
            is_long=is_long,
            stop_loss=stop_loss,
            take_profit=take_profit,
            sizer_type=sizer_type,
            sizer_params=sizer_params
        )
        
        if json_output:
            pretty_print_json(approval_data)
            return
        
        # Print approval result
        approved = approval_data.get('approved', False)
        print(f"\n===== TRADE {'APPROVED' if approved else 'REJECTED'} =====")
        print(f"Symbol: {symbol}")
        print(f"Direction: {format_direction(is_long)}")
        print(f"Entry Price: {entry_price}")
        
        if stop_loss:
            print(f"Stop Loss: {stop_loss}")
        if take_profit:
            print(f"Take Profit: {take_profit}")
        
        if approved:
            print(f"Position Size: {approval_data.get('position_size', 0):.2f}")
            print(f"Position Value: {format_currency(approval_data.get('position_value', 0))}")
            print(f"Risk Amount: {format_currency(approval_data.get('risk_amount', 0))}")
            print(f"Risk Percent: {format_percent(approval_data.get('risk_percent', 0))}")
            print(f"Approval ID: {approval_data.get('approval_id', 'N/A')}")
        else:
            print(f"Rejection Reason: {approval_data.get('rejection_reason', 'Unknown reason')}")
            
    except Exception as e:
        logger.error(f"Error simulating trade approval: {str(e)}")
        sys.exit(1)


def main():
    """Main entry point for the command-line interface."""
    parser = argparse.ArgumentParser(description="Risk Manager CLI")
    
    # Global options
    parser.add_argument("--url", default="http://localhost:5000", help="Base URL for the Risk Manager API")
    parser.add_argument("--api-key", help="API key for authentication")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # status command
    status_parser = subparsers.add_parser("status", help="Show current risk status")
    status_parser.add_argument("--agent", help="Filter status for a specific agent")
    
    # agents command
    agents_parser = subparsers.add_parser("agents", help="List registered trading agents")
    
    # agent command
    agent_parser = subparsers.add_parser("agent", help="Show details about a specific agent")
    agent_parser.add_argument("agent_id", help="ID of the agent to show")
    
    # register-agent command
    register_parser = subparsers.add_parser("register-agent", help="Register a new trading agent")
    register_parser.add_argument("agent_id", help="ID for the new agent")
    register_parser.add_argument("agent_name", help="Name for the new agent")
    register_parser.add_argument("agent_type", help="Type of the new agent")
    register_parser.add_argument("--max-risk-per-trade", type=float, default=1.0, help="Maximum risk percentage per trade")
    register_parser.add_argument("--max-total-risk", type=float, default=5.0, help="Maximum total risk percentage")
    register_parser.add_argument("--allowed-symbols", nargs="+", help="List of allowed symbols for the agent")
    
    # update-config command
    update_parser = subparsers.add_parser("update-config", help="Update risk manager configuration")
    update_parser.add_argument("--account-equity", type=float, help="New account equity value")
    update_parser.add_argument("--max-portfolio-risk", type=float, help="New maximum portfolio risk percentage")
    update_parser.add_argument("--max-asset-risk", type=float, help="New maximum asset risk percentage")
    update_parser.add_argument("--max-leverage", type=float, help="New maximum leverage")
    
    # simulate-trade command
    simulate_parser = subparsers.add_parser("simulate-trade", help="Simulate a trade approval request")
    simulate_parser.add_argument("symbol", help="Trading symbol (e.g., 'EURUSD')")
    simulate_parser.add_argument("entry_price", type=float, help="Entry price for the trade")
    simulate_parser.add_argument("--direction", choices=["long", "short"], default="long", help="Trade direction (default: long)")
    simulate_parser.add_argument("--stop-loss", type=float, help="Stop loss price")
    simulate_parser.add_argument("--take-profit", type=float, help="Take profit price")
    simulate_parser.add_argument("--sizer-type", help="Position sizer type (e.g., 'fixed_percent')")
    simulate_parser.add_argument("--risk-percent", type=float, help="Risk percentage (for fixed_percent sizer)")
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.verbose)
    
    # Create risk client
    risk_client = RiskManagerClient(
        base_url=args.url,
        api_key=args.api_key,
        auto_register=False
    )
    
    # Execute command
    if args.command == "status":
        show_risk_status(risk_client, args.agent, args.json)
    elif args.command == "agents":
        show_agents(risk_client, args.json)
    elif args.command == "agent":
        show_agent(risk_client, args.agent_id, args.json)
    elif args.command == "register-agent":
        register_agent(
            risk_client,
            args.agent_id,
            args.agent_name,
            args.agent_type,
            args.max_risk_per_trade,
            args.max_total_risk,
            args.allowed_symbols,
            args.json
        )
    elif args.command == "update-config":
        update_risk_config(
            risk_client,
            args.account_equity,
            args.max_portfolio_risk,
            args.max_asset_risk,
            args.max_leverage,
            args.json
        )
    elif args.command == "simulate-trade":
        simulate_trade_approval(
            risk_client,
            args.symbol,
            args.entry_price,
            args.direction == "long",
            args.stop_loss,
            args.take_profit,
            args.sizer_type,
            args.risk_percent,
            args.json
        )
    else:
        # If no command is provided, show help
        parser.print_help()


if __name__ == "__main__":
    main() 