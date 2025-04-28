"""
Strategy Evaluator for A/B Testing
----------------------------------
Main class for evaluating and comparing trading strategies.
"""

import pandas as pd
import numpy as np
import uuid
import json
import os
from typing import Dict, List, Any, Optional, Union, Tuple, Callable
from datetime import datetime

from .data_processor import DataProcessor
from .metrics_calculator import MetricsCalculator
from .statistical_tester import StatisticalTester


class Strategy:
    """
    Base class for trading strategies.
    
    All trading strategies should inherit from this class and implement
    the predict method.
    """
    
    def __init__(self, name: str = None):
        """
        Initialize the strategy.
        
        Args:
            name: Optional name for the strategy
        """
        self.name = name or self.__class__.__name__
    
    def predict(self, 
                data: pd.DataFrame, 
                **kwargs) -> pd.DataFrame:
        """
        Generate predictions for the strategy.
        
        Args:
            data: Market data DataFrame
            **kwargs: Additional arguments for the strategy
            
        Returns:
            DataFrame with predictions/signals
        """
        raise NotImplementedError("Subclasses must implement predict method")
    
    def backtest(self, 
                 data: pd.DataFrame, 
                 initial_capital: float = 10000.0,
                 position_size: float = 1.0,
                 transaction_cost: float = 0.0,
                 **kwargs) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Backtest the strategy on historical data.
        
        Args:
            data: Market data DataFrame
            initial_capital: Initial capital for the backtest
            position_size: Fraction of capital to allocate per trade
            transaction_cost: Transaction cost per trade
            **kwargs: Additional arguments for the strategy
            
        Returns:
            Tuple of (positions DataFrame, trades DataFrame)
        """
        # Get strategy predictions
        predictions = self.predict(data, **kwargs)
        
        # Ensure we have a timestamp column
        if 'timestamp' not in data.columns:
            if data.index.name == 'timestamp':
                data = data.reset_index()
            else:
                raise ValueError("Data must have a 'timestamp' column or index")
        
        # Merge predictions with data
        if 'timestamp' in predictions.columns:
            merged = pd.merge(data, predictions, on='timestamp', how='inner')
        else:
            # If predictions doesn't have a timestamp, assume it's aligned with data
            merged = data.copy()
            for col in predictions.columns:
                merged[col] = predictions[col].values
        
        # Initialize positions and trades DataFrames
        positions = pd.DataFrame({
            'timestamp': merged['timestamp'],
            'price': merged['close'],
            'position': 0.0,
            'position_value': initial_capital,
            'cash': initial_capital,
            'total_value': initial_capital
        })
        
        trades = []
        
        # Implement simple backtesting logic (long only for demo purposes)
        # In a real implementation, this would be more sophisticated
        for i in range(1, len(merged)):
            # Get current and previous positions
            prev_position = positions.loc[i-1, 'position']
            
            # Get current signal/prediction (assuming a 'signal' column)
            if 'signal' not in merged.columns:
                raise ValueError("Predictions must include a 'signal' column")
                
            current_signal = merged.loc[i, 'signal']
            
            # Determine the new position
            if current_signal > 0 and prev_position == 0:
                # Enter long position
                entry_price = merged.loc[i, 'close']
                cash_available = positions.loc[i-1, 'cash']
                
                # Calculate the position size (in cash terms)
                position_cash = cash_available * position_size
                
                # Calculate shares to buy
                shares = position_cash / entry_price
                
                # Apply transaction cost
                cost = position_cash * transaction_cost
                
                # Update positions
                positions.loc[i, 'position'] = shares
                positions.loc[i, 'cash'] = cash_available - position_cash - cost
                
                # Record trade
                trades.append({
                    'timestamp': merged.loc[i, 'timestamp'],
                    'type': 'buy',
                    'price': entry_price,
                    'shares': shares,
                    'value': position_cash,
                    'cost': cost
                })
            
            elif current_signal <= 0 and prev_position > 0:
                # Exit long position
                exit_price = merged.loc[i, 'close']
                shares = positions.loc[i-1, 'position']
                
                # Calculate position value
                position_cash = shares * exit_price
                
                # Apply transaction cost
                cost = position_cash * transaction_cost
                
                # Update positions
                positions.loc[i, 'position'] = 0
                positions.loc[i, 'cash'] = positions.loc[i-1, 'cash'] + position_cash - cost
                
                # Calculate profit
                entry_trade = next((t for t in reversed(trades) if t['type'] == 'buy'), None)
                profit = position_cash - entry_trade['value'] - cost - entry_trade['cost'] if entry_trade else 0
                
                # Record trade
                trades.append({
                    'timestamp': merged.loc[i, 'timestamp'],
                    'type': 'sell',
                    'price': exit_price,
                    'shares': shares,
                    'value': position_cash,
                    'cost': cost,
                    'profit': profit
                })
            
            else:
                # Maintain position
                positions.loc[i, 'position'] = prev_position
                positions.loc[i, 'cash'] = positions.loc[i-1, 'cash']
            
            # Update position value
            positions.loc[i, 'position_value'] = positions.loc[i, 'position'] * merged.loc[i, 'close']
            
            # Update total value
            positions.loc[i, 'total_value'] = positions.loc[i, 'position_value'] + positions.loc[i, 'cash']
        
        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame(columns=[
            'timestamp', 'type', 'price', 'shares', 'value', 'cost', 'profit'
        ])
        
        return positions, trades_df


class StrategyEvaluator:
    """
    Evaluates and compares trading strategies.
    
    This class provides a framework for A/B testing trading strategies,
    including data preparation, backtesting, metric calculation, and
    statistical testing.
    """
    
    def __init__(self, 
                 data_processor: Optional[DataProcessor] = None,
                 metrics_calculator: Optional[MetricsCalculator] = None,
                 statistical_tester: Optional[StatisticalTester] = None,
                 experiment_id: Optional[str] = None,
                 experiment_dir: str = 'experiments'):
        """
        Initialize the strategy evaluator.
        
        Args:
            data_processor: DataProcessor instance for data preprocessing
            metrics_calculator: MetricsCalculator instance for metric calculation
            statistical_tester: StatisticalTester instance for statistical testing
            experiment_id: Unique ID for the experiment
            experiment_dir: Directory to save experiment results
        """
        self.data_processor = data_processor or DataProcessor()
        self.metrics_calculator = metrics_calculator or MetricsCalculator()
        self.statistical_tester = statistical_tester or StatisticalTester()
        
        self.experiment_id = experiment_id or self._generate_experiment_id()
        self.experiment_dir = experiment_dir
        
        # Create experiment directory if it doesn't exist
        if not os.path.exists(experiment_dir):
            os.makedirs(experiment_dir)
        
        # Dictionary to store evaluation results
        self.results = {}
        
        # Experiment metadata
        self.metadata = {
            'experiment_id': self.experiment_id,
            'start_time': datetime.now().isoformat(),
            'strategies': [],
            'metrics': {},
            'comparison_results': None,
            'data_info': {},
            'experiment_config': {
                'data_processor': self.data_processor.__class__.__name__,
                'metrics_calculator': self.metrics_calculator.__class__.__name__,
                'statistical_tester': self.statistical_tester.__class__.__name__
            }
        }
    
    def _generate_experiment_id(self) -> str:
        """
        Generate a unique experiment ID.
        
        Returns:
            Unique experiment ID
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        random_suffix = uuid.uuid4().hex[:6]
        return f"exp_{timestamp}_{random_suffix}"
    
    def evaluate_strategy(self,
                          strategy: Strategy,
                          data: pd.DataFrame,
                          name: Optional[str] = None,
                          params: Optional[Dict[str, Any]] = None,
                          backtest_params: Optional[Dict[str, Any]] = None,
                          train_test_split: bool = True,
                          return_details: bool = False) -> Union[Dict[str, Any], Tuple[Dict[str, Any], Dict[str, Any]]]:
        """
        Evaluate a single strategy.
        
        Args:
            strategy: Strategy instance to evaluate
            data: Market data DataFrame
            name: Name for the strategy (defaults to strategy class name)
            params: Parameters to pass to the strategy's predict method
            backtest_params: Parameters for backtesting
            train_test_split: Whether to split data into train/val/test
            return_details: Whether to return detailed results
            
        Returns:
            Dictionary of evaluation metrics or tuple of (metrics, details)
        """
        strategy_name = name or strategy.name
        params = params or {}
        backtest_params = backtest_params or {}
        
        # Log the strategy
        self.metadata['strategies'].append(strategy_name)
        
        # Process data
        processed_data = self.data_processor.process(data)
        
        # Split data if requested
        if train_test_split:
            train_data, val_data, test_data = self.data_processor.split_time_periods(processed_data)
            
            # Store data info in metadata
            self.metadata['data_info'] = {
                'total_samples': len(processed_data),
                'train_samples': len(train_data),
                'val_samples': len(val_data),
                'test_samples': len(test_data),
                'train_period': f"{train_data['timestamp'].iloc[0]} to {train_data['timestamp'].iloc[-1]}",
                'val_period': f"{val_data['timestamp'].iloc[0]} to {val_data['timestamp'].iloc[-1]}",
                'test_period': f"{test_data['timestamp'].iloc[0]} to {test_data['timestamp'].iloc[-1]}"
            }
            
            # Backtest the strategy
            positions, trades = strategy.backtest(test_data, **backtest_params)
        else:
            # Backtest on the entire dataset
            positions, trades = strategy.backtest(processed_data, **backtest_params)
            
            # Store data info in metadata
            self.metadata['data_info'] = {
                'total_samples': len(processed_data),
                'period': f"{processed_data['timestamp'].iloc[0]} to {processed_data['timestamp'].iloc[-1]}"
            }
        
        # Calculate metrics
        metrics = self.metrics_calculator.calculate(positions, trades, processed_data)
        
        # Store results
        self.results[strategy_name] = {
            'metrics': metrics,
            'positions': positions,
            'trades': trades,
            'params': params,
            'backtest_params': backtest_params
        }
        
        # Update metadata
        self.metadata['metrics'][strategy_name] = metrics
        
        if return_details:
            return metrics, self.results[strategy_name]
        else:
            return metrics
    
    def compare_strategies(self, 
                           strategy_names: List[str] = None,
                           tests: List[str] = None) -> Dict[str, Any]:
        """
        Compare multiple strategies using statistical tests.
        
        Args:
            strategy_names: List of strategy names to compare (defaults to all evaluated)
            tests: List of tests to perform
            
        Returns:
            Dictionary with comparison results
        """
        if not self.results:
            raise ValueError("No strategies have been evaluated yet")
        
        # Default to all strategies if none specified
        strategy_names = strategy_names or list(self.results.keys())
        
        if len(strategy_names) < 2:
            raise ValueError("Need at least two strategies to compare")
        
        # Check that all specified strategies have been evaluated
        missing = [name for name in strategy_names if name not in self.results]
        if missing:
            raise ValueError(f"Strategies not found: {missing}")
        
        # Perform pairwise comparisons
        comparison_results = {}
        
        for i, name1 in enumerate(strategy_names):
            for name2 in strategy_names[i+1:]:
                # Extract returns
                returns1 = self.results[name1]['positions']['daily_return'].values
                returns2 = self.results[name2]['positions']['daily_return'].values
                
                # Perform statistical tests
                result = self.statistical_tester.compare_strategies(returns1, returns2, tests)
                
                # Store results
                key = f"{name1} vs {name2}"
                comparison_results[key] = result
        
        # Update metadata
        self.metadata['comparison_results'] = comparison_results
        
        return comparison_results
    
    def save_results(self, 
                     include_positions: bool = True,
                     include_trades: bool = True) -> str:
        """
        Save experiment results to file.
        
        Args:
            include_positions: Whether to include positions DataFrames
            include_trades: Whether to include trades DataFrames
            
        Returns:
            Path to the saved results file
        """
        # Update end time
        self.metadata['end_time'] = datetime.now().isoformat()
        
        # Create a copy of results to save
        results_to_save = {
            'metadata': self.metadata,
            'strategies': {}
        }
        
        for name, result in self.results.items():
            strategy_result = {
                'metrics': result['metrics'],
                'params': result['params'],
                'backtest_params': result['backtest_params']
            }
            
            if include_positions:
                strategy_result['positions'] = result['positions'].to_dict(orient='records')
            
            if include_trades and 'trades' in result and not result['trades'].empty:
                strategy_result['trades'] = result['trades'].to_dict(orient='records')
            
            results_to_save['strategies'][name] = strategy_result
        
        # Create experiment directory
        experiment_path = os.path.join(self.experiment_dir, self.experiment_id)
        if not os.path.exists(experiment_path):
            os.makedirs(experiment_path)
        
        # Save results to JSON file
        results_path = os.path.join(experiment_path, 'results.json')
        with open(results_path, 'w') as f:
            json.dump(results_to_save, f, indent=2)
        
        return results_path
    
    def load_results(self, experiment_id: str) -> Dict[str, Any]:
        """
        Load experiment results from file.
        
        Args:
            experiment_id: ID of the experiment to load
            
        Returns:
            Dictionary with experiment results
        """
        experiment_path = os.path.join(self.experiment_dir, experiment_id)
        results_path = os.path.join(experiment_path, 'results.json')
        
        if not os.path.exists(results_path):
            raise ValueError(f"Results file not found: {results_path}")
        
        with open(results_path, 'r') as f:
            results = json.load(f)
        
        # Update instance variables
        self.experiment_id = experiment_id
        self.metadata = results['metadata']
        
        # Convert positions and trades back to DataFrames
        self.results = {}
        
        for name, result in results['strategies'].items():
            strategy_result = {
                'metrics': result['metrics'],
                'params': result.get('params', {}),
                'backtest_params': result.get('backtest_params', {})
            }
            
            if 'positions' in result:
                strategy_result['positions'] = pd.DataFrame(result['positions'])
            
            if 'trades' in result:
                strategy_result['trades'] = pd.DataFrame(result['trades'])
            
            self.results[name] = strategy_result
        
        return results
    
    def get_best_strategy(self, 
                          metric: str = 'sharpe_ratio', 
                          higher_is_better: bool = True) -> str:
        """
        Get the name of the best-performing strategy according to a specific metric.
        
        Args:
            metric: Metric to compare (e.g., 'sharpe_ratio', 'total_return')
            higher_is_better: Whether higher values of the metric are better
            
        Returns:
            Name of the best strategy
        """
        if not self.results:
            raise ValueError("No strategies have been evaluated yet")
        
        # Extract metric values for each strategy
        metric_values = {}
        
        for name, result in self.results.items():
            if metric in result['metrics']:
                metric_values[name] = result['metrics'][metric]
            else:
                raise ValueError(f"Metric '{metric}' not found for strategy '{name}'")
        
        # Find the best strategy
        if higher_is_better:
            best_strategy = max(metric_values.items(), key=lambda x: x[1])[0]
        else:
            best_strategy = min(metric_values.items(), key=lambda x: x[1])[0]
        
        return best_strategy
    
    def get_experiment_summary(self) -> Dict[str, Any]:
        """
        Generate a summary of the experiment.
        
        Returns:
            Dictionary with experiment summary
        """
        if not self.results:
            raise ValueError("No strategies have been evaluated yet")
        
        # Extract key metrics for each strategy
        key_metrics = ['total_return', 'sharpe_ratio', 'sortino_ratio', 'max_drawdown']
        
        summary = {
            'experiment_id': self.experiment_id,
            'start_time': self.metadata.get('start_time'),
            'end_time': self.metadata.get('end_time'),
            'strategies': self.metadata.get('strategies', []),
            'data_info': self.metadata.get('data_info', {}),
            'metrics': {},
            'best_strategies': {}
        }
        
        # Compile metrics
        for name, result in self.results.items():
            summary['metrics'][name] = {
                metric: result['metrics'].get(metric)
                for metric in key_metrics
                if metric in result['metrics']
            }
        
        # Find best strategy for each metric
        for metric in key_metrics:
            try:
                if metric == 'max_drawdown':
                    # For drawdown, lower is better
                    best = self.get_best_strategy(metric, higher_is_better=False)
                else:
                    best = self.get_best_strategy(metric)
                
                summary['best_strategies'][metric] = best
            except ValueError:
                pass  # Metric not available for all strategies
        
        # Add statistical comparison results if available
        if self.metadata.get('comparison_results'):
            summary['comparison_results'] = {
                comparison: result.get('overall', {})
                for comparison, result in self.metadata['comparison_results'].items()
            }
        
        return summary 