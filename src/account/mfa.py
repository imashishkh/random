"""
Multi-Factor Authentication (MFA) Module

This module provides functionality for implementing multi-factor authentication
for the withdrawal system, including TOTP (time-based one-time passwords)
and backup code authentication methods.
"""

import os
import base64
import logging
import secrets
import string
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime, timedelta
import pyotp
import qrcode
from io import BytesIO

from ..db import get_db_connection
from .models import User

# Setup logging
logger = logging.getLogger(__name__)

# MFA type constants
class MFAType:
    TOTP = "totp"
    SMS = "sms"
    EMAIL = "email"
    BACKUP = "backup"

# Number of backup codes to generate
NUM_BACKUP_CODES = 10
# Length of each backup code
BACKUP_CODE_LENGTH = 10


def generate_totp_secret() -> str:
    """
    Generate a new secret key for TOTP.
    
    Returns:
        Base32 encoded secret key
    """
    # Generate a random 32-byte value
    random_bytes = secrets.token_bytes(32)
    # Convert to base32 for TOTP
    return base64.b32encode(random_bytes).decode('utf-8')


def get_totp_uri(email: str, secret: str, issuer: str = "ForexTrading") -> str:
    """
    Get the TOTP URI for QR code generation.
    
    Args:
        email: User's email address
        secret: TOTP secret key
        issuer: Name of the issuing application
    
    Returns:
        TOTP URI string
    """
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=email,
        issuer_name=issuer
    )


def generate_qr_code(totp_uri: str) -> BytesIO:
    """
    Generate a QR code for the TOTP URI.
    
    Args:
        totp_uri: TOTP URI string
    
    Returns:
        BytesIO object containing the QR code image
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(totp_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    
    return buffer


def verify_totp_code(secret: str, code: str) -> bool:
    """
    Verify a TOTP code.
    
    Args:
        secret: TOTP secret key
        code: TOTP code to verify
    
    Returns:
        True if code is valid, False otherwise
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(code)


def generate_backup_codes() -> List[str]:
    """
    Generate a set of backup codes.
    
    Returns:
        List of backup codes
    """
    # Define characters to use (alphanumeric, removing similar looking characters)
    allowed_chars = string.ascii_uppercase + string.digits
    allowed_chars = allowed_chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
    
    # Generate random codes
    codes = []
    for _ in range(NUM_BACKUP_CODES):
        # Generate a random code
        code = ''.join(secrets.choice(allowed_chars) for _ in range(BACKUP_CODE_LENGTH))
        # Format with hyphens for readability (e.g., ABCD-EFGH-IJKL)
        formatted_code = '-'.join([code[i:i+4] for i in range(0, len(code), 4)])
        codes.append(formatted_code)
    
    return codes


def setup_mfa_for_user(user_id: str, mfa_type: str = MFAType.TOTP) -> Dict[str, Union[str, List[str]]]:
    """
    Set up MFA for a user.
    
    Args:
        user_id: User ID
        mfa_type: Type of MFA to set up
    
    Returns:
        Dictionary with setup information (secret, URI, QR code, etc.)
    
    Raises:
        ValueError: If setup fails
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Get user
        cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            raise ValueError(f"User with ID {user_id} not found")
        
        # Generate MFA secrets based on type
        if mfa_type == MFAType.TOTP:
            # Generate TOTP secret
            secret = generate_totp_secret()
            
            # Generate URI and QR code
            totp_uri = get_totp_uri(user['email'], secret)
            
            # Generate backup codes
            backup_codes = generate_backup_codes()
            
            # Save to database
            cursor.execute("""
                UPDATE users 
                SET mfa_enabled = TRUE, mfa_type = %s, mfa_secret = %s
                WHERE id = %s
            """, (mfa_type, secret, user_id))
            
            # Save backup codes
            for code in backup_codes:
                cursor.execute("""
                    INSERT INTO mfa_backup_codes (user_id, code)
                    VALUES (%s, %s)
                """, (user_id, code))
            
            conn.commit()
            
            # Return setup info
            return {
                'secret': secret,
                'uri': totp_uri,
                'backup_codes': backup_codes
            }
            
        elif mfa_type == MFAType.SMS:
            # SMS implementation would go here
            raise NotImplementedError("SMS MFA not implemented yet")
            
        elif mfa_type == MFAType.EMAIL:
            # Email implementation would go here
            raise NotImplementedError("Email MFA not implemented yet")
            
        else:
            raise ValueError(f"Unsupported MFA type: {mfa_type}")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error setting up MFA for user {user_id}: {e}")
        raise ValueError(f"Failed to set up MFA: {str(e)}")
    finally:
        conn.close()


def verify_mfa_code(user_id: str, code: str) -> bool:
    """
    Verify an MFA code.
    
    Args:
        user_id: User ID
        code: MFA code to verify
    
    Returns:
        True if code is valid, False otherwise
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Get user's MFA settings
        cursor.execute("""
            SELECT mfa_enabled, mfa_type, mfa_secret 
            FROM users WHERE id = %s
        """, (user_id,))
        user = cursor.fetchone()
        
        if not user:
            logger.error(f"User with ID {user_id} not found")
            return False
        
        if not user['mfa_enabled']:
            logger.error(f"MFA not enabled for user {user_id}")
            return False
        
        # Normalize code (remove spaces and hyphens)
        normalized_code = code.replace(' ', '').replace('-', '')
        
        # Check if it's a backup code
        cursor.execute("""
            SELECT id FROM mfa_backup_codes 
            WHERE user_id = %s AND code = %s AND is_used = FALSE
        """, (user_id, normalized_code))
        backup_code = cursor.fetchone()
        
        if backup_code:
            # Mark backup code as used
            cursor.execute("""
                UPDATE mfa_backup_codes 
                SET is_used = TRUE, used_at = NOW() 
                WHERE id = %s
            """, (backup_code['id'],))
            conn.commit()
            logger.info(f"Backup code used for user {user_id}")
            return True
        
        # Verify based on MFA type
        if user['mfa_type'] == MFAType.TOTP:
            # Verify TOTP code
            return verify_totp_code(user['mfa_secret'], normalized_code)
            
        elif user['mfa_type'] == MFAType.SMS:
            # SMS verification would go here
            # This would typically check a short-lived code in a separate table
            return False
            
        elif user['mfa_type'] == MFAType.EMAIL:
            # Email verification would go here
            return False
            
        else:
            logger.error(f"Unsupported MFA type: {user['mfa_type']}")
            return False
        
    except Exception as e:
        logger.error(f"Error verifying MFA code for user {user_id}: {e}")
        return False
    finally:
        conn.close()


def disable_mfa_for_user(user_id: str) -> bool:
    """
    Disable MFA for a user.
    
    Args:
        user_id: User ID
    
    Returns:
        True if successful, False otherwise
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Disable MFA
        cursor.execute("""
            UPDATE users 
            SET mfa_enabled = FALSE, mfa_type = NULL, mfa_secret = NULL
            WHERE id = %s
        """, (user_id,))
        
        # Delete backup codes
        cursor.execute("""
            DELETE FROM mfa_backup_codes 
            WHERE user_id = %s
        """, (user_id,))
        
        conn.commit()
        logger.info(f"MFA disabled for user {user_id}")
        return True
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error disabling MFA for user {user_id}: {e}")
        return False
    finally:
        conn.close()


def regenerate_backup_codes(user_id: str) -> List[str]:
    """
    Regenerate backup codes for a user.
    
    Args:
        user_id: User ID
    
    Returns:
        List of new backup codes
    
    Raises:
        ValueError: If regeneration fails
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Check if MFA is enabled
        cursor.execute("""
            SELECT mfa_enabled FROM users WHERE id = %s
        """, (user_id,))
        user = cursor.fetchone()
        
        if not user or not user[0]:
            raise ValueError("MFA is not enabled for this user")
        
        # Generate new backup codes
        new_codes = generate_backup_codes()
        
        # Delete old backup codes
        cursor.execute("""
            DELETE FROM mfa_backup_codes 
            WHERE user_id = %s
        """, (user_id,))
        
        # Insert new backup codes
        for code in new_codes:
            cursor.execute("""
                INSERT INTO mfa_backup_codes (user_id, code)
                VALUES (%s, %s)
            """, (user_id, code))
        
        conn.commit()
        logger.info(f"Backup codes regenerated for user {user_id}")
        return new_codes
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error regenerating backup codes for user {user_id}: {e}")
        raise ValueError(f"Failed to regenerate backup codes: {str(e)}")
    finally:
        conn.close()


def get_user_mfa_status(user_id: str) -> Dict[str, Union[bool, str, int]]:
    """
    Get MFA status for a user.
    
    Args:
        user_id: User ID
    
    Returns:
        Dictionary with MFA status information
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Get user MFA settings
        cursor.execute("""
            SELECT mfa_enabled, mfa_type 
            FROM users WHERE id = %s
        """, (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return {
                'enabled': False,
                'type': None,
                'backup_codes_remaining': 0
            }
        
        # Get number of remaining backup codes
        backup_codes_remaining = 0
        if user['mfa_enabled']:
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM mfa_backup_codes 
                WHERE user_id = %s AND is_used = FALSE
            """, (user_id,))
            result = cursor.fetchone()
            backup_codes_remaining = result['count']
        
        return {
            'enabled': user['mfa_enabled'],
            'type': user['mfa_type'],
            'backup_codes_remaining': backup_codes_remaining
        }
        
    except Exception as e:
        logger.error(f"Error getting MFA status for user {user_id}: {e}")
        return {
            'enabled': False,
            'type': None,
            'backup_codes_remaining': 0,
            'error': str(e)
        }
    finally:
        conn.close()


def change_mfa_type(user_id: str, new_mfa_type: str) -> Dict[str, Union[str, List[str]]]:
    """
    Change MFA type for a user.
    
    Args:
        user_id: User ID
        new_mfa_type: New MFA type
    
    Returns:
        Dictionary with setup information for the new MFA type
    
    Raises:
        ValueError: If change fails
    """
    # First disable MFA
    if not disable_mfa_for_user(user_id):
        raise ValueError("Failed to disable current MFA")
    
    # Then set up new MFA
    return setup_mfa_for_user(user_id, new_mfa_type) 