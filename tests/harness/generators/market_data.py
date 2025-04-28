"""
Market Data Generators

This module provides generators for different types of market data,
including tick data, trade data, order book data, and candle data.
"""

import asyncio
import random
import math
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, AsyncIterator, Tuple, Callable
import logging
from pathlib import Path
import json
import yaml
import time

from .base import MarketDataGenerator, MarketDataTick, MarketDataTrade, OrderBookSnapshot, CandleData
from .base import OrderBookLevel, MarketData
from ..config import MarketDataType, PatternType


class TickDataGenerator(MarketDataGenerator):
    """Generator for high-frequency tick data."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the tick data generator.
        
        Args:
            config: Configuration dictionary
            logger: Optional logger instance
        """
        super().__init__(config, logger)
        
        # Initialize base prices for each symbol
        self.base_prices = self._initialize_base_prices()
        
        # Store current prices
        self.current_prices = self.base_prices.copy()
        
        # Pattern-specific settings
        if self.pattern == PatternType.VOLATILE:
            self.volatility_multiplier = 5.0
        elif self.pattern in [PatternType.TRENDING_UP, PatternType.TRENDING_DOWN]:
            self.trend_strength = 0.0001  # 0.01% per tick on average
            self.trend_direction = 1 if self.pattern == PatternType.TRENDING_UP else -1
        elif self.pattern == PatternType.RANGE_BOUND:
            self.range_width = 0.002  # 0.2% range
            self.range_centers = {symbol: price for symbol, price in self.base_prices.items()}
        elif self.pattern == PatternType.CUSTOM:
            self.custom_pattern = self._load_custom_pattern()
            self.pattern_index = 0
        elif self.pattern == PatternType.CYCLICAL:
            # Initialize cyclical pattern parameters
            self.cycle_amplitude = config.get('cycle_amplitude', 0.01)
            self.cycle_frequency = config.get('cycle_frequency', 0.005)
            self.cycle_phase_offset = config.get('cycle_phase_offset', 0)
            self.cycle_tick_count = 0
        elif self.pattern == PatternType.MULTI_PHASE:
            # Initialize multi-phase pattern parameters
            self.phases = config.get('phases', [
                {'type': PatternType.NORMAL, 'duration': 5000, 'weight': 1.0},
                {'type': PatternType.VOLATILE, 'duration': 2000, 'weight': 1.0},
                {'type': PatternType.TRENDING_UP, 'duration': 3000, 'weight': 1.0}
            ])
            self.transition_ticks = config.get('transition_ticks', 500)
            self.current_phase_index = 0
            self.current_phase_tick = 0
            self.phase_transition_progress = 0
            
            # Initialize temporary pattern parameters for the current phase
            self._initialize_phase_parameters(self.phases[0]['type'])
        elif self.pattern == PatternType.STRESS_TEST:
            # Initialize stress test pattern parameters
            self.base_pattern = config.get('base_pattern', PatternType.NORMAL)
            self.stress_events = config.get('stress_events', [])
            self.tick_count = 0
            
            # Sort stress events by tick for efficient lookup
            self.stress_events.sort(key=lambda x: x['tick'])
            
            # Active stress events
            self.active_stress_events = []
            
            # Initialize base pattern parameters
            self._initialize_base_pattern_parameters()
            
        # Time tracking
        self.start_time = None
        self.tick_count = 0
        
        # Performance tracking
        self.perf_last_report = time.time()
        self.perf_count = 0

    async def start(self) -> None:
        """Start the tick data generator."""
        await super().start()
        self.start_time = datetime.now()
        self.logger.info(f"Starting tick data generation at {self.rate} ticks/sec for symbols: {', '.join(self.symbols)}")
        
        # Start the generation loop as a task
        asyncio.create_task(self._generation_loop())
    
    async def stop(self) -> None:
        """Stop the tick data generator."""
        await super().stop()
        self.logger.info(f"Stopped tick data generation after {self.tick_count} ticks")
        
    async def _generation_loop(self) -> None:
        """Main loop for generating tick data."""
        interval = 1.0 / self.rate  # Time between ticks in seconds
        
        try:
            self.logger.debug(f"Starting generation loop with interval {interval:.6f} seconds")
            
            while self._running:
                # Generate tick for each symbol
                for symbol in self.symbols:
                    tick = await self._generate_tick(symbol)
                    self._notify_listeners(tick)
                    self.tick_count += 1
                    self.perf_count += 1
                
                # Report performance stats periodically
                self._report_performance()
                
                # Sleep until next tick
                await self._sleep_adjusted(interval)
                
                # Adjust interval if rate has changed
                interval = 1.0 / self.rate
        
        except asyncio.CancelledError:
            self.logger.info("Tick generation loop cancelled")
        except Exception as e:
            self.logger.error(f"Error in tick generation loop: {e}", exc_info=True)
    
    async def generate_data(self) -> AsyncIterator[MarketData]:
        """
        Generate market data.
        
        Returns:
            AsyncIterator yielding MarketDataTick objects
        """
        interval = 1.0 / self.rate  # Time between ticks in seconds
        
        while self._running:
            for symbol in self.symbols:
                tick = await self._generate_tick(symbol)
                yield tick
            
            # Sleep until next tick
            await self._sleep_adjusted(interval)
            
            # Adjust interval if rate has changed
            interval = 1.0 / self.rate
    
    async def _generate_tick(self, symbol: str) -> MarketDataTick:
        """
        Generate a single market data tick.
        
        Args:
            symbol: Symbol to generate data for
            
        Returns:
            MarketDataTick instance
        """
        # Get current mid price
        current_price = self.current_prices[symbol]
        
        # Apply pattern-specific price changes
        new_price = self._apply_pattern(symbol, current_price)
        
        # Calculate spread based on volatility
        spread = self._calculate_spread(symbol, new_price)
        
        # Calculate bid and ask
        bid = new_price - spread / 2
        ask = new_price + spread / 2
        
        # Update current price
        self.current_prices[symbol] = new_price
        
        # Create tick
        return MarketDataTick(
            symbol=symbol,
            timestamp=datetime.now(),
            bid=round(bid, 5),
            ask=round(ask, 5)
        )
    
    def _initialize_base_prices(self) -> Dict[str, float]:
        """
        Initialize realistic base prices for each symbol.
        
        Returns:
            Dictionary mapping symbols to base prices
        """
        # Realistic base prices for common forex pairs
        common_prices = {
            'EURUSD': 1.08,
            'GBPUSD': 1.25,
            'USDJPY': 150.0,
            'AUDUSD': 0.65,
            'USDCAD': 1.35,
            'NZDUSD': 0.60,
            'USDCHF': 0.90,
            'EURGBP': 0.85,
            'EURJPY': 160.0,
            'GBPJPY': 190.0
        }
        
        # Use common prices if available, otherwise generate random prices
        base_prices = {}
        for symbol in self.symbols:
            if symbol in common_prices:
                base_prices[symbol] = common_prices[symbol]
            else:
                # Generate random price between 0.5 and 2.0
                base_prices[symbol] = random.uniform(0.5, 2.0)
                
        return base_prices
    
    def _apply_pattern(self, symbol: str, current_price: float) -> float:
        """
        Apply the current pattern to update the price.
        
        Args:
            symbol: Symbol to update
            current_price: Current price
            
        Returns:
            New price after applying pattern
        """
        if self.pattern == PatternType.NORMAL:
            # Random walk with small steps
            step = random.normalvariate(0, self.volatility * current_price)
            return max(0.00001, current_price + step)
            
        elif self.pattern == PatternType.VOLATILE:
            # Random walk with larger steps
            step = random.normalvariate(0, self.volatility * current_price * self.volatility_multiplier)
            return max(0.00001, current_price + step)
            
        elif self.pattern in [PatternType.TRENDING_UP, PatternType.TRENDING_DOWN]:
            # Trending with noise
            trend = self.trend_strength * current_price * self.trend_direction
            noise = random.normalvariate(0, self.volatility * current_price)
            return max(0.00001, current_price + trend + noise)
            
        elif self.pattern == PatternType.RANGE_BOUND:
            # Mean reversion within a range
            center = self.range_centers[symbol]
            range_min = center * (1 - self.range_width / 2)
            range_max = center * (1 + self.range_width / 2)
            
            # Calculate mean reversion force
            distance_from_center = current_price - center
            reversion = -distance_from_center * 0.05  # 5% reversion towards center
            
            # Add noise
            noise = random.normalvariate(0, self.volatility * current_price)
            
            # Calculate new price and constrain to range
            new_price = current_price + reversion + noise
            return max(range_min, min(range_max, new_price))
            
        elif self.pattern == PatternType.OPENING:
            # Higher volatility with slight upward drift
            drift = 0.00005 * current_price  # Slight upward drift
            volatility_factor = 2.0  # Higher volatility during opening
            step = random.normalvariate(drift, self.volatility * current_price * volatility_factor)
            return max(0.00001, current_price + step)
            
        elif self.pattern == PatternType.CLOSING:
            # Declining volatility with slight convergence
            center = self.base_prices[symbol]
            reversion = (center - current_price) * 0.01  # Slight reversion to base price
            volatility_factor = 1.5  # Higher than normal, lower than opening
            step = random.normalvariate(reversion, self.volatility * current_price * volatility_factor)
            return max(0.00001, current_price + step)
            
        elif self.pattern == PatternType.CUSTOM and self.custom_pattern:
            # Apply custom pattern if available
            if not self.custom_pattern:
                return current_price
                
            pattern_length = len(self.custom_pattern['modifiers'])
            if pattern_length == 0:
                return current_price
                
            # Get current pattern value and advance index
            modifier = self.custom_pattern['modifiers'][self.pattern_index]
            self.pattern_index = (self.pattern_index + 1) % pattern_length
            
            # Apply modifier to price
            if self.custom_pattern['type'] == 'absolute':
                return modifier
            elif self.custom_pattern['type'] == 'relative':
                return current_price * (1 + modifier)
            elif self.custom_pattern['type'] == 'additive':
                return current_price + modifier
            else:
                return current_price
        
        elif self.pattern == PatternType.CYCLICAL:
            # Oscillating price with sinusoidal pattern
            
            # Increment tick counter
            self.cycle_tick_count += 1
            
            # Calculate phase position
            phase = self.cycle_phase_offset + self.cycle_frequency * self.cycle_tick_count
            
            # Apply sinusoidal oscillation
            oscillation = math.sin(2 * math.pi * phase) * self.cycle_amplitude
            
            # Add random noise for realism
            noise = random.normalvariate(0, self.volatility * current_price)
            
            # Apply to current price
            return max(0.00001, current_price * (1 + oscillation) + noise)
        
        elif self.pattern == PatternType.MULTI_PHASE:
            # Apply current phase pattern and handle transitions
            
            # Get current phase information
            current_phase = self.phases[self.current_phase_index]
            next_phase_index = (self.current_phase_index + 1) % len(self.phases)
            next_phase = self.phases[next_phase_index]
            
            # Update phase tracking
            self.current_phase_tick += 1
            
            # Check if we need to transition to next phase
            if self.current_phase_tick >= current_phase['duration']:
                # Reset counters and move to next phase
                self.current_phase_tick = 0
                self.current_phase_index = next_phase_index
                self.phase_transition_progress = 0
                
                # Initialize parameters for the next phase
                self._initialize_phase_parameters(PatternType(next_phase['type']))
                
                # Handle transition if needed
                if self.transition_ticks > 0:
                    self.phase_transition_progress = 1  # Start transition
            
            # Handle phase transition
            if self.phase_transition_progress > 0 and self.transition_ticks > 0:
                # Calculate transition progress (0 to 1)
                transition_progress = min(1.0, self.current_phase_tick / self.transition_ticks)
                
                # Apply current phase pattern
                current_phase_price = self._apply_specific_pattern(
                    PatternType(current_phase['type']), 
                    symbol, 
                    current_price
                )
                
                # Apply next phase pattern
                next_phase_price = self._apply_specific_pattern(
                    PatternType(next_phase['type']), 
                    symbol, 
                    current_price
                )
                
                # Blend based on transition progress
                return (1 - transition_progress) * current_phase_price + transition_progress * next_phase_price
            else:
                # Apply current phase pattern directly
                return self._apply_specific_pattern(
                    PatternType(current_phase['type']), 
                    symbol, 
                    current_price
                )
        
        elif self.pattern == PatternType.STRESS_TEST:
            # Apply base pattern with stress events
            
            # Increment tick counter
            self.tick_count += 1
            
            # Check for new stress events to activate
            for event in self.stress_events:
                if event['tick'] == self.tick_count:
                    self.active_stress_events.append({
                        'type': event['type'],
                        'magnitude': event['magnitude'],
                        'remaining_ticks': event['duration'],
                        'current_tick': 0
                    })
                    self.logger.info(f"Activated stress event: {event['type']} with magnitude {event['magnitude']}")
            
            # Apply base pattern
            base_price = self._apply_specific_pattern(self.base_pattern, symbol, current_price)
            
            # Apply active stress events
            price = base_price
            remaining_events = []
            
            for event in self.active_stress_events:
                event['current_tick'] += 1
                
                if event['current_tick'] <= event['remaining_ticks']:
                    # Event still active, apply effect
                    if event['type'] == 'crash':
                        # Sharp decline followed by recovery
                        progress = event['current_tick'] / event['remaining_ticks']
                        if progress < 0.2:  # Initial crash phase
                            # Sharp drop
                            crash_factor = event['magnitude'] * (progress / 0.2)
                            price = price * (1 - crash_factor)
                        else:  # Recovery phase
                            # Gradual recovery with noise
                            recovery_progress = (progress - 0.2) / 0.8
                            recovery_factor = event['magnitude'] * (1 - recovery_progress)
                            noise_factor = random.normalvariate(0, 0.1 * event['magnitude'])
                            price = price * (1 - recovery_factor + noise_factor)
                    
                    elif event['type'] == 'spike':
                        # Sharp spike followed by correction
                        progress = event['current_tick'] / event['remaining_ticks']
                        if progress < 0.2:  # Initial spike phase
                            # Sharp rise
                            spike_factor = event['magnitude'] * (progress / 0.2)
                            price = price * (1 + spike_factor)
                        else:  # Correction phase
                            # Gradual correction with noise
                            correction_progress = (progress - 0.2) / 0.8
                            correction_factor = event['magnitude'] * (1 - correction_progress)
                            noise_factor = random.normalvariate(0, 0.1 * event['magnitude'])
                            price = price * (1 + correction_factor + noise_factor)
                    
                    elif event['type'] == 'gap':
                        # Sudden price gap
                        if event['current_tick'] == 1:  # First tick of the event
                            price = price * (1 + event['magnitude'])
                    
                    remaining_events.append(event)
            
            # Update active events list
            self.active_stress_events = remaining_events
            
            return max(0.00001, price)
        
        # Default case
        return current_price
    
    def _calculate_spread(self, symbol: str, price: float) -> float:
        """
        Calculate the bid-ask spread based on symbol and current price.
        
        Args:
            symbol: Symbol to calculate spread for
            price: Current price
            
        Returns:
            Bid-ask spread
        """
        # Base spread is 0.01% of price (very tight) up to 0.05% (wider)
        if self.config.get('realistic_spreads', True):
            # More realistic spreads for different pairs
            if symbol.endswith('JPY'):
                base_spread = 0.02  # 2 pips for JPY pairs
            elif symbol in ['EURUSD', 'GBPUSD', 'USDCHF']:
                base_spread = 0.0001  # 1 pip for major pairs
            else:
                base_spread = 0.0002  # 2 pips for other pairs
            
            # Adjust for pattern - higher volatility means wider spreads
            if self.pattern == PatternType.VOLATILE:
                base_spread *= 2.0
            elif self.pattern == PatternType.OPENING:
                base_spread *= 1.5
                
            # Random variation in spread (±20%)
            spread_multiplier = random.uniform(0.8, 1.2)
            
            return base_spread * spread_multiplier
        else:
            # Simple fixed percentage of price
            return price * 0.0001  # 0.01% spread
    
    def _load_custom_pattern(self) -> Optional[Dict[str, Any]]:
        """
        Load custom pattern from file.
        
        Returns:
            Dictionary with pattern data or None if not available
        """
        custom_pattern_path = self.config.get('custom_pattern_path')
        if not custom_pattern_path:
            self.logger.warning("Custom pattern selected but no pattern file specified")
            return None
            
        path = Path(custom_pattern_path)
        if not path.exists():
            self.logger.warning(f"Custom pattern file not found: {custom_pattern_path}")
            return None
            
        try:
            if path.suffix.lower() == '.json':
                with open(path, 'r') as f:
                    pattern_data = json.load(f)
            elif path.suffix.lower() in ['.yml', '.yaml']:
                with open(path, 'r') as f:
                    pattern_data = yaml.safe_load(f)
            else:
                self.logger.warning(f"Unsupported pattern file format: {path.suffix}")
                return None
                
            # Validate pattern data
            if 'type' not in pattern_data or 'modifiers' not in pattern_data:
                self.logger.warning("Invalid pattern data: missing 'type' or 'modifiers'")
                return None
                
            if pattern_data['type'] not in ['absolute', 'relative', 'additive']:
                self.logger.warning(f"Invalid pattern type: {pattern_data['type']}")
                return None
                
            if not isinstance(pattern_data['modifiers'], list) or len(pattern_data['modifiers']) == 0:
                self.logger.warning("Invalid or empty 'modifiers' array in pattern data")
                return None
                
            return pattern_data
            
        except Exception as e:
            self.logger.warning(f"Error loading custom pattern: {e}")
            return None
    
    def _report_performance(self) -> None:
        """Report performance statistics periodically."""
        now = time.time()
        elapsed = now - self.perf_last_report
        
        # Report every 5 seconds
        if elapsed >= 5.0:
            rate = self.perf_count / elapsed
            self.logger.info(f"Performance: {rate:.2f} ticks/sec (over {elapsed:.1f}s)")
            
            # Reset counters
            self.perf_last_report = now
            self.perf_count = 0

    def _initialize_phase_parameters(self, pattern_type: PatternType) -> None:
        """
        Initialize parameters for the current phase in a multi-phase pattern.
        
        Args:
            pattern_type: Pattern type for the current phase
        """
        if pattern_type == PatternType.VOLATILE:
            self.volatility_multiplier = 5.0
        elif pattern_type in [PatternType.TRENDING_UP, PatternType.TRENDING_DOWN]:
            self.trend_strength = 0.0001  # 0.01% per tick on average
            self.trend_direction = 1 if pattern_type == PatternType.TRENDING_UP else -1
        elif pattern_type == PatternType.RANGE_BOUND:
            self.range_width = 0.002  # 0.2% range
            self.range_centers = {symbol: price for symbol, price in self.current_prices.items()}
    
    def _initialize_base_pattern_parameters(self) -> None:
        """Initialize parameters for the base pattern in a stress test pattern."""
        if self.base_pattern == PatternType.VOLATILE:
            self.volatility_multiplier = 5.0
        elif self.base_pattern in [PatternType.TRENDING_UP, PatternType.TRENDING_DOWN]:
            self.trend_strength = 0.0001  # 0.01% per tick on average
            self.trend_direction = 1 if self.base_pattern == PatternType.TRENDING_UP else -1
        elif self.base_pattern == PatternType.RANGE_BOUND:
            self.range_width = 0.002  # 0.2% range
            self.range_centers = {symbol: price for symbol, price in self.base_prices.items()}

    def _apply_specific_pattern(self, pattern_type: PatternType, symbol: str, current_price: float) -> float:
        """
        Apply a specific pattern type to the current price.
        Used by multi-phase and stress test patterns.
        
        Args:
            pattern_type: The pattern type to apply
            symbol: Symbol to update
            current_price: Current price
            
        Returns:
            New price after applying the pattern
        """
        if pattern_type == PatternType.NORMAL:
            # Random walk with small steps
            step = random.normalvariate(0, self.volatility * current_price)
            return max(0.00001, current_price + step)
            
        elif pattern_type == PatternType.VOLATILE:
            # Random walk with larger steps
            step = random.normalvariate(0, self.volatility * current_price * self.volatility_multiplier)
            return max(0.00001, current_price + step)
            
        elif pattern_type in [PatternType.TRENDING_UP, PatternType.TRENDING_DOWN]:
            # Trending with noise
            direction = 1 if pattern_type == PatternType.TRENDING_UP else -1
            trend = self.trend_strength * current_price * direction
            noise = random.normalvariate(0, self.volatility * current_price)
            return max(0.00001, current_price + trend + noise)
            
        elif pattern_type == PatternType.RANGE_BOUND:
            # Mean reversion within a range
            center = self.range_centers.get(symbol, current_price)
            range_min = center * (1 - self.range_width / 2)
            range_max = center * (1 + self.range_width / 2)
            
            # Calculate mean reversion force
            distance_from_center = current_price - center
            reversion = -distance_from_center * 0.05  # 5% reversion towards center
            
            # Add noise
            noise = random.normalvariate(0, self.volatility * current_price)
            
            # Calculate new price and constrain to range
            new_price = current_price + reversion + noise
            return max(range_min, min(range_max, new_price))
            
        elif pattern_type == PatternType.OPENING:
            # Higher volatility with slight upward drift
            drift = 0.00005 * current_price  # Slight upward drift
            volatility_factor = 2.0  # Higher volatility during opening
            step = random.normalvariate(drift, self.volatility * current_price * volatility_factor)
            return max(0.00001, current_price + step)
            
        elif pattern_type == PatternType.CLOSING:
            # Declining volatility with slight convergence
            center = self.base_prices.get(symbol, current_price)
            reversion = (center - current_price) * 0.01  # Slight reversion to base price
            volatility_factor = 1.5  # Higher than normal, lower than opening
            step = random.normalvariate(reversion, self.volatility * current_price * volatility_factor)
            return max(0.00001, current_price + step)
        
        # Default case - no change
        return current_price


class TradeDataGenerator(MarketDataGenerator):
    """Generator for trade execution data."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the trade data generator.
        
        Args:
            config: Configuration dictionary
            logger: Optional logger instance
        """
        super().__init__(config, logger)
        
        # Default to lower rate for trades
        self.rate = config.get('rate', 10)  # Trades per second
        
        # Reference to a TickDataGenerator to get current prices
        self.tick_generator = None
        
    def set_tick_generator(self, generator: TickDataGenerator) -> None:
        """
        Set the tick generator to get price data from.
        
        Args:
            generator: TickDataGenerator instance
        """
        self.tick_generator = generator
    
    async def start(self) -> None:
        """Start the trade data generator."""
        await super().start()
        self.logger.info(f"Starting trade data generation at {self.rate} trades/sec for symbols: {', '.join(self.symbols)}")
        
        # Start the generation loop as a task
        asyncio.create_task(self._generation_loop())
    
    async def stop(self) -> None:
        """Stop the trade data generator."""
        await super().stop()
        self.logger.info("Stopped trade data generation")
        
    async def _generation_loop(self) -> None:
        """Main loop for generating trade data."""
        interval = 1.0 / self.rate  # Time between trades in seconds
        
        try:
            while self._running:
                # Choose a random symbol from the list
                symbol = random.choice(self.symbols)
                
                # Generate trade
                trade = await self._generate_trade(symbol)
                self._notify_listeners(trade)
                
                # Sleep until next trade
                await self._sleep_adjusted(interval)
                
                # Adjust interval if rate has changed
                interval = 1.0 / self.rate
        
        except asyncio.CancelledError:
            self.logger.info("Trade generation loop cancelled")
        except Exception as e:
            self.logger.error(f"Error in trade generation loop: {e}", exc_info=True)
    
    async def generate_data(self) -> AsyncIterator[MarketData]:
        """
        Generate market data.
        
        Returns:
            AsyncIterator yielding MarketDataTrade objects
        """
        interval = 1.0 / self.rate  # Time between trades in seconds
        
        while self._running:
            # Choose a random symbol from the list
            symbol = random.choice(self.symbols)
            
            # Generate trade
            trade = await self._generate_trade(symbol)
            yield trade
            
            # Sleep until next trade
            await self._sleep_adjusted(interval)
            
            # Adjust interval if rate has changed
            interval = 1.0 / self.rate
    
    async def _generate_trade(self, symbol: str) -> MarketDataTrade:
        """
        Generate a single trade.
        
        Args:
            symbol: Symbol to generate trade for
            
        Returns:
            MarketDataTrade instance
        """
        # Get current price from tick generator if available
        price = None
        if self.tick_generator and symbol in self.tick_generator.current_prices:
            price = self.tick_generator.current_prices[symbol]
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
            price = base_price * (1 + random.normalvariate(0, 0.0002))
        
        # Random volume between 0.1 and 100
        volume = round(random.uniform(0.1, 100.0), 2)
        
        # Random direction
        direction = "buy" if random.random() < 0.5 else "sell"
        
        # Create trade
        return MarketDataTrade(
            symbol=symbol,
            timestamp=datetime.now(),
            price=round(price, 5),
            volume=volume,
            direction=direction
        ) 