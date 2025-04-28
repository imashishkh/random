"""
Risk Enforcer Module

This module implements the RiskEnforcer class that is responsible for
executing risk control actions based on detected limit violations.
"""

import logging
from typing import List, Dict, Any, Optional

from .risk_control_action import ActionType, RiskControlAction
from .action_logger import ActionLogger


class RiskEnforcer:
    """
    Enforces risk control actions in response to risk limit violations.
    
    The RiskEnforcer is responsible for receiving risk control actions
    and executing them according to their type. It coordinates with
    the trading system to implement preventive and corrective actions.
    """
    
    def __init__(self, trading_manager=None, order_manager=None):
        """
        Initialize the risk enforcer.
        
        Args:
            trading_manager: Optional reference to the trading manager
            order_manager: Optional reference to the order manager
        """
        self.logger = logging.getLogger(__name__)
        self.action_logger = ActionLogger()
        self.trading_manager = trading_manager
        self.order_manager = order_manager
        self.is_trading_paused = False
        self.is_trading_stopped = False
        
    def enforce_action(self, action: RiskControlAction) -> bool:
        """
        Enforce a risk control action.
        
        Args:
            action: The risk control action to enforce
            
        Returns:
            bool: True if action was successfully enforced, False otherwise
        """
        self.logger.info(f"Enforcing action: {action}")
        
        # Dispatch to appropriate method based on action type
        if action.action_type == ActionType.LOG:
            return self._enforce_log(action)
        elif action.action_type == ActionType.ALERT:
            return self._enforce_alert(action)
        elif action.action_type == ActionType.REJECT_ENTRY:
            return self._enforce_reject_entry(action)
        elif action.action_type == ActionType.REDUCE_SIZE:
            return self._enforce_reduce_size(action)
        elif action.action_type == ActionType.CLOSE_POSITION:
            return self._enforce_close_position(action)
        elif action.action_type == ActionType.REDUCE_POSITION:
            return self._enforce_reduce_position(action)
        elif action.action_type == ActionType.PAUSE_TRADING:
            return self._enforce_pause_trading(action)
        elif action.action_type == ActionType.STOP_TRADING:
            return self._enforce_stop_trading(action)
        else:
            self.logger.warning(f"Unsupported action type: {action.action_type}")
            return False
    
    def enforce_actions(self, actions: List[RiskControlAction]) -> Dict[RiskControlAction, bool]:
        """
        Enforce multiple risk control actions.
        
        Args:
            actions: List of risk control actions to enforce
            
        Returns:
            Dict mapping actions to their enforcement result (True if successful)
        """
        results = {}
        for action in actions:
            results[action] = self.enforce_action(action)
        return results
    
    def _enforce_log(self, action: RiskControlAction) -> bool:
        """
        Enforce a LOG action by logging the message.
        
        Args:
            action: The LOG action to enforce
            
        Returns:
            bool: True if the action was successfully enforced
        """
        level = action.params.get('level', 'info').lower()
        details = action.params.get('details', {})
        
        if level == 'error':
            self.action_logger.log_warning(action.reason, action.symbol, details)
            self.logger.error(action.reason)
        elif level == 'warning':
            self.action_logger.log_warning(action.reason, action.symbol, details)
            self.logger.warning(action.reason)
        else:
            self.action_logger.log_info(action.reason, action.symbol, details)
            self.logger.info(action.reason)
            
        return True
    
    def _enforce_alert(self, action: RiskControlAction) -> bool:
        """
        Enforce an ALERT action by logging and potentially notifying.
        
        Args:
            action: The ALERT action to enforce
            
        Returns:
            bool: True if the action was successfully enforced
        """
        level = action.params.get('level', 'warning').lower()
        
        if level == 'error':
            self.logger.error(f"ALERT: {action.reason}")
            # Here you would integrate with notification system
            # such as email, SMS, etc.
        elif level == 'warning':
            self.logger.warning(f"ALERT: {action.reason}")
            # Less urgent notification
        else:
            self.logger.info(f"ALERT: {action.reason}")
            
        # Log the alert in the action logger
        self.action_logger.log_warning(
            f"ALERT: {action.reason}",
            action.symbol,
            {'alert_level': level}
        )
        
        return True
    
    def _enforce_reject_entry(self, action: RiskControlAction) -> bool:
        """
        Enforce a REJECT_ENTRY action.
        
        Args:
            action: The REJECT_ENTRY action to enforce
            
        Returns:
            bool: True if the action was successfully enforced
        """
        symbol = action.symbol
        reason = action.reason
        requested_size = action.params.get('requested_size')
        
        size_info = f"(size: {requested_size})" if requested_size else ""
        self.logger.warning(f"REJECTING ENTRY for {symbol} {size_info}: {reason}")
        
        # Log the rejection in the action logger
        details = {'requested_size': requested_size} if requested_size else {}
        self.action_logger.log_warning(
            f"Entry rejected: {reason}",
            symbol,
            details
        )
        
        # Here you would integrate with order manager to reject the entry
        # This is a placeholder for implementation
        if self.order_manager is not None:
            # self.order_manager.reject_entry(symbol, reason)
            pass
            
        return True
    
    def _enforce_reduce_size(self, action: RiskControlAction) -> bool:
        """
        Enforce a REDUCE_SIZE action.
        
        Args:
            action: The REDUCE_SIZE action to enforce
            
        Returns:
            bool: True if the action was successfully enforced
        """
        symbol = action.symbol
        reason = action.reason
        original_size = action.params.get('original_size')
        new_size = action.params.get('new_size')
        
        if original_size is None or new_size is None:
            self.logger.error("Cannot enforce REDUCE_SIZE without original and new size")
            return False
        
        self.logger.warning(
            f"REDUCING POSITION SIZE for {symbol} from {original_size} to {new_size}: {reason}"
        )
        
        # Log the size reduction in the action logger
        self.action_logger.log_position_adjustment(
            f"Position size reduced: {reason}",
            symbol,
            {
                'adjustment_type': 'reduce_size',
                'original_size': original_size,
                'new_size': new_size
            }
        )
        
        # Here you would integrate with order manager to adjust the size
        # This is a placeholder for implementation
        if self.order_manager is not None:
            # self.order_manager.reduce_order_size(symbol, new_size, reason)
            pass
            
        return True
    
    def _enforce_close_position(self, action: RiskControlAction) -> bool:
        """
        Enforce a CLOSE_POSITION action.
        
        Args:
            action: The CLOSE_POSITION action to enforce
            
        Returns:
            bool: True if the action was successfully enforced
        """
        symbol = action.symbol
        reason = action.reason
        position_id = action.params.get('position_id')
        
        id_info = f"(ID: {position_id})" if position_id else ""
        self.logger.warning(f"CLOSING POSITION for {symbol} {id_info}: {reason}")
        
        # Log the position closure in the action logger
        details = {'position_id': position_id} if position_id else {}
        self.action_logger.log_position_adjustment(
            f"Position closed: {reason}",
            symbol,
            {**details, 'adjustment_type': 'close_position'}
        )
        
        # Here you would integrate with trading manager to close the position
        # This is a placeholder for implementation
        if self.trading_manager is not None:
            # if position_id:
            #     self.trading_manager.close_position_by_id(position_id, reason=reason)
            # else:
            #     self.trading_manager.close_position_by_symbol(symbol, reason=reason)
            pass
            
        return True
    
    def _enforce_reduce_position(self, action: RiskControlAction) -> bool:
        """
        Enforce a REDUCE_POSITION action.
        
        Args:
            action: The REDUCE_POSITION action to enforce
            
        Returns:
            bool: True if the action was successfully enforced
        """
        symbol = action.symbol
        reason = action.reason
        current_size = action.params.get('current_size')
        target_size = action.params.get('target_size')
        position_id = action.params.get('position_id')
        
        if current_size is None or target_size is None:
            self.logger.error("Cannot enforce REDUCE_POSITION without current and target size")
            return False
        
        id_info = f"(ID: {position_id})" if position_id else ""
        self.logger.warning(
            f"REDUCING POSITION for {symbol} {id_info} from {current_size} to {target_size}: {reason}"
        )
        
        # Log the position reduction in the action logger
        details = {
            'adjustment_type': 'reduce_position',
            'current_size': current_size,
            'target_size': target_size
        }
        if position_id:
            details['position_id'] = position_id
            
        self.action_logger.log_position_adjustment(
            f"Position reduced: {reason}",
            symbol,
            details
        )
        
        # Here you would integrate with trading manager to reduce the position
        # This is a placeholder for implementation
        if self.trading_manager is not None:
            # if position_id:
            #     self.trading_manager.reduce_position_by_id(
            #         position_id, target_size=target_size, reason=reason
            #     )
            # else:
            #     self.trading_manager.reduce_position_by_symbol(
            #         symbol, target_size=target_size, reason=reason
            #     )
            pass
            
        return True
    
    def _enforce_pause_trading(self, action: RiskControlAction) -> bool:
        """
        Enforce a PAUSE_TRADING action.
        
        Args:
            action: The PAUSE_TRADING action to enforce
            
        Returns:
            bool: True if the action was successfully enforced
        """
        reason = action.reason
        duration = action.params.get('duration_minutes')
        
        duration_str = f"for {duration} minutes" if duration else "indefinitely"
        self.logger.warning(f"PAUSING TRADING {duration_str}: {reason}")
        
        # Log the trading pause in the action logger
        details = {'duration_minutes': duration} if duration else {}
        self.action_logger.log_warning(
            f"Trading paused {duration_str}: {reason}",
            None,
            {**details, 'action': 'pause_trading'}
        )
        
        # Set internal state
        self.is_trading_paused = True
        
        # Here you would integrate with trading manager to pause trading
        # This is a placeholder for implementation
        if self.trading_manager is not None:
            # self.trading_manager.pause_trading(
            #     reason=reason, duration_minutes=duration
            # )
            pass
            
        return True
    
    def _enforce_stop_trading(self, action: RiskControlAction) -> bool:
        """
        Enforce a STOP_TRADING action.
        
        Args:
            action: The STOP_TRADING action to enforce
            
        Returns:
            bool: True if the action was successfully enforced
        """
        reason = action.reason
        
        self.logger.warning(f"STOPPING TRADING: {reason}")
        
        # Log the trading stop in the action logger
        self.action_logger.log_warning(
            f"Trading stopped: {reason}",
            None,
            {'action': 'stop_trading'}
        )
        
        # Set internal state
        self.is_trading_stopped = True
        self.is_trading_paused = False  # stopped supersedes paused
        
        # Here you would integrate with trading manager to stop trading
        # This is a placeholder for implementation
        if self.trading_manager is not None:
            # self.trading_manager.stop_trading(reason=reason)
            pass
            
        return True
    
    def is_trading_allowed(self) -> bool:
        """
        Check if trading is currently allowed.
        
        Returns:
            bool: True if trading is allowed, False if paused or stopped
        """
        return not (self.is_trading_paused or self.is_trading_stopped)
    
    def resume_trading(self, reason: str = "Manual override") -> bool:
        """
        Resume trading after it was paused.
        
        Args:
            reason: Reason for resuming trading
            
        Returns:
            bool: True if trading was resumed, False if it was not paused
                  or was stopped (which cannot be resumed)
        """
        if self.is_trading_stopped:
            self.logger.warning("Cannot resume trading: trading is stopped, not paused")
            return False
            
        if not self.is_trading_paused:
            self.logger.info("Trading is already active")
            return True
            
        self.logger.info(f"Resuming trading: {reason}")
        
        # Log the trading resume in the action logger
        self.action_logger.log_info(
            f"Trading resumed: {reason}",
            None,
            {'action': 'resume_trading'}
        )
        
        # Set internal state
        self.is_trading_paused = False
        
        # Here you would integrate with trading manager to resume trading
        # This is a placeholder for implementation
        if self.trading_manager is not None:
            # self.trading_manager.resume_trading(reason=reason)
            pass
            
        return True 