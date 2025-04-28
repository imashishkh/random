"""
Cryptocurrency Trading Environment for Reinforcement Learning

This module implements a Gymnasium-compatible environment for cryptocurrency
trading, designed for training reinforcement learning agents. It simulates
a cryptocurrency market with configurable parameters for realistic trading.
"""

import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Optional, Any, Union


class CryptoTradingEnv(gym.Env):
    """
    Custom Gymnasium environment for cryptocurrency trading.
    
    This environment simulates trading in cryptocurrency markets with realistic
    features like bid-ask spreads, slippage, and transaction costs. It supports
    both discrete and continuous action spaces, along with multiple reward functions.
    
    Attributes:
        df (pd.DataFrame): Historical price data with OHLCV columns
        initial_balance (float): Starting balance for each episode
        commission (float): Transaction fee as a percentage
        window_size (int): Number of time steps to include in the state
        reward_type (str): Type of reward function ('profit', 'sharpe', 'sortino')
        action_type (str): Type of action space ('discrete' or 'continuous')
        trading_volume (float): Percentage of balance to trade per action
        slippage (float): Maximum slippage as a percentage of price
        technical_indicators (List[str]): Technical indicators to include in state
    """
    
    metadata = {'render_modes': ['human', 'rgb_array'], 'render_fps': 4}
    
    def __init__(
        self,
        df: pd.DataFrame,
        initial_balance: float = 10000.0,
        commission: float = 0.001,
        window_size: int = 20,
        reward_type: str = 'sharpe',
        action_type: str = 'discrete',
        trading_volume: float = 0.1,
        slippage: float = 0.0005,
        technical_indicators: List[str] = None,
        render_mode: Optional[str] = None
    ):
        """
        Initialize the trading environment.
        
        Args:
            df: DataFrame with OHLCV data (columns: open, high, low, close, volume)
            initial_balance: Starting account balance
            commission: Trading fee as a percentage (e.g., 0.001 = 0.1%)
            window_size: Number of time steps to include in the state
            reward_type: Type of reward function ('profit', 'sharpe', 'sortino')
            action_type: Type of action space ('discrete' or 'continuous')
            trading_volume: Percentage of balance to trade per action
            slippage: Maximum slippage as a percentage of price
            technical_indicators: List of technical indicators to include in state
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
        self.commission = commission
        self.window_size = window_size
        self.reward_type = reward_type
        self.action_type = action_type
        self.trading_volume = trading_volume
        self.slippage = slippage
        self.technical_indicators = technical_indicators or []
        self.render_mode = render_mode
        
        # Preprocess data - add technical indicators and normalize
        self._preprocess_data()
        
        # Build observation and action spaces
        self._build_observation_space()
        self._build_action_space()
        
        # Initialize variables that will be reset
        self.current_step = None
        self.balance = None
        self.position = None
        self.portfolio_value = None
        self.previous_portfolio_value = None
        self.returns_history = None
        self.trades_history = None
        
        # Rendering
        self.viewer = None
        self.fig = None
        self.ax = None
    
    def _preprocess_data(self):
        """
        Preprocess the data by adding technical indicators and normalizing.
        """
        # Copy the dataframe to avoid modifying the original
        self.processed_df = self.df.copy()
        
        # Calculate logarithmic returns for normalization
        self.processed_df['log_returns'] = np.log(
            self.processed_df['close'] / self.processed_df['close'].shift(1)
        ).fillna(0)
        
        # Add simple moving average if requested
        if 'sma' in self.technical_indicators:
            self.processed_df['sma'] = self.processed_df['close'].rolling(window=14).mean().fillna(0)
        
        # Add relative strength index (RSI) if requested
        if 'rsi' in self.technical_indicators:
            # Calculate price changes
            delta = self.processed_df['close'].diff().fillna(0)
            
            # Calculate gains and losses
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            # Calculate average gains and losses over 14 periods
            avg_gain = gain.rolling(window=14).mean().fillna(0)
            avg_loss = loss.rolling(window=14).mean().fillna(0)
            
            # Calculate relative strength
            rs = avg_gain / avg_loss.replace(0, 1e-9)  # Avoid division by zero
            
            # Calculate RSI
            self.processed_df['rsi'] = 100 - (100 / (1 + rs))
            self.processed_df['rsi'].fillna(50, inplace=True)  # Fill NaN with neutral value
        
        # Add moving average convergence divergence (MACD) if requested
        if 'macd' in self.technical_indicators:
            # Calculate EMA-12 and EMA-26
            ema12 = self.processed_df['close'].ewm(span=12, adjust=False).mean()
            ema26 = self.processed_df['close'].ewm(span=26, adjust=False).mean()
            
            # Calculate MACD line and signal line
            self.processed_df['macd'] = ema12 - ema26
            self.processed_df['macd_signal'] = self.processed_df['macd'].ewm(span=9, adjust=False).mean()
            
            # Calculate histogram
            self.processed_df['macd_hist'] = self.processed_df['macd'] - self.processed_df['macd_signal']
        
        # Add Bollinger Bands if requested
        if 'bbands' in self.technical_indicators:
            # Calculate 20-period SMA and standard deviation
            sma20 = self.processed_df['close'].rolling(window=20).mean()
            std20 = self.processed_df['close'].rolling(window=20).std()
            
            # Calculate upper and lower bands
            self.processed_df['bb_upper'] = sma20 + (2 * std20)
            self.processed_df['bb_middle'] = sma20
            self.processed_df['bb_lower'] = sma20 - (2 * std20)
            
            # Calculate %B (position within bands)
            self.processed_df['bb_pct'] = (self.processed_df['close'] - self.processed_df['bb_lower']) / (
                self.processed_df['bb_upper'] - self.processed_df['bb_lower']
            ).replace(0, 1e-9)  # Avoid division by zero
            
            # Fill NaN values
            bands_cols = ['bb_upper', 'bb_middle', 'bb_lower', 'bb_pct']
            self.processed_df[bands_cols] = self.processed_df[bands_cols].fillna(0)
        
        # Calculate normalization values
        self.price_mean = self.processed_df['close'].mean()
        self.price_std = self.processed_df['close'].std()
        self.volume_mean = self.processed_df['volume'].mean()
        self.volume_std = self.processed_df['volume'].std()
        
        # Ensure we have enough data for the window
        if len(self.processed_df) <= self.window_size:
            raise ValueError(f"Data length ({len(self.processed_df)}) must be greater than window_size ({self.window_size})")
    
    def _build_observation_space(self):
        """Define the observation space."""
        # Calculate feature count
        base_features = 5  # OHLCV
        
        # Count how many technical indicator columns we have
        tech_features = 0
        if 'sma' in self.technical_indicators:
            tech_features += 1
        if 'rsi' in self.technical_indicators:
            tech_features += 1
        if 'macd' in self.technical_indicators:
            tech_features += 3  # macd, signal, histogram
        if 'bbands' in self.technical_indicators:
            tech_features += 4  # upper, middle, lower, %B
        
        portfolio_features = 2  # balance, position
        self.features_count = base_features + tech_features + portfolio_features
        
        # Use Box space with appropriate shape for time-series data
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, 
            shape=(self.window_size, self.features_count), 
            dtype=np.float32
        )
    
    def _build_action_space(self):
        """Define the action space based on configuration."""
        if self.action_type == 'discrete':
            # Discrete actions: 0=hold, 1=buy, 2=sell
            self.action_space = spaces.Discrete(3)
        else:
            # Continuous actions: portfolio allocation between -1 (short) and 1 (long)
            self.action_space = spaces.Box(
                low=-1, high=1, shape=(1,), dtype=np.float32
            )
    
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
        self.portfolio_value = self.initial_balance
        self.previous_portfolio_value = self.portfolio_value
        self.returns_history = []
        self.trades_history = []
        
        # Get initial observation
        observation = self._get_observation()
        info = {}
        
        return observation, info
    
    def step(self, action):
        """
        Take an action in the environment.
        
        Args:
            action: The action to take (depends on action_type)
            
        Returns:
            observation: The new state
            reward: The reward for the action
            terminated: Whether the episode is done
            truncated: Whether the episode was truncated
            info: Additional information
        """
        # Store previous values for reward calculation
        self.previous_portfolio_value = self.portfolio_value
        
        # Execute action and update state
        self._take_action(action)
        
        # Move to next time step
        self.current_step += 1
        
        # Calculate reward
        reward = self._calculate_reward()
        
        # Update portfolio value
        current_price = self.df.iloc[self.current_step]['close']
        self.portfolio_value = self.balance + self.position * current_price
        
        # Calculate return for this step
        if self.previous_portfolio_value > 0:
            current_return = (self.portfolio_value / self.previous_portfolio_value) - 1
            self.returns_history.append(current_return)
        
        # Check if episode is done
        terminated = self.current_step >= len(self.df) - 1
        truncated = False
        
        # Get next observation
        observation = self._get_observation()
        
        # Populate info
        info = {
            'portfolio_value': self.portfolio_value,
            'balance': self.balance,
            'position': self.position,
            'return': current_return if self.previous_portfolio_value > 0 else 0
        }
        
        return observation, reward, terminated, truncated, info
    
    def _get_observation(self):
        """
        Get the current state observation.
        
        Returns:
            numpy.ndarray: The current state as a 2D array
        """
        # Get the window slice from the processed data
        start_idx = self.current_step - self.window_size + 1
        end_idx = self.current_step + 1  # exclusive
        window_data = self.processed_df.iloc[start_idx:end_idx].copy()
        
        # Normalize OHLCV data
        for col in ['open', 'high', 'low', 'close']:
            window_data[f'{col}_norm'] = (window_data[col] - self.price_mean) / self.price_std
        
        window_data['volume_norm'] = (window_data['volume'] - self.volume_mean) / self.volume_std
        
        # Prepare feature columns based on configuration
        feature_cols = []
        
        # Add normalized OHLCV
        feature_cols.extend(['open_norm', 'high_norm', 'low_norm', 'close_norm', 'volume_norm'])
        
        # Add technical indicators
        if 'sma' in self.technical_indicators:
            # Normalize SMA
            window_data['sma_norm'] = (window_data['sma'] - self.price_mean) / self.price_std
            feature_cols.append('sma_norm')
        
        if 'rsi' in self.technical_indicators:
            # RSI is already normalized (0-100)
            # Scale to [0, 1] for consistency
            window_data['rsi_norm'] = window_data['rsi'] / 100
            feature_cols.append('rsi_norm')
        
        if 'macd' in self.technical_indicators:
            # Normalize MACD features
            window_data['macd_norm'] = window_data['macd'] / self.price_std
            window_data['macd_signal_norm'] = window_data['macd_signal'] / self.price_std
            window_data['macd_hist_norm'] = window_data['macd_hist'] / self.price_std
            feature_cols.extend(['macd_norm', 'macd_signal_norm', 'macd_hist_norm'])
        
        if 'bbands' in self.technical_indicators:
            # Normalize Bollinger Bands
            window_data['bb_upper_norm'] = (window_data['bb_upper'] - self.price_mean) / self.price_std
            window_data['bb_middle_norm'] = (window_data['bb_middle'] - self.price_mean) / self.price_std
            window_data['bb_lower_norm'] = (window_data['bb_lower'] - self.price_mean) / self.price_std
            # %B is already normalized
            feature_cols.extend(['bb_upper_norm', 'bb_middle_norm', 'bb_lower_norm', 'bb_pct'])
        
        # Add portfolio information
        # Normalize balance and position
        window_data['balance_norm'] = self.balance / self.initial_balance
        window_data['position_norm'] = self.position * self.processed_df.iloc[self.current_step]['close'] / self.initial_balance
        feature_cols.extend(['balance_norm', 'position_norm'])
        
        # Create observation array
        observation = window_data[feature_cols].values.astype(np.float32)
        
        # Check if observation shape matches the expected shape
        if observation.shape != (self.window_size, self.features_count):
            raise ValueError(f"Observation shape {observation.shape} doesn't match expected shape {(self.window_size, self.features_count)}")
        
        return observation
    
    def _take_action(self, action):
        """
        Execute the specified trading action.
        
        Args:
            action: Trading action to take (buy/sell/hold)
        """
        # Get current price data
        current_price_data = self.processed_df.iloc[self.current_step]
        current_price = current_price_data['close']
        
        # Calculate bid-ask spread based on price and slippage
        spread = current_price * self.slippage
        bid_price = current_price - spread / 2  # Price we can sell at
        ask_price = current_price + spread / 2  # Price we can buy at
        
        # Determine the action based on action_type
        if self.action_type == 'discrete':
            # Discrete actions: 0=hold, 1=buy, 2=sell
            discrete_action = action
        else:
            # Continuous actions: Convert to discrete
            # action is a continuous value between -1 and 1
            # -1 to -0.33: sell
            # -0.33 to 0.33: hold
            # 0.33 to 1: buy
            if action[0] > 0.33:
                discrete_action = 1  # buy
            elif action[0] < -0.33:
                discrete_action = 2  # sell
            else:
                discrete_action = 0  # hold
        
        # Calculate trading size
        cash_to_use = self.balance * self.trading_volume
        position_to_sell = abs(self.position) * self.trading_volume
        
        # Zero out small amounts to prevent dust positions
        if cash_to_use < 1.0:
            cash_to_use = 0
        if position_to_sell < 0.01:
            position_to_sell = 0
            
        # Log the intended action
        action_map = {0: 'HOLD', 1: 'BUY', 2: 'SELL'}
        intended_action = action_map[discrete_action]
        
        # Execute the action
        if discrete_action == 0:  # HOLD
            # No action taken
            pass
            
        elif discrete_action == 1:  # BUY
            if cash_to_use > 0:
                # Calculate buy amount considering fees
                buy_price = ask_price * (1 + self.commission)
                max_shares_to_buy = cash_to_use / buy_price
                
                # Execute the trade
                self.position += max_shares_to_buy
                self.balance -= max_shares_to_buy * buy_price
                
                # Log the trade
                self.trades_history.append({
                    'step': self.current_step,
                    'type': 'BUY',
                    'price': buy_price,
                    'amount': max_shares_to_buy,
                    'cost': max_shares_to_buy * buy_price,
                    'balance': self.balance,
                    'position': self.position
                })
                
        elif discrete_action == 2:  # SELL
            if self.position > 0 and position_to_sell > 0:
                # Calculate sell amount considering fees
                sell_price = bid_price * (1 - self.commission)
                shares_to_sell = min(position_to_sell, self.position)
                
                # Execute the trade
                self.position -= shares_to_sell
                self.balance += shares_to_sell * sell_price
                
                # Log the trade
                self.trades_history.append({
                    'step': self.current_step,
                    'type': 'SELL',
                    'price': sell_price,
                    'amount': shares_to_sell,
                    'revenue': shares_to_sell * sell_price,
                    'balance': self.balance,
                    'position': self.position
                })
        
        # Calculate current portfolio value
        self.portfolio_value = self.balance + self.position * current_price
    
    def _calculate_reward(self):
        """
        Calculate the reward for the current step.
        
        Returns:
            float: The calculated reward
        """
        if self.reward_type == 'profit':
            reward = self._calculate_profit_reward()
        elif self.reward_type == 'sharpe':
            reward = self._calculate_sharpe_reward()
        elif self.reward_type == 'sortino':
            reward = self._calculate_sortino_reward()
        else:
            raise ValueError(f"Unknown reward type: {self.reward_type}")
        
        return reward
    
    def _calculate_profit_reward(self):
        """
        Calculate a simple profit-based reward.
        
        Returns:
            float: The profit-based reward
        """
        # Calculate profit for this step
        profit = self.portfolio_value - self.previous_portfolio_value
        
        # Normalize profit by initial balance for more stable scaling
        normalized_profit = profit / self.initial_balance
        
        return normalized_profit
    
    def _calculate_sharpe_reward(self):
        """
        Calculate a Sharpe ratio based reward.
        
        Returns:
            float: The Sharpe ratio based reward
        """
        # Need at least 2 returns to calculate volatility
        if len(self.returns_history) < 2:
            return 0
        
        # Calculate returns mean and standard deviation
        returns_mean = np.mean(self.returns_history[-20:])  # Use last 20 returns
        returns_std = np.std(self.returns_history[-20:])
        
        # Avoid division by zero
        if returns_std == 0:
            returns_std = 1e-6
        
        # Calculate Sharpe ratio (simplified - no risk-free rate)
        # Annualized assuming daily returns
        sharpe = np.sqrt(252) * returns_mean / returns_std
        
        # Scale for better learning dynamics
        # Typical Sharpe values are between -3 and 3, so scale to a similar range as profit reward
        scaled_sharpe = np.clip(sharpe / 10, -1, 1)
        
        return scaled_sharpe
    
    def _calculate_sortino_reward(self):
        """
        Calculate a Sortino ratio based reward (penalizes only downside volatility).
        
        Returns:
            float: The Sortino ratio based reward
        """
        # Need at least 2 returns to calculate downside deviation
        if len(self.returns_history) < 2:
            return 0
        
        # Calculate returns mean and downside deviation
        returns = np.array(self.returns_history[-20:])  # Use last 20 returns
        returns_mean = np.mean(returns)
        
        # Filter for negative returns (downside)
        negative_returns = returns[returns < 0]
        
        # Avoid division by zero if no negative returns
        if len(negative_returns) < 1:
            downside_std = 1e-6
        else:
            downside_std = np.std(negative_returns)
            
            # Avoid division by zero
            if downside_std == 0:
                downside_std = 1e-6
        
        # Calculate Sortino ratio (simplified - no minimum acceptable return)
        # Annualized assuming daily returns
        sortino = np.sqrt(252) * returns_mean / downside_std
        
        # Scale for better learning dynamics
        # Typical Sortino values might be larger than Sharpe, so scale appropriately
        scaled_sortino = np.clip(sortino / 15, -1, 1)
        
        return scaled_sortino
    
    def render(self):
        """
        Render the environment.
        
        Returns:
            The rendering of the environment, depending on render_mode
        """
        if self.render_mode is None:
            return
        
        # Create the figure if it doesn't exist
        if self.fig is None:
            self.fig, self.ax = plt.subplots(figsize=(10, 6))
            plt.ion()  # Turn on interactive mode
        
        # Clear the axes
        self.ax.clear()
        
        # Get data for the visible window
        start_idx = max(0, self.current_step - 50)  # Show the last 50 steps
        end_idx = self.current_step + 1  # Include current step
        plot_df = self.processed_df.iloc[start_idx:end_idx].copy()
        
        # Plot price
        self.ax.plot(plot_df.index, plot_df['close'], label='Price', color='blue')
        
        # Add buy and sell markers from trades history
        for trade in self.trades_history:
            if trade['step'] >= start_idx and trade['step'] <= self.current_step:
                # Get the price at this step
                price = self.processed_df.iloc[trade['step']]['close']
                
                if trade['type'] == 'BUY':
                    self.ax.scatter(trade['step'], price, color='green', marker='^', s=100)
                elif trade['type'] == 'SELL':
                    self.ax.scatter(trade['step'], price, color='red', marker='v', s=100)
        
        # Add technical indicators if available
        if 'sma' in self.technical_indicators:
            self.ax.plot(plot_df.index, plot_df['sma'], label='SMA', color='orange', alpha=0.7)
        
        if 'bbands' in self.technical_indicators:
            self.ax.plot(plot_df.index, plot_df['bb_upper'], label='BB Upper', color='gray', linestyle='--', alpha=0.5)
            self.ax.plot(plot_df.index, plot_df['bb_middle'], label='BB Middle', color='gray', linestyle='-', alpha=0.5)
            self.ax.plot(plot_df.index, plot_df['bb_lower'], label='BB Lower', color='gray', linestyle='--', alpha=0.5)
        
        # Add portfolio value as a separate axis
        portfolio_values = []
        for i in range(start_idx, end_idx):
            if i < self.window_size:
                # Not enough history yet
                portfolio_values.append(self.initial_balance)
            else:
                # Calculate historical portfolio value
                step_position = 0
                step_balance = self.initial_balance
                
                # Apply trades up to this point
                for trade in self.trades_history:
                    if trade['step'] <= i:
                        step_position = trade['position']
                        step_balance = trade['balance']
                
                # Calculate portfolio value at this step
                price = self.processed_df.iloc[i]['close']
                portfolio_value = step_balance + step_position * price
                portfolio_values.append(portfolio_value)
        
        # Create a secondary y-axis for portfolio value
        ax2 = self.ax.twinx()
        ax2.plot(plot_df.index, portfolio_values, label='Portfolio Value', color='purple', linestyle='-.')
        ax2.set_ylabel('Portfolio Value ($)', color='purple')
        
        # Add labels and legend
        self.ax.set_title('Cryptocurrency Trading Environment')
        self.ax.set_xlabel('Time Step')
        self.ax.set_ylabel('Price ($)', color='blue')
        
        # Add legends for both axes
        lines1, labels1 = self.ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        self.ax.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
        # Add current portfolio information
        info_text = (
            f"Step: {self.current_step}\n"
            f"Price: ${self.processed_df.iloc[self.current_step]['close']:.2f}\n"
            f"Balance: ${self.balance:.2f}\n"
            f"Position: {self.position:.6f}\n"
            f"Portfolio: ${self.portfolio_value:.2f}"
        )
        plt.gcf().text(0.01, 0.01, info_text, fontsize=9)
        
        # Render
        if self.render_mode == 'human':
            plt.draw()
            plt.pause(0.01)
            return None
        elif self.render_mode == 'rgb_array':
            # Convert figure to RGB array
            self.fig.canvas.draw()
            img = np.array(self.fig.canvas.renderer.buffer_rgba())
            return img
    
    def close(self):
        """Release resources."""
        if self.viewer:
            self.viewer.close()
            self.viewer = None
        if self.fig:
            plt.close(self.fig)
            self.fig = None 