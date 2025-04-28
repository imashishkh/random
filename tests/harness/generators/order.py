"""
Order Generators

This module provides generators for different types of order data,
including random orders, pattern-based orders, and burst orders.
"""

import asyncio
import random
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, AsyncIterator, Tuple
import numpy as np
import json
import os

from .base import OrderGenerator, OrderData, MarketDataTick
from .market_data import TickDataGenerator
from ..config import OrderGenerationConfig, PatternType


class RandomOrderGenerator(OrderGenerator):
    """
    Generator for random orders with configurable properties.
    """
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize random order generator.
        
        Args:
            config: Configuration dictionary
            logger: Optional logger instance
        """
        super().__init__(config, logger)
        
        # Extract config values
        self.order_types = config.get('order_types', ['market', 'limit'])
        self.size_min = config.get('size_min', 0.1)
        self.size_max = config.get('size_max', 10.0)
        self.limit_distance_min = config.get('limit_distance_min', 0.0001)
        self.limit_distance_max = config.get('limit_distance_max', 0.002)
        self.rate = config.get('rate', 1)  # Orders per second
        
        # Reference to a TickDataGenerator for price data
        self.tick_generator = None
        
        # Order count for ID generation
        self.order_counter = 0
        
        # Performance tracking
        self.perf_last_report = time.time()
        self.perf_count = 0
    
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
        self.logger.info(f"Starting random order generation at {self.rate} orders/sec for symbols: {', '.join(self.symbols)}")
        
        # Start the generation loop as a task
        asyncio.create_task(self._generation_loop())
    
    async def stop(self) -> None:
        """Stop the order generator."""
        await super().stop()
        self.logger.info("Stopped order generation")
    
    async def _generation_loop(self) -> None:
        """Main loop for generating orders."""
        interval = 1.0 / self.rate  # Time between orders in seconds
        
        try:
            while self._running:
                # Choose a random symbol from the list
                symbol = random.choice(self.symbols)
                
                # Generate order
                order = await self._generate_order(symbol)
                self._notify_listeners(order)
                self.perf_count += 1
                
                # Report performance stats periodically
                self._report_performance()
                
                # Sleep until next order
                await self._sleep_adjusted(interval)
                
                # Adjust interval if rate has changed
                interval = 1.0 / self.rate
        
        except asyncio.CancelledError:
            self.logger.info("Order generation loop cancelled")
        except Exception as e:
            self.logger.error(f"Error in order generation loop: {e}", exc_info=True)
    
    async def _generate_order(self, symbol: str) -> OrderData:
        """
        Generate a single order.
        
        Args:
            symbol: Symbol to generate order for
            
        Returns:
            OrderData instance
        """
        # Generate unique order ID
        self.order_counter += 1
        order_id = f"order_{self.order_counter}"
        
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
        
        # Random order type
        order_type = random.choice(self.order_types)
        
        # Random direction (buy/sell)
        direction = "buy" if random.random() < 0.5 else "sell"
        
        # Random size
        size = round(random.uniform(self.size_min, self.size_max), 2)
        
        # Price depends on order type
        price = None
        if order_type == 'market':
            # Market orders use current price
            price = current_price
        elif order_type == 'limit':
            # Limit orders are placed some distance from current price
            # Buy limits are below current price, sell limits are above
            distance = random.uniform(self.limit_distance_min, self.limit_distance_max)
            if direction == 'buy':
                price = current_price * (1 - distance)
            else:
                price = current_price * (1 + distance)
                
            # Round to appropriate number of decimals
            price = round(price, 5)
        elif order_type == 'stop':
            # Stop orders are placed some distance from current price
            # Buy stops are above current price, sell stops are below
            distance = random.uniform(self.limit_distance_min, self.limit_distance_max)
            if direction == 'buy':
                price = current_price * (1 + distance)
            else:
                price = current_price * (1 - distance)
                
            # Round to appropriate number of decimals
            price = round(price, 5)
        
        # Create order
        return OrderData(
            order_id=order_id,
            symbol=symbol,
            timestamp=datetime.now(),
            direction=direction,
            order_type=order_type,
            price=price,
            size=size
        )
    
    def _report_performance(self) -> None:
        """Report performance statistics periodically."""
        now = time.time()
        elapsed = now - self.perf_last_report
        
        # Report every 5 seconds
        if elapsed >= 5.0:
            rate = self.perf_count / elapsed
            self.logger.info(f"Performance: {rate:.2f} orders/sec (over {elapsed:.1f}s)")
            
            # Reset counters
            self.perf_last_report = now
            self.perf_count = 0


class BurstOrderGenerator(OrderGenerator):
    """
    Generator for bursts of orders with configurable properties.
    """
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize burst order generator.
        
        Args:
            config: Configuration dictionary
            logger: Optional logger instance
        """
        super().__init__(config, logger)
        
        # Extract config values
        self.order_types = config.get('order_types', ['market', 'limit'])
        self.size_min = config.get('size_min', 0.1)
        self.size_max = config.get('size_max', 10.0)
        self.limit_distance_min = config.get('limit_distance_min', 0.0001)
        self.limit_distance_max = config.get('limit_distance_max', 0.002)
        
        # Burst-specific parameters
        self.burst_size_min = config.get('burst_size_min', 10)
        self.burst_size_max = config.get('burst_size_max', 50)
        self.burst_interval_min = config.get('burst_interval_min', 5)
        self.burst_interval_max = config.get('burst_interval_max', 30)
        self.burst_duration_min = config.get('burst_duration_min', 0.5)
        self.burst_duration_max = config.get('burst_duration_max', 2.0)
        
        # Reference to a TickDataGenerator for price data
        self.tick_generator = None
        
        # Order count for ID generation
        self.order_counter = 0
        
        # Burst tracking
        self.bursts_generated = 0
        self.orders_in_bursts = 0
        self.in_burst = False
        self.burst_task = None
    
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
        self.logger.info(f"Starting burst order generation for symbols: {', '.join(self.symbols)}")
        
        # Start the burst scheduling loop as a task
        asyncio.create_task(self._burst_scheduling_loop())
    
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
        """Generate a burst of orders over a short period."""
        # Determine burst parameters
        burst_size = random.randint(self.burst_size_min, self.burst_size_max)
        burst_duration = random.uniform(self.burst_duration_min, self.burst_duration_max)
        interval = burst_duration / burst_size
        
        # Choose a random symbol for this burst
        symbol = random.choice(self.symbols)
        
        self.in_burst = True
        self.logger.info(f"Starting burst of {burst_size} orders over {burst_duration:.2f} seconds ({1/interval:.1f} orders/sec)")
        
        try:
            # Generate orders in the burst
            for i in range(burst_size):
                # Generate an order
                order = await self._generate_order(symbol)
                self._notify_listeners(order)
                self.orders_in_bursts += 1
                
                # Sleep until next order in burst
                if i < burst_size - 1:  # Don't sleep after the last order
                    await asyncio.sleep(interval)
            
            self.bursts_generated += 1
            self.logger.info(f"Completed burst #{self.bursts_generated} with {burst_size} orders")
            
        except asyncio.CancelledError:
            self.logger.info("Burst generation cancelled")
        except Exception as e:
            self.logger.error(f"Error generating burst: {e}", exc_info=True)
        finally:
            self.in_burst = False
    
    async def _generate_order(self, symbol: str) -> OrderData:
        """
        Generate a single order.
        
        Args:
            symbol: Symbol to generate order for
            
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
        
        # Random order type - in bursts, favor market orders
        if random.random() < 0.7:  # 70% market orders in bursts
            order_type = 'market'
        else:
            order_type = random.choice(self.order_types)
        
        # Random direction with slight bias in bursts
        # In a single burst, orders tend to have the same direction
        burst_bias = random.random()
        if burst_bias < 0.7:  # 70% chance of same direction in a burst
            direction = "buy" if random.random() < 0.5 else "sell"
        else:
            # Random direction
            direction = "buy" if random.random() < 0.5 else "sell"
        
        # Random size - make some orders in bursts larger
        if random.random() < 0.2:  # 20% chance of larger orders
            size = round(random.uniform(self.size_max / 2, self.size_max * 2), 2)
        else:
            size = round(random.uniform(self.size_min, self.size_max), 2)
        
        # Price depends on order type
        price = None
        if order_type == 'market':
            # Market orders use current price
            price = current_price
        elif order_type == 'limit':
            # Limit orders are placed some distance from current price
            # Buy limits are below current price, sell limits are above
            distance = random.uniform(self.limit_distance_min, self.limit_distance_max)
            if direction == 'buy':
                price = current_price * (1 - distance)
            else:
                price = current_price * (1 + distance)
                
            # Round to appropriate number of decimals
            price = round(price, 5)
        elif order_type == 'stop':
            # Stop orders are placed some distance from current price
            # Buy stops are above current price, sell stops are below
            distance = random.uniform(self.limit_distance_min, self.limit_distance_max)
            if direction == 'buy':
                price = current_price * (1 + distance)
            else:
                price = current_price * (1 - distance)
                
            # Round to appropriate number of decimals
            price = round(price, 5)
        
        # Create order
        return OrderData(
            order_id=order_id,
            symbol=symbol,
            timestamp=datetime.now(),
            direction=direction,
            order_type=order_type,
            price=price,
            size=size
        ) 


class PatternOrderGenerator(OrderGenerator):
    """
    Generator for orders following specific patterns.
    """
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize pattern-based order generator.
        
        Args:
            config: Configuration dictionary
            logger: Optional logger instance
        """
        super().__init__(config, logger)
        
        # Extract config values
        self.order_types = config.get('order_types', ['market', 'limit'])
        self.size_min = config.get('size_min', 0.1)
        self.size_max = config.get('size_max', 10.0)
        self.limit_distance_min = config.get('limit_distance_min', 0.0001)
        self.limit_distance_max = config.get('limit_distance_max', 0.002)
        self.rate = config.get('rate', 1)  # Orders per second
        
        # Pattern-specific parameters
        self.pattern_type = PatternType(config.get('pattern_type', 'normal'))
        self.custom_pattern_file = config.get('custom_pattern_file', None)
        self.pattern_cycle_time = config.get('pattern_cycle_time', 60)  # seconds
        
        # Reference to a TickDataGenerator for price data
        self.tick_generator = None
        
        # Order count for ID generation
        self.order_counter = 0
        
        # Pattern tracking
        self.pattern_start_time = time.time()
        self.custom_pattern = None
        self.cycle_position = 0
        
        # Performance tracking
        self.perf_last_report = time.time()
        self.perf_count = 0
        
        # Load custom pattern if specified
        if self.pattern_type == PatternType.CUSTOM and self.custom_pattern_file:
            self._load_custom_pattern()
    
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
        self.logger.info(f"Starting pattern-based order generation ({self.pattern_type.name}) at {self.rate} orders/sec for symbols: {', '.join(self.symbols)}")
        
        # Start the generation loop as a task
        asyncio.create_task(self._generation_loop())
    
    async def stop(self) -> None:
        """Stop the order generator."""
        await super().stop()
        self.logger.info("Stopped pattern-based order generation")
    
    async def _generation_loop(self) -> None:
        """Main loop for generating orders."""
        interval = 1.0 / self.rate  # Time between orders in seconds
        
        try:
            while self._running:
                # Choose a symbol from the list based on pattern
                symbol = self._select_symbol_for_pattern()
                
                # Generate order
                order = await self._generate_order(symbol)
                self._notify_listeners(order)
                self.perf_count += 1
                
                # Update pattern cycle position
                self._update_cycle_position()
                
                # Report performance stats periodically
                self._report_performance()
                
                # Sleep until next order
                await self._sleep_adjusted(interval)
                
                # Adjust interval if rate has changed
                interval = 1.0 / self.rate
        
        except asyncio.CancelledError:
            self.logger.info("Order generation loop cancelled")
        except Exception as e:
            self.logger.error(f"Error in order generation loop: {e}", exc_info=True)
    
    def _select_symbol_for_pattern(self) -> str:
        """
        Select a symbol based on the current pattern.
        
        Returns:
            Selected symbol
        """
        if self.pattern_type == PatternType.NORMAL:
            # Normal pattern: random selection
            return random.choice(self.symbols)
        
        elif self.pattern_type == PatternType.TRENDING:
            # Trending pattern: focus on one symbol for a while, then switch
            elapsed = time.time() - self.pattern_start_time
            
            # Switch focus every pattern_cycle_time / 4 seconds
            switch_time = self.pattern_cycle_time / 4
            
            # Use elapsed time to determine which symbol to focus on
            focus_index = int(elapsed / switch_time) % len(self.symbols)
            
            # 70% chance to use the focus symbol, 30% chance for others
            if random.random() < 0.7:
                return self.symbols[focus_index]
            else:
                return random.choice(self.symbols)
        
        elif self.pattern_type == PatternType.VOLATILE:
            # Volatile pattern: more randomized with some clustering
            return random.choice(self.symbols)
        
        elif self.pattern_type == PatternType.RANGE_BOUND:
            # Range-bound pattern: more evenly distributed
            return self.symbols[self.cycle_position % len(self.symbols)]
        
        elif self.pattern_type == PatternType.OPENING:
            # Opening pattern: concentrate at beginning of pattern cycle
            if self.cycle_position < 0.3:  # First 30% of cycle
                # Focus on a subset of symbols
                subset = self.symbols[:max(1, len(self.symbols) // 2)]
                return random.choice(subset)
            else:
                return random.choice(self.symbols)
        
        elif self.pattern_type == PatternType.CLOSING:
            # Closing pattern: concentrate at end of pattern cycle
            if self.cycle_position > 0.7:  # Last 30% of cycle
                # Focus on a subset of symbols
                subset = self.symbols[-max(1, len(self.symbols) // 2):]
                return random.choice(subset)
            else:
                return random.choice(self.symbols)
        
        elif self.pattern_type == PatternType.CUSTOM and self.custom_pattern:
            # Custom pattern based on loaded pattern file
            # Use cycle_position to determine which symbol to use
            if not self.custom_pattern or 'symbols' not in self.custom_pattern:
                return random.choice(self.symbols)
            
            symbol_weights = self.custom_pattern.get('symbols', {})
            
            # Find weights for current position in cycle
            position_weights = {}
            for symbol in self.symbols:
                if symbol in symbol_weights:
                    # Get weight array for this symbol
                    weights = symbol_weights[symbol]
                    
                    # Interpolate weight based on cycle position
                    idx = min(len(weights) - 1, int(self.cycle_position * len(weights)))
                    position_weights[symbol] = weights[idx]
                else:
                    # Default weight for symbols not in pattern
                    position_weights[symbol] = 1.0
            
            # Normalize weights
            total_weight = sum(position_weights.values())
            if total_weight > 0:
                for symbol in position_weights:
                    position_weights[symbol] /= total_weight
            else:
                # If all weights are zero, use equal weights
                for symbol in position_weights:
                    position_weights[symbol] = 1.0 / len(position_weights)
            
            # Select symbol based on weights
            symbols = list(position_weights.keys())
            weights = list(position_weights.values())
            
            return random.choices(symbols, weights=weights, k=1)[0]
        
        else:
            # Default to random selection
            return random.choice(self.symbols)
    
    def _update_cycle_position(self) -> None:
        """Update the position in the pattern cycle."""
        elapsed = time.time() - self.pattern_start_time
        
        # Convert elapsed time to a position in the cycle (0.0 to 1.0)
        self.cycle_position = (elapsed % self.pattern_cycle_time) / self.pattern_cycle_time
        
        # Check if we've completed a cycle
        if elapsed >= self.pattern_cycle_time and elapsed % self.pattern_cycle_time < 0.1:
            # Only log once per cycle (in the first 10% of the new cycle)
            if int(elapsed / self.pattern_cycle_time) > int((elapsed - 0.2) / self.pattern_cycle_time):
                self.logger.info(f"Completed pattern cycle #{int(elapsed / self.pattern_cycle_time)}")
    
    def _load_custom_pattern(self) -> None:
        """Load a custom pattern from a file."""
        try:
            if not os.path.exists(self.custom_pattern_file):
                self.logger.error(f"Custom pattern file not found: {self.custom_pattern_file}")
                return
                
            with open(self.custom_pattern_file, 'r') as f:
                self.custom_pattern = json.load(f)
            
            # Validate pattern structure
            if not isinstance(self.custom_pattern, dict):
                self.logger.error(f"Invalid custom pattern: must be a dictionary")
                self.custom_pattern = None
                return
                
            if 'symbols' not in self.custom_pattern:
                self.logger.error(f"Invalid custom pattern: missing 'symbols' section")
                self.custom_pattern = None
                return
                
            # Validate symbols section
            symbols = self.custom_pattern.get('symbols', {})
            if not isinstance(symbols, dict):
                self.logger.error(f"Invalid custom pattern: 'symbols' must be a dictionary")
                self.custom_pattern = None
                return
                
            for symbol, weights in symbols.items():
                if not isinstance(weights, list):
                    self.logger.error(f"Invalid custom pattern: weights for '{symbol}' must be a list")
                    self.custom_pattern = None
                    return
                    
                if not all(isinstance(w, (int, float)) for w in weights):
                    self.logger.error(f"Invalid custom pattern: weights for '{symbol}' must be numbers")
                    self.custom_pattern = None
                    return
            
            self.logger.info(f"Loaded custom pattern from {self.custom_pattern_file}")
            
        except Exception as e:
            self.logger.error(f"Error loading custom pattern: {e}", exc_info=True)
            self.custom_pattern = None
    
    async def _generate_order(self, symbol: str) -> OrderData:
        """
        Generate a single order based on the current pattern.
        
        Args:
            symbol: Symbol to generate order for
            
        Returns:
            OrderData instance
        """
        # Generate unique order ID
        self.order_counter += 1
        order_id = f"pattern_order_{self.order_counter}"
        
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
        
        # Determine order type based on pattern
        order_type = self._get_pattern_order_type()
        
        # Determine direction based on pattern
        direction = self._get_pattern_direction(symbol)
        
        # Determine size based on pattern
        size = self._get_pattern_size()
        
        # Price depends on order type and pattern
        price = None
        if order_type == 'market':
            # Market orders use current price
            price = current_price
        elif order_type == 'limit':
            # Limit orders are placed some distance from current price
            # Adjust distance based on pattern
            distance = self._get_pattern_distance()
            
            if direction == 'buy':
                price = current_price * (1 - distance)
            else:
                price = current_price * (1 + distance)
                
            # Round to appropriate number of decimals
            price = round(price, 5)
        elif order_type == 'stop':
            # Stop orders are placed some distance from current price
            # Adjust distance based on pattern
            distance = self._get_pattern_distance()
            
            if direction == 'buy':
                price = current_price * (1 + distance)
            else:
                price = current_price * (1 - distance)
                
            # Round to appropriate number of decimals
            price = round(price, 5)
        
        # Create order
        return OrderData(
            order_id=order_id,
            symbol=symbol,
            timestamp=datetime.now(),
            direction=direction,
            order_type=order_type,
            price=price,
            size=size
        )
    
    def _get_pattern_order_type(self) -> str:
        """
        Determine order type based on the current pattern.
        
        Returns:
            Order type (market, limit, stop)
        """
        if self.pattern_type == PatternType.NORMAL:
            # Normal pattern: balanced mix
            return random.choice(self.order_types)
            
        elif self.pattern_type == PatternType.TRENDING:
            # Trending pattern: more market orders
            weights = {'market': 0.6, 'limit': 0.3, 'stop': 0.1}
            order_types = [t for t in self.order_types if t in weights]
            weights_list = [weights[t] for t in order_types]
            
            # Normalize weights
            total = sum(weights_list)
            if total > 0:
                weights_list = [w / total for w in weights_list]
                
            return random.choices(order_types, weights=weights_list, k=1)[0]
            
        elif self.pattern_type == PatternType.VOLATILE:
            # Volatile pattern: more stops and limits
            weights = {'market': 0.4, 'limit': 0.3, 'stop': 0.3}
            order_types = [t for t in self.order_types if t in weights]
            weights_list = [weights[t] for t in order_types]
            
            # Normalize weights
            total = sum(weights_list)
            if total > 0:
                weights_list = [w / total for w in weights_list]
                
            return random.choices(order_types, weights=weights_list, k=1)[0]
            
        elif self.pattern_type == PatternType.RANGE_BOUND:
            # Range-bound pattern: more limits
            weights = {'market': 0.3, 'limit': 0.6, 'stop': 0.1}
            order_types = [t for t in self.order_types if t in weights]
            weights_list = [weights[t] for t in order_types]
            
            # Normalize weights
            total = sum(weights_list)
            if total > 0:
                weights_list = [w / total for w in weights_list]
                
            return random.choices(order_types, weights=weights_list, k=1)[0]
            
        elif self.pattern_type == PatternType.OPENING:
            # Opening pattern: more market orders at beginning, more limits later
            if self.cycle_position < 0.3:
                # More market orders at beginning
                weights = {'market': 0.8, 'limit': 0.1, 'stop': 0.1}
            else:
                # More limits and stops later
                weights = {'market': 0.3, 'limit': 0.5, 'stop': 0.2}
                
            order_types = [t for t in self.order_types if t in weights]
            weights_list = [weights[t] for t in order_types]
            
            # Normalize weights
            total = sum(weights_list)
            if total > 0:
                weights_list = [w / total for w in weights_list]
                
            return random.choices(order_types, weights=weights_list, k=1)[0]
            
        elif self.pattern_type == PatternType.CLOSING:
            # Closing pattern: more limits at beginning, more market orders later
            if self.cycle_position < 0.7:
                # More limits and stops at beginning
                weights = {'market': 0.2, 'limit': 0.6, 'stop': 0.2}
            else:
                # More market orders later
                weights = {'market': 0.7, 'limit': 0.2, 'stop': 0.1}
                
            order_types = [t for t in self.order_types if t in weights]
            weights_list = [weights[t] for t in order_types]
            
            # Normalize weights
            total = sum(weights_list)
            if total > 0:
                weights_list = [w / total for w in weights_list]
                
            return random.choices(order_types, weights=weights_list, k=1)[0]
            
        elif self.pattern_type == PatternType.CUSTOM and self.custom_pattern:
            # Custom pattern
            if 'order_types' in self.custom_pattern:
                weights = self.custom_pattern['order_types']
                
                # Get weight array for each order type
                if all(isinstance(weights.get(t, []), list) for t in self.order_types):
                    # Get weights for current cycle position
                    pos_weights = {}
                    for t in self.order_types:
                        if t in weights:
                            # Get weight array for this type
                            type_weights = weights[t]
                            
                            # Interpolate weight based on cycle position
                            idx = min(len(type_weights) - 1, int(self.cycle_position * len(type_weights)))
                            pos_weights[t] = type_weights[idx]
                        else:
                            # Default weight
                            pos_weights[t] = 1.0
                    
                    # Normalize weights
                    total_weight = sum(pos_weights.values())
                    if total_weight > 0:
                        for t in pos_weights:
                            pos_weights[t] /= total_weight
                    else:
                        # If all weights are zero, use equal weights
                        for t in pos_weights:
                            pos_weights[t] = 1.0 / len(pos_weights)
                    
                    # Select order type based on weights
                    order_types = list(pos_weights.keys())
                    weights_list = list(pos_weights.values())
                    
                    return random.choices(order_types, weights=weights_list, k=1)[0]
            
            # Default to random choice if custom pattern doesn't specify order types
            return random.choice(self.order_types)
        
        else:
            # Default to random choice
            return random.choice(self.order_types)
    
    def _get_pattern_direction(self, symbol: str) -> str:
        """
        Determine direction based on the current pattern.
        
        Args:
            symbol: Symbol to determine direction for
            
        Returns:
            Direction (buy, sell)
        """
        if self.pattern_type == PatternType.NORMAL:
            # Normal pattern: balanced
            return "buy" if random.random() < 0.5 else "sell"
            
        elif self.pattern_type == PatternType.TRENDING:
            # Trending pattern: direction depends on position in cycle
            # First half of cycle: trend up (more buys)
            # Second half: trend down (more sells)
            if self.cycle_position < 0.5:
                return "buy" if random.random() < 0.7 else "sell"
            else:
                return "sell" if random.random() < 0.7 else "buy"
            
        elif self.pattern_type == PatternType.VOLATILE:
            # Volatile pattern: more balanced but with short-term biases
            # Create biases that shift every 10% of the cycle
            bias_period = int(self.cycle_position * 10) % 10
            if bias_period % 2 == 0:
                return "buy" if random.random() < 0.6 else "sell"
            else:
                return "sell" if random.random() < 0.6 else "buy"
            
        elif self.pattern_type == PatternType.RANGE_BOUND:
            # Range-bound pattern: alternating bias
            # Buy at bottom of range, sell at top
            if self.cycle_position < 0.25 or (self.cycle_position >= 0.5 and self.cycle_position < 0.75):
                return "buy" if random.random() < 0.7 else "sell"
            else:
                return "sell" if random.random() < 0.7 else "buy"
            
        elif self.pattern_type == PatternType.OPENING:
            # Opening pattern: more buys at beginning
            if self.cycle_position < 0.3:
                return "buy" if random.random() < 0.7 else "sell"
            else:
                return "buy" if random.random() < 0.5 else "sell"
            
        elif self.pattern_type == PatternType.CLOSING:
            # Closing pattern: more sells at end
            if self.cycle_position > 0.7:
                return "sell" if random.random() < 0.7 else "buy"
            else:
                return "buy" if random.random() < 0.5 else "sell"
            
        elif self.pattern_type == PatternType.CUSTOM and self.custom_pattern:
            # Custom pattern
            if 'directions' in self.custom_pattern:
                directions = self.custom_pattern['directions']
                
                # Check if we have direction weights for this symbol
                if symbol in directions:
                    symbol_dirs = directions[symbol]
                    
                    if 'buy' in symbol_dirs and 'sell' in symbol_dirs:
                        # Get weight arrays
                        buy_weights = symbol_dirs['buy']
                        sell_weights = symbol_dirs['sell']
                        
                        if isinstance(buy_weights, list) and isinstance(sell_weights, list):
                            # Interpolate weights based on cycle position
                            idx_buy = min(len(buy_weights) - 1, int(self.cycle_position * len(buy_weights)))
                            idx_sell = min(len(sell_weights) - 1, int(self.cycle_position * len(sell_weights)))
                            
                            buy_weight = buy_weights[idx_buy]
                            sell_weight = sell_weights[idx_sell]
                            
                            # Normalize weights
                            total = buy_weight + sell_weight
                            if total > 0:
                                buy_prob = buy_weight / total
                                return "buy" if random.random() < buy_prob else "sell"
                
                # Check if we have a default direction pattern
                if '_default' in directions:
                    default_dirs = directions['_default']
                    
                    if 'buy' in default_dirs and 'sell' in default_dirs:
                        # Get weight arrays
                        buy_weights = default_dirs['buy']
                        sell_weights = default_dirs['sell']
                        
                        if isinstance(buy_weights, list) and isinstance(sell_weights, list):
                            # Interpolate weights based on cycle position
                            idx_buy = min(len(buy_weights) - 1, int(self.cycle_position * len(buy_weights)))
                            idx_sell = min(len(sell_weights) - 1, int(self.cycle_position * len(sell_weights)))
                            
                            buy_weight = buy_weights[idx_buy]
                            sell_weight = sell_weights[idx_sell]
                            
                            # Normalize weights
                            total = buy_weight + sell_weight
                            if total > 0:
                                buy_prob = buy_weight / total
                                return "buy" if random.random() < buy_prob else "sell"
            
            # Default to random direction if custom pattern doesn't specify directions
            return "buy" if random.random() < 0.5 else "sell"
        
        else:
            # Default to random direction
            return "buy" if random.random() < 0.5 else "sell"
    
    def _get_pattern_size(self) -> float:
        """
        Determine order size based on the current pattern.
        
        Returns:
            Order size
        """
        if self.pattern_type == PatternType.NORMAL:
            # Normal pattern: uniform distribution
            return round(random.uniform(self.size_min, self.size_max), 2)
            
        elif self.pattern_type == PatternType.TRENDING:
            # Trending pattern: size increases over the cycle
            min_size = self.size_min
            max_size = self.size_max
            
            # Adjust size range based on position in cycle
            cycle_factor = self.cycle_position
            adjusted_min = min_size + (max_size - min_size) * 0.3 * cycle_factor
            adjusted_max = min_size + (max_size - min_size) * (0.7 + 0.3 * cycle_factor)
            
            return round(random.uniform(adjusted_min, adjusted_max), 2)
            
        elif self.pattern_type == PatternType.VOLATILE:
            # Volatile pattern: wider range with occasional large orders
            if random.random() < 0.1:  # 10% chance of large order
                return round(random.uniform(self.size_max * 0.7, self.size_max * 2), 2)
            else:
                return round(random.uniform(self.size_min, self.size_max), 2)
            
        elif self.pattern_type == PatternType.RANGE_BOUND:
            # Range-bound pattern: more consistent sizes
            mid_size = (self.size_min + self.size_max) / 2
            range_width = (self.size_max - self.size_min) * 0.6  # Narrower range
            
            return round(random.uniform(mid_size - range_width/2, mid_size + range_width/2), 2)
            
        elif self.pattern_type == PatternType.OPENING:
            # Opening pattern: larger sizes at beginning
            if self.cycle_position < 0.3:
                # Larger orders at beginning
                return round(random.uniform(self.size_max * 0.5, self.size_max * 1.5), 2)
            else:
                # Normal sized orders later
                return round(random.uniform(self.size_min, self.size_max), 2)
            
        elif self.pattern_type == PatternType.CLOSING:
            # Closing pattern: larger sizes at end
            if self.cycle_position > 0.7:
                # Larger orders at end
                return round(random.uniform(self.size_max * 0.5, self.size_max * 1.5), 2)
            else:
                # Normal sized orders earlier
                return round(random.uniform(self.size_min, self.size_max), 2)
            
        elif self.pattern_type == PatternType.CUSTOM and self.custom_pattern:
            # Custom pattern
            if 'sizes' in self.custom_pattern:
                sizes = self.custom_pattern['sizes']
                
                if isinstance(sizes, list) and len(sizes) > 1:
                    # Size array specifies [min_size, max_size] at different points in the cycle
                    
                    # Get min and max for current cycle position
                    idx = min(len(sizes) - 1, int(self.cycle_position * len(sizes)))
                    
                    if isinstance(sizes[idx], list) and len(sizes[idx]) >= 2:
                        min_size = sizes[idx][0]
                        max_size = sizes[idx][1]
                        
                        return round(random.uniform(min_size, max_size), 2)
            
            # Default to normal range if custom pattern doesn't specify sizes
            return round(random.uniform(self.size_min, self.size_max), 2)
        
        else:
            # Default to uniform distribution
            return round(random.uniform(self.size_min, self.size_max), 2)
    
    def _get_pattern_distance(self) -> float:
        """
        Determine order distance (for limit and stop orders) based on the current pattern.
        
        Returns:
            Distance as a decimal (e.g., 0.001 = 0.1%)
        """
        if self.pattern_type == PatternType.NORMAL:
            # Normal pattern: uniform distribution
            return random.uniform(self.limit_distance_min, self.limit_distance_max)
            
        elif self.pattern_type == PatternType.TRENDING:
            # Trending pattern: further distances in direction of trend
            # First half of cycle: trend up (buys closer, sells further)
            # Second half: trend down (sells closer, buys further)
            if self.cycle_position < 0.5:
                # Trend up
                if random.random() < 0.7:  # Direction probability
                    # More buys in trend up, place closer
                    return random.uniform(self.limit_distance_min, 
                                        (self.limit_distance_min + self.limit_distance_max) / 2)
                else:
                    # Sells in trend up, place further
                    return random.uniform((self.limit_distance_min + self.limit_distance_max) / 2,
                                        self.limit_distance_max * 1.5)
            else:
                # Trend down
                if random.random() < 0.7:  # Direction probability  
                    # More sells in trend down, place closer
                    return random.uniform(self.limit_distance_min,
                                        (self.limit_distance_min + self.limit_distance_max) / 2)
                else:
                    # Buys in trend down, place further
                    return random.uniform((self.limit_distance_min + self.limit_distance_max) / 2,
                                        self.limit_distance_max * 1.5)
            
        elif self.pattern_type == PatternType.VOLATILE:
            # Volatile pattern: wider range of distances
            return random.uniform(self.limit_distance_min, self.limit_distance_max * 2)
            
        elif self.pattern_type == PatternType.RANGE_BOUND:
            # Range-bound pattern: distances correlate with cycle position
            # Near bottom of range (buys closer, sells further)
            # Near top of range (sells closer, buys further)
            cycle_mod = self.cycle_position % 0.5  # 0-0.5 range repeating
            
            if cycle_mod < 0.25:  # Bottom half of range
                factor = 1 - (cycle_mod / 0.25)  # 1.0 at bottom, 0.0 at middle
                if random.random() < 0.7:  # Direction probability
                    # More buys at bottom, place closer
                    max_dist = self.limit_distance_min + (self.limit_distance_max - self.limit_distance_min) * 0.7
                    return random.uniform(self.limit_distance_min, max_dist)
                else:
                    # Sells at bottom, place further
                    min_dist = self.limit_distance_min + (self.limit_distance_max - self.limit_distance_min) * 0.3
                    max_dist = self.limit_distance_max * (1 + 0.5 * factor)
                    return random.uniform(min_dist, max_dist)
            else:  # Top half of range
                factor = (cycle_mod - 0.25) / 0.25  # 0.0 at middle, 1.0 at top
                if random.random() < 0.7:  # Direction probability
                    # More sells at top, place closer
                    max_dist = self.limit_distance_min + (self.limit_distance_max - self.limit_distance_min) * 0.7
                    return random.uniform(self.limit_distance_min, max_dist)
                else:
                    # Buys at top, place further
                    min_dist = self.limit_distance_min + (self.limit_distance_max - self.limit_distance_min) * 0.3
                    max_dist = self.limit_distance_max * (1 + 0.5 * factor)
                    return random.uniform(min_dist, max_dist)
            
        elif self.pattern_type == PatternType.OPENING:
            # Opening pattern: closer at beginning
            if self.cycle_position < 0.3:
                return random.uniform(self.limit_distance_min, 
                                     (self.limit_distance_min + self.limit_distance_max) / 2)
            else:
                return random.uniform(self.limit_distance_min, self.limit_distance_max)
            
        elif self.pattern_type == PatternType.CLOSING:
            # Closing pattern: closer at end
            if self.cycle_position > 0.7:
                return random.uniform(self.limit_distance_min, 
                                     (self.limit_distance_min + self.limit_distance_max) / 2)
            else:
                return random.uniform(self.limit_distance_min, self.limit_distance_max)
            
        elif self.pattern_type == PatternType.CUSTOM and self.custom_pattern:
            # Custom pattern
            if 'distances' in self.custom_pattern:
                distances = self.custom_pattern['distances']
                
                if isinstance(distances, list) and len(distances) > 1:
                    # Distance array specifies [min_distance, max_distance] at different points in the cycle
                    
                    # Get min and max for current cycle position
                    idx = min(len(distances) - 1, int(self.cycle_position * len(distances)))
                    
                    if isinstance(distances[idx], list) and len(distances[idx]) >= 2:
                        min_distance = distances[idx][0]
                        max_distance = distances[idx][1]
                        
                        return random.uniform(min_distance, max_distance)
            
            # Default to normal range if custom pattern doesn't specify distances
            return random.uniform(self.limit_distance_min, self.limit_distance_max)
        
        else:
            # Default to uniform distribution
            return random.uniform(self.limit_distance_min, self.limit_distance_max)
    
    def _report_performance(self) -> None:
        """Report performance statistics periodically."""
        now = time.time()
        elapsed = now - self.perf_last_report
        
        # Report every 5 seconds
        if elapsed >= 5.0:
            rate = self.perf_count / elapsed
            pattern_name = self.pattern_type.name if self.pattern_type else "unknown"
            cycle_pos = f"{self.cycle_position:.2f}"
            
            self.logger.info(f"Performance: {rate:.2f} orders/sec (over {elapsed:.1f}s) | Pattern: {pattern_name} | Cycle: {cycle_pos}")
            
            # Reset counters
            self.perf_last_report = now
            self.perf_count = 0 