"""
Withdrawal Management API

This module provides API endpoints to manage withdrawal requests,
including creating, approving, rejecting, and processing withdrawals.
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional
from flask import Blueprint, request, jsonify, g

from ..account.withdrawal import (
    create_withdrawal_request, get_withdrawal_request,
    get_user_withdrawal_requests, approve_withdrawal_request,
    reject_withdrawal_request, process_approved_withdrawals,
    WithdrawalStatus
)
from .auth import authenticate, admin_required
from .utils import validate_input, ApiError

# Setup logger
logger = logging.getLogger(__name__)

# Blueprint for withdrawal endpoints
withdrawal_bp = Blueprint('withdrawal', __name__, url_prefix='/api/withdrawal')


@withdrawal_bp.route('/request', methods=['POST'])
@authenticate
def create_request():
    """
    Create a new withdrawal request.
    
    Request body:
    {
        "wallet_id": 123,
        "to_address": "0x123...",
        "amount": "0.5",
        "token_address": "0xabc..." (optional)
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        validate_input(data, {
            'wallet_id': {'type': 'int', 'required': True},
            'to_address': {'type': 'string', 'required': True},
            'amount': {'type': 'decimal', 'required': True, 'min': 0.00000001},
            'token_address': {'type': 'string', 'required': False}
        })
        
        # Get values
        wallet_id = data['wallet_id']
        to_address = data['to_address']
        amount = Decimal(str(data['amount']))
        token_address = data.get('token_address')
        user_id = g.user.id
        
        # Create withdrawal request
        request_id = create_withdrawal_request(
            user_id=user_id,
            wallet_id=wallet_id,
            to_address=to_address,
            amount=amount,
            token_address=token_address
        )
        
        # Return success response
        return jsonify({
            'success': True,
            'request_id': request_id,
            'message': 'Withdrawal request created successfully'
        }), 201
        
    except ValueError as e:
        logger.error(f"Error creating withdrawal request: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Unexpected error creating withdrawal request: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@withdrawal_bp.route('/request/<int:request_id>', methods=['GET'])
@authenticate
def get_request(request_id: int):
    """Get a withdrawal request by ID."""
    try:
        # Get withdrawal request
        withdrawal = get_withdrawal_request(request_id)
        
        if not withdrawal:
            return jsonify({
                'success': False,
                'error': f'Withdrawal request {request_id} not found'
            }), 404
        
        # Check if user is authorized to view this request
        if withdrawal['user_id'] != g.user.id and not g.user.is_admin:
            return jsonify({
                'success': False,
                'error': 'Not authorized to view this withdrawal request'
            }), 403
        
        # Return withdrawal request details
        return jsonify({
            'success': True,
            'data': withdrawal
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting withdrawal request: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@withdrawal_bp.route('/user', methods=['GET'])
@authenticate
def get_user_requests():
    """Get withdrawal requests for the authenticated user."""
    try:
        # Get pagination parameters
        limit = int(request.args.get('limit', 20))
        offset = int(request.args.get('offset', 0))
        
        # Limit maximum results
        if limit > 100:
            limit = 100
        
        # Get user's withdrawal requests
        withdrawals = get_user_withdrawal_requests(
            user_id=g.user.id,
            limit=limit,
            offset=offset
        )
        
        # Return success response
        return jsonify({
            'success': True,
            'data': {
                'withdrawals': withdrawals,
                'count': len(withdrawals),
                'limit': limit,
                'offset': offset
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting user withdrawal requests: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@withdrawal_bp.route('/pending', methods=['GET'])
@admin_required
def get_pending_requests():
    """Get pending withdrawal requests (admin only)."""
    try:
        # Get pagination parameters
        limit = int(request.args.get('limit', 20))
        
        # Limit maximum results
        if limit > 100:
            limit = 100
        
        # Get pending withdrawal requests
        from src.account.withdrawal import get_pending_withdrawal_requests
        withdrawals = get_pending_withdrawal_requests(limit=limit)
        
        # Return success response
        return jsonify({
            'success': True,
            'data': {
                'withdrawals': withdrawals,
                'count': len(withdrawals)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting pending withdrawal requests: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@withdrawal_bp.route('/approve/<int:request_id>', methods=['POST'])
@authenticate
def approve_request(request_id: int):
    """
    Approve a withdrawal request.
    
    Request body (optional):
    {
        "approver_address": "0x123..."
    }
    """
    try:
        data = request.get_json() or {}
        
        # Get approver address (can be overridden for admin)
        approver_address = data.get('approver_address')
        
        # Fetch the withdrawal request to check ownership/permissions
        withdrawal = get_withdrawal_request(request_id)
        
        if not withdrawal:
            return jsonify({
                'success': False,
                'error': f'Withdrawal request {request_id} not found'
            }), 404
        
        # For non-admins, verify ownership if it's not a multisig
        if not g.user.is_admin and withdrawal['user_id'] != g.user.id:
            return jsonify({
                'success': False,
                'error': 'Not authorized to approve this withdrawal request'
            }), 403
        
        # Must provide approver address
        if not approver_address:
            return jsonify({
                'success': False,
                'error': 'Approver address is required'
            }), 400
        
        # Approve the withdrawal request
        approved = approve_withdrawal_request(
            request_id=request_id,
            approver_address=approver_address
        )
        
        # Return success response
        return jsonify({
            'success': approved,
            'message': 'Withdrawal request approved successfully'
        }), 200
        
    except ValueError as e:
        logger.error(f"Error approving withdrawal request: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Unexpected error approving withdrawal request: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@withdrawal_bp.route('/reject/<int:request_id>', methods=['POST'])
@authenticate
def reject_request(request_id: int):
    """
    Reject a withdrawal request.
    
    Request body:
    {
        "approver_address": "0x123...",
        "reason": "Optional reason for rejection"
    }
    """
    try:
        data = request.get_json() or {}
        
        # Get approver address and reason
        approver_address = data.get('approver_address')
        reason = data.get('reason', '')
        
        # Must provide approver address
        if not approver_address:
            return jsonify({
                'success': False,
                'error': 'Approver address is required'
            }), 400
        
        # Fetch the withdrawal request to check ownership/permissions
        withdrawal = get_withdrawal_request(request_id)
        
        if not withdrawal:
            return jsonify({
                'success': False,
                'error': f'Withdrawal request {request_id} not found'
            }), 404
        
        # For non-admins, verify ownership
        if not g.user.is_admin and withdrawal['user_id'] != g.user.id:
            return jsonify({
                'success': False,
                'error': 'Not authorized to reject this withdrawal request'
            }), 403
        
        # Reject the withdrawal request
        rejected = reject_withdrawal_request(
            request_id=request_id,
            approver_address=approver_address,
            reason=reason
        )
        
        # Return success response
        return jsonify({
            'success': rejected,
            'message': 'Withdrawal request rejected successfully'
        }), 200
        
    except ValueError as e:
        logger.error(f"Error rejecting withdrawal request: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Unexpected error rejecting withdrawal request: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@withdrawal_bp.route('/process', methods=['POST'])
@admin_required
def process_withdrawals():
    """
    Process approved withdrawal requests (admin only).
    
    Request body:
    {
        "password": "password to decrypt wallet keys",
        "batch_size": 5 (optional)
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        validate_input(data, {
            'password': {'type': 'string', 'required': True},
            'batch_size': {'type': 'int', 'required': False, 'min': 1, 'max': 50}
        })
        
        # Get values
        password = data['password']
        batch_size = data.get('batch_size', 5)
        
        # Process approved withdrawals
        results = process_approved_withdrawals(
            password=password,
            batch_size=batch_size
        )
        
        # Return success response
        return jsonify({
            'success': True,
            'data': {
                'processed': len(results),
                'results': results
            }
        }), 200
        
    except ValueError as e:
        logger.error(f"Error processing withdrawals: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Unexpected error processing withdrawals: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


def init_app(app):
    """Register blueprint with Flask app."""
    app.register_blueprint(withdrawal_bp)
    logger.info("Registered withdrawal API endpoints") 