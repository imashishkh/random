"""
Data Manager Package

This package provides a comprehensive data fetching and preprocessing system
for market analysis and trading applications.
"""

from .data_manager import DataManager
from .data_source import DataSourceAdapter, DataSourceFactory
from .preprocessor import DataPreprocessor, PreprocessorFactory

__all__ = [
    'DataManager',
    'DataSourceAdapter',
    'DataSourceFactory',
    'DataPreprocessor',
    'PreprocessorFactory'
] 