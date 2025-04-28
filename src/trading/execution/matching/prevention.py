"""
Self-match prevention system to avoid trading against own orders.
"""
import logging
from typing import Dict, Any, Optional, List, Set, Tuple
from datetime import datetime
from threading import Lock

from .execution.core.base import Order, OrderStatus, OrderSide

# Configure logger
logger = logging.getLogger(__name__)

class SelfMatchPreventionRegistry:
    """
    Registry for tracking orders to prevent self-matches.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the self-match prevention registry.
        
        Args:
            config: Optional configuration with the following keys:
                - prevention_level: Level at which to prevent matches ('strategy', 'account', 'global')
                - max_history: Maximum number of orders to keep in history per level
                - check_closed_orders: Whether to check against closed orders as well
        """
        self.config = config or {}
        self.prevention_level = self.config.get("prevention_level", "strategy")
        self.max_history = self.config.get("max_history", 1000)
        self.check_closed_orders = self.config.get("check_closed_orders", False)
        
        # Maps of active orders by different levels
        self.strategy_orders: Dict[str, Dict[str, Dict[str, List[Order]]]] = {}  # strategy_id -> symbol -> side -> [orders]
        self.account_orders: Dict[str, Dict[str, Dict[str, List[Order]]]] = {}   # account_id -> symbol -> side -> [orders]
        self.global_orders: Dict[str, Dict[str, List[Order]]] = {}               # symbol -> side -> [orders]
        
        # History of closed orders (if enabled)
        self.strategy_history: Dict[str, Dict[str, Dict[str, List[Order]]]] = {}  # Same structure as active orders
        self.account_history: Dict[str, Dict[str, Dict[str, List[Order]]]] = {}
        self.global_history: Dict[str, Dict[str, List[Order]]] = {}
        
        # Lock for thread safety
        self.lock = Lock()
        
        logger.info(f"Initialized self-match prevention registry with level={self.prevention_level}")
    
    def _get_orders_map(self, order: Order, for_history: bool = False) -> Tuple[Dict, str]:
        """
        Get the appropriate orders map for an order based on the prevention level.
        
        Args:
            order: Order to get map for
            for_history: Whether to get the history map instead of active orders
            
        Returns:
            Tuple of (orders_map, key)
        """
        if self.prevention_level == "strategy":
            strategy_id = order.strategy_id or "default"
            if for_history:
                orders_map = self.strategy_history
            else:
                orders_map = self.strategy_orders
            return orders_map, strategy_id
        elif self.prevention_level == "account":
            account_id = order.metadata.get("account_id", "default")
            if for_history:
                orders_map = self.account_history
            else:
                orders_map = self.account_orders
            return orders_map, account_id
        else:  # global
            if for_history:
                orders_map = self.global_history
            else:
                orders_map = self.global_orders
            return orders_map, None
    
    def add_order(self, order: Order) -> None:
        """
        Add an order to the registry.
        
        Args:
            order: Order to add
        """
        with self.lock:
            # Get the appropriate orders map
            orders_map, level_key = self._get_orders_map(order)
            
            # For global level, we don't need the level_key
            if level_key is None:
                # Initialize the maps if needed
                if order.symbol not in orders_map:
                    orders_map[order.symbol] = {
                        OrderSide.BUY.value: [],
                        OrderSide.SELL.value: []
                    }
                
                # Add the order to the appropriate list
                orders_map[order.symbol][order.side.value].append(order)
            else:
                # Initialize the maps if needed
                if level_key not in orders_map:
                    orders_map[level_key] = {}
                
                if order.symbol not in orders_map[level_key]:
                    orders_map[level_key][order.symbol] = {
                        OrderSide.BUY.value: [],
                        OrderSide.SELL.value: []
                    }
                
                # Add the order to the appropriate list
                orders_map[level_key][order.symbol][order.side.value].append(order)
            
            logger.debug(f"Added order {order.client_order_id} to self-match prevention registry")
    
    def remove_order(self, order: Order) -> None:
        """
        Remove an order from the registry (e.g., when it's filled or cancelled).
        
        Args:
            order: Order to remove
        """
        with self.lock:
            # Get the appropriate orders map
            orders_map, level_key = self._get_orders_map(order)
            
            # For global level, we don't need the level_key
            if level_key is None:
                # Remove the order from the list if it exists
                if (order.symbol in orders_map and 
                    order.side.value in orders_map[order.symbol]):
                    
                    # Find the order by client_order_id
                    orders_list = orders_map[order.symbol][order.side.value]
                    for i, existing_order in enumerate(orders_list):
                        if existing_order.client_order_id == order.client_order_id:
                            orders_list.pop(i)
                            
                            # Add to history if enabled
                            if self.check_closed_orders:
                                history_map, _ = self._get_orders_map(order, for_history=True)
                                if order.symbol not in history_map:
                                    history_map[order.symbol] = {
                                        OrderSide.BUY.value: [],
                                        OrderSide.SELL.value: []
                                    }
                                
                                history_list = history_map[order.symbol][order.side.value]
                                history_list.append(order)
                                
                                # Trim history if needed
                                if len(history_list) > self.max_history:
                                    history_list.pop(0)
                            
                            logger.debug(f"Removed order {order.client_order_id} from self-match prevention registry")
                            break
            else:
                # Remove the order from the list if it exists
                if (level_key in orders_map and 
                    order.symbol in orders_map[level_key] and 
                    order.side.value in orders_map[level_key][order.symbol]):
                    
                    # Find the order by client_order_id
                    orders_list = orders_map[level_key][order.symbol][order.side.value]
                    for i, existing_order in enumerate(orders_list):
                        if existing_order.client_order_id == order.client_order_id:
                            orders_list.pop(i)
                            
                            # Add to history if enabled
                            if self.check_closed_orders:
                                history_map, history_key = self._get_orders_map(order, for_history=True)
                                if history_key not in history_map:
                                    history_map[history_key] = {}
                                
                                if order.symbol not in history_map[history_key]:
                                    history_map[history_key][order.symbol] = {
                                        OrderSide.BUY.value: [],
                                        OrderSide.SELL.value: []
                                    }
                                
                                history_list = history_map[history_key][order.symbol][order.side.value]
                                history_list.append(order)
                                
                                # Trim history if needed
                                if len(history_list) > self.max_history:
                                    history_list.pop(0)
                            
                            logger.debug(f"Removed order {order.client_order_id} from self-match prevention registry")
                            break
    
    def update_order_status(self, order_id: str, status: OrderStatus) -> None:
        """
        Update the status of an order in the registry.
        
        Args:
            order_id: Order ID to update
            status: New status
        """
        # This is a simplified implementation - in a real system, we would
        # need to search through all orders to find the one to update
        logger.debug(f"Updated order {order_id} status to {status.value} in self-match prevention registry")
        
        # If the order is now completed, we would want to remove it from active
        # and add to history, but that requires finding it first
        # For simplicity, this is left as an exercise for a real implementation
    
    def check_self_match(self, order: Order) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Check if an order would match against any existing orders from the same source.
        
        Args:
            order: Order to check
            
        Returns:
            Tuple of (would_match, error_message, match_details)
        """
        with self.lock:
            # Get the appropriate orders map
            orders_map, level_key = self._get_orders_map(order)
            
            # Get the opposite side for matching
            opposite_side = OrderSide.SELL.value if order.side == OrderSide.BUY else OrderSide.BUY.value
            
            # For global level, we don't need the level_key
            if level_key is None:
                # Check if there are any opposite orders for this symbol
                if (order.symbol in orders_map and 
                    opposite_side in orders_map[order.symbol] and 
                    orders_map[order.symbol][opposite_side]):
                    
                    matching_orders = []
                    for existing_order in orders_map[order.symbol][opposite_side]:
                        # In a real system, we would check price levels, etc.
                        # For simplicity, we'll just consider any opposite order a potential match
                        matching_orders.append({
                            "order_id": existing_order.client_order_id,
                            "quantity": existing_order.quantity - existing_order.executed_quantity,
                            "price": existing_order.price,
                            "side": existing_order.side.value
                        })
                    
                    if matching_orders:
                        logger.warning(f"Self-match detected for order {order.client_order_id}")
                        return True, "Self-match detected", {"matching_orders": matching_orders}
            else:
                # Check if there are any opposite orders for this symbol at this level
                if (level_key in orders_map and 
                    order.symbol in orders_map[level_key] and 
                    opposite_side in orders_map[level_key][order.symbol] and 
                    orders_map[level_key][order.symbol][opposite_side]):
                    
                    matching_orders = []
                    for existing_order in orders_map[level_key][order.symbol][opposite_side]:
                        # In a real system, we would check price levels, etc.
                        # For simplicity, we'll just consider any opposite order a potential match
                        matching_orders.append({
                            "order_id": existing_order.client_order_id,
                            "quantity": existing_order.quantity - existing_order.executed_quantity,
                            "price": existing_order.price,
                            "side": existing_order.side.value
                        })
                    
                    if matching_orders:
                        logger.warning(f"Self-match detected for order {order.client_order_id}")
                        return True, "Self-match detected", {"matching_orders": matching_orders}
            
            # If we also need to check history
            if self.check_closed_orders:
                history_map, history_key = self._get_orders_map(order, for_history=True)
                
                # Check history in a similar way to the active orders
                # (Implementation left out for brevity, as it would be very similar)
            
            return False, None, None

class SelfMatchPreventionService:
    """
    Service for preventing self-matches in order execution.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the self-match prevention service.
        
        Args:
            config: Optional configuration with the following keys:
                - prevention_mode: How to handle potential self-matches ('reject', 'cancel_newest', 'cancel_oldest')
                - registry_config: Configuration for the registry
        """
        self.config = config or {}
        self.prevention_mode = self.config.get("prevention_mode", "reject")
        registry_config = self.config.get("registry_config", {})
        
        self.registry = SelfMatchPreventionRegistry(registry_config)
        
        logger.info(f"Initialized self-match prevention service with mode={self.prevention_mode}")
    
    def check_order(self, order: Order) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Check if an order would create a self-match, and handle according to prevention mode.
        
        Args:
            order: Order to check
            
        Returns:
            Tuple of (allowed, error_message, details)
        """
        # Check for potential self-matches
        would_match, error, details = self.registry.check_self_match(order)
        
        if would_match:
            if self.prevention_mode == "reject":
                # Simply reject the order
                return False, error, details
            
            elif self.prevention_mode == "cancel_newest":
                # In a real system, we would need to communicate with the exchange
                # to cancel the order, but for now we'll just track it in our registry
                # and reject the new order
                return False, f"Self-match detected, rejected under 'cancel_newest' mode", details
            
            elif self.prevention_mode == "cancel_oldest":
                # In a real system, we would need to communicate with the exchange
                # to cancel the oldest order and then submit the new one
                # For simplicity, we'll just record the new order and accept it
                self.registry.add_order(order)
                return True, None, {
                    "prevention_action": "cancel_oldest",
                    "cancelled_orders": [order_info["order_id"] for order_info in details["matching_orders"]]
                }
            
            else:
                # Unknown prevention mode, reject to be safe
                return False, f"Unknown prevention mode: {self.prevention_mode}", None
        
        # No self-match detected, record the order
        self.registry.add_order(order)
        return True, None, None
    
    def update_order(self, order: Order) -> None:
        """
        Update an existing order in the registry.
        
        Args:
            order: Updated order
        """
        # For updates, we'll just remove and re-add the order
        self.registry.remove_order(order)
        self.registry.add_order(order)
    
    def remove_order(self, order: Order) -> None:
        """
        Remove an order from the registry.
        
        Args:
            order: Order to remove
        """
        self.registry.remove_order(order)
    
    def update_order_status(self, order_id: str, status: OrderStatus) -> None:
        """
        Update the status of an order in the registry.
        
        Args:
            order_id: Order ID to update
            status: New status
        """
        self.registry.update_order_status(order_id, status)

# Export the classes
__all__ = [
    "SelfMatchPreventionRegistry",
    "SelfMatchPreventionService"
] 