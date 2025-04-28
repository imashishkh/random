"""
Strategy and Risk Management Integration

This module provides classes and functions to integrate the strategy engine
with the risk management system, enabling seamless position sizing and
risk limit enforcement based on trading signals.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple, Union

import pandas as pd

from .engine import StrategyEngine
from .base import Signal, SignalType
from ..risk.risk_manager import RiskManager
from ..risk.base import PositionSizingResult

logger = logging.getLogger(__name__)


class StrategyRiskIntegrator:
    """
    Integrates the strategy engine with the risk management system.
    
    This class serves as the bridge between the strategy engine and risk manager,
    processing signals from strategies and calculating appropriate position sizes
    based on risk parameters and market conditions.
    """
    
    def __init__(
        self,
        strategy_engine: StrategyEngine,
        risk_manager: RiskManager,
        default_position_sizer: str = "fixed_percent",
        default_risk_percent: float = 1.0,
        default_pip_value: float = 0.0001,
        default_stop_loss_pips: int = 30,
        default_take_profit_pips: int = 60,
        **kwargs
    ):
        """
        Initialize the strategy risk integrator.
        
        Args:
            strategy_engine: Strategy engine instance
            risk_manager: Risk manager instance
            default_position_sizer: Default position sizing algorithm
            default_risk_percent: Default risk percentage per trade
            default_pip_value: Default pip value for the instruments
            default_stop_loss_pips: Default stop loss distance in pips
            default_take_profit_pips: Default take profit distance in pips
            **kwargs: Additional parameters
        """
        self.strategy_engine = strategy_engine
        self.risk_manager = risk_manager
        self.default_position_sizer = default_position_sizer
        self.default_risk_percent = default_risk_percent
        self.default_pip_value = default_pip_value
        self.default_stop_loss_pips = default_stop_loss_pips
        self.default_take_profit_pips = default_take_profit_pips
        self.signal_history: List[Dict[str, Any]] = []
        
    def process_signals(
        self,
        signals: List[Signal],
        market_data: Dict[str, pd.DataFrame],
        position_sizer: Optional[str] = None,
        risk_percent: Optional[float] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Process signals from the strategy engine and calculate position sizes.
        
        Args:
            signals: List of signals from strategies
            market_data: Market data for each symbol
            position_sizer: Position sizing algorithm to use
            risk_percent: Risk percentage per trade
            **kwargs: Additional parameters for position sizing
            
        Returns:
            List of dictionaries containing processed signals with position sizing
        """
        processed_signals = []
        
        for signal in signals:
            # Skip non-actionable signals
            if signal.signal_type not in [SignalType.BUY, SignalType.SELL]:
                logger.debug(f"Skipping non-actionable signal: {signal}")
                continue
                
            symbol = signal.symbol
            
            # Extract market data for this symbol
            symbol_data = market_data.get(symbol)
            if symbol_data is None:
                logger.warning(f"No market data available for {symbol}, skipping position sizing")
                continue
                
            # Determine if long or short position
            is_long = signal.signal_type == SignalType.BUY
            
            # Calculate stop loss and take profit prices
            pip_value = kwargs.get('pip_value', self.default_pip_value)
            stop_loss_pips = kwargs.get('stop_loss_pips', self.default_stop_loss_pips)
            take_profit_pips = kwargs.get('take_profit_pips', self.default_take_profit_pips)
            
            stop_loss_distance = stop_loss_pips * pip_value
            take_profit_distance = take_profit_pips * pip_value
            
            if is_long:
                stop_loss = signal.price - stop_loss_distance
                take_profit = signal.price + take_profit_distance
            else:
                stop_loss = signal.price + stop_loss_distance
                take_profit = signal.price - take_profit_distance
            
            # Calculate position size using risk manager
            position_result = self.risk_manager.calculate_position_size(
                symbol=symbol,
                entry_price=signal.price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                market_data=symbol_data,
                is_long=is_long,
                sizer_type=position_sizer or self.default_position_sizer,
                sizer_params={
                    'risk_percent': risk_percent or self.default_risk_percent * signal.strength,
                    **kwargs
                }
            )
            
            # Create processed signal with position sizing information
            processed_signal = {
                'signal': signal,
                'position': position_result,
                'timestamp': signal.timestamp,
                'symbol': symbol,
                'action': signal.signal_type.value,
                'entry_price': signal.price,
                'stop_loss': position_result['stop_loss'],
                'take_profit': position_result['take_profit'],
                'position_size': position_result['size'],
                'position_value': position_result['value'],
                'risk_amount': position_result['risk_amount'],
                'risk_percent': position_result['risk_percent'],
                'metadata': {**signal.metadata, **position_result['metadata']}
            }
            
            # Add to processed signals
            processed_signals.append(processed_signal)
            
            # Add to signal history
            self.signal_history.append(processed_signal)
            
            logger.info(
                f"Processed {signal.signal_type.value} signal for {symbol} @ {signal.price:.5f} "
                f"with position size {position_result['size']:.2f} units, "
                f"risking ${position_result['risk_amount']:.2f} ({position_result['risk_percent']:.2%})"
            )
        
        return processed_signals
    
    def execute_signals(
        self,
        processed_signals: List[Dict[str, Any]],
        execute_fn: callable,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Execute processed signals using the provided execution function.
        
        Args:
            processed_signals: List of processed signals with position sizing
            execute_fn: Function to execute the signals
                The function should accept a processed signal dict and return
                execution results
            **kwargs: Additional parameters for the execution function
            
        Returns:
            List of execution results
        """
        execution_results = []
        
        for signal in processed_signals:
            # Execute the signal
            try:
                result = execute_fn(signal, **kwargs)
                
                # Register the position with the risk manager if execution was successful
                if result.get('success', False):
                    self.risk_manager.register_position(
                        symbol=signal['symbol'],
                        position_result=signal['position'],
                        asset_class=signal.get('metadata', {}).get('asset_class', 'unknown')
                    )
                
                execution_results.append(result)
                
                logger.info(
                    f"Executed {signal['action']} for {signal['symbol']} @ {signal['entry_price']:.5f}: "
                    f"{'Success' if result.get('success', False) else 'Failed'}"
                )
                
            except Exception as e:
                logger.error(f"Error executing signal for {signal['symbol']}: {e}")
                execution_results.append({
                    'success': False,
                    'error': str(e),
                    'signal': signal
                })
        
        return execution_results
    
    def analyze_and_process(
        self,
        data: Dict[str, pd.DataFrame],
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Analyze data with the strategy engine, generate signals, and process them.
        
        This is a convenience method that combines strategy signal generation
        with position sizing in one step.
        
        Args:
            data: Market data for the strategy engine
            **kwargs: Additional parameters for signal processing
            
        Returns:
            List of processed signals with position sizing
        """
        # Generate signals from all strategies
        signals_by_strategy = self.strategy_engine.generate_signals_from_all_strategies(data)
        
        # Aggregate signals
        signals = self.strategy_engine.aggregate_signals(signals_by_strategy)
        
        # Process signals
        return self.process_signals(signals, data, **kwargs)
    
    def get_risk_metrics(self) -> Dict[str, Any]:
        """
        Get current risk metrics from the risk manager.
        
        Returns:
            Dictionary containing risk metrics
        """
        return self.risk_manager.get_risk_metrics()
    
    def get_signal_history(
        self,
        symbol: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get signal history, optionally filtered by symbol and action.
        
        Args:
            symbol: Filter by symbol
            action: Filter by action type (BUY, SELL, etc.)
            limit: Maximum number of signals to return
            
        Returns:
            List of processed signals
        """
        filtered_history = self.signal_history
        
        if symbol:
            filtered_history = [s for s in filtered_history if s['symbol'] == symbol]
            
        if action:
            filtered_history = [s for s in filtered_history if s['action'] == action]
            
        # Return most recent signals first
        return sorted(filtered_history, key=lambda x: x['timestamp'], reverse=True)[:limit] 