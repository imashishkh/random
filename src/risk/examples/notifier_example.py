"""
Risk Notifier Example

This script demonstrates how to use the RiskNotifier class to send
risk alerts via Slack for different scenarios.
"""

import os
import sys
import logging
import json
from datetime import datetime
import time
from pathlib import Path

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from .notifier import RiskNotifier, NotificationConfig, NotificationLevel, NotificationTemplate
from .manager import RiskManager


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_notifier():
    """Set up a RiskNotifier with a Slack webhook."""
    # Get webhook URL from environment variable or use a placeholder
    webhook_url = os.environ.get('SLACK_WEBHOOK_URL', 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL')
    
    # Create notification config
    config = NotificationConfig(
        slack_webhook_url=webhook_url,
        rate_limit_period=60,  # 1 minute rate limit period
        rate_limit_count={
            NotificationLevel.INFO.value: 5,
            NotificationLevel.WARNING.value: 3,
            NotificationLevel.CRITICAL.value: 1,
        },
        fallback_to_logging=True
    )
    
    # Create notifier
    notifier = RiskNotifier(config)
    
    # Add custom template
    notifier.add_template("market_volatility_alert", NotificationTemplate(
        title="Market Volatility Alert",
        message="Unusual volatility detected in {symbol}. Current volatility is {volatility:.2f}x normal levels.",
        fields={
            "Symbol": "{symbol}",
            "Current Volatility": "{volatility:.2f}x normal",
            "Price Change": "{price_change:.2%} in {time_period}",
            "Recommendation": "{recommendation}"
        },
        actions=[
            {"text": "View Chart", "url": "{chart_url}"},
            {"text": "Adjust Risk Settings", "url": "{settings_url}"}
        ]
    ))
    
    return notifier


def integrate_with_risk_manager(notifier):
    """Demonstrate integration with RiskManager."""
    # Create a RiskManager instance
    risk_manager = RiskManager(account_balance=100000.0)
    
    # Simulate positions
    positions = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "0.5",
            "entryPrice": "40000",
            "markPrice": "41000",
            "unRealizedProfit": "500",
            "liquidationPrice": "35000",
            "leverage": "5",
            "marginType": "isolated",
            "positionSide": "LONG"
        },
        {
            "symbol": "ETHUSDT",
            "positionAmt": "5",
            "entryPrice": "2500",
            "markPrice": "2600",
            "unRealizedProfit": "500",
            "liquidationPrice": "2000",
            "leverage": "5",
            "marginType": "isolated",
            "positionSide": "LONG"
        }
    ]
    
    # Mock the position fetching method
    risk_manager.fetch_binance_position_risk = lambda: positions
    
    # Update position tracking
    normalized_positions = risk_manager._normalize_position_data(positions)
    risk_manager._update_position_tracking(normalized_positions)
    
    # Override RiskManager's _send_slack_alert method to use our notifier
    def send_slack_alert(message, severity="info"):
        return notifier.notify_simple(severity, f"Risk Manager Alert", message)
    
    risk_manager._send_slack_alert = send_slack_alert
    
    # Override _send_risk_alerts to use our templated notifications
    def send_risk_alerts(violations):
        if not violations:
            return
            
        for v in violations:
            if v['type'] == 'global_exposure':
                notifier.notify(
                    v['severity'],
                    "global_exposure_exceeded",
                    {
                        "current_exposure": v['current'],
                        "exposure_limit": v['limit'],
                        "limit_type": v['severity'],
                        "portfolio_value": risk_manager.account_balance
                    }
                )
            elif v['type'] == 'symbol_exposure':
                position = risk_manager.get_position(v['symbol'])
                notifier.notify(
                    v['severity'],
                    "symbol_exposure_exceeded",
                    {
                        "symbol": v['symbol'],
                        "current_exposure": v['current'],
                        "exposure_limit": v['limit'],
                        "limit_type": v['severity'],
                        "position_size": position['size'],
                        "position_value": position['notional_value']
                    }
                )
    
    risk_manager._send_risk_alerts = send_risk_alerts
    
    # Override activate_circuit_breaker to use our templates
    original_activate_circuit_breaker = risk_manager.activate_circuit_breaker
    
    def activate_circuit_breaker_with_notification(reason, duration=None):
        result = original_activate_circuit_breaker(reason, duration)
        
        # Send notification
        activated_at = datetime.now()
        duration = duration or risk_manager.params['circuit_breaker_timeout']
        resume_at = datetime.fromtimestamp(risk_manager._circuit_breaker_end_time).strftime('%Y-%m-%d %H:%M:%S')
        
        notifier.notify(
            NotificationLevel.CRITICAL,
            "circuit_breaker_activated",
            {
                "reason": reason,
                "duration": duration,
                "activated_at": activated_at.strftime('%Y-%m-%d %H:%M:%S'),
                "resume_at": resume_at
            }
        )
        
        return result
    
    risk_manager.activate_circuit_breaker = activate_circuit_breaker_with_notification
    
    return risk_manager


def demonstrate_notifications(notifier, risk_manager):
    """Demonstrate various notification scenarios."""
    logger.info("Starting notification demonstrations...")
    
    # 1. Simple notifications
    logger.info("1. Sending simple notifications at different levels...")
    notifier.notify_simple(NotificationLevel.INFO, "Info Alert", "This is an informational alert.")
    time.sleep(1)
    notifier.notify_simple(NotificationLevel.WARNING, "Warning Alert", "This is a warning alert!")
    time.sleep(1)
    notifier.notify_simple(NotificationLevel.CRITICAL, "Critical Alert", "This is a critical alert!!!")
    time.sleep(1)
    
    # 2. Template-based notifications
    logger.info("2. Sending template-based notification for market volatility...")
    notifier.notify(
        NotificationLevel.WARNING,
        "market_volatility_alert",
        {
            "symbol": "BTCUSDT",
            "volatility": 2.5,
            "price_change": 0.045,
            "time_period": "1 hour",
            "recommendation": "Consider reducing position sizes",
            "chart_url": "https://example.com/chart/BTCUSDT",
            "settings_url": "https://example.com/risk-settings"
        }
    )
    time.sleep(1)
    
    # 3. Risk Manager integrated notifications
    logger.info("3. Demonstrating Risk Manager integrated notifications...")
    
    # Simulate global exposure limit violation
    logger.info("3.1. Simulating global exposure limit violation...")
    risk_manager._total_exposure = 0.85  # Set above the default 0.80 limit
    violations = risk_manager.check_risk_limits()
    risk_manager._handle_violations(violations['violations'])
    time.sleep(1)
    
    # Simulate circuit breaker activation
    logger.info("3.2. Simulating circuit breaker activation...")
    risk_manager.activate_circuit_breaker("Sudden 5% price drop in BTCUSDT", 300)
    time.sleep(1)
    
    # Simulate emergency shutdown
    logger.info("3.3. Simulating emergency shutdown...")
    # Override emergency_shutdown to avoid actual API calls
    original_shutdown = risk_manager.emergency_shutdown
    risk_manager.emergency_shutdown = lambda reason="manual": {
        "success": True,
        "reason": reason,
        "positions_closed": 2,
        "results": [
            {"symbol": "BTCUSDT", "success": True},
            {"symbol": "ETHUSDT", "success": True}
        ]
    }
    
    # Override _send_emergency_alert to use our template
    def send_emergency_alert(reason, results):
        success_count = sum(1 for r in results if r.get('success', False))
        failure_count = len(results) - success_count
        
        notifier.notify(
            NotificationLevel.CRITICAL,
            "emergency_shutdown",
            {
                "reason": reason,
                "triggered_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "positions_closed": f"{success_count}/{len(results)}",
                "failures": failure_count,
                "dashboard_url": "https://example.com/dashboard",
                "reset_url": "https://example.com/reset-system"
            }
        )
    
    risk_manager._send_emergency_alert = send_emergency_alert
    
    # Trigger emergency shutdown
    risk_manager.emergency_shutdown("Manual demonstration shutdown")
    
    logger.info("All demonstrations completed.")


def demonstrate_rate_limiting(notifier):
    """Demonstrate rate limiting functionality."""
    logger.info("4. Demonstrating rate limiting...")
    
    # Try to send multiple info notifications (limit: 5)
    logger.info("4.1. Sending 7 INFO notifications (limit: 5)...")
    for i in range(7):
        result = notifier.notify_simple(
            NotificationLevel.INFO,
            f"Rate Limit Test {i+1}",
            f"This is test message {i+1}"
        )
        logger.info(f"Message {i+1} sent: {result}")
        time.sleep(0.2)
    
    # Try to send multiple critical notifications (limit: 1)
    logger.info("4.2. Sending 3 CRITICAL notifications (limit: 1)...")
    for i in range(3):
        result = notifier.notify_simple(
            NotificationLevel.CRITICAL,
            f"Critical Rate Limit Test {i+1}",
            f"This is critical test message {i+1}"
        )
        logger.info(f"Critical message {i+1} sent: {result}")
        time.sleep(0.2)


if __name__ == "__main__":
    try:
        # Set up the notifier
        notifier = setup_notifier()
        
        # Integrate with risk manager
        risk_manager = integrate_with_risk_manager(notifier)
        
        # Run demonstrations
        demonstrate_notifications(notifier, risk_manager)
        
        # Demonstrate rate limiting
        demonstrate_rate_limiting(notifier)
        
    except Exception as e:
        logger.error(f"Error in demonstration: {e}", exc_info=True) 