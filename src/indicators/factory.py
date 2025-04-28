"""
Indicator Factory module.

This module provides a factory class for creating technical indicator calculators.
"""
import pandas as pd
import talib
import numpy as np
from typing import Dict, Any, Callable, Optional


class IndicatorFactory:
    """
    Factory class for creating technical indicator calculation functions.
    
    This class provides static methods to create and retrieve indicator calculation
    functions based on indicator names. It supports both built-in indicators and
    custom indicator implementations.
    """
    
    # Registry of available indicators
    _registry = {}
    
    @classmethod
    def register(cls, name: str, func: Callable) -> None:
        """
        Register a new indicator function.
        
        Args:
            name: Name of the indicator
            func: Function that calculates the indicator
        """
        cls._registry[name.upper()] = func
    
    @classmethod
    def get(cls, name: str) -> Callable:
        """
        Get an indicator calculation function.
        
        Args:
            name: Name of the indicator to retrieve
            
        Returns:
            A function that calculates the requested indicator
            
        Raises:
            ValueError: If the indicator is not registered
        """
        name = name.upper()
        
        # Check if the indicator is already registered
        if name in cls._registry:
            return cls._registry[name]
        
        # Check if the indicator is supported by TA-Lib
        if hasattr(talib, name):
            # Create and register a function for the TA-Lib indicator
            func = cls._create_talib_indicator(name)
            cls.register(name, func)
            return func
        
        raise ValueError(f"Indicator '{name}' is not registered and not found in TA-Lib")
    
    @classmethod
    def list_available(cls) -> Dict[str, str]:
        """
        List all available indicators with descriptions.
        
        Returns:
            A dictionary mapping indicator names to their descriptions
        """
        available = {}
        
        # Add registered indicators
        for name in cls._registry.keys():
            func = cls._registry[name]
            available[name] = func.__doc__ or "No description available"
        
        # Add TA-Lib indicators that aren't explicitly registered
        for func_name in dir(talib):
            if func_name.isupper() and not func_name.startswith('_') and func_name not in available:
                func = getattr(talib, func_name)
                if callable(func):
                    available[func_name] = func.__doc__ or "TA-Lib indicator"
        
        return available
    
    @classmethod
    def _create_talib_indicator(cls, name: str) -> Callable:
        """
        Create a function wrapper for a TA-Lib indicator.
        
        Args:
            name: Name of the TA-Lib indicator
            
        Returns:
            A function that wraps the TA-Lib indicator to work with pandas DataFrames
        """
        talib_func = getattr(talib, name)
        
        def indicator_function(data: pd.DataFrame, **kwargs) -> pd.Series:
            """
            Calculate the indicator using TA-Lib.
            
            Args:
                data: Market data as a pandas DataFrame
                **kwargs: Parameters for the indicator calculation
                
            Returns:
                A pandas Series containing the calculated indicator values
            """
            # Most TA-Lib functions accept OHLCV data
            inputs = {}
            
            # Map common column names to expected TA-Lib input names
            column_mapping = {
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume',
                
                # Alternative names that might be used
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume',
                
                'o': 'open',
                'h': 'high',
                'l': 'low',
                'c': 'close',
                'v': 'volume',
                
                # Add more mappings as needed
            }
            
            # Check which columns are available in the data
            for col, input_name in column_mapping.items():
                if col in data.columns:
                    inputs[input_name] = data[col].values
            
            # Get the parameter information by inspecting the function
            import inspect
            params = inspect.signature(talib_func).parameters
            
            # Prepare the arguments
            args = []
            for param_name in params:
                if param_name == 'open':
                    args.append(inputs.get('open', np.array([])))
                elif param_name == 'high':
                    args.append(inputs.get('high', np.array([])))
                elif param_name == 'low':
                    args.append(inputs.get('low', np.array([])))
                elif param_name == 'close':
                    args.append(inputs.get('close', np.array([])))
                elif param_name == 'volume':
                    args.append(inputs.get('volume', np.array([])))
                elif param_name in kwargs:
                    args.append(kwargs[param_name])
            
            # Calculate the indicator
            result = talib_func(*args)
            
            # Handle different return types (some TA-Lib functions return multiple arrays)
            if isinstance(result, tuple):
                # If we have a tuple of results, convert to a DataFrame
                result_dict = {}
                # Try to get output names from the function docstring
                doc = talib_func.__doc__ or ""
                output_lines = [line for line in doc.split('\n') if 'output:' in line.lower()]
                
                # If we have clear output names in the docstring, use them
                if output_lines and len(output_lines) == len(result):
                    for i, line in enumerate(output_lines):
                        name = line.split(':')[-1].strip()
                        result_dict[name] = result[i]
                else:
                    # Otherwise, use generic names
                    for i, res in enumerate(result):
                        result_dict[f"{name.lower()}_{i+1}"] = res
                
                # Return the first output as a Series (most common use case)
                # In more complex cases, the user can handle the conversion as needed
                return pd.Series(result[0], index=data.index)
            else:
                # Single output, return as a Series
                return pd.Series(result, index=data.index)
        
        # Set the docstring for the wrapper function
        indicator_function.__doc__ = talib_func.__doc__
        
        return indicator_function

    # Register custom indicators here
    @classmethod
    def register_custom_indicators(cls):
        """Register all custom indicators."""
        # Example: Register a custom SMA implementation
        cls.register('CUSTOM_SMA', cls._custom_sma)
        
        # Register more custom indicators as needed

    @staticmethod
    def _custom_sma(data: pd.DataFrame, period: int = 14, column: str = 'close') -> pd.Series:
        """
        Calculate Simple Moving Average.
        
        Args:
            data: Market data as a pandas DataFrame
            period: Period for calculation (default: 14)
            column: Column to use for calculation (default: 'close')
            
        Returns:
            A pandas Series containing the SMA values
        """
        # Handle column name case insensitivity
        column_lower = column.lower()
        for col in data.columns:
            if col.lower() == column_lower:
                column = col
                break
                
        return data[column].rolling(window=period).mean()


# Register all custom indicators
IndicatorFactory.register_custom_indicators() 