"""
Risk Manager API Module

This module provides API endpoints for trading agents to interact with the Risk Manager,
including querying risk status, requesting trade approvals, and registering agents.
"""

import logging
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from typing import Dict, Any, List, Optional

from ..risk.manager import RiskManager
from ..risk.risk_manager import RiskManager as LegacyRiskManager
from .auth import authenticate, admin_required
from .utils import validate_input, ApiError
from ..agents.base_agent import BaseAgent
from ..db import get_db_connection

# Setup logger
logger = logging.getLogger(__name__)

# Blueprint for Risk Manager endpoints
risk_bp = Blueprint('risk', __name__, url_prefix='/api/risk')

# Global risk manager instance (will be initialized in init_app)
_risk_manager = None

# Registry of trading agents
_registered_agents: Dict[str, Dict[str, Any]] = {}


def get_risk_manager() -> LegacyRiskManager:
    """Get the global risk manager instance."""
    global _risk_manager
    if _risk_manager is None:
        # Initialize with default settings - would typically load from config
        _risk_manager = LegacyRiskManager(
            account_equity=100000.0,  # Default starting equity
            default_sizer="fixed_percent",
            default_sizer_params={"risk_percent": 1.0},
            max_portfolio_risk_percent=5.0,
            max_asset_risk_percent=2.0,
            max_correlated_risk_percent=4.0,
            max_leverage=10.0
        )
    return _risk_manager


@risk_bp.route('/status', methods=['GET'])
@authenticate
def get_risk_status():
    """
    Get current risk status including portfolio risk, positions, and limits.
    
    Query parameters:
    - agent_id: Optional agent ID to filter results for a specific agent
    """
    try:
        agent_id = request.args.get('agent_id')
        
        # Get the risk manager
        risk_manager = get_risk_manager()
        
        # Get risk metrics from the risk manager
        risk_metrics = risk_manager.get_risk_metrics()
        
        # If agent_id is provided, filter positions for that agent
        if agent_id and agent_id in _registered_agents:
            # Filter positions (will be implemented in actual integration)
            # For now, we'll just return all positions
            pass
            
        return jsonify({
            'success': True,
            'data': {
                'account_equity': risk_manager.account_equity,
                'current_portfolio_risk_percent': risk_manager.current_portfolio_risk_percent,
                'max_portfolio_risk_percent': risk_manager.max_portfolio_risk_percent,
                'max_asset_risk_percent': risk_manager.max_asset_risk_percent,
                'max_leverage': risk_manager.max_leverage,
                'current_positions': {
                    symbol: {
                        'size': pos['size'],
                        'value': pos['value'],
                        'risk_amount': pos['risk_amount'],
                        'risk_percent': pos['risk_percent'],
                        'metadata': pos['metadata']
                    } for symbol, pos in risk_manager.current_positions.items()
                },
                'agent_specific': agent_id is not None,
                'agent_id': agent_id
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting risk status: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@risk_bp.route('/approval', methods=['POST'])
@authenticate
def request_trade_approval():
    """
    Request approval for a trade from the risk manager.
    
    Request body:
    {
        "agent_id": "agent123",
        "symbol": "EURUSD",
        "entry_price": 1.1050,
        "stop_loss": 1.1000,
        "take_profit": 1.1150,
        "is_long": true,
        "account_balance": 10000.0,  # Optional, uses system value if not provided
        "sizer_type": "fixed_percent",  # Optional
        "sizer_params": {"risk_percent": 1.0}  # Optional
    }
    """
    try:
        data = request.get_json()
        
        # Validate input
        validate_input(data, {
            'agent_id': {'type': 'string', 'required': True},
            'symbol': {'type': 'string', 'required': True},
            'entry_price': {'type': 'number', 'required': True},
            'stop_loss': {'type': 'number', 'required': False},
            'take_profit': {'type': 'number', 'required': False},
            'is_long': {'type': 'boolean', 'required': True},
            'account_balance': {'type': 'number', 'required': False},
            'sizer_type': {'type': 'string', 'required': False},
            'sizer_params': {'type': 'dict', 'required': False}
        })
        
        # Check if agent is registered
        agent_id = data['agent_id']
        if agent_id not in _registered_agents:
            return jsonify({
                'success': False,
                'error': f'Agent with ID {agent_id} is not registered'
            }), 400
        
        # Get the risk manager
        risk_manager = get_risk_manager()
        
        # Update account equity if provided
        if 'account_balance' in data:
            risk_manager.update_account_equity(data['account_balance'])
        
        # Calculate position size
        position_result = risk_manager.calculate_position_size(
            symbol=data['symbol'],
            entry_price=data['entry_price'],
            stop_loss=data.get('stop_loss'),
            take_profit=data.get('take_profit'),
            is_long=data['is_long'],
            sizer_type=data.get('sizer_type'),
            sizer_params=data.get('sizer_params')
        )
        
        # Generate approval ID
        approval_id = str(uuid.uuid4())
        
        # Store approval details (would typically save to database)
        # For this example, we'll just create an in-memory record
        approval_record = {
            'id': approval_id,
            'agent_id': agent_id,
            'symbol': data['symbol'],
            'position_result': position_result,
            'timestamp': datetime.now().isoformat(),
            'expires_at': None  # Could add expiration logic
        }
        
        # Determine approval status
        approved = position_result['size'] > 0
        
        response_data = {
            'success': True,
            'data': {
                'approved': approved,
                'approval_id': approval_id,
                'position_size': position_result['size'],
                'position_value': position_result['value'],
                'risk_amount': position_result['risk_amount'],
                'risk_percent': position_result['risk_percent'],
                'metadata': position_result['metadata']
            }
        }
        
        # If not approved, include reason
        if not approved and 'adjustment_reason' in position_result['metadata']:
            response_data['data']['rejection_reason'] = position_result['metadata']['adjustment_reason']
        
        return jsonify(response_data), 200
        
    except ValueError as e:
        logger.error(f"Error processing trade approval: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Unexpected error processing trade approval: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@risk_bp.route('/agents', methods=['POST'])
@authenticate
def register_agent():
    """
    Register a trading agent with the risk manager.
    
    Request body:
    {
        "agent_id": "agent123",
        "agent_name": "MACD Trend Follower",
        "agent_type": "technical",
        "max_risk_per_trade": 1.0,
        "max_total_risk": 5.0,
        "allowed_symbols": ["EURUSD", "GBPUSD", "USDJPY"]
    }
    """
    try:
        data = request.get_json()
        
        # Validate input
        validate_input(data, {
            'agent_id': {'type': 'string', 'required': True},
            'agent_name': {'type': 'string', 'required': True},
            'agent_type': {'type': 'string', 'required': True},
            'max_risk_per_trade': {'type': 'number', 'required': False},
            'max_total_risk': {'type': 'number', 'required': False},
            'allowed_symbols': {'type': 'list', 'required': False}
        })
        
        agent_id = data['agent_id']
        
        # Check if agent is already registered
        if agent_id in _registered_agents:
            return jsonify({
                'success': False,
                'error': f'Agent with ID {agent_id} is already registered'
            }), 400
        
        # Register the agent
        _registered_agents[agent_id] = {
            'id': agent_id,
            'name': data['agent_name'],
            'type': data['agent_type'],
            'max_risk_per_trade': data.get('max_risk_per_trade', 1.0),
            'max_total_risk': data.get('max_total_risk', 5.0),
            'allowed_symbols': data.get('allowed_symbols', []),
            'registered_at': datetime.now().isoformat(),
            'last_active': datetime.now().isoformat(),
            'active': True
        }
        
        return jsonify({
            'success': True,
            'data': {
                'agent_id': agent_id,
                'registered_at': _registered_agents[agent_id]['registered_at']
            },
            'message': f'Agent {agent_id} registered successfully'
        }), 201
        
    except ValueError as e:
        logger.error(f"Error registering agent: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Unexpected error registering agent: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@risk_bp.route('/agents/<agent_id>', methods=['GET'])
@authenticate
def get_agent(agent_id):
    """Get information about a registered agent."""
    try:
        if agent_id not in _registered_agents:
            return jsonify({
                'success': False,
                'error': f'Agent with ID {agent_id} is not registered'
            }), 404
        
        return jsonify({
            'success': True,
            'data': _registered_agents[agent_id]
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting agent info: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@risk_bp.route('/agents', methods=['GET'])
@authenticate
@admin_required
def list_agents():
    """List all registered agents (admin only)."""
    try:
        return jsonify({
            'success': True,
            'data': list(_registered_agents.values())
        }), 200
        
    except Exception as e:
        logger.error(f"Error listing agents: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@risk_bp.route('/config', methods=['GET'])
@authenticate
@admin_required
def get_risk_config():
    """Get risk manager configuration (admin only)."""
    try:
        risk_manager = get_risk_manager()
        
        return jsonify({
            'success': True,
            'data': {
                'account_equity': risk_manager.account_equity,
                'default_sizer': risk_manager.default_sizer_type,
                'default_sizer_params': risk_manager.default_sizer_params,
                'max_portfolio_risk_percent': risk_manager.max_portfolio_risk_percent,
                'max_asset_risk_percent': risk_manager.max_asset_risk_percent,
                'max_correlated_risk_percent': risk_manager.max_correlated_risk_percent,
                'max_leverage': risk_manager.max_leverage
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting risk configuration: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@risk_bp.route('/config', methods=['PUT'])
@authenticate
@admin_required
def update_risk_config():
    """
    Update risk manager configuration (admin only).
    
    Request body:
    {
        "account_equity": 120000.0,
        "default_sizer": "fixed_percent",
        "default_sizer_params": {"risk_percent": 1.0},
        "max_portfolio_risk_percent": 5.0,
        "max_asset_risk_percent": 2.0,
        "max_correlated_risk_percent": 4.0,
        "max_leverage": 10.0
    }
    """
    try:
        data = request.get_json()
        
        # Validate input (all fields optional since this is a partial update)
        validate_input(data, {
            'account_equity': {'type': 'number', 'required': False},
            'default_sizer': {'type': 'string', 'required': False},
            'default_sizer_params': {'type': 'dict', 'required': False},
            'max_portfolio_risk_percent': {'type': 'number', 'required': False},
            'max_asset_risk_percent': {'type': 'number', 'required': False},
            'max_correlated_risk_percent': {'type': 'number', 'required': False},
            'max_leverage': {'type': 'number', 'required': False}
        })
        
        risk_manager = get_risk_manager()
        
        # Update account equity if provided
        if 'account_equity' in data:
            risk_manager.update_account_equity(data['account_equity'])
        
        # Update default sizer if provided
        if 'default_sizer' in data and 'default_sizer_params' in data:
            risk_manager.set_default_sizer(
                data['default_sizer'],
                data['default_sizer_params']
            )
        elif 'default_sizer' in data:
            risk_manager.set_default_sizer(data['default_sizer'])
        
        # Update risk limits if provided
        risk_limits = {}
        if 'max_portfolio_risk_percent' in data:
            risk_limits['max_portfolio_risk_percent'] = data['max_portfolio_risk_percent']
        if 'max_asset_risk_percent' in data:
            risk_limits['max_asset_risk_percent'] = data['max_asset_risk_percent']
        if 'max_correlated_risk_percent' in data:
            risk_limits['max_correlated_risk_percent'] = data['max_correlated_risk_percent']
        if 'max_leverage' in data:
            risk_limits['max_leverage'] = data['max_leverage']
            
        if risk_limits:
            risk_manager.set_risk_limits(**risk_limits)
        
        return jsonify({
            'success': True,
            'message': 'Risk configuration updated successfully'
        }), 200
        
    except ValueError as e:
        logger.error(f"Error updating risk configuration: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Unexpected error updating risk configuration: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


def init_app(app):
    """Register the blueprint with the Flask app."""
    app.register_blueprint(risk_bp)
    
    # Initialize the global risk manager (will be lazily initialized when needed)
    logger.info("Risk Manager API initialized") 