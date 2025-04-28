"""
Implementation of advanced execution algorithms (TWAP, VWAP, Iceberg).
"""
import asyncio
import logging
import random
import numpy as np
from typing import Dict, Any, Optional, List, Tuple, Callable, Set
from datetime import datetime, timedelta
from asyncio import Task, CancelledError

from .execution.core.base import Order, OrderType, OrderStatus, OrderSide
from .execution.algorithms.base import ExecutionAlgorithm

# Configure logger
logger = logging.getLogger(__name__)

class TWAPAlgorithm(ExecutionAlgorithm):
    """
    Time-Weighted Average Price (TWAP) algorithm.
    Divides the order into equal-sized child orders executed at regular time intervals.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the TWAP algorithm.
        
        Args:
            config: Configuration with the following keys:
                - default_duration_minutes: Default duration in minutes (default: 60)
                - default_num_slices: Default number of slices (default: 10)
                - randomize_times: Whether to randomize execution times (default: True)
                - randomize_sizes: Whether to randomize slice sizes (default: True)
                - randomization_factor: Factor for randomization (default: 0.1)
        """
        super().__init__("TWAP", config)
        
        self.default_duration_minutes = self.config.get("default_duration_minutes", 60)
        self.default_num_slices = self.config.get("default_num_slices", 10)
        self.randomize_times = self.config.get("randomize_times", True)
        self.randomize_sizes = self.config.get("randomize_sizes", True)
        self.randomization_factor = self.config.get("randomization_factor", 0.1)
        
        self._running = False
        self._task: Optional[Task] = None
        self._child_orders: List[Order] = []
        self._cancel_requested = False
        
    @property
    def is_running(self) -> bool:
        """
        Check if the algorithm is currently running.
        
        Returns:
            Whether the algorithm is running
        """
        return self._running
    
    async def execute(self, order: Order, 
                     submit_order_func: Callable[[Order], Tuple[bool, Optional[str], Optional[Dict[str, Any]]]],
                     context: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Execute an order using the TWAP algorithm.
        
        Args:
            order: Parent order to execute
            submit_order_func: Function to submit child orders
            context: Optional context information
            
        Returns:
            Tuple of (success, error_message, execution_details)
        """
        if self._running:
            return False, "TWAP execution already in progress", None
        
        context = context or {}
        self._running = True
        self._cancel_requested = False
        self._child_orders = []
        
        # Get algorithm parameters from order or defaults
        params = order.algo_params or {}
        duration_minutes = params.get("duration_minutes", self.default_duration_minutes)
        num_slices = params.get("num_slices", self.default_num_slices)
        randomize_times = params.get("randomize_times", self.randomize_times)
        randomize_sizes = params.get("randomize_sizes", self.randomize_sizes)
        randomization_factor = params.get("randomization_factor", self.randomization_factor)
        
        logger.info(f"Starting TWAP execution for order {order.client_order_id}: "
                   f"duration={duration_minutes}min, slices={num_slices}")
        
        # Calculate base time interval and slice size
        time_interval = duration_minutes * 60 / num_slices  # in seconds
        base_slice_size = order.quantity / num_slices
        
        # Generate slice sizes
        if randomize_sizes:
            # Generate random factors around 1.0 with specified randomization
            factors = np.random.normal(1.0, randomization_factor, num_slices)
            # Ensure factors sum to num_slices (to preserve total quantity)
            factors = factors * (num_slices / np.sum(factors))
            slice_sizes = [base_slice_size * factor for factor in factors]
        else:
            slice_sizes = [base_slice_size] * num_slices
        
        # Adjust the last slice to ensure the total matches exactly
        total_size = sum(slice_sizes[:-1])
        slice_sizes[-1] = order.quantity - total_size
        
        # Generate execution times
        start_time = datetime.utcnow()
        execution_times = []
        
        for i in range(num_slices):
            base_time = start_time + timedelta(seconds=i * time_interval)
            
            if randomize_times and i > 0:  # Don't randomize the first slice
                # Add random time within ±randomization_factor of the interval
                random_seconds = time_interval * randomization_factor * (2 * random.random() - 1)
                execution_time = base_time + timedelta(seconds=random_seconds)
            else:
                execution_time = base_time
            
            execution_times.append(execution_time)
        
        # Sort by execution time (in case randomization changed the order)
        slices = sorted(zip(execution_times, slice_sizes))
        
        # Create a task to execute the slices
        self._task = asyncio.create_task(
            self._execute_slices(order, slices, submit_order_func, context)
        )
        
        # Return immediately, the task will run in the background
        return True, None, {
            "algorithm": "TWAP",
            "order_id": order.client_order_id,
            "num_slices": num_slices,
            "duration_minutes": duration_minutes,
            "start_time": start_time.isoformat(),
            "expected_end_time": (start_time + timedelta(minutes=duration_minutes)).isoformat()
        }
    
    async def _execute_slices(self, 
                             parent_order: Order, 
                             slices: List[Tuple[datetime, float]],
                             submit_order_func: Callable[[Order], Tuple[bool, Optional[str], Optional[Dict[str, Any]]]],
                             context: Dict[str, Any]) -> None:
        """
        Execute the TWAP slices.
        
        Args:
            parent_order: Parent order
            slices: List of (execution_time, slice_size) tuples
            submit_order_func: Function to submit child orders
            context: Context information
        """
        try:
            results = []
            for i, (execution_time, slice_size) in enumerate(slices):
                # Check if cancellation was requested
                if self._cancel_requested:
                    logger.info(f"TWAP execution cancelled for order {parent_order.client_order_id} "
                               f"after {i}/{len(slices)} slices")
                    break
                
                # Wait until execution time
                now = datetime.utcnow()
                if execution_time > now:
                    wait_seconds = (execution_time - now).total_seconds()
                    await asyncio.sleep(wait_seconds)
                
                # Check again if cancellation was requested after waiting
                if self._cancel_requested:
                    break
                
                # Create and submit child order
                child_order = self._create_child_order(
                    parent_order,
                    order_type=OrderType.LIMIT if parent_order.price is not None else OrderType.MARKET,
                    quantity=slice_size,
                    price=parent_order.price
                )
                
                logger.info(f"Executing TWAP slice {i+1}/{len(slices)} for order {parent_order.client_order_id}: "
                           f"quantity={slice_size}")
                
                success, error, details = await submit_order_func(child_order)
                self._child_orders.append(child_order)
                
                results.append({
                    "slice": i + 1,
                    "time": datetime.utcnow().isoformat(),
                    "size": slice_size,
                    "success": success,
                    "error": error,
                    "details": details
                })
                
                if not success:
                    logger.error(f"Failed to execute TWAP slice {i+1}/{len(slices)}: {error}")
            
            logger.info(f"TWAP execution completed for order {parent_order.client_order_id}")
            
        except CancelledError:
            logger.info(f"TWAP execution task cancelled for order {parent_order.client_order_id}")
        except Exception as e:
            logger.exception(f"Error in TWAP execution for order {parent_order.client_order_id}: {str(e)}")
        finally:
            self._running = False
    
    async def cancel(self) -> bool:
        """
        Cancel the algorithm execution.
        
        Returns:
            Whether the cancellation was successful
        """
        if not self._running:
            return False
        
        self._cancel_requested = True
        
        if self._task is not None:
            # Don't cancel the task, let it complete naturally
            # Just set the flag to prevent further slices
            #self._task.cancel()
            self._task = None
        
        logger.info("TWAP execution cancellation requested")
        return True

class VWAPAlgorithm(ExecutionAlgorithm):
    """
    Volume-Weighted Average Price (VWAP) algorithm.
    Divides the order into slices proportional to expected volume profile.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the VWAP algorithm.
        
        Args:
            config: Configuration with the following keys:
                - default_duration_minutes: Default duration in minutes (default: 60)
                - default_num_slices: Default number of slices (default: 10)
                - randomize_times: Whether to randomize execution times (default: True)
                - randomize_sizes: Whether to randomize slice sizes (default: True)
                - randomization_factor: Factor for randomization (default: 0.1)
                - default_volume_profile: Default volume profile if none provided
        """
        super().__init__("VWAP", config)
        
        self.default_duration_minutes = self.config.get("default_duration_minutes", 60)
        self.default_num_slices = self.config.get("default_num_slices", 10)
        self.randomize_times = self.config.get("randomize_times", True)
        self.randomize_sizes = self.config.get("randomize_sizes", True)
        self.randomization_factor = self.config.get("randomization_factor", 0.1)
        
        # Default volume profile (example: slightly higher volumes at beginning and end)
        self.default_volume_profile = self.config.get("default_volume_profile", [
            0.12, 0.11, 0.10, 0.09, 0.08, 0.08, 0.08, 0.09, 0.10, 0.15
        ])
        
        self._running = False
        self._task: Optional[Task] = None
        self._child_orders: List[Order] = []
        self._cancel_requested = False
        
    @property
    def is_running(self) -> bool:
        """
        Check if the algorithm is currently running.
        
        Returns:
            Whether the algorithm is running
        """
        return self._running
    
    async def execute(self, order: Order, 
                     submit_order_func: Callable[[Order], Tuple[bool, Optional[str], Optional[Dict[str, Any]]]],
                     context: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Execute an order using the VWAP algorithm.
        
        Args:
            order: Parent order to execute
            submit_order_func: Function to submit child orders
            context: Optional context information
            
        Returns:
            Tuple of (success, error_message, execution_details)
        """
        if self._running:
            return False, "VWAP execution already in progress", None
        
        context = context or {}
        self._running = True
        self._cancel_requested = False
        self._child_orders = []
        
        # Get algorithm parameters from order or defaults
        params = order.algo_params or {}
        duration_minutes = params.get("duration_minutes", self.default_duration_minutes)
        num_slices = params.get("num_slices", self.default_num_slices)
        randomize_times = params.get("randomize_times", self.randomize_times)
        randomize_sizes = params.get("randomize_sizes", self.randomize_sizes)
        randomization_factor = params.get("randomization_factor", self.randomization_factor)
        
        # Get volume profile from params, context, or default
        volume_profile = params.get("volume_profile") or context.get("volume_profile")
        
        if volume_profile is None:
            # Use default profile or generate equal slices
            if num_slices == len(self.default_volume_profile):
                volume_profile = self.default_volume_profile
            else:
                # Equal distribution if slice count doesn't match default profile
                volume_profile = [1.0 / num_slices] * num_slices
        
        # Normalize volume profile to ensure it sums to 1
        total_volume = sum(volume_profile)
        volume_profile = [v / total_volume for v in volume_profile]
        
        logger.info(f"Starting VWAP execution for order {order.client_order_id}: "
                   f"duration={duration_minutes}min, slices={num_slices}")
        
        # Calculate base time interval
        time_interval = duration_minutes * 60 / num_slices  # in seconds
        
        # Generate slice sizes based on volume profile
        base_slice_sizes = [order.quantity * v for v in volume_profile]
        
        if randomize_sizes:
            # Apply randomization to the slice sizes
            factors = np.random.normal(1.0, randomization_factor, num_slices)
            # Ensure factors average to 1.0
            factors = factors * (num_slices / np.sum(factors))
            slice_sizes = [size * factor for size, factor in zip(base_slice_sizes, factors)]
        else:
            slice_sizes = base_slice_sizes
        
        # Adjust the last slice to ensure the total matches exactly
        total_size = sum(slice_sizes[:-1])
        slice_sizes[-1] = order.quantity - total_size
        
        # Generate execution times
        start_time = datetime.utcnow()
        execution_times = []
        
        for i in range(num_slices):
            base_time = start_time + timedelta(seconds=i * time_interval)
            
            if randomize_times and i > 0:  # Don't randomize the first slice
                # Add random time within ±randomization_factor of the interval
                random_seconds = time_interval * randomization_factor * (2 * random.random() - 1)
                execution_time = base_time + timedelta(seconds=random_seconds)
            else:
                execution_time = base_time
            
            execution_times.append(execution_time)
        
        # Sort by execution time (in case randomization changed the order)
        slices = sorted(zip(execution_times, slice_sizes))
        
        # Create a task to execute the slices
        self._task = asyncio.create_task(
            self._execute_slices(order, slices, submit_order_func, context)
        )
        
        # Return immediately, the task will run in the background
        return True, None, {
            "algorithm": "VWAP",
            "order_id": order.client_order_id,
            "num_slices": num_slices,
            "duration_minutes": duration_minutes,
            "volume_profile": volume_profile,
            "start_time": start_time.isoformat(),
            "expected_end_time": (start_time + timedelta(minutes=duration_minutes)).isoformat()
        }
    
    async def _execute_slices(self, 
                             parent_order: Order, 
                             slices: List[Tuple[datetime, float]],
                             submit_order_func: Callable[[Order], Tuple[bool, Optional[str], Optional[Dict[str, Any]]]],
                             context: Dict[str, Any]) -> None:
        """
        Execute the VWAP slices.
        
        Args:
            parent_order: Parent order
            slices: List of (execution_time, slice_size) tuples
            submit_order_func: Function to submit child orders
            context: Context information
        """
        # Implementation very similar to TWAP
        try:
            results = []
            for i, (execution_time, slice_size) in enumerate(slices):
                # Check if cancellation was requested
                if self._cancel_requested:
                    logger.info(f"VWAP execution cancelled for order {parent_order.client_order_id} "
                               f"after {i}/{len(slices)} slices")
                    break
                
                # Wait until execution time
                now = datetime.utcnow()
                if execution_time > now:
                    wait_seconds = (execution_time - now).total_seconds()
                    await asyncio.sleep(wait_seconds)
                
                # Check again if cancellation was requested after waiting
                if self._cancel_requested:
                    break
                
                # Create and submit child order
                child_order = self._create_child_order(
                    parent_order,
                    order_type=OrderType.LIMIT if parent_order.price is not None else OrderType.MARKET,
                    quantity=slice_size,
                    price=parent_order.price
                )
                
                logger.info(f"Executing VWAP slice {i+1}/{len(slices)} for order {parent_order.client_order_id}: "
                           f"quantity={slice_size}")
                
                success, error, details = await submit_order_func(child_order)
                self._child_orders.append(child_order)
                
                results.append({
                    "slice": i + 1,
                    "time": datetime.utcnow().isoformat(),
                    "size": slice_size,
                    "success": success,
                    "error": error,
                    "details": details
                })
                
                if not success:
                    logger.error(f"Failed to execute VWAP slice {i+1}/{len(slices)}: {error}")
            
            logger.info(f"VWAP execution completed for order {parent_order.client_order_id}")
            
        except CancelledError:
            logger.info(f"VWAP execution task cancelled for order {parent_order.client_order_id}")
        except Exception as e:
            logger.exception(f"Error in VWAP execution for order {parent_order.client_order_id}: {str(e)}")
        finally:
            self._running = False
    
    async def cancel(self) -> bool:
        """
        Cancel the algorithm execution.
        
        Returns:
            Whether the cancellation was successful
        """
        if not self._running:
            return False
        
        self._cancel_requested = True
        
        if self._task is not None:
            # Just set the flag to prevent further slices
            self._task = None
        
        logger.info("VWAP execution cancellation requested")
        return True

class IcebergAlgorithm(ExecutionAlgorithm):
    """
    Iceberg algorithm.
    Displays only a small portion of the total order quantity at a time.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the Iceberg algorithm.
        
        Args:
            config: Configuration with the following keys:
                - default_display_quantity: Default display quantity (default: 10% of total)
                - randomize_display: Whether to randomize display quantities (default: True)
                - randomization_factor: Factor for randomization (default: 0.1)
                - refresh_seconds: Time to wait before refreshing (default: 5)
        """
        super().__init__("Iceberg", config)
        
        self.default_display_pct = self.config.get("default_display_pct", 0.1)  # 10% of total
        self.randomize_display = self.config.get("randomize_display", True)
        self.randomization_factor = self.config.get("randomization_factor", 0.1)
        self.refresh_seconds = self.config.get("refresh_seconds", 5)
        
        self._running = False
        self._task: Optional[Task] = None
        self._child_orders: List[Order] = []
        self._cancel_requested = False
        
    @property
    def is_running(self) -> bool:
        """
        Check if the algorithm is currently running.
        
        Returns:
            Whether the algorithm is running
        """
        return self._running
    
    async def execute(self, order: Order, 
                     submit_order_func: Callable[[Order], Tuple[bool, Optional[str], Optional[Dict[str, Any]]]],
                     context: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Execute an order using the Iceberg algorithm.
        
        Args:
            order: Parent order to execute
            submit_order_func: Function to submit child orders
            context: Optional context information
            
        Returns:
            Tuple of (success, error_message, execution_details)
        """
        if self._running:
            return False, "Iceberg execution already in progress", None
        
        # Iceberg orders require a price
        if order.price is None:
            return False, "Iceberg orders require a price", None
        
        context = context or {}
        self._running = True
        self._cancel_requested = False
        self._child_orders = []
        
        # Get algorithm parameters from order or defaults
        params = order.algo_params or {}
        display_quantity = params.get("display_quantity")
        
        if display_quantity is None:
            # Calculate default display quantity
            display_quantity = order.quantity * self.default_display_pct
        
        randomize_display = params.get("randomize_display", self.randomize_display)
        randomization_factor = params.get("randomization_factor", self.randomization_factor)
        refresh_seconds = params.get("refresh_seconds", self.refresh_seconds)
        
        logger.info(f"Starting Iceberg execution for order {order.client_order_id}: "
                   f"total={order.quantity}, display={display_quantity}")
        
        # Create a task to execute the iceberg
        self._task = asyncio.create_task(
            self._execute_iceberg(
                order, display_quantity, randomize_display, 
                randomization_factor, refresh_seconds, 
                submit_order_func, context
            )
        )
        
        # Return immediately, the task will run in the background
        return True, None, {
            "algorithm": "Iceberg",
            "order_id": order.client_order_id,
            "display_quantity": display_quantity,
            "randomize_display": randomize_display,
            "start_time": datetime.utcnow().isoformat()
        }
    
    async def _execute_iceberg(self, 
                              parent_order: Order, 
                              display_quantity: float,
                              randomize_display: bool,
                              randomization_factor: float,
                              refresh_seconds: float,
                              submit_order_func: Callable[[Order], Tuple[bool, Optional[str], Optional[Dict[str, Any]]]],
                              context: Dict[str, Any]) -> None:
        """
        Execute the Iceberg order.
        
        Args:
            parent_order: Parent order
            display_quantity: Base display quantity
            randomize_display: Whether to randomize display quantities
            randomization_factor: Factor for randomization
            refresh_seconds: Time to wait between refreshes
            submit_order_func: Function to submit child orders
            context: Context information
        """
        try:
            remaining_quantity = parent_order.quantity
            results = []
            
            while remaining_quantity > 0 and not self._cancel_requested:
                # Determine the current display quantity
                current_display = min(display_quantity, remaining_quantity)
                
                if randomize_display:
                    # Apply randomization, but ensure display quantity is within bounds
                    factor = 1.0 + randomization_factor * (2 * random.random() - 1)
                    current_display = min(
                        max(current_display * factor, current_display * 0.5),
                        min(current_display * 1.5, remaining_quantity)
                    )
                
                # Create and submit child order
                child_order = self._create_child_order(
                    parent_order,
                    order_type=OrderType.LIMIT,  # Iceberg orders are always limit orders
                    quantity=current_display,
                    price=parent_order.price
                )
                
                logger.info(f"Submitting Iceberg slice for order {parent_order.client_order_id}: "
                           f"quantity={current_display}, remaining={remaining_quantity}")
                
                success, error, details = await submit_order_func(child_order)
                self._child_orders.append(child_order)
                
                results.append({
                    "time": datetime.utcnow().isoformat(),
                    "display_quantity": current_display,
                    "remaining_quantity": remaining_quantity,
                    "success": success,
                    "error": error,
                    "details": details
                })
                
                if not success:
                    logger.error(f"Failed to submit Iceberg slice: {error}")
                    # Wait before retrying
                    await asyncio.sleep(refresh_seconds)
                    continue
                
                # Wait for the order to be filled or cancelled
                filled = False
                while not filled and not self._cancel_requested:
                    # In a real implementation, this would check the order status
                    # For now, we'll just wait and then assume it was filled
                    await asyncio.sleep(refresh_seconds)
                    
                    # TODO: Check order status and update filled status
                    # For this example, we'll just assume it was filled
                    filled = True
                
                # Update remaining quantity
                if filled:
                    remaining_quantity -= current_display
            
            logger.info(f"Iceberg execution completed for order {parent_order.client_order_id}")
            
        except CancelledError:
            logger.info(f"Iceberg execution task cancelled for order {parent_order.client_order_id}")
        except Exception as e:
            logger.exception(f"Error in Iceberg execution for order {parent_order.client_order_id}: {str(e)}")
        finally:
            self._running = False
    
    async def cancel(self) -> bool:
        """
        Cancel the algorithm execution.
        
        Returns:
            Whether the cancellation was successful
        """
        if not self._running:
            return False
        
        self._cancel_requested = True
        
        if self._task is not None:
            # Just set the flag to prevent further slices
            self._task = None
        
        logger.info("Iceberg execution cancellation requested")
        return True

# Export the algorithms
__all__ = [
    "TWAPAlgorithm",
    "VWAPAlgorithm",
    "IcebergAlgorithm"
] 