"""
Experience replay buffer implementation for reinforcement learning.

This module provides an efficient experience replay buffer with support for
prioritized sampling, n-step returns, and other advanced features.
"""

import torch
import numpy as np
from torch.utils.data import Dataset
from collections import deque
import random
import os
import pickle
from typing import Dict, Tuple, List, Any, Optional, Union


class ExperienceReplayBuffer(Dataset):
    """Experience replay buffer implemented as a PyTorch Dataset.
    
    This buffer stores transitions (state, action, reward, next_state, done)
    and allows sampling according to priorities based on TD errors. It also
    supports n-step returns and TD(λ) eligibility traces.
    """
    
    def __init__(self, capacity: int, state_dim: int, 
                alpha: float = 0.6, beta: float = 0.4, 
                beta_annealing: float = 0.001,
                epsilon: float = 1e-6,
                n_step: int = 1,
                gamma: float = 0.99,
                lambda_td: Optional[float] = None):
        """Initialize experience replay buffer.
        
        Args:
            capacity: Maximum size of the buffer
            state_dim: Dimension of state representation
            alpha: Exponent for prioritization (0 = uniform, 1 = full prioritization)
            beta: Importance sampling exponent (0 = no correction, 1 = full correction)
            beta_annealing: Rate at which beta increases to 1
            epsilon: Small constant to add to priorities to ensure non-zero sampling probability
            n_step: Number of steps for n-step returns
            gamma: Discount factor
            lambda_td: Parameter for TD(λ) eligibility traces (None = disabled)
        """
        self.capacity = capacity
        self.state_dim = state_dim
        self.alpha = alpha
        self.beta = beta
        self.beta_annealing = beta_annealing
        self.epsilon = epsilon
        self.n_step = n_step
        self.gamma = gamma
        self.lambda_td = lambda_td
        
        # Storage for experiences
        self.states = np.zeros((capacity, state_dim), dtype=np.float32)
        self.actions = np.zeros(capacity, dtype=np.int64)
        self.rewards = np.zeros(capacity, dtype=np.float32)
        self.next_states = np.zeros((capacity, state_dim), dtype=np.float32)
        self.dones = np.zeros(capacity, dtype=np.bool_)
        
        # Priorities and tracking variables
        self.priorities = np.zeros(capacity, dtype=np.float32)
        self.position = 0
        self.size = 0
        
        # n-step return buffer
        self.n_step_buffer = deque(maxlen=n_step)
        
        # For td(λ)
        self.eligibility_traces = None
        if lambda_td is not None:
            self.eligibility_traces = np.zeros(capacity, dtype=np.float32)
    
    def add(self, state: np.ndarray, action: int, reward: float, 
           next_state: np.ndarray, done: bool) -> None:
        """Add a new experience to the buffer.
        
        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state
            done: Whether the episode is done
        """
        # Add to n-step buffer first
        self.n_step_buffer.append((state, action, reward, next_state, done))
        
        # If we don't have enough experiences for n-step return, return early
        if len(self.n_step_buffer) < self.n_step and not done:
            return
            
        # Get the first experience from the n-step buffer
        s0, a0, _, _, _ = self.n_step_buffer[0]
        
        # Calculate n-step reward
        n_step_reward = 0
        for i, (_, _, r, _, d) in enumerate(self.n_step_buffer):
            n_step_reward += r * (self.gamma ** i)
            if d:
                break
                
        # Get the last state and done flag
        _, _, _, s_n, d_n = self.n_step_buffer[-1]
        
        # Store experience with n-step reward
        self._store(s0, a0, n_step_reward, s_n, d_n)
        
        # If the episode is done, process remaining experiences
        if done:
            while len(self.n_step_buffer) > 1:
                self.n_step_buffer.popleft()
                s0, a0, _, _, _ = self.n_step_buffer[0]
                n_step_reward = 0
                for i, (_, _, r, _, d) in enumerate(self.n_step_buffer):
                    n_step_reward += r * (self.gamma ** i)
                    if d:
                        break
                _, _, _, s_n, d_n = self.n_step_buffer[-1]
                self._store(s0, a0, n_step_reward, s_n, d_n)
                
    def _store(self, state: np.ndarray, action: int, reward: float, 
              next_state: np.ndarray, done: bool) -> None:
        """Store a processed experience in the buffer.
        
        Args:
            state: Current state
            action: Action taken
            reward: Reward received (possibly n-step)
            next_state: Next state (possibly n-step)
            done: Whether the episode is done
        """
        # Use max priority for new experiences
        max_priority = self.priorities.max() if self.size > 0 else 1.0
        
        # Store experience
        self.states[self.position] = state
        self.actions[self.position] = action
        self.rewards[self.position] = reward
        self.next_states[self.position] = next_state
        self.dones[self.position] = done
        self.priorities[self.position] = max_priority
        
        # Update position and size
        self.position = (self.position + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)
    
    def update_priorities(self, indices: List[int], td_errors: np.ndarray) -> None:
        """Update priorities based on TD errors.
        
        Args:
            indices: Indices of transitions to update
            td_errors: TD errors for the transitions
        """
        for idx, td_error in zip(indices, td_errors):
            # Add small constant to ensure non-zero priority
            priority = (abs(td_error) + self.epsilon) ** self.alpha
            self.priorities[idx] = priority
            
            # Update eligibility traces if using TD(λ)
            if self.lambda_td is not None:
                self.eligibility_traces[idx] = 1.0
                
                # Decay all other traces
                mask = np.ones(self.size, dtype=np.bool_)
                mask[idx] = False
                self.eligibility_traces[:self.size][mask] *= self.lambda_td
    
    def anneal_beta(self) -> None:
        """Increase beta parameter toward 1 for importance sampling."""
        self.beta = min(1.0, self.beta + self.beta_annealing)
    
    def __len__(self) -> int:
        """Return current size of buffer."""
        return self.size
    
    def __getitem__(self, idx: int) -> Tuple:
        """Get an item from the buffer by index (unused for prioritized sampling).
        
        Args:
            idx: Index of the item to retrieve
            
        Returns:
            Tuple containing (state, action, reward, next_state, done)
        """
        return (
            self.states[idx],
            self.actions[idx],
            self.rewards[idx],
            self.next_states[idx],
            self.dones[idx]
        )
    
    def sample(self, batch_size: int) -> Dict[str, torch.Tensor]:
        """Sample a batch of experiences based on priorities.
        
        Args:
            batch_size: Number of experiences to sample
            
        Returns:
            Dictionary containing sampled batch with tensors for state, action, reward,
            next_state, done, and importance sampling weights
            
        Raises:
            ValueError: If the buffer is empty
        """
        if self.size == 0:
            raise ValueError("Cannot sample from an empty buffer")
            
        # Calculate sampling probabilities
        if self.alpha == 0:
            # Uniform sampling
            indices = np.random.choice(self.size, batch_size)
            weights = np.ones(batch_size, dtype=np.float32)
        else:
            # Priority sampling
            priorities = self.priorities[:self.size]
            probs = priorities / priorities.sum()
            
            # Sample indices based on probabilities
            indices = np.random.choice(self.size, batch_size, p=probs)
            
            # Calculate importance sampling weights
            weights = (self.size * probs[indices]) ** (-self.beta)
            weights /= weights.max()  # Normalize to stabilize learning
        
        # Get experiences from buffer
        states = torch.tensor(self.states[indices], dtype=torch.float32)
        actions = torch.tensor(self.actions[indices], dtype=torch.long)
        rewards = torch.tensor(self.rewards[indices], dtype=torch.float32)
        next_states = torch.tensor(self.next_states[indices], dtype=torch.float32)
        dones = torch.tensor(self.dones[indices], dtype=torch.float32)
        weights = torch.tensor(weights, dtype=torch.float32)
        
        # Return batch as dictionary
        batch = {
            'states': states,
            'actions': actions,
            'rewards': rewards,
            'next_states': next_states,
            'dones': dones,
            'weights': weights,
            'indices': indices
        }
        
        return batch
    
    def save(self, path: str) -> None:
        """Save buffer state to file.
        
        Args:
            path: Path to save the buffer state
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Create state dictionary
        state = {
            'states': self.states[:self.size],
            'actions': self.actions[:self.size],
            'rewards': self.rewards[:self.size],
            'next_states': self.next_states[:self.size],
            'dones': self.dones[:self.size],
            'priorities': self.priorities[:self.size],
            'position': self.position,
            'size': self.size,
            'alpha': self.alpha,
            'beta': self.beta,
            'n_step': self.n_step,
            'gamma': self.gamma,
            'lambda_td': self.lambda_td,
            'n_step_buffer': list(self.n_step_buffer)
        }
        
        # Save state to file
        with open(path, 'wb') as f:
            pickle.dump(state, f)
    
    def load(self, path: str) -> None:
        """Load buffer state from file.
        
        Args:
            path: Path to the buffer state file
        """
        with open(path, 'rb') as f:
            state = pickle.load(f)
        
        # Restore state
        size = state['size']
        self.states[:size] = state['states']
        self.actions[:size] = state['actions']
        self.rewards[:size] = state['rewards']
        self.next_states[:size] = state['next_states']
        self.dones[:size] = state['dones']
        self.priorities[:size] = state['priorities']
        self.position = state['position']
        self.size = size
        self.alpha = state['alpha']
        self.beta = state['beta']
        
        # Restore n-step buffer
        self.n_step_buffer.clear()
        for item in state['n_step_buffer']:
            self.n_step_buffer.append(item)
            
        # Create eligibility traces if needed
        if state['lambda_td'] is not None and self.eligibility_traces is None:
            self.lambda_td = state['lambda_td']
            self.eligibility_traces = np.zeros(self.capacity, dtype=np.float32)


class TorchRLExperienceReplayBuffer:
    """Experience replay buffer implementation using TorchRL.
    
    This is an alternative implementation that leverages TorchRL's
    ReplayBuffer and PrioritizedSliceSampler for efficient prioritized
    experience replay.
    """
    
    def __init__(self, capacity: int, state_dim: int,
                alpha: float = 0.6, beta: float = 0.4,
                beta_annealing: float = 0.001,
                n_step: int = 1,
                gamma: float = 0.99):
        """Initialize TorchRL-based experience replay buffer.
        
        Args:
            capacity: Maximum size of the buffer
            state_dim: Dimension of state representation
            alpha: Exponent for prioritization (0 = uniform, 1 = full prioritization)
            beta: Importance sampling exponent (0 = no correction, 1 = full correction)
            beta_annealing: Rate at which beta increases to 1
            n_step: Number of steps for n-step returns
            gamma: Discount factor
        """
        try:
            from torchrl.data import ReplayBuffer, PrioritizedSliceSampler
            from tensordict import TensorDict
            
            # Create a prioritized replay buffer
            self.buffer = ReplayBuffer(
                storage="memory",  # or "disk"
                sampler=PrioritizedSliceSampler(
                    max_capacity=capacity,
                    alpha=alpha,
                    beta=beta
                )
            )
            
            self.tensordict_available = True
            self.TensorDict = TensorDict
        except ImportError:
            print("TorchRL not available, falling back to custom implementation")
            # Fallback to custom implementation
            self.buffer = ExperienceReplayBuffer(
                capacity=capacity,
                state_dim=state_dim,
                alpha=alpha,
                beta=beta,
                beta_annealing=beta_annealing,
                n_step=n_step,
                gamma=gamma
            )
            self.tensordict_available = False
    
    def add(self, state: torch.Tensor, action: int, reward: float,
           next_state: torch.Tensor, done: bool) -> None:
        """Add a new experience to the buffer.
        
        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state
            done: Whether the episode is done
        """
        if self.tensordict_available:
            # Create a TensorDict for the experience
            td = self.TensorDict({
                "state": state.unsqueeze(0) if isinstance(state, torch.Tensor) else torch.tensor([state], dtype=torch.float32),
                "action": torch.tensor([action], dtype=torch.long),
                "reward": torch.tensor([reward], dtype=torch.float32),
                "next_state": next_state.unsqueeze(0) if isinstance(next_state, torch.Tensor) else torch.tensor([next_state], dtype=torch.float32),
                "done": torch.tensor([done], dtype=torch.bool)
            })
            
            # Add to buffer
            self.buffer.add(td)
        else:
            # Use custom implementation
            self.buffer.add(
                state.cpu().numpy() if isinstance(state, torch.Tensor) else state,
                action,
                reward,
                next_state.cpu().numpy() if isinstance(next_state, torch.Tensor) else next_state,
                done
            )
    
    def sample(self, batch_size: int) -> Dict[str, torch.Tensor]:
        """Sample a batch of experiences.
        
        Args:
            batch_size: Number of experiences to sample
            
        Returns:
            Dictionary containing sampled batch
        """
        if self.tensordict_available:
            # Sample from TorchRL buffer
            td = self.buffer.sample(batch_size)
            
            # Convert to regular batch dict
            batch = {
                "states": td["state"],
                "actions": td["action"],
                "rewards": td["reward"],
                "next_states": td["next_state"],
                "dones": td["done"],
                "weights": td.get("_weight", torch.ones(batch_size)),
                "indices": td.get("_idx", torch.arange(batch_size))
            }
            return batch
        else:
            # Use custom implementation
            return self.buffer.sample(batch_size)
    
    def update_priorities(self, indices: List[int], td_errors: torch.Tensor) -> None:
        """Update priorities based on TD errors.
        
        Args:
            indices: Indices of transitions to update
            td_errors: TD errors for the transitions
        """
        if self.tensordict_available:
            # Update priorities in TorchRL buffer
            self.buffer.update_priority(indices, td_errors.abs().cpu().numpy())
        else:
            # Use custom implementation
            self.buffer.update_priorities(
                indices,
                td_errors.abs().cpu().numpy() if isinstance(td_errors, torch.Tensor) else np.abs(td_errors)
            )
    
    def anneal_beta(self) -> None:
        """Increase beta parameter toward 1 for importance sampling."""
        if self.tensordict_available:
            # Update beta in TorchRL buffer
            self.buffer.sampler.beta = min(1.0, self.buffer.sampler.beta + self.buffer.sampler.beta_annealing)
        else:
            # Use custom implementation
            self.buffer.anneal_beta()
    
    def __len__(self) -> int:
        """Return current size of buffer."""
        if self.tensordict_available:
            return len(self.buffer)
        else:
            return len(self.buffer)
    
    def save(self, path: str) -> None:
        """Save buffer state to file.
        
        Args:
            path: Path to save the buffer state
        """
        if self.tensordict_available:
            # Save TorchRL buffer
            torch.save(self.buffer, path)
        else:
            # Use custom implementation
            self.buffer.save(path)
    
    def load(self, path: str) -> None:
        """Load buffer state from file.
        
        Args:
            path: Path to the buffer state file
        """
        if self.tensordict_available:
            # Load TorchRL buffer
            self.buffer = torch.load(path)
        else:
            # Use custom implementation
            self.buffer.load(path) 