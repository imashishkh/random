"""
Indicator Factory for Technical Analysis.

This module provides a factory class for creating and accessing technical indicators
with a unified interface, abstracting away the differences between TA-Lib and Pandas TA.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Union, Callable, Tuple


class TAIndicatorFactory:
    """
    Factory class for technical analysis indicators.
    
    This class provides a unified interface for creating and accessing technical indicators
    from different libraries (TA-Lib and Pandas TA), with fallback mechanisms.
    """
    
    # Registry of available indicators and their implementations
    _registry = {}
    
    @classmethod
    def register(cls, name: str, talib_func: Optional[Callable] = None, 
                pandas_ta_func: Optional[Callable] = None, custom_func: Optional[Callable] = None,
                description: Optional[str] = None) -> None:
        """
        Register an indicator with its implementations.
        
        Args:
            name: Name of the indicator
            talib_func: TA-Lib implementation function
            pandas_ta_func: Pandas TA implementation function
            custom_func: Custom implementation function
            description: Description of the indicator
        """
        cls._registry[name.upper()] = {
            'talib': talib_func,
            'pandas_ta': pandas_ta_func,
            'custom': custom_func,
            'description': description or "No description available"
        }
        
    @classmethod
    def create_indicator(cls, indicator_type: str, data: pd.DataFrame, 
                        params: Optional[Dict[str, Any]] = None, 
                        preferred_lib: str = 'auto') -> pd.Series:
        """
        Create and compute a technical indicator.
        
        Args:
            indicator_type: Name of the indicator (e.g., 'RSI', 'MACD')
            data: Market data as a pandas DataFrame with OHLCV columns
            params: Parameters for the indicator calculation
            preferred_lib: Preferred library ('talib', 'pandas_ta', 'custom', or 'auto')
            
        Returns:
            Computed indicator values as a pandas Series
        """
        params = params or {}
        indicator_type = indicator_type.upper()
        
        # Check if indicator is registered
        if indicator_type not in cls._registry:
            # Try to find and register the indicator
            cls._try_register_indicator(indicator_type)
            
        if indicator_type in cls._registry:
            implementations = cls._registry[indicator_type]
            
            # Determine which implementation to use
            if preferred_lib == 'auto':
                # Try TA-Lib first, then Pandas TA, then custom
                if implementations['talib'] and cls._is_talib_available():
                    return cls._compute_talib_indicator(indicator_type, data, params)
                elif implementations['pandas_ta'] and cls._is_pandas_ta_available():
                    return cls._compute_pandas_ta_indicator(indicator_type, data, params)
                elif implementations['custom']:
                    return cls._compute_custom_indicator(indicator_type, data, params)
                else:
                    raise ValueError(f"No available implementation for indicator '{indicator_type}'")
            elif preferred_lib == 'talib':
                if implementations['talib'] and cls._is_talib_available():
                    return cls._compute_talib_indicator(indicator_type, data, params)
                else:
                    raise ValueError(f"TA-Lib implementation not available for indicator '{indicator_type}'")
            elif preferred_lib == 'pandas_ta':
                if implementations['pandas_ta'] and cls._is_pandas_ta_available():
                    return cls._compute_pandas_ta_indicator(indicator_type, data, params)
                else:
                    raise ValueError(f"Pandas TA implementation not available for indicator '{indicator_type}'")
            elif preferred_lib == 'custom':
                if implementations['custom']:
                    return cls._compute_custom_indicator(indicator_type, data, params)
                else:
                    raise ValueError(f"Custom implementation not available for indicator '{indicator_type}'")
            else:
                raise ValueError(f"Invalid preferred_lib value: {preferred_lib}")
        else:
            raise ValueError(f"Indicator '{indicator_type}' not found")
    
    @classmethod
    def _try_register_indicator(cls, indicator_type: str) -> None:
        """
        Try to automatically register an indicator from TA-Lib or Pandas TA.
        
        Args:
            indicator_type: Name of the indicator to try to register
        """
        indicator_type = indicator_type.upper()
        talib_func = None
        pandas_ta_func = None
        
        # Check TA-Lib
        if cls._is_talib_available():
            import talib
            if hasattr(talib, indicator_type):
                talib_func = getattr(talib, indicator_type)
        
        # Check Pandas TA
        if cls._is_pandas_ta_available():
            import pandas_ta as pta
            # Pandas TA has a different organization of functions
            # Try to find the indicator in pandas_ta
            if hasattr(pta, indicator_type.lower()):
                pandas_ta_func = getattr(pta, indicator_type.lower())
        
        # Register if we found any implementation
        if talib_func or pandas_ta_func:
            cls.register(indicator_type, talib_func, pandas_ta_func)
    
    @classmethod
    def _is_talib_available(cls) -> bool:
        """Check if TA-Lib is available"""
        try:
            import talib
            return True
        except ImportError:
            return False
    
    @classmethod
    def _is_pandas_ta_available(cls) -> bool:
        """Check if Pandas TA is available"""
        try:
            import pandas_ta
            return True
        except ImportError:
            return False
    
    @classmethod
    def _compute_talib_indicator(cls, indicator_type: str, data: pd.DataFrame, 
                               params: Dict[str, Any]) -> pd.Series:
        """
        Compute an indicator using TA-Lib.
        
        Args:
            indicator_type: Name of the indicator
            data: Market data
            params: Parameters for the calculation
            
        Returns:
            Computed indicator values
        """
        import talib
        
        # Get the TA-Lib function
        talib_func = cls._registry[indicator_type]['talib']
        
        # Prepare inputs for the TA-Lib function
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
        }
        
        # Check which columns are available in the data
        for col, input_name in column_mapping.items():
            if col in data.columns:
                inputs[input_name] = data[col].values
        
        # Get the parameter information by inspecting the function
        import inspect
        sig_params = inspect.signature(talib_func).parameters
        
        # Prepare the arguments
        args = []
        for param_name in sig_params:
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
            elif param_name in params:
                args.append(params[param_name])
        
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
                    result_dict[f"{indicator_type.lower()}_{i+1}"] = res
            
            # Return the first output as a Series (most common use case)
            return pd.Series(result[0], index=data.index)
        else:
            # Single output, return as a Series
            return pd.Series(result, index=data.index)
    
    @classmethod
    def _compute_pandas_ta_indicator(cls, indicator_type: str, data: pd.DataFrame, 
                                  params: Dict[str, Any]) -> pd.Series:
        """
        Compute an indicator using Pandas TA.
        
        Args:
            indicator_type: Name of the indicator
            data: Market data
            params: Parameters for the calculation
            
        Returns:
            Computed indicator values
        """
        import pandas_ta as pta
        
        # Get the Pandas TA function
        pandas_ta_func = cls._registry[indicator_type]['pandas_ta']
        
        # Map common TA-Lib parameter names to Pandas TA names
        param_mapping = {
            'timeperiod': 'length',
            'fastperiod': 'fast',
            'slowperiod': 'slow',
            'signalperiod': 'signal',
            'nbdevup': 'std_upper',
            'nbdevdn': 'std_lower',
        }
        
        # Adjust parameter names if needed
        adjusted_params = {}
        for param_name, param_value in params.items():
            if param_name in param_mapping:
                adjusted_params[param_mapping[param_name]] = param_value
            else:
                adjusted_params[param_name] = param_value
        
        # Calculate the indicator
        result = pandas_ta_func(data, **adjusted_params)
        
        # Convert to Series if a DataFrame is returned
        if isinstance(result, pd.DataFrame):
            if len(result.columns) == 1:
                return result.iloc[:, 0]
            else:
                # Return the first column as a Series (most common use case)
                return result.iloc[:, 0]
        else:
            return result
    
    @classmethod
    def _compute_custom_indicator(cls, indicator_type: str, data: pd.DataFrame, 
                               params: Dict[str, Any]) -> pd.Series:
        """
        Compute an indicator using a custom implementation.
        
        Args:
            indicator_type: Name of the indicator
            data: Market data
            params: Parameters for the calculation
            
        Returns:
            Computed indicator values
        """
        # Get the custom function
        custom_func = cls._registry[indicator_type]['custom']
        
        # Calculate the indicator
        return custom_func(data, **params)
    
    @classmethod
    def list_available_indicators(cls) -> Dict[str, str]:
        """
        List all available indicators with descriptions.
        
        Returns:
            Dictionary mapping indicator names to their descriptions
        """
        available = {}
        
        # Add registered indicators
        for name, impl in cls._registry.items():
            available[name] = impl['description']
        
        # Add TA-Lib indicators that aren't explicitly registered
        if cls._is_talib_available():
            import talib
            for func_name in dir(talib):
                if func_name.isupper() and not func_name.startswith('_') and func_name not in available:
                    func = getattr(talib, func_name)
                    if callable(func):
                        available[func_name] = func.__doc__ or "TA-Lib indicator"
        
        # Add Pandas TA indicators that aren't explicitly registered
        if cls._is_pandas_ta_available():
            import pandas_ta as pta
            for func_name in dir(pta):
                if not func_name.startswith('_') and func_name.lower() not in [name.lower() for name in available]:
                    func = getattr(pta, func_name)
                    if callable(func):
                        available[func_name.upper()] = func.__doc__ or "Pandas TA indicator"
        
        return available
    
    # Register common indicators
    @classmethod
    def register_common_indicators(cls):
        """Register commonly used technical indicators with both implementations."""
        # Make sure libraries are available
        talib_available = cls._is_talib_available()
        pandas_ta_available = cls._is_pandas_ta_available()
        
        if talib_available:
            import talib
        
        if pandas_ta_available:
            import pandas_ta as pta
        
        # RSI
        cls.register(
            'RSI',
            talib_func=talib.RSI if talib_available else None,
            pandas_ta_func=pta.rsi if pandas_ta_available else None,
            description="Relative Strength Index"
        )
        
        # MACD
        cls.register(
            'MACD',
            talib_func=talib.MACD if talib_available else None,
            pandas_ta_func=pta.macd if pandas_ta_available else None,
            description="Moving Average Convergence Divergence"
        )
        
        # Bollinger Bands
        cls.register(
            'BBANDS',
            talib_func=talib.BBANDS if talib_available else None,
            pandas_ta_func=pta.bbands if pandas_ta_available else None,
            description="Bollinger Bands"
        )
        
        # Simple Moving Average
        cls.register(
            'SMA',
            talib_func=talib.SMA if talib_available else None,
            pandas_ta_func=pta.sma if pandas_ta_available else None,
            description="Simple Moving Average"
        )
        
        # Exponential Moving Average
        cls.register(
            'EMA',
            talib_func=talib.EMA if talib_available else None,
            pandas_ta_func=pta.ema if pandas_ta_available else None,
            description="Exponential Moving Average"
        )
        
        # Average True Range
        cls.register(
            'ATR',
            talib_func=talib.ATR if talib_available else None,
            pandas_ta_func=pta.atr if pandas_ta_available else None,
            description="Average True Range"
        )
        
        # Stochastic Oscillator
        cls.register(
            'STOCH',
            talib_func=talib.STOCH if talib_available else None,
            pandas_ta_func=pta.stoch if pandas_ta_available else None,
            description="Stochastic Oscillator"
        )
        
        # On-Balance Volume
        cls.register(
            'OBV',
            talib_func=talib.OBV if talib_available else None,
            pandas_ta_func=pta.obv if pandas_ta_available else None,
            description="On-Balance Volume"
        )
        
        # Add more common indicators as needed
        
    # Register custom indicator implementations
    @classmethod
    def register_custom_indicators(cls):
        """Register custom indicator implementations."""
        
        # Example: Custom implementation of a Simple Moving Average
        def custom_sma(data, length=14, column='close'):
            """
            Calculate Simple Moving Average.
            
            Args:
                data: Market data as a pandas DataFrame
                length: Period for calculation (default: 14)
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
                    
            return data[column].rolling(window=length).mean()
        
        # Register the custom SMA
        cls.register(
            'CUSTOM_SMA',
            custom_func=custom_sma,
            description="Custom Simple Moving Average implementation"
        )
        
        # Add more custom indicators as needed


# Initialize the factory
TAIndicatorFactory.register_common_indicators()
TAIndicatorFactory.register_custom_indicators() 