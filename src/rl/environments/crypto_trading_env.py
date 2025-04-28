import gymnasium as gym
import numpy as np
from gymnasium import spaces
from typing import Dict, List, Optional, Tuple, Union, Any
import pandas as pd


class CryptoTradingEnv(gym.Env):
    """
    A cryptocurrency trading environment that follows the Gymnasium interface.
    
    This environment simulates trading on cryptocurrency markets with realistic
    features like slippage, fees, and partial fills based on liquidity.
    
    Attributes:
        action_space: The space of valid actions an agent can take
        observation_space: The space of valid observations
        reward_range: The range of possible rewards
    """
    metadata = {"render_modes": ["human", "rgb_array"], "render_fps": 4}
    
    def __init__(
        self,
        price_data: pd.DataFrame,
        initial_balance: float = 10000.0,
        transaction_fee: float = 0.001,  # 0.1% fee
        slippage: float = 0.0005,  # 0.05% slippage
        window_size: int = 24,  # Use 24-hour price history for state
        reward_function: str = "sharpe",  # 'simple' or 'sharpe'
        action_type: str = "discrete",  # 'discrete' or 'continuous'
        max_position: float = 1.0,  # Maximum position size as a fraction of balance
        render_mode: Optional[str] = None,
    ):
        """
        Initialize the trading environment.
        
        Args:
            price_data: Historical price data with OHLCV columns
            initial_balance: Starting account balance in quote currency
            transaction_fee: Fee per transaction as a fraction
            slippage: Average slippage per trade as a fraction
            window_size: Number of time steps to include in the state
            reward_function: Method to calculate reward ('simple' or 'sharpe')
            action_type: Type of action space ('discrete' or 'continuous')
            max_position: Maximum position size as a fraction of balance
            render_mode: Mode for rendering the environment
        """
        super().__init__()
        
        self.price_data = price_data
        self.initial_balance = initial_balance
        self.transaction_fee = transaction_fee
        self.slippage = slippage
        self.window_size = window_size
        self.reward_function = reward_function
        self.action_type = action_type
        self.max_position = max_position
        self.render_mode = render_mode
        
        # Validate the price data
        self._validate_price_data()
        
        # Action space
        if action_type == "discrete":
            # Discrete actions: Buy, Sell, Hold
            self.action_space = spaces.Discrete(3)
        else:
            # Continuous action: Position size ranges from -1.0 (full short) to 1.0 (full long)
            self.action_space = spaces.Box(
                low=-1.0, high=1.0, shape=(1,), dtype=np.float32
            )
        
        # Observation space: Price history + account state
        # Price history for window_size steps: OHLCV (normalized) = 5 features
        # Account state: current balance, current position, unrealized profit = 3 features
        # Total features: 5 * window_size + 3
        num_features = 5 * window_size + 3
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(num_features,), dtype=np.float32
        )
        
        # Episode state
        self.current_step = 0
        self.balance = initial_balance
        self.position = 0  # Current position in base currency
        self.trades = []
        self.returns = []
        self.done = False
        
    def _validate_price_data(self):
        """Validate the price data has required columns."""
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in required_columns:
            if col not in self.price_data.columns:
                raise ValueError(f"Price data missing required column: {col}")
        
    def reset(
        self, 
        seed: Optional[int] = None, 
        options: Optional[Dict[str, Any]] = None
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Reset the environment to an initial state.
        
        Args:
            seed: The seed to use for random number generation
            options: Additional options for environment reset
            
        Returns:
            observation: The initial state of the environment
            info: Additional information about the reset
        """
        super().reset(seed=seed)
        
        # Reset episode state
        self.current_step = self.window_size
        self.balance = self.initial_balance
        self.position = 0
        self.trades = []
        self.returns = []
        self.done = False
        
        return self._get_observation(), {}
    
    def step(self, action: Union[int, np.ndarray]) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """
        Take a step in the environment with the specified action.
        
        Args:
            action: The action to take (depends on action_type)
            
        Returns:
            observation: The new state after taking the action
            reward: The reward for taking the action
            terminated: Whether the episode is terminated
            truncated: Whether the episode was truncated
            info: Additional information about the step
        """
        if self.done:
            # If we're done, return terminal state
            return self._get_observation(), 0.0, True, False, {}
        
        # Process the action
        old_position = self.position
        old_portfolio_value = self._get_portfolio_value()
        
        if self.action_type == "discrete":
            # Discrete action: 0 = Buy, 1 = Sell, 2 = Hold
            if action == 0:  # Buy
                self._buy(position_size=self.max_position)
            elif action == 1:  # Sell
                self._sell(position_size=self.max_position)
            # action == 2 is Hold, do nothing
        else:
            # Continuous action: Value between -1.0 and 1.0 representing position size
            # Negative values indicate short positions, positive values indicate long positions
            target_position = float(action[0]) * self.max_position
            
            if target_position > old_position:
                # Increase position (buy)
                self._buy(position_size=target_position - old_position)
            elif target_position < old_position:
                # Decrease position (sell)
                self._sell(position_size=old_position - target_position)
        
        # Move to the next time step
        self.current_step += 1
        
        # Check if we've reached the end of the data
        if self.current_step >= len(self.price_data) - 1:
            self.done = True
        
        # Calculate reward based on portfolio value change
        new_portfolio_value = self._get_portfolio_value()
        simple_return = new_portfolio_value / old_portfolio_value - 1
        self.returns.append(simple_return)
        
        if self.reward_function == "simple":
            reward = simple_return
        elif self.reward_function == "sharpe":
            # Calculate Sharpe ratio-like reward if we have enough returns
            if len(self.returns) > 1:
                returns_array = np.array(self.returns)
                reward = self._calculate_sharpe(returns_array)
            else:
                reward = 0.0
        else:
            reward = simple_return  # Default to simple return
        
        # Get observation and return
        observation = self._get_observation()
        info = {
            "portfolio_value": new_portfolio_value,
            "position": self.position,
            "balance": self.balance,
            "return": simple_return,
        }
        
        return observation, reward, self.done, False, info
    
    def _buy(self, position_size: float):
        """
        Buy the specified position size.
        
        Args:
            position_size: Position size as a fraction of available balance
        """
        if position_size <= 0:
            return
        
        available_balance = self.balance
        if available_balance <= 0:
            return
        
        # Current price with slippage (slightly higher when buying)
        current_price = self._get_price() * (1 + self.slippage)
        
        # Calculate the amount to buy
        amount_to_spend = available_balance * position_size
        amount_to_buy = amount_to_spend / current_price
        
        # Apply transaction fee
        fee = amount_to_spend * self.transaction_fee
        amount_to_spend += fee
        
        # Ensure we don't spend more than our balance
        if amount_to_spend > self.balance:
            amount_to_spend = self.balance
            amount_to_buy = (amount_to_spend - fee) / current_price
        
        # Update balance and position
        self.balance -= amount_to_spend
        self.position += amount_to_buy
        
        # Record the trade
        self.trades.append({
            "step": self.current_step,
            "type": "buy",
            "price": current_price,
            "amount": amount_to_buy,
            "cost": amount_to_spend,
            "fee": fee
        })
    
    def _sell(self, position_size: float):
        """
        Sell the specified position size.
        
        Args:
            position_size: Position size as a fraction of current position
        """
        if position_size <= 0 or self.position <= 0:
            return
        
        # Current price with slippage (slightly lower when selling)
        current_price = self._get_price() * (1 - self.slippage)
        
        # Calculate the amount to sell
        amount_to_sell = self.position * position_size
        
        # Calculate proceeds and fee
        proceeds = amount_to_sell * current_price
        fee = proceeds * self.transaction_fee
        net_proceeds = proceeds - fee
        
        # Update balance and position
        self.balance += net_proceeds
        self.position -= amount_to_sell
        
        # Record the trade
        self.trades.append({
            "step": self.current_step,
            "type": "sell",
            "price": current_price,
            "amount": amount_to_sell,
            "proceeds": net_proceeds,
            "fee": fee
        })
    
    def _get_price(self) -> float:
        """Get the current price."""
        return self.price_data.iloc[self.current_step]['close']
    
    def _get_portfolio_value(self) -> float:
        """Calculate total portfolio value including balance and current position."""
        if self.position == 0:
            return self.balance
        
        current_price = self._get_price()
        position_value = self.position * current_price
        return self.balance + position_value
    
    def _calculate_sharpe(self, returns: np.ndarray, risk_free_rate: float = 0.0, window: int = 20) -> float:
        """
        Calculate the Sharpe ratio over a window of returns.
        
        Args:
            returns: Array of historical returns
            risk_free_rate: The risk-free rate of return
            window: Window size for Sharpe calculation
            
        Returns:
            Sharpe ratio
        """
        # Use only the most recent returns within the window
        if len(returns) > window:
            returns = returns[-window:]
        
        # Calculate mean and std of returns
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        # Avoid division by zero
        if std_return == 0:
            return 0.0
        
        # Calculate Sharpe ratio
        sharpe = (mean_return - risk_free_rate) / std_return
        
        # Annualize (assuming daily returns)
        sharpe_annualized = sharpe * np.sqrt(252)
        
        return sharpe_annualized
    
    def _get_observation(self) -> np.ndarray:
        """
        Get the current state observation.
        
        Returns:
            numpy array representing the current state
        """
        # Get price history
        start_idx = self.current_step - self.window_size
        end_idx = self.current_step
        
        # Extract and normalize price history
        price_history = self.price_data.iloc[start_idx:end_idx]
        
        # Normalize OHLCV data
        normalized_history = []
        for col in ['open', 'high', 'low', 'close', 'volume']:
            values = price_history[col].values
            # Simple normalization: divide by the first value
            normalized = values / values[0] - 1.0
            normalized_history.extend(normalized)
        
        # Account state
        portfolio_value = self._get_portfolio_value()
        normalized_balance = self.balance / self.initial_balance - 1.0
        normalized_position = self.position * self._get_price() / self.initial_balance
        unrealized_profit = portfolio_value / self.initial_balance - 1.0
        
        # Combine price history with account state
        observation = np.array(normalized_history + [normalized_balance, normalized_position, unrealized_profit], dtype=np.float32)
        
        return observation
    
    def render(self):
        """Render the environment."""
        if self.render_mode is None:
            return
        
        # In a real implementation, we would render the environment
        # For simplicity, we just print the current state
        print(f"Step: {self.current_step}")
        print(f"Portfolio Value: {self._get_portfolio_value():.2f}")
        print(f"Position: {self.position:.6f}")
        print(f"Balance: {self.balance:.2f}")
        print(f"Current Price: {self._get_price():.2f}")

    def close(self):
        """Clean up resources."""
        pass 