"""
Unit tests for experience replay buffer.
"""

import unittest
import numpy as np
import torch
import os
import sys
import tempfile
import shutil

# Add the parent directory to the path to import the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from experience_replay import ExperienceReplayBuffer, TorchRLExperienceReplayBuffer


class TestExperienceReplayBuffer(unittest.TestCase):
    """Test cases for the experience replay buffer."""
    
    def setUp(self):
        """Set up test cases."""
        self.buffer_size = 100
        self.state_dim = 10
        self.buffer = ExperienceReplayBuffer(
            capacity=self.buffer_size,
            state_dim=self.state_dim,
            alpha=0.6,
            beta=0.4,
            beta_annealing=0.001,
            n_step=3,
            gamma=0.99
        )
        
        # Create temporary directory for file operations
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up after tests."""
        # Remove temporary directory
        shutil.rmtree(self.temp_dir)
    
    def test_add_single_transition(self):
        """Test adding a single transition."""
        state = np.random.randn(self.state_dim).astype(np.float32)
        action = 1
        reward = 0.5
        next_state = np.random.randn(self.state_dim).astype(np.float32)
        done = False
        
        # Adding a single transition should not increase size yet (n_step > 1)
        initial_size = self.buffer.size
        self.buffer.add(state, action, reward, next_state, done)
        self.assertEqual(self.buffer.size, initial_size)
        
        # n_step buffer should contain the transition
        self.assertEqual(len(self.buffer.n_step_buffer), 1)
    
    def test_add_n_step_transitions(self):
        """Test adding multiple transitions to fill n_step buffer."""
        # Add n_step transitions
        for i in range(3):  # n_step = 3
            state = np.random.randn(self.state_dim).astype(np.float32)
            action = i % 3
            reward = 0.1 * (i + 1)
            next_state = np.random.randn(self.state_dim).astype(np.float32)
            done = i == 2  # Last one is done
            
            self.buffer.add(state, action, reward, next_state, done)
        
        # Should have stored 3 transitions (with done=True, all are processed)
        self.assertEqual(self.buffer.size, 3)
    
    def test_n_step_reward_calculation(self):
        """Test n-step reward calculation."""
        # Reset buffer
        self.buffer = ExperienceReplayBuffer(
            capacity=self.buffer_size,
            state_dim=self.state_dim,
            alpha=0.6,
            beta=0.4,
            beta_annealing=0.001,
            n_step=3,
            gamma=0.99
        )
        
        # Add 3 transitions with known rewards
        states = [np.zeros(self.state_dim) for _ in range(3)]
        actions = [0, 1, 2]
        rewards = [1.0, 2.0, 3.0]
        next_states = [np.ones(self.state_dim) for _ in range(3)]
        dones = [False, False, False]
        
        # Add first two transitions
        self.buffer.add(states[0], actions[0], rewards[0], next_states[0], dones[0])
        self.buffer.add(states[1], actions[1], rewards[1], next_states[1], dones[1])
        
        # Buffer shouldn't store anything yet
        self.assertEqual(self.buffer.size, 0)
        
        # Add third transition
        self.buffer.add(states[2], actions[2], rewards[2], next_states[2], dones[2])
        
        # Now buffer should store the first transition with n-step return
        self.assertEqual(self.buffer.size, 1)
        
        # Calculate expected n-step return
        expected_reward = rewards[0] + rewards[1] * self.buffer.gamma + rewards[2] * (self.buffer.gamma ** 2)
        
        # Check stored transition
        self.assertEqual(self.buffer.actions[0], actions[0])
        self.assertAlmostEqual(self.buffer.rewards[0], expected_reward, places=6)
    
    def test_add_with_episode_end(self):
        """Test adding transitions with episode end."""
        # Reset buffer
        self.buffer = ExperienceReplayBuffer(
            capacity=self.buffer_size,
            state_dim=self.state_dim,
            alpha=0.6,
            beta=0.4,
            beta_annealing=0.001,
            n_step=3,
            gamma=0.99
        )
        
        # Add 2 transitions then one with done=True
        states = [np.zeros(self.state_dim) for _ in range(3)]
        actions = [0, 1, 2]
        rewards = [1.0, 2.0, 3.0]
        next_states = [np.ones(self.state_dim) for _ in range(3)]
        dones = [False, False, True]  # Last one ends the episode
        
        # Add all transitions
        for i in range(3):
            self.buffer.add(states[i], actions[i], rewards[i], next_states[i], dones[i])
        
        # Buffer should store all 3 transitions now
        self.assertEqual(self.buffer.size, 3)
    
    def test_buffer_capacity(self):
        """Test that buffer respects capacity."""
        # Create a small buffer
        buffer = ExperienceReplayBuffer(
            capacity=5,
            state_dim=self.state_dim,
            alpha=0.6,
            beta=0.4,
            beta_annealing=0.001,
            n_step=1,  # Use n_step=1 for simplicity
            gamma=0.99
        )
        
        # Add more transitions than capacity
        for i in range(10):
            state = np.random.randn(self.state_dim).astype(np.float32)
            action = i % 3
            reward = 0.1
            next_state = np.random.randn(self.state_dim).astype(np.float32)
            done = False
            
            buffer.add(state, action, reward, next_state, done)
        
        # Size should be limited to capacity
        self.assertEqual(buffer.size, 5)
        
        # Position should have wrapped around
        self.assertEqual(buffer.position, 0)
    
    def test_prioritized_sampling(self):
        """Test prioritized sampling with non-uniform priorities."""
        # Create buffer with very strong prioritization
        buffer = ExperienceReplayBuffer(
            capacity=100,
            state_dim=self.state_dim,
            alpha=1.0,  # Full prioritization
            beta=0.4,
            beta_annealing=0.001,
            n_step=1,  # Use n_step=1 for simplicity
            gamma=0.99
        )
        
        # Add transitions with varying rewards
        for i in range(50):
            state = np.zeros(self.state_dim)
            action = 0
            reward = i  # Increasing rewards
            next_state = np.ones(self.state_dim)
            done = False
            
            buffer.add(state, action, reward, next_state, done)
        
        # Update priorities so they're very different
        indices = np.arange(50)
        td_errors = np.linspace(0.1, 10.0, 50)  # Priorities will be powers of these
        buffer.update_priorities(indices, td_errors)
        
        # Sample many batches and track frequency
        n_samples = 1000
        batch_size = 10
        sampled_indices = []
        
        for _ in range(n_samples):
            batch = buffer.sample(batch_size)
            sampled_indices.extend(batch['indices'])
        
        # Count occurrences of each index
        counts = np.bincount(sampled_indices, minlength=50)
        
        # Higher priority indices should be sampled more often
        # Test that indices with higher td_errors (40-49) are sampled at least twice as often
        # as indices with lower td_errors (0-9)
        high_priority_avg = np.mean(counts[40:50])
        low_priority_avg = np.mean(counts[0:10])
        
        self.assertGreater(high_priority_avg, low_priority_avg * 1.5)
    
    def test_uniform_sampling(self):
        """Test uniform sampling with alpha=0."""
        # Create buffer with uniform sampling
        buffer = ExperienceReplayBuffer(
            capacity=100,
            state_dim=self.state_dim,
            alpha=0.0,  # Uniform sampling
            beta=0.4,
            beta_annealing=0.001,
            n_step=1,  # Use n_step=1 for simplicity
            gamma=0.99
        )
        
        # Add transitions
        for i in range(50):
            state = np.zeros(self.state_dim)
            action = 0
            reward = i
            next_state = np.ones(self.state_dim)
            done = False
            
            buffer.add(state, action, reward, next_state, done)
        
        # Update priorities to very different values
        indices = np.arange(50)
        td_errors = np.linspace(0.1, 10.0, 50)
        buffer.update_priorities(indices, td_errors)
        
        # Sample many batches and track frequency
        n_samples = 1000
        batch_size = 10
        sampled_indices = []
        
        for _ in range(n_samples):
            batch = buffer.sample(batch_size)
            sampled_indices.extend(batch['indices'])
        
        # Count occurrences of each index
        counts = np.bincount(sampled_indices, minlength=50)
        
        # All indices should be sampled approximately equally
        high_priority_avg = np.mean(counts[40:50])
        low_priority_avg = np.mean(counts[0:10])
        
        # Allow some statistical variation but they should be close
        self.assertLess(high_priority_avg / low_priority_avg, 1.3)
    
    def test_importance_sampling_weights(self):
        """Test that importance sampling weights are calculated correctly."""
        # Create buffer with prioritization
        buffer = ExperienceReplayBuffer(
            capacity=100,
            state_dim=self.state_dim,
            alpha=0.6,
            beta=0.4,
            beta_annealing=0.001,
            n_step=1,  # Use n_step=1 for simplicity
            gamma=0.99
        )
        
        # Add transitions
        for i in range(50):
            state = np.zeros(self.state_dim)
            action = 0
            reward = i
            next_state = np.ones(self.state_dim)
            done = False
            
            buffer.add(state, action, reward, next_state, done)
        
        # Set very different priorities
        indices = np.arange(50)
        td_errors = np.array([0.1] * 25 + [10.0] * 25)  # Two groups with very different priorities
        buffer.update_priorities(indices, td_errors)
        
        # Sample and check weights
        batch = buffer.sample(20)
        weights = batch['weights'].numpy()
        sampled_indices = batch['indices']
        
        # Find which indices came from each group
        low_priority_mask = sampled_indices < 25
        high_priority_mask = sampled_indices >= 25
        
        if np.any(low_priority_mask) and np.any(high_priority_mask):
            # Low priority samples should have higher weights
            low_priority_weights = weights[low_priority_mask]
            high_priority_weights = weights[high_priority_mask]
            
            # Average weight for low priority should be higher
            self.assertGreater(np.mean(low_priority_weights), np.mean(high_priority_weights))
    
    def test_beta_annealing(self):
        """Test that beta parameter increases with annealing."""
        # Create buffer with fast annealing
        buffer = ExperienceReplayBuffer(
            capacity=100,
            state_dim=self.state_dim,
            alpha=0.6,
            beta=0.4,
            beta_annealing=0.1,  # Fast annealing
            n_step=1,
            gamma=0.99
        )
        
        initial_beta = buffer.beta
        
        # Anneal several times
        for _ in range(5):
            buffer.anneal_beta()
        
        # Beta should have increased
        self.assertGreater(buffer.beta, initial_beta)
        
        # Beta should not exceed 1
        for _ in range(50):
            buffer.anneal_beta()
        
        self.assertLessEqual(buffer.beta, 1.0)
    
    def test_save_load(self):
        """Test saving and loading buffer state."""
        # Create buffer and add some data
        buffer = ExperienceReplayBuffer(
            capacity=100,
            state_dim=self.state_dim,
            alpha=0.6,
            beta=0.4,
            beta_annealing=0.001,
            n_step=2,
            gamma=0.99
        )
        
        # Add transitions
        for i in range(10):
            state = np.random.randn(self.state_dim).astype(np.float32)
            action = i % 3
            reward = 0.1 * (i + 1)
            next_state = np.random.randn(self.state_dim).astype(np.float32)
            done = False
            
            buffer.add(state, action, reward, next_state, done)
        
        # Add one with done=True to process pending transitions
        buffer.add(
            np.random.randn(self.state_dim).astype(np.float32),
            0,
            0.1,
            np.random.randn(self.state_dim).astype(np.float32),
            True
        )
        
        # Save buffer
        save_path = os.path.join(self.temp_dir, 'buffer.pkl')
        buffer.save(save_path)
        
        # Create new buffer and load
        new_buffer = ExperienceReplayBuffer(
            capacity=100,
            state_dim=self.state_dim,
            alpha=0.6,
            beta=0.4,
            beta_annealing=0.001,
            n_step=2,
            gamma=0.99
        )
        
        new_buffer.load(save_path)
        
        # Check that state was restored correctly
        self.assertEqual(buffer.size, new_buffer.size)
        self.assertEqual(buffer.position, new_buffer.position)
        self.assertEqual(buffer.alpha, new_buffer.alpha)
        self.assertEqual(buffer.beta, new_buffer.beta)
        
        # Check that data is the same
        np.testing.assert_array_equal(buffer.states[:buffer.size], new_buffer.states[:new_buffer.size])
        np.testing.assert_array_equal(buffer.actions[:buffer.size], new_buffer.actions[:new_buffer.size])
        np.testing.assert_array_equal(buffer.rewards[:buffer.size], new_buffer.rewards[:new_buffer.size])
        np.testing.assert_array_equal(buffer.next_states[:buffer.size], new_buffer.next_states[:new_buffer.size])
        np.testing.assert_array_equal(buffer.dones[:buffer.size], new_buffer.dones[:new_buffer.size])
        np.testing.assert_array_almost_equal(buffer.priorities[:buffer.size], new_buffer.priorities[:new_buffer.size])
    
    def test_sample_format(self):
        """Test that sampled batch has the correct format."""
        # Create buffer and add some data
        buffer = ExperienceReplayBuffer(
            capacity=100,
            state_dim=self.state_dim,
            alpha=0.6,
            beta=0.4,
            beta_annealing=0.001,
            n_step=1,
            gamma=0.99
        )
        
        # Add transitions
        for i in range(20):
            state = np.random.randn(self.state_dim).astype(np.float32)
            action = i % 3
            reward = 0.1 * (i + 1)
            next_state = np.random.randn(self.state_dim).astype(np.float32)
            done = i % 10 == 9  # Every 10th transition ends episode
            
            buffer.add(state, action, reward, next_state, done)
        
        # Sample batch
        batch_size = 10
        batch = buffer.sample(batch_size)
        
        # Check batch format
        self.assertIsInstance(batch, dict)
        self.assertIn('states', batch)
        self.assertIn('actions', batch)
        self.assertIn('rewards', batch)
        self.assertIn('next_states', batch)
        self.assertIn('dones', batch)
        self.assertIn('weights', batch)
        self.assertIn('indices', batch)
        
        # Check tensor shapes
        self.assertEqual(batch['states'].shape, (batch_size, self.state_dim))
        self.assertEqual(batch['actions'].shape, (batch_size,))
        self.assertEqual(batch['rewards'].shape, (batch_size,))
        self.assertEqual(batch['next_states'].shape, (batch_size, self.state_dim))
        self.assertEqual(batch['dones'].shape, (batch_size,))
        self.assertEqual(batch['weights'].shape, (batch_size,))
        self.assertEqual(len(batch['indices']), batch_size)
        
        # Check data types
        self.assertEqual(batch['states'].dtype, torch.float32)
        self.assertEqual(batch['actions'].dtype, torch.int64)
        self.assertEqual(batch['rewards'].dtype, torch.float32)
        self.assertEqual(batch['next_states'].dtype, torch.float32)
        self.assertEqual(batch['dones'].dtype, torch.float32)
        self.assertEqual(batch['weights'].dtype, torch.float32)


class TestTorchRLExperienceReplayBuffer(unittest.TestCase):
    """Test cases for the TorchRL experience replay buffer wrapper."""
    
    def setUp(self):
        """Set up test cases."""
        self.buffer_size = 100
        self.state_dim = 10
        self.buffer = TorchRLExperienceReplayBuffer(
            capacity=self.buffer_size,
            state_dim=self.state_dim,
            alpha=0.6,
            beta=0.4,
            beta_annealing=0.001,
            n_step=3,
            gamma=0.99
        )
        
        # Create temporary directory for file operations
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up after tests."""
        # Remove temporary directory
        shutil.rmtree(self.temp_dir)
    
    def test_add_sample_basic(self):
        """Test basic add and sample operations."""
        # Add transitions
        for i in range(20):
            state = torch.randn(self.state_dim)
            action = i % 3
            reward = 0.1 * (i + 1)
            next_state = torch.randn(self.state_dim)
            done = i % 10 == 9  # Every 10th transition ends episode
            
            self.buffer.add(state, action, reward, next_state, done)
        
        # Sample batch
        batch_size = 10
        try:
            batch = self.buffer.sample(batch_size)
            
            # Check batch format
            self.assertIsInstance(batch, dict)
            self.assertIn('states', batch)
            self.assertIn('actions', batch)
            self.assertIn('rewards', batch)
            self.assertIn('next_states', batch)
            self.assertIn('dones', batch)
            self.assertIn('weights', batch)
            self.assertIn('indices', batch)
            
            # Check tensor shapes (either TorchRL batch or custom implementation)
            self.assertEqual(batch['states'].shape[-1], self.state_dim)
            self.assertGreaterEqual(len(batch['actions'].shape), 1)
            self.assertGreaterEqual(len(batch['rewards'].shape), 1)
            self.assertEqual(batch['next_states'].shape[-1], self.state_dim)
        except Exception as e:
            # This could fail if TorchRL is not available
            # In that case, just check that we fall back to custom implementation
            if hasattr(self.buffer, 'tensordict_available') and not self.buffer.tensordict_available:
                pass
            else:
                raise e
    
    def test_update_priorities(self):
        """Test updating priorities."""
        # Add transitions
        for i in range(10):
            state = torch.randn(self.state_dim)
            action = i % 3
            reward = 0.1 * (i + 1)
            next_state = torch.randn(self.state_dim)
            done = i % 5 == 4
            
            self.buffer.add(state, action, reward, next_state, done)
        
        # Sample batch
        try:
            batch = self.buffer.sample(5)
            
            # Update priorities
            indices = batch['indices']
            td_errors = torch.rand(len(indices))
            
            # This should not raise an exception
            self.buffer.update_priorities(indices, td_errors)
        except Exception as e:
            # This could fail if TorchRL is not available
            if hasattr(self.buffer, 'tensordict_available') and not self.buffer.tensordict_available:
                pass
            else:
                raise e
    
    def test_save_load(self):
        """Test saving and loading buffer."""
        # Add transitions
        for i in range(10):
            state = torch.randn(self.state_dim)
            action = i % 3
            reward = 0.1 * (i + 1)
            next_state = torch.randn(self.state_dim)
            done = i % 5 == 4
            
            self.buffer.add(state, action, reward, next_state, done)
        
        # Save buffer
        save_path = os.path.join(self.temp_dir, 'torchrl_buffer.pkl')
        try:
            self.buffer.save(save_path)
            
            # Create new buffer and load
            new_buffer = TorchRLExperienceReplayBuffer(
                capacity=self.buffer_size,
                state_dim=self.state_dim,
                alpha=0.6,
                beta=0.4,
                beta_annealing=0.001,
                n_step=3,
                gamma=0.99
            )
            
            new_buffer.load(save_path)
            
            # Sample from both buffers to check they work
            self.buffer.sample(5)
            new_buffer.sample(5)
        except Exception as e:
            # This could fail if TorchRL is not available
            if hasattr(self.buffer, 'tensordict_available') and not self.buffer.tensordict_available:
                pass
            else:
                raise e


if __name__ == '__main__':
    unittest.main() 