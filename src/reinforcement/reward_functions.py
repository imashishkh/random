"""
Reward functions for reinforcement learning trading agents.

This module provides a flexible and modular reward function framework for
trading agents, including PnL-based, risk-adjusted, and custom rewards.
"""

from abc import ABC, abstractmethod
import numpy as np
from typing import Dict, Any, Union, List, Optional


class RewardFunction(ABC):
    """Base abstract class for all reward functions.
    
    This class defines the interface that all reward functions must implement.
    Reward functions calculate the reward based on the state transition and
    trading information.
    """
    
    @abstractmethod
    def __call__(self, state: Dict[str, Any], action: int, 
                next_state: Dict[str, Any], info: Dict[str, Any]) -> float:
        """Calculate reward based on state transition and trading info.
        
        Args:
            state: Current state dictionary
            action: Action taken by the agent
            next_state: Next state dictionary
            info: Additional information from the environment
            
        Returns:
            float: Calculated reward
        """
        pass
    
    def reset(self) -> None:
        """Reset any internal state of the reward function.
        
        This method is called at the beginning of each episode.
        """
        pass
        

class PnLReward(RewardFunction):
    """Simple profit/loss reward based on absolute or percentage returns.
    
    This reward function calculates rewards based on the profit or loss
    from trading actions, optionally as a percentage of portfolio value,
    and applies transaction costs.
    """
    
    def __init__(self, use_percentage: bool = True, 
                transaction_cost: float = 0.0001,
                scale_factor: float = 1.0):
        """Initialize the PnL reward function.
        
        Args:
            use_percentage: Whether to use percentage returns instead of absolute
            transaction_cost: Cost applied when buy/sell actions are taken
            scale_factor: Scaling factor applied to the final reward
        """
        self.use_percentage = use_percentage
        self.transaction_cost = transaction_cost
        self.scale_factor = scale_factor
        
    def __call__(self, state: Dict[str, Any], action: int, 
                next_state: Dict[str, Any], info: Dict[str, Any]) -> float:
        """Calculate PnL-based reward.
        
        Args:
            state: Current state dictionary
            action: Action taken by the agent
            next_state: Next state dictionary
            info: Additional information from the environment
            
        Returns:
            float: Calculated reward
        """
        # Extract PnL from info dictionary provided by environment
        pnl = info.get('realized_pnl', 0.0)
        
        # If action is buy/sell, apply transaction cost
        if action in [1, 2]:  # Assuming 1=buy, 2=sell
            pnl -= self.transaction_cost
            
        # Convert to percentage return if required
        if self.use_percentage and 'portfolio_value' in info:
            portfolio_value = max(info['portfolio_value'], 1e-8)  # Avoid division by zero
            pnl = pnl / portfolio_value
                
        return pnl * self.scale_factor


class SharpeReward(RewardFunction):
    """Risk-adjusted reward using Sharpe ratio.
    
    This reward function calculates rewards based on the Sharpe ratio,
    which measures the excess return per unit of total risk (volatility).
    """
    
    def __init__(self, window_size: int = 100, risk_free_rate: float = 0.0, 
                min_observations: int = 10, scaling: float = 1.0):
        """Initialize the Sharpe ratio reward function.
        
        Args:
            window_size: Number of returns to consider for calculation
            risk_free_rate: Risk-free rate to use in Sharpe calculation
            min_observations: Minimum number of observations before using Sharpe
            scaling: Scaling factor for the reward
        """
        self.window_size = window_size
        self.risk_free_rate = risk_free_rate
        self.min_observations = min_observations
        self.scaling = scaling
        self.returns = []
        
    def __call__(self, state: Dict[str, Any], action: int, 
                next_state: Dict[str, Any], info: Dict[str, Any]) -> float:
        """Calculate Sharpe ratio-based reward.
        
        Args:
            state: Current state dictionary
            action: Action taken by the agent
            next_state: Next state dictionary
            info: Additional information from the environment
            
        Returns:
            float: Calculated reward
        """
        # Extract return from info
        ret = info.get('return', 0.0)
        
        # Add to returns history
        self.returns.append(ret)
        if len(self.returns) > self.window_size:
            self.returns.pop(0)
            
        # If we don't have enough observations, return the raw return
        if len(self.returns) < self.min_observations:
            return ret
            
        # Calculate Sharpe ratio
        returns_array = np.array(self.returns)
        mean_return = np.mean(returns_array)
        std_return = np.std(returns_array)
        
        # Avoid division by zero
        if std_return <= 1e-8:
            return 0.0
            
        sharpe = (mean_return - self.risk_free_rate) / std_return
        
        # Scale and return
        return sharpe * self.scaling
    
    def reset(self) -> None:
        """Reset returns history."""
        self.returns = []


class SortinoReward(RewardFunction):
    """Risk-adjusted reward using Sortino ratio (penalizing only downside deviation).
    
    This reward function calculates rewards based on the Sortino ratio,
    which measures the excess return per unit of downside risk.
    """
    
    def __init__(self, window_size: int = 100, risk_free_rate: float = 0.0,
                min_observations: int = 10, scaling: float = 1.0,
                target_return: Optional[float] = None):
        """Initialize the Sortino ratio reward function.
        
        Args:
            window_size: Number of returns to consider for calculation
            risk_free_rate: Risk-free rate to use in Sortino calculation
            min_observations: Minimum number of observations before using Sortino
            scaling: Scaling factor for the reward
            target_return: Target return for downside deviation calculation
                          (defaults to risk_free_rate if None)
        """
        self.window_size = window_size
        self.risk_free_rate = risk_free_rate
        self.min_observations = min_observations
        self.scaling = scaling
        self.target_return = target_return if target_return is not None else risk_free_rate
        self.returns = []
        
    def __call__(self, state: Dict[str, Any], action: int, 
                next_state: Dict[str, Any], info: Dict[str, Any]) -> float:
        """Calculate Sortino ratio-based reward.
        
        Args:
            state: Current state dictionary
            action: Action taken by the agent
            next_state: Next state dictionary
            info: Additional information from the environment
            
        Returns:
            float: Calculated reward
        """
        # Extract return from info
        ret = info.get('return', 0.0)
        
        # Add to returns history
        self.returns.append(ret)
        if len(self.returns) > self.window_size:
            self.returns.pop(0)
            
        # If we don't have enough observations, return the raw return
        if len(self.returns) < self.min_observations:
            return ret
            
        # Calculate Sortino ratio
        returns_array = np.array(self.returns)
        mean_return = np.mean(returns_array)
        
        # Calculate downside deviation (only negative returns relative to target)
        downside_returns = returns_array[returns_array < self.target_return] - self.target_return
        
        # If no downside returns, return a high value (but finite)
        if len(downside_returns) == 0:
            return 10.0 * self.scaling
            
        downside_deviation = np.sqrt(np.mean(downside_returns**2))
        
        # Avoid division by zero
        if downside_deviation <= 1e-8:
            return 0.0
            
        sortino = (mean_return - self.risk_free_rate) / downside_deviation
        
        # Scale and return
        return sortino * self.scaling
    
    def reset(self) -> None:
        """Reset returns history."""
        self.returns = []


class DrawdownPenaltyReward(RewardFunction):
    """Reward with penalties for drawdowns.
    
    This reward function wraps another reward function and applies
    penalties based on the current drawdown from peak portfolio value.
    """
    
    def __init__(self, base_reward: RewardFunction, 
                max_drawdown_penalty: float = 2.0,
                drawdown_exponent: float = 1.5):
        """Initialize the drawdown penalty reward function.
        
        Args:
            base_reward: Base reward function to wrap
            max_drawdown_penalty: Maximum penalty to apply for drawdowns
            drawdown_exponent: Exponent to apply to drawdown for non-linear scaling
        """
        self.base_reward = base_reward
        self.max_drawdown_penalty = max_drawdown_penalty
        self.drawdown_exponent = drawdown_exponent
        self.peak = 0.0
        
    def __call__(self, state: Dict[str, Any], action: int, 
                next_state: Dict[str, Any], info: Dict[str, Any]) -> float:
        """Calculate reward with drawdown penalties.
        
        Args:
            state: Current state dictionary
            action: Action taken by the agent
            next_state: Next state dictionary
            info: Additional information from the environment
            
        Returns:
            float: Calculated reward
        """
        # Get base reward
        reward = self.base_reward(state, action, next_state, info)
        
        # Extract portfolio value
        portfolio_value = info.get('portfolio_value', 0.0)
        
        # Update peak
        if portfolio_value > self.peak:
            self.peak = portfolio_value
        
        # Calculate drawdown
        if self.peak > 0:
            drawdown = max(0, (self.peak - portfolio_value) / self.peak)
            
            # Apply penalty (non-linear scaling of drawdown)
            penalty = self.max_drawdown_penalty * (drawdown ** self.drawdown_exponent)
            reward -= penalty
        
        return reward
    
    def reset(self) -> None:
        """Reset drawdown tracking and base reward."""
        self.peak = 0.0
        self.base_reward.reset()


class MultiObjectiveReward(RewardFunction):
    """Combines multiple reward functions with weights.
    
    This reward function allows combining multiple reward functions
    with different weights to create a composite reward.
    """
    
    def __init__(self, reward_functions: List[RewardFunction], 
                weights: List[float]):
        """Initialize the multi-objective reward function.
        
        Args:
            reward_functions: List of reward functions to combine
            weights: List of weights for each reward function
        """
        assert len(reward_functions) == len(weights), "Reward functions and weights must have the same length"
        self.reward_functions = reward_functions
        self.weights = weights
        
    def __call__(self, state: Dict[str, Any], action: int, 
                next_state: Dict[str, Any], info: Dict[str, Any]) -> float:
        """Calculate weighted sum of rewards.
        
        Args:
            state: Current state dictionary
            action: Action taken by the agent
            next_state: Next state dictionary
            info: Additional information from the environment
            
        Returns:
            float: Calculated reward
        """
        # Calculate weighted sum of rewards
        reward = 0.0
        for func, weight in zip(self.reward_functions, self.weights):
            reward += weight * func(state, action, next_state, info)
        return reward
    
    def reset(self) -> None:
        """Reset all component reward functions."""
        for func in self.reward_functions:
            func.reset()


class RewardFactory:
    """Factory to create reward functions based on configuration.
    
    This factory class allows creating reward functions from configuration
    dictionaries, making it easy to experiment with different reward functions.
    """
    
    @staticmethod
    def create(config: Dict[str, Any]) -> RewardFunction:
        """Create a reward function from configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            RewardFunction: Created reward function
            
        Raises:
            ValueError: If an unknown reward type is specified
        """
        reward_type = config.get('type', 'pnl')
        
        if reward_type == 'pnl':
            return PnLReward(
                use_percentage=config.get('use_percentage', True),
                transaction_cost=config.get('transaction_cost', 0.0001),
                scale_factor=config.get('scale_factor', 1.0)
            )
        elif reward_type == 'sharpe':
            return SharpeReward(
                window_size=config.get('window_size', 100),
                risk_free_rate=config.get('risk_free_rate', 0.0),
                min_observations=config.get('min_observations', 10),
                scaling=config.get('scaling', 1.0)
            )
        elif reward_type == 'sortino':
            return SortinoReward(
                window_size=config.get('window_size', 100),
                risk_free_rate=config.get('risk_free_rate', 0.0),
                min_observations=config.get('min_observations', 10),
                scaling=config.get('scaling', 1.0),
                target_return=config.get('target_return', None)
            )
        elif reward_type == 'drawdown':
            base_reward_config = config.get('base_reward', {'type': 'pnl'})
            base_reward = RewardFactory.create(base_reward_config)
            return DrawdownPenaltyReward(
                base_reward=base_reward,
                max_drawdown_penalty=config.get('max_drawdown_penalty', 2.0),
                drawdown_exponent=config.get('drawdown_exponent', 1.5)
            )
        elif reward_type == 'multi':
            reward_configs = config.get('rewards', [])
            weights = config.get('weights', [1.0] * len(reward_configs))
            reward_functions = [RewardFactory.create(cfg) for cfg in reward_configs]
            return MultiObjectiveReward(reward_functions, weights)
        else:
            raise ValueError(f"Unknown reward type: {reward_type}") 