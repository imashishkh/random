from typing import Dict, List, Optional, Union, Any, Callable
import gymnasium as gym
import numpy as np
import pandas as pd
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecNormalize

from .environments.crypto_trading_env import CryptoTradingEnv


def make_env(
    price_data: pd.DataFrame,
    initial_balance: float = 10000.0,
    transaction_fee: float = 0.001,
    slippage: float = 0.0005,
    window_size: int = 24,
    reward_function: str = "sharpe",
    action_type: str = "discrete",
    max_position: float = 1.0,
    seed: Optional[int] = None,
) -> Callable[[], gym.Env]:
    """
    Create a callable function that will create and return a crypto trading environment.
    
    Args:
        price_data: Historical price data with OHLCV columns
        initial_balance: Starting account balance in quote currency
        transaction_fee: Fee per transaction as a fraction
        slippage: Average slippage per trade as a fraction
        window_size: Number of time steps to include in the state
        reward_function: Method to calculate reward ('simple' or 'sharpe')
        action_type: Type of action space ('discrete' or 'continuous')
        max_position: Maximum position size as a fraction of balance
        seed: Random seed for the environment
        
    Returns:
        A callable that creates and returns a crypto trading environment
    """
    def _init() -> gym.Env:
        env = CryptoTradingEnv(
            price_data=price_data,
            initial_balance=initial_balance,
            transaction_fee=transaction_fee,
            slippage=slippage,
            window_size=window_size,
            reward_function=reward_function,
            action_type=action_type,
            max_position=max_position,
        )
        env.reset(seed=seed)
        return env
    
    return _init


def create_env(
    price_data: pd.DataFrame,
    n_envs: int = 1,
    use_subproc: bool = False,
    normalize: bool = True,
    **env_kwargs
) -> gym.Env:
    """
    Create a vectorized environment for parallel training.
    
    Args:
        price_data: Historical price data with OHLCV columns
        n_envs: Number of environments to run in parallel
        use_subproc: Whether to use SubprocVecEnv (for true parallelism)
        normalize: Whether to apply normalization to the observations and rewards
        **env_kwargs: Additional keyword arguments to pass to the environment
        
    Returns:
        A vectorized environment
    """
    # Create list of env creation functions
    env_fns = []
    for i in range(n_envs):
        # Use different seeds for each environment
        seed = env_kwargs.pop('seed', 0) + i if 'seed' in env_kwargs else i
        
        # Create a copy of the price data with small random variations
        # to ensure diversity across environments
        if n_envs > 1:
            # Add small noise to the price data (±0.1%)
            noise_factor = 0.001  # 0.1%
            noisy_data = price_data.copy()
            for col in ['open', 'high', 'low', 'close']:
                noise = np.random.normal(0, noise_factor, len(price_data))
                noise_multiplier = 1.0 + noise
                noisy_data[col] = price_data[col] * noise_multiplier
            
            # Ensure high >= low after adding noise
            noisy_data['high'] = np.maximum(noisy_data['high'], noisy_data['low'])
            
            # Volume can have more variation
            vol_noise = np.random.normal(0, noise_factor * 5, len(price_data))
            vol_multiplier = 1.0 + vol_noise
            noisy_data['volume'] = price_data['volume'] * vol_multiplier
            noisy_data['volume'] = np.maximum(noisy_data['volume'], 0)  # Ensure non-negative
            
            env_data = noisy_data
        else:
            env_data = price_data
        
        # Create environment function
        env_fn = make_env(
            price_data=env_data,
            seed=seed,
            **env_kwargs
        )
        env_fns.append(env_fn)
    
    # Create vectorized environment
    if use_subproc and n_envs > 1:
        vec_env = SubprocVecEnv(env_fns)
    else:
        vec_env = DummyVecEnv(env_fns)
    
    # Apply normalization if requested
    if normalize:
        vec_env = VecNormalize(
            vec_env,
            norm_obs=True,
            norm_reward=True,
            clip_obs=10.0,
            clip_reward=10.0,
            gamma=0.99,
        )
    
    return vec_env 