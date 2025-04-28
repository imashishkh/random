"""
Airflow DAG for nightly retraining of agent models.

This DAG handles the extraction of training data, preprocessing, model training,
validation, and deployment of agent models used in the Forex Trading system.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
import contextlib

# Airflow imports
from airflow import DAG
from airflow.decorators import task
from airflow.utils.dates import days_ago
from airflow.models import Variable
from airflow.models.connection import Connection
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator
from airflow.exceptions import AirflowSkipException, AirflowFailException

# Project imports
import pandas as pd
import numpy as np
from ...db.connection import get_connection, execute_query
from ...utils.logging.logger import get_logger
from ...rl.utils.feature_extraction import FeatureExtractor

# Set up logging
logger = get_logger(__name__)

# Default arguments for the DAG
default_args = {
    'owner': 'ml_team',
    'depends_on_past': False,
    'email': ['ml-alerts@example.com'],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(minutes=60),
    'start_date': days_ago(1),
    'pool': 'ml_training_pool',
}

# Create the DAG
with DAG(
    dag_id='agent_model_retraining',
    default_args=default_args,
    description='DAG for nightly retraining of agent models',
    schedule_interval='0 2 * * *',  # Run at 2 AM daily
    catchup=False,
    tags=['ml', 'agent', 'retraining'],
    doc_md=__doc__
) as dag:
    
    # Helper function to create directory if it doesn't exist
    def ensure_dir(dir_path: str) -> str:
        """Create directory if it doesn't exist and return the path."""
        os.makedirs(dir_path, exist_ok=True)
        return dir_path
    
    # Define model storage directories
    MODEL_BASE_DIR = Variable.get('model_storage_dir', '/opt/airflow/models')
    DATA_BASE_DIR = Variable.get('data_storage_dir', '/opt/airflow/data')
    
    @task(retries=2, retry_delay=timedelta(minutes=2))
    def extract_training_data(**context) -> Dict[str, Any]:
        """
        Extract training data for agent model retraining.
        
        This task extracts historical trading data, agent performance metrics,
        and signal validation results from the database for model training.
        
        Returns:
            Dict containing paths to extracted data files and metadata.
        """
        try:
            # Get execution date for versioning
            execution_date = context['ds']  # Format: YYYY-MM-DD
            execution_ts = context['ts']    # Format: YYYY-MM-DDTHH:MM:SS+00:00
            
            # Define data storage paths
            data_dir = ensure_dir(f"{DATA_BASE_DIR}/{execution_date}")
            
            # Initialize result dictionary
            result = {
                'execution_date': execution_date,
                'execution_ts': execution_ts,
                'data_dir': data_dir,
                'files': {},
                'metrics': {
                    'total_records': 0,
                    'agent_types': [],
                    'date_range': {'start': None, 'end': None}
                }
            }
            
            logger.info(f"Extracting training data for execution date: {execution_date}")
            
            # Extract signal validation data
            with get_connection() as conn:
                # Get trading signals with outcomes
                signals_query = """
                    SELECT 
                        s.id,
                        s.agent_id,
                        s.trading_pair,
                        s.agent_type,
                        s.signal_time,
                        s.confidence,
                        s.strength,
                        s.direction,
                        s.timeframe,
                        s.metadata,
                        t.outcome_profit_pct,
                        t.was_profitable,
                        t.created_at,
                        t.updated_at
                    FROM 
                        trading_signals s
                    JOIN 
                        signal_outcomes t ON s.id = t.signal_id
                    WHERE
                        t.created_at >= %s AND t.created_at < %s
                """
                
                # Calculate date range (last 30 days by default)
                end_date = datetime.strptime(execution_date, '%Y-%m-%d')
                start_date = end_date - timedelta(days=30)
                
                # Execute query
                signals_data = execute_query(
                    signals_query, 
                    (start_date.strftime('%Y-%m-%d'), execution_date)
                )
                
                # Convert to DataFrame
                signals_df = pd.DataFrame(signals_data)
                
                if not signals_df.empty:
                    # Update metrics
                    result['metrics']['total_records'] += len(signals_df)
                    result['metrics']['agent_types'] = signals_df['agent_type'].unique().tolist()
                    result['metrics']['date_range']['start'] = signals_df['created_at'].min().isoformat()
                    result['metrics']['date_range']['end'] = signals_df['created_at'].max().isoformat()
                    
                    # Save to CSV
                    signals_file = f"{data_dir}/signals_data.csv"
                    signals_df.to_csv(signals_file, index=False)
                    result['files']['signals'] = signals_file
                    
                    logger.info(f"Extracted {len(signals_df)} signal records")
                else:
                    logger.warning("No signal data found for the specified date range")
                
                # Extract agent performance metrics
                performance_query = """
                    SELECT 
                        agent_id,
                        agent_type,
                        metric_name,
                        metric_value,
                        timestamp
                    FROM 
                        agent_performance_metrics
                    WHERE
                        timestamp >= %s AND timestamp < %s
                """
                
                performance_data = execute_query(
                    performance_query, 
                    (start_date.strftime('%Y-%m-%d'), execution_date)
                )
                
                # Convert to DataFrame
                performance_df = pd.DataFrame(performance_data)
                
                if not performance_df.empty:
                    # Update metrics
                    result['metrics']['total_records'] += len(performance_df)
                    
                    # Save to CSV
                    performance_file = f"{data_dir}/performance_data.csv"
                    performance_df.to_csv(performance_file, index=False)
                    result['files']['performance'] = performance_file
                    
                    logger.info(f"Extracted {len(performance_df)} performance records")
                else:
                    logger.warning("No performance data found for the specified date range")
                
                # Extract market data for context
                market_query = """
                    SELECT 
                        symbol,
                        timeframe,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        timestamp
                    FROM 
                        market_data
                    WHERE
                        timestamp >= %s AND timestamp < %s
                    ORDER BY
                        symbol, timeframe, timestamp
                """
                
                market_data = execute_query(
                    market_query, 
                    (start_date.strftime('%Y-%m-%d'), execution_date)
                )
                
                # Convert to DataFrame
                market_df = pd.DataFrame(market_data)
                
                if not market_df.empty:
                    # Save to CSV
                    market_file = f"{data_dir}/market_data.csv"
                    market_df.to_csv(market_file, index=False)
                    result['files']['market'] = market_file
                    
                    logger.info(f"Extracted {len(market_df)} market data records")
                else:
                    logger.warning("No market data found for the specified date range")
            
            # Save metadata for later tasks
            metadata_file = f"{data_dir}/metadata.json"
            with open(metadata_file, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            
            logger.info(f"Data extraction complete. Results saved to {data_dir}")
            return result
            
        except Exception as e:
            logger.error(f"Error extracting training data: {str(e)}")
            raise
    
    def validate_data_quality(df: pd.DataFrame, validation_config: Dict = None) -> Dict[str, Any]:
        """
        Validate the quality of the input data.
        
        Args:
            df: DataFrame to validate
            validation_config: Configuration parameters for validation
            
        Returns:
            Dict with validation results including pass/fail status and issues
        """
        if validation_config is None:
            validation_config = {
                'min_rows': 100,
                'max_missing_pct': 0.05,
                'max_outlier_pct': 0.10,
                'max_correlation': 0.95
            }
            
        validation_results = {
            'passed': True,
            'issues': []
        }
        
        # Skip validation for empty dataframes
        if df.empty:
            validation_results['passed'] = False
            validation_results['issues'].append("DataFrame is empty")
            return validation_results
        
        # Check for sufficient data
        if len(df) < validation_config['min_rows']:
            validation_results['issues'].append(
                f"Insufficient data: {len(df)} rows (minimum {validation_config['min_rows']})"
            )
        
        # Check for missing values
        missing_pct = df.isnull().mean()
        high_missing_cols = missing_pct[missing_pct > validation_config['max_missing_pct']].index.tolist()
        if high_missing_cols:
            validation_results['issues'].append(
                f"High missing values in columns: {high_missing_cols}"
            )
        
        # Check for outliers using IQR method
        for col in df.select_dtypes(include=['float64', 'int64']).columns:
            # Skip if column has too many missing values
            if df[col].isnull().mean() > 0.5:
                continue
                
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            
            # Skip if IQR is too small (near constant values)
            if IQR < 1e-10:
                continue
                
            outlier_pct = ((df[col] < (Q1 - 1.5 * IQR)) | (df[col] > (Q3 + 1.5 * IQR))).mean()
            if outlier_pct > validation_config['max_outlier_pct']:
                validation_results['issues'].append(
                    f"High outlier percentage ({outlier_pct:.2%}) in column: {col}"
                )
        
        # Check for feature correlation (only if there are sufficient numeric columns)
        numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
        if len(numeric_cols) > 5:  # Only check correlation for datasets with multiple features
            corr_matrix = df[numeric_cols].corr().abs()
            high_corr_pairs = []
            for i in range(len(corr_matrix.columns)):
                for j in range(i+1, len(corr_matrix.columns)):
                    if corr_matrix.iloc[i, j] > validation_config['max_correlation']:
                        high_corr_pairs.append((corr_matrix.columns[i], corr_matrix.columns[j]))
            
            if high_corr_pairs:
                # Limit the number of pairs shown in the message
                shown_pairs = high_corr_pairs[:5]
                additional_pairs = len(high_corr_pairs) - len(shown_pairs)
                
                message = f"High correlation (>{validation_config['max_correlation']}) between features: {shown_pairs}"
                if additional_pairs > 0:
                    message += f" and {additional_pairs} more pairs"
                    
                validation_results['issues'].append(message)
        
        # Set overall pass/fail status
        validation_results['passed'] = len(validation_results['issues']) == 0
        
        # Add summary statistics
        validation_results['summary'] = {
            'row_count': len(df),
            'column_count': len(df.columns),
            'missing_values_avg': df.isnull().mean().mean(),
            'timestamp': datetime.now().isoformat()
        }
        
        return validation_results
    
    def create_walk_forward_split(
        df: pd.DataFrame, 
        time_column: str = 'timestamp',
        n_splits: int = 5, 
        test_size: float = 0.2
    ) -> List[Dict[str, pd.DataFrame]]:
        """
        Creates walk-forward validation splits for time series data.
        
        Args:
            df: DataFrame with time series data
            time_column: Name of the timestamp column
            n_splits: Number of validation splits to create
            test_size: Size of each validation set as a proportion
            
        Returns:
            List of dictionaries containing training and validation data for each split
        """
        # Ensure data is sorted by time
        if time_column in df.columns:
            df = df.sort_values(by=time_column).reset_index(drop=True)
        
        splits = []
        total_size = len(df)
        fold_size = int(total_size / n_splits)
        
        for i in range(n_splits):
            # For the last fold, use all remaining data
            if i == n_splits - 1:
                end_idx = total_size
            else:
                end_idx = (i + 1) * fold_size
                
            # Calculate validation set size for this fold
            val_size = int(fold_size * test_size)
            
            # Create train/val split
            train_end = end_idx - val_size
            val_start = train_end
            
            # Create split with both indices and actual dataframes
            split = {
                'train_idx': list(range(0, train_end)),
                'val_idx': list(range(val_start, end_idx)),
                'train_data': df.iloc[:train_end].copy(),
                'val_data': df.iloc[val_start:end_idx].copy()
            }
            
            splits.append(split)
        
        return splits
    
    def get_data_statistics(df: pd.DataFrame) -> Dict[str, Any]:
        """
        Generate comprehensive statistics for monitoring data quality and drift.
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            Dict with statistical information
        """
        # Skip empty dataframes
        if df.empty:
            return {
                'row_count': 0,
                'column_count': 0,
                'timestamp': datetime.now().isoformat()
            }
        
        stats = {
            'row_count': len(df),
            'column_count': len(df.columns),
            'missing_values': df.isnull().sum().to_dict(),
            'missing_percentage': (df.isnull().mean() * 100).to_dict(),
            'numeric_stats': {},
            'categorical_stats': {},
            'timestamp': datetime.now().isoformat()
        }
        
        # Numeric column statistics
        for col in df.select_dtypes(include=['float64', 'int64']).columns:
            # Skip columns with too many missing values
            if df[col].isnull().mean() > 0.5:
                continue
                
            stats['numeric_stats'][col] = {
                'mean': float(df[col].mean()),
                'median': float(df[col].median()),
                'std': float(df[col].std()),
                'min': float(df[col].min()),
                'max': float(df[col].max()),
                'q1': float(df[col].quantile(0.25)),
                'q3': float(df[col].quantile(0.75))
            }
        
        # Categorical column statistics
        for col in df.select_dtypes(include=['object', 'category']).columns:
            value_counts = df[col].value_counts().to_dict()
            stats['categorical_stats'][col] = {
                'unique_count': df[col].nunique(),
                'top_values': dict(list(value_counts.items())[:10])
            }
        
        return stats
    
    def log_preprocessing_error(context: Dict, agent_type: str, error_message: str, extraction_output: Dict = None, traceback: str = None):
        """Log detailed information about preprocessing errors to simplify debugging."""
        logger.error(f"Error preprocessing data for {agent_type}: {error_message}")
        
        # Log additional context if available
        if extraction_output:
            logger.error(f"Extraction output for {agent_type}: {json.dumps(extraction_output, indent=2)}")
        
        # Log traceback if available
        if traceback:
            logger.error(f"Traceback for {agent_type}: {traceback}")
        
        # Push error to XCom for potential alert tasks
        ti = context['ti']
        ti.xcom_push(
            key=f"preprocessing_error_{agent_type}",
            value={
                "agent_type": agent_type,
                "error": error_message,
                "extraction_output": extraction_output,
                "traceback": traceback
            }
        )

    def load_model(model_path: str, model_type: str = 'ml'):
        """
        Load a trained model from disk based on the model type.
        
        Args:
            model_path: Path to the saved model file
            model_type: Type of model ('ml', 'classifier', 'rl', 'ensemble')
            
        Returns:
            Loaded model object
        """
        logger.info(f"Loading {model_type} model from {model_path}")
        
        if model_type == 'ml':
            # Standard ML model (sklearn, xgboost, etc.)
            return joblib.load(model_path)
        
        elif model_type == 'classifier':
            # Classification models (may need special handling)
            return joblib.load(model_path)
        
        elif model_type == 'rl':
            # Reinforcement learning models
            try:
                # Different RL libraries may have different loading methods
                # Check for common formats
                if model_path.endswith('.zip'):
                    import stable_baselines3 as sb3
                    # Try to determine algorithm type from filename
                    algo_types = ['PPO', 'A2C', 'DQN', 'SAC', 'TD3']
                    algo_type = next((algo for algo in algo_types if algo in model_path), 'PPO')
                    # Dynamic loading based on algorithm
                    algo_class = getattr(sb3, algo_type)
                    return algo_class.load(model_path)
                else:
                    # Fall back to joblib for custom RL models
                    return joblib.load(model_path)
            except Exception as e:
                logger.error(f"RL model loading error: {str(e)}")
                raise ValueError(f"Error loading RL model: {str(e)}")
            
        elif model_type == 'ensemble':
            # For ensemble models, load each component and return as dict/list
            import os
            import glob
            
            # Check if path is a directory for ensemble models
            if os.path.isdir(model_path):
                model_files = glob.glob(os.path.join(model_path, "*.joblib"))
                ensemble = {}
                for model_file in model_files:
                    model_name = os.path.basename(model_file).split('.')[0]
                    ensemble[model_name] = joblib.load(model_file)
                return ensemble
            else:
                # Single file ensemble
                return joblib.load(model_path)
        
        else:
            # For unknown types, try joblib as default
            logger.warning(f"Unknown model type: {model_type}, attempting to load with joblib")
            return joblib.load(model_path)

    def load_benchmark_model(agent_type: str):
        """
        Load a benchmark model for comparison with newly trained models.
        
        Args:
            agent_type: The type of agent model to load a benchmark for
            
        Returns:
            Benchmark model object or None if not available
        """
        # Get benchmark model configuration from Airflow variables
        benchmark_config = Variable.get(
            'benchmark_models',
            deserialize_json=True,
            default={}
        )
        
        # Check if we have a benchmark for this agent type
        if agent_type not in benchmark_config:
            logger.info(f"No benchmark model configured for {agent_type}")
            return None
        
        agent_benchmark = benchmark_config[agent_type]
        
        # Load the benchmark model
        try:
            model_path = agent_benchmark.get('model_path', '')
            model_type = agent_benchmark.get('model_type', 'ml')
            
            if not model_path:
                logger.warning(f"Missing model path for {agent_type} benchmark")
                return None
            
            return load_model(model_path, model_type)
        
        except Exception as e:
            logger.warning(f"Error loading benchmark model for {agent_type}: {str(e)}")
            return None

    def prepare_validation_data(validation_data: pd.DataFrame, model_type: str = 'ml'):
        """
        Prepare features and targets from validation data based on model type.
        
        Args:
            validation_data: DataFrame containing validation data
            model_type: Type of model ('ml', 'classifier', 'rl', 'ensemble')
            
        Returns:
            Tuple of (features, targets) or Dictionary with prepared data for specific model types
        """
        # Make a copy to avoid modifying the original data
        data = validation_data.copy()
        
        # For RL models, we might need a different format
        if model_type == 'rl':
            # RL often needs state, action, reward format
            # This is a simplified example, adjust based on your actual data structure
            if all(col in data.columns for col in ['state', 'action', 'reward']):
                return {
                    'states': data['state'].values,
                    'actions': data['action'].values,
                    'rewards': data['reward'].values,
                    'next_states': data['next_state'].values if 'next_state' in data.columns else None,
                    'dones': data['done'].values if 'done' in data.columns else None
                }
        
        # For traditional ML models, extract features and targets
        # First, try to identify target column(s)
        target_cols = []
        for col in ['target', 'label', 'y', 'action', 'signal', 'prediction']:
            if col in data.columns:
                target_cols.append(col)
            
        # If we couldn't find a target column, use a heuristic
        if not target_cols:
            # Assume last column is target in financial data
            target_cols = [data.columns[-1]]
            logger.warning(f"No obvious target column found, using {target_cols[0]}")
        
        # Extract targets
        y = data[target_cols]
        
        # Extract features (all columns except targets and non-feature columns)
        non_feature_cols = target_cols + ['timestamp', 'date', 'time', 'datetime', 'index', 'id']
        feature_cols = [col for col in data.columns if col not in non_feature_cols]
        
        # Ensure we have features
        if not feature_cols:
            logger.warning("No feature columns identified")
            # In this case, we'll use all columns except the identified target
            feature_cols = [col for col in data.columns if col not in target_cols]
        
        X = data[feature_cols]
        
        # For ensemble models, we might need more complex preparation
        if model_type == 'ensemble':
            return {
                'features': X,
                'targets': y,
                'feature_names': feature_cols,
                'target_names': target_cols
            }
        
        # For standard ML and classifiers, return X, y
        return X, y

    def simulate_trades(predictions: np.ndarray, targets: np.ndarray, initial_capital: float = 10000.0):
        """
        Simulate trading based on model predictions to calculate performance metrics.
        
        Args:
            predictions: Model predictions (signals)
            targets: Actual price movements or returns
            initial_capital: Starting capital for simulation
            
        Returns:
            Dictionary with performance metrics and equity curve
        """
        # Ensure predictions and targets are numpy arrays
        preds = np.array(predictions).flatten()
        actual = np.array(targets).flatten()
        
        # Ensure both arrays are the same length
        min_length = min(len(preds), len(actual))
        preds = preds[:min_length]
        actual = actual[:min_length]
        
        # Initialize tracking variables
        capital = initial_capital
        position = 0  # 0 = no position, 1 = long, -1 = short
        trades = []
        equity_curve = [capital]
        
        # Trading simulation
        for i in range(min_length):
            # Get the signal
            signal = np.sign(preds[i])  # +1 for buy, -1 for sell, 0 for hold
            
            # Only trade on non-zero signals
            if signal != 0:
                # Close existing position if opposite direction
                if position != 0 and position != signal:
                    # Calculate profit/loss
                    pnl = position * actual[i]
                    capital += pnl
                    trades.append(pnl)
                    
                    # Open new position
                    position = signal
                
                # Open new position if not already in one
                elif position == 0:
                    position = signal
            
            # Update equity curve
            if position != 0:
                # If in a position, update capital with unrealized P&L
                current_capital = capital + (position * actual[i])
            else:
                current_capital = capital
            
            equity_curve.append(current_capital)
        
        # Close final position
        if position != 0:
            final_pnl = position * actual[-1]
            capital += final_pnl
            trades.append(final_pnl)
        
        # Calculate basic metrics
        returns = np.diff(equity_curve) / np.array(equity_curve[:-1])
        
        # Return performance metrics
        return {
            'final_capital': capital,
            'total_return': (capital / initial_capital) - 1,
            'equity_curve': equity_curve,
            'returns': returns.tolist(),
            'trades': trades,
            'win_rate': np.sum(np.array(trades) > 0) / max(len(trades), 1),
            'profit_factor': abs(np.sum(np.array(trades)[np.array(trades) > 0]) / 
                              np.sum(np.array(trades)[np.array(trades) < 0])) 
                              if np.sum(np.array(trades)[np.array(trades) < 0]) != 0 else float('inf'),
            'sharpe_ratio': np.mean(returns) / (np.std(returns) + 1e-9) * np.sqrt(252),  # Annualized
            'max_drawdown': calculate_max_drawdown(equity_curve)
        }

    def calculate_sharpe_ratio(returns: Union[List[float], np.ndarray], risk_free_rate: float = 0.0, periods_per_year: int = 252):
        """
        Calculate the Sharpe ratio of returns.
        
        Args:
            returns: Array of period returns
            risk_free_rate: Risk-free rate (default 0)
            periods_per_year: Number of periods in a year (252 trading days by default)
            
        Returns:
            Sharpe ratio
        """
        returns_array = np.array(returns)
        
        # Handle empty or constant returns
        if len(returns_array) == 0 or np.std(returns_array) == 0:
            return 0.0
        
        excess_returns = returns_array - risk_free_rate
        sharpe = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(periods_per_year)
        
        return sharpe

    def calculate_max_drawdown(equity_curve: Union[List[float], np.ndarray]):
        """
        Calculate the maximum drawdown of an equity curve.
        
        Args:
            equity_curve: Array or list of equity values over time
            
        Returns:
            Maximum drawdown as a percentage (negative value)
        """
        # Convert to numpy array if not already
        equity = np.array(equity_curve)
        
        # Handle empty or single value arrays
        if len(equity) <= 1:
            return 0.0
        
        # Calculate running maximum
        running_max = np.maximum.accumulate(equity)
        
        # Calculate drawdown in percentage terms
        drawdowns = (equity - running_max) / running_max
        
        # Return the worst drawdown (minimum value)
        return np.min(drawdowns) if len(drawdowns) > 0 else 0.0

    def calculate_win_rate(trades: Union[List[float], np.ndarray]):
        """
        Calculate the win rate of trades.
        
        Args:
            trades: List of trade profits/losses
            
        Returns:
            Win rate as a decimal (0.0 to 1.0)
        """
        trades_array = np.array(trades)
        
        # Handle empty trades array
        if len(trades_array) == 0:
            return 0.0
        
        # Calculate win rate
        wins = np.sum(trades_array > 0)
        return wins / len(trades_array)

    def calculate_profit_factor(trades: Union[List[float], np.ndarray]):
        """
        Calculate the profit factor of trades (gross profit / gross loss).
        
        Args:
            trades: List of trade profits/losses
            
        Returns:
            Profit factor (>1 is profitable)
        """
        trades_array = np.array(trades)
        
        # Handle empty trades array
        if len(trades_array) == 0:
            return 0.0
        
        # Calculate profits and losses
        profits = trades_array[trades_array > 0]
        losses = trades_array[trades_array < 0]
        
        # Calculate profit factor
        gross_profit = np.sum(profits) if len(profits) > 0 else 0.0
        gross_loss = abs(np.sum(losses)) if len(losses) > 0 else 0.0
        
        # Handle division by zero
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        
        return gross_profit / gross_loss

    def calculate_total_return(equity_curve: Union[List[float], np.ndarray]):
        """
        Calculate the total return of an equity curve.
        
        Args:
            equity_curve: Array or list of equity values over time
            
        Returns:
            Total return as a decimal (e.g., 0.15 for 15%)
        """
        # Handle empty or single value arrays
        if len(equity_curve) <= 1:
            return 0.0
        
        # Calculate total return
        return (equity_curve[-1] / equity_curve[0]) - 1.0

    def calculate_volatility(returns: Union[List[float], np.ndarray], periods_per_year: int = 252):
        """
        Calculate the annualized volatility of returns.
        
        Args:
            returns: Array of period returns
            periods_per_year: Number of periods in a year (252 trading days by default)
            
        Returns:
            Annualized volatility
        """
        returns_array = np.array(returns)
        
        # Handle empty or constant returns
        if len(returns_array) <= 1:
            return 0.0
        
        # Calculate annualized volatility
        return np.std(returns_array) * np.sqrt(periods_per_year)

    def calculate_sortino_ratio(returns: Union[List[float], np.ndarray], risk_free_rate: float = 0.0, periods_per_year: int = 252):
        """
        Calculate the Sortino ratio of returns (downside risk only).
        
        Args:
            returns: Array of period returns
            risk_free_rate: Risk-free rate (default 0)
            periods_per_year: Number of periods in a year (252 trading days by default)
            
        Returns:
            Sortino ratio
        """
        returns_array = np.array(returns)
        
        # Handle empty or constant returns
        if len(returns_array) <= 1:
            return 0.0
        
        # Calculate excess returns
        excess_returns = returns_array - risk_free_rate
        
        # Calculate downside returns (negative returns only)
        downside_returns = excess_returns[excess_returns < 0]
        
        # Handle the case where there are no downside returns
        if len(downside_returns) == 0:
            return float('inf') if np.mean(excess_returns) > 0 else 0.0
        
        # Calculate downside deviation
        downside_deviation = np.sqrt(np.mean(np.square(downside_returns)))
        
        # Handle division by zero
        if downside_deviation == 0:
            return float('inf') if np.mean(excess_returns) > 0 else 0.0
        
        # Calculate Sortino ratio
        return np.mean(excess_returns) / downside_deviation * np.sqrt(periods_per_year)

    def calculate_calmar_ratio(returns: Union[List[float], np.ndarray], equity_curve: Union[List[float], np.ndarray], periods_per_year: int = 252):
        """
        Calculate the Calmar ratio (annualized return / max drawdown).
        
        Args:
            returns: Array of period returns
            equity_curve: Array of equity values over time
            periods_per_year: Number of periods in a year (252 trading days by default)
            
        Returns:
            Calmar ratio
        """
        # Calculate annualized return
        annualized_return = np.mean(returns) * periods_per_year if len(returns) > 0 else 0.0
        
        # Calculate max drawdown
        max_dd = calculate_max_drawdown(equity_curve)
        
        # Handle division by zero or very small drawdown
        if max_dd >= 0 or abs(max_dd) < 1e-6:
            return 0.0 if annualized_return == 0 else float('inf')
        
        # Calculate Calmar ratio
        return annualized_return / abs(max_dd)

    def evaluate_window_performance(metrics: Dict[str, float], thresholds: Dict[str, float]) -> bool:
        """
        Evaluate if a window's performance passes validation thresholds.
        
        Args:
            metrics: Dictionary of performance metrics
            thresholds: Dictionary of metric thresholds
            
        Returns:
            Boolean indicating if performance is acceptable
        """
        # Check each applicable threshold
        for metric, threshold in thresholds.items():
            # Skip consistency factor - it's for overall evaluation
            if metric == 'consistency_factor':
                continue
            
            # Extract metric name and threshold type (min/max)
            parts = metric.split('_')
            if len(parts) > 1 and (parts[-1] == 'min' or parts[-1] == 'max'):
                metric_name = '_'.join(parts[:-1])
                threshold_type = parts[-1]
                
                # Check if metric exists in results
                if metric_name in metrics:
                    value = metrics[metric_name]
                    
                    # Check minimum thresholds
                    if threshold_type == 'min' and value < threshold:
                        return False
                    
                    # Check maximum thresholds
                    if threshold_type == 'max' and value > threshold:
                        return False
        
        # All thresholds passed
        return True

    def calculate_overall_metrics(window_metrics: List[Dict]) -> Dict[str, float]:
        """
        Calculate overall metrics across all validation windows.
        
        Args:
            window_metrics: List of dictionaries containing window-specific metrics
            
        Returns:
            Dictionary of aggregated metrics
        """
        # Count windows that passed validation
        total_windows = len(window_metrics)
        passed_windows = sum(1 for w in window_metrics if w.get('passed', False))
        
        # Calculate consistency (% of windows that passed)
        consistency = passed_windows / total_windows if total_windows > 0 else 0
        
        # Aggregate metrics across windows
        aggregated = {
            'total_windows': total_windows,
            'passed_windows': passed_windows,
            'consistency': consistency
        }
        
        # If there are no windows, return early
        if total_windows == 0:
            return aggregated
        
        # Collect metrics from all windows
        for metric_name in ['sharpe_ratio', 'win_rate', 'profit_factor', 'total_return', 'max_drawdown']:
            # Extract metric values across all windows
            values = [
                w['metrics'].get(metric_name, 0) 
                for w in window_metrics 
                if 'metrics' in w and metric_name in w['metrics']
            ]
            
            # Skip if no values available
            if not values:
                continue
            
            # Calculate aggregate statistics
            aggregated[metric_name] = np.mean(values)
            aggregated[f"{metric_name}_min"] = np.min(values)
            aggregated[f"{metric_name}_max"] = np.max(values)
            aggregated[f"{metric_name}_std"] = np.std(values)
        
        return aggregated

    def generate_validation_report(agent_type: str, validation_results: Dict, output_dir: str) -> str:
        """
        Generate a detailed validation report with visualizations.
        
        Args:
            agent_type: The agent type being validated
            validation_results: Dictionary containing validation metrics and results
            output_dir: Directory to save the report to
            
        Returns:
            Path to the generated report file
        """
        # Create unique report filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"{agent_type}_validation_{timestamp}.html"
        report_path = os.path.join(output_dir, report_filename)
        
        # Create a basic HTML report
        with open(report_path, 'w') as f:
            # Write HTML header
            f.write(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Validation Report: {agent_type}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .header {{ background-color: #f0f0f0; padding: 10px; border-bottom: 1px solid #ccc; }}
                    .section {{ margin: 20px 0; }}
                    .passed {{ color: green; }}
                    .failed {{ color: red; }}
                    table {{ border-collapse: collapse; width: 100%; }}
                    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                    th {{ background-color: #f2f2f2; }}
                    tr:nth-child(even) {{ background-color: #f9f9f9; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>Model Validation Report: {agent_type}</h1>
                    <p>Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                    <p class="{'passed' if validation_results.get('passed', False) else 'failed'}">
                        Overall Status: {'PASSED' if validation_results.get('passed', False) else 'FAILED'}
                    </p>
                </div>
            """)
            
            # Add overall metrics section
            f.write("""
                <div class="section">
                    <h2>Overall Metrics</h2>
                    <table>
                        <tr>
                            <th>Metric</th>
                            <th>Value</th>
                            <th>Min</th>
                            <th>Max</th>
                            <th>Std Dev</th>
                        </tr>
            """)
            
            # Add rows for each metric
            overall = validation_results.get('overall', {})
            for metric in ['sharpe_ratio', 'win_rate', 'profit_factor', 'total_return', 'max_drawdown', 'consistency']:
                if metric in overall:
                    f.write(f"""
                        <tr>
                            <td>{metric.replace('_', ' ').title()}</td>
                            <td>{overall.get(metric, 0):.4f}</td>
                            <td>{overall.get(f"{metric}_min", ''):.4f if f"{metric}_min" in overall else '-'}</td>
                            <td>{overall.get(f"{metric}_max", ''):.4f if f"{metric}_max" in overall else '-'}</td>
                            <td>{overall.get(f"{metric}_std", ''):.4f if f"{metric}_std" in overall else '-'}</td>
                        </tr>
                    """)
            
            f.write("</table></div>")
            
            # Add failure reasons if any
            failure_reasons = validation_results.get('failure_reasons', [])
            if failure_reasons:
                f.write("""
                    <div class="section">
                        <h2>Failure Reasons</h2>
                        <ul>
                """)
                
                for reason in failure_reasons:
                    f.write(f"<li>{reason}</li>")
                
                f.write("</ul></div>")
            
            # Add window results
            windows = validation_results.get('windows', [])
            if windows:
                f.write("""
                    <div class="section">
                        <h2>Validation Windows</h2>
                        <table>
                            <tr>
                                <th>Window</th>
                                <th>Time Range</th>
                                <th>Status</th>
                                <th>Sharpe</th>
                                <th>Win Rate</th>
                                <th>Max Drawdown</th>
                                <th>Total Return</th>
                            </tr>
                """)
                
                for window in windows:
                    metrics = window.get('metrics', {})
                    time_range = window.get('time_range', {})
                    time_desc = f"{time_range.get('start', 'N/A')} - {time_range.get('end', 'N/A')}"
                    
                    f.write(f"""
                        <tr>
                            <td>{window.get('window_idx', 'N/A')}</td>
                            <td>{time_desc}</td>
                            <td class="{'passed' if window.get('passed', False) else 'failed'}">
                                {'PASSED' if window.get('passed', False) else 'FAILED'}
                            </td>
                            <td>{metrics.get('sharpe_ratio', 0):.4f}</td>
                            <td>{metrics.get('win_rate', 0):.4f}</td>
                            <td>{metrics.get('max_drawdown', 0):.4f}</td>
                            <td>{metrics.get('total_return', 0):.4f}</td>
                        </tr>
                    """)
                
                f.write("</table></div>")
            
            # Close the HTML
            f.write("</body></html>")
        
        logger.info(f"Validation report generated at {report_path}")
        return report_path

    def validate_model_on_window(model, validation_data: pd.DataFrame, model_type: str = 'ml', benchmark_model = None):
        """
        Validate a model on a specific time window and calculate trading-specific metrics.
        
        Args:
            model: Trained model to validate
            validation_data: DataFrame containing validation data for this window
            model_type: Type of model ('ml', 'classifier', 'rl', 'ensemble')
            benchmark_model: Optional benchmark model to compare against
            
        Returns:
            Dictionary of performance metrics
        """
        # Prepare features and targets
        if model_type in ['ml', 'classifier']:
            X, y = prepare_validation_data(validation_data, model_type)
            
            # Make predictions
            try:
                predictions = model.predict(X)
            except Exception as e:
                logger.error(f"Error making predictions: {str(e)}")
                raise ValueError(f"Prediction error: {str(e)}")
            
            # Get benchmark predictions if available
            if benchmark_model is not None:
                try:
                    benchmark_predictions = benchmark_model.predict(X)
                except Exception as e:
                    logger.warning(f"Error making benchmark predictions: {str(e)}")
                    benchmark_predictions = None
                
        elif model_type == 'rl':
            # For RL models, we need a different approach
            data = prepare_validation_data(validation_data, model_type)
            
            # For RL, predictions might be actions based on states
            try:
                predictions = np.array([model.predict(state)[0] for state in data['states']])
            except Exception as e:
                logger.error(f"Error making RL predictions: {str(e)}")
                raise ValueError(f"RL prediction error: {str(e)}")
            
            # Use rewards as "true" values for performance calculation
            y = data['rewards']
            
            # Get benchmark predictions if available
            if benchmark_model is not None:
                try:
                    benchmark_predictions = np.array([benchmark_model.predict(state)[0] for state in data['states']])
                except Exception as e:
                    logger.warning(f"Error making benchmark RL predictions: {str(e)}")
                    benchmark_predictions = None
            
        elif model_type == 'ensemble':
            # For ensemble models, we need to handle multiple models
            data = prepare_validation_data(validation_data, model_type)
            X = data['features']
            y = data['targets']
            
            # Aggregating predictions from multiple models
            try:
                # If model is a dictionary of models
                if isinstance(model, dict):
                    # Simple ensemble: average predictions
                    individual_preds = [model.predict(X) for model in model.values()]
                    predictions = np.mean(individual_preds, axis=0)
                else:
                    # Model might have a predict method that handles ensemble logic
                    predictions = model.predict(X)
            except Exception as e:
                logger.error(f"Error making ensemble predictions: {str(e)}")
                raise ValueError(f"Ensemble prediction error: {str(e)}")
            
            # Get benchmark predictions if available
            if benchmark_model is not None:
                try:
                    if isinstance(benchmark_model, dict):
                        individual_preds = [model.predict(X) for model in benchmark_model.values()]
                        benchmark_predictions = np.mean(individual_preds, axis=0)
                    else:
                        benchmark_predictions = benchmark_model.predict(X)
                except Exception as e:
                    logger.warning(f"Error making benchmark ensemble predictions: {str(e)}")
                    benchmark_predictions = None
        else:
            raise ValueError(f"Unsupported model type: {model_type}")
        
        # If y is a DataFrame with multiple columns, use the first column
        if isinstance(y, pd.DataFrame) and y.shape[1] > 0:
            y = y.iloc[:, 0]
        
        # If y is a Series, convert to numpy array
        if isinstance(y, pd.Series):
            y = y.values
        
        # Simulate trading with model predictions
        trading_metrics = simulate_trades(predictions, y)
        
        # Simulate trading with benchmark predictions (if available)
        if benchmark_model is not None and benchmark_predictions is not None:
            benchmark_metrics = simulate_trades(benchmark_predictions, y)
            
            # Calculate comparative metrics
            for metric in ['total_return', 'sharpe_ratio', 'max_drawdown', 'win_rate', 'profit_factor']:
                if metric in trading_metrics and metric in benchmark_metrics:
                    trading_metrics[f'benchmark_{metric}'] = benchmark_metrics[metric]
                    
                    # Calculate relative improvement
                    benchmark_value = benchmark_metrics[metric]
                    model_value = trading_metrics[metric]
                    
                    # Handle metrics where higher is better
                    if metric in ['total_return', 'sharpe_ratio', 'win_rate', 'profit_factor']:
                        if benchmark_value != 0:
                            relative_improvement = (model_value - benchmark_value) / abs(benchmark_value)
                        else:
                            relative_improvement = float('inf') if model_value > 0 else 0
                            
                    # Handle metrics where lower is better (e.g., max_drawdown - which is negative)
                    else:
                        if benchmark_value != 0:
                            relative_improvement = (benchmark_value - model_value) / abs(benchmark_value)
                        else:
                            relative_improvement = float('inf') if model_value < 0 else 0
                    
                    trading_metrics[f'{metric}_vs_benchmark'] = relative_improvement
        
        return trading_metrics

    @task(
        retries=3,
        retry_delay=timedelta(minutes=5),
        execution_timeout=timedelta(hours=2),
        pool='model_preprocessing_pool',
        pool_slots=2
    )
    def preprocess_data(agent_types: List[str], extraction_date: str, **context) -> Dict[str, Any]:
        """
        Preprocess the extracted data for each agent type.
        
        This task handles data cleaning, feature engineering, and validation dataset creation
        for each agent. It prepares data in the format required for model training.
        
        Args:
            agent_types: List of agent types to preprocess data for
            extraction_date: Date string for the extraction run
            
        Returns:
            Dict containing paths to preprocessed training and validation data
        """
        try:
            # Get execution date for versioning
            execution_date = context['ds']
            
            # Get data directory and file paths from extraction output
            data_dir = context['data_dir']
            files = context['files']
            
            # Create processed data directory
            processed_dir = ensure_dir(f"{data_dir}/processed")
            
            # Initialize result object
            result = {
                'execution_date': execution_date,
                'processed_dir': processed_dir,
                'files': {},
                'stats': {},
                'validation': {},
                'splits': {}
            }
            
            logger.info(f"Starting data preprocessing for execution date: {execution_date}")
            
            # Check if required files exist
            if not files:
                logger.warning("No input files found from extraction task")
                result['validation']['overall'] = {
                    'passed': False,
                    'issues': ["No input files provided from extraction task"]
                }
                return result
            
            # Process market data if available
            if 'market' in files and os.path.exists(files['market']):
                market_file = files['market']
                logger.info(f"Processing market data from {market_file}")
                
                # Load market data
                market_df = pd.read_csv(market_file)
                
                # Convert timestamp to datetime
                if 'timestamp' in market_df.columns:
                    market_df['timestamp'] = pd.to_datetime(market_df['timestamp'])
                
                # Perform data validation
                market_validation = validate_data_quality(market_df)
                result['validation']['market'] = market_validation
                
                if not market_validation['passed']:
                    logger.warning(f"Market data validation issues: {market_validation['issues']}")
                
                # Group by symbol and timeframe for separate processing
                grouped = market_df.groupby(['symbol', 'timeframe'])
                
                # Dictionary to store processed dataframes
                processed_market_dfs = {}
                
                # Process each group separately
                for (symbol, timeframe), group_df in grouped:
                    # Sort by timestamp
                    group_df = group_df.sort_values('timestamp')
                    
                    # Feature engineering using FeatureExtractor
                    feature_extractor = FeatureExtractor(
                        window_size=30,
                        normalization="standard",
                        include_indicators=True,
                        include_volumes=True
                    )
                    
                    # Only process if we have enough data
                    if len(group_df) >= 50:  # Minimum rows needed for feature calculation
                        try:
                            # Transform the data
                            features = feature_extractor.fit_transform(group_df)
                            
                            # Get the processed dataframe with features
                            processed_df = feature_extractor._preprocess_data(group_df)
                            
                            # Store in dictionary
                            processed_market_dfs[(symbol, timeframe)] = processed_df
                            
                            logger.info(f"Successfully processed {len(processed_df)} rows for {symbol}/{timeframe}")
                        except Exception as e:
                            logger.warning(f"Error processing {symbol}/{timeframe}: {str(e)}")
                            continue
                
                # Save processed market data
                for (symbol, timeframe), processed_df in processed_market_dfs.items():
                    # Create directory for symbol
                    symbol_dir = ensure_dir(f"{processed_dir}/market/{symbol}")
                    
                    # Save to CSV
                    output_file = f"{symbol_dir}/{timeframe}.csv"
                    processed_df.to_csv(output_file, index=False)
                    
                    # Track in result
                    if 'market' not in result['files']:
                        result['files']['market'] = {}
                    
                    if symbol not in result['files']['market']:
                        result['files']['market'][symbol] = {}
                    
                    result['files']['market'][symbol][timeframe] = output_file
                    
                    # Calculate and store statistics
                    if 'market' not in result['stats']:
                        result['stats']['market'] = {}
                    
                    if symbol not in result['stats']['market']:
                        result['stats']['market'][symbol] = {}
                    
                    result['stats']['market'][symbol][timeframe] = get_data_statistics(processed_df)
                    
                    # Create walk-forward splits
                    if 'market' not in result['splits']:
                        result['splits']['market'] = {}
                    
                    if symbol not in result['splits']['market']:
                        result['splits']['market'][symbol] = {}
                    
                    # Create splits
                    splits = create_walk_forward_split(
                        processed_df,
                        time_column='timestamp',
                        n_splits=5,
                        test_size=0.2
                    )
                    
                    # Save splits
                    splits_dir = ensure_dir(f"{symbol_dir}/splits")
                    
                    for i, split in enumerate(splits):
                        # Save training data
                        train_file = f"{splits_dir}/fold_{i+1}_train.csv"
                        split['train_data'].to_csv(train_file, index=False)
                        
                        # Save validation data
                        val_file = f"{splits_dir}/fold_{i+1}_val.csv"
                        split['val_data'].to_csv(val_file, index=False)
                        
                        # Update split info
                        splits[i]['train_file'] = train_file
                        splits[i]['val_file'] = val_file
                        
                        # Remove dataframes to prevent serialization issues
                        del splits[i]['train_data']
                        del splits[i]['val_data']
                    
                    result['splits']['market'][symbol][timeframe] = splits
            else:
                logger.warning("No market data file found")
            
            # Process signals data if available
            if 'signals' in files and os.path.exists(files['signals']):
                signals_file = files['signals']
                logger.info(f"Processing signals data from {signals_file}")
                
                # Load signals data
                signals_df = pd.read_csv(signals_file)
                
                # Convert timestamp columns to datetime
                for col in ['signal_time', 'created_at', 'updated_at']:
                    if col in signals_df.columns:
                        signals_df[col] = pd.to_datetime(signals_df[col])
                
                # Perform data validation
                signals_validation = validate_data_quality(signals_df)
                result['validation']['signals'] = signals_validation
                
                if not signals_validation['passed']:
                    logger.warning(f"Signals data validation issues: {signals_validation['issues']}")
                
                # Process metadata column if it exists and contains JSON
                if 'metadata' in signals_df.columns:
                    # Try to parse JSON metadata
                    try:
                        # Convert JSON strings to dictionaries
                        signals_df['metadata_dict'] = signals_df['metadata'].apply(
                            lambda x: json.loads(x) if isinstance(x, str) else {}
                        )
                        
                        # Extract common fields from metadata if they exist
                        common_metadata_fields = [
                            'indicator_values', 'confidence_factors', 'timeframe_analysis'
                        ]
                        
                        for field in common_metadata_fields:
                            signals_df[f'metadata_{field}'] = signals_df['metadata_dict'].apply(
                                lambda x: json.dumps(x.get(field, {})) if isinstance(x, dict) else '{}'
                            )
                        
                        # Drop the intermediate dictionary column
                        signals_df.drop('metadata_dict', axis=1, inplace=True)
                    except Exception as e:
                        logger.warning(f"Error processing metadata column: {str(e)}")
                
                # Group by agent_type for separate processing
                grouped = signals_df.groupby('agent_type')
                
                # Dictionary to store processed dataframes
                processed_signals_dfs = {}
                
                # Process each agent type separately
                for agent_type, group_df in grouped:
                    # Sort by signal_time
                    if 'signal_time' in group_df.columns:
                        group_df = group_df.sort_values('signal_time')
                    
                    # Feature engineering
                    # 1. Calculate rolling statistics for confidence and profit
                    for window in [5, 10, 20]:
                        if 'confidence' in group_df.columns:
                            group_df[f'confidence_ma_{window}'] = group_df['confidence'].rolling(window).mean()
                            group_df[f'confidence_std_{window}'] = group_df['confidence'].rolling(window).std()
                        
                        if 'outcome_profit_pct' in group_df.columns:
                            group_df[f'profit_ma_{window}'] = group_df['outcome_profit_pct'].rolling(window).mean()
                            group_df[f'profit_std_{window}'] = group_df['outcome_profit_pct'].rolling(window).std()
                    
                    # 2. Calculate success rate in rolling windows
                    if 'was_profitable' in group_df.columns:
                        for window in [10, 20, 50]:
                            group_df[f'success_rate_{window}'] = group_df['was_profitable'].rolling(window).mean()
                    
                    # 3. Create other derivative features
                    if 'strength' in group_df.columns and 'confidence' in group_df.columns:
                        group_df['strength_confidence_ratio'] = group_df['strength'] / group_df['confidence'].clip(lower=0.01)
                    
                    # Store in dictionary
                    processed_signals_dfs[agent_type] = group_df
                
                # Save processed signals data
                for agent_type, processed_df in processed_signals_dfs.items():
                    # Create directory for agent type
                    agent_dir = ensure_dir(f"{processed_dir}/signals/{agent_type}")
                    
                    # Save to CSV
                    output_file = f"{agent_dir}/signals.csv"
                    processed_df.to_csv(output_file, index=False)
                    
                    # Track in result
                    if 'signals' not in result['files']:
                        result['files']['signals'] = {}
                    
                    result['files']['signals'][agent_type] = output_file
                    
                    # Calculate and store statistics
                    if 'signals' not in result['stats']:
                        result['stats']['signals'] = {}
                    
                    result['stats']['signals'][agent_type] = get_data_statistics(processed_df)
                    
                    # Create walk-forward splits
                    if 'signals' not in result['splits']:
                        result['splits']['signals'] = {}
                    
                    # Choose appropriate time column
                    time_column = 'signal_time' if 'signal_time' in processed_df.columns else 'created_at'
                    
                    if time_column in processed_df.columns:
                        # Create splits
                        splits = create_walk_forward_split(
                            processed_df,
                            time_column=time_column,
                            n_splits=5,
                            test_size=0.2
                        )
                        
                        # Save splits
                        splits_dir = ensure_dir(f"{agent_dir}/splits")
                        
                        for i, split in enumerate(splits):
                            # Save training data
                            train_file = f"{splits_dir}/fold_{i+1}_train.csv"
                            split['train_data'].to_csv(train_file, index=False)
                            
                            # Save validation data
                            val_file = f"{splits_dir}/fold_{i+1}_val.csv"
                            split['val_data'].to_csv(val_file, index=False)
                            
                            # Update split info
                            splits[i]['train_file'] = train_file
                            splits[i]['val_file'] = val_file
                            
                            # Remove dataframes to prevent serialization issues
                            del splits[i]['train_data']
                            del splits[i]['val_data']
                        
                        result['splits']['signals'][agent_type] = splits
            else:
                logger.warning("No signals data file found")
            
            # Process performance data if available
            if 'performance' in files and os.path.exists(files['performance']):
                performance_file = files['performance']
                logger.info(f"Processing performance data from {performance_file}")
                
                # Load performance data
                performance_df = pd.read_csv(performance_file)
                
                # Convert timestamp to datetime
                if 'timestamp' in performance_df.columns:
                    performance_df['timestamp'] = pd.to_datetime(performance_df['timestamp'])
                
                # Perform data validation
                performance_validation = validate_data_quality(performance_df)
                result['validation']['performance'] = performance_validation
                
                if not performance_validation['passed']:
                    logger.warning(f"Performance data validation issues: {performance_validation['issues']}")
                
                # Group by agent_type for separate processing
                grouped = performance_df.groupby('agent_type')
                
                # Dictionary to store processed dataframes
                processed_performance_dfs = {}
                
                # Process each agent type separately
                for agent_type, group_df in grouped:
                    # Sort by timestamp
                    if 'timestamp' in group_df.columns:
                        group_df = group_df.sort_values('timestamp')
                    
                    # Feature engineering: pivot metrics into columns
                    if 'metric_name' in group_df.columns and 'metric_value' in group_df.columns:
                        pivot_df = group_df.pivot_table(
                            index=['agent_id', 'timestamp'],
                            columns='metric_name',
                            values='metric_value',
                            aggfunc='first'
                        ).reset_index()
                        
                        # Flatten hierarchical column index
                        pivot_df.columns = [
                            '_'.join(col).strip('_') if isinstance(col, tuple) else col 
                            for col in pivot_df.columns.values
                        ]
                        
                        # Store pivoted data
                        processed_performance_dfs[agent_type] = pivot_df
                    else:
                        # If pivoting is not possible, use original data
                        processed_performance_dfs[agent_type] = group_df
                
                # Save processed performance data
                for agent_type, processed_df in processed_performance_dfs.items():
                    # Create directory for agent type
                    agent_dir = ensure_dir(f"{processed_dir}/performance/{agent_type}")
                    
                    # Save to CSV
                    output_file = f"{agent_dir}/performance.csv"
                    processed_df.to_csv(output_file, index=False)
                    
                    # Track in result
                    if 'performance' not in result['files']:
                        result['files']['performance'] = {}
                    
                    result['files']['performance'][agent_type] = output_file
                    
                    # Calculate and store statistics
                    if 'performance' not in result['stats']:
                        result['stats']['performance'] = {}
                    
                    result['stats']['performance'][agent_type] = get_data_statistics(processed_df)
            else:
                logger.warning("No performance data file found")
            
            # Save overall metadata
            metadata_file = f"{processed_dir}/metadata.json"
            with open(metadata_file, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            
            logger.info(f"Data preprocessing complete. Results saved to {processed_dir}")
            return result
            
        except Exception as e:
            logger.error(f"Error during data preprocessing: {str(e)}")
            log_preprocessing_error(context, agent_type, str(e), extraction_output=result, traceback=traceback.format_exc())
            raise
    
    # Create task instances
    extract_data = extract_training_data()
    preprocess_data_task = preprocess_data(extract_data)
    
    # Task dependencies
    extract_data >> preprocess_data_task
    # preprocess_data_task >> next_task  # To be defined in next subtask

    @task(
        retries=3,
        retry_delay=timedelta(minutes=5),
        execution_timeout=timedelta(hours=2),
        pool='model_validation_pool',
        pool_slots=2
    )
    def validate_models(
        preprocessing_output: Dict[str, Any],
        training_output: Dict[str, Any],
        **context
    ) -> Dict[str, Any]:
        """
        Validate trained models on out-of-sample data to ensure they meet performance requirements.
        
        This task implements walk-forward validation to test model performance across different
        market regimes, calculating key trading metrics like Sharpe ratio, drawdown, and win rate.
        Only models that pass validation criteria will be deployed to production.
        
        Args:
            preprocessing_output: Output from the preprocess_data task
            training_output: Output from the train_models task
            
        Returns:
            Dict containing validation results and paths to deployable models
        """
        logger.info("Starting model validation process")
        
        # Initialize validation output
        validation_output = {
            'passed_models': {},
            'failed_models': {},
            'validation_reports': {},
            'overall_status': 'failed',  # Default to failed, will update if any model passes
            'metrics': {}
        }
        
        # Get execution date for timestamping
        execution_date = context['ds']
        
        # Get validation thresholds from Airflow variables
        validation_thresholds = Variable.get(
            'validation_thresholds',
            deserialize_json=True,
            default={
                'default': {
                    'sharpe_ratio_min': 0.5,
                    'max_drawdown_max': -0.15,
                    'win_rate_min': 0.45,
                    'profit_factor_min': 1.1,
                    'consistency_factor': 0.7  # 70% of windows must pass
                }
            }
        )
        
        # Check if we have any trained models to validate
        if not training_output or 'models' not in training_output:
            logger.warning("No trained models found in training output. Skipping validation.")
            validation_output['error'] = "No trained models to validate"
            return validation_output
        
        # Get processed data path from preprocessing output
        if not preprocessing_output or 'processed_data_dir' not in preprocessing_output:
            logger.warning("Missing processed data. Cannot validate models.")
            validation_output['error'] = "Missing processed data for validation"
            return validation_output
        
        # Create validation directory
        validation_dir = ensure_dir(f"{DATA_BASE_DIR}/{execution_date}/validation")
        
        # Load benchmark models if available
        try:
            benchmark_models = {
                agent_type: load_benchmark_model(agent_type)
                for agent_type in training_output['models'].keys()
            }
        except Exception as e:
            logger.warning(f"Error loading benchmark models: {str(e)}")
            benchmark_models = {}
        
        # Track how many models pass validation
        passed_count = 0
        total_models = len(training_output['models'])
        
        # Validate each trained model by agent type
        for agent_type, model_info in training_output['models'].items():
            logger.info(f"Validating {agent_type} model")
            
            # Skip if model path is missing
            if 'model_path' not in model_info:
                logger.warning(f"Model path missing for {agent_type}. Skipping validation.")
                validation_output['failed_models'][agent_type] = {
                    'reason': 'Missing model path',
                    'metrics': {}
                }
                continue
            
            model_path = model_info['model_path']
            model_type = model_info.get('model_type', 'ml')  # Default to ML model if not specified
            
            # Get model-specific thresholds or use default
            thresholds = validation_thresholds.get(agent_type, validation_thresholds['default'])
            
            # Load the trained model
            try:
                model = load_model(model_path, model_type)
            except Exception as e:
                logger.error(f"Error loading model for {agent_type}: {str(e)}")
                validation_output['failed_models'][agent_type] = {
                    'reason': f"Error loading model: {str(e)}",
                    'metrics': {}
                }
                continue
            
            # Get validation data for this agent type
            validation_data_path = preprocessing_output.get('validation_data', {}).get(agent_type, None)
            if not validation_data_path:
                logger.warning(f"No validation data found for {agent_type}. Skipping validation.")
                validation_output['failed_models'][agent_type] = {
                    'reason': 'Missing validation data',
                    'metrics': {}
                }
                continue
            
            # Get benchmark model if available
            benchmark_model = benchmark_models.get(agent_type, None)
            
            # Load the validation data
            try:
                validation_data = pd.read_csv(validation_data_path)
                
                # Check if data is sufficient for validation
                if len(validation_data) < 100:  # Arbitrary minimum threshold
                    logger.warning(f"Insufficient validation data for {agent_type} ({len(validation_data)} samples). Skipping validation.")
                    validation_output['failed_models'][agent_type] = {
                        'reason': f"Insufficient validation data ({len(validation_data)} samples)",
                        'metrics': {}
                    }
                    continue
                
            except Exception as e:
                logger.error(f"Error loading validation data for {agent_type}: {str(e)}")
                validation_output['failed_models'][agent_type] = {
                    'reason': f"Error loading validation data: {str(e)}",
                    'metrics': {}
                }
                continue
            
            logger.info(f"Performing walk-forward validation for {agent_type}")
            
            # Configure walk-forward validation
            # For models that need to be tested across different market regimes
            try:
                # Get validation windows based on the data
                # We'll use a sliding window approach
                window_size = min(len(validation_data) // 3, 500)  # Use ~1/3 of data or 500 points max
                stride = window_size // 2  # 50% overlap between windows
                
                # Create validation windows
                windows = []
                for i in range(0, len(validation_data) - window_size + 1, stride):
                    window_data = validation_data.iloc[i:i+window_size].copy()
                    
                    # Skip windows with too little data
                    if len(window_data) < window_size * 0.9:  # Allow for some missing data
                        continue
                    
                    # Determine time range for this window
                    time_col = None
                    for col in ['timestamp', 'signal_time', 'created_at', 'time']:
                        if col in window_data.columns:
                            time_col = col
                            break
                    
                    time_range = {
                        'start': window_data[time_col].min() if time_col else f"Window {len(windows)}",
                        'end': window_data[time_col].max() if time_col else f"Window {len(windows)} end"
                    }
                    
                    windows.append({
                        'window_idx': len(windows),
                        'data': window_data,
                        'time_range': time_range
                    })
                
                # Log validation plan
                logger.info(f"Created {len(windows)} validation windows for {agent_type}")
                
                # Results for each window
                window_metrics = []
                
                # Validate on each window
                for window in windows:
                    logger.info(f"Validating window {window['window_idx']} ({window['time_range']['start']} to {window['time_range']['end']})")
                    
                    try:
                        # Run validation on this window
                        metrics = validate_model_on_window(
                            model=model,
                            validation_data=window['data'],
                            model_type=model_type,
                            benchmark_model=benchmark_model
                        )
                        
                        # Determine if this window passes validation
                        window_passed = evaluate_window_performance(metrics, thresholds)
                        
                        # Store results
                        window_metrics.append({
                            'window_idx': window['window_idx'],
                            'time_range': window['time_range'],
                            'metrics': metrics,
                            'passed': window_passed
                        })
                        
                        # Log key metrics
                        logger.info(f"Window {window['window_idx']} metrics: "
                                   f"Sharpe={metrics.get('sharpe_ratio', 0):.2f}, "
                                   f"Win Rate={metrics.get('win_rate', 0):.2f}, "
                                   f"Drawdown={metrics.get('max_drawdown', 0):.2f}, "
                                   f"Passed={window_passed}")
                    
                    except Exception as e:
                        logger.error(f"Error validating window {window['window_idx']}: {str(e)}")
                        # Add failed window with error
                        window_metrics.append({
                            'window_idx': window['window_idx'],
                            'time_range': window['time_range'],
                            'metrics': {},
                            'passed': False,
                            'error': str(e)
                        })
                
                # Calculate overall metrics
                overall_metrics = calculate_overall_metrics(window_metrics)
                
                # Determine if model passes validation based on:
                # 1. Consistency factor (% of windows that passed)
                # 2. Overall metrics meeting minimum thresholds
                consistency_threshold = thresholds.get('consistency_factor', 0.7)
                consistency_passed = overall_metrics['consistency'] >= consistency_threshold
                
                # Check if overall metrics meet thresholds
                overall_passed = True
                failure_reasons = []
                
                for metric, threshold in thresholds.items():
                    if metric == 'consistency_factor':
                        if not consistency_passed:
                            overall_passed = False
                            failure_reasons.append(f"Consistency below threshold: {overall_metrics['consistency']:.2f} < {consistency_threshold}")
                        continue
                        
                    # Check if we have this metric in overall results
                    metric_base = metric.split('_')[0] if '_min' in metric or '_max' in metric else metric
                    
                    if metric_base in overall_metrics:
                        value = overall_metrics[metric_base]
                        
                        # Check minimum thresholds
                        if metric.endswith('_min') and value < threshold:
                            overall_passed = False
                            failure_reasons.append(f"{metric_base} below minimum: {value:.2f} < {threshold}")
                            
                        # Check maximum thresholds
                        if metric.endswith('_max') and value > threshold:
                            overall_passed = False
                            failure_reasons.append(f"{metric_base} above maximum: {value:.2f} > {threshold}")
                
                # Store validation results for this model
                validation_results = {
                    'passed': overall_passed,
                    'failure_reasons': failure_reasons,
                    'overall': overall_metrics,
                    'windows': window_metrics,
                    'model_info': {
                        'model_path': model_path,
                        'model_type': model_type,
                        'validation_data': validation_data_path
                    }
                }
                
                # Generate validation report
                report_path = generate_validation_report(agent_type, validation_results, validation_dir)
                validation_results['report_path'] = report_path
                
                # Update validation output
                if overall_passed:
                    validation_output['passed_models'][agent_type] = validation_results
                    passed_count += 1
                    logger.info(f"{agent_type} model PASSED validation")
                else:
                    validation_output['failed_models'][agent_type] = validation_results
                    logger.warning(f"{agent_type} model FAILED validation: {', '.join(failure_reasons)}")
                
                # Store validation report path
                validation_output['validation_reports'][agent_type] = report_path
                
            except Exception as e:
                logger.error(f"Error during walk-forward validation for {agent_type}: {str(e)}")
                validation_output['failed_models'][agent_type] = {
                    'reason': f"Validation error: {str(e)}",
                    'metrics': {}
                }
        
        # Update overall status
        if passed_count > 0:
            validation_output['overall_status'] = 'partial' if passed_count < total_models else 'success'
        else:
            validation_output['overall_status'] = 'failed'
        
        # Log validation summary
        logger.info(f"Validation complete: {passed_count}/{total_models} models passed")
        logger.info(f"Passed models: {list(validation_output['passed_models'].keys())}")
        logger.info(f"Failed models: {list(validation_output['failed_models'].keys())}")
        
        return validation_output

    @task(
        retries=3,
        retry_delay=timedelta(minutes=5),
        execution_timeout=timedelta(hours=1),
        pool='model_training_pool',
        pool_slots=2
    )
    def train_models(preprocessing_output: Dict[str, Any], **context) -> Dict[str, Any]:
        """
        Train agent models based on the preprocessed data.
        
        This task trains models for each agent type, using the training data
        prepared in the preprocessing stage. It handles different model types
        and configurations based on agent-specific requirements.
        
        Args:
            preprocessing_output: Output from the preprocess_data task
            
        Returns:
            Dict containing paths to trained models and metadata
        """
        logger.info("Starting model training process")
        
        # Get execution date for timestamping
        execution_date = context['ds']
        
        # Get processed data path from preprocessing output
        if not preprocessing_output or 'processed_data_dir' not in preprocessing_output:
            logger.warning("Missing processed data. Cannot train models.")
            return {
                'error': "Missing processed data for training"
            }
        
        processed_dir = preprocessing_output['processed_dir']
        
        # Initialize result object
        result = {
            'execution_date': execution_date,
            'trained_models': {},
            'stats': {},
            'validation': {}
        }
        
        # Train models for each agent type
        for agent_type, model_info in training_output['models'].items():
            logger.info(f"Training {agent_type} model")
            
            # Skip if model path is missing
            if 'model_path' not in model_info:
                logger.warning(f"Model path missing for {agent_type}. Skipping training.")
                result['trained_models'][agent_type] = {
                    'reason': 'Missing model path',
                    'model_path': None
                }
                continue
            
            model_path = model_info['model_path']
            model_type = model_info.get('model_type', 'ml')  # Default to ML model if not specified
            
            # Train the model
            try:
                model = load_model(model_path, model_type)
                result['trained_models'][agent_type] = {
                    'model_path': model_path,
                    'model_type': model_type
                }
                logger.info(f"{agent_type} model trained successfully")
            except Exception as e:
                logger.error(f"Error training {agent_type} model: {str(e)}")
                result['trained_models'][agent_type] = {
                    'reason': f"Training error: {str(e)}",
                    'model_path': None
                }
                continue
            
            # Calculate model statistics
            model_stats = get_data_statistics(model)
            result['stats'][agent_type] = model_stats
            
            # Log model training completion
            logger.info(f"{agent_type} model training completed successfully")
        
        # Log training summary
        logger.info(f"Training complete: {len(result['trained_models'])} models trained")
        logger.info(f"Trained models: {list(result['trained_models'].keys())}")
        
        return result

    # Model Deployment and Notification Tasks
    from src.utils.notification_manager import NotificationManager, NotificationLevel, NotificationChannel
    from src.deployment.model_registry import get_model_registry
    from src.deployment.model_server import ModelServer
    from airflow.utils.task_group import TaskGroup
    import traceback

    @task(
        retries=3,
        retry_delay=timedelta(minutes=2),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=10),
        execution_timeout=timedelta(minutes=30),
        pool='model_deployment_pool',
        pool_slots=2
    )
    def decide_deployment(validation_output: Dict[str, Any], **context) -> str:
        """
        Decide whether to deploy the model based on validation results.
        
        This is a branching task that determines the next step in the workflow.
        
        Args:
            validation_output: Output from the validation task
            
        Returns:
            Next task ID to execute
        """
        logger.info("Evaluating validation results for deployment decision")
        
        try:
            # Get validation decision
            passed_validation = validation_output.get('passed_validation', False)
            agent_types = validation_output.get('agent_types', [])
            validation_metrics = validation_output.get('metrics', {})
            
            # Add detailed logging
            logger.info(f"Validation passed: {passed_validation}")
            for agent_type, metrics in validation_metrics.items():
                logger.info(f"Agent {agent_type} metrics: {metrics}")
            
            # Get deployment thresholds from variables
            deployment_thresholds = Variable.get(
                "model_deployment_thresholds",
                deserialize_json=True,
                default={}
            )
            
            # Detailed threshold checking for each model type
            deployment_decisions = {}
            for agent_type in agent_types:
                agent_metrics = validation_metrics.get(agent_type, {})
                agent_thresholds = deployment_thresholds.get(agent_type, {})
                
                # Default to the global validation decision if no specific thresholds
                if not agent_thresholds:
                    deployment_decisions[agent_type] = passed_validation
                    continue
                
                # Check each metric against its threshold
                passed_thresholds = True
                for metric, threshold in agent_thresholds.items():
                    if metric not in agent_metrics:
                        logger.warning(f"Metric {metric} not found for agent {agent_type}")
                        continue
                        
                    if agent_metrics[metric] < threshold:
                        logger.info(f"Agent {agent_type} failed threshold for {metric}: "
                                    f"{agent_metrics[metric]} < {threshold}")
                        passed_thresholds = False
                        break
                
                deployment_decisions[agent_type] = passed_thresholds
            
            # Store decisions in XCom for downstream tasks
            context['ti'].xcom_push(key='deployment_decisions', value=deployment_decisions)
            
            # If any models passed validation, proceed with deployment
            if any(deployment_decisions.values()):
                logger.info("At least one model passed validation. Proceeding with deployment.")
                return 'deploy_models'
            else:
                logger.info("No models passed validation. Skipping deployment.")
                return 'send_validation_failure_notification'
                
        except Exception as e:
            logger.error(f"Error in deployment decision: {str(e)}")
            # In case of error, don't deploy
            return 'send_validation_failure_notification'

    def _verify_model_deployment(
        model_id: str,
        version: str,
        environment: str
    ) -> bool:
        """
        Verify that a model was deployed correctly in the specified environment.
        
        Args:
            model_id: Model identifier
            version: Model version
            environment: Target environment
            
        Returns:
            True if verification passed, False otherwise
        """
        try:
            # In a real implementation, this would do more thorough verification:
            # 1. Load the model and run test inference
            # 2. Check for corrupted files
            # 3. Verify model signature
            # 4. Check model size and other basic properties
            registry = get_model_registry()
            model_info = registry.get_model(model_id, version, environment)
            
            if not model_info:
                logger.error(f"Model {model_id} version {version} not found in {environment}")
                return False
            
            # Check that the model file exists
            if not os.path.exists(model_info["path"]):
                logger.error(f"Model file not found: {model_info['path']}")
                return False
            
            # Additional verification steps would go here
            
            return True
        except Exception as e:
            logger.error(f"Error verifying model deployment: {str(e)}")
            return False

    @task(
        retries=3,
        retry_delay=timedelta(minutes=5),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=30),
        execution_timeout=timedelta(hours=1),
        pool='model_deployment_pool',
        pool_slots=2
    )
    def deploy_models(
        training_output: Dict[str, Any],
        validation_output: Dict[str, Any],
        **context
    ) -> Dict[str, Any]:
        """
        Deploy models that passed validation to production.
        
        Args:
            training_output: Output from the training task
            validation_output: Output from the validation task
            
        Returns:
            Deployment results
        """
        logger.info("Starting model deployment")
        
        # Get deployment decisions from upstream task
        ti = context['ti']
        deployment_decisions = ti.xcom_pull(
            task_ids='decide_deployment',
            key='deployment_decisions'
        )
        
        if not deployment_decisions:
            raise ValueError("Deployment decisions not found")
        
        # Get model paths and metadata
        model_paths = training_output.get('model_paths', {})
        model_metadata = training_output.get('model_metadata', {})
        
        # Get validation metrics
        validation_metrics = validation_output.get('metrics', {})
        
        # Initialize model registry and server
        registry = get_model_registry()
        
        # Get model server config
        model_server_config = Variable.get(
            "model_server_config",
            deserialize_json=True,
            default={
                "host": "localhost",
                "port": 8000,
                "model_dir": "/opt/airflow/models"
            }
        )
        
        # Connect to model server (in real implementation, this would use a client)
        model_server = ModelServer(model_server_config["model_dir"])
        
        # Track deployment results
        deployment_results = {
            "success": [],
            "failed": [],
            "skipped": [],
            "timestamp": datetime.now().isoformat(),
            "models": {}
        }
        
        # Deploy each model that passed validation
        for agent_type, deploy_decision in deployment_decisions.items():
            if not deploy_decision:
                logger.info(f"Skipping deployment for {agent_type} (failed validation)")
                deployment_results["skipped"].append(agent_type)
                continue
            
            if agent_type not in model_paths:
                logger.warning(f"No model path found for {agent_type}")
                deployment_results["skipped"].append(agent_type)
                continue
            
            try:
                model_path = model_paths[agent_type]
                metrics = validation_metrics.get(agent_type, {})
                metadata = model_metadata.get(agent_type, {})
                
                # Update metadata with runtime information
                metadata.update({
                    "deployed_by": "airflow",
                    "dag_id": context['dag'].dag_id,
                    "execution_date": context['execution_date'].isoformat(),
                    "deployment_timestamp": datetime.now().isoformat()
                })
                
                # Register model in registry
                registry_result = registry.register_model(
                    model_id=agent_type,
                    model_path=model_path,
                    metadata=metadata,
                    metrics=metrics,
                    environment="staging"  # First register to staging
                )
                
                # Verify model in staging first
                if _verify_model_deployment(agent_type, registry_result["version"], "staging"):
                    # If verification passed, promote to production
                    promotion_result = registry.promote_model(
                        model_id=agent_type,
                        version=registry_result["version"],
                        target_environment="production"
                    )
                    
                    # Load model into ModelServer
                    model_id = f"{agent_type}_{registry_result['version']}"
                    load_success = model_server.load_model(model_id, promotion_result["path"])
                    
                    if load_success:
                        # Set as active model
                        model_server.set_active_model(model_id)
                        
                        logger.info(f"Successfully deployed {agent_type} version {registry_result['version']} to production")
                        deployment_results["success"].append(agent_type)
                        deployment_results["models"][agent_type] = {
                            "version": registry_result["version"],
                            "path": promotion_result["path"],
                            "metrics": metrics
                        }
                    else:
                        logger.error(f"Failed to load model {agent_type} into ModelServer")
                        deployment_results["failed"].append(agent_type)
                else:
                    logger.error(f"Model verification failed for {agent_type} in staging")
                    deployment_results["failed"].append(agent_type)
                    
            except Exception as e:
                logger.error(f"Error deploying model {agent_type}: {str(e)}")
                logger.error(traceback.format_exc())
                deployment_results["failed"].append(agent_type)
        
        # Log summary
        logger.info(f"Deployment summary: {len(deployment_results['success'])} succeeded, "
                    f"{len(deployment_results['failed'])} failed, "
                    f"{len(deployment_results['skipped'])} skipped")
        
        return deployment_results

    @task(
        retries=3,
        retry_delay=timedelta(minutes=2),
        execution_timeout=timedelta(minutes=10),
        pool='notification_pool',
        pool_slots=1
    )
    def send_success_notification(
        validation_output: Dict[str, Any],
        deployment_output: Dict[str, Any],
        **context
    ) -> Dict[str, Any]:
        """
        Send success notification for models that were deployed successfully.
        
        Args:
            validation_output: Output from validation task
            deployment_output: Output from deployment task
            
        Returns:
            Notification results
        """
        logger.info("Sending success notifications")
        
        # Get notification manager
        notification_manager = NotificationManager()
        
        # Get deployment results
        successful_models = deployment_output.get("success", [])
        failed_models = deployment_output.get("failed", [])
        skipped_models = deployment_output.get("skipped", [])
        model_details = deployment_output.get("models", {})
        
        # Format message
        execution_date = context['execution_date'].strftime('%Y-%m-%d')
        message = f"Model Training and Deployment Summary ({execution_date})\n\n"
        
        if successful_models:
            message += "✅ Successfully Deployed Models:\n"
            for model_id in successful_models:
                model_info = model_details.get(model_id, {})
                model_version = model_info.get("version", "unknown")
                model_metrics = model_info.get("metrics", {})
                
                message += f"  - {model_id} (v{model_version}):\n"
                for metric, value in model_metrics.items():
                    message += f"      {metric}: {value:.4f}\n"
            message += "\n"
        
        if failed_models:
            message += "❌ Failed Deployments:\n"
            message += "  - " + "\n  - ".join(failed_models) + "\n\n"
        
        if skipped_models:
            message += "⏭️ Skipped Models (Failed Validation):\n"
            message += "  - " + "\n  - ".join(skipped_models) + "\n\n"
        
        # Add links to dashboards or logs
        airflow_url = Variable.get("airflow_base_url", default="http://localhost:8080")
        dag_id = context['dag'].dag_id
        run_id = context['run_id']
        message += f"View run details: {airflow_url}/graph?dag_id={dag_id}&run_id={run_id}\n"
        
        # Send notifications
        channels = [
            NotificationChannel.EMAIL, 
            NotificationChannel.LOG
        ]
        
        # Check if Slack notifications are enabled
        slack_enabled = Variable.get("enable_slack_notifications", default="false").lower() == "true"
        if slack_enabled:
            channels.append(NotificationChannel.TELEGRAM)  # Using Telegram as a proxy for Slack
        
        # Send the notification
        notification_id = notification_manager.send_notification(
            title="Model Deployment Summary",
            message=message,
            level=NotificationLevel.INFO,
            source="agent_retraining_dag",
            channels=channels,
            metadata={
                "dag_id": context['dag'].dag_id,
                "task_id": context['task'].task_id,
                "execution_date": context['execution_date'].isoformat(),
                "deployment_results": deployment_output
            }
        )
        
        return {
            "notification_sent": True,
            "notification_id": notification_id,
            "message": message
        }

    @task(
        retries=3,
        retry_delay=timedelta(minutes=2),
        execution_timeout=timedelta(minutes=10),
        pool='notification_pool',
        pool_slots=1,
        trigger_rule="all_done"  # Run even if upstream tasks fail
    )
    def send_validation_failure_notification(
        validation_output: Dict[str, Any],
        **context
    ) -> Dict[str, Any]:
        """
        Send notification for failed model validation.
        
        Args:
            validation_output: Output from validation task
            
        Returns:
            Notification results
        """
        logger.info("Sending validation failure notification")
        
        # Get notification manager
        notification_manager = NotificationManager()
        
        # Get validation results
        agent_types = validation_output.get("agent_types", [])
        all_metrics = validation_output.get("metrics", {})
        thresholds = validation_output.get("thresholds", {})
        
        # Format message
        execution_date = context['execution_date'].strftime('%Y-%m-%d')
        message = f"⚠️ Model Validation Failed ({execution_date})\n\n"
        message += "The following models failed validation and were not deployed:\n\n"
        
        for agent_type in agent_types:
            metrics = all_metrics.get(agent_type, {})
            agent_thresholds = thresholds.get(agent_type, {})
            
            message += f"Model: {agent_type}\n"
            message += "Metrics:\n"
            
            for metric, value in metrics.items():
                threshold = agent_thresholds.get(metric, "N/A")
                status = "✅" if threshold == "N/A" or value >= threshold else "❌"
                message += f"  - {metric}: {value:.4f} (threshold: {threshold}) {status}\n"
            
            message += "\n"
        
        message += "Please review the model training and validation logs for more details.\n"
        
        # Add links to dashboards or logs
        airflow_url = Variable.get("airflow_base_url", default="http://localhost:8080")
        dag_id = context['dag'].dag_id
        run_id = context['run_id']
        message += f"View run details: {airflow_url}/graph?dag_id={dag_id}&run_id={run_id}\n"
        
        # Send notifications with WARNING level
        channels = [
            NotificationChannel.EMAIL, 
            NotificationChannel.LOG
        ]
        
        # Check if Slack notifications are enabled
        slack_enabled = Variable.get("enable_slack_notifications", default="false").lower() == "true"
        if slack_enabled:
            channels.append(NotificationChannel.TELEGRAM)  # Using Telegram as a proxy for Slack
        
        # Send the notification
        notification_id = notification_manager.send_notification(
            title="Model Validation Failed",
            message=message,
            level=NotificationLevel.WARNING,
            source="agent_retraining_dag",
            channels=channels,
            metadata={
                "dag_id": context['dag'].dag_id,
                "task_id": context['task'].task_id,
                "execution_date": context['execution_date'].isoformat(),
                "validation_output": validation_output
            }
        )
        
        return {
            "notification_sent": True,
            "notification_id": notification_id,
            "message": message
        }

    # Define a task group for model deployment and notification
    def define_deployment_task_group(
        training_output,
        validation_output
    ):
        """Define deployment and notification task group."""
        with TaskGroup(group_id="model_deployment_and_notification") as deployment_group:
            # Decide whether to deploy
            deployment_decision = decide_deployment(validation_output)
            
            # Create deployment branch
            deployment_result = deploy_models(
                training_output,
                validation_output
            )
            
            # Notification tasks
            success_notification = send_success_notification(
                validation_output,
                deployment_result
            )
            
            failure_notification = send_validation_failure_notification(
                validation_output
            )
            
            # Define dependencies
            deployment_decision >> [deployment_result, failure_notification]
            deployment_result >> success_notification
        
        return deployment_group

    # Add deployment task group to the DAG
    deployment_tasks = define_deployment_task_group(
        training_output=training_output,
        validation_output=validation_output
    )

    # Connect to existing DAG
    validation_output >> deployment_tasks

# Add a comment for testing
if __name__ == "__main__":
    dag.test() 