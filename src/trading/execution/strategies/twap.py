"""
TWAP (Time-Weighted Average Price) execution strategy implementation.

This module implements an advanced TWAP strategy with adaptive time slicing,
price tolerance bands, and catch-up logic for missed executions.
"""

import logging
import threading
import time
import math
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

from .execution.strategies.base import ExecutionStrategy, ExecutionStatus

# Configure logger
logger = logging.getLogger(__name__)


class TWAPStrategy(ExecutionStrategy):
    """
    Time-Weighted Average Price (TWAP) execution strategy.
    
    Splits a large order into smaller slices distributed over time to minimize
    market impact. Features adaptive time slicing, price tolerance bands,
    and catch-up logic.
    """
    
    def __init__(
        self,
        exchange_client: Any,
        order_manager: Any,
        params: Dict[str, Any] = None,
        callbacks: Dict[str, Any] = None
    ):
        """
        Initialize TWAP strategy.
        
        Args:
            exchange_client: Exchange client for market data and order execution
            order_manager: Order manager for tracking orders
            params: Strategy parameters
            callbacks: Callback functions for various events
        """
        # Default parameters
        default_params = {
            "time_window_minutes": 30,
            "num_slices": 10,
            "slice_randomization_percent": 5,
            "price_band_percent": 0.5,
            "catch_up_enabled": True,
            "adaptive_intervals": True,
            "participation_rate": 10,  # % of market volume
            "min_slice_interval": 30,  # seconds
            "max_volatility_threshold": 2.0,  # %
            "max_price_deviation": 1.0  # %
        }
        
        # Merge with provided params
        merged_params = {**default_params, **(params or {})}
        
        super().__init__(exchange_client, order_manager, merged_params, callbacks)
        
        # TWAP-specific tracking
        self._slice_schedule = []
        self._executed_slices = []
        self._next_slice_time = None
        self._last_slice_time = None
        self._current_slice = 0
        self._volatility_history = []
        self._volume_history = []
        self._skipped_slices = 0
        
        # For adaptive scheduling
        self._recalculate_schedule_event = threading.Event()
        
    def execute_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        **kwargs
    ) -> str:
        """
        Execute an order using TWAP strategy.
        
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
            self.metrics.total_quantity = quantity
            
            # Store execution parameters
            self._symbol = symbol
            self._side = side
            self._quantity = quantity
            self._limit_price = price
            
            # Generate slice schedule
            self._generate_slice_schedule()
            
            # Start execution thread
            self._stop_event.clear()
            self._execution_thread = threading.Thread(
                target=self._execution_loop,
                daemon=True,
                name=f"TWAP-{self.execution_id}"
            )
            self._execution_thread.start()
            
            # Update status
            self._update_status(ExecutionStatus.ACTIVE)
        
        return self.execution_id
    
    def cancel(self) -> bool:
        """
        Cancel TWAP execution.
        
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
        Update TWAP strategy parameters.
        
        Args:
            new_params: New parameters to update
        """
        with self._lock:
            # Update parameters
            self.params.update(new_params)
            
            # Signal recalculation of schedule
            self._recalculate_schedule_event.set()
            
            logger.info(f"Updated TWAP parameters: {new_params}")
    
    def _generate_slice_schedule(self) -> None:
        """Generate time and quantity schedule for TWAP slices."""
        with self._lock:
            # Get parameters
            time_window_minutes = self.params["time_window_minutes"]
            num_slices = self.params["num_slices"]
            randomization_percent = self.params["slice_randomization_percent"]
            
            # Calculate base values
            start_time = datetime.now()
            end_time = start_time + timedelta(minutes=time_window_minutes)
            base_interval_seconds = (time_window_minutes * 60) / num_slices
            base_quantity = self._quantity / num_slices
            
            # Clear old schedule
            self._slice_schedule = []
            
            # Generate new schedule
            current_time = start_time
            remaining_qty = self._quantity
            
            for i in range(num_slices):
                # Last slice uses remaining quantity
                if i == num_slices - 1:
                    slice_qty = remaining_qty
                else:
                    # Apply randomization to quantity (if enabled)
                    rand_factor = 1.0
                    if randomization_percent > 0:
                        # Random between -x% and +x%
                        rand_range = randomization_percent / 100
                        rand_factor = 1.0 + ((random.random() * 2 - 1) * rand_range)
                    
                    slice_qty = min(base_quantity * rand_factor, remaining_qty)
                    remaining_qty -= slice_qty
                
                # Apply randomization to time (if enabled)
                if i > 0 and randomization_percent > 0:
                    # Random between -x% and +x%
                    rand_range = randomization_percent / 100
                    rand_factor = 1.0 + ((random.random() * 2 - 1) * rand_range)
                    interval = max(base_interval_seconds * rand_factor, self.params["min_slice_interval"])
                else:
                    interval = base_interval_seconds
                
                if i > 0:
                    current_time += timedelta(seconds=interval)
                
                # Create slice
                slice_info = {
                    "slice_id": i,
                    "scheduled_time": current_time,
                    "quantity": slice_qty,
                    "executed": False,
                    "actual_time": None,
                    "order_id": None,
                    "status": "scheduled"
                }
                
                self._slice_schedule.append(slice_info)
            
            # Set next slice time
            if self._slice_schedule:
                self._next_slice_time = self._slice_schedule[0]["scheduled_time"]
                logger.info(f"TWAP schedule generated: {num_slices} slices over {time_window_minutes} minutes")
    
    def _execution_loop(self) -> None:
        """Main execution loop for TWAP strategy."""
        try:
            logger.info(f"Starting TWAP execution loop for {self.execution_id}")
            
            while not self._stop_event.is_set():
                # Check if we need to recalculate schedule
                if self._recalculate_schedule_event.is_set():
                    self._recalculate_schedule_event.clear()
                    self._generate_slice_schedule()
                
                # Check if execution is completed
                with self._lock:
                    if self._is_execution_complete():
                        logger.info(f"TWAP execution completed: {self.metrics.executed_quantity}/{self.metrics.total_quantity}")
                        
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
                
                # Handle catch-up logic for skipped slices
                if (self.params["catch_up_enabled"] and self._skipped_slices > 0 and 
                    (not self._next_slice_time or datetime.now() >= self._next_slice_time)):
                    self._execute_catch_up_slice()
                
                # Check if it's time for the next slice
                current_time = datetime.now()
                
                if self._next_slice_time and current_time >= self._next_slice_time:
                    try:
                        # Get current slice
                        with self._lock:
                            if self._current_slice < len(self._slice_schedule):
                                slice_info = self._slice_schedule[self._current_slice]
                                
                                # Execute slice
                                self._execute_slice(slice_info)
                                
                                # Move to next slice
                                self._current_slice += 1
                                
                                # Update next slice time
                                if self._current_slice < len(self._slice_schedule):
                                    self._next_slice_time = self._slice_schedule[self._current_slice]["scheduled_time"]
                                else:
                                    self._next_slice_time = None
                    except Exception as e:
                        logger.error(f"Error executing TWAP slice: {str(e)}")
                        
                        # Check if we should skip this slice
                        current_time = datetime.now()
                        if (self._next_slice_time and 
                            (current_time - self._next_slice_time).total_seconds() > 
                            self.params["min_slice_interval"]):
                            logger.warning(f"Skipping TWAP slice due to execution error")
                            self._skipped_slices += 1
                            
                            # Move to next slice
                            self._current_slice += 1
                            
                            # Update next slice time
                            if self._current_slice < len(self._slice_schedule):
                                self._next_slice_time = self._slice_schedule[self._current_slice]["scheduled_time"]
                            else:
                                self._next_slice_time = None
                
                # Update market data and check circuit breakers
                if self._current_slice < len(self._slice_schedule):
                    try:
                        self._update_market_data()
                        
                        # Check circuit breakers
                        market_data = {
                            "volatility": self._calculate_volatility(),
                            "volume": self._calculate_volume_profile()
                        }
                        
                        should_break, reason = self._check_circuit_breakers(market_data)
                        if should_break:
                            logger.warning(f"TWAP circuit breaker activated: {reason}")
                            
                            # Pause execution
                            self._update_status(ExecutionStatus.PAUSED)
                            
                            # Wait for manual intervention
                            while (not self._stop_event.is_set() and 
                                   self.status == ExecutionStatus.PAUSED):
                                time.sleep(1)
                    except Exception as e:
                        logger.error(f"Error updating market data: {str(e)}")
                
                # Update slice intervals if adaptive intervals enabled
                if self.params["adaptive_intervals"] and len(self._volatility_history) > 1:
                    self._adapt_slice_intervals()
                
                # Sleep for a short time
                time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error in TWAP execution loop: {str(e)}", exc_info=True)
            
            # Update status
            with self._lock:
                self.error = str(e)
                self._update_status(ExecutionStatus.ERROR)
        
        logger.info(f"TWAP execution loop ended for {self.execution_id}")
    
    def _execute_slice(self, slice_info: Dict[str, Any]) -> None:
        """
        Execute a single TWAP slice.
        
        Args:
            slice_info: Slice information dictionary
        """
        # Get slice information
        slice_id = slice_info["slice_id"]
        quantity = slice_info["quantity"]
        
        # Check if we should execute this slice (price tolerance)
        should_execute, reason = self._check_price_tolerance()
        if not should_execute:
            logger.warning(f"Skipping TWAP slice {slice_id}: {reason}")
            
            # Mark slice as skipped
            slice_info["status"] = "skipped"
            slice_info["skip_reason"] = reason
            self._skipped_slices += 1
            
            return
        
        # Place order
        try:
            logger.info(f"Executing TWAP slice {slice_id}: {self._side} {quantity} {self._symbol}")
            
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
            
            # Update slice info
            slice_info["order_id"] = order_result["orderId"]
            slice_info["actual_time"] = datetime.now()
            slice_info["status"] = "executed"
            slice_info["executed"] = True
            
            # Add to active orders
            self.active_orders[order_result["orderId"]] = order_result
            
            # Update metrics
            with self._lock:
                self.metrics.num_orders += 1
                self.metrics.order_ids.append(order_result["orderId"])
            
            # Add to executed slices
            self._executed_slices.append(slice_info)
            
            # Update last slice time
            self._last_slice_time = slice_info["actual_time"]
            
            logger.info(f"TWAP slice {slice_id} executed successfully, order ID: {order_result['orderId']}")
            
        except Exception as e:
            logger.error(f"Error executing TWAP slice {slice_id}: {str(e)}")
            
            # Mark slice as failed
            slice_info["status"] = "failed"
            slice_info["error"] = str(e)
            
            # May need to retry or adjust strategy
            raise
    
    def _execute_catch_up_slice(self) -> None:
        """Execute a catch-up slice for previously skipped slices."""
        if self._skipped_slices <= 0:
            return
        
        # Calculate catch-up quantity
        remaining_slices = len(self._slice_schedule) - self._current_slice
        if remaining_slices <= 0:
            return
        
        catch_up_quantity = (self._skipped_slices / remaining_slices) * (self._quantity / len(self._slice_schedule))
        
        # Cap at a reasonable size
        catch_up_quantity = min(catch_up_quantity, self._quantity * 0.1)
        
        # Create catch-up slice
        catch_up_slice = {
            "slice_id": f"catch_up_{self._current_slice}",
            "scheduled_time": datetime.now(),
            "quantity": catch_up_quantity,
            "executed": False,
            "actual_time": None,
            "order_id": None,
            "status": "catch_up"
        }
        
        logger.info(f"Executing TWAP catch-up slice: {catch_up_quantity} {self._symbol}")
        
        try:
            # Execute the catch-up slice
            self._execute_slice(catch_up_slice)
            
            # Reduce skipped slices counter
            self._skipped_slices -= 1
            
        except Exception as e:
            logger.error(f"Error executing catch-up slice: {str(e)}")
    
    def _check_price_tolerance(self) -> Tuple[bool, Optional[str]]:
        """
        Check if current price is within tolerance bands.
        
        Returns:
            Tuple of (should_execute, reason)
        """
        try:
            # Get current price
            ticker = self.exchange_client.get_ticker(self._symbol)
            current_price = float(ticker["lastPrice"])
            
            # Get benchmark price (if available)
            benchmark_price = None
            if self.metrics.expected_price:
                benchmark_price = self.metrics.expected_price
            elif self._limit_price:
                benchmark_price = self._limit_price
            
            # If no benchmark, use first price
            if not benchmark_price:
                self.metrics.expected_price = current_price
                return True, None
            
            # Calculate price deviation
            price_deviation = abs((current_price - benchmark_price) / benchmark_price) * 100
            
            # Check if within tolerance
            if price_deviation > self.params["price_band_percent"]:
                return False, f"Price deviation {price_deviation:.2f}% exceeds tolerance {self.params['price_band_percent']}%"
            
            return True, None
            
        except Exception as e:
            logger.error(f"Error checking price tolerance: {str(e)}")
            return False, str(e)
    
    def _update_market_data(self) -> None:
        """Update market data for volatility calculation and volume profile."""
        try:
            # Get recent trades
            trades = self.exchange_client.get_recent_trades(self._symbol, limit=100)
            
            # Get recent klines
            klines = self.exchange_client.get_klines(
                self._symbol, 
                interval="1m", 
                limit=30
            )
            
            # Calculate volatility
            if klines and len(klines) > 1:
                # Extract close prices
                close_prices = [float(k[4]) for k in klines]
                
                # Calculate returns
                returns = [
                    (close_prices[i] - close_prices[i-1]) / close_prices[i-1] * 100
                    for i in range(1, len(close_prices))
                ]
                
                # Calculate volatility (standard deviation of returns)
                if returns:
                    mean_return = sum(returns) / len(returns)
                    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
                    volatility = math.sqrt(variance)
                    
                    # Add to history
                    self._volatility_history.append({
                        "timestamp": datetime.now(),
                        "volatility": volatility
                    })
                    
                    # Keep only recent history
                    if len(self._volatility_history) > 30:
                        self._volatility_history = self._volatility_history[-30:]
            
            # Calculate volume profile
            if trades:
                # Extract volumes by minute
                volumes = {}
                for trade in trades:
                    # Extract timestamp and convert to minute
                    trade_time = datetime.fromtimestamp(trade["time"] / 1000)
                    minute_key = trade_time.replace(second=0, microsecond=0)
                    
                    # Add volume
                    if minute_key not in volumes:
                        volumes[minute_key] = 0
                    
                    volumes[minute_key] += float(trade["qty"])
                
                # Add to history
                for minute, volume in volumes.items():
                    self._volume_history.append({
                        "timestamp": minute,
                        "volume": volume
                    })
                
                # Keep only recent history
                if len(self._volume_history) > 60:
                    self._volume_history = self._volume_history[-60:]
            
        except Exception as e:
            logger.error(f"Error updating market data: {str(e)}")
    
    def _calculate_volatility(self) -> float:
        """
        Calculate current market volatility.
        
        Returns:
            Volatility as a percentage
        """
        if not self._volatility_history:
            return 0.0
        
        # Use most recent volatility
        return self._volatility_history[-1]["volatility"]
    
    def _calculate_volume_profile(self) -> Dict[str, Any]:
        """
        Calculate volume profile for VWAP components.
        
        Returns:
            Dictionary with volume profile information
        """
        if not self._volume_history:
            return {"average": 0, "current": 0, "trend": 0}
        
        # Calculate average volume
        total_volume = sum(v["volume"] for v in self._volume_history)
        avg_volume = total_volume / len(self._volume_history)
        
        # Calculate current volume (last 5 minutes)
        recent_history = self._volume_history[-5:]
        current_volume = sum(v["volume"] for v in recent_history) / len(recent_history)
        
        # Calculate trend (positive = increasing volume)
        if len(self._volume_history) > 10:
            prev_volume = sum(v["volume"] for v in self._volume_history[-10:-5]) / 5
            trend = (current_volume - prev_volume) / prev_volume if prev_volume > 0 else 0
        else:
            trend = 0
        
        return {
            "average": avg_volume,
            "current": current_volume,
            "trend": trend
        }
    
    def _adapt_slice_intervals(self) -> None:
        """Adapt slice intervals based on market volatility and volume."""
        if len(self._slice_schedule) <= self._current_slice:
            return
        
        try:
            # Calculate current volatility
            volatility = self._calculate_volatility()
            volume_profile = self._calculate_volume_profile()
            
            # Skip if not enough data
            if volatility == 0 or volume_profile["average"] == 0:
                return
            
            # Adjust intervals based on volatility
            # Higher volatility = larger intervals to avoid trading during extreme moves
            # Lower volatility = smaller intervals for more even distribution
            
            # Base volatility is the average of historical data
            base_volatility = sum(v["volatility"] for v in self._volatility_history) / len(self._volatility_history)
            
            # Volatility adjustment factor
            if base_volatility > 0:
                vol_factor = volatility / base_volatility
            else:
                vol_factor = 1.0
            
            # Volume adjustment factor
            # Higher volume = smaller intervals (more liquidity)
            # Lower volume = larger intervals (less liquidity)
            vol_ratio = volume_profile["current"] / volume_profile["average"] if volume_profile["average"] > 0 else 1.0
            
            # Combined adjustment factor (higher = larger intervals)
            adjustment_factor = vol_factor / (vol_ratio ** 0.5)
            
            # Limit adjustment factor
            adjustment_factor = max(0.5, min(2.0, adjustment_factor))
            
            # Get remaining time window
            current_time = datetime.now()
            last_scheduled_time = self._slice_schedule[-1]["scheduled_time"]
            remaining_time = (last_scheduled_time - current_time).total_seconds()
            
            # Get remaining slices
            remaining_slices = len(self._slice_schedule) - self._current_slice
            
            if remaining_slices <= 1 or remaining_time <= 0:
                return
            
            # Calculate new interval
            new_base_interval = remaining_time / remaining_slices
            
            # Apply adjustment factor
            adjusted_interval = new_base_interval * adjustment_factor
            
            # Enforce minimum interval
            adjusted_interval = max(adjusted_interval, self.params["min_slice_interval"])
            
            # Reschedule remaining slices
            next_time = max(current_time, self._next_slice_time)
            
            for i in range(self._current_slice, len(self._slice_schedule)):
                # Apply randomization
                if self.params["slice_randomization_percent"] > 0:
                    rand_range = self.params["slice_randomization_percent"] / 100
                    rand_factor = 1.0 + ((random.random() * 2 - 1) * rand_range)
                    interval = max(adjusted_interval * rand_factor, self.params["min_slice_interval"])
                else:
                    interval = adjusted_interval
                
                next_time += timedelta(seconds=interval)
                self._slice_schedule[i]["scheduled_time"] = next_time
            
            # Update next slice time
            self._next_slice_time = self._slice_schedule[self._current_slice]["scheduled_time"]
            
            logger.info(
                f"Adapted TWAP intervals: volatility={volatility:.2f}, "
                f"volume_ratio={vol_ratio:.2f}, adjustment={adjustment_factor:.2f}"
            )
            
        except Exception as e:
            logger.error(f"Error adapting slice intervals: {str(e)}")
    
    def _check_circuit_breakers(self, market_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Check if circuit breakers should be activated.
        
        Args:
            market_data: Current market data
            
        Returns:
            Tuple of (should_break, reason)
        """
        # Get volatility and max threshold
        volatility = market_data.get("volatility", 0)
        max_volatility = self.params["max_volatility_threshold"]
        
        # Check for excessive volatility
        if volatility > max_volatility:
            return True, f"Excessive volatility: {volatility:.2f}% > {max_volatility:.2f}%"
        
        # Check for price deviation
        try:
            # Get current price
            ticker = self.exchange_client.get_ticker(self._symbol)
            current_price = float(ticker["lastPrice"])
            
            # Check against expected price
            if self.metrics.expected_price:
                price_deviation = abs((current_price - self.metrics.expected_price) / self.metrics.expected_price) * 100
                max_deviation = self.params["max_price_deviation"]
                
                if price_deviation > max_deviation:
                    return True, f"Excessive price deviation: {price_deviation:.2f}% > {max_deviation:.2f}%"
        except Exception as e:
            logger.error(f"Error checking price deviation: {str(e)}")
        
        return False, None
    
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
    
    def _is_execution_complete(self) -> bool:
        """
        Check if TWAP execution is complete.
        
        Returns:
            True if execution is complete, False otherwise
        """
        with self._lock:
            # Check if all slices are executed
            if len(self._slice_schedule) > 0 and self._current_slice >= len(self._slice_schedule):
                # Check if executed quantity matches the expected total
                if self.metrics.executed_quantity >= self.metrics.total_quantity * 0.99:
                    return True
            
            return False 