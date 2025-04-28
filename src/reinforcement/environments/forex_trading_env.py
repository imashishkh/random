"""
Forex Trading Environment for Reinforcement Learning

This module implements a Gymnasium-compatible environment for forex
trading, designed for training reinforcement learning agents. It simulates
a forex market with configurable parameters for realistic trading.
"""

import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Optional, Any, Union
import logging

from ...indicators.factory import IndicatorFactory
from ...indicators.calculator import IndicatorCalculator

# Set up logging
logger = logging.getLogger(__name__)

class ForexTradingEnv(gym.Env):
    """
    Custom Gymnasium environment for forex trading.
    
    This environment simulates trading in forex markets with realistic
    features like bid-ask spreads, slippage, and transaction costs. It supports
    a comprehensive state representation and continuous action space.
    
    Attributes:
        df (pd.DataFrame): Historical price data with OHLCV and bid-ask columns
        initial_balance (float): Starting balance for each episode
        spread (float): Fixed spread in pips if bid-ask not provided in data
        leverage (float): Trading leverage (e.g., 50:1, 100:1)
        commission (float): Transaction fee as a percentage
        window_size (int): Number of time steps to include in the state
        reward_type (str): Type of reward function ('profit', 'sharpe', 'sortino')
        trading_volume (float): Maximum percentage of balance to trade per action
        slippage (float): Maximum slippage as a percentage of price
        technical_indicators (List[str]): Technical indicators to include in state
        multi_timeframe (bool): Whether to include multi-timeframe analysis
        include_sentiment (bool): Whether to include sentiment features
    """
    
    metadata = {'render_modes': ['human', 'rgb_array'], 'render_fps': 4}
    
    def __init__(
        self,
        df: pd.DataFrame,
        initial_balance: float = 10000.0,
        spread: float = 0.0001,  # 1 pip for major pairs
        leverage: float = 50.0,
        commission: float = 0.0001,
        window_size: int = 20,
        reward_type: str = 'sharpe',
        trading_volume: float = 0.1,
        slippage: float = 0.0001,
        technical_indicators: List[str] = None,
        multi_timeframe: bool = False,
        include_sentiment: bool = False,
        render_mode: Optional[str] = None
    ):
        """
        Initialize the forex trading environment.
        
        Args:
            df: DataFrame with OHLCV data (columns: open, high, low, close, volume)
                and optionally bid, ask columns
            initial_balance: Starting account balance
            spread: Fixed spread in pips (used if bid-ask not in data)
            leverage: Trading leverage (50.0 = 50:1 leverage)
            commission: Trading fee as a percentage (e.g., 0.0001 = 0.01%)
            window_size: Number of time steps to include in the state
            reward_type: Type of reward function ('profit', 'sharpe', 'sortino')
            trading_volume: Maximum percentage of balance to trade per action
            slippage: Maximum slippage as a percentage of price
            technical_indicators: List of indicators to include in state
            multi_timeframe: Whether to include multi-timeframe analysis
            include_sentiment: Whether to include sentiment features
            render_mode: Mode for visualization ('human', 'rgb_array')
        """
        super().__init__()
        
        # Validate input data
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_columns):
            raise ValueError(f"DataFrame must contain columns: {required_columns}")
        
        # Store parameters
        self.df = df
        self.initial_balance = initial_balance
        self.spread = spread
        self.leverage = leverage
        self.commission = commission
        self.window_size = window_size
        self.reward_type = reward_type
        self.trading_volume = trading_volume
        self.slippage = slippage
        self.render_mode = render_mode
        self.multi_timeframe = multi_timeframe
        self.include_sentiment = include_sentiment
        
        # Set default technical indicators if none provided
        if technical_indicators is None:
            self.technical_indicators = [
                'sma_20', 'sma_50', 'sma_200',
                'ema_9', 'ema_21',
                'rsi_14',
                'macd_12_26_9',
                'bbands_20_2',
                'atr_14',
                'adx_14',
                'stoch_14_3_3',
                'cci_14',
                'tsi_25_13'
            ]
        else:
            self.technical_indicators = technical_indicators
        
        # Create indicator calculator
        self.indicator_calculator = IndicatorCalculator()
        
        # Preprocess data - add technical indicators and normalize
        self._preprocess_data()
        
        # Build observation and action spaces
        self._build_observation_space()
        self._build_action_space()
        
        # Initialize variables that will be reset
        self.current_step = None
        self.balance = None
        self.margin_used = None
        self.position = None
        self.position_value = None
        self.portfolio_value = None
        self.previous_portfolio_value = None
        self.returns_history = None
        self.trades_history = None
        self.unrealized_pnl = None
        
        # Rendering
        self.viewer = None
        self.fig = None
        self.ax = None
    
    def _preprocess_data(self):
        """
        Preprocess the data by adding technical indicators, bid-ask data, and normalizing.
        """
        # Copy the dataframe to avoid modifying the original
        self.processed_df = self.df.copy()
        
        # Add bid-ask columns if not already present
        if 'bid' not in self.processed_df.columns:
            self.processed_df['bid'] = self.processed_df['close'] - (self.processed_df['close'] * self.spread / 2)
        if 'ask' not in self.processed_df.columns:
            self.processed_df['ask'] = self.processed_df['close'] + (self.processed_df['close'] * self.spread / 2)
        
        # Calculate logarithmic returns for normalization
        self.processed_df['log_returns'] = np.log(
            self.processed_df['close'] / self.processed_df['close'].shift(1)
        ).fillna(0)
        
        # Calculate spread in pips
        self.processed_df['spread_pips'] = ((self.processed_df['ask'] - self.processed_df['bid']) / 
                                           self.processed_df['close']) * 10000  # 10000 for 4-digit pip convention
        
        # Calculate technical indicators
        self._calculate_technical_indicators()
        
        # Calculate normalization parameters for each feature
        self._calculate_normalization_params()
        
        # Ensure we have enough data for the window
        if len(self.processed_df) <= self.window_size:
            raise ValueError(f"Data length ({len(self.processed_df)}) must be greater than window_size ({self.window_size})")
    
    def _calculate_technical_indicators(self):
        """
        Calculate all required technical indicators using the indicator calculator.
        """
        # Initialize a dictionary to hold indicator parameters
        indicator_params = {}
        
        # Parse indicator names and parameters from the technical_indicators list
        for indicator_str in self.technical_indicators:
            if '_' in indicator_str:
                # Parse parameters from the indicator string (e.g., 'sma_20' -> 'SMA', period=20)
                parts = indicator_str.split('_')
                name = parts[0].upper()
                params = {f"period{i+1}": int(param) for i, param in enumerate(parts[1:])}
                
                # Special handling for certain indicators
                if name == 'MACD' and len(parts) >= 4:
                    params = {
                        'fastperiod': int(parts[1]),
                        'slowperiod': int(parts[2]),
                        'signalperiod': int(parts[3])
                    }
                elif name == 'BBANDS' and len(parts) >= 3:
                    params = {
                        'timeperiod': int(parts[1]),
                        'nbdevup': float(parts[2]),
                        'nbdevdn': float(parts[2])
                    }
                
                # Add to the parameters dictionary
                indicator_params[indicator_str] = {'name': name, 'params': params}
            else:
                # Simple indicator with no parameters
                indicator_params[indicator_str] = {'name': indicator_str.upper(), 'params': {}}
        
        # Calculate each indicator
        for indicator_str, config in indicator_params.items():
            try:
                # Calculate the indicator
                result = self.indicator_calculator.calculate(
                    config['name'],
                    self.processed_df,
                    config['params']
                )
                
                # Handle different return types
                if isinstance(result, pd.Series):
                    self.processed_df[indicator_str] = result
                elif isinstance(result, dict):
                    # For indicators that return multiple series
                    for key, series in result.items():
                        self.processed_df[f"{indicator_str}_{key}"] = series
                
                logger.debug(f"Calculated indicator: {indicator_str}")
            except Exception as e:
                logger.warning(f"Failed to calculate indicator {indicator_str}: {e}")
                # Add placeholder column to avoid missing data
                self.processed_df[indicator_str] = 0
        
        # Fill NaN values with appropriate defaults
        # Use forward fill for most indicators and zero for any remaining NaNs
        self.processed_df = self.processed_df.fillna(method='ffill').fillna(0)
        
        # Special handling for bounded indicators
        if 'rsi_14' in self.processed_df.columns:
            self.processed_df['rsi_14'].fillna(50, inplace=True)
        
        if 'stoch_14_3_3' in self.processed_df.columns:
            self.processed_df['stoch_14_3_3'].fillna(50, inplace=True)
    
    def _calculate_normalization_params(self):
        """
        Calculate normalization parameters for each feature.
        """
        # Store means and standard deviations for normalization
        self.normalization_params = {}
        
        # Price data normalization (Z-score parameters)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            self.normalization_params[col] = {
                'mean': self.processed_df[col].mean(),
                'std': self.processed_df[col].std() or 1.0  # Avoid division by zero
            }
        
        # Log returns typically centered around 0, but still need scaling
        self.normalization_params['log_returns'] = {
            'mean': 0,
            'std': self.processed_df['log_returns'].std() or 0.001  # Avoid division by zero
        }
        
        # Store min/max for bounded indicators (MinMax scaling)
        for col in self.processed_df.columns:
            if col.startswith('rsi_') or col.startswith('stoch_'):
                self.normalization_params[col] = {
                    'min': self.processed_df[col].min(),
                    'max': self.processed_df[col].max()
                }
    
    def _build_observation_space(self):
        """
        Define the observation space for the Forex trading environment.
        
        The observation space is a Box with shape (window_size, features_count),
        representing a window of time steps with various features.
        """
        # Calculate feature count
        base_features = 7  # OHLCV + log_returns + spread_pips
        
        # Count technical indicator columns
        tech_columns = [col for col in self.processed_df.columns 
                       if any(col.startswith(ind.lower()) for ind in self.technical_indicators)]
        tech_features = len(tech_columns)
        
        # Portfolio state features
        portfolio_features = 3  # balance, position, unrealized_pnl
        
        # Total features
        self.features_count = base_features + tech_features + portfolio_features
        
        # Use Box space with appropriate shape for time-series data
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, 
            shape=(self.window_size, self.features_count), 
            dtype=np.float32
        )
        
        # Store the column names for debugging and observation construction
        self.feature_columns = (
            ['open', 'high', 'low', 'close', 'volume', 'log_returns', 'spread_pips'] + 
            tech_columns
        )
        
        logger.info(f"Observation space shape: {self.observation_space.shape} with {len(self.feature_columns)} market features")
    
    def _build_action_space(self):
        """
        Define the action space for the Forex trading environment.
        
        We use a continuous action space where the value represents the 
        desired position as a percentage of the maximum possible position.
        
        Action space:
        - Box([-1.0], [1.0]) where:
          * -1.0: Maximum short position
          * 0.0: No position
          * 1.0: Maximum long position
        """
        # Continuous action space for position sizing
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(1,), dtype=np.float32
        )
        
        logger.info(f"Action space: {self.action_space}")
    
    def reset(self, seed=None, options=None):
        """
        Reset the environment to an initial state.
        
        Args:
            seed: Random seed for reproducibility
            options: Additional options (not used)
            
        Returns:
            observation: Initial state
            info: Additional information
        """
        # Initialize the RNG
        super().reset(seed=seed)
        
        # Reset environment state
        self.current_step = self.window_size
        self.balance = self.initial_balance
        self.position = 0
        self.margin_used = 0
        self.position_value = 0
        self.unrealized_pnl = 0
        self.portfolio_value = self.initial_balance
        self.previous_portfolio_value = self.portfolio_value
        self.returns_history = []
        self.trades_history = []
        
        # Get initial observation
        observation = self._get_observation()
        info = self._get_info()
        
        return observation, info
    
    def step(self, action):
        """
        Take an action in the environment.
        
        Args:
            action: The action to take, representing desired position size
            
        Returns:
            observation: New state after action
            reward: Reward for the action
            terminated: Whether the episode is terminated
            truncated: Whether the episode is truncated
            info: Additional information
        """
        # Store pre-action state
        previous_portfolio_value = self.portfolio_value
        
        # Execute the action
        self._take_action(action)
        
        # Move to next step
        self.current_step += 1
        
        # Check if episode is done
        terminated = False
        truncated = False
        
        # Episode ends if we've reached the end of data or balance is too low
        if self.current_step >= len(self.processed_df) - 1:
            truncated = True
        elif self.portfolio_value < self.initial_balance * 0.1:
            # Stop if lost 90% of initial capital
            terminated = True
        
        # Calculate reward
        reward = self._calculate_reward()
        
        # Get new observation
        observation = self._get_observation()
        
        # Update return history
        if self.previous_portfolio_value > 0:
            returns = (self.portfolio_value - self.previous_portfolio_value) / self.previous_portfolio_value
            self.returns_history.append(returns)
        
        self.previous_portfolio_value = self.portfolio_value
        
        # Compile step information
        info = self._get_info()
        
        return observation, reward, terminated, truncated, info
    
    def _get_observation(self):
        """
        Get the current observation (state).
        
        Returns:
            A normalized window of market data and portfolio state.
        """
        # Get the window of market data
        market_data = self.processed_df.iloc[self.current_step - self.window_size:self.current_step]
        
        # Extract features from the market data
        market_features = market_data[self.feature_columns].values
        
        # Normalize market features
        normalized_features = np.zeros_like(market_features, dtype=np.float32)
        for i, col in enumerate(self.feature_columns):
            if col in self.normalization_params:
                params = self.normalization_params[col]
                if 'mean' in params:
                    # Z-score normalization
                    normalized_features[:, i] = (market_features[:, i] - params['mean']) / params['std']
                elif 'min' in params:
                    # Min-max normalization to [0, 1]
                    normalized_features[:, i] = (market_features[:, i] - params['min']) / (params['max'] - params['min'] + 1e-10)
            else:
                # Default to Z-score with global parameters if specific ones not found
                mean = market_features[:, i].mean()
                std = market_features[:, i].std() or 1.0
                normalized_features[:, i] = (market_features[:, i] - mean) / std
        
        # Create a template for the full observation
        observation = np.zeros((self.window_size, self.features_count), dtype=np.float32)
        
        # Fill in the normalized market features
        observation[:, :len(self.feature_columns)] = normalized_features
        
        # Add portfolio state features (repeated for each time step)
        # Normalize balance as percentage of initial balance
        normalized_balance = (self.balance / self.initial_balance) - 1.0  # Center around 0
        
        # Position is already normalized between -1 and 1
        normalized_position = self.position
        
        # Normalize unrealized PnL as percentage of balance
        normalized_pnl = self.unrealized_pnl / (self.balance + 1e-10)
        
        # Add portfolio features to each time step
        portfolio_features = np.array([normalized_balance, normalized_position, normalized_pnl], dtype=np.float32)
        for i in range(self.window_size):
            observation[i, len(self.feature_columns):len(self.feature_columns) + 3] = portfolio_features
        
        return observation
    
    def _take_action(self, action):
        """
        Execute a trading action.
        
        Args:
            action: Continuous value representing the desired position
                   -1.0: Maximum short, 0.0: No position, 1.0: Maximum long
        """
        # Convert action value to desired position
        # Action is a numpy array with shape (1,), extract the scalar
        action_value = action[0]
        
        # Apply any action noise or transformation here if needed
        desired_position = action_value
        
        # Calculate the current portfolio value
        current_bid = self.processed_df.iloc[self.current_step]['bid']
        current_ask = self.processed_df.iloc[self.current_step]['ask']
        
        # Calculate unrealized PnL
        if self.position > 0:
            # Long position, use bid price for valuation
            self.unrealized_pnl = self.position_value * ((current_bid / self.entry_price) - 1.0)
        elif self.position < 0:
            # Short position, use ask price for valuation
            self.unrealized_pnl = -self.position_value * ((current_ask / self.entry_price) - 1.0)
        else:
            self.unrealized_pnl = 0.0
        
        # Update portfolio value
        self.portfolio_value = self.balance + self.unrealized_pnl
        
        # Calculate max position size based on leverage and balance
        max_position_size = self.balance * self.leverage * self.trading_volume
        
        # Calculate the target position
        target_position = desired_position
        
        # Calculate the change in position
        delta_position = target_position - self.position
        
        # If position change is very small, don't trade
        if abs(delta_position) < 0.01:
            return
        
        # Calculate the actual position change
        actual_delta_position = delta_position
        
        # Define position size in terms of account size
        position_size_delta = abs(actual_delta_position) * max_position_size
        
        # Record trade details for logging
        trade_price = 0
        trade_cost = 0
        
        # Execute the trade
        if actual_delta_position > 0:
            # Increasing position (either buying or reducing short)
            trade_price = current_ask * (1 + self.slippage)  # Include slippage
            trade_cost = position_size_delta * self.commission  # Commission
            
            # Update account
            self.balance -= trade_cost
            
            # If this is a new position or flipping from short to long
            if self.position <= 0:
                self.entry_price = trade_price
                self.position_value = position_size_delta
            else:
                # Increasing existing long position - adjust average entry price
                self.position_value += position_size_delta
                self.entry_price = ((self.entry_price * self.position) + 
                                  (trade_price * actual_delta_position)) / target_position
            
        elif actual_delta_position < 0:
            # Decreasing position (either selling or increasing short)
            trade_price = current_bid * (1 - self.slippage)  # Include slippage
            trade_cost = position_size_delta * self.commission  # Commission
            
            # Update account
            self.balance -= trade_cost
            
            # If closing a long position
            if self.position > 0 and target_position <= 0:
                # Realized P&L from closing long
                realized_pnl = self.position_value * ((trade_price / self.entry_price) - 1.0) - trade_cost
                self.balance += self.position_value + realized_pnl
                
                # If flipping to short, set new position parameters
                if target_position < 0:
                    self.entry_price = trade_price
                    self.position_value = position_size_delta
                else:
                    # Just closing to flat
                    self.position_value = 0
                    
            # If closing a short position
            elif self.position < 0 and target_position >= 0:
                # Realized P&L from closing short
                realized_pnl = -self.position_value * ((trade_price / self.entry_price) - 1.0) - trade_cost
                self.balance += self.position_value + realized_pnl
                
                # If flipping to long, set new position parameters
                if target_position > 0:
                    self.entry_price = trade_price
                    self.position_value = position_size_delta
                else:
                    # Just closing to flat
                    self.position_value = 0
                    
            # If adjusting an existing position
            else:
                # Just adjust the position size
                self.position_value = abs(target_position) * max_position_size
        
        # Update the position
        self.position = target_position
        
        # Update margin used
        self.margin_used = self.position_value / self.leverage if self.position != 0 else 0
        
        # Log the trade
        self.trades_history.append({
            'step': self.current_step,
            'price': trade_price,
            'position_delta': actual_delta_position,
            'cost': trade_cost,
            'position': self.position,
            'balance': self.balance,
            'portfolio_value': self.portfolio_value
        })
    
    def _calculate_reward(self):
        """
        Calculate the reward based on the specified reward type.
        """
        if self.reward_type == 'profit':
            return self._calculate_profit_reward()
        elif self.reward_type == 'sharpe':
            return self._calculate_sharpe_reward()
        elif self.reward_type == 'sortino':
            return self._calculate_sortino_reward()
        else:
            return self._calculate_profit_reward()  # Default
    
    def _calculate_profit_reward(self):
        """
        Calculate reward based on profit/loss.
        """
        # Simple change in portfolio value
        return (self.portfolio_value - self.previous_portfolio_value) / self.initial_balance
    
    def _calculate_sharpe_reward(self):
        """
        Calculate reward based on Sharpe ratio.
        """
        if len(self.returns_history) < 2:
            return 0.0
        
        # Calculate Sharpe ratio over recent returns
        recent_returns = self.returns_history[-20:] if len(self.returns_history) > 20 else self.returns_history
        
        mean_return = np.mean(recent_returns)
        std_return = np.std(recent_returns) or 1e-6  # Avoid division by zero
        
        # Use risk-free rate of 0 for simplicity
        sharpe = mean_return / std_return * np.sqrt(252)  # Annualized
        
        # Scale down the sharpe reward
        return sharpe * 0.01
    
    def _calculate_sortino_reward(self):
        """
        Calculate reward based on Sortino ratio (penalizes only downside volatility).
        """
        if len(self.returns_history) < 2:
            return 0.0
        
        # Calculate Sortino ratio over recent returns
        recent_returns = self.returns_history[-20:] if len(self.returns_history) > 20 else self.returns_history
        
        mean_return = np.mean(recent_returns)
        
        # Calculate downside deviation (only negative returns)
        negative_returns = [r for r in recent_returns if r < 0]
        if not negative_returns:
            downside_deviation = 1e-6  # Avoid division by zero if no negative returns
        else:
            downside_deviation = np.sqrt(np.mean(np.square(negative_returns)))
        
        # Use risk-free rate of 0 for simplicity
        sortino = mean_return / downside_deviation * np.sqrt(252)  # Annualized
        
        # Scale down the sortino reward
        return sortino * 0.01
    
    def _get_info(self):
        """
        Get additional information about the current state.
        """
        return {
            'step': self.current_step,
            'balance': self.balance,
            'position': self.position,
            'position_value': self.position_value,
            'unrealized_pnl': self.unrealized_pnl,
            'portfolio_value': self.portfolio_value,
            'margin_used': self.margin_used,
            'margin_level': (self.balance / self.margin_used) if self.margin_used > 0 else float('inf'),
            'price': self.processed_df.iloc[self.current_step]['close'],
            'trades_count': len(self.trades_history)
        }
    
    def render(self):
        """
        Render the environment visualization.
        
        Returns:
            A visualization of the trading environment based on render_mode.
        """
        # Implement rendering logic similar to CryptoTradingEnv but tailored for forex
        # This would include plotting price data, indicators, and trading actions
        pass
    
    def close(self):
        """
        Clean up resources.
        """
        if self.viewer is not None:
            self.viewer.close()
            self.viewer = None
        if self.fig is not None:
            plt.close(self.fig)
            self.fig = None 