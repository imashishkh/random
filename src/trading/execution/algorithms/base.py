"""
Base module for execution algorithms.
Defines the core interfaces for advanced order types like TWAP, VWAP, Iceberg.
"""
import abc
import uuid
import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple, Union, Callable
from datetime import datetime, timedelta

from .execution.core.base import Order, OrderType, OrderStatus, OrderSide

# Configure logger
logger = logging.getLogger(__name__)

class ExecutionAlgorithm(abc.ABC):
    """Abstract base class for execution algorithms."""
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize an execution algorithm.
        
        Args:
            name: Algorithm name
            config: Optional configuration
        """
        self.name = name
        self.config = config or {}
        self.id = str(uuid.uuid4())
        logger.info(f"Initialized execution algorithm: {name} ({self.id})")
    
    @abc.abstractmethod
    async def execute(self, order: Order, 
                     submit_order_func: Callable[[Order], Tuple[bool, Optional[str], Optional[Dict[str, Any]]]],
                     context: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Execute an order using this algorithm.
        
        Args:
            order: Parent order to execute
            submit_order_func: Function to submit child orders
            context: Optional context information
            
        Returns:
            Tuple of (success, error_message, execution_details)
        """
        pass
    
    @abc.abstractmethod
    async def cancel(self) -> bool:
        """
        Cancel the algorithm execution.
        
        Returns:
            Whether the cancellation was successful
        """
        pass
    
    @property
    @abc.abstractmethod
    def is_running(self) -> bool:
        """
        Check if the algorithm is currently running.
        
        Returns:
            Whether the algorithm is running
        """
        pass
    
    def _create_child_order(self, parent_order: Order, 
                           order_type: OrderType = OrderType.LIMIT,
                           quantity: Optional[float] = None,
                           price: Optional[float] = None) -> Order:
        """
        Create a child order from a parent order.
        
        Args:
            parent_order: Parent order
            order_type: Type of the child order
            quantity: Quantity for the child order
            price: Price for the child order
            
        Returns:
            Child order
        """
        # Use parent order's values as defaults
        quantity = quantity if quantity is not None else parent_order.quantity
        price = price if price is not None else parent_order.price
        
        child_order = Order(
            symbol=parent_order.symbol,
            order_type=order_type,
            side=parent_order.side,
            quantity=quantity,
            price=price,
            exchange=parent_order.exchange,
            strategy_id=parent_order.strategy_id,
            algo_params={"parent_order_id": parent_order.client_order_id, "algorithm": self.name}
        )
        
        return child_order

class AlgorithmManager:
    """
    Manager for execution algorithms.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the algorithm manager.
        
        Args:
            config: Optional configuration
        """
        self.algorithms: Dict[str, ExecutionAlgorithm] = {}
        self.active_executions: Dict[str, Dict[str, Any]] = {}
        self.config = config or {}
        logger.info("Initialized algorithm manager")
    
    def register_algorithm(self, algo_type: str, algorithm: ExecutionAlgorithm) -> None:
        """
        Register an algorithm with the manager.
        
        Args:
            algo_type: Algorithm type (e.g., 'twap', 'vwap', 'iceberg')
            algorithm: Algorithm instance
        """
        self.algorithms[algo_type] = algorithm
        logger.info(f"Registered algorithm: {algo_type} -> {algorithm.name}")
    
    def get_algorithm(self, algo_type: str) -> Optional[ExecutionAlgorithm]:
        """
        Get an algorithm by type.
        
        Args:
            algo_type: Algorithm type
            
        Returns:
            Algorithm instance or None if not found
        """
        return self.algorithms.get(algo_type.lower())
    
    async def execute_order(self, 
                          order: Order, 
                          submit_order_func: Callable[[Order], Tuple[bool, Optional[str], Optional[Dict[str, Any]]]],
                          context: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Execute an order using the appropriate algorithm.
        
        Args:
            order: Order to execute
            submit_order_func: Function to submit child orders
            context: Optional context information
            
        Returns:
            Tuple of (success, error_message, execution_details)
        """
        if not order.order_type.value.lower() in self.algorithms:
            return False, f"Unsupported algorithm: {order.order_type.value}", None
        
        algorithm = self.algorithms[order.order_type.value.lower()]
        
        # Start execution
        execution_id = f"{algorithm.name}_{order.client_order_id}"
        self.active_executions[execution_id] = {
            "order": order,
            "algorithm": algorithm,
            "start_time": datetime.utcnow(),
            "status": "running"
        }
        
        try:
            success, error, details = await algorithm.execute(order, submit_order_func, context)
            
            if success:
                self.active_executions[execution_id]["status"] = "completed"
                logger.info(f"Algorithm execution completed: {execution_id}")
            else:
                self.active_executions[execution_id]["status"] = "failed"
                self.active_executions[execution_id]["error"] = error
                logger.error(f"Algorithm execution failed: {execution_id} - {error}")
            
            return success, error, details
            
        except Exception as e:
            self.active_executions[execution_id]["status"] = "error"
            self.active_executions[execution_id]["error"] = str(e)
            logger.exception(f"Error in algorithm execution: {execution_id}")
            return False, f"Algorithm execution error: {str(e)}", None
    
    async def cancel_execution(self, order_id: str) -> bool:
        """
        Cancel an active algorithm execution.
        
        Args:
            order_id: Order ID of the execution to cancel
            
        Returns:
            Whether the cancellation was successful
        """
        # Find all active executions for this order
        executions_to_cancel = [
            execution_id for execution_id, execution in self.active_executions.items()
            if execution["order"].client_order_id == order_id and execution["status"] == "running"
        ]
        
        if not executions_to_cancel:
            logger.warning(f"No active executions found for order {order_id}")
            return False
        
        # Cancel all found executions
        success = True
        for execution_id in executions_to_cancel:
            execution = self.active_executions[execution_id]
            algorithm = execution["algorithm"]
            
            try:
                if await algorithm.cancel():
                    self.active_executions[execution_id]["status"] = "cancelled"
                    logger.info(f"Cancelled algorithm execution: {execution_id}")
                else:
                    self.active_executions[execution_id]["status"] = "cancel_failed"
                    logger.warning(f"Failed to cancel algorithm execution: {execution_id}")
                    success = False
            except Exception as e:
                self.active_executions[execution_id]["status"] = "cancel_error"
                self.active_executions[execution_id]["error"] = str(e)
                logger.exception(f"Error cancelling algorithm execution: {execution_id}")
                success = False
        
        return success
    
    def get_active_executions(self) -> List[Dict[str, Any]]:
        """
        Get all active algorithm executions.
        
        Returns:
            List of active executions
        """
        return [
            {
                "execution_id": execution_id,
                "order_id": execution["order"].client_order_id,
                "algorithm": execution["algorithm"].name,
                "start_time": execution["start_time"].isoformat(),
                "status": execution["status"],
                "error": execution.get("error")
            }
            for execution_id, execution in self.active_executions.items()
            if execution["status"] == "running"
        ] 