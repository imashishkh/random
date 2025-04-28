"""
Data Processor for Strategy Evaluation
--------------------------------------
Handles data preprocessing and time period splitting for strategy evaluation.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any, Optional, Union


class DataProcessor:
    """
    Processes market data for strategy evaluation.
    
    This class handles data preprocessing, normalization, and time period splitting
    for consistent evaluation of strategies.
    """
    
    def __init__(self, 
                 train_size: float = 0.6, 
                 val_size: float = 0.2,
                 test_size: float = 0.2,
                 random_state: Optional[int] = None,
                 preprocessing_steps: Optional[Dict[str, Any]] = None):
        """
        Initialize the data processor.
        
        Args:
            train_size: Proportion of data to use for training (default: 0.6)
            val_size: Proportion of data to use for validation (default: 0.2)
            test_size: Proportion of data to use for testing (default: 0.2)
            random_state: Random state for reproducibility
            preprocessing_steps: Dictionary of preprocessing steps to apply
        """
        # Validate split proportions
        if abs(train_size + val_size + test_size - 1.0) > 1e-10:
            raise ValueError("Train, validation, and test sizes must sum to 1.0")
        
        self.train_size = train_size
        self.val_size = val_size
        self.test_size = test_size
        self.random_state = random_state
        self.preprocessing_steps = preprocessing_steps or {}
        
        # Store statistics for feature normalization
        self.feature_stats = {}
    
    def process(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Apply preprocessing steps to the data.
        
        Args:
            data: Raw market data DataFrame
            
        Returns:
            Processed DataFrame
        """
        processed_data = data.copy()
        
        # Handle missing values
        if 'fill_method' in self.preprocessing_steps:
            method = self.preprocessing_steps['fill_method']
            processed_data = processed_data.fillna(method=method)
        
        # Normalize features if specified
        if self.preprocessing_steps.get('normalize', False):
            numeric_cols = processed_data.select_dtypes(include=np.number).columns
            
            # Store mean and std for each feature during training
            if not self.feature_stats:
                self.feature_stats = {
                    col: {'mean': processed_data[col].mean(), 'std': processed_data[col].std()}
                    for col in numeric_cols
                }
            
            # Apply normalization
            for col in numeric_cols:
                mean = self.feature_stats[col]['mean']
                std = self.feature_stats[col]['std']
                # Avoid division by zero
                if std > 0:
                    processed_data[col] = (processed_data[col] - mean) / std
        
        # Add technical indicators if specified
        if 'technical_indicators' in self.preprocessing_steps:
            processed_data = self._add_technical_indicators(
                processed_data, 
                self.preprocessing_steps['technical_indicators']
            )
        
        return processed_data
    
    def split_time_periods(self, data: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Split data into training, validation, and test sets chronologically.
        
        Args:
            data: Processed market data DataFrame
            
        Returns:
            Tuple of (training, validation, test) DataFrames
        """
        n = len(data)
        train_end = int(n * self.train_size)
        val_end = train_end + int(n * self.val_size)
        
        train_data = data.iloc[:train_end].copy()
        val_data = data.iloc[train_end:val_end].copy()
        test_data = data.iloc[val_end:].copy()
        
        return train_data, val_data, test_data
    
    def split_cross_validation(self, 
                               data: pd.DataFrame, 
                               n_splits: int = 5) -> list:
        """
        Create cross-validation folds for time series data.
        
        Args:
            data: Processed market data DataFrame
            n_splits: Number of folds to create
            
        Returns:
            List of (train, test) index tuples for each fold
        """
        n = len(data)
        fold_size = n // n_splits
        
        folds = []
        for i in range(n_splits):
            test_start = i * fold_size
            test_end = test_start + fold_size if i < n_splits - 1 else n
            
            train_indices = list(range(0, test_start)) + list(range(test_end, n))
            test_indices = list(range(test_start, test_end))
            
            folds.append((train_indices, test_indices))
        
        return folds
    
    def _add_technical_indicators(self, 
                                 data: pd.DataFrame, 
                                 indicators: list) -> pd.DataFrame:
        """
        Add technical indicators to the dataframe.
        
        Args:
            data: Market data DataFrame
            indicators: List of indicator names to add
            
        Returns:
            DataFrame with added technical indicators
        """
        df = data.copy()
        
        # Define required columns for indicators
        required_columns = {
            'sma': ['close'],
            'ema': ['close'],
            'rsi': ['close'],
            'macd': ['close'],
            'bollinger': ['close'],
            'atr': ['high', 'low', 'close']
        }
        
        # Check if we have the necessary columns
        price_cols = set(['open', 'high', 'low', 'close'])
        available_cols = set(df.columns)
        
        # Case conversion for column names (some data sources use uppercase)
        col_mapping = {}
        for col in available_cols:
            col_lower = col.lower()
            if col_lower in price_cols:
                col_mapping[col_lower] = col
        
        for indicator in indicators:
            required = required_columns.get(indicator, [])
            missing = [col for col in required if col not in col_mapping]
            
            if missing:
                print(f"Warning: Cannot add {indicator}, missing columns: {missing}")
                continue
            
            # Map the required columns to actual dataframe columns
            mapped_cols = {col: col_mapping[col] for col in required}
            
            # Add the indicator based on its type
            if indicator == 'sma':
                periods = [5, 10, 20, 50, 200]
                for period in periods:
                    df[f'sma_{period}'] = df[mapped_cols['close']].rolling(window=period).mean()
            
            elif indicator == 'ema':
                periods = [5, 10, 20, 50, 200]
                for period in periods:
                    df[f'ema_{period}'] = df[mapped_cols['close']].ewm(span=period, adjust=False).mean()
            
            elif indicator == 'rsi':
                period = 14
                close = df[mapped_cols['close']]
                delta = close.diff()
                gain = delta.where(delta > 0, 0)
                loss = -delta.where(delta < 0, 0)
                
                avg_gain = gain.rolling(window=period).mean()
                avg_loss = loss.rolling(window=period).mean()
                
                rs = avg_gain / avg_loss
                df['rsi'] = 100 - (100 / (1 + rs))
            
            elif indicator == 'bollinger':
                period = 20
                close = df[mapped_cols['close']]
                df['bollinger_mid'] = close.rolling(window=period).mean()
                df['bollinger_std'] = close.rolling(window=period).std()
                df['bollinger_upper'] = df['bollinger_mid'] + (df['bollinger_std'] * 2)
                df['bollinger_lower'] = df['bollinger_mid'] - (df['bollinger_std'] * 2)
            
            elif indicator == 'macd':
                ema12 = df[mapped_cols['close']].ewm(span=12, adjust=False).mean()
                ema26 = df[mapped_cols['close']].ewm(span=26, adjust=False).mean()
                df['macd'] = ema12 - ema26
                df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
                df['macd_hist'] = df['macd'] - df['macd_signal']
            
            elif indicator == 'atr':
                period = 14
                high = df[mapped_cols['high']]
                low = df[mapped_cols['low']]
                close = df[mapped_cols['close']]
                
                tr1 = high - low
                tr2 = (high - close.shift()).abs()
                tr3 = (low - close.shift()).abs()
                
                tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                df['atr'] = tr.rolling(window=period).mean()
        
        # Drop rows with NaN values resulting from indicators
        if self.preprocessing_steps.get('drop_na', True):
            df = df.dropna()
        
        return df 