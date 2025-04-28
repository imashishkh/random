"""
Risk Manager CLI

This module provides a command-line interface for the Global Risk Manager,
allowing administrators to monitor positions, check risk limits, control
circuit breakers, and trigger emergency actions.
"""

import click
import logging
import json
import sys
import time
from pprint import pprint
from typing import Dict, Any

from ..risk import GlobalRiskManager
from ..risk.circuit_breakers import (
    CircuitBreakerTrigger,
    CircuitBreakerScope,
    CircuitBreakerSeverity
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global risk manager instance
risk_manager = None


def get_risk_manager() -> GlobalRiskManager:
    """
    Get or create the risk manager instance.
    
    Returns:
        GlobalRiskManager instance
    """
    global risk_manager
    
    if risk_manager is None:
        # Create a new risk manager (would normally load config from file)
        risk_manager = GlobalRiskManager()
        logger.info("Initialized Risk Manager")
    
    return risk_manager


def format_json(data: Dict[str, Any]) -> str:
    """
    Format data as colored JSON.
    
    Args:
        data: Data to format
        
    Returns:
        Formatted JSON string
    """
    return json.dumps(data, indent=2)


@click.group()
def cli():
    """Risk Manager CLI for monitoring and controlling trading risk."""
    pass


@cli.command()
@click.option('--detailed', '-d', is_flag=True, help='Show detailed position information')
def positions(detailed):
    """Fetch and display current positions."""
    try:
        manager = get_risk_manager()
        
        if detailed:
            # Fetch full position details from exchange
            positions = manager.fetch_binance_position_risk()
            click.echo(f"Current positions ({len(positions)}):")
            click.echo(format_json(positions))
        else:
            # Show summary only
            exposure = manager.get_exposure_summary()
            click.echo(f"Exposure summary:")
            click.echo(format_json(exposure))
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.option('--violations-only', '-v', is_flag=True, help='Show only violations, not full status')
def check_limits(violations_only):
    """Check current positions against risk limits."""
    try:
        manager = get_risk_manager()
        risk_status = manager.check_risk_limits()
        
        if violations_only:
            violations = risk_status.get('violations', [])
            if violations:
                click.echo(f"Risk violations detected ({len(violations)}):")
                click.echo(format_json(violations))
            else:
                click.echo("No risk violations detected.")
        else:
            click.echo("Risk status:")
            click.echo(format_json(risk_status))
    except Exception as e:
        logger.error(f"Error checking risk limits: {e}")
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.option('--reason', '-r', required=True, help='Reason for circuit breaker activation')
@click.option('--duration', '-d', type=int, default=300, help='Duration in seconds (default: 300)')
@click.option('--severity', '-s', type=click.Choice(['warning', 'soft', 'hard', 'emergency']), 
              default='hard', help='Severity level (default: hard)')
@click.option('--symbol', help='Symbol to apply circuit breaker to (optional)')
@click.option('--strategy', help='Strategy to apply circuit breaker to (optional)')
@click.option('--agent', help='Agent to apply circuit breaker to (optional)')
def activate_circuit_breaker(reason, duration, severity, symbol, strategy, agent):
    """Manually activate a circuit breaker."""
    try:
        manager = get_risk_manager()
        
        # Determine scope and identifier
        scope = CircuitBreakerScope.GLOBAL
        identifier = None
        
        if symbol:
            scope = CircuitBreakerScope.SYMBOL
            identifier = symbol
        elif strategy:
            scope = CircuitBreakerScope.STRATEGY
            identifier = strategy
        elif agent:
            scope = CircuitBreakerScope.AGENT
            identifier = agent
        
        # Convert severity string to enum
        severity_enum = CircuitBreakerSeverity(severity)
        
        # Activate
        if hasattr(manager, 'circuit_breaker'):
            # If using separate CircuitBreaker instance
            manager.circuit_breaker.activate(
                trigger=CircuitBreakerTrigger.MANUAL,
                scope=scope,
                identifier=identifier,
                severity=severity_enum,
                duration=duration,
                threshold_value=0,
                current_value=0,
                metadata={"reason": reason}
            )
            
            # If scope is GLOBAL, also activate the built-in manager circuit breaker
            if scope == CircuitBreakerScope.GLOBAL:
                manager.activate_circuit_breaker(reason=reason, duration=duration)
        else:
            # Using built-in circuit breaker (only supports global)
            manager.activate_circuit_breaker(reason=reason, duration=duration)
        
        click.echo(f"Circuit breaker activated: {scope.value}" + 
                  (f" ({identifier})" if identifier else ""))
        click.echo(f"Severity: {severity}, Duration: {duration}s, Reason: {reason}")
    except Exception as e:
        logger.error(f"Error activating circuit breaker: {e}")
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.option('--symbol', help='Symbol to deactivate circuit breaker for (optional)')
@click.option('--strategy', help='Strategy to deactivate circuit breaker for (optional)')
@click.option('--agent', help='Agent to deactivate circuit breaker for (optional)')
@click.option('--all', '-a', 'deactivate_all', is_flag=True, help='Deactivate all circuit breakers')
def deactivate_circuit_breaker(symbol, strategy, agent, deactivate_all):
    """Manually deactivate a circuit breaker."""
    try:
        manager = get_risk_manager()
        
        if deactivate_all:
            # Deactivate all circuit breakers
            if hasattr(manager, 'circuit_breaker'):
                count = manager.circuit_breaker.deactivate_all()
                manager.deactivate_circuit_breaker()  # Also deactivate built-in
                click.echo(f"Deactivated {count + 1} circuit breakers")
            else:
                manager.deactivate_circuit_breaker()
                click.echo("Deactivated global circuit breaker")
        else:
            # Determine scope and identifier
            scope = CircuitBreakerScope.GLOBAL
            identifier = None
            
            if symbol:
                scope = CircuitBreakerScope.SYMBOL
                identifier = symbol
            elif strategy:
                scope = CircuitBreakerScope.STRATEGY
                identifier = strategy
            elif agent:
                scope = CircuitBreakerScope.AGENT
                identifier = agent
            
            # Deactivate
            if hasattr(manager, 'circuit_breaker') and scope != CircuitBreakerScope.GLOBAL:
                # If using separate CircuitBreaker instance
                deactivated = manager.circuit_breaker.deactivate(
                    scope=scope,
                    identifier=identifier
                )
                
                if deactivated:
                    click.echo(f"Deactivated circuit breaker: {scope.value}" + 
                              (f" ({identifier})" if identifier else ""))
                else:
                    click.echo(f"No active circuit breaker found for {scope.value}" + 
                              (f" ({identifier})" if identifier else ""))
            else:
                # Using built-in circuit breaker (only supports global)
                manager.deactivate_circuit_breaker()
                click.echo("Deactivated global circuit breaker")
    except Exception as e:
        logger.error(f"Error deactivating circuit breaker: {e}")
        click.echo(f"Error: {e}", err=True)


@cli.command()
def circuit_breaker_status():
    """Get the status of all circuit breakers."""
    try:
        manager = get_risk_manager()
        
        if hasattr(manager, 'circuit_breaker'):
            # If using separate CircuitBreaker instance
            statuses = manager.circuit_breaker.get_all_statuses()
            click.echo("Circuit breaker status:")
            click.echo(format_json(statuses))
            
            # Also check built-in circuit breaker
            is_active = manager.is_circuit_breaker_active()
            click.echo(f"\nBuilt-in global circuit breaker active: {is_active}")
        else:
            # Using built-in circuit breaker
            is_active = manager.is_circuit_breaker_active()
            click.echo(f"Global circuit breaker active: {is_active}")
    except Exception as e:
        logger.error(f"Error getting circuit breaker status: {e}")
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.option('--reason', '-r', required=True, help='Reason for emergency shutdown')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation')
@click.option('--simulate', '-s', is_flag=True, help='Simulation mode (no real orders)')
def emergency_shutdown(reason, force, simulate):
    """Execute emergency shutdown to close all positions."""
    try:
        if not force:
            click.confirm('This will close ALL positions. Are you sure?', abort=True)
        
        manager = get_risk_manager()
        
        if simulate:
            click.echo("SIMULATION MODE: No real orders will be placed")
            
            # Mock fetch positions
            positions = [
                {"symbol": "BTCUSDT", "position_amount": 1.0, "mark_price": 50000},
                {"symbol": "ETHUSDT", "position_amount": 10.0, "mark_price": 2000}
            ]
            
            click.echo(f"Would close {len(positions)} positions:")
            for pos in positions:
                value = float(pos["position_amount"]) * float(pos["mark_price"])
                click.echo(f"  {pos['symbol']}: {pos['position_amount']} (${value:.2f})")
        else:
            # Execute real emergency shutdown
            click.echo(f"Executing emergency shutdown: {reason}")
            result = manager.emergency_shutdown(reason=reason)
            
            if result['success']:
                click.echo("Emergency shutdown successful")
                click.echo(f"Closed {len(result['closed_positions'])} positions:")
                
                for pos in result['closed_positions']:
                    click.echo(f"  {pos['symbol']}: {pos['amount']} ({'success' if pos['success'] else 'FAILED'})")
            else:
                click.echo(f"Emergency shutdown failed: {result.get('error', 'Unknown error')}", err=True)
    except Exception as e:
        logger.error(f"Error executing emergency shutdown: {e}")
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.option('--max-global', type=float, help='Maximum global exposure (0.0-1.0)')
@click.option('--agent-limits', type=str, help='Agent exposure limits as JSON string')
@click.option('--symbol-limits', type=str, help='Symbol exposure limits as JSON string')
def set_limits(max_global, agent_limits, symbol_limits):
    """Set risk limits for the system."""
    try:
        manager = get_risk_manager()
        
        # Parse JSON strings if provided
        agent_limits_dict = json.loads(agent_limits) if agent_limits else None
        symbol_limits_dict = json.loads(symbol_limits) if symbol_limits else None
        
        # Set limits
        manager.set_global_limits(
            max_global_exposure=max_global,
            max_agent_exposure=agent_limits_dict,
            max_symbol_exposure=symbol_limits_dict
        )
        
        click.echo("Risk limits updated:")
        if max_global is not None:
            click.echo(f"  Max global exposure: {max_global:.2%}")
        if agent_limits_dict:
            click.echo("  Agent limits:")
            for agent, limit in agent_limits_dict.items():
                click.echo(f"    {agent}: {limit:.2%}")
        if symbol_limits_dict:
            click.echo("  Symbol limits:")
            for symbol, limit in symbol_limits_dict.items():
                click.echo(f"    {symbol}: {limit:.2%}")
    except Exception as e:
        logger.error(f"Error setting risk limits: {e}")
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.option('--enable/--disable', default=True, help='Enable or disable circuit breakers')
@click.option('--volatility', type=float, help='Volatility threshold multiplier')
@click.option('--price-change', type=float, help='Price change threshold (decimal)')
@click.option('--timeout', type=int, help='Circuit breaker timeout in seconds')
def configure_circuit_breakers(enable, volatility, price_change, timeout):
    """Configure circuit breaker parameters."""
    try:
        manager = get_risk_manager()
        
        # Configure circuit breakers
        manager.configure_circuit_breakers(
            enabled=enable,
            volatility_threshold=volatility,
            price_change_threshold=price_change,
            timeout=timeout
        )
        
        click.echo("Circuit breaker configuration updated:")
        click.echo(f"  Enabled: {enable}")
        
        if volatility is not None:
            click.echo(f"  Volatility threshold: {volatility}x")
        if price_change is not None:
            click.echo(f"  Price change threshold: {price_change:.2%}")
        if timeout is not None:
            click.echo(f"  Timeout: {timeout}s")
    except Exception as e:
        logger.error(f"Error configuring circuit breakers: {e}")
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.option('--webhook-url', required=True, help='Slack webhook URL')
def setup_slack(webhook_url):
    """Configure Slack alerts."""
    try:
        manager = get_risk_manager()
        manager.configure_slack_alerts(webhook_url)
        click.echo("Slack alerts configured successfully")
    except Exception as e:
        logger.error(f"Error configuring Slack alerts: {e}")
        click.echo(f"Error: {e}", err=True)


if __name__ == '__main__':
    cli() 