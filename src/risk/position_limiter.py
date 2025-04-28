"""
Position Limiter Module

This module implements position limiting functionality for risk management.
It enforces position size limits based on various risk parameters.
"""

from datetime import datetime
import logging
from .action_logger import ActionLogger


class PositionLimiter:
    """
    Position limiter for enforcing position size limits based on risk parameters.
    
    This class provides methods to:
    - Check if a position can be entered based on risk rules
    - Calculate maximum allowed position size
    - Track existing positions and their metrics
    - Enforce various risk control limits
    """
    
    def __init__(self, max_position_size=10.0, max_positions=10, 
                 max_portfolio_exposure=20.0, max_drawdown_pct=10.0, 
                 max_daily_loss_pct=5.0, max_symbol_exposure_pct=5.0,
                 action_logger=None):
        """
        Initialize the position limiter with risk control parameters.
        
        Args:
            max_position_size (float): Maximum position size in lots
            max_positions (int): Maximum number of concurrent positions
            max_portfolio_exposure (float): Maximum portfolio exposure percentage
            max_drawdown_pct (float): Maximum drawdown percentage allowed
            max_daily_loss_pct (float): Maximum daily loss percentage allowed
            max_symbol_exposure_pct (float): Maximum exposure percentage for a single symbol
            action_logger (ActionLogger, optional): Logger for risk control actions
        """
        self.max_position_size = max_position_size
        self.max_positions = max_positions
        self.max_portfolio_exposure = max_portfolio_exposure
        self.max_drawdown_pct = max_drawdown_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_symbol_exposure_pct = max_symbol_exposure_pct
        
        # Initialize tracking variables
        self.account_equity = 10000  # Default value
        self.initial_equity = 10000  # Default value for tracking drawdown
        self.daily_high_equity = 10000  # For tracking daily losses
        self.day_start_equity = 10000  # For tracking daily losses
        self.last_equity_update = datetime.now()
        
        # Open positions tracking
        self.open_positions = {}  # {symbol: position_size}
        self.current_portfolio_exposure = 0.0
        self.symbol_exposure = {}  # {symbol: exposure_pct}
        
        # Setup logger
        if action_logger is None:
            self.action_logger = ActionLogger('position_limiter.log')
        else:
            self.action_logger = action_logger
            
        self.logger = logging.getLogger(__name__)
        
    def set_account_equity(self, equity, update_initial=False, 
                           update_daily_metrics=False):
        """
        Update account equity and related metrics.
        
        Args:
            equity (float): Current account equity
            update_initial (bool): Whether to update initial equity (for new periods)
            update_daily_metrics (bool): Whether to update daily metrics
        """
        self.account_equity = equity
        
        # Update initial equity if requested or first time
        if update_initial or self.initial_equity == 10000:
            self.initial_equity = equity
        
        # Update daily high water mark
        if equity > self.daily_high_equity:
            self.daily_high_equity = equity
            
        # Check if we need to reset daily metrics (new day)
        current_time = datetime.now()
        if (current_time.date() > self.last_equity_update.date() or update_daily_metrics):
            self.day_start_equity = equity
            self.daily_high_equity = equity
            
        self.last_equity_update = current_time
        
        # Recalculate exposure percentages based on new equity
        if self.account_equity > 0:
            self.recalculate_exposure()
            
    def recalculate_exposure(self):
        """Recalculate portfolio and symbol exposure based on current equity"""
        if self.account_equity <= 0:
            return
            
        # Recalculate individual symbol exposures
        for symbol, position_size in self.open_positions.items():
            # Simplified calculation - in real system would use actual position value
            exposure_pct = (position_size / self.account_equity) * 100
            self.symbol_exposure[symbol] = exposure_pct
            
        # Recalculate total portfolio exposure
        self.current_portfolio_exposure = sum(self.symbol_exposure.values())
    
    def register_position(self, symbol, position_size):
        """
        Register a new open position.
        
        Args:
            symbol (str): Symbol being traded
            position_size (float): Position size in lots
            
        Returns:
            bool: Whether registration was successful
        """
        # Add position to tracking
        self.open_positions[symbol] = position_size
        
        # Calculate exposure percentage
        if self.account_equity > 0:
            exposure_pct = (position_size / self.account_equity) * 100
            self.symbol_exposure[symbol] = exposure_pct
            
            # Update total portfolio exposure
            self.current_portfolio_exposure = sum(self.symbol_exposure.values())
            
        return True
    
    def close_position(self, symbol):
        """
        Register a position as closed.
        
        Args:
            symbol (str): Symbol being closed
            
        Returns:
            bool: Whether the operation was successful
        """
        if symbol in self.open_positions:
            del self.open_positions[symbol]
            if symbol in self.symbol_exposure:
                del self.symbol_exposure[symbol]
                
            # Recalculate total portfolio exposure
            self.current_portfolio_exposure = sum(self.symbol_exposure.values())
            return True
        return False
    
    def can_enter_position(self, symbol, position_size):
        """
        Check if a position can be entered based on risk controls.
        
        Args:
            symbol (str): Symbol to trade
            position_size (float): Proposed position size in lots
            
        Returns:
            bool: Whether the position can be entered
        """
        # Check maximum position size limit
        if position_size > self.max_position_size:
            self.action_logger.log_limit_violation(
                "MAX_POSITION_SIZE", 
                f"Position size {position_size} exceeds maximum allowed {self.max_position_size}",
                {"symbol": symbol, "position_size": position_size, "max_allowed": self.max_position_size}
            )
            return False
            
        # Check maximum positions limit
        if len(self.open_positions) >= self.max_positions and symbol not in self.open_positions:
            self.action_logger.log_limit_violation(
                "MAX_POSITIONS", 
                f"Maximum number of positions ({self.max_positions}) already reached",
                {"symbol": symbol, "current_positions": len(self.open_positions)}
            )
            return False
            
        # Calculate new exposure if this position is added
        new_portfolio_exposure = self.current_portfolio_exposure
        if symbol in self.symbol_exposure:
            # Adjust for existing position being replaced
            new_portfolio_exposure -= self.symbol_exposure[symbol]
            
        # Calculate new exposure percentage 
        new_exposure_pct = (position_size / self.account_equity) * 100 if self.account_equity > 0 else 100
        new_portfolio_exposure += new_exposure_pct
        
        # Check maximum portfolio exposure
        if new_portfolio_exposure > self.max_portfolio_exposure:
            self.action_logger.log_limit_violation(
                "MAX_PORTFOLIO_EXPOSURE", 
                f"Portfolio exposure {new_portfolio_exposure:.2f}% would exceed maximum {self.max_portfolio_exposure}%",
                {"symbol": symbol, "position_size": position_size, 
                 "current_exposure": self.current_portfolio_exposure,
                 "new_exposure": new_portfolio_exposure}
            )
            return False
            
        # Check symbol exposure limit
        if new_exposure_pct > self.max_symbol_exposure_pct:
            self.action_logger.log_limit_violation(
                "MAX_SYMBOL_EXPOSURE", 
                f"Symbol exposure {new_exposure_pct:.2f}% would exceed maximum {self.max_symbol_exposure_pct}%",
                {"symbol": symbol, "position_size": position_size, 
                 "exposure_pct": new_exposure_pct}
            )
            return False
            
        # Check drawdown limit
        if self.initial_equity > 0:
            current_drawdown_pct = ((self.initial_equity - self.account_equity) / self.initial_equity) * 100
            if current_drawdown_pct > self.max_drawdown_pct:
                self.action_logger.log_limit_violation(
                    "MAX_DRAWDOWN", 
                    f"Current drawdown {current_drawdown_pct:.2f}% exceeds maximum {self.max_drawdown_pct}%",
                    {"symbol": symbol, "position_size": position_size, 
                     "current_drawdown": current_drawdown_pct}
                )
                return False
                
        # Check daily loss limit
        if self.day_start_equity > 0:
            daily_loss_pct = ((self.day_start_equity - self.account_equity) / self.day_start_equity) * 100
            if daily_loss_pct > self.max_daily_loss_pct:
                self.action_logger.log_limit_violation(
                    "MAX_DAILY_LOSS", 
                    f"Daily loss {daily_loss_pct:.2f}% exceeds maximum {self.max_daily_loss_pct}%",
                    {"symbol": symbol, "position_size": position_size, 
                     "daily_loss_pct": daily_loss_pct}
                )
                return False
                
        # All checks passed
        return True
    
    def get_max_allowed_position_size(self, symbol):
        """
        Calculate the maximum allowed position size based on all risk rules.
        
        Args:
            symbol (str): Symbol to check
            
        Returns:
            float: Maximum allowed position size, or None if no position allowed
        """
        # Start with base maximum position size
        max_allowed = self.max_position_size
        
        # Check maximum positions limit
        if len(self.open_positions) >= self.max_positions and symbol not in self.open_positions:
            return 0.0
            
        # Check drawdown and daily loss limits
        if self.initial_equity > 0:
            current_drawdown_pct = ((self.initial_equity - self.account_equity) / self.initial_equity) * 100
            if current_drawdown_pct > self.max_drawdown_pct:
                return 0.0
                
        if self.day_start_equity > 0:
            daily_loss_pct = ((self.day_start_equity - self.account_equity) / self.day_start_equity) * 100
            if daily_loss_pct > self.max_daily_loss_pct:
                return 0.0
        
        # Calculate available portfolio exposure
        available_exposure = self.max_portfolio_exposure - self.current_portfolio_exposure
        if symbol in self.symbol_exposure:
            available_exposure += self.symbol_exposure[symbol]  # Add back current exposure for this symbol
            
        # Convert exposure percentage to position size
        if available_exposure <= 0:
            return 0.0
            
        exposure_limited_size = (available_exposure * self.account_equity) / 100
        max_allowed = min(max_allowed, exposure_limited_size)
        
        # Apply symbol exposure limit
        symbol_limited_size = (self.max_symbol_exposure_pct * self.account_equity) / 100
        max_allowed = min(max_allowed, symbol_limited_size)
        
        return max_allowed
    
    def get_current_exposure(self):
        """
        Get current portfolio exposure metrics.
        
        Returns:
            dict: Dictionary with current exposure metrics
        """
        return {
            "portfolio_exposure": self.current_portfolio_exposure,
            "symbol_exposure": self.symbol_exposure.copy(),
            "open_positions": len(self.open_positions),
            "position_sizes": self.open_positions.copy()
        }
        
    def get_risk_metrics(self):
        """
        Get current risk metrics.
        
        Returns:
            dict: Dictionary with current risk metrics
        """
        # Calculate current drawdown
        drawdown_pct = 0
        if self.initial_equity > 0:
            drawdown_pct = ((self.initial_equity - self.account_equity) / self.initial_equity) * 100
            
        # Calculate daily loss
        daily_loss_pct = 0
        if self.day_start_equity > 0:
            daily_loss_pct = ((self.day_start_equity - self.account_equity) / self.day_start_equity) * 100
            
        return {
            "account_equity": self.account_equity,
            "initial_equity": self.initial_equity,
            "day_start_equity": self.day_start_equity,
            "daily_high_equity": self.daily_high_equity,
            "drawdown_pct": drawdown_pct,
            "daily_loss_pct": daily_loss_pct,
            "violations": self.action_logger.get_violations()
        } 