"""
Unit tests for reward functions.
"""

import unittest
import numpy as np
import sys
import os

# Add the parent directory to the path to import the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from reward_functions import (
    RewardFunction, PnLReward, SharpeReward, SortinoReward,
    DrawdownPenaltyReward, MultiObjectiveReward, RewardFactory
)


class TestPnLReward(unittest.TestCase):
    """Test cases for the PnL reward function."""
    
    def test_absolute_pnl(self):
        """Test PnL reward with absolute returns."""
        reward_func = PnLReward(use_percentage=False, transaction_cost=0.001, scale_factor=2.0)
        
        # Simple case with profit
        state, next_state = {}, {}
        action = 1  # Buy
        info = {'realized_pnl': 0.05}
        
        reward = reward_func(state, action, next_state, info)
        
        # Expected: (0.05 - 0.001) * 2.0 = 0.098
        self.assertAlmostEqual(reward, 0.098, places=6)
        
        # Case with loss
        info = {'realized_pnl': -0.02}
        reward = reward_func(state, action, next_state, info)
        
        # Expected: (-0.02 - 0.001) * 2.0 = -0.042
        self.assertAlmostEqual(reward, -0.042, places=6)
        
        # No transaction cost for hold action
        action = 0  # Hold
        info = {'realized_pnl': 0.01}
        reward = reward_func(state, action, next_state, info)
        
        # Expected: 0.01 * 2.0 = 0.02
        self.assertAlmostEqual(reward, 0.02, places=6)
    
    def test_percentage_pnl(self):
        """Test PnL reward with percentage returns."""
        reward_func = PnLReward(use_percentage=True, transaction_cost=0.001, scale_factor=1.0)
        
        # Simple case with profit
        state, next_state = {}, {}
        action = 2  # Sell
        info = {'realized_pnl': 0.05, 'portfolio_value': 1000}
        
        reward = reward_func(state, action, next_state, info)
        
        # Expected: (0.05 - 0.001) / 1000 = 0.000049
        self.assertAlmostEqual(reward, 0.000049, places=6)
        
        # Test with zero portfolio value (should avoid division by zero)
        info = {'realized_pnl': 0.05, 'portfolio_value': 0}
        reward = reward_func(state, action, next_state, info)
        
        # Expected: (0.05 - 0.001) / 1e-8 (small value to avoid division by zero)
        self.assertGreater(reward, 0)  # Should be a large positive number
        
        # Test without portfolio value (should fall back to absolute)
        info = {'realized_pnl': 0.05}
        reward = reward_func(state, action, next_state, info)
        
        # Expected: (0.05 - 0.001) = 0.049
        self.assertAlmostEqual(reward, 0.049, places=6)


class TestSharpeReward(unittest.TestCase):
    """Test cases for the Sharpe reward function."""
    
    def test_few_observations(self):
        """Test with fewer than min_observations returns."""
        reward_func = SharpeReward(window_size=5, min_observations=3)
        
        # First returns should pass through directly
        state, action, next_state = {}, 0, {}
        
        for ret in [0.01, 0.02]:
            info = {'return': ret}
            reward = reward_func(state, action, next_state, info)
            self.assertEqual(reward, ret)
    
    def test_sharpe_calculation(self):
        """Test Sharpe ratio calculation with many returns."""
        reward_func = SharpeReward(window_size=5, min_observations=3, risk_free_rate=0.001, scaling=2.0)
        
        # Add returns and calculate expected Sharpe ratio
        state, action, next_state = {}, 0, {}
        returns = [0.01, 0.02, 0.03, -0.01, 0.02]
        
        # First two returns should pass through
        for i, ret in enumerate(returns[:2]):
            info = {'return': ret}
            reward = reward_func(state, action, next_state, info)
            self.assertEqual(reward, ret)
        
        # From third return onwards, should calculate Sharpe
        window_returns = []
        for i, ret in enumerate(returns[2:], 2):
            window_returns.append(returns[i-2])
            window_returns.append(returns[i-1])
            window_returns.append(ret)
            window_returns = window_returns[-5:]  # Keep only window_size items
            
            info = {'return': ret}
            reward = reward_func(state, action, next_state, info)
            
            # Calculate expected Sharpe
            mean_return = np.mean(window_returns)
            std_return = np.std(window_returns)
            expected_sharpe = (mean_return - 0.001) / std_return * 2.0 if std_return > 0 else 0.0
            
            self.assertAlmostEqual(reward, expected_sharpe, places=6)
    
    def test_zero_std(self):
        """Test Sharpe ratio with zero standard deviation."""
        reward_func = SharpeReward(window_size=3, min_observations=3)
        
        # Add identical returns (zero standard deviation)
        state, action, next_state = {}, 0, {}
        
        for _ in range(3):
            info = {'return': 0.02}
            reward_func(state, action, next_state, info)
        
        # All returns are 0.02, so std = 0
        info = {'return': 0.02}
        reward = reward_func(state, action, next_state, info)
        
        # Expected Sharpe: 0 due to division by zero protection
        self.assertEqual(reward, 0.0)
    
    def test_reset(self):
        """Test that reset clears the returns history."""
        reward_func = SharpeReward(window_size=3, min_observations=2)
        
        # Add some returns
        state, action, next_state = {}, 0, {}
        
        for ret in [0.01, 0.02, 0.03]:
            info = {'return': ret}
            reward_func(state, action, next_state, info)
        
        # Check that we have returns
        self.assertEqual(len(reward_func.returns), 3)
        
        # Reset and check that returns are cleared
        reward_func.reset()
        self.assertEqual(len(reward_func.returns), 0)
        
        # After reset, first return should pass through
        info = {'return': 0.01}
        reward = reward_func(state, action, next_state, info)
        self.assertEqual(reward, 0.01)


class TestSortinoReward(unittest.TestCase):
    """Test cases for the Sortino reward function."""
    
    def test_few_observations(self):
        """Test with fewer than min_observations returns."""
        reward_func = SortinoReward(window_size=5, min_observations=3)
        
        # First returns should pass through directly
        state, action, next_state = {}, 0, {}
        
        for ret in [0.01, 0.02]:
            info = {'return': ret}
            reward = reward_func(state, action, next_state, info)
            self.assertEqual(reward, ret)
    
    def test_sortino_calculation(self):
        """Test Sortino ratio calculation with mixed returns."""
        reward_func = SortinoReward(window_size=5, min_observations=3, risk_free_rate=0.0, scaling=1.0)
        
        # Add returns with some below target (0.0)
        state, action, next_state = {}, 0, {}
        returns = [0.01, 0.02, 0.03, -0.01, -0.02]
        
        # Process returns
        for ret in returns:
            info = {'return': ret}
            reward_func(state, action, next_state, info)
        
        # For test purposes, directly calculate Sortino ratio
        mean_return = np.mean(returns)
        downside_returns = np.array([r for r in returns if r < 0])
        downside_deviation = np.sqrt(np.mean(downside_returns**2))
        expected_sortino = mean_return / downside_deviation
        
        # Add one more return and test
        info = {'return': 0.01}
        reward = reward_func(state, action, next_state, info)
        
        # Last return will change the window, so we need to recalculate
        current_returns = returns[1:] + [0.01]  # Sliding window
        mean_return = np.mean(current_returns)
        downside_returns = np.array([r for r in current_returns if r < 0])
        downside_deviation = np.sqrt(np.mean(downside_returns**2))
        expected_sortino = mean_return / downside_deviation
        
        self.assertAlmostEqual(reward, expected_sortino, places=6)
    
    def test_no_downside(self):
        """Test Sortino ratio with no downside returns."""
        reward_func = SortinoReward(window_size=3, min_observations=3, scaling=2.0)
        
        # Add all positive returns (no downside)
        state, action, next_state = {}, 0, {}
        
        for ret in [0.01, 0.02, 0.03]:
            info = {'return': ret}
            reward_func(state, action, next_state, info)
        
        # All returns are positive, so no downside
        info = {'return': 0.04}
        reward = reward_func(state, action, next_state, info)
        
        # Expected Sortino: 10.0 * scaling (high but finite value for no downside)
        self.assertEqual(reward, 20.0)  # 10.0 * 2.0
    
    def test_custom_target(self):
        """Test Sortino with custom target return."""
        reward_func = SortinoReward(window_size=5, min_observations=3, target_return=0.02)
        
        # Add returns with some below target (0.02)
        state, action, next_state = {}, 0, {}
        returns = [0.01, 0.03, 0.02, 0.01, 0.03]
        
        # Process returns
        for ret in returns:
            info = {'return': ret}
            reward_func(state, action, next_state, info)
        
        # For test purposes, directly calculate Sortino ratio with target 0.02
        mean_return = np.mean(returns)
        downside_returns = np.array([r - 0.02 for r in returns if r < 0.02])
        downside_deviation = np.sqrt(np.mean(downside_returns**2))
        expected_sortino = mean_return / downside_deviation
        
        # Add one more return and test
        info = {'return': 0.01}
        reward = reward_func(state, action, next_state, info)
        
        # Last return will change the window, so we need to recalculate
        current_returns = returns[1:] + [0.01]  # Sliding window
        mean_return = np.mean(current_returns)
        downside_returns = np.array([r - 0.02 for r in current_returns if r < 0.02])
        downside_deviation = np.sqrt(np.mean(downside_returns**2))
        expected_sortino = mean_return / downside_deviation
        
        self.assertAlmostEqual(reward, expected_sortino, places=6)


class TestDrawdownPenaltyReward(unittest.TestCase):
    """Test cases for the drawdown penalty reward function."""
    
    def test_no_drawdown(self):
        """Test with continuously increasing portfolio value."""
        base_reward = PnLReward(use_percentage=False)
        reward_func = DrawdownPenaltyReward(base_reward, max_drawdown_penalty=2.0, drawdown_exponent=1.5)
        
        # Series of increasing portfolio values
        state, action, next_state = {}, 0, {}
        portfolio_values = [1000, 1100, 1200, 1300]
        
        for i, val in enumerate(portfolio_values):
            info = {'realized_pnl': 0.05, 'portfolio_value': val}
            reward = reward_func(state, action, next_state, info)
            
            # No drawdown, so reward should be the base reward
            self.assertEqual(reward, 0.05)
            
            # Check that peak is updated correctly
            self.assertEqual(reward_func.peak, val)
    
    def test_with_drawdown(self):
        """Test with portfolio drawdown."""
        base_reward = PnLReward(use_percentage=False)
        reward_func = DrawdownPenaltyReward(base_reward, max_drawdown_penalty=2.0, drawdown_exponent=1.5)
        
        # Series with a drawdown
        state, action, next_state = {}, 0, {}
        
        # First set a peak
        info = {'realized_pnl': 0.05, 'portfolio_value': 1000}
        reward = reward_func(state, action, next_state, info)
        self.assertEqual(reward, 0.05)
        
        # Now a drawdown
        info = {'realized_pnl': 0.02, 'portfolio_value': 800}
        reward = reward_func(state, action, next_state, info)
        
        # Drawdown is (1000 - 800) / 1000 = 0.2
        # Penalty is 2.0 * (0.2 ** 1.5) ≈ 0.179
        # Expected reward: 0.02 - 0.179 ≈ -0.159
        self.assertAlmostEqual(reward, -0.159, places=3)
        
        # Peak should still be 1000
        self.assertEqual(reward_func.peak, 1000)
        
        # New peak
        info = {'realized_pnl': 0.03, 'portfolio_value': 1200}
        reward = reward_func(state, action, next_state, info)
        self.assertEqual(reward, 0.03)
        self.assertEqual(reward_func.peak, 1200)
    
    def test_reset(self):
        """Test that reset clears the peak."""
        base_reward = PnLReward(use_percentage=False)
        reward_func = DrawdownPenaltyReward(base_reward, max_drawdown_penalty=2.0, drawdown_exponent=1.5)
        
        # Set a peak
        state, action, next_state = {}, 0, {}
        info = {'realized_pnl': 0.05, 'portfolio_value': 1000}
        reward_func(state, action, next_state, info)
        self.assertEqual(reward_func.peak, 1000)
        
        # Reset
        reward_func.reset()
        self.assertEqual(reward_func.peak, 0.0)
        
        # After reset, should set a new peak
        info = {'realized_pnl': 0.03, 'portfolio_value': 800}
        reward = reward_func(state, action, next_state, info)
        self.assertEqual(reward, 0.03)
        self.assertEqual(reward_func.peak, 800)


class TestMultiObjectiveReward(unittest.TestCase):
    """Test cases for the multi-objective reward function."""
    
    def test_weighted_combination(self):
        """Test weighted combination of multiple reward functions."""
        reward1 = PnLReward(use_percentage=False)
        reward2 = SharpeReward(window_size=3, min_observations=1)
        
        # Create multi-objective reward with different weights
        weights = [0.7, 0.3]
        reward_func = MultiObjectiveReward([reward1, reward2], weights)
        
        # Test with some values
        state, action, next_state = {}, 0, {}
        info = {'realized_pnl': 0.05, 'return': 0.02}
        
        # First call, Sharpe will just return the raw return
        reward = reward_func(state, action, next_state, info)
        
        # Expected: 0.7 * 0.05 + 0.3 * 0.02 = 0.041
        self.assertAlmostEqual(reward, 0.041, places=6)
        
        # Add more returns to build Sharpe history
        for _ in range(2):
            reward_func(state, action, next_state, info)
        
        # Directly calculate Sharpe for test
        sharpe = 0.02 / 0.0  # Mean / std, but std = 0 as all returns are 0.02
        
        # Sharpe will be 0 due to zero std protection
        info = {'realized_pnl': 0.05, 'return': 0.02}
        reward = reward_func(state, action, next_state, info)
        
        # Expected: 0.7 * 0.05 + 0.3 * 0 = 0.035
        self.assertAlmostEqual(reward, 0.035, places=6)
    
    def test_reset(self):
        """Test that reset propagates to all component rewards."""
        reward1 = SharpeReward(window_size=3, min_observations=1)
        reward2 = SortinoReward(window_size=3, min_observations=1)
        
        # Create multi-objective reward
        reward_func = MultiObjectiveReward([reward1, reward2], [0.5, 0.5])
        
        # Add some returns
        state, action, next_state = {}, 0, {}
        for _ in range(3):
            info = {'return': 0.02}
            reward_func(state, action, next_state, info)
        
        # Check that both functions have returns
        self.assertEqual(len(reward1.returns), 3)
        self.assertEqual(len(reward2.returns), 3)
        
        # Reset and check that both are cleared
        reward_func.reset()
        self.assertEqual(len(reward1.returns), 0)
        self.assertEqual(len(reward2.returns), 0)


class TestRewardFactory(unittest.TestCase):
    """Test cases for the reward factory."""
    
    def test_pnl_reward(self):
        """Test creating a PnL reward."""
        config = {
            'type': 'pnl',
            'use_percentage': True,
            'transaction_cost': 0.002,
            'scale_factor': 1.5
        }
        
        reward = RewardFactory.create(config)
        
        self.assertIsInstance(reward, PnLReward)
        self.assertEqual(reward.use_percentage, True)
        self.assertEqual(reward.transaction_cost, 0.002)
        self.assertEqual(reward.scale_factor, 1.5)
    
    def test_sharpe_reward(self):
        """Test creating a Sharpe reward."""
        config = {
            'type': 'sharpe',
            'window_size': 50,
            'risk_free_rate': 0.001,
            'min_observations': 5,
            'scaling': 2.0
        }
        
        reward = RewardFactory.create(config)
        
        self.assertIsInstance(reward, SharpeReward)
        self.assertEqual(reward.window_size, 50)
        self.assertEqual(reward.risk_free_rate, 0.001)
        self.assertEqual(reward.min_observations, 5)
        self.assertEqual(reward.scaling, 2.0)
    
    def test_sortino_reward(self):
        """Test creating a Sortino reward."""
        config = {
            'type': 'sortino',
            'window_size': 50,
            'risk_free_rate': 0.001,
            'min_observations': 5,
            'scaling': 2.0,
            'target_return': 0.002
        }
        
        reward = RewardFactory.create(config)
        
        self.assertIsInstance(reward, SortinoReward)
        self.assertEqual(reward.window_size, 50)
        self.assertEqual(reward.risk_free_rate, 0.001)
        self.assertEqual(reward.min_observations, 5)
        self.assertEqual(reward.scaling, 2.0)
        self.assertEqual(reward.target_return, 0.002)
    
    def test_drawdown_reward(self):
        """Test creating a drawdown penalty reward."""
        config = {
            'type': 'drawdown',
            'base_reward': {
                'type': 'pnl',
                'use_percentage': True
            },
            'max_drawdown_penalty': 3.0,
            'drawdown_exponent': 2.0
        }
        
        reward = RewardFactory.create(config)
        
        self.assertIsInstance(reward, DrawdownPenaltyReward)
        self.assertIsInstance(reward.base_reward, PnLReward)
        self.assertEqual(reward.base_reward.use_percentage, True)
        self.assertEqual(reward.max_drawdown_penalty, 3.0)
        self.assertEqual(reward.drawdown_exponent, 2.0)
    
    def test_multi_reward(self):
        """Test creating a multi-objective reward."""
        config = {
            'type': 'multi',
            'rewards': [
                {'type': 'pnl', 'use_percentage': True},
                {'type': 'sortino', 'window_size': 50}
            ],
            'weights': [0.6, 0.4]
        }
        
        reward = RewardFactory.create(config)
        
        self.assertIsInstance(reward, MultiObjectiveReward)
        self.assertEqual(len(reward.reward_functions), 2)
        self.assertIsInstance(reward.reward_functions[0], PnLReward)
        self.assertIsInstance(reward.reward_functions[1], SortinoReward)
        self.assertEqual(reward.weights, [0.6, 0.4])
    
    def test_unknown_type(self):
        """Test error on unknown reward type."""
        config = {
            'type': 'unknown'
        }
        
        with self.assertRaises(ValueError):
            RewardFactory.create(config)


if __name__ == '__main__':
    unittest.main() 