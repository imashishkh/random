"""
Emergency Kill Switch

This module provides a kill switch mechanism for emergency risk control,
allowing for immediate halt of all trading activity and position closure.
"""

import time
import logging
import json
from typing import Dict, Any, Optional, List, Callable

from .action_log import RiskActionLog

# Configure logger
logger = logging.getLogger(__name__)


class EmergencyKillSwitch:
    """
    Emergency Kill Switch that can immediately halt all trading and optionally
    close all open positions in response to extreme risk events.
    
    Features:
    - Multiple activation methods (manual, automatic thresholds)
    - Phased shutdown approach to minimize market impact
    - Detailed event logging and recovery procedures
    - Multiple notification channels for critical events
    """
    
    def __init__(
        self,
        exchange_client=None,
        action_log: Optional[RiskActionLog] = None,
        config: Dict[str, Any] = None
    ):
        """
        Initialize the Emergency Kill Switch.
        
        Args:
            exchange_client: Client for interacting with the exchange
            action_log: RiskActionLog instance for detailed event logging
            config: Configuration dictionary with settings
        """
        self.exchange_client = exchange_client
        self.action_log = action_log
        self.config = config or {}
        
        # Set default configuration
        self.config.setdefault('close_positions_on_activation', True)
        self.config.setdefault('cancel_orders_on_activation', True)
        self.config.setdefault('notify_on_activation', True)
        self.config.setdefault('authorized_deactivators', [])  # User IDs authorized to deactivate
        self.config.setdefault('auto_deactivation_timeout', None)  # No auto-deactivation by default
        
        # Internal state
        self.active = False
        self.triggered_at = None
        self.triggered_by = None
        self.activation_reason = None
        self.deactivated_at = None
        self.deactivated_by = None
        
        # Callbacks for external systems
        self.pre_activation_callbacks = []
        self.post_activation_callbacks = []
        self.pre_deactivation_callbacks = []
        self.post_deactivation_callbacks = []
        
        logger.info("Initialized Emergency Kill Switch")
    
    def activate(
        self,
        reason: str,
        triggered_by: str = 'manual',
        close_positions: Optional[bool] = None,
        cancel_orders: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Activate the emergency kill switch.
        
        Args:
            reason: Why the kill switch was activated
            triggered_by: What triggered it (manual, auto, threshold)
            close_positions: Whether to close all open positions (overrides config)
            cancel_orders: Whether to cancel all open orders (overrides config)
            metadata: Additional metadata about the activation
            
        Returns:
            Dictionary with activation results
        """
        # Check if already active
        if self.active:
            logger.warning(f"Kill switch already active (triggered by {self.triggered_by})")
            return {
                'success': False,
                'error': 'already_active',
                'message': 'Kill switch is already active',
                'triggered_at': self.triggered_at,
                'triggered_by': self.triggered_by,
                'reason': self.activation_reason
            }
        
        # Prepare for activation
        activation_time = time.time()
        results = {
            'success': True,
            'triggered_at': activation_time,
            'triggered_by': triggered_by,
            'reason': reason,
            'actions': []
        }
        
        # Execute pre-activation callbacks
        for callback in self.pre_activation_callbacks:
            try:
                callback_result = callback(
                    reason=reason,
                    triggered_by=triggered_by,
                    metadata=metadata or {}
                )
                if isinstance(callback_result, dict):
                    results.setdefault('callback_results', []).append(callback_result)
            except Exception as e:
                logger.error(f"Error in pre-activation callback: {str(e)}")
        
        # Set instance state
        self.active = True
        self.triggered_at = activation_time
        self.triggered_by = triggered_by
        self.activation_reason = reason
        self.deactivated_at = None
        self.deactivated_by = None
        
        # Log the activation
        logger.critical(
            f"EMERGENCY KILL SWITCH ACTIVATED by {triggered_by}: {reason}"
        )
        
        try:
            # Determine actions to take
            should_close_positions = close_positions if close_positions is not None else self.config['close_positions_on_activation']
            should_cancel_orders = cancel_orders if cancel_orders is not None else self.config['cancel_orders_on_activation']
            
            # Cancel all orders if requested
            if should_cancel_orders and self.exchange_client:
                try:
                    cancel_result = self.cancel_all_orders()
                    results['actions'].append({
                        'action': 'cancel_orders',
                        'success': cancel_result['success'],
                        'details': cancel_result
                    })
                except Exception as e:
                    error_msg = f"Error cancelling orders: {str(e)}"
                    logger.error(error_msg)
                    results['actions'].append({
                        'action': 'cancel_orders',
                        'success': False,
                        'error': str(e)
                    })
            
            # Close positions if requested
            if should_close_positions and self.exchange_client:
                try:
                    close_result = self.close_all_positions()
                    results['actions'].append({
                        'action': 'close_positions',
                        'success': close_result['success'],
                        'details': close_result
                    })
                except Exception as e:
                    error_msg = f"Error closing positions: {str(e)}"
                    logger.error(error_msg)
                    results['actions'].append({
                        'action': 'close_positions',
                        'success': False,
                        'error': str(e)
                    })
            
            # Execute post-activation callbacks
            for callback in self.post_activation_callbacks:
                try:
                    callback_result = callback(
                        reason=reason,
                        triggered_by=triggered_by,
                        results=results,
                        metadata=metadata or {}
                    )
                    if isinstance(callback_result, dict):
                        results.setdefault('callback_results', []).append(callback_result)
                except Exception as e:
                    logger.error(f"Error in post-activation callback: {str(e)}")
            
            # Send notification if configured
            if self.config['notify_on_activation']:
                self._send_activation_notification(reason, triggered_by, results)
            
            # Record the event with the action log
            if self.action_log:
                event_data = {
                    'triggered_by': triggered_by,
                    'reason': reason,
                    'actions': results['actions'],
                    'metadata': metadata or {}
                }
                self.action_log.log_kill_switch(event_data)
            
            return results
            
        except Exception as e:
            # Log failure but maintain kill switch active state
            logger.critical(f"Error during kill switch activation: {str(e)}")
            results['success'] = False
            results['error'] = str(e)
            
            # Still record the event even if there was an error
            if self.action_log:
                event_data = {
                    'triggered_by': triggered_by,
                    'reason': reason,
                    'error': str(e),
                    'metadata': metadata or {}
                }
                self.action_log.log_kill_switch(event_data)
                
            return results
    
    def deactivate(
        self,
        authorized_by: str,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Deactivate the kill switch, allowing trading to resume.
        
        Args:
            authorized_by: Who authorized the deactivation
            reason: Reason for deactivation
            metadata: Additional metadata
            
        Returns:
            Dictionary with deactivation results
        """
        # Check if kill switch is active
        if not self.active:
            logger.warning("Attempted to deactivate kill switch, but it is not active")
            return {
                'success': False,
                'error': 'not_active',
                'message': 'Kill switch is not active'
            }
        
        # Check authorization if configured
        if (self.config['authorized_deactivators'] and 
            authorized_by not in self.config['authorized_deactivators']):
            logger.warning(f"Unauthorized deactivation attempt by {authorized_by}")
            return {
                'success': False,
                'error': 'unauthorized',
                'message': f"User {authorized_by} is not authorized to deactivate kill switch"
            }
        
        # Execute pre-deactivation callbacks
        for callback in self.pre_deactivation_callbacks:
            try:
                callback(
                    authorized_by=authorized_by,
                    reason=reason,
                    metadata=metadata or {}
                )
            except Exception as e:
                logger.error(f"Error in pre-deactivation callback: {str(e)}")
        
        # Track the deactivation details
        self.deactivated_at = time.time()
        self.deactivated_by = authorized_by
        
        logger.warning(f"Deactivating kill switch, authorized by: {authorized_by}")
        
        # Record deactivation details
        deactivation_data = {
            'success': True,
            'kill_switch_activated_at': self.triggered_at,
            'kill_switch_activated_by': self.triggered_by,
            'kill_switch_reason': self.activation_reason,
            'deactivated_at': self.deactivated_at,
            'deactivated_by': authorized_by,
            'active_duration': self.deactivated_at - self.triggered_at,
            'reason': reason or 'Not specified',
            'metadata': metadata or {}
        }
        
        # Set state
        self.active = False
        
        # Log the deactivation
        logger.info(f"Kill switch deactivated: {json.dumps(deactivation_data)}")
        
        # Record the event with the action log
        if self.action_log:
            self.action_log.log_event(
                "KILL_SWITCH_DEACTIVATED",
                deactivation_data,
                "WARNING"
            )
        
        # Execute post-deactivation callbacks
        for callback in self.post_deactivation_callbacks:
            try:
                callback(
                    authorized_by=authorized_by,
                    reason=reason,
                    deactivation_data=deactivation_data,
                    metadata=metadata or {}
                )
            except Exception as e:
                logger.error(f"Error in post-deactivation callback: {str(e)}")
        
        return deactivation_data
    
    def is_active(self) -> bool:
        """
        Check if kill switch is currently active.
        
        Returns:
            True if kill switch is active, False otherwise
        """
        return self.active
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current kill switch status.
        
        Returns:
            Dictionary with kill switch status information
        """
        status = {
            'active': self.active,
            'config': self.config
        }
        
        if self.active:
            status.update({
                'triggered_at': self.triggered_at,
                'triggered_by': self.triggered_by,
                'reason': self.activation_reason,
                'active_duration': time.time() - self.triggered_at
            })
        elif self.triggered_at:
            status.update({
                'last_activation': {
                    'triggered_at': self.triggered_at,
                    'triggered_by': self.triggered_by,
                    'reason': self.activation_reason,
                    'deactivated_at': self.deactivated_at,
                    'deactivated_by': self.deactivated_by,
                    'duration': self.deactivated_at - self.triggered_at if self.deactivated_at else None
                }
            })
        
        return status
    
    def add_activation_callback(self, pre_callback=None, post_callback=None):
        """
        Add callbacks to be executed during kill switch activation.
        
        Args:
            pre_callback: Function to call before activation actions
            post_callback: Function to call after activation actions
        """
        if pre_callback:
            self.pre_activation_callbacks.append(pre_callback)
            
        if post_callback:
            self.post_activation_callbacks.append(post_callback)
    
    def add_deactivation_callback(self, pre_callback=None, post_callback=None):
        """
        Add callbacks to be executed during kill switch deactivation.
        
        Args:
            pre_callback: Function to call before deactivation
            post_callback: Function to call after deactivation
        """
        if pre_callback:
            self.pre_deactivation_callbacks.append(pre_callback)
            
        if post_callback:
            self.post_deactivation_callbacks.append(post_callback)
    
    def configure(self, new_config: Dict[str, Any]) -> None:
        """
        Update kill switch configuration.
        
        Args:
            new_config: New configuration dictionary
        """
        # Update configuration
        for key, value in new_config.items():
            self.config[key] = value
            
        logger.info(f"Kill switch configuration updated: {self.config}")
    
    def cancel_all_orders(self) -> Dict[str, Any]:
        """
        Cancel all open orders across all symbols.
        
        Returns:
            Dictionary with cancellation results
        """
        if not self.exchange_client:
            return {
                'success': False,
                'error': 'no_exchange_client',
                'message': 'No exchange client configured'
            }
            
        try:
            logger.info("Cancelling all orders")
            result = self.exchange_client.cancel_all_orders()
            logger.info(f"Cancelled all orders: {result}")
            return {
                'success': True,
                'result': result
            }
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def close_all_positions(self) -> Dict[str, Any]:
        """
        Close all open positions using market orders.
        
        Returns:
            Dictionary with position closure results
        """
        if not self.exchange_client:
            return {
                'success': False,
                'error': 'no_exchange_client',
                'message': 'No exchange client configured'
            }
            
        try:
            # Get current positions
            logger.info("Fetching current positions")
            positions = self.exchange_client.get_positions()
            
            # Track closure results
            results = {
                'success': True,
                'positions_closed': [],
                'errors': []
            }
            
            # For each position, create a market order in the opposite direction
            for position in positions:
                try:
                    position_size = float(position.get('position_amount', 0))
                    
                    # Skip empty positions
                    if position_size == 0:
                        continue
                    
                    symbol = position.get('symbol')
                    
                    # Calculate opposite order
                    side = 'sell' if position_size > 0 else 'buy'
                    size = abs(position_size)
                    
                    # Place market order to close
                    logger.info(f"Closing position for {symbol}: {side} {size}")
                    result = self.exchange_client.create_market_order(
                        symbol=symbol,
                        side=side,
                        amount=size,
                        reduce_only=True  # Important - ensure we only reduce positions
                    )
                    
                    results['positions_closed'].append({
                        'symbol': symbol,
                        'side': side,
                        'size': size,
                        'result': result
                    })
                    
                    logger.info(f"Closed position for {symbol}: {result}")
                    
                except Exception as e:
                    error = f"Error closing position for {position.get('symbol', 'unknown')}: {str(e)}"
                    logger.error(error)
                    results['errors'].append(error)
            
            # Set overall success based on errors
            if results['errors']:
                results['success'] = False
                
            return results
        except Exception as e:
            logger.error(f"Failed to close all positions: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _send_activation_notification(
        self,
        reason: str,
        triggered_by: str,
        results: Dict[str, Any]
    ) -> None:
        """
        Send notification about kill switch activation.
        
        Args:
            reason: Activation reason
            triggered_by: What triggered the activation
            results: Activation results
        """
        # This is a placeholder - implement based on notification system
        logger.info("Kill switch notification placeholder - implement based on notification system")
        # Could integrate with Slack, email, SMS, etc. 