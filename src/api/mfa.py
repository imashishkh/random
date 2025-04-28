"""
MFA API Module

This module provides API endpoints for setting up, verifying,
and managing multi-factor authentication for users.
"""

import logging
import base64
from datetime import datetime
from flask import Blueprint, request, jsonify, g, send_file, session
from io import BytesIO

from ..account.mfa import (
    setup_mfa_for_user, verify_mfa_code, disable_mfa_for_user,
    regenerate_backup_codes, get_user_mfa_status, generate_qr_code,
    get_totp_uri, MFAType
)
from .auth import authenticate, admin_required
from .utils import validate_input, ApiError
from ..db import get_db_connection

# Setup logger
logger = logging.getLogger(__name__)

# Blueprint for MFA endpoints
mfa_bp = Blueprint('mfa', __name__, url_prefix='/api/mfa')


@mfa_bp.route('/status', methods=['GET'])
@authenticate
def get_mfa_status():
    """Get MFA status for the authenticated user."""
    try:
        status = get_user_mfa_status(g.user.id)
        return jsonify({
            'success': True,
            'data': status
        }), 200
    except Exception as e:
        logger.error(f"Error getting MFA status: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@mfa_bp.route('/setup', methods=['POST'])
@authenticate
def setup_mfa():
    """
    Set up MFA for the authenticated user.
    
    Request body:
    {
        "mfa_type": "totp" (optional, defaults to TOTP)
    }
    """
    try:
        data = request.get_json() or {}
        
        # Validate input
        validate_input(data, {
            'mfa_type': {'type': 'string', 'required': False}
        })
        
        # Get MFA type (default to TOTP)
        mfa_type = data.get('mfa_type', MFAType.TOTP)
        
        # Check if the MFA type is supported
        if mfa_type not in [MFAType.TOTP, MFAType.SMS, MFAType.EMAIL]:
            return jsonify({
                'success': False,
                'error': f'Unsupported MFA type: {mfa_type}'
            }), 400
        
        # Set up MFA
        result = setup_mfa_for_user(g.user.id, mfa_type)
        
        # Return success with setup information
        response_data = {
            'success': True,
            'data': {
                'mfa_type': mfa_type,
                'backup_codes': result.get('backup_codes', [])
            },
            'message': 'MFA set up successfully'
        }
        
        # Add TOTP-specific information
        if mfa_type == MFAType.TOTP:
            response_data['data']['secret'] = result['secret']
            response_data['data']['uri'] = result['uri']
        
        return jsonify(response_data), 201
        
    except ValueError as e:
        logger.error(f"Error setting up MFA: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Unexpected error setting up MFA: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@mfa_bp.route('/qrcode', methods=['GET'])
@authenticate
def get_mfa_qrcode():
    """Get QR code for TOTP setup."""
    try:
        # Get MFA status
        status = get_user_mfa_status(g.user.id)
        
        if not status['enabled'] or status['type'] != MFAType.TOTP:
            return jsonify({
                'success': False,
                'error': 'TOTP MFA not enabled'
            }), 400
        
        # Get TOTP secret
        # Note: In a real implementation, you would need to securely fetch the secret
        # This is just an example and might require adjustments based on your actual data model
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT mfa_secret, email FROM users WHERE id = %s
        """, (g.user.id,))
        user = cursor.fetchone()
        conn.close()
        
        if not user or not user['mfa_secret']:
            return jsonify({
                'success': False,
                'error': 'TOTP secret not found'
            }), 400
        
        # Generate URI and QR code
        totp_uri = get_totp_uri(user['email'], user['mfa_secret'])
        qr_buffer = generate_qr_code(totp_uri)
        
        # Return the QR code image
        return send_file(
            qr_buffer,
            mimetype='image/png',
            as_attachment=False,
            download_name='mfa_qrcode.png'
        )
        
    except Exception as e:
        logger.error(f"Error generating QR code: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@mfa_bp.route('/verify', methods=['POST'])
@authenticate
def verify_mfa():
    """
    Verify an MFA code.
    
    Request body:
    {
        "code": "123456"
    }
    """
    try:
        data = request.get_json()
        
        # Validate input
        validate_input(data, {
            'code': {'type': 'string', 'required': True}
        })
        
        code = data['code']
        
        # Verify the code
        is_valid = verify_mfa_code(g.user.id, code)
        
        if is_valid:
            # Store verification in session for sensitive operations
            session['mfa_verified'] = True
            session['mfa_verified_at'] = datetime.now().isoformat()
            
            return jsonify({
                'success': True,
                'message': 'Code verified successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Invalid code'
            }), 400
        
    except Exception as e:
        logger.error(f"Error verifying MFA code: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@mfa_bp.route('/disable', methods=['POST'])
@authenticate
def disable_mfa():
    """
    Disable MFA for the authenticated user.
    
    Request body:
    {
        "code": "123456"  # Current MFA code for verification
    }
    """
    try:
        data = request.get_json()
        
        # Validate input
        validate_input(data, {
            'code': {'type': 'string', 'required': True}
        })
        
        code = data['code']
        
        # Verify the code first
        is_valid = verify_mfa_code(g.user.id, code)
        
        if not is_valid:
            return jsonify({
                'success': False,
                'error': 'Invalid code'
            }), 400
        
        # Disable MFA
        success = disable_mfa_for_user(g.user.id)
        
        if success:
            # Clear MFA verification from session
            if 'mfa_verified' in session:
                del session['mfa_verified']
            if 'mfa_verified_at' in session:
                del session['mfa_verified_at']
                
            return jsonify({
                'success': True,
                'message': 'MFA disabled successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to disable MFA'
            }), 500
        
    except Exception as e:
        logger.error(f"Error disabling MFA: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


@mfa_bp.route('/backup-codes', methods=['POST'])
@authenticate
def generate_new_backup_codes():
    """
    Generate new backup codes.
    
    Request body:
    {
        "code": "123456"  # Current MFA code for verification
    }
    """
    try:
        data = request.get_json()
        
        # Validate input
        validate_input(data, {
            'code': {'type': 'string', 'required': True}
        })
        
        code = data['code']
        
        # Verify the code first
        is_valid = verify_mfa_code(g.user.id, code)
        
        if not is_valid:
            return jsonify({
                'success': False,
                'error': 'Invalid code'
            }), 400
        
        # Generate new backup codes
        new_codes = regenerate_backup_codes(g.user.id)
        
        return jsonify({
            'success': True,
            'data': {
                'backup_codes': new_codes
            },
            'message': 'Backup codes regenerated successfully'
        }), 200
        
    except ValueError as e:
        logger.error(f"Error regenerating backup codes: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Unexpected error regenerating backup codes: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500


def init_app(app):
    """Initialize the MFA blueprint with the app."""
    app.register_blueprint(mfa_bp)
    logger.info("Registered MFA blueprint") 