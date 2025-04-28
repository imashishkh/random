#!/usr/bin/env python3
"""
Risk Manager Dashboard

A simple web dashboard for monitoring and managing the Risk Manager.
The dashboard provides a UI for viewing risk status, managing positions,
configuring risk parameters, and monitoring trading agent activity.
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response

from .client import RiskManagerClient

# Initialize Flask app
app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
            static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.secret_key = os.environ.get('RISK_DASHBOARD_SECRET_KEY', 'risk_dashboard_secret')

# Initialize Risk Manager client
def get_client() -> RiskManagerClient:
    """Get Risk Manager client with configuration from environment variables."""
    api_url = os.environ.get('RISK_MANAGER_API_URL', 'http://localhost:5000/api/risk')
    api_key = os.environ.get('RISK_MANAGER_API_KEY', 'risk_manager_default_key')
    return RiskManagerClient(api_url=api_url, api_key=api_key)

# Dashboard routes
@app.route('/')
def index():
    """Dashboard home page."""
    client = get_client()
    risk_status = client.get_risk_status()
    positions = client.get_positions()
    config = client.get_config()
    agents = client.get_agents()
    
    return render_template('dashboard.html',
                          risk_status=risk_status,
                          positions=positions.get('positions', []),
                          config=config,
                          agents=agents.get('agents', []))

@app.route('/api/risk_status')
def api_risk_status():
    """API endpoint for risk status."""
    client = get_client()
    risk_status = client.get_risk_status()
    return jsonify(risk_status)

@app.route('/api/positions')
def api_positions():
    """API endpoint for positions."""
    client = get_client()
    positions = client.get_positions()
    return jsonify(positions)

@app.route('/api/agents')
def api_agents():
    """API endpoint for agents."""
    client = get_client()
    agents = client.get_agents()
    return jsonify(agents)

@app.route('/api/config')
def api_config():
    """API endpoint for risk configuration."""
    client = get_client()
    config = client.get_config()
    return jsonify(config)

@app.route('/positions')
def positions():
    """View all positions."""
    client = get_client()
    positions = client.get_positions()
    return render_template('positions.html', positions=positions.get('positions', []))

@app.route('/positions/<position_id>')
def position_detail(position_id):
    """View position details."""
    client = get_client()
    position = client.get_position(position_id)
    return render_template('position_detail.html', position=position)

@app.route('/positions/add', methods=['GET', 'POST'])
def add_position():
    """Add a new position."""
    if request.method == 'POST':
        client = get_client()
        
        # Parse form data
        symbol = request.form.get('symbol')
        direction = request.form.get('direction')
        entry_price = float(request.form.get('entry_price', 0))
        stop_loss = float(request.form.get('stop_loss', 0))
        units = float(request.form.get('units', 0))
        risk_percent = float(request.form.get('risk_percent', 0))
        metadata = {}
        
        try:
            response = client.add_position(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                units=units,
                risk_percent=risk_percent,
                metadata=metadata
            )
            
            if response.get('success'):
                flash('Position added successfully', 'success')
                return redirect(url_for('positions'))
            else:
                flash(f"Error adding position: {response.get('message', 'Unknown error')}", 'error')
        except Exception as e:
            flash(f"Error adding position: {str(e)}", 'error')
        
    return render_template('add_position.html')

@app.route('/positions/remove/<position_id>', methods=['POST'])
def remove_position(position_id):
    """Remove a position."""
    client = get_client()
    
    try:
        response = client.remove_position(position_id)
        
        if response.get('success'):
            flash('Position removed successfully', 'success')
        else:
            flash(f"Error removing position: {response.get('message', 'Unknown error')}", 'error')
    except Exception as e:
        flash(f"Error removing position: {str(e)}", 'error')
    
    return redirect(url_for('positions'))

@app.route('/agents')
def agents():
    """View all agents."""
    client = get_client()
    agents = client.get_agents()
    return render_template('agents.html', agents=agents.get('agents', []))

@app.route('/agents/<agent_id>')
def agent_detail(agent_id):
    """View agent details."""
    client = get_client()
    try:
        agent = client.get_agent(agent_id)
        return render_template('agent_detail.html', agent=agent)
    except Exception as e:
        flash(f"Error getting agent: {str(e)}", 'error')
        return redirect(url_for('agents'))

@app.route('/agents/register', methods=['GET', 'POST'])
def register_agent():
    """Register a new agent."""
    if request.method == 'POST':
        client = get_client()
        
        # Parse form data
        name = request.form.get('name')
        agent_type = request.form.get('type')
        description = request.form.get('description', '')
        risk_limits_str = request.form.get('risk_limits', '{}')
        
        try:
            risk_limits = json.loads(risk_limits_str)
            metadata = {}
            
            response = client.register_agent(
                name=name,
                agent_type=agent_type,
                description=description,
                risk_limits=risk_limits,
                metadata=metadata
            )
            
            if response.get('success'):
                flash('Agent registered successfully', 'success')
                return redirect(url_for('agents'))
            else:
                flash(f"Error registering agent: {response.get('message', 'Unknown error')}", 'error')
        except json.JSONDecodeError:
            flash('Invalid JSON for risk limits', 'error')
        except Exception as e:
            flash(f"Error registering agent: {str(e)}", 'error')
        
    return render_template('register_agent.html')

@app.route('/agents/update/<agent_id>', methods=['GET', 'POST'])
def update_agent(agent_id):
    """Update an agent."""
    client = get_client()
    
    if request.method == 'GET':
        try:
            agent = client.get_agent(agent_id)
            return render_template('update_agent.html', agent=agent)
        except Exception as e:
            flash(f"Error getting agent: {str(e)}", 'error')
            return redirect(url_for('agents'))
    
    elif request.method == 'POST':
        # Parse form data
        name = request.form.get('name')
        agent_type = request.form.get('type')
        description = request.form.get('description', '')
        risk_limits_str = request.form.get('risk_limits', '{}')
        
        try:
            risk_limits = json.loads(risk_limits_str)
            metadata = {}
            
            response = client.update_agent(
                agent_id=agent_id,
                name=name,
                agent_type=agent_type,
                description=description,
                risk_limits=risk_limits,
                metadata=metadata
            )
            
            if response.get('success'):
                flash('Agent updated successfully', 'success')
                return redirect(url_for('agent_detail', agent_id=agent_id))
            else:
                flash(f"Error updating agent: {response.get('message', 'Unknown error')}", 'error')
        except json.JSONDecodeError:
            flash('Invalid JSON for risk limits', 'error')
        except Exception as e:
            flash(f"Error updating agent: {str(e)}", 'error')
        
        return redirect(url_for('update_agent', agent_id=agent_id))

@app.route('/config', methods=['GET', 'POST'])
def config():
    """View and update risk configuration."""
    client = get_client()
    
    if request.method == 'POST':
        # Parse form data
        account_balance = float(request.form.get('account_balance', 0))
        params_str = request.form.get('params', '{}')
        
        try:
            params = json.loads(params_str)
            
            response = client.update_config(
                account_balance=account_balance,
                params=params
            )
            
            if response.get('success'):
                flash('Configuration updated successfully', 'success')
            else:
                flash(f"Error updating configuration: {response.get('message', 'Unknown error')}", 'error')
        except json.JSONDecodeError:
            flash('Invalid JSON for parameters', 'error')
        except Exception as e:
            flash(f"Error updating configuration: {str(e)}", 'error')
    
    # Get current configuration
    config = client.get_config()
    return render_template('config.html', config=config)

@app.route('/approve-trade', methods=['GET', 'POST'])
def approve_trade():
    """Request trade approval."""
    if request.method == 'POST':
        client = get_client()
        
        # Parse form data
        symbol = request.form.get('symbol')
        direction = request.form.get('direction')
        entry_price = float(request.form.get('entry_price', 0))
        stop_loss = float(request.form.get('stop_loss', 0))
        units = float(request.form.get('units', 0)) if request.form.get('units') else None
        risk_percent = float(request.form.get('risk_percent', 0)) if request.form.get('risk_percent') else None
        metadata = {}
        
        try:
            response = client.request_trade_approval(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                units=units,
                risk_percent=risk_percent,
                metadata=metadata
            )
            
            return render_template('trade_approval_result.html', response=response)
        except Exception as e:
            flash(f"Error requesting trade approval: {str(e)}", 'error')
        
    return render_template('approve_trade.html')

def main():
    """Start the dashboard application."""
    host = os.environ.get('RISK_DASHBOARD_HOST', '0.0.0.0')
    port = int(os.environ.get('RISK_DASHBOARD_PORT', 8080))
    debug = os.environ.get('RISK_DASHBOARD_DEBUG', 'True').lower() == 'true'
    
    app.run(host=host, port=port, debug=debug)

if __name__ == '__main__':
    main() 