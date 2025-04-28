import logging
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from ..dashboard.wallet_dashboard import WalletDashboard
from ..services.auth import require_login

# Create a blueprint for wallet routes
wallet_bp = Blueprint('wallet', __name__, url_prefix='/wallet')
logger = logging.getLogger(__name__)

# Create a wallet dashboard instance
dashboard = WalletDashboard()

@wallet_bp.route('/')
@require_login
def wallet_dashboard():
    """Render the wallet dashboard page."""
    return render_template('wallet/dashboard.html')

@wallet_bp.route('/data')
@require_login
def get_dashboard_data():
    """Get the rendered wallet dashboard HTML."""
    return jsonify({
        'html': dashboard.render()
    })

@wallet_bp.route('/switch/<wallet_id>')
@require_login
def switch_wallet(wallet_id):
    """Switch to a different wallet."""
    success = dashboard.switch_wallet(wallet_id)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({
            'success': False, 
            'error': 'Failed to switch wallet'
        }), 400

@wallet_bp.route('/action', methods=['POST'])
@require_login
def process_action():
    """Process a wallet action."""
    data = request.json
    action = data.get('action')
    params = data.get('params', {})
    
    if not action:
        return jsonify({
            'success': False,
            'error': 'No action specified'
        }), 400
    
    success = dashboard.process_action(action, params)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({
            'success': False,
            'error': f'Failed to process {action} action'
        }), 400 