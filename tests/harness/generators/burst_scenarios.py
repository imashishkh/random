"""
Burst Order Scenario Generators

This module provides specialized generators for simulating burst order scenarios
with various patterns and correlation with market data.
"""

import asyncio
import random
import time
import logging
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Any, AsyncIterator, Union, Tuple, Callable
import math

from .base import OrderGenerator, OrderData, MarketData
from .market_data import TickDataGenerator
from .order_events import OrderCancellation, OrderModification


class BurstOrderScenarioGenerator(OrderGenerator):
    """
    Base class for burst order scenario generators with advanced configuration.
    """
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the burst order scenario generator.
        
        Args:
            config: Configuration dictionary
            logger: Optional logger instance
        """
        super().__init__(config, logger)
        
        # Basic burst parameters
        self.burst_size_min = config.get('burst_size_min', 10)
        self.burst_size_max = config.get('burst_size_max', 50)
        self.burst_interval_min = config.get('burst_interval_min', 5)
        self.burst_interval_max = config.get('burst_interval_max', 30)
        self.burst_duration_min = config.get('burst_duration_min', 0.5)
        self.burst_duration_max = config.get('burst_duration_max', 2.0)
        
        # Advanced parameters
        self.order_type_distribution = config.get('order_type_distribution', {'market': 0.7, 'limit': 0.2, 'stop': 0.1})
        self.order_lifetime_distribution = config.get('order_lifetime_distribution', {'ioc': 0.2, 'gtc': 0.7, 'fok': 0.1})
        self.cancellation_rate = config.get('cancellation_rate', 0.3)  # 30% of orders get cancelled
        self.modification_rate = config.get('modification_rate', 0.2)  # 20% of orders get modified
        self.limit_distance_min = config.get('limit_distance_min', 0.0001)
        self.limit_distance_max = config.get('limit_distance_max', 0.002)
        
        # Correlation parameters
        self.market_correlation_enabled = config.get('market_correlation_enabled', True)
        self.correlation_thresholds = config.get('correlation_thresholds', {
            'price_movement': 0.002,  # 0.2% price movement triggers event
            'volatility': 0.005,  # Volatility above 0.5% triggers event
            'spread': 0.0003,  # Spread widening beyond 3 pips triggers event
        })
        
        # State management
        self.order_store = {}  # For tracking orders that might be cancelled/modified
        self.cancelled_orders = set()  # Track cancelled order IDs
        self.market_data_cache = {}  # Cache recent market data for correlation
        self.order_counter = 0
        self.bursts_generated = 0
        self.orders_in_bursts = 0
        self.in_burst = False
        self.burst_task = None
        
        # Reference to a TickDataGenerator for price data
        self.tick_generator = None
    
    def set_tick_generator(self, generator: TickDataGenerator) -> None:
        """
        Set the tick generator to get price data from.
        
        Args:
            generator: TickDataGenerator instance
        """
        self.tick_generator = generator
    
    async def start(self) -> None:
        """Start the order generator."""
        await super().start()
        self.logger.info(f"Starting burst scenario order generation for symbols: {', '.join(self.symbols)}")
        
        # Start the burst scheduling loop as a task
        asyncio.create_task(self._burst_scheduling_loop())
        
        # Start order cancellation/modification loop if enabled
        if self.cancellation_rate > 0 or self.modification_rate > 0:
            asyncio.create_task(self._order_lifecycle_loop())
    
    async def stop(self) -> None:
        """Stop the order generator."""
        await super().stop()
        
        # Cancel any ongoing burst
        if self.burst_task and not self.burst_task.done():
            self.burst_task.cancel()
            
        self.logger.info(f"Stopped burst order generation. Generated {self.bursts_generated} bursts with {self.orders_in_bursts} total orders")
    
    async def _burst_scheduling_loop(self) -> None:
        """Loop for scheduling bursts of orders."""
        try:
            while self._running:
                # Schedule next burst after a random interval
                interval = random.uniform(self.burst_interval_min, self.burst_interval_max)
                self.logger.info(f"Next order burst in {interval:.1f} seconds")
                await asyncio.sleep(interval)
                
                if not self._running:
                    break
                
                # Generate a burst of orders
                self.burst_task = asyncio.create_task(self._generate_burst())
                await self.burst_task
        
        except asyncio.CancelledError:
            self.logger.info("Burst scheduling loop cancelled")
        except Exception as e:
            self.logger.error(f"Error in burst scheduling loop: {e}", exc_info=True)
    
    async def _generate_burst(self) -> None:
        """
        Generate a burst of orders according to the scenario logic.
        This method should be overridden by subclasses to implement specific burst patterns.
        """
        raise NotImplementedError("Subclasses must implement _generate_burst method")
    
    async def _order_lifecycle_loop(self) -> None:
        """Loop for handling order cancellations and modifications."""
        try:
            while self._running:
                # Process order cancellations and modifications every second
                await asyncio.sleep(1.0)
                
                # Get list of active orders (not yet cancelled)
                active_orders = {order_id: order for order_id, order in self.order_store.items() 
                                if order_id not in self.cancelled_orders}
                
                if not active_orders:
                    continue
                
                # Randomly select orders for cancellation
                cancellation_count = int(len(active_orders) * self.cancellation_rate * random.uniform(0.5, 1.5))
                if cancellation_count > 0:
                    orders_to_cancel = random.sample(list(active_orders.keys()), min(cancellation_count, len(active_orders)))
                    for order_id in orders_to_cancel:
                        await self._cancel_order(order_id, active_orders[order_id])
                        self.cancelled_orders.add(order_id)
                        
                # Update active orders after cancellations
                active_orders = {order_id: order for order_id, order in active_orders.items() 
                                if order_id not in self.cancelled_orders}
                
                # Randomly select orders for modification
                modification_count = int(len(active_orders) * self.modification_rate * random.uniform(0.5, 1.5))
                if modification_count > 0:
                    orders_to_modify = random.sample(list(active_orders.keys()), min(modification_count, len(active_orders)))
                    for order_id in orders_to_modify:
                        await self._modify_order(order_id, active_orders[order_id])
        
        except asyncio.CancelledError:
            self.logger.info("Order lifecycle loop cancelled")
        except Exception as e:
            self.logger.error(f"Error in order lifecycle loop: {e}", exc_info=True)
    
    async def _cancel_order(self, order_id: str, order: OrderData) -> None:
        """Cancel an order and notify listeners."""
        # Create cancellation event
        cancellation = OrderCancellation(
            order_id=order_id,
            symbol=order.symbol,
            timestamp=datetime.now(),
            original_order=order
        )
        self.logger.debug(f"Cancelling order: {order_id}")
        self._notify_listeners(cancellation)
    
    async def _modify_order(self, order_id: str, order: OrderData) -> None:
        """Modify an order and notify listeners."""
        # Only limit and stop orders can be modified
        if order.order_type == 'market':
            return
            
        # Calculate modified price (slightly different from original)
        if order.price is not None:
            # Random price adjustment between -0.5% and +0.5%
            price_adjustment = random.uniform(-0.005, 0.005)
            new_price = order.price * (1 + price_adjustment)
            new_price = round(new_price, 5)
        else:
            new_price = None
            
        # Calculate modified size (slightly different from original)
        # Random size adjustment between -20% and +20%
        size_adjustment = random.uniform(-0.2, 0.2)
        new_size = order.size * (1 + size_adjustment)
        new_size = round(new_size, 2)
        
        # Create modification event
        modification = OrderModification(
            order_id=order_id,
            symbol=order.symbol,
            timestamp=datetime.now(),
            original_order=order,
            new_price=new_price,
            new_size=new_size
        )
        self.logger.debug(f"Modifying order: {order_id}, new price: {new_price}, new size: {new_size}")
        self._notify_listeners(modification)
    
    async def _generate_order(self, symbol: str, type_distribution: Optional[Dict[str, float]] = None) -> OrderData:
        """
        Generate a single order with diverse characteristics.
        
        Args:
            symbol: Symbol to generate order for
            type_distribution: Optional override for order type distribution
            
        Returns:
            OrderData instance
        """
        # Generate unique order ID
        self.order_counter += 1
        order_id = f"burst_order_{self.order_counter}"
        
        # Get current price from tick generator if available
        current_price = None
        if self.tick_generator and symbol in self.tick_generator.current_prices:
            current_price = self.tick_generator.current_prices[symbol]
        else:
            # Use a default price range if tick generator not available
            base_price = 1.0
            if symbol in ['EURUSD', 'GBPUSD']:
                base_price = random.uniform(1.0, 1.5)
            elif symbol in ['USDJPY', 'EURJPY']:
                base_price = random.uniform(100.0, 150.0)
            else:
                base_price = random.uniform(0.5, 2.0)
            
            # Add some noise
            current_price = base_price * (1 + random.normalvariate(0, 0.0002))
        
        # Determine order type based on distribution
        distribution = type_distribution or self.order_type_distribution
        order_type = random.choices(
            list(distribution.keys()), 
            weights=list(distribution.values()), 
            k=1
        )[0]
        
        # Determine direction
        # Direction can be biased based on recent price movement if market data correlation is enabled
        direction_bias = 0.5  # Default 50/50
        if self.market_correlation_enabled and symbol in self.market_data_cache:
            recent_data = self.market_data_cache[symbol][-5:]
            if len(recent_data) >= 2:
                # If price is trending up, bias towards selling
                # If price is trending down, bias towards buying
                first_price = getattr(recent_data[0], 'price', None) or getattr(recent_data[0], 'mid_price', None)
                last_price = getattr(recent_data[-1], 'price', None) or getattr(recent_data[-1], 'mid_price', None)
                if first_price and last_price:
                    price_change = (last_price - first_price) / first_price
                    # Adjust bias based on price change (0.01 = 1% change)
                    direction_bias = 0.5 + min(0.3, max(-0.3, price_change * 10))  # Caps bias at 20%-80%
        
        direction = "buy" if random.random() < direction_bias else "sell"
        
        # Size with realistic distribution (log-normal - most orders are smaller, with occasional larger ones)
        size_mu = np.log((self.size_min + self.size_max) / 2)
        size_sigma = 0.5  # Controls the spread of the distribution
        size = round(min(self.size_max * 2, max(self.size_min, np.random.lognormal(size_mu, size_sigma))), 2)
        
        # Price depends on order type
        price = None
        stop_price = None
        
        if order_type == 'market':
            # Market orders use current price
            price = current_price
        elif order_type == 'limit':
            # Limit orders are placed some distance from current price
            # Buy limits are below current price, sell limits are above
            # Distance follows a power-law distribution (more orders near the current price)
            distance_min = self.limit_distance_min
            distance_max = self.limit_distance_max
            distance_alpha = 2.0  # Higher values concentrate more orders near the current price
            
            # Generate power-law distributed distance
            distance = distance_min + (distance_max - distance_min) * (random.random() ** distance_alpha)
            
            if direction == 'buy':
                price = current_price * (1 - distance)
            else:
                price = current_price * (1 + distance)
                
            # Round to appropriate number of decimals
            price = round(price, 5)
        elif order_type == 'stop':
            # Stop orders are placed some distance from current price
            # Buy stops are above current price, sell stops are below
            distance_min = self.limit_distance_min
            distance_max = self.limit_distance_max
            
            # Stops often cluster at certain levels - simulate this with a mixture of uniform and normal distributions
            if random.random() < 0.7:
                # Normal distribution around key levels
                level_distances = [0.001, 0.002, 0.005, 0.01]  # Common stop distances
                base_distance = random.choice(level_distances)
                distance = max(distance_min, min(distance_max, base_distance + random.normalvariate(0, base_distance/5)))
            else:
                # Uniform distribution
                distance = random.uniform(distance_min, distance_max)
            
            if direction == 'buy':
                price = current_price
                stop_price = current_price * (1 + distance)
            else:
                price = current_price
                stop_price = current_price * (1 - distance)
                
            # Round to appropriate number of decimals
            stop_price = round(stop_price, 5)
        
        # Create order
        return OrderData(
            order_id=order_id,
            symbol=symbol,
            timestamp=datetime.now(),
            direction=direction,
            order_type=order_type,
            price=price,
            size=size,
            stop_price=stop_price
        )
    
    def update_market_data(self, data: MarketData) -> None:
        """
        Update the market data cache with new data.
        
        Args:
            data: New market data
        """
        if not self.market_correlation_enabled:
            return
            
        symbol = data.symbol
        
        # Initialize cache for this symbol if needed
        if symbol not in self.market_data_cache:
            self.market_data_cache[symbol] = []
            
        # Add new data
        self.market_data_cache[symbol].append(data)
        
        # Limit cache size
        max_cache_size = 100
        if len(self.market_data_cache[symbol]) > max_cache_size:
            self.market_data_cache[symbol] = self.market_data_cache[symbol][-max_cache_size:]
    
    def is_market_condition_met(self, symbol: str, condition_type: str) -> bool:
        """
        Check if a specific market condition is met for generating a burst.
        
        Args:
            symbol: Symbol to check condition for
            condition_type: Type of condition to check
            
        Returns:
            True if condition is met, False otherwise
        """
        if not self.market_correlation_enabled or symbol not in self.market_data_cache:
            return False
            
        recent_data = self.market_data_cache[symbol][-10:]  # Last 10 data points
        
        if len(recent_data) < 2:
            return False
            
        if condition_type == 'price_movement':
            # Check for significant price movement
            prices = []
            for data in recent_data:
                if hasattr(data, 'price'):
                    prices.append(data.price)
                elif hasattr(data, 'mid_price'):
                    prices.append(data.mid_price)
                elif hasattr(data, 'bid') and hasattr(data, 'ask'):
                    prices.append((data.bid + data.ask) / 2)
            
            if not prices or len(prices) < 2:
                return False
                
            price_change = abs(prices[-1] - prices[0]) / prices[0]
            return price_change > self.correlation_thresholds['price_movement']
            
        elif condition_type == 'volatility':
            # Check for high volatility
            prices = []
            for data in recent_data:
                if hasattr(data, 'price'):
                    prices.append(data.price)
                elif hasattr(data, 'mid_price'):
                    prices.append(data.mid_price)
                elif hasattr(data, 'bid') and hasattr(data, 'ask'):
                    prices.append((data.bid + data.ask) / 2)
            
            if not prices or len(prices) < 5:
                return False
                
            volatility = np.std(prices) / np.mean(prices)
            return volatility > self.correlation_thresholds['volatility']
            
        elif condition_type == 'spread':
            # Check for widening spread
            spreads = []
            for data in recent_data:
                if hasattr(data, 'bid') and hasattr(data, 'ask'):
                    spreads.append(data.ask - data.bid)
            
            if not spreads:
                return False
                
            return spreads[-1] > self.correlation_thresholds['spread']
            
        return False


class SuddenBurstScenario(BurstOrderScenarioGenerator):
    """
    Generates sudden bursts of orders with high intensity in a short period.
    Simulates market reactions to unexpected events or news.
    """
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the sudden burst scenario generator.
        
        Args:
            config: Configuration dictionary
            logger: Optional logger instance
        """
        super().__init__(config, logger)
        
        # Sudden burst specific parameters
        self.intensity_factor = config.get('intensity_factor', 2.0)  # Higher values = more intense bursts
        self.market_order_bias = config.get('market_order_bias', 0.7)  # Higher proportion of market orders in sudden bursts
    
    async def _generate_burst(self) -> None:
        """Generate a sudden burst of orders over a short period."""
        # Determine burst parameters - sudden bursts tend to be more intense, shorter
        burst_size = random.randint(self.burst_size_min, self.burst_size_max)
        # Shorter duration for more intensity
        burst_duration = random.uniform(self.burst_duration_min, self.burst_duration_min * 1.5)
        interval = burst_duration / burst_size
        
        # Choose a symbol - in a sudden burst, often focused on a single symbol
        symbol = random.choice(self.symbols)
        
        self.in_burst = True
        self.logger.info(f"Starting sudden burst of {burst_size} orders over {burst_duration:.2f} seconds ({1/interval:.1f} orders/sec)")
        
        # For sudden bursts, favor more market orders (higher urgency)
        temp_distribution = self.order_type_distribution.copy()
        temp_distribution['market'] = min(0.9, self.market_order_bias)
        
        # Adjust other order types proportionally
        remaining = 1.0 - temp_distribution['market']
        original_limit_stop_ratio = (
            self.order_type_distribution.get('limit', 0.2) / 
            (self.order_type_distribution.get('limit', 0.2) + self.order_type_distribution.get('stop', 0.1))
        )
        temp_distribution['limit'] = remaining * original_limit_stop_ratio
        temp_distribution['stop'] = remaining * (1.0 - original_limit_stop_ratio)
        
        try:
            # Generate orders in the burst - use exponential distribution for realistic behavior
            # Most orders arrive in the beginning of the burst (front-loaded)
            time_points = np.random.exponential(scale=burst_duration/self.intensity_factor, size=burst_size)
            time_points = np.sort([min(t, burst_duration) for t in time_points])
            
            last_time = 0
            for i, time_point in enumerate(time_points):
                # Wait until the next order time
                sleep_time = time_point - last_time
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                
                # Generate order with sudden burst characteristics
                order = await self._generate_order(symbol, temp_distribution)
                self._notify_listeners(order)
                self.orders_in_bursts += 1
                self.order_store[order.order_id] = order
                
                last_time = time_point
            
            self.bursts_generated += 1
            self.logger.info(f"Completed sudden burst #{self.bursts_generated} with {burst_size} orders")
            
        except asyncio.CancelledError:
            self.logger.info("Sudden burst generation cancelled")
        except Exception as e:
            self.logger.error(f"Error generating sudden burst: {e}", exc_info=True)
        finally:
            self.in_burst = False


class RampBurstScenario(BurstOrderScenarioGenerator):
    """
    Generates bursts of orders with a gradual ramp-up and/or ramp-down pattern.
    Simulates gradual market reactions to anticipated events or scheduled announcements.
    """
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the ramp burst scenario generator.
        
        Args:
            config: Configuration dictionary
            logger: Optional logger instance
        """
        super().__init__(config, logger)
        
        # Ramp specific parameters
        self.ramp_up_percentage = config.get('ramp_up_percentage', 0.4)  # 40% of duration is ramp-up
        self.ramp_down_percentage = config.get('ramp_down_percentage', 0.4)  # 40% of duration is ramp-down
        self.plateau_percentage = config.get('plateau_percentage', 0.2)  # 20% of duration is plateau
        self.ramp_type = config.get('ramp_type', 'quadratic')  # linear, quadratic, cubic
        
        # Validate percentages sum to 1.0
        total = self.ramp_up_percentage + self.plateau_percentage + self.ramp_down_percentage
        if abs(total - 1.0) > 0.01:  # Allow for small floating point errors
            self.logger.warning(f"Ramp percentages sum to {total}, normalizing to 1.0")
            factor = 1.0 / total
            self.ramp_up_percentage *= factor
            self.plateau_percentage *= factor
            self.ramp_down_percentage *= factor
    
    async def _generate_burst(self) -> None:
        """Generate a burst of orders with a ramp-up/down pattern."""
        # Determine burst parameters - ramp bursts tend to last longer
        burst_size = random.randint(self.burst_size_min, self.burst_size_max)
        burst_duration = random.uniform(self.burst_duration_min * 1.5, self.burst_duration_max)
        
        # Calculate phase durations
        ramp_up_duration = burst_duration * self.ramp_up_percentage
        plateau_duration = burst_duration * self.plateau_percentage
        ramp_down_duration = burst_duration * self.ramp_down_percentage
        
        # Choose a symbol or symbols - ramp bursts might involve multiple symbols
        if random.random() < 0.7:  # 70% chance of single symbol
            symbols = [random.choice(self.symbols)]
        else:
            # Use 2-3 symbols
            num_symbols = min(len(self.symbols), random.randint(2, 3))
            symbols = random.sample(self.symbols, num_symbols)
        
        self.in_burst = True
        self.logger.info(f"Starting ramp burst of {burst_size} orders over {burst_duration:.2f} seconds with ramp up/down pattern")
        
        try:
            # Calculate orders per phase
            ramp_up_orders = int(burst_size * self.ramp_up_percentage)
            plateau_orders = int(burst_size * self.plateau_percentage)
            ramp_down_orders = burst_size - ramp_up_orders - plateau_orders
            
            time_points = []
            
            # Generate timestamps for ramp-up phase (accelerating)
            if ramp_up_orders > 0:
                if self.ramp_type == 'linear':
                    # Linear ramp (uniform)
                    ramp_up_points = np.linspace(0, ramp_up_duration, ramp_up_orders, endpoint=False)
                    time_points.extend(ramp_up_points)
                elif self.ramp_type == 'quadratic':
                    # Quadratic ramp (accelerating)
                    ramp_up_raw_points = np.linspace(0, 1, ramp_up_orders, endpoint=False)
                    ramp_up_points = [t**2 * ramp_up_duration for t in ramp_up_raw_points]
                    time_points.extend(ramp_up_points)
                elif self.ramp_type == 'cubic':
                    # Cubic ramp (sharper acceleration)
                    ramp_up_raw_points = np.linspace(0, 1, ramp_up_orders, endpoint=False)
                    ramp_up_points = [t**3 * ramp_up_duration for t in ramp_up_raw_points]
                    time_points.extend(ramp_up_points)
            
            # Generate timestamps for plateau phase (constant rate)
            if plateau_orders > 0:
                plateau_points = np.linspace(ramp_up_duration, 
                                            ramp_up_duration + plateau_duration, 
                                            plateau_orders, endpoint=False)
                time_points.extend(plateau_points)
            
            # Generate timestamps for ramp-down phase (decelerating)
            if ramp_down_orders > 0:
                ramp_down_start = ramp_up_duration + plateau_duration
                
                if self.ramp_type == 'linear':
                    # Linear ramp down
                    ramp_down_points = np.linspace(ramp_down_start, burst_duration, ramp_down_orders, endpoint=False)
                    time_points.extend(ramp_down_points)
                elif self.ramp_type == 'quadratic':
                    # Quadratic ramp down (decelerating)
                    ramp_down_raw_points = np.linspace(0, 1, ramp_down_orders, endpoint=False)
                    ramp_down_points = [ramp_down_start + (1-(1-t)**2) * ramp_down_duration 
                                       for t in ramp_down_raw_points]
                    time_points.extend(ramp_down_points)
                elif self.ramp_type == 'cubic':
                    # Cubic ramp down (sharper deceleration)
                    ramp_down_raw_points = np.linspace(0, 1, ramp_down_orders, endpoint=False)
                    ramp_down_points = [ramp_down_start + (1-(1-t)**3) * ramp_down_duration 
                                       for t in ramp_down_raw_points]
                    time_points.extend(ramp_down_points)
            
            # Sort and remove any duplicates to ensure chronological order
            time_points = sorted(set(time_points))
            
            # Order type distribution varies by phase
            # More limit orders during ramp-up, more market orders during plateau, mixed during ramp-down
            ramp_up_dist = {'market': 0.3, 'limit': 0.6, 'stop': 0.1}
            plateau_dist = {'market': 0.6, 'limit': 0.3, 'stop': 0.1}
            ramp_down_dist = {'market': 0.5, 'limit': 0.3, 'stop': 0.2}
            
            # Execute the burst
            last_time = 0
            for i, time_point in enumerate(time_points):
                # Wait until the next order time
                sleep_time = time_point - last_time
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                
                # Determine which phase we're in
                if time_point < ramp_up_duration:
                    phase_dist = ramp_up_dist
                elif time_point < ramp_up_duration + plateau_duration:
                    phase_dist = plateau_dist
                else:
                    phase_dist = ramp_down_dist
                
                # Choose symbol - if multiple, pick them in sequence to simulate spreading effect
                if len(symbols) > 1:
                    symbol_idx = i % len(symbols)
                    symbol = symbols[symbol_idx]
                else:
                    symbol = symbols[0]
                
                # Generate order
                order = await self._generate_order(symbol, phase_dist)
                self._notify_listeners(order)
                self.orders_in_bursts += 1
                self.order_store[order.order_id] = order
                
                last_time = time_point
            
            self.bursts_generated += 1
            self.logger.info(f"Completed ramp burst #{self.bursts_generated} with {burst_size} orders")
            
        except asyncio.CancelledError:
            self.logger.info("Ramp burst generation cancelled")
        except Exception as e:
            self.logger.error(f"Error generating ramp burst: {e}", exc_info=True)
        finally:
            self.in_burst = False


class OscillatingBurstScenario(BurstOrderScenarioGenerator):
    """
    Generates bursts of orders with a wave-like pattern (oscillating intensity).
    Simulates market volatility with periodic surges and lulls in trading activity.
    """
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the oscillating burst scenario generator.
        
        Args:
            config: Configuration dictionary
            logger: Optional logger instance
        """
        super().__init__(config, logger)
        
        # Oscillation specific parameters
        self.num_cycles = config.get('num_cycles', 3)  # Number of oscillation cycles
        self.wave_type = config.get('wave_type', 'sine')  # sine, square, triangle
        self.amplitude_factor = config.get('amplitude_factor', 0.8)  # Controls intensity variation (0-1)
        self.phase_shift = config.get('phase_shift', 0.0)  # Phase shift in radians
        
        # Market correlation for oscillation timing
        self.market_triggered_oscillation = config.get('market_triggered_oscillation', False)
        self.market_trigger_threshold = config.get('market_trigger_threshold', 0.02)  # 2% price movement
        
        # Validate amplitude factor
        if not 0 <= self.amplitude_factor <= 1:
            self.logger.warning(f"Invalid amplitude factor {self.amplitude_factor}, setting to 0.8")
            self.amplitude_factor = 0.8
    
    async def _generate_burst(self) -> None:
        """Generate a burst of orders with an oscillating pattern."""
        # Oscillating bursts may last longer to show the pattern
        burst_size = random.randint(self.burst_size_min, self.burst_size_max)
        burst_duration = random.uniform(self.burst_duration_min * 2, self.burst_duration_max * 2)
        
        # Oscillating bursts may involve multiple symbols
        if random.random() < 0.5:  # 50% chance of multiple symbols
            num_symbols = min(len(self.symbols), random.randint(2, 4))
            symbols = random.sample(self.symbols, num_symbols)
        else:
            symbols = [random.choice(self.symbols)]
        
        self.in_burst = True
        self.logger.info(f"Starting oscillating burst of {burst_size} orders over {burst_duration:.2f} seconds with {self.num_cycles} cycles")
        
        try:
            time_points = []
            
            # Define time points based on wave type
            if self.wave_type == 'sine':
                # Generate time points with sine wave distribution
                t = np.linspace(0, burst_duration, burst_size)
                
                # Apply sine wave density modulation to create clusters
                for i in range(burst_size):
                    phase = 2 * math.pi * self.num_cycles * (t[i] / burst_duration) + self.phase_shift
                    probability = 0.5 + 0.5 * self.amplitude_factor * math.sin(phase)
                    
                    # Skip some points in low-probability regions to create clusters
                    if random.random() <= probability:
                        time_points.append(t[i])
                
            elif self.wave_type == 'square':
                # Generate time points with square wave distribution
                t = np.linspace(0, burst_duration, burst_size * 2)  # Double points to allow filtering
                
                for i in range(len(t)):
                    cycle_position = (t[i] / burst_duration) * self.num_cycles
                    in_high_period = (cycle_position % 1) < 0.5  # High for first half of each cycle
                    
                    # High probability during high period, low during low period
                    probability = 0.8 if in_high_period else 0.2
                    if random.random() <= probability:
                        time_points.append(t[i])
                        if len(time_points) >= burst_size:
                            break
                
            elif self.wave_type == 'triangle':
                # Generate time points with triangle wave distribution
                t = np.linspace(0, burst_duration, burst_size * 2)  # Double points to allow filtering
                
                for i in range(len(t)):
                    phase = (t[i] / burst_duration) * self.num_cycles
                    fraction_in_cycle = phase % 1
                    
                    # Triangle wave: rises linearly to 1, then falls linearly to 0
                    triangle_value = 2 * abs(fraction_in_cycle - 0.5)
                    probability = 0.3 + 0.7 * triangle_value  # Scale to 0.3-1.0 range
                    
                    if random.random() <= probability:
                        time_points.append(t[i])
                        if len(time_points) >= burst_size:
                            break
            
            # Sort time points
            time_points = sorted(time_points)
            
            # If we didn't get enough points, add more uniformly
            while len(time_points) < burst_size:
                # Add points at random positions between existing ones or at the end
                if len(time_points) > 0:
                    if len(time_points) == 1 or random.random() < 0.5:
                        # Add between points
                        idx = random.randint(0, len(time_points) - 2)
                        new_point = (time_points[idx] + time_points[idx + 1]) / 2
                    else:
                        # Add at end
                        new_point = min(burst_duration, time_points[-1] + random.uniform(0.01, 0.1))
                else:
                    new_point = random.uniform(0, burst_duration)
                
                # Only add if it's a unique point
                if new_point not in time_points:
                    time_points.append(new_point)
                    time_points.sort()
            
            # Limit to burst_size if we have too many
            if len(time_points) > burst_size:
                time_points = time_points[:burst_size]
            
            # Execute the burst
            last_time = 0
            for i, time_point in enumerate(time_points):
                # Wait until the next order time
                sleep_time = time_point - last_time
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                
                # Choose symbol - for multiple symbols, distribute orders in a pattern
                if len(symbols) > 1:
                    # Cycle through symbols at different rates depending on position in burst
                    cycle_position = (time_point / burst_duration) * self.num_cycles
                    symbol_index = int((cycle_position * len(symbols)) % len(symbols))
                    symbol = symbols[symbol_index]
                else:
                    symbol = symbols[0]
                
                # Order type distribution varies based on wave cycle position
                cycle_position = (time_point / burst_duration) * self.num_cycles
                phase_in_cycle = (cycle_position % 1) * 2 * math.pi
                
                # Adjust order type distribution based on position in wave
                if self.wave_type == 'sine':
                    # More market orders at wave peaks, more limit orders at troughs
                    market_bias = 0.5 + 0.3 * math.sin(phase_in_cycle)
                    order_type_dist = {
                        'market': market_bias,
                        'limit': 0.9 - market_bias,  # Ensures sum is 0.9
                        'stop': 0.1
                    }
                elif self.wave_type == 'square':
                    # Square wave: distinct high/low periods
                    if phase_in_cycle < math.pi:  # First half of cycle
                        order_type_dist = {'market': 0.7, 'limit': 0.2, 'stop': 0.1}
                    else:  # Second half of cycle
                        order_type_dist = {'market': 0.3, 'limit': 0.6, 'stop': 0.1}
                else:  # triangle or default
                    # Linear variation between market and limit
                    if phase_in_cycle < math.pi:  # Rising phase
                        market_ratio = 0.3 + (phase_in_cycle / math.pi) * 0.4  # 0.3 to 0.7
                    else:  # Falling phase
                        market_ratio = 0.7 - ((phase_in_cycle - math.pi) / math.pi) * 0.4  # 0.7 to 0.3
                    
                    order_type_dist = {
                        'market': market_ratio,
                        'limit': 0.9 - market_ratio,
                        'stop': 0.1
                    }
                
                # Generate order
                order = await self._generate_order(symbol, order_type_dist)
                self._notify_listeners(order)
                self.orders_in_bursts += 1
                self.order_store[order.order_id] = order
                
                last_time = time_point
            
            self.bursts_generated += 1
            self.logger.info(f"Completed oscillating burst #{self.bursts_generated} with {len(time_points)} orders")
            
        except asyncio.CancelledError:
            self.logger.info("Oscillating burst generation cancelled")
        except Exception as e:
            self.logger.error(f"Error generating oscillating burst: {e}", exc_info=True)
        finally:
            self.in_burst = False


class MarketEventBurstScenario(BurstOrderScenarioGenerator):
    """
    Generates bursts of orders in response to specific market data conditions.
    Simulates market reactions to price movements, volatility changes, or spread widening.
    """
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the market event burst scenario generator.
        
        Args:
            config: Configuration dictionary
            logger: Optional logger instance
        """
        super().__init__(config, logger)
        
        # Market event specific parameters
        self.trigger_conditions = config.get('trigger_conditions', [
            'price_movement',
            'volatility',
            'spread'
        ])
        
        self.trigger_thresholds = config.get('trigger_thresholds', {
            'price_movement': config.get('price_movement_threshold', 0.002),  # 0.2% movement
            'volatility': config.get('volatility_threshold', 0.005),  # 0.5% volatility
            'spread': config.get('spread_threshold', 0.0003)  # 3 pips spread
        })
        
        self.response_delay = config.get('response_delay', 0.2)  # Seconds to wait after detecting condition
        self.condition_check_interval = config.get('condition_check_interval', 1.0)  # How often to check conditions
        self.event_cooldown = config.get('event_cooldown', 15.0)  # Minimum time between triggered events
        self.last_event_time = 0
        
        # Configure order distributions for different event types
        self.event_order_distributions = config.get('event_order_distributions', {
            'price_movement': {'market': 0.8, 'limit': 0.15, 'stop': 0.05},
            'volatility': {'market': 0.4, 'limit': 0.3, 'stop': 0.3},
            'spread': {'market': 0.2, 'limit': 0.7, 'stop': 0.1}
        })
        
        # Burst parameters for different event types
        self.event_burst_parameters = config.get('event_burst_parameters', {
            'price_movement': {
                'size_factor': 1.2,  # Larger bursts for price movements
                'duration_factor': 0.8  # Shorter duration (more intense)
            },
            'volatility': {
                'size_factor': 1.5,  # Largest bursts for volatility
                'duration_factor': 1.2  # Longer duration (more sustained)
            },
            'spread': {
                'size_factor': 1.0,  # Normal sized bursts for spread changes
                'duration_factor': 1.0  # Normal duration
            }
        })
    
    async def start(self) -> None:
        """Start the order generator."""
        await super().start()
        self.logger.info(f"Starting market event burst order generation for symbols: {', '.join(self.symbols)}")
        
        # Start the market condition monitoring loop as a task
        asyncio.create_task(self._market_condition_loop())
    
    async def _market_condition_loop(self) -> None:
        """Loop for monitoring market conditions and triggering bursts when conditions are met."""
        try:
            while self._running:
                # Check if cooldown period has passed
                current_time = time.time()
                if current_time - self.last_event_time < self.event_cooldown:
                    await asyncio.sleep(0.5)  # Check more frequently during cooldown
                    continue
                    
                # Loop through symbols to check conditions
                for symbol in self.symbols:
                    for condition in self.trigger_conditions:
                        if self.is_market_condition_met(symbol, condition):
                            self.logger.info(f"Market condition '{condition}' detected for {symbol}")
                            # Wait a short delay to simulate reaction time
                            await asyncio.sleep(self.response_delay)
                            
                            # Trigger burst in response to the market condition
                            burst_task = asyncio.create_task(self._generate_market_event_burst(symbol, condition))
                            await burst_task
                            
                            # Update last event time and apply cooldown
                            self.last_event_time = time.time()
                            break  # Only trigger one burst per check cycle
                        
                # Sleep until next check
                await asyncio.sleep(self.condition_check_interval)
                
        except asyncio.CancelledError:
            self.logger.info("Market condition monitoring loop cancelled")
        except Exception as e:
            self.logger.error(f"Error in market condition loop: {e}", exc_info=True)
    
    def is_market_condition_met(self, symbol: str, condition: str) -> bool:
        """
        Check if a specific market condition is met for a symbol.
        
        Args:
            symbol: The symbol to check
            condition: The type of condition to check ('price_movement', 'volatility', 'spread')
            
        Returns:
            bool: True if the condition is met, False otherwise
        """
        try:
            # Get the market data for this symbol
            market_data = self.market_data_source.get_market_data(symbol)
            if not market_data:
                return False
                
            threshold = self.trigger_thresholds.get(condition, 0.001)
            
            if condition == 'price_movement':
                # Check for significant price movement (using returns)
                # Get recent prices and calculate returns
                recent_prices = market_data.get('recent_prices', [])
                if len(recent_prices) < 2:
                    return False
                    
                # Calculate return over most recent interval
                price_return = abs((recent_prices[-1] - recent_prices[0]) / recent_prices[0])
                return price_return > threshold
                
            elif condition == 'volatility':
                # Check for high volatility
                # Get recent volatility estimate (if available) or calculate from recent prices
                volatility = market_data.get('volatility')
                if volatility is None:
                    # Calculate simple volatility from recent prices
                    recent_prices = market_data.get('recent_prices', [])
                    if len(recent_prices) < 5:  # Need enough data points
                        return False
                        
                    # Calculate returns
                    returns = [(recent_prices[i] - recent_prices[i-1]) / recent_prices[i-1] 
                              for i in range(1, len(recent_prices))]
                    
                    # Calculate volatility as standard deviation of returns
                    volatility = np.std(returns) if returns else 0
                    
                return volatility > threshold
                
            elif condition == 'spread':
                # Check for wide bid-ask spread
                bid = market_data.get('bid')
                ask = market_data.get('ask')
                
                if bid is None or ask is None:
                    return False
                    
                # Calculate spread as percentage of price
                mid_price = (bid + ask) / 2
                spread_pct = abs(ask - bid) / mid_price
                
                return spread_pct > threshold
                
            # Unknown condition type
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking market condition '{condition}' for {symbol}: {e}")
            return False
    
    async def _generate_market_event_burst(self, symbol: str, condition: str) -> None:
        """
        Generate a burst of orders in response to a market event.
        
        Args:
            symbol: Symbol that triggered the condition
            condition: Type of condition that was detected
        """
        # Get the parameters for this event type
        event_params = self.event_burst_parameters.get(condition, 
                                                      {'size_factor': 1.0, 'duration_factor': 1.0})
        
        # Calculate burst size with adjustment for event type
        size_min = int(self.burst_size_min * event_params['size_factor'])
        size_max = int(self.burst_size_max * event_params['size_factor'])
        burst_size = random.randint(size_min, size_max)
        
        # Calculate burst duration with adjustment for event type
        duration_min = self.burst_duration_min * event_params['duration_factor']
        duration_max = self.burst_duration_max * event_params['duration_factor']
        burst_duration = random.uniform(duration_min, duration_max)
        
        # Get order type distribution for this event type
        distribution = self.event_order_distributions.get(condition, self.order_type_distribution)
        
        self.in_burst = True
        self.logger.info(f"Starting market event burst for condition '{condition}' on {symbol}: {burst_size} orders over {burst_duration:.2f} seconds")
        
        try:
            # Generate orders in the burst - use exponential distribution for realistic event response
            # Most orders arrive soon after the event
            time_points = np.random.exponential(scale=burst_duration/3, size=burst_size)
            time_points = np.sort([min(t, burst_duration) for t in time_points])
            
            # Determine if we should include related symbols
            include_related = random.random() < 0.3  # 30% chance to include related symbols
            
            if include_related and len(self.symbols) > 1:
                # Choose a few related symbols (e.g., same currency pairs)
                related_symbols = [s for s in self.symbols if s != symbol and 
                                  (s[:3] == symbol[:3] or s[-3:] == symbol[-3:])]
                
                if not related_symbols:  # If no related symbols found, just take random ones
                    num_related = min(2, len(self.symbols) - 1)
                    if num_related > 0:
                        related_symbols = random.sample([s for s in self.symbols if s != symbol], num_related)
                
                # Add the primary symbol
                all_symbols = [symbol] + related_symbols
                symbol_weights = [0.7] + [(0.3 / len(related_symbols)) for _ in related_symbols]
            else:
                all_symbols = [symbol]
                symbol_weights = [1.0]
            
            last_time = 0
            for i, time_point in enumerate(time_points):
                # Wait until the next order time
                sleep_time = time_point - last_time
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                
                # Choose symbol - primary symbol is more likely
                chosen_symbol = random.choices(all_symbols, weights=symbol_weights, k=1)[0]
                
                # Generate order with market event characteristics
                order = await self._generate_order(chosen_symbol, distribution)
                self._notify_listeners(order)
                self.orders_in_bursts += 1
                self.order_store[order.order_id] = order
                
                last_time = time_point
            
            self.bursts_generated += 1
            self.logger.info(f"Completed market event burst #{self.bursts_generated} with {burst_size} orders")
            
        except asyncio.CancelledError:
            self.logger.info("Market event burst generation cancelled")
        except Exception as e:
            self.logger.error(f"Error generating market event burst: {e}", exc_info=True)
        finally:
            self.in_burst = False
    
    async def _generate_burst(self) -> None:
        """
        Generate a random burst without waiting for market conditions.
        This is used for testing and when bursts are scheduled rather than AI-triggered.
        """
        # Choose a random condition and symbol
        condition = random.choice(self.trigger_conditions)
        symbol = random.choice(self.symbols)
        
        # Generate burst for this condition
        await self._generate_market_event_burst(symbol, condition)


class AIReactiveBurstScenario(BurstOrderScenarioGenerator):
    """
    Generates bursts of orders using AI predictions of market conditions.
    Simulates how AI systems might react to market data patterns with varying 
    degrees of aggression, sophistication, and coordination.
    """
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the AI reactive burst scenario generator.
        
        Args:
            config: Configuration dictionary
            logger: Optional logger instance
        """
        super().__init__(config, logger)
        
        # AI model parameters
        self.prediction_window = config.get('prediction_window', 10)  # How many seconds ahead to predict
        self.prediction_confidence_threshold = config.get('prediction_confidence_threshold', 0.65)
        self.ai_sophistication = config.get('ai_sophistication', 0.7)  # 0.0-1.0 scale, higher = more sophisticated
        self.ai_aggression = config.get('ai_aggression', 0.5)  # 0.0-1.0 scale, higher = more aggressive
        self.ai_coordination = config.get('ai_coordination', 0.3)  # 0.0-1.0 scale, higher = more coordinated
        self.ai_reaction_time = config.get('ai_reaction_time', 0.15)  # Base reaction time in seconds
        
        # Market analysis parameters
        self.market_data_history = config.get('market_data_history', 30)  # How many seconds of data to keep
        self.technical_indicators = config.get('technical_indicators', [
            'trend',        # Simple price trend direction
            'momentum',     # Rate of price change
            'volatility',   # Price volatility
            'liquidity',    # Market depth/liquidity
            'correlation'   # Correlation with other assets
        ])
        
        # Internal state
        self.market_data_buffer = {}  # Buffer for historical market data by symbol
        self.last_prediction_time = 0
        self.prediction_interval = config.get('prediction_interval', 1.0)  # How often to make predictions
        self.current_predictions = {}  # Current set of active predictions by symbol
        self.historical_accuracy = 0.7  # Simulated historical accuracy of predictions
        self.accuracy_adjustment = 0.0  # Dynamic adjustment based on market conditions
        
        # AI strategy parameters - determines order characteristics for different prediction types
        self.ai_strategies = config.get('ai_strategies', {
            'trend_following': {
                'weight': 0.4,
                'order_types': {'market': 0.3, 'limit': 0.6, 'stop': 0.1},
                'size_factor': 1.0,
                'duration_factor': 1.2,
                'cancellation_factor': 0.8,
                'modification_factor': 1.2
            },
            'mean_reversion': {
                'weight': 0.3,
                'order_types': {'market': 0.2, 'limit': 0.7, 'stop': 0.1},
                'size_factor': 0.8,
                'duration_factor': 0.9,
                'cancellation_factor': 1.3,
                'modification_factor': 1.5
            },
            'momentum': {
                'weight': 0.2,
                'order_types': {'market': 0.6, 'limit': 0.3, 'stop': 0.1},
                'size_factor': 1.3,
                'duration_factor': 0.7,
                'cancellation_factor': 0.5,
                'modification_factor': 0.9
            },
            'volatility_expansion': {
                'weight': 0.1,
                'order_types': {'market': 0.4, 'limit': 0.4, 'stop': 0.2},
                'size_factor': 1.5,
                'duration_factor': 0.5,
                'cancellation_factor': 0.7,
                'modification_factor': 1.0
            }
        })
    
    async def start(self) -> None:
        """Start the order generator."""
        await super().start()
        self.logger.info(f"Starting AI reactive burst order generation for symbols: {', '.join(self.symbols)}")
        
        # Start the AI prediction loop as a task
        asyncio.create_task(self._ai_prediction_loop())
    
    async def _ai_prediction_loop(self) -> None:
        """Loop for generating AI predictions and triggering bursts based on predictions."""
        try:
            while self._running:
                # Check if enough time has passed since last prediction
                current_time = time.time()
                if current_time - self.last_prediction_time < self.prediction_interval:
                    await asyncio.sleep(0.1)  # Check more frequently during waiting period
                    continue
                
                self.last_prediction_time = current_time
                
                # For each symbol, generate new predictions
                for symbol in self.symbols:
                    # Skip if we don't have enough market data
                    if not self._has_sufficient_market_data(symbol):
                        continue
                    
                    # Generate AI prediction for this symbol
                    prediction = self._generate_ai_prediction(symbol)
                    
                    # If prediction confidence exceeds threshold, schedule a reaction
                    if prediction and prediction['confidence'] > self.prediction_confidence_threshold:
                        # Calculate reaction time based on AI parameters and prediction type
                        reaction_time = self._calculate_ai_reaction_time(prediction['type'])
                        self.logger.info(f"AI prediction for {symbol}: {prediction['type']} with {prediction['confidence']:.2f} confidence. Reacting in {reaction_time:.3f}s")
                        
                        # Schedule a reaction after the calculated delay
                        asyncio.create_task(self._delayed_ai_reaction(symbol, prediction, reaction_time))
                
                # Sleep until next prediction cycle
                await asyncio.sleep(self.prediction_interval)
                
        except asyncio.CancelledError:
            self.logger.info("AI prediction loop cancelled")
        except Exception as e:
            self.logger.error(f"Error in AI prediction loop: {e}", exc_info=True)
    
    def _has_sufficient_market_data(self, symbol: str) -> bool:
        """Check if we have sufficient market data to make a prediction."""
        if symbol not in self.market_data_buffer:
            return False
        
        buffer = self.market_data_buffer[symbol]
        # Check if we have enough data points and recency
        return (len(buffer) >= 5 and 
                buffer[-1]['timestamp'] - buffer[0]['timestamp'] >= min(self.market_data_history, 5))
    
    def _generate_ai_prediction(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Generate an AI prediction for a symbol based on market data.
        
        Args:
            symbol: The trading symbol to generate prediction for
            
        Returns:
            Optional[Dict]: Prediction details or None if no prediction can be made
        """
        try:
            # Get market data history for this symbol
            market_data = self.market_data_buffer.get(symbol, [])
            if not market_data:
                return None
            
            # Extract recent price data
            recent_prices = [data.get('price', 0) for data in market_data if 'price' in data]
            recent_volumes = [data.get('volume', 0) for data in market_data if 'volume' in data]
            
            if len(recent_prices) < 3:
                return None
            
            # Calculate simple technical indicators
            price_change = recent_prices[-1] - recent_prices[0]
            price_change_pct = price_change / recent_prices[0] if recent_prices[0] > 0 else 0
            price_direction = 1 if price_change > 0 else -1 if price_change < 0 else 0
            
            # Calculate volatility (standard deviation of returns)
            if len(recent_prices) >= 3:
                returns = [(recent_prices[i] - recent_prices[i-1]) / recent_prices[i-1] 
                          for i in range(1, len(recent_prices))]
                volatility = np.std(returns) if returns else 0
            else:
                volatility = 0
            
            # Calculate volume trend
            volume_change = 0
            if len(recent_volumes) >= 2:
                volume_change = sum(recent_volumes[-2:]) / (2 * sum(recent_volumes[:len(recent_volumes)-2]) / len(recent_volumes[:len(recent_volumes)-2]) if len(recent_volumes[:len(recent_volumes)-2]) > 0 else 1)
            
            # Determine which strategy the AI would use based on market conditions and randomness
            # The sophistication level affects how much randomness vs. analysis is used
            random_factor = 1.0 - self.ai_sophistication
            analysis_factor = self.ai_sophistication
            
            # Calculate strategy scores
            strategy_scores = {
                'trend_following': (0.7 * abs(price_change_pct) * (1 if price_direction != 0 else 0) * analysis_factor +
                                  0.3 * random.random() * random_factor),
                
                'mean_reversion': (0.6 * (1 / (abs(price_change_pct) + 0.001)) * analysis_factor + 
                                 0.4 * random.random() * random_factor),
                
                'momentum': (0.8 * (abs(price_change_pct) * volume_change) * analysis_factor +
                           0.2 * random.random() * random_factor),
                
                'volatility_expansion': (0.9 * volatility * analysis_factor +
                                      0.1 * random.random() * random_factor)
            }
            
            # Select strategy with highest score
            prediction_type = max(strategy_scores.items(), key=lambda x: x[1])[0]
            
            # Calculate confidence - based on strategy score and AI sophistication
            # A more sophisticated AI has higher confidence when indicators are strong
            base_confidence = strategy_scores[prediction_type] / max(strategy_scores.values())
            sophistication_adjusted_confidence = base_confidence * (0.7 + 0.3 * self.ai_sophistication)
            
            # Calculate direction (1 = buy, -1 = sell) based on prediction type and market indicators
            if prediction_type == 'trend_following':
                direction = price_direction
            elif prediction_type == 'mean_reversion':
                direction = -price_direction  # Opposite of trend
            elif prediction_type == 'momentum':
                direction = price_direction  # Same as trend but more aggressive
            else:  # volatility_expansion
                # During volatility expansion, slightly favor the recent direction
                direction = price_direction if random.random() < 0.6 else -price_direction
            
            # Generate random price target based on prediction type
            current_price = recent_prices[-1]
            if prediction_type == 'trend_following':
                # Trend followers look for continuation
                price_target = current_price * (1 + 0.005 * direction)
            elif prediction_type == 'mean_reversion':
                # Mean reversers look for reversal to average
                avg_price = sum(recent_prices) / len(recent_prices)
                price_target = avg_price
            elif prediction_type == 'momentum':
                # Momentum traders look for larger moves
                price_target = current_price * (1 + 0.01 * direction)
            else:  # volatility_expansion
                # Volatility traders place wider targets
                price_target = current_price * (1 + 0.015 * direction * random.uniform(0.8, 1.2))
            
            # Create and return the prediction
            prediction = {
                'symbol': symbol,
                'type': prediction_type,
                'direction': direction,
                'price_target': price_target,
                'confidence': sophistication_adjusted_confidence,
                'timestamp': time.time(),
                'horizon': self.prediction_window
            }
            
            return prediction
            
        except Exception as e:
            self.logger.error(f"Error generating AI prediction for {symbol}: {e}")
            return None
    
    def _calculate_ai_reaction_time(self, prediction_type: str) -> float:
        """
        Calculate the reaction time for the AI based on its characteristics and prediction type.
        
        Args:
            prediction_type: The type of prediction that triggered the reaction
            
        Returns:
            float: Reaction time in seconds
        """
        # Base reaction time from configuration
        base_time = self.ai_reaction_time
        
        # Adjust based on AI aggression level
        # More aggressive AIs react faster
        aggression_factor = 1.0 - (0.5 * self.ai_aggression)
        
        # Adjust based on prediction type
        type_factor = 1.0
        if prediction_type == 'momentum':
            type_factor = 0.8  # Momentum strategies tend to be faster
        elif prediction_type == 'volatility_expansion':
            type_factor = 0.9  # Volatility strategies react relatively quickly
        elif prediction_type == 'trend_following':
            type_factor = 1.0  # Average reaction time
        elif prediction_type == 'mean_reversion':
            type_factor = 1.1  # Slightly slower
        
        # Add some randomness
        random_factor = random.uniform(0.9, 1.1)
        
        # Calculate final reaction time with a minimum floor
        reaction_time = max(0.05, base_time * aggression_factor * type_factor * random_factor)
        return reaction_time
    
    async def _delayed_ai_reaction(self, symbol: str, prediction: Dict[str, Any], delay: float) -> None:
        """
        Trigger an AI reaction after a specified delay.
        
        Args:
            symbol: The trading symbol
            prediction: The AI prediction details
            delay: Delay before reaction in seconds
        """
        try:
            # Wait for the AI's reaction time
            await asyncio.sleep(delay)
            
            # Check if we're still running and the prediction is still valid
            if not self._running or time.time() - prediction['timestamp'] > prediction['horizon']:
                return
                
            # Generate a burst based on the AI prediction
            await self._generate_ai_burst(symbol, prediction)
            
        except asyncio.CancelledError:
            self.logger.info(f"Delayed AI reaction cancelled for {symbol}")
        except Exception as e:
            self.logger.error(f"Error in delayed AI reaction for {symbol}: {e}")
    
    async def _generate_ai_burst(self, symbol: str, prediction: Dict[str, Any]) -> None:
        """
        Generate a burst of orders based on an AI prediction.
        
        Args:
            symbol: Symbol that the AI is trading
            prediction: AI prediction details
        """
        prediction_type = prediction['type']
        direction = prediction['direction']
        
        # Get strategy parameters for this prediction type
        strategy = self.ai_strategies.get(prediction_type, self.ai_strategies['trend_following'])
        
        # Calculate burst parameters based on the strategy and AI characteristics
        # Adjust burst size based on AI aggression and strategy
        size_factor = strategy['size_factor'] * (0.8 + 0.4 * self.ai_aggression)
        size_min = max(1, int(self.burst_size_min * size_factor))
        size_max = max(size_min + 1, int(self.burst_size_max * size_factor))
        burst_size = random.randint(size_min, size_max)
        
        # Adjust burst duration based on strategy
        duration_factor = strategy['duration_factor']
        duration_min = self.burst_duration_min * duration_factor
        duration_max = self.burst_duration_max * duration_factor
        burst_duration = random.uniform(duration_min, duration_max)
        
        # Get order type distribution for this strategy
        distribution = strategy.get('order_types', self.order_type_distribution)
        
        # Set burst state
        self.in_burst = True
        self.logger.info(f"Starting AI-driven {prediction_type} burst for {symbol}: {burst_size} orders over {burst_duration:.2f} seconds (direction: {'buy' if direction > 0 else 'sell'})")
        
        try:
            # Generate time points for orders - distribution depends on strategy type
            if prediction_type == 'momentum' or prediction_type == 'volatility_expansion':
                # Front-loaded distribution for aggressive strategies
                time_points = np.random.exponential(scale=burst_duration/3, size=burst_size)
            else:
                # More evenly distributed for measured strategies
                time_points = np.random.uniform(0, burst_duration, size=burst_size)
                
            time_points = np.sort([min(t, burst_duration) for t in time_points])
            
            # Determine if coordinated with other symbols (based on AI coordination parameter)
            coordinated = random.random() < self.ai_coordination
            
            # For coordinated strategies, we might involve related symbols
            if coordinated and len(self.symbols) > 1:
                related_symbols = self._get_related_symbols(symbol, prediction_type)
                # Add the primary symbol
                all_symbols = [symbol] + related_symbols
                
                # Weight by correlation/importance - primary symbol gets most weight
                if prediction_type == 'correlation':
                    # Equal weight for correlation strategies
                    symbol_weights = [1.0 / len(all_symbols) for _ in all_symbols]
                else:
                    # Primary symbol gets more weight for other strategies
                    symbol_weights = [0.6] + [(0.4 / len(related_symbols)) for _ in related_symbols]
            else:
                all_symbols = [symbol]
                symbol_weights = [1.0]
            
            last_time = 0
            for i, time_point in enumerate(time_points):
                # Wait until the next order time
                sleep_time = time_point - last_time
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                
                # Choose symbol - primary symbol is more likely
                chosen_symbol = random.choices(all_symbols, weights=symbol_weights, k=1)[0]
                
                # Adjust buy/sell probability based on prediction direction
                # Direction is -1 to 1, map to probability 0 to 1 for side distribution
                side_probability = (direction + 1) / 2  # Map from [-1, 1] to [0, 1]
                
                # Generate order with characteristics based on the AI strategy
                order = await self._generate_order(
                    chosen_symbol, 
                    distribution,
                    side_probability=side_probability,
                    price_target=prediction.get('price_target')
                )
                
                # For AI strategies, we track orders more carefully for later modification/cancellation
                order.metadata['ai_strategy'] = prediction_type
                order.metadata['prediction_confidence'] = prediction['confidence']
                
                self._notify_listeners(order)
                self.orders_in_bursts += 1
                self.order_store[order.order_id] = order
                
                last_time = time_point
            
            self.bursts_generated += 1
            self.logger.info(f"Completed AI {prediction_type} burst #{self.bursts_generated} with {burst_size} orders")
            
        except asyncio.CancelledError:
            self.logger.info("AI burst generation cancelled")
        except Exception as e:
            self.logger.error(f"Error generating AI burst: {e}", exc_info=True)
        finally:
            self.in_burst = False
    
    def _get_related_symbols(self, primary_symbol: str, strategy_type: str) -> List[str]:
        """
        Get a list of related symbols based on the primary symbol and strategy.
        
        Args:
            primary_symbol: The main symbol being traded
            strategy_type: The type of strategy being employed
            
        Returns:
            List[str]: Related symbols to include in coordinated trading
        """
        # Filter other symbols
        other_symbols = [s for s in self.symbols if s != primary_symbol]
        if not other_symbols:
            return []
            
        # How many related symbols to include
        num_related = min(int(len(other_symbols) * self.ai_coordination) + 1, len(other_symbols))
        if num_related <= 0:
            return []
            
        # For simplistic correlation, look for symbols with shared currency components
        if len(primary_symbol) >= 6 and any(len(s) >= 6 for s in other_symbols):
            # For forex pairs like 'EURUSD', 'GBPUSD', etc.
            base_curr = primary_symbol[:3]
            quote_curr = primary_symbol[3:6]
            
            # Prioritize symbols sharing same base or quote currency
            related = [s for s in other_symbols if 
                       (s.startswith(base_curr) or s.endswith(quote_curr)) and
                       len(s) >= 6]
            
            if related:
                # Take up to num_related symbols from related list
                return sorted(related)[:num_related]
        
        # If we don't have currency pairs or couldn't find related ones, just take random symbols
        return random.sample(other_symbols, min(num_related, len(other_symbols)))
    
    async def _generate_order(self, symbol: str, type_distribution: Optional[Dict[str, float]] = None,
                             side_probability: float = 0.5, price_target: Optional[float] = None) -> OrderData:
        """
        Generate an order with AI strategy characteristics.
        
        Args:
            symbol: The trading symbol
            type_distribution: Distribution of order types to use
            side_probability: Probability of generating a buy order (vs sell)
            price_target: Target price for the strategy
            
        Returns:
            OrderData: The generated order
        """
        # Override the side probability based on the AI's prediction direction
        side_distribution = {'buy': side_probability, 'sell': 1.0 - side_probability}
        
        # Call the parent class's _generate_order method with our custom distributions
        order = await super()._generate_order(symbol, type_distribution)
        
        # For limit and stop orders, adjust the price based on the AI's price target if provided
        if price_target is not None and order.order_type in ['limit', 'stop']:
            current_price = self._get_current_price(symbol)
            if current_price and order.side == 'buy':
                # For buy limit orders, price should be below market and below target
                if order.order_type == 'limit':
                    # Set limit price between current price and target if target is higher
                    if price_target > current_price:
                        order.price = current_price * 0.998  # Slightly below current price
                    else:
                        # Target is below current price - use a tighter spread to the target
                        order.price = price_target * random.uniform(0.999, 1.001)
                # For buy stop orders, price should be above market (breakout strategy)
                elif order.order_type == 'stop':
                    order.price = current_price * random.uniform(1.001, 1.003)
                    
            elif current_price and order.side == 'sell':
                # For sell limit orders, price should be above market and above target
                if order.order_type == 'limit':
                    # Set limit price between current price and target if target is lower
                    if price_target < current_price:
                        order.price = current_price * 1.002  # Slightly above current price
                    else:
                        # Target is above current price - use a tighter spread to the target
                        order.price = price_target * random.uniform(0.999, 1.001)
                # For sell stop orders, price should be below market (stop-loss strategy)
                elif order.order_type == 'stop':
                    order.price = current_price * random.uniform(0.997, 0.999)
        
        return order
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get the current price for a symbol from market data."""
        if not self.market_data_source:
            return None
            
        market_data = self.market_data_source.get_market_data(symbol)
        if not market_data:
            return None
            
        # Try different price representations
        if 'price' in market_data:
            return market_data['price']
        elif 'mid' in market_data:
            return market_data['mid']
        elif 'bid' in market_data and 'ask' in market_data:
            return (market_data['bid'] + market_data['ask']) / 2
            
        return None
    
    def update_market_data(self, data: MarketData) -> None:
        """
        Update market data and maintain history buffer.
        
        Args:
            data: Market data update
        """
        super().update_market_data(data)
        
        # Store into buffer for AI analysis
        symbol = data.symbol
        if symbol not in self.market_data_buffer:
            self.market_data_buffer[symbol] = []
            
        # Add the new data point
        self.market_data_buffer[symbol].append({
            'timestamp': time.time(),
            'price': data.price,
            'bid': data.bid,
            'ask': data.ask,
            'volume': data.volume
        })
        
        # Trim buffer to keep only recent history
        current_time = time.time()
        self.market_data_buffer[symbol] = [
            point for point in self.market_data_buffer[symbol]
            if current_time - point['timestamp'] <= self.market_data_history
        ]
    
    async def _generate_burst(self) -> None:
        """
        Generate a random burst without waiting for AI prediction.
        This is used for testing and when bursts are scheduled rather than AI-triggered.
        """
        # Choose a random strategy and symbol
        strategy_type = random.choices(
            list(self.ai_strategies.keys()),
            weights=[self.ai_strategies[s]['weight'] for s in self.ai_strategies],
            k=1
        )[0]
        symbol = random.choice(self.symbols)
        
        # Create a simulated prediction
        prediction = {
            'symbol': symbol,
            'type': strategy_type,
            'direction': random.choice([-1, 1]),
            'price_target': self._get_current_price(symbol) or 1.0,
            'confidence': random.uniform(0.7, 0.9),
            'timestamp': time.time(),
            'horizon': self.prediction_window
        }
        
        # Generate burst for this prediction
        await self._generate_ai_burst(symbol, prediction)


def create_burst_scenario(scenario_type: str, config: Dict[str, Any], logger: Optional[logging.Logger] = None) -> BurstOrderScenarioGenerator:
    """
    Factory method to create the appropriate burst scenario generator.
    
    Args:
        scenario_type: Type of burst scenario ('sudden', 'ramp', 'oscillating', 'market_event', 'ai_reactive')
        config: Configuration dictionary
        logger: Optional logger instance
        
    Returns:
        BurstOrderScenarioGenerator instance
        
    Raises:
        ValueError: If scenario_type is not recognized
    """
    if scenario_type == 'sudden':
        return SuddenBurstScenario(config, logger)
    elif scenario_type == 'ramp':
        return RampBurstScenario(config, logger)
    elif scenario_type == 'oscillating':
        return OscillatingBurstScenario(config, logger)
    elif scenario_type == 'market_event':
        return MarketEventBurstScenario(config, logger)
    elif scenario_type == 'ai_reactive':
        return AIReactiveBurstScenario(config, logger)
    else:
        raise ValueError(f"Unknown burst scenario type: {scenario_type}") 