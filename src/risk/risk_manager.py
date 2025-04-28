"""
Risk management implementation for the Forex Trading platform.

This module provides the RiskManager class which manages position sizing,
risk limits, and exposure tracking across the trading system.
"""

import logging
from typing import Any, Dict, List, Optional, Union, Tuple, Type

import pandas as pd

from .base import PositionSizer, PositionSizingResult
from .position_sizers import (
    FixedAmountSizer,
    FixedPercentSizer, 
    KellyCriterionSizer, 
    VolatilityAdjustedSizer
)

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Central risk management system for the trading platform.
    
    The RiskManager handles all aspects of risk, including:
    - Position sizing using various algorithms
    - Portfolio-wide risk limits
    - Exposure tracking by asset and asset class
    - Risk metrics calculation
    - Position validation
    """
    
    # Available position sizers
    POSITION_SIZERS = {
        "fixed_amount": FixedAmountSizer,
        "fixed_percent": FixedPercentSizer,
        "kelly_criterion": KellyCriterionSizer,
        "volatility_adjusted": VolatilityAdjustedSizer,
    }
    
    def __init__(self, 
                 account_equity: float,
                 default_sizer: str = "fixed_percent",
                 default_sizer_params: Optional[Dict[str, Any]] = None,
                 max_portfolio_risk_percent: float = 5.0,
                 max_asset_risk_percent: float = 2.0,
                 max_correlated_risk_percent: float = 4.0,
                 max_leverage: float = 10.0,
                 **kwargs):
        """
        Initialize the RiskManager.
        
        Args:
            account_equity: Current account equity
            default_sizer: Default position sizing algorithm
            default_sizer_params: Parameters for the default sizer
            max_portfolio_risk_percent: Maximum risk percentage for entire portfolio
            max_asset_risk_percent: Maximum risk percentage for a single asset
            max_correlated_risk_percent: Maximum risk percentage for correlated assets
            max_leverage: Maximum leverage allowed
            **kwargs: Additional parameters
        """
        self.account_equity = account_equity
        self.max_portfolio_risk_percent = max_portfolio_risk_percent
        self.max_asset_risk_percent = max_asset_risk_percent
        self.max_correlated_risk_percent = max_correlated_risk_percent
        self.max_leverage = max_leverage
        
        # Initialize default position sizer
        default_sizer_params = default_sizer_params or {}
        self._initialize_position_sizer(default_sizer, default_sizer_params)
        
        # Track current portfolio risk
        self.current_positions: Dict[str, PositionSizingResult] = {}
        self.current_portfolio_risk_percent: float = 0.0
        self.current_asset_risk: Dict[str, float] = {}
        self.current_asset_class_risk: Dict[str, float] = {}
        
    def _initialize_position_sizer(self, 
                                  sizer_type: str, 
                                  sizer_params: Dict[str, Any]) -> None:
        """
        Initialize the position sizer.
        
        Args:
            sizer_type: Type of position sizer to use
            sizer_params: Parameters for the position sizer
        """
        if sizer_type not in self.POSITION_SIZERS:
            logger.warning(f"Unknown position sizer '{sizer_type}'. Using fixed_percent.")
            sizer_type = "fixed_percent"
            
        sizer_class = self.POSITION_SIZERS[sizer_type]
        self.default_sizer = sizer_class(**sizer_params)
        self.default_sizer_type = sizer_type
        self.default_sizer_params = sizer_params.copy()
        
    def create_position_sizer(self, 
                            sizer_type: str, 
                            sizer_params: Optional[Dict[str, Any]] = None) -> PositionSizer:
        """
        Create a new position sizer instance.
        
        Args:
            sizer_type: Type of position sizer to create
            sizer_params: Parameters for the position sizer
            
        Returns:
            PositionSizer instance
        """
        if sizer_type not in self.POSITION_SIZERS:
            logger.warning(f"Unknown position sizer '{sizer_type}'. Using fixed_percent.")
            sizer_type = "fixed_percent"
            
        sizer_params = sizer_params or {}
        sizer_class = self.POSITION_SIZERS[sizer_type]
        return sizer_class(**sizer_params)
    
    def calculate_position_size(self,
                              symbol: str,
                              entry_price: float,
                              stop_loss: Optional[float] = None,
                              take_profit: Optional[float] = None,
                              market_data: Optional[pd.DataFrame] = None,
                              sizer_type: Optional[str] = None,
                              sizer_params: Optional[Dict[str, Any]] = None,
                              is_long: bool = True,
                              force_sizer_creation: bool = False,
                              **kwargs) -> PositionSizingResult:
        """
        Calculate position size for a trade.
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price of the position
            stop_loss: Stop loss price
            take_profit: Take profit price
            market_data: Historical market data
            sizer_type: Type of position sizer to use (uses default if None)
            sizer_params: Parameters for the position sizer
            is_long: Whether the position is long or short
            force_sizer_creation: Whether to create a new sizer instance even if type matches default
            **kwargs: Additional parameters for the position sizer
            
        Returns:
            PositionSizingResult with calculated position details
        """
        # Select the position sizer
        sizer = self.default_sizer
        
        # Create a new sizer if requested
        if sizer_type is not None and (sizer_type != self.default_sizer_type or force_sizer_creation):
            sizer = self.create_position_sizer(sizer_type, sizer_params)
        # Update default sizer params if provided but not creating new sizer
        elif sizer_params:
            sizer.update_parameters(**sizer_params)
        
        # Adjust stop loss and take profit for short positions
        if not is_long and stop_loss is not None:
            # For short positions, the stop should be above entry
            if stop_loss < entry_price:
                stop_loss = entry_price + (entry_price - stop_loss)
                
            # For short positions, the take profit should be below entry
            if take_profit is not None and take_profit > entry_price:
                take_profit = entry_price - (take_profit - entry_price)
        
        # Calculate the position size
        position_result = sizer.calculate_position_size(
            equity=self.account_equity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            market_data=market_data,
            **kwargs
        )
        
        # Add symbol and position direction to metadata
        position_result["metadata"]["symbol"] = symbol
        position_result["metadata"]["is_long"] = is_long
        
        # Validate the position against risk limits
        position_result = self.validate_position(position_result, symbol, **kwargs)
        
        return position_result
    
    def validate_position(self,
                        position_result: PositionSizingResult,
                        symbol: str,
                        asset_class: Optional[str] = None,
                        correlated_symbols: Optional[List[str]] = None,
                        **kwargs) -> PositionSizingResult:
        """
        Validate a position against risk limits.
        
        Args:
            position_result: Position sizing result to validate
            symbol: Trading symbol
            asset_class: Asset class (forex, crypto, etc.)
            correlated_symbols: List of symbols correlated with this one
            **kwargs: Additional parameters
            
        Returns:
            Validated and possibly adjusted position sizing result
        """
        # First, apply individual position validation from the sizer
        position_result = self.default_sizer.validate_position(
            position_result, 
            max_risk_percent=self.max_asset_risk_percent,
            **kwargs
        )
        
        # Check portfolio-wide risk limits
        total_risk_percent = self.current_portfolio_risk_percent
        new_risk_percent = position_result["risk_percent"]
        
        # Skip if risk percent is tiny or zero - likely means no stop loss provided
        if new_risk_percent < 0.01:
            return position_result
        
        # If the symbol already has a position, subtract its risk
        if symbol in self.current_positions:
            total_risk_percent -= self.current_positions[symbol]["risk_percent"]
            
        # Calculate projected total risk
        projected_risk = total_risk_percent + new_risk_percent
        
        # Adjust if over max portfolio risk
        if projected_risk > self.max_portfolio_risk_percent:
            # Calculate how much risk budget remains
            risk_budget = max(0, self.max_portfolio_risk_percent - total_risk_percent)
            
            if risk_budget <= 0:
                logger.warning(f"No risk budget available. Position for {symbol} rejected.")
                position_result["size"] = 0
                position_result["value"] = 0
                position_result["risk_amount"] = 0
                position_result["risk_percent"] = 0
                position_result["metadata"]["adjusted"] = True
                position_result["metadata"]["adjustment_reason"] = "no_risk_budget"
                return position_result
            
            # Adjust position size to fit within risk budget
            adjustment_factor = risk_budget / new_risk_percent
            position_result["size"] *= adjustment_factor
            position_result["value"] *= adjustment_factor
            position_result["risk_amount"] *= adjustment_factor
            position_result["risk_percent"] = risk_budget
            position_result["metadata"]["adjusted"] = True
            position_result["metadata"]["adjustment_reason"] = "portfolio_risk_limit"
            
        return position_result
    
    def register_position(self, 
                         symbol: str, 
                         position_result: PositionSizingResult,
                         asset_class: Optional[str] = None) -> bool:
        """
        Register a new position in the risk manager.
        
        Args:
            symbol: Trading symbol
            position_result: Position sizing result
            asset_class: Asset class (forex, crypto, etc.)
            
        Returns:
            True if the position was registered successfully
        """
        # Store the position
        self.current_positions[symbol] = position_result
        
        # Update risk metrics
        risk_percent = position_result["risk_percent"]
        self.current_portfolio_risk_percent += risk_percent
        
        # Update asset risk
        if symbol not in self.current_asset_risk:
            self.current_asset_risk[symbol] = 0
        self.current_asset_risk[symbol] += risk_percent
        
        # Update asset class risk
        if asset_class:
            if asset_class not in self.current_asset_class_risk:
                self.current_asset_class_risk[asset_class] = 0
            self.current_asset_class_risk[asset_class] += risk_percent
            
        logger.info(f"Position registered: {symbol}, Size: {position_result['size']:.4f}, "
                    f"Risk: {risk_percent:.2f}%, Portfolio risk: {self.current_portfolio_risk_percent:.2f}%")
        
        return True
    
    def close_position(self, 
                      symbol: str,
                      partial_percent: Optional[float] = None) -> bool:
        """
        Close or partially close a position.
        
        Args:
            symbol: Trading symbol
            partial_percent: Percentage to close (0-100), None for full close
            
        Returns:
            True if the position was closed successfully
        """
        if symbol not in self.current_positions:
            logger.warning(f"Cannot close position for {symbol}: position not found")
            return False
        
        position = self.current_positions[symbol]
        risk_percent = position["risk_percent"]
        asset_class = position["metadata"].get("asset_class")
        
        # Handle partial close
        if partial_percent is not None and 0 < partial_percent < 100:
            close_factor = partial_percent / 100.0
            remaining_factor = 1.0 - close_factor
            
            # Update position size and risk
            position["size"] *= remaining_factor
            position["value"] *= remaining_factor
            position["risk_amount"] *= remaining_factor
            position["risk_percent"] *= remaining_factor
            
            # Update risk metrics
            risk_reduction = risk_percent * close_factor
            self.current_portfolio_risk_percent -= risk_reduction
            self.current_asset_risk[symbol] -= risk_reduction
            
            if asset_class and asset_class in self.current_asset_class_risk:
                self.current_asset_class_risk[asset_class] -= risk_reduction
                
            logger.info(f"Position partially closed: {symbol}, {partial_percent:.1f}%, "
                        f"Remaining size: {position['size']:.4f}, "
                        f"Remaining risk: {position['risk_percent']:.2f}%")
        else:
            # Full close
            # Update risk metrics
            self.current_portfolio_risk_percent -= risk_percent
            self.current_asset_risk[symbol] -= risk_percent
            
            if asset_class and asset_class in self.current_asset_class_risk:
                self.current_asset_class_risk[asset_class] -= risk_percent
                
            # Remove the position
            del self.current_positions[symbol]
            
            logger.info(f"Position closed: {symbol}, "
                        f"Portfolio risk: {self.current_portfolio_risk_percent:.2f}%")
            
        return True
    
    def update_account_equity(self, new_equity: float) -> None:
        """
        Update the account equity value.
        
        This should be called regularly to ensure position sizing is based
        on current account value.
        
        Args:
            new_equity: New account equity value
        """
        old_equity = self.account_equity
        self.account_equity = new_equity
        
        # Log significant changes
        if abs(new_equity - old_equity) / old_equity > 0.01:  # 1% change
            logger.info(f"Account equity updated: {old_equity:.2f} -> {new_equity:.2f} "
                        f"({(new_equity - old_equity) / old_equity * 100:.2f}%)")
            
    def get_risk_metrics(self) -> Dict[str, Any]:
        """
        Get current risk metrics.
        
        Returns:
            Dictionary of risk metrics
        """
        return {
            "account_equity": self.account_equity,
            "portfolio_risk_percent": self.current_portfolio_risk_percent,
            "max_portfolio_risk_percent": self.max_portfolio_risk_percent,
            "risk_utilization": self.current_portfolio_risk_percent / self.max_portfolio_risk_percent if self.max_portfolio_risk_percent > 0 else 0,
            "position_count": len(self.current_positions),
            "asset_risk": self.current_asset_risk,
            "asset_class_risk": self.current_asset_class_risk,
            "positions": self.current_positions
        }
    
    def set_default_sizer(self, 
                         sizer_type: str, 
                         sizer_params: Optional[Dict[str, Any]] = None) -> bool:
        """
        Set the default position sizer.
        
        Args:
            sizer_type: Type of position sizer to use
            sizer_params: Parameters for the position sizer
            
        Returns:
            True if successful
        """
        sizer_params = sizer_params or {}
        try:
            self._initialize_position_sizer(sizer_type, sizer_params)
            logger.info(f"Default position sizer changed to: {sizer_type}")
            return True
        except Exception as e:
            logger.error(f"Failed to set default sizer: {e}")
            return False
            
    def set_risk_limits(self,
                       max_portfolio_risk_percent: Optional[float] = None,
                       max_asset_risk_percent: Optional[float] = None,
                       max_correlated_risk_percent: Optional[float] = None,
                       max_leverage: Optional[float] = None) -> None:
        """
        Update risk limits.
        
        Args:
            max_portfolio_risk_percent: Maximum risk percentage for entire portfolio
            max_asset_risk_percent: Maximum risk percentage for a single asset
            max_correlated_risk_percent: Maximum risk percentage for correlated assets
            max_leverage: Maximum leverage allowed
        """
        if max_portfolio_risk_percent is not None:
            self.max_portfolio_risk_percent = max_portfolio_risk_percent
            
        if max_asset_risk_percent is not None:
            self.max_asset_risk_percent = max_asset_risk_percent
            
        if max_correlated_risk_percent is not None:
            self.max_correlated_risk_percent = max_correlated_risk_percent
            
        if max_leverage is not None:
            self.max_leverage = max_leverage
            
        logger.info(f"Risk limits updated: Portfolio: {self.max_portfolio_risk_percent}%, "
                    f"Asset: {self.max_asset_risk_percent}%, "
                    f"Correlated: {self.max_correlated_risk_percent}%, "
                    f"Max Leverage: {self.max_leverage}x") 