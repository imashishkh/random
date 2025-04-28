import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Union, Optional
from sklearn.preprocessing import StandardScaler, MinMaxScaler


class FeatureExtractor:
    """
    Feature extractor for processing financial time series data for RL agents.
    This class extracts and normalizes features from market data.
    """
    
    def __init__(
        self,
        feature_list: List[str] = None,
        window_size: int = 30,
        normalization: str = "standard",
        include_indicators: bool = True,
        include_volumes: bool = True,
    ):
        """
        Initialize the feature extractor.
        
        Args:
            feature_list: List of features to extract. If None, all available features will be used.
            window_size: Size of the window for rolling features and indicators.
            normalization: Type of normalization to apply ('standard', 'minmax', or None).
            include_indicators: Whether to include technical indicators.
            include_volumes: Whether to include volume-related features.
        """
        self.feature_list = feature_list
        self.window_size = window_size
        self.normalization = normalization
        self.include_indicators = include_indicators
        self.include_volumes = include_volumes
        
        # Initialize scalers for different feature groups
        self.price_scaler = None
        self.volume_scaler = None
        self.indicator_scaler = None
        
        # Feature group tracking
        self.price_columns = []
        self.volume_columns = []
        self.indicator_columns = []
        self.all_features = []
    
    def fit(self, data: pd.DataFrame) -> None:
        """
        Fit the feature extractor to the data.
        
        Args:
            data: DataFrame containing the raw price and volume data.
        """
        processed_data = self._preprocess_data(data)
        
        # Group features and fit scalers
        self._group_features(processed_data)
        
        if self.normalization == "standard":
            self.price_scaler = StandardScaler().fit(processed_data[self.price_columns])
            if self.include_volumes and self.volume_columns:
                self.volume_scaler = StandardScaler().fit(processed_data[self.volume_columns])
            if self.include_indicators and self.indicator_columns:
                self.indicator_scaler = StandardScaler().fit(processed_data[self.indicator_columns])
        
        elif self.normalization == "minmax":
            self.price_scaler = MinMaxScaler().fit(processed_data[self.price_columns])
            if self.include_volumes and self.volume_columns:
                self.volume_scaler = MinMaxScaler().fit(processed_data[self.volume_columns])
            if self.include_indicators and self.indicator_columns:
                self.indicator_scaler = MinMaxScaler().fit(processed_data[self.indicator_columns])
    
    def transform(self, data: pd.DataFrame) -> np.ndarray:
        """
        Transform the data using the fitted feature extractor.
        
        Args:
            data: DataFrame containing the raw price and volume data.
            
        Returns:
            Numpy array of processed features.
        """
        processed_data = self._preprocess_data(data)
        
        # Apply scaling if configured
        if self.normalization in ["standard", "minmax"]:
            price_data = self.price_scaler.transform(processed_data[self.price_columns])
            
            if self.include_volumes and self.volume_columns:
                volume_data = self.volume_scaler.transform(processed_data[self.volume_columns])
            else:
                volume_data = np.array([])
            
            if self.include_indicators and self.indicator_columns:
                indicator_data = self.indicator_scaler.transform(processed_data[self.indicator_columns])
            else:
                indicator_data = np.array([])
            
            # Combine all features
            if volume_data.size > 0 and indicator_data.size > 0:
                features = np.hstack((price_data, volume_data, indicator_data))
            elif volume_data.size > 0:
                features = np.hstack((price_data, volume_data))
            elif indicator_data.size > 0:
                features = np.hstack((price_data, indicator_data))
            else:
                features = price_data
        else:
            # Use features without scaling
            features = processed_data[self.all_features].values
        
        return features
    
    def fit_transform(self, data: pd.DataFrame) -> np.ndarray:
        """
        Fit to data, then transform it.
        
        Args:
            data: DataFrame containing the raw price and volume data.
            
        Returns:
            Numpy array of processed features.
        """
        self.fit(data)
        return self.transform(data)
    
    def _preprocess_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Preprocess the data by computing technical indicators and other features.
        
        Args:
            data: DataFrame containing the raw price and volume data.
            
        Returns:
            DataFrame with added features.
        """
        df = data.copy()
        
        # Ensure required columns exist
        required_columns = ['open', 'high', 'low', 'close']
        if self.include_volumes:
            required_columns.append('volume')
        
        # Check if columns exist and create dummy columns if not
        for col in required_columns:
            if col not in df.columns:
                if col == 'volume' and 'close' in df.columns:
                    df[col] = df['close'] * 0.1  # Dummy volume
                elif 'close' in df.columns:
                    df[col] = df['close']  # Use close price for missing OHLC
                else:
                    raise ValueError(f"Required column {col} not found in data")
        
        # Calculate price-based features
        # Returns and log returns
        df['return'] = df['close'].pct_change()
        df['log_return'] = np.log(df['close']).diff()
        
        # Price ratios
        df['high_low_ratio'] = df['high'] / df['low']
        df['close_open_ratio'] = df['close'] / df['open']
        
        # Rolling statistics for prices
        df['rolling_mean'] = df['close'].rolling(self.window_size).mean()
        df['rolling_std'] = df['close'].rolling(self.window_size).std()
        
        # Only add indicators if requested
        if self.include_indicators:
            # Moving averages
            df['sma_5'] = df['close'].rolling(5).mean()
            df['sma_10'] = df['close'].rolling(10).mean()
            df['sma_20'] = df['close'].rolling(20).mean()
            df['ema_5'] = df['close'].ewm(span=5).mean()
            df['ema_10'] = df['close'].ewm(span=10).mean()
            df['ema_20'] = df['close'].ewm(span=20).mean()
            
            # MACD
            df['ema_12'] = df['close'].ewm(span=12).mean()
            df['ema_26'] = df['close'].ewm(span=26).mean()
            df['macd'] = df['ema_12'] - df['ema_26']
            df['macd_signal'] = df['macd'].ewm(span=9).mean()
            df['macd_hist'] = df['macd'] - df['macd_signal']
            
            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # Bollinger Bands
            df['bb_middle'] = df['close'].rolling(20).mean()
            df['bb_std'] = df['close'].rolling(20).std()
            df['bb_upper'] = df['bb_middle'] + 2 * df['bb_std']
            df['bb_lower'] = df['bb_middle'] - 2 * df['bb_std']
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
            
            # Calculate ATR
            df['tr1'] = abs(df['high'] - df['low'])
            df['tr2'] = abs(df['high'] - df['close'].shift())
            df['tr3'] = abs(df['low'] - df['close'].shift())
            df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            df['atr'] = df['tr'].rolling(14).mean()
            
            # Momentum
            df['momentum'] = df['close'] - df['close'].shift(10)
            
            # Stochastic oscillator
            high_max = df['high'].rolling(14).max()
            low_min = df['low'].rolling(14).min()
            df['stoch_k'] = 100 * ((df['close'] - low_min) / (high_max - low_min))
            df['stoch_d'] = df['stoch_k'].rolling(3).mean()
        
        # Only add volume features if requested
        if self.include_volumes:
            # Volume-based features
            df['volume_change'] = df['volume'].pct_change()
            df['volume_ma_5'] = df['volume'].rolling(5).mean()
            df['volume_ma_10'] = df['volume'].rolling(10).mean()
            df['volume_ma_ratio'] = df['volume'] / df['volume_ma_5']
            
            # On-balance volume
            obv = (df['close'].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df['volume']).cumsum()
            df['obv'] = obv
            df['obv_ma'] = df['obv'].rolling(10).mean()
        
        # Drop NaN values
        df = df.dropna()
        
        return df
    
    def _group_features(self, data: pd.DataFrame) -> None:
        """
        Group and filter features according to feature_list specification.
        
        Args:
            data: DataFrame with processed features.
        """
        # Group price features
        self.price_columns = ['open', 'high', 'low', 'close', 'return', 'log_return', 
                              'high_low_ratio', 'close_open_ratio', 'rolling_mean', 'rolling_std']
        
        # Group volume features if included
        if self.include_volumes and 'volume' in data.columns:
            self.volume_columns = ['volume', 'volume_change', 'volume_ma_5', 'volume_ma_10', 'volume_ma_ratio', 'obv', 'obv_ma']
            # Filter to only columns present in the DataFrame
            self.volume_columns = [col for col in self.volume_columns if col in data.columns]
        else:
            self.volume_columns = []
        
        # Group indicator features if included
        if self.include_indicators:
            self.indicator_columns = ['sma_5', 'sma_10', 'sma_20', 'ema_5', 'ema_10', 'ema_20',
                                     'macd', 'macd_signal', 'macd_hist', 'rsi',
                                     'bb_middle', 'bb_upper', 'bb_lower', 'bb_width',
                                     'atr', 'momentum', 'stoch_k', 'stoch_d']
            # Filter to only columns present in the DataFrame
            self.indicator_columns = [col for col in self.indicator_columns if col in data.columns]
        else:
            self.indicator_columns = []
        
        # Combine all features
        self.all_features = self.price_columns + self.volume_columns + self.indicator_columns
        
        # Filter according to feature_list if specified
        if self.feature_list is not None:
            self.all_features = [col for col in self.all_features if col in self.feature_list]
            self.price_columns = [col for col in self.price_columns if col in self.feature_list]
            self.volume_columns = [col for col in self.volume_columns if col in self.feature_list]
            self.indicator_columns = [col for col in self.indicator_columns if col in self.feature_list]
        
        # Ensure features exist in the data
        self.all_features = [col for col in self.all_features if col in data.columns]
        self.price_columns = [col for col in self.price_columns if col in data.columns]
        self.volume_columns = [col for col in self.volume_columns if col in data.columns]
        self.indicator_columns = [col for col in self.indicator_columns if col in data.columns]


class StateProcessor:
    """
    Processes environment state to create a representation suitable for RL models.
    """
    
    def __init__(
        self,
        feature_extractor: FeatureExtractor,
        lookback_window: int = 30,
        stack_frames: bool = True,
        include_position: bool = True,
        include_balance: bool = True,
        normalize_portfolio: bool = True,
    ):
        """
        Initialize the state processor.
        
        Args:
            feature_extractor: Feature extractor instance.
            lookback_window: Number of past time steps to include in state.
            stack_frames: Whether to stack the time frames in a single array.
            include_position: Whether to include current position in state.
            include_balance: Whether to include account balance in state.
            normalize_portfolio: Whether to normalize portfolio values.
        """
        self.feature_extractor = feature_extractor
        self.lookback_window = lookback_window
        self.stack_frames = stack_frames
        self.include_position = include_position
        self.include_balance = include_balance
        self.normalize_portfolio = normalize_portfolio
        
        # Portfolio stats scaler
        self.portfolio_scaler = MinMaxScaler(feature_range=(-1, 1))
        self.portfolio_scaler.fit(np.array([[0], [1000000]]))  # Fit with reasonable range
    
    def transform(
        self, 
        observation: Dict[str, Union[pd.DataFrame, float, int]], 
        position: float = 0.0, 
        balance: float = 0.0
    ) -> np.ndarray:
        """
        Transform observation dictionary into a state representation for the RL model.
        
        Args:
            observation: Dictionary containing 'prices' DataFrame and other info.
            position: Current trading position.
            balance: Current account balance.
            
        Returns:
            Numpy array representing the state.
        """
        # Extract market data features
        price_data = observation['prices']
        features = self.feature_extractor.transform(price_data.iloc[-self.lookback_window:])
        
        # Prepare time-series features
        if self.stack_frames:
            # Structure as [time, features]
            state = features[-self.lookback_window:]
        else:
            # Flatten to a single vector
            state = features[-self.lookback_window:].flatten()
        
        # Add position and balance information if requested
        additional_info = []
        
        if self.include_position:
            # Normalize position to [-1, 1]
            position = np.clip(position, -1.0, 1.0)
            additional_info.append(position)
        
        if self.include_balance and self.normalize_portfolio:
            # Normalize balance using the scaler
            normalized_balance = self.portfolio_scaler.transform(np.array([[balance]]))[0, 0]
            additional_info.append(normalized_balance)
        elif self.include_balance:
            # Use raw balance
            additional_info.append(balance)
        
        # Combine market features with additional information
        if additional_info and not self.stack_frames:
            state = np.append(state, additional_info)
        elif additional_info:
            # Add as separate features for each time step
            additional_info = np.array(additional_info)
            if len(state.shape) == 2:
                # For 2D state with shape (time, features)
                state = np.column_stack((state, np.tile(additional_info, (state.shape[0], 1))))
            else:
                # Add as new axis for 1D state
                state = np.concatenate((state, additional_info.reshape(1, -1)))
        
        return state 