import numpy as np
import torch as th
import torch.nn as nn
import torch.nn.functional as F
from typing import Any, Dict, List, Optional, Tuple, Type, Union

from stable_baselines3 import DQN
from stable_baselines3.common.policies import BasePolicy
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor, FlattenExtractor
from stable_baselines3.common.type_aliases import Schedule


class NoisyLinear(nn.Module):
    """
    Noisy Linear Layer for exploration.
    
    This implements a noisy linear layer as described in:
    "Noisy Networks for Exploration" (Fortunato et al., 2017)
    """
    
    def __init__(self, in_features: int, out_features: int, std_init: float = 0.5):
        """
        Initialize the noisy linear layer.
        
        Args:
            in_features: Number of input features
            out_features: Number of output features
            std_init: Initial standard deviation of the noise
        """
        super(NoisyLinear, self).__init__()
        
        self.in_features = in_features
        self.out_features = out_features
        self.std_init = std_init
        
        # Mean weights and biases
        self.weight_mu = nn.Parameter(th.Tensor(out_features, in_features))
        self.weight_sigma = nn.Parameter(th.Tensor(out_features, in_features))
        self.register_buffer('weight_epsilon', th.Tensor(out_features, in_features))
        
        self.bias_mu = nn.Parameter(th.Tensor(out_features))
        self.bias_sigma = nn.Parameter(th.Tensor(out_features))
        self.register_buffer('bias_epsilon', th.Tensor(out_features))
        
        self.reset_parameters()
        self.reset_noise()
    
    def reset_parameters(self):
        """Reset the parameters of the layer."""
        mu_range = 1 / np.sqrt(self.in_features)
        self.weight_mu.data.uniform_(-mu_range, mu_range)
        self.weight_sigma.data.fill_(self.std_init / np.sqrt(self.in_features))
        
        self.bias_mu.data.uniform_(-mu_range, mu_range)
        self.bias_sigma.data.fill_(self.std_init / np.sqrt(self.out_features))
    
    def _scale_noise(self, size: int) -> th.Tensor:
        """
        Scale noise to have f(x) = sign(x) * sqrt(|x|).
        
        Args:
            size: Size of the tensor
            
        Returns:
            Scaled noise tensor
        """
        x = th.randn(size)
        return x.sign().mul(x.abs().sqrt())
    
    def reset_noise(self):
        """Reset the noise values."""
        epsilon_in = self._scale_noise(self.in_features)
        epsilon_out = self._scale_noise(self.out_features)
        
        self.weight_epsilon.copy_(epsilon_out.outer(epsilon_in))
        self.bias_epsilon.copy_(epsilon_out)
    
    def forward(self, x: th.Tensor) -> th.Tensor:
        """
        Forward pass through the layer.
        
        Args:
            x: Input tensor
            
        Returns:
            Output tensor
        """
        if self.training:
            return F.linear(
                x,
                self.weight_mu + self.weight_sigma * self.weight_epsilon,
                self.bias_mu + self.bias_sigma * self.bias_epsilon
            )
        else:
            return F.linear(x, self.weight_mu, self.bias_mu)


class DuelingNetwork(nn.Module):
    """
    Dueling Network Architecture.
    
    This implements the dueling network architecture as described in:
    "Dueling Network Architectures for Deep Reinforcement Learning" (Wang et al., 2016)
    """
    
    def __init__(
        self,
        features_dim: int,
        action_dim: int,
        hidden_dim: int = 128,
        activation_fn: Type[nn.Module] = nn.ReLU,
        use_noisy: bool = True,
    ):
        """
        Initialize the dueling network.
        
        Args:
            features_dim: Dimension of the feature extractor output
            action_dim: Dimension of the action space
            hidden_dim: Hidden layer dimension
            activation_fn: Activation function
            use_noisy: Whether to use noisy linear layers for exploration
        """
        super(DuelingNetwork, self).__init__()
        
        self.features_dim = features_dim
        self.action_dim = action_dim
        self.use_noisy = use_noisy
        
        # Feature extraction
        if use_noisy:
            # Value stream
            self.value_hidden = NoisyLinear(features_dim, hidden_dim)
            self.value = NoisyLinear(hidden_dim, 1)
            
            # Advantage stream
            self.advantage_hidden = NoisyLinear(features_dim, hidden_dim)
            self.advantage = NoisyLinear(hidden_dim, action_dim)
        else:
            # Value stream
            self.value_hidden = nn.Linear(features_dim, hidden_dim)
            self.value = nn.Linear(hidden_dim, 1)
            
            # Advantage stream
            self.advantage_hidden = nn.Linear(features_dim, hidden_dim)
            self.advantage = nn.Linear(hidden_dim, action_dim)
        
        self.activation = activation_fn()
    
    def forward(self, features: th.Tensor) -> th.Tensor:
        """
        Forward pass through the dueling network.
        
        Args:
            features: Features extracted from the observation
            
        Returns:
            Action-value (Q-value) estimates
        """
        # Value stream
        value = self.activation(self.value_hidden(features))
        value = self.value(value)
        
        # Advantage stream
        advantage = self.activation(self.advantage_hidden(features))
        advantage = self.advantage(advantage)
        
        # Combine value and advantage
        # Q(s, a) = V(s) + A(s, a) - mean(A(s, a'))
        return value + advantage - advantage.mean(dim=1, keepdim=True)
    
    def reset_noise(self):
        """Reset the noise in all noisy layers."""
        if not self.use_noisy:
            return
        
        self.value_hidden.reset_noise()
        self.value.reset_noise()
        self.advantage_hidden.reset_noise()
        self.advantage.reset_noise()


class DuelingQNetwork(BasePolicy):
    """
    Dueling Q-Network with optional noisy layers.
    
    This is a Q-Network that uses the dueling architecture and optionally noisy 
    linear layers for exploration.
    """
    
    def __init__(
        self,
        observation_space,
        action_space,
        features_extractor: nn.Module,
        features_dim: int,
        hidden_dim: int = 128,
        activation_fn: Type[nn.Module] = nn.ReLU,
        normalize_images: bool = True,
        use_noisy: bool = True,
    ):
        """
        Initialize the dueling Q-network.
        
        Args:
            observation_space: Observation space
            action_space: Action space
            features_extractor: Features extractor to use
            features_dim: Dimension of the feature extractor output
            hidden_dim: Hidden layer dimension
            activation_fn: Activation function
            normalize_images: Whether to normalize images
            use_noisy: Whether to use noisy linear layers for exploration
        """
        super(DuelingQNetwork, self).__init__(
            observation_space,
            action_space,
            features_extractor=features_extractor,
            normalize_images=normalize_images,
        )
        
        self.action_dim = self.action_space.n
        self.use_noisy = use_noisy
        
        self.q_net = DuelingNetwork(
            features_dim,
            self.action_dim,
            hidden_dim=hidden_dim,
            activation_fn=activation_fn,
            use_noisy=use_noisy,
        )
    
    def forward(self, obs: th.Tensor) -> th.Tensor:
        """
        Forward pass through the network.
        
        Args:
            obs: Observation tensor
            
        Returns:
            Action-value (Q-value) estimates
        """
        # Extract features and pass through dueling network
        features = self.extract_features(obs)
        return self.q_net(features)
    
    def _predict(self, obs: th.Tensor, deterministic: bool = True) -> th.Tensor:
        """
        Get the action for a given observation.
        
        Args:
            obs: Observation
            deterministic: Whether to return deterministic actions
            
        Returns:
            Actions
        """
        q_values = self.forward(obs)
        return q_values.argmax(dim=1)
    
    def reset_noise(self):
        """Reset the noise in all noisy layers."""
        if not self.use_noisy:
            return
        
        self.q_net.reset_noise()


class ExtendedDQN(DQN):
    """
    Extended DQN implementation with double DQN, dueling networks, and noisy networks.
    
    This extends the base DQN implementation from Stable Baselines3 to include:
    1. Double DQN: Uses the online network to select actions and the target network to evaluate them
    2. Dueling Networks: Separates the value and advantage functions
    3. Noisy Networks: Uses noisy linear layers for exploration instead of epsilon-greedy
    """
    
    def __init__(
        self,
        policy: Union[str, Type[BasePolicy]],
        env,
        learning_rate: Union[float, Schedule] = 1e-4,
        buffer_size: int = 1000000,
        learning_starts: int = 50000,
        batch_size: int = 32,
        tau: float = 1.0,
        gamma: float = 0.99,
        train_freq: Union[int, Tuple[int, str]] = 4,
        gradient_steps: int = 1,
        replay_buffer_class = None,
        replay_buffer_kwargs: Optional[Dict[str, Any]] = None,
        optimize_memory_usage: bool = False,
        target_update_interval: int = 10000,
        exploration_fraction: float = 0.1,
        exploration_initial_eps: float = 1.0,
        exploration_final_eps: float = 0.05,
        max_grad_norm: float = 10,
        tensorboard_log: Optional[str] = None,
        create_eval_env: bool = False,
        policy_kwargs: Optional[Dict[str, Any]] = None,
        verbose: int = 0,
        seed: Optional[int] = None,
        device: Union[th.device, str] = "auto",
        _init_setup_model: bool = True,
        use_double_dqn: bool = True,
        use_dueling: bool = True,
        use_noisy: bool = True,
        hidden_dim: int = 128,
    ):
        """
        Initialize the extended DQN.
        
        Args:
            policy: The policy model to use
            env: The environment to learn from
            learning_rate: The learning rate
            buffer_size: Size of the replay buffer
            learning_starts: How many steps of the model to collect transitions for before learning starts
            batch_size: Minibatch size
            tau: Target network update rate
            gamma: Discount factor
            train_freq: Update the model every 'train_freq' steps
            gradient_steps: How many gradient update steps to do after each rollout
            replay_buffer_class: Replay buffer class to use
            replay_buffer_kwargs: Keyword arguments to pass to the replay buffer on creation
            optimize_memory_usage: Enable a memory efficient variant of the replay buffer
            target_update_interval: Update the target network every 'target_update_interval' steps
            exploration_fraction: Fraction of entire training period over which exploration rate is annealed
            exploration_initial_eps: Initial value of random action probability
            exploration_final_eps: Final value of random action probability
            max_grad_norm: Maximum norm for gradient clipping
            tensorboard_log: The log location for tensorboard
            create_eval_env: Whether to create a second environment to evaluate on
            policy_kwargs: Additional arguments to pass to the policy on creation
            verbose: Verbosity level
            seed: Random seed
            device: Device to use for computation
            _init_setup_model: Whether or not to build the network at the creation of the instance
            use_double_dqn: Whether to use double DQN
            use_dueling: Whether to use dueling networks
            use_noisy: Whether to use noisy networks for exploration
            hidden_dim: Hidden dimension for the networks
        """
        # Initialize defaults for policy_kwargs if not provided
        policy_kwargs = {} if policy_kwargs is None else policy_kwargs
        
        # Add our custom parameters to policy_kwargs
        if use_dueling:
            # We need to use our custom policy for dueling networks
            policy = DuelingQNetwork
            
            # Set up the policy kwargs
            policy_kwargs.update({
                "hidden_dim": hidden_dim,
                "use_noisy": use_noisy,
            })
        
        # Store parameters specific to our extensions
        self.use_double_dqn = use_double_dqn
        self.use_dueling = use_dueling
        self.use_noisy = use_noisy
        
        # If using noisy networks, we don't need epsilon-greedy exploration
        if use_noisy:
            exploration_fraction = 0
            exploration_initial_eps = 0
            exploration_final_eps = 0
        
        # Initialize the base DQN
        super(ExtendedDQN, self).__init__(
            policy=policy,
            env=env,
            learning_rate=learning_rate,
            buffer_size=buffer_size,
            learning_starts=learning_starts,
            batch_size=batch_size,
            tau=tau,
            gamma=gamma,
            train_freq=train_freq,
            gradient_steps=gradient_steps,
            replay_buffer_class=replay_buffer_class,
            replay_buffer_kwargs=replay_buffer_kwargs,
            optimize_memory_usage=optimize_memory_usage,
            target_update_interval=target_update_interval,
            exploration_fraction=exploration_fraction,
            exploration_initial_eps=exploration_initial_eps,
            exploration_final_eps=exploration_final_eps,
            max_grad_norm=max_grad_norm,
            tensorboard_log=tensorboard_log,
            create_eval_env=create_eval_env,
            policy_kwargs=policy_kwargs,
            verbose=verbose,
            seed=seed,
            device=device,
            _init_setup_model=_init_setup_model,
        )
    
    def train(self, gradient_steps: int, batch_size: int = 100) -> None:
        """
        Override train method to implement double DQN.
        
        Args:
            gradient_steps: How many gradient steps to perform
            batch_size: Sample batch size
        """
        # Switch to train mode
        self.policy.set_training_mode(True)
        
        # Reset noise if using noisy networks
        if self.use_noisy and hasattr(self.policy, "reset_noise"):
            self.policy.reset_noise()
            self.policy.q_net.reset_noise()
        
        # Update learning rate
        self._update_learning_rate(self.policy.optimizer)
        
        losses = []
        for _ in range(gradient_steps):
            # Sample replay buffer
            replay_data = self.replay_buffer.sample(batch_size, env=self._vec_normalize_env)
            
            with th.no_grad():
                # Compute the next Q-values using the target network
                next_q_values = self.q_net_target(replay_data.next_observations)
                
                if self.use_double_dqn:
                    # Double DQN: Use online network for action selection
                    next_q_values_online = self.q_net(replay_data.next_observations)
                    next_actions = next_q_values_online.argmax(dim=1)
                    # Use target network for action evaluation
                    next_q_values = next_q_values.gather(1, next_actions.unsqueeze(1)).squeeze(1)
                else:
                    # Vanilla DQN: Use max of target network
                    next_q_values = next_q_values.max(dim=1)[0]
                
                # Compute target Q values
                target_q_values = replay_data.rewards + (1 - replay_data.dones) * self.gamma * next_q_values
            
            # Get current Q-values
            current_q_values = self.q_net(replay_data.observations)
            current_q_values = current_q_values.gather(1, replay_data.actions).squeeze(1)
            
            # Compute loss
            loss = F.smooth_l1_loss(current_q_values, target_q_values)
            losses.append(loss.item())
            
            # Optimize the policy
            self.policy.optimizer.zero_grad()
            loss.backward()
            
            # Clip gradients
            if self.max_grad_norm > 0:
                nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
            
            self.policy.optimizer.step()
        
        # Update target network periodically
        if self._n_updates % self.target_update_interval == 0:
            self._update_target_network()
        
        self._n_updates += gradient_steps
        
        self.logger.record("train/n_updates", self._n_updates, exclude="tensorboard")
        if losses:
            self.logger.record("train/loss", np.mean(losses))
    
    def predict(
        self, 
        observation: Union[np.ndarray, Dict[str, np.ndarray]], 
        state: Optional[Tuple[np.ndarray, ...]] = None,
        episode_start: Optional[np.ndarray] = None,
        deterministic: bool = False,
    ) -> Tuple[np.ndarray, Optional[Tuple[np.ndarray, ...]]]:
        """
        Override predict to handle noisy networks.
        
        Args:
            observation: The input observation
            state: The last states (for recurrent policies)
            episode_start: Whether the observation is the first for an episode
            deterministic: Whether to return deterministic actions
            
        Returns:
            The model's action and the next state
        """
        # Reset noise for deterministic actions if requested
        if deterministic and self.use_noisy and hasattr(self.policy, "reset_noise"):
            self.policy.reset_noise()
        
        return super().predict(observation, state, episode_start, deterministic) 