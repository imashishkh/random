"""
Test script for ForexTradingEnv.

This script demonstrates how to use the ForexTradingEnv
and validates its functionality.
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from gymnasium.wrappers import RecordEpisodeStatistics

# Add the project root to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from .environments.forex_trading_env import ForexTradingEnv

def load_sample_data():
    """
    Load or generate sample forex data for testing.
    
    Returns:
        pd.DataFrame: Sample OHLCV data
    """
    try:
        # Try to load existing data if available
        from src.data_manager.loader import DataLoader
        loader = DataLoader()
        data = loader.load_forex_data('EUR_USD', '1h', start_date='2022-01-01', end_date='2022-03-01')
        return data
    except (ImportError, Exception) as e:
        print(f"Could not load real data, generating synthetic data: {e}")
        
        # Generate synthetic data
        np.random.seed(42)
        n_points = 1000
        dates = pd.date_range(start='2022-01-01', periods=n_points, freq='H')
        
        # Start with a base price and apply random walk
        close = np.random.normal(0, 0.0005, n_points).cumsum() + 1.2
        
        # Generate other OHLCV data based on close
        data = pd.DataFrame({
            'timestamp': dates,
            'open': close + np.random.normal(0, 0.0003, n_points),
            'high': close + np.abs(np.random.normal(0, 0.001, n_points)),
            'low': close - np.abs(np.random.normal(0, 0.001, n_points)),
            'close': close,
            'volume': np.random.lognormal(10, 1, n_points)
        })
        
        # Ensure high is always >= close >= low
        data['high'] = np.maximum(data['high'], np.maximum(data['open'], data['close']))
        data['low'] = np.minimum(data['low'], np.minimum(data['open'], data['close']))
        
        # Set the timestamp as index
        data.set_index('timestamp', inplace=True)
        
        return data

def test_env_creation():
    """Test basic environment creation and reset."""
    data = load_sample_data()
    
    env = ForexTradingEnv(
        df=data,
        window_size=20,
        leverage=50.0,
        commission=0.0001,
        spread=0.0001,
        technical_indicators=['sma_20', 'rsi_14', 'macd_12_26_9']
    )
    
    print(f"Observation Space: {env.observation_space}")
    print(f"Action Space: {env.action_space}")
    
    obs, info = env.reset(seed=42)
    print(f"Observation shape: {obs.shape}")
    print(f"Info: {info}")
    
    return env

def test_env_step(env, num_steps=100):
    """Test environment stepping and action handling."""
    env.reset(seed=42)
    
    # Storage for metrics
    portfolio_values = []
    positions = []
    rewards = []
    
    # Take random actions
    for i in range(num_steps):
        # Random action between -1 and 1
        action = np.array([np.random.uniform(-1, 1)])
        
        obs, reward, terminated, truncated, info = env.step(action)
        
        portfolio_values.append(info['portfolio_value'])
        positions.append(info['position'])
        rewards.append(reward)
        
        print(f"Step {i}: Action={action[0]:.4f}, Position={info['position']:.4f}, "
              f"PnL=${info['unrealized_pnl']:.2f}, Reward={reward:.4f}")
        
        if terminated or truncated:
            print(f"Episode ended after {i+1} steps")
            break
    
    # Plot results
    plt.figure(figsize=(12, 8))
    
    plt.subplot(3, 1, 1)
    plt.plot(portfolio_values)
    plt.title('Portfolio Value')
    plt.grid(True)
    
    plt.subplot(3, 1, 2)
    plt.plot(positions)
    plt.title('Position')
    plt.grid(True)
    
    plt.subplot(3, 1, 3)
    plt.plot(rewards)
    plt.title('Rewards')
    plt.grid(True)
    
    plt.tight_layout()
    plt.savefig('forex_env_test_results.png')
    plt.close()
    
    return portfolio_values, positions, rewards

def test_normalization():
    """Test the observation normalization."""
    data = load_sample_data()
    
    env = ForexTradingEnv(
        df=data,
        window_size=20,
        technical_indicators=['sma_20', 'rsi_14']
    )
    
    obs, _ = env.reset(seed=42)
    
    # Check if observation values are mostly within a reasonable range (-10 to 10)
    # after normalization (excluding potential outliers)
    flat_obs = obs.flatten()
    non_outliers = flat_obs[(flat_obs > -10) & (flat_obs < 10)]
    
    print(f"Observation statistics:")
    print(f"  Min: {np.min(flat_obs):.4f}")
    print(f"  Max: {np.max(flat_obs):.4f}")
    print(f"  Mean: {np.mean(flat_obs):.4f}")
    print(f"  Std: {np.std(flat_obs):.4f}")
    print(f"  % within [-10, 10]: {len(non_outliers) / len(flat_obs) * 100:.2f}%")
    
    return len(non_outliers) / len(flat_obs) >= 0.95  # At least 95% should be in reasonable range

def test_reward_functions():
    """Test different reward functions."""
    data = load_sample_data()
    
    # Test different reward types
    reward_types = ['profit', 'sharpe', 'sortino']
    rewards_by_type = {}
    
    for reward_type in reward_types:
        env = ForexTradingEnv(
            df=data,
            window_size=20,
            reward_type=reward_type
        )
        
        env = RecordEpisodeStatistics(env)
        env.reset(seed=42)
        
        rewards = []
        
        # Take random actions for 100 steps
        for _ in range(100):
            action = np.array([np.random.uniform(-1, 1)])
            _, reward, terminated, truncated, _ = env.step(action)
            rewards.append(reward)
            
            if terminated or truncated:
                break
        
        rewards_by_type[reward_type] = rewards
        print(f"Reward type: {reward_type}")
        print(f"  Min: {np.min(rewards):.6f}")
        print(f"  Max: {np.max(rewards):.6f}")
        print(f"  Mean: {np.mean(rewards):.6f}")
        print(f"  Std: {np.std(rewards):.6f}")
    
    # Plot reward comparisons
    plt.figure(figsize=(12, 6))
    
    for reward_type, rewards in rewards_by_type.items():
        plt.plot(rewards, label=reward_type)
    
    plt.title('Comparison of Reward Functions')
    plt.xlabel('Step')
    plt.ylabel('Reward')
    plt.legend()
    plt.grid(True)
    
    plt.savefig('forex_env_reward_comparison.png')
    plt.close()
    
    return rewards_by_type

def run_all_tests():
    """Run all test functions."""
    print("Testing environment creation...")
    env = test_env_creation()
    
    print("\nTesting environment step...")
    portfolio_values, positions, rewards = test_env_step(env)
    
    print("\nTesting observation normalization...")
    normalization_ok = test_normalization()
    print(f"Normalization test passed: {normalization_ok}")
    
    print("\nTesting reward functions...")
    rewards_by_type = test_reward_functions()
    
    print("\nAll tests completed!")

if __name__ == "__main__":
    run_all_tests() 