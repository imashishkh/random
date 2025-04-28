"""
VWAP (Volume-Weighted Average Price) execution strategy implementation.

This module implements an advanced VWAP strategy with volume prediction,
adaptive participation rates, and anomaly detection for optimal execution.
"""

import logging
import threading
import time
import math
import random
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

from .execution.strategies.base import ExecutionStrategy, ExecutionStatus

# Configure logger
logger = logging.getLogger(__name__)


class VWAPStrategy(ExecutionStrategy):
    """
    Volume-Weighted Average Price (VWAP) execution strategy.
    
    Executes orders based on predicted and real-time volume profiles to achieve
    execution prices close to the volume-weighted average price for the time period.
    """
    
    def __init__(
        self,
        exchange_client: Any,
        order_manager: Any,
        params: Dict[str, Any] = None,
        callbacks: Dict[str, Any] = None
    ):
        """
        Initialize VWAP strategy.
        
        Args:
            exchange_client: Exchange client for market data and order execution
            order_manager: Order manager for tracking orders
            params: Strategy parameters
            callbacks: Callback functions for various events
        """
        # Default parameters
        default_params = {
            "time_window_minutes": 60,
            "participation_rate": 10,  # % of market volume
            "min_participation": 5,    # % minimum participation
            "max_participation": 20,   # % maximum participation
            "volume_prediction_method": "historical",  # historical, ml, adaptive
            "anomaly_detection_enabled": True,
            "max_deviation_threshold": 3.0,  # standard deviations
            "price_tolerance_percent": 0.5,
            "max_volatility_threshold": 2.0,  # %
            "use_historical_bins": True,
            "historical_volume_days": 20,
            "num_bins": 12,  # Number of time bins for volume profile
            "bin_interval_minutes": 5,  # Minutes per bin
            "min_execution_interval_seconds": 30,  # Minimum time between executions
            "max_bin_deviation": 30  # % maximum deviation from predicted volume
        }
        
        # Merge with provided params
        merged_params = {**default_params, **(params or {})}
        
        super().__init__(exchange_client, order_manager, merged_params, callbacks)
        
        # VWAP-specific tracking
        self._volume_history = []
        self._volume_profile = {}
        self._executed_slices = []
        self._volume_predictor = None
        self._anomaly_detector = None
        self._current_bin = 0
        self._bin_volume_targets = []
        self._bin_actual_volumes = []
        self._bin_executed_quantities = []
        self._previous_bin_volumes = []
        self._volume_predictions = []
        self._next_execution_time = None
        self._market_vwap = None
        self._starting_time = None
        self._ending_time = None
        
        # Lock for thread safety
        self._vwap_lock = threading.RLock()
        
        # Initialize tracking variables
        self._symbol = None
        self._side = None
        self._quantity = 0
        self._limit_price = None
        self._filled_quantity = 0
        self._remaining_quantity = 0
        
        # Setup execution thread
        self._execution_thread = None
    
    def execute_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        **kwargs
    ) -> str:
        """
        Execute an order using VWAP strategy.
        
        Args:
            symbol: Trading pair symbol
            side: Order side (BUY or SELL)
            quantity: Order quantity
            price: Limit price (optional)
            **kwargs: Additional parameters
            
        Returns:
            Execution ID
        """
        # Log execution start
        self._log_execution_start(symbol, side, quantity, price)
        
        # Validate market conditions
        valid, error_msg = self._validate_market_conditions(symbol)
        if not valid:
            self.error = error_msg
            self._update_status(ExecutionStatus.ERROR)
            logger.error(f"Market validation failed: {error_msg}")
            return self.execution_id
        
        # Initialize execution
        with self._lock:
            # Store execution parameters
            self._symbol = symbol
            self._side = side
            self._quantity = quantity
            self._limit_price = price
            self._remaining_quantity = quantity
            
            # Set metrics
            self.metrics.total_quantity = quantity
            
            # Set execution time window
            self._starting_time = datetime.now()
            self._ending_time = self._starting_time + timedelta(
                minutes=self.params["time_window_minutes"]
            )
            
            # Generate volume profile
            self._generate_volume_profile()
            
            # Start execution thread
            self._stop_event.clear()
            self._execution_thread = threading.Thread(
                target=self._execution_loop,
                daemon=True,
                name=f"VWAP-{self.execution_id}"
            )
            self._execution_thread.start()
            
            # Update status
            self._update_status(ExecutionStatus.ACTIVE)
        
        return self.execution_id
    
    def cancel(self) -> bool:
        """
        Cancel VWAP execution.
        
        Returns:
            True if cancellation was successful, False otherwise
        """
        with self._lock:
            if self.status not in [ExecutionStatus.ACTIVE, ExecutionStatus.PAUSED]:
                logger.warning(f"Cannot cancel execution in state {self.status.value}")
                return False
            
            # Set stop event to terminate execution loop
            self._stop_event.set()
            
            # Cancel all active orders
            for order_id in list(self.active_orders.keys()):
                try:
                    self.exchange_client.cancel_order(
                        symbol=self._symbol,
                        order_id=order_id
                    )
                    logger.info(f"Cancelled order {order_id}")
                except Exception as e:
                    logger.error(f"Error cancelling order {order_id}: {str(e)}")
            
            # Update status
            self._update_status(ExecutionStatus.CANCELLED)
            
            # Set end time
            self.metrics.end_time = datetime.now()
            
            # Calculate execution time
            if self.metrics.start_time:
                self.metrics.execution_time_ms = (
                    self.metrics.end_time - self.metrics.start_time
                ).total_seconds() * 1000
            
            return True
    
    def update_parameters(self, new_params: Dict[str, Any]) -> None:
        """
        Update VWAP strategy parameters.
        
        Args:
            new_params: New parameters to update
        """
        with self._lock:
            # Update parameters
            old_params = self.params.copy()
            self.params.update(new_params)
            
            # Check if we need to regenerate volume profile
            regenerate_profile = False
            profile_params = [
                "time_window_minutes", "num_bins", "volume_prediction_method",
                "use_historical_bins", "historical_volume_days"
            ]
            
            for param in profile_params:
                if param in new_params and old_params.get(param) != new_params[param]:
                    regenerate_profile = True
                    break
            
            if regenerate_profile and self.status == ExecutionStatus.ACTIVE:
                # Recalculate volume profile
                self._generate_volume_profile()
                logger.info("Regenerated VWAP volume profile due to parameter changes")
                
            logger.info(f"Updated VWAP parameters: {new_params}")
    
    def _generate_volume_profile(self) -> None:
        """Generate volume profile for the execution time window."""
        try:
            # Calculate the number of bins
            num_bins = self.params["num_bins"]
            bin_duration_minutes = self.params["time_window_minutes"] / num_bins
            
            # Initialize bins
            self._bin_volume_targets = [0.0] * num_bins
            self._bin_actual_volumes = [0.0] * num_bins
            self._bin_executed_quantities = [0.0] * num_bins
            self._volume_predictions = [0.0] * num_bins
            
            # Get historical volume profile if enabled
            if self.params["use_historical_bins"]:
                self._load_historical_volume_profile()
            else:
                # Use uniform distribution if no historical data
                for i in range(num_bins):
                    self._bin_volume_targets[i] = 1.0 / num_bins
            
            # Calculate target quantities for each bin
            total_target_quantity = self._quantity
            for i in range(num_bins):
                bin_qty = total_target_quantity * self._bin_volume_targets[i]
                self._volume_predictions[i] = bin_qty
            
            # Log volume profile
            logger.info(f"Generated VWAP volume profile with {num_bins} bins")
            for i in range(num_bins):
                logger.debug(f"Bin {i}: {self._bin_volume_targets[i]:.2%} of volume, " +
                             f"target qty: {self._volume_predictions[i]:.4f}")
                
        except Exception as e:
            logger.error(f"Error generating volume profile: {str(e)}")
            # Use uniform distribution as fallback
            num_bins = self.params["num_bins"]
            for i in range(num_bins):
                self._bin_volume_targets[i] = 1.0 / num_bins
                self._volume_predictions[i] = self._quantity / num_bins
    
    def _load_historical_volume_profile(self) -> None:
        """Load historical volume profile for predicting future volumes."""
        try:
            # Calculate the time range to analyze
            end_time = datetime.now()
            start_time = end_time - timedelta(days=self.params["historical_volume_days"])
            
            # Get historical volume data
            historical_volumes = self._get_historical_volume_data(
                self._symbol, start_time, end_time
            )
            
            if not historical_volumes:
                logger.warning("No historical volume data available, using uniform distribution")
                # Use uniform distribution as fallback
                num_bins = self.params["num_bins"]
                for i in range(num_bins):
                    self._bin_volume_targets[i] = 1.0 / num_bins
                return
            
            # Calculate time of day profile
            num_bins = self.params["num_bins"]
            bin_volumes = [[] for _ in range(num_bins)]
            
            # Group volumes by time of day bin
            for timestamp, volume in historical_volumes:
                # Extract time of day
                time_of_day = timestamp.time()
                # Map to execution window
                execution_hours = self.params["time_window_minutes"] / 60
                start_hour = self._starting_time.hour + self._starting_time.minute / 60
                # Calculate the bin this volume belongs to
                bin_duration_hours = execution_hours / num_bins
                bin_index = int(((time_of_day.hour + time_of_day.minute / 60) - start_hour) / bin_duration_hours)
                
                # Skip if outside our execution window
                if bin_index < 0 or bin_index >= num_bins:
                    continue
                
                # Add to appropriate bin
                bin_volumes[bin_index].append(volume)
            
            # Calculate average volume for each bin
            total_volume = 0
            bin_avg_volumes = [0.0] * num_bins
            
            for i in range(num_bins):
                if bin_volumes[i]:
                    bin_avg_volumes[i] = sum(bin_volumes[i]) / len(bin_volumes[i])
                    total_volume += bin_avg_volumes[i]
            
            # Normalize to get percentage of volume
            if total_volume > 0:
                for i in range(num_bins):
                    self._bin_volume_targets[i] = bin_avg_volumes[i] / total_volume
            else:
                # Fallback to uniform distribution
                for i in range(num_bins):
                    self._bin_volume_targets[i] = 1.0 / num_bins
            
            # Store for anomaly detection
            self._previous_bin_volumes = bin_avg_volumes.copy()
            
        except Exception as e:
            logger.error(f"Error loading historical volume profile: {str(e)}")
            # Use uniform distribution as fallback
            num_bins = self.params["num_bins"]
            for i in range(num_bins):
                self._bin_volume_targets[i] = 1.0 / num_bins
    
    def _get_historical_volume_data(self, symbol: str, start_time: datetime, end_time: datetime) -> List[Tuple[datetime, float]]:
        """
        Get historical volume data for the given time range.
        
        Args:
            symbol: Trading pair symbol
            start_time: Start time for historical data
            end_time: End time for historical data
            
        Returns:
            List of (timestamp, volume) tuples
        """
        try:
            # Convert times to milliseconds since epoch
            start_ms = int(start_time.timestamp() * 1000)
            end_ms = int(end_time.timestamp() * 1000)
            
            # Get klines (candlestick data)
            klines = self.exchange_client.get_historical_klines(
                symbol=symbol,
                interval="1h",
                start_str=start_ms,
                end_str=end_ms
            )
            
            # Extract timestamps and volumes
            result = []
            for kline in klines:
                # Format: [open_time, open, high, low, close, volume, ...]
                timestamp = datetime.fromtimestamp(kline[0] / 1000)
                volume = float(kline[5])
                result.append((timestamp, volume))
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting historical volume data: {str(e)}")
            return []
    
    def _execution_loop(self) -> None:
        """Main execution loop for VWAP strategy."""
        try:
            logger.info(f"Starting VWAP execution loop for {self.execution_id}")
            
            while not self._stop_event.is_set():
                # Check if execution is completed
                with self._lock:
                    if self._is_execution_complete():
                        logger.info(f"VWAP execution completed: {self.metrics.executed_quantity}/{self.metrics.total_quantity}")
                        
                        # Update status
                        self._update_status(ExecutionStatus.COMPLETED)
                        
                        # Set end time
                        self.metrics.end_time = datetime.now()
                        
                        # Calculate execution time
                        if self.metrics.start_time:
                            self.metrics.execution_time_ms = (
                                self.metrics.end_time - self.metrics.start_time
                            ).total_seconds() * 1000
                        
                        break
                
                # Check if we're still within the execution window
                current_time = datetime.now()
                if current_time > self._ending_time:
                    logger.info("VWAP execution window has ended")
                    # Execute remaining quantity if any
                    with self._lock:
                        if self._remaining_quantity > 0:
                            logger.info(f"Executing remaining quantity: {self._remaining_quantity}")
                            self._execute_remaining()
                    break
                
                # Update current bin
                self._update_current_bin()
                
                # Update market data and volume profile
                self._update_market_data()
                
                # Check circuit breakers
                market_data = {
                    "volatility": self._calculate_volatility(),
                    "volume_deviation": self._calculate_volume_deviation(),
                    "current_price": self._get_current_price()
                }
                
                should_break, reason = self._check_circuit_breakers(market_data)
                if should_break:
                    logger.warning(f"VWAP circuit breaker activated: {reason}")
                    # Pause execution
                    self._update_status(ExecutionStatus.PAUSED)
                    # Wait for manual intervention
                    while (not self._stop_event.is_set() and 
                           self.status == ExecutionStatus.PAUSED):
                        time.sleep(1)
                
                # Check if it's time to place an order
                if self._should_place_order():
                    try:
                        # Calculate order quantity based on volume profile
                        order_quantity = self._calculate_order_quantity()
                        
                        if order_quantity > 0:
                            # Place order
                            self._place_order(order_quantity)
                            
                            # Update next execution time
                            self._next_execution_time = current_time + timedelta(
                                seconds=self.params["min_execution_interval_seconds"]
                            )
                    except Exception as e:
                        logger.error(f"Error placing VWAP order: {str(e)}")
                
                # Sleep to avoid tight loop
                time.sleep(0.5)
        
        except Exception as e:
            logger.error(f"Error in VWAP execution loop: {str(e)}", exc_info=True)
            
            # Update status
            with self._lock:
                self.error = str(e)
                self._update_status(ExecutionStatus.ERROR)
        
        logger.info(f"VWAP execution loop ended for {self.execution_id}")
    
    def _update_current_bin(self) -> None:
        """Update the current volume bin based on elapsed time."""
        current_time = datetime.now()
        elapsed_minutes = (current_time - self._starting_time).total_seconds() / 60
        total_minutes = self.params["time_window_minutes"]
        
        if elapsed_minutes >= total_minutes:
            self._current_bin = self.params["num_bins"] - 1
        else:
            self._current_bin = int((elapsed_minutes / total_minutes) * self.params["num_bins"])
    
    def _update_market_data(self) -> None:
        """Update market data for volume profile and VWAP calculation."""
        try:
            symbol = self._symbol
            
            # Get recent trades
            trades = self.exchange_client.get_recent_trades(symbol, limit=100)
            
            # Update volume and price
            current_bin = self._current_bin
            
            # Process trades
            if trades:
                # Extract volume and prices
                bin_volume = 0
                volume_price_sum = 0
                
                for trade in trades:
                    price = float(trade["price"])
                    qty = float(trade["qty"])
                    
                    bin_volume += qty
                    volume_price_sum += price * qty
                
                # Update actual volume for current bin
                self._bin_actual_volumes[current_bin] += bin_volume
                
                # Update market VWAP
                if bin_volume > 0:
                    bin_vwap = volume_price_sum / bin_volume
                    
                    if self._market_vwap is None:
                        self._market_vwap = bin_vwap
                    else:
                        # Weighted average with previous VWAP
                        total_volume = sum(self._bin_actual_volumes)
                        if total_volume > 0:
                            self._market_vwap = (
                                (self._market_vwap * (total_volume - bin_volume)) +
                                (bin_vwap * bin_volume)
                            ) / total_volume
            
            # Get current order book
            order_book = self.exchange_client.get_order_book(symbol=symbol, limit=20)
            
        except Exception as e:
            logger.error(f"Error updating market data: {str(e)}")
    
    def _calculate_volatility(self) -> float:
        """Calculate current market volatility."""
        try:
            # Get recent klines
            klines = self.exchange_client.get_klines(
                self._symbol, 
                interval="1m", 
                limit=30
            )
            
            if not klines or len(klines) < 2:
                return 0.0
            
            # Extract close prices
            close_prices = [float(k[4]) for k in klines]
            
            # Calculate returns
            returns = [
                (close_prices[i] - close_prices[i-1]) / close_prices[i-1] * 100
                for i in range(1, len(close_prices))
            ]
            
            # Calculate volatility (standard deviation of returns)
            if not returns:
                return 0.0
                
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            volatility = math.sqrt(variance)
            
            return volatility
            
        except Exception as e:
            logger.error(f"Error calculating volatility: {str(e)}")
            return 0.0
    
    def _calculate_volume_deviation(self) -> float:
        """
        Calculate the deviation of actual volume from predicted volume.
        
        Returns:
            Percentage deviation
        """
        current_bin = self._current_bin
        
        if current_bin < 0 or current_bin >= len(self._bin_volume_targets):
            return 0.0
        
        # Check if we have predictions and actual volumes
        if not self._volume_predictions or self._volume_predictions[current_bin] == 0:
            return 0.0
            
        if not self._bin_actual_volumes:
            return 0.0
        
        # Calculate predicted volume and actual volume for current bin
        predicted_volume = self._volume_predictions[current_bin]
        actual_volume = self._bin_actual_volumes[current_bin]
        
        # Calculate deviation
        if predicted_volume > 0:
            deviation = (actual_volume - predicted_volume) / predicted_volume * 100
        else:
            deviation = 0.0
        
        return deviation
    
    def _get_current_price(self) -> float:
        """Get current market price for the symbol."""
        try:
            ticker = self.exchange_client.get_ticker(self._symbol)
            return float(ticker["lastPrice"])
        except Exception as e:
            logger.error(f"Error getting current price: {str(e)}")
            return 0.0
    
    def _should_place_order(self) -> bool:
        """Determine if we should place an order now."""
        current_time = datetime.now()
        
        # Check if we need to wait for next execution time
        if self._next_execution_time and current_time < self._next_execution_time:
            return False
        
        # Check if we have remaining quantity
        if self._remaining_quantity <= 0:
            return False
        
        # Check if we're still within the execution window
        if current_time > self._ending_time:
            return False
        
        # Check if there's significant volume to participate in
        current_bin = self._current_bin
        if current_bin < len(self._bin_actual_volumes):
            current_volume = self._bin_actual_volumes[current_bin]
            if current_volume <= 0:
                return False
        
        return True
    
    def _calculate_order_quantity(self) -> float:
        """
        Calculate the appropriate order quantity based on volume profile.
        
        Returns:
            Order quantity
        """
        with self._lock:
            # Check if we have remaining quantity
            if self._remaining_quantity <= 0:
                return 0.0
            
            current_bin = self._current_bin
            if current_bin < 0 or current_bin >= len(self._bin_volume_targets):
                return 0.0
            
            # Get current bin parameters
            target_bin_percentage = self._bin_volume_targets[current_bin]
            target_bin_quantity = self._quantity * target_bin_percentage
            executed_bin_quantity = self._bin_executed_quantities[current_bin]
            remaining_bin_quantity = target_bin_quantity - executed_bin_quantity
            
            # Check if we've already filled this bin's quota
            if remaining_bin_quantity <= 0:
                return 0.0
            
            # Calculate order quantity based on participation rate
            current_market_volume = self._bin_actual_volumes[current_bin]
            participation_rate = self.params["participation_rate"] / 100.0
            
            if current_market_volume > 0:
                # Calculate quantity based on participation rate
                participation_quantity = current_market_volume * participation_rate
                
                # Adjust based on min/max participation
                min_participation = self.params["min_participation"] / 100.0
                max_participation = self.params["max_participation"] / 100.0
                
                min_quantity = current_market_volume * min_participation
                max_quantity = current_market_volume * max_participation
                
                participation_quantity = max(min_quantity, min(participation_quantity, max_quantity))
                
                # Don't exceed remaining bin quantity or total remaining quantity
                order_quantity = min(participation_quantity, remaining_bin_quantity, self._remaining_quantity)
            else:
                # No market volume data, use time-based approach
                time_progress = (datetime.now() - self._starting_time).total_seconds() / (
                    self.params["time_window_minutes"] * 60
                )
                
                # Calculate how far behind we are in execution
                expected_filled = self._quantity * time_progress
                actual_filled = self._quantity - self._remaining_quantity
                
                if expected_filled > actual_filled:
                    # We're behind, catch up
                    order_quantity = min(
                        (expected_filled - actual_filled) * 0.5,  # Catch up gradually
                        remaining_bin_quantity,
                        self._remaining_quantity
                    )
                else:
                    # We're ahead or on track, small order
                    order_quantity = min(
                        self._remaining_quantity * 0.01,  # Small percentage
                        remaining_bin_quantity,
                        self._remaining_quantity
                    )
            
            # Ensure order is not too small
            min_notional = 0.001  # Minimum order value
            current_price = self._get_current_price()
            
            if current_price > 0 and order_quantity * current_price < min_notional:
                order_quantity = max(min_notional / current_price, order_quantity)
                order_quantity = min(order_quantity, self._remaining_quantity)
            
            return order_quantity
    
    def _place_order(self, quantity: float) -> None:
        """
        Place an order for the specified quantity.
        
        Args:
            quantity: Order quantity
        """
        if quantity <= 0:
            return
        
        try:
            logger.info(f"Placing VWAP order: {self._side} {quantity} {self._symbol}")
            
            # Create order parameters
            order_params = {
                "symbol": self._symbol,
                "side": self._side,
                "quantity": quantity,
                "type": "MARKET"  # Using market orders for simplicity
            }
            
            if self._limit_price:
                order_params["type"] = "LIMIT"
                order_params["price"] = self._limit_price
                order_params["timeInForce"] = "GTC"
            
            # Execute order
            order_result = self.exchange_client.create_order(**order_params)
            
            # Update tracking
            with self._lock:
                # Add to active orders
                self.active_orders[order_result["orderId"]] = order_result
                
                # Update metrics
                self.metrics.num_orders += 1
                self.metrics.order_ids.append(order_result["orderId"])
                
                # Update remaining quantity (optimistically assume full fill for market orders)
                self._remaining_quantity -= quantity
                
                # Update bin executed quantities
                self._bin_executed_quantities[self._current_bin] += quantity
            
            logger.info(f"VWAP order placed successfully, order ID: {order_result['orderId']}")
            
        except Exception as e:
            logger.error(f"Error placing VWAP order: {str(e)}")
            raise
    
    def _execute_remaining(self) -> None:
        """Execute any remaining quantity at the end of the time window."""
        with self._lock:
            if self._remaining_quantity <= 0:
                return
            
            try:
                logger.info(f"Executing remaining VWAP quantity: {self._remaining_quantity}")
                
                # Create order parameters
                order_params = {
                    "symbol": self._symbol,
                    "side": self._side,
                    "quantity": self._remaining_quantity,
                    "type": "MARKET"  # Using market orders for simplicity
                }
                
                if self._limit_price:
                    order_params["type"] = "LIMIT"
                    order_params["price"] = self._limit_price
                    order_params["timeInForce"] = "GTC"
                
                # Execute order
                order_result = self.exchange_client.create_order(**order_params)
                
                # Update tracking
                self.active_orders[order_result["orderId"]] = order_result
                
                # Update metrics
                self.metrics.num_orders += 1
                self.metrics.order_ids.append(order_result["orderId"])
                
                # Update remaining quantity
                self._remaining_quantity = 0
                
                logger.info(f"Remaining VWAP quantity executed, order ID: {order_result['orderId']}")
                
            except Exception as e:
                logger.error(f"Error executing remaining VWAP quantity: {str(e)}")
    
    def _check_circuit_breakers(self, market_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Check if circuit breakers should be activated.
        
        Args:
            market_data: Current market data
            
        Returns:
            Tuple of (should_break, reason)
        """
        # Check for excessive volatility
        volatility = market_data.get("volatility", 0)
        max_volatility = self.params["max_volatility_threshold"]
        
        if volatility > max_volatility:
            return True, f"Excessive volatility: {volatility:.2f}% > {max_volatility:.2f}%"
        
        # Check for anomalous volume
        if self.params["anomaly_detection_enabled"]:
            volume_deviation = market_data.get("volume_deviation", 0)
            max_deviation = self.params["max_bin_deviation"]
            
            if abs(volume_deviation) > max_deviation:
                return True, f"Anomalous volume: {volume_deviation:.2f}% deviation > {max_deviation:.2f}%"
        
        # Check for price deviation
        current_price = market_data.get("current_price", 0)
        
        if current_price > 0 and self._market_vwap is not None:
            price_deviation = abs((current_price - self._market_vwap) / self._market_vwap) * 100
            max_price_deviation = self.params["price_tolerance_percent"]
            
            if price_deviation > max_price_deviation:
                return True, f"Excessive price deviation: {price_deviation:.2f}% > {max_price_deviation:.2f}%"
        
        return False, None
    
    def _is_execution_complete(self) -> bool:
        """
        Check if VWAP execution is complete.
        
        Returns:
            True if execution is complete, False otherwise
        """
        with self._lock:
            # Check if all quantity is executed
            return self._remaining_quantity <= 0 or self.metrics.executed_quantity >= self.metrics.total_quantity * 0.99
    
    def _validate_market_conditions(self, symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Validate market conditions before starting execution.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check if symbol is valid
            exchange_info = self.exchange_client.get_exchange_info()
            symbol_info = None
            
            for s in exchange_info["symbols"]:
                if s["symbol"] == symbol:
                    symbol_info = s
                    break
            
            if not symbol_info:
                return False, f"Symbol {symbol} not found"
            
            # Check if trading is enabled
            if symbol_info["status"] != "TRADING":
                return False, f"Trading is not enabled for {symbol}"
            
            # Check if there is enough liquidity
            ticker = self.exchange_client.get_ticker(symbol)
            if float(ticker["volume"]) < 1:
                return False, f"Insufficient volume for {symbol}"
            
            return True, None
            
        except Exception as e:
            logger.error(f"Error validating market conditions: {str(e)}")
            return False, str(e)
    
    def _update_metrics(self, order_update: Dict[str, Any]) -> None:
        """
        Update execution metrics based on order update.
        
        Args:
            order_update: Order update data
        """
        super()._update_metrics(order_update)
        
        with self._lock:
            if "status" in order_update and order_update["status"] == "FILLED":
                # Update fill statistics
                fill_qty = float(order_update.get("executedQty", 0))
                
                # Update remaining quantity
                self._remaining_quantity = max(0, self._remaining_quantity - fill_qty)
                
                # Calculate slippage against market VWAP
                if self._market_vwap is not None and "price" in order_update:
                    fill_price = float(order_update["price"])
                    self.metrics.calculate_slippage(self._market_vwap) 