import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from typing import Dict, List, Tuple, Union, Optional, Any

from .models.networks import ActorCriticNetwork, MLP


class PPOAgent:
    """
    Proximal Policy Optimization (PPO) agent with clipped objective, 
    generalized advantage estimation (GAE), and entropy bonus.
    """
    
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dims: List[int] = [64, 64],
        learning_rate: float = 0.0003,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_ratio: float = 0.2,
        value_coef: float = 0.5,
        entropy_coef: float = 0.01,
        max_grad_norm: float = 0.5,
        continuous_actions: bool = False,
        device: str = None,
    ):
        """
        Initialize the PPO agent.
        
        Args:
            state_dim: Dimension of the state space.
            action_dim: Dimension of the action space.
            hidden_dims: List of hidden layer dimensions.
            learning_rate: Learning rate for the optimizer.
            gamma: Discount factor.
            gae_lambda: Lambda parameter for GAE.
            clip_ratio: Clip parameter for PPO.
            value_coef: Coefficient for value function loss.
            entropy_coef: Coefficient for entropy bonus.
            max_grad_norm: Maximum norm for gradient clipping.
            continuous_actions: Whether the action space is continuous.
            device: Device to use for training (cpu or cuda).
        """
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_ratio = clip_ratio
        self.value_coef = value_coef
        self.entropy_coef = entropy_coef
        self.max_grad_norm = max_grad_norm
        self.continuous_actions = continuous_actions
        
        # Set device
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)
        
        # Initialize network
        self.network = ActorCriticNetwork(
            state_dim=state_dim,
            action_dim=action_dim,
            hidden_dims=hidden_dims,
            continuous_actions=continuous_actions
        ).to(self.device)
        
        # Initialize optimizer
        self.optimizer = optim.Adam(self.network.parameters(), lr=learning_rate)
    
    def select_action(self, state: np.ndarray, evaluate: bool = False) -> Union[int, np.ndarray]:
        """
        Select an action based on the current policy.
        
        Args:
            state: Current state.
            evaluate: Whether to evaluate (deterministic) or sample from the policy.
            
        Returns:
            Selected action, action log probability, and state value.
        """
        # Convert state to tensor
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            # Get policy and value
            if self.continuous_actions:
                action_mean, action_std, state_value = self.network(state_tensor)
                
                if evaluate:
                    # Deterministic action (mean)
                    action = action_mean.cpu().numpy()[0]
                    log_prob = None
                else:
                    # Sample from normal distribution
                    dist = torch.distributions.Normal(action_mean, action_std)
                    action = dist.sample().cpu().numpy()[0]
                    log_prob = dist.log_prob(torch.FloatTensor(action).to(self.device)).sum().item()
            else:
                action_probs, state_value = self.network(state_tensor)
                
                if evaluate:
                    # Deterministic action (argmax)
                    action = torch.argmax(action_probs, dim=1).item()
                    log_prob = None
                else:
                    # Sample from categorical distribution
                    dist = torch.distributions.Categorical(action_probs)
                    action = dist.sample().item()
                    log_prob = dist.log_prob(torch.tensor(action).to(self.device)).item()
        
        if evaluate:
            return action
        else:
            return action, log_prob, state_value.item()
    
    def compute_advantages(self, rewards: List[float], values: List[float], dones: List[bool], next_value: float) -> List[float]:
        """
        Compute advantages using Generalized Advantage Estimation (GAE).
        
        Args:
            rewards: List of rewards for each step.
            values: List of state values for each step.
            dones: List of done flags for each step.
            next_value: Value estimate for the next state.
            
        Returns:
            List of advantage estimates for each step.
        """
        advantages = []
        gae = 0
        
        # Process steps in reverse order
        for t in reversed(range(len(rewards))):
            if t == len(rewards) - 1:
                # For the last step, use next_value
                next_val = next_value
            else:
                # For other steps, use the next step's value
                next_val = values[t + 1]
            
            # Calculate TD error
            delta = rewards[t] + self.gamma * next_val * (1 - dones[t]) - values[t]
            
            # Update GAE
            gae = delta + self.gamma * self.gae_lambda * (1 - dones[t]) * gae
            
            # Insert at the beginning (since we're going backwards)
            advantages.insert(0, gae)
        
        return advantages
    
    def train(self, 
              states: np.ndarray, 
              actions: np.ndarray, 
              old_log_probs: np.ndarray, 
              rewards: np.ndarray, 
              values: np.ndarray, 
              dones: np.ndarray, 
              next_value: float,
              epochs: int = 4,
              batch_size: int = 64) -> Dict[str, float]:
        """
        Train the agent using PPO.
        
        Args:
            states: Array of states.
            actions: Array of actions.
            old_log_probs: Array of log probabilities of actions under the old policy.
            rewards: Array of rewards.
            values: Array of state values.
            dones: Array of done flags.
            next_value: Value estimate for the next state.
            epochs: Number of optimization epochs.
            batch_size: Batch size for training.
            
        Returns:
            Dictionary with training metrics.
        """
        # Convert to PyTorch tensors
        states_tensor = torch.FloatTensor(states).to(self.device)
        if self.continuous_actions:
            actions_tensor = torch.FloatTensor(actions).to(self.device)
        else:
            actions_tensor = torch.LongTensor(actions).to(self.device)
        old_log_probs_tensor = torch.FloatTensor(old_log_probs).to(self.device)
        
        # Compute advantages and returns
        advantages = self.compute_advantages(rewards, values, dones, next_value)
        returns = [adv + val for adv, val in zip(advantages, values)]
        
        advantages_tensor = torch.FloatTensor(advantages).to(self.device)
        returns_tensor = torch.FloatTensor(returns).to(self.device)
        
        # Normalize advantages
        advantages_tensor = (advantages_tensor - advantages_tensor.mean()) / (advantages_tensor.std() + 1e-8)
        
        # Training metrics
        metrics = {
            "policy_loss": 0,
            "value_loss": 0,
            "entropy": 0,
            "total_loss": 0,
            "approx_kl": 0,
            "clip_frac": 0,
        }
        
        # PPO optimization loop
        for _ in range(epochs):
            # Generate random indices for mini-batches
            indices = np.random.permutation(len(states))
            
            # Process mini-batches
            for start_idx in range(0, len(states), batch_size):
                # Get mini-batch indices
                batch_indices = indices[start_idx:start_idx + batch_size]
                
                # Extract mini-batch tensors
                batch_states = states_tensor[batch_indices]
                batch_actions = actions_tensor[batch_indices]
                batch_old_log_probs = old_log_probs_tensor[batch_indices]
                batch_advantages = advantages_tensor[batch_indices]
                batch_returns = returns_tensor[batch_indices]
                
                # Compute policy and value
                if self.continuous_actions:
                    action_mean, action_std, values_pred = self.network(batch_states)
                    
                    # Compute log probabilities using Normal distribution
                    dist = torch.distributions.Normal(action_mean, action_std)
                    new_log_probs = dist.log_prob(batch_actions).sum(dim=1)
                    entropy = dist.entropy().sum(dim=1).mean()
                else:
                    action_probs, values_pred = self.network(batch_states)
                    
                    # Compute log probabilities using Categorical distribution
                    dist = torch.distributions.Categorical(action_probs)
                    new_log_probs = dist.log_prob(batch_actions)
                    entropy = dist.entropy().mean()
                
                # Reshape values_pred if needed
                if len(values_pred.shape) > 1:
                    values_pred = values_pred.squeeze(-1)
                
                # Compute ratio for PPO
                ratio = torch.exp(new_log_probs - batch_old_log_probs)
                
                # Compute surrogate objectives
                surrogate1 = ratio * batch_advantages
                surrogate2 = torch.clamp(ratio, 1.0 - self.clip_ratio, 1.0 + self.clip_ratio) * batch_advantages
                
                # Compute policy loss (negative because we're maximizing)
                policy_loss = -torch.min(surrogate1, surrogate2).mean()
                
                # Compute value loss
                value_loss = nn.functional.mse_loss(values_pred, batch_returns)
                
                # Compute total loss
                total_loss = policy_loss + self.value_coef * value_loss - self.entropy_coef * entropy
                
                # Optimize
                self.optimizer.zero_grad()
                total_loss.backward()
                
                # Clip gradients
                nn.utils.clip_grad_norm_(self.network.parameters(), self.max_grad_norm)
                
                self.optimizer.step()
                
                # Update metrics
                metrics["policy_loss"] += policy_loss.item()
                metrics["value_loss"] += value_loss.item()
                metrics["entropy"] += entropy.item()
                metrics["total_loss"] += total_loss.item()
                
                # Compute approximate KL divergence for monitoring
                with torch.no_grad():
                    log_ratio = new_log_probs - batch_old_log_probs
                    approx_kl = ((torch.exp(log_ratio) - 1) - log_ratio).mean().item()
                    metrics["approx_kl"] += approx_kl
                    
                    # Compute fraction of training data that triggered the clipped objective
                    clip_frac = ((ratio < 1.0 - self.clip_ratio) | (ratio > 1.0 + self.clip_ratio)).float().mean().item()
                    metrics["clip_frac"] += clip_frac
        
        # Average metrics over all batches and epochs
        num_batches = len(states) // batch_size + int(len(states) % batch_size > 0)
        total_updates = num_batches * epochs
        
        for key in metrics:
            metrics[key] /= total_updates
        
        return metrics
    
    def save(self, path: str):
        """
        Save the agent's model.
        
        Args:
            path: Path to save the model.
        """
        torch.save({
            'network': self.network.state_dict(),
            'optimizer': self.optimizer.state_dict(),
        }, path)
    
    def load(self, path: str):
        """
        Load the agent's model.
        
        Args:
            path: Path to load the model from.
        """
        checkpoint = torch.load(path, map_location=self.device)
        self.network.load_state_dict(checkpoint['network'])
        self.optimizer.load_state_dict(checkpoint['optimizer'])


class PPOMemory:
    """
    Memory buffer for storing trajectories during PPO training.
    """
    
    def __init__(self):
        """
        Initialize empty lists for storing trajectories.
        """
        self.states = []
        self.actions = []
        self.log_probs = []
        self.rewards = []
        self.values = []
        self.dones = []
    
    def add(self, state, action, log_prob, reward, value, done):
        """
        Add a transition to the memory.
        
        Args:
            state: Current state.
            action: Action taken.
            log_prob: Log probability of the action.
            reward: Reward received.
            value: Value estimate for the state.
            done: Whether the episode is done.
        """
        self.states.append(state)
        self.actions.append(action)
        self.log_probs.append(log_prob)
        self.rewards.append(reward)
        self.values.append(value)
        self.dones.append(done)
    
    def get_all(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Get all stored transitions.
        
        Returns:
            Tuple of (states, actions, log_probs, rewards, values, dones).
        """
        return (
            np.array(self.states),
            np.array(self.actions),
            np.array(self.log_probs),
            np.array(self.rewards),
            np.array(self.values),
            np.array(self.dones)
        )
    
    def clear(self):
        """
        Clear the memory.
        """
        self.states = []
        self.actions = []
        self.log_probs = []
        self.rewards = []
        self.values = []
        self.dones = []
    
    def __len__(self) -> int:
        """
        Get the current size of the memory.
        
        Returns:
            Number of transitions in the memory.
        """
        return len(self.states) 