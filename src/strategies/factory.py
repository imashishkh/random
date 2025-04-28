from typing import Dict, Any, Type, List, Optional
import logging
import inspect
import importlib
import os
import pkgutil
from pathlib import Path

from .base import Strategy

logger = logging.getLogger(__name__)


class StrategyFactory:
    """
    Factory class for creating strategy instances.
    
    This class is responsible for:
    1. Discovering available strategy implementations
    2. Creating instances of strategies with configuration
    3. Providing metadata about available strategies
    """
    
    def __init__(self):
        self._strategy_classes: Dict[str, Type[Strategy]] = {}
        
    def register_strategy(self, strategy_class: Type[Strategy], name: str = None) -> None:
        """
        Register a strategy class.
        
        Args:
            strategy_class: Strategy class to register
            name: Optional name to register the strategy under (defaults to class name)
        """
        if not inspect.isclass(strategy_class) or not issubclass(strategy_class, Strategy):
            raise TypeError(f"Expected Strategy subclass, got {type(strategy_class)}")
            
        name = name or strategy_class.__name__
        self._strategy_classes[name] = strategy_class
        logger.info(f"Registered strategy class: {name}")
        
    def create_strategy(
        self, 
        strategy_name: str, 
        name: str = None,
        params: Dict[str, Any] = None
    ) -> Strategy:
        """
        Create an instance of a registered strategy.
        
        Args:
            strategy_name: Name of the registered strategy class
            name: Optional name for the strategy instance
            params: Optional parameters for the strategy
            
        Returns:
            Instantiated strategy
            
        Raises:
            ValueError: If strategy is not registered
        """
        if strategy_name not in self._strategy_classes:
            raise ValueError(f"Strategy '{strategy_name}' not registered")
            
        strategy_class = self._strategy_classes[strategy_name]
        instance_name = name or strategy_name
        
        try:
            strategy = strategy_class(name=instance_name, params=params)
            logger.debug(f"Created strategy: {instance_name} of type {strategy_name}")
            return strategy
        except Exception as e:
            logger.error(f"Error creating strategy {strategy_name}: {e}")
            raise
            
    def get_available_strategies(self) -> List[str]:
        """
        Get a list of registered strategy names.
        
        Returns:
            List of strategy names
        """
        return list(self._strategy_classes.keys())
        
    def get_strategy_class(self, strategy_name: str) -> Type[Strategy]:
        """
        Get a strategy class by name.
        
        Args:
            strategy_name: Name of the registered strategy
            
        Returns:
            Strategy class
            
        Raises:
            ValueError: If strategy is not registered
        """
        if strategy_name not in self._strategy_classes:
            raise ValueError(f"Strategy '{strategy_name}' not registered")
            
        return self._strategy_classes[strategy_name]
        
    def discover_strategies(self, package_path: str = None) -> None:
        """
        Automatically discover and register strategy classes from a package.
        
        This method looks for Strategy subclasses in all modules within the package.
        
        Args:
            package_path: Optional path to the package to scan (defaults to current package)
        """
        if package_path is None:
            # Default to the 'strategies' module
            package_path = os.path.dirname(__file__)
            
        package_name = os.path.basename(package_path)
        logger.info(f"Discovering strategies in package: {package_name}")
        
        # Find all modules in the package
        for _, name, is_pkg in pkgutil.iter_modules([package_path]):
            if name in ['base', 'engine', 'factory', '__init__', '__pycache__']:
                continue  # Skip special modules
                
            module_name = f"{package_name}.{name}"
            try:
                module = importlib.import_module(module_name)
                
                # Look for Strategy subclasses in the module
                for item_name, item in module.__dict__.items():
                    if (inspect.isclass(item) and 
                        issubclass(item, Strategy) and 
                        item is not Strategy):
                        self.register_strategy(item)
                        
            except Exception as e:
                logger.error(f"Error loading module {module_name}: {e}")
        
        logger.info(f"Discovered {len(self._strategy_classes)} strategy classes")
        
    def load_strategies_from_config(self, config: List[Dict[str, Any]]) -> List[Strategy]:
        """
        Load multiple strategies from a configuration list.
        
        Args:
            config: List of strategy configurations
                   Each item should have 'name' and optionally 'params'
                   
        Returns:
            List of instantiated strategies
            
        Example config:
        [
            {"name": "MovingAverageCrossover", "params": {"fast_period": 10, "slow_period": 30}},
            {"name": "RSIStrategy", "params": {"period": 14, "overbought": 70, "oversold": 30}}
        ]
        """
        strategies = []
        
        for strategy_config in config:
            strategy_name = strategy_config.get('name')
            if not strategy_name:
                logger.warning(f"Skipping strategy config with missing name: {strategy_config}")
                continue
                
            params = strategy_config.get('params', {})
            instance_name = strategy_config.get('instance_name')
            
            try:
                strategy = self.create_strategy(
                    strategy_name=strategy_name,
                    name=instance_name,
                    params=params
                )
                strategies.append(strategy)
            except Exception as e:
                logger.error(f"Error creating strategy {strategy_name}: {e}")
                
        return strategies


# Create singleton factory instance
strategy_factory = StrategyFactory() 