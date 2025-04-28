import time
import logging
import threading
from typing import Dict, List, Optional, Set
import random

from .models import Position, ExitOrder, MarketData, OrderType, OrderStatus
from .strategies.base import ExitStrategy
from .config import ExitManagerConfig, GlobalRiskParameters, StrategyExitConfig
from .factory import ExitStrategyFactory


logger = logging.getLogger(__name__)


class ExitOrderMonitor:
    """Service for monitoring and managing exit orders (stop-loss and take-profit)"""
    
    def __init__(self, exchange_client, market_data_service, position_service, 
                 config: ExitManagerConfig = None):
        """
        Initialize the monitor service
        
        Args:
            exchange_client: Client for placing/canceling orders
            market_data_service: Service for retrieving market data
            position_service: Service for tracking positions
            config: Configuration for the exit manager
        """
        self.exchange_client = exchange_client
        self.market_data_service = market_data_service
        self.position_service = position_service
        self.config = config or ExitManagerConfig()
        
        self.running = False
        self.monitor_thread = None
        
        # Thread lock for concurrent access
        self._lock = threading.RLock()
        
        # Cache of active exit strategies for positions
        self.position_strategies: Dict[str, Dict] = {}  # position_id -> {sl_strategy, tp_strategy}
        
        # Circuit breaker state
        self._failure_count = 0
        self._circuit_open = False
        self._circuit_open_time = 0
        
    def start(self):
        """Start the monitoring service"""
        with self._lock:
            if self.running:
                return
                
            self.running = True
            self.monitor_thread = threading.Thread(target=self._monitoring_loop)
            self.monitor_thread.daemon = True
            self.monitor_thread.start()
            logger.info("Exit order monitor started")
        
    def stop(self):
        """Stop the monitoring service"""
        with self._lock:
            self.running = False
            
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5.0)
            logger.info("Exit order monitor stopped")
        
    def _monitoring_loop(self):
        """Main monitoring loop that runs in a separate thread"""
        while self.running:
            try:
                # Check circuit breaker
                if self._is_circuit_breaker_open():
                    logger.warning("Circuit breaker is open. Pausing exit order updates.")
                    time.sleep(5.0)  # Sleep longer when circuit breaker is open
                    continue
                    
                self._update_all_positions()
            except Exception as e:
                logger.error(f"Error in exit order monitor: {e}", exc_info=True)
                self._increment_failure_count()
                
            # Sleep for the update interval
            time.sleep(self.config.update_interval_ms / 1000.0)
            
    def _update_all_positions(self):
        """Update exit orders for all open positions"""
        # Get open positions
        positions = self.position_service.get_open_positions()
        
        # Track processed positions
        processed_positions = set()
        
        for position in positions:
            position_id = position.position_id
            processed_positions.add(position_id)
            
            try:
                # Get market data for this symbol
                market_data = self.market_data_service.get_market_data(position.symbol)
                
                # Update this position's exit orders
                self._update_position_exit_orders(position, market_data)
            except Exception as e:
                logger.error(f"Error updating position {position_id}: {e}", exc_info=True)
                self._increment_failure_count()
            
        # Remove strategies for closed positions
        with self._lock:
            closed_positions = set(self.position_strategies.keys()) - processed_positions
            for position_id in closed_positions:
                self.position_strategies.pop(position_id, None)
            
    def _update_position_exit_orders(self, position: Position, market_data: MarketData):
        """Update exit orders for a single position"""
        position_id = position.position_id
        
        # Get or create strategies for this position
        with self._lock:
            if position_id not in self.position_strategies:
                # Get strategies from position configuration
                strategies = self._get_position_strategies(position)
                self.position_strategies[position_id] = strategies
            else:
                strategies = self.position_strategies[position_id]
            
        # Update stop-loss orders
        sl_strategy = strategies.get("stop_loss")
        if sl_strategy:
            self._update_exit_strategy_orders(
                position, market_data, sl_strategy, position.stop_loss_orders, is_stop_loss=True
            )
            
        # Update take-profit orders
        tp_strategy = strategies.get("take_profit")
        if tp_strategy:
            self._update_exit_strategy_orders(
                position, market_data, tp_strategy, position.take_profit_orders, is_stop_loss=False
            )
    
    def _update_exit_strategy_orders(self, position: Position, market_data: MarketData,
                                    strategy: ExitStrategy, current_orders: List[ExitOrder],
                                    is_stop_loss: bool):
        """Update orders for a specific exit strategy"""
        # Get updated orders from the strategy
        updated_orders = strategy.update_exit_orders(position, current_orders, market_data)
        
        # If orders have changed, cancel existing orders and place new ones
        if self._orders_have_changed(current_orders, updated_orders):
            # Cancel existing orders
            for order in current_orders:
                if order.order_id:  # Only cancel orders that have been placed
                    try:
                        self.exchange_client.cancel_order(position.symbol, order.order_id)
                    except Exception as e:
                        logger.error(f"Error canceling order {order.order_id}: {e}")
                        self._increment_failure_count()
            
            # Place new orders
            placed_orders = []
            for order in updated_orders:
                try:
                    # Determine side based on position side
                    order_side = "SELL" if position.side == "BUY" else "BUY"
                    
                    result = self.exchange_client.place_order(
                        symbol=position.symbol,
                        side=order_side,
                        type=order.type.value,
                        quantity=order.quantity,
                        price=order.price
                    )
                    # Update order with exchange data
                    order.order_id = result.get("orderId")
                    order.status = result.get("status")
                    order.exchange_info = result
                    placed_orders.append(order)
                    self._reset_failure_count()  # Successful operation
                except Exception as e:
                    logger.error(f"Error placing {order.type} order for {position.symbol}: {e}")
                    self._increment_failure_count()
                    # Add the order without exchange ID for retry
                    placed_orders.append(order)
            
            # Update position's orders
            if is_stop_loss:
                position.stop_loss_orders = placed_orders
            else:
                position.take_profit_orders = placed_orders
                
            # Update position in service
            self.position_service.update_position(position)
    
    def _orders_have_changed(self, current_orders: List[ExitOrder], 
                            updated_orders: List[ExitOrder]) -> bool:
        """Check if orders have changed and need to be updated on the exchange"""
        if len(current_orders) != len(updated_orders):
            return True
            
        for i, current_order in enumerate(current_orders):
            updated_order = updated_orders[i]
            
            # Check if price or quantity has changed significantly
            if (abs(current_order.price - updated_order.price) > 0.0001 or
                abs(current_order.quantity - updated_order.quantity) > 0.0001 or
                current_order.type != updated_order.type):
                return True
                
        return False
        
    def _get_position_strategies(self, position: Position) -> Dict:
        """Get exit strategies for a position from its configuration"""
        # This would retrieve strategy configuration from position metadata
        # For demo purposes, use default strategy configuration
        strategy_id = position.position_id  # Use position ID as strategy ID
        
        # Get strategy config
        strategy_config = self.config.get_strategy_config(strategy_id)
        
        # Create stop-loss strategy
        sl_config = strategy_config.get_stop_loss_config(self.config.global_params)
        sl_strategy = ExitStrategyFactory.create_strategy(sl_config)
        
        # Create take-profit strategy
        tp_config = strategy_config.get_take_profit_config(self.config.global_params)
        tp_strategy = ExitStrategyFactory.create_strategy(tp_config)
        
        return {
            "stop_loss": sl_strategy,
            "take_profit": tp_strategy
        }
        
    def register_position(self, position: Position, exit_config: Optional[StrategyExitConfig] = None):
        """
        Register a new position with the monitor
        
        Args:
            position: The position to register
            exit_config: Optional exit configuration for this position
        """
        with self._lock:
            if position.position_id in self.position_strategies:
                # Already registered
                return
                
            # If exit config is provided, register it
            if exit_config:
                strategy_id = position.position_id
                self.config.strategy_configs[strategy_id] = exit_config
                
            # Get strategies for this position
            strategies = self._get_position_strategies(position)
            self.position_strategies[position.position_id] = strategies
            
            # Calculate and place initial exit orders
            market_data = self.market_data_service.get_market_data(position.symbol)
            
            # Generate stop-loss orders
            sl_strategy = strategies.get("stop_loss")
            if sl_strategy:
                position.stop_loss_orders = sl_strategy.generate_exit_orders(position, market_data)
                
            # Generate take-profit orders
            tp_strategy = strategies.get("take_profit")
            if tp_strategy:
                position.take_profit_orders = tp_strategy.generate_exit_orders(position, market_data)
                
            # Initial order placement happens in the monitor loop
            
    def _increment_failure_count(self):
        """Increment the failure count for circuit breaker logic"""
        with self._lock:
            self._failure_count += 1
            
            # Check if we need to open the circuit
            if (self._failure_count >= self.config.circuit_breaker_threshold and 
                not self._circuit_open):
                self._circuit_open = True
                self._circuit_open_time = time.time()
                logger.warning("Circuit breaker opened due to repeated failures")
                
    def _reset_failure_count(self):
        """Reset the failure count after successful operations"""
        with self._lock:
            self._failure_count = 0
            
    def _is_circuit_breaker_open(self) -> bool:
        """Check if the circuit breaker is open"""
        with self._lock:
            if not self._circuit_open:
                return False
                
            # Check if enough time has passed to reset
            current_time = time.time()
            if (current_time - self._circuit_open_time) * 1000 >= self.config.circuit_breaker_reset_time_ms:
                # Reset circuit breaker
                self._circuit_open = False
                self._failure_count = 0
                logger.info("Circuit breaker reset after cooling period")
                return False
                
            return True 