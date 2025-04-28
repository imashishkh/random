"""
Strategy Evaluation Module
--------------------------
Framework for A/B testing and evaluation of trading strategies.
"""

from .data_processor import DataProcessor
from .metrics_calculator import MetricsCalculator
from .statistical_tester import StatisticalTester
from .strategy_evaluator import Strategy, StrategyEvaluator

__all__ = [
    'DataProcessor',
    'MetricsCalculator',
    'StatisticalTester',
    'Strategy',
    'StrategyEvaluator'
]
