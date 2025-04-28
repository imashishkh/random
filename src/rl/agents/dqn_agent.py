import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import random
from collections import deque, namedtuple
from typing import Dict, List, Tuple, Union, Optional

from .models.networks import DuelingDQN, MLP


# Define a named tuple for storing experience
Experience = namedtuple('Experience', ['state', 'action', 'reward', 'next_state', 'done'])


class ReplayBuffer:
    """
    Experience replay buffer for storing and sampling transitions.
    """
    
    def __init__(self, capacity: int):
        """
        Initialize the replay buffer with a fixed capacity.
        
        Args:
            capacity: Maximum number of experiences to store.
        """
        self.buffer = deque(maxlen=capacity)
    
    def add(self, state, action, reward, next_state, done):
        """
        Add an experience to the buffer.
        
        Args:
            state: Current state.
            action: Action taken.
            reward: Reward received.
            next_state: Next state.
            done: Whether the episode is done.
        """
        experience = Experience(state, action, reward, next_state, done)
        self.buffer.append(experience)
    
    def sample(self, batch_size: int) -> List[Experience]:
        """
        Sample a batch of experiences from the buffer.
        
        Args:
            batch_size: Number of experiences to sample.
            
        Returns:
            A list of sampled experiences.
        """
        return random.sample(self.buffer, min(batch_size, len(self.buffer)))
    
    def __len__(self) -> int:
        """
        Get the current size of the buffer.
        
        Returns:
            Number of experiences in the buffer.
        """
        return len(self.buffer)


class PrioritizedReplayBuffer:
    """
    Prioritized experience replay buffer using sum-tree data structure.
    """
    
    def __init__(self, capacity: int, alpha: float = 0.6, beta: float = 0.4, beta_increment: float = 0.001):
        """
        Initialize the prioritized replay buffer.
        
        Args:
            capacity: Maximum number of experiences to store.
            alpha: Exponent for prioritization (0 = uniform sampling, 1 = full prioritization).
            beta: Exponent for importance sampling correction (0 = no correction, 1 = full correction).
            beta_increment: Increment for beta parameter annealing.
        """
        self.capacity = capacity
        self.alpha = alpha
        self.beta = beta
        self.beta_increment = beta_increment
        self.max_priority = 1.0
        self.tree_idx = 0
        self.size = 0
        
        # Sum tree for priorities
        self.sum_tree = np.zeros(2 * capacity - 1)
        
        # Experience buffer
        self.buffer = np.empty(capacity, dtype=object)
    
    def _propagate_priority(self, idx, change):
        """
        Propagate the priority change up through the tree.
        
        Args:
            idx: Index of changed priority.
            change: Change in priority.
        """
        parent = (idx - 1) // 2
        self.sum_tree[parent] += change
        
        if parent != 0:
            self._propagate_priority(parent, change)
    
    def _update_priority(self, idx, priority):
        """
        Update the priority at a specific index.
        
        Args:
            idx: Index to update.
            priority: New priority.
        """
        change = priority - self.sum_tree[idx]
        self.sum_tree[idx] = priority
        self._propagate_priority(idx, change)
    
    def add(self, state, action, reward, next_state, done, priority=None):
        """
        Add an experience to the buffer with priority.
        
        Args:
            state: Current state.
            action: Action taken.
            reward: Reward received.
            next_state: Next state.
            done: Whether the episode is done.
            priority: Priority for the experience (if None, uses max_priority).
        """
        experience = Experience(state, action, reward, next_state, done)
        
        # Use max priority if not specified
        if priority is None:
            priority = self.max_priority
        
        # Apply alpha exponent for prioritization
        priority = priority ** self.alpha
        
        # Get the leaf index
        idx = self.capacity - 1 + self.tree_idx
        
        # Store experience and update priority
        self.buffer[self.tree_idx] = experience
        self._update_priority(idx, priority)
        
        # Update index
        self.tree_idx = (self.tree_idx + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)
    
    def _get_leaf(self, value):
        """
        Get leaf node index based on a value.
        
        Args:
            value: Value to search for in the sum tree.
            
        Returns:
            Tuple of (leaf index, priority, experience index).
        """
        idx = 0
        
        while idx < self.capacity - 1:  # Internal nodes
            left = 2 * idx + 1
            right = left + 1
            
            if value <= self.sum_tree[left]:
                idx = left
            else:
                value -= self.sum_tree[left]
                idx = right
        
        return idx, self.sum_tree[idx], idx - (self.capacity - 1)
    
    def sample(self, batch_size: int) -> Tuple[List[Experience], List[int], np.ndarray]:
        """
        Sample a batch of experiences from the buffer based on priorities.
        
        Args:
            batch_size: Number of experiences to sample.
            
        Returns:
            Tuple of (experiences, indices, importance sampling weights).
        """
        # Increment beta for importance sampling annealing
        self.beta = min(1.0, self.beta + self.beta_increment)
        
        # Ensure buffer has enough elements
        batch_size = min(batch_size, self.size)
        
        # Get batch
        experiences = []
        indices = []
        weights = np.empty(batch_size, dtype=np.float32)
        
        # Calculate segment size
        segment = self.sum_tree[0] / batch_size
        
        # Calculate min priority for normalization
        min_prob = np.min(self.sum_tree[self.capacity - 1:self.capacity - 1 + self.size]) / self.sum_tree[0]
        
        for i in range(batch_size):
            # Get values for each segment
            a = segment * i
            b = segment * (i + 1)
            
            # Sample value within segment
            value = np.random.uniform(a, b)
            
            # Get leaf and experience
            idx, priority, buffer_idx = self._get_leaf(value)
            
            # Calculate importance sampling weight
            prob = priority / self.sum_tree[0]
            weight = (prob / min_prob) ** (-self.beta)
            
            experiences.append(self.buffer[buffer_idx])
            indices.append(idx)
            weights[i] = weight
        
        # Normalize weights
        weights /= np.max(weights)
        
        return experiences, indices, weights
    
    def update_priorities(self, indices, priorities):
        """
        Update priorities for a batch of experiences.
        
        Args:
            indices: List of tree indices to update.
            priorities: New priorities (before alpha exponent).
        """
        for idx, priority in zip(indices, priorities):
            # Update max priority
            self.max_priority = max(self.max_priority, priority)
            
            # Apply alpha exponent
            priority = priority ** self.alpha
            
            # Update tree
            self._update_priority(idx, priority)
    
    def __len__(self) -> int:
        """
        Get the current size of the buffer.
        
        Returns:
            Number of experiences in the buffer.
        """
        return self.size


class DQNAgent:
    """
    Deep Q-Network Agent with various extensions like target networks,
    double Q-learning, prioritized experience replay, and dueling networks.
    """
    
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dims: List[int] = [128, 64],
        learning_rate: float = 0.001,
        gamma: float = 0.99,
        epsilon_start: float = 1.0,
        epsilon_end: float = 0.1,
        epsilon_decay: float = 0.995,
        target_update_freq: int = 100,
        use_double_q: bool = True,
        use_dueling: bool = True,
        use_prioritized_replay: bool = False,
        buffer_size: int = 10000,
        batch_size: int = 64,
        device: str = None,
    ):
        """
        Initialize the DQN agent.
        
        Args:
            state_dim: Dimension of the state space.
            action_dim: Dimension of the action space.
            hidden_dims: List of hidden layer dimensions.
            learning_rate: Learning rate for the optimizer.
            gamma: Discount factor.
            epsilon_start: Initial exploration rate.
            epsilon_end: Final exploration rate.
            epsilon_decay: Decay rate for exploration.
            target_update_freq: Frequency for updating the target network.
            use_double_q: Whether to use double Q-learning.
            use_dueling: Whether to use dueling network architecture.
            use_prioritized_replay: Whether to use prioritized experience replay.
            buffer_size: Size of the replay buffer.
            batch_size: Batch size for training.
            device: Device to use for training (cpu or cuda).
        """
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.epsilon = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay = epsilon_decay
        self.target_update_freq = target_update_freq
        self.use_double_q = use_double_q
        self.use_prioritized_replay = use_prioritized_replay
        self.batch_size = batch_size
        self.update_count = 0
        
        # Set device
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)
        
        # Initialize networks
        if use_dueling:
            self.q_network = DuelingDQN(state_dim, action_dim, hidden_dims=hidden_dims).to(self.device)
            self.target_network = DuelingDQN(state_dim, action_dim, hidden_dims=hidden_dims).to(self.device)
        else:
            self.q_network = MLP(state_dim, action_dim, hidden_dims=hidden_dims).to(self.device)
            self.target_network = MLP(state_dim, action_dim, hidden_dims=hidden_dims).to(self.device)
        
        # Copy weights to target network
        self.target_network.load_state_dict(self.q_network.state_dict())
        self.target_network.eval()  # Target network in evaluation mode
        
        # Initialize optimizer
        self.optimizer = optim.Adam(self.q_network.parameters(), lr=learning_rate)
        
        # Initialize replay buffer
        if use_prioritized_replay:
            self.replay_buffer = PrioritizedReplayBuffer(buffer_size)
        else:
            self.replay_buffer = ReplayBuffer(buffer_size)
    
    def select_action(self, state: np.ndarray, evaluate: bool = False) -> int:
        """
        Select an action using epsilon-greedy policy.
        
        Args:
            state: Current state.
            evaluate: Whether to evaluate (use greedy policy) or explore.
            
        Returns:
            Selected action.
        """
        if not evaluate and random.random() < self.epsilon:
            # Explore
            return random.randrange(self.action_dim)
        else:
            # Exploit
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            with torch.no_grad():
                q_values = self.q_network(state_tensor)
            return q_values.argmax().item()
    
    def update_epsilon(self):
        """
        Update exploration rate.
        """
        self.epsilon = max(self.epsilon_end, self.epsilon * self.epsilon_decay)
    
    def train(self) -> Dict[str, float]:
        """
        Train the agent using a batch of experiences.
        
        Returns:
            Dictionary with training metrics.
        """
        # Check if buffer has enough samples
        if len(self.replay_buffer) < self.batch_size:
            return {"loss": 0.0}
        
        # Sample from replay buffer
        if self.use_prioritized_replay:
            experiences, indices, weights = self.replay_buffer.sample(self.batch_size)
            weights_tensor = torch.FloatTensor(weights).to(self.device)
        else:
            experiences = self.replay_buffer.sample(self.batch_size)
            weights_tensor = None
        
        # Convert batch of experiences to tensors
        states = torch.FloatTensor([e.state for e in experiences]).to(self.device)
        actions = torch.LongTensor([e.action for e in experiences]).unsqueeze(1).to(self.device)
        rewards = torch.FloatTensor([e.reward for e in experiences]).unsqueeze(1).to(self.device)
        next_states = torch.FloatTensor([e.next_state for e in experiences]).to(self.device)
        dones = torch.FloatTensor([float(e.done) for e in experiences]).unsqueeze(1).to(self.device)
        
        # Compute current Q values
        q_values = self.q_network(states).gather(1, actions)
        
        # Compute target Q values
        with torch.no_grad():
            if self.use_double_q:
                # Double Q-learning: select actions using online network
                next_actions = self.q_network(next_states).argmax(dim=1, keepdim=True)
                # Evaluate actions using target network
                next_q_values = self.target_network(next_states).gather(1, next_actions)
            else:
                # Standard Q-learning: select actions using target network
                next_q_values = self.target_network(next_states).max(dim=1, keepdim=True)[0]
            
            # Compute target values
            target_q_values = rewards + (1 - dones) * self.gamma * next_q_values
        
        # Compute loss
        if self.use_prioritized_replay:
            # Compute temporal difference (TD) errors for prioritized replay
            td_errors = torch.abs(q_values - target_q_values).detach().cpu().numpy()
            
            # Use weighted MSE loss for prioritized replay
            loss = (weights_tensor * torch.square(q_values - target_q_values)).mean()
        else:
            # Use standard MSE loss
            loss = nn.functional.mse_loss(q_values, target_q_values)
        
        # Optimize the model
        self.optimizer.zero_grad()
        loss.backward()
        
        # Clip gradients (optional)
        # torch.nn.utils.clip_grad_norm_(self.q_network.parameters(), max_norm=10.0)
        
        self.optimizer.step()
        
        # Update target network periodically
        self.update_count += 1
        if self.update_count % self.target_update_freq == 0:
            self.target_network.load_state_dict(self.q_network.state_dict())
        
        # Update priorities in prioritized replay buffer
        if self.use_prioritized_replay:
            self.replay_buffer.update_priorities(indices, td_errors.flatten() + 1e-6)  # Small constant to avoid zero priority
        
        return {"loss": loss.item()}
    
    def save(self, path: str):
        """
        Save the agent's model.
        
        Args:
            path: Path to save the model.
        """
        torch.save({
            'q_network': self.q_network.state_dict(),
            'target_network': self.target_network.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'epsilon': self.epsilon,
            'update_count': self.update_count,
        }, path)
    
    def load(self, path: str):
        """
        Load the agent's model.
        
        Args:
            path: Path to load the model from.
        """
        checkpoint = torch.load(path, map_location=self.device)
        self.q_network.load_state_dict(checkpoint['q_network'])
        self.target_network.load_state_dict(checkpoint['target_network'])
        self.optimizer.load_state_dict(checkpoint['optimizer'])
        self.epsilon = checkpoint['epsilon']
        self.update_count = checkpoint['update_count'] 