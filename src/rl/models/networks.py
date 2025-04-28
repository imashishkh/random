import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Tuple, Dict, Optional, Union


class MLP(nn.Module):
    """
    Multi-layer perceptron for value function approximation or policy networks.
    """
    
    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        hidden_dims: List[int] = [128, 64],
        activation_fn: nn.Module = nn.ReLU,
        output_activation: Optional[nn.Module] = None,
        use_batch_norm: bool = False,
        dropout_rate: float = 0.0,
    ):
        """
        Initialize the MLP.
        
        Args:
            input_dim: Input dimension.
            output_dim: Output dimension.
            hidden_dims: List of hidden layer dimensions.
            activation_fn: Activation function for hidden layers.
            output_activation: Activation function for output layer.
            use_batch_norm: Whether to use batch normalization.
            dropout_rate: Dropout rate for regularization.
        """
        super(MLP, self).__init__()
        
        # Build network layers
        layers = []
        prev_dim = input_dim
        
        for dim in hidden_dims:
            layers.append(nn.Linear(prev_dim, dim))
            
            if use_batch_norm:
                layers.append(nn.BatchNorm1d(dim))
                
            layers.append(activation_fn())
            
            if dropout_rate > 0:
                layers.append(nn.Dropout(dropout_rate))
                
            prev_dim = dim
        
        # Output layer
        layers.append(nn.Linear(prev_dim, output_dim))
        
        # Optional output activation
        if output_activation is not None:
            layers.append(output_activation())
        
        self.network = nn.Sequential(*layers)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through the network.
        
        Args:
            x: Input tensor.
            
        Returns:
            Output tensor.
        """
        return self.network(x)


class CNN(nn.Module):
    """
    Convolutional neural network for processing time series data.
    """
    
    def __init__(
        self,
        input_channels: int,
        input_length: int,
        output_dim: int,
        kernel_sizes: List[int] = [3, 5, 7],
        n_filters: List[int] = [32, 64, 128],
        hidden_dims: List[int] = [128, 64],
        activation_fn: nn.Module = nn.ReLU,
        output_activation: Optional[nn.Module] = None,
        use_batch_norm: bool = False,
        dropout_rate: float = 0.0,
    ):
        """
        Initialize the CNN.
        
        Args:
            input_channels: Number of input channels (features per time step).
            input_length: Length of input time series.
            output_dim: Output dimension.
            kernel_sizes: List of kernel sizes for convolution layers.
            n_filters: List of numbers of filters for convolution layers.
            hidden_dims: List of hidden layer dimensions for MLP head.
            activation_fn: Activation function for hidden layers.
            output_activation: Activation function for output layer.
            use_batch_norm: Whether to use batch normalization.
            dropout_rate: Dropout rate for regularization.
        """
        super(CNN, self).__init__()
        
        assert len(kernel_sizes) == len(n_filters), "kernel_sizes and n_filters must have the same length"
        
        # CNN feature extractor
        self.cnn_layers = nn.ModuleList()
        prev_channels = input_channels
        
        for i, (kernel_size, filters) in enumerate(zip(kernel_sizes, n_filters)):
            padding = kernel_size // 2  # Same padding
            conv_layer = nn.Conv1d(prev_channels, filters, kernel_size=kernel_size, padding=padding)
            
            self.cnn_layers.append(conv_layer)
            
            if use_batch_norm:
                self.cnn_layers.append(nn.BatchNorm1d(filters))
                
            self.cnn_layers.append(activation_fn())
            
            # Pool every other layer
            if i % 2 == 1:
                self.cnn_layers.append(nn.MaxPool1d(2))
                input_length = input_length // 2
                
            if dropout_rate > 0:
                self.cnn_layers.append(nn.Dropout(dropout_rate))
                
            prev_channels = filters
        
        # Calculate flattened size
        # After pooling, the length of the time series might change
        flattened_size = prev_channels * input_length
        
        # MLP head
        mlp_layers = []
        prev_dim = flattened_size
        
        for dim in hidden_dims:
            mlp_layers.append(nn.Linear(prev_dim, dim))
            
            if use_batch_norm:
                mlp_layers.append(nn.BatchNorm1d(dim))
                
            mlp_layers.append(activation_fn())
            
            if dropout_rate > 0:
                mlp_layers.append(nn.Dropout(dropout_rate))
                
            prev_dim = dim
        
        # Output layer
        mlp_layers.append(nn.Linear(prev_dim, output_dim))
        
        # Optional output activation
        if output_activation is not None:
            mlp_layers.append(output_activation())
        
        self.mlp_head = nn.Sequential(*mlp_layers)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through the network.
        
        Args:
            x: Input tensor of shape (batch_size, time_steps, features).
            
        Returns:
            Output tensor.
        """
        # Convert from (batch, time, features) to (batch, features, time)
        x = x.permute(0, 2, 1)
        
        # Pass through CNN layers
        for layer in self.cnn_layers:
            x = layer(x)
        
        # Flatten
        x = x.view(x.size(0), -1)
        
        # Pass through MLP head
        x = self.mlp_head(x)
        
        return x


class LSTM(nn.Module):
    """
    Long Short-Term Memory network for sequential data processing.
    """
    
    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        hidden_dim: int = 64,
        num_layers: int = 2,
        hidden_dims: List[int] = [64],
        bidirectional: bool = False,
        activation_fn: nn.Module = nn.ReLU,
        output_activation: Optional[nn.Module] = None,
        dropout_rate: float = 0.0,
        use_attention: bool = False,
    ):
        """
        Initialize the LSTM network.
        
        Args:
            input_dim: Input dimension (features per time step).
            output_dim: Output dimension.
            hidden_dim: Hidden dimension for LSTM cells.
            num_layers: Number of LSTM layers.
            hidden_dims: List of hidden layer dimensions for MLP head.
            bidirectional: Whether to use bidirectional LSTM.
            activation_fn: Activation function for hidden layers.
            output_activation: Activation function for output layer.
            dropout_rate: Dropout rate for regularization.
            use_attention: Whether to use attention mechanism over LSTM outputs.
        """
        super(LSTM, self).__init__()
        
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=bidirectional,
            dropout=dropout_rate if num_layers > 1 else 0,
        )
        
        self.use_attention = use_attention
        lstm_output_dim = hidden_dim * 2 if bidirectional else hidden_dim
        
        if use_attention:
            self.attention = nn.Linear(lstm_output_dim, 1)
        
        # MLP head
        mlp_layers = []
        prev_dim = lstm_output_dim
        
        for dim in hidden_dims:
            mlp_layers.append(nn.Linear(prev_dim, dim))
            mlp_layers.append(activation_fn())
            
            if dropout_rate > 0:
                mlp_layers.append(nn.Dropout(dropout_rate))
                
            prev_dim = dim
        
        # Output layer
        mlp_layers.append(nn.Linear(prev_dim, output_dim))
        
        # Optional output activation
        if output_activation is not None:
            mlp_layers.append(output_activation())
        
        self.mlp_head = nn.Sequential(*mlp_layers)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through the network.
        
        Args:
            x: Input tensor of shape (batch_size, time_steps, features).
            
        Returns:
            Output tensor.
        """
        # LSTM returns output and hidden state
        lstm_out, _ = self.lstm(x)  # Shape: (batch_size, seq_len, hidden_dim * dirs)
        
        if self.use_attention:
            # Apply attention
            attention_weights = F.softmax(self.attention(lstm_out), dim=1)  # Shape: (batch_size, seq_len, 1)
            context_vector = torch.sum(attention_weights * lstm_out, dim=1)  # Shape: (batch_size, hidden_dim * dirs)
            lstm_out = context_vector
        else:
            # Take only the last output
            lstm_out = lstm_out[:, -1, :]  # Shape: (batch_size, hidden_dim * dirs)
        
        # Pass through MLP head
        out = self.mlp_head(lstm_out)
        
        return out


class DuelingDQN(nn.Module):
    """
    Dueling DQN architecture that separates state value and advantage functions.
    This can help to better estimate Q-values for improved policy learning.
    """
    
    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        hidden_dims: List[int] = [128, 64],
        activation_fn: nn.Module = nn.ReLU,
        use_batch_norm: bool = False,
        dropout_rate: float = 0.0,
    ):
        """
        Initialize the Dueling DQN.
        
        Args:
            input_dim: Input dimension.
            output_dim: Output dimension (number of actions).
            hidden_dims: List of hidden layer dimensions.
            activation_fn: Activation function for hidden layers.
            use_batch_norm: Whether to use batch normalization.
            dropout_rate: Dropout rate for regularization.
        """
        super(DuelingDQN, self).__init__()
        
        # Feature extractor
        self.feature_extractor = MLP(
            input_dim=input_dim,
            output_dim=hidden_dims[-1],
            hidden_dims=hidden_dims[:-1],
            activation_fn=activation_fn,
            output_activation=activation_fn,
            use_batch_norm=use_batch_norm,
            dropout_rate=dropout_rate,
        )
        
        # Value stream (scalar)
        self.value_stream = nn.Linear(hidden_dims[-1], 1)
        
        # Advantage stream (per action)
        self.advantage_stream = nn.Linear(hidden_dims[-1], output_dim)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through the network.
        
        Args:
            x: Input tensor.
            
        Returns:
            Q-values tensor.
        """
        # Extract features
        features = self.feature_extractor(x)
        
        # Calculate value and advantage
        value = self.value_stream(features)
        advantage = self.advantage_stream(features)
        
        # Combine to get Q-values
        # Subtract mean advantage to ensure value stream updates are identifiable
        q_values = value + (advantage - advantage.mean(dim=1, keepdim=True))
        
        return q_values


class ActorCriticNetwork(nn.Module):
    """
    Combined Actor-Critic Network that shares a feature extractor.
    Suitable for algorithms like A2C, PPO, etc.
    """
    
    def __init__(
        self,
        input_dim: int,
        action_dim: int,
        hidden_dims: List[int] = [128, 64],
        activation_fn: nn.Module = nn.ReLU,
        use_batch_norm: bool = False,
        dropout_rate: float = 0.0,
        continuous_actions: bool = False,
    ):
        """
        Initialize the Actor-Critic Network.
        
        Args:
            input_dim: Input dimension.
            action_dim: Number of actions for discrete actions or dimensions for continuous actions.
            hidden_dims: List of hidden layer dimensions.
            activation_fn: Activation function for hidden layers.
            use_batch_norm: Whether to use batch normalization.
            dropout_rate: Dropout rate for regularization.
            continuous_actions: Whether the action space is continuous.
        """
        super(ActorCriticNetwork, self).__init__()
        
        self.continuous_actions = continuous_actions
        
        # Shared feature extractor
        self.feature_extractor = MLP(
            input_dim=input_dim,
            output_dim=hidden_dims[-1],
            hidden_dims=hidden_dims[:-1],
            activation_fn=activation_fn,
            output_activation=activation_fn,
            use_batch_norm=use_batch_norm,
            dropout_rate=dropout_rate,
        )
        
        # Value head (critic)
        self.value_head = nn.Linear(hidden_dims[-1], 1)
        
        # Policy head (actor)
        if continuous_actions:
            # For continuous actions, output mean and log_std
            self.mean_head = nn.Linear(hidden_dims[-1], action_dim)
            self.log_std_head = nn.Parameter(torch.zeros(action_dim))
        else:
            # For discrete actions, output action probabilities
            self.policy_head = nn.Linear(hidden_dims[-1], action_dim)
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass through the network.
        
        Args:
            x: Input tensor.
            
        Returns:
            Tuple of (policy_output, value). 
            For continuous actions, policy_output is (mean, log_std).
            For discrete actions, policy_output is action logits.
        """
        # Extract features
        features = self.feature_extractor(x)
        
        # Calculate value (critic output)
        value = self.value_head(features)
        
        # Calculate policy (actor output)
        if self.continuous_actions:
            mean = self.mean_head(features)
            log_std = self.log_std_head.expand_as(mean)
            policy_output = (mean, log_std)
        else:
            policy_output = self.policy_head(features)
        
        return policy_output, value
    
    def get_action_and_value(
        self, 
        x: torch.Tensor, 
        deterministic: bool = False
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Get action and value from observation.
        
        Args:
            x: Input tensor.
            deterministic: Whether to take the most likely action (True) or sample (False).
            
        Returns:
            Tuple of (action, log_prob, value).
        """
        policy_output, value = self.forward(x)
        
        if self.continuous_actions:
            mean, log_std = policy_output
            
            if deterministic:
                action = mean
                log_prob = None
            else:
                # Sample action using reparameterization trick
                std = log_std.exp()
                normal = torch.distributions.Normal(mean, std)
                action = normal.rsample()
                log_prob = normal.log_prob(action).sum(dim=-1)
        else:
            logits = policy_output
            
            if deterministic:
                action = torch.argmax(logits, dim=-1)
                log_prob = None
            else:
                # Sample action from categorical distribution
                dist = torch.distributions.Categorical(logits=logits)
                action = dist.sample()
                log_prob = dist.log_prob(action)
        
        return action, log_prob, value


class NoisyLinear(nn.Module):
    """
    Noisy Linear layer for exploration in Deep Q-Networks.
    Implements the factorized Gaussian noise approach from the NoisyNets paper.
    """
    
    def __init__(self, in_features: int, out_features: int, std_init: float = 0.5):
        """
        Initialize the NoisyLinear layer.
        
        Args:
            in_features: Input features.
            out_features: Output features.
            std_init: Initial standard deviation.
        """
        super(NoisyLinear, self).__init__()
        
        self.in_features = in_features
        self.out_features = out_features
        self.std_init = std_init
        
        # Learnable parameters
        self.weight_mu = nn.Parameter(torch.Tensor(out_features, in_features))
        self.weight_sigma = nn.Parameter(torch.Tensor(out_features, in_features))
        self.register_buffer('weight_epsilon', torch.Tensor(out_features, in_features))
        
        self.bias_mu = nn.Parameter(torch.Tensor(out_features))
        self.bias_sigma = nn.Parameter(torch.Tensor(out_features))
        self.register_buffer('bias_epsilon', torch.Tensor(out_features))
        
        self.reset_parameters()
        self.reset_noise()
    
    def reset_parameters(self):
        """
        Reset learned parameters.
        """
        mu_range = 1.0 / np.sqrt(self.in_features)
        self.weight_mu.data.uniform_(-mu_range, mu_range)
        self.weight_sigma.data.fill_(self.std_init / np.sqrt(self.in_features))
        self.bias_mu.data.uniform_(-mu_range, mu_range)
        self.bias_sigma.data.fill_(self.std_init / np.sqrt(self.out_features))
    
    def _scale_noise(self, size: int) -> torch.Tensor:
        """
        Scale noise for the factorized Gaussian noise.
        
        Args:
            size: Dimension of noise to generate.
            
        Returns:
            Scaled noise tensor.
        """
        x = torch.randn(size)
        return x.sign().mul(x.abs().sqrt())
    
    def reset_noise(self):
        """
        Reset the factorized Gaussian noise.
        """
        epsilon_in = self._scale_noise(self.in_features)
        epsilon_out = self._scale_noise(self.out_features)
        self.weight_epsilon.copy_(epsilon_out.outer(epsilon_in))
        self.bias_epsilon.copy_(epsilon_out)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass with added noise.
        
        Args:
            x: Input tensor.
            
        Returns:
            Output tensor.
        """
        if self.training:
            weight = self.weight_mu + self.weight_sigma * self.weight_epsilon
            bias = self.bias_mu + self.bias_sigma * self.bias_epsilon
        else:
            weight = self.weight_mu
            bias = self.bias_mu
        
        return F.linear(x, weight, bias) 