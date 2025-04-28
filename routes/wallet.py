from flask import Blueprint, render_template, request, jsonify, current_app, session, flash, redirect, url_for
import json
from datetime import datetime
from decimal import Decimal

from src.account.manager import WalletManager
from src.account.models import TransactionType

# Define the blueprint
wallet_bp = Blueprint('wallet', __name__, url_prefix='/wallet')

# Helper function to format currency
def format_currency(amount, currency='USD'):
    if currency == 'USD':
        return f"${amount:.2f}"
    elif currency == 'EUR':
        return f"€{amount:.2f}"
    elif currency == 'GBP':
        return f"£{amount:.2f}"
    else:
        return f"{amount:.2f} {currency}"

# Helper function to format datetime
def format_datetime(dt):
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
    return dt.strftime('%Y-%m-%d %H:%M')

# Helper function to get badge class for transaction type
def get_type_class(transaction_type):
    if transaction_type in ['deposit', 'credit']:
        return 'badge-deposit'
    elif transaction_type in ['withdrawal', 'debit']:
        return 'badge-withdrawal'
    elif transaction_type in ['transfer']:
        return 'badge-transfer'
    else:
        return 'badge-secondary'

# Helper function to get badge class for transaction status
def get_status_class(status):
    if status in ['complete', 'completed', 'success']:
        return 'badge-complete'
    elif status in ['pending', 'processing']:
        return 'badge-pending'
    elif status in ['failed', 'rejected', 'error']:
        return 'badge-failed'
    elif status in ['active']:
        return 'badge-active'
    elif status in ['closed', 'inactive']:
        return 'badge-closed'
    else:
        return 'badge-secondary'

# Helper function to get class for amount display
def get_amount_class(amount):
    if amount > 0:
        return 'amount-positive'
    elif amount < 0:
        return 'amount-negative'
    else:
        return ''

# Routes
@wallet_bp.route('/dashboard')
def dashboard():
    """Render the wallet dashboard page"""
    return render_template('wallet/dashboard.html')

@wallet_bp.route('/get_dashboard_data')
def get_dashboard_data():
    """API endpoint to fetch dashboard data"""
    try:
        # Create wallet manager instance
        wallet_manager = WalletManager()
        
        # Get wallet ID from query parameter or session
        wallet_id = request.args.get('wallet_id', type=int)
        if not wallet_id and 'current_wallet_id' in session:
            wallet_id = session['current_wallet_id']
        
        # If no wallet ID specified, use the first wallet or default
        user_id = session.get('user_id', '1')  # Default user ID if not logged in
        wallets = wallet_manager.get_user_wallets(user_id)
        
        if not wallets:
            return jsonify({
                'status': 'error',
                'message': 'No wallets found for this user.'
            }), 404
        
        # If no specific wallet requested, use the first one
        if not wallet_id:
            wallet_data = wallets[0]
            wallet_id = wallet_data.get('id')
            session['current_wallet_id'] = wallet_id
        else:
            # Find the selected wallet
            wallet_data = next((w for w in wallets if w.get('id') == wallet_id), None)
            if not wallet_data:
                wallet_data = wallets[0]
                wallet_id = wallet_data.get('id')
        
        # Prepare wallet data for template
        wallet = {
            'id': wallet_id,
            'name': wallet_data.get('name', 'Wallet'),
            'balance': wallet_data.get('balance', Decimal('0.00')),
            'available': wallet_data.get('available', wallet_data.get('balance', Decimal('0.00'))),
            'reserved': wallet_data.get('reserved', Decimal('0.00')),
            'currency': wallet_data.get('currency', 'USD')
        }
        
        # Get other wallets (for switching)
        other_wallets = [
            {
                'id': w.get('id'),
                'name': w.get('name', 'Wallet'),
                'balance': w.get('balance', Decimal('0.00')),
                'currency': w.get('currency', 'USD')
            }
            for w in wallets if w.get('id') != wallet_id
        ]
        
        # Get transactions for this wallet
        raw_transactions = wallet_manager.get_wallet_transactions(
            wallet_id=wallet_id,
            limit=10  # Show last 10 transactions
        )
        
        # Format transactions for the template
        transactions = []
        for tx in raw_transactions:
            tx_type = tx.get('transaction_type', 'unknown')
            amount = Decimal(tx.get('amount', 0))
            
            transactions.append({
                'id': tx.get('transaction_id', ''),
                'date': tx.get('timestamp', datetime.now()),
                'description': tx.get('description', ''),
                'type': tx_type,
                'type_class': get_type_class(tx_type),
                'amount': amount,
                'amount_class': get_amount_class(amount),
                'status': tx.get('status', 'pending'),
                'status_class': get_status_class(tx.get('status', 'pending'))
            })
        
        # Get active investments (positions) for this wallet
        raw_positions = wallet_manager.get_positions(wallet_id) if hasattr(wallet_manager, 'get_positions') else []
        
        # Format investments for the template
        investments = []
        for pos in raw_positions:
            market = pos.get('symbol', '')
            amount = Decimal(pos.get('size', 0))
            profit = Decimal(pos.get('unrealized_pnl', 0))
            
            investments.append({
                'id': pos.get('position_id', ''),
                'market': market,
                'amount': amount,
                'status': 'active' if pos.get('status') != 'closed' else 'closed',
                'status_class': 'badge-active' if pos.get('status') != 'closed' else 'badge-closed',
                'profit': profit,
                'profit_class': 'amount-positive' if profit >= 0 else 'amount-negative'
            })
        
        # Get payment methods and withdrawal methods
        # In a real app, these would come from a database or service
        payment_methods = [
            {'id': 'bank', 'name': 'Bank Transfer'},
            {'id': 'card', 'name': 'Credit Card'},
            {'id': 'paypal', 'name': 'PayPal'}
        ]
        
        withdrawal_methods = [
            {'id': 'bank', 'name': 'Bank Account'},
            {'id': 'paypal', 'name': 'PayPal'},
            {'id': 'crypto', 'name': 'Crypto Wallet'}
        ]
        
        # Prepare template context
        context = {
            'wallet': wallet,
            'other_wallets': other_wallets,
            'transactions': transactions,
            'investments': investments,
            'payment_methods': payment_methods,
            'withdrawal_methods': withdrawal_methods
        }
        
        # Render the dashboard content template
        html_content = render_template('wallet/dashboard_content.html', **context)
        
        return jsonify({
            'status': 'success',
            'html': html_content
        })
    
    except Exception as e:
        current_app.logger.error(f"Error fetching dashboard data: {e}")
        return jsonify({
            'status': 'error',
            'message': 'An error occurred while loading the dashboard.'
        }), 500

@wallet_bp.route('/switch_wallet', methods=['POST'])
def switch_wallet():
    """API endpoint to switch between wallets"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No data provided.'
            }), 400
            
        wallet_id = data.get('wallet_id')
        
        if not wallet_id:
            return jsonify({
                'status': 'error',
                'message': 'Invalid wallet ID.'
            }), 400
        
        # Validate that the wallet belongs to the user
        user_id = session.get('user_id', '1')  # Default user ID if not logged in
        wallet_manager = WalletManager()
        wallets = wallet_manager.get_user_wallets(user_id)
        
        if not any(w.get('id') == wallet_id for w in wallets):
            return jsonify({
                'status': 'error',
                'message': 'You do not have access to this wallet.'
            }), 403
        
        # Store the selection in session
        session['current_wallet_id'] = wallet_id
        
        return jsonify({
            'status': 'success',
            'message': 'Wallet switched successfully.'
        })
    
    except Exception as e:
        current_app.logger.error(f"Error switching wallet: {e}")
        return jsonify({
            'status': 'error',
            'message': 'An error occurred while switching wallets.'
        }), 500

@wallet_bp.route('/process_action', methods=['POST'])
def process_action():
    """API endpoint to process wallet actions (deposit, withdraw, transfer)"""
    try:
        wallet_manager = WalletManager()
        
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No data provided.'
            }), 400
            
        action = data.get('action')
        params = data.get('params', {})
        
        wallet_id = session.get('current_wallet_id')
        if not wallet_id:
            return jsonify({
                'status': 'error',
                'message': 'No wallet selected.'
            }), 400
        
        if action == 'deposit':
            amount = Decimal(str(params.get('amount', 0)))
            method = params.get('method')
            
            if amount <= 0:
                return jsonify({
                    'status': 'error',
                    'message': 'Amount must be greater than zero.'
                }), 400
            
            # Process deposit
            wallet_manager.record_transaction(
                transaction_type=TransactionType.DEPOSIT,
                asset='USD',  # Assuming default currency, adjust as needed
                amount=amount,
                notes=f"Deposit via {method}"
            )
            
            message = f"Deposit of {amount} initiated successfully."
            
        elif action == 'withdraw':
            amount = Decimal(str(params.get('amount', 0)))
            method = params.get('method')
            
            if amount <= 0:
                return jsonify({
                    'status': 'error',
                    'message': 'Amount must be greater than zero.'
                }), 400
            
            # Get wallet to check available balance
            wallet_data = wallet_manager.get_wallet(wallet_id)
            available = Decimal(str(wallet_data.get('available', 0)))
            
            if amount > available:
                return jsonify({
                    'status': 'error',
                    'message': f'Insufficient funds. You can only withdraw up to {available}.'
                }), 400
            
            # Process withdrawal
            wallet_manager.record_transaction(
                transaction_type=TransactionType.WITHDRAWAL,
                asset='USD',  # Assuming default currency, adjust as needed
                amount=-amount,  # Negative amount for withdrawal
                notes=f"Withdrawal to {method}"
            )
            
            message = f"Withdrawal of {amount} initiated successfully."
            
        elif action == 'transfer':
            amount = Decimal(str(params.get('amount', 0)))
            to_wallet_id = params.get('to_wallet_id')
            
            if amount <= 0:
                return jsonify({
                    'status': 'error',
                    'message': 'Amount must be greater than zero.'
                }), 400
            
            if not to_wallet_id:
                return jsonify({
                    'status': 'error',
                    'message': 'Target wallet not specified.'
                }), 400
            
            # Get wallet to check available balance
            wallet_data = wallet_manager.get_wallet(wallet_id)
            available = Decimal(str(wallet_data.get('available', 0)))
            
            if amount > available:
                return jsonify({
                    'status': 'error',
                    'message': f'Insufficient funds. You can only transfer up to {available}.'
                }), 400
            
            # Process transfer - debit from source wallet
            wallet_manager.record_transaction(
                transaction_type=TransactionType.TRANSFER,
                asset='USD',  # Assuming default currency, adjust as needed
                amount=-amount,  # Negative amount for outgoing transfer
                notes=f"Transfer to wallet {to_wallet_id}"
            )
            
            # Credit to target wallet would typically be handled by a separate process
            # or transaction manager to ensure atomicity
            
            message = f"Transfer of {amount} initiated successfully."
            
        else:
            return jsonify({
                'status': 'error',
                'message': 'Invalid action requested.'
            }), 400
        
        return jsonify({
            'status': 'success',
            'message': message
        })
    
    except ValueError as e:
        current_app.logger.error(f"Value error in wallet action: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Invalid amount specified.'
        }), 400
    except Exception as e:
        current_app.logger.error(f"Error processing wallet action: {e}")
        return jsonify({
            'status': 'error',
            'message': 'An error occurred while processing your request.'
        }), 500 