"""
Risk Control Action Module

This module defines the risk control actions that can be taken in response to
risk limit violations.
"""

from enum import Enum, auto


class ActionType(Enum):
    """Enumeration of risk control action types."""
    
    # Informational actions
    LOG = auto()
    ALERT = auto()
    
    # Preventive actions
    REJECT_ENTRY = auto()
    REDUCE_SIZE = auto()
    
    # Corrective actions
    CLOSE_POSITION = auto()
    REDUCE_POSITION = auto()
    HEDGE_POSITION = auto()
    
    # System actions
    PAUSE_TRADING = auto()
    STOP_TRADING = auto()
    
    # Time-based actions
    WAIT_FOR_RESET = auto()


class RiskControlAction:
    """
    Represents a risk control action to be taken in response to a risk event.
    
    This class encapsulates all details about a risk control action, including
    the type of action, the reason for the action, and any parameters needed
    to execute the action.
    """
    
    def __init__(self, action_type, symbol=None, reason=None, params=None):
        """
        Initialize a risk control action.
        
        Args:
            action_type (ActionType): Type of action to take
            symbol (str, optional): Trading symbol this action applies to
            reason (str, optional): Reason for this action
            params (dict, optional): Additional parameters for the action
        """
        self.action_type = action_type
        self.symbol = symbol
        self.reason = reason
        self.params = params or {}
        
    def __repr__(self):
        """Return string representation of the action."""
        symbol_str = f", symbol={self.symbol}" if self.symbol else ""
        reason_str = f", reason='{self.reason}'" if self.reason else ""
        params_str = f", params={self.params}" if self.params else ""
        
        return f"RiskControlAction(action_type={self.action_type.name}{symbol_str}{reason_str}{params_str})"
    
    @classmethod
    def create_reject_entry(cls, symbol, reason, requested_size=None):
        """
        Create an action to reject a position entry.
        
        Args:
            symbol (str): Trading symbol
            reason (str): Reason for rejection
            requested_size (float, optional): Size that was requested
            
        Returns:
            RiskControlAction: Action to reject entry
        """
        params = {}
        if requested_size is not None:
            params['requested_size'] = requested_size
            
        return cls(
            action_type=ActionType.REJECT_ENTRY,
            symbol=symbol,
            reason=reason,
            params=params
        )
    
    @classmethod
    def create_reduce_size(cls, symbol, reason, original_size, new_size):
        """
        Create an action to reduce position size before entry.
        
        Args:
            symbol (str): Trading symbol
            reason (str): Reason for size reduction
            original_size (float): Original requested size
            new_size (float): New reduced size
            
        Returns:
            RiskControlAction: Action to reduce size
        """
        return cls(
            action_type=ActionType.REDUCE_SIZE,
            symbol=symbol,
            reason=reason,
            params={
                'original_size': original_size,
                'new_size': new_size
            }
        )
    
    @classmethod
    def create_close_position(cls, symbol, reason, position_id=None):
        """
        Create an action to close a position.
        
        Args:
            symbol (str): Trading symbol
            reason (str): Reason for closing position
            position_id (str, optional): ID of position to close
            
        Returns:
            RiskControlAction: Action to close position
        """
        params = {}
        if position_id is not None:
            params['position_id'] = position_id
            
        return cls(
            action_type=ActionType.CLOSE_POSITION,
            symbol=symbol,
            reason=reason,
            params=params
        )
    
    @classmethod
    def create_reduce_position(cls, symbol, reason, current_size, target_size, position_id=None):
        """
        Create an action to reduce an existing position.
        
        Args:
            symbol (str): Trading symbol
            reason (str): Reason for reducing position
            current_size (float): Current position size
            target_size (float): Target reduced size
            position_id (str, optional): ID of position to reduce
            
        Returns:
            RiskControlAction: Action to reduce position
        """
        params = {
            'current_size': current_size,
            'target_size': target_size
        }
        
        if position_id is not None:
            params['position_id'] = position_id
            
        return cls(
            action_type=ActionType.REDUCE_POSITION,
            symbol=symbol,
            reason=reason,
            params=params
        )
    
    @classmethod
    def create_pause_trading(cls, reason, duration_minutes=None):
        """
        Create an action to pause trading.
        
        Args:
            reason (str): Reason for pausing trading
            duration_minutes (int, optional): Duration in minutes to pause
            
        Returns:
            RiskControlAction: Action to pause trading
        """
        params = {}
        if duration_minutes is not None:
            params['duration_minutes'] = duration_minutes
            
        return cls(
            action_type=ActionType.PAUSE_TRADING,
            reason=reason,
            params=params
        )
    
    @classmethod
    def create_stop_trading(cls, reason):
        """
        Create an action to stop trading.
        
        Args:
            reason (str): Reason for stopping trading
            
        Returns:
            RiskControlAction: Action to stop trading
        """
        return cls(
            action_type=ActionType.STOP_TRADING,
            reason=reason
        )
    
    @classmethod
    def create_alert(cls, message, level="warning", symbol=None):
        """
        Create an alert action.
        
        Args:
            message (str): Alert message
            level (str): Alert level (info, warning, error)
            symbol (str, optional): Trading symbol related to alert
            
        Returns:
            RiskControlAction: Alert action
        """
        return cls(
            action_type=ActionType.ALERT,
            symbol=symbol,
            reason=message,
            params={'level': level}
        )
        
    @classmethod
    def create_log(cls, message, level="info", symbol=None, details=None):
        """
        Create a log action.
        
        Args:
            message (str): Log message
            level (str): Log level (info, warning, error)
            symbol (str, optional): Trading symbol related to log
            details (dict, optional): Additional details to log
            
        Returns:
            RiskControlAction: Log action
        """
        params = {'level': level}
        if details:
            params['details'] = details
            
        return cls(
            action_type=ActionType.LOG,
            symbol=symbol,
            reason=message,
            params=params
        ) 