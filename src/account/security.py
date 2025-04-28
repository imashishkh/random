"""
Security Module for Withdrawal System

This module implements security measures for the withdrawal system, including:
- Velocity checks to detect and prevent suspicious withdrawal patterns
- Withdrawal limits based on user tier and time period
- IP address and device verification
- Notification system for suspicious activities
"""

import os
import logging
import ipaddress
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
from functools import lru_cache

from ..db import get_db_connection
from .models import User

# Setup logging
logger = logging.getLogger(__name__)

# Time windows for velocity checks (in hours)
VELOCITY_TIME_WINDOWS = [1, 24, 168]  # 1 hour, 24 hours (1 day), 168 hours (7 days)

# Default withdrawal limits by tier
DEFAULT_WITHDRAWAL_LIMITS = {
    'basic': {
        'daily': Decimal('1000'),
        'weekly': Decimal('5000'),
        'monthly': Decimal('20000'),
        'per_transaction': Decimal('500')
    },
    'verified': {
        'daily': Decimal('5000'),
        'weekly': Decimal('20000'),
        'monthly': Decimal('50000'),
        'per_transaction': Decimal('2000')
    },
    'premium': {
        'daily': Decimal('20000'),
        'weekly': Decimal('50000'),
        'monthly': Decimal('100000'),
        'per_transaction': Decimal('10000')
    }
}

# Load limits from environment if available
if os.getenv('WITHDRAWAL_LIMITS'):
    import json
    try:
        env_limits = json.loads(os.getenv('WITHDRAWAL_LIMITS'))
        for tier, limits in env_limits.items():
            for period, amount in limits.items():
                DEFAULT_WITHDRAWAL_LIMITS[tier][period] = Decimal(str(amount))
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error parsing withdrawal limits from environment: {e}")

# Threshold multipliers for velocity alerts
VELOCITY_ALERT_THRESHOLDS = {
    'medium': 1.5,  # Alert if velocity is 1.5x the user's average
    'high': 3.0     # Alert if velocity is 3x the user's average
}


def check_withdrawal_limits(
    user_id: str,
    amount: Decimal,
    token_symbol: str = 'BNB'
) -> Tuple[bool, str]:
    """
    Check if a withdrawal amount exceeds the user's limits.
    
    Args:
        user_id: The user's ID
        amount: The withdrawal amount
        token_symbol: The token symbol (default: BNB)
    
    Returns:
        Tuple of (is_allowed, reason)
    """
    conn = get_db_connection()
    try:
        # Get user tier
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT tier FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return False, "User not found"
        
        user_tier = user['tier']
        if user_tier not in DEFAULT_WITHDRAWAL_LIMITS:
            user_tier = 'basic'  # Default to basic tier if user's tier is not defined
        
        limits = DEFAULT_WITHDRAWAL_LIMITS[user_tier]
        
        # Check per-transaction limit
        if amount > limits['per_transaction']:
            return False, f"Amount exceeds per-transaction limit of {limits['per_transaction']}"
        
        # Check daily limit
        daily_start = datetime.now() - timedelta(days=1)
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM withdrawal_requests
            WHERE created_by = %s AND created_at > %s AND status NOT IN ('rejected', 'failed')
        """, (user_id, daily_start))
        daily_total = Decimal(cursor.fetchone()['total'] or 0)
        
        if daily_total + amount > limits['daily']:
            return False, f"Amount would exceed daily withdrawal limit of {limits['daily']}"
        
        # Check weekly limit
        weekly_start = datetime.now() - timedelta(days=7)
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM withdrawal_requests
            WHERE created_by = %s AND created_at > %s AND status NOT IN ('rejected', 'failed')
        """, (user_id, weekly_start))
        weekly_total = Decimal(cursor.fetchone()['total'] or 0)
        
        if weekly_total + amount > limits['weekly']:
            return False, f"Amount would exceed weekly withdrawal limit of {limits['weekly']}"
        
        # Check monthly limit
        monthly_start = datetime.now() - timedelta(days=30)
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM withdrawal_requests
            WHERE created_by = %s AND created_at > %s AND status NOT IN ('rejected', 'failed')
        """, (user_id, monthly_start))
        monthly_total = Decimal(cursor.fetchone()['total'] or 0)
        
        if monthly_total + amount > limits['monthly']:
            return False, f"Amount would exceed monthly withdrawal limit of {limits['monthly']}"
        
        return True, "Withdrawal amount within limits"
        
    except Exception as e:
        logger.error(f"Error checking withdrawal limits: {e}")
        return False, f"Error checking withdrawal limits: {str(e)}"
    finally:
        conn.close()


def check_withdrawal_velocity(
    user_id: str,
    amount: Decimal,
    ip_address: Optional[str] = None,
    device_id: Optional[str] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Check for suspicious withdrawal velocity.
    
    Args:
        user_id: The user's ID
        amount: The withdrawal amount
        ip_address: The user's IP address (optional)
        device_id: The user's device ID (optional)
    
    Returns:
        Tuple of (is_suspicious, details)
    """
    conn = get_db_connection()
    try:
        # Check for withdrawals in different time windows
        velocity_results = {}
        is_suspicious = False
        
        for window_hours in VELOCITY_TIME_WINDOWS:
            window_start = datetime.now() - timedelta(hours=window_hours)
            
            # Get withdrawal count and total in this time window
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
                FROM withdrawal_requests
                WHERE created_by = %s AND created_at > %s
            """, (user_id, window_start))
            result = cursor.fetchone()
            
            # Calculate velocity metrics
            count = result['count']
            total = Decimal(result['total'] or 0)
            avg_amount = total / count if count > 0 else Decimal('0')
            
            # Get historical average for this time window
            historical_start = datetime.now() - timedelta(days=30)  # Look back 30 days
            cursor.execute("""
                SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
                FROM withdrawal_requests
                WHERE created_by = %s AND created_at BETWEEN %s AND %s
            """, (user_id, historical_start, window_start))
            historical = cursor.fetchone()
            
            historical_count = historical['count']
            historical_total = Decimal(historical['total'] or 0)
            
            # Calculate historical averages
            window_days = window_hours / 24
            historical_daily_count = historical_count / 30 if historical_count > 0 else 0
            historical_window_count = historical_daily_count * window_days
            
            historical_daily_amount = historical_total / 30 if historical_total > 0 else Decimal('0')
            historical_window_amount = historical_daily_amount * Decimal(str(window_days))
            
            # Calculate velocity multipliers (comparing current to historical)
            count_multiplier = (count + 1) / (historical_window_count + 1)  # +1 to avoid division by zero
            amount_multiplier = (total + amount) / (historical_window_amount + Decimal('0.0001'))
            
            # Check if velocity is suspicious
            count_alert_level = None
            amount_alert_level = None
            
            if count_multiplier > VELOCITY_ALERT_THRESHOLDS['high']:
                count_alert_level = 'high'
                is_suspicious = True
            elif count_multiplier > VELOCITY_ALERT_THRESHOLDS['medium']:
                count_alert_level = 'medium'
            
            if amount_multiplier > VELOCITY_ALERT_THRESHOLDS['high']:
                amount_alert_level = 'high'
                is_suspicious = True
            elif amount_multiplier > VELOCITY_ALERT_THRESHOLDS['medium']:
                amount_alert_level = 'medium'
            
            velocity_results[f"{window_hours}h"] = {
                'current_count': count,
                'current_total': float(total),
                'historical_window_count': float(historical_window_count),
                'historical_window_amount': float(historical_window_amount),
                'count_multiplier': float(count_multiplier),
                'amount_multiplier': float(amount_multiplier),
                'count_alert_level': count_alert_level,
                'amount_alert_level': amount_alert_level
            }
        
        # Check for new IP address
        ip_suspicious = False
        if ip_address:
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM user_auth_events
                WHERE user_id = %s AND ip_address = %s AND created_at > %s
            """, (user_id, ip_address, datetime.now() - timedelta(days=30)))
            ip_history = cursor.fetchone()
            
            if ip_history['count'] == 0:
                ip_suspicious = True
                is_suspicious = True
        
        # Check for new device
        device_suspicious = False
        if device_id:
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM user_auth_events
                WHERE user_id = %s AND device_id = %s AND created_at > %s
            """, (user_id, device_id, datetime.now() - timedelta(days=30)))
            device_history = cursor.fetchone()
            
            if device_history['count'] == 0:
                device_suspicious = True
                is_suspicious = True
        
        details = {
            'is_suspicious': is_suspicious,
            'velocity_checks': velocity_results,
            'ip_suspicious': ip_suspicious,
            'device_suspicious': device_suspicious,
            'timestamp': datetime.now().isoformat()
        }
        
        if is_suspicious:
            # Log suspicious activity
            log_suspicious_activity(user_id, 'withdrawal_velocity', details)
        
        return is_suspicious, details
        
    except Exception as e:
        logger.error(f"Error checking withdrawal velocity: {e}")
        return True, {'error': str(e)}  # Default to suspicious if there's an error
    finally:
        conn.close()


def verify_withdrawal_request(
    user_id: str,
    wallet_id: int,
    amount: Decimal,
    token_symbol: str = 'BNB',
    ip_address: Optional[str] = None,
    device_id: Optional[str] = None,
    mfa_verified: bool = False
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Comprehensive verification of a withdrawal request.
    
    Args:
        user_id: The user's ID
        wallet_id: The wallet ID
        amount: The withdrawal amount
        token_symbol: The token symbol
        ip_address: The user's IP address
        device_id: The user's device ID
        mfa_verified: Whether MFA has been verified
    
    Returns:
        Tuple of (is_allowed, reason, details)
    """
    # Check MFA verification
    if not mfa_verified:
        return False, "MFA verification required for withdrawals", {}
    
    # Check withdrawal limits
    limits_allowed, limits_reason = check_withdrawal_limits(user_id, amount, token_symbol)
    if not limits_allowed:
        return False, limits_reason, {}
    
    # Check velocity
    is_suspicious, velocity_details = check_withdrawal_velocity(
        user_id, amount, ip_address, device_id
    )
    
    # If suspicious, require additional verification or admin approval
    if is_suspicious:
        # For highly suspicious activity, block the withdrawal
        if any(
            velocity_details['velocity_checks'][window]['count_alert_level'] == 'high' or
            velocity_details['velocity_checks'][window]['amount_alert_level'] == 'high'
            for window in velocity_details['velocity_checks']
        ):
            return False, "Withdrawal blocked due to suspicious activity", velocity_details
        
        # For medium suspicious activity, flag for review
        return True, "Withdrawal flagged for review due to unusual activity", velocity_details
    
    return True, "Withdrawal verified", velocity_details


def log_suspicious_activity(user_id: str, activity_type: str, details: Dict[str, Any]) -> bool:
    """
    Log suspicious activity for further review.
    
    Args:
        user_id: The user's ID
        activity_type: Type of suspicious activity
        details: Details of the suspicious activity
    
    Returns:
        True if logged successfully, False otherwise
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Convert details to JSON string
        import json
        details_json = json.dumps(details)
        
        query = """
        INSERT INTO security_alerts
        (user_id, alert_type, details, is_resolved, created_at)
        VALUES (%s, %s, %s, FALSE, NOW())
        """
        
        cursor.execute(query, (user_id, activity_type, details_json))
        conn.commit()
        
        logger.warning(
            f"Suspicious activity detected - User: {user_id}, "
            f"Type: {activity_type}, Details: {details_json}"
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error logging suspicious activity: {e}")
        return False
    finally:
        conn.close()


def get_client_risk_score(
    user_id: str,
    ip_address: Optional[str] = None,
    device_id: Optional[str] = None
) -> float:
    """
    Calculate a risk score for the client based on various factors.
    
    Args:
        user_id: The user's ID
        ip_address: The user's IP address
        device_id: The user's device ID
    
    Returns:
        Risk score between 0 (low risk) and 1 (high risk)
    """
    risk_score = 0.0
    risk_factors = 0
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Check account age
        cursor.execute("""
            SELECT created_at FROM users WHERE id = %s
        """, (user_id,))
        user = cursor.fetchone()
        
        if user:
            account_age_days = (datetime.now() - user['created_at']).days
            if account_age_days < 30:
                risk_score += 0.3
            elif account_age_days < 90:
                risk_score += 0.1
            risk_factors += 1
        
        # Check previous suspicious activities
        cursor.execute("""
            SELECT COUNT(*) as count FROM security_alerts
            WHERE user_id = %s AND created_at > %s
        """, (user_id, datetime.now() - timedelta(days=90)))
        alerts = cursor.fetchone()
        
        if alerts and alerts['count'] > 0:
            if alerts['count'] >= 5:
                risk_score += 0.5
            else:
                risk_score += 0.1 * alerts['count']
            risk_factors += 1
        
        # Check IP address risk
        if ip_address:
            # Check if IP is from high-risk country
            country_code = get_country_from_ip(ip_address)
            if country_code in get_high_risk_countries():
                risk_score += 0.3
                risk_factors += 1
            
            # Check for IP address history
            cursor.execute("""
                SELECT COUNT(*) as count FROM user_auth_events
                WHERE user_id = %s AND ip_address = %s
            """, (user_id, ip_address))
            ip_history = cursor.fetchone()
            
            if ip_history and ip_history['count'] == 0:
                risk_score += 0.2  # New IP address
            risk_factors += 1
            
            # Check for multiple users from same IP
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as count FROM user_auth_events
                WHERE ip_address = %s AND user_id != %s
            """, (ip_address, user_id))
            shared_ip = cursor.fetchone()
            
            if shared_ip and shared_ip['count'] > 5:
                risk_score += 0.2  # IP shared by many users
            risk_factors += 1
        
        # Normalize risk score
        if risk_factors > 0:
            # Cap at 1.0
            return min(risk_score / risk_factors, 1.0)
        return 0.0
        
    except Exception as e:
        logger.error(f"Error calculating client risk score: {e}")
        return 0.5  # Default to medium risk on error
    finally:
        conn.close()


@lru_cache(maxsize=1024)
def get_country_from_ip(ip_address: str) -> Optional[str]:
    """
    Get country code from IP address.
    
    Args:
        ip_address: IP address to check
    
    Returns:
        Two-letter country code or None if not found
    """
    try:
        # This is a placeholder - in a real implementation,
        # you would use a GeoIP database like MaxMind
        # For now, just return None
        return None
    except Exception as e:
        logger.error(f"Error getting country from IP: {e}")
        return None


@lru_cache(maxsize=1)
def get_high_risk_countries() -> List[str]:
    """
    Get list of high-risk countries.
    
    Returns:
        List of two-letter country codes
    """
    # This should ideally be loaded from a configuration file or database
    # These are just examples and should be updated based on your risk assessment
    return [
        'AF', 'IR', 'KP', 'RU', 'SY', 'VE', 'YE', 'ZW'
    ]


def is_ip_in_allowed_range(ip_address: str, allowed_ranges: List[str]) -> bool:
    """
    Check if an IP address is within allowed ranges.
    
    Args:
        ip_address: IP address to check
        allowed_ranges: List of allowed CIDR ranges
    
    Returns:
        True if IP is in allowed range, False otherwise
    """
    try:
        ip = ipaddress.ip_address(ip_address)
        return any(ip in ipaddress.ip_network(allowed_range) for allowed_range in allowed_ranges)
    except ValueError:
        return False


def require_enhanced_verification(risk_score: float) -> bool:
    """
    Determine if enhanced verification is required based on risk score.
    
    Args:
        risk_score: Risk score between 0 and 1
    
    Returns:
        True if enhanced verification is required, False otherwise
    """
    # These thresholds can be adjusted based on your risk tolerance
    if risk_score >= 0.7:  # High risk
        return True
    elif risk_score >= 0.4:  # Medium risk
        # For medium risk, randomly require enhanced verification 50% of the time
        import random
        return random.random() < 0.5
    return False  # Low risk 