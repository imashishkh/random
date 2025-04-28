#!/usr/bin/env python3
"""
Risk Manager API

Flask-based REST API for the Risk Manager service, providing endpoints for:
- Risk status and configuration
- Agent registration and management
- Position tracking and management
- Trade approval and risk checking
- Position size calculation

The API requires authentication via API keys for all endpoints.
"""

import os
import json
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union

from flask import Flask, request, jsonify, Response, g
from flask_cors import CORS
from functools import wraps

# Import the Risk Manager and related classes
from .manager import RiskManager, Agent, Position

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Load configuration
app.config.from_mapping(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'dev_key_change_in_production'),
    API_KEYS=os.environ.get('RISK_MANAGER_API_KEYS', 'test_key').split(','),
    DEBUG=os.environ.get('DEBUG', 'False').lower() in ('true', '1', 't'),
)

# Initialize risk manager
risk_manager = RiskManager()

# API key authentication decorator
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({"error": "API key is required"}), 401
            
        if api_key not in app.config['API_KEYS']:
            return jsonify({"error": "Invalid API key"}), 403
            
        return f(*args, **kwargs)
    return decorated_function

# Error handler for JSON parsing
@app.errorhandler(400)
def bad_request(error):
    return jsonify({"error": "Bad request, invalid JSON format"}), 400

# Error handler for API endpoints
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def server_error(error):
    logger.error(f"Server error: {str(error)}")
    return jsonify({"error": "Internal server error"}), 500

# Health check endpoint (no auth required)
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "risk_manager"
    })

# Root endpoint
@app.route('/', methods=['GET'])
def root():
    return jsonify({
        "service": "Risk Manager API",
        "version": "1.0.0",
        "documentation": "/docs"
    })

# API Documentation endpoint (optional, no auth required)
@app.route('/docs', methods=['GET'])
def docs():
    return jsonify({
        "title": "Risk Manager API",
        "version": "1.0.0",
        "description": "API for managing trading risk, positions, and agent interactions",
        "endpoints": [
            {"path": "/risk/status", "methods": ["GET"], "description": "Get current risk status"},
            {"path": "/risk/config", "methods": ["GET", "PUT"], "description": "Get or update risk configuration"},
            {"path": "/risk/agents", "methods": ["GET", "POST"], "description": "Get all agents or register a new agent"},
            {"path": "/risk/agents/<agent_id>", "methods": ["GET", "PUT"], "description": "Get or update a specific agent"},
            {"path": "/risk/positions", "methods": ["GET", "POST"], "description": "Get all positions or add a new position"},
            {"path": "/risk/positions/<position_id>", "methods": ["GET", "DELETE"], "description": "Get or remove a specific position"},
            {"path": "/risk/trades/approve", "methods": ["POST"], "description": "Request approval for a trade"},
            {"path": "/risk/calculate", "methods": ["POST"], "description": "Calculate position size based on risk parameters"}
        ]
    })

# Risk status endpoint
@app.route('/risk/status', methods=['GET'])
@require_api_key
def get_risk_status():
    return jsonify(risk_manager.get_status())

# Risk configuration endpoints
@app.route('/risk/config', methods=['GET'])
@require_api_key
def get_risk_config():
    return jsonify(risk_manager.get_config())

@app.route('/risk/config', methods=['PUT'])
@require_api_key
def update_risk_config():
    try:
        data = request.get_json()
        
        # Update account balance if provided
        if 'account_balance' in data:
            risk_manager.update_account_balance(data['account_balance'])
            
        # Update other configuration parameters
        if 'config' in data:
            risk_manager.update_config(data['config'])
            
        return jsonify({
            "success": True,
            "message": "Risk configuration updated",
            "config": risk_manager.get_config()
        })
    except Exception as e:
        logger.error(f"Error updating config: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Agent management endpoints
@app.route('/risk/agents', methods=['GET'])
@require_api_key
def get_agents():
    try:
        agents = risk_manager.get_agents()
        return jsonify({
            "success": True,
            "agents": agents,
            "count": len(agents)
        })
    except Exception as e:
        logger.error(f"Error getting agents: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/risk/agents/<agent_id>', methods=['GET'])
@require_api_key
def get_agent(agent_id):
    try:
        agent = risk_manager.get_agent(agent_id)
        if not agent:
            return jsonify({"error": f"Agent with ID {agent_id} not found"}), 404
        return jsonify(agent)
    except Exception as e:
        logger.error(f"Error getting agent {agent_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/risk/agents', methods=['POST'])
@require_api_key
def register_agent():
    try:
        data = request.get_json()
        
        # Required fields
        if 'name' not in data:
            return jsonify({"error": "Agent name is required"}), 400
            
        # Create agent ID if not provided
        agent_id = data.get('agent_id', str(uuid.uuid4()))
        
        # Create agent object
        agent = Agent(
            agent_id=agent_id,
            name=data['name'],
            agent_type=data.get('type', 'trading'),
            description=data.get('description', ''),
            risk_limits=data.get('risk_limits', {}),
            metadata=data.get('metadata', {})
        )
        
        # Register agent
        risk_manager.register_agent(agent)
        
        return jsonify({
            "success": True,
            "message": "Agent registered successfully",
            "agent_id": agent_id,
            "agent": agent.to_dict()
        })
    except Exception as e:
        logger.error(f"Error registering agent: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/risk/agents/<agent_id>', methods=['PUT'])
@require_api_key
def update_agent(agent_id):
    try:
        data = request.get_json()
        
        # Get existing agent
        agent = risk_manager.get_agent(agent_id)
        if not agent:
            return jsonify({"error": f"Agent with ID {agent_id} not found"}), 404
            
        # Update fields
        if 'name' in data:
            agent['name'] = data['name']
        
        if 'type' in data:
            agent['agent_type'] = data['type']
            
        if 'description' in data:
            agent['description'] = data['description']
            
        if 'risk_limits' in data:
            agent['risk_limits'] = data['risk_limits']
            
        if 'metadata' in data:
            # Merge metadata
            if isinstance(agent['metadata'], dict) and isinstance(data['metadata'], dict):
                agent['metadata'].update(data['metadata'])
            else:
                agent['metadata'] = data['metadata']
        
        # Convert dict back to Agent
        updated_agent = Agent.from_dict(agent)
        
        # Update in risk manager
        risk_manager.update_agent(updated_agent)
        
        return jsonify({
            "success": True,
            "message": "Agent updated successfully",
            "agent": agent
        })
    except Exception as e:
        logger.error(f"Error updating agent {agent_id}: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Position management endpoints
@app.route('/risk/positions', methods=['GET'])
@require_api_key
def get_positions():
    try:
        agent_id = request.args.get('agent_id')
        symbol = request.args.get('symbol')
        
        positions = risk_manager.get_positions(agent_id=agent_id, symbol=symbol)
        
        return jsonify({
            "success": True,
            "positions": positions,
            "count": len(positions)
        })
    except Exception as e:
        logger.error(f"Error getting positions: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/risk/positions/<position_id>', methods=['GET'])
@require_api_key
def get_position(position_id):
    try:
        position = risk_manager.get_position(position_id)
        if not position:
            return jsonify({"error": f"Position with ID {position_id} not found"}), 404
        return jsonify(position)
    except Exception as e:
        logger.error(f"Error getting position {position_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/risk/positions', methods=['POST'])
@require_api_key
def add_position():
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['symbol', 'direction', 'entry_price', 'stop_loss']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Field '{field}' is required"}), 400
                
        # Create position ID if not provided
        position_id = data.get('position_id', str(uuid.uuid4()))
        
        # Validate direction
        if data['direction'] not in ['long', 'short']:
            return jsonify({"error": "Direction must be 'long' or 'short'"}), 400
            
        # Validate numeric fields
        try:
            entry_price = float(data['entry_price'])
            stop_loss = float(data['stop_loss'])
            
            if 'risk_percent' in data:
                risk_percent = float(data['risk_percent'])
            else:
                risk_percent = None
                
            if 'units' in data:
                units = float(data['units'])
            else:
                units = None
                
        except ValueError:
            return jsonify({"error": "Numeric fields must be valid numbers"}), 400
            
        # Create position object
        position = Position(
            position_id=position_id,
            symbol=data['symbol'],
            direction=data['direction'],
            entry_price=entry_price,
            stop_loss=stop_loss,
            risk_percent=risk_percent,
            units=units,
            agent_id=data.get('agent_id'),
            metadata=data.get('metadata', {})
        )
        
        # Add position
        risk_manager.add_position(position)
        
        return jsonify({
            "success": True,
            "message": "Position added successfully",
            "position_id": position_id,
            "position": position.to_dict()
        })
    except Exception as e:
        logger.error(f"Error adding position: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/risk/positions/<position_id>', methods=['DELETE'])
@require_api_key
def remove_position(position_id):
    try:
        result = risk_manager.remove_position(position_id)
        if not result:
            return jsonify({"error": f"Position with ID {position_id} not found"}), 404
            
        return jsonify({
            "success": True,
            "message": f"Position {position_id} removed successfully"
        })
    except Exception as e:
        logger.error(f"Error removing position {position_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Trade approval endpoint
@app.route('/risk/trades/approve', methods=['POST'])
@require_api_key
def approve_trade():
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['symbol', 'direction', 'entry_price', 'stop_loss']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Field '{field}' is required"}), 400
                
        # Validate direction
        if data['direction'] not in ['long', 'short']:
            return jsonify({"error": "Direction must be 'long' or 'short'"}), 400
            
        # Validate numeric fields
        try:
            entry_price = float(data['entry_price'])
            stop_loss = float(data['stop_loss'])
            
            if 'risk_percent' in data:
                risk_percent = float(data['risk_percent'])
            else:
                risk_percent = None
                
            if 'units' in data:
                units = float(data['units'])
            else:
                units = None
                
        except ValueError:
            return jsonify({"error": "Numeric fields must be valid numbers"}), 400
            
        # Create a temporary position for approval
        position = Position(
            position_id=str(uuid.uuid4()),
            symbol=data['symbol'],
            direction=data['direction'],
            entry_price=entry_price,
            stop_loss=stop_loss,
            risk_percent=risk_percent,
            units=units,
            agent_id=data.get('agent_id'),
            metadata=data.get('metadata', {})
        )
        
        # Check if trade is approved
        approved, analysis = risk_manager.approve_trade(position)
        
        return jsonify({
            "approved": approved,
            "analysis": analysis,
            "position": position.to_dict()
        })
    except Exception as e:
        logger.error(f"Error approving trade: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Position size calculation endpoint
@app.route('/risk/calculate', methods=['POST'])
@require_api_key
def calculate_position_size():
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['symbol', 'entry_price', 'stop_loss']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Field '{field}' is required"}), 400
                
        # Validate numeric fields
        try:
            entry_price = float(data['entry_price'])
            stop_loss = float(data['stop_loss'])
            risk_percent = data.get('risk_percent')
            
            if risk_percent is not None:
                risk_percent = float(risk_percent)
                
        except ValueError:
            return jsonify({"error": "Numeric fields must be valid numbers"}), 400
            
        # Calculate position size
        result = risk_manager.calculate_position_size(
            symbol=data['symbol'],
            entry_price=entry_price,
            stop_loss=stop_loss,
            risk_percent=risk_percent
        )
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error calculating position size: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Start the server if run directly
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=app.config['DEBUG']) 