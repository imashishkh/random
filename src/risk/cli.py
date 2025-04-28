#!/usr/bin/env python3
"""
Risk Manager CLI

Command-line interface for interacting with the Risk Manager API.
This allows for managing risk settings, agents, positions, and monitoring risk status
from the command line.
"""

import argparse
import json
import os
import sys
from typing import Dict, Any, List, Optional

from .client import RiskManagerClient

def format_json(data: Dict[str, Any], pretty: bool = True) -> str:
    """
    Format JSON data for display.
    
    Args:
        data: The data to format
        pretty: Whether to pretty-print the JSON
        
    Returns:
        Formatted JSON string
    """
    if pretty:
        return json.dumps(data, indent=2)
    return json.dumps(data)

def print_response(response: Dict[str, Any], pretty: bool = True) -> None:
    """
    Print an API response with proper formatting.
    
    Args:
        response: The API response to print
        pretty: Whether to pretty-print the JSON
    """
    print(format_json(response, pretty))

def get_client(args: argparse.Namespace) -> RiskManagerClient:
    """
    Create a Risk Manager client from command-line arguments.
    
    Args:
        args: Command-line arguments
        
    Returns:
        Configured Risk Manager client
    """
    # Get API key from args, env var, or default
    api_key = args.api_key
    if not api_key:
        api_key = os.environ.get('RISK_MANAGER_API_KEY', 'risk_manager_default_key')
    
    # Get API URL from args, env var, or default
    api_url = args.api_url
    if not api_url:
        api_url = os.environ.get('RISK_MANAGER_API_URL', 'http://localhost:5000/api/risk')
    
    return RiskManagerClient(api_url=api_url, api_key=api_key)

def handle_status(args: argparse.Namespace) -> None:
    """
    Handle the 'status' command.
    
    Args:
        args: Command-line arguments
    """
    client = get_client(args)
    response = client.get_risk_status()
    print_response(response, not args.compact)

def handle_config_get(args: argparse.Namespace) -> None:
    """
    Handle the 'config get' command.
    
    Args:
        args: Command-line arguments
    """
    client = get_client(args)
    response = client.get_config()
    print_response(response, not args.compact)

def handle_config_update(args: argparse.Namespace) -> None:
    """
    Handle the 'config update' command.
    
    Args:
        args: Command-line arguments
    """
    client = get_client(args)
    
    # Build config updates
    updates = {}
    
    if args.account_balance is not None:
        updates['account_balance'] = args.account_balance
    
    if args.params:
        # Parse params from key=value strings
        params = {}
        for param in args.params:
            try:
                key, value = param.split('=', 1)
                # Try to convert to number if possible
                try:
                    value = float(value)
                    # Convert to int if it's a whole number
                    if value.is_integer():
                        value = int(value)
                except ValueError:
                    # If not a number, treat as string or JSON
                    if value.lower() in ('true', 'false'):
                        value = value.lower() == 'true'
                    elif value.startswith('{') or value.startswith('['):
                        try:
                            value = json.loads(value)
                        except json.JSONDecodeError:
                            pass
                params[key] = value
            except ValueError:
                print(f"Error: Invalid parameter format: {param}. Use key=value format.")
                sys.exit(1)
        
        if params:
            updates['params'] = params
    
    if not updates:
        print("Error: No updates specified.")
        sys.exit(1)
    
    response = client.update_config(**updates)
    print_response(response, not args.compact)

def handle_agents_list(args: argparse.Namespace) -> None:
    """
    Handle the 'agents list' command.
    
    Args:
        args: Command-line arguments
    """
    client = get_client(args)
    response = client.get_agents()
    print_response(response, not args.compact)

def handle_agents_get(args: argparse.Namespace) -> None:
    """
    Handle the 'agents get' command.
    
    Args:
        args: Command-line arguments
    """
    client = get_client(args)
    
    try:
        response = client.get_agent(args.agent_id)
        print_response(response, not args.compact)
    except ValueError as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

def handle_agents_register(args: argparse.Namespace) -> None:
    """
    Handle the 'agents register' command.
    
    Args:
        args: Command-line arguments
    """
    client = get_client(args)
    
    # Parse risk limits
    risk_limits = {}
    if args.risk_limits:
        for limit in args.risk_limits:
            try:
                key, value = limit.split('=', 1)
                try:
                    value = float(value)
                except ValueError:
                    if value.lower() in ('true', 'false'):
                        value = value.lower() == 'true'
                risk_limits[key] = value
            except ValueError:
                print(f"Error: Invalid risk limit format: {limit}. Use key=value format.")
                sys.exit(1)
    
    # Parse metadata
    metadata = {}
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print(f"Error: Invalid metadata JSON: {args.metadata}")
            sys.exit(1)
    
    try:
        response = client.register_agent(
            name=args.name,
            agent_type=args.type,
            description=args.description,
            risk_limits=risk_limits,
            metadata=metadata
        )
        print_response(response, not args.compact)
    except ValueError as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

def handle_agents_update(args: argparse.Namespace) -> None:
    """
    Handle the 'agents update' command.
    
    Args:
        args: Command-line arguments
    """
    client = get_client(args)
    
    # Parse risk limits
    risk_limits = None
    if args.risk_limits:
        risk_limits = {}
        for limit in args.risk_limits:
            try:
                key, value = limit.split('=', 1)
                try:
                    value = float(value)
                except ValueError:
                    if value.lower() in ('true', 'false'):
                        value = value.lower() == 'true'
                risk_limits[key] = value
            except ValueError:
                print(f"Error: Invalid risk limit format: {limit}. Use key=value format.")
                sys.exit(1)
    
    # Parse metadata
    metadata = None
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print(f"Error: Invalid metadata JSON: {args.metadata}")
            sys.exit(1)
    
    updates = {
        'agent_id': args.agent_id
    }
    
    if args.name is not None:
        updates['name'] = args.name
    
    if args.type is not None:
        updates['agent_type'] = args.type
    
    if args.description is not None:
        updates['description'] = args.description
    
    if risk_limits is not None:
        updates['risk_limits'] = risk_limits
    
    if metadata is not None:
        updates['metadata'] = metadata
    
    try:
        response = client.update_agent(**updates)
        print_response(response, not args.compact)
    except ValueError as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

def handle_positions_list(args: argparse.Namespace) -> None:
    """
    Handle the 'positions list' command.
    
    Args:
        args: Command-line arguments
    """
    client = get_client(args)
    response = client.get_positions()
    print_response(response, not args.compact)

def handle_positions_get(args: argparse.Namespace) -> None:
    """
    Handle the 'positions get' command.
    
    Args:
        args: Command-line arguments
    """
    client = get_client(args)
    response = client.get_position(args.position_id)
    print_response(response, not args.compact)

def handle_positions_add(args: argparse.Namespace) -> None:
    """
    Handle the 'positions add' command.
    
    Args:
        args: Command-line arguments
    """
    client = get_client(args)
    
    # Parse metadata
    metadata = {}
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print(f"Error: Invalid metadata JSON: {args.metadata}")
            sys.exit(1)
    
    try:
        response = client.add_position(
            symbol=args.symbol,
            direction=args.direction,
            entry_price=args.entry_price,
            stop_loss=args.stop_loss,
            units=args.units,
            risk_percent=args.risk_percent,
            position_value=args.position_value,
            risk_amount=args.risk_amount,
            metadata=metadata
        )
        print_response(response, not args.compact)
    except ValueError as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

def handle_positions_remove(args: argparse.Namespace) -> None:
    """
    Handle the 'positions remove' command.
    
    Args:
        args: Command-line arguments
    """
    client = get_client(args)
    
    try:
        response = client.remove_position(args.position_id)
        print_response(response, not args.compact)
    except ValueError as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

def handle_approve_trade(args: argparse.Namespace) -> None:
    """
    Handle the 'approve-trade' command.
    
    Args:
        args: Command-line arguments
    """
    client = get_client(args)
    
    # Parse metadata
    metadata = {}
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print(f"Error: Invalid metadata JSON: {args.metadata}")
            sys.exit(1)
    
    try:
        response = client.request_trade_approval(
            symbol=args.symbol,
            direction=args.direction,
            entry_price=args.entry_price,
            stop_loss=args.stop_loss,
            units=args.units,
            risk_percent=args.risk_percent,
            metadata=metadata
        )
        print_response(response, not args.compact)
    except ValueError as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

def main():
    """
    Main entry point for the Risk Manager CLI.
    """
    parser = argparse.ArgumentParser(description='Risk Manager CLI')
    
    # Global options
    parser.add_argument('--api-url', help='Risk Manager API URL')
    parser.add_argument('--api-key', help='Risk Manager API key')
    parser.add_argument('--compact', action='store_true', help='Output compact JSON')
    
    # Create subparsers for commands
    subparsers = parser.add_subparsers(dest='command', help='Command')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Get risk status')
    status_parser.set_defaults(func=handle_status)
    
    # Config commands
    config_parser = subparsers.add_parser('config', help='Risk Manager configuration')
    config_subparsers = config_parser.add_subparsers(dest='config_command', help='Config command')
    
    # Config get command
    config_get_parser = config_subparsers.add_parser('get', help='Get risk configuration')
    config_get_parser.set_defaults(func=handle_config_get)
    
    # Config update command
    config_update_parser = config_subparsers.add_parser('update', help='Update risk configuration')
    config_update_parser.add_argument('--account-balance', type=float, help='Account balance')
    config_update_parser.add_argument('--params', nargs='+', help='Risk parameters (key=value)')
    config_update_parser.set_defaults(func=handle_config_update)
    
    # Agent commands
    agents_parser = subparsers.add_parser('agents', help='Agent management')
    agents_subparsers = agents_parser.add_subparsers(dest='agents_command', help='Agents command')
    
    # Agents list command
    agents_list_parser = agents_subparsers.add_parser('list', help='List registered agents')
    agents_list_parser.set_defaults(func=handle_agents_list)
    
    # Agents get command
    agents_get_parser = agents_subparsers.add_parser('get', help='Get agent details')
    agents_get_parser.add_argument('agent_id', help='Agent ID')
    agents_get_parser.set_defaults(func=handle_agents_get)
    
    # Agents register command
    agents_register_parser = agents_subparsers.add_parser('register', help='Register a new agent')
    agents_register_parser.add_argument('--name', required=True, help='Agent name')
    agents_register_parser.add_argument('--type', required=True, help='Agent type')
    agents_register_parser.add_argument('--description', help='Agent description')
    agents_register_parser.add_argument('--risk-limits', nargs='+', help='Risk limits (key=value)')
    agents_register_parser.add_argument('--metadata', help='Metadata JSON')
    agents_register_parser.set_defaults(func=handle_agents_register)
    
    # Agents update command
    agents_update_parser = agents_subparsers.add_parser('update', help='Update agent details')
    agents_update_parser.add_argument('agent_id', help='Agent ID')
    agents_update_parser.add_argument('--name', help='Agent name')
    agents_update_parser.add_argument('--type', help='Agent type')
    agents_update_parser.add_argument('--description', help='Agent description')
    agents_update_parser.add_argument('--risk-limits', nargs='+', help='Risk limits (key=value)')
    agents_update_parser.add_argument('--metadata', help='Metadata JSON')
    agents_update_parser.set_defaults(func=handle_agents_update)
    
    # Position commands
    positions_parser = subparsers.add_parser('positions', help='Position management')
    positions_subparsers = positions_parser.add_subparsers(dest='positions_command', help='Positions command')
    
    # Positions list command
    positions_list_parser = positions_subparsers.add_parser('list', help='List positions')
    positions_list_parser.set_defaults(func=handle_positions_list)
    
    # Positions get command
    positions_get_parser = positions_subparsers.add_parser('get', help='Get position details')
    positions_get_parser.add_argument('position_id', help='Position ID')
    positions_get_parser.set_defaults(func=handle_positions_get)
    
    # Positions add command
    positions_add_parser = positions_subparsers.add_parser('add', help='Add a position')
    positions_add_parser.add_argument('--symbol', required=True, help='Trading symbol')
    positions_add_parser.add_argument('--direction', required=True, choices=['long', 'short'], help='Trade direction')
    positions_add_parser.add_argument('--entry-price', required=True, type=float, help='Entry price')
    positions_add_parser.add_argument('--stop-loss', required=True, type=float, help='Stop loss price')
    positions_add_parser.add_argument('--units', type=float, help='Position units')
    positions_add_parser.add_argument('--risk-percent', type=float, help='Risk percentage')
    positions_add_parser.add_argument('--position-value', type=float, help='Position value')
    positions_add_parser.add_argument('--risk-amount', type=float, help='Risk amount')
    positions_add_parser.add_argument('--metadata', help='Metadata JSON')
    positions_add_parser.set_defaults(func=handle_positions_add)
    
    # Positions remove command
    positions_remove_parser = positions_subparsers.add_parser('remove', help='Remove a position')
    positions_remove_parser.add_argument('position_id', help='Position ID')
    positions_remove_parser.set_defaults(func=handle_positions_remove)
    
    # Approve trade command
    approve_trade_parser = subparsers.add_parser('approve-trade', help='Request trade approval')
    approve_trade_parser.add_argument('--symbol', required=True, help='Trading symbol')
    approve_trade_parser.add_argument('--direction', required=True, choices=['long', 'short'], help='Trade direction')
    approve_trade_parser.add_argument('--entry-price', required=True, type=float, help='Entry price')
    approve_trade_parser.add_argument('--stop-loss', required=True, type=float, help='Stop loss price')
    approve_trade_parser.add_argument('--units', type=float, help='Position units')
    approve_trade_parser.add_argument('--risk-percent', type=float, help='Risk percentage')
    approve_trade_parser.add_argument('--metadata', help='Metadata JSON')
    approve_trade_parser.set_defaults(func=handle_approve_trade)
    
    # Parse arguments
    args = parser.parse_args()
    
    # Handle command
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main() 