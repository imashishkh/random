"""
Test script for CryptoTradingEnv

This script demonstrates how to use the CryptoTradingEnv with random actions.
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import gymnasium as gym
from stable_baselines3.common.evaluation import evaluate_policy
from stable_baselines3.common.env_checker import check_env

# Add parent directory to sys.path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the environment
from environments.crypto_trading_env import CryptoTradingEnv


def generate_sample_data(n_samples=1000):
    """Generate sample OHLCV data for testing."""
    np.random.seed(42)
    
    # Initial price
    price = 100.0
    
    # Trend component
    trend = np.linspace(0, 0.2, n_samples)
    
    # Noise component
    noise = np.random.normal(0, 0.01, n_samples)
    
    # Volatility component (GARCH-like)
    volatility = np.zeros(n_samples)
    volatility[0] = 0.01
    for i in range(1, n_samples):
        volatility[i] = 0.9 * volatility[i-1] + 0.1 * abs(noise[i-1])
    
    # Calculate price path
    returns = noise * volatility + 0.0002 - 0.5 * volatility**2 + trend
    for i in range(1, n_samples):
        price = price * (1 + returns[i])
    
    # Generate price series
    prices = np.zeros(n_samples)
    prices[0] = price
    for i in range(1, n_samples):
        prices[i] = prices[i-1] * (1 + returns[i])
    
    # Generate OHLCV data
    dates = pd.date_range(start='2023-01-01', periods=n_samples, freq='H')
    
    # Create dataframe
    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices * (1 + np.random.normal(0, 0.002, n_samples)),
        'high': prices * (1 + np.abs(np.random.normal(0, 0.004, n_samples))),
        'low': prices * (1 - np.abs(np.random.normal(0, 0.004, n_samples))),
        'close': prices,
        'volume': np.random.lognormal(10, 1, n_samples)
    })
    
    # Ensure high is always the highest and low is always the lowest
    for i in range(n_samples):
        values = [df.loc[i, 'open'], df.loc[i, 'close']]
        df.loc[i, 'high'] = max(df.loc[i, 'high'], max(values))
        df.loc[i, 'low'] = min(df.loc[i, 'low'], min(values))
    
    return df


def test_random_actions(env, n_episodes=3, max_steps=100):
    """Test the environment with random actions."""
    
    for episode in range(n_episodes):
        obs, info = env.reset()
        total_reward = 0
        
        for step in range(max_steps):
            # Sample random action
            action = env.action_space.sample()
            
            # Step environment
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            
            # Render (if in human mode)
            env.render()
            
            if terminated or truncated:
                break
            
        print(f"Episode {episode+1}: Total Reward = {total_reward:.4f}, Final Portfolio Value = {info['portfolio_value']:.2f}")
    
    env.close()


def main():
    # Generate sample data
    print("Generating sample data...")
    df = generate_sample_data()
    
    # Define technical indicators to use
    tech_indicators = ['sma', 'rsi', 'macd', 'bbands']
    
    # Create environment
    print("Creating environment...")
    env = CryptoTradingEnv(
        df=df,
        initial_balance=10000.0,
        commission=0.001,
        window_size=20,
        reward_type='sharpe',
        action_type='discrete',
        technical_indicators=tech_indicators,
        render_mode='human'
    )
    
    # Check environment with SB3 env checker
    print("Checking environment compatibility with Gymnasium...")
    check_env(env, warn=True)
    
    # Test with random actions
    print("Testing environment with random actions...")
    test_random_actions(env)
    
    print("Test completed successfully!")


if __name__ == "__main__":
    main() 