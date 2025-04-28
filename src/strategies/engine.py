from typing import Dict, List, Type, Any, Optional, Union, Set
import pandas as pd
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from .base import Strategy, Signal, SignalType

logger = logging.getLogger(__name__)


class StrategyEngine:
    """
    Strategy engine that manages multiple trading strategies.
    
    This class is responsible for:
    1. Registering and managing strategy instances
    2. Providing data to strategies
    3. Collecting and aggregating signals from multiple strategies
    4. Handling strategy execution lifecycle
    """
    
    def __init__(self, max_workers: int = 4):
        self._strategies: Dict[str, Strategy] = {}
        self._strategy_registry: Dict[str, Type[Strategy]] = {}
        self._max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        logger.info(f"Strategy engine initialized with {max_workers} worker threads")
    
    def register_strategy_class(self, strategy_class: Type[Strategy], name: str = None) -> None:
        """
        Register a strategy class in the strategy registry.
        
        Args:
            strategy_class: The strategy class to register
            name: Optional name to register the strategy under (defaults to class name)
        """
        name = name or strategy_class.__name__
        if name in self._strategy_registry:
            logger.warning(f"Strategy {name} already registered, overwriting")
        self._strategy_registry[name] = strategy_class
        logger.info(f"Registered strategy class: {name}")
    
    def create_strategy(
        self, 
        strategy_name: str, 
        instance_name: str = None, 
        params: Dict[str, Any] = None
    ) -> Strategy:
        """
        Create a strategy instance from a registered strategy class.
        
        Args:
            strategy_name: Name of the registered strategy class
            instance_name: Optional unique name for this strategy instance
            params: Optional parameters to initialize the strategy with
            
        Returns:
            Instantiated strategy object
        
        Raises:
            ValueError: If strategy name is not registered
        """
        if strategy_name not in self._strategy_registry:
            raise ValueError(f"Strategy '{strategy_name}' not registered")
            
        strategy_class = self._strategy_registry[strategy_name]
        instance_name = instance_name or f"{strategy_name}_{int(time.time())}"
        
        if instance_name in self._strategies:
            logger.warning(f"Strategy instance {instance_name} already exists, overwriting")
            
        strategy = strategy_class(name=instance_name, params=params)
        self._strategies[instance_name] = strategy
        
        logger.info(f"Created strategy instance: {instance_name} of type {strategy_name}")
        return strategy
    
    def initialize_strategy(self, strategy_name: str) -> None:
        """
        Initialize a specific strategy.
        
        Args:
            strategy_name: Name of the strategy instance to initialize
            
        Raises:
            ValueError: If strategy does not exist
        """
        if strategy_name not in self._strategies:
            raise ValueError(f"Strategy '{strategy_name}' does not exist")
            
        strategy = self._strategies[strategy_name]
        if not strategy.is_initialized:
            strategy.initialize()
            strategy.is_initialized = True
            logger.info(f"Initialized strategy: {strategy_name}")
    
    def initialize_all_strategies(self) -> None:
        """Initialize all registered strategies."""
        for strategy_name in self._strategies:
            self.initialize_strategy(strategy_name)
    
    def get_strategy(self, strategy_name: str) -> Strategy:
        """
        Get a strategy instance by name.
        
        Args:
            strategy_name: Name of the strategy instance
            
        Returns:
            Strategy instance
            
        Raises:
            ValueError: If strategy does not exist
        """
        if strategy_name not in self._strategies:
            raise ValueError(f"Strategy '{strategy_name}' does not exist")
        return self._strategies[strategy_name]
    
    def remove_strategy(self, strategy_name: str) -> None:
        """
        Remove a strategy instance.
        
        Args:
            strategy_name: Name of the strategy instance to remove
            
        Raises:
            ValueError: If strategy does not exist
        """
        if strategy_name not in self._strategies:
            raise ValueError(f"Strategy '{strategy_name}' does not exist")
            
        del self._strategies[strategy_name]
        logger.info(f"Removed strategy: {strategy_name}")
    
    def get_all_required_indicators(self) -> Set[str]:
        """
        Get a set of all indicators required by all registered strategies.
        
        Returns:
            Set of indicator names
        """
        indicators = set()
        for strategy in self._strategies.values():
            indicators.update(strategy.get_required_indicators())
        return indicators
    
    def get_all_required_timeframes(self) -> Set[str]:
        """
        Get a set of all timeframes required by all registered strategies.
        
        Returns:
            Set of timeframe strings
        """
        timeframes = set()
        for strategy in self._strategies.values():
            timeframes.update(strategy.get_required_timeframes())
        return timeframes
    
    def analyze_single_strategy(
        self, 
        strategy_name: str, 
        data: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Run analysis on a single strategy.
        
        Args:
            strategy_name: Name of the strategy instance
            data: Market data for analysis
            
        Returns:
            Analysis results
            
        Raises:
            ValueError: If strategy does not exist
        """
        strategy = self.get_strategy(strategy_name)
        
        if not strategy.is_initialized:
            self.initialize_strategy(strategy_name)
            
        return strategy.analyze(data)
    
    def analyze_all_strategies(
        self, 
        data: Dict[str, pd.DataFrame]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Run analysis on all strategies with appropriate data.
        
        Args:
            data: Dictionary mapping strategy names to their respective data
            
        Returns:
            Dictionary mapping strategy names to their analysis results
        """
        results = {}
        futures = {}
        
        for strategy_name, strategy in self._strategies.items():
            if not strategy.is_initialized:
                self.initialize_strategy(strategy_name)
                
            # Use strategy's data if available, otherwise use generic data
            strategy_data = data.get(strategy_name, data.get('default', None))
            
            if strategy_data is None:
                logger.warning(f"No data provided for strategy {strategy_name}")
                continue
                
            future = self._executor.submit(strategy.analyze, strategy_data)
            futures[future] = strategy_name
        
        for future in as_completed(futures):
            strategy_name = futures[future]
            try:
                result = future.result()
                results[strategy_name] = result
            except Exception as e:
                logger.error(f"Error analyzing strategy {strategy_name}: {e}")
                results[strategy_name] = {"error": str(e)}
        
        return results
    
    def generate_signals_from_strategy(
        self, 
        strategy_name: str, 
        data: pd.DataFrame
    ) -> List[Signal]:
        """
        Generate signals from a single strategy.
        
        Args:
            strategy_name: Name of the strategy instance
            data: Market data for signal generation
            
        Returns:
            List of signals
            
        Raises:
            ValueError: If strategy does not exist
        """
        strategy = self.get_strategy(strategy_name)
        
        if not strategy.is_initialized:
            self.initialize_strategy(strategy_name)
            
        return strategy.generate_signals(data)
    
    def generate_signals_from_all_strategies(
        self, 
        data: Dict[str, pd.DataFrame]
    ) -> Dict[str, List[Signal]]:
        """
        Generate signals from all strategies with appropriate data.
        
        Args:
            data: Dictionary mapping strategy names to their respective data
            
        Returns:
            Dictionary mapping strategy names to their generated signals
        """
        all_signals = {}
        futures = {}
        
        for strategy_name, strategy in self._strategies.items():
            if not strategy.is_initialized:
                self.initialize_strategy(strategy_name)
                
            # Use strategy's data if available, otherwise use generic data
            strategy_data = data.get(strategy_name, data.get('default', None))
            
            if strategy_data is None:
                logger.warning(f"No data provided for strategy {strategy_name}")
                continue
                
            future = self._executor.submit(strategy.generate_signals, strategy_data)
            futures[future] = strategy_name
        
        for future in as_completed(futures):
            strategy_name = futures[future]
            try:
                signals = future.result()
                all_signals[strategy_name] = signals
            except Exception as e:
                logger.error(f"Error generating signals for strategy {strategy_name}: {e}")
                all_signals[strategy_name] = []
        
        return all_signals
    
    def aggregate_signals(
        self, 
        signals_by_strategy: Dict[str, List[Signal]],
        weights: Dict[str, float] = None
    ) -> List[Signal]:
        """
        Aggregate signals from multiple strategies, potentially with different weights.
        
        Args:
            signals_by_strategy: Dictionary mapping strategy names to their signals
            weights: Optional dictionary mapping strategy names to their weights
                    (defaults to equal weights)
            
        Returns:
            Aggregated list of signals
        """
        if not signals_by_strategy:
            return []
            
        # Default to equal weights if not provided
        if weights is None:
            weights = {name: 1.0 for name in signals_by_strategy.keys()}
            
        # Normalize weights to sum to 1.0
        weight_sum = sum(weights.values())
        normalized_weights = {
            name: weight / weight_sum for name, weight in weights.items()
        }
        
        # Aggregate signals by symbol and type
        signal_map = {}  # (symbol, signal_type) -> (signal, cumulative_strength)
        
        for strategy_name, signals in signals_by_strategy.items():
            strategy_weight = normalized_weights.get(strategy_name, 0.0)
            
            for signal in signals:
                key = (signal.symbol, signal.signal_type)
                
                if key not in signal_map:
                    # Create a copy of the first signal for this key
                    weighted_signal = Signal(
                        signal_type=signal.signal_type,
                        symbol=signal.symbol,
                        price=signal.price,
                        timestamp=signal.timestamp,
                        strength=signal.strength * strategy_weight,
                        metadata={
                            "strategies": {strategy_name: signal.strength},
                            "original_signal": signal
                        }
                    )
                    signal_map[key] = weighted_signal
                else:
                    # Update existing signal
                    existing_signal = signal_map[key]
                    existing_signal.strength += signal.strength * strategy_weight
                    existing_signal.metadata["strategies"][strategy_name] = signal.strength
                    
                    # Use the most recent timestamp
                    if signal.timestamp > existing_signal.timestamp:
                        existing_signal.timestamp = signal.timestamp
                        existing_signal.price = signal.price
        
        # Convert the map back to a list and return
        return list(signal_map.values())
    
    def shutdown(self) -> None:
        """Shutdown the strategy engine and free resources."""
        self._executor.shutdown(wait=True)
        logger.info("Strategy engine shutdown complete") 